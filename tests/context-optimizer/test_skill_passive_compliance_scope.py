"""Scope and exception tests for the passive compliance validator."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

repo_root = Path(__file__).parent.parent.parent
scripts_dir = repo_root / ".claude" / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(scripts_dir))

from test_skill_passive_compliance import (  # noqa: E402
    audit_size_exception,
    main,
    print_table_format,
    run_compliance_checks,
)


@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / ".git").mkdir()
        yield repo_path


def write_size_exception(skill_dir: Path, comment: str) -> None:
    """Write one declared size exception with the supplied audit comment."""
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {skill_dir.name}
description: Large workflow
size-exception: true
---

<!--
{comment}
-->
"""
    )


def test_complete_size_exception_surfaces_safeguard_evidence(temp_repo):
    """A declared exception reports its rationale and safeguard evidence."""
    skill_dir = temp_repo / "skills" / "large-skill"
    write_size_exception(
        skill_dir,
        """size-exception rationale: Splitting this workflow would separate
mutation ownership from the state that proves the mutation remains safe.
Preserved invariant: One workflow owns the mutation lease through completion.
Behavioral tests: `tests/test_lease.py`, `tests/test_live_state.py`
Review trigger: Revisit when a measured split preserves both behavior tests.""",
    )

    result = audit_size_exception(skill_dir)

    assert result is not None
    assert result.passed
    assert result.details["preservedInvariant"].startswith("One workflow")
    assert result.details["behavioralTests"] == (
        "`tests/test_lease.py`, `tests/test_live_state.py`"
    )
    assert result.details["reviewTrigger"].startswith("Revisit")


def test_incomplete_size_exception_fails_with_missing_fields(temp_repo):
    """A declared exception without safeguard evidence returns an error."""
    skill_dir = temp_repo / "skills" / "large-skill"
    write_size_exception(skill_dir, "size-exception rationale:")

    result = audit_size_exception(skill_dir)

    assert result is not None
    assert not result.passed
    assert result.details["missingFields"] == [
        "Preserved invariant",
        "Behavioral tests",
        "Review trigger",
    ]
    assert "Missing rationale" in result.details["auditIssues"]


def test_size_exception_does_not_require_maintainer_test_files(temp_repo):
    """Shipped audit metadata can name tests outside the consumer repository."""
    skill_dir = temp_repo / "skills" / "large-skill"
    write_size_exception(
        skill_dir,
        """size-exception rationale: One ordered safety protocol owns mutation.
Preserved invariant: One workflow owns the mutation lease through completion.
Behavioral tests: `tests/test_missing.py`
Review trigger: Revisit when a measured split preserves the behavior test.""",
    )

    result = audit_size_exception(skill_dir)

    assert result is not None
    assert result.passed
    assert result.details["behavioralTests"] == "`tests/test_missing.py`"


def test_skill_without_size_exception_has_no_audit(temp_repo):
    """A skill with no declared exception has no exception audit."""
    skill_dir = temp_repo / "skills" / "small-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: small-skill
description: Small workflow
---
"""
    )

    assert audit_size_exception(skill_dir) is None


def test_repository_pr_autofix_exception_has_auditable_safeguards():
    """The shipped exception exposes its rationale and safety review trigger."""
    result = audit_size_exception(repo_root / "src" / "copilot-cli" / "skills" / "pr-autofix")

    assert result is not None
    assert result.passed
    assert "lease" in result.details["preservedInvariant"]
    assert "late_live_state" in result.details["behavioralTests"]
    assert "measured split" in result.details["reviewTrigger"]


def test_repository_removes_false_vendor_attribution_from_both_skill_trees():
    """Canonical and generated docs distinguish vendor guidance from local policy."""
    files = [
        repo_root
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
        / "test_skill_passive_compliance.py",
        repo_root / ".claude" / "skills" / "context-optimizer" / "SKILL.md",
        repo_root
        / "src"
        / "copilot-cli"
        / "skills"
        / "context-optimizer"
        / "scripts"
        / "test_skill_passive_compliance.py",
        repo_root
        / "src"
        / "copilot-cli"
        / "skills"
        / "context-optimizer"
        / "SKILL.md",
    ]

    contents = [path.read_text() for path in files]

    assert all("Anthropic recommendation" not in content for content in contents)
    assert all("MEMORY.md" in content for content in contents[1::2])
    assert all("command_size.py" in content for content in contents[1::2])


def test_compliance_scope_names_excluded_layers_and_separate_check(temp_repo, monkeypatch):
    """JSON data names context layers that this validator does not evaluate."""
    monkeypatch.chdir(temp_repo)
    (temp_repo / "AGENTS.md").write_text("# Imported\n" + ("line\n" * 300))
    (temp_repo / "CLAUDE.md").write_text("# Test\n\n@AGENTS.md\n")
    path_local = temp_repo / "src" / "AGENTS.md"
    path_local.parent.mkdir()
    path_local.write_text("# Path-local instructions\n")
    generated = temp_repo / ".github" / "instructions" / "project.instructions.md"
    generated.parent.mkdir(parents=True)
    generated.write_text("---\napplyTo: '**'\n---\n\n# Generated instructions\n")

    results = run_compliance_checks(Path(".claude"), Path("CLAUDE.md"))

    assert results.scope["notEvaluated"] == [
        "@imported file size",
        "hierarchical CLAUDE.md and AGENTS.md files",
        "generated instruction layers",
        "plugin-provided context",
    ]
    assert "skill_size.py" in results.scope["requiredSeparateChecks"][0]
    assert results.summary["measurements"] == 1
    assert results.scope["claudeMdMeasurementResult"]["lineCount"] == 3


def test_table_output_reports_scope_and_measurement(temp_repo, monkeypatch, capsys):
    """Table output separates measured data from evaluated checks."""
    monkeypatch.chdir(temp_repo)
    (temp_repo / "CLAUDE.md").write_text("# Test\n")
    results = run_compliance_checks(Path(".claude"), Path("CLAUDE.md"))

    print_table_format(results)

    output = capsys.readouterr().out
    assert "CLAUDE.md Single-File Measurement" in output
    assert "plugin-provided context" in output
    assert "skill_size.py" in output
    assert "[PASS] All evaluated checks passed. See scope and separate checks." in output


def test_json_output_reports_scope_and_measurement(temp_repo, monkeypatch, capsys):
    """JSON output separates measured data from evaluated checks."""
    monkeypatch.chdir(temp_repo)
    (temp_repo / "CLAUDE.md").write_text("# Test\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "test_skill_passive_compliance.py",
            "--path",
            ".claude",
            "--claude-md-path",
            "CLAUDE.md",
            "--format",
            "json",
        ],
    )

    exit_code = main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["summary"]["measurements"] == 1
    assert "plugin-provided context" in payload["scope"]["notEvaluated"]
    assert "skill_size.py" in payload["scope"]["requiredSeparateChecks"][0]


def test_nested_incomplete_size_exception_fails_table_and_json(temp_repo, monkeypatch, capsys):
    """Default recursive discovery rejects an unaudited nested exception."""
    monkeypatch.chdir(temp_repo)
    (temp_repo / "CLAUDE.md").write_text("# Test\n")
    skill_dir = temp_repo / ".claude" / "skills" / "large-skill"
    write_size_exception(skill_dir, "size-exception: Historical exception.")

    results = run_compliance_checks(Path(".claude"), Path("CLAUDE.md"))
    print_table_format(results)
    table_output = capsys.readouterr().out

    assert results.summary["failed"] == 1
    assert results.size_exceptions[0]["skill"] == "large-skill"
    assert "Size Exception Audit (large-skill)" in table_output
    assert "[FAIL] Compliance violations detected" in table_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "test_skill_passive_compliance.py",
            "--path",
            ".claude",
            "--claude-md-path",
            "CLAUDE.md",
            "--format",
            "json",
        ],
    )
    assert main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["violations"][0]["check"] == "Size Exception Audit (large-skill)"
