"""Checks 2 and 3 of validate-pr-description must depend on discovered gates.

A consumer repository may have no PR template, no tracking issue, and no
workflow that enforces either. The skill must discover those first and report
the checks as not applicable, instead of claiming upstream-only gates exist.
Issue #7411.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = REPO_ROOT / "templates" / "skills" / "validate-pr-description.SKILL.md.tmpl"
RENDERED = REPO_ROOT / "src" / "claude" / "skills" / "validate-pr-description" / "SKILL.md"


def _section(text: str, heading: str) -> str:
    """Return the body of one `### ` or `## ` section, up to the next heading."""
    match = re.search(
        rf"^(#{{2,3}}) {re.escape(heading)}\n(.*?)(?=^#{{2,3}} |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"section {heading!r} missing"
    return match.group(2)


def _check_row(text: str, number: int) -> str:
    phase2 = _section(text, "Phase 2: Run the checks")
    for line in phase2.splitlines():
        if line.startswith(f"| {number} |"):
            return line
    raise AssertionError(f"Phase 2 row {number} missing")


def _upstream_only_claims(text: str) -> list[str]:
    """Phrases that assert an upstream gate exists in every repository."""
    claims = [
        "fails the repository's issue-linkage rule",
        "The spec-coverage job reports FAIL",
        "the spec-coverage job parses",
    ]
    flat = " ".join(text.split())
    return [claim for claim in claims if claim in flat]


@pytest.fixture(params=[TEMPLATE, RENDERED], ids=["template", "rendered"])
def skill_text(request: pytest.FixtureRequest) -> str:
    path: Path = request.param
    return path.read_text(encoding="utf-8")


def test_discovery_phase_precedes_checks(skill_text: str) -> None:
    discovery = skill_text.index("### Phase 1b: Discover the target repository's metadata gates")
    checks = skill_text.index("### Phase 2: Run the checks")
    assert discovery < checks


def test_discovery_names_template_and_gate_signals(skill_text: str) -> None:
    body = _section(skill_text, "Phase 1b: Discover the target repository's metadata gates")
    assert "PR template" in body
    assert "Issue-link gate" in body
    assert "Template gate" in body
    assert ".github/workflows/" in body


def test_title_check_always_applies(skill_text: str) -> None:
    assert "| Always |" in _check_row(skill_text, 1)


def test_issue_keyword_check_is_conditional(skill_text: str) -> None:
    row = _check_row(skill_text, 2)
    assert "Always" not in row
    assert "tracking issue exists" in row
    assert "issue-link gate" in row


def test_template_check_reads_discovered_template(skill_text: str) -> None:
    row = _check_row(skill_text, 3)
    assert "Discovery found a PR template" in row
    # Upstream section names must not be hardcoded as the consumer's template.
    assert "Type of Change" not in row
    assert "Summary non-empty" not in row


def test_inapplicable_checks_report_not_applicable(skill_text: str) -> None:
    phase2 = _section(skill_text, "Phase 2: Run the checks")
    assert "`NOT APPLICABLE`" in phase2
    assert "Never ask the author to open an issue" in phase2


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_plugin_validator_warnings_are_relabelled_in_consumers(skill_text: str) -> None:
    phase2 = _flat(_section(skill_text, "Phase 2: Run the checks"))
    assert "plugin's copy, not a gate of that repository" in phase2
    assert "Its title result always stands." in phase2


def test_keyword_warning_stands_when_tracking_issue_exists(skill_text: str) -> None:
    """A known tracking issue keeps check 2 live even with no template or gate."""
    phase2 = _flat(_section(skill_text, "Phase 2: Run the checks"))
    assert "A keyword WARN stands when a tracking issue or an issue-link gate exists" in phase2
    assert "`NOT APPLICABLE` only when neither does" in phase2
    # The pre-review wording relabelled both WARNs on template or gate alone.
    assert (
        "relabel them `NOT APPLICABLE` when discovery found no matching template or gate"
        not in phase2
    )


def test_validator_exit_code_is_not_read_as_a_gate(skill_text: str) -> None:
    phase2 = _flat(_section(skill_text, "Phase 2: Run the checks"))
    assert "read the per-check output, not the exit code" in phase2


def test_discovery_names_how_a_tracking_issue_is_found(skill_text: str) -> None:
    body = _section(skill_text, "Phase 1b: Discover the target repository's metadata gates")
    row = next(line for line in body.splitlines() if line.startswith("| Tracking issue |"))
    assert "author names one" in row
    assert "branch name" in row
    assert row.rstrip().endswith("| Check 2 |")


def test_keyword_rule_accepts_cross_repository_references(skill_text: str) -> None:
    assert "`owner/repo#N`" in _check_row(skill_text, 2)


def test_no_unconditional_upstream_gate_claims(skill_text: str) -> None:
    assert _upstream_only_claims(skill_text) == []


def test_negative_control_detects_old_wording() -> None:
    """The claim detector fires on the pre-fix wording, so the guard is live."""
    old = (
        "| 2 | Issue-linking keyword | body holds `Closes #N` | The issue stays open "
        "after merge, and the PR fails the repository's issue-linkage rule |\n"
        "| 3 | Template compliance | Summary non-empty | The spec-coverage job "
        "reports FAIL on an unpopulated section |\n"
    )
    assert len(_upstream_only_claims(old)) == 2


def test_check_row_rejects_missing_phase() -> None:
    with pytest.raises(AssertionError, match="Phase 2: Run the checks"):
        _check_row("## Process\n\nNo checks here.\n", 2)
