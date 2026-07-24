from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

LANG_LINE = re.compile(r"^([^=]+)=(.*)$")
TARGET_LANG_FILE = "zh_cn_cfpa.json"


def is_standard_mc_version(version: str) -> bool:
    if not version:
        return False
    for part in version.split("."):
        if not part or not part.isdigit():
            return False
    return True


def _version_tuple(version: str) -> tuple[int, ...] | None:
    if not is_standard_mc_version(version):
        return None
    return tuple(int(p) for p in version.split("."))


def _version_sort_key(version: str) -> tuple:
    parts = _version_tuple(version)
    if parts is None:
        return (0, 0, (), version)
    return (1, parts, version)


def compare_mc_versions(a: str, b: str) -> int:
    ta, tb = _version_tuple(a), _version_tuple(b)
    if ta is None and tb is None:
        if a == b:
            return 0
        return 1 if a > b else -1
    if ta is None:
        return -1
    if tb is None:
        return 1
    n = max(len(ta), len(tb))
    ta_pad = ta + (0,) * (n - len(ta))
    tb_pad = tb + (0,) * (n - len(tb))
    if ta_pad < tb_pad:
        return -1
    if ta_pad > tb_pad:
        return 1
    return 0


def max_mc_version(versions: list[str]) -> str | None:
    if not versions:
        return None
    return max(versions, key=lambda v: (_version_sort_key(v), v))


def parse_lang_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    parse_escapes = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            if line == "#PARSE_ESCAPES":
                parse_escapes = True
            continue
        match = LANG_LINE.match(line)
        if not match:
            continue
        key, value = match.group(1).strip(), match.group(2)
        if parse_escapes:
            try:
                value = bytes(value, "utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                pass
        result[key] = value
    return result


def parse_json_lang_file(path: Path) -> dict[str, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return None
    return data


def load_lang_pair(lang_dir: Path) -> tuple[dict[str, str], dict[str, str]] | None:
    for ext in (".json", ".lang"):
        en_path = lang_dir / f"en_us{ext}"
        zh_path = lang_dir / f"zh_cn{ext}"
        if not en_path.is_file() or not zh_path.is_file():
            continue
        if ext == ".json":
            en_data = parse_json_lang_file(en_path)
            zh_data = parse_json_lang_file(zh_path)
        else:
            try:
                en_data = parse_lang_file(en_path)
                zh_data = parse_lang_file(zh_path)
            except OSError:
                return None
        if en_data is None or zh_data is None:
            return None
        return en_data, zh_data
    return None


@dataclass(frozen=True)
class ModCandidate:
    modid: str
    mc_version: str
    namespace: str
    lang_dir: Path


def discover_mod_lang_dirs(cfpa_root: Path) -> list[ModCandidate]:
    assets = cfpa_root / "projects" / "assets"
    if not assets.is_dir():
        return []
    out: list[ModCandidate] = []
    for namespace_dir in assets.iterdir():
        if not namespace_dir.is_dir():
            continue
        for version_dir in namespace_dir.iterdir():
            if not version_dir.is_dir():
                continue
            for mod_dir in version_dir.iterdir():
                if not mod_dir.is_dir():
                    continue
                lang_dir = mod_dir / "lang"
                if lang_dir.is_dir():
                    out.append(
                        ModCandidate(
                            modid=mod_dir.name,
                            mc_version=version_dir.name,
                            namespace=namespace_dir.name,
                            lang_dir=lang_dir,
                        )
                    )
    return out


def select_mods_for_extract(candidates: list[ModCandidate]) -> dict[str, ModCandidate]:
    by_modid: dict[str, list[ModCandidate]] = {}
    for candidate in candidates:
        by_modid.setdefault(candidate.modid, []).append(candidate)

    selected: dict[str, ModCandidate] = {}
    for modid, group in by_modid.items():
        latest = max_mc_version([c.mc_version for c in group])
        if latest is None:
            continue
        at_latest = [c for c in group if c.mc_version == latest]
        best: ModCandidate | None = None
        best_key_count = -1
        for candidate in at_latest:
            pair = load_lang_pair(candidate.lang_dir)
            if pair is None:
                continue
            _, zh = pair
            if len(zh) > best_key_count:
                best = candidate
                best_key_count = len(zh)
        if best is not None:
            selected[modid] = best
    return selected


def write_mod_output(
    res_root: Path, modid: str, en_data: dict[str, str], zh_data: dict[str, str]
) -> None:
    out_dir = res_root / f"cfpa-{modid}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "en_us.json").write_text(
        json.dumps(en_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / TARGET_LANG_FILE).write_text(
        json.dumps(zh_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def extract_cfpa(cfpa_root: Path, res_root: Path) -> int:
    candidates = discover_mod_lang_dirs(cfpa_root)
    selected = select_mods_for_extract(candidates)
    written = 0
    skipped_invalid_pair = 0
    for modid, candidate in sorted(selected.items()):
        pair = load_lang_pair(candidate.lang_dir)
        if pair is None:
            skipped_invalid_pair += 1
            print(
                f"WARN skip {modid}: missing or invalid lang pair at {candidate.lang_dir}",
                flush=True,
            )
            continue
        en_data, zh_data = pair
        write_mod_output(res_root, modid, en_data, zh_data)
        written += 1
    print(
        f"CFPA extract summary: written={written} selected={len(selected)} "
        f"skipped_invalid_pair={skipped_invalid_pair}",
        flush=True,
    )
    if written == 0:
        raise SystemExit(1)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract CFPA lang files into res/cfpa-<modid>/")
    parser.add_argument("cfpa_root", type=Path, help="Cloned CFPA repository root")
    parser.add_argument("res_root", type=Path, help="Glossary res/ output directory")
    args = parser.parse_args()
    if not args.cfpa_root.is_dir():
        raise SystemExit(f"CFPA root not found: {args.cfpa_root}")
    args.res_root.mkdir(parents=True, exist_ok=True)
    extract_cfpa(args.cfpa_root, args.res_root)


if __name__ == "__main__":
    main()
