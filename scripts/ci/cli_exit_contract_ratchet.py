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
mechanically decidable and catches every one of those shapes at once.

Crediting is deliberately narrow, because a gate that credits the defect shape
is worse than no gate. A nonzero assertion counts only when it shares a test
function with an invocation of that script's ``main`` or with a subprocess call
naming that script's path. Anything looser re-admits the hole: an earlier
revision of this file credited any nonzero assertion anywhere in a file that
named one module, which blessed three helper-only test files, and credited a
bare ``"scripts/ci/<stem>.py"`` string in a workflow-wiring assertion, which is
the first test an extraction PR writes.

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
from dataclasses import dataclass
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

# Both directories hold ADR-006 extraction output and both are invoked straight
# from workflow ``run:`` blocks, so both carry the same exit contract.
_SCRIPT_GLOBS = ("scripts/ci/*.py", ".github/scripts/*.py")
_TEST_GLOBS = ("tests/**/*.py", "tests/*.py")

# The four assertion shapes that report a nonzero exit. Each is written against
# the forms already in tests/ci; a new shape widens this pattern rather than
# exempting the script.
#
#   assert main(["--bad"]) == 1
#   assert main([]) == EXIT_CONFIG          (any EXIT_ name that is not success)
#   assert result.returncode == 2           (subprocess-driven CLI)
#   assert excinfo.value.code != 0          (pytest.raises(SystemExit))
#
# Matching one of these is necessary, never sufficient: ``covered_stems`` also
# requires the assertion to sit in a test function that drives the script's CLI.
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

# A subprocess-driven CLI names the script by file name instead of importing it.
# The match is intersected with the tracked stems, so a bare `<name>.py` is only
# read as a script reference when a script by that name exists.
_SCRIPT_FILE_NAME = re.compile(r"(\w+)\.py")

# The callees that start a process. A path string inside one of these is a CLI
# invocation; the same string inside an ``assert "... x.py" in workflow`` is a
# wiring assertion and proves nothing about the exit code.
_PROCESS_CALLEES = frozenset({"run", "check_output", "check_call", "call", "Popen"})


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


def _bare_main_stems(source: str, stems: frozenset[str]) -> set[str]:
    """Stems whose ``main`` this file imported under its own name.

    ``from require_job_results import failures, main`` makes a later bare
    ``main([])`` an invocation of that module's CLI.
    """
    bound: set[str] = set()
    for module, clause in _FROM_IMPORT.findall(source):
        if "main" not in {name for _original, name in _imported_names(clause)}:
            continue
        stem = module.rsplit(".", 1)[-1]
        if stem in stems:
            bound.add(stem)
    return bound


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function body in the file, method or not.

    The scope has to be the function, not the top-level statement. Class-scoped
    matching credited ``show_generated_agent_diff``: one method asserted a
    helper raised with ``returncode == 128`` and a different method in the same
    class called ``main``, which returns 0 on that very failure.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _referenced_stems(source: str, stems: frozenset[str]) -> set[str]:
    """Every script stem this file names, however it binds the module."""
    return {
        stem for stem in stems if re.search(rf"(?<![\w.]){re.escape(stem)}\b", source)
    }


@dataclass(frozen=True)
class _Bindings:
    """How one test file names the scripts it drives."""

    aliases: dict[str, str]  # module alias -> stem
    bare: frozenset[str]  # stems whose `main` is bound under that bare name
    paths: dict[str, set[str]]  # local name holding a script path -> stems
    sole: str | None  # the only stem the file names, when it names one
    stems: frozenset[str]


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _stems_in_text(text: str, stems: frozenset[str]) -> set[str]:
    return {match for match in _SCRIPT_FILE_NAME.findall(text)} & stems


def _expression_stems(
    node: ast.AST, paths: dict[str, set[str]], stems: frozenset[str]
) -> set[str]:
    """Script stems an expression names, by literal path or by a bound name."""
    found: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            found |= _stems_in_text(inner.value, stems)
        elif isinstance(inner, ast.Name):
            found |= paths.get(inner.id, set())
    return found


def _path_names(tree: ast.Module, stems: frozenset[str]) -> dict[str, set[str]]:
    """Local names that hold a script path, name -> stems.

    ``SCRIPT = REPO / ".github" / "scripts" / "run_with_retry.py"`` then
    ``subprocess.run([sys.executable, str(SCRIPT), ...])``. Two passes so a
    command list assembled from such a name resolves too.
    """
    paths: dict[str, set[str]] = {}
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    for _hop in range(2):
        for node in assignments:
            found = _expression_stems(node.value, paths, stems)
            if not found:
                continue
            for target in node.targets:
                for leaf in ast.walk(target):
                    if isinstance(leaf, ast.Name):
                        paths.setdefault(leaf.id, set()).update(found)
    return paths


def _main_target(func: ast.expr, binding: _Bindings) -> set[str]:
    """Stems a ``main`` call belongs to.

    ``sole`` is the file's only referenced stem, when it has exactly one. It
    covers the bindings no alias matcher reaches: a hand-rolled
    ``spec_from_file_location`` block binds ``mod``, and ``main = _mod.main``
    binds nothing at all. Naming one script and calling ``main`` is unambiguous.
    """
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        stem = binding.aliases.get(func.value.id)
        if stem is not None:
            return {stem}
    targets = set(binding.bare)
    if binding.sole is not None:
        targets.add(binding.sole)
    return targets


def _invocation_stems(
    node: ast.Call, binding: _Bindings, helpers: dict[str, set[str]]
) -> set[str]:
    """Stems whose CLI this call drives: its ``main``, its path, or a helper.

    A path string only counts inside a process-starting call. The same string in
    an ``assert "python3 scripts/ci/newthing.py" in workflow`` is a wiring
    assertion, and crediting it let an extraction PR satisfy the gate with the
    first test it writes.
    """
    name = _callee_name(node.func)
    if name is None:
        return set()
    if name == "main":
        return _main_target(node.func, binding)
    if name in _PROCESS_CALLEES:
        return _expression_stems(node, binding.paths, binding.stems)
    return set(helpers.get(name, set()))


def _scope_invocations(
    scope: ast.AST, binding: _Bindings, helpers: dict[str, set[str]]
) -> tuple[set[str], set[str]]:
    """(stems this scope drives, names it binds to the result of driving one)."""
    driven: set[str] = set()
    results: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            driven |= _invocation_stems(node, binding, helpers)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _invocation_stems(node.value, binding, helpers):
                results |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return driven, results


def _helper_stems(
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef], binding: _Bindings
) -> dict[str, set[str]]:
    """Locally defined functions that drive a CLI, name -> stems.

    Tests wrap the invocation often enough to matter: ``tests/test_run_with_retry.py``
    runs the script inside a module-level ``_run`` helper and asserts on
    ``result.returncode`` in every test method.
    """
    helpers: dict[str, set[str]] = {}
    for _hop in range(2):
        for function in functions:
            driven, _results = _scope_invocations(function, binding, helpers)
            if driven:
                helpers.setdefault(function.name, set()).update(driven)
    return helpers


def _proves_failure(segment: str, results: set[str]) -> bool:
    """True when this scope reports a nonzero exit.

    ``results`` holds the names bound to a CLI invocation, so the two-step form
    (``rc = main([...])`` then ``assert rc == 1``) counts without letting an
    unrelated ``assert count == 3`` count anywhere.
    """
    if _NONZERO_EXIT_ASSERTION.search(segment):
        return True
    return any(
        re.search(rf"(?<![\w.]){re.escape(name)}(?:\.\w+)?\s*(?:==\s*[1-9]|!=\s*0)", segment)
        for name in results
    )


def _bindings(test_source: str, tree: ast.Module, stems: frozenset[str]) -> _Bindings:
    referenced = _referenced_stems(test_source, stems)
    return _Bindings(
        aliases=_module_aliases(test_source, stems),
        bare=frozenset(_bare_main_stems(test_source, stems)),
        paths=_path_names(tree, stems),
        sole=next(iter(referenced)) if len(referenced) == 1 else None,
        stems=stems,
    )


def covered_stems(test_source: str, stems: frozenset[str]) -> set[str]:
    """Stems whose CLI this test file proves can exit nonzero.

    A stem is credited when one test function both reports a nonzero exit and
    drives that script's CLI, by calling its ``main`` or by running its path in
    a subprocess. Requiring both in one function is what separates a proof from
    a coincidence: a helper-level ``assert helper() == EXIT_VIOLATIONS`` says the
    helper reports failure and says nothing about what the process returns, which
    is the exact defect this gate exists to block (issue #4068).
    """
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return set()

    binding = _bindings(test_source, tree, stems)
    functions = _test_functions(tree)
    helpers = _helper_stems(functions, binding)

    lines = test_source.splitlines()
    covered: set[str] = set()
    for scope in functions:
        driven, results = _scope_invocations(scope, binding, helpers)
        if not driven:
            continue
        segment = "\n".join(lines[scope.lineno - 1 : scope.end_lineno or len(lines)])
        if _proves_failure(segment, results):
            covered |= driven
    return covered & stems


def _read(repo_root: Path, relative: str) -> str | None:
    try:
        return (repo_root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def uncovered_scripts(repo_root: Path) -> list[str] | None:
    """Script paths that define ``main`` with no test proving a nonzero exit."""
    scripts = tracked_files(repo_root, _SCRIPT_GLOBS)
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
        if Path(script).stem not in covered:
            uncovered.append(script)
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
    for script in uncovered:
        print(f"  {script}: no test asserts a nonzero exit from main()")
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
