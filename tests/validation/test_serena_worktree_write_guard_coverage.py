"""Every Serena memory-mutation call site in a template carries the linked-worktree guard.

Issue #5061: one Serena MCP server serves a whole session with its project root
fixed at launch (`.mcp.json` passes `--project ${workspaceFolder:-.}`). A
subagent working in a linked git worktree that calls `mcp__serena__write_memory`
(or `edit_memory`, `delete_memory`, `rename_memory`) mutates the MAIN checkout's
`.serena/memories/`, not its own. `templates/rules/universal.md` MUST NOT 11
already forbids this generically; this test enforces route A, the
point-of-use prevention instruction, at every template call site.

The guard text lives once per render pipeline, mirroring how
`untrusted-content.mustache` is split (`test_untrusted_content_partial_parity.py`):
`templates/agents/partials/serena-worktree-write-guard.mustache` and
`templates/skills/partials/serena-worktree-write-guard.mustache` are
byte-identical partials, included via `{{> serena-worktree-write-guard}}`.

`templates/agents/*.shared.md` files are a third case, not a partial-tree
gap: `build/generate_agents.py` reads them as plain markdown (no mustache,
confirmed by `grep -c '{{>' templates/agents/*.shared.md` returning 0 for
every file, 2026-09-27) for the vscode and visual-studio platforms; only
copilot-cli and github override from the rendered `.copilot.md.tmpl` (see
that module's `_COPILOT_FAMILY` and `_apply_copilot_override`). A `{{> }}`
tag there would render as literal unresolved text in those platforms'
output, so those files carry the guard's prose verbatim instead of the
include tag. The rendering test below therefore treats `.shared.md` files
as already-rendered text (read directly) rather than routing them through
`render()`.

This test renders every template through the same `render()` function
`build/scripts/agent_templates.py` and `build/scripts/skill_templates.py`
use (imported from `skill_template_grammar`, which agents and skills share
per that module's docstring), rather than reading committed generated
output: a template edit is caught here immediately, without requiring
`build/scripts/build_all.py` to have run first. This is the "assert per
rendered output" fallback the issue's spec allows in place of a full
"reached through a template that includes it" graph.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "build" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from skill_template_grammar import render

_AGENTS_DIR = _REPO_ROOT / "templates" / "agents"
_AGENTS_PARTIALS = _AGENTS_DIR / "partials"
_SKILLS_DIR = _REPO_ROOT / "templates" / "skills"
_SKILLS_PARTIALS = _SKILLS_DIR / "partials"

_AGENT_PARTIAL = _AGENTS_PARTIALS / "serena-worktree-write-guard.mustache"
_SKILL_PARTIAL = _SKILLS_PARTIALS / "serena-worktree-write-guard.mustache"

# Unique phrase from the guard partial (verified absent elsewhere in the repo
# 2026-09-27 via `grep -rn "checkout active at server start" .`). A call site
# passes this test only when the rendered text carrying "write_memory" also
# carries this sentinel, proving the guard partial actually resolved there
# rather than merely being named in a comment or unreachable branch.
_SENTINEL = "checkout active at server start"
_MUTATION_MARKERS = ("write_memory", "edit_memory", "delete_memory", "rename_memory")

# The Copilot orchestrator prompt sat at 29994 of the 30000-character host
# limit enforced by tests/test_orchestrator_shared_contracts.py, so the guard
# cannot fit. The orchestrator runs in the main checkout and delegates; the
# worktree-scoped workers it spawns carry the guard themselves. The same
# exemption covers orchestrator.shared.md, which must match the Copilot render.
_COPILOT_EXEMPT = {
    "orchestrator": "Copilot orchestrator prompt has no room under the 30000-character host limit",
}


def _mentions_mutation(text: str) -> bool:
    return any(marker in text for marker in _MUTATION_MARKERS)


def _discover_agent_stems() -> list[str]:
    claude_suffix = ".claude.md.tmpl"
    return sorted(
        path.name[: -len(claude_suffix)] for path in _AGENTS_DIR.glob(f"*{claude_suffix}")
    )


def _discover_skill_names() -> list[str]:
    suffix = ".SKILL.md.tmpl"
    return sorted(path.name[: -len(suffix)] for path in _SKILLS_DIR.glob(f"*{suffix}"))


def _discover_shared_md_names() -> list[str]:
    suffix = ".shared.md"
    return sorted(path.name[: -len(suffix)] for path in _AGENTS_DIR.glob(f"*{suffix}"))


def test_both_partials_exist() -> None:
    assert _AGENT_PARTIAL.is_file()
    assert _SKILL_PARTIAL.is_file()


def test_the_two_partials_are_byte_identical() -> None:
    """Mirrors `untrusted-content.mustache`'s split: one text, two render trees."""
    assert _AGENT_PARTIAL.read_bytes() == _SKILL_PARTIAL.read_bytes()


def test_the_partial_states_the_invariant() -> None:
    text = _AGENT_PARTIAL.read_text(encoding="utf-8")

    assert _SENTINEL in text
    assert "mcp__serena__write_memory" in text
    assert "edit_memory" in text
    assert "delete_memory" in text
    assert "rename_memory" in text
    assert "issue #5061" in text
    assert "universal.md" in text
    assert "MUST NOT 11" in text


def test_the_partial_has_no_em_or_en_dash() -> None:
    text = _AGENT_PARTIAL.read_text(encoding="utf-8")

    assert "\u2014" not in text
    assert "\u2013" not in text


def test_the_partial_is_within_the_word_budget() -> None:
    """R1: target <= 90 words for the shared guard text."""
    text = _AGENT_PARTIAL.read_text(encoding="utf-8")

    assert len(text.split()) <= 90


@pytest.mark.parametrize("stem", _discover_agent_stems())
def test_claude_agent_render_carries_guard_wherever_it_mentions_write_memory(
    stem: str,
) -> None:
    template_path = _AGENTS_DIR / f"{stem}.claude.md.tmpl"
    if not template_path.is_file():
        pytest.skip(f"{stem} has no .claude.md.tmpl variant")

    rendered = str(render(template_path, _AGENTS_PARTIALS))

    if _mentions_mutation(rendered):
        assert _SENTINEL in rendered, (
            f"{template_path} renders a Serena memory-mutation call without the "
            f"linked-worktree guard (issue #5061)."
        )


@pytest.mark.parametrize("stem", _discover_agent_stems())
def test_copilot_agent_render_carries_guard_wherever_it_mentions_write_memory(
    stem: str,
) -> None:
    template_path = _AGENTS_DIR / f"{stem}.copilot.md.tmpl"
    if not template_path.is_file():
        pytest.skip(f"{stem} has no .copilot.md.tmpl variant")
    if stem in _COPILOT_EXEMPT:
        pytest.skip(_COPILOT_EXEMPT[stem])

    rendered = str(render(template_path, _AGENTS_PARTIALS))

    if _mentions_mutation(rendered):
        assert _SENTINEL in rendered, (
            f"{template_path} renders a Serena memory-mutation call without the "
            f"linked-worktree guard (issue #5061)."
        )


@pytest.mark.parametrize("name", _discover_skill_names())
def test_skill_render_carries_guard_wherever_it_mentions_write_memory(name: str) -> None:
    template_path = _SKILLS_DIR / f"{name}.SKILL.md.tmpl"

    rendered = str(render(template_path, _SKILLS_PARTIALS))

    if _mentions_mutation(rendered):
        assert _SENTINEL in rendered, (
            f"{template_path} renders a Serena memory-mutation call without the "
            f"linked-worktree guard (issue #5061)."
        )


@pytest.mark.parametrize("stem", _discover_shared_md_names())
def test_shared_md_carries_guard_wherever_it_mentions_write_memory(stem: str) -> None:
    """`.shared.md` is not mustache-rendered (see module docstring); read directly."""
    if stem in _COPILOT_EXEMPT:
        pytest.skip(_COPILOT_EXEMPT[stem])
    path = _AGENTS_DIR / f"{stem}.shared.md"
    text = path.read_text(encoding="utf-8")

    if _mentions_mutation(text):
        assert _SENTINEL in text, (
            f"{path} mentions a Serena memory-mutation call without the "
            f"linked-worktree guard (issue #5061)."
        )


def test_memory_skill_router_carries_the_guard() -> None:
    """R3: the memory skill router's 'Store new factual knowledge directly?' branch."""
    template_path = _SKILLS_DIR / "memory.SKILL.md.tmpl"
    rendered = str(render(template_path, _SKILLS_PARTIALS))

    assert "Store new factual knowledge directly" in rendered
    assert _SENTINEL in rendered


def test_negative_fixture_without_the_guard_fails_the_check(tmp_path: Path) -> None:
    """A fixture that calls write_memory without including the guard must fail.

    This proves `_mentions_mutation` / the sentinel check is not vacuously
    true: it renders a minimal template with no partial include and confirms
    the guard sentinel is correctly reported absent.
    """
    fixture = tmp_path / "no-guard.claude.md.tmpl"
    fixture.write_text(
        "---\nname: no-guard\ndescription: fixture\n---\n\n"
        "Call `mcp__serena__write_memory` to persist a finding.\n",
        encoding="utf-8",
    )
    empty_partials = tmp_path / "partials"
    empty_partials.mkdir()

    rendered = str(render(fixture, empty_partials))

    assert _mentions_mutation(rendered)
    assert _SENTINEL not in rendered


def test_positive_fixture_with_the_guard_passes_the_check(tmp_path: Path) -> None:
    """The mirror of the negative fixture: including the partial clears the check."""
    fixture = tmp_path / "with-guard.claude.md.tmpl"
    fixture.write_text(
        "---\nname: with-guard\ndescription: fixture\n---\n\n"
        "Call `mcp__serena__write_memory` to persist a finding.\n\n"
        "{{> serena-worktree-write-guard}}\n",
        encoding="utf-8",
    )
    partials_dir = tmp_path / "partials"
    partials_dir.mkdir()
    (partials_dir / "serena-worktree-write-guard.mustache").write_bytes(_AGENT_PARTIAL.read_bytes())

    rendered = str(render(fixture, partials_dir))

    assert _mentions_mutation(rendered)
    assert _SENTINEL in rendered


_REFERENCE_MUTATION = re.compile(r"mcp__serena__(write|edit|delete|rename)_memory")
_SKILL_REFERENCES = sorted((_REPO_ROOT / ".claude" / "skills").glob("*/references/*.md"))


@pytest.mark.parametrize(
    "reference",
    [p for p in _SKILL_REFERENCES if _REFERENCE_MUTATION.search(p.read_text(encoding="utf-8"))],
    ids=lambda p: f"{p.parent.parent.name}/{p.name}",
)
def test_skill_reference_carries_guard_wherever_it_calls_a_mutation_tool(reference: Path) -> None:
    """Hand-maintained skill references have no partial pipeline, so they carry a short note."""
    assert _SENTINEL in reference.read_text(encoding="utf-8")


@pytest.mark.parametrize("stem", _discover_agent_stems())
def test_claude_agent_render_carries_the_guard_at_most_once(stem: str) -> None:
    """One guard per prompt: a model reads the whole prompt, so repeats only cost tokens."""
    template_path = _AGENTS_DIR / f"{stem}.claude.md.tmpl"
    if not template_path.is_file():
        pytest.skip(f"{stem} has no .claude.md.tmpl variant")

    rendered = str(render(template_path, _AGENTS_PARTIALS))

    assert rendered.count(_SENTINEL) <= 1
