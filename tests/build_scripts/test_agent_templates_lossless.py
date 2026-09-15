"""Tests for lossless template rendering to fixtures (ADR-109 B1).

Verifies that rendering templates/agents/<stem>.{claude,copilot}.md.tmpl
with partials produces bytes identical to fixtures in
tests/build_scripts/fixtures/agent_templates_b1/expected/{claude,copilot_source}/<stem>.md.
Also verifies that committed src/claude/agents/<stem>.md equals the fixture.
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
    return _TEST_DIR / "fixtures" / "agent_templates_b1" / "expected"


def _discover_fixture_stems() -> list[str]:
    """Discover all stems from the claude fixture directory."""
    fixture_dir = _fixture_dir()
    claude_dir = fixture_dir / "claude"
    if not claude_dir.is_dir():
        return []
    return sorted(
        path.name[:-3] for path in claude_dir.glob("*.md")
    )


class TestLosslessRendering:
    """Template rendering must be lossless to fixtures."""

    @pytest.mark.parametrize("stem", _discover_fixture_stems())
    def test_claude_template_renders_to_fixture(self, stem: str) -> None:
        """Claude template renders identically to fixture."""
        fixture_dir = _fixture_dir()
        fixture_path = fixture_dir / "claude" / f"{stem}.md"
        template_path = _REPO_ROOT / "templates" / "agents" / f"{stem}.claude.md.tmpl"
        partials_dir = _REPO_ROOT / "templates" / "agents" / "partials"

        fixture_bytes = fixture_path.read_bytes()
        rendered = render(template_path, partials_dir)
        rendered_bytes = str(rendered).encode("utf-8")

        assert rendered_bytes == fixture_bytes, (
            f"Claude template for {stem} renders differently from fixture. "
            f"Template: {template_path}, Fixture: {fixture_path}"
        )

    @pytest.mark.parametrize("stem", _discover_fixture_stems())
    def test_copilot_template_renders_to_fixture(self, stem: str) -> None:
        """Copilot template renders identically to fixture."""
        fixture_dir = _fixture_dir()
        fixture_path = fixture_dir / "copilot_source" / f"{stem}.md"
        template_path = _REPO_ROOT / "templates" / "agents" / f"{stem}.copilot.md.tmpl"
        partials_dir = _REPO_ROOT / "templates" / "agents" / "partials"

        fixture_bytes = fixture_path.read_bytes()
        rendered = render(template_path, partials_dir)
        rendered_bytes = str(rendered).encode("utf-8")

        assert rendered_bytes == fixture_bytes, (
            f"Copilot template for {stem} renders differently from fixture. "
            f"Template: {template_path}, Fixture: {fixture_path}"
        )

    @pytest.mark.parametrize("stem", _discover_fixture_stems())
    def test_committed_claude_file_equals_fixture(self, stem: str) -> None:
        """Committed src/claude/agents/<stem>.md equals fixture."""
        fixture_dir = _fixture_dir()
        fixture_path = fixture_dir / "claude" / f"{stem}.md"
        committed_path = _REPO_ROOT / "src" / "claude" / "agents" / f"{stem}.md"

        fixture_bytes = fixture_path.read_bytes()
        if committed_path.is_file():
            committed_bytes = committed_path.read_bytes()
            assert committed_bytes == fixture_bytes, (
                f"Committed file {committed_path} differs from fixture {fixture_path}"
            )

    def test_fixture_count_is_31(self) -> None:
        """Exactly 31 fixtures must exist."""
        stems = _discover_fixture_stems()
        assert len(stems) == 31, (
            f"Expected 31 fixtures, found {len(stems)}: {stems}"
        )

    def test_negative_control_template_change_is_detected(
        self, tmp_path: Path
    ) -> None:
        """Appending to template produces different bytes (proves test can fail)."""
        fixture_dir = _fixture_dir()
        stems = _discover_fixture_stems()
        if not stems:
            pytest.skip("No fixtures found")
        stem = stems[0]

        fixture_path = fixture_dir / "claude" / f"{stem}.md"
        fixture_bytes = fixture_path.read_bytes()

        # Copy template to tmp_path and modify it
        src_template = _REPO_ROOT / "templates" / "agents" / f"{stem}.claude.md.tmpl"
        tmp_template = tmp_path / f"{stem}.claude.md.tmpl"
        tmp_template.write_bytes(src_template.read_bytes() + b"\n# MODIFIED\n")

        partials_dir = _REPO_ROOT / "templates" / "agents" / "partials"
        rendered = render(tmp_template, partials_dir)
        rendered_bytes = str(rendered).encode("utf-8")

        assert rendered_bytes != fixture_bytes, (
            "Negative control failed: modified template produced fixture bytes"
        )
