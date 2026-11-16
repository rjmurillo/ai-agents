"""Boundary tests for host-specific split-agent reference roots.

Claude Code and Copilot CLI renders carry their own bare plugin-root token on the
six split-agent reference paths. Cursor replaces the bare Claude token in a plugin
agent body, so its copy keeps that token. Codex and Muse Code replace no token and
set no plugin-root variable, so their copies and the drift normalizer keep the
shared fallback root (probes of 2026-11-16).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import agent_templates  # noqa: E402
import agent_tree_copy as atc  # noqa: E402
import detect_agent_drift  # noqa: E402
import generate_agents  # noqa: E402
import schema_tree_keys  # noqa: E402
from split_reference_roots import (  # noqa: E402
    CLAUDE_ROOT,
    COPILOT_ROOT,
    SHARED_ROOT,
    SPLIT_REFERENCE_SKILLS,
    render_host_reference_roots,
    restore_shared_reference_roots,
)

HOST_ROOTS = (CLAUDE_ROOT, COPILOT_ROOT)
FALLBACK_TREES = ("src/muse/agents", "src/codex/agents")
CURSOR_TREE = "src/cursor/agents"


def _ref(root: str, skill: str) -> str:
    return f"{root}/skills/{skill}/references/"


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_render_replaces_shared_root_on_split_reference_path(host_root: str, skill: str) -> None:
    text = f"Read `{_ref(SHARED_ROOT, skill)}x.md` first."

    rendered = render_host_reference_roots(text, host_root)

    assert rendered == f"Read `{_ref(host_root, skill)}x.md` first."


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_render_leaves_non_split_skill_path_alone(host_root: str) -> None:
    text = f"See `{_ref(SHARED_ROOT, 'retrospective')}`."

    assert render_host_reference_roots(text, host_root) == text


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_render_leaves_other_folders_of_split_skill_alone(host_root: str) -> None:
    text = f"python3 {SHARED_ROOT}/skills/build/scripts/run.py and {SHARED_ROOT}/skills/test/"

    assert render_host_reference_roots(text, host_root) == text


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_render_returns_empty_for_empty_input(host_root: str) -> None:
    assert render_host_reference_roots("", host_root) == ""


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_render_is_idempotent(host_root: str) -> None:
    text = "\n".join(_ref(SHARED_ROOT, skill) for skill in SPLIT_REFERENCE_SKILLS)

    once = render_host_reference_roots(text, host_root)

    assert render_host_reference_roots(once, host_root) == once


@pytest.mark.parametrize("bad_root", ["", SHARED_ROOT, "${PLUGIN_ROOT}", ".claude"])
def test_render_rejects_unknown_root(bad_root: str) -> None:
    with pytest.raises(ValueError, match="unknown host plugin root"):
        render_host_reference_roots(_ref(SHARED_ROOT, "build"), bad_root)


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_restore_inverts_render(host_root: str, skill: str) -> None:
    original = f"Under `{_ref(SHARED_ROOT, skill)}`, read one file."

    rendered = render_host_reference_roots(original, host_root)

    assert rendered != original
    assert restore_shared_reference_roots(rendered) == original


def test_restore_does_not_wrap_shared_root_twice() -> None:
    text = "\n".join(_ref(SHARED_ROOT, skill) for skill in SPLIT_REFERENCE_SKILLS)

    assert restore_shared_reference_roots(text) == text


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_restore_leaves_bare_root_outside_split_references_alone(host_root: str) -> None:
    text = f"{_ref(host_root, 'retrospective')} and {host_root}/skills/build/scripts/x.py"

    assert restore_shared_reference_roots(text) == text


def test_restore_returns_empty_for_empty_input() -> None:
    assert restore_shared_reference_roots("") == ""


def test_host_wrappers_render_their_own_root() -> None:
    text = _ref(SHARED_ROOT, "adr-review")

    assert agent_templates._rewrite_claude_reference_roots(text) == _ref(CLAUDE_ROOT, "adr-review")
    assert generate_agents._rewrite_copilot_reference_roots(text) == _ref(
        COPILOT_ROOT, "adr-review"
    )


def test_drift_normalizer_equates_host_renders_with_shared_form() -> None:
    body = "## Reference Loading\n\nReferences live under `{}`.\n"
    shared = body.format(_ref(SHARED_ROOT, "autoplan"))

    normalized = {
        detect_agent_drift.normalize_content(body.format(_ref(root, "autoplan")))
        for root in (SHARED_ROOT, *HOST_ROOTS)
    }

    assert normalized == {detect_agent_drift.normalize_content(shared)}


def test_drift_normalizer_keeps_non_split_bare_root() -> None:
    text = f"References live under `{_ref(CLAUDE_ROOT, 'retrospective')}`.\n"

    assert _ref(CLAUDE_ROOT, "retrospective") in detect_agent_drift.normalize_content(text)


def test_tree_copy_restores_shared_root_from_claude_body() -> None:
    body = f"\nReferences live under `{_ref(CLAUDE_ROOT, 'build')}`.\n"
    spec = atc.RenderSpec(keep=["name"])

    rendered = atc.render_parsed({"name": "implementer"}, body, "implementer.md", spec)

    assert rendered is not None
    assert _ref(SHARED_ROOT, "build") in rendered
    assert CLAUDE_ROOT not in rendered


def test_tree_copy_keeps_claude_root_when_the_host_replaces_it() -> None:
    body = f"\nReferences live under `{_ref(CLAUDE_ROOT, 'build')}`.\n"
    spec = atc.RenderSpec(keep=["name"], keep_claude_reference_root=True)

    rendered = atc.render_parsed({"name": "implementer"}, body, "implementer.md", spec)

    assert rendered is not None
    assert _ref(CLAUDE_ROOT, "build") in rendered
    assert SHARED_ROOT not in rendered


@pytest.mark.parametrize(
    ("platform", "expected"), [("cursor", True), ("codex", False), ("muse", False)]
)
def test_platform_config_sets_reference_root_per_host(platform: str, expected: bool) -> None:
    config = REPO_ROOT / "templates" / "platforms" / f"{platform}.yaml"
    stanza = atc._read_stanza(config)

    assert stanza is not None
    assert (stanza.get(atc.KEEP_ROOT_KEY) is True) is expected


def test_schema_rejects_non_boolean_keep_root() -> None:
    stanza = {"frontmatterKeep": ["name"], "sourceDir": "a", "outputDir": "b"}
    stanza[atc.KEEP_ROOT_KEY] = "yes"

    errors = schema_tree_keys.validate_agents_tree_copy("agents", stanza)

    assert any("keepClaudeReferenceRoot`: must be a boolean" in e for e in errors)


def test_schema_rejects_keep_root_without_tree_copy() -> None:
    errors = schema_tree_keys.validate_agents_tree_copy("agents", {atc.KEEP_ROOT_KEY: True})

    assert any("keepClaudeReferenceRoot`: requires `frontmatterKeep`" in e for e in errors)


def test_every_split_skill_ships_a_references_folder() -> None:
    for skill in SPLIT_REFERENCE_SKILLS:
        assert (REPO_ROOT / "src" / "claude" / "skills" / skill / "references").is_dir(), skill


def _split_agent_files(tree: str) -> list[Path]:
    files = sorted((REPO_ROOT / tree).glob("*.*"))
    assert files, f"no agent files under {tree}"
    return files


def test_cursor_agents_carry_the_bare_claude_reference_root() -> None:
    found = [
        path.name
        for path in _split_agent_files(CURSOR_TREE)
        for skill in SPLIT_REFERENCE_SKILLS
        if _ref(CLAUDE_ROOT, skill) in path.read_text(encoding="utf-8")
    ]
    nested = [
        path.name
        for path in _split_agent_files(CURSOR_TREE)
        for skill in SPLIT_REFERENCE_SKILLS
        if _ref(SHARED_ROOT, skill) in path.read_text(encoding="utf-8")
    ]

    assert sorted(found) == [
        "architect.md",
        "critic.md",
        "implementer.md",
        "orchestrator.md",
        "qa.md",
    ]
    assert nested == []


@pytest.mark.parametrize("tree", FALLBACK_TREES)
def test_fallback_host_agents_carry_no_bare_claude_reference_root(tree: str) -> None:
    files = _split_agent_files(tree)
    shared = [
        path.name
        for path in files
        for skill in SPLIT_REFERENCE_SKILLS
        if _ref(SHARED_ROOT, skill) in path.read_text(encoding="utf-8")
    ]
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()}: {skill}"
        for path in files
        for skill in SPLIT_REFERENCE_SKILLS
        if _ref(CLAUDE_ROOT, skill) in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
    assert len(shared) == 5, shared


SPLIT_AGENTS = ("architect", "critic", "implementer", "orchestrator", "qa", "security")


@pytest.mark.parametrize(
    ("pattern", "host_root"),
    [
        ("src/claude/agents/{}.md", CLAUDE_ROOT),
        ("src/copilot-cli/agents/{}.agent.md", COPILOT_ROOT),
    ],
    ids=["claude", "copilot-cli"],
)
@pytest.mark.parametrize("agent", SPLIT_AGENTS)
def test_host_render_carries_its_own_reference_root(
    pattern: str, host_root: str, agent: str
) -> None:
    text = (REPO_ROOT / pattern.format(agent)).read_text(encoding="utf-8")

    assert any(_ref(host_root, skill) in text for skill in SPLIT_REFERENCE_SKILLS), agent
    assert not any(_ref(SHARED_ROOT, skill) in text for skill in SPLIT_REFERENCE_SKILLS), agent
