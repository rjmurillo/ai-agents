"""Tests for ai-agents-validation-and-qa scripts/test_layout.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-validation-and-qa/scripts/test_layout.py"

spec = importlib.util.spec_from_file_location("test_layout", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PROSE = "Zero `*.Tests.ps1` files exist.\n"


def _repo(tmp_path: Path, doc: str | None = "Uses Pester.\n") -> Path:
    if doc is not None:
        d = tmp_path / ".agents/governance"
        d.mkdir(parents=True)
        (d / "test-location-standards.md").write_text(doc)
    (tmp_path / "prose.md").write_text(PROSE)
    return tmp_path


def _pester(repo: Path, capsys, md: str = "prose.md"):
    rc = mod.main(["--repo", str(repo), "pester", "--skill-md", str(repo / md)])
    return rc, json.loads(capsys.readouterr().out)


def test_pester_warning_live_exits_0(tmp_path, capsys):
    rc, out = _pester(_repo(tmp_path), capsys)
    assert rc == 0 and out["pester_test_files"] == 0 and not out["warning_is_dead_prose"]


def test_pester_dead_prose_exits_1(tmp_path, capsys):
    rc, out = _pester(_repo(tmp_path, doc="Python only.\n"), capsys)
    assert rc == 1 and out["warning_is_dead_prose"] is True


def test_pester_counts_files_and_skips_vendored(tmp_path, capsys):
    repo = _repo(tmp_path, doc="Python only.\n")
    (repo / "a").mkdir()
    (repo / "a/x.Tests.ps1").write_text("")
    (repo / "node_modules").mkdir()
    (repo / "node_modules/y.Tests.ps1").write_text("")
    rc, out = _pester(repo, capsys)
    assert out["pester_test_files"] == 1 and rc == 0


def test_pester_missing_skill_md_exits_2(tmp_path, capsys):
    rc, out = _pester(_repo(tmp_path), capsys, md="absent.md")
    assert rc == 2 and "error" in out


def test_pester_missing_doc_with_no_files_counts_as_dead(tmp_path, capsys):
    rc, _ = _pester(_repo(tmp_path, doc=None), capsys)
    assert rc == 1


def _skill_dir(tmp_path: Path, name: str) -> Path:
    d = tmp_path / "tests/skills" / name
    d.mkdir(parents=True)
    return d


def test_skill_tests_filesystem_lists_collectable_files(tmp_path, capsys):
    d = _skill_dir(tmp_path, "foo")
    for f in ("test_a.py", "b_test.py", "helper.py", "conftest.py"):
        (d / f).write_text("")
    rc = mod.main(["--repo", str(tmp_path), "skill-tests", "foo", "--no-pytest"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["examined"] == 2 and out["mode"] == "filesystem"
    assert all("helper" not in f and "conftest" not in f for f in out["test_files"])


def test_skill_tests_none_found_exits_1(tmp_path, capsys):
    _skill_dir(tmp_path, "foo")
    rc = mod.main(["--repo", str(tmp_path), "skill-tests", "foo", "--no-pytest"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and out["test_files"] == [] and out["dir_exists"] is True


def test_skill_tests_missing_dir_exits_1(tmp_path, capsys):
    rc = mod.main(["--repo", str(tmp_path), "skill-tests", "nope", "--no-pytest"])
    assert rc == 1 and json.loads(capsys.readouterr().out)["dir_exists"] is False


def test_skill_tests_rejects_path_traversal_name(tmp_path, capsys):
    rc = mod.main(["--repo", str(tmp_path), "skill-tests", "../x", "--no-pytest"])
    assert rc == 2


class _Proc:
    def __init__(self, rc, out):
        self.returncode, self.stdout = rc, out


def test_skill_tests_pytest_mode_parses_collect_output(tmp_path, capsys, monkeypatch):
    (tmp_path / "tests/skills/foo").mkdir(parents=True)
    out = "tests/skills/foo/test_a.py::t1\ntests/skills/foo/test_a.py::t2\n"
    out += "tests/skills/foo/test_b.py::t3\n\n3 tests collected\n"
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Proc(0, out))
    rc = mod.main(["--repo", str(tmp_path), "skill-tests", "foo"])
    res = json.loads(capsys.readouterr().out)
    assert rc == 0 and res["mode"] == "pytest" and res["examined"] == 2


def test_skill_tests_pytest_no_tests_exits_1(tmp_path, capsys, monkeypatch):
    (tmp_path / "tests/skills/foo").mkdir(parents=True)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Proc(5, "no tests\n"))
    assert mod.main(["--repo", str(tmp_path), "skill-tests", "foo"]) == 1


def test_skill_tests_pytest_collection_error_exits_3(tmp_path, monkeypatch):
    (tmp_path / "tests/skills/foo").mkdir(parents=True)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Proc(2, ""))
    assert mod.main(["--repo", str(tmp_path), "skill-tests", "foo"]) == 3


def test_skill_tests_uv_missing_exits_3(tmp_path, monkeypatch):
    (tmp_path / "tests/skills/foo").mkdir(parents=True)

    def boom(*a, **k):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    assert mod.main(["--repo", str(tmp_path), "skill-tests", "foo"]) == 3


def test_cli_help_exits_0():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "skill-tests" in r.stdout


def test_skill_tests_pytest_mode_clears_addopts(tmp_path, monkeypatch):
    (tmp_path / "tests/skills/foo").mkdir(parents=True)
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return _Proc(0, "tests/skills/foo/test_a.py::t1\n")

    monkeypatch.setattr(mod.subprocess, "run", fake)
    assert mod.main(["--repo", str(tmp_path), "skill-tests", "foo"]) == 0
    assert seen["cmd"][:3] == ["uv", "run", "pytest"] and "addopts=" in seen["cmd"]


def test_skill_tests_pytest_mode_missing_dir_exits_1_without_running_pytest(
    tmp_path, capsys, monkeypatch
):
    def boom(*a, **k):
        raise AssertionError("pytest must not run when the directory is missing")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    rc = mod.main(["--repo", str(tmp_path), "skill-tests", "foo"])
    res = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert res["dir_exists"] is False and res["test_files"] == [] and res["mode"] == "pytest"
