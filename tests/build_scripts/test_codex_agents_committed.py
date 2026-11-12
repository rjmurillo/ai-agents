"""Committed ``src/codex/agents/*.toml`` against an independent reading of the sources.

The expected values come from parsing ``src/claude/agents/<stem>.md`` here with
``yaml`` and a regex, not from the generator, so a generator bug cannot hide
itself. The list of tool-restricted agents is written out below and compared with
what the sources declare.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import tomllib
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_AGENTS = REPO_ROOT / "src" / "claude" / "agents"
CODEX_AGENTS = REPO_ROOT / "src" / "codex" / "agents"
NOT_SHIPPED = ["analyst", "code-reviewer", "comment-analyzer", "security"]
PARAGRAPH = (
    "\n\n## Agents not installed on this host\n\n"
    "These agents are not installed on this host: "
    "`analyst`, `code-reviewer`, `comment-analyzer`, `security`. "
    "When a step above hands work to one of them, do that step yourself "
    "in this session and say that you did. "
    "A step you do yourself is a self-review, not an independent review, so report it as one. "
    "It does not satisfy a review gate: name the gate as unreviewed in your completion report. "
    "When you are asked to review or challenge work, set aside the author's reasoning "
    "and judge the artifact itself. "
    "If the step is a security review or clears a security flag, do not mark it done: "
    "state that no security agent reviewed it and leave the flag open for the user.\n"
)
# Edits templates/platforms/codex.yaml makes to orchestrator.md: the rows for agents
# Codex does not install go, and the delegation tool is spawn_agent.
NO_SUBAGENTS = "\n\n## Subagents\n\nDo not start subagents. Do the work in this session.\n"
BODY_EDITS = {
    "orchestrator": [
        ("| **analyst** | Research, root cause, feasibility | Already have enough context |\n", ""),
        ("| **security** | Threat modeling, vulnerability review | Pure performance work |\n", ""),
        (
            "Task (for delegation)",
            'spawn_agent (for delegation; pass fork_turns="none" when the child reviews work)',
        ),
    ]
}
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_EXCLUDED = {"AGENTS.md", "CLAUDE.md"}


def _read_source(stem: str) -> tuple[dict[str, object], str]:
    match = _FRONTMATTER.match((CLAUDE_AGENTS / f"{stem}.md").read_text(encoding="utf-8"))
    assert match is not None, stem
    return yaml.safe_load(match.group(1)), match.group(2)


def _source_stems() -> list[str]:
    return sorted(p.stem for p in CLAUDE_AGENTS.glob("*.md") if p.name not in _EXCLUDED)


def _restricted_in_sources() -> list[str]:
    return [stem for stem in _source_stems() if "tools" in _read_source(stem)[0]]


def _committed() -> list[Path]:
    return sorted(CODEX_AGENTS.glob("*.toml"))


def problems_with(stem: str, committed_text: str) -> list[str]:
    """Differences between a committed file's text and what the source should produce."""
    front, body = _read_source(stem)
    for old, new in BODY_EDITS.get(stem, []):
        body = body.replace(old, new)
    try:
        parsed = tomllib.loads(committed_text)
    except tomllib.TOMLDecodeError as exc:
        return [f"not TOML: {exc}"]
    found: list[str] = []
    if list(parsed) != ["name", "description", "developer_instructions"]:
        found.append(f"keys are {list(parsed)}")
    if parsed.get("name") != stem or parsed.get("name") != front["name"]:
        found.append(f"name is {parsed.get('name')!r}")
    if parsed.get("description") != front["description"]:
        found.append("description differs from the source")
    no_subagents = "Agent" in [
        t.strip() for t in str(front.get("disallowedTools") or "").split(",")
    ]
    expected = (body.rstrip("\n") + (NO_SUBAGENTS if no_subagents else "")).rstrip("\n") + PARAGRAPH
    if parsed.get("developer_instructions") != expected:
        found.append("developer_instructions differs from source body plus paragraph")
    return found


def test_the_not_shipped_list_is_what_the_sources_declare() -> None:
    assert _restricted_in_sources() == NOT_SHIPPED


def test_committed_files_are_exactly_the_unrestricted_agents() -> None:
    assert [p.stem for p in _committed()] == sorted(set(_source_stems()) - set(NOT_SHIPPED))


@pytest.mark.parametrize("path", _committed(), ids=lambda p: p.stem)
def test_committed_toml_matches_the_independent_expectation(path: Path) -> None:
    assert problems_with(path.stem, path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "tamper",
    [
        lambda t: t.replace('developer_instructions = "', 'developer_instructions = "X', 1),
        lambda t: t.replace("say that you did.", "say nothing.", 1),
        lambda t: t.replace('name = "', 'name = "x', 1),
        lambda t: t + 'extra = "key"\n',
        lambda t: t.replace("description = ", 'description = "changed"\n#', 1),
        lambda t: "not = [toml",
    ],
    ids=["body", "paragraph", "name", "extra-key", "description", "invalid"],
)
def test_a_tampered_temp_copy_fails_the_real_comparison(tamper, tmp_path: Path) -> None:
    """Negative control: the same comparison, run on an edited copy, reports problems."""
    source = _committed()[0]
    copy = tmp_path / source.name
    copy.write_text(tamper(source.read_text(encoding="utf-8")), encoding="utf-8")
    assert problems_with(source.stem, copy.read_text(encoding="utf-8")) != []
    assert problems_with(source.stem, source.read_text(encoding="utf-8")) == []


def test_orchestrator_names_no_agent_that_is_not_installed() -> None:
    """The edited orchestrator must not route to a skipped agent or to Claude's Task tool."""
    text = tomllib.loads((CODEX_AGENTS / "orchestrator.toml").read_text(encoding="utf-8"))
    table = text["developer_instructions"].split("Every row above")[0]
    assert "| **analyst** |" not in table and "| **security** |" not in table
    rows = [line for line in table.splitlines() if line.startswith("| **")]
    assert rows, "the routing table moved; update this test"
    named = [
        stem for stem in _restricted_in_sources() for line in rows if f"| **{stem}** |" in line
    ]
    assert named == [], f"table rows route to agents that are not installed: {named}"
    assert "Task (for delegation)" not in text["developer_instructions"]
    assert (
        'spawn_agent (for delegation; pass fork_turns="none" when the child reviews work)'
        in text["developer_instructions"]
    )


def test_the_row_edits_are_load_bearing() -> None:
    """Negative control: the unedited source still names the skipped agents."""
    _, body = _read_source("orchestrator")
    assert "| **analyst** |" in body and "| **security** |" in body
    assert "Task (for delegation)" in body
