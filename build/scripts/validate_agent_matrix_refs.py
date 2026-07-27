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
``.github/agents``.

Suffix stripping alone is NOT enough to decide what is an agent. In the trees
whose suffix is a bare ``.md`` it admits any sibling markdown file, and a second
adversarial review showed ``src/claude/claude-instructions.template.md`` entering
the roster as an agent named ``claude-instructions.template``, so a matrix row
citing that name passed. An uppercase-stem filter did not help, because the
filename is lowercase. Membership is therefore decided by content: a file counts
as an agent only when it opens with a YAML frontmatter block carrying a
``description:`` key. Both fences must be complete lines: a substring search for
``\n---`` accepted ``---not-a-closing-fence`` and admitted a malformed document
as an agent. Measured across all six trees that rule keeps all 175 agent
files and excludes exactly four suffix-matching sibling documents:
``.claude/agents/AGENTS.md``, ``.claude/agents/CLAUDE.md``,
``src/claude/AGENTS.md``, and ``src/claude/claude-instructions.template.md``. It
also fully subsumes the uppercase-stem filter it replaced.

GFM RENDERS A TABLE INDENTED UP TO THREE SPACES. Every table pattern here
therefore tolerates that indent. Anchoring them at column zero made an indented
matrix invisible to the scan while a reader still saw a rendered table, which the
same adversarial review used to hide a phantom row and get a clean exit. Four
spaces is an indented code block, so the patterns stop there, and the
continuation pattern uses the same tolerance as the row pattern so an
over-indented line ends the table instead of being reported as a parse gap.

GFM ALSO MAKES THE OUTER PIPES OPTIONAL, and a later review hid a phantom row in
a table written ``Agent | Focus`` with no leading pipe. The header and row
patterns therefore treat the leading pipe as optional. That is safe because the
alignment row is REQUIRED for a table to open: a bare ``| Agent |`` line in prose
renders as text, not as routing, and the row pattern is only ever applied inside
a table that a header and an alignment row have already established.

FENCED CODE BLOCKS ARE SKIPPED. A fenced example showing the matrix format
renders as code, and the same review appended one to an agent to make the
validator fail on an illustrative row citing an agent that does not exist. The
fence walk is shared by the row parser and the has-a-matrix test so a file cannot
be recorded as carrying a matrix and then reported as a parse gap for a table
that never rendered.

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
that rule would fire on correct repositories.

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
# header is the marker; downstream columns vary per matrix. Bold, italic, and
# backticks are tolerated because a header reformat must not silently drop a
# whole table from the scan: an adversarial review hid a phantom row behind
# ``| **Agent** |`` and the stricter pattern reported success.
#
# GitHub Flavored Markdown allows a block to be indented up to three spaces and
# still render as a table, so every pattern here tolerates that indentation. A
# review demonstrated a two-space indented matrix carrying a phantom row that the
# column-zero patterns could not see at all.
#
# The leading pipe is optional because GFM makes it optional. A later review hid
# a phantom row in a table written ``Agent | Focus`` with no leading pipe, which
# GitHub renders as a table and the pipe-anchored pattern could not see.
MATRIX_HEADER = re.compile(
    r"^ {0,3}\|?\s*(\*{1,3}|_{1,3})?\s*`?Agent`?\s*(?(1)\1)\s*\|",
    re.IGNORECASE,
)

# ``|-------|---------|`` alignment row directly under a header, with the outer
# pipes optional. GFM requires this row for a table to render at all, so it is
# what promotes a bare ``| Agent |`` line into a table rather than prose. Cells
# must be real alignment cells: ``[\s:|-]+`` also matched a row of stray colons.
TABLE_SEPARATOR = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")

# Any line that continues a table body: a non-blank line, indented no more than
# the table itself, carrying at least one cell separator. A matrix runs until the
# first line that does not match this.
TABLE_LINE = re.compile(r"^ {0,3}\S[^\n]*\|")

# A fenced code block opener or closer. Content inside a fence renders as code,
# not as a table, so a documentation example of the matrix format must not be
# enforced as routing. A review appended a fenced example matrix to an agent and
# the validator failed the run on the example's illustrative row.
CODE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

# ``| **implementer** | ... |``, ``| implementer | ... |``,
# ``| `implementer` | ... |``, or ``| *implementer* | ... |``. Agent names are
# lowercase kebab-case. Emphasis and backticks are optional: the orchestrator
# matrix bolds the name, the per-category tables in ``AGENTS.md`` do not, and
# either could gain code or italic formatting in a reformat. The ``| Agent |``
# header is what establishes that column one holds an agent name, so every one of
# those spellings is in scope and none is a false positive. A row inside a matrix
# that matches none of them is not ignored; it is reported as a parse gap.
#
# The closing delimiter is a conditional backreference rather than a second
# independent optional group, because underscore is a legal name character. With
# an independent closing group, ``__implementer__`` parsed as an agent literally
# named ``implementer__``: the opening ``__`` was consumed as emphasis and the
# closing ``__`` was swallowed by the name. The backreference also rejects
# asymmetric emphasis such as ``*name**``, which does not render as emphasis
# either. Three delimiters are allowed because ``***name***`` renders as bold
# italic.
#
# The leading pipe is optional for the same reason it is optional in the header.
# The pattern is only applied inside a table already established by a header and
# an alignment row, so the optional pipe cannot reach ordinary prose.
MATRIX_ROW = re.compile(
    r"^ {0,3}\|?\s*(\*{1,3}|_{1,3})?\s*`?([a-z0-9][a-z0-9._-]*)`?\s*(?(1)\1)\s*\|"
)

# A frontmatter key every agent definition carries, in every tree. Presence of a
# frontmatter block containing this key is what separates an agent from a sibling
# document that happens to share the tree's filename suffix.
FRONTMATTER_DESCRIPTION = re.compile(r"^description:", re.MULTILINE)

# The closing delimiter of a frontmatter block, which must be a line holding
# nothing but three hyphens. Searching for the substring ``\n---`` instead
# accepted ``---not-a-closing-fence``, which let a malformed document present
# itself as an agent.
FRONTMATTER_CLOSE = re.compile(r"^---[ \t]*$", re.MULTILINE)


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
        elif not any(path.is_relative_to(CANONICAL_TREE) for path in self.files_with_matrix):
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


def is_agent_definition(path: Path) -> bool:
    """Report whether ``path`` is an agent definition rather than a sibling doc.

    An agent opens with a YAML frontmatter block carrying a ``description:``
    key. Filename suffix alone cannot decide this: in the trees whose suffix is
    a bare ``.md`` it admits any sibling markdown file, which is how
    ``claude-instructions.template.md`` became a citable agent name.

    Both fences are required and the key must be anchored to the start of a line
    inside the block. Without the opening fence a body-level ``---`` horizontal
    rule turns any prose above it into a pseudo-block; without the anchor a key
    such as ``x-description:`` satisfies the check. The closing fence must be a
    line holding nothing but three hyphens: a substring search for ``\n---``
    accepted ``---not-a-closing-fence`` and admitted a malformed document.

    A directory or a dangling symlink raises ``OSError`` from ``read_text``, so
    no separate ``is_file`` guard is needed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if not text.startswith("---\n"):
        return False
    close = FRONTMATTER_CLOSE.search(text, 4)
    if close is None:
        return False
    return bool(FRONTMATTER_DESCRIPTION.search(text[4 : close.start()]))


def known_agents(tree_root: Path, suffix: str) -> set[str]:
    """Return the agent names one tree ships, by stripping ``suffix``.

    Files not ending in ``suffix`` are not agent definitions and are excluded.
    So are files that carry the suffix but no agent frontmatter, which is what
    keeps ``AGENTS.md``, ``CLAUDE.md``, and ``claude-instructions.template.md``
    out of the roster.
    """
    names: set[str] = set()
    for path in tree_root.glob(f"*{suffix}"):
        name = path.name[: -len(suffix)]
        if name and is_agent_definition(path):
            names.add(name)
    return names


def _closes_fence(opener: str, line: str) -> bool:
    """Report whether ``line`` closes a code fence opened by ``opener``.

    A closing fence uses the same character, runs at least as long, and carries
    no info string.
    """
    match = CODE_FENCE.match(line)
    if match is None:
        return False
    run = match.group(1)
    return run[0] == opener[0] and len(run) >= len(opener) and not match.group(2).strip()


def parse_matrix_rows(text: str) -> tuple[list[tuple[str, int]], list[tuple[int, str]]]:
    """Split every matrix in ``text`` into parsed rows and unparsed rows.

    Returns ``(rows, unparsed)`` where ``rows`` holds ``(agent_name, line)`` and
    ``unparsed`` holds ``(line, raw_text)`` for data rows that sit inside a
    matrix but do not yield an agent name. Line numbers are 1-based. A matrix
    runs from a ``| Agent |`` header and its alignment row through the first line
    that does not continue the table.

    The alignment row is required, not merely tolerated, because GFM requires it
    for a table to render. Without it a stray ``| Agent |`` line in prose opens a
    table that does not exist on the rendered page.

    Fenced code blocks are skipped. A documentation example showing the matrix
    format renders as code, not as routing, and enforcing its illustrative rows
    fails the run on a table no agent will ever consult.

    Unparsed rows are returned rather than skipped. Skipping them is what let a
    backtick-wrapped phantom name survive an earlier version of this check: the
    file still produced other rows, so no gap was visible and the run passed.
    """
    rows: list[tuple[str, int]] = []
    unparsed: list[tuple[int, str]] = []
    lines = text.splitlines()
    index = 0
    open_fence: str | None = None
    while index < len(lines):
        line = lines[index]
        if open_fence is not None:
            if _closes_fence(open_fence, line):
                open_fence = None
            index += 1
            continue
        fence = CODE_FENCE.match(line)
        if fence:
            open_fence = fence.group(1)
            index += 1
            continue
        separator_follows = index + 1 < len(lines) and TABLE_SEPARATOR.match(lines[index + 1])
        if not (MATRIX_HEADER.match(line) and separator_follows):
            index += 1
            continue
        cursor = index + 2
        while cursor < len(lines) and TABLE_LINE.match(lines[cursor]):
            match = MATRIX_ROW.match(lines[cursor])
            if match:
                rows.append((match.group(2), cursor + 1))
            elif not TABLE_SEPARATOR.match(lines[cursor]):
                unparsed.append((cursor + 1, lines[cursor]))
            cursor += 1
        index = cursor
    return rows, unparsed


def has_matrix_header(text: str) -> bool:
    """Report whether ``text`` contains a matrix header that opens a real table.

    A header alone does not open a table: GFM requires the alignment row, and a
    header inside a fenced example is code rather than routing. This mirrors
    ``parse_matrix_rows`` so a file cannot be recorded as carrying a matrix and
    then reported as a parse gap for a table that never rendered.
    """
    lines = text.splitlines()
    open_fence: str | None = None
    for index, line in enumerate(lines):
        if open_fence is not None:
            if _closes_fence(open_fence, line):
                open_fence = None
            continue
        fence = CODE_FENCE.match(line)
        if fence:
            open_fence = fence.group(1)
            continue
        if MATRIX_HEADER.match(line):
            following = lines[index + 1] if index + 1 < len(lines) else ""
            if TABLE_SEPARATOR.match(following):
                return True
    return False


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
        (c for c in result.citations if c.name not in result.agents_by_tree.get(c.tree, set())),
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
