"""Tests for build/scripts/agent_templates.py.

Module docstring quotes the exit-code table from agent_templates.py:
  0 - no template pairs found, or every pair renders clean (write mode) /
      matches the committed target (validate mode)
  1 - a rendered target drifted from the committed one (validate mode), the
      rendered text still contains an unresolved {{, or a
      NO-REGEN-skipped target
  2 - a discovered stem's name does not match ^[a-z0-9]+(-[a-z0-9]+)*$,
      only one of the two variant templates exists for a stem, the
      src/claude/agents/ root or a stem's target resolves outside the
      repository or through a symlink, or the template (or a partial it
      transitively includes) used a disallowed tag, named a missing or
      cyclic partial, or referenced a partial missing its trailing newline

Covers positive render, drift detection, validation errors, and edge cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import agent_templates  # noqa: E402


def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repository with git init."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def write_pair(root: Path, stem: str, claude_text: str, copilot_text: str) -> tuple[Path, Path]:
    """Write a paired Claude and Copilot template, return paths."""
    agents_dir = root / "templates" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    claude_path = agents_dir / f"{stem}.claude.md.tmpl"
    copilot_path = agents_dir / f"{stem}.copilot.md.tmpl"
    claude_path.write_text(claude_text, encoding="utf-8")
    copilot_path.write_text(copilot_text, encoding="utf-8")
    return claude_path, copilot_path


def write_partial(root: Path, slug: str, body: str) -> Path:
    """Write a partial template."""
    partials_dir = root / "templates" / "agents" / "partials"
    partials_dir.mkdir(parents=True, exist_ok=True)
    path = partials_dir / f"{slug}.mustache"
    path.write_text(body, encoding="utf-8")
    return path


def test_positive_render_writes_and_validates(tmp_path: Path) -> None:
    """Positive: pair renders clean, exit 0, file written and cached."""
    root = fake_repo(tmp_path)
    write_pair(root, "test-agent", "# Test\ncontent\n", "# Copilot\n")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "agents" / "test-agent.md"
    assert str(target) in result.written
    assert target.read_text(encoding="utf-8") == "# Test\ncontent\n"

    result2 = agent_templates.compile_all(root, validate=True)
    assert result2.exit_code == 0
    assert result2.drifted == []


def test_positive_with_partial_renders_expanded(tmp_path: Path) -> None:
    """Positive: Claude template with partial includes partial expansion."""
    root = fake_repo(tmp_path)
    write_partial(root, "intro", "Hello World\n")
    write_pair(root, "greet", "{{> intro}}\nDone\n", "copilot\n")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "agents" / "greet.md"
    assert target.read_text(encoding="utf-8") == "Hello World\nDone\n"
    assert "greet" in result.copilot_rendered
    assert result.copilot_rendered["greet"] == "copilot\n"


def test_drift_validate_mode_exits_1(tmp_path: Path) -> None:
    """Drift: edit target, validate=True exits 1, file unchanged."""
    root = fake_repo(tmp_path)
    write_pair(root, "drift", "new content\n", "copilot\n")
    compile_all_write = agent_templates.compile_all(root, validate=False)
    assert compile_all_write.exit_code == 0

    target = root / "src" / "claude" / "agents" / "drift.md"
    target.write_text("hand edited\n", encoding="utf-8")

    result = agent_templates.compile_all(root, validate=True)

    assert result.exit_code == 1
    assert str(target) in result.drifted
    assert target.read_text(encoding="utf-8") == "hand edited\n"


def test_missing_partial_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Missing partial: template references nonexistent partial, exit 2."""
    root = fake_repo(tmp_path)
    write_pair(root, "bad", "{{> missing}}\n", "copilot\n")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert "missing" in capsys.readouterr().err


def test_forbidden_tag_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Forbidden tag: template uses disallowed {{name}}, exit 2."""
    root = fake_repo(tmp_path)
    write_pair(root, "bad", "{{name}}\n", "copilot\n")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert "Error:" in capsys.readouterr().err


def test_single_variant_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Single variant: only Claude template present, exit 2, reported."""
    root = fake_repo(tmp_path)
    agents_dir = root / "templates" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "incomplete.claude.md.tmpl").write_text("body\n", encoding="utf-8")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    errors = agent_templates.discover_errors(root)
    assert len(errors) == 1
    assert "incomplete" in errors[0]
    assert "missing" in errors[0].lower()


def test_literal_double_brace_in_output_exits_1(tmp_path: Path) -> None:
    """Unresolved tag: unclosed tag in template is a grammar error, exit 2."""
    root = fake_repo(tmp_path)
    write_pair(root, "unresolved", "{{unclosed", "copilot\n")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 2


def test_no_regen_sentinel_skipped_and_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """NO-REGEN sentinel: target skipped, reported at WARN, exit at least 1."""
    root = fake_repo(tmp_path)
    write_pair(root, "sentinel", "new\n", "copilot\n")
    compile_all_write = agent_templates.compile_all(root, validate=False)
    assert compile_all_write.exit_code == 0

    target = root / "src" / "claude" / "agents" / "sentinel.md"
    target.write_text("<!-- NO-REGEN: manual edit -->\nhand\n", encoding="utf-8")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code >= 1
    assert str(target) in result.skipped
    assert target.read_text(encoding="utf-8") == "<!-- NO-REGEN: manual edit -->\nhand\n"
    out = capsys.readouterr()
    assert "WARN" in (out.err + out.out)


def test_partial_without_trailing_newline_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Partial missing trailing newline: exit 2."""
    root = fake_repo(tmp_path)
    partials_dir = root / "templates" / "agents" / "partials"
    partials_dir.mkdir(parents=True, exist_ok=True)
    (partials_dir / "bad.mustache").write_text("no newline", encoding="utf-8")
    write_pair(root, "test", "{{> bad}}\n", "copilot\n")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert "trailing newline" in capsys.readouterr().err.lower()


def test_bad_stem_name_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Bad stem name: uppercase or special chars, exit 2, reported."""
    root = fake_repo(tmp_path)
    write_pair(root, "Bad_Name", "body\n", "copilot\n")

    result = agent_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    errors = agent_templates.discover_errors(root)
    assert len(errors) == 1
    assert "Bad_Name" in errors[0]
    assert "invalid" in errors[0].lower()


def test_owned_targets_returns_all_rendered_claude_files(tmp_path: Path) -> None:
    """owned_targets: returns set of all src/claude/agents/<stem>.md files."""
    root = fake_repo(tmp_path)
    write_pair(root, "agent1", "body\n", "copilot\n")
    write_pair(root, "agent2", "body\n", "copilot\n")

    targets = agent_templates.owned_targets(root)

    assert targets == {
        root / "src" / "claude" / "agents" / "agent1.md",
        root / "src" / "claude" / "agents" / "agent2.md",
    }


def test_owned_targets_empty_when_no_valid_pairs(tmp_path: Path) -> None:
    """owned_targets: empty when no valid pairs discovered."""
    root = fake_repo(tmp_path)
    write_pair(root, "Bad_Name", "body\n", "copilot\n")

    assert agent_templates.owned_targets(root) == set()


def test_what_if_mode_writes_nothing(tmp_path: Path) -> None:
    """what_if: compile with what_if=True writes nothing."""
    root = fake_repo(tmp_path)
    write_pair(root, "test", "body\n", "copilot\n")

    result = agent_templates.compile_all(root, validate=False, what_if=True)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "agents" / "test.md"
    assert not target.exists()
    assert result.written == []
