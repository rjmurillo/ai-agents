"""QA approval-gate parity between the Claude and Copilot renderings (issue #6989).

Both rendered variants must name the same acceptance gates, require every
named gate for APPROVED, and block when evidence for any gate (including the
PR description check) is missing or failing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "build" / "scripts"))

from agent_capabilities import load_mcp_table  # noqa: E402
from agent_templates import render_claude  # noqa: E402
from skill_template_grammar import render  # noqa: E402

_AGENTS = _REPO_ROOT / "templates" / "agents"
_PARTIALS = _AGENTS / "partials"
EXPECTED_GATES = (
    "CI Environment Tests",
    "Fail-Safe Patterns",
    "Test-Implementation Alignment",
    "Coverage Threshold",
    "PR Description",
)


def _claude() -> str:
    return str(render_claude(_AGENTS / "qa.claude.md.tmpl", _PARTIALS, load_mcp_table(_REPO_ROOT)))


def _copilot() -> str:
    return str(render(_AGENTS / "qa.copilot.md.tmpl", _PARTIALS))


@pytest.fixture(params=["claude", "copilot"])
def rendered(request: pytest.FixtureRequest) -> str:
    return _claude() if request.param == "claude" else _copilot()


def _summary_gates(text: str) -> list[str]:
    block = text.split("## Validation Summary", 1)[1].split("## Evidence", 1)[0]
    return [
        m.group(1).strip()
        for m in re.finditer(r"^\| ([^|]+) \| \[PASS\]/\[FAIL\] \| Yes \|$", block, re.M)
    ]


def _approved_row(text: str) -> str:
    rows = [r for r in text.splitlines() if r.rstrip().endswith("| APPROVED | All gates green |")]
    assert len(rows) == 1, rows
    return rows[0]


def _blocked_rows(text: str) -> list[str]:
    return [r for r in text.splitlines() if "| BLOCKED |" in r]


class TestPositive:
    def test_summary_table_names_expected_gates(self, rendered: str) -> None:
        assert _summary_gates(rendered) == list(EXPECTED_GATES)

    def test_approved_row_requires_all_named_gates(self, rendered: str) -> None:
        """The row defers to the named table, so it carries no count that can drift."""
        assert _approved_row(rendered).startswith("| All gates PASS,")
        assert len(_summary_gates(rendered)) == len(EXPECTED_GATES)

    def test_approved_row_has_no_numeric_gate_count(self, rendered: str) -> None:
        assert not re.search(r"All \d+ gates", rendered)

    def test_pr_description_step_rendered_with_script(self, rendered: str) -> None:
        assert "#### Step 5: PR Description Validation" in rendered
        assert "validate_pr_description.py" in rendered


class TestNegative:
    def test_any_gate_fail_blocks(self, rendered: str) -> None:
        assert any("Any gate FAIL" in r for r in _blocked_rows(rendered))

    def test_pr_description_is_blocking_gate(self, rendered: str) -> None:
        assert "| PR Description | [PASS]/[FAIL] | Yes |" in rendered


class TestMissingEvidence:
    def test_missing_gate_evidence_blocks(self, rendered: str) -> None:
        assert any("or gate evidence |" in r for r in _blocked_rows(rendered))

    def test_evidence_section_covers_all_steps(self, rendered: str) -> None:
        assert "[Include Step 1-5 evidence above]" in rendered


def test_variants_apply_identical_acceptance_rules() -> None:
    """Equivalent evidence yields equivalent decisions: same gates, same verdict table."""
    c, p = _claude(), _copilot()
    assert _summary_gates(c) == _summary_gates(p)
    assert _approved_row(c) == _approved_row(p)
    assert _blocked_rows(c) == _blocked_rows(p)

    def cond(t: str) -> list[str]:
        return [r for r in t.splitlines() if "| CONDITIONAL |" in r]

    assert cond(c) == cond(p)
