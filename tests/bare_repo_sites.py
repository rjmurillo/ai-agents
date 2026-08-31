"""What one module contributes to the bare-repository scan: its token sites.

Issue #4698 acceptance criterion 3, "Fixture-creating tests are shown to write
bare repositories only under a temporary path." Split from
``tests/bare_repo_scan.py``, which owns the call graph and the verdict, so both
stay under the 500-line taste ceiling. The seam is facts against judgement: this
module reads one file's syntax tree and answers what is written there, and
decides nothing about the corpus.

The mechanism the issue names: ``core.bare`` is worktree-specific once
``extensions.worktreeConfig`` is on, so a ``git init --bare`` or a
``git config core.bare true`` that resolves against an inherited working
directory instead of a fixture path writes into the developer's shared
``.git/config`` and breaks the main worktree and every linked worktree at once.

Two questions are answered per token, and the scan needs both:

* **Is this a command being built, or a value being compared?** Only the first
  can run. See ``_CONSTRUCTION_PARENTS``.
* **Which names could carry this command's target?** ``Site.references`` for a
  direct call, ``Site.carriers`` for the build-then-run shape. Temp-rooting the
  enclosing function says nothing about the path handed to git, so the verdict
  module traces one of these back to a root.

Kept out of ``conftest.py`` deliberately: these helpers are specific to one
assertion, and a package-wide conftest name would be visible to every test
module. ``tests/gh_base_ref_test_helpers.py`` carries the same reasoning.

Refs #4698, #4717, #4287.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = PROJECT_ROOT / "tests"

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

# The only two spellings by which a git argument vector reaches a bare
# repository. `git init --bare`, `git clone --bare`, and
# `git config core.bare <value>` all carry one of them as a literal argument.
BARE_TOKENS = ("--bare", "core.bare")

# A token counts as a site only where it is being BUILT into something a
# process could receive: an element of a list or tuple, a value in a dict, an
# argument to a call, or the right side of an assignment. A token being
# COMPARED is not a site, which is what keeps assertions and expected-message
# data out of the corpus: `assert "core.bare" in result.stderr` puts the token
# under an `ast.Compare`, and no construction node is its parent.
#
# The narrower rule of "only inside a subprocess call" was considered and
# rejected: it under-reports. `tests/gh_base_ref_test_helpers.py:26-30` builds
# `args = ["git", "init"]`, appends `--bare` conditionally, and passes `args` to
# `subprocess.run` two statements later, so a lexical test for a subprocess
# argument list sees no site at a call that really does create a bare
# repository. Carrier tracking below follows that shape instead.
_CONSTRUCTION_PARENTS = (
    ast.Call,
    ast.keyword,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.Assign,
    ast.AnnAssign,
    ast.Starred,
    ast.Return,
)

# Methods that append to a command vector already bound to a name. The token
# reaches a process through the name, not through this call's own arguments.
_VECTOR_MUTATORS = frozenset({"append", "extend", "insert"})

# Reaching git through the environment rather than through an argument vector.
# `GIT_CONFIG_KEY_0=core.bare` is the live case in
# `tests/test_git_isolation_blast_radius.py` and
# `tests/validation/test_check_repo_health_hostile_inputs.py`: git applies it to
# whatever repository the child process lands in.
_ENV_SETTERS = frozenset({"setenv", "putenv"})
_ENV_KEYWORD = "env"

# pytest's own temp fixtures. Requesting one roots every path the body derives
# from it under the session temp directory, outside every checkout.
_PYTEST_TEMP_PARAMS = frozenset(
    {"tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory"}
)

# stdlib temp factories, matched on the attribute or the bare name so both
# `tempfile.TemporaryDirectory()` and an imported `TemporaryDirectory()` count.
_TEMPFILE_FACTORIES = frozenset(
    {"TemporaryDirectory", "mkdtemp", "mkstemp", "NamedTemporaryFile"}
)

# This repository's durable fixture root, required by `.claude/rules/testing.md`
# MUST NOT 4 for fixtures that must outlive one test. `.gitignore` covers it and
# `validate_plugin_manifests.py` prunes it, so it is a temporary path in the
# sense the acceptance criterion means even though it sits inside the checkout.
_REPO_TEMP_ROOT = ".pytest_tmp"

# The scanner's own modules hold the tokens as data rather than as git
# arguments, so scanning them reports the token table above and the negative
# controls in the corpus test module. `TestTheScannerRunsNoGitCommand` keeps the
# exclusion honest by failing if any of them ever spawns a process.
# `tests/test_bare_repo_scan_targets.py` is deliberately NOT here: its controls
# carry the tokens inside longer source strings, so it scans clean from inside
# the corpus, which is a stronger position than an exclusion.
SCANNER_MODULES = frozenset(
    {
        "tests.bare_repo_scan",
        "tests.bare_repo_sites",
        "tests.test_bare_repo_fixtures_are_temp_rooted",
    }
)

@dataclass(frozen=True)
class Violation:
    """One bare-repository literal not traced to a temp-rooted target."""

    module: str
    lineno: int
    token: str
    scope: str
    reason: str

    def __str__(self) -> str:
        return f"{self.module}:{self.lineno}: {self.token!r} in {self.scope} -- {self.reason}"


@dataclass(frozen=True)
class Site:
    """One bare-repository token, with the names its command could reach.

    ``references`` are the names the token's own call hands over, which is where
    the target path or ``cwd=`` sits for a direct
    ``subprocess.run(["git", "init", "--bare", str(target)])``. ``carriers`` are
    the names the token flows into instead, for the build-then-run shape where
    the target reaches a later call.
    """

    token: str
    lineno: int
    enclosing: FunctionNode | None
    bindings: tuple[str, ...]
    references: frozenset[str]
    carriers: frozenset[str]
    # An environment site carries no path to trace: `GIT_CONFIG_KEY_0=core.bare`
    # names no repository, and git applies it wherever the child lands. The
    # question there is the one the call graph already answers, whether every
    # process the function can spawn runs under a temp root, so target tracing
    # is skipped rather than failed.
    environment: bool = False


@dataclass
class ScanResult:
    """What the scan examined and what it found. Both halves are required.

    A violation count alone cannot distinguish "nothing is wrong" from "nothing
    was examined" (`.claude/rules/ci-scripts.md` MUST 12), so callers assert on
    the examined counts too.
    """

    violations: list[Violation] = field(default_factory=list)
    modules_parsed: int = 0
    sites_examined: int = 0
    functions_accepted: int = 0
    functions_seen: int = 0


class _ModuleFacts:
    """The AST facts one module contributes to the scan."""

    def __init__(self, module: str, source: str) -> None:
        self.module = module
        self.functions: list[FunctionNode] = []
        self.calls: list[tuple[str, FunctionNode | None]] = []
        self.sites: list[Site] = []
        self.imports: dict[str, tuple[str, str]] = {}
        self.name_reads: dict[str, set[FunctionNode]] = {}
        # Every call's argument names, per enclosing function. A carrier is
        # traced by asking which calls in the same scope receive it.
        self.call_references: dict[FunctionNode | None, list[frozenset[str]]] = {}
        tree = ast.parse(source, filename=module)
        parents: dict[ast.AST, ast.AST] = {
            child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
        }
        self._walk(tree, [], parents)

    def _walk(
        self,
        node: ast.AST,
        stack: list[FunctionNode],
        parents: Mapping[ast.AST, ast.AST],
    ) -> None:
        pushed = self._record(node, stack, parents)
        for child in ast.iter_child_nodes(node):
            self._walk(child, stack, parents)
        if pushed:
            stack.pop()

    def _record(
        self,
        node: ast.AST,
        stack: list[FunctionNode],
        parents: Mapping[ast.AST, ast.AST],
    ) -> bool:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            self.functions.append(node)
            stack.append(node)
            return True
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                self.imports[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Call):
            scope = stack[-1] if stack else None
            name = _callee_name(node)
            if name:
                self.calls.append((name, scope))
            self.call_references.setdefault(scope, []).append(_argument_names(node))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and stack:
            self.name_reads.setdefault(node.id, set()).add(stack[-1])
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in BARE_TOKENS
            and isinstance(parents.get(node), _CONSTRUCTION_PARENTS)
        ):
            self._record_site(node, node.value, stack[-1] if stack else None, parents)
        return False

    def _record_site(
        self,
        node: ast.Constant,
        token: str,
        enclosing: FunctionNode | None,
        parents: Mapping[ast.AST, ast.AST],
    ) -> None:
        call = _enclosing_call(node, parents)
        references: frozenset[str] = frozenset()
        carriers = set(_binding_names(node, parents))
        if call is not None:
            receiver = _mutated_vector(call)
            if receiver is None:
                references = _argument_names(call)
            else:
                carriers.add(receiver)
        self.sites.append(
            Site(
                token=token,
                lineno=node.lineno,
                enclosing=enclosing,
                bindings=_binding_names(node, parents),
                references=references,
                carriers=frozenset(carriers),
                environment=_reaches_git_through_the_environment(node, call, parents),
            )
        )


def _callee_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _loaded_names(nodes: Iterable[ast.AST]) -> frozenset[str]:
    """Every name read anywhere inside ``nodes``."""
    return frozenset(
        sub.id
        for node in nodes
        for sub in ast.walk(node)
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
    )


def _argument_names(call: ast.Call) -> frozenset[str]:
    """Names a call hands over, which is where a target path or ``cwd=`` sits.

    The callee is excluded on purpose: ``_git(repo, ...)`` passes ``repo`` and
    names ``_git``, and only the first can be a path.
    """
    return _loaded_names([*call.args, *(keyword.value for keyword in call.keywords)])


def _mutated_vector(call: ast.Call) -> str | None:
    """Return the name a ``vector.append(...)`` style call mutates, or None."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _VECTOR_MUTATORS:
        if isinstance(func.value, ast.Name):
            return func.value.id
    return None


def _reaches_git_through_the_environment(
    node: ast.AST, call: ast.Call | None, parents: Mapping[ast.AST, ast.AST]
) -> bool:
    """True when the token is being written into a child process's environment.

    Two spellings: ``monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.bare")``, and
    a mapping handed to a spawn as ``env=``.
    """
    if call is not None and _callee_name(call) in _ENV_SETTERS:
        return True
    current: ast.AST | None = parents.get(node)
    while current is not None and not isinstance(current, ast.stmt):
        if isinstance(current, ast.keyword) and current.arg == _ENV_KEYWORD:
            return True
        current = parents.get(current)
    return False


def _enclosing_call(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> ast.Call | None:
    """Return the innermost call whose arguments contain ``node``, within one statement."""
    current = parents.get(node)
    while current is not None and not isinstance(current, ast.stmt):
        if isinstance(current, ast.Call):
            return current
        current = parents.get(current)
    return None


def _binding_names(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> tuple[str, ...]:
    """Names a module-scope literal is assigned to, walking up to the statement.

    A token at module scope runs no git command by itself. ``_HOSTILE_CONFIG``
    in ``tests/test_git_isolation_blast_radius.py`` is the live example: it
    holds ``core.bare`` as the payload a negative control injects into a child
    process. Attributing the site to the functions that read the binding follows
    the data to where a git command could actually see it.
    """
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, ast.Assign):
            return tuple(t.id for t in current.targets if isinstance(t, ast.Name))
        if isinstance(current, ast.AnnAssign) and isinstance(current.target, ast.Name):
            return (current.target.id,)
        current = parents.get(current)
    return ()


def _parameter_names(node: FunctionNode) -> list[str]:
    args = node.args
    names = [arg.arg for arg in args.posonlyargs + args.args + args.kwonlyargs]
    if args.vararg:
        names.append(args.vararg.arg)
    if args.kwarg:
        names.append(args.kwarg.arg)
    return names


def _is_directly_temp_rooted(node: FunctionNode) -> bool:
    """True when the function establishes a temp root without help from callers."""
    if _PYTEST_TEMP_PARAMS.intersection(_parameter_names(node)):
        return True
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            name = _callee_name(sub)
            if name in _TEMPFILE_FACTORIES:
                return True
        if isinstance(sub, ast.Constant) and sub.value == _REPO_TEMP_ROOT:
            return True
    return False


def _bound_names(target: ast.AST) -> list[str]:
    """Names one assignment target binds, unpacking tuples and lists.

    ``bare, linked = _make_bare_with_worktree(tmp_path)`` is the live shape;
    reading only ``ast.Name`` targets loses both names and reports the two paths
    they hold as untraced.
    """
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple | ast.List):
        return [name for element in target.elts for name in _bound_names(element)]
    if isinstance(target, ast.Starred):
        return _bound_names(target.value)
    return []


def _assignment_targets(node: ast.AST) -> tuple[list[str], list[ast.AST]]:
    """Return ``(names bound, expressions bound from)`` for one statement."""
    if isinstance(node, ast.Assign):
        names = [name for target in node.targets for name in _bound_names(target)]
        return names, [node.value]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id], [node.value] if node.value else []
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return _bound_names(node.optional_vars), [node.context_expr]
    return [], []


def _roots_a_path(sources: Iterable[ast.AST], known: frozenset[str]) -> bool:
    """True when an expression derives from a temp root already established."""
    for source in sources:
        for sub in ast.walk(source):
            if isinstance(sub, ast.Call) and _callee_name(sub) in _TEMPFILE_FACTORIES:
                return True
            if isinstance(sub, ast.Constant) and sub.value == _REPO_TEMP_ROOT:
                return True
            if isinstance(sub, ast.Name) and sub.id in known:
                return True
    return False


def _temp_rooted_names(node: FunctionNode, seeds: frozenset[str]) -> frozenset[str]:
    """Return every name in ``node`` that holds a path under a temp root.

    Starts from ``seeds`` (the parameters a caller or fixture has already
    vetted) and reaches a fixed point over assignments and ``with`` bindings, so
    ``bare = tmp_path / name`` carries the root that ``tmp_path`` established.

    This is what makes the scan a claim about the target rather than about the
    function. Temp-rooting the enclosing function is not evidence that the git
    command uses that path: ``def test_x(tmp_path): subprocess.run(["git",
    "init", "--bare", "/home/user/live.git"])`` roots the function and writes
    the bare repository into a live checkout.
    """
    known = set(seeds)
    known.update(_PYTEST_TEMP_PARAMS.intersection(_parameter_names(node)))
    changed = True
    while changed:
        changed = False
        for sub in ast.walk(node):
            names, sources = _assignment_targets(sub)
            fresh = [name for name in names if name not in known]
            if fresh and _roots_a_path(sources, frozenset(known)):
                known.update(fresh)
                changed = True
    return frozenset(known)


def _has_fixture_decorator(node: FunctionNode) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "fixture":
            return True
        if isinstance(target, ast.Name) and target.id == "fixture":
            return True
    return False
