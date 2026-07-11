#!/usr/bin/env bash
set -euo pipefail

# Publishes glossary index release assets to S3 and maintains metadata.json
# with the latest 3 index versions.

CDN_BASE_URL="${CDN_BASE_URL:-https://cdn.packtrans.download}"
METADATA_KEY="glossary/metadata.json"
INDEXES_PREFIX="glossary/indexes"
KEEP_VERSIONS="${KEEP_VERSIONS:-3}"

VERSION_TAG="${1:?release tag required (e.g. index-20260601)}"
ASSETS_DIR="${2:?assets directory required}"

: "${S3_ENDPOINT:?S3_ENDPOINT is required}"
: "${S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID is required}"
: "${S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"

export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="${S3_REGION:-auto}"

aws_s3() {
  aws s3 "$@" --endpoint-url "$S3_ENDPOINT"
}

declare -a languages=()

for zip in "$ASSETS_DIR"/*.zip; do
  [[ -f "$zip" ]] || continue
  basename="$(basename "$zip")"

  if [[ ! "$basename" =~ ^packtrans-glossary-index-(.+)-[0-9]{8}\.zip$ ]]; then
    echo "Skipping unrecognized asset: $basename" >&2
    continue
  fi

  lang="${BASH_REMATCH[1]}"
  languages+=("$lang")

  dest_key="${INDEXES_PREFIX}/${VERSION_TAG}/packtrans-glossary-index-${lang}.zip"
  echo "Uploading ${basename} -> s3://${S3_BUCKET}/${dest_key}"
  aws_s3 cp "$zip" "s3://${S3_BUCKET}/${dest_key}" \
    --content-type "application/zip" \
    --cache-control "public, max-age=3600"
done

if [[ "${#languages[@]}" -eq 0 ]]; then
  echo "No glossary index zip assets found in ${ASSETS_DIR}" >&2
  exit 1
fi

IFS=$'\n' languages=($(printf '%s\n' "${languages[@]}" | sort -u))
unset IFS

langs_json="$(printf '%s\n' "${languages[@]}" | jq -R . | jq -s .)"

files_json="$(jq -n \
  --arg version "$VERSION_TAG" \
  --arg cdn "$CDN_BASE_URL" \
  --argjson langs "$langs_json" \
  '$langs | map({
    key: .,
    value: ($cdn + "/glossary/indexes/" + $version + "/packtrans-glossary-index-" + . + ".zip")
  }) | from_entries')"

new_entry="$(jq -n \
  --arg version "$VERSION_TAG" \
  --argjson langs "$langs_json" \
  --argjson files "$files_json" \
  '{
    version: $version,
    indexesLanguages: $langs,
    indexesFiles: $files
  }')"

metadata_file="$(mktemp)"
if aws_s3 cp "s3://${S3_BUCKET}/${METADATA_KEY}" "$metadata_file" 2>/dev/null; then
  echo "Loaded existing metadata.json"
else
  echo '{"indexes":[]}' > "$metadata_file"
fi

updated_metadata="$(jq \
  --argjson entry "$new_entry" \
  --argjson keep "$KEEP_VERSIONS" \
  --arg now "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" \
  '
    .indexes = ([$entry] + (.indexes // [] | map(select(.version != $entry.version))))
      | .indexes = (.indexes | sort_by(.version) | reverse | .[:$keep])
      | .lastUpdatedAt = $now
      | .latestIndexesVersion = .indexes[0].version
  ' "$metadata_file")"

echo "$updated_metadata" | jq . > "$metadata_file"

echo "Uploading metadata.json -> s3://${S3_BUCKET}/${METADATA_KEY}"
aws_s3 cp "$metadata_file" "s3://${S3_BUCKET}/${METADATA_KEY}" \
  --content-type "application/json" \
  --cache-control "public, max-age=300"

kept_versions="$(jq -r '.indexes[].version' "$metadata_file")"
echo "Keeping versions:"
echo "$kept_versions"

while IFS= read -r prefix; do
  [[ -n "$prefix" ]] || continue
  version="${prefix%/}"
  version="${version##*/}"

  if grep -qx "$version" <<< "$kept_versions"; then
    continue
  fi

  delete_prefix="${INDEXES_PREFIX}/${version}/"
  echo "Deleting old version from S3: ${delete_prefix}"
  aws_s3 rm --recursive "s3://${S3_BUCKET}/${delete_prefix}" || true
done < <(aws_s3 ls "s3://${S3_BUCKET}/${INDEXES_PREFIX}/" | awk '{print $2}')

echo "Publish complete."
