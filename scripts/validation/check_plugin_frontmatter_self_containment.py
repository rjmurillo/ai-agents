#!/usr/bin/env python3
"""Frontmatter self-containment gate for shipped plugin files (issue #3565).

Why this exists separately from ``check_skill_md_portability.py``:

  That validator is a baselined ratchet over skill *prose*, scoped to
  ``.claude/skills``. Three of the four surfaces the plugin-self-containment
  rule names are outside its scan (``.claude/commands``, ``src/claude``,
  ``src/copilot-cli``), and its pattern set does not include ``docs/``. A
  ``docs/`` reference in a shipped frontmatter description therefore passes
  every gate in this repository, wherever it sits. Two were sitting in the
  tree, both far older than the rule that forbids them. ``docs/agent-metrics.md``
  arrived with the first commit of ``.claude/skills/metrics/SKILL.md``
  (``625e224ab3``, #255, 2025-12-27) and ``docs/autonomous-pr-monitor.md`` with
  the ``pr-autofix`` rename (``c70fb06eb5``, #2138, 2026-05-30). The rule
  forbidding both shipped on 2026-07-26 in #3443 with no validator, so neither
  moved. Check provenance against the source file, never the generated mirror:
  the mirror's history begins when the generator first wrote it, which dates
  the copy rather than the claim.

Measured precision, and the cost of being wrong:

  The gate has no baseline, so a false positive hard-blocks a legitimate
  change. That claim was tested rather than asserted. Replaying this check
  over every historical version of every Markdown file in all three plugin
  roots, 3,687 blobs reachable from ``git rev-list --objects --all``, produces
  four distinct references and no others: ``docs/autonomous-pr-monitor.md``,
  ``docs/agent-metrics.md``, ``.agents/governance/golden-principles.md``
  (declared), and ``scripts/incoherence.py`` in a deprecated skill. All four
  are real. None resolves for a consumer. Across the 3,909 Markdown files in
  the current tree the gate reports nothing at all.

  The known theoretical false positive is a description that names a consumer
  artifact the skill writes rather than reads, such as
  ``.github/workflows/ci.yml``. The extension test cannot tell those apart
  from an upstream dependency. That shape has never appeared in a shipped
  frontmatter in this repository's history, which is why the check is absolute
  instead of baselined. If one lands, the remedy is a ``vendor-portability``
  marker naming that path, and a second marker vocabulary is worth adding only
  once the case is real rather than imagined.

Why frontmatter, and only frontmatter:

  A ``description`` is loaded into every session so the harness can route,
  whether or not the skill is ever invoked. Body prose is read only on
  invocation. A dangling path in a description is therefore the most-read and
  least-useful kind: the consumer sees it constantly and can never resolve it.
  Body prose is a far larger surface (2,554 references across 347 files by
  time of writing) that needs per-file classification against the rule's
  three-kind table, so it stays with the existing ratchet and with review.

What counts as a violation:

  A frontmatter ``description`` or ``name`` under a plugin root that names a
  *file* (a path with an extension) under a directory that exists only in
  ``rjmurillo/ai-agents``.

  Requiring an extension is what keeps this check honest. The rule permits
  consumer-workspace paths, which are the plugin doing its job: an agent told
  to write to ``.agents/planning/`` or ``docs/adr/`` is correct, because those
  are directories in the *installing* repo. Those have no extension. It also
  sidesteps the prose collisions the rule warns about, such as
  "build/buy/partner", which would match a bare ``build/`` prefix.

  ``templates/`` is deliberately narrowed to ``templates/agents/`` and
  ``templates/platforms/``. The bare directory name is overloaded: a skill may
  ship its own ``templates/`` directory, and framework conventions appear in
  prose. Only those two are upstream-only.

Opt-out:

  A ``<!-- vendor-portability: ... -->`` marker suppresses a frontmatter
  reference only when the marker itself names that path. The sibling
  validators read the marker as a whole-file switch, and for frontmatter that
  is demonstrably wrong: ``.claude/skills/metrics/SKILL.md`` carries one
  written about the consumer's ``.agents/`` artifacts, and a whole-file reading
  lets it silence the unrelated ``docs/agent-metrics.md`` sitting in its own
  description. The rule states the general form: a whole-file declaration
  "would also hide a later real regression in the same file". Scoping the
  opt-out to the path it names keeps the hatch specific and makes it say what
  it is buying.

No baseline. The surface is four files, two of which are declared, so the
honest starting point is zero and staying there. A baseline on a surface this
small would only invite drift.

Exit codes:
  0 - no undeclared outward file references in frontmatter
  1 - at least one violation
  2 - configuration error (no plugin root found)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

PLUGIN_ROOTS = (".claude", "src/claude", "src/copilot-cli")

# Directories that exist only in this repository. A consumer who installs a
# plugin receives the plugin root and nothing above it.
UPSTREAM_ONLY = (
    r"docs",
    r"\.agents",
    r"\.github",
    r"\.serena",
    r"scripts",
    r"tests",
    r"build",
    r"templates/agents",
    r"templates/platforms",
)

# A path under an upstream-only directory that names a file, not a directory.
# The trailing extension is load-bearing: see the module docstring.
OUTWARD_FILE = re.compile(
    r"(?<![\w./-])(?:\.{1,2}/)?(?:"
    + "|".join(UPSTREAM_ONLY)
    + r")/[\w./-]*\w\.[A-Za-z][A-Za-z0-9]{0,4}(?![\w/])"
)

DECLARATION = re.compile(r"<!--\s*vendor-portability:(.*?)-->", re.IGNORECASE | re.DOTALL)

# Frontmatter keys whose values reach the consumer before invocation.
CHECKED_KEYS = ("description", "name")

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG = 2


def frontmatter_lines(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, line)`` for the frontmatter block, 1-based.

    Empty when the file has no frontmatter or the block is unterminated. An
    unterminated block is not frontmatter; treating the whole file as
    frontmatter would scan body prose this check deliberately excludes.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return [(n + 2, line) for n, line in enumerate(lines[1:index])]
    return []


def checked_values(text: str) -> list[tuple[int, str, str]]:
    """Return ``(line_number, key, value)`` for each checked frontmatter key.

    Continuation lines of a folded or literal YAML scalar belong to the key
    that opened them, so they are attributed to it rather than skipped.
    """
    found: list[tuple[int, str, str]] = []
    active: str | None = None
    for number, line in frontmatter_lines(text):
        match = re.match(r"([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if match:
            key = match.group(1)
            active = key if key in CHECKED_KEYS else None
            if active:
                found.append((number, key, match.group(2)))
            continue
        if active and line.startswith((" ", "\t")):
            found.append((number, active, line.strip()))
    return found


def declared_paths(text: str) -> set[str]:
    """Paths named inside this file's ``vendor-portability`` markers.

    Scoping the opt-out to the paths it names is the difference between an
    escape hatch and a blanket. A marker written about one dependency must not
    silence an unrelated one that lands in the same file later.
    """
    declared: set[str] = set()
    for body in DECLARATION.findall(text):
        declared.update(OUTWARD_FILE.findall(body))
    return declared


def root_shipper(repo_root: Path, root: str) -> Callable[[str], bool]:
    """True for references that resolve inside the plugin root that ships them.

    Self-containment is a property of a path relative to its own plugin root,
    not of the directory name. ``src/copilot-cli`` ships its own ``docs/``
    directory, so ``docs/copilot-instructions.md`` resolves for that plugin's
    consumer and must not be flagged, while the same string under ``.claude``
    points at nothing the consumer installed.
    """

    base = repo_root / root

    def ships(reference: str) -> bool:
        candidate = reference[2:] if reference.startswith("./") else reference
        if ".." in candidate.split("/"):
            return False
        return (base / candidate).exists()

    return ships


def scan_file(
    path: Path, text: str, ships: Callable[[str], bool] | None = None
) -> list[tuple[int, str, str]]:
    """Return ``(line_number, key, reference)`` violations for one file."""
    declared = declared_paths(text)
    violations: list[tuple[int, str, str]] = []
    for number, key, value in checked_values(text):
        for reference in OUTWARD_FILE.findall(value):
            if reference in declared:
                continue
            if ships is not None and ships(reference):
                continue
            violations.append((number, key, reference))
    return violations


def iter_markdown(root: Path) -> list[Path]:
    """Every ``.md`` file under the plugin roots, in a stable order.

    ``.claude/worktrees`` holds nested checkouts of this same repository. They
    are not source, and scanning them multiplies every finding by the number of
    live agent worktrees.
    """
    found: list[Path] = []
    for name in PLUGIN_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            parts = path.relative_to(root).parts
            if "worktrees" in parts or "__pycache__" in parts or "node_modules" in parts:
                continue
            found.append(path)
    return sorted(found)


def owning_root(path: Path, repo_root: Path) -> str | None:
    """The plugin root that ships ``path``, or ``None`` if it is outside them."""
    relative = path.relative_to(repo_root).as_posix()
    for name in PLUGIN_ROOTS:
        if relative.startswith(f"{name}/"):
            return name
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to the tree containing this script.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root or Path(__file__).resolve().parents[2]
    if not any((root / name).is_dir() for name in PLUGIN_ROOTS):
        print(f"No plugin root found under {root}", file=sys.stderr)
        return EXIT_CONFIG

    files = iter_markdown(root)
    violations: list[tuple[Path, int, str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            print(f"Could not read {path}: {error}", file=sys.stderr)
            return EXIT_CONFIG
        root_name = owning_root(path, root)
        ships = root_shipper(root, root_name) if root_name else None
        for number, key, reference in scan_file(path, text, ships):
            violations.append((path, number, key, reference))

    if not violations:
        print(
            f"No outward frontmatter references. Scanned {len(files)} files "
            f"across {len(PLUGIN_ROOTS)} plugin roots."
        )
        return EXIT_OK

    print(f"Outward frontmatter references in {len(violations)} place(s):\n", file=sys.stderr)
    for path, number, key, reference in violations:
        relative = path.relative_to(root)
        print(f"  {relative}:{number}  {key}: {reference}", file=sys.stderr)
    print(
        "\nA frontmatter description loads into every session, and a consumer "
        "who installs the plugin receives the plugin root and nothing above it, "
        "so these paths never resolve for them. Inline the fact, drop the "
        "clause, or declare the dependency with a "
        "'<!-- vendor-portability: ... -->' marker if it is real and intended. "
        "See .claude/rules/plugin-self-containment.md.",
        file=sys.stderr,
    )
    return EXIT_VIOLATION


if __name__ == "__main__":
    raise SystemExit(main())
