"""Tests for the ai-agents-config-catalog skill script flag_locator.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-config-catalog/scripts/flag_locator.py"
spec = importlib.util.spec_from_file_location("flag_locator", SCRIPT)
assert spec is not None and spec.loader is not None
flag_locator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flag_locator)


def _run(capsys, *args):
    code = flag_locator.main(list(args))
    return code, capsys.readouterr()


def test_ai_agents_config_catalog_every_flag_id_resolves_at_head(capsys):
    for flag_id in flag_locator.FLAGS:
        code, cap = _run(capsys, "--repo", str(ROOT), "locate", flag_id)
        assert code == 0, flag_id
        out = json.loads(cap.out)
        assert out["examined"] == len(flag_locator.FLAGS[flag_id]["files"])
        assert all(r["lines"] for r in out["results"])


def test_markers_lists_declared_names(capsys):
    code, cap = _run(capsys, "--repo", str(ROOT), "markers")
    names = {m["name"] for m in json.loads(cap.out)["markers"]}
    assert code == 0 and {"unit", "smoke", "windows_path"} <= names


def test_retired_clean_at_head(capsys):
    code, cap = _run(capsys, "--repo", str(ROOT), "retired")
    assert code == 0 and json.loads(cap.out)["reappeared"] == []


def test_retired_reappearing_flag_exits_1(tmp_path, capsys):
    (tmp_path / "scripts/validation").mkdir(parents=True)
    (tmp_path / "CONTRIBUTING.md").write_text("ok\nuse SKIP_PREPUSH=1\n")
    (tmp_path / "scripts/validation/pre_pr.py").write_text("x = 1\n")
    code, cap = _run(capsys, "--repo", str(tmp_path), "retired")
    out = json.loads(cap.out)
    assert code == 1 and out["reappeared"] == ["CONTRIBUTING.md:2 SKIP_PREPUSH"]


def test_locate_missing_file_exits_1(tmp_path, capsys):
    code, cap = _run(capsys, "--repo", str(tmp_path), "locate", "git-config-count")
    assert code == 1 and json.loads(cap.out)["results"][0]["exists"] is False


def test_locate_no_hit_exits_1(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/conftest.py").write_text("nothing here\n")
    code, _ = _run(capsys, "--repo", str(tmp_path), "locate", "git-config-count")
    assert code == 1


def test_locate_unknown_id_exits_2(capsys):
    code, _ = _run(capsys, "--repo", str(ROOT), "locate", "no-such-flag")
    assert code == 2


def test_locate_without_id_exits_2(capsys):
    code, _ = _run(capsys, "--repo", str(ROOT), "locate")
    assert code == 2


def test_locate_list_prints_ids(capsys):
    code, cap = _run(capsys, "--repo", str(ROOT), "locate", "--list")
    assert code == 0 and "size-exception" in json.loads(cap.out)["ids"]


def test_markers_without_pyproject_exits_2(tmp_path, capsys):
    code, _ = _run(capsys, "--repo", str(tmp_path), "markers")
    assert code == 2


def test_markers_empty_list_exits_2(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\nmarkers = []\n")
    code, _ = _run(capsys, "--repo", str(tmp_path), "markers")
    assert code == 2


def test_help_exits_0(capsys):
    code, _ = _run(capsys, "--help")
    assert code == 0


def test_locate_unreadable_file_exits_3(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/conftest.py").write_bytes(b"\xff\xfe\x00bad utf-8 \x80")
    code, cap = _run(capsys, "--repo", str(tmp_path), "locate", "git-config-count")
    err = json.loads(cap.err)
    assert code == 3 and "cannot read tests/conftest.py" in err["error"]


def test_retired_unreadable_file_exits_3(tmp_path, capsys):
    (tmp_path / "scripts/validation").mkdir(parents=True)
    (tmp_path / "CONTRIBUTING.md").write_bytes(b"\xff\xfe\x80")
    (tmp_path / "scripts/validation/pre_pr.py").write_text("x = 1\n")
    code, cap = _run(capsys, "--repo", str(tmp_path), "retired")
    err = json.loads(cap.err)
    assert code == 3 and "cannot read CONTRIBUTING.md" in err["error"]


def test_locate_accepts_exact_flag_name_alias(capsys):
    code, cap = _run(capsys, "--repo", str(ROOT), "locate", "AI_AGENTS_PYTEST_WORKERS")
    out = json.loads(cap.out)
    assert code == 0 and out["id"] == "pytest-workers"


def test_locate_alias_is_case_sensitive(capsys):
    code, _ = _run(capsys, "--repo", str(ROOT), "locate", "ai_agents_pytest_workers")
    assert code == 2
