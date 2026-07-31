"""Regression guard for .markdownlint-cli2.yaml invariants.

Issue #1837: ``python3 scripts/validation/pre_pr.py`` failed Markdown Linting on
a pristine ``main`` because the regenerated Copilot CLI skills under
``src/copilot-cli/skills/**`` carried 403 MD040/MD041/MD036 violations, while
their source counterparts under ``.claude/skills/**`` were excluded from lint
scope. The fix at the time excluded both trees. Those violations were
subsequently fixed, so both blanket exclusions are now stale (issue #4038,
measured 2026-07-30: 0 violations in either tree under the project config).

These tests guard the invariants that matter going forward:
- The blanket skill-tree exclusions are ABSENT (to catch a regression
  back to the stale exclusion pattern).
- MD024, MD040, MD041 remain in their required states.

Canonical source: ``.markdownlint-cli2.yaml`` (repo root).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / ".markdownlint-cli2.yaml"


@pytest.fixture(scope="module")
def config() -> dict[str, object]:
    """Parsed .markdownlint-cli2.yaml from the repo root."""
    assert CONFIG_PATH.is_file(), f"missing config: {CONFIG_PATH}"
    return cast(dict[str, object], yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))


def test_config_parses_as_mapping(config: dict[str, object]) -> None:
    """The config file is a YAML mapping with the expected top-level keys."""
    assert isinstance(config, dict)
    assert "config" in config
    assert "ignores" in config


def test_blanket_claude_skills_exclusion_removed(config: dict[str, object]) -> None:
    """Blanket ``.claude/skills/**`` exclusion must not be in ignores.

    The exclusion was added in PR #331 under the label "third-party plugins."
    Measured 2026-07-30: 0 violations in 357 ``.claude/skills/**/*.md`` files
    under the project config.  The stated rationale is false; the exclusion
    is a detector that cannot fail on the paths it covers (issue #4038).

    This test is the negative control: it fails if the blanket exclusion
    is re-added, preventing silent regression to the stale suppression.
    """
    ignores = cast(list[str], config["ignores"])
    assert ".claude/skills/**" not in ignores, (
        ".claude/skills/** blanket exclusion was re-added; "
        "see issue #4038 for the measured rationale that it is stale."
    )


def test_blanket_copilot_skills_exclusion_removed(config: dict[str, object]) -> None:
    """Blanket ``src/copilot-cli/skills/**`` exclusion must not be in ignores.

    Issue #1837 added this exclusion because the mirror tree carried 403
    violations at the time.  Measured 2026-07-30: 0 violations in 367
    ``src/copilot-cli/skills/**/*.md`` files (issue #4038).
    """
    ignores = cast(list[str], config["ignores"])
    assert "src/copilot-cli/skills/**" not in ignores, (
        "src/copilot-cli/skills/** blanket exclusion was re-added; "
        "see issue #4038 for the measured rationale that it is stale."
    )


def test_md024_scoped_to_siblings(config: dict[str, object]) -> None:
    """MD024 must be siblings_only so repeated platform sub-headings pass.

    docs/installation.md intentionally reuses "Claude Code" and "GitHub Copilot
    CLI" sub-headings under several distinct parent sections. siblings_only
    permits that while still catching true sibling duplicates.
    """
    md024 = cast(dict[str, Any], config["config"]).get("MD024")
    assert isinstance(md024, dict), "MD024 must be configured as a mapping"
    assert md024.get("siblings_only") is True


def test_md040_remains_enabled(config: dict[str, object]) -> None:
    """MD040 (fenced-code-language) stays on; the authored fixes depend on it.

    The fix added language identifiers to bare fences in agent files, README,
    and eval docs. If MD040 were disabled, those fixes would be unverified.
    """
    assert cast(dict[str, Any], config["config"]).get("MD040") is True


def test_md041_remains_enabled(config: dict[str, object]) -> None:
    """MD041 (first-line-heading) stays on; agent files keep their H1 to pass it."""
    assert cast(dict[str, Any], config["config"]).get("MD041") is True

