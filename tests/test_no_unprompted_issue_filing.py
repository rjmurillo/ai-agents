"""Regression guard: no agent or skill template instructs unprompted issue filing.

Epic #5698, AC-6. The owner decides what becomes a tracked issue. An agent that
finds work flags it to the owner (builder-ethos.md, Task Completion Contract);
it does not file it. Filing is allowed only when the user's request asked for it.

Two checks run over every agent and skill authoring surface:

1. Directive phrases that make filing a gate condition or a default step, such
   as "cite the follow-up issue number" or "Create tech debt issue". Any match
   fails.
2. Filing commands (``gh issue create``, ``new_issue.py``, ``issue_write``,
   ``create_issue``). A match passes only when the same paragraph or the
   neighboring lines carry a user-request gate ("only when the user", "explicit")
   or a prohibition ("Do not file"), and never with ``--source agent``.

The github skill is exempt: it documents the filing tools for callers that were
asked to file. Every other exemption sits in ``ALLOWLIST`` with a reason, and a
stale entry (one that no longer matches anything) fails the test.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Authoring templates, then the hand-maintained and rendered copies that ship.
SCAN_GLOBS = (
    "templates/agents/**/*.md",
    "templates/agents/**/*.tmpl",
    "templates/agents/**/*.mustache",
    "templates/skills/**/*.tmpl",
    "templates/skills/**/*.md",
    ".claude/skills/*/references/**/*.md",
    ".claude/agents/*.md",
    ".github/agents/*.agent.md",
    "src/claude/agents/*.md",
)

# The github skill documents the filing tools themselves.
EXEMPT_PREFIXES = (
    "templates/skills/github.SKILL.md.tmpl",
    ".claude/skills/github/",
)

DIRECTIVE_PATTERNS = {
    "follow-up issue as a gate": re.compile(
        r"follow-?up issue (number|that will close)|cite (the )?follow-?up issue",
        re.IGNORECASE,
    ),
    "issue filing as the default step": re.compile(
        r"file (a|the) (github |follow-?up )+issue when|and file the follow-?up issue"
        r"|create tech debt issue|must be (backlogged|filed) as|filed as (a )?github issue",
        re.IGNORECASE,
    ),
    "agent-sourced filing": re.compile(r"--source agent", re.IGNORECASE),
}

FILING_COMMAND = re.compile(r"gh issue create|new_issue\.py|issue_write|create_issue\b")

# A user-request gate or a prohibition within the window clears a filing command.
GATE = re.compile(
    r"only when the user|user explicitly asks|explicitly asks? (you )?(for|to)"
    r"|user's request|Do not (run|file)|Never pass|never file|does not file"
    r"|not file",
    re.IGNORECASE,
)
WINDOW_LINES = 8

# path -> reason. Each entry is a filing mention that is not agent-initiated.
ALLOWLIST: dict[str, str] = {}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    text: str


def _is_exempt(relative: str) -> bool:
    return relative.startswith(EXEMPT_PREFIXES)


def scan_text(relative: str, text: str) -> list[Violation]:
    """Return every violation in one file's text. Pure, no I/O."""
    lines = text.splitlines()
    found: list[Violation] = []
    for index, line in enumerate(lines):
        for rule, pattern in DIRECTIVE_PATTERNS.items():
            if pattern.search(line) and not _gated_prohibition(lines, index):
                found.append(Violation(relative, index + 1, rule, line.strip()[:120]))
        if FILING_COMMAND.search(line) and not _has_gate(lines, index):
            found.append(
                Violation(relative, index + 1, "ungated filing command", line.strip()[:120])
            )
    return found


def _window(lines: list[str], index: int) -> str:
    return "\n".join(lines[max(0, index - WINDOW_LINES) : index + WINDOW_LINES + 1])


def _has_gate(lines: list[str], index: int) -> bool:
    return bool(GATE.search(_window(lines, index)))


def _gated_prohibition(lines: list[str], index: int) -> bool:
    """A directive phrase quoted inside a prohibition, for example 'Never pass --source agent'."""
    return bool(re.search(r"Never pass|Do not file|Do not run", lines[index], re.IGNORECASE))


def _scan_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in SCAN_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def scan_repo() -> list[Violation]:
    found: list[Violation] = []
    for path in _scan_files():
        relative = path.relative_to(ROOT).as_posix()
        if _is_exempt(relative) or relative in ALLOWLIST:
            continue
        found.extend(scan_text(relative, path.read_text(encoding="utf-8")))
    return found


def _format(violations: list[Violation]) -> str:
    return "\n".join(f"{v.path}:{v.line}: {v.rule}: {v.text}" for v in violations)


class TestRepositoryTemplates:
    def test_no_template_or_skill_instructs_unprompted_filing(self):
        violations = scan_repo()
        assert not violations, (
            "Agent and skill text must flag agent-found work to the owner, not file it. "
            "Gate filing on the user's explicit request.\n" + _format(violations)
        )

    def test_scan_covers_the_known_sites(self):
        scanned = {p.relative_to(ROOT).as_posix() for p in _scan_files()}
        for expected in (
            ".claude/skills/adr-review/references/issue-resolution.md",
            "templates/agents/qa.shared.md",
            "templates/agents/security.shared.md",
            "templates/skills/research.SKILL.md.tmpl",
            "templates/agents/task-decomposer.claude.md.tmpl",
        ):
            assert expected in scanned

    def test_allowlist_has_no_stale_entries(self):
        scanned = {p.relative_to(ROOT).as_posix() for p in _scan_files()}
        assert set(ALLOWLIST) <= scanned

    def test_github_skill_is_exempt_because_it_documents_the_tools(self):
        assert _is_exempt("templates/skills/github.SKILL.md.tmpl")
        assert _is_exempt(".claude/skills/github/references/examples.md")
        assert not _is_exempt("templates/skills/research.SKILL.md.tmpl")


class TestDetector:
    """The old wording of every swept site must fail; the new wording must pass."""

    def test_qa_conditional_requiring_an_issue_number_fails(self):
        text = "A CONDITIONAL verdict must cite the follow-up issue number that will close the gap."
        assert scan_text("a.md", text)

    def test_security_conditional_requiring_an_issue_number_fails(self):
        text = "Cite the follow-up issue number in the verdict."
        assert scan_text("a.md", text)

    def test_adr_review_deferral_must_be_backlogged_fails(self):
        text = "**Critical**: Deferred P1 items MUST be backlogged as GitHub issues."
        assert scan_text("a.md", text)

    def test_adr_review_gh_issue_create_template_fails(self):
        assert scan_text("a.md", "```bash\ngh issue create \\\n  --title X\n```")

    def test_research_file_issue_when_work_identified_fails(self):
        assert scan_text(
            "a.md", "5. **Action.** File a GitHub issue when implementation work is identified."
        )

    def test_research_description_filing_the_follow_up_fails(self):
        assert scan_text("a.md", "map it onto this project, and file the follow-up issue.")

    def test_task_decomposer_source_agent_fails(self):
        assert scan_text("a.md", "`new_issue.py` to file (with `--source agent`, `--blocked-by`)")

    def test_implementer_tech_debt_issue_fails(self):
        assert scan_text("a.md", "- **No**: Create tech debt issue, do not refactor now")

    def test_bare_filing_command_fails(self):
        assert scan_text("a.md", "Run `gh issue create --title X` for each finding.")

    def test_filing_command_gated_on_the_user_request_passes(self):
        text = (
            "Bash only for `gh issue create`, and only when the user explicitly asks for an issue."
        )
        assert scan_text("a.md", text) == []

    def test_prohibition_passes(self):
        text = "Do not run `gh issue create` or `new_issue.py` to record a deferral."
        assert scan_text("a.md", text) == []

    def test_gate_far_from_the_command_does_not_clear_it(self):
        filler = "\n".join("unrelated line" for _ in range(WINDOW_LINES + 2))
        text = f"Only when the user asks.\n{filler}\nRun `gh issue create` now."
        assert scan_text("a.md", text)

    def test_never_pass_source_agent_is_a_prohibition(self):
        assert scan_text("a.md", "Never pass `--source agent` from this skill.") == []

    def test_clean_text_passes(self):
        assert scan_text("a.md", "Flag the gap to the owner in the verdict.") == []

    def test_violation_reports_one_based_line(self):
        found = scan_text("a.md", "ok\nCreate tech debt issue")
        assert [v.line for v in found] == [2]
