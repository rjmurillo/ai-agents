"""Contract tests for validate_spec_frontmatter (issue #2001).

These tests pin the schema enum contract from .agents/governance/spec-schemas.md.
The negative cases are the exact frontmatter drift the spec-generator agent
shipped on PR #1995 and PR #1989 (priority=medium, category=tooling,
status=ready, complexity mismatch); the validator MUST reject each.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from validate_spec_frontmatter import (  # noqa: E402
    extract_frontmatter,
    main,
    validate_fields,
    validate_file,
)


def _fm(**fields: str) -> dict[str, str]:
    base = {"created": "2026-05-31", "updated": "2026-05-31"}
    base.update(fields)
    return base


class TestValidRequirement:
    def test_passes(self):
        result = validate_fields(
            "REQ.md",
            _fm(type="requirement", id="REQ-001", title="x", status="approved", priority="P0", category="functional"),
        )
        assert result.ok, result.errors


class TestValidDesign:
    def test_passes(self):
        result = validate_fields(
            "DESIGN.md",
            _fm(type="design", id="DESIGN-001", title="x", status="approved", priority="P0", related="[present]"),
        )
        assert result.ok, result.errors


class TestValidTask:
    def test_passes(self):
        result = validate_fields(
            "TASK.md",
            _fm(type="task", id="TASK-001", title="x", status="todo", priority="P1", complexity="XS", related="[present]"),
        )
        assert result.ok, result.errors


class TestDocumentedDriftRejected:
    """The exact bad values from PR #1995 / #1989."""

    def test_priority_medium_rejected(self):
        result = validate_fields(
            "REQ.md",
            _fm(type="requirement", id="REQ-001", title="x", status="approved", priority="medium", category="functional"),
        )
        assert not result.ok
        assert any("priority" in e and "medium" in e for e in result.errors)

    def test_category_tooling_rejected(self):
        result = validate_fields(
            "REQ.md",
            _fm(type="requirement", id="REQ-001", title="x", status="approved", priority="P0", category="tooling"),
        )
        assert not result.ok
        assert any("category" in e and "tooling" in e for e in result.errors)

    def test_task_status_ready_rejected(self):
        result = validate_fields(
            "TASK.md",
            _fm(type="task", id="TASK-001", title="x", status="ready", priority="P1", complexity="XS", related="[present]"),
        )
        assert not result.ok
        assert any("status" in e and "ready" in e for e in result.errors)

    def test_design_missing_status_and_priority_rejected(self):
        result = validate_fields(
            "DESIGN.md",
            _fm(type="design", id="DESIGN-001", title="x", related="[present]"),
        )
        assert not result.ok
        assert any("status" in e for e in result.errors)
        assert any("priority" in e for e in result.errors)

    def test_complexity_out_of_range_rejected(self):
        result = validate_fields(
            "TASK.md",
            _fm(type="task", id="TASK-001", title="x", status="todo", priority="P1", complexity="medium", related="[present]"),
        )
        assert not result.ok
        assert any("complexity" in e for e in result.errors)


class TestStructuralFailures:
    def test_unknown_type_rejected(self):
        result = validate_fields("X.md", _fm(type="epic", id="EPIC-001", title="x"))
        assert not result.ok
        assert any("type" in e for e in result.errors)

    def test_bad_id_pattern_rejected(self):
        result = validate_fields(
            "REQ.md",
            _fm(type="requirement", id="REQ-1", title="x", status="draft", priority="P2", category="constraint"),
        )
        assert not result.ok
        assert any("id" in e for e in result.errors)


class TestExtractFrontmatter:
    def test_parses_scalar_fields(self):
        text = "---\ntype: requirement\nid: REQ-001\npriority: P0\n---\n# body\n"
        fields = extract_frontmatter(text)
        assert fields == {"type": "requirement", "id": "REQ-001", "priority": "P0"}

    def test_strips_quotes_and_comments(self):
        text = '---\ntitle: "hello"\npriority: P1  # normal\n---\n'
        fields = extract_frontmatter(text)
        assert fields["title"] == "hello"
        assert fields["priority"] == "P1"

    def test_list_field_marked_present(self):
        text = "---\ntype: design\nrelated:\n  - REQ-001\n---\n"
        fields = extract_frontmatter(text)
        assert fields["related"] == "[present]"

    def test_no_frontmatter_returns_none(self):
        assert extract_frontmatter("# just a heading\n") is None

    def test_unterminated_frontmatter_returns_none(self):
        assert extract_frontmatter("---\ntype: task\n") is None


class TestValidateFileAndMain:
    def test_valid_file_passes(self, tmp_path):
        p = tmp_path / "REQ-001-x.md"
        p.write_text(
            "---\ntype: requirement\nid: REQ-001\ntitle: x\nstatus: draft\n"
            "priority: P1\ncategory: functional\ncreated: 2026-05-31\nupdated: 2026-05-31\n---\n# x\n",
            encoding="utf-8",
        )
        assert validate_file(str(p)).ok

    def test_missing_frontmatter_file_fails(self, tmp_path):
        p = tmp_path / "x.md"
        p.write_text("# no frontmatter\n", encoding="utf-8")
        assert not validate_file(str(p)).ok

    def test_main_no_args_is_config_error(self):
        assert main([]) == 2

    def test_main_returns_1_on_invalid(self, tmp_path):
        p = tmp_path / "bad.md"
        p.write_text("---\ntype: task\nid: TASK-001\nstatus: ready\n---\n", encoding="utf-8")
        assert main([str(p)]) == 1

    def test_main_returns_0_on_valid(self, tmp_path):
        p = tmp_path / "ok.md"
        p.write_text(
            "---\ntype: task\nid: TASK-001\ntitle: x\nstatus: todo\npriority: P0\n"
            "complexity: M\nrelated:\n  - DESIGN-001\ncreated: 2026-05-31\nupdated: 2026-05-31\n---\n",
            encoding="utf-8",
        )
        assert main([str(p)]) == 0


class TestHeldOutGeneralization:
    """Drift values the SKILL does NOT name in its 'Common drift this gate stops'
    list. These prove the validator enforces the schema RULE (enum membership),
    not just the four documented values. Added from the #2001 live-eval held-out
    run (evals/spec-generator-spike/heldout-results.json), where the removed agent
    rejected these against hallucinated enum sets while the skill cited canonical.
    """

    def test_priority_high_rejected(self):
        result = validate_fields(
            "REQ.md",
            _fm(type="requirement", id="REQ-001", title="x", status="approved", priority="high", category="functional"),
        )
        assert not result.ok
        assert any("priority" in e and "high" in e for e in result.errors)

    def test_task_status_pending_rejected(self):
        result = validate_fields(
            "TASK.md",
            _fm(type="task", id="TASK-001", title="x", status="pending", priority="P1", complexity="S", related="[present]"),
        )
        assert not result.ok
        assert any("status" in e and "pending" in e for e in result.errors)

    def test_category_infra_rejected(self):
        result = validate_fields(
            "REQ.md",
            _fm(type="requirement", id="REQ-002", title="x", status="draft", priority="P2", category="infra"),
        )
        assert not result.ok
        assert any("category" in e and "infra" in e for e in result.errors)

    def test_design_status_unnamed_value_rejected(self):
        result = validate_fields(
            "DESIGN.md",
            _fm(type="design", id="DESIGN-001", title="x", status="wip", priority="P0", related="[present]"),
        )
        assert not result.ok
        assert any("status" in e and "wip" in e for e in result.errors)
