#!/usr/bin/env python3
"""CLI exit-contract ratchet for extracted CI scripts (issue #4068).

ADR-006 extraction moves a workflow ``run:`` block into a Python module. A
``run:`` block executes under ``set -e``, so any command exiting nonzero fails
the step. The natural Python translation returns a sentinel instead: an empty
string, ``None``, an empty list, a warning followed by ``return 0``. When no
caller turns that sentinel into a nonzero exit, the step goes green on a
failure that used to be red. Extraction is a silent-pass generator, not only a
silent-pass detector.

Six instances were found in two in-flight extraction PRs, and three of them
shipped tests asserting the swallow. Every one of those tests asserted on a
helper's return value and never on ``main(argv)``. A helper-level assertion
structurally cannot catch an exit-code defect: the helper correctly reports
failure, and nothing checks that the process does.

So gate the observable property rather than the data flow. A sentinel-tracing
AST scan is high false-positive and only catches shapes already enumerated.
"an extracted CI script whose CLI is never proven to exit nonzero" is
mechanically decidable and catches all six shapes at once.

The ratchet policy (equality, ``--update`` records a decrease, ``--base-ref``
blocks a PR that widens the allowance) is shared with ``ruff_count_ratchet.py``
and ``taste_count_ratchet.py`` through ``count_ratchet.run``. Only the counting
below is new.

Exit codes (AGENTS.md contract):
    0 - ok (count == baseline, or --update records a decrease)
    1 - regression (count != baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (git could not run)
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    build_parser,
    run,
    tracked_files,
)

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "covered_stems",
    "current_count",
    "defines_main",
    "main",
    "uncovered_scripts",
]

_BASELINE_PATH = Path(__file__).with_name("cli_exit_contract_baseline.txt")

_SCRIPT_GLOB = "scripts/ci/*.py"
_TEST_GLOBS = ("tests/**/*.py", "tests/*.py")

# The four assertion shapes that prove a CLI reports failure. Each is written
# against the forms already in tests/ci; a new shape widens this pattern rather
# than exempting the script.
#
#   assert main(["--bad"]) == 1
#   assert main([]) == EXIT_CONFIG          (any EXIT_ name that is not success)
#   assert result.returncode == 2           (subprocess-driven CLI)
#   assert excinfo.value.code != 0          (pytest.raises(SystemExit))
_NONZERO_EXIT_ASSERTION = re.compile(
    r"""
      main\(.*\)\s*(?:==\s*[1-9]|!=\s*0)
    | ==\s*(?:[A-Za-z_][\w.]*\.)?EXIT_(?!OK\b|SUCCESS\b)[A-Z][A-Z_]*
    | returncode\s*(?:==\s*[1-9]|!=\s*0)
    | \.code\s*(?:==\s*[1-9]|!=\s*0)
    """,
    re.VERBOSE,
)


def defines_main(source: str) -> bool:
    """True when the module body defines a ``main`` function.

    Only a module-level definition counts. A ``main`` nested inside a class or
    another function is not the process entry point, so it carries no exit
    contract to prove.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        for node in tree.body
    )


# The binding styles tests under tests/ci actually use:
#   from scripts.ci import check_codeql_sarif as ccs
#   from require_job_results import failures, main   (inside a sys.path fixture)
#   import run_quality_grades as grades
#   qa_mod = _load_module("check_pr_qa_report")
_FROM_IMPORT = re.compile(r"^[ \t]*from\s+([\w.]+)\s+import\s+(.+)$", re.MULTILINE)
_PLAIN_IMPORT = re.compile(r"^[ \t]*import\s+([\w.]+)(?:\s+as\s+(\w+))?", re.MULTILINE)
_LOADER_ALIAS = re.compile(r"^[ \t]*(\w+)\s*=\s*_load_module\(\s*[\"'](\w+)[\"']", re.MULTILINE)
# A hand-rolled spec_from_file_location block registers the module by name:
#   sys.modules["check_ai_review_infra_gate"] = mod
_SYS_MODULES_ALIAS = re.compile(
    r"^[ \t]*sys\.modules\[[\"'](\w+)[\"']\]\s*=\s*(\w+)", re.MULTILINE
)

# A subprocess-driven CLI names the script by path instead of importing it.
_SCRIPT_PATH_REFERENCE = re.compile(r"scripts/ci/(\w+)\.py")


def _imported_names(clause: str) -> list[tuple[str, str]]:
    """(original, bound) pairs from an import clause, honouring ``as``."""
    pairs: list[tuple[str, str]] = []
    for part in clause.replace("(", " ").replace(")", " ").split(","):
        tokens = part.split()
        if not tokens:
            continue
        bound = tokens[2] if len(tokens) >= 3 and tokens[1] == "as" else tokens[0]
        pairs.append((tokens[0], bound))
    return pairs


def _from_import_aliases(source: str, stems: frozenset[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for module, clause in _FROM_IMPORT.findall(source):
        names = _imported_names(clause)
        if module == "scripts.ci":
            aliases.update({b: o for o, b in names if o in stems})
            continue
        stem = module.rsplit(".", 1)[-1]
        if stem in stems:
            aliases[stem] = stem
            aliases.update({bound: stem for _original, bound in names})
    return aliases


def _module_aliases(source: str, stems: frozenset[str]) -> dict[str, str]:
    """Names bound to a ``scripts/ci`` module in this test file, alias -> stem."""
    aliases = _from_import_aliases(source, stems)
    for module, alias in _PLAIN_IMPORT.findall(source):
        stem = module.rsplit(".", 1)[-1]
        if stem in stems:
            aliases[alias or stem] = stem
    for alias, stem in _LOADER_ALIAS.findall(source):
        if stem in stems:
            aliases[alias] = stem
    for stem, alias in _SYS_MODULES_ALIAS.findall(source):
        if stem in stems:
            aliases[alias] = stem
    return aliases


def _top_level_segments(source: str) -> list[str]:
    """Source of each top-level statement, so coverage is scoped, not file-wide.

    File-wide matching over-credits: ``tests/ci/test_pr_validation_workflow.py``
    drives five modules, so any nonzero assertion anywhere in it would vouch for
    all five. Scoping to the enclosing top-level test function or class keeps a
    newly added script from inheriting a sibling's coverage.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [source]
    lines = source.splitlines()
    return [
        "\n".join(lines[node.lineno - 1 : node.end_lineno or len(lines)])
        for node in tree.body
    ]


def _referenced_stems(source: str, stems: frozenset[str]) -> set[str]:
    """Every ``scripts/ci`` stem this file names, however it binds the module."""
    return {
        stem for stem in stems if re.search(rf"(?<![\w.]){re.escape(stem)}\b", source)
    }


def covered_stems(test_source: str, stems: frozenset[str]) -> set[str]:
    """Stems whose CLI this test file proves can exit nonzero.

    A single-subject test file is settled by a file-wide read: there is only one
    module it could be asserting about, and the binding styles in this repo run
    from ``from scripts.ci import x as y`` through a hand-rolled
    ``spec_from_file_location`` block, which no alias matcher covers completely.

    A multi-subject file needs scoping, because file-wide matching would let one
    module's nonzero assertion vouch for every other module in the same file.
    ``tests/ci/test_pr_validation_workflow.py`` drives five. There the search is
    per top-level statement, and a bound name matches only where nothing
    qualifies it, so a bare ``main(...)`` imported from module A does not credit
    A on a line that reads ``other_mod.main(...)``.
    """
    if not _NONZERO_EXIT_ASSERTION.search(test_source):
        return set()
    referenced = _referenced_stems(test_source, stems)
    if len(referenced) == 1:
        return set(referenced)

    aliases = _module_aliases(test_source, stems)
    covered: set[str] = set()
    for segment in _top_level_segments(test_source):
        if not _NONZERO_EXIT_ASSERTION.search(segment):
            continue
        covered.update(
            stem
            for alias, stem in aliases.items()
            if re.search(rf"(?<![\w.]){re.escape(alias)}\b", segment)
        )
        covered.update(_SCRIPT_PATH_REFERENCE.findall(segment))
    return covered


def _read(repo_root: Path, relative: str) -> str | None:
    try:
        return (repo_root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def uncovered_scripts(repo_root: Path) -> list[str] | None:
    """Script stems that define ``main`` with no test proving a nonzero exit."""
    scripts = tracked_files(repo_root, (_SCRIPT_GLOB,))
    if scripts is None:
        return None
    tests = tracked_files(repo_root, _TEST_GLOBS)
    if tests is None:
        return None

    stems = frozenset(Path(script).stem for script in scripts)
    covered: set[str] = set()
    for path in tests:
        source = _read(repo_root, path)
        if source is not None:
            covered |= covered_stems(source, stems)

    uncovered: list[str] = []
    for script in scripts:
        source = _read(repo_root, script)
        if source is None or not defines_main(source):
            continue
        stem = Path(script).stem
        if stem not in covered:
            uncovered.append(stem)
    return sorted(uncovered)


def current_count(repo_root: Path) -> int | None:
    """Count of uncovered scripts, or None when the tracked-file scan failed.

    Returning None rather than 0 on failure is load-bearing: a zero from a
    broken scan looks like a clean tree, and ``--update`` would write it into
    the baseline and permanently disarm the gate.
    """
    uncovered = uncovered_scripts(repo_root)
    if uncovered is None:
        return None
    for stem in uncovered:
        print(f"  scripts/ci/{stem}.py: no test asserts a nonzero exit from main()")
    return len(uncovered)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "CLI exit-contract ratchet for extracted CI scripts (issue #4068).",
        _BASELINE_PATH,
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="cli exit contract ratchet",
        counter=current_count,
        scan_error="could not list tracked files",
        regression_advice=(
            "A script under scripts/ci that defines main() must ship a test "
            "asserting a nonzero return from main() on a failure path the shell "
            "original failed on. Assert on main(argv), not on a helper's return "
            "value: a helper-level assertion cannot catch an exit-code defect "
            "(issue #4068)."
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
