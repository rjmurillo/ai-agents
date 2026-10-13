"""Committed Cursor plugin artifacts against Cursor's published schemas (ADR-115).

Decision 11 requires each manifest to validate against the host's schema. The
schemas live in ``tests/fixtures/cursor-plugin/`` (source URLs in ``SOURCE.md``).
The negative controls prove those schemas are closed, so a pass means something.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "cursor-plugin"
CURSOR_TREE = REPO_ROOT / "src" / "cursor"
PLUGIN_JSON = CURSOR_TREE / ".cursor-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".cursor-plugin" / "marketplace.json"
CLAUDE_TREE = REPO_ROOT / "src" / "claude"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str) -> Draft7Validator:
    schema = _load(FIXTURES / name)
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


@pytest.fixture(scope="module")
def plugin_schema() -> Draft7Validator:
    return _validator("plugin.schema.json")


@pytest.fixture(scope="module")
def marketplace_schema() -> Draft7Validator:
    return _validator("marketplace.schema.json")


# Schema fixtures -------------------------------------------------------------


def test_fixture_schemas_are_cursors_and_closed() -> None:
    plugin = _load(FIXTURES / "plugin.schema.json")
    marketplace = _load(FIXTURES / "marketplace.schema.json")
    assert plugin["$id"] == "https://cursor.com/schemas/cursor-plugin/plugin.json"
    assert marketplace["$id"] == "https://cursor.com/schemas/cursor-plugin/marketplace.json"
    assert plugin["additionalProperties"] is False
    assert marketplace["additionalProperties"] is False


def test_source_note_names_both_upstream_urls() -> None:
    note = (FIXTURES / "SOURCE.md").read_text(encoding="utf-8")
    assert "cursor/plugins/main/schemas/plugin.schema.json" in note
    assert "cursor/plugins/main/schemas/marketplace.schema.json" in note


# plugin.json -----------------------------------------------------------------


def test_plugin_json_validates_against_the_official_schema(plugin_schema: Draft7Validator) -> None:
    errors = sorted(e.message for e in plugin_schema.iter_errors(_load(PLUGIN_JSON)))
    assert errors == []


def test_plugin_json_carries_no_version(plugin_schema: Draft7Validator) -> None:
    assert "version" not in _load(PLUGIN_JSON)  # ADR-092


def test_plugin_json_names_the_shared_toolkit_plugin() -> None:
    data = _load(PLUGIN_JSON)
    assert data["name"] == "project-toolkit"
    assert data["author"] == {"name": "rjmurillo"}
    assert data["repository"].startswith("https://")
    assert data["homepage"].startswith("https://")


def test_plugin_json_declares_no_component_paths() -> None:
    """Default discovery finds skills/, rules/, and agents/ without them."""
    data = _load(PLUGIN_JSON)
    assert not {"skills", "rules", "agents", "commands", "hooks", "mcpServers"} & set(data)


@pytest.mark.parametrize(
    "mutation",
    [
        {"name": "Project Toolkit"},
        {"name": ""},
        {"unknownKey": 1},
        {"author": {"email": "x@example.com"}},
        {"keywords": "not-a-list"},
    ],
)
def test_schema_rejects_bad_plugin_manifests(
    plugin_schema: Draft7Validator, mutation: dict[str, object]
) -> None:
    bad = {**_load(PLUGIN_JSON), **mutation}
    assert list(plugin_schema.iter_errors(bad))


def test_schema_requires_a_plugin_name(plugin_schema: Draft7Validator) -> None:
    assert list(plugin_schema.iter_errors({"description": "no name"}))


# marketplace.json ------------------------------------------------------------


def test_marketplace_validates_against_the_official_schema(
    marketplace_schema: Draft7Validator,
) -> None:
    errors = sorted(e.message for e in marketplace_schema.iter_errors(_load(MARKETPLACE_JSON)))
    assert errors == []


def test_marketplace_lists_exactly_the_cursor_tree() -> None:
    data = _load(MARKETPLACE_JSON)
    assert data["name"] == "ai-agents"
    assert [(p["name"], p["source"]) for p in data["plugins"]] == [
        ("project-toolkit", "./src/cursor")
    ]


def test_marketplace_declares_an_owner() -> None:
    """The docs call owner required; the schema does not. Emit it to satisfy both."""
    assert _load(MARKETPLACE_JSON)["owner"]["name"] == "rjmurillo"


def test_marketplace_entry_uses_only_schema_keys_and_no_version() -> None:
    for entry in _load(MARKETPLACE_JSON)["plugins"]:
        assert set(entry) <= {"name", "source", "description", "minClientVersions"}
        assert "version" not in entry


def test_marketplace_entry_describes_the_same_plugin_as_the_manifest() -> None:
    entry = _load(MARKETPLACE_JSON)["plugins"][0]
    assert entry["description"] == _load(PLUGIN_JSON)["description"]


def test_marketplace_source_is_a_relative_dir_holding_the_manifest() -> None:
    source = _load(MARKETPLACE_JSON)["plugins"][0]["source"]
    assert source.startswith("./")
    assert ".." not in source
    assert (REPO_ROOT / source / ".cursor-plugin" / "plugin.json").is_file()


@pytest.mark.parametrize(
    "mutation",
    [
        {"plugins": [{"name": "x"}]},
        {"plugins": [{"name": "x", "source": {"path": "./a"}}]},
        {"plugins": [{"name": "x", "source": "./a", "version": "1.0.0"}]},
        {"unknown": True},
        {"plugins": "nope"},
    ],
)
def test_schema_rejects_bad_marketplaces(
    marketplace_schema: Draft7Validator, mutation: dict[str, object]
) -> None:
    bad = {**_load(MARKETPLACE_JSON), **mutation}
    assert list(marketplace_schema.iter_errors(bad))


# Tree contents ---------------------------------------------------------------


def test_cursor_tree_ships_the_same_skill_set_as_the_claude_tree() -> None:
    claude = sorted(p.parent.name for p in (CLAUDE_TREE / "skills").glob("*/SKILL.md"))
    cursor = sorted(p.parent.name for p in (CURSOR_TREE / "skills").glob("*/SKILL.md"))
    assert cursor, "no skills found in the Claude tree"
    assert cursor == claude


def test_skill_support_files_are_byte_identical_to_the_claude_tree() -> None:
    mismatched = []
    for src in (CLAUDE_TREE / "skills").rglob("*"):
        if not src.is_file() or src.name == "SKILL.md" or "__pycache__" in src.parts:
            continue
        dst = CURSOR_TREE / "skills" / src.relative_to(CLAUDE_TREE / "skills")
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            mismatched.append(src.relative_to(CLAUDE_TREE).as_posix())
    assert mismatched == []


def test_skill_bodies_are_byte_identical_to_the_claude_tree() -> None:
    for src in (CLAUDE_TREE / "skills").glob("*/SKILL.md"):
        dst = CURSOR_TREE / "skills" / src.parent.name / "SKILL.md"
        assert dst.read_text(encoding="utf-8").endswith(
            src.read_text(encoding="utf-8").split("\n---\n", 1)[1]
        ), src.parent.name


def test_rules_are_mdc_only_and_none_is_all_internal() -> None:
    rules = sorted(p.name for p in (CURSOR_TREE / "rules").iterdir())
    assert rules
    assert all(name.endswith(".mdc") for name in rules)
    for path in (CURSOR_TREE / "rules").glob("*.mdc"):
        head = path.read_text(encoding="utf-8").split("---")[1]
        assert "priority" not in head and "applyTo" not in head and "paths" not in head
        assert "alwaysApply:" in head
        assert ".claude/" not in head


def test_the_always_on_rules_are_always_applied() -> None:
    for name in ("universal", "builder-ethos", "voice"):
        path = CURSOR_TREE / "rules" / f"{name}.mdc"
        if path.exists():
            assert "alwaysApply: true" in path.read_text(encoding="utf-8").split("---")[1]


def test_no_repository_guide_ships_at_the_cursor_plugin_root() -> None:
    """A root AGENTS.md would load as an always-on rule. Skill-nested guides match src/claude."""
    guides = [p.name for p in CURSOR_TREE.iterdir() if p.name in {"AGENTS.md", "CLAUDE.md"}]
    assert guides == []
    for sub in ("rules", "agents", "lib"):
        assert not list((CURSOR_TREE / sub).rglob("AGENTS.md")), sub
        assert not list((CURSOR_TREE / sub).rglob("CLAUDE.md")), sub


def test_cursor_tree_has_lib_for_skill_scripts() -> None:
    lib = CURSOR_TREE / "lib"
    assert {p.name for p in lib.iterdir() if p.name != "__pycache__"} == {
        "ai_review_common",
        "bootstrap.py",
        "github_core",
        "hook_utilities",
    }
    assert (CURSOR_TREE / "skills" / "review" / "scripts" / "validate_review_marker.py").is_file()


def test_cursor_tree_ships_no_hooks() -> None:
    assert not (CURSOR_TREE / "hooks").exists()


def test_cursor_files_are_scanned_for_component_counts() -> None:
    """Both Cursor files publish a description, so the count gate scans both."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
    import check_plugin_manifest_parity as parity

    scanned = {path.resolve() for path in parity._DESCRIBED_FILES}
    assert MARKETPLACE_JSON.resolve() in scanned
    assert PLUGIN_JSON.resolve() in scanned
