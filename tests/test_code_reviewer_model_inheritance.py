"""code-reviewer inherits the host model on Copilot hosts (issue #6638).

Copilot CLI refused `claude-haiku-4.5` on a host that did not offer it, so the
reviewer never started when the caller omitted `model`. The Copilot CLI and
VS Code projections carry no `model:` key and inherit the host default
(ADR-119 decision 11). This module pins that in the committed trees. Claude
pins are the owner's call and are not asserted here.

CI has no Copilot CLI host, so these checks read the generated output. A
top-level Copilot CLI 1.0.98 Linux run is recorded on the pull request. The
`task` subagent dispatch path on 1.0.99-3 Windows, where the failure was first
seen, is unverified.

The last section guards every generated Copilot-side agent, not only
code-reviewer. `scripts/validation/check_model_pins.py` reads `src/copilot-cli`
only through the `.github/agents` symlinks and never reads `src/vs-code-agents`,
and the generator turns `model_tier: haiku` into a versioned id, so a
new haiku-tier template would bring the bug back unseen.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "build"))

from model_pin_manifest import format_model_id_for_platform  # noqa: E402

COPILOT_SIDE_FILES = (
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "code-reviewer.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "code-reviewer.agent.md",
    REPO_ROOT / ".github" / "agents" / "code-reviewer.agent.md",
)
COPILOT_TEMPLATES = (
    REPO_ROOT / "templates" / "agents" / "code-reviewer.copilot.md.tmpl",
    REPO_ROOT / "templates" / "agents" / "code-reviewer.shared.md",
)


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, block, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(block)
    assert isinstance(loaded, dict), f"{path} frontmatter is not a mapping"
    return loaded


def _assert_no_model(path: Path) -> None:
    assert "model" not in _frontmatter(path), (
        f"{path} pins a model, so a host without it rejects the reviewer."
    )


@pytest.mark.parametrize("path", COPILOT_SIDE_FILES, ids=lambda p: p.parent.parent.name)
def test_copilot_side_code_reviewer_sets_no_model(path: Path) -> None:
    _assert_no_model(path)


@pytest.mark.parametrize("path", COPILOT_TEMPLATES, ids=lambda p: p.name)
def test_copilot_side_template_sets_no_model_tier(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert not [line for line in lines if line.startswith("model_tier:")]


def test_versioned_haiku_id_is_absent_from_copilot_side_files() -> None:
    for path in COPILOT_SIDE_FILES:
        text = path.read_text(encoding="utf-8")
        assert "claude-haiku-4.5" not in text
        assert "Claude Haiku 4.5" not in text


def test_pinned_model_is_detected(tmp_path: Path) -> None:
    """Negative control: a reviewer that pins a model fails the check."""
    agent = tmp_path / "code-reviewer.agent.md"
    agent.write_text("---\ndescription: x\nmodel: claude-haiku-4.5\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="pins a model"):
        _assert_no_model(agent)


def test_unpinned_model_passes_check(tmp_path: Path) -> None:
    """Edge: frontmatter with no model key passes."""
    agent = tmp_path / "code-reviewer.agent.md"
    agent.write_text("---\ndescription: x\n---\nbody\n", encoding="utf-8")

    _assert_no_model(agent)


# Repo-wide guard: no generated Copilot-side agent pins a model without evidence.
GENERATED_COPILOT_AGENT_GLOBS = (
    "src/copilot-cli/agents/*.agent.md",
    "src/vs-code-agents/*.agent.md",
    ".github/agents/*.agent.md",
)
PIN_MANIFEST = REPO_ROOT / ".agents" / "governance" / "model-pin-evidence.json"


def _generated_copilot_agents() -> list[Path]:
    found: list[Path] = []
    for pattern in GENERATED_COPILOT_AGENT_GLOBS:
        found.extend(sorted(REPO_ROOT.glob(pattern)))
    return found


def _kept_pins(manifest: Path) -> dict[str, str]:
    """Map agent name to the model id its KEEP_PIN manifest entry justifies."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    kept: dict[str, str] = {}
    for entry in data.get("pins", []):
        if entry.get("decision") == "KEEP_PIN":
            # Unit paths look like templates/agents/<name>.shared.md.
            kept[Path(str(entry["unit"])).name.split(".")[0]] = str(entry.get("model", ""))
    return kept


# Each generated tree maps to the platform YAML that renders its `model:` value.
# The generator rewrites a KEEP_PIN manifest id into the platform's own spelling
# (format_model_id_for_platform), so the check must do the same before comparing.
# .github/agents has no entry: every file there is a symlink into
# src/copilot-cli/agents (ADR-119), so path.resolve() classifies it as
# src/copilot-cli and the copilot-cli tier map applies.
COPILOT_CLI_YAML = REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"
VSCODE_YAML = REPO_ROOT / "templates" / "platforms" / "vscode.yaml"
PLATFORM_YAML_BY_TREE: dict[str, Path] = {
    "src/copilot-cli": COPILOT_CLI_YAML,
    "src/vs-code-agents": VSCODE_YAML,
}


def _tiers_from_yaml(yaml_path: Path) -> dict[str, object]:
    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    legacy = config.get("legacy") or {}
    tiers = legacy.get("model_tiers") or config.get("model_tiers")
    assert isinstance(tiers, dict), f"{yaml_path} has no model_tiers map"
    return tiers


def _platform_tiers(path: Path) -> dict[str, object]:
    """Return the model_tiers map of the platform that rendered `path`.

    Symlinks are followed on purpose: a `.github/agents` file is the
    `src/copilot-cli` render, so it takes the copilot-cli map.
    """
    relative = path.resolve().relative_to(REPO_ROOT).as_posix()
    for tree, yaml_path in PLATFORM_YAML_BY_TREE.items():
        if relative.startswith(tree + "/"):
            return _tiers_from_yaml(yaml_path)
    raise AssertionError(f"{path} is not under a known generated Copilot tree")


def _assert_pin_is_backed(path: Path, kept: dict[str, str], tiers: dict[str, object]) -> None:
    pinned = _frontmatter(path).get("model")
    if pinned is None:
        return
    name = path.name.split(".")[0]
    assert name in kept, (
        f"{path} pins a model with no KEEP_PIN entry in the model-pin-evidence "
        "manifest. A host without that model rejects the agent."
    )
    expected = format_model_id_for_platform(kept[name], tiers)
    assert pinned == expected, (
        f"{path} pins model {pinned!r} but the KEEP_PIN entry justifies "
        f"{expected!r} on this platform (manifest id {kept[name]!r}). "
        "The sweep evidence does not cover the pinned id."
    )


def test_generated_copilot_agents_are_discovered() -> None:
    """Guard against a vacuous pass if the trees move."""
    paths = _generated_copilot_agents()
    assert len(paths) >= 30
    relative = {p.relative_to(REPO_ROOT).as_posix() for p in paths}
    for pattern in GENERATED_COPILOT_AGENT_GLOBS:
        prefix = pattern.split("*")[0]
        assert any(r.startswith(prefix) for r in relative), f"no agents found under {prefix}"


def _unguarded_agents(tracked: set[str], guarded: set[str]) -> list[str]:
    """Return tracked agent files that no guarded glob covers."""
    return sorted(tracked - guarded)


def test_every_tracked_agent_file_is_in_a_guarded_tree() -> None:
    """A new tree or nested agent must join the scan set, or this fails."""
    listing = subprocess.run(
        ["git", "ls-files", "*.agent.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert listing.returncode == 0, f"git ls-files failed: {listing.stderr}"
    tracked = {line for line in listing.stdout.splitlines() if line}
    assert tracked, "git ls-files found no .agent.md files"
    guarded = {p.relative_to(REPO_ROOT).as_posix() for p in _generated_copilot_agents()}
    unguarded = _unguarded_agents(tracked, guarded)
    assert not unguarded, (
        f"{unguarded} sit outside GENERATED_COPILOT_AGENT_GLOBS, so the #6638 pin "
        "guard never reads them. Add the tree to the globs and PLATFORM_YAML_BY_TREE "
        "(a symlinked mirror needs no map entry)."
    )


def test_unlisted_tree_is_reported_as_unguarded() -> None:
    """Negative control: an agent in a new tree is flagged."""
    tracked = {"src/copilot-cli/agents/a.agent.md", "src/new-host/agents/b.agent.md"}
    guarded = {"src/copilot-cli/agents/a.agent.md"}

    assert _unguarded_agents(tracked, guarded) == ["src/new-host/agents/b.agent.md"]


def test_listed_trees_report_no_unguarded_agents() -> None:
    """Edge: full coverage returns an empty list."""
    both = {"src/copilot-cli/agents/a.agent.md"}

    assert _unguarded_agents(both, both) == []


@pytest.mark.parametrize(
    "path",
    _generated_copilot_agents(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_generated_copilot_agent_pins_no_unbacked_model(path: Path) -> None:
    _assert_pin_is_backed(path, _kept_pins(PIN_MANIFEST), _platform_tiers(path))


COPILOT_CLI_TIERS = _tiers_from_yaml(COPILOT_CLI_YAML)
VSCODE_TIERS = _tiers_from_yaml(VSCODE_YAML)


def _write_agent(tmp_path: Path, model: str, name: str = "new-agent") -> Path:
    agent = tmp_path / f"{name}.agent.md"
    agent.write_text(f"---\ndescription: x\nmodel: {model}\n---\nbody\n", encoding="utf-8")
    return agent


def test_unbacked_pin_in_generated_agent_is_rejected(tmp_path: Path) -> None:
    """Negative control: a haiku-tier template rendered to a versioned id fails."""
    agent = _write_agent(tmp_path, "claude-haiku-4.5")

    with pytest.raises(AssertionError, match="no KEEP_PIN entry"):
        _assert_pin_is_backed(agent, {}, COPILOT_CLI_TIERS)


def test_manifest_backed_pin_in_generated_agent_is_accepted(tmp_path: Path) -> None:
    """Positive: a KEEP_PIN entry for the agent justifies its pin."""
    manifest = tmp_path / "model-pin-evidence.json"
    manifest.write_text(
        json.dumps(
            {
                "pins": [
                    {
                        "unit": "templates/agents/new-agent.shared.md",
                        "model": "claude-haiku-4.5",
                        "decision": "KEEP_PIN",
                    },
                    {"unit": "templates/agents/other.shared.md", "decision": "DROP_PIN"},
                ]
            }
        ),
        encoding="utf-8",
    )
    agent = _write_agent(tmp_path, "claude-haiku-4.5")
    kept = _kept_pins(manifest)

    assert kept == {"new-agent": "claude-haiku-4.5"}
    _assert_pin_is_backed(agent, kept, COPILOT_CLI_TIERS)


@pytest.mark.parametrize(
    ("manifest_id", "tiers", "rendered"),
    [
        # Canonical hyphen form (check_model_pins._normalize_id) on each platform.
        ("claude-haiku-4-5", COPILOT_CLI_TIERS, "claude-haiku-4.5"),
        ("claude-haiku-4-5", VSCODE_TIERS, "Claude Haiku 4.5 (copilot)"),
        # Dot form, as the pre-existing copilot-cli control wrote it.
        ("claude-haiku-4.5", COPILOT_CLI_TIERS, "claude-haiku-4.5"),
        ("claude-haiku-4.5", VSCODE_TIERS, "Claude Haiku 4.5 (copilot)"),
        # Non-haiku tier: the rewrite is not specific to the haiku default.
        ("claude-sonnet-4-6", VSCODE_TIERS, "Claude Sonnet 4.6 (copilot)"),
    ],
)
def test_keep_pin_matches_the_platform_rendered_spelling(
    tmp_path: Path, manifest_id: str, tiers: dict[str, object], rendered: str
) -> None:
    """Positive: the generator rewrites a manifest id per platform, so the check must too.

    Without the rewrite, a legitimate ADR-080 KEEP_PIN entry in the canonical
    hyphen form would fail on copilot-cli, and on VS Code for every spelling.
    """
    agent = _write_agent(tmp_path, rendered)

    _assert_pin_is_backed(agent, {"new-agent": manifest_id}, tiers)


def test_raw_manifest_spelling_is_not_accepted_when_the_platform_renders_another(
    tmp_path: Path,
) -> None:
    """Negative: a VS Code agent carrying the raw manifest id was not rendered by the generator."""
    agent = _write_agent(tmp_path, "claude-haiku-4-5")

    with pytest.raises(AssertionError, match="does not cover the pinned id"):
        _assert_pin_is_backed(agent, {"new-agent": "claude-haiku-4-5"}, VSCODE_TIERS)


def test_pin_to_a_different_model_than_the_manifest_is_rejected(tmp_path: Path) -> None:
    """Negative: a KEEP_PIN for one id does not back a regenerated pin to another."""
    agent = _write_agent(tmp_path, "claude-haiku-4.6")

    with pytest.raises(AssertionError, match="does not cover the pinned id"):
        _assert_pin_is_backed(agent, {"new-agent": "claude-haiku-4.5"}, COPILOT_CLI_TIERS)


def test_manifest_id_the_formatter_cannot_render_backs_no_pin(tmp_path: Path) -> None:
    """Edge: a date-stamped id fails closed in the generator, so it cannot back a pin."""
    agent = _write_agent(tmp_path, "claude-opus-4-20250514")

    with pytest.raises(AssertionError, match="does not cover the pinned id"):
        _assert_pin_is_backed(agent, {"new-agent": "claude-opus-4-20250514"}, COPILOT_CLI_TIERS)


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("src/copilot-cli/agents/x.agent.md", COPILOT_CLI_TIERS),
        ("src/vs-code-agents/x.agent.md", VSCODE_TIERS),
        # A real tracked file: a symlink into src/copilot-cli, so copilot-cli tiers.
        (".github/agents/code-reviewer.agent.md", COPILOT_CLI_TIERS),
    ],
)
def test_platform_tiers_maps_each_generated_tree(
    relative: str, expected: dict[str, object]
) -> None:
    assert _platform_tiers(REPO_ROOT / relative) == expected


def test_github_agents_are_symlinks_into_the_copilot_cli_tree() -> None:
    """Invariant behind the missing .github map entry: every file mirrors src/copilot-cli."""
    github_agents = sorted((REPO_ROOT / ".github" / "agents").glob("*.agent.md"))
    assert github_agents, "no .github/agents files found"
    cli_root = (REPO_ROOT / "src" / "copilot-cli" / "agents").resolve()
    for agent in github_agents:
        assert agent.is_symlink(), f"{agent} is a real file, so it needs its own tier map"
        assert agent.resolve().parent == cli_root, f"{agent} does not mirror src/copilot-cli"


def test_non_symlink_github_agent_is_rejected_as_an_unknown_tree() -> None:
    """Negative: a real .github/agents file has no tier map, so the guard fails closed."""
    with pytest.raises(AssertionError, match="not under a known generated Copilot tree"):
        _platform_tiers(REPO_ROOT / ".github" / "agents" / "not-a-link.agent.md")


def test_platform_tiers_rejects_an_unknown_tree() -> None:
    """Error path: a new generated tree must be mapped before the guard covers it."""
    with pytest.raises(AssertionError, match="not under a known generated Copilot tree"):
        _platform_tiers(REPO_ROOT / "src" / "claude" / "agents" / "x.md")


def test_keep_pin_entry_without_model_backs_no_pin(tmp_path: Path) -> None:
    """Edge: a KEEP_PIN entry missing its model field cannot back any concrete pin."""
    manifest = tmp_path / "model-pin-evidence.json"
    manifest.write_text(
        json.dumps({"pins": [{"unit": "templates/agents/x.shared.md", "decision": "KEEP_PIN"}]}),
        encoding="utf-8",
    )
    agent = _write_agent(tmp_path, "claude-haiku-4.5", name="x")

    with pytest.raises(AssertionError, match="does not cover the pinned id"):
        _assert_pin_is_backed(agent, _kept_pins(manifest), COPILOT_CLI_TIERS)


def test_non_keep_pin_manifest_entry_does_not_back_a_pin(tmp_path: Path) -> None:
    """Edge: only KEEP_PIN decisions count."""
    manifest = tmp_path / "model-pin-evidence.json"
    manifest.write_text(
        json.dumps({"pins": [{"unit": "templates/agents/x.shared.md", "decision": "DROP_PIN"}]}),
        encoding="utf-8",
    )

    assert _kept_pins(manifest) == {}


def test_empty_manifest_backs_nothing(tmp_path: Path) -> None:
    """Edge: the committed steady state, an empty pins list."""
    manifest = tmp_path / "model-pin-evidence.json"
    manifest.write_text(json.dumps({"pins": []}), encoding="utf-8")

    assert _kept_pins(manifest) == {}
