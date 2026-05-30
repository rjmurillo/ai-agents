"""Regression guard for .markdownlint-cli2.yaml invariants (Issue #1837).

Issue #1837: ``python3 scripts/validation/pre_pr.py`` failed Markdown Linting on
a pristine ``main`` because the regenerated Copilot CLI skills under
``src/copilot-cli/skills/**`` carried 403 MD040/MD041/MD036 violations, while
their source counterparts under ``.claude/skills/**`` were excluded from lint
scope. The fix excludes the Copilot mirror the same way and scopes MD024 to
siblings so the intentional repeated platform sub-headings in
``docs/installation.md`` pass.

These tests pin the config decisions so a future edit cannot silently drop them
and reintroduce the baseline failure.

Canonical source: ``.markdownlint-cli2.yaml`` (repo root). The exclusion claim
"the Copilot skills tree is excluded the same way ``.claude/skills/**`` is"
is asserted directly against that file's ``ignores`` list rather than
paraphrased, per ``.claude/rules/canonical-source-mirror.md``. The Copilot
skills tree is itself a verbatim directory-copy of ``.claude/skills/`` produced
by ``build/scripts/generate_skills.py`` (module docstring line 2: "Generate
Copilot CLI skill artifacts from .claude/skills/ (REQ-003-001)").
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / ".markdownlint-cli2.yaml"


@pytest.fixture(scope="module")
def config() -> dict:
    """Parsed .markdownlint-cli2.yaml from the repo root."""
    assert CONFIG_PATH.is_file(), f"missing config: {CONFIG_PATH}"
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_config_parses_as_mapping(config: dict) -> None:
    """The config file is a YAML mapping with the expected top-level keys."""
    assert isinstance(config, dict)
    assert "config" in config
    assert "ignores" in config


def test_copilot_skills_excluded_like_claude_skills(config: dict) -> None:
    """Copilot CLI skills get the same blanket lint exclusion as Claude skills.

    The Copilot tree is a verbatim copy of ``.claude/skills/``; both are
    plugin-class content. Excluding one but not the other made pre_pr.py fail on
    a clean checkout (Issue #1837). Assert both globs are present together so the
    asymmetry cannot return.
    """
    ignores = config["ignores"]
    assert ".claude/skills/**" in ignores
    assert "src/copilot-cli/skills/**" in ignores


def test_md024_scoped_to_siblings(config: dict) -> None:
    """MD024 must be siblings_only so repeated platform sub-headings pass.

    docs/installation.md intentionally reuses "Claude Code" and "GitHub Copilot
    CLI" sub-headings under several distinct parent sections. siblings_only
    permits that while still catching true sibling duplicates.
    """
    md024 = config["config"].get("MD024")
    assert isinstance(md024, dict), "MD024 must be configured as a mapping"
    assert md024.get("siblings_only") is True


def test_md040_remains_enabled(config: dict) -> None:
    """MD040 (fenced-code-language) stays on; the authored fixes depend on it.

    The fix added language identifiers to bare fences in agent files, README,
    and eval docs. If MD040 were disabled, those fixes would be unverified.
    """
    assert config["config"].get("MD040") is True


def test_md041_remains_enabled(config: dict) -> None:
    """MD041 (first-line-heading) stays on; agent files keep their H1 to pass it."""
    assert config["config"].get("MD041") is True
