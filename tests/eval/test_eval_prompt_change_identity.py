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


def _pinned(repo: Path, **kw: Any) -> Any:
    """Pin the inputs the way `main` does: resolve the ref, hash the bytes read."""
    args = _args(**kw)
    path = repo / args.scenarios
    return ev.pin_inputs(args, path.read_bytes() if path.exists() else None)


def test_git_mode_records_every_identity(repo: Path) -> None:
    out = ev.run_identity(_args(), "surface text", _pinned(repo))
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
    out = ev.run_identity(_args(prompt=None), "x", _pinned(repo, prompt=None))
    assert out["base_commit"] is None
    assert out["base_ref"] is None


def test_unresolvable_ref_records_none(repo: Path) -> None:
    pinned = _pinned(repo, base_ref="nope")
    assert pinned.base_commit is None
    assert ev.run_identity(_args(base_ref="nope"), "x", pinned)["base_commit"] is None


def test_missing_scenarios_file_records_none(repo: Path) -> None:
    pinned = _pinned(repo, scenarios="absent.json")
    assert pinned.scenarios_sha256 is None
    out = ev.run_identity(_args(scenarios="absent.json"), "x", pinned)
    assert out["scenarios_sha256"] is None


def test_namespace_without_paths(repo: Path) -> None:
    out = ev.run_identity(argparse.Namespace(model="m"), "x")
    assert out["scenarios_sha256"] is None
    assert out["base_commit"] is None


def test_git_failure_records_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("no git")

    monkeypatch.setattr(ev.subprocess, "run", boom)
    assert ev.resolve_base_commit("main") is None


def test_run_identity_reads_nothing_after_pinning(repo: Path) -> None:
    """A moved ref and an edited scenario file cannot change a pinned identity."""
    pinned = _pinned(repo)
    (repo / "s.json").write_text('{"scenarios": [1]}\n', encoding="utf-8")
    (repo / "f.txt").write_text("later\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "moves main")
    out = ev.run_identity(_args(), "x", pinned)
    assert out["base_commit"] == pinned.base_commit != _git(repo, "rev-parse", "main")
    assert out["scenarios_sha256"] == pinned.scenarios_sha256


def test_no_pinned_inputs_records_none(repo: Path) -> None:
    out = ev.run_identity(_args(), "x")
    assert out["base_commit"] is None
    assert out["scenarios_sha256"] is None


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
        ev._run_and_report("k", "base", "after text", [scenario], args, "src", _pinned(repo))
    assert exc.value.code == 0
    identity = json.loads(out.read_text(encoding="utf-8"))["identity"]
    assert identity["prompt_surface_sha256"] == hashlib.sha256(b"after text").hexdigest()
    assert identity["base_commit"] == _git(repo, "rev-parse", "main")


class TestIdentityIsPinnedBeforeTheModelPreflight:
    """The ref and the scenario file move after loading; the identity must not follow."""

    PROMPT = "p/SKILL.md"
    SCENARIO = {"id": "S1", "desc": "d", "input": "i", "expected_verdict": "GO"}

    def _commit_prompt(self, repo: Path, text: str) -> str:
        (repo / "p").mkdir(exist_ok=True)
        (repo / self.PROMPT).write_text(text, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "prompt")
        return _git(repo, "rev-parse", "HEAD")

    def _run_main(self, repo: Path, monkeypatch: pytest.MonkeyPatch, preflight: Any) -> dict:
        seen: list[str] = []

        def fake_multi(_k: str, prompt: str, scenario: Any, _m: str, runs: int, **_kw: Any) -> Any:
            seen.append(prompt)
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
        monkeypatch.setattr(ev, "load_api_key_for_selected_provider", lambda *_: "k")
        monkeypatch.setattr(ev, "verify_model_available", preflight)
        out = repo / "r.json"
        argv = ["prog", "--prompt", self.PROMPT, "--base-ref", "main"]
        argv += ["--scenarios", "s.json", "--output", str(out)]
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            ev.main()
        assert exc.value.code == 0
        result = json.loads(out.read_text(encoding="utf-8"))
        result["prompts_seen"] = seen
        return result

    def test_base_commit_is_the_commit_the_before_text_came_from(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loaded_sha = self._commit_prompt(repo, "BEFORE at the commit the run loaded")
        scenarios = json.dumps({"scenarios": [self.SCENARIO]}).encode()
        (repo / "s.json").write_bytes(scenarios)
        (repo / self.PROMPT).write_text("AFTER, the working copy", encoding="utf-8")

        def preflight(_key: str, _model: str) -> None:
            self._commit_prompt(repo, "BEFORE at a commit pushed during the preflight")
            (repo / self.PROMPT).write_text("AFTER, the working copy", encoding="utf-8")
            extra = {**self.SCENARIO, "id": "S2"}
            (repo / "s.json").write_text(json.dumps([self.SCENARIO, extra]), encoding="utf-8")

        result = self._run_main(repo, monkeypatch, preflight)
        identity = result["identity"]
        assert _git(repo, "rev-parse", "main") != loaded_sha
        assert identity["base_commit"] == loaded_sha
        assert identity["scenarios_sha256"] == hashlib.sha256(scenarios).hexdigest()
        assert "BEFORE at the commit the run loaded" in result["prompts_seen"]
        assert not any("pushed during the preflight" in p for p in result["prompts_seen"])


class TestIdentityPathsAreRepositoryRelative:
    """The checker compares paths as the repository spells them, not as typed."""

    def _paths(self, repo: Path, **kw: Any) -> tuple[Any, Any]:
        out = ev.run_identity(_args(**kw), "x", _pinned(repo, **kw))
        return out["prompt_path"], out["scenarios_path"]

    def test_plain_paths_are_unchanged(self, repo: Path) -> None:
        assert self._paths(repo) == ("p/SKILL.md", "s.json")

    def test_dot_slash_prefix_is_stripped(self, repo: Path) -> None:
        paths = self._paths(repo, prompt="./p/SKILL.md", scenarios="./s.json")
        assert paths == ("p/SKILL.md", "s.json")

    def test_symlinked_skill_path_resolves_to_the_real_file(self, repo: Path) -> None:
        real = repo / "src" / "claude" / "skills" / "x"
        real.mkdir(parents=True)
        (real / "SKILL.md").write_text("x\n", encoding="utf-8")
        link = repo / ".claude" / "skills" / "x"
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(Path("../../src/claude/skills/x"), target_is_directory=True)
        except OSError:
            pytest.skip("symlinks are not available")
        prompt, _ = self._paths(repo, prompt=".claude/skills/x/SKILL.md")
        assert prompt == "src/claude/skills/x/SKILL.md"

    def test_repo_local_skill_keeps_its_real_claude_path(self, repo: Path) -> None:
        local = repo / ".claude" / "skills" / "y"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("y\n", encoding="utf-8")
        prompt, _ = self._paths(repo, prompt="./.claude/skills/y/SKILL.md")
        assert prompt == ".claude/skills/y/SKILL.md"

    def test_paths_are_relative_to_the_root_not_the_cwd(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (repo / "sub").mkdir()
        monkeypatch.chdir(repo / "sub")
        paths = self._paths(repo, prompt="../p/SKILL.md", scenarios="../s.json")
        assert paths == ("p/SKILL.md", "s.json")

    def test_path_outside_the_repo_stays_as_typed(self, repo: Path) -> None:
        outside = repo.parent / "outside.json"
        outside.write_text("[]", encoding="utf-8")
        assert self._paths(repo, scenarios=str(outside))[1] == str(outside)
        assert self._paths(repo, scenarios="../outside.json")[1] == "../outside.json"

    def test_outside_a_checkout_paths_stay_as_typed(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(repo.parent)
        assert self._paths(repo, prompt="./p/SKILL.md") == ("./p/SKILL.md", "s.json")

    def test_git_failure_leaves_paths_as_typed(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_k: Any) -> None:
            raise OSError("no git")

        monkeypatch.setattr(ev.subprocess, "run", boom)
        assert self._paths(repo, prompt="./p/SKILL.md") == ("./p/SKILL.md", "s.json")
