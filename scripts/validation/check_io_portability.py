#!/usr/bin/env python3
"""Flag added Python lines that depend on the platform's text encoding or symlink privilege.

Three rules, each an AST check with no guesswork about intent:

``subprocess-text-encoding``
    A ``subprocess`` call in text mode (``text=True`` or
    ``universal_newlines=True``) that passes no ``encoding``. Python then decodes
    with the locale encoding, which is cp1252 on many Windows hosts.
``file-text-encoding``
    ``Path.read_text()``, ``Path.write_text(data)`` or builtin ``open()`` in
    text mode with no ``encoding``. Same locale dependency. An attribute
    ``.open()`` is not checked: its receiver may be a zip member, an image, or a
    browser, and the AST cannot tell which.
``unguarded-symlink``
    A test file calls ``symlink_to`` or ``os.symlink`` outside a ``try`` that
    catches ``OSError`` or ``NotImplementedError``, in a function with no
    ``skip`` in its name, no ``skipif`` marker on the function or its class, and
    no module ``pytestmark`` that skips. Windows without Developer Mode raises ``OSError``,
    so the test errors instead of skipping.

These are the three mechanical rules behind 85 of the 166 Cursor Bugbot
"learned rule" findings on pull requests #6110 to #7380 (evals/third-party-review-gap).

Scope: with ``--base-ref``, only lines the branch's commits add over that
ref are reported (``base...HEAD``, read from HEAD), so existing code does not
block. A line moved unchanged within a file is not new and is not reported.
Generated mirror trees (``MIRROR_PREFIXES``) are skipped in that mode, because
``build_all.py`` copies them from ``src/claude/`` and ``scripts/``. Generated
copies outside that list, such as ``src/claude/lib/`` and the rendered hook
launchers, are still checked, so a violation in their source can be reported
more than once. With file arguments, every line in those files is reported. A
call carrying ``**kwargs`` is skipped: its encoding cannot be read statically.

Suppress one line with ``# io-portability: ignore <reason>``.

Exit codes (ADR-035): 0 clean, 1 violations, 2 configuration error.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# checks_common imports ``scripts.cli_exec`` by absolute name, so the repository
# root must be importable when this runs as a plain script, as in the sibling
# added-lines gates (check_measurement_anchoring.py).
for _entry in (_REPO_ROOT, _SCRIPT_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import checks_common  # noqa: E402
import citation_head_state  # noqa: E402
from io_portability_rules import (  # noqa: E402
    SUPPRESS,
    Violation,
    is_test_path,
    scan_source,
)

__all__ = ["SUPPRESS", "Violation", "is_test_path", "scan_source"]

# Generated Python trees: every output prefix in
# scripts/validation/git_hook_policy.py:_GENERATED_MIRRORS that can hold a .py
# file, plus src/hermes/ (ADR-115 Decision 6 packs). src/claude/skills/ is
# deliberately absent although that map lists it: since ADR-119 it is the
# canonical, hand-maintained skill source, so its scripts are checked.
# test_mirror_prefixes_match_the_generated_mirror_map pins this.
MIRROR_PREFIXES: tuple[str, ...] = (
    "src/copilot-cli/skills/",
    "src/copilot-cli/lib/",
    "src/copilot-cli/hooks/",
    "src/codex/skills/",
    "src/codex/lib/",
    "src/cursor/skills/",
    "src/cursor/lib/",
    "src/muse/skills/",
    "src/muse/lib/",
    "src/hermes/",
)


def added_line_numbers(
    repo_root: Path, base_ref: str, head_ref: str = "HEAD"
) -> dict[str, set[int]]:
    """Line numbers each path adds between ``base_ref`` and ``head_ref``, as the gate reads them.

    The one parser the gate uses (``citation_head_state._added_lines_since_base``),
    so an eval that replays a past commit pair measures the shipped behavior.
    """
    added = citation_head_state._added_lines_since_base(repo_root, base_ref, head_ref)
    if added is None:
        raise ValueError(f"git diff {base_ref}...{head_ref} failed")
    return {path: {number for number, _text in lines} for path, lines in added.items()}


def _git(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run git; a timeout or a missing binary is a configuration error (exit 2), not a finding."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError(f"git {args[0]} could not run: {exc}") from exc


def is_skipped_path(path: str) -> bool:
    """Generated mirrors and fixture trees are not authored code under review."""
    return path.startswith(MIRROR_PREFIXES) or "fixtures" in Path(path).parts


def scan_diff(base_ref: str, repo_root: Path = Path(".")) -> tuple[list[Violation], int]:
    """Violations on lines this branch adds over ``base_ref``, and Python files examined.

    Judges what a push sends: the committed ``base_ref...HEAD`` diff, with
    sources read from HEAD, so an uncommitted edit neither hides nor adds a
    finding. The added lines come from ``citation_head_state._added_lines_since_base``,
    the parser the other added-lines gates share, which pins prefixes, colour,
    rename detection and diff drivers so a contributor's git config cannot empty
    the diff, and keeps renamed, copied and type-changed files.
    """
    changed = {
        path: lines
        for path, lines in added_line_numbers(repo_root, base_ref).items()
        if path.endswith(".py") and not is_skipped_path(path)
    }
    found: list[Violation] = []
    for path, lines in sorted(changed.items()):
        shown = _git(repo_root, ["show", f"HEAD:{path}"])
        if shown.returncode != 0:
            raise ValueError(f"cannot read {path} at HEAD: {shown.stderr.strip()}")
        found.extend(
            v for v in scan_source(path, shown.stdout) if any(v.spans(line) for line in lines)
        )
    return found, len(changed)


def repository_root() -> Path:
    """The working tree's top level, so a run from a subdirectory sees the whole diff."""
    top = _git(Path("."), ["rev-parse", "--show-toplevel"])
    if top.returncode != 0:
        raise ValueError(f"not inside a git repository: {top.stderr.strip()}")
    return Path(top.stdout.strip())


def validate_io_portability(repo_root: Path) -> bool:
    """Pre-PR gate entry point: print findings, return True when added lines are clean.

    Resolving no base ref prints ``[SKIP]`` and passes, the same contract as the
    other added-lines gates: with no base there is no added range to judge.
    """
    base_ref = checks_common._resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] io-portability: no base ref resolved; nothing to diff against")
        return True
    try:
        found, examined = scan_diff(base_ref, repo_root)
    except ValueError as exc:
        print(f"[io-portability] {exc}", file=sys.stderr)
        return False
    for violation in found:
        print(violation.render(), file=sys.stderr)
    status = "FAIL" if found else "OK"
    print(
        f"[{status}] io-portability: {len(found)} violation(s) on added lines "
        f"in {examined} changed Python file(s) vs {base_ref}"
    )
    if found:
        print(
            "  Fix: pass encoding='utf-8' (and errors='replace' for subprocess capture), "
            "or create test symlinks through a helper that skips on OSError.",
            file=sys.stderr,
        )
    return not found


def scan_files(paths: Sequence[str]) -> tuple[list[Violation], int]:
    found: list[Violation] = []
    for path in paths:
        try:
            source = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"cannot read {path}: {exc}") from exc
        found.extend(scan_source(path, source))
    return found, len(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", help="scan these files in full")
    parser.add_argument("--base-ref", help="scan only lines added since the merge base")
    args = parser.parse_args(argv)
    if bool(args.files) == bool(args.base_ref):
        print("error: pass either files or --base-ref", file=sys.stderr)
        return 2
    try:
        if args.base_ref:
            found, examined = scan_diff(args.base_ref, repository_root())
        else:
            found, examined = scan_files(args.files)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for violation in found:
        print(violation.render())
    print(f"{len(found)} io-portability violation(s) in {examined} file(s) examined")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
