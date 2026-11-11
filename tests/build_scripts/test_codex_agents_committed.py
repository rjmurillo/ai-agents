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
    "If the step is a security review, state that no security agent reviewed it.\n"
)
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
    if parsed.get("developer_instructions") != body.rstrip("\n") + PARAGRAPH:
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
