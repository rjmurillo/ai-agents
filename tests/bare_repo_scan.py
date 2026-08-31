"""Static scan: which test functions can create a bare git repository, and where.

Issue #4698 acceptance criterion 3, "Fixture-creating tests are shown to write
bare repositories only under a temporary path." The gate added for criteria 1
and 2 (``scripts/validation/check_repo_health.py``) reports the damage after it
lands; this reports the shape that produces it before it merges.

``tests/bare_repo_sites.py`` reads each module and answers what tokens are
written there. This module answers whether the corpus is safe, which takes two
things that file cannot see on its own:

* **The call graph.** A helper such as ``_init_git_repo`` in
  ``tests/gh_base_ref_test_helpers.py`` takes its target as a parameter, so it
  is safe exactly when every caller reached through the graph is temp-rooted.
  Callers live in other modules, which is what ``resolve_more`` pulls in.
* **The target trace.** Acceptance of the enclosing function is necessary and
  not sufficient: ``def test_x(tmp_path): subprocess.run(["git", "init",
  "--bare", "/home/user/live.git"])`` roots the function and writes a bare
  repository into a live checkout. :func:`_target_is_temp_rooted` follows the
  command's own argument, ``cwd=``, or command vector back to the root.

Both counts are reported next to the violations, because a violation count
alone cannot distinguish "nothing is wrong" from "nothing was examined"
(``.claude/rules/ci-scripts.md`` MUST-12).

Refs #4698, #4717, #4287.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping

from tests.bare_repo_sites import (
    BARE_TOKENS,
    PROJECT_ROOT,
    SCANNER_MODULES,
    TESTS_ROOT,
    FunctionNode,
    ScanResult,
    Site,
    Violation,
    _has_fixture_decorator,
    _is_directly_temp_rooted,
    _ModuleFacts,
    _parameter_names,
    _temp_rooted_names,
)

# Bound above the depth of any helper chain in the suite. Each round pulls the
# callers of one more level of unaccepted helpers. Exceeding it raises rather
# than reporting a clean scan of a call graph the walk never finished.
_MAX_ROUNDS = 8


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

    def vetted_parameters(self, node: FunctionNode, module: str) -> frozenset[str]:
        """Parameters whose values a caller or a fixture has already rooted.

        A function admitted by :meth:`accepted` because every caller is
        temp-rooted receives temp-rooted arguments, so its parameters carry the
        root inward. A function that roots itself does not get that credit for
        arbitrary parameters, or ``def test_x(tmp_path)`` would launder any
        literal path it also passes: there only the fixture parameters count.
        """
        parameters = _parameter_names(node)
        fixtures = frozenset(
            param
            for param in parameters
            for candidate in self.resolve(module, param)
            if _has_fixture_decorator(candidate)
        )
        if _is_directly_temp_rooted(node):
            return fixtures
        return fixtures | frozenset(parameters)

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
        for site in facts.sites:
            if site.enclosing is not None:
                scopes.add(site.enclosing)
                continue
            for binding in site.bindings:
                scopes |= facts.name_reads.get(binding, set())
    return scopes


_NO_TEMP_ROOT = (
    "no temp root: the function requests no pytest temp fixture, calls no "
    "tempfile factory, names no .pytest_tmp root, and at least one caller is "
    "itself not temp-rooted"
)

_TARGET_NOT_TRACED = (
    "the function is temp-rooted but this command's target is not: no argument "
    "of the git call, and no cwd= it is given, resolves back to a temp root"
)

_MODULE_LEVEL_CALL = (
    "a bare-repository command at module scope runs during import, against "
    "whatever directory collection happens to be in; bind it inside a "
    "temp-rooted function"
)


def _report(graph: _Graph, accepted: set[FunctionNode]) -> ScanResult:
    result = ScanResult(
        modules_parsed=len(graph.facts),
        functions_accepted=len(accepted),
        functions_seen=len(graph.owner),
    )
    for module, facts in sorted(graph.facts.items()):
        for site in facts.sites:
            result.sites_examined += 1
            result.violations.extend(_site_violations(graph, facts, module, site, accepted))
    return result


def _site_violations(
    graph: _Graph,
    facts: _ModuleFacts,
    module: str,
    site: Site,
    accepted: set[FunctionNode],
) -> Iterator[Violation]:
    """Every reason this one token is not shown to write under a temp root."""
    if site.enclosing is None:
        yield from _module_scope_violations(facts, module, site, accepted)
        return
    if site.enclosing not in accepted:
        yield Violation(
            module=module,
            lineno=site.lineno,
            token=site.token,
            scope=f"{site.enclosing.name}()",
            reason=_NO_TEMP_ROOT,
        )
        return
    if not site.environment and not _target_is_temp_rooted(graph, facts, module, site):
        yield Violation(
            module=module,
            lineno=site.lineno,
            token=site.token,
            scope=f"{site.enclosing.name}()",
            reason=_TARGET_NOT_TRACED,
        )


def _target_is_temp_rooted(
    graph: _Graph, facts: _ModuleFacts, module: str, site: Site
) -> bool:
    """Trace this command's target, or the vector carrying it, to a temp root."""
    scope = site.enclosing
    assert scope is not None
    rooted = _temp_rooted_names(scope, graph.vetted_parameters(scope, module))
    if site.references & rooted:
        return True
    # The build-then-run shape: the token was appended to a vector, so the
    # target travels with a later call that receives that vector.
    consumers = facts.call_references.get(scope, [])
    return any(
        site.carriers & names and names & rooted for names in consumers
    )


def _module_scope_violations(
    facts: _ModuleFacts,
    module: str,
    site: Site,
    accepted: set[FunctionNode],
) -> Iterator[Violation]:
    """A module-scope token is data until some function reads it, or a call.

    An unbound one is a call: ``subprocess.run(["git", "init", "--bare",
    "remote.git"])`` at module scope executes at import, during pytest
    collection, against the ambient working directory. It binds no name, so
    following bindings to their readers finds nothing and the old walk reported
    it clean. It is a violation on sight.
    """
    if not site.bindings:
        yield Violation(
            module=module,
            lineno=site.lineno,
            token=site.token,
            scope="module scope",
            reason=_MODULE_LEVEL_CALL,
        )
        return
    readers = {r for b in site.bindings for r in facts.name_reads.get(b, set())}
    label = "/".join(site.bindings)
    for reader in sorted(readers, key=lambda node: node.lineno):
        if reader in accepted:
            continue
        yield Violation(
            module=module,
            lineno=site.lineno,
            token=site.token,
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
