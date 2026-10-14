"""The adr-review ten-round cap must say whether it resets, in every shipped copy (issue #5251).

The cap is a lifetime limit per debate log. A revision of the ADR text never
resets it. A closed debate (consensus, or round 10 without consensus) is
followed by a new debate in a new log that restarts at round 1. These tests pin
the wording in the template-owned SKILL.md, in the hand-maintained protocol
reference (`.claude/skills/adr-review/references`, the source for the mirrors),
and in the debate-log template. They also pin that every shipped tree carries
identical copies of the references.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

from copilot_body_translation import translate_reference_file

SKILL_TEMPLATE = REPO_ROOT / "templates" / "skills" / "adr-review.SKILL.md.tmpl"
SKILL_TREES = (
    REPO_ROOT / ".claude" / "skills" / "adr-review",
    REPO_ROOT / "src" / "claude" / "skills" / "adr-review",
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "adr-review",
    REPO_ROOT / "src" / "codex" / "skills" / "adr-review",
)
SOURCE_TREE = SKILL_TREES[0]
PROTOCOL = Path("references") / "debate-protocol.md"
ARTIFACTS = Path("references") / "artifacts.md"
FIRST_LOG_PATH = ".project-toolkit/critique/ADR-NNN-debate-log.md"
LATER_LOG_PATH = ".project-toolkit/critique/ADR-NNN-debate-log-2.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _round_cap_section(text: str) -> str:
    match = re.search(r"(?ms)^## Round Cap\n(.*?)(?=^## |\Z)", text)
    assert match, "debate-protocol.md has no '## Round Cap' section"
    return match.group(1)


def _debate_log_template(text: str) -> str:
    match = re.search(r"(?s)## Debate Log.*?```markdown\n(.*?)```", text)
    assert match, "artifacts.md has no fenced debate-log template"
    return match.group(1)


def test_skill_template_states_the_cap_is_a_lifetime_limit_per_log() -> None:
    text = _read(SKILL_TEMPLATE)
    consensus = next(line for line in text.splitlines() if line.startswith("**Consensus**"))
    assert "Max 10 rounds per debate log" in consensus
    assert "does not reset" in text
    assert "references/debate-protocol.md#round-cap" in text


def test_skill_template_checklist_asks_for_a_new_log_after_a_closed_debate() -> None:
    text = _read(SKILL_TEMPLATE)
    assert re.search(r"- \[ \] .*new debate log.*closed", text), (
        "the post-invocation checklist must tell a reviewer to look for a new log "
        "when the ADR was revised after a closed debate"
    )


@pytest.mark.parametrize("tree", SKILL_TREES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_protocol_round_cap_section_answers_the_reset_question(tree: Path) -> None:
    section = _round_cap_section(_read(tree / PROTOCOL))
    assert "lifetime limit per debate log" in section
    assert "does not reset" in section
    assert "Round 10 with no consensus" in section
    assert "accepts no round 11" in section


@pytest.mark.parametrize("tree", SKILL_TREES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_protocol_new_debate_rules_are_complete(tree: Path) -> None:
    section = _round_cap_section(_read(tree / PROTOCOL))
    # A later edit after any closed debate starts a new log at round 1.
    assert re.search(r"closed by consensus.*new debate", section, re.DOTALL)
    assert "restart at round 1" in section
    # The new log names its predecessor and inherits its unresolved issues.
    assert "Prior debate log" in section
    assert "unresolved issues" in section
    # The author of the contested text does not choose the reading.
    assert "does not choose" in section
    # An owner request for more rounds takes the same path, not an extension.
    assert "owner" in section


@pytest.mark.parametrize("tree", SKILL_TREES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_protocol_has_no_per_revision_budget_language(tree: Path) -> None:
    text = _read(tree / PROTOCOL).lower()
    for phrase in ("per-revision budget", "fresh 10-round", "counter resets", "reset the round"):
        assert phrase not in text, f"protocol must not describe a per-revision reset: {phrase!r}"


@pytest.mark.parametrize("tree", SKILL_TREES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_debate_log_template_makes_the_numbering_legible(tree: Path) -> None:
    template = _debate_log_template(_read(tree / ARTIFACTS))
    assert "- **Rounds**: [N] of 10" in template
    assert re.search(r"- \*\*Prior debate log\*\*: none \(otherwise the path", template)
    assert "## Round [N] Summary" in template


def test_skill_template_names_the_later_log_path_in_both_path_lines() -> None:
    text = _read(SKILL_TEMPLATE)
    assert text.count(LATER_LOG_PATH) >= 2, (
        "both SKILL.md debate-log path lines must name the later-log path, "
        "or following the checklist overwrites the closed log"
    )
    assert LATER_LOG_PATH in next(
        line for line in text.splitlines() if "new debate log exists" in line
    )


@pytest.mark.parametrize("tree", SKILL_TREES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_artifacts_save_to_defines_a_distinct_path_for_later_logs(tree: Path) -> None:
    text = _read(tree / ARTIFACTS)
    save_to = re.search(r"(?ms)^## Debate Log\n(.*?)^```markdown", text)
    assert save_to, "artifacts.md has no Debate Log Save-to block"
    assert FIRST_LOG_PATH in save_to.group(1)
    assert LATER_LOG_PATH in save_to.group(1)


@pytest.mark.parametrize("tree", SKILL_TREES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_protocol_round_cap_names_the_later_log_path(tree: Path) -> None:
    section = _round_cap_section(_read(tree / PROTOCOL))
    assert LATER_LOG_PATH in section
    assert "never overwrite" in section


@pytest.mark.parametrize("tree", SKILL_TREES[1:], ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
@pytest.mark.parametrize("reference", [PROTOCOL, ARTIFACTS], ids=lambda p: p.name)
def test_shipped_trees_mirror_the_source_references(tree: Path, reference: Path) -> None:
    expected = _read(SOURCE_TREE / reference)
    if tree.parts[-3] == "copilot-cli":
        # The Copilot mirror translates Claude call syntax (issue #5657).
        expected = translate_reference_file(expected, tree.parent)
    assert _read(tree / reference) == expected
