#!/usr/bin/env python3
"""Fail when a shipped Codex or Muse file names a Claude-only tool as a bare call.

Issue #7226, part 3. The Codex and Muse plugin trees copy skill bodies from
``src/claude/skills`` almost verbatim. Neither host registers a ``Task`` tool or
an ``AskUserQuestion`` tool: Codex spawns agents with ``spawn_agent`` and asks
with ``request_user_input`` (Plan mode only); Muse Code spawns with
``subagent_spawn``. A skill line that tells the model to call ``Task(...)`` or
``AskUserQuestion`` with no other host named sends it to a tool that does not
exist.

What counts as a violation, per line, in every file under ``src/codex`` and
``src/muse``:

* ``Task(`` at a word boundary. ``RunnableTask(`` and ``_Task(`` do not count.
  Code fences are scanned too: a fenced ``Task(subagent_type=...)`` block is a
  dispatch instruction to the model that reads it.
* ``AskUserQuestion`` anywhere.

A line that also contains ``Claude Code`` is attributed, not bare: it names the
Claude tool as one host's choice beside the others, which is the host-neutral
wording the skills use. YAML frontmatter at the top of a Markdown file is
skipped. ``allowed-tools`` lists live there, and which keys the Codex and Muse
platform files keep is a platform decision (``templates/platforms/*.yaml``),
not a prose defect.

A second rule covers dispatch written in prose (ADR-115 Decision 13). A file
that names ``subagent_type`` anywhere outside frontmatter, even on a line
attributed to Claude Code, must carry the host-delegation paragraph, marked by
``**Delegation on each host.**``
(``templates/skills/partials/host-delegation.mustache``). The paragraph names
Codex ``spawn_agent`` and Muse Code ``subagent_spawn`` and tells the model to run
the step itself when the host has no subagent tool. Narrowest correct scope:

* The file carries the marker itself, or
* it sits under ``skills/<name>/`` and that skill's ``SKILL.md`` carries it. A
  script that prints a hint, or a reference file the model loads from
  ``SKILL.md``, is covered by the skill body that loaded it, or
* the line itself names Codex ``spawn_agent`` and Muse Code ``subagent_spawn``,
  so it already is the per-host text the paragraph would add.

A file under ``src/claude`` is not scanned: Claude Code registers ``Task``. The
Codex and Muse trees are generated from the same sources, so a miss there is a
miss in the source.

Exit codes: 0 clean, 1 violations found, 2 a scanned tree is missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

SHIPPED_TREES: tuple[str, ...] = ("src/codex", "src/muse")
ATTRIBUTION = "Claude Code"
BARE_TASK = re.compile(r"(?<![A-Za-z0-9_])Task\(")
BARE_ASK = re.compile(r"AskUserQuestion")
SUBAGENT_TYPE = "subagent_type"
DELEGATION_MARKER = "**Delegation on each host.**"
MISSING_DELEGATION = "subagent_type without the host-delegation paragraph"
INLINE_HOST_TOOLS: tuple[str, ...] = ("spawn_agent", "subagent_spawn")


def _body_lines(path: Path, text: str) -> Iterator[tuple[int, str]]:
    """Yield (line number, line) for every line outside Markdown frontmatter."""
    lines = text.splitlines()
    start = 0
    if path.suffix == ".md" and lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                start = index + 1
                break
    for index in range(start, len(lines)):
        yield index + 1, lines[index]


def line_violation(line: str) -> str | None:
    """Return the bare tool name a line calls, or None when the line is fine."""
    if ATTRIBUTION in line:
        return None
    if BARE_TASK.search(line):
        return "Task("
    if BARE_ASK.search(line):
        return "AskUserQuestion"
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _skill_root(tree: Path, path: Path) -> Path | None:
    """Return ``<tree>/skills/<name>`` for a file inside a skill, else None."""
    parts = path.relative_to(tree).parts
    if len(parts) < 3 or parts[0] != "skills":
        return None
    return tree / parts[0] / parts[1]


def _skill_carries_marker(tree: Path, path: Path) -> bool:
    root = _skill_root(tree, path)
    if root is None:
        return False
    body = _read(root / "SKILL.md")
    return body is not None and DELEGATION_MARKER in body


def scan_file(path: Path, *, covered: bool = False) -> list[tuple[int, str]]:
    """Return (line number, problem) for one file.

    ``covered`` says the owning skill's SKILL.md carries the delegation
    paragraph, which satisfies the prose rule for a script or reference file.
    """
    text = _read(path)
    if text is None:
        return []
    has_marker = covered or DELEGATION_MARKER in text
    found: list[tuple[int, str]] = []
    for number, line in _body_lines(path, text):
        tool = line_violation(line)
        names_hosts = all(name in line for name in INLINE_HOST_TOOLS)
        if tool is None and SUBAGENT_TYPE in line and not has_marker and not names_hosts:
            tool = MISSING_DELEGATION
        if tool is not None:
            found.append((number, tool))
    return found


def scan_tree(tree: Path) -> tuple[int, list[tuple[Path, int, str]]]:
    """Scan every file under a tree. Return (files examined, violations)."""
    examined = 0
    violations: list[tuple[Path, int, str]] = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        examined += 1
        covered = _skill_carries_marker(tree, path)
        for number, tool in scan_file(path, covered=covered):
            violations.append((path, number, tool))
    return examined, violations


def _describe(tool: str) -> str:
    return tool if tool == MISSING_DELEGATION else f"bare {tool} call"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root.resolve()
    total_examined = 0
    violations: list[tuple[Path, int, str]] = []
    for relative in SHIPPED_TREES:
        tree = root / relative
        if not tree.is_dir():
            print(f"host-neutral-dispatch: missing tree {relative}", file=sys.stderr)
            return 2
        examined, found = scan_tree(tree)
        total_examined += examined
        violations.extend(found)
    for path, number, tool in violations:
        rel = path.relative_to(root).as_posix()
        print(f"{rel}:{number}: {_describe(tool)}; name each host's tool, see issue #7226")
    print(
        f"host-neutral-dispatch: {len(violations)} violation(s) in {total_examined} files examined"
    )
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
