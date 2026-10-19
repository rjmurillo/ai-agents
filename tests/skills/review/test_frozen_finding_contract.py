"""Frozen finding contract for review rounds after the first (issue #6745).

Round caps bound cost, not scope. From round 2 on, only a defect the diff
introduced or an unmet acceptance criterion may count. Everything else is a
flagged note that never reaches the verdict.

Three layers:
- ``validate_findings_scope.py --frozen`` turns an all-out-of-scope verdict
  into PASS (unit and end-to-end with a real git repo and ``merge_verdicts``).
- The rendered ``review`` skill states the contract and keeps its caps.
- ``pr-review`` and ``pr-comment-responder`` carry the same contract through
  the review-conversation protocol.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not installed")

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
for _entry in (TESTS_SKILLS_DIR, str(PROJECT_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from claude_skills_import import import_skill_script

from scripts.ai_review_common import merge_verdicts

mod = import_skill_script(
    ".claude/skills/review/scripts/validate_findings_scope.py",
    module_name="validate_findings_scope_frozen",
)
SCRIPT_PATH = (
    PROJECT_ROOT / ".claude" / "skills" / "review" / "scripts" / "validate_findings_scope.py"
)

_DIFF_FILES = ["src/new_feature.py"]

_PRE_EXISTING_ONLY = """\
severity: CRITICAL
category: error-handling
location: legacy/old_module.py:12
recommendation: validate the input

Verdict: CRITICAL_FAIL
"""

_DIFF_INTRODUCED = """\
severity: CRITICAL
category: error-handling
location: src/new_feature.py:7
recommendation: validate the input

Verdict: CRITICAL_FAIL
"""

_MIXED = _PRE_EXISTING_ONLY.replace("Verdict: CRITICAL_FAIL\n", "") + _DIFF_INTRODUCED


class TestFrozenVerdict:
    def test_pre_existing_only_becomes_pass_when_frozen(self) -> None:
        assert mod.scope_adjusted_verdict(_PRE_EXISTING_ONLY, _DIFF_FILES, frozen=True) == "PASS"

    def test_round_one_keeps_the_warn_downgrade(self) -> None:
        """Negative control: the frozen mode is the only thing that returns PASS."""
        assert mod.scope_adjusted_verdict(_PRE_EXISTING_ONLY, _DIFF_FILES) == "WARN"

    @pytest.mark.parametrize("token", ["WARN", "PARTIAL", "FAIL", "NEEDS_REVIEW", "REJECTED"])
    def test_every_counting_verdict_becomes_pass_when_frozen(self, token: str) -> None:
        text = _PRE_EXISTING_ONLY.replace("CRITICAL_FAIL", token)
        assert mod.scope_adjusted_verdict(text, _DIFF_FILES, frozen=True) == "PASS"

    def test_unknown_stays_unknown_when_frozen(self) -> None:
        text = _PRE_EXISTING_ONLY.replace("CRITICAL_FAIL", "UNKNOWN")
        assert mod.scope_adjusted_verdict(text, _DIFF_FILES, frozen=True) == "UNKNOWN"

    def test_diff_introduced_defect_still_blocks_when_frozen(self) -> None:
        assert (
            mod.scope_adjusted_verdict(_DIFF_INTRODUCED, _DIFF_FILES, frozen=True)
            == "CRITICAL_FAIL"
        )

    def test_mixed_output_keeps_its_verdict_when_frozen(self) -> None:
        assert mod.scope_adjusted_verdict(_MIXED, _DIFF_FILES, frozen=True) == "CRITICAL_FAIL"

    def test_no_verdict_line_returns_none(self) -> None:
        assert (
            mod.scope_adjusted_verdict("location: legacy/a.py:1", _DIFF_FILES, frozen=True) is None
        )

    def test_empty_diff_never_downgrades(self) -> None:
        assert mod.scope_adjusted_verdict(_PRE_EXISTING_ONLY, [], frozen=True) == "CRITICAL_FAIL"


class TestDiffCausedRegression:
    """A regression the diff causes in an untouched file still counts."""

    _TAGGED = _PRE_EXISTING_ONLY.replace(
        "location: legacy/old_module.py:12", "location: legacy/old_module.py:12 [diff-caused]"
    )

    def test_tagged_regression_keeps_its_verdict_when_frozen(self) -> None:
        assert mod.scope_adjusted_verdict(self._TAGGED, _DIFF_FILES, frozen=True) == "CRITICAL_FAIL"

    def test_untagged_twin_is_demoted_when_frozen(self) -> None:
        """Negative control: the tag is the only difference."""
        assert mod.scope_adjusted_verdict(_PRE_EXISTING_ONLY, _DIFF_FILES, frozen=True) == "PASS"

    def test_tag_is_ignored_in_round_one(self) -> None:
        assert mod.scope_adjusted_verdict(self._TAGGED, _DIFF_FILES) == "WARN"

    def test_tagged_line_is_not_marked_pre_existing(self) -> None:
        out = mod.format_scope_checked_text(self._TAGGED, _DIFF_FILES, frozen=True)
        assert "[pre-existing - not in this PR diff]" not in out
        assert "Verdict: CRITICAL_FAIL" in out


class TestFrozenText:
    def test_text_marks_location_and_says_flagged(self) -> None:
        out = mod.format_scope_checked_text(_PRE_EXISTING_ONLY, _DIFF_FILES, frozen=True)
        assert "[pre-existing - not in this PR diff]" in out
        assert "Verdict: PASS" in out
        assert "flagged notes" in out
        assert "do not count toward the verdict" in out

    def test_round_one_text_keeps_the_original_wording(self) -> None:
        out = mod.format_scope_checked_text(_PRE_EXISTING_ONLY, _DIFF_FILES)
        assert "Verdict: WARN" in out
        assert "downgraded to WARN" in out
        assert "flagged notes" not in out


def _git(args: list[str], cwd: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Frozen Test",
        "GIT_AUTHOR_EMAIL": "frozen-test@example.com",
        "GIT_COMMITTER_NAME": "Frozen Test",
        "GIT_COMMITTER_EMAIL": "frozen-test@example.com",
    }
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"


@pytest.fixture
def pr_repo(tmp_path: Path) -> Path:
    """A repo whose PR branch adds src/new_feature.py and leaves legacy/ alone."""
    repo = tmp_path / "repo"
    (repo / "legacy").mkdir(parents=True)
    _git(["init", "-b", "main", str(repo)], tmp_path)
    (repo / "legacy" / "old_module.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)
    _git(["update-ref", "refs/remotes/origin/main", "HEAD"], repo)
    _git(["switch", "-c", "pr-branch"], repo)
    (repo / "src").mkdir()
    (repo / "src" / "new_feature.py").write_text("def g(x):\n    return x\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "feature"], repo)
    return repo


def _run_cli(repo: Path, text: str, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--worktree",
            str(repo),
            "--base-branch",
            "main",
            "--emit-adjusted-text",
            *flags,
        ],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _verdict_of(stdout: str) -> str:
    verdict = mod.extract_verdict(stdout)
    assert verdict is not None, f"no verdict in:\n{stdout}"
    return verdict


@_needs_git
class TestLaterRoundDoesNotBlockOnPreExistingDefect:
    """Issue #6745 acceptance: a later round does not block on a pre-existing defect."""

    def test_round_two_final_verdict_is_pass(self, pr_repo: Path) -> None:
        result = _run_cli(pr_repo, _PRE_EXISTING_ONLY, "--frozen")
        assert result.returncode == 1, "out-of-scope locations still exit 1 (ADR-035)"
        assert "legacy/old_module.py" in result.stderr
        assert merge_verdicts([_verdict_of(result.stdout), "PASS", "PASS"]) == "PASS"

    def test_round_one_same_text_still_warns(self, pr_repo: Path) -> None:
        result = _run_cli(pr_repo, _PRE_EXISTING_ONLY)
        assert merge_verdicts([_verdict_of(result.stdout), "PASS", "PASS"]) == "WARN"

    def test_round_two_regression_in_untouched_file_still_blocks(self, pr_repo: Path) -> None:
        text = _PRE_EXISTING_ONLY.replace("old_module.py:12", "old_module.py:12 [diff-caused]")
        result = _run_cli(pr_repo, text, "--frozen")
        assert "[pre-existing - not in this PR diff]" not in result.stdout
        assert merge_verdicts([_verdict_of(result.stdout), "PASS"]) == "CRITICAL_FAIL"

    def test_round_two_defect_in_the_diff_still_blocks(self, pr_repo: Path) -> None:
        result = _run_cli(pr_repo, _DIFF_INTRODUCED, "--frozen")
        assert result.returncode == 0
        assert merge_verdicts([_verdict_of(result.stdout), "PASS"]) == "CRITICAL_FAIL"

    def test_round_two_defect_in_a_fix_commit_still_blocks(self, pr_repo: Path) -> None:
        """A fix commit after round 1 is part of the PR diff, so its defects count."""
        (pr_repo / "src" / "fix.py").write_text("def h(x):\n    return x\n", encoding="utf-8")
        _git(["add", "."], pr_repo)
        _git(["commit", "-m", "round 1 fix"], pr_repo)
        text = _DIFF_INTRODUCED.replace("src/new_feature.py:7", "src/fix.py:2")
        result = _run_cli(pr_repo, text, "--frozen")
        assert merge_verdicts([_verdict_of(result.stdout), "PASS"]) == "CRITICAL_FAIL"


# ---------------------------------------------------------------------------
# Rendered skill text
# ---------------------------------------------------------------------------

_REVIEW = PROJECT_ROOT / ".claude" / "skills" / "review" / "SKILL.md"
_PR_REVIEW = PROJECT_ROOT / ".claude" / "skills" / "pr-review" / "SKILL.md"
_RESPONDER = PROJECT_ROOT / ".claude" / "skills" / "pr-comment-responder" / "SKILL.md"
_PROTOCOL = (
    PROJECT_ROOT
    / ".claude"
    / "skills"
    / "pr-comment-responder"
    / "references"
    / "review-conversation.md"
)


def _section(text: str, heading: str) -> str:
    _head, marker, rest = text.partition(heading)
    assert marker, f"missing heading: {heading}"
    return rest.split("\n## ", 1)[0]


_CONTRACT = (
    PROJECT_ROOT / ".claude" / "skills" / "review" / "resources" / "frozen-finding-contract.md"
)


class TestReviewSkillStatesTheContract:
    def test_skill_states_the_rule_and_points_to_the_resource(self) -> None:
        body = _section(_REVIEW.read_text(encoding="utf-8"), "## Frozen finding contract")
        assert "defect the diff introduced" in body
        assert "unmet acceptance criterion the PR claims" in body
        assert "flagged notes" in body
        assert "never a reason for another round" in body
        assert "--frozen" in body
        assert "resources/frozen-finding-contract.md" in body
        assert "The caps stay" in body

    def test_resource_states_both_counting_rules(self) -> None:
        text = _CONTRACT.read_text(encoding="utf-8")
        assert "A defect the diff introduced" in text
        assert "acceptance criterion the PR claims" in text
        assert "fix commits since round 1" in text

    def test_resource_says_flagged_notes_never_count_or_trigger_a_round(self) -> None:
        text = _CONTRACT.read_text(encoding="utf-8")
        assert "A flagged note is listed, never counted" in text
        assert "does not enter `merge_verdicts`" in text
        assert "does not trigger another round" in text

    def test_existing_round_caps_stay(self) -> None:
        skill = _REVIEW.read_text(encoding="utf-8")
        text = _CONTRACT.read_text(encoding="utf-8")
        assert "3 rounds for this skill" in text
        assert "default 5 for `check_pr_round_cap.py`" in text
        assert "MUST NOT exceed 3 rounds" in skill

    def test_resource_tells_axes_to_tag_diff_caused_regressions(self) -> None:
        text = _CONTRACT.read_text(encoding="utf-8")
        assert "`[diff-caused]`" in text
        assert "a file it did not touch" in text

    def test_resource_has_no_dashes(self) -> None:
        text = _CONTRACT.read_text(encoding="utf-8")
        assert "\u2014" not in text
        assert "\u2013" not in text

    def test_output_lists_flagged_notes_outside_the_verdict(self) -> None:
        output = _section(_REVIEW.read_text(encoding="utf-8"), "## Output")
        assert "Flagged notes (not counted)" in output
        assert "never change the verdict" in output

    def test_verification_checklist_covers_the_contract(self) -> None:
        text = _REVIEW.read_text(encoding="utf-8")
        assert "step 4a used `--frozen`" in _section(text, "## Verification")


class TestPrLoopsCarryTheSameContract:
    def test_protocol_owns_the_pr_loop_rule(self) -> None:
        body = _section(_PROTOCOL.read_text(encoding="utf-8"), "## Bounded loops and handoff")
        assert "Freeze the finding contract after round 1" in body
        assert "diff introduced the defect" in body
        assert "acceptance criterion the PR claims" in body
        assert "flagged note" in body
        assert "`[WONTFIX]`" in body
        assert "caps above" in body

    def test_protocol_scenario_covers_a_pre_existing_thread(self) -> None:
        text = _PROTOCOL.read_text(encoding="utf-8")
        assert "19. Round 2 or later, thread on a pre-existing defect" in text

    @pytest.mark.parametrize("path", [_PR_REVIEW, _RESPONDER], ids=["pr-review", "responder"])
    def test_consumer_points_to_the_frozen_rule(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert "flagged note" in text.lower()
        assert "new round" in text or "another round" in text
        assert "Bounded loops and handoff" in text or "frozen finding contract" in text

    def test_pr_review_summary_lists_flagged_notes(self) -> None:
        assert '"Flagged notes" in the Step 6 summary' in _PR_REVIEW.read_text(encoding="utf-8")
