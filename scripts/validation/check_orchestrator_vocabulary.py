#!/usr/bin/env python3
"""Gate: router agents carry no manager or supervisor vocabulary (ADR-065 Decision 1).

ADR-065 says the orchestrator routes and retries. It does not supervise: there
is no loop in which one model watches another, only a prompt out and a reply
back. A prompt that tells the router to coach, notice when a worker is stuck,
or course-correct asks for a capability that does not exist, and the gap is
silent because nothing fails when the supervision never happens.

Scope. ADR-065 names ``templates/agents/orchestrator*.md`` and any agent
declaring ``role: orchestrator``. ADR-098 later renamed roles, and no
``orchestrator`` role value exists now. The agents that route work are the
ones ``check_agent_delegation.py`` registers in ``DELEGATORS``; this gate
imports that set rather than keeping a second list. For each one it scans the
three rendered trees that carry the full body: ``src/claude/agents/``,
``src/copilot-cli/agents/``, and ``src/vs-code-agents/``.

What is scanned: the ``description`` frontmatter value and the body. Other
frontmatter keys are skipped, because tool lists name MCP servers such as
``cloudmcp-manager`` that are not prose. Fenced code blocks and inline code
spans are skipped for the same reason. A fence that never closes is itself a
finding, because everything after it would otherwise go unread. Fence rules
come from ``agent_gate_cli.prose_lines``, the same ones the delegation gate
uses.

Tokens. ADR-065's initial list is ``manage``, ``supervise``, ``coach``,
``mentor``, ``course-correct``, ``course correct``, ``notice when``,
``motivate``, and ``oversee``. This gate matches them at word boundaries in
their verb forms (``manages``, ``managing``, ``oversaw``), their agent nouns
(``manager``, ``supervisor``, ``overseer``), and their action nouns
(``supervision``, ``motivation``, ``course-correction``). Different than
canonical: it does not match ``management``, because the orchestrator's
``Context Budget Management`` section manages a context window, not an agent.
The action nouns that remain each describe one agent acting on another, so
they stay banned. ``manager`` is also the retired ADR-098 tier name.

Limit. ADR-065 Decision 1 also bans "semantically equivalent language". A token
list cannot see a paraphrase, so that part stays a review duty.

CLI::

    uv run python scripts/validation/check_orchestrator_vocabulary.py
    uv run python scripts/validation/check_orchestrator_vocabulary.py <repo-root>

Exit codes (ADR-035):
    0 - Success (no banned token in any router agent)
    1 - Logic error (a banned token, an unclosed fence, or a missing router file)
    2 - Config error (invalid repository root, or the Claude agent tree is missing)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_gate_cli
from check_agent_delegation import DELEGATORS

# (tree, filename suffix) for each rendered tree that carries the full body.
AGENT_TREES: tuple[tuple[Path, str], ...] = (
    (Path("src/claude/agents"), ".md"),
    (Path("src/copilot-cli/agents"), ".agent.md"),
    (Path("src/vs-code-agents"), ".agent.md"),
)

BANNED = re.compile(
    r"\b("
    r"manag(?:e|es|ed|ing|er|ers)"
    r"|supervis(?:e|es|ed|ing|or|ors|ion)"
    r"|coach(?:es|ed|ing)?"
    r"|mentor(?:s|ed|ing)?"
    r"|course[- ]correct(?:s|ed|ing|ion)?"
    r"|notice\s+when"
    r"|motivat(?:e|es|ed|ing|ion)"
    r"|overs(?:ee|ees|eeing|een|eer|aw)"
    r")\b",
    re.IGNORECASE,
)

# A code span may wrap onto the next line inside one paragraph (CommonMark 6.1),
# so the span pattern crosses single newlines. Paragraphs are scanned whole,
# which keeps a span from crossing a blank line.
# A code span opens and closes on backtick runs of equal length (CommonMark 6.1),
# so ``a `b` c`` is one span.
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)")


_INDENTED_MARKER = re.compile(r"^(?: {4,}|\t)[ \t]*(?:`+|~+)[ \t]*$")


def _mask_code(text: str) -> str:
    """Blank out inline code spans, keeping newlines so offsets map to lines."""
    return _INLINE_CODE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _paragraphs(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join consecutive non-blank prose lines into ``(first_line, text)`` paragraphs.

    Markdown treats a soft line break inside a paragraph as whitespace, so a
    banned phrase such as ``notice when`` may wrap across two lines.
    """
    paragraphs: list[tuple[int, str]] = []
    start, previous = 0, -1
    chunk: list[str] = []
    for number, line in lines:
        contiguous = chunk and number == previous + 1 and line.strip()
        if not contiguous:
            if chunk:
                paragraphs.append((start, "\n".join(chunk)))
            start, chunk = number, []
        # With no paragraph open, a line indented 4 or more spaces is an
        # indented code block (CommonMark 4.4). A bare backtick or tilde run
        # there is code, so it must not pair with a later run as a code span.
        if not chunk and _INDENTED_MARKER.match(line):
            previous = number
            continue
        if line.strip():
            chunk.append(line)
        previous = number
    if chunk:
        paragraphs.append((start, "\n".join(chunk)))
    return paragraphs


def scan_text(text: str) -> list[str]:
    """Return findings for one rendered agent file's text.

    Raises ``ValueError`` with a reason when the frontmatter cannot be read.
    """
    agent = agent_gate_cli.read_agent_text(text)
    findings: list[str] = []
    description = agent.frontmatter.get("description")
    if isinstance(description, str):
        for match in BANNED.finditer(_mask_code(description)):
            findings.append(f"description: '{match.group(0)}'")
    elif description is not None:
        findings.append(f"description is not a string ({type(description).__name__})")
    lines, unclosed = agent_gate_cli.prose_lines(agent.body)
    for first, paragraph in _paragraphs(lines):
        for match in BANNED.finditer(_mask_code(paragraph)):
            number = first + paragraph.count("\n", 0, match.start()) + agent.body_line_offset
            findings.append(f"line {number}: '{' '.join(match.group(0).split())}'")
    if unclosed:
        findings.append("a fenced code block never closes, so the rest of the body went unscanned")
    return findings


def find_vocabulary_findings(repo_root: Path) -> list[tuple[str, str]]:
    """Return ``(path, finding)`` pairs for every router agent in every tree."""
    findings: list[tuple[str, str]] = []
    for tree, suffix in AGENT_TREES:
        for name in sorted(DELEGATORS):
            rel = (tree / f"{name}{suffix}").as_posix()
            path = repo_root / rel
            if not path.is_file():
                findings.append((rel, "router agent file is missing"))
                continue
            try:
                hits = scan_text(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                findings.append((rel, f"cannot scan: {exc}"))
                continue
            findings.extend((rel, hit) for hit in hits)
    return findings


def validate_orchestrator_vocabulary(repo_root: Path) -> bool:
    """Return True when no router agent uses manager or supervisor vocabulary.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    findings = find_vocabulary_findings(repo_root)
    if not findings:
        return True
    print(
        f"[FAIL] {len(findings)} manager-vocabulary finding(s) in router agents. "
        "The orchestrator routes and retries; it cannot supervise (ADR-065 Decision 1):",
        file=sys.stderr,
    )
    for rel, text in findings:
        print(f"  {rel}: {text}", file=sys.stderr)
    print(
        "\nReword the template under templates/agents/ (shared, Claude, Copilot, "
        "and any partial), then run 'uv run python build/scripts/build_all.py'. "
        "Refs issue #7639.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    return agent_gate_cli.run_repo_gate(argv, validate_orchestrator_vocabulary, AGENT_TREES[0][0])


if __name__ == "__main__":
    raise SystemExit(main())
