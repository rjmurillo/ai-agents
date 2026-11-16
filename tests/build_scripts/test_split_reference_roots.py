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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from split_reference_helpers import (
    HOST_ROOTS,
    MARKER,
    ref,
    rendered_sentence,
    sentence,
    skills_with_references,
)

# isort: split

import agent_templates
import agent_tree_copy as atc
import detect_agent_drift
import generate_agents
import schema_tree_keys
from generate_agents_common import (
    CLAUDE_ROOT,
    COPILOT_ROOT,
    MARKER_DECLARATION,
    SHARED_ROOT,
    SPLIT_REFERENCE_SKILLS,
    restore_shared_reference_roots,
)
from generate_agents_common import (
    convert_reference_roots as render_host_reference_roots,
)


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_render_adds_checkout_clause_after_sentence_path(host_root: str, skill: str) -> None:
    rendered = render_host_reference_roots(sentence(SHARED_ROOT, skill), host_root)

    assert rendered == rendered_sentence(host_root, skill)
    assert f"`.claude/skills/{skill}/references/`" in rendered


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_restore_drops_checkout_clause(host_root: str, skill: str) -> None:
    rendered = render_host_reference_roots(sentence(SHARED_ROOT, skill), host_root)

    assert restore_shared_reference_roots(rendered) == sentence(SHARED_ROOT, skill)
    assert render_host_reference_roots(rendered, host_root) == rendered


def test_restore_keeps_clause_naming_another_skill() -> None:
    mismatched = rendered_sentence(CLAUDE_ROOT, "build").replace(
        "`.claude/skills/build/references/`", "`.claude/skills/test/references/`"
    )

    restored = restore_shared_reference_roots(mismatched)

    assert "`.claude/skills/test/references/` instead." in restored


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_drift_normalizer_drops_checkout_clause(host_root: str) -> None:
    rendered = render_host_reference_roots(sentence(SHARED_ROOT, "test"), host_root)

    assert detect_agent_drift.normalize_content(rendered) == detect_agent_drift.normalize_content(
        sentence(SHARED_ROOT, "test")
    )


@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_claude_render_copy_matches_shared_render_with_clause(skill: str) -> None:
    text = sentence(SHARED_ROOT, skill)

    assert agent_templates._rewrite_claude_reference_roots(text) == render_host_reference_roots(
        text, CLAUDE_ROOT
    )


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_render_replaces_shared_root_on_split_reference_path(host_root: str, skill: str) -> None:
    text = f"Read `{ref(SHARED_ROOT, skill)}x.md` first."

    rendered = render_host_reference_roots(text, host_root)

    assert rendered == f"Read `{ref(host_root, skill)}x.md` first."


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_render_leaves_non_split_skill_path_alone(host_root: str) -> None:
    text = f"See `{ref(SHARED_ROOT, 'retrospective')}`."

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
    text = "\n".join(ref(SHARED_ROOT, skill) for skill in SPLIT_REFERENCE_SKILLS)

    once = render_host_reference_roots(text, host_root)

    assert render_host_reference_roots(once, host_root) == once


@pytest.mark.parametrize("bad_root", ["", SHARED_ROOT, "${PLUGIN_ROOT}", ".claude"])
def test_render_rejects_unknown_root(bad_root: str) -> None:
    with pytest.raises(ValueError, match="unknown host plugin root"):
        render_host_reference_roots(ref(SHARED_ROOT, "build"), bad_root)


@pytest.mark.parametrize("host_root", HOST_ROOTS)
@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_restore_inverts_render(host_root: str, skill: str) -> None:
    original = f"Under `{ref(SHARED_ROOT, skill)}`, read one file."

    rendered = render_host_reference_roots(original, host_root)

    assert rendered != original
    assert restore_shared_reference_roots(rendered) == original


def test_restore_does_not_wrap_shared_root_twice() -> None:
    text = "\n".join(ref(SHARED_ROOT, skill) for skill in SPLIT_REFERENCE_SKILLS)

    assert restore_shared_reference_roots(text) == text


@pytest.mark.parametrize("host_root", HOST_ROOTS)
def test_restore_leaves_bare_root_outside_split_references_alone(host_root: str) -> None:
    text = f"{ref(host_root, 'retrospective')} and {host_root}/skills/build/scripts/x.py"

    assert restore_shared_reference_roots(text) == text


def test_restore_returns_empty_for_empty_input() -> None:
    assert restore_shared_reference_roots("") == ""


def test_host_wrappers_render_their_own_root() -> None:
    text = ref(SHARED_ROOT, "adr-review")

    assert agent_templates._rewrite_claude_reference_roots(text) == ref(CLAUDE_ROOT, "adr-review")
    assert generate_agents._rewrite_copilot_reference_roots(text) == ref(COPILOT_ROOT, "adr-review")


def test_drift_normalizer_equates_host_renders_with_shared_form() -> None:
    body = "## Reference Loading\n\nReferences live under `{}`.\n"
    shared = body.format(ref(SHARED_ROOT, "autoplan"))

    normalized = {
        detect_agent_drift.normalize_content(body.format(ref(root, "autoplan")))
        for root in (SHARED_ROOT, *HOST_ROOTS)
    }

    assert normalized == {detect_agent_drift.normalize_content(shared)}


def test_drift_normalizer_keeps_non_split_bare_root() -> None:
    text = f"References live under `{ref(CLAUDE_ROOT, 'retrospective')}`.\n"

    assert ref(CLAUDE_ROOT, "retrospective") in detect_agent_drift.normalize_content(text)


def test_tree_copy_restores_shared_root_from_claude_body() -> None:
    body = "\n" + rendered_sentence(CLAUDE_ROOT, "build") + "\n"
    spec = atc.RenderSpec(keep=["name"])

    rendered = atc.render_parsed({"name": "implementer"}, body, "implementer.md", spec)

    assert rendered is not None
    assert sentence(SHARED_ROOT, "build") in rendered
    assert CLAUDE_ROOT not in rendered
    assert "In a checkout" not in rendered


def test_tree_copy_keeps_claude_root_when_the_host_replaces_it() -> None:
    body = "\n" + rendered_sentence(CLAUDE_ROOT, "build") + "\n"
    spec = atc.RenderSpec(keep=["name"], keep_claude_reference_root=True)

    rendered = atc.render_parsed({"name": "implementer"}, body, "implementer.md", spec)

    assert rendered is not None
    assert rendered_sentence(CLAUDE_ROOT, "build") in rendered
    assert SHARED_ROOT not in rendered


def test_schema_rejects_non_boolean_keep_root() -> None:
    stanza = {"frontmatterKeep": ["name"], "sourceDir": "a", "outputDir": "b"}
    stanza[atc.KEEP_ROOT_KEY] = "yes"

    errors = schema_tree_keys.validate_agents_tree_copy("agents", stanza)

    assert any("keepClaudeReferenceRoot`: must be a boolean" in e for e in errors)


def test_schema_rejects_keep_root_without_tree_copy() -> None:
    errors = schema_tree_keys.validate_agents_tree_copy("agents", {atc.KEEP_ROOT_KEY: True})

    assert any("keepClaudeReferenceRoot`: requires `frontmatterKeep`" in e for e in errors)


def test_agent_templates_private_skill_list_matches_the_shared_list() -> None:
    assert agent_templates._SPLIT_REFERENCE_SKILLS == SPLIT_REFERENCE_SKILLS
    assert agent_templates._SHARED_ROOT == SHARED_ROOT


@pytest.mark.parametrize("skill", skills_with_references())
def test_every_copy_rewrites_exactly_the_shared_skill_set(skill: str) -> None:
    shared = ref(SHARED_ROOT, skill)
    expected = skill in SPLIT_REFERENCE_SKILLS

    claude = agent_templates._rewrite_claude_reference_roots(shared)
    copilot = generate_agents._rewrite_copilot_reference_roots(shared)
    drift = {root: detect_agent_drift.normalize_content(ref(root, skill)) for root in HOST_ROOTS}

    assert (claude == ref(CLAUDE_ROOT, skill)) is expected
    assert (copilot == ref(COPILOT_ROOT, skill)) is expected
    for root, normalized in drift.items():
        assert (shared in normalized) is expected, root
        assert (restore_shared_reference_roots(ref(root, skill)) == shared) is expected, root


def test_render_declares_checkout_path_in_existing_marker() -> None:
    text = MARKER + "\n\n" + sentence(SHARED_ROOT, "build")

    rendered = render_host_reference_roots(text, COPILOT_ROOT)

    declared = MARKER.replace(" -->", MARKER_DECLARATION.format(skill="build") + " -->")
    assert rendered.startswith(declared + "\n\n")
    assert rendered.count("Checkout fallback path") == 1
    assert render_host_reference_roots(rendered, COPILOT_ROOT) == rendered


def test_render_adds_no_marker_when_body_has_none() -> None:
    rendered = render_host_reference_roots(sentence(SHARED_ROOT, "build"), COPILOT_ROOT)

    assert "vendor-portability" not in rendered


def test_render_leaves_marker_alone_without_a_clause() -> None:
    text = MARKER + "\n" + f"Read `{ref(SHARED_ROOT, 'build')}x.md` first."

    rendered = render_host_reference_roots(text, COPILOT_ROOT)

    assert rendered.startswith(MARKER + "\n")


def test_restore_drops_marker_declaration() -> None:
    text = MARKER + "\n\n" + sentence(SHARED_ROOT, "build")

    rendered = render_host_reference_roots(text, COPILOT_ROOT)

    assert restore_shared_reference_roots(rendered) == text


@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_every_copy_handles_a_marker_body_the_same(skill: str) -> None:
    text = MARKER + "\n\n" + sentence(SHARED_ROOT, skill)

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
