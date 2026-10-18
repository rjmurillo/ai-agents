"""Tests for build/scripts/rule_distribution.py (ADR-119 decision 13).

Covers the repo-only classifier, the pinned set of repo-only rules, its
agreement with the shipped Copilot instruction tree, and a rule flipping
between shipped and repo-only in both directions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import rule_distribution  # noqa: E402
import rule_templates  # noqa: E402

# A change to this set changes what the Claude plugin ships. Edit it only on
# purpose, in the same change that edits the rule's `paths:` scope.
_PINNED_REPO_ONLY = frozenset(
    {
        "adr-records",
        "governance",
        "push-lock",
        "secret-redaction",
        "session-logs",
        "tool-use-hook-bar",
    }
)


def _rule(paths: str) -> str:
    return f"---\npaths: {paths}\n---\n# Rule\n"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_rule('[".claude/**", ".agents/x/**"]'), True),
        (_rule('".project-toolkit/**, .serena/memories/**"'), True),
        (_rule('[".claude/**", "docs/**"]'), False),
        (_rule('["**"]'), False),
        (_rule("[]"), False),
        ("# no frontmatter\n", False),
        ("---\npriority: high\n---\nbody\n", False),
        ("---\n- just a list\n---\nbody\n", False),
    ],
    ids=[
        "list-all-internal",
        "comma-string-all-internal",
        "mixed-scope-ships",
        "always-on-ships",
        "empty-list-ships",
        "no-frontmatter-ships",
        "unscoped-ships",
        "non-mapping-frontmatter-ships",
    ],
)
def test_is_repo_only(text: str, expected: bool) -> None:
    assert rule_distribution.is_repo_only(text) is expected


def test_malformed_frontmatter_raises_instead_of_shipping(tmp_path: Path) -> None:
    tmpl = tmp_path / "bad.md"
    tmpl.write_text("---\npaths: [unclosed\n---\nbody\n", encoding="utf-8")
    with pytest.raises(Exception, match="flow sequence|expected"):
        rule_distribution.render_target(tmp_path, "bad", tmpl)


def test_live_repo_only_set_is_pinned() -> None:
    assert rule_distribution.repo_only_rule_names(_REPO_ROOT) == _PINNED_REPO_ONLY


def test_live_repo_only_set_matches_what_copilot_skips() -> None:
    """The template-side classifier and generate_rules' scope skip agree."""
    templates = {p.stem for p in (_REPO_ROOT / "templates" / "rules").glob("*.md")}
    shipped = {
        p.name.removesuffix(".instructions.md")
        for p in (_REPO_ROOT / "src" / "copilot-cli" / "instructions").glob("*.instructions.md")
    }
    assert templates - shipped == _PINNED_REPO_ONLY


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "templates" / "rules").mkdir(parents=True)
    return tmp_path


def _write(root: Path, name: str, paths: str) -> None:
    (root / "templates" / "rules" / f"{name}.md").write_text(_rule(paths), encoding="utf-8")


def _link_shipped(root: Path, name: str) -> Path:
    link = root / ".claude" / "rules" / f"{name}.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(f"../../src/claude/rules/{name}.md")
    return link


def test_shipped_rule_turning_repo_only_replaces_its_link(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "flip", '["docs/**"]')
    assert rule_templates.compile_all(root, validate=False).exit_code == 0
    link = _link_shipped(root, "flip")
    plugin_copy = root / "src" / "claude" / "rules" / "flip.md"
    assert plugin_copy.is_file()

    _write(root, "flip", '[".claude/**"]')
    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    assert not link.is_symlink()
    assert link.read_text(encoding="utf-8") == _rule('[".claude/**"]')
    assert not plugin_copy.exists()
    assert rule_templates.compile_all(root, validate=True).exit_code == 0


def test_flip_in_validate_mode_reports_drift_and_writes_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "flip", '["docs/**"]')
    rule_templates.compile_all(root, validate=False)
    link = _link_shipped(root, "flip")
    _write(root, "flip", '[".claude/**"]')

    result = rule_templates.compile_all(root, validate=True)

    assert result.exit_code == 1
    assert link.is_symlink()
    assert (root / "src" / "claude" / "rules" / "flip.md").is_file()


def test_foreign_symlink_at_repo_only_target_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "inner", '[".claude/**"]')
    outside = tmp_path / "outside.md"
    outside.write_text("do not overwrite\n", encoding="utf-8")
    planted = root / ".claude" / "rules" / "inner.md"
    planted.parent.mkdir(parents=True)
    planted.symlink_to(outside)

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert outside.read_text(encoding="utf-8") == "do not overwrite\n"
    assert os.readlink(planted) == str(outside)


def test_repo_only_rule_turning_shipped_moves_to_plugin_tree(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "flip", '[".claude/**"]')
    rule_templates.compile_all(root, validate=False)
    assert (root / ".claude" / "rules" / "flip.md").is_file()

    _write(root, "flip", '[".claude/**", "docs/**"]')
    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 0
    assert (root / "src" / "claude" / "rules" / "flip.md").is_file()
    # The stale real file is binplace's to replace with a link (_link_one).
    assert rule_distribution.render_target(
        root, "flip", root / "templates" / "rules" / "flip.md"
    ) == (root / "src" / "claude" / "rules" / "flip.md")
