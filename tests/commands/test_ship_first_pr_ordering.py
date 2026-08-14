"""Ordering contract for `/ship`: a branch with no PR must be able to open its first one.

Issue #4841. `/ship` ran `pipeline-validator` as GitHub pre-flight check 1 and gated
`/push-pr` behind every pre-flight check passing. `pipeline-validator` refuses to run
without a PR, and `/push-pr` is the step that creates the first PR, so a fresh branch
could never leave that state: check 1 stopped the run, the PR was never created, and the
next `/ship` hit the same wall.

The canonical contract this deadlock comes from is in
`.claude/skills/pipeline-validator/SKILL.md`, Step 1 "Decision", read verbatim on
2026-08-13:

    - **No PR found:** Report to user. A PR must exist before pipeline validation. The
      calling skill should have created one.

That contract is correct for the validator. The bug was the order in which `/ship` called
it, so the fix is in `/ship` and this module pins the repaired order.

Two inverse failure modes are pinned alongside the fix, because either one turns the
repair into a worse defect:

1. **Over-deferral.** Deferring pipeline validation for every GitHub run would drop the
   pre-flight CI gate on branches that already have a PR.
   `test_open_pr_still_validates_in_preflight` fails if the existing-PR branch stops
   invoking the validator up front.
2. **Silent skip.** Deferring and never discharging would let a ship report read green
   with zero CI evidence. `test_process_discharges_deferral_after_push_pr` fails if the
   validator is not invoked after `/push-pr`.

Assertions parse the document into sections and bullets rather than substring-matching the
whole file (`.claude/rules/testing.md` MUST 9): a bare `"pipeline-validator" in text` holds
when the name survives only in a prose reference and proves nothing about which branch
invokes it. `TestPreFixControl` feeds the pre-fix ordering back through the same helpers, so
every check here is shown to fail on the shape it was written against
(`.claude/rules/testing.md` SHOULD 10).

`.claude/commands/ship.md` is the source; `src/copilot-cli/skills/ship/SKILL.md` is
generated from it by `build/scripts/generate_commands.py` (see
`.agents/governance/GENERATOR-FILES.md`). Both are asserted so the shipped Copilot copy
cannot carry the deadlock after the Claude copy is fixed. The generator rewrites the
invocation syntax (`Skill(skill="pipeline-validator")` becomes
`` `skill: "pipeline-validator"` ``), so `invokes_pipeline_validator` accepts both forms.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / ".claude" / "commands" / "ship.md"
COMMAND_MIRROR_PATH = REPO_ROOT / "src" / "copilot-cli" / "skills" / "ship" / "SKILL.md"
VALIDATOR_SKILL_PATH = REPO_ROOT / ".claude" / "skills" / "pipeline-validator" / "SKILL.md"

_FRONTMATTER_RE = re.compile(r"^---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_HEADING_RE = re.compile(r"^## .+$", re.MULTILINE)
_NUMBERED_ITEM_RE = re.compile(r"^\d+\. ", re.MULTILINE)
_HOST_BULLET_RE = re.compile(r"^ {3}- (?P<body>.*)$", re.MULTILINE)
# Claude: Invoke Skill(skill="pipeline-validator"). Copilot: Invoke `skill: "pipeline-validator"`.
_INVOKE_VALIDATOR_RE = re.compile(r'(?:Skill\(skill=|skill:\s*)"pipeline-validator"')
_DISCHARGES_CI_RE = re.compile(
    r'(?:Skill\(skill=|skill:\s*)"pipeline-validator"|get_pr_checks\.py'
)
_NO_PR_DECISION_RE = re.compile(r"^- (\*\*No PR found:\*\* .+)$", re.MULTILINE)


def body_of(text: str) -> str:
    """Return the markdown body with any YAML frontmatter removed."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def section(text: str, heading: str) -> str:
    """Return the ``## heading`` section body, up to the next level-2 heading.

    Raises AssertionError when the heading is absent so a renamed section fails loudly
    instead of silently returning an empty string that passes every "not in" assertion.
    """
    marker = f"## {heading}"
    start = body_of(text).find(marker)
    assert start != -1, f"section '{marker}' not found"
    rest = body_of(text)[start + len(marker) :]
    next_heading = _HEADING_RE.search(rest)
    return rest[: next_heading.start()] if next_heading else rest


def numbered_items(section_text: str) -> list[str]:
    """Return the top-level numbered list items of ``section_text``, in document order."""
    starts = [m.start() for m in _NUMBERED_ITEM_RE.finditer(section_text)]
    assert starts, "section contains no numbered items"
    bounds = zip(starts, [*starts[1:], len(section_text)], strict=True)
    return [section_text[begin:end] for begin, end in bounds]


def numbered_item(section_text: str, opening: str) -> str:
    """Return one numbered list item of ``section_text``, selected by its opening text."""
    matches = [i for i in numbered_items(section_text) if opening in i.splitlines()[0]]
    assert len(matches) == 1, f"expected 1 item opening with {opening!r}, got {len(matches)}"
    return matches[0]


def host_bullets(item_text: str) -> list[str]:
    """Return the host-branch bullets of a pre-flight item (three-space indented)."""
    bullets = (m.group("body") for m in _HOST_BULLET_RE.finditer(item_text))
    return [b for b in bullets if "host=" in b]


def invokes_pipeline_validator(text: str) -> bool:
    """True when ``text`` invokes the skill, not merely when it names the file."""
    return _INVOKE_VALIDATOR_RE.search(text) is not None


def github_bullets_without_pr_condition(pipeline_item: str) -> list[str]:
    """Return `host=github` bullets that do not branch on PR existence.

    A GitHub bullet with no `pr=` qualifier is the #4841 deadlock shape: it applies to
    every GitHub run, including the one where no PR exists yet.
    """
    return [b for b in host_bullets(pipeline_item) if "`host=github`" in b and "pr=" not in b]


def discharges_ci(text: str) -> bool:
    """True when ``text`` discharges the deferred CI check via any supported mechanism.

    The discharge can invoke the pipeline-validator skill (ADO path) or query CI status
    through ``get_pr_checks.py`` (GitHub path).
    """
    return _DISCHARGES_CI_RE.search(text) is not None


def deferral_discharged_after_push_pr(process_section: str) -> bool:
    """True when a later process step validates CI than the step creating the PR.

    Compares list-item positions rather than character offsets: the discharge step names
    `/push-pr` again while describing which PR to validate, so an offset comparison would
    read that mention and report the invocation as coming first.
    """
    items = numbered_items(process_section)
    creates = [i for i, item in enumerate(items) if "/push-pr" in item]
    validates = [i for i, item in enumerate(items) if discharges_ci(item)]
    return bool(creates) and bool(validates) and min(validates) > min(creates)


def canonical_no_pr_contract() -> str:
    """Return the verbatim 'No PR found' decision line from the pipeline-validator skill."""
    match = _NO_PR_DECISION_RE.search(VALIDATOR_SKILL_PATH.read_text(encoding="utf-8"))
    assert match is not None, f"no 'No PR found' decision line in {VALIDATOR_SKILL_PATH}"
    return match.group(1)


@pytest.fixture(params=[COMMAND_PATH, COMMAND_MIRROR_PATH], ids=["claude", "copilot"])
def ship_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


@pytest.fixture
def pipeline_item(ship_text: str) -> str:
    return numbered_item(section(ship_text, "Pre-flight Checks"), "**Pipeline health**")


class TestPipelineHealthBranchesOnPrExistence:
    def test_no_github_bullet_applies_to_every_run(self, pipeline_item: str) -> None:
        assert github_bullets_without_pr_condition(pipeline_item) == []

    def test_open_pr_still_validates_in_preflight(self, pipeline_item: str) -> None:
        """Inverse guard: the fix must not disarm the gate for branches that have a PR."""
        with_pr = [b for b in host_bullets(pipeline_item) if "`pr=#<number>`" in b]
        assert len(with_pr) == 1
        assert invokes_pipeline_validator(with_pr[0])

    def test_no_pr_bullet_defers_instead_of_invoking(self, pipeline_item: str) -> None:
        without_pr = [b for b in host_bullets(pipeline_item) if "`pr=none`" in b]
        assert len(without_pr) == 1
        assert not invokes_pipeline_validator(without_pr[0])
        assert "DEFERRED" in without_pr[0]
        assert "not skipped" in without_pr[0]

    def test_no_pr_bullet_quotes_the_canonical_validator_contract(self, ship_text: str) -> None:
        """The cited reason must be the validator's real contract, not a remembered one.

        The reference uses a generic name ("the pipeline-validator skill") rather than a
        tree-specific path, per plugin-self-containment.md.
        """
        assert "pipeline-validator skill" in ship_text.lower()
        assert canonical_no_pr_contract() in ship_text

    def test_ado_branch_still_evaluates_build_policies(self, pipeline_item: str) -> None:
        """Sibling non-regression: the ADO branch never had the deadlock and is untouched."""
        ado = [b for b in host_bullets(pipeline_item) if "`host=ado`" in b]
        assert len(ado) == 1
        assert "pipeline-validator does not apply" in ado[0]
        assert not invokes_pipeline_validator(ado[0])
        assert "az repos pr policy list" in pipeline_item
        assert "az pipelines build list" in pipeline_item


class TestProcessDischargesTheDeferral:
    def test_process_discharges_deferral_after_push_pr(self, ship_text: str) -> None:
        """Inverse guard: a deferred check must be run later, not dropped."""
        assert deferral_discharged_after_push_pr(section(ship_text, "Process"))

    def test_discharge_step_forbids_reporting_pass_without_the_run(self, ship_text: str) -> None:
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "MUST NOT be reported as PASS without this run" in discharge
        assert "DEFERRED->FAIL" in discharge
        assert "RESULT: BLOCKED" in discharge

    def test_discharge_uses_github_aware_ci_check(self, ship_text: str) -> None:
        """The discharge step must use a GitHub-aware flow, not the ADO-only validator."""
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "get_pr_checks.py" in discharge
        assert "--pull-request" in discharge


    def test_discharge_requires_allpassing_not_just_exit_code(self, ship_text: str) -> None:
        """Exit code 0 alone is insufficient; discharge must check Data.AllPassing."""
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "AllPassing" in discharge, "discharge must gate on Data.AllPassing"
        assert "exit code" in discharge.lower(), \
            "discharge must mention exit code is insufficient alone"

    def test_contributor_mode_still_creates_no_pr(self, ship_text: str) -> None:
        """Inverse guard: the deferral must not leak PR creation into contributor mode."""
        process = section(ship_text, "Process")
        assert "`mode=contributor`: do NOT create a PR and do NOT merge." in process


class TestPrDetectionDistinguishesErrors:
    """The `pr` variable must not treat auth/network failures as 'no PR'."""

    def test_mode_detection_distinguishes_no_pr_from_query_failure(self, ship_text: str) -> None:
        detection = section(ship_text, "Mode Detection")
        # Must mention that non-zero exit can mean different things
        assert "no PR exists" in detection.lower() or "no pull requests" in detection.lower()
        # Must require stopping on non-no-PR failures
        assert "stop" in detection.lower() or "error" in detection.lower()


class TestShipReportStatesTheDeferral:
    def test_report_states_pr_presence_at_preflight(self, ship_text: str) -> None:
        assert "PR-AT-PREFLIGHT: none|#<number>" in section(ship_text, "Output")

    def test_report_offers_both_deferred_outcomes(self, ship_text: str) -> None:
        output = section(ship_text, "Output")
        pipeline_lines = [ln for ln in output.splitlines() if ln.strip().startswith("Pipeline:")]
        assert len(pipeline_lines) == 1
        assert "DEFERRED->PASS" in pipeline_lines[0]
        assert "DEFERRED->FAIL" in pipeline_lines[0]


# The pre-fix ordering, reduced to the parts these helpers read. Reproduced from
# `.claude/commands/ship.md` at commit ab9c636de5 (origin/main, 2026-08-13). Keeping it
# inline rather than reading git history makes the control independent of branch state.
_PRE_FIX_SHIP_MD = """---
description: Ship it.
---

## Pre-flight Checks

1. **Pipeline health**
   - `host=github`: Invoke Skill(skill="pipeline-validator"). All CI checks green?
   - `host=ado`: pipeline-validator does not apply. Evaluate ADO build policies instead.
2. **Security posture** - Invoke Skill(skill="security-scan").

## Process

1. Run all 4 pre-flight checks, branching by `host` and `mode`.
2. If any blocking check fails: report what failed, why, and how to fix. Stop.
3. If all pass:
   - `mode=owner`, `host=github`: run /validate-pr-description, then run /push-pr to open the PR.
4. Report: host, mode, what was validated or shipped, PR link, any warnings.
"""


class TestPreFixControl:
    """The pre-fix text must fail the checks above, or they prove nothing."""

    def test_pre_fix_github_bullet_applies_to_every_run(self) -> None:
        item = numbered_item(section(_PRE_FIX_SHIP_MD, "Pre-flight Checks"), "**Pipeline health**")
        offenders = github_bullets_without_pr_condition(item)
        assert len(offenders) == 1
        assert invokes_pipeline_validator(offenders[0])

    def test_pre_fix_has_no_deferral_branch(self) -> None:
        item = numbered_item(section(_PRE_FIX_SHIP_MD, "Pre-flight Checks"), "**Pipeline health**")
        assert [b for b in host_bullets(item) if "`pr=none`" in b] == []

    def test_pre_fix_never_discharges_after_push_pr(self) -> None:
        assert not deferral_discharged_after_push_pr(section(_PRE_FIX_SHIP_MD, "Process"))

    def test_pre_fix_report_omits_pr_presence(self) -> None:
        assert "PR-AT-PREFLIGHT" not in _PRE_FIX_SHIP_MD

