#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: this file is 304 lines of code carrying
# roughly 230 lines of prose. Each paragraph records which defect made a rule
# exist, and most of them were found by adversarial review rather than by
# reasoning, so the rationale is not reconstructable from the code. The two
# concerns here, deciding what text is a route and deciding which files to
# read, would split cleanly, but the split is driven by a count measured
# mostly on prose: it would put the fail-open story that justifies balanced
# unwrapping in a different file from the balance test itself. The executable
# core is well inside every threshold the same lint applies to functions.
# Revisit if the code, not the prose, approaches the limit.
"""Routing gate: a plugin root must contain every skill its tables route to.

Why this exists
---------------

Skills are generated from ``.claude/skills`` into per-platform plugin roots,
but a platform config may deliberately drop one. ``templates/platforms/
copilot-cli.yaml`` excludes ``merge-resolver`` from the Copilot shipping set
because that skill is hard-wired to this repository's layout and is useless in
a consumer repo (issue #2026).

Dropping the skill and keeping the prose that routes to it are two separate
edits. Only the first one was made. ``autoplan`` shipped a routing table row
reading ``Skill: merge-resolver`` inside a root that no longer contained
``merge-resolver``, so a consumer who installed the toolkit and hit a merge
conflict was routed to a skill that was not there. Every existing gate passed:
the packaging change was internally consistent, and the routing table was
byte-identical to its canonical source, which is correct on Claude.

That is coordination drift. The packaging control plane and the routing
control plane each stayed self-consistent while disagreeing about what is
reachable. This module makes the disagreement fail loudly.

The invariant
-------------

The check is symmetric across roots: for every plugin root, each ``Skill:
<name>`` route in that root's markdown must resolve to
``<root>/skills/<name>/SKILL.md``. A root is responsible for its own routes.
There is no canonical allowlist, so a route naming a skill that exists nowhere
(a typo) fails in exactly the same way as one naming a skill that was dropped
during packaging.

Precision comes from parsing, not from an allowlist
---------------------------------------------------

A bare ``Skill: <word>`` regex over prose produces false positives: heading
text in authoring documentation, and a checklist item reading ``Skill: create
`.claude/skills/NAME/tests/...``` where ``create`` is an English verb.

Routing lives in markdown tables by construction, so the scan is restricted to
table cells, where a ``Skill:`` token is a route and nothing else. That scope
is resolved by the CommonMark parser in ``scripts/utils/markdown_parser.py``,
not by matching pipe-shaped lines. A line-based approximation is wrong in both
directions: it misses tables written without outer pipes, inside a blockquote,
or indented under a list item, and it matches pipe-shaped prose that renders as
a paragraph for want of a delimiter row. Parsing also excludes fenced and
indented code and HTML comments for free, since none of them parse as a table.

Scoping this way is what makes the no-allowlist invariant affordable, which in
turn is what lets the gate catch typos. It also removes a case-sensitivity trap:
an earlier revision matched only lowercase names and was blind to a
mixed-case name such as ``Skill: SkillForge``.

A cell may list several skills, as ``Skill: analyze, Skill: context-gather``
does today, so a captured name is unwrapped before it is resolved: balanced
wrapper pairs are stripped, and so is trailing sentence punctuation, the two
alternating so ``Skill: (autoplan).`` reduces fully. Balance is the load-bearing
part. Blindly stripping any leading bracket turns a malformed name into a legal
one, so ``Skill: ((autoplan`` would resolve to an installed skill and report a
pass over text nobody wrote deliberately. Closing punctuation is stripped
unconditionally because a cell can carry only the closing half, as in
``[Skill: autoplan]`` where the capture starts at the name. A name that is
still not a legal skill identifier after unwrapping, ``Skill: known/ghost`` for
instance, is reported as malformed rather than silently truncated to its
leading segment and resolved against a real skill.

The keyword must stand alone. ``Meta-Skill:`` and ``Task/Skill:`` are prose,
and the live tree carries 148 of them.

Rendering is the contract, not source bytes
-------------------------------------------

A consumer reads the rendered document, so the gate reads the rendered
document. An earlier revision skipped any file whose raw bytes lacked the
literal word ``Skill``, which cut the run from 2.8s to 1.3s and looked free.
``Sk&#105;ll: ghost`` renders as a route, carries no literal keyword, and
passed silently. There is no source-text prefilter.

The same rule decides what a code span means. ``markdown_parser`` yields each
cell as segments tagged code or text; a span carrying a whole route, as in
`` `Skill: x` ``, is documentation showing the syntax, while a span carrying
only a name, as in ``Skill: `x` ``, is part of the route. A span carrying the
bare keyword is decided by what follows it in the cell: `` `Skill:` `` alone
documents the keyword, while `` `Skill:` x `` styles the label of a real route
whose name sits outside the span. Backticks around the keyword never change
the verdict for what follows, which is the point: if they did, an author could
silence a drift report with two punctuation marks. That policy lives here
rather than in the shared parser, which reports structure and decides nothing.

Known limitation: a route written outside a table, say as a bullet reading
``- Skill: foo``, is not checked. That is a deliberate trade. Every one of the
17 live routes per root is a table cell, and the non-table ``Skill:`` hits are
all prose: five example headings in ``skillforge/references/evolution-scoring
.md`` and one checklist item where ``create`` is an English verb. None of them
names a real skill. If routing outside tables ever becomes a real authoring
pattern, widen the scope here and expect to pay for it in false positives.

A second limitation runs the other way. A route inside a raw HTML ``<code>``
tag in a table cell is read as a route, because the parser marks
``code_inline`` tokens and not ``html_inline`` ones. That is the fail-closed
direction: a documentation example reads as drift rather than a real route
going unchecked, and the author's workaround is one backtick. No table cell in
the three plugin roots contains a ``<code>`` tag. Closing it would mean
teaching a markdown parser several gates share to track HTML token depth,
which adds a fail-open path to shared code to serve zero present occurrences.

A third limitation is that a cell holding two keywords with ambiguous text
between them, ``Skill: (some text) Skill: autoplan``, reports the first as a
malformed route. Rendered, that text does read as a route to ``(some text)``,
so the report is the fail-closed default rather than a code-span defect: the
plain and backticked spellings of that cell return the same exit code, which
is the property that stops backticks from becoming a way to silence a report.

A fourth is that ``_NAME_RE`` accepts a trailing dot that ``_unwrap`` always
strips, so a skill directory named ``my.skill.`` could never be routed to.
Tightening the pattern to forbid a trailing dot costs more than it saves: the
obvious form, requiring the last character to be alphanumeric, rejects every
one-character skill name. A directory whose name ends in a period is
pathological and none exists in any root, while ``Skill: autoplan.`` ending a
sentence is ordinary and has to keep working.

Walk discipline
---------------

Plugin roots are discovered from a bounded candidate set, the repository-root
``.claude`` plus the direct children of ``src/``, and not from a recursive glob
for ``.claude-plugin/plugin.json``. This repository keeps full working copies
under ``.cache/worktrees/``, ``.claude/worktrees/`` and ``.wt/``, so a recursive
glob matches dozens of throwaway roots and reports findings in trees nobody is
shipping. For the same reason the per-root walk prunes those directory names,
which keeps the whole check near 2.8s instead of ~11s.

Pruning is by name at every depth, exempting a directory directly under
``<root>/skills`` that carries a ``SKILL.md``. Pruning only at the walk root
left ``node_modules`` and ``.venv`` inside a skill in the scan, which reads
third-party prose as drift and trips the symlink refusal on the interpreter
links every virtualenv carries, blocking every push in the repository. Pruning
at every depth without an exemption hides a real skill whose name collides with
a tooling name. Exempting the whole skills namespace by location was too broad,
because a ``.venv`` created there is a direct child too and brings the same
interpreter links back. The marker is what separates the two: it is the same
question ``skill_names`` asks, so a directory cannot count as a skill in one
place and as tooling in the other. Measured on the live repository the rule
yields the same 906 files as the root-only rule at the same speed.

Vacuity is checked per root, not on the repository-wide route total. A root
that ships skills and yields no routes has gone dark, and summing across roots
would let a sibling's routes hide that.

Every way this check can fail to see a file is an error, not a pass: an
unreadable directory, an unreadable file, undecodable bytes, a root the process
cannot stat or list, a path that exists with the wrong kind, a symlinked plugin
root or a symlinked directory inside one, and input the markdown parser cannot
fully represent all exit 2. ``Path.is_file`` and ``Path.is_dir`` are not used
for discovery because they answer False for a path they cannot stat, which
drops a whole plugin root and leaves its siblings to carry the pass. A gate
that fails open is worse than no gate, because it also reports success.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils.markdown_parser import CellSegment, TableCell, iter_table_cell_text

CANONICAL_ROOT_NAME = ".claude"
PLATFORM_PARENT = Path("src")
PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"
# What makes a directory a skill. Both the skill inventory and the walk's
# pruning exemption ask that question, and they have to answer it the same
# way or a directory counts as a skill in one place and as tooling in the
# other.
SKILL_FILE = "SKILL.md"

# Full working copies of this repository live under these directory names.
# Descending into them multiplies the walk and reports drift in throwaway trees.
PRUNED_DIRS = frozenset(
    {"worktrees", "node_modules", ".git", ".venv", "venv", "__pycache__"}
)

# Captures whatever follows ``Skill:`` up to whitespace, so a malformed name is
# seen rather than silently truncated to its leading legal segment. The
# lookbehind rejects a compound word such as MetaSkill:. Matching is
# case-sensitive on the keyword but not on the name, so a mixed-case name
# such as ``Skill: SkillForge`` is captured rather than dropped. The
# lookbehind rejects a compound word or a path
# segment, so ``Meta-Skill:``, ``Task/Skill:`` and ``docs\Skill:`` are prose
# rather than routes. The live tree carries 148 such compound forms.
_ROUTE_RE = re.compile(r"(?<![\w./\\-])Skill:\s*(\S+)?")

# A legal skill directory name.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Wrapper pairs that can enclose a name in a prose cell. Unwrapping is
# balanced: an opener is stripped only when its own closer is at the other
# end. Stripping an unmatched opener turns a malformed name into a legal one,
# so ``Skill: ((merge-resolver`` would resolve to an installed skill and mask
# real drift.
_PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "“": "”", "‘": "’"}

# Sentence and list punctuation that can trail a name. None of it is legal
# inside a name, so stripping it cannot mask a real drift; leaving it on turns
# a resolvable route into a false malformed report that blocks the push.
_TRAILING = ",;.:!?\"'”’…"

# Bracket pairs, the subset of ``_PAIRS`` that nests unambiguously. A cell can
# carry only the closing half of one, as in ``[Skill: merge-resolver]`` where
# the capture starts at the name, so a trailing closer has to be strippable.
# Stripping it unconditionally is fail-open: ``Skill: (merge-resolver])``
# reduces to an installed skill through a balanced strip followed by a blind
# one. A closer is therefore stripped only when something before the route
# opened it.
_BRACKETS = {"(": ")", "[": "]", "{": "}"}


def _awaited_closers(before: str) -> list[str]:
    """Return the closers still owed by brackets opened before a route.

    Outermost first, which is the order they arrive in when a captured name is
    stripped from its right end: ``[see (Skill: autoplan)]`` captures
    ``autoplan)]``, whose last character closes the outer bracket.

    Quotes are excluded because the same character opens and closes them, so
    nesting cannot be read from the text.
    """
    stack: list[str] = []
    for char in before:
        closer = _BRACKETS.get(char)
        if closer is not None:
            stack.append(closer)
        elif stack and char == stack[-1]:
            stack.pop()
    return stack


def _unwrap(raw: str, awaited: list[str] | None = None) -> str:
    """Strip balanced wrappers and trailing punctuation from a captured name.

    Alternates the two so a wrapper closed by a sentence, ``(autoplan).``,
    reduces fully, while an unmatched opener survives to be reported.
    ``awaited`` carries the closers owed by brackets opened before the route,
    outermost first, and each is spent as it is consumed, so a cell opening
    one bracket cannot justify stripping two.
    """
    owed = list(awaited or ())
    while raw:
        if len(raw) > 1 and _PAIRS.get(raw[0]) == raw[-1]:
            raw = raw[1:-1]
        elif owed and raw[-1] == owed[0]:
            raw = raw[:-1]
            owed.pop(0)
        elif raw[-1] in _TRAILING:
            raw = raw[:-1]
        else:
            break
    return raw


EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2


@dataclass(frozen=True)
class Finding:
    root: str
    path: str
    line: int
    skill: str
    legal: bool = True

    def render(self) -> str:
        if not self.legal:
            shown = self.skill or "(empty)"
            return (
                f"{self.path}:{self.line}: routes to 'Skill: {shown}' which is "
                "not a legal skill name"
            )
        return (
            f"{self.path}:{self.line}: routes to 'Skill: {self.skill}' but "
            f"{self.root}/skills/{self.skill}/SKILL.md does not exist"
        )


class CheckError(Exception):
    """A condition that makes the result untrustworthy rather than a finding."""


def skill_names(root: Path) -> set[str]:
    """Return the skill directory names that have a SKILL.md in ``root``.

    Each marker is checked with ``_present`` rather than trusted from the
    glob, because a glob lists a broken symlink the same as a real file. The
    walk's pruning exemption asks the same question through the same call, so
    a directory cannot count as a skill here and as tooling there.
    """
    skills_dir = root / "skills"
    if not _present(skills_dir, directory=True):
        return set()
    return {
        marker.parent.name
        for marker in skills_dir.glob(f"*/{SKILL_FILE}")
        if _present(marker, directory=False)
    }


def _stat_mode(path: Path) -> int | None:
    """Return ``path``'s st_mode, or None when it is genuinely absent.

    One fail-closed stat policy for the whole module. ``Path.is_dir`` and
    ``Path.is_file`` answer False for a path the process cannot stat, which
    would silently drop a plugin root from the scan and leave the remaining
    roots to carry a pass. Only a genuinely absent path is None here.
    Anything else raises, matching the posture the walk and the decode take.

    A broken symlink raises rather than reading as absent. The link is a
    deliberate statement that something should be there, so treating it as
    nothing drops whatever it named: a broken manifest link removes a whole
    plugin root from discovery and lets the surviving roots report a pass.
    """
    try:
        return path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError) as exc:
        if os.path.islink(path):
            raise CheckError(f"cannot resolve symlink {path}: {exc}") from exc
        return None
    except OSError as exc:
        raise CheckError(f"cannot stat {path}: {exc}") from exc


def _present(path: Path, *, directory: bool) -> bool:
    """Return whether a path the caller requires exists, asserting its kind.

    For paths whose kind is part of the contract: a manifest must be a file,
    a skills namespace must be a directory. A path that exists with the wrong
    kind is a malformed root, not an absent one, so it raises rather than
    reporting absence and dropping that root from the scan unnoticed.

    Use ``_is_directory`` instead when a non-directory is an ordinary answer
    rather than a contract violation, as when sifting candidates out of a
    directory that also holds files.
    """
    mode = _stat_mode(path)
    if mode is None:
        return False
    if directory and not stat.S_ISDIR(mode):
        raise CheckError(f"{path} exists but is not a directory")
    if not directory and not stat.S_ISREG(mode):
        raise CheckError(f"{path} exists but is not a regular file")
    return True


def _is_directory(path: Path) -> bool:
    """Return whether ``path`` is a directory, without asserting it must be.

    Shares the fail-closed stat above, so an unreadable candidate still
    raises rather than being sifted out unnoticed.
    """
    mode = _stat_mode(path)
    return mode is not None and stat.S_ISDIR(mode)


def discover_roots(repo_root: Path) -> list[Path]:
    """Return plugin roots from a bounded candidate set.

    Deliberately not a recursive glob. See the Walk discipline note above.
    """
    candidates = [repo_root / CANONICAL_ROOT_NAME]
    platform_parent = repo_root / PLATFORM_PARENT
    if _is_directory(platform_parent):
        try:
            children = sorted(platform_parent.iterdir())
        except OSError as exc:
            raise CheckError(f"cannot list {platform_parent}: {exc}") from exc
        candidates.extend(p for p in children if _is_directory(p))
    return [c for c in candidates if _present(c / PLUGIN_MANIFEST, directory=False)]


def iter_markdown(root: Path) -> Iterator[Path]:
    """Yield markdown files under ``root``, pruning nested working copies.

    Pruning is by name at every depth, exempting a directory directly under
    ``<root>/skills`` that has a ``SKILL.md``. That is the same definition of
    a skill ``skill_names`` uses, so a real skill whose name collides with a
    tooling name is scanned while a real virtualenv sitting in the skills
    namespace is not. Exempting the whole namespace by location was too broad:
    a ``.venv`` created there is a direct child too, and its interpreter
    symlinks trip the refusal below. Pruning only at the walk root was too
    narrow: a ``node_modules`` inside a skill was scanned, which reads
    third-party prose as drift and trips the same refusal.

    A directory the walk cannot read raises rather than being skipped:
    ``os.walk`` swallows those by default, which would silently shrink the
    scan.
    """

    def fail(exc: OSError) -> None:
        raise CheckError(f"cannot walk {exc.filename}: {exc}")

    if root.is_symlink():
        # The refusal below covers directories found during the walk, but
        # os.walk follows its own starting path, so a symlinked root would
        # slip past the policy it states.
        raise CheckError(
            f"{root.name} is a symlinked plugin root; its markdown cannot be "
            "scanned under the same policy as the rest of the tree. Replace "
            "it with a real directory."
        )
    skills_dir = root / "skills"
    for dirpath, dirnames, filenames in os.walk(root, onerror=fail):
        current = Path(dirpath)

        def keep(name: str, here: Path = current) -> bool:
            if name not in PRUNED_DIRS:
                return True
            return here == skills_dir and _present(here / name / SKILL_FILE, directory=False)

        dirnames[:] = [d for d in dirnames if keep(d)]
        for name in dirnames:
            if (current / name).is_symlink():
                # os.walk does not descend into a symlinked directory, so its
                # markdown would go unscanned and a drifted route inside it
                # would pass. followlinks=True is the other option and is
                # worse: a cycle costs dozens of redundant walks before the
                # OS symlink limit stops it, and one file reachable two ways
                # is reported twice. No plugin root ships one today.
                raise CheckError(
                    f"{(current / name).relative_to(root.parent)} is a "
                    "symlinked directory inside a plugin root; its markdown "
                    "cannot be scanned. Replace it with a real directory."
                )
        for name in sorted(filenames):
            if name.endswith(".md"):
                yield Path(dirpath) / name


def _cell_text(cell: TableCell) -> str:
    """Return a cell's text with syntax-illustrating code spans blanked.

    A code span that carries a whole route, as in `` `Skill: x` ``, is
    documentation showing the syntax and must not be read as a route. A code
    span that only styles the name, as in ``Skill: `x` ``, is a route and its
    content belongs in the text. Testing the span against the route pattern
    keeps one definition of what a route looks like. Blanking preserves the
    surrounding offsets so no two spans are accidentally joined.

    A span carrying the bare keyword is decided by what follows it in the
    cell, because the name group is optional and the pattern therefore matches
    either shape. In `` `Skill:` x `` the span styles the label of a real
    route whose name sits outside it, and blanking would delete the keyword
    and hide the route. A `` `Skill:` `` with nothing after it is documenting
    the keyword and is blanked like any other syntax example.

    The forward read skips later spans that are themselves whole routes. Those
    are documentation and get blanked, so letting one satisfy the bare span
    would keep a keyword whose only name is about to be erased, and the cell
    would report an empty malformed route.
    """

    def documents_a_route(segment: CellSegment) -> bool:
        if not segment.code:
            return False
        match = _ROUTE_RE.search(segment.content)
        return match is not None and bool(match.group(1))

    survives = [
        "" if documents_a_route(segment) else segment.content
        for segment in cell.segments
    ]

    def blanked(index: int, segment: CellSegment) -> str:
        if not segment.code:
            return segment.content
        match = _ROUTE_RE.search(segment.content)
        if match is None:
            return segment.content
        if not match.group(1):
            trailing = "".join(survives[index + 1 :])
            carried = _ROUTE_RE.search(segment.content + trailing)
            if carried is not None and carried.group(1):
                return segment.content
        return " " * len(segment.content)

    return "".join(blanked(index, s) for index, s in enumerate(cell.segments))


def route_names(text: str) -> Iterator[tuple[int, str, bool]]:
    """Yield ``(line, name, is_legal)`` for every ``Skill:`` route in a table.

    Table scope is resolved by the CommonMark parser. A malformed name is
    yielded with ``is_legal`` false rather than dropped, so it is reported
    instead of passing as a route nobody validated.
    """
    for cell in iter_table_cell_text(text):
        rendered = _cell_text(cell)
        for match in _ROUTE_RE.finditer(rendered):
            awaited = _awaited_closers(rendered[: match.start()])
            raw = _unwrap(match.group(1) or "", awaited)
            yield cell.line, raw, bool(raw) and bool(_NAME_RE.match(raw))


def scan_root(root: Path, repo_root: Path) -> tuple[list[Finding], int]:
    """Return ``(findings, routes_seen)`` for one plugin root."""
    present = skill_names(root)
    relative_root = root.relative_to(repo_root).as_posix()
    findings: list[Finding] = []
    seen = 0
    for path in iter_markdown(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            # Failing open here would let an unreadable file hide a live route.
            raise CheckError(f"cannot read {path}: {exc}") from exc
        except UnicodeDecodeError as exc:
            # errors="replace" would silently corrupt a route into a pass.
            raise CheckError(f"cannot decode {path}: {exc}") from exc
        try:
            found = list(route_names(text))
        except CheckError:
            raise
        except Exception as exc:
            # A file the parser cannot fully represent is an incomplete scan.
            raise CheckError(f"cannot parse {path}: {exc}") from exc
        for number, name, legal in found:
            seen += 1
            if legal and name in present:
                continue
            findings.append(
                Finding(
                    root=relative_root,
                    path=path.relative_to(repo_root).as_posix(),
                    line=number,
                    skill=name,
                    legal=legal,
                )
            )
    if present and seen == 0:
        # A root that ships skills also ships the tables that route to them.
        # Checking this per root rather than on the repository-wide total is
        # what stops one root from going dark while a sibling's routes keep
        # the total above zero and the gate reporting success. Roots that ship
        # no skills at all, such as src/claude, are exempt by construction.
        raise CheckError(
            f"{relative_root} ships {len(present)} skill(s) but no 'Skill:' "
            "route was found in it; the scan matched nothing and a pass "
            "for this root would be vacuous"
        )
    return findings, seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.root

    findings: list[Finding] = []
    total_routes = 0
    try:
        roots = discover_roots(repo_root)
        if not roots:
            print(
                f"[FAIL] no plugin roots found under {repo_root}; wrong --root?",
                file=sys.stderr,
            )
            return EXIT_CONFIG
        for root in roots:
            root_findings, seen = scan_root(root, repo_root)
            findings.extend(root_findings)
            total_routes += seen
    except CheckError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if total_routes == 0:
        # Every populated root carries routing tables. Zero means the walk
        # found nothing, so a pass here would be vacuous.
        print(
            "[FAIL] no 'Skill:' routes found in any plugin root; "
            "the scan matched nothing and a pass would be vacuous",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    if findings:
        print("[FAIL] plugin roots route to skills they do not contain:")
        for finding in findings:
            print(f"  {finding.render()}")
        print(
            "\nEither ship the skill, or change the route. When a skill is "
            "excluded\nfrom a platform on purpose, route to the agent instead: "
            'Task(subagent_type="<name>")\ntranslates per harness and resolves '
            "in both trees."
        )
        return EXIT_DRIFT

    print(
        f"[PASS] {total_routes} Skill: route(s) resolve across "
        f"{len(roots)} plugin root(s)"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
