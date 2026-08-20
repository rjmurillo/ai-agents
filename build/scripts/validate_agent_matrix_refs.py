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
``.github/agents``. When an agent file also carries a frontmatter ``name`` key,
that value must match the filename-derived name. Dispatch hosts read the
frontmatter name, while this validator resolves matrix rows against filenames;
letting those drift makes the validator and host disagree about the same file.

Suffix stripping alone is NOT enough to decide what is an agent. In the trees
whose suffix is a bare ``.md`` it admits any sibling markdown file, and a second
adversarial review showed ``src/claude/claude-instructions.template.md`` entering
the roster as an agent named ``claude-instructions.template``, so a matrix row
citing that name passed. An uppercase-stem filter did not help, because the
filename is lowercase. Membership is therefore decided by content: a file counts
as an agent only when it opens with a YAML frontmatter block carrying a
non-empty string ``description:`` key. Both fences must be complete lines: a
substring search for ``\n---`` accepted ``---not-a-closing-fence`` and admitted
a malformed document as an agent. Measured across all six trees that rule keeps
all 175 agent files and excludes exactly four suffix-matching sibling documents:
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

A CONFIGURED TREE THAT IS ABSENT FROM THE CHECKOUT IS A CONFIGURATION ERROR, not
a tree to skip. ``scan`` still tolerates a missing directory so tests can build
partial fixtures, but ``main`` refuses to run. The distinction matters because
the two gates that execute this code fire on different paths: the workflow that
runs this script covers every agent tree, while the workflow that runs the test
suite fires only on Python changes. A markdown-only deletion of an agent tree
therefore reaches the script without ever reaching the test, and a citation into
the deleted tree would pass by omission.

The guard deliberately does not require every scanned tree to carry a matrix. A
tree holding only agent definitions and no routing table is a valid state, so
that rule would fire on correct repositories.

EXIT CODES. This script uses the 0-2 subset of the 0-4 contract in
.agents/architecture/ADR-035-exit-code-standardization.md. Codes 3 (external
service error) and 4 (authentication error) are unreachable here, not
redefined: the scan reads local files only and makes no network or
authenticated call.
  0 - Success: every cited agent name resolves within its own tree
  1 - Violations found, or the scan degenerated (no matrices, or a parse gap)
  2 - Configuration error: a configured tree is absent, or no tree yields agents
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

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

# Agent names are lowercase kebab-case. A first-column cell inside a matrix that
# does not match this is not ignored; it is reported as a parse gap, because a
# malformed row is exactly how a phantom name hid from an earlier version.
AGENT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# The first-column header that marks a table as a capability matrix.
MATRIX_HEADER_CELL = "agent"

# A CommonMark parser with the GFM table extension, which is what GitHub renders.
#
# This replaced roughly a hundred and twenty lines of hand-written regex that
# approximated the same grammar and disagreed with the rendered page in four
# separate ways found by review: a fenced example nested in a list item was
# enforced as routing, a fence opener whose info string contained a backtick hid
# a real table, a blockquote or heading after a table was recorded as a broken
# row, and a delimiter row whose cell count did not match the header opened a
# table that GitHub renders as a setext heading. Each was a separate patch to the
# regex. The library already implements the specification the patches were
# converging on, and ``markdown-it-py`` is a declared dependency of this project.
#
# The ``linkify`` rule of the ``gfm-like`` preset needs ``linkify-it-py``, which
# is not a dependency, so the table plugin is enabled on the CommonMark preset
# instead. Link autodetection has no bearing on table structure.
MARKDOWN = MarkdownIt("commonmark").enable("table")

# A frontmatter key every agent definition carries as a non-empty string, in
# every tree. Presence of a valid frontmatter block with this key separates an
# agent from a sibling document sharing the tree's filename suffix.
FRONTMATTER_KEY = "description"

# The opening delimiter, anchored at the first byte. Anchoring is what stops a
# body-level ``---`` horizontal rule from turning the prose above it into a
# pseudo-block. Trailing spaces are tolerated because the closing fence already
# tolerates them, and rejecting them here reported a real agent as missing.
# A fourth hyphen still fails: ``----`` is not the frontmatter convention.
FRONTMATTER_OPEN = re.compile(r"---[ \t]*\n")

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


@dataclass(frozen=True)
class NameMismatch:
    """An agent file whose frontmatter name disagrees with its filename."""

    path: Path
    tree: Path
    filename_name: str
    frontmatter_name: str


@dataclass
class ScanResult:
    """Outcome of a full repository scan."""

    citations: list[Citation] = field(default_factory=list)
    files_with_matrix: list[Path] = field(default_factory=list)
    parse_gaps: list[Path] = field(default_factory=list)
    unparsed_rows: list[tuple[Path, int, str]] = field(default_factory=list)
    name_mismatches: list[NameMismatch] = field(default_factory=list)
    config_errors: list[str] = field(default_factory=list)
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
                "no capability matrix found in any scanned tree; either the "
                f"first-column header is no longer {MATRIX_HEADER_CELL!r} or "
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


class DuplicateFrontmatterKey(yaml.YAMLError):
    """Raised when frontmatter carries the agent key more than once.

    PyYAML keeps the last occurrence and reports nothing, so ``description``
    written twice loads as the second value with no signal that the first was
    discarded. A stricter reader rejects the document outright, which means the
    validator and the host disagree about a file that ships.

    Subclassing ``YAMLError`` keeps every existing caller correct: a handler
    that treats a parse failure as "not an agent" already catches this. Callers
    that want the detail catch this class first. Line numbers are zero-based and
    relative to the frontmatter block, not the file; the caller owns the offset
    because only it knows where the block starts.
    """

    def __init__(self, key: str, first_line: int, second_line: int) -> None:
        super().__init__(f"frontmatter repeats the {key!r} key")
        self.key = key
        self.first_line = first_line
        self.second_line = second_line


class FrontmatterLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that refuses YAML alias references.

    ``safe_load`` blocks arbitrary object construction but not resource
    exhaustion. ``SafeConstructor.flatten_mapping`` expands a merge key by
    copying every entry of the mapping it references, so a chain of merge keys
    that each reference the previous level nine times multiplies the entry count
    by nine per level. A 433 byte frontmatter block held this scan for 21
    seconds; two further levels reach half an hour. The validator runs on
    ``pull_request``, so a fork supplies that file.

    Anchors are harmless on their own, and a merge key cannot amplify without an
    alias to reference, so refusing the alias closes the amplification with one
    override. ``ComposerError`` is a ``YAMLError``, which the caller already
    treats as "not an agent", so a file using aliases drops out of the roster.
    That fails closed: a matrix citing such a file reports an unknown agent
    rather than passing silently. No agent ships frontmatter that uses anchors,
    aliases, or merge keys, so nothing legitimate is excluded.
    """

    def compose_node(self, parent: yaml.Node | None, index: int | yaml.Node | None) -> yaml.Node:
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()
            raise yaml.composer.ComposerError(
                None,
                None,
                "alias references are not allowed in agent frontmatter",
                event.start_mark,
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        """Reject a repeated agent key before PyYAML silently collapses it.

        Only ``FRONTMATTER_KEY`` is checked. Repeating any key is sloppy, but
        that key alone decides whether the file counts as a shipping agent, so
        it is the only one whose duplication makes the validator disagree with
        the host. Checking every key would also fire on sibling documents that
        are not agents at all, which turns a targeted signal into noise.

        The scan runs before ``super()`` so it reads the keys as written. The
        base implementation calls ``flatten_mapping`` first, which rewrites
        ``node.value`` when a merge key is present and would hide the original
        pairs.
        """
        first_seen: int | None = None
        for key_node, _ in node.value:
            if getattr(key_node, "value", None) != FRONTMATTER_KEY:
                continue
            if first_seen is not None:
                raise DuplicateFrontmatterKey(
                    FRONTMATTER_KEY, first_seen, key_node.start_mark.line
                )
            first_seen = key_node.start_mark.line
        mapping: dict[Any, Any] = super().construct_mapping(node, deep)
        return mapping


def agent_frontmatter(path: Path, reasons: list[str] | None = None) -> dict[str, object] | None:
    """Return parsed agent frontmatter for ``path``, or ``None`` when absent.

    The caller decides what to do with optional keys. This helper only answers
    whether the file is an agent definition by requiring a loadable mapping with
    a usable ``description`` key.

    Both fences are required, and the opening fence must sit at the first byte.
    Without that anchor a body-level ``---`` horizontal rule turns any prose
    above it into a pseudo-block. Each fence tolerates trailing spaces and
    neither tolerates a fourth hyphen. The closing fence must otherwise be a
    line holding nothing but three hyphens: a substring search for ``\n---``
    accepted ``---not-a-closing-fence`` and admitted a malformed document.

    The block is parsed as YAML rather than pattern matched. A textual search for
    the key reported success on ``description: [``, which no host can load, so a
    document that cannot be an agent anywhere still supplied a citable name. The
    parsed result must be a mapping with a non-empty string description: a null
    or duplicate description disagrees with stricter hosts and therefore must
    not enter the roster.

    A directory or a dangling symlink raises ``OSError`` from ``read_text``, so
    no separate ``is_file`` guard is needed.

    ``reasons`` collects why a file that looked like an agent was refused. Only
    the two shapes a host rejects are recorded: a ``description`` that is not a
    non-empty string, and the key written twice. Every other refusal means the
    file was never an agent, which is the normal case for a sibling document and
    is not worth reporting. Entries carry no path prefix; the caller owns how
    the file is named because only it knows the root to display against.

    Validation lives here rather than in ``is_agent_definition`` so that every
    caller reading frontmatter gets the same answer. Splitting the parse from
    the checks let a file be refused as an agent by one caller and read for its
    ``name`` by another.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    if not (opened := FRONTMATTER_OPEN.match(text)):
        return None
    close = FRONTMATTER_CLOSE.search(text, opened.end())
    if close is None:
        return None
    try:
        block = yaml.load(text[opened.end() : close.start()], Loader=FrontmatterLoader)
    except DuplicateFrontmatterKey as exc:
        # Marks are zero-based within the block, and the block starts on the
        # line after the opening fence, so file line = mark + 2.
        _record(
            reasons,
            f"frontmatter repeats the {exc.key!r} key at lines "
            f"{exc.first_line + 2} and {exc.second_line + 2}; PyYAML keeps the "
            "last value and a stricter reader rejects the file outright",
        )
        return None
    except yaml.YAMLError:
        return None
    if not isinstance(block, dict) or FRONTMATTER_KEY not in block:
        return None
    value = block[FRONTMATTER_KEY]
    if not isinstance(value, str) or not value.strip():
        _record(
            reasons,
            f"frontmatter {FRONTMATTER_KEY!r} must be a non-empty string, "
            f"found {_describe(value)}; an agent with no dispatch text is "
            "rejected by every host",
        )
        return None
    return block


def is_agent_definition(path: Path, reasons: list[str] | None = None) -> bool:
    """Report whether ``path`` is an agent definition rather than a sibling doc.

    An agent opens with a YAML frontmatter block carrying a ``description:``
    key. Filename suffix alone cannot decide this: in the trees whose suffix is
    a bare ``.md`` it admits any sibling markdown file, which is how
    ``claude-instructions.template.md`` became a citable agent name.

    See ``agent_frontmatter`` for the parse rules and for what ``reasons``
    collects.
    """
    return agent_frontmatter(path, reasons) is not None


def _record(reasons: list[str] | None, message: str) -> None:
    """Append ``message`` when the caller asked for reasons."""
    if reasons is not None:
        reasons.append(message)


def _describe(value: object) -> str:
    """Name the offending value without quoting a payload of unknown size."""
    if value is None:
        return "null"
    if isinstance(value, str):
        return "a blank string"
    name = type(value).__name__
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}"


def known_agents(
    tree_root: Path, suffix: str, problems: list[str] | None = None, repo_root: Path | None = None
) -> set[str]:
    """Return the agent names one tree ships, by stripping ``suffix``.

    Files not ending in ``suffix`` are not agent definitions and are excluded.
    So are files that carry the suffix but no agent frontmatter, which is what
    keeps ``AGENTS.md``, ``CLAUDE.md``, and ``claude-instructions.template.md``
    out of the roster.

    ``problems`` collects path-prefixed reasons for files that looked like
    agents and were refused. Without it such a file drops out silently and the
    only symptom is a matrix row reporting an agent nobody ships, which points
    at the citation rather than at the malformed definition.
    """
    names: set[str] = set()
    for path in sorted(tree_root.glob(f"*{suffix}")):
        name = path.name[: -len(suffix)]
        if not name:
            continue
        reasons: list[str] = []
        if is_agent_definition(path, reasons):
            names.add(name)
        if problems is None:
            continue
        shown = path.relative_to(repo_root) if repo_root else path
        problems.extend(f"{shown}: {reason}" for reason in reasons)
    return names


def nested_agent_definitions(
    tree_root: Path, suffix: str, repo_root: Path | None = None
) -> list[str]:
    """Return nested files that carry agent frontmatter, as reportable strings.

    Every host contract in this repository names the flat form:
    ``.claude/agents/*.md`` and ``.github/agents/*.agent.md`` (ADR-003,
    ADR-036, ADR-057, ADR-080). :func:`known_agents` matches that with a
    non-recursive glob, so a definition placed one directory down loads in no
    host and appears in no roster. Without this check the only symptom is a
    matrix row reporting a phantom, which points at the citation instead of at
    the misplaced file (issue #3601).

    Subdirectories that hold sidecar prose stay silent. ``agents/security/
    references/`` already ships three such files, and they carry no agent
    frontmatter, so requiring frontmatter is what separates a misplaced agent
    from reference material.

    A file whose frontmatter is BROKEN is reported too, under its own message.
    Gating solely on :func:`is_agent_definition` left a hole that both the
    ``critic`` and ``independent-thinker`` passes on PR #5177 found
    independently: a malformed nested file is not a definition, so it was
    skipped here, and the test-side corpus never sees it because
    ``_agent_files`` globs each tree non-recursively. It therefore escaped this
    guard, the fail-closed corpus guard, tree discovery, and all three role
    consumers at once.

    Broken means the file opens a fence and the block does not yield a YAML
    mapping: unclosed, unparseable, or a scalar. A well-formed mapping that
    simply carries no ``description`` stays silent, because that is a sidecar
    note and not a botched agent. Splitting on brokenness rather than on the
    presence of a fence is what keeps ``references/notes.md`` silent while
    catching the unbalanced-quote case.
    """
    found: list[str] = []
    for path in sorted(tree_root.rglob(f"*{suffix}")):
        if path.parent == tree_root:
            continue
        if not path.name[: -len(suffix)]:
            continue
        shown = path.relative_to(repo_root) if repo_root else path
        tree_shown = tree_root.relative_to(repo_root) if repo_root else tree_root
        if not is_agent_definition(path):
            if _frontmatter_is_broken(path):
                found.append(
                    f"{shown}: file in a subdirectory opens a frontmatter block "
                    f"that does not parse. A broken agent is invisible to every "
                    f"role guard, so fix the frontmatter and move it to "
                    f"{tree_shown.as_posix()}/*{suffix}, or drop the opening "
                    f"fence if it is reference material."
                )
            continue
        found.append(
            f"{shown}: agent definition in a subdirectory. Hosts load only the "
            f"flat form {tree_shown.as_posix()}/*{suffix}; move it up one level."
        )
    return found


def _frontmatter_is_broken(path: Path) -> bool:
    """Report whether ``path`` opens a frontmatter block that does not parse.

    Answers True only for a file that declares frontmatter and then fails to
    produce a YAML mapping from it. A file with no opening fence answers False
    (it is prose), and so does one whose block loads cleanly but carries no
    ``description`` (it is a sidecar note).

    The fence rules are :func:`agent_frontmatter`'s, deliberately: a helper that
    disagreed with it about where a block starts would report files that
    function correctly, or miss ones that do not. Unreadable files answer False
    because this helper only escalates a refusal that already happened, and an
    unreadable file is not evidence of an intended definition.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False
    if not (opened := FRONTMATTER_OPEN.match(text)):
        return False
    close = FRONTMATTER_CLOSE.search(text, opened.end())
    if close is None:
        return True
    try:
        block = yaml.load(text[opened.end() : close.start()], Loader=FrontmatterLoader)
    except (DuplicateFrontmatterKey, yaml.YAMLError):
        return True
    return not isinstance(block, dict)


def frontmatter_name_mismatches(repo_root: Path, tree: Path, suffix: str) -> list[NameMismatch]:
    """Return agent files whose optional frontmatter name disagrees with filename."""
    mismatches: list[NameMismatch] = []
    directory = repo_root / tree
    for path in sorted(directory.glob(f"*{suffix}")):
        filename_name = path.name[: -len(suffix)]
        if not filename_name:
            continue
        frontmatter = agent_frontmatter(path)
        if frontmatter is None or "name" not in frontmatter:
            continue
        raw_name = frontmatter["name"]
        frontmatter_name = raw_name.strip() if isinstance(raw_name, str) else repr(raw_name)
        if frontmatter_name != filename_name:
            mismatches.append(
                NameMismatch(
                    path=path.relative_to(repo_root),
                    tree=tree,
                    filename_name=filename_name,
                    frontmatter_name=frontmatter_name,
                )
            )
    return mismatches


def _cell_text(inline: Token) -> str:
    """Return the plain text of one table cell, with formatting removed.

    ``**memory**``, ```memory```, and ``memory`` all yield ``memory``. The parser
    has already resolved emphasis and code spans into their own tokens, so the
    delimiters never reach this string. Hand-written patterns had to enumerate
    the spellings, and an asymmetric one such as ``*name**`` was a live defect.
    """
    return "".join(
        child.content for child in (inline.children or []) if child.type in ("text", "code_inline")
    ).strip()


class ParserInvariantError(RuntimeError):
    """The parser emitted a token stream this module does not know how to read."""


def _first_cell(tokens: list[Token], row_open: int) -> tuple[int, Token]:
    """Return the index of the row's closing token and its first cell.

    Every cell the parser emits carries an inline token, empty ones included, so
    a row always has a first cell. Measured against 69,847 rows in 3,106 files
    plus rows built to hold nothing, no row ever lacked one. The invariant is
    stated rather than worked around: a version that broke it would otherwise
    turn every row of every matrix into an unparsed row, and the run would blame
    the documents for a change in the parser.
    """
    cursor = row_open + 1
    first: Token | None = None
    while cursor < len(tokens) and tokens[cursor].type != "tr_close":
        if tokens[cursor].type == "inline" and first is None:
            first = tokens[cursor]
        cursor += 1
    if first is None:
        raise ParserInvariantError(
            f"table row at token {row_open} holds no cell; "
            "the markdown parser no longer emits an inline token per cell"
        )
    return cursor, first


def _one_table(
    tokens: list[Token], table_open: int
) -> tuple[int, str | None, list[tuple[Token, Token]]]:
    """Walk one table, returning its closing index, header cell, and body rows."""
    in_header = False
    header: str | None = None
    body: list[tuple[Token, Token]] = []
    cursor = table_open + 1
    while cursor < len(tokens) and tokens[cursor].type != "table_close":
        token = tokens[cursor]
        if token.type == "thead_open":
            in_header = True
        elif token.type == "thead_close":
            in_header = False
        elif token.type == "tr_open":
            cursor, first = _first_cell(tokens, cursor)
            if in_header:
                header = _cell_text(first)
            else:
                body.append((token, first))
        cursor += 1
    return cursor, header, body


def _matrices(text: str) -> list[list[tuple[Token, Token]]]:
    """Return the body rows of every capability matrix in ``text``.

    A table qualifies when its header's first cell reads ``Agent``. A matrix with
    a header and no body rows is returned as an empty list, which is how a real
    but empty table stays distinguishable from a document with no table at all.

    Both callers share this walk. Two independent walks would eventually
    disagree, and a file recorded as carrying a matrix from which zero rows parse
    fails the run as a parse gap.
    """
    tokens = MARKDOWN.parse(text)
    matrices: list[list[tuple[Token, Token]]] = []
    index = 0
    while index < len(tokens):
        if tokens[index].type != "table_open":
            index += 1
            continue
        index, header, body = _one_table(tokens, index)
        if header is not None and header.lower() == MATRIX_HEADER_CELL:
            matrices.append(body)
        index += 1
    return matrices


def parse_matrix_rows(text: str) -> tuple[list[tuple[str, int]], list[tuple[int, str]]]:
    """Split every matrix in ``text`` into parsed rows and unparsed rows.

    Returns ``(rows, unparsed)`` where ``rows`` holds ``(agent_name, line)`` and
    ``unparsed`` holds ``(line, raw_text)`` for body rows that sit inside a
    matrix but do not yield an agent name. Line numbers are 1-based.

    Structure comes from the CommonMark parser, so a table is recognised exactly
    when GitHub renders one. Fenced examples, tables nested in a list item or a
    blockquote, delimiter rows whose cell count disagrees with the header, and
    the block constructs that terminate a table are all the parser's problem
    rather than this module's.

    Unparsed rows are reported rather than skipped. Skipping them is what let a
    malformed phantom row survive an earlier version of this check: the file
    still produced other rows, so no gap was visible and the run passed.
    """
    rows: list[tuple[str, int]] = []
    unparsed: list[tuple[int, str]] = []
    source = text.splitlines()
    for body in _matrices(text):
        for row_open, first in body:
            line = (row_open.map[0] + 1) if row_open.map else 0
            name = _cell_text(first)
            if AGENT_NAME.match(name):
                rows.append((name, line))
            else:
                raw = source[line - 1] if 0 < line <= len(source) else name
                unparsed.append((line, raw))
    return rows, unparsed


def has_matrix_header(text: str) -> bool:
    """Report whether ``text`` contains a capability matrix that actually renders."""
    return bool(_matrices(text))


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
        agents = known_agents(directory, suffix, result.config_errors, repo_root)
        result.config_errors.extend(nested_agent_definitions(directory, suffix, repo_root))
        result.agents_by_tree[tree] = agents
        result.name_mismatches.extend(frontmatter_name_mismatches(repo_root, tree, suffix))
        if not agents:
            result.empty_trees.append(tree)
        for path in sorted(directory.glob("*.md")):
            relative = path.relative_to(repo_root)
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                result.config_errors.append(f"{relative}: cannot read markdown file: {exc}")
                continue
            if not has_matrix_header(text):
                continue
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

    if not bad and not result.name_mismatches and not degeneracy:
        print("OK: every agent named in a capability matrix ships in the tree that cites it.")
        return

    if result.name_mismatches:
        print(
            "FRONTMATTER NAME MISMATCHES: "
            f"{len(result.name_mismatches)} agent file(s) have a name that differs "
            "from the filename"
        )
        print()
        for mismatch in result.name_mismatches:
            print(
                f"  {mismatch.path}: frontmatter name {mismatch.frontmatter_name!r} "
                f"does not match filename-derived name {mismatch.filename_name!r} "
                f"in {mismatch.tree}"
            )
        print()

    if not bad:
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

    missing = [tree for tree, _ in AGENT_TREES if not (repo_root / tree).is_dir()]
    if missing:
        print(
            "CONFIG ERROR: configured agent tree(s) absent from the checkout: "
            + ", ".join(str(tree) for tree in missing)
            + ". A tree that is not scanned cannot be checked, so a citation "
            "into it would pass by omission. Either restore the tree or remove "
            "it from AGENT_TREES.",
            file=sys.stderr,
        )
        return 2

    result = scan(repo_root)
    if result.config_errors:
        for error in result.config_errors:
            print(f"CONFIG ERROR: {error}", file=sys.stderr)
        return 2

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

    if bad or result.name_mismatches or result.degeneracy():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
