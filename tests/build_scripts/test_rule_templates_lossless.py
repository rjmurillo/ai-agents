"""Tests for lossless template rendering to fixtures (ADR-109 B2).

Verifies that rendering templates/rules/<name>.md produces bytes identical
to fixtures in tests/build_scripts/fixtures/rule_templates_b2/expected/<name>.md.
Also verifies that committed src/claude/rules/<name>.md and .claude/rules/<name>.md
equal the fixture. Mirrors test_agent_templates_lossless.py's shape, single-variant.
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

from skill_template_grammar import render  # noqa: E402


def _fixture_dir() -> Path:
    """Return path to the fixtures directory."""
    return _TEST_DIR / "fixtures" / "rule_templates_b2" / "expected"


def _discover_fixture_names() -> list[str]:
    """Discover all names from the fixture directory."""
    fixture_dir = _fixture_dir()
    if not fixture_dir.is_dir():
        return []
    return sorted(path.stem for path in fixture_dir.glob("*.md"))


class TestLosslessRendering:
    """Template rendering must be lossless to fixtures."""

    @pytest.mark.parametrize("name", _discover_fixture_names())
    def test_template_renders_to_fixture(self, name: str) -> None:
        """Rule template renders identically to fixture.

        Every fixture is a byte copy of the pre-migration rule, and every
        template except ``testing.md`` is a byte copy too, so this case
        mostly proves the templates carry no tag; git history is the real
        pin. ``testing.md`` is the one render that transforms (its escape).
        """
        fixture_path = _fixture_dir() / f"{name}.md"
        template_path = _REPO_ROOT / "templates" / "rules" / f"{name}.md"
        partials_dir = _REPO_ROOT / "templates" / "rules" / "partials"

        fixture_bytes = fixture_path.read_bytes()
        rendered = render(template_path, partials_dir)
        rendered_bytes = str(rendered).encode("utf-8")

        assert rendered_bytes == fixture_bytes, (
            f"Rule template for {name} renders differently from fixture. "
            f"Template: {template_path}, Fixture: {fixture_path}"
        )

    @pytest.mark.parametrize("name", _discover_fixture_names())
    def test_committed_claude_plugin_file_equals_fixture(self, name: str) -> None:
        """Committed src/claude/rules/<name>.md equals fixture."""
        fixture_path = _fixture_dir() / f"{name}.md"
        committed_path = _REPO_ROOT / "src" / "claude" / "rules" / f"{name}.md"

        fixture_bytes = fixture_path.read_bytes()
        assert committed_path.is_file(), f"compiled rule missing: {committed_path}"
        committed_bytes = committed_path.read_bytes()
        assert committed_bytes == fixture_bytes, (
            f"Committed file {committed_path} differs from fixture {fixture_path}"
        )

    @pytest.mark.parametrize("name", _discover_fixture_names())
    def test_binplaced_claude_install_file_equals_fixture(self, name: str) -> None:
        """Binplaced .claude/rules/<name>.md equals fixture (unchanged by migration)."""
        fixture_path = _fixture_dir() / f"{name}.md"
        installed_path = _REPO_ROOT / ".claude" / "rules" / f"{name}.md"

        fixture_bytes = fixture_path.read_bytes()
        assert installed_path.is_file(), f"{installed_path} missing"
        installed_bytes = installed_path.read_bytes()
        assert installed_bytes == fixture_bytes, (
            f"Installed file {installed_path} differs from fixture {fixture_path}"
        )

    def test_fixture_count_matches_rules(self) -> None:
        """One fixture per rule under .claude/rules, and the sets agree."""
        names = _discover_fixture_names()
        rules = sorted(p.stem for p in (_REPO_ROOT / ".claude" / "rules").glob("*.md"))
        assert len(names) == len(rules), f"{len(names)} fixtures for {len(rules)} rules"
        assert names == rules, f"fixtures and rules differ: {set(names) ^ set(rules)}"

    def test_testing_rule_uses_the_literal_brace_escape(self) -> None:
        """testing.md templates its GitHub Actions example through the escape."""
        template = (_REPO_ROOT / "templates" / "rules" / "testing.md").read_text(encoding="utf-8")
        rendered = (_REPO_ROOT / ".claude" / "rules" / "testing.md").read_text(encoding="utf-8")
        assert "$\\{{ a && b }}" in template
        assert "${{ a && b }}" in rendered
        assert "\\{{" not in rendered

    def test_negative_control_template_change_is_detected(self, tmp_path: Path) -> None:
        """Appending to template produces different bytes (proves test can fail)."""
        names = _discover_fixture_names()
        if not names:
            pytest.skip("No fixtures found")
        name = names[0]

        fixture_path = _fixture_dir() / f"{name}.md"
        fixture_bytes = fixture_path.read_bytes()

        src_template = _REPO_ROOT / "templates" / "rules" / f"{name}.md"
        tmp_template = tmp_path / f"{name}.md"
        tmp_template.write_bytes(src_template.read_bytes() + b"\n# MODIFIED\n")

        partials_dir = _REPO_ROOT / "templates" / "rules" / "partials"
        rendered = render(tmp_template, partials_dir)
        rendered_bytes = str(rendered).encode("utf-8")

        assert rendered_bytes != fixture_bytes, (
            "Negative control failed: modified template produced fixture bytes"
        )
