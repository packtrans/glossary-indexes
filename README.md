# PackTrans Glossary Indexes

Pre-built Tantivy glossary indexes for Minecraft mod translations, published monthly as GitHub releases.

See [glossary](https://github.com/packtrans/glossary) for the indexer CLI source.

## Configuration

Target languages are listed in [`languages.json`](languages.json) using the same codes as the glossary CLI (for example `zh_cn`). The monthly workflow builds one release asset per language, named `packtrans-glossary-index-{lang}-{date}.zip` (for example `packtrans-glossary-index-zh_cn-20250526.zip`), and also attaches `languages.json` to the release.

## Manual builds

After the workflow is on the default branch, run it from **Actions → Build glossary indexes → Run workflow** (`workflow_dispatch`). The scheduled monthly run uses the same job.

## CI secrets

The [build workflow](.github/workflows/build-indexes.yml) requires `CURSEFORGE_API_KEY` only for the CurseForge `create-mod-list` step. Language file downloads use public endpoints and do not need the key.
