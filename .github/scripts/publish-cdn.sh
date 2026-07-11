#!/usr/bin/env bash
set -euo pipefail

CDN_BASE_URL="${CDN_BASE_URL:-https://cdn.packtrans.download/glossary}"
S3_PREFIX="${S3_PREFIX:-glossary}"
KEEP_VERSIONS="${KEEP_VERSIONS:-3}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
S3_BUCKET="${S3_BUCKET:?S3_BUCKET is required}"
S3_ENDPOINT="${S3_ENDPOINT:?S3_ENDPOINT is required}"
AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID is required}"
AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY is required}"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

aws_s3() {
  aws s3 "$@" --endpoint-url "$S3_ENDPOINT"
}

s3_object_exists() {
  local key="$1"
  aws_s3 ls "s3://${S3_BUCKET}/${key}" >/dev/null 2>&1
}

fetch_releases_json() {
  gh api "repos/${REPO}/releases" --paginate \
    --jq '[.[] | select(.tag_name | startswith("index-"))] | sort_by(.tag_name) | reverse'
}

upload_index_asset() {
  local version="$1"
  local lang="$2"
  local local_path="$3"
  local remote_name="packtrans-glossary-index-${lang}.zip"
  local s3_key="${S3_PREFIX}/indexes/${version}/${remote_name}"
  aws_s3 cp "$local_path" "s3://${S3_BUCKET}/${s3_key}" \
    --content-type application/zip
  echo "$remote_name"
}

upload_dict_asset() {
  local version="$1"
  local remote_name="$2"
  local local_path="$3"
  local s3_key="${S3_PREFIX}/dicts/${version}/${remote_name}"
  aws_s3 cp "$local_path" "s3://${S3_BUCKET}/${s3_key}" \
    --content-type application/zip
}

upload_release_assets() {
  local version="$1"
  local release_json="$2"
  local asset_dir="${WORK_DIR}/${version}"
  mkdir -p "$asset_dir"

  echo "Uploading assets for ${version}"
  gh release download "$version" \
    --repo "$REPO" \
    --dir "$asset_dir" \
    --pattern 'packtrans-glossary-*' \
    --skip-existing

  shopt -s nullglob
  for local_path in "$asset_dir"/packtrans-glossary-*; do
    local asset_name
    asset_name="$(basename "$local_path")"

    if [[ "$asset_name" =~ ^packtrans-glossary-index-(.+)-[0-9]{8}\.zip$ ]]; then
      local lang="${BASH_REMATCH[1]}"
      upload_index_asset "$version" "$lang" "$local_path" >/dev/null
      echo "  uploaded index: ${lang}"
      continue
    fi

    if [[ "$asset_name" =~ ^packtrans-glossary-dict-(.+)\.zip$ ]]; then
      local dict_name="${BASH_REMATCH[1]}"
      local remote_name="packtrans-glossary-dict-${dict_name}.zip"
      upload_dict_asset "$version" "$remote_name" "$local_path"
      echo "  uploaded dict: ${dict_name}"
      continue
    fi

    echo "  skipped unsupported asset: ${asset_name}"
  done
  shopt -u nullglob
}

ensure_release_on_s3() {
  local version="$1"
  local release_json="$2"
  local marker_key="${S3_PREFIX}/indexes/${version}/.uploaded"

  if s3_object_exists "$marker_key"; then
    echo "${version} already present on S3"
    return 0
  fi

  local first_index
  first_index="$(jq -r --arg version "$version" '
    [.assets[]
      | select(.name | test("^packtrans-glossary-index-.+-[0-9]{8}\\.zip$"))
      | .name][0] // empty
  ' <<<"$release_json")"

  if [[ -n "$first_index" ]]; then
    local lang remote_name s3_key
    lang="$(sed -E 's/^packtrans-glossary-index-(.+)-[0-9]{8}\.zip$/\1/' <<<"$first_index")"
    remote_name="packtrans-glossary-index-${lang}.zip"
    s3_key="${S3_PREFIX}/indexes/${version}/${remote_name}"
    if s3_object_exists "$s3_key"; then
      aws_s3 cp /dev/null "s3://${S3_BUCKET}/${marker_key}"
      echo "${version} indexes already on S3"
      return 0
    fi
  fi

  echo "Backfilling ${version} from GitHub release"
  upload_release_assets "$version" "$release_json"
  aws_s3 cp /dev/null "s3://${S3_BUCKET}/${marker_key}"
}

delete_version_from_s3() {
  local version="$1"
  echo "Deleting old version from S3: ${version}"
  aws_s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/indexes/${version}/" --recursive || true
  aws_s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/dicts/${version}/" --recursive || true
}

build_metadata() {
  local releases_json="$1"
  local output_path="$2"
  local now_iso latest_version

  now_iso="$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"
  latest_version="$(jq -r ".[0].tag_name" <<<"$releases_json")"

  jq \
    --arg now "$now_iso" \
    --arg latest "$latest_version" \
    --arg cdn "$CDN_BASE_URL" \
  '
    {
      lastUpdatedAt: $now,
      latestIndexesVersion: $latest,
      indexes: [
        .[:'"$KEEP_VERSIONS"'][]
        | . as $release
        | ($release.tag_name) as $version
        | [
            $release.assets[]
            | select(.name | test("^packtrans-glossary-index-.+-[0-9]{8}\\.zip$"))
            | .name
            | capture("^packtrans-glossary-index-(?<lang>.+)-[0-9]{8}\\.zip$").lang
          ] as $langs
        | {
            version: $version,
            indexesLanguages: ($langs | sort),
            indexesFiles: (
              $langs
              | map(. as $lang
                | { key: $lang, value: ($cdn + "/indexes/" + $version + "/packtrans-glossary-index-" + $lang + ".zip") })
              | from_entries
            )
          }
      ]
    }
  ' <<<"$releases_json" >"$output_path"
}

main() {
  local releases_json
  releases_json="$(fetch_releases_json)"

  local release_count
  release_count="$(jq 'length' <<<"$releases_json")"
  if [[ "$release_count" -eq 0 ]]; then
    echo "No index releases found" >&2
    exit 1
  fi

  if [[ -n "${RELEASE_TAG:-}" ]]; then
    local release_json
    release_json="$(jq --arg tag "$RELEASE_TAG" '.[] | select(.tag_name == $tag)' <<<"$releases_json")"
    if [[ -z "$release_json" ]]; then
      echo "Release ${RELEASE_TAG} not found or is not an index release" >&2
      exit 1
    fi
    upload_release_assets "$RELEASE_TAG" "$release_json"
    aws_s3 cp /dev/null "s3://${S3_BUCKET}/${S3_PREFIX}/indexes/${RELEASE_TAG}/.uploaded"
  fi

  while IFS= read -r version; do
    [[ -z "$version" ]] && continue
    local release_json
    release_json="$(jq --arg tag "$version" '.[] | select(.tag_name == $tag)' <<<"$releases_json")"
    ensure_release_on_s3 "$version" "$release_json"
  done < <(jq -r ".[:${KEEP_VERSIONS}][] | .tag_name" <<<"$releases_json")

  local metadata_path="${WORK_DIR}/metadata.json"
  build_metadata "$releases_json" "$metadata_path"
  echo "Metadata:"
  cat "$metadata_path"

  aws_s3 cp "$metadata_path" "s3://${S3_BUCKET}/${S3_PREFIX}/metadata.json" \
    --content-type application/json \
    --cache-control "public, max-age=300"

  while IFS= read -r version; do
    [[ -z "$version" ]] && continue
    delete_version_from_s3 "$version"
  done < <(jq -r --argjson keep "$KEEP_VERSIONS" '.[$keep:][] | .tag_name' <<<"$releases_json")

  echo "Published metadata to ${CDN_BASE_URL}/metadata.json"
}

main "$@"
