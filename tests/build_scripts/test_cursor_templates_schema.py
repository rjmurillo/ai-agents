"""Schema keys added for the Cursor tree (ADR-115 Decision 2).

``artifacts.rules.outputFormat``, ``artifacts.skills.frontmatterKeep``,
``artifacts.agents.frontmatterKeep`` and ``artifacts.agents.deriveReadonly``,
each with positive, negative, and edge cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_templates_schema as vts  # noqa: E402


def _errors(artifact: str, stanza: object) -> list[str]:
    return vts._validate_artifact_stanza(artifact, stanza)


def _rules(**extra: object) -> dict[str, object]:
    return {"sourceDir": "src/claude/rules", "outputDir": "src/x/rules", **extra}


def _skills(**extra: object) -> dict[str, object]:
    return {"sourceDir": "src/claude/skills", "outputDir": "src/x/skills", **extra}


def _agents(**extra: object) -> dict[str, object]:
    return {"sourceDir": "src/claude/agents", "outputDir": "src/x/agents", **extra}


# rules.outputFormat ----------------------------------------------------------


@pytest.mark.parametrize("value", ["instructions", "cursor-mdc"])
def test_rules_output_format_accepts_known_values(value: str) -> None:
    assert _errors("rules", _rules(outputFormat=value)) == []


def test_rules_output_format_is_optional() -> None:
    assert _errors("rules", _rules()) == []


@pytest.mark.parametrize("value", ["mdc", "Instructions", "", None, 3, ["cursor-mdc"], True])
def test_rules_output_format_rejects_other_values(value: object) -> None:
    errors = _errors("rules", _rules(outputFormat=value))
    assert len(errors) == 1
    assert "outputFormat" in errors[0]


# skills.frontmatterKeep ------------------------------------------------------


def test_skills_keep_accepts_a_list_of_strings() -> None:
    assert _errors("skills", _skills(frontmatterKeep=["name", "description"])) == []


@pytest.mark.parametrize("value", ["name", None, [1], ["name", None], {"name": 1}])
def test_skills_keep_rejects_non_string_lists(value: object) -> None:
    errors = _errors("skills", _skills(frontmatterKeep=value))
    assert any("frontmatterKeep" in e and "list of strings" in e for e in errors)


def test_skills_keep_rejects_an_empty_list() -> None:
    errors = _errors("skills", _skills(frontmatterKeep=[]))
    assert any("must not be empty" in e for e in errors)


def test_skills_keep_and_drop_are_mutually_exclusive() -> None:
    errors = _errors("skills", _skills(frontmatterKeep=["name"], frontmatterDrop=["model"]))
    assert any("mutually exclusive" in e for e in errors)


def test_skills_drop_alone_is_still_valid() -> None:
    assert _errors("skills", _skills(frontmatterDrop=["model"])) == []


# agents.frontmatterKeep and deriveReadonly -----------------------------------


def test_agents_keep_with_directories_is_valid() -> None:
    stanza = _agents(frontmatterKeep=["name", "description"], deriveReadonly=True)
    assert _errors("agents", stanza) == []


@pytest.mark.parametrize("missing", ["sourceDir", "outputDir"])
def test_agents_keep_requires_both_directories(missing: str) -> None:
    stanza = _agents(frontmatterKeep=["name"])
    del stanza[missing]
    errors = _errors("agents", stanza)
    assert any(f"requires `{missing}`" in e for e in errors)


@pytest.mark.parametrize("value", [[], "name", None, [3]])
def test_agents_keep_rejects_bad_lists(value: object) -> None:
    assert _errors("agents", _agents(frontmatterKeep=value))


@pytest.mark.parametrize("value", ["true", 1, None])
def test_agents_derive_readonly_must_be_boolean(value: object) -> None:
    errors = _errors("agents", _agents(frontmatterKeep=["name"], deriveReadonly=value))
    assert any("deriveReadonly" in e and "boolean" in e for e in errors)


def test_agents_derive_readonly_requires_keep() -> None:
    errors = _errors("agents", _agents(deriveReadonly=True))
    assert any("requires `frontmatterKeep`" in e for e in errors)


def test_agents_keep_path_traversal_in_source_dir_is_rejected() -> None:
    stanza = _agents(frontmatterKeep=["name"], sourceDir="../escape")
    assert _errors("agents", stanza)


def test_copilot_agents_stanza_without_new_keys_is_unchanged() -> None:
    stanza = {
        "sourceDir": "templates/agents",
        "outputDir": "src/copilot-cli/agents",
        "excludeFilenames": ["AGENTS.md"],
    }
    assert _errors("agents", stanza) == []


def test_every_committed_platform_config_validates() -> None:
    configs = vts.find_platform_configs(REPO_ROOT)
    assert any(c.name == "cursor.yaml" for c in configs)
    for config in configs:
        assert vts.validate_file(config) == ([], False), config.name
