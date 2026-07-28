#!/usr/bin/env python3
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
an earlier revision matched only lowercase names and was blind to the live
``Skill: SkillForge`` route.

A cell may list several skills, as ``Skill: analyze, Skill: context-gather``
does today, so a captured name is stripped of trailing sentence, quotation and
bracket punctuation before it is resolved. A name that is still not a legal
skill identifier after that, ``Skill: known/ghost`` for instance, is reported as
malformed rather than silently truncated to its leading segment and resolved
against a real skill.

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
only a name, as in ``Skill: `x` ``, is part of the route. That policy lives
here rather than in the shared parser, which reports structure and decides
nothing.

Known limitation: a route written outside a table, say as a bullet reading
``- Skill: foo``, is not checked. That is a deliberate trade. Every one of the
17 live routes per root is a table cell, and the non-table ``Skill:`` hits are
all prose: five example headings in ``SkillForge/references/evolution-scoring
.md`` and one checklist item where ``create`` is an English verb. None of them
names a real skill. If routing outside tables ever becomes a real authoring
pattern, widen the scope here and expect to pay for it in false positives.

Walk discipline
---------------

Plugin roots are discovered from a bounded candidate set, the repository-root
``.claude`` plus the direct children of ``src/``, and not from a recursive glob
for ``.claude-plugin/plugin.json``. This repository keeps full working copies
under ``.cache/worktrees/``, ``.claude/worktrees/`` and ``.wt/``, so a recursive
glob matches dozens of throwaway roots and reports findings in trees nobody is
shipping. For the same reason the per-root walk prunes those directory names at
the walk root, which keeps the whole check near 2.8s instead of ~11s.

Vacuity is checked per root, not on the repository-wide route total. A root
that ships skills and yields no routes has gone dark, and summing across roots
would let a sibling's routes hide that.

Every way this check can fail to see a file is an error, not a pass: an
unreadable directory, an unreadable file, undecodable bytes, a root the process
cannot stat or list, a symlinked directory ``os.walk`` will not descend into,
and input the markdown parser cannot fully represent all exit 2. ``Path.is_file``
and ``Path.is_dir`` are not used for discovery because they answer False for a
path they cannot stat, which drops a whole plugin root and leaves its siblings
to carry the pass. A gate that fails open is worse than no gate, because it
also reports success.
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

from scripts.utils.markdown_parser import TableCell, iter_table_cell_text

CANONICAL_ROOT_NAME = ".claude"
PLATFORM_PARENT = Path("src")
PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"

# Full working copies of this repository live under these directory names.
# Descending into them multiplies the walk and reports drift in throwaway trees.
PRUNED_DIRS = frozenset(
    {"worktrees", "node_modules", ".git", ".venv", "venv", "__pycache__"}
)

# Captures whatever follows ``Skill:`` up to whitespace, so a malformed name is
# seen rather than silently truncated to its leading legal segment. The
# lookbehind rejects a compound word such as MetaSkill:. Matching is
# case-sensitive on the keyword but not on the name: the live tree routes to
# ``Skill: SkillForge``. The lookbehind rejects a compound word or a path
# segment, so ``Meta-Skill:``, ``Task/Skill:`` and ``docs\Skill:`` are prose
# rather than routes. The live tree carries 148 such compound forms.
_ROUTE_RE = re.compile(r"(?<![\w./\\-])Skill:\s*(\S+)?")

# A legal skill directory name.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Sentence, list and quotation punctuation that can trail a name in a prose
# cell. None of these is legal inside a name, so stripping them cannot mask a
# real drift; leaving them on turns a resolvable route into a false malformed
# report that blocks the push.
_TRAILING = ",;.:!?)]}\"'”’…"

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
    """Return the skill directory names that have a SKILL.md in ``root``."""
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return set()
    return {p.parent.name for p in skills_dir.glob("*/SKILL.md")}


def _present(path: Path, *, directory: bool) -> bool:
    """Return whether ``path`` exists and is of the requested kind.

    ``Path.is_dir`` and ``Path.is_file`` answer False for a path the process
    cannot stat, which would silently drop a plugin root from the scan and
    leave the remaining roots to carry a pass. Only a genuinely absent path
    is False here. Anything else is a config error, matching the fail-closed
    posture the walk and the decode already take.
    """
    try:
        info = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as exc:
        raise CheckError(f"cannot stat {path}: {exc}") from exc
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)


def discover_roots(repo_root: Path) -> list[Path]:
    """Return plugin roots from a bounded candidate set.

    Deliberately not a recursive glob. See the Walk discipline note above.
    """
    candidates = [repo_root / CANONICAL_ROOT_NAME]
    platform_parent = repo_root / PLATFORM_PARENT
    if _present(platform_parent, directory=True):
        try:
            children = sorted(platform_parent.iterdir())
        except OSError as exc:
            raise CheckError(f"cannot list {platform_parent}: {exc}") from exc
        candidates.extend(p for p in children if _present(p, directory=True))
    return [c for c in candidates if _present(c / PLUGIN_MANIFEST, directory=False)]


def iter_markdown(root: Path) -> Iterator[Path]:
    """Yield markdown files under ``root``, pruning nested working copies.

    Pruning applies at the walk root only. Measured over the live repository,
    root-level pruning and all-depth pruning yield the identical 906 files at
    the identical speed, because every nested copy sits under ``<root>/
    worktrees`` and is unreachable once that one directory is pruned. Scoping
    the prune to the root removes the failure mode where a real skill named
    ``worktrees`` or a content directory named ``venv`` is skipped and the
    routes inside it are never checked.

    A directory the walk cannot read raises rather than being skipped:
    ``os.walk`` swallows those by default, which would silently shrink the
    scan.
    """

    def fail(exc: OSError) -> None:
        raise CheckError(f"cannot walk {exc.filename}: {exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=fail):
        current = Path(dirpath)
        if current == root:
            dirnames[:] = [d for d in dirnames if d not in PRUNED_DIRS]
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

    A code span that itself carries a whole route, as in `` `Skill: x` ``, is
    documentation showing the syntax and must not be read as a route. A code
    span that only styles the name, as in ``Skill: `x` ``, is a route and its
    content belongs in the text. Testing the span against the route pattern
    keeps one definition of what a route looks like. Blanking preserves the
    surrounding offsets so no two spans are accidentally joined.
    """
    return "".join(
        " " * len(segment.content)
        if segment.code and _ROUTE_RE.search(segment.content)
        else segment.content
        for segment in cell.segments
    )


def route_names(text: str) -> Iterator[tuple[int, str, bool]]:
    """Yield ``(line, name, is_legal)`` for every ``Skill:`` route in a table.

    Table scope is resolved by the CommonMark parser. A malformed name is
    yielded with ``is_legal`` false rather than dropped, so it is reported
    instead of passing as a route nobody validated.
    """
    for cell in iter_table_cell_text(text):
        for match in _ROUTE_RE.finditer(_cell_text(cell)):
            raw = (match.group(1) or "").rstrip(_TRAILING)
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
