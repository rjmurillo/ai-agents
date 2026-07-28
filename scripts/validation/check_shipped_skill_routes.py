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

Precision comes from structure, not from an allowlist
-----------------------------------------------------

A bare ``Skill: <word>`` regex over prose produces false positives: heading
text in authoring documentation, and a checklist item reading ``Skill: create
`.claude/skills/NAME/tests/...``` where ``create`` is an English verb.

Restricting the scan to markdown table rows removes all of them. Routing lives
in tables by construction, so inside a table cell a ``Skill:`` token is a route
and nothing else. Measured over both populated roots, table scoping finds every
real route (17 per root) and zero false positives, while an unscoped scan of
the same content reports six prose hits per root.

Scoping this way is what makes the no-allowlist invariant affordable, which in
turn is what lets the gate catch typos. It also removes a case-sensitivity trap:
an earlier revision matched only lowercase names and was blind to the live
``Skill: SkillForge`` route.

Known limitation: a route written outside a table, say as a bullet reading
``- Skill: foo``, is not checked. That is a deliberate trade. Every one of the
17 live routes per root is a table row, and the non-table ``Skill:`` hits are
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
shipping. For the same reason the per-root walk prunes those directory names in
place rather than filtering after the fact: pruning during the walk keeps the
whole check at ~0.1s instead of ~11s.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

CANONICAL_ROOT_NAME = ".claude"
PLATFORM_PARENT = Path("src")
PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"

# Full working copies of this repository live under these directory names.
# Descending into them multiplies the walk and reports drift in throwaway trees.
PRUNED_DIRS = frozenset(
    {"worktrees", "node_modules", ".git", ".venv", "venv", "__pycache__"}
)

# A markdown table row: up to three leading spaces (four would make it an
# indented code block), a leading pipe, and a trailing pipe. Restricting the
# route scan to these lines is what keeps the no-allowlist invariant clean.
_TABLE_ROW_RE = re.compile(r"^\s{0,3}\|.*\|\s*$")

# Rejects a leading backtick or word character so an inline-code span such as
# `Skill: x` and a compound word such as MetaSkill: do not match. The name is
# deliberately case-insensitive: the live tree routes to `Skill: SkillForge`.
_ROUTE_RE = re.compile(r"(?<![`\w])Skill:\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

# CommonMark fence: up to three leading spaces, then three or more backticks or
# tildes. The closing fence must use the same character and be at least as long,
# so a nested or longer fence does not terminate the block early.
_FENCE_RE = re.compile(r"^\s{0,3}(?P<delim>`{3,}|~{3,})")

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2


@dataclass(frozen=True)
class Finding:
    root: str
    path: str
    line: int
    skill: str

    def render(self) -> str:
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


def discover_roots(repo_root: Path) -> list[Path]:
    """Return plugin roots from a bounded candidate set.

    Deliberately not a recursive glob. See the Walk discipline note above.
    """
    candidates = [repo_root / CANONICAL_ROOT_NAME]
    platform_parent = repo_root / PLATFORM_PARENT
    if platform_parent.is_dir():
        candidates.extend(sorted(p for p in platform_parent.iterdir() if p.is_dir()))
    return [c for c in candidates if (c / PLUGIN_MANIFEST).is_file()]


def iter_markdown(root: Path) -> Iterator[Path]:
    """Yield markdown files under ``root``, pruning nested working copies."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIRS]
        for name in sorted(filenames):
            if name.endswith(".md"):
                yield Path(dirpath) / name


def route_lines(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, line)`` for table rows eligible for route scanning.

    Excludes fenced code blocks, which hold example payloads and transcripts
    where a routing table is illustrative rather than live, and HTML comments,
    which are not rendered and therefore route nobody.
    """
    # Blank the body of each comment while preserving line count so reported
    # line numbers stay accurate.
    text = _HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)

    out: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FENCE_RE.match(line)
        if match:
            delim = match.group("delim")
            if fence is None:
                fence = delim
                continue
            # Same character and at least as long closes the block.
            if delim[0] == fence[0] and len(delim) >= len(fence):
                fence = None
            continue
        if fence is None and _TABLE_ROW_RE.match(line):
            out.append((number, line))
    return out


def scan_root(root: Path, repo_root: Path) -> tuple[list[Finding], int]:
    """Return ``(findings, routes_seen)`` for one plugin root."""
    present = skill_names(root)
    relative_root = root.relative_to(repo_root).as_posix()
    findings: list[Finding] = []
    seen = 0
    for path in iter_markdown(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # Failing open here would let an unreadable file hide a live route.
            raise CheckError(f"cannot read {path}: {exc}") from exc
        for number, line in route_lines(text):
            for name in _ROUTE_RE.findall(line):
                seen += 1
                if name in present:
                    continue
                findings.append(
                    Finding(
                        root=relative_root,
                        path=path.relative_to(repo_root).as_posix(),
                        line=number,
                        skill=name,
                    )
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

    roots = discover_roots(repo_root)
    if not roots:
        print(
            f"[FAIL] no plugin roots found under {repo_root}; wrong --root?",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    findings: list[Finding] = []
    total_routes = 0
    try:
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
