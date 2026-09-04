"""Select the pytest files affected by a set of changed files.

Applies the fail-safe rules from issue #5050: any non-Python change, any
``conftest.py`` change, any file matching a runtime-read pattern, any dynamic
import in a changed file, or any file the import graph cannot map falls back to
the full suite. Otherwise the import graph yields the exact set of test files
that transitively import the changed files.

Run directly to see the decision for a diff::

    python scripts/test_selection/select_tests.py --from-git origin/main path/a.py
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.test_selection import import_graph
except ModuleNotFoundError:  # pragma: no cover - exercised via direct file execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.test_selection import import_graph

FULL_SUITE = "FULL_SUITE"
_PATTERNS_FILE = Path(__file__).with_name("runtime_read_patterns.txt")


@dataclass(frozen=True)
class Selection:
    """Outcome of test selection.

    ``full`` True means run the entire suite; ``tests`` is empty in that case.
    ``full`` False means run exactly ``tests`` (never empty: an empty result is
    promoted to a full run so a push can never pass by running zero tests).
    """

    full: bool
    reason: str
    tests: tuple[str, ...] = ()


def _full(reason: str) -> Selection:
    return Selection(full=True, reason=reason, tests=())


def load_runtime_read_patterns(patterns_file: Path | None = None) -> tuple[str, ...]:
    """Read non-import dependency globs, ignoring blanks and ``#`` comments."""
    path = patterns_file if patterns_file is not None else _PATTERNS_FILE
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(
        stripped for line in lines if (stripped := line.strip()) and not stripped.startswith("#")
    )


def _matches_pattern(rel: str, pattern: str) -> bool:
    if rel == pattern:
        return True
    # fnmatch treats "*" as matching across "/", so collapsing "**" to "*"
    # over-matches rather than under-matches: a wider full-suite trigger is the
    # safe direction here.
    return fnmatch.fnmatch(rel, pattern.replace("**", "*"))


def _matches_any_pattern(rel: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        if _matches_pattern(rel, pattern):
            return pattern
    return None


def _is_python(rel: str) -> bool:
    return rel.endswith(".py")


def _is_test_file(rel: str) -> bool:
    return rel.startswith("tests/") and fnmatch.fnmatch(Path(rel).name, "test_*.py")


def has_dynamic_import(path: Path) -> bool:
    """True when ``path`` uses importlib or ``__import__`` (an unmapped edge).

    Static import statements are traced by the graph. A dynamic import is not,
    so a changed file that does one cannot be trusted to have a complete edge
    set and forces the full suite.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "importlib" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "importlib":
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":
                return True
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
                and isinstance(func.value, ast.Name)
                and func.value.id == "importlib"
            ):
                return True
    return False


def select(
    changed: list[str],
    repo_root: Path,
    cache_path: Path | None = None,
    patterns_file: Path | None = None,
) -> Selection:
    """Decide which tests to run for ``changed`` files, falling back to full."""
    changed = [rel.replace("\\", "/").strip() for rel in changed if rel.strip()]
    if not changed:
        return _full("no changed files reported")

    patterns = load_runtime_read_patterns(patterns_file)
    for rel in changed:
        matched = _matches_any_pattern(rel, patterns)
        if matched is not None:
            return _full(f"{rel} matches runtime-read pattern {matched}")

    for rel in changed:
        if not _is_python(rel):
            return _full(f"non-Python change: {rel}")

    for rel in changed:
        if Path(rel).name == "conftest.py":
            return _full(f"conftest change: {rel}")

    for rel in changed:
        candidate = repo_root / rel
        if candidate.is_file() and has_dynamic_import(candidate):
            return _full(f"dynamic import in changed file: {rel}")

    try:
        graph_data = import_graph.load_or_build_data(repo_root, cache_path)
    except RuntimeError as exc:
        return _full(f"import graph unavailable: {exc}")

    graph = graph_data.graph
    unmapped = [rel for rel in changed if rel not in graph]
    if unmapped:
        return _full(f"unmapped changed files: {', '.join(sorted(unmapped))}")

    reverse = import_graph.reverse_graph(graph)
    affected = import_graph.affected_closure(changed, reverse)
    if graph_data.wildcard_dependents:
        affected.update(import_graph.affected_closure(graph_data.wildcard_dependents, reverse))
    tests = tuple(sorted(rel for rel in affected if _is_test_file(rel)))
    if not tests:
        return _full("no test transitively imports the changed files")
    return Selection(full=False, reason="import-graph subset", tests=tests)


def changed_from_git(repo_root: Path, base: str, head: str = "HEAD") -> list[str] | None:
    """Files ``head`` changed versus ``base`` (three-dot diff), or None.

    ``head`` defaults to the checkout's own HEAD, which is what a developer and
    a `push` run want. On `pull_request`, Actions checks out the synthetic
    `refs/pull/N/merge` commit, so HEAD carries every base-branch commit made
    since the event's `base.sha` as well as the author's. Measured on the shape
    issue #5378 reports: with `base.sha` at the fork point and the merge commit
    as HEAD, the diff listed an unrelated `.github/workflows/claude.yml` from
    the base branch and forced the full suite. Passing the pull request's own
    `head.sha` reproduces GitHub's base-to-head file list instead.

    Returns None when git cannot compute the diff, which includes an unfetched
    or unknown SHA. Every caller treats None as "run everything", so a checkout
    too shallow to hold both commits fails closed.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...{head}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=str(import_graph.find_repo_root()),
        help="Repository root (defaults to the checkout containing this script).",
    )
    parser.add_argument(
        "--from-git",
        metavar="BASE",
        default=None,
        help="Compute changed files from `git diff BASE...HEAD` instead of positionals.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="text prints FULL_SUITE or one test path per line; json prints the full decision.",
    )
    parser.add_argument("files", nargs="*", help="Changed files (repo-relative).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if args.from_git is not None:
        changed = changed_from_git(repo_root, args.from_git)
        if changed is None:
            selection = _full(f"could not diff against {args.from_git}")
        else:
            selection = select(changed, repo_root)
    else:
        selection = select(list(args.files), repo_root)

    if args.format == "json":
        import json

        print(
            json.dumps(
                {"full": selection.full, "reason": selection.reason, "tests": list(selection.tests)}
            )
        )
        return 0

    print(f"selection: {selection.reason}", file=sys.stderr)
    if selection.full:
        print(FULL_SUITE)
    else:
        for test in selection.tests:
            print(test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
