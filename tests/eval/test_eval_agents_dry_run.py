"""Unit tests for scripts/eval/eval-agents.py dry-run zero-score semantics.

Targets issue #2441: `eval-suite.py --scope agents --dry-run` exits 1 with
"FAIL" purely because dry-run produces all-zero placeholder scores and the
weak-spot gate (overall < 3.5) catches every agent. A dry-run that did no
real scoring is not a failed evaluation: it is a successful preflight, and
nonzero exits must carry an actionable reason.

Mirrors the contract test pattern established for issue #2345 in the skills
path (see tests/eval/test_eval_knowledge_integration.py and the NO_DATA
verdict in scripts/eval/eval-knowledge-integration.py).

Contract under test:
- `decide_dry_run_exit` returns (exit_code, reason) given the dry-run
  output dict. Real-data zero-prompt configuration errors stay nonzero
  with an actionable reason; dry-run-only zero scores exit 0.
- `eval-agents.py --agent <real> --dry-run` exits 0 (not 1) and never
  emits a weak-spot table in dry-run mode.
- `eval-agents.py --agent <missing> --dry-run` still exits 1 (config
  error: agent file not found). The dry-run shortcut never masks real
  configuration errors.
- `eval-suite.py --scope agents --dry-run` does not exit 1 solely because
  no scored evaluation ran. End-to-end, the dry-run preflight stays green.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
AGENTS_SCRIPT = EVAL_DIR / "eval-agents.py"
SUITE_SCRIPT = EVAL_DIR / "eval-suite.py"
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")

# eval-agents.py imports sibling modules (_anthropic_api, _eval_common) via
# plain `from X import Y`, so EVAL_DIR must be on sys.path while the module
# loads. Scope the mutation to the load and remove it after.
_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    _spec = importlib.util.spec_from_file_location("eval_agents", AGENTS_SCRIPT)
    assert _spec and _spec.loader
    eval_agents = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(eval_agents)
    _suite_spec = importlib.util.spec_from_file_location("eval_suite", SUITE_SCRIPT)
    assert _suite_spec and _suite_spec.loader
    eval_suite = importlib.util.module_from_spec(_suite_spec)
    _suite_spec.loader.exec_module(eval_suite)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


def _clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    for var in GIT_ENV_VARS:
        env.pop(var, None)
    return env


def _run_agents(*args: str) -> subprocess.CompletedProcess[str]:
    """Run eval-agents.py with a stripped env to keep dry-run hermetic."""
    return subprocess.run(
        [sys.executable, str(AGENTS_SCRIPT), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=str(REPO_ROOT),
        env=_clean_subprocess_env(),
    )


def _run_suite(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SUITE_SCRIPT), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(REPO_ROOT),
        env=env if env is not None else _clean_subprocess_env(),
    )


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in `cwd` with a stripped env, raising on failure."""
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env=_clean_subprocess_env(),
    )


@contextmanager
def _temp_git_repo() -> Iterator[Path]:
    """Yield a fresh git repo with one commit and a clean index.

    eval-suite's detect_changed_files hardcodes cwd=REPO_ROOT, so the diff
    always runs against the developer checkout unless git is redirected by
    env vars. Pair this fixture with _suite_env to point that diff at an
    isolated repo whose state the test owns (issue #3138).
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git(["init", "-q"], repo)
        (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(["add", "seed.txt"], repo)
        _git(
            [
                "-c", "user.email=eval@test",
                "-c", "user.name=eval",
                "-c", "commit.gpgsign=false",
                "commit", "-q", "-m", "seed",
            ],
            repo,
        )
        yield repo


def _suite_env(repo: Path) -> dict[str, str]:
    """Env that redirects eval-suite's git queries to `repo`."""
    env = _clean_subprocess_env()
    git_dir = repo / ".git"
    env["GIT_DIR"] = str(git_dir)
    env["GIT_WORK_TREE"] = str(repo)
    env["GIT_INDEX_FILE"] = str(git_dir / "index")
    return env


class TestDecideDryRunExit:
    """Pure unit tests for the dry-run exit decision."""

    def test_dry_run_zero_scores_exits_zero(self):
        """All-zero scores from a dry run are expected, not a failure."""
        output = {
            "dry_run": True,
            "agents_assessed": ["architect"],
            "results": {
                "architect": {
                    "avg_scores": {
                        "role_adherence": 0,
                        "actionability": 0,
                        "quality": 0,
                        "appropriateness": 0,
                    },
                    "overall": 0.0,
                }
            },
        }
        exit_code, reason = eval_agents.decide_dry_run_exit(output)
        assert exit_code == 0
        # Reason must be informative, not silent
        assert reason
        assert "dry-run" in reason.lower() or "dry run" in reason.lower()

    def test_real_run_weak_agents_exits_one(self):
        """Real-data low scores still fail (no regression of the gate)."""
        output = {
            "dry_run": False,
            "agents_assessed": ["weakling"],
            "results": {
                "weakling": {
                    "avg_scores": {
                        "role_adherence": 2,
                        "actionability": 1,
                        "quality": 2,
                        "appropriateness": 1,
                    },
                    "overall": 1.5,
                }
            },
        }
        exit_code, reason = eval_agents.decide_dry_run_exit(output)
        assert exit_code == 1
        assert reason

    def test_real_run_null_overall_exits_one(self):
        """Real-data null overall scores are treated as weak scores."""
        output = {
            "dry_run": False,
            "agents_assessed": ["null-score"],
            "results": {"null-score": {"overall": None}},
        }
        exit_code, reason = eval_agents.decide_dry_run_exit(output)
        assert exit_code == 1
        assert "null-score" in reason

    def test_dry_run_no_agents_assessed_exits_one_with_config_reason(self):
        """Empty agent list in dry-run is a config error, not silent pass."""
        output = {
            "dry_run": True,
            "agents_assessed": [],
            "results": {},
        }
        exit_code, reason = eval_agents.decide_dry_run_exit(output)
        assert exit_code == 1
        # Must name the missing piece so the operator can fix it
        assert reason
        assert "no agent" in reason.lower() or "agents_assessed" in reason.lower()


class TestEvalAgentsCli:
    def test_dry_run_real_agent_exits_zero(self):
        """End-to-end: --dry-run on a real agent must exit 0 (issue #2441)."""
        # `architect` is a real agent with prompts in PROMPTS (verified at
        # test-collection time via the imported module).
        assert "architect" in eval_agents.PROMPTS, (
            "Test precondition: architect agent must be registered in PROMPTS"
        )
        result = _run_agents("--agent", "architect", "--dry-run")
        assert result.returncode == 0, (
            f"Expected dry-run exit 0; got {result.returncode}.\n"
            f"stderr: {result.stderr[-500:]}"
        )
        # Must explicitly signal dry-run completion, not silently exit
        assert "dry-run" in result.stderr.lower() or "dry run" in result.stderr.lower()

    def test_dry_run_no_weak_spot_table(self):
        """Dry-run zero scores must not surface as 'BELOW THRESHOLD' alarm."""
        result = _run_agents("--agent", "architect", "--dry-run")
        # The weak-spot table is the false-positive symptom users see in 2441.
        assert "BELOW THRESHOLD" not in result.stderr, (
            "Dry-run all-zero scores must not be flagged as below-threshold "
            "weak spots (issue #2441)."
        )

    def test_dry_run_missing_agent_still_exits_one(self):
        """Config errors must remain loud even in dry-run mode."""
        result = _run_agents("--agent", "not-a-real-agent-xyz", "--dry-run")
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()


class TestEvalSuiteAgentsDryRun:
    """End-to-end suite tests, isolated from the developer checkout.

    detect_changed_files (scripts/eval/eval-suite.py) hardcodes cwd=REPO_ROOT
    and diffs HEAD against the working tree plus the index, so `--base-ref HEAD`
    does NOT mean `HEAD..HEAD`: staged or unstaged changes in the outer checkout
    (an in-progress merge, for example) leak into the diff. These tests redirect
    the suite's git queries to a throwaway repo via GIT_DIR / GIT_WORK_TREE /
    GIT_INDEX_FILE so the diff reflects the fixture, not the checkout (issue #3138).
    """

    def test_suite_agents_dry_run_does_not_fail_on_zero_scores(self):
        """Empty diff yields a green dry-run (issue #2441 acceptance criterion 1).

        A clean index against HEAD produces no changed files, so the classifier
        returns nothing and the suite exits 0 without scoring anything. Isolated
        per issue #3138 so outer-repo state cannot force a false failure.
        """
        with _temp_git_repo() as repo:
            result = _run_suite(
                "--scope", "agents", "--dry-run", "--base-ref", "HEAD",
                env=_suite_env(repo),
            )
        assert result.returncode == 0, (
            f"Suite dry-run with empty diff must exit 0; got "
            f"{result.returncode}. stderr: {result.stderr[-500:]}"
        )

    def test_suite_classifies_staged_agent_files(self):
        """Staged agent files route to the agent classifier (issue #3138).

        The empty-diff isolation must not hide real changes. Stage an agent
        definition in the fixture repo and prove the suite classifies it as an
        agent. Classification comes from the isolated git diff, so it stays
        independent of the developer checkout.

        The suite exit code is intentionally not asserted. eval-agents resolves
        the agent file from AGENTS_DIR (its own __file__ path, the real
        checkout), not from the fixture, so a returncode check would couple this
        test back to the outer-repo state that issue #3138 exists to remove. The
        eval-agents exit contract is covered by TestEvalAgentsCli.
        """
        agent_rel = ".claude/agents/architect.md"
        with _temp_git_repo() as repo:
            agent_path = repo / agent_rel
            agent_path.parent.mkdir(parents=True, exist_ok=True)
            agent_path.write_text("# architect\n", encoding="utf-8")
            _git(["add", agent_rel], repo)
            out_file = repo / ".git" / "eval-out.json"
            _run_suite(
                "--scope", "agents", "--dry-run", "--base-ref", "HEAD",
                "--output", str(out_file),
                env=_suite_env(repo),
            )
            output = json.loads(out_file.read_text(encoding="utf-8"))

        assert agent_rel in output["classification"]["agents"], (
            f"Staged agent file must be classified as an agent; "
            f"classification: {output.get('classification')}"
        )

    def test_invalid_base_ref_exits_config(self):
        result = _run_suite(
            "--scope", "agents",
            "--dry-run",
            "--base-ref", "definitely-not-a-real-ref",
        )

        assert result.returncode == 2
        assert "git diff against definitely-not-a-real-ref failed" in result.stderr

    def test_malformed_behavioral_child_output_is_external_failure(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "not json"
            stderr = ""

        monkeypatch.setattr(eval_suite.subprocess, "run", lambda *_args, **_kwargs: _Result())
        result = eval_suite.run_behavioral_for_prompt(
            "prompt.md", "scenarios.json", "HEAD", False, "model", False
        )

        assert result["passed"] is False
        assert result["exit_code"] == 3

    def test_malformed_agent_child_output_is_external_failure(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "not json"
            stderr = ""

        monkeypatch.setattr(eval_suite.subprocess, "run", lambda *_args, **_kwargs: _Result())
        result = eval_suite.run_agent_quality([".claude/agents/demo.md"], "model", False)

        assert result["passed"] is False
        assert result["agents"]["demo"]["passed"] is False
        assert result["agents"]["demo"]["exit_code"] == 3

    def test_malformed_skill_child_output_is_external_failure(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "[1, 2, 3]"
            stderr = ""

        monkeypatch.setattr(eval_suite.subprocess, "run", lambda *_args, **_kwargs: _Result())
        result = eval_suite.run_skill_knowledge(
            [".claude/skills/demo/SKILL.md"], "model", False
        )

        assert result["passed"] is False
        assert result["skills"]["demo"]["passed"] is False
        assert result["skills"]["demo"]["exit_code"] == 3
