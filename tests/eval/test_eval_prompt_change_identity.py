"""The runner records the four ADR-127 decision 9 identities in `--output`."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
_added = str(EVAL_DIR) not in sys.path
if _added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    _spec = importlib.util.spec_from_file_location(
        "epc_identity", EVAL_DIR / "eval-prompt-change.py"
    )
    assert _spec and _spec.loader
    ev = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ev)
finally:
    if _added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    (root / "s.json").write_text('{"scenarios": []}\n', encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    monkeypatch.chdir(root)
    return root


def _args(**kw: Any) -> argparse.Namespace:
    base = {"model": "m", "prompt": "p/SKILL.md", "scenarios": "s.json", "base_ref": "main"}
    base.update(kw)
    return argparse.Namespace(**base)


def test_git_mode_records_every_identity(repo: Path) -> None:
    out = ev.run_identity(_args(), "surface text")
    assert out == {
        "prompt_path": "p/SKILL.md",
        "prompt_surface_sha256": hashlib.sha256(b"surface text").hexdigest(),
        "scenarios_path": "s.json",
        "scenarios_sha256": hashlib.sha256((repo / "s.json").read_bytes()).hexdigest(),
        "base_ref": "main",
        "base_commit": _git(repo, "rev-parse", "main"),
        "model": "m",
    }


def test_explicit_mode_has_no_base_commit(repo: Path) -> None:
    out = ev.run_identity(_args(prompt=None), "x")
    assert out["base_commit"] is None
    assert out["base_ref"] is None


def test_unresolvable_ref_records_none(repo: Path) -> None:
    assert ev.run_identity(_args(base_ref="nope"), "x")["base_commit"] is None


def test_missing_scenarios_file_records_none(repo: Path) -> None:
    assert ev.run_identity(_args(scenarios="absent.json"), "x")["scenarios_sha256"] is None


def test_namespace_without_paths(repo: Path) -> None:
    out = ev.run_identity(argparse.Namespace(model="m"), "x")
    assert out["scenarios_sha256"] is None
    assert out["base_commit"] is None


def test_git_failure_records_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("no git")

    monkeypatch.setattr(ev.subprocess, "run", boom)
    assert ev.resolve_base_commit("main") is None


def test_output_file_carries_identity(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_multi(_k: str, _p: str, scenario: Any, _m: str, runs: int, **_kw: Any) -> Any:
        per_run = [{"verdict": "GO", "passed": True, "not_scored": False}] * runs
        return {
            "scenario_id": scenario["id"],
            "passes": runs,
            "runs": runs,
            "requested_runs": runs,
            "not_scored_runs": 0,
            "pass_rate": 1.0,
            "passed": True,
            "flaky": False,
            "reason_mismatch_runs": 0,
            "per_run": per_run,
        }

    monkeypatch.setattr(ev, "run_scenario_multi", fake_multi)
    out = repo / "r.json"
    args = _args(
        runs=3, security_critical=False, base_resamples=0, max_tokens=1024, output=str(out)
    )
    scenario = {"id": "S1", "desc": "d", "input": "i", "expected_verdict": "GO"}
    with pytest.raises(SystemExit) as exc:
        ev._run_and_report("k", "base", "after text", [scenario], args, "src")
    assert exc.value.code == 0
    identity = json.loads(out.read_text(encoding="utf-8"))["identity"]
    assert identity["prompt_surface_sha256"] == hashlib.sha256(b"after text").hexdigest()
    assert identity["base_commit"] == _git(repo, "rev-parse", "main")
