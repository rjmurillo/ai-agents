"""The project-toolkit plugin must stay disabled inside its own checkout.

Issue #4871. `.claude-plugin/marketplace.json` publishes `project-toolkit`
with `"source": "./.claude"`. When cwd is this repository, Claude Code loads
`.claude/agents`, `.claude/skills`, and `.claude/commands` natively at project
scope AND a second time as the installed plugin, so every agent, skill, and
command reaches the system prompt twice: bare (`analyst`) and prefixed
(`project-toolkit:analyst`). Measured duplicate frontmatter payload, counting
`name` plus `description` across the files that carry frontmatter: 31 agents
(10,534 B) + 95 skills (42,182 B) + 25 commands (3,132 B) = 55,848 B, about
13,962 tokens per session, all of it redundant here. The file counts are lower
than a raw glob (33 agent files, 26 command files) because `AGENTS.md` and
`CLAUDE.md` carry no frontmatter and load nothing.

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


# Issue #5457: both harnesses install Ponytail from repository configuration,
# pinned to the same reviewed release. Both harnesses pin through `ref`.
# Copilot CLI 1.0.89 ignores a marketplace `sha`: with `sha` alone, a clean
# install checked out upstream main. Copilot also keeps `sha` so the reviewed
# commit is recorded next to the tag. `evals/ponytail-incumbent/README.md`
# records the live check that the tag resolves to this commit.
PONYTAIL_ID = "ponytail@ponytail"
PONYTAIL_REPO = "DietrichGebert/ponytail"
PONYTAIL_TAG = "v4.9.0"
PONYTAIL_SHA = "0a4dd63ad4541f4f655c4108a295916f3c1d8fda"
COPILOT_PINS = {"ref": PONYTAIL_TAG, "sha": PONYTAIL_SHA}

# A phrase unique to Ponytail's SKILL.md. Finding it in a repository
# instruction surface means someone copied the ruleset instead of installing it.
PONYTAIL_FINGERPRINT = "The best code is the code never written"
INSTRUCTION_SURFACES = (
    "AGENTS.md",
    "CLAUDE.md",
    ".github/copilot-instructions.md",
    ".github/instructions",
    ".claude/rules",
    ".claude/skills",
    ".claude/agents",
    "templates",
    "src",
)


def _ponytail_pin_errors(settings: Any, pins: dict[str, str]) -> list[str]:
    """Return every way `settings` fails to install the reviewed Ponytail."""
    if not isinstance(settings, dict):
        return ["settings is not a JSON object"]
    errors = []
    markets = settings.get("extraKnownMarketplaces")
    source = markets.get("ponytail", {}) if isinstance(markets, dict) else {}
    source = source.get("source") if isinstance(source, dict) else None
    if not isinstance(source, dict):
        errors.append("marketplace 'ponytail' is not declared")
    else:
        if source.get("source") != "github" or source.get("repo") != PONYTAIL_REPO:
            errors.append(f"marketplace 'ponytail' is not github {PONYTAIL_REPO}")
        for key, value in pins.items():
            if source.get(key) != value:
                errors.append(f"marketplace 'ponytail' {key} is not {value}")
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict) or enabled.get(PONYTAIL_ID) is not True:
        errors.append(f"{PONYTAIL_ID} is not enabled with JSON true")
    return errors


class TestPonytailIsInstalledFromRepositoryConfig:
    """Positive: both harnesses pin the same reviewed Ponytail release."""

    def test_claude_settings_pin_the_reviewed_tag(self) -> None:
        assert _ponytail_pin_errors(_load(CLAUDE_SETTINGS), {"ref": PONYTAIL_TAG}) == []

    def test_copilot_settings_pin_the_reviewed_commit(self) -> None:
        assert _ponytail_pin_errors(_load(COPILOT_SETTINGS), COPILOT_PINS) == []

    def test_copilot_keeps_its_other_marketplaces(self) -> None:
        markets = _load(COPILOT_SETTINGS)["extraKnownMarketplaces"]
        for name in ("caveman", "ai-agents", "agent-plugins", "graybeard"):
            assert name in markets, f"repinning Ponytail displaced {name!r}"

    def test_no_instruction_surface_copies_the_ruleset(self) -> None:
        hits = []
        for surface in INSTRUCTION_SURFACES:
            root = REPO_ROOT / surface
            files = [root] if root.is_file() else sorted(root.rglob("*"))
            for path in files:
                rel = path.relative_to(REPO_ROOT).as_posix()
                if path.is_dir() and path.name.startswith("ponytail"):
                    hits.append(f"{rel}: local ponytail directory shadows the plugin")
                elif path.is_file() and path.suffix in {".md", ".json", ".yaml", ".tmpl"}:
                    if PONYTAIL_FINGERPRINT in path.read_text(encoding="utf-8", errors="ignore"):
                        hits.append(f"{rel}: copies Ponytail's SKILL.md")
        assert hits == [], "\n".join(hits)


def _source(settings: dict[str, Any]) -> dict[str, Any]:
    return settings["extraKnownMarketplaces"]["ponytail"]["source"]


class TestPonytailPinPredicateRejectsDrift:
    """Negative and edge: every shape that drops or repoints the plugin."""

    GOOD = {
        "extraKnownMarketplaces": {
            "ponytail": {"source": {"source": "github", "repo": PONYTAIL_REPO, **COPILOT_PINS}}
        },
        "enabledPlugins": {PONYTAIL_ID: True},
    }

    def test_good_shape_passes(self) -> None:
        assert _ponytail_pin_errors(self.GOOD, COPILOT_PINS) == []

    @pytest.mark.parametrize(
        ("mutate", "why"),
        [
            (lambda s: s.pop("extraKnownMarketplaces"), "marketplace dropped"),
            (lambda s: s["extraKnownMarketplaces"].pop("ponytail"), "ponytail entry dropped"),
            (lambda s: s["extraKnownMarketplaces"]["ponytail"].pop("source"), "source dropped"),
            (lambda s: _source(s).update(repo="fork/ponytail"), "repointed repo"),
            (lambda s: _source(s).update(source="url"), "wrong source kind"),
            (
                lambda s: _source(s).update(sha="2ed6c52c9d7e5e56942508591085fd45dea277d3"),
                "old sha",
            ),
            (lambda s: _source(s).pop("sha"), "sha dropped"),
            (lambda s: _source(s).pop("ref"), "ref dropped, sha alone does not pin"),
            (lambda s: _source(s).update(ref="main"), "floating ref"),
            (lambda s: s.pop("enabledPlugins"), "enabledPlugins dropped"),
            (lambda s: s["enabledPlugins"].update({PONYTAIL_ID: False}), "disabled"),
            (lambda s: s["enabledPlugins"].update({PONYTAIL_ID: "true"}), "string is not true"),
        ],
    )
    def test_drift_is_reported(self, mutate: Any, why: str) -> None:
        settings = json.loads(json.dumps(self.GOOD))
        mutate(settings)
        assert _ponytail_pin_errors(settings, COPILOT_PINS), why

    @pytest.mark.parametrize("settings", [None, [], "x"])
    def test_non_object_settings_fail(self, settings: Any) -> None:
        assert _ponytail_pin_errors(settings, COPILOT_PINS)
