#!/usr/bin/env python3
"""Inventory and rewrite the legacy plugin-root form into the ADR-121 locator.

Two modes, one of which is required::

    python3 build/scripts/plugin_run_fix.py --inventory
    python3 build/scripts/plugin_run_fix.py --fix PATH [PATH ...]

The file is not executable in git (mode 100644), so run it through ``python3``.

``--inventory`` is read-only. It prints, for each tracked file under ``templates/`` and
``src/claude/``, the count of legacy invocation sites, of assignment sites (lines
that match the ``git grep`` pattern ADR-121 prints), and of any other mention of the
nested form. It writes nothing.

``--fix`` rewrites the legacy invocations in the named authored files
(``plugin_run_rewrite.rewrite_text``). It checks every path first and writes nothing
when any path is refused. A path is refused when it is not a Markdown or template
file, when the build generates it, or when it is not an authored file the ratchet
counts. Edit a template and run ``build_all.py`` to change a render. A site the
rewrite cannot parse stays as it is and is reported on stderr with its line.

Exit codes (ADR-035):
    0 - success; ``--fix`` rewrote or found every site it could and none was refused
    1 - ``--fix`` left at least one site for a person
    2 - configuration error (a refused path, a missing file, an unreadable file)
    3 - external error (git failed)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
for _entry in (_SCRIPT_DIR, _REPO_ROOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import plugin_run_rewrite  # noqa: E402
from atomic_write import publish_bytes_preserving_mode  # noqa: E402

from scripts.validation import plugin_root_interpreter_ratchet as ratchet  # noqa: E402
from scripts.validation import plugin_root_interpreter_sites as sites  # noqa: E402

EXIT_OK, EXIT_LEFT_FOR_PERSON, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3
FIXABLE_SUFFIXES = (".md", ".tmpl", ".mustache")
INVENTORY_SCOPE = ("templates", "src/claude")
RENDER_GROUP = "render (not ratcheted)"
# The assignment pattern, read from the validator's own regex so the printed `git grep`
# command and the count cannot differ. ADR-121 printed an older, narrower spelling
# (`[A-Za-z_]+=`) that skips a name with a digit.
ADR_ASSIGNMENT_GREP = sites.ASSIGNMENT_RE.pattern
_NESTED_MENTION = "COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-"


class FixError(Exception):
    """A usage or configuration problem. ``code`` is the exit code to return."""

    def __init__(self, message: str, code: int = EXIT_CONFIG) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class InventoryRow:
    """The counts of one file that holds at least one mention of the nested form."""

    path: str
    group: str
    invocations: int
    assignments: int
    mentions: int


def _git(repo_root: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FixError(f"git {' '.join(args)} failed: {exc}", EXIT_EXTERNAL) from exc
    return done.stdout


def _read_text(path: Path) -> str | None:
    """Return the file's text, or ``None`` for a binary file."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    except OSError as exc:
        raise FixError(f"could not read {path}: {exc}") from exc


def collect_inventory(repo_root: Path) -> list[InventoryRow]:
    """Return one row per tracked file in scope that mentions the nested form."""
    listing = _git(repo_root, "ls-files", "-z", "--", *INVENTORY_SCOPE)
    rows: list[InventoryRow] = []
    for rel in sorted(filter(None, listing.split("\0"))):
        path = repo_root / rel
        if path.is_symlink() or not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            continue
        mentions = text.count(_NESTED_MENTION)
        counts = sites.count_legacy_sites(text)
        if not (mentions or counts.invocations or counts.assignments):
            continue
        group = ratchet.authored_group(rel) or RENDER_GROUP
        rows.append(InventoryRow(rel, group, counts.invocations, counts.assignments, mentions))
    return rows


def format_inventory(rows: list[InventoryRow], sha: str) -> str:
    """Return the inventory report: scope, per-group totals, then per-file counts."""
    by_group: dict[str, list[InventoryRow]] = defaultdict(list)
    for row in rows:
        by_group[row.group].append(row)
    lines = [
        f"plugin-run-fix inventory at {sha}",
        "scope: tracked files under templates/ and src/claude/, read from the working tree.",
        'invocations: legacy `python3 "${...}/skills/...py"` commands (the validator\'s count).',
        "assignments: lines matching the validator's assignment pattern, run as "
        f"git grep -nE '{ADR_ASSIGNMENT_GREP}' -- {' '.join(INVENTORY_SCOPE)}",
        "mentions: every occurrence of the nested form, the ADR-121 context count.",
        "",
        f"{'group':<26}{'files':>6}{'invocations':>13}{'assignments':>13}{'mentions':>10}",
    ]
    for group in sorted(by_group):
        members = by_group[group]
        lines.append(
            f"{group:<26}{len(members):>6}{sum(r.invocations for r in members):>13}"
            f"{sum(r.assignments for r in members):>13}{sum(r.mentions for r in members):>10}"
        )
    lines += ["", f"{'file':<76}{'group':<26}{'inv':>5}{'asg':>5}{'ment':>6}"]
    lines += [
        f"{r.path:<76}{r.group:<26}{r.invocations:>5}{r.assignments:>5}{r.mentions:>6}"
        for r in sorted(rows, key=lambda row: (row.group, row.path))
    ]
    return "\n".join(lines) + "\n"


def _generated_targets(repo_root: Path) -> set[str]:
    """Return every file the build renders, as repository-relative POSIX paths."""
    import agent_templates
    import hook_templates
    import rule_templates
    import skill_templates

    targets: set[Path] = set()
    try:
        for module in (agent_templates, hook_templates, rule_templates, skill_templates):
            targets |= module.owned_targets(repo_root)
    except (OSError, ValueError) as exc:
        raise FixError(f"could not list the files the build renders: {exc}") from exc
    return {target.relative_to(repo_root).as_posix() for target in targets}


def generated_reason(rel: str, targets: set[str]) -> str | None:
    """Return why the build owns ``rel``, or ``None`` when a person edits it.

    ``targets`` is :func:`_generated_targets`. The set comes from the build's own
    lists: the render targets of the four template classes, and
    ``build_all.OWNED_PREFIXES``. The one carve-out is the files under
    ``src/claude/skills/<name>/`` other than ``SKILL.md``: the build docs call
    them hand-maintained, and ``OWNED_PREFIXES`` covers ``src/`` whole.
    """
    import build_all

    if rel in targets:
        return "the build renders it from a template"
    if ratchet.authored_group(rel) is not None and rel.startswith("src/claude/skills/"):
        return None
    for prefix in build_all.OWNED_PREFIXES:
        if rel == prefix or rel.startswith(prefix):
            return f"it sits under the build output prefix {prefix}"
    return None


def check_target(repo_root: Path, arg: str, targets: set[str]) -> Path:
    """Return the real path for ``arg``, or raise :class:`FixError` naming why it is refused."""
    path = Path(arg)
    if not path.is_file():
        raise FixError(f"{arg}: not a file")
    real = path.resolve()
    try:
        rel = real.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise FixError(f"{arg}: outside the repository {repo_root}") from exc
    if not rel.endswith(FIXABLE_SUFFIXES):
        raise FixError(
            f"{arg}: only {', '.join(FIXABLE_SUFFIXES)} files are rewritten. YAML is Class G "
            "and Python bootstraps itself (ADR-121 decision 1)"
        )
    reason = generated_reason(rel, targets)
    if reason is not None:
        raise FixError(f"{arg}: generated, {reason}. Edit its template and run build_all.py")
    if ratchet.authored_group(rel) is None:
        raise FixError(f"{arg}: not an authored file under templates/ or src/claude/skills/")
    return real


def _head_label(repo_root: Path) -> str:
    """Return the short commit the working tree sits on, or a note for a repository with none."""
    try:
        return _git(repo_root, "rev-parse", "--verify", "--short=9", "HEAD").strip()
    except FixError:
        return "no commit yet"


def _write(path: Path, text: str) -> None:
    try:
        publish_bytes_preserving_mode(path, text.encode("utf-8"))
    except OSError as exc:
        raise FixError(f"could not write {path}: {exc}") from exc


def run_inventory(repo_root: Path) -> int:
    """Print the inventory. Reads files and git; writes nothing."""
    sys.stdout.write(format_inventory(collect_inventory(repo_root), _head_label(repo_root)))
    return EXIT_OK


def run_fix(repo_root: Path, args: list[str]) -> int:
    """Rewrite the named files. Check every path before the first write."""
    generated = _generated_targets(repo_root)
    targets = [check_target(repo_root, arg, generated) for arg in args]
    results = []
    for real in targets:
        text = _read_text(real)
        if text is None:
            raise FixError(f"{real}: not UTF-8 text")
        results.append((real, text, plugin_run_rewrite.rewrite_text(text)))
    left = 0
    for real, text, result in results:
        if result.text != text:
            _write(real, result.text)
        for refusal in result.refusals:
            print(f"{real}:{refusal.lineno}: left for a person: {refusal.reason}", file=sys.stderr)
        left += len(result.refusals)
        print(f"{real}: {result.fixed} fixed, {len(result.refusals)} left")
    return EXIT_LEFT_FOR_PERSON if left else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true", help="Print counts. Writes nothing.")
    mode.add_argument("--fix", nargs="+", metavar="PATH", help="Rewrite these authored files.")
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT, help="Repository root.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one mode and return its exit code."""
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        if args.inventory:
            return run_inventory(repo_root)
        return run_fix(repo_root, args.fix)
    except FixError as exc:
        print(f"plugin-run-fix: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
