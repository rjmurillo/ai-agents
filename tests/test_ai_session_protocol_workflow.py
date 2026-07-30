"""Regression guards for the ai-session-protocol validate step.

Issue #2384: the legacy-markdown branch invoked ./scripts/Convert-SessionToJson.ps1,
a script removed during the PowerShell-to-Python migration (PR #1063/#1064) and
whose wrapper was sunset in PR #2359. Any markdown session log routed through that
branch failed with "Migration failed".

Issue #3365: the MUST-failure counter regexed for markdown table rows that
scripts/validate_session_json.py has never emitted, pinning the count at 0 and
making the downstream enforcement step decorative.

Issue #3364: a blocking gate computed its findings, wrote them to an artifact,
and never echoed them, so a red required check showed only "Exit code: 1".

The step's logic moved from inline PowerShell to
scripts/ci/validate_session_protocol.py (ADR-006, issue #3520). Behavioral
coverage for all three regressions now lives in
tests/ci/test_validate_session_protocol.py, which calls the real functions
instead of asserting on the shape of a shell string. What remains here are the
negative guards: the removed constructs must not reappear in either the workflow
or the script that replaced it. Those assertions are genuinely textual, so they
stay textual.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = _ROOT / ".github" / "workflows" / "ai-session-protocol.yml"
SCRIPT = _ROOT / "scripts" / "ci" / "validate_session_protocol.py"

# Both files the validate step's behavior can live in. Guarding only the
# workflow would let a removed construct return by being reintroduced in the
# extracted script, which is where the logic now is.
SOURCES = [
    pytest.param(WORKFLOW, id="workflow"),
    pytest.param(SCRIPT, id="script"),
]


def _validate_step_run() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in doc["jobs"]["validate"]["steps"]:
        if step.get("id") == "validate":
            return step["run"]
    raise AssertionError("validate step not found in ai-session-protocol.yml")


@pytest.mark.parametrize("source", SOURCES)
def test_the_phantom_convert_script_is_not_invoked(source: Path) -> None:
    """Issue #2384: Convert-SessionToJson.ps1 was deleted; calling it always fails."""
    assert "Convert-SessionToJson.ps1" not in source.read_text(encoding="utf-8"), (
        f"{source.name} references the removed Convert-SessionToJson.ps1 (issue #2384)."
    )


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize(
    "claim",
    [
        "Migration failed - could not convert markdown to JSON",
        "Legacy markdown detected - migrating to JSON",
    ],
)
def test_the_dead_markdown_migration_branch_stays_gone(source: Path, claim: str) -> None:
    """Issue #2384: there is no migration path, so nothing may advertise one."""
    assert claim not in source.read_text(encoding="utf-8"), (
        f"{source.name} still advertises the removed migration branch: {claim!r}"
    )


@pytest.mark.parametrize("source", SOURCES)
def test_the_phantom_must_failure_regex_stays_gone(source: Path) -> None:
    """Issue #3365: the counter matched a markdown table no validator emits."""
    assert "MUST\\s*\\|\\s*FAIL" not in source.read_text(encoding="utf-8"), (
        f"{source.name} counts MUST failures with a regex for a markdown table "
        "that validate_session_json.py never emits (issue #3365)."
    )


def test_the_validate_step_delegates_to_the_extracted_script() -> None:
    """ADR-006: the step is a call, not a program.

    This delegation is the seam that lets every guard above scan the script
    rather than a shell string. If the logic moves back inline, those guards go
    blind, so the delegation itself has to be pinned.
    """
    assert "validate_session_protocol.py" in _validate_step_run()
