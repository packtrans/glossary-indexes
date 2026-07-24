# zh_cn_cfpa Glossary Index Design

## Summary

Add a **`zh_cn_cfpa`** target language to [packtrans/glossary-indexes](https://github.com/packtrans/glossary-indexes): a Tantivy glossary index built **only** from [CFPAOrg/Minecraft-Mod-Language-Package](https://github.com/CFPAOrg/Minecraft-Mod-Language-Package), published alongside existing `zh_cn` / `zh_tw` / `zh_hk` / `ja_jp` indexes. Translators query CFPA-specific terminology via `packtrans-glossary query --lang zh_cn_cfpa`.

## Goals

- Separate corpus from platform-sourced `zh_cn` (Modrinth / CurseForge / Minecraft jars).
- No changes to `packtrans/glossary` CLI for v1.
- Keep `languages.json` as a **plain string array** (add `"zh_cn_cfpa"` only).
- Single scan directory **`res/`** for all languages.

## Non-goals

- Full CFPA packer fidelity (`packer-policy.json`, nested JSON resources, `.local` / `.hl`, composition rules).
- Replacing or merging into existing `zh_cn` index data.
- Consuming [CFPATools/i18n-dict](https://github.com/CFPATools/i18n-dict) as a data source.

## Requirements (from design review)

| Decision | Choice |
|----------|--------|
| Purpose | Separate glossary index alongside `zh_cn` |
| Data source | CFPA repo only |
| Version selection | Latest MC version per modid |
| Extraction scope | Simple `lang/en_us.*` + `lang/zh_cn.*` pairs only |
| Missing `en_us` on latest version | Skip mod |
| Mod layout in `res/` | `cfpa-{modid}/` prefix; always write CFPA `en_us` + `zh_cn_cfpa` |

## Architecture

```
CFPA repo (shallow clone, main)
        │
        ▼
  extract_cfpa.py
        │  scan projects/assets/*/{mc_version}/{modid}/lang/
        │  pick latest MC version with both en_us and zh_cn
        ▼
  res/cfpa-<modid>/
    en_us.json
    zh_cn_cfpa.json
        │
        ▼  (after Modrinth/CurseForge/Minecraft downloads into res/<modid>/)
  packtrans-glossary-builder index --scan-dir res --lang zh_cn_cfpa --out indexes
        │
        ▼
  dist/packtrans-glossary-index-zh_cn_cfpa-{date}.zip
        │
        ▼
  GitHub Release + S3 CDN (existing publish-metadata flow)
```

Existing mod download steps are unchanged. CFPA extraction runs **after** downloads and only adds `res/cfpa-*` directories.

## Extraction logic (`extract_cfpa.py`)

**Location:** `.github/scripts/extract_cfpa.py`

**Inputs:** Path to cloned CFPA repo root, path to `res/` output root.

**Scan pattern:** `projects/assets/*/{mc_version}/{modid}/lang/`

**Per modid:**

1. Collect all `(mc_version, namespace, path)` where `lang/en_us` and `lang/zh_cn` exist (as `.json` or `.lang`, same extension for both).
2. Select the **latest** `mc_version` (numeric segment comparison: `1.20.1` > `1.18` > `1.12.2`; non-standard labels such as `1UNKNOWN` sort last).
3. If the latest version folder does not have **both** files, skip the mod.
4. Write to `res/cfpa-{modid}/en_us.json` and `res/cfpa-{modid}/zh_cn_cfpa.json`.

**File handling:**

| Input | Action |
|-------|--------|
| `en_us.json` + `zh_cn.json` | Parse JSON; write normalized JSON |
| `en_us.lang` + `zh_cn.lang` | Parse key=value (skip `#` comments; basic escapes); write JSON |
| Mixed extensions | Skip mod |
| Malformed file | Warn; skip mod |

**Duplicate modid at same latest version across namespaces:** Keep the copy with more translation keys; log a warning.

**Keys:** Flat string map only (top-level JSON object or `.lang` lines). Nested JSON objects are out of scope for v1; skip or flatten-not-supported — **skip mod** if `zh_cn.json` / `en_us.json` root is not a flat object of strings.

## Configuration

**`languages.json`** — add one entry, format unchanged:

```json
[
  "zh_cn",
  "zh_tw",
  "zh_hk",
  "ja_jp",
  "zh_cn_cfpa"
]
```

Build loop continues to use `jq -r '.[]'` and `--scan-dir res` for every language.

## Workflow changes (`build-indexes.yml`)

New steps after **Download language files**, before **Build indexes and package releases**:

1. **Checkout CFPA** — shallow clone `CFPAOrg/Minecraft-Mod-Language-Package` ref `main` into `cfpa-src/` (depth 1).
2. **Extract CFPA** — `python3 .github/scripts/extract_cfpa.py cfpa-src res`

No `scan_dir` branching in the index step.

## Error handling

| Situation | Behavior |
|-----------|----------|
| Malformed `.lang` / `.json` | Warning + skip mod |
| Latest version missing pair | Skip mod |
| CFPA clone failure | Fail job |
| Zero mods extracted | Fail job with explicit error |
| Index build | Existing CLI behavior (skip mods without both langs) |

End-of-run summary: counts for written mods, skipped mods (by reason), warnings.

## Licensing

CFPA translation data is [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Document attribution in README and/or GitHub release notes for the `zh_cn_cfpa` asset. PackTrans index packaging remains MIT; the **indexed content** carries CFPA license terms.

## Testing

- **Unit tests:** Fixtures under `tests/fixtures/cfpa/` covering version ordering, skip rules, `.lang` conversion, `cfpa-` paths, namespace duplicate resolution.
- **CI:** Run unit tests on pull requests; full index build on schedule / `workflow_dispatch`.
- **Manual:** Shallow clone CFPA locally, extract, `packtrans-glossary-builder index`, `packtrans-glossary query --lang zh_cn_cfpa`.

## Scale estimate

~6,700 `zh_cn` files exist across many MC versions in CFPA. After latest-version deduplication and requiring paired `en_us` in that version, expect on the order of **1,500–2,500** `cfpa-*` mod directories (approximate).

## Future enhancements (out of scope)

- Cache CFPA checkout by commit SHA in Actions.
- Deeper CFPA resource types (packer policies, nested JSON).
- Optional `packtrans-glossary-builder download --platform cfpa`.
