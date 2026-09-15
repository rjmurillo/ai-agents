"""Tests for build/scripts/rule_templates.py.

Module docstring quotes the exit-code table from rule_templates.py:
  0 - no templates found, or every template renders clean (write mode) /
      matches the committed target (validate mode)
  1 - a rendered target drifted from the committed one (validate mode), the
      rendered text still contains an unresolved {{, or a
      NO-REGEN-skipped target
  2 - a discovered name does not match ^[a-z0-9]+(-[a-z0-9]+)*$, the
      source templates/rules/<name>.md is a symlink or not a regular file,
      the src/claude/rules/ root or a name's target resolves outside the
      repository or through a symlink, or the template (or a partial it
      transitively includes) used a disallowed tag, named a missing or
      cyclic partial, or referenced a partial missing its trailing newline

Covers positive render, drift detection, validation errors, and edge cases.
This module is a single-variant twin of agent_templates.py (one template per
name, not a Claude/Copilot pair), so this test file mirrors
tests/build_scripts/test_agent_templates_compile.py's shape with the pair
machinery removed.
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

import rule_templates  # noqa: E402


def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repository with git init."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def write_template(root: Path, name: str, text: str) -> Path:
    """Write a rule template, return its path."""
    rules_dir = root / "templates" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_partial(root: Path, slug: str, body: str) -> Path:
    """Write a partial template."""
    partials_dir = root / "templates" / "rules" / "partials"
    partials_dir.mkdir(parents=True, exist_ok=True)
    path = partials_dir / f"{slug}.mustache"
    path.write_text(body, encoding="utf-8")
    return path


def test_positive_render_writes_and_validates(tmp_path: Path) -> None:
    """Positive: template renders clean, exit 0, file written and cached."""
    root = fake_repo(tmp_path)
    write_template(root, "test-rule", "# Test\ncontent\n")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "rules" / "test-rule.md"
    assert str(target) in result.written
    assert target.read_text(encoding="utf-8") == "# Test\ncontent\n"

    result2 = rule_templates.compile_all(root, validate=True)
    assert result2.exit_code == 0
    assert result2.drifted == []


def test_positive_with_partial_renders_expanded(tmp_path: Path) -> None:
    """Positive: template with partial includes partial expansion."""
    root = fake_repo(tmp_path)
    write_partial(root, "intro", "Hello World\n")
    write_template(root, "greet", "{{> intro}}\nDone\n")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "rules" / "greet.md"
    assert target.read_text(encoding="utf-8") == "Hello World\nDone\n"


def test_drift_validate_mode_exits_1(tmp_path: Path) -> None:
    """Drift: edit target, validate=True exits 1, file unchanged."""
    root = fake_repo(tmp_path)
    write_template(root, "drift", "new content\n")
    compile_write = rule_templates.compile_all(root, validate=False)
    assert compile_write.exit_code == 0

    target = root / "src" / "claude" / "rules" / "drift.md"
    target.write_text("hand edited\n", encoding="utf-8")

    result = rule_templates.compile_all(root, validate=True)

    assert result.exit_code == 1
    assert str(target) in result.drifted
    assert target.read_text(encoding="utf-8") == "hand edited\n"


def test_missing_partial_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Missing partial: template references nonexistent partial, exit 2."""
    root = fake_repo(tmp_path)
    write_template(root, "bad", "{{> missing}}\n")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert "missing" in capsys.readouterr().err
    target = root / "src" / "claude" / "rules" / "bad.md"
    assert not target.exists()


def test_forbidden_tag_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Forbidden tag: template uses disallowed {{name}}, exit 2.

    Regression guard for the exact shape .claude/rules/testing.md hit: a
    literal `${{ a && b }}` (or any bare `{{name}}`) is a disallowed tag
    under the ADR-108 grammar, not a partial reference or a comment.
    """
    root = fake_repo(tmp_path)
    write_template(root, "bad", "${{ a && b }}\n")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert "Error:" in capsys.readouterr().err
    target = root / "src" / "claude" / "rules" / "bad.md"
    assert not target.exists()


def test_untemplated_rule_left_untouched(tmp_path: Path) -> None:
    """Edge: discover() on a directory missing one name compiles the rest.

    Mirrors this repository's own transitional state: templates/rules/
    carries 28 of 29 names; the 29th (testing.md) has no template and is
    simply absent from discover()'s mapping, never touched by compile_all.
    """
    root = fake_repo(tmp_path)
    write_template(root, "templated", "body\n")
    # A pre-existing hand-maintained file with no matching template.
    claude_rules_dir = root / ".claude" / "rules"
    claude_rules_dir.mkdir(parents=True, exist_ok=True)
    untemplated = claude_rules_dir / "untemplated.md"
    untemplated.write_text("hand-maintained\n", encoding="utf-8")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    assert "untemplated" not in rule_templates.discover(root)
    assert untemplated.read_text(encoding="utf-8") == "hand-maintained\n"
    target = root / "src" / "claude" / "rules" / "templated.md"
    assert target.read_text(encoding="utf-8") == "body\n"


def test_no_regen_sentinel_skipped_and_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """NO-REGEN sentinel: target skipped, reported at WARN, exit at least 1."""
    root = fake_repo(tmp_path)
    write_template(root, "sentinel", "new\n")
    compile_write = rule_templates.compile_all(root, validate=False)
    assert compile_write.exit_code == 0

    target = root / "src" / "claude" / "rules" / "sentinel.md"
    target.write_text("<!-- NO-REGEN: manual edit -->\nhand\n", encoding="utf-8")

    result = rule_templates.compile_all(root, validate=False)

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
    partials_dir = root / "templates" / "rules" / "partials"
    partials_dir.mkdir(parents=True, exist_ok=True)
    (partials_dir / "bad.mustache").write_text("no newline", encoding="utf-8")
    write_template(root, "test", "{{> bad}}\n")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert "trailing newline" in capsys.readouterr().err.lower()


def test_bad_name_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Bad name: uppercase or special chars, exit 2, reported."""
    root = fake_repo(tmp_path)
    write_template(root, "Bad_Name", "body\n")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    errors = rule_templates.discover_errors(root)
    assert len(errors) == 1
    assert "Bad_Name" in errors[0]
    assert "invalid" in errors[0].lower()


def test_owned_targets_returns_all_rendered_files(tmp_path: Path) -> None:
    """owned_targets: returns set of all src/claude/rules/<name>.md files."""
    root = fake_repo(tmp_path)
    write_template(root, "rule1", "body\n")
    write_template(root, "rule2", "body\n")

    targets = rule_templates.owned_targets(root)

    assert targets == {
        root / "src" / "claude" / "rules" / "rule1.md",
        root / "src" / "claude" / "rules" / "rule2.md",
    }


def test_owned_targets_empty_when_no_valid_templates(tmp_path: Path) -> None:
    """owned_targets: empty when no valid templates discovered."""
    root = fake_repo(tmp_path)
    write_template(root, "Bad_Name", "body\n")

    assert rule_templates.owned_targets(root) == set()


def test_what_if_mode_writes_nothing(tmp_path: Path) -> None:
    """what_if: compile with what_if=True writes nothing."""
    root = fake_repo(tmp_path)
    write_template(root, "test", "body\n")

    result = rule_templates.compile_all(root, validate=False, what_if=True)

    assert result.exit_code == 0
    target = root / "src" / "claude" / "rules" / "test.md"
    assert not target.exists()
    assert result.written == []


def test_rules_dir_symlink_exits_2(tmp_path: Path) -> None:
    """src/claude/rules/ symlink: exit 2, write nothing."""
    root = fake_repo(tmp_path)
    inside = root / "real-rules"
    inside.mkdir()
    claude_dir = root / "src" / "claude"
    claude_dir.mkdir(parents=True)
    link = claude_dir / "rules"
    try:
        link.symlink_to(inside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_template(root, "test", "body\n")
    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    target = root / "src" / "claude" / "rules" / "test.md"
    assert not target.exists()


def test_rule_target_symlink_exits_2(tmp_path: Path) -> None:
    """Rule target symlink: src/claude/rules/<name>.md is a symlink, exit 2."""
    root = fake_repo(tmp_path)
    rules_dir = root / "src" / "claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    write_template(root, "test", "body\n")

    compile_write = rule_templates.compile_all(root, validate=False)
    assert compile_write.exit_code == 0

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "test.md"
    outside_file.write_text("outside content\n", encoding="utf-8")

    target = rules_dir / "test.md"
    try:
        target.unlink()
        target.symlink_to(outside_file)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert target.is_symlink()
    assert outside_file.read_text(encoding="utf-8") == "outside content\n"


def test_rules_dir_symlink_outside_repo_exits_2(tmp_path: Path) -> None:
    """src/claude/rules/ symlink outside repo: exit 2, link target untouched."""
    root = fake_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    claude_dir = root / "src" / "claude"
    claude_dir.mkdir(parents=True)
    link = claude_dir / "rules"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_template(root, "test", "body\n")
    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert link.is_symlink()
    assert not (outside / "test.md").exists()


def test_symlinked_template_source_exits_2(tmp_path: Path) -> None:
    """Symlinked source: templates/rules/<name>.md is a symlink, exit 2, no write."""
    root = fake_repo(tmp_path)
    rules_dir = root / "templates" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    real_template = tmp_path / "real-template.md"
    real_template.write_text("body\n", encoding="utf-8")

    link = rules_dir / "linked.md"
    try:
        link.symlink_to(real_template)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    errors = rule_templates.discover_errors(root)
    assert len(errors) == 1
    assert "symlink" in errors[0].lower()
    assert "linked" not in rule_templates.discover(root)
    target = root / "src" / "claude" / "rules" / "linked.md"
    assert not target.exists()


def test_rules_root_symlink_ancestor_when_leaf_missing_exits_2(tmp_path: Path) -> None:
    """src/claude symlinked outside repo, rules/ absent: exit 2, nothing created outside.

    ``outside`` MUST be a sibling of ``tmp_path``, not a child of it: a
    symlink target under ``tmp_path / "outside"`` still resolves inside the
    repo root (``root`` IS ``tmp_path``), so the containment check would
    pass for the wrong reason. A true sibling is the only way to exercise
    the "resolves outside the repository root" branch this test targets.
    """
    root = fake_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-ancestor"
    outside.mkdir()

    src_dir = root / "src"
    src_dir.mkdir(parents=True)
    claude_link = src_dir / "claude"
    try:
        claude_link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    write_template(root, "test", "body\n")
    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert claude_link.is_symlink()
    assert not (outside / "rules").exists()


def test_discover_on_missing_templates_dir_returns_empty(tmp_path: Path) -> None:
    """Edge: absent templates/rules/ directory yields empty mapping, not an error."""
    root = fake_repo(tmp_path)

    assert rule_templates.discover(root) == {}
    result = rule_templates.compile_all(root, validate=False)
    assert result.exit_code == 0
    assert result.written == []
