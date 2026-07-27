#!/usr/bin/env python3
"""Validate that every agent named in a capability matrix is a real agent.

Several agent prompts publish a routing table whose first column is a bolded
agent name, introduced by a ``| Agent |`` header row. The orchestrator's
"Agent Capability Matrix" is the largest. Those tables are the routing surface:
a model reads the table and delegates to the name it finds there.

A row naming an agent that does not exist is worse than a missing row. The
delegation call resolves to nothing, the harness reports no error, and the work
is silently skipped. Issue: the orchestrator matrix carried a ``memory`` row for
months after cross-session memory became a skill rather than an agent, so every
orchestrator run that trusted the table and routed memory work lost it.

This validator pins one direction only: every name cited in a matrix MUST have
an agent file. It deliberately does NOT enforce the inverse (every agent file
must appear in some matrix). Matrix membership is a curation decision with a
context-budget cost: the repo ships more agents than any single routing table
should list, and which ones earn a row is a judgment call, not an invariant.

Scanned trees, all of which carry copies of the same matrices:

  templates/agents/       canonical shared templates
  .claude/agents/         hand-maintained Claude Code copy (also the name source)
  .github/agents/         hand-maintained Copilot copy
  src/claude/             hand-maintained claude-agents plugin copy
  src/copilot-cli/agents/ generated Copilot plugin copy
  src/vs-code-agents/     generated VS Code copy

Agent existence is resolved against ``.claude/agents/*.md``, the tree that
``validate_install_parity.py`` treats as the self-host copy and that carries one
file per registered agent.

ANTI-VACUOUS GUARD: a scan that silently finds nothing is a passing scan that
proves nothing. Three structural checks fail the run rather than report success:
no matrix found anywhere, no matrix found in the canonical ``templates/agents``
tree, and a file whose text contains a matrix header but from which zero rows
parse. The last catches the realistic regression, where the table format shifts
and the row pattern quietly stops matching while the validator keeps exiting 0.

The guard deliberately does not require every scanned tree to carry a matrix. A
tree holding only agent definitions and no routing table is a valid state, so
that rule would fire on correct repositories. Protection against a tree being
dropped from ``MATRIX_TREES`` lives in the test suite instead, anchored on the
filesystem rather than on this module's own constants.

EXIT CODES (per .agents/architecture/ADR-035-exit-code-standardization.md):
  0 - Success: every cited agent name resolves
  1 - Violations found, or the scan degenerated (no matrices, or a parse gap)
  2 - Configuration error: the agent name source is missing
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Tree that defines which agent names exist. One file per registered agent.
AGENT_NAME_SOURCE = Path(".claude/agents")

# Canonical tree. Matrices originate here and propagate to the copies, so a
# scan that finds nothing here is looking in the wrong place.
CANONICAL_TREE = Path("templates/agents")

# Trees carrying matrix copies. Relative to the repo root. An absent tree is
# skipped, and a present tree carrying no matrix is a valid state: not every
# agent tree publishes a routing table.
MATRIX_TREES: tuple[Path, ...] = (
    Path("templates/agents"),
    Path(".claude/agents"),
    Path(".github/agents"),
    Path("src/claude"),
    Path("src/copilot-cli/agents"),
    Path("src/vs-code-agents"),
)

# ``| Agent | Use For | Model | Avoid When |`` and friends. The first column
# header is the marker; downstream columns vary per matrix.
MATRIX_HEADER = re.compile(r"^\|\s*Agent\s*\|")

# ``|-------|---------|`` alignment row directly under a header.
TABLE_SEPARATOR = re.compile(r"^\|[\s:|-]+\|\s*$")

# ``| **implementer** | ... |`` or ``| implementer | ... |``. Agent names are
# lowercase kebab-case. Bold is optional: the orchestrator matrix bolds the
# name, the per-category tables in ``AGENTS.md`` do not. The ``| Agent |``
# header is what establishes that column one holds an agent name, so both
# spellings are in scope and neither is a false positive.
MATRIX_ROW = re.compile(r"^\|\s*(?:\*\*)?([a-z0-9][a-z0-9._-]*)(?:\*\*)?\s*\|")


@dataclass(frozen=True)
class Citation:
    """One agent name cited by one matrix row."""

    name: str
    path: Path
    line: int


@dataclass
class ScanResult:
    """Outcome of a full repository scan."""

    citations: list[Citation] = field(default_factory=list)
    files_with_matrix: list[Path] = field(default_factory=list)
    parse_gaps: list[Path] = field(default_factory=list)
    trees_scanned: list[Path] = field(default_factory=list)

    def degeneracy(self) -> list[str]:
        """Return reasons the scan found too little to prove anything.

        An empty list means the scan covered real ground. Any entry means the
        run must fail even when zero violations were found.
        """
        reasons: list[str] = []
        if not self.files_with_matrix:
            reasons.append(
                "no capability matrix found in any scanned tree; either "
                "MATRIX_HEADER no longer matches the table format or "
                "MATRIX_TREES is stale"
            )
        elif not any(
            path.is_relative_to(CANONICAL_TREE) for path in self.files_with_matrix
        ):
            reasons.append(
                f"no capability matrix found under {CANONICAL_TREE}; the "
                "canonical templates are where the matrices originate, so an "
                "empty result there means the scan is looking in the wrong place"
            )
        for path in self.parse_gaps:
            reasons.append(f"matrix header present but no rows parsed: {path}")
        return reasons


def known_agents(repo_root: Path) -> set[str]:
    """Return the set of registered agent names.

    Raises:
        FileNotFoundError: the name source tree is absent, which makes every
            citation look broken. Fail loudly rather than report a flood of
            false violations.
    """
    source = repo_root / AGENT_NAME_SOURCE
    if not source.is_dir():
        raise FileNotFoundError(f"agent name source not found: {AGENT_NAME_SOURCE}")
    return {
        p.stem
        for p in source.glob("*.md")
        # AGENTS.md and CLAUDE.md are directory-scoped instruction files, not
        # agent definitions, and their stems are uppercase so they cannot
        # collide with a kebab-case citation.
        if not p.stem.isupper()
    }


def parse_matrix_rows(text: str) -> list[tuple[str, int]]:
    """Extract ``(agent_name, line_number)`` for every matrix row in ``text``.

    Line numbers are 1-based. A matrix runs from a ``| Agent |`` header through
    the first line that does not start with a pipe.
    """
    rows: list[tuple[str, int]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not MATRIX_HEADER.match(lines[index]):
            index += 1
            continue
        cursor = index + 1
        if cursor < len(lines) and TABLE_SEPARATOR.match(lines[cursor]):
            cursor += 1
        while cursor < len(lines) and lines[cursor].startswith("|"):
            match = MATRIX_ROW.match(lines[cursor])
            if match:
                rows.append((match.group(1), cursor + 1))
            cursor += 1
        index = cursor
    return rows


def has_matrix_header(text: str) -> bool:
    """Report whether ``text`` contains a matrix header line at all."""
    return any(MATRIX_HEADER.match(line) for line in text.splitlines())


def scan(repo_root: Path) -> ScanResult:
    """Scan every configured tree for matrix citations and structural gaps."""
    result = ScanResult()
    for tree in MATRIX_TREES:
        directory = repo_root / tree
        if not directory.is_dir():
            continue
        result.trees_scanned.append(tree)
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if not has_matrix_header(text):
                continue
            relative = path.relative_to(repo_root)
            result.files_with_matrix.append(relative)
            rows = parse_matrix_rows(text)
            if not rows:
                result.parse_gaps.append(relative)
                continue
            for name, line in rows:
                result.citations.append(Citation(name, relative, line))
    return result


def violations(result: ScanResult, agents: set[str]) -> list[Citation]:
    """Return citations naming an agent with no file, sorted for stable output."""
    return sorted(
        (c for c in result.citations if c.name not in agents),
        key=lambda c: (c.name, str(c.path), c.line),
    )


def report(result: ScanResult, agents: set[str], bad: list[Citation]) -> None:
    """Print a human-readable summary of the scan."""
    print("=== Agent Capability Matrix Reference Validation ===")
    print()
    print(f"Registered agents:      {len(agents)}")
    print(f"Trees scanned:          {len(result.trees_scanned)}")
    print(f"Files carrying matrix:  {len(result.files_with_matrix)}")
    print(f"Rows cited:             {len(result.citations)}")
    print(f"Distinct names cited:   {len({c.name for c in result.citations})}")
    print()

    degeneracy = result.degeneracy()
    for reason in degeneracy:
        print(f"ERROR: {reason}")
    if degeneracy:
        print()
        print(
            "A scan that finds nothing proves nothing. Fix the pattern or the "
            "tree list; do not silence this."
        )
        print()

    if not bad:
        print("OK: every agent named in a capability matrix resolves to an agent file.")
        return

    print(f"VIOLATIONS: {len(bad)} matrix row(s) name an agent that does not exist")
    print()
    for citation in bad:
        print(f"  {citation.path}:{citation.line}: unknown agent '{citation.name}'")
    print()
    print(
        "A delegation naming a nonexistent agent fails silently and the work is "
        "skipped. Either add the agent, or remove the row. If the capability "
        "moved to a skill, say so in prose instead of leaving a routing row."
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See module docstring for exit codes."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root to scan. Defaults to the checkout containing this script.",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()

    try:
        agents = known_agents(repo_root)
    except FileNotFoundError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    result = scan(repo_root)
    bad = violations(result, agents)
    report(result, agents, bad)

    if bad or result.degeneracy():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
