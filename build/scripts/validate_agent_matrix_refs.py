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
  .claude/agents/         hand-maintained Claude Code copy
  .github/agents/         hand-maintained Copilot copy
  src/claude/             hand-maintained claude-agents plugin copy
  src/copilot-cli/agents/ generated Copilot plugin copy
  src/vs-code-agents/     generated VS Code copy

RESOLUTION IS PER TREE, NOT GLOBAL. A citation is checked against the agent
files of the tree that carries it, never against a single repository-wide
roster. The first version of this validator resolved every citation against
``.claude/agents``, and that is the tree carrying the most agent files, so it
validated the weakest claim available: "this name exists somewhere". The
load-bearing claim is "this name exists in the install that ships this table".
An adversarial review found the difference is not theoretical. ``quality-auditor``
shipped to ``.claude/agents`` alone while the shared orchestrator body cited it,
so five of six installs published a routing row for an agent they do not carry,
and a global check reported success. ``.claude/``, ``src/claude/``, and
``src/copilot-cli/`` are separate plugin roots that install standalone, so a
name absent from a root is unreachable for everyone who installs that root.

Agent names are derived by stripping each tree's own filename suffix, because
the trees do not agree on one: ``orchestrator.shared.md`` in the templates,
``orchestrator.md`` under ``.claude/agents``, ``orchestrator.agent.md`` under
``.github/agents``. Suffix stripping is also what keeps non-agent files such as
``copilot-instructions.md`` out of the roster.

ANTI-VACUOUS GUARD: a scan that silently finds nothing is a passing scan that
proves nothing. These structural checks fail the run rather than report success:
no matrix found anywhere, no matrix found in the canonical ``templates/agents``
tree, a file whose text contains a matrix header but from which zero rows parse,
a data row inside a matrix that does not parse as an agent name, and a
configured tree that exists but yields no agent files at all. The last three
catch the realistic regressions, where a table format shifts or a filename
convention changes and the patterns quietly stop matching while the validator
keeps exiting 0. Every one of these was reachable in review: bolding the header
and wrapping a name in backticks both hid a phantom row from the first version.

The guard deliberately does not require every scanned tree to carry a matrix. A
tree holding only agent definitions and no routing table is a valid state, so
that rule would fire on correct repositories. Protection against a tree being
dropped from ``AGENT_TREES`` lives in the test suite instead, anchored on the
filesystem rather than on this module's own constants.

EXIT CODES (per .agents/architecture/ADR-035-exit-code-standardization.md):
  0 - Success: every cited agent name resolves within its own tree
  1 - Violations found, or the scan degenerated (no matrices, or a parse gap)
  2 - Configuration error: no configured tree yields any agent file
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Canonical tree. Matrices originate here and propagate to the copies, so a
# scan that finds nothing here is looking in the wrong place.
CANONICAL_TREE = Path("templates/agents")

# Trees carrying matrix copies, each paired with the filename suffix that marks
# an agent definition in that tree. The suffix is what turns a filename into an
# agent name, so it also decides which files are agents at all: stripping
# ``.agent.md`` leaves ``copilot-instructions.md`` out of the roster, where a
# bare ``.md`` rule would have admitted it.
#
# Relative to the repo root. An absent tree is skipped, and a present tree
# carrying no matrix is a valid state: not every agent tree publishes a routing
# table. A present tree yielding no agent files is not valid, and is caught by
# the degeneracy guard.
AGENT_TREES: tuple[tuple[Path, str], ...] = (
    (Path("templates/agents"), ".shared.md"),
    (Path(".claude/agents"), ".md"),
    (Path(".github/agents"), ".agent.md"),
    (Path("src/claude"), ".md"),
    (Path("src/copilot-cli/agents"), ".agent.md"),
    (Path("src/vs-code-agents"), ".agent.md"),
)

# ``| Agent | Use For | Model | Avoid When |`` and friends. The first column
# header is the marker; downstream columns vary per matrix. Bold and backticks
# are tolerated because a header reformat must not silently drop a whole table
# from the scan: an adversarial review hid a phantom row behind ``| **Agent** |``
# and the stricter pattern reported success.
MATRIX_HEADER = re.compile(r"^\|\s*(?:\*\*)?\s*`?Agent`?\s*(?:\*\*)?\s*\|", re.IGNORECASE)

# ``|-------|---------|`` alignment row directly under a header.
TABLE_SEPARATOR = re.compile(r"^\|[\s:|-]+\|\s*$")

# ``| **implementer** | ... |``, ``| implementer | ... |``, or
# ``| `implementer` | ... |``. Agent names are lowercase kebab-case. Bold and
# backticks are optional: the orchestrator matrix bolds the name, the
# per-category tables in ``AGENTS.md`` do not, and either could gain code
# formatting in a reformat. The ``| Agent |`` header is what establishes that
# column one holds an agent name, so all three spellings are in scope and none
# is a false positive. A row inside a matrix that matches none of them is not
# ignored; it is reported as a parse gap.
MATRIX_ROW = re.compile(r"^\|\s*(?:\*\*)?\s*`?([a-z0-9][a-z0-9._-]*)`?\s*(?:\*\*)?\s*\|")


@dataclass(frozen=True)
class Citation:
    """One agent name cited by one matrix row, and the tree that must carry it."""

    name: str
    path: Path
    line: int
    tree: Path


@dataclass
class ScanResult:
    """Outcome of a full repository scan."""

    citations: list[Citation] = field(default_factory=list)
    files_with_matrix: list[Path] = field(default_factory=list)
    parse_gaps: list[Path] = field(default_factory=list)
    unparsed_rows: list[tuple[Path, int, str]] = field(default_factory=list)
    trees_scanned: list[Path] = field(default_factory=list)
    empty_trees: list[Path] = field(default_factory=list)
    agents_by_tree: dict[Path, set[str]] = field(default_factory=dict)

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
                "AGENT_TREES is stale"
            )
        elif not any(
            path.is_relative_to(CANONICAL_TREE) for path in self.files_with_matrix
        ):
            reasons.append(
                f"no capability matrix found under {CANONICAL_TREE}; the "
                "canonical templates are where the matrices originate, so an "
                "empty result there means the scan is looking in the wrong place"
            )
        for tree in self.empty_trees:
            reasons.append(
                f"tree {tree} exists but yields no agent files; its configured "
                "filename suffix no longer matches what the tree ships, so "
                "every citation in it would resolve against an empty roster"
            )
        for path in self.parse_gaps:
            reasons.append(f"matrix header present but no rows parsed: {path}")
        for path, line, text in self.unparsed_rows:
            reasons.append(
                f"{path}:{line}: row inside a capability matrix does not parse "
                f"as an agent name: {text.strip()[:72]}"
            )
        return reasons


def known_agents(tree_root: Path, suffix: str) -> set[str]:
    """Return the agent names one tree ships, by stripping ``suffix``.

    Files not ending in ``suffix`` are not agent definitions and are excluded.
    Uppercase stems are directory-scoped instruction files such as ``AGENTS.md``
    and ``CLAUDE.md``, never agents, and are excluded as well; they cannot
    collide with a kebab-case citation in any case.
    """
    names: set[str] = set()
    for path in tree_root.glob(f"*{suffix}"):
        name = path.name[: -len(suffix)]
        if name and not name.isupper():
            names.add(name)
    return names


def parse_matrix_rows(text: str) -> tuple[list[tuple[str, int]], list[tuple[int, str]]]:
    """Split every matrix in ``text`` into parsed rows and unparsed rows.

    Returns ``(rows, unparsed)`` where ``rows`` holds ``(agent_name, line)`` and
    ``unparsed`` holds ``(line, raw_text)`` for data rows that sit inside a
    matrix but do not yield an agent name. Line numbers are 1-based. A matrix
    runs from a ``| Agent |`` header through the first line that does not start
    with a pipe.

    Unparsed rows are returned rather than skipped. Skipping them is what let a
    backtick-wrapped phantom name survive an earlier version of this check: the
    file still produced other rows, so no gap was visible and the run passed.
    """
    rows: list[tuple[str, int]] = []
    unparsed: list[tuple[int, str]] = []
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
            elif not TABLE_SEPARATOR.match(lines[cursor]):
                unparsed.append((cursor + 1, lines[cursor]))
            cursor += 1
        index = cursor
    return rows, unparsed


def has_matrix_header(text: str) -> bool:
    """Report whether ``text`` contains a matrix header line at all."""
    return any(MATRIX_HEADER.match(line) for line in text.splitlines())


def scan(repo_root: Path) -> ScanResult:
    """Scan every configured tree for matrix citations and structural gaps.

    Each citation is tagged with the tree that carries it so existence can be
    resolved against that tree's own roster rather than a repository-wide one.
    """
    result = ScanResult()
    for tree, suffix in AGENT_TREES:
        directory = repo_root / tree
        if not directory.is_dir():
            continue
        result.trees_scanned.append(tree)
        agents = known_agents(directory, suffix)
        result.agents_by_tree[tree] = agents
        if not agents:
            result.empty_trees.append(tree)
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if not has_matrix_header(text):
                continue
            relative = path.relative_to(repo_root)
            result.files_with_matrix.append(relative)
            rows, unparsed = parse_matrix_rows(text)
            for line, raw in unparsed:
                result.unparsed_rows.append((relative, line, raw))
            if not rows:
                result.parse_gaps.append(relative)
                continue
            for name, line in rows:
                result.citations.append(Citation(name, relative, line, tree))
    return result


def violations(result: ScanResult) -> list[Citation]:
    """Return citations naming an agent their own tree does not ship.

    Resolution is per tree. A name present in one install and absent from
    another is a violation in the install that lacks it, because the plugin
    roots ship standalone and a routing row cannot reach outside its own root.
    """
    return sorted(
        (
            c
            for c in result.citations
            if c.name not in result.agents_by_tree.get(c.tree, set())
        ),
        key=lambda c: (c.name, str(c.path), c.line),
    )


def report(result: ScanResult, bad: list[Citation]) -> None:
    """Print a human-readable summary of the scan."""
    print("=== Agent Capability Matrix Reference Validation ===")
    print()
    print(f"Trees scanned:          {len(result.trees_scanned)}")
    for tree in result.trees_scanned:
        print(f"  {str(tree) + ':':26s} {len(result.agents_by_tree.get(tree, ())):3d} agents")
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
        print("OK: every agent named in a capability matrix ships in the tree that cites it.")
        return

    print(f"VIOLATIONS: {len(bad)} matrix row(s) name an agent their own tree does not ship")
    print()
    for citation in bad:
        print(
            f"  {citation.path}:{citation.line}: '{citation.name}' is not shipped "
            f"in {citation.tree}"
        )
    print()
    print(
        "A delegation naming an agent the install does not carry fails silently "
        "and the work is skipped. Either ship the agent in every tree that cites "
        "it, or remove the row. If the capability moved to a skill, say so in "
        "prose instead of leaving a routing row. Remember that .claude/, "
        "src/claude/, and src/copilot-cli/ install standalone, so a row cannot "
        "reach an agent that lives only in a sibling root."
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

    result = scan(repo_root)
    if not any(result.agents_by_tree.values()):
        print(
            "CONFIG ERROR: no configured tree yields any agent file. Every "
            "citation would resolve against an empty roster, so the run proves "
            "nothing. Check AGENT_TREES and the per-tree filename suffixes.",
            file=sys.stderr,
        )
        return 2

    bad = violations(result)
    report(result, bad)

    if bad or result.degeneracy():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
