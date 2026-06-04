"""Tests for build/generate_agent_catalog.py (Issue #1904).

Covers the positive path (templates render to a table), the empty/negative
path (no templates yields a zero-count catalog and a malformed template is
rejected), and drift detection (--check exits non-zero when the committed file
is stale or missing).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_agent_catalog as gac  # noqa: E402

# Helpers --------------------------------------------------------------------


def _write_template(
    templates_dir: Path,
    name: str,
    *,
    description: str = "A test agent.",
    tier: str = "builder",
    extra_body: str = "Body line.\n",
) -> Path:
    """Write a ``<name>.shared.md`` template with the given frontmatter."""
    templates_dir.mkdir(parents=True, exist_ok=True)
    path = templates_dir / f"{name}.shared.md"
    content = (
        "---\n"
        f"tier: {tier}\n"
        f"description: {description}\n"
        "---\n"
        f"# {name.title()} Agent\n"
        f"{extra_body}"
    )
    path.write_text(content, encoding="utf-8")
    return path


# Positive path --------------------------------------------------------------


def test_render_includes_one_row_per_template(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "alpha", description="First agent.", tier="builder")
    _write_template(templates_dir, "beta", description="Second agent.", tier="expert")

    # Act
    content = gac.render_catalog(gac.collect_entries(templates_dir))

    # Assert
    assert "| [alpha](../templates/agents/alpha.shared.md) | builder |" in content
    assert "First agent." in content
    assert "| [beta](../templates/agents/beta.shared.md) | expert |" in content
    assert "_2 agent templates indexed._" in content


def test_entries_are_sorted_by_name(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "zeta")
    _write_template(templates_dir, "alpha")

    # Act
    entries = gac.collect_entries(templates_dir)

    # Assert
    assert [entry.name for entry in entries] == ["alpha", "zeta"]


def test_name_is_derived_from_filename_not_frontmatter(tmp_path: Path) -> None:
    # Arrange: templates carry no name: field; the stem is the source of truth.
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "merge-resolver")

    # Act
    entries = gac.collect_entries(templates_dir)

    # Assert
    assert entries[0].name == "merge-resolver"


def test_loc_counts_every_line(tmp_path: Path) -> None:
    # Arrange: 4 frontmatter lines + 1 heading + 1 body line = 6 lines.
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "alpha", extra_body="Body line.\n")

    # Act
    entries = gac.collect_entries(templates_dir)

    # Assert
    assert entries[0].loc == 6


def test_pipe_in_description_is_escaped(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(
        templates_dir,
        "alpha",
        description="'Use A | B to choose.'",
    )

    # Act
    content = gac.render_catalog(gac.collect_entries(templates_dir))

    # Assert: the literal pipe is escaped so the table column count is intact.
    assert "Use A \\| B to choose." in content


def test_generate_writes_file_and_creates_parent(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "alpha")
    output_path = tmp_path / "docs" / "agent-catalog.md"

    # Act
    written = gac.generate(templates_dir, output_path)

    # Assert
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == written
    assert "# Agent Catalog" in written


# Negative / empty path ------------------------------------------------------


def test_empty_templates_dir_yields_zero_count_catalog(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    templates_dir.mkdir(parents=True)

    # Act
    content = gac.render_catalog(gac.collect_entries(templates_dir))

    # Assert
    assert "_0 agent templates indexed._" in content
    assert gac._TABLE_HEADER in content


def test_missing_frontmatter_raises_catalog_error(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    templates_dir.mkdir(parents=True)
    (templates_dir / "broken.shared.md").write_text("no frontmatter here\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(gac.CatalogError, match="no YAML frontmatter"):
        gac.collect_entries(templates_dir)


def test_invalid_yaml_raises_catalog_error(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    templates_dir.mkdir(parents=True)
    (templates_dir / "broken.shared.md").write_text(
        "---\ndescription: ['unterminated\n---\nbody\n", encoding="utf-8"
    )

    # Act / Assert
    with pytest.raises(gac.CatalogError):
        gac.collect_entries(templates_dir)


def test_main_returns_config_error_when_templates_dir_missing(tmp_path: Path) -> None:
    # Arrange
    missing = tmp_path / "does-not-exist"

    # Act
    code = gac.main(["--templates-path", str(missing), "--output", str(tmp_path / "out.md")])

    # Assert
    assert code == 2


def test_main_returns_external_error_on_bad_template(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    templates_dir.mkdir(parents=True)
    (templates_dir / "broken.shared.md").write_text("not frontmatter\n", encoding="utf-8")

    # Act
    code = gac.main(["--templates-path", str(templates_dir), "--output", str(tmp_path / "out.md")])

    # Assert
    assert code == 3


# Drift detection ------------------------------------------------------------


def test_check_passes_when_committed_matches(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "alpha")
    output_path = tmp_path / "docs" / "agent-catalog.md"
    gac.generate(templates_dir, output_path)

    # Act
    code = gac.main(
        ["--check", "--templates-path", str(templates_dir), "--output", str(output_path)]
    )

    # Assert
    assert code == 0


def test_check_detects_drift(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "alpha")
    output_path = tmp_path / "docs" / "agent-catalog.md"
    gac.generate(templates_dir, output_path)
    # Mutate the committed file so it drifts from the templates.
    output_path.write_text("stale content\n", encoding="utf-8")

    # Act
    code = gac.main(
        ["--check", "--templates-path", str(templates_dir), "--output", str(output_path)]
    )

    # Assert
    assert code == 1


def test_check_detects_drift_after_template_change(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "alpha")
    output_path = tmp_path / "docs" / "agent-catalog.md"
    gac.generate(templates_dir, output_path)
    # Add a new template without regenerating the committed catalog.
    _write_template(templates_dir, "beta")

    # Act
    code = gac.main(
        ["--check", "--templates-path", str(templates_dir), "--output", str(output_path)]
    )

    # Assert
    assert code == 1


def test_check_missing_output_returns_logic_error(tmp_path: Path) -> None:
    # Arrange
    templates_dir = tmp_path / "templates" / "agents"
    _write_template(templates_dir, "alpha")
    output_path = tmp_path / "docs" / "agent-catalog.md"  # never written

    # Act
    code = gac.main(
        ["--check", "--templates-path", str(templates_dir), "--output", str(output_path)]
    )

    # Assert
    assert code == 1


# Committed-artifact gate ----------------------------------------------------


def test_repo_catalog_matches_templates() -> None:
    """The committed docs/agent-catalog.md must match the live templates.

    This is the committed-artifact gate: it runs against the real repo, not a
    fixture, so a hand-edit or a forgotten regeneration fails here.
    """
    # Arrange
    templates_dir = REPO_ROOT / "templates" / "agents"
    output_path = REPO_ROOT / "docs" / "agent-catalog.md"

    # Act
    code = gac.main(
        ["--check", "--templates-path", str(templates_dir), "--output", str(output_path)]
    )

    # Assert
    assert code == 0
