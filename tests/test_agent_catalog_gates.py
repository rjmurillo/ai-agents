"""Regression tests for P0 agent-catalog drift gates."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"
VALIDATE_GENERATED = REPO_ROOT / ".github" / "workflows" / "validate-generated-agents.yml"


def test_pre_commit_regenerates_agent_catalog_with_templates() -> None:
    text = PRE_COMMIT.read_text(encoding="utf-8")

    assert 'GENERATE_AGENT_CATALOG_SCRIPT="$REPO_ROOT/build/generate_agent_catalog.py"' in text
    assert '"$GENERATE_AGENT_CATALOG_SCRIPT"' in text
    assert 'git add -- "$REPO_ROOT/docs/agent-catalog.md"' in text
    assert "Regenerated and staged agent catalog." in text


def test_validate_generated_agents_workflow_triggers_on_catalog_inputs() -> None:
    workflow = yaml.safe_load(VALIDATE_GENERATED.read_text(encoding="utf-8"))
    filters = workflow["jobs"]["check-paths"]["steps"][1]["with"]["filters"]

    assert "docs/agent-catalog.md" in filters
    assert "build/generate_agent_catalog.py" in filters
