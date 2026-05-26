# PackTrans Glossary Indexes

Pre-built Tantivy glossary indexes for Minecraft mod translations, published monthly as GitHub releases.

See [glossary](https://github.com/packtrans/glossary) for the indexer CLI source.

## Configuration

Target languages are listed in [`languages.json`](languages.json) using the same codes as the glossary CLI (for example `zh_cn`). The monthly workflow builds one release asset per language, named `packtrans-glossary-index-{lang}-{date}.zip` (for example `packtrans-glossary-index-zh_cn-20250526.zip`).

## CI secrets

The [build workflow](.github/workflows/build-indexes.yml) requires `CURSEFORGE_API_KEY` for CurseForge mod list and download steps.
