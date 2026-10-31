"""Tests for the ai-agents-failure-archaeology corpus_index.py script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-failure-archaeology/scripts/corpus_index.py"

spec = importlib.util.spec_from_file_location("corpus_index", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FM = """# FM

## Index

| # | Pattern | Severity | Primary Evidence |
|---|---------|----------|------------------|
| 1 | First thing | High | `a.md` |
| 2 | Second thing | Low | `b.md` |

## 1. First Thing
"""


def make_repo(tmp_path: Path, index_names: list[str], retros: list[str]) -> Path:
    r = tmp_path / ".project-toolkit/retrospective"
    r.mkdir(parents=True)
    for n in retros:
        (r / n).write_text("x")
    (r / "INDEX.md").write_text("\n".join(index_names))
    g = tmp_path / ".agents/governance"
    g.mkdir(parents=True)
    (g / "FAILURE-MODES.md").write_text(FM)
    m = tmp_path / ".serena/memories"
    m.mkdir(parents=True)
    (m / "one.md").write_text("m")
    (m / "two.md").write_text("m")
    return tmp_path


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_ai_agents_failure_archaeology_positive_all_indexed(tmp_path):
    repo = make_repo(tmp_path, ["a.md", "b.md"], ["a.md", "b.md"])
    r = run("--repo", str(repo))
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert out["retro_files"] == 2 and out["retro_index_covered"] == 2
    assert out["failure_mode_count"] == 2
    assert out["failure_modes"][0] == {"n": 1, "name": "First thing"}
    assert out["memory_files"] == 2
    assert out["examined"] == 6


def test_negative_unindexed_retro_exits_1(tmp_path):
    repo = make_repo(tmp_path, ["a.md"], ["a.md", "b.md"])
    r = run("--repo", str(repo))
    out = json.loads(r.stdout)
    assert r.returncode == 1
    assert out["retro_index_missing"] == [".project-toolkit/retrospective/b.md"]


def test_edge_missing_dirs_exit_2(tmp_path):
    r = run("--repo", str(tmp_path))
    assert r.returncode == 2
    assert "error" in json.loads(r.stdout)


def test_edge_heading_fallback_when_no_index_table():
    text = "## 1. Alpha\nbody\n## 2. Beta\n"
    assert mod.parse_failure_modes(text) == [{"n": 1, "name": "Alpha"}, {"n": 2, "name": "Beta"}]


def test_shas_resolve_against_temp_git_repo(tmp_path):
    repo = make_repo(tmp_path, ["a.md"], ["a.md"])
    env = ["-c", "user.email=t@t", "-c", "user.name=t", "-C", str(repo)]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", *env, "add", "-A"], check=True)
    subprocess.run(["git", *env, "commit", "-qm", "x"], check=True)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    out = json.loads(run("--repo", str(repo), "--shas", head, "deadbee").stdout)
    assert out["shas"] == {head: True, "deadbee": False}


def test_shas_git_missing_exits_3(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, ["a.md"], ["a.md"])

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    assert mod.main(["--repo", str(repo), "--shas", "abc"]) == 3


def test_help_works():
    assert run("--help").returncode == 0
