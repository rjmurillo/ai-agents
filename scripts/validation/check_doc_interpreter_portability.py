#!/usr/bin/env python3
"""Interpreter-portability ratchet for documented script invocations (issue #3791).

A document that tells a contributor to run

    python3 scripts/sync_adr_protocol.py

is only correct on a machine whose *system* interpreter already has the script's
third-party dependencies. ``scripts/sync_adr_protocol.py:24`` is ``import yaml``
and PyYAML is a declared project dependency (``pyproject.toml``), not a stdlib
module, so on a clean checkout the documented command dies with::

    ModuleNotFoundError: No module named 'yaml'

The portable form names the project environment::

    uv run python scripts/sync_adr_protocol.py

Why a docs guard and not a code fix:
  PR #3793 tried to delete the ``import yaml`` by hand-rolling a scalar reader.
  It was closed unmerged after review measured six behavioral divergences from
  ``yaml.safe_load`` on a script that decides ADR lifecycle state. The settled
  resolution is to name the right interpreter in the docs, which carries no
  behavioral risk. This guard keeps that fix from silently regressing.

What it counts:
  A ``python``/``python3`` invocation, optionally with short options
  (``python3 -u ...``), of a **tracked** ``.py`` file whose module-level import
  closure reaches a module that is neither stdlib
  (``sys.stdlib_module_names``) nor another tracked module in this repository.

  Module-level is the operative word. ``scripts/eval/eval-suite.py`` imports
  ``_anthropic_api``, which imports ``anthropic`` inside a function body. That
  import does not run on the documented ``--dry-run`` path, and
  ``python3 -S scripts/eval/eval-suite.py --dry-run`` succeeds, so counting it
  would be a false positive. Only imports that execute at import time count:
  the module body, plus ``if``/``try``/``with``/``for`` and class bodies nested
  in it, never a function body.

  An invocation already prefixed with ``uv run`` does NOT match; that is the
  fixed form. ``#!/usr/bin/env python3`` shebangs do not match (no ``.py``
  operand). Hook registrations such as
  ``python3 -u .claude/hooks/<EventName>/invoke_<purpose>.py`` do not match:
  the placeholder path is not a tracked file, and hooks run under the host's
  ambient interpreter by contract (``.claude/rules/python.md``).

Scope:
  Tracked Markdown, minus two exclusions.

  * **Historical roots** (``.agents/sessions/``, ``.agents/retrospective/``,
    ``.agents/architecture/``, and siblings). These are records of what was
    decided or done, not instructions to follow. Rewriting a session log or an
    ADR body to change a command it quotes would falsify the record.
  * **Generated mirrors** (``src/copilot-cli/``, ``src/claude/``,
    ``src/vs-code-agents/``, ``.github/instructions/``). Per
    ``.agents/governance/GENERATOR-FILES.md`` these are build outputs; the fix
    belongs in the canonical source and arrives here by regeneration.

Baseline ratchet:
  Current offenders are grandfathered in ``doc_interpreter_baseline.json``. The
  check FAILS only when a file rises above its baseline or a clean file starts
  offending. It REPORTS when a count drops so the baseline can be tightened with
  ``--update-baseline``. Because history and mirrors are out of scope, the
  baseline is the live migration worklist, not a dump of the whole repository.

Exit codes (ADR-035):
  0 - no drift (counts at or below baseline), or --update-baseline wrote the file
  1 - drift detected (a file exceeds its baseline or a new file offends)
  2 - configuration error (baseline unreadable, git unavailable)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

_DEFAULT_BASELINE_NAME = "doc_interpreter_baseline.json"

# Records, not instructions. A command quoted inside one of these describes what
# was run at the time; changing it would rewrite the record.
HISTORICAL_ROOTS: tuple[str, ...] = (
    ".agents/analysis/",
    ".agents/archive/",
    ".agents/architecture/",
    ".agents/audit/",
    ".agents/audits/",
    ".agents/critique/",
    ".agents/devops/",
    ".agents/planning/",
    ".agents/projects/",
    ".agents/qa/",
    ".agents/retrospective/",
    ".agents/sessions/",
    ".agents/specs/",
    ".claude-mem/",
    ".forgetful/",
    ".serena/",
    "evals/",
)

# Build outputs per .agents/governance/GENERATOR-FILES.md. Fix the source; these
# arrive by regeneration.
GENERATED_ROOTS: tuple[str, ...] = (
    ".github/instructions/",
    "src/claude/",
    "src/copilot-cli/",
    "src/vs-code-agents/",
)

# `uv run [flags] python[3] [short opts] <tracked>.py`
# The optional `uv` group is captured so an already-fixed invocation can be
# recognized and skipped rather than reported.
INVOCATION_PATTERN = re.compile(
    r"(?<![\w./-])"
    r"(?P<uv>uv[ \t]+run[ \t]+(?:--?[\w-]+(?:[ \t]+|=)\S*[ \t]*)*)?"
    r"python3?"
    r"(?:[ \t]+-[\w-]+)*"
    r"[ \t]+"
    r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.py)"
    r"(?![\w./-])"
)


def _run_git(repo_root: Path, *args: str) -> str:
    """Return stdout of a git command run at ``repo_root``."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def tracked_files(repo_root: Path, *patterns: str) -> list[str]:
    """Return tracked paths matching ``patterns``, POSIX-normalized."""
    out = _run_git(repo_root, "ls-files", "-z", *patterns)
    return [entry.replace("\\", "/") for entry in out.split("\0") if entry]


def is_in_scope(rel_path: str) -> bool:
    """Return whether a document carries instructions this guard should gate."""
    return not rel_path.startswith(HISTORICAL_ROOTS + GENERATED_ROOTS)


def _import_time_nodes(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield statements that execute when the module is imported.

    Descends into ``if``/``try``/``with``/``for`` and class bodies, which run at
    import time. Skips function bodies, whose imports run only when called.
    """
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield node
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(node, field, None)
            if isinstance(nested, list):
                yield from _import_time_nodes(nested)
        for handler in getattr(node, "handlers", []):
            yield from _import_time_nodes(handler.body)


def _imported_roots(tree: ast.Module) -> list[str]:
    """Return top-level module names imported at import time."""
    names: list[str] = []
    for node in _import_time_nodes(tree.body):
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module.split(".")[0])
    return names


def _local_modules(name: str, importer: str, tracked_py: set[str]) -> list[str] | None:
    """Resolve ``import <name>`` from ``importer`` to tracked files.

    Returns the resolved files, or ``None`` when ``name`` is not a repo module.

    Scripts here reach siblings through ``sys.path`` insertion, so a
    same-directory match wins. Failing that, a single repo-wide match is
    unambiguous and is followed. Two or more matches are NOT followed: the guard
    cannot prove which one the runtime loads, and unioning their imports invents
    dependencies. ``scripts/memory/validate_memory_sizes.py`` imports
    ``test_memory_size``, which matches four tracked files; one of them imports
    ``pytest``. Unioning reported the documented command as unportable even
    though ``python3 -S scripts/memory/validate_memory_sizes.py`` succeeds.
    An ambiguous name resolves to "local, nothing proven" so this blocking gate
    fails only on provable cases.
    """
    suffixes = (f"/{name}.py", f"/{name}/__init__.py")
    exact = (f"{name}.py", f"{name}/__init__.py")
    candidates = sorted(p for p in tracked_py if p.endswith(suffixes) or p in exact)
    if not candidates:
        return None
    same_dir = str(Path(importer).parent)
    preferred = [p for p in candidates if str(Path(p).parent) == same_dir]
    if preferred:
        return preferred
    return candidates if len(candidates) == 1 else []


def third_party_imports(
    rel_path: str,
    repo_root: Path,
    tracked_py: set[str],
    seen: set[str] | None = None,
) -> set[str]:
    """Return non-stdlib, non-repo modules reachable at import time from ``rel_path``."""
    seen = set() if seen is None else seen
    if rel_path in seen:
        return set()
    seen.add(rel_path)
    try:
        tree = ast.parse((repo_root / rel_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return set()

    found: set[str] = set()
    for name in _imported_roots(tree):
        if name in sys.stdlib_module_names:
            continue
        local = _local_modules(name, rel_path, tracked_py)
        if local is None:
            found.add(name)
            continue
        for target in local:
            found |= third_party_imports(target, repo_root, tracked_py, seen)
    return found


def find_offenses(line: str, repo_root: Path, tracked_py: set[str]) -> list[tuple[str, list[str]]]:
    """Return (script, third-party modules) for each unportable invocation on ``line``."""
    offenses: list[tuple[str, list[str]]] = []
    for match in INVOCATION_PATTERN.finditer(line):
        if match.group("uv"):
            continue
        script = match.group("path")
        while script.startswith("./"):
            script = script[2:]
        if script not in tracked_py:
            continue
        external = third_party_imports(script, repo_root, tracked_py)
        if external:
            offenses.append((script, sorted(external)))
    return offenses


def scan(repo_root: Path) -> dict[str, int]:
    """Return {doc path: unportable invocation count} for in-scope documents."""
    tracked_py = set(tracked_files(repo_root, "*.py"))
    counts: dict[str, int] = {}
    for rel in tracked_files(repo_root, "*.md"):
        if not is_in_scope(rel):
            continue
        path = repo_root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total = sum(len(find_offenses(line, repo_root, tracked_py)) for line in text.splitlines())
        if total:
            counts[rel] = total
    return counts


def load_baseline(path: Path) -> dict[str, int]:
    """Load the grandfathered per-file counts."""
    if not path.is_file():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    files = data.get("files", data)
    if not isinstance(files, dict):
        raise ValueError("Baseline 'files' must be a JSON object")
    baseline: dict[str, int] = {}
    for key, value in files.items():
        try:
            baseline[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Baseline count for {key!r} is not an integer") from exc
    return baseline


def diff_against_baseline(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements) comparing current counts to baseline."""
    regressions = [
        f"{rel}: {count} documented bare-interpreter invocation(s) of a script with "
        f"third-party imports (baseline {baseline.get(rel, 0)}). Use "
        f"'uv run python <script>' so the project environment supplies the "
        f"dependencies (issue #3791)."
        for rel, count in sorted(current.items())
        if count > baseline.get(rel, 0)
    ]
    improvements = [
        f"{rel}: {current.get(rel, 0)} invocations (baseline {allowed})"
        for rel, allowed in sorted(baseline.items())
        if current.get(rel, 0) < allowed
    ]
    return regressions, improvements


def validate_doc_interpreter_portability(repo_root: Path) -> bool:
    """Print drift and return True when every file is at or below its baseline."""
    return main(["--repo-root", str(repo_root)]) == 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Documented-interpreter portability ratchet.")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root.")
    parser.add_argument("--baseline", type=Path, default=None, help="Baseline JSON path.")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline from the current scan.",
    )
    return parser


def _resolve_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    repo_root = (args.repo_root or Path.cwd()).resolve()
    baseline = args.baseline or repo_root / "scripts" / "validation" / _DEFAULT_BASELINE_NAME
    return repo_root, baseline


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet."""
    args = build_parser().parse_args(argv)
    repo_root, baseline_path = _resolve_roots(args)

    try:
        current = scan(repo_root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"check-doc-interpreter-portability: {exc}", file=sys.stderr)
        return 2

    if args.update_baseline:
        payload = json.dumps({"files": dict(sorted(current.items()))}, indent=2) + "\n"
        baseline_path.write_text(payload, encoding="utf-8")
        print(f"check-doc-interpreter-portability: wrote {baseline_path} ({len(current)} files)")
        return 0

    try:
        baseline = load_baseline(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"check-doc-interpreter-portability: {exc}", file=sys.stderr)
        return 2

    regressions, improvements = diff_against_baseline(current, baseline)
    for line in improvements:
        print(f"IMPROVED {line}")
    for line in regressions:
        print(f"DRIFT {line}", file=sys.stderr)

    if regressions:
        print(
            "check-doc-interpreter-portability: FAIL. Rerun with --update-baseline "
            "only after fixing, never to silence a new offender.",
            file=sys.stderr,
        )
        return 1

    print("check-doc-interpreter-portability: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
