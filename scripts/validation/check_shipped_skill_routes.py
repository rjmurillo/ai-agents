#!/usr/bin/env python3
"""Cross-tree routing gate: a shipped tree must contain the skills it routes to.

Why this exists
---------------

Skills are generated from ``.claude/skills`` into per-platform plugin trees,
but the platform config may deliberately drop one. ``templates/platforms/
copilot-cli.yaml`` excludes ``merge-resolver`` from the Copilot shipping set
because that skill is hard-wired to this repository's layout and is useless in
a consumer repo (issue #2026).

Dropping the skill and keeping the prose that routes to it are two separate
edits. Only the first one was made. ``autoplan`` shipped a routing table row
reading ``Skill: merge-resolver`` inside a tree that no longer contained
``merge-resolver``, so a consumer who installed the toolkit and hit a merge
conflict was routed to a skill that was not there. Every existing gate passed:
the packaging change was internally consistent, and the routing table was
byte-identical to its canonical source, which is correct on Claude.

That is coordination drift. The packaging control plane and the routing
control plane each stayed self-consistent while disagreeing about what is
reachable. This module makes the disagreement fail loudly.

The invariant
-------------

For every shipped tree, each ``Skill: <name>`` route in a skill body must
resolve to ``<tree>/skills/<name>/SKILL.md``.

Precision
---------

A bare ``Skill: <word>`` regex over prose produces false positives. The real
one in this tree is a checklist item reading ``Skill: create
`.claude/skills/NAME/tests/...``` where ``create`` is an English verb, not a
route.

The filter: only report a name that exists as a skill in the canonical tree.
That is exactly the drift signature this gate is for, a skill that the
canonical tree has and the shipped tree dropped while keeping the reference.
An unknown name is either prose or a typo, which is a different defect class
and not worth the false-positive rate that catching it here would cost.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CANONICAL_TREE = Path(".claude")
SHIPPED_TREES = (Path("src/copilot-cli"),)

# Rejects a leading backtick or word character so an inline-code span such as
# `Skill: x` and a compound word such as MetaSkill: do not match.
_ROUTE_RE = re.compile(r"(?<![`\w])Skill:\s*([a-z0-9][a-z0-9-]{2,})")

_FENCE_RE = re.compile(r"^\s*(```|~~~)")

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2


@dataclass(frozen=True)
class Finding:
    tree: str
    path: str
    line: int
    skill: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}: routes to 'Skill: {self.skill}' but "
            f"{self.tree}/skills/{self.skill}/SKILL.md does not exist"
        )


def skill_names(tree: Path) -> set[str]:
    """Return the skill directory names that have a SKILL.md in ``tree``."""
    skills_dir = tree / "skills"
    if not skills_dir.is_dir():
        return set()
    return {p.parent.name for p in skills_dir.glob("*/SKILL.md")}


def strip_fenced_blocks(text: str) -> list[tuple[int, str]]:
    """Yield ``(line_number, line)`` for lines outside fenced code blocks.

    Routing prose lives in tables. Fenced blocks hold example payloads and
    shell transcripts, where a ``Skill:`` string is illustrative rather than a
    live route.
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((number, line))
    return out


def scan_tree(tree: Path, canonical: set[str], root: Path) -> list[Finding]:
    present = skill_names(tree)
    relative_tree = tree.relative_to(root).as_posix()
    findings: list[Finding] = []
    for path in sorted((tree / "skills").rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in strip_fenced_blocks(text):
            for name in _ROUTE_RE.findall(line):
                if name in present:
                    continue
                if name not in canonical:
                    # Prose or typo. See the Precision note in the docstring.
                    continue
                findings.append(
                    Finding(
                        tree=relative_tree,
                        path=path.relative_to(root).as_posix(),
                        line=number,
                        skill=name,
                    )
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root

    canonical = skill_names(root / CANONICAL_TREE)
    if not canonical:
        print(
            f"[FAIL] no skills found under {CANONICAL_TREE}/skills; wrong --root?",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    findings: list[Finding] = []
    for tree in SHIPPED_TREES:
        absolute = root / tree
        if not absolute.is_dir():
            print(f"[FAIL] shipped tree missing: {tree}", file=sys.stderr)
            return EXIT_CONFIG
        findings.extend(scan_tree(absolute, canonical, root))

    if findings:
        print("[FAIL] shipped trees route to skills they do not contain:")
        for finding in findings:
            print(f"  {finding.render()}")
        print(
            "\nEither ship the skill, or change the route. When a skill is "
            "excluded\nfrom a platform on purpose, route to the agent instead: "
            'Task(subagent_type="<name>")\ntranslates per harness and resolves '
            "in both trees."
        )
        return EXIT_DRIFT

    print(f"[PASS] all Skill: routes resolve in {len(SHIPPED_TREES)} shipped tree(s)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
