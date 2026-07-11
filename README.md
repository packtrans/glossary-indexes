# PackTrans Glossary Indexes

Pre-built Tantivy glossary indexes for Minecraft mod translations, published monthly as GitHub releases.

See [glossary](https://github.com/packtrans/glossary) for the indexer CLI source.

## Configuration

Target languages are listed in [`languages.json`](languages.json) using the same codes as the glossary CLI (for example `zh_cn`). The monthly workflow builds one release asset per language, named `packtrans-glossary-index-{lang}-{date}.zip` (for example `packtrans-glossary-index-zh_cn-20250526.zip`).

## Manual builds

After the workflow is on the default branch, run it from **Actions → Build glossary indexes → Run workflow** (`workflow_dispatch`). The scheduled monthly run uses the same job.

## CI secrets

The [build workflow](.github/workflows/build-indexes.yml) requires `CURSEFORGE_API_KEY` only for the CurseForge `create-mod-list` step. Language file downloads use public endpoints and do not need the key.

The [CDN publish workflow](.github/workflows/publish-cdn.yml) runs after each `index-*` release is published. It uploads index (and optional dict) zip assets to S3, writes `metadata.json` for the latest three index versions, and deletes older versions from the bucket. Configure these repository secrets:

| Secret | Purpose |
| --- | --- |
| `S3_ENDPOINT` | S3-compatible API endpoint |
| `S3_ACCESS_KEY_ID` | S3 access key |
| `S3_SECRET_ACCESS_KEY` | S3 secret key |
| `S3_BUCKET` | Target bucket name |

Published metadata is served at [https://cdn.packtrans.download/glossary/metadata.json](https://cdn.packtrans.download/glossary/metadata.json). Index archives are uploaded under `glossary/indexes/{version}/packtrans-glossary-index-{lang}.zip`; optional dict archives use `glossary/dicts/{version}/`.

Run **Actions → Publish glossary CDN metadata → Run workflow** to rebuild metadata and backfill missing objects without creating a new release.
