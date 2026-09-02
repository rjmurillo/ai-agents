"""The project-toolkit plugin must stay disabled inside its own checkout.

Issue #4871. `.claude-plugin/marketplace.json` publishes `project-toolkit`
with `"source": "./.claude"`. When cwd is this repository, Claude Code loads
`.claude/agents`, `.claude/skills`, and `.claude/commands` natively at project
scope AND a second time as the installed plugin, so every agent, skill, and
command reaches the system prompt twice: bare (`analyst`) and prefixed
(`project-toolkit:analyst`). Measured duplicate frontmatter payload: 33 agents
(10,138 B) + 95 skills (40,269 B) + 26 commands (3,132 B) = 53,539 B, about
13,385 tokens per session, all of it redundant here.

`.claude/settings.json` turns the plugin off at project scope, which is exactly
the shape `.github/copilot/settings.json` already carries for the Copilot CLI
(PR #4888 / issue #4885). Consumers are unaffected: the plugin stays published
in the marketplace, and a settings.json shipped inside a plugin root is not a
settings source for a consumer working in a different directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
COPILOT_SETTINGS = REPO_ROOT / ".github" / "copilot" / "settings.json"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"

PLUGIN_ID = "project-toolkit@ai-agents"


def _plugin_is_disabled(settings: Any, plugin_id: str) -> bool:
    """Return True iff `settings` turns `plugin_id` off at this scope.

    Only a JSON boolean `false` counts. A missing key, a missing
    `enabledPlugins` block, `true`, `null`, or the string `"false"` all leave
    the plugin enabled, because Claude Code reads the value as JSON and any
    non-`false` value falls through to the user-scope setting.
    """
    if not isinstance(settings, dict):
        return False
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict):
        return False
    return enabled.get(plugin_id) is False


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class TestShippedSettingsDisableTheSelfPlugin:
    """Positive: the committed configuration disables the plugin."""

    def test_claude_settings_disable_project_toolkit(self) -> None:
        assert _plugin_is_disabled(_load(CLAUDE_SETTINGS), PLUGIN_ID), (
            f"{CLAUDE_SETTINGS} must set "
            f'"enabledPlugins": {{"{PLUGIN_ID}": false}} so the plugin does '
            "not load a second time inside its own checkout (issue #4871)"
        )

    def test_copilot_settings_disable_project_toolkit(self) -> None:
        assert _plugin_is_disabled(_load(COPILOT_SETTINGS), PLUGIN_ID), (
            f"{COPILOT_SETTINGS} must keep the same disable (PR #4888)"
        )

    def test_claude_settings_parse_as_json_object(self) -> None:
        settings = _load(CLAUDE_SETTINGS)
        assert isinstance(settings, dict)
        assert isinstance(settings["enabledPlugins"], dict)

    def test_unrelated_settings_keys_survive(self) -> None:
        settings = _load(CLAUDE_SETTINGS)
        for key in ("env", "permissions", "hooks"):
            assert key in settings, (
                f"{key!r} disappeared from {CLAUDE_SETTINGS}; the "
                "enabledPlugins edit must not displace existing config"
            )

    def test_marketplace_still_publishes_the_plugin(self) -> None:
        """The disable is scope-local, not an unpublish."""
        names = {plugin["name"] for plugin in _load(MARKETPLACE)["plugins"]}
        assert "project-toolkit" in names, (
            "consumers still install project-toolkit from this marketplace; "
            "disabling it locally must not remove the published entry"
        )


class TestDisabledPredicateRejectsNonDisablingShapes:
    """Negative and edge: every shape that leaves the plugin enabled."""

    @pytest.mark.parametrize(
        ("settings", "why"),
        [
            ({}, "no enabledPlugins block at all"),
            ({"enabledPlugins": {}}, "block present but plugin unlisted"),
            ({"enabledPlugins": {PLUGIN_ID: True}}, "explicitly enabled"),
            ({"enabledPlugins": {PLUGIN_ID: None}}, "null is not false"),
            ({"enabledPlugins": {PLUGIN_ID: "false"}}, "string is not false"),
            ({"enabledPlugins": {PLUGIN_ID: 0}}, "zero is not false"),
            ({"enabledPlugins": {"project-toolkit": False}}, "id missing marketplace"),
            ({"enabledPlugins": {PLUGIN_ID.upper(): False}}, "ids are case sensitive"),
            ({"enabledPlugins": [PLUGIN_ID]}, "list is the wrong type"),
            ({"enabledPlugins": None}, "null block"),
            ([{"enabledPlugins": {PLUGIN_ID: False}}], "settings is not an object"),
            (None, "settings is null"),
        ],
    )
    def test_non_disabling_shape_returns_false(self, settings: Any, why: str) -> None:
        assert not _plugin_is_disabled(settings, PLUGIN_ID), why

    def test_disabling_shape_returns_true(self) -> None:
        """The predicate is not vacuously false."""
        assert _plugin_is_disabled({"enabledPlugins": {PLUGIN_ID: False}}, PLUGIN_ID)

    def test_other_plugins_are_left_alone(self) -> None:
        """Disabling a sibling does not satisfy the check for this plugin."""
        settings = {"enabledPlugins": {"caveman@caveman": False, PLUGIN_ID: True}}
        assert not _plugin_is_disabled(settings, PLUGIN_ID)
        assert _plugin_is_disabled(settings, "caveman@caveman")
