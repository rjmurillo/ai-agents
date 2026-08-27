"""Static scan: which test functions can create a bare git repository, and where.

Issue #4698 acceptance criterion 3, "Fixture-creating tests are shown to write
bare repositories only under a temporary path." The gate added for criteria 1
and 2 (``scripts/validation/check_repo_health.py``) reports the damage after it
lands; this reports the shape that produces it before it merges.

The mechanism the issue names: ``core.bare`` is worktree-specific once
``extensions.worktreeConfig`` is on, so a ``git init --bare`` or a
``git config core.bare true`` that resolves against an inherited working
directory instead of a fixture path writes into the developer's shared
``.git/config`` and breaks the main worktree and every linked worktree at once.

Kept out of ``conftest.py`` deliberately: these helpers are specific to one
assertion, and a package-wide conftest name would be visible to every test
module. ``tests/gh_base_ref_test_helpers.py`` carries the same reasoning.

Refs #4698, #4717, #4287.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = PROJECT_ROOT / "tests"

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

# The only two spellings by which a git argument vector reaches a bare
# repository. `git init --bare`, `git clone --bare`, and
# `git config core.bare <value>` all carry one of them as a literal argument.
BARE_TOKENS = ("--bare", "core.bare")

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

# The scanner's own two modules hold the tokens as data rather than as git
# arguments, so scanning them reports the token table above and the negative
# controls in the test module. `TestTheScannerRunsNoGitCommand` keeps the
# exclusion honest by failing if either file ever spawns a process.
SCANNER_MODULES = frozenset(
    {
        "tests.bare_repo_scan",
        "tests.test_bare_repo_fixtures_are_temp_rooted",
    }
)

# Bound above the depth of any helper chain in the suite. Each round pulls the
# callers of one more level of unaccepted helpers. Exceeding it raises rather
# than reporting a clean scan of a call graph the walk never finished.
_MAX_ROUNDS = 8


@dataclass(frozen=True)
class Violation:
    """One bare-repository literal whose enclosing scope is not temp-rooted."""

    module: str
    lineno: int
    token: str
    scope: str
    reason: str

    def __str__(self) -> str:
        return f"{self.module}:{self.lineno}: {self.token!r} in {self.scope} -- {self.reason}"


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
        self.sites: list[tuple[str, int, FunctionNode | None, tuple[str, ...]]] = []
        self.imports: dict[str, tuple[str, str]] = {}
        self.name_reads: dict[str, set[FunctionNode]] = {}
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
            name = _callee_name(node)
            if name:
                self.calls.append((name, stack[-1] if stack else None))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and stack:
            self.name_reads.setdefault(node.id, set()).add(stack[-1])
        elif isinstance(node, ast.Constant) and node.value in BARE_TOKENS:
            enclosing = stack[-1] if stack else None
            bindings = () if enclosing else _binding_names(node, parents)
            self.sites.append((node.value, node.lineno, enclosing, bindings))
        return False


def _callee_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
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


def _has_fixture_decorator(node: FunctionNode) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "fixture":
            return True
        if isinstance(target, ast.Name) and target.id == "fixture":
            return True
    return False


class _Graph:
    """The call graph over the modules loaded so far."""

    def __init__(self) -> None:
        self.facts: dict[str, _ModuleFacts] = {}
        self.owner: dict[FunctionNode, tuple[str, str]] = {}
        self._by_qualified: dict[tuple[str, str], list[FunctionNode]] = {}
        self._by_name: dict[str, list[FunctionNode]] = {}

    def add(self, module: str, source: str) -> None:
        facts = _ModuleFacts(module, source)
        self.facts[module] = facts
        for node in facts.functions:
            self.owner[node] = (module, node.name)
            self._by_qualified.setdefault((module, node.name), []).append(node)
            self._by_name.setdefault(node.name, []).append(node)

    def resolve(self, module: str, name: str) -> list[FunctionNode]:
        """Candidate definitions for ``name`` as it is spelled inside ``module``.

        A same-module definition wins, then an explicit ``from X import name``,
        then every definition of that name anywhere loaded. That last rung is
        deliberately conservative: merging same-named helpers from two modules
        can only add callers, so it can reject a helper that would otherwise
        pass, never admit one that should fail.
        """
        local = self._by_qualified.get((module, name))
        if local:
            return local
        facts = self.facts.get(module)
        imported = facts.imports.get(name) if facts else None
        if imported and imported in self._by_qualified:
            return self._by_qualified[imported]
        return self._by_name.get(name, [])

    def callers(self) -> dict[FunctionNode, list[FunctionNode | None]]:
        edges: dict[FunctionNode, list[FunctionNode | None]] = {}
        for module, facts in self.facts.items():
            for name, enclosing in facts.calls:
                for target in self.resolve(module, name):
                    edges.setdefault(target, []).append(enclosing)
        return edges

    def accepted(self) -> set[FunctionNode]:
        """Fixed point over "every path this function builds is temp-rooted"."""
        accepted = {node for node in self.owner if _is_directly_temp_rooted(node)}
        edges = self.callers()
        changed = True
        while changed:
            changed = False
            for node, (module, _name) in self.owner.items():
                if node in accepted:
                    continue
                if self._takes_an_accepted_fixture(node, module, accepted):
                    accepted.add(node)
                    changed = True
                    continue
                incoming = edges.get(node, [])
                if incoming and all(c is not None and c in accepted for c in incoming):
                    accepted.add(node)
                    changed = True
        return accepted

    def _takes_an_accepted_fixture(
        self, node: FunctionNode, module: str, accepted: set[FunctionNode]
    ) -> bool:
        """A parameter naming an already-accepted fixture roots the body too.

        ``decoy_repo`` and ``git_sandbox`` are the live cases: both build their
        sandbox with ``tmp_path_factory`` or ``tempfile``, so a test requesting
        either receives a temp-rooted path. The ``@pytest.fixture`` check is
        load-bearing; without it any parameter that happened to share a name
        with an accepted function anywhere under ``tests/`` would launder the
        body.
        """
        return any(
            candidate in accepted and _has_fixture_decorator(candidate)
            for param in _parameter_names(node)
            for candidate in self.resolve(module, param)
        )


def scan(
    seed: Mapping[str, str],
    resolve_more: Callable[[str], Mapping[str, str]] | None = None,
) -> ScanResult:
    """Scan ``seed`` modules, pulling more through ``resolve_more`` when needed.

    ``resolve_more(name)`` returns modules that mention ``name``, so the walk
    reaches the callers of a helper defined in one file and used from another
    without parsing the whole tree.
    """
    graph = _Graph()
    for module, source in seed.items():
        graph.add(module, source)

    relevant: set[FunctionNode] = set()
    for _ in range(_MAX_ROUNDS):
        accepted = graph.accepted()
        relevant |= _site_scopes(graph)
        pending = {graph.owner[node][1] for node in relevant if node not in accepted}
        if not pending or resolve_more is None:
            return _report(graph, accepted)
        extra = {
            module: source
            for name in sorted(pending)
            for module, source in resolve_more(name).items()
            if module not in graph.facts
        }
        if not extra:
            return _report(graph, accepted)
        for module, source in extra.items():
            graph.add(module, source)
        edges = graph.callers()
        relevant |= {
            caller
            for node in list(relevant)
            for caller in edges.get(node, [])
            if caller is not None
        }
    raise AssertionError(
        f"call-graph walk did not settle in {_MAX_ROUNDS} rounds; reporting now "
        "would claim a clean result for a graph the walk never finished"
    )


def _site_scopes(graph: _Graph) -> set[FunctionNode]:
    """Functions that must be temp-rooted: site bodies, plus constant readers."""
    scopes: set[FunctionNode] = set()
    for facts in graph.facts.values():
        for _token, _lineno, enclosing, bindings in facts.sites:
            if enclosing is not None:
                scopes.add(enclosing)
                continue
            for binding in bindings:
                scopes |= facts.name_reads.get(binding, set())
    return scopes


_NO_TEMP_ROOT = (
    "no temp root: the function requests no pytest temp fixture, calls no "
    "tempfile factory, names no .pytest_tmp root, and at least one caller is "
    "itself not temp-rooted"
)


def _report(graph: _Graph, accepted: set[FunctionNode]) -> ScanResult:
    result = ScanResult(
        modules_parsed=len(graph.facts),
        functions_accepted=len(accepted),
        functions_seen=len(graph.owner),
    )
    for module, facts in sorted(graph.facts.items()):
        for token, lineno, enclosing, bindings in facts.sites:
            result.sites_examined += 1
            if enclosing is None:
                result.violations.extend(
                    _constant_violations(facts, module, token, lineno, bindings, accepted)
                )
            elif enclosing not in accepted:
                result.violations.append(
                    Violation(
                        module=module,
                        lineno=lineno,
                        token=token,
                        scope=f"{enclosing.name}()",
                        reason=_NO_TEMP_ROOT,
                    )
                )
    return result


def _constant_violations(
    facts: _ModuleFacts,
    module: str,
    token: str,
    lineno: int,
    bindings: tuple[str, ...],
    accepted: set[FunctionNode],
) -> Iterator[Violation]:
    readers = {r for b in bindings for r in facts.name_reads.get(b, set())}
    label = "/".join(bindings) or "<unbound>"
    for reader in sorted(readers, key=lambda node: node.lineno):
        if reader in accepted:
            continue
        yield Violation(
            module=module,
            lineno=lineno,
            token=token,
            scope=f"module constant {label} read by {reader.name}()",
            reason="the function that reads this constant is not temp-rooted",
        )


_SOURCE_CACHE: dict[str, str] | None = None


def scannable_sources() -> dict[str, str]:
    """Every scannable module under ``tests/``, read once and cached.

    Reading the working tree rather than a git ref is required here: a newly
    added test file is exactly the regression this guards, and
    ``.claude/rules/ci-scripts.md`` MUST 9 carves out pre-commit-shaped checks
    for that reason.
    """
    global _SOURCE_CACHE
    if _SOURCE_CACHE is None:
        cache: dict[str, str] = {}
        for path in sorted(TESTS_ROOT.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            module = ".".join(path.relative_to(PROJECT_ROOT).with_suffix("").parts)
            if module in SCANNER_MODULES:
                continue
            cache[module] = path.read_text(encoding="utf-8")
        _SOURCE_CACHE = cache
    return _SOURCE_CACHE


def modules_mentioning(needle: str) -> dict[str, str]:
    """Scannable modules whose text contains ``needle``.

    A text prefilter rather than a full-tree parse. Parsing all 1000-plus test
    modules to reach the 48 live literals cost 14.7s of CPU when measured; the
    prefilter parses only the 23 modules that can matter.
    """
    return {module: text for module, text in scannable_sources().items() if needle in text}


_SCAN_CACHE: ScanResult | None = None


def scan_test_suite() -> ScanResult:
    """Scan every bare-repository literal under ``tests/``, cached per session."""
    global _SCAN_CACHE
    if _SCAN_CACHE is None:
        seed: dict[str, str] = {}
        for token in BARE_TOKENS:
            seed.update(modules_mentioning(token))
        _SCAN_CACHE = scan(seed, resolve_more=modules_mentioning)
    return _SCAN_CACHE
