"""Does a test file prove an extracted CI script's CLI can exit nonzero?

Split out of ``cli_exit_contract_ratchet``, which owns the counting and the
ratchet policy. This module owns the one question the gate turns on, and the
answer is deliberately narrow: a nonzero assertion counts only where the same
test function drives that script's CLI. See the ratchet's module docstring for
why (issue #4068).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from functools import lru_cache

__all__ = ["covered_stems", "defines_main"]

# The four assertion shapes that report a nonzero exit. Each is written against
# the forms already in tests/ci; a new shape widens this pattern rather than
# exempting the script.
#
#   assert main(["--bad"]) == 1
#   assert main([]) == EXIT_CONFIG          (any EXIT_ name that is not success)
#   assert main([]) == EXTERNAL_ERROR       (the other constant style in this tree)
#   assert result.returncode == 2           (subprocess-driven CLI)
#   assert excinfo.value.code != 0          (pytest.raises(SystemExit))
#
# Matching one of these is necessary, never sufficient: ``covered_stems`` also
# requires the assertion to sit in a test function that drives the script's CLI.
_NONZERO_EXIT_ASSERTION = re.compile(
    r"""
      main\(.*\)\s*(?:==\s*[1-9]|!=\s*0)
    | ==\s*(?:[A-Za-z_][\w.]*\.)?EXIT_(?!OK\b|SUCCESS\b)[A-Z][A-Z_]*
    | ==\s*(?:[A-Za-z_][\w.]*\.)?[A-Z][A-Z_]*_ERROR\b
    | returncode\s*(?:==\s*[1-9]|!=\s*0)
    | \.code\s*(?:==\s*[1-9]|!=\s*0)
    """,
    re.VERBOSE,
)


# A superset of every proof shape, used only to skip files that cannot credit
# anything before paying for a parse.
_ANY_NONZERO_COMPARISON = re.compile(r"==\s*[1-9]|!=\s*0|EXIT_|_ERROR")


@lru_cache(maxsize=4)
def _stem_probe(stems: frozenset[str]) -> re.Pattern[str]:
    """One alternation over the tracked stems, reused across the whole corpus.

    Compiled once per stem set rather than once per file: the ratchet calls
    ``covered_stems`` for every tracked test file with the same set, and the
    merge-tree ratchet calls it a second time against the merged tree.
    """
    return re.compile("|".join(sorted(map(re.escape, stems))))


# An identifier that nothing qualifies, so `widget` counts and `pkg.widget`
# does not.
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
_LOADER_ALIAS = re.compile(
    r"^[ \t]*(\w+)\s*=\s*(?:_load_module|_import_script)\(\s*[\"'](\w+)[\"']",
    re.MULTILINE,
)
_SPEC_FROM_FILE_LOCATION_ALIAS = re.compile(
    r"^[ \t]*(\w+)\s*=\s*importlib\.util\.spec_from_file_location\(\s*[\"'](\w+)[\"']",
    re.MULTILINE,
)
_MODULE_FROM_SPEC_ALIAS = re.compile(
    r"^[ \t]*(\w+)\s*=\s*importlib\.util\.module_from_spec\(\s*(\w+)\s*\)",
    re.MULTILINE,
)
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
_UNQUALIFIED_NAME = re.compile(r"(?<![\w.])([A-Za-z_]\w*)")


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


def _spec_from_file_aliases(source: str, stems: frozenset[str]) -> dict[str, str]:
    """Module aliases created through importlib spec loaders."""
    spec_aliases = {
        alias: stem
        for alias, stem in _SPEC_FROM_FILE_LOCATION_ALIAS.findall(source)
        if stem in stems
    }
    aliases: dict[str, str] = {}
    for alias, spec_name in _MODULE_FROM_SPEC_ALIAS.findall(source):
        stem = spec_aliases.get(spec_name)
        if stem is not None:
            aliases[alias] = stem
    return aliases


def _spec_loader_stem(node: ast.AST, stems: frozenset[str]) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "spec_from_file_location":
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    if not isinstance(node.args[0].value, str):
        return None
    return node.args[0].value if node.args[0].value in stems else None


def _helper_loader_stems(tree: ast.Module, stems: frozenset[str]) -> dict[str, str]:
    helper_stems: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if stem := _spec_loader_stem(inner, stems):
                helper_stems[node.name] = stem
    return helper_stems


def _helper_loader_aliases(source: str, stems: frozenset[str]) -> dict[str, str]:
    """Aliases assigned from local helpers that import one tracked script."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    helper_stems = _helper_loader_stems(tree, stems)
    aliases: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name):
            continue
        stem = helper_stems.get(node.value.func.id)
        if stem is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                aliases[target.id] = stem
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
    aliases.update(_spec_from_file_aliases(source, stems))
    aliases.update(_helper_loader_aliases(source, stems))
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


def _compute_main_credit(
    tree: ast.Module, stems: frozenset[str], aliases: dict[str, str], referenced: set[str]
) -> dict[int, frozenset[str]]:
    """Per-function bare-main credit via source-ordered state tracking."""
    from scripts.ci._main_binding import compute_bare_credit

    return compute_bare_credit(tree, stems, aliases, referenced)



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
    """Every script stem this file names, however it binds the module.

    One pass over the file's unqualified identifiers rather than one regex per
    stem. With 69 tracked scripts the per-stem form was two thirds of the gate's
    runtime.
    """
    return set(_UNQUALIFIED_NAME.findall(source)) & stems


@dataclass(frozen=True)
class _Bindings:
    """How one test file names the scripts it drives."""

    aliases: dict[str, str]  # module alias -> stem
    main_credit: dict[int, frozenset[str]]  # func lineno -> bare main() credit stems
    paths: dict[str, set[str]]  # local name holding a script path -> stems
    stems: frozenset[str]


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _stems_in_text(text: str, stems: frozenset[str]) -> set[str]:
    return set(_SCRIPT_FILE_NAME.findall(text)) & stems


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


def _main_target(
    func: ast.expr, binding: _Bindings, bare_credit: frozenset[str]
) -> set[str]:
    """Stems a ``main`` call belongs to.

    Qualified calls (``widget.main()``) resolve through aliases.  Bare
    ``main()`` calls credit only the stems determined by source-ordered
    binding-state analysis at the enclosing function's definition point.
    """
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        stem = binding.aliases.get(func.value.id)
        if stem is not None:
            return {stem}
        return set()
    return set(bare_credit)


def _invocation_stems(
    node: ast.Call,
    binding: _Bindings,
    helpers: dict[str, set[str]],
    bare_credit: frozenset[str],
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
        return _main_target(node.func, binding, bare_credit)
    if name in _PROCESS_CALLEES:
        return _expression_stems(node, binding.paths, binding.stems)
    return set(helpers.get(name, set()))


def _scope_invocations(
    scope: ast.AST,
    binding: _Bindings,
    helpers: dict[str, set[str]],
    bare_credit: frozenset[str] = frozenset(),
) -> tuple[set[str], set[str]]:
    """(stems this scope drives, names it binds to the result of driving one)."""
    driven: set[str] = set()
    results: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            driven |= _invocation_stems(node, binding, helpers, bare_credit)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _invocation_stems(node.value, binding, helpers, bare_credit):
                results |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return driven, results


def _helper_stems(
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef], binding: _Bindings
) -> dict[str, set[str]]:
    """Locally defined functions that drive a CLI, name -> stems.

    One pass in definition order, so a helper that calls an earlier helper still
    resolves. A helper defined after its caller does not, and no test in this
    repo is written that way.

    Tests wrap the invocation often enough to matter: ``tests/test_run_with_retry.py``
    runs the script inside a module-level ``_run`` helper and asserts on
    ``result.returncode`` in every test method.
    """
    helpers: dict[str, set[str]] = {}
    for function in functions:
        credit = binding.main_credit.get(function.lineno, frozenset())
        driven, _results = _scope_invocations(function, binding, helpers, credit)
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
    aliases = _module_aliases(test_source, stems)
    referenced = _referenced_stems(test_source, stems)
    main_credit = _compute_main_credit(tree, stems, aliases, referenced)
    return _Bindings(
        aliases=aliases,
        main_credit=main_credit,
        paths=_path_names(tree, stems),
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
    # Cheap bail before the parse: a file with no nonzero comparison anywhere
    # cannot credit anything, and most test files are that. The pattern is a
    # superset of both proof forms, including the two-step `assert rc == 1`
    # that _proves_failure resolves through a bound name.
    if not _ANY_NONZERO_COMPARISON.search(test_source):
        return set()
    # Second cheap bail, and the one that pays (issue #4876). Every credit this
    # function can return names a stem that appears verbatim in the source:
    # module aliases resolve through the module path, path credit matches
    # ``<stem>.py`` inside a string, bare-``main`` credit intersects the file's
    # identifiers, and the return value is intersected with ``stems`` besides.
    # So a file naming no stem at all is decided here instead of through a
    # parse and six tree walks. Measured on this corpus: 207 of 1092 tracked
    # test files name one, and the gate's counting pass dropped from 16.9s to
    # 7.2s, in a ratchet the aggregate runs twice (once directly, once inside
    # the merge-tree ratchet) against an 85 second shared deadline.
    #
    # Substring, not identifier, on purpose. ``_UNQUALIFIED_NAME`` skips a name
    # preceded by a dot, so it would miss the ``"pkg/a.b.widget.py"`` shape that
    # ``_SCRIPT_FILE_NAME`` credits. A superset cannot drop a credit.
    if not stems or not _stem_probe(stems).search(test_source):
        return set()
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
        credit = binding.main_credit.get(scope.lineno, frozenset())
        driven, results = _scope_invocations(scope, binding, helpers, credit)
        if not driven:
            continue
        segment = "\n".join(lines[scope.lineno - 1 : scope.end_lineno or len(lines)])
        if _proves_failure(segment, results):
            covered |= driven
    return covered & stems
