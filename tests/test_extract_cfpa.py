from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import extract_cfpa  # noqa: E402

FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "cfpa"


def test_compare_mc_versions_orders_release_versions() -> None:
    assert extract_cfpa.compare_mc_versions("1.18", "1.12.2") > 0
    assert extract_cfpa.compare_mc_versions("1.20.1", "1.20") > 0
    assert extract_cfpa.compare_mc_versions("1.12.2", "1.12.2") == 0


def test_non_standard_version_sorts_last() -> None:
    assert extract_cfpa.compare_mc_versions("1.18", "1UNKNOWN") > 0
    assert extract_cfpa.compare_mc_versions("1UNKNOWN", "1.12.2") < 0


def test_parse_lang_file_skips_comments_and_parses_pairs() -> None:
    content = "# comment\nfoo.bar=Hello\n#PARSE_ESCAPES\nbaz=Line\\nTwo\n"
    with tempfile.NamedTemporaryFile("w", suffix=".lang", delete=False, encoding="utf-8") as handle:
        handle.write(content)
        path = Path(handle.name)
    try:
        data = extract_cfpa.parse_lang_file(path)
        assert data["foo.bar"] == "Hello"
        assert data["baz"] == "Line\nTwo"
    finally:
        path.unlink()


def test_parse_json_lang_file_rejects_nested() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump({"a": {"b": "c"}}, handle)
        path = Path(handle.name)
    try:
        assert extract_cfpa.parse_json_lang_file(path) is None
    finally:
        path.unlink()


def test_load_lang_pair_requires_same_extension(tmp_path: Path) -> None:
    lang_dir = tmp_path / "lang"
    lang_dir.mkdir()
    (lang_dir / "en_us.json").write_text('{"k":"v"}', encoding="utf-8")
    (lang_dir / "zh_cn.lang").write_text("k=译", encoding="utf-8")
    assert extract_cfpa.load_lang_pair(lang_dir) is None


def test_select_mods_skips_when_latest_version_missing_en_us() -> None:
    candidates = extract_cfpa.discover_mod_lang_dirs(FIXTURE_ROOT)
    selected = extract_cfpa.select_mods_for_extract(candidates)
    assert "demo-mod" not in selected


def test_select_mods_uses_latest_version_with_complete_pair(tmp_path: Path) -> None:
    base = tmp_path / "projects/assets/x/1.18/mymod/lang"
    base.mkdir(parents=True)
    (base / "en_us.json").write_text('{"a":"b"}', encoding="utf-8")
    (base / "zh_cn.json").write_text('{"a":"乙"}', encoding="utf-8")
    base2 = tmp_path / "projects/assets/x/1.12/mymod/lang"
    base2.mkdir(parents=True)
    (base2 / "en_us.json").write_text('{"a":"old"}', encoding="utf-8")
    (base2 / "zh_cn.json").write_text('{"a":"旧"}', encoding="utf-8")
    candidates = extract_cfpa.discover_mod_lang_dirs(tmp_path)
    selected = extract_cfpa.select_mods_for_extract(candidates)
    assert selected["mymod"].mc_version == "1.18"


def test_extract_cfpa_writes_prefixed_mod_dirs(tmp_path: Path) -> None:
    lang = tmp_path / "projects/assets/x/1.18/ok-mod/lang"
    lang.mkdir(parents=True)
    (lang / "en_us.json").write_text('{"k":"v"}', encoding="utf-8")
    (lang / "zh_cn.json").write_text('{"k":"译"}', encoding="utf-8")
    res = tmp_path / "res"
    res.mkdir()
    count = extract_cfpa.extract_cfpa(tmp_path, res)
    assert count == 1
    assert (res / "cfpa-ok-mod" / "en_us.json").is_file()
    assert (res / "cfpa-ok-mod" / "zh_cn_cfpa.json").is_file()
    zh = json.loads((res / "cfpa-ok-mod" / "zh_cn_cfpa.json").read_text(encoding="utf-8"))
    assert zh["k"] == "译"


def test_extract_cfpa_exits_when_nothing_written(tmp_path: Path) -> None:
    res = tmp_path / "res"
    res.mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit) as exc:
        extract_cfpa.extract_cfpa(empty, res)
    assert exc.value.code == 1
