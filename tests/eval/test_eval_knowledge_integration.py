"""Unit tests for scripts/eval/eval-knowledge-integration.py zero-prompt handling.

Targets issue #2345: a --skill that resolves to a directory but has no prompts
in PROMPTS produces an empty results dict. apply_kill_gate({}) used to emit STOP
with an empty failures list, a false negative that hid the misconfiguration. The
fix routes empty results to a distinct NO_DATA verdict and fails fast in main()
with an actionable message naming the unprompted skill.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
SCRIPT = EVAL_DIR / "eval-knowledge-integration.py"

# eval-knowledge-integration.py imports sibling modules (_anthropic_api,
# _eval_common) via plain `from X import Y`, so EVAL_DIR must be on sys.path
# while the module loads. Scope the mutation to the load and remove it after.
_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    _spec = importlib.util.spec_from_file_location(
        "eval_knowledge_integration", SCRIPT
    )
    assert _spec and _spec.loader
    eval_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(eval_mod)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestApplyKillGateZeroData:
    def test_empty_results_returns_no_data_not_stop(self):
        gate = eval_mod.apply_kill_gate({})
        assert gate["verdict"] == "NO_DATA"
        assert gate["verdict"] != "STOP"

    def test_empty_results_is_not_passing(self):
        gate = eval_mod.apply_kill_gate({})
        assert gate["passed"] is False

    def test_empty_results_records_actionable_failure(self):
        gate = eval_mod.apply_kill_gate({})
        assert gate["failures"], "NO_DATA must carry an explanatory failure message"
        assert "No skills" in gate["failures"][0]

    def test_non_empty_results_still_reaches_proceed(self):
        results = {
            "demo": {
                "baseline": [{"accuracy": 1, "depth": 1, "specificity": 1}],
                "enhanced": [{"accuracy": 5, "depth": 5, "specificity": 5}],
            }
        }
        gate = eval_mod.apply_kill_gate(results)
        assert gate["verdict"] == "PROCEED"


class TestCliZeroPromptGuard:
    def test_registered_but_unprompted_skill_exits_config_error(self):
        # github is a real skill directory with no entry in PROMPTS.
        result = _run("--skill", "github", "--dry-run")
        assert result.returncode == 2
        assert "no prompts found" in result.stderr
        assert "github" in result.stderr
        assert "STOP" not in result.stdout

    def test_unregistered_skill_exits_one_before_guard(self):
        # A skill with no directory fails the directory check (exit 1) before
        # the prompt guard; assert the existing contract is unchanged.
        result = _run("--skill", "not-a-real-skill-xyz", "--dry-run")
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_prompted_skill_reaches_gate_not_prompt_guard(self):
        # cva-analysis has prompts in PROMPTS; a dry run passes the prompt guard
        # and reaches the kill gate. Dry-run scores are all zero, so the verdict
        # is a legitimate STOP (delta below threshold), exit 1. The key contract:
        # a prompted run never hits the zero-prompt guard and never emits NO_DATA.
        result = _run("--skill", "cva-analysis", "--dry-run")
        assert result.returncode == 1
        assert "no prompts found" not in result.stderr
        assert "STOP" in result.stderr
        assert "NO_DATA" not in result.stderr
