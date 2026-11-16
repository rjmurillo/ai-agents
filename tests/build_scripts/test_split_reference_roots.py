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
from generate_agents_common import (  # noqa: E402
    CHECKOUT_CLAUSE,
    CLAUDE_ROOT,
    COPILOT_ROOT,
    MARKER_DECLARATION,
    SHARED_ROOT,
    SPLIT_REFERENCE_SKILLS,
    restore_shared_reference_roots,
)
from generate_agents_common import (  # noqa: E402
    convert_reference_roots as render_host_reference_roots,
)

HOST_ROOTS = (CLAUDE_ROOT, COPILOT_ROOT)
FALLBACK_TREES = ("src/muse/agents", "src/codex/agents")
CURSOR_TREE = "src/cursor/agents"


def _ref(root: str, skill: str) -> str:
    return f"{root}/skills/{skill}/references/"


def _sentence(root: str, skill: str) -> str:
    return f"References live under `{_ref(root, skill)}`. They serve this agent."


def _rendered_sentence(root: str, skill: str) -> str:
    clause = CHECKOUT_CLAUSE.format(skill=skill)
    return f"References live under `{_ref(root, skill)}`.{clause} They serve this agent."


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_render_adds_checkout_clause_after_sentence_path(host_root: str, skill: str) -> None:
    rendered = render_host_reference_roots(_sentence(SHARED_ROOT, skill), host_root)

    assert rendered == _rendered_sentence(host_root, skill)
    assert f"`.claude/skills/{skill}/references/`" in rendered


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_restore_drops_checkout_clause(host_root: str, skill: str) -> None:
    rendered = render_host_reference_roots(_sentence(SHARED_ROOT, skill), host_root)

    assert restore_shared_reference_roots(rendered) == _sentence(SHARED_ROOT, skill)
    assert render_host_reference_roots(rendered, host_root) == rendered


def test_restore_keeps_clause_naming_another_skill() -> None:
    mismatched = _rendered_sentence(CLAUDE_ROOT, "build").replace(
        "`.claude/skills/build/references/`", "`.claude/skills/test/references/`"
    )

    restored = restore_shared_reference_roots(mismatched)

    assert "`.claude/skills/test/references/` instead." in restored


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_drift_normalizer_drops_checkout_clause(host_root: str) -> None:
    rendered = render_host_reference_roots(_sentence(SHARED_ROOT, "test"), host_root)

    assert detect_agent_drift.normalize_content(rendered) == detect_agent_drift.normalize_content(
        _sentence(SHARED_ROOT, "test")
    )


@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_claude_render_copy_matches_shared_render_with_clause(skill: str) -> None:
    text = _sentence(SHARED_ROOT, skill)

    assert agent_templates._rewrite_claude_reference_roots(text) == render_host_reference_roots(
        text, CLAUDE_ROOT
    )


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
    body = "\n" + _rendered_sentence(CLAUDE_ROOT, "build") + "\n"
    spec = atc.RenderSpec(keep=["name"])

    rendered = atc.render_parsed({"name": "implementer"}, body, "implementer.md", spec)

    assert rendered is not None
    assert _sentence(SHARED_ROOT, "build") in rendered
    assert CLAUDE_ROOT not in rendered
    assert "In a checkout" not in rendered


def test_tree_copy_keeps_claude_root_when_the_host_replaces_it() -> None:
    body = "\n" + _rendered_sentence(CLAUDE_ROOT, "build") + "\n"
    spec = atc.RenderSpec(keep=["name"], keep_claude_reference_root=True)

    rendered = atc.render_parsed({"name": "implementer"}, body, "implementer.md", spec)

    assert rendered is not None
    assert _rendered_sentence(CLAUDE_ROOT, "build") in rendered
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


@pytest.mark.parametrize("tree", ["claude", "copilot-cli", "cursor", "codex", "muse"])
def test_every_split_skill_ships_a_references_folder_in_each_host_tree(tree: str) -> None:
    missing = [
        skill
        for skill in SPLIT_REFERENCE_SKILLS
        if not (REPO_ROOT / "src" / tree / "skills" / skill / "references").is_dir()
    ]

    assert missing == []


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

    clauses = [path.name for path in files if "In a checkout that loads" in path.read_text("utf-8")]

    assert offenders == []
    assert len(shared) == 5, shared
    assert clauses == []


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


def _skills_with_references() -> list[str]:
    root = REPO_ROOT / "src" / "claude" / "skills"
    return sorted(p.parent.name for p in root.glob("*/references") if p.is_dir())


def test_agent_templates_private_skill_list_matches_the_shared_list() -> None:
    assert agent_templates._SPLIT_REFERENCE_SKILLS == SPLIT_REFERENCE_SKILLS
    assert agent_templates._SHARED_ROOT == SHARED_ROOT


@pytest.mark.parametrize("skill", _skills_with_references())
def test_every_copy_rewrites_exactly_the_shared_skill_set(skill: str) -> None:
    shared = _ref(SHARED_ROOT, skill)
    expected = skill in SPLIT_REFERENCE_SKILLS

    claude = agent_templates._rewrite_claude_reference_roots(shared)
    copilot = generate_agents._rewrite_copilot_reference_roots(shared)
    drift = {root: detect_agent_drift.normalize_content(_ref(root, skill)) for root in HOST_ROOTS}

    assert (claude == _ref(CLAUDE_ROOT, skill)) is expected
    assert (copilot == _ref(COPILOT_ROOT, skill)) is expected
    for root, normalized in drift.items():
        assert (shared in normalized) is expected, root
        assert (restore_shared_reference_roots(_ref(root, skill)) == shared) is expected, root


AGENT_SKILL = {
    "architect": "adr-review",
    "critic": "decision-critic",
    "implementer": "build",
    "orchestrator": "autoplan",
    "qa": "test",
    "security": "security-scan",
}


@pytest.mark.parametrize(
    ("pattern", "host_root"),
    [
        ("src/claude/agents/{}.md", CLAUDE_ROOT),
        ("src/copilot-cli/agents/{}.agent.md", COPILOT_ROOT),
        ("src/cursor/agents/{}.md", CLAUDE_ROOT),
    ],
    ids=["claude", "copilot-cli", "cursor"],
)
@pytest.mark.parametrize("agent", SPLIT_AGENTS)
def test_bare_root_render_names_the_checkout_path(pattern: str, host_root: str, agent: str) -> None:
    path = REPO_ROOT / pattern.format(agent)
    if "cursor" in pattern and agent == "security":
        assert not path.exists()  # Cursor ships no security agent (ADR-115 Decision 3).
        return
    skill = AGENT_SKILL[agent]
    expected = f"`{_ref(host_root, skill)}`." + CHECKOUT_CLAUSE.format(skill=skill)

    assert path.read_text(encoding="utf-8").count(expected) == 1


@pytest.mark.parametrize("agent", SPLIT_AGENTS)
def test_vs_code_render_keeps_nested_form_without_clause(agent: str) -> None:
    text = (REPO_ROOT / f"src/vs-code-agents/{agent}.agent.md").read_text(encoding="utf-8")

    assert f"`{_ref(SHARED_ROOT, AGENT_SKILL[agent])}`." in text
    assert "In a checkout that loads" not in text


@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_checkout_path_named_by_the_clause_holds_reference_files(skill: str) -> None:
    folder = REPO_ROOT / ".claude" / "skills" / skill / "references"

    assert folder.is_dir(), folder
    assert sorted(folder.glob("*.md")), folder


def test_agent_skill_map_covers_the_shared_skill_list() -> None:
    assert sorted(AGENT_SKILL.values()) == sorted(SPLIT_REFERENCE_SKILLS)


MARKER = "<!-- vendor-portability: declares `.agents/` paths. -->"


def test_render_declares_checkout_path_in_existing_marker() -> None:
    text = MARKER + "\n\n" + _sentence(SHARED_ROOT, "build")

    rendered = render_host_reference_roots(text, COPILOT_ROOT)

    declared = MARKER.replace(" -->", MARKER_DECLARATION.format(skill="build") + " -->")
    assert rendered.startswith(declared + "\n\n")
    assert rendered.count("Checkout fallback path") == 1
    assert render_host_reference_roots(rendered, COPILOT_ROOT) == rendered


def test_render_adds_no_marker_when_body_has_none() -> None:
    rendered = render_host_reference_roots(_sentence(SHARED_ROOT, "build"), COPILOT_ROOT)

    assert "vendor-portability" not in rendered


def test_render_leaves_marker_alone_without_a_clause() -> None:
    text = MARKER + "\n" + f"Read `{_ref(SHARED_ROOT, 'build')}x.md` first."

    rendered = render_host_reference_roots(text, COPILOT_ROOT)

    assert rendered.startswith(MARKER + "\n")


def test_restore_drops_marker_declaration() -> None:
    text = MARKER + "\n\n" + _sentence(SHARED_ROOT, "build")

    rendered = render_host_reference_roots(text, COPILOT_ROOT)

    assert restore_shared_reference_roots(rendered) == text


def test_copilot_implementer_marker_declares_the_checkout_path() -> None:
    text = (REPO_ROOT / "src/copilot-cli/agents/implementer.agent.md").read_text("utf-8")
    vs_code = (REPO_ROOT / "src/vs-code-agents/implementer.agent.md").read_text("utf-8")

    assert MARKER_DECLARATION.format(skill="build") in text
    assert "Checkout fallback path" not in vs_code


@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_every_copy_handles_a_marker_body_the_same(skill: str) -> None:
    text = MARKER + "\n\n" + _sentence(SHARED_ROOT, skill)

    shared = render_host_reference_roots(text, CLAUDE_ROOT)
    private = agent_templates._rewrite_claude_reference_roots(text)
    normalized = {
        root: detect_agent_drift.normalize_content(render_host_reference_roots(text, root))
        for root in HOST_ROOTS
    }

    assert private == shared
    assert MARKER_DECLARATION.format(skill=skill) in shared
    for root, value in normalized.items():
        assert value == detect_agent_drift.normalize_content(text), root
