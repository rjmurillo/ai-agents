"""Pin the system-capability doctrine to one canonical home (issue #6656).

The objective (optimize verified system outcomes, not unaided model
competence) lives only in ``.agents/governance/agent-design-principles.md``.
``AGENTS.md`` and its routing detail mirror carry a one-clause pointer so an
agent with no prior context can find it. These tests fail if the pointer
drifts from the doc, if the doc loses the four-part distinction, or if the
doctrine is copied into an always-on rule.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / ".agents" / "governance" / "agent-design-principles.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
HEADING = "## Operating Objective: System Capability, Not Model Competence"
FOUR_PARTS = ("Base model", "Agent system", "External state", "Measurable outcomes")
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
ROUTING_DETAIL = REPO_ROOT / ".project-toolkit" / "context" / "AGENTS-details" / "routing.md"
POINTER_FILES = (AGENTS_MD, ROUTING_DETAIL)
DOCTRINE_SENTENCES = (
    "Frozen weights do not stop the agent system",
    "Optimize verified task outcomes of the whole system",
)
RULES_DIR = REPO_ROOT / "templates" / "rules"
POINTER_CLAUSE = "goal: system outcomes, not model competence (gov `agent-design-principles`)"
INVERTED_CLAUSE = "goal: maximize model competence (gov `agent-design-principles`)"


def _rule_paths(text: str) -> list[str]:
    """Return the ``paths`` frontmatter entries of a rule, or ``[]`` if absent."""
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return []
    frontmatter = match.group(1)
    inline = re.search(r"^paths:\s*\[(.*)\]\s*$", frontmatter, re.MULTILINE)
    if inline:
        return re.findall(r"[\"']([^\"']+)[\"']", inline.group(1))
    block = re.search(r"^paths:\s*\n((?:[ \t]+-[^\n]*\n?)+)", frontmatter, re.MULTILINE)
    if block:
        return re.findall(r"^[ \t]+-\s*[\"']?([^\"'\n]+?)[\"']?\s*$", block.group(1), re.MULTILINE)
    return []


def _discover_always_on_rules() -> tuple[Path, ...]:
    return tuple(
        rule
        for rule in sorted(RULES_DIR.glob("*.md"))
        if _rule_paths(rule.read_text(encoding="utf-8")) == ["**"]
    )


ALWAYS_ON_RULES = _discover_always_on_rules()


def test_doc_has_heading_exactly_once() -> None:
    assert DOC.read_text(encoding="utf-8").count(HEADING) == 1


def _section_text(text: str) -> str:
    """Return the doctrine section body: from HEADING to the next ``## `` heading."""
    start = text.index(HEADING)
    end = text.find("\n## ", start + len(HEADING))
    return text[start:] if end == -1 else text[start:end]


@pytest.mark.parametrize("part", FOUR_PARTS)
def test_doc_names_each_system_part_as_table_row(part: str) -> None:
    section = _section_text(DOC.read_text(encoding="utf-8"))
    assert f"| {part} |" in section


def test_section_slice_excludes_text_after_next_heading() -> None:
    text = f"{HEADING}\n\n| Base model |\n\n## Other\n\n| Agent system |\n"
    section = _section_text(text)
    assert "| Base model |" in section
    assert "| Agent system |" not in section


def test_section_slice_runs_to_end_when_no_later_heading() -> None:
    assert "| Base model |" in _section_text(f"{HEADING}\n\n| Base model |\n")


CONTRADICTING_PHRASES = ("cannot learn", "no system-level learning", "system cannot improve")


def test_doc_does_not_claim_frozen_weights_mean_no_system_learning() -> None:
    section = _section_text(DOC.read_text(encoding="utf-8"))
    assert "Frozen weights do not stop the agent system" in section
    lowered = section.lower()
    for phrase in CONTRADICTING_PHRASES:
        assert phrase not in lowered


def test_contradicting_phrase_check_would_catch_an_inverted_claim() -> None:
    inverted = (
        f"{HEADING}\n\nFrozen weights do not stop the agent system. The system cannot learn.\n"
    )
    assert any(phrase in _section_text(inverted).lower() for phrase in CONTRADICTING_PHRASES)


def test_doc_links_outcome_measurement_issue_instead_of_reimplementing() -> None:
    assert "#5768" in DOC.read_text(encoding="utf-8")


def test_doc_names_in_repo_outcome_instrument_and_it_exists() -> None:
    section = _section_text(DOC.read_text(encoding="utf-8"))
    assert "REQ-042" in section
    assert "scripts/eval/eval_durable_outcome.py" in section
    assert (REPO_ROOT / "scripts" / "eval" / "eval_durable_outcome.py").is_file()
    assert list((REPO_ROOT / ".project-toolkit" / "specs" / "requirements").glob("REQ-042-*.md"))


def _pointer_is_exact(line: str) -> bool:
    return POINTER_CLAUSE in line.split("|")


def _context_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("Context|")
    ]


@pytest.mark.parametrize("guide", POINTER_FILES, ids=lambda p: p.name)
def test_context_line_carries_exact_pointer_clause(guide: Path) -> None:
    lines = _context_lines(guide)
    assert len(lines) == 1, f"{guide} needs exactly one Context| line, got {len(lines)}"
    assert _pointer_is_exact(lines[0])


def test_pointer_target_doc_exists() -> None:
    assert DOC.is_file()


def test_pointer_check_accepts_the_exact_clause() -> None:
    assert _pointer_is_exact(f"Context|{POINTER_CLAUSE}|script/rule before model")


def test_pointer_check_rejects_a_split_pointer() -> None:
    split = "Context|goal: not model competence|x|gov `agent-design-principles`"
    assert not _pointer_is_exact(split)


def test_pointer_check_rejects_a_missing_pointer() -> None:
    assert not _pointer_is_exact("Context|script/rule before model")


def test_pointer_check_rejects_the_inverted_objective() -> None:
    assert not _pointer_is_exact(f"Context|{INVERTED_CLAUSE}|script/rule before model")


def test_always_on_discovery_is_non_empty_and_includes_universal() -> None:
    names = {rule.name for rule in ALWAYS_ON_RULES}
    assert names, "no always-on rules discovered; frontmatter parser may be broken"
    assert "universal.md" in names


def test_always_on_discovery_matches_every_star_star_rule() -> None:
    expected = {
        rule.name
        for rule in RULES_DIR.glob("*.md")
        if re.search(r'^paths:\s*\[\s*"\*\*"\s*\]', rule.read_text(encoding="utf-8"), re.MULTILINE)
    }
    assert {rule.name for rule in ALWAYS_ON_RULES} == expected


def test_rule_paths_parses_block_list_and_ignores_missing_frontmatter() -> None:
    assert _rule_paths('---\npaths:\n  - "a/**"\n  - "b"\npriority: high\n---\nbody') == [
        "a/**",
        "b",
    ]
    assert _rule_paths("no frontmatter") == []
    assert _rule_paths("---\npriority: high\n---\nbody") == []


def test_discovery_includes_lossless_queue_reads() -> None:
    assert "lossless-queue-reads.md" in {rule.name for rule in ALWAYS_ON_RULES}


def test_claude_md_keeps_orchestrator_default_for_non_trivial_work() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert 'Task(subagent_type="orchestrator")` by default for non-trivial work' in text


@pytest.mark.parametrize("rule", ALWAYS_ON_RULES, ids=lambda p: p.name)
def test_doctrine_is_not_copied_into_always_on_rules(rule: Path) -> None:
    text = rule.read_text(encoding="utf-8")
    assert HEADING not in text
    for sentence in DOCTRINE_SENTENCES:
        assert sentence not in text


def _tracked_files_containing(needles: tuple[str, ...]) -> set[str]:
    """Return repo-relative tracked paths that contain any needle as a fixed string."""
    args = ["git", "grep", "-l", "-F"]
    for needle in needles:
        args += ["-e", needle]
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return {line for line in result.stdout.splitlines() if line}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_doctrine_has_exactly_one_canonical_source_in_tracked_files() -> None:
    hits = _tracked_files_containing((HEADING, *DOCTRINE_SENTENCES))
    hits.discard(Path(__file__).resolve().relative_to(REPO_ROOT).as_posix())
    assert hits == {DOC.relative_to(REPO_ROOT).as_posix()}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_tracked_file_scan_reports_known_hit_and_no_hit_for_absent_text() -> None:
    assert _tracked_files_containing((HEADING,)) >= {DOC.relative_to(REPO_ROOT).as_posix()}
    assert _tracked_files_containing(("zz-no-such-doctrine-text-\x01-zz",)) == set()
