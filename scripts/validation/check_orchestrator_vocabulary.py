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
spans are skipped for the same reason.

Tokens. ADR-065's initial list is ``manage``, ``supervise``, ``coach``,
``mentor``, ``course-correct``, ``course correct``, ``notice when``,
``motivate``, and ``oversee``. This gate matches their verb and agent-noun
forms at word boundaries (``manages``, ``managing``, ``supervisor``,
``oversaw``). Different than canonical: it does not match ``management``,
because the orchestrator's ``Context Budget Management`` section manages a
context window, not an agent, and a bare ``manage`` substring would flag it.
It does match ``manager``, the retired ADR-098 tier name.

CLI::

    uv run python scripts/validation/check_orchestrator_vocabulary.py
    uv run python scripts/validation/check_orchestrator_vocabulary.py <repo-root>

Exit codes (ADR-035):
    0 - Success (no banned token in any router agent)
    1 - Logic error (one or more banned tokens found, or a router file is missing)
    2 - Config error (invalid repository root)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_agent_delegation import DELEGATORS

from scripts.hook_utilities.frontmatter_block import (
    FrontmatterStatus,
    parse_frontmatter,
)

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

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"`[^`\n]*`")


def _prose_lines(body: str) -> list[tuple[int, str]]:
    """Return ``(line_number, text)`` for body lines outside fences, code spans removed."""
    kept: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(body.splitlines(), start=1):
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence is None:
            kept.append((number, _INLINE_CODE.sub("", line)))
    return kept


def scan_text(text: str) -> list[str]:
    """Return findings for one rendered agent file's text.

    Raises ``ValueError`` when the file has no readable frontmatter.
    """
    result = parse_frontmatter(text, yaml, allow_duplicate_keys=True)
    if not result.present or result.status is not FrontmatterStatus.VALID:
        raise ValueError("no readable YAML frontmatter block")
    loaded = result.metadata if isinstance(result.metadata, dict) else {}
    findings: list[str] = []
    description = loaded.get("description")
    if isinstance(description, str):
        for match in BANNED.finditer(_INLINE_CODE.sub("", description)):
            findings.append(f"description: '{match.group(0)}'")
    # Report file line numbers, not body-relative ones, so a reader can jump to them.
    body = result.body
    offset = text[: len(text) - len(body)].count("\n") if text.endswith(body) else 0
    for number, line in _prose_lines(body):
        for match in BANNED.finditer(line):
            findings.append(f"line {number + offset}: '{match.group(0)}'")
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
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_orchestrator_vocabulary(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
