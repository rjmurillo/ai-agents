"""Every script under scripts/validation and build/scripts must have a caller.

The sibling module ``test_ci_scripts_are_wired`` asks whether a workflow step
names a script literally. That is the right question for ``scripts/ci``, where
every guard is invoked directly, and it found nothing there.

Pointed at the two larger directories the same question reports 59 of 89
scripts unwired (issue #3341). That number is an artifact of the model, not a
defect count. Most of those scripts are invoked through an aggregator
(``pre_pr.py``, ``build_all.py``), imported as a library by something a
workflow does run, or called from a hook or a skill. Literal reference cannot
see any of that, and an allowlist with 59 entries would reproduce the defect
from #3329 with extra ceremony: a list nobody reads, silencing a guard nobody
trusts.

This asks the question the failure mode actually poses. #3329 was two guards
that shipped with green tests and no caller anywhere. So: is this script
reachable from anything that runs? Reachability follows imports and executable
script-path literals, ignoring comments and docstrings, transitively from three
entry surfaces:

- a live ``run:`` body in a workflow or composite action
- a git hook, via ``lefthook.yml`` or ``.githooks/``
- a skill, via helper scripts named by its ``SKILL.md``

Workflow, hook, and skill documentation can name an entry point. Once a
``SKILL.md`` names a helper script, the graph follows that helper's imports and
executable string literals.

Under that model the same 89 scripts yield three unreachable, each of which is a
real decision recorded in ``_NO_CALLER`` below rather than a bulk exemption.

What this does not do: prove the caller is correct, or that the script would
pass if run. Both of the entries below are unreachable precisely because
they fail against the current tree, which is tracked separately. Reachability
is the floor, not the ceiling.
"""

from __future__ import annotations

import ast
import functools
import re
import sys
from pathlib import Path

import pytest

from tests.ci.test_ci_scripts_are_wired import _live_run_blocks, _strip_commented_lines

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARDED_DIRS = ("scripts/validation", "build/scripts")

# Spelled-out counts, so the module docstring can be checked against reality.
_NUMBER_WORDS = {
    0: "no",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}

# Directories searched when following a reference from one script to another.
_CALLER_ROOTS = (
    "scripts",
    "build",
    ".claude/hooks",
    ".claude/skills",
    "src/copilot-cli/skills",
    "src/claude",
)

# Scripts with no caller on any entry surface. Each needs a non-empty reason,
# so adding one is a decision rather than a way to silence this test.
_NO_CALLER: dict[str, str] = {
    "scripts/validation/validate_seed_parity.py": (
        "Forensic tool, and its own module docstring says so: 'This is a "
        "FORENSIC TOOL, not a regression gate. Do NOT add it to CI.' It answers "
        "a one-time historical question about how the review axes under "
        "REQ-008 were seeded. Wiring it would make it a gate it was explicitly "
        "written not to be."
    ),
    "scripts/validation/check_dual_priority_labels.py": (
        "Queries the GitHub issue and PR label sets, so it needs a token and "
        "network and gates nothing in a diff. It is a triage report for #2623, "
        "not a code gate: a PR cannot introduce a duplicate priority label on "
        "an issue. Belongs on a schedule, which does not exist yet."
    ),
    "scripts/validation/check_ruleset_params_drift.py": (
        "Queries the live GitHub API for ruleset parameters, so it needs gh "
        "auth and network. A PR cannot change a ruleset setting. Designed for "
        "on-demand and scheduled use to detect server-side drift (#4646)."
    ),
}


def _guarded_scripts() -> list[Path]:
    scripts: list[Path] = []
    for directory in _GUARDED_DIRS:
        base = _REPO_ROOT / directory
        if base.is_dir():
            scripts.extend(p for p in sorted(base.glob("*.py")) if p.name != "__init__.py")
    return scripts


@functools.lru_cache(maxsize=1)
def _python_sources() -> tuple[Path, ...]:
    skip = ("__pycache__", ".venv", ".cache", "worktrees", "node_modules")
    sources: list[Path] = []
    for root in _CALLER_ROOTS:
        base = _REPO_ROOT / root
        if not base.is_dir():
            continue
        sources.extend(
            p
            for p in base.rglob("*.py")
            if not any(s in p.relative_to(_REPO_ROOT).parts for s in skip)
        )
    return tuple(sources)


def test_python_sources_keeps_checkout_nested_under_worktrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skip tokens are path-relative so agent worktree parents do not hide all files."""
    repo = tmp_path / ".claude" / "worktrees" / "issue-4159"
    included = repo / "scripts" / "caller.py"
    relative_skip = repo / "scripts" / "worktrees" / "scratch.py"
    cache_skip = repo / "scripts" / "__pycache__" / "cached.py"
    for source in (included, relative_skip, cache_skip):
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('reachable')\n", encoding="utf-8")

    monkeypatch.setattr(sys.modules[__name__], "_REPO_ROOT", repo)
    _python_sources.cache_clear()
    try:
        assert _python_sources() == (included,)
    finally:
        _python_sources.cache_clear()


def _module_name(rel: str) -> str:
    module = rel[: -len(".py")].replace("/", ".")
    return module.removesuffix(".__init__")


def _imported_modules(tree: ast.AST, caller: str) -> set[str]:
    """Resolve import statements to in-repo module names."""
    modules: set[str] = set()
    caller_module = _module_name(caller)
    package = caller_module if caller.endswith("/__init__.py") else caller_module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".") if package else []
                keep = max(0, len(parts) - node.level + 1)
                prefix = ".".join(parts[:keep])
                base = ".".join(part for part in (prefix, node.module or "") if part)
            else:
                base = node.module or ""
            if base:
                modules.add(base)
            for alias in node.names:
                if alias.name != "*":
                    modules.add(".".join(part for part in (base, alias.name) if part))
    return modules


_EXECUTION_CALLS = frozenset(
    {
        "call",
        "check_call",
        "check_output",
        "exec",
        "execv",
        "execve",
        "execute",
        "invoke",
        "launch",
        "popen",
        "run",
        "run_command",
        "run_path",
        "spawnv",
    }
)


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        return node.attr.lower()
    return ""


def _is_execution_call(name: str) -> bool:
    return name.strip("_") in _EXECUTION_CALLS or any(
        marker in name for marker in ("subprocess", "execute", "invoke", "launch", "popen", "spawn")
    )


def _string_literals(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _execution_string_literals(tree: ast.AST) -> set[str]:
    """Return strings passed positionally to execution-like calls."""
    bindings: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        strings = _string_literals(value)
        for target in targets:
            if isinstance(target, ast.Name):
                bindings.setdefault(target.id, set()).update(strings)

    literals: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_execution_call(_call_name(node.func)):
            continue
        for argument in node.args:
            literals.update(_string_literals(argument))
            literals.update(
                literal
                for child in ast.walk(argument)
                if isinstance(child, ast.Name)
                for literal in bindings.get(child.id, ())
            )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value.lower() in {"command", "driver", "executable", "script"}
            ):
                literals.update(_string_literals(value))
    return literals


@functools.lru_cache(maxsize=1)
def _source_paths() -> tuple[str, ...]:
    return tuple(path.relative_to(_REPO_ROOT).as_posix() for path in _python_sources())


@functools.lru_cache(maxsize=1)
def _source_index() -> dict[str, tuple[str, ...]]:
    """Every in-repo Python source under `_CALLER_ROOTS`, keyed by module name."""
    index: dict[str, list[str]] = {}
    for rel in _source_paths():
        index.setdefault(_module_name(rel), []).append(rel)
    return {module: tuple(paths) for module, paths in index.items()}


@functools.lru_cache(maxsize=1)
def _source_paths_by_name() -> dict[str, tuple[str, ...]]:
    by_name: dict[str, list[str]] = {}
    for rel in _source_paths():
        by_name.setdefault(Path(rel).name, []).append(rel)
    return {name: tuple(paths) for name, paths in by_name.items()}


def _mentions_token(text: str, token: str) -> bool:
    return re.search(rf"(?<![\w.-]){re.escape(token)}(?![\w.-])", text) is not None


_SCRIPT_TOKEN_RE = re.compile(r"(?<![\w.-])(?:[\w.-]+/)*[\w.-]+\.py(?![\w.-])")
_MODULE_TOKEN_RE = re.compile(r"(?<![\w.-])[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,}(?![\w.-])")


def _invoked_scripts(tree: ast.AST, caller: str) -> set[str]:
    """Resolve script paths passed to execution-like calls without basename collisions."""
    caller_dir = Path(caller).parent
    invoked: set[str] = set()
    source_paths = frozenset(_source_paths())
    for literal in _execution_string_literals(tree):
        normalized = literal.replace("\\", "/")
        for token in _SCRIPT_TOKEN_RE.findall(normalized):
            rel_token = token.lstrip("/")
            if rel_token in source_paths:
                invoked.add(rel_token)
                continue
            name = Path(token).name
            matches = _source_paths_by_name().get(name, ())
            sibling = (caller_dir / name).as_posix()
            if sibling in matches:
                invoked.add(sibling)
            elif len(matches) == 1:
                invoked.add(matches[0])
    return invoked


def _resolve_import(
    index: dict[str, tuple[str, ...]],
    module: str,
    caller: str,
) -> tuple[str, ...]:
    """Resolve an import exactly, relative to its caller, or by unique bare name."""
    if module in index:
        return index[module]

    package = _module_name(caller).rpartition(".")[0]
    sibling = ".".join(part for part in (package, module) if part)
    if sibling in index:
        return index[sibling]

    if "." in module:
        return ()
    matches = [
        paths for name, paths in index.items() if name == module or name.endswith(f".{module}")
    ]
    return matches[0] if len(matches) == 1 else ()


@functools.lru_cache(maxsize=1)
def _reference_graph() -> dict[str, frozenset[str]]:
    """Map every Python source to every in-repo source it imports or names.

    Edges point at any file under `_CALLER_ROOTS`, not only at guarded
    scripts. Restricting the targets to guarded scripts would break the
    closure the moment a chain ran through two ordinary modules: a workflow
    that calls `a.py`, which imports `b.py`, which imports the guarded
    `c.py`, would leave `c.py` looking unreachable because no edge ever
    reaches `b.py` to be followed.
    """
    index = _source_index()
    graph: dict[str, frozenset[str]] = {}
    for path in _python_sources():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # The file existed when `_python_sources` listed it, but another
            # process deleted it before this read. A vanished file cannot make
            # a guarded script reachable or unreachable, so skip the stale edge.
            continue
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"Cannot inspect Python source {rel}: {exc}") from exc
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise RuntimeError(f"Cannot parse Python source {rel}: {exc}") from exc
        reached = _invoked_scripts(tree, rel)
        for module in _imported_modules(tree, rel):
            reached.update(_resolve_import(index, module, rel))
        graph[rel] = frozenset(reached - {rel})
    return graph


def _module_path(rel: str) -> str:
    """`scripts/validation/x.py` as `scripts.validation.x`, the `-m` spelling."""
    return rel[: -len(".py")].replace("/", ".")


def _read_text(path: Path, surface: str) -> str:
    """Read one entry surface, naming the file when it cannot be read.

    Without the path in the message an unreadable file surfaces as a bare
    OSError from somewhere inside a reachability computation, which tells the
    next reader nothing about which surface to go look at.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        rel = path.relative_to(_REPO_ROOT).as_posix()
        raise RuntimeError(f"Cannot inspect {surface} {rel}: {exc}") from exc


def _text_of(patterns: tuple[str, ...]) -> str:
    chunks: list[str] = []
    for pattern in patterns:
        for path in _REPO_ROOT.glob(pattern):
            if path.is_file():
                chunks.append(_read_text(path, "entry surface"))
    return "\n".join(chunks)


@functools.lru_cache(maxsize=1)
def _entry_points() -> frozenset[str]:
    """Scripts named directly by a workflow step, a git hook, or a skill.

    Three spellings count, because all three appear in this repository:
    the repo-relative path, the bare file name, and the dotted module form
    that ``python -m`` takes. Missing the third is not hypothetical: this
    guard's first run reported ``passive_context_budget.py`` unreachable
    while ``passive-context-budget.yml`` runs
    ``python3 -m scripts.validation.passive_context_budget --ci``, and took
    ``token_budget.py`` down with it because it is only imported from there.
    """
    workflow_text = "\n".join(_strip_commented_lines(body) for _, body in _live_run_blocks())
    # Hook configs are YAML and shell, where `#` opens a comment, so a
    # commented-out command must not seed the closure. SKILL.md files are
    # markdown, where `#` opens a heading and carries real prose; stripping
    # those would drop live entry points. The asymmetry is deliberate.
    hook_text = _strip_commented_lines(
        _text_of(("lefthook.yml", ".config/lefthook.yml", ".githooks/*"))
    )
    skill_patterns = (
        ".claude/skills/*/SKILL.md",
        "src/copilot-cli/skills/*/SKILL.md",
    )
    skill_documents = [
        (skill_md, _read_text(skill_md, "skill entry surface"))
        for pattern in skill_patterns
        for skill_md in _REPO_ROOT.glob(pattern)
    ]
    skill_text = "\n".join(text for _, text in skill_documents)
    corpus = "\n".join((workflow_text, hook_text, skill_text))
    script_tokens = {token.removeprefix("./") for token in _SCRIPT_TOKEN_RE.findall(corpus)}
    module_tokens = set(_MODULE_TOKEN_RE.findall(corpus))
    named = {
        rel for rel in _source_paths() if rel in script_tokens or _module_path(rel) in module_tokens
    }
    for skill_md, text in skill_documents:
        skill_dir = skill_md.parent
        local_tokens = set(_SCRIPT_TOKEN_RE.findall(text))
        local_names = {Path(token).name for token in local_tokens}
        for helper in skill_dir.glob("scripts/**/*.py"):
            helper_rel = helper.relative_to(_REPO_ROOT).as_posix()
            local_rel = helper.relative_to(skill_dir).as_posix()
            if local_rel in local_tokens or helper.name in local_names:
                named.add(helper_rel)
    return frozenset(named)


@functools.lru_cache(maxsize=1)
def _reachable() -> frozenset[str]:
    """Transitive closure of the entry points over the reference graph."""
    graph = _reference_graph()
    seen = set(_entry_points())
    stack = list(seen)
    while stack:
        for target in graph.get(stack.pop(), ()):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return frozenset(seen)


@pytest.mark.parametrize("script", _guarded_scripts(), ids=lambda p: p.name)
def test_validation_script_is_reachable_from_something_that_runs(script: Path) -> None:
    rel = script.relative_to(_REPO_ROOT).as_posix()
    if rel in _NO_CALLER:
        pytest.skip(_NO_CALLER[rel])
    assert rel in _reachable(), (
        f"{rel} is not reachable from any workflow step, git hook, or skill, "
        f"directly or through anything they call. A script nothing runs is not "
        f"a guard, and its own tests stay green while it protects nothing "
        f"(issue #3329). Wire it, delete it, or add it to _NO_CALLER with a "
        f"reason."
    )


def test_every_no_caller_entry_carries_a_reason() -> None:
    """An empty reason turns the allowlist into a silent opt-out."""
    for name, reason in _NO_CALLER.items():
        assert reason.strip(), f"_NO_CALLER[{name!r}] needs a reason"


def test_every_no_caller_entry_still_exists() -> None:
    """A stale entry silently exempts nothing and hides a deleted script."""
    present = {p.relative_to(_REPO_ROOT).as_posix() for p in _guarded_scripts()}
    stale = sorted(set(_NO_CALLER) - present)
    assert not stale, (
        f"_NO_CALLER names scripts that no longer exist: {stale}. Remove them, "
        f"or the list stops describing the repository."
    )


def test_no_caller_entries_are_still_unreachable() -> None:
    """A newly wired script must leave the allowlist before it can regress."""
    reachable_exemptions = sorted(set(_NO_CALLER) & _reachable())
    assert not reachable_exemptions, (
        f"_NO_CALLER entries are now reachable: {reachable_exemptions}. Remove "
        "their exemptions so a future caller regression fails this guard."
    )


def test_the_allowlist_stays_small_enough_to_read() -> None:
    """The failure this guards is a list nobody reads.

    59 entries would be the literal-reference model's answer. The bound is
    generous against the five real entries so that ordinary churn does not trip
    it, and tight enough that a bulk exemption has to argue for itself.
    """
    assert len(_NO_CALLER) <= 12, (
        f"{len(_NO_CALLER)} allowlist entries. Past a dozen this is a bulk "
        f"exemption rather than a set of decisions, which is the #3329 defect "
        f"with extra ceremony."
    )


class TestTheReachabilityProbeWorks:
    """Guard the guard: a broken probe makes every case above vacuous."""

    def test_entry_points_are_not_empty(self) -> None:
        assert _entry_points(), (
            "no script is named by any workflow, hook, or skill, so every "
            "reachability assertion is vacuous"
        )

    def test_the_graph_covers_more_than_one_file(self) -> None:
        assert len(_reference_graph()) > 1, "the probe is not walking the tree"

    def test_a_python_source_that_vanishes_mid_walk_is_skipped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        real_source = next(p for p in _python_sources() if p.is_file())
        vanished = _REPO_ROOT / "scripts" / "__vanished_probe__.py"
        assert not vanished.exists()
        monkeypatch.setattr(
            "tests.ci.test_validation_scripts_are_reachable._python_sources",
            lambda: (real_source, vanished),
        )
        _source_paths.cache_clear()
        _source_index.cache_clear()
        _source_paths_by_name.cache_clear()
        _reference_graph.cache_clear()
        try:
            graph = _reference_graph()
        finally:
            _source_paths.cache_clear()
            _source_index.cache_clear()
            _source_paths_by_name.cache_clear()
            _reference_graph.cache_clear()

        real_rel = real_source.relative_to(_REPO_ROOT).as_posix()
        vanished_rel = vanished.relative_to(_REPO_ROOT).as_posix()
        assert real_rel in graph
        assert vanished_rel not in graph
        assert all(vanished_rel not in targets for targets in graph.values())

    def test_an_unreadable_python_source_still_fails_hard(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        unreadable = _REPO_ROOT / "scripts" / "__unreadable_probe__.py"
        monkeypatch.setattr(
            "tests.ci.test_validation_scripts_are_reachable._python_sources",
            lambda: (unreadable,),
        )
        real_read_text = Path.read_text

        def raise_permission_error(self: Path, *args, **kwargs) -> str:
            if self == unreadable:
                raise PermissionError("permission denied")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", raise_permission_error)
        _source_paths.cache_clear()
        _source_index.cache_clear()
        _source_paths_by_name.cache_clear()
        _reference_graph.cache_clear()
        try:
            with pytest.raises(RuntimeError, match=r"__unreadable_probe__\.py"):
                _reference_graph()
        finally:
            _source_paths.cache_clear()
            _source_index.cache_clear()
            _source_paths_by_name.cache_clear()
            _reference_graph.cache_clear()

    def test_reachability_is_transitive(self) -> None:
        """An aggregator's callees count, which is the whole point."""
        graph = {"a.py": frozenset({"b.py"}), "b.py": frozenset({"c.py"}), "c.py": frozenset()}
        seen, stack = {"a.py"}, ["a.py"]
        while stack:
            for target in graph.get(stack.pop(), ()):
                if target not in seen:
                    seen.add(target)
                    stack.append(target)
        assert seen == {"a.py", "b.py", "c.py"}

    def test_an_import_is_resolved(self) -> None:
        tree = ast.parse("from scripts.validation import pre_pr")
        assert "scripts.validation.pre_pr" in _imported_modules(tree, "entry.py")

    def test_a_relative_import_is_resolved_from_the_caller(self) -> None:
        tree = ast.parse("from . import models")
        assert "scripts.memory.models" in _imported_modules(
            tree,
            "scripts/memory/loader.py",
        )

    def test_a_mention_in_a_comment_is_not_an_import(self) -> None:
        tree = ast.parse("# import ghost_module\nx = 1")
        assert _imported_modules(tree, "entry.py") == set()

    def test_a_known_aggregated_script_is_reachable(self) -> None:
        """pre_pr.py fans out to most of scripts/validation and runs from a hook.

        Anchoring on it means a regression that breaks aggregator-following
        shows up here as a named failure rather than as 40 parametrized ones.
        """
        assert "scripts/validation/pre_pr.py" in _reachable()

    def test_a_script_that_exists_nowhere_is_not_reachable(self) -> None:
        assert "scripts/validation/definitely_not_a_real_script.py" not in _reachable()

    def test_the_dotted_module_spelling_is_recognized(self) -> None:
        assert _module_path("scripts/validation/x.py") == "scripts.validation.x"
        assert _module_path("build/scripts/y.py") == "build.scripts.y"

    def test_a_module_invoked_with_dash_m_is_reachable(self) -> None:
        """passive-context-budget.yml uses `python3 -m`, not a file path.

        This is the concrete case the path-only probe missed on its first run.
        """
        assert "scripts/validation/passive_context_budget.py" in _reachable()

    def test_a_library_reached_only_through_a_dash_m_entry_point_is_reachable(
        self,
    ) -> None:
        """token_budget.py has exactly one importer, and it is that module."""
        assert "scripts/validation/token_budget.py" in _reachable()

    def test_the_graph_reaches_files_that_are_not_guarded_scripts(self) -> None:
        """Edges must cover ordinary modules, or the closure stops at one hop.

        An earlier version of `_reference_graph` pointed edges only at
        guarded scripts. That still resolved a workflow-to-guarded chain,
        but silently broke on `entry.py -> ordinary.py -> guarded.py`:
        nothing ever put `ordinary.py` on the stack, so `guarded.py` looked
        unreachable. Reaching at least one non-guarded file is the
        observable difference between the two models.
        """
        guarded = {p.relative_to(_REPO_ROOT).as_posix() for p in _guarded_scripts()}
        reached = {t for targets in _reference_graph().values() for t in targets}
        assert reached - guarded, (
            "every graph edge lands on a guarded script, so the closure cannot "
            "cross an ordinary module and multi-hop chains read as unreachable"
        )

    def test_a_multi_hop_chain_through_ordinary_modules_resolves(self) -> None:
        """The graph must contain chains deeper than one hop.

        This checks the precondition the closure walk depends on, not the
        walk itself: if every source sat one edge from an entry point, a
        non-transitive `_reachable` would look correct and the guard would
        pass for the wrong reason.
        """
        graph = _reference_graph()
        depth = {rel: 0 for rel in _entry_points()}
        stack = list(depth)
        while stack:
            current = stack.pop()
            for target in graph.get(current, ()):
                if target not in depth:
                    depth[target] = depth[current] + 1
                    stack.append(target)
        assert max(depth.values(), default=0) >= 2, (
            "no source is more than one hop from an entry point, which means "
            "the closure is not actually transitive"
        )


class TestExecutionStringLiterals:
    def test_executable_string_is_detected(self) -> None:
        tree = ast.parse('subprocess.run(["python", "scripts/validation/pre_pr.py"])')
        assert "scripts/validation/pre_pr.py" in _execution_string_literals(tree)

    def test_help_and_log_strings_are_ignored(self) -> None:
        tree = ast.parse(
            'parser.add_argument("--x", help="Used by pre_pr.py")\n'
            'logger.info("Run pre_pr.py manually")\n'
        )
        assert _execution_string_literals(tree) == set()

    def test_bare_name_collision_does_not_seed_every_copy(self) -> None:
        assert "scripts/validation/validate_review_marker.py" not in _entry_points()

    def test_filename_substrings_do_not_count_as_mentions(self) -> None:
        assert not _mentions_token("validate_pr_description.py", "pr_description.py")
        assert not _mentions_token("manifest_counts.py", "counts.py")


class TestTheDocstringMatchesTheAllowlist:
    """A hardcoded count in prose drifts the moment the list changes."""

    def test_the_stated_unreachable_count_is_the_real_one(self) -> None:
        stated = f"yield {_NUMBER_WORDS[len(_NO_CALLER)]} unreachable"
        assert __doc__ is not None
        assert stated in __doc__, (
            f"module docstring should say {stated!r}; it drifts every time "
            f"_NO_CALLER changes unless something checks it"
        )


class TestInvokedScripts:
    @pytest.mark.parametrize(
        ("literal", "expected"),
        [
            ("scripts/validation/foo.py", {"scripts/validation/foo.py"}),
            ("foo.py", {"scripts/other/foo.py"}),
        ],
        ids=["exact-path", "bare-sibling"],
    )
    def test_exact_paths_precede_bare_name_fallback(
        self,
        monkeypatch: pytest.MonkeyPatch,
        literal: str,
        expected: set[str],
    ) -> None:
        fake_paths = (
            "scripts/validation/foo.py",
            "scripts/other/foo.py",
        )
        fake_by_name = {
            "foo.py": ("scripts/validation/foo.py", "scripts/other/foo.py"),
        }
        monkeypatch.setattr(
            "tests.ci.test_validation_scripts_are_reachable._source_paths",
            lambda: fake_paths,
        )
        monkeypatch.setattr(
            "tests.ci.test_validation_scripts_are_reachable._source_paths_by_name",
            lambda: fake_by_name,
        )
        tree = ast.parse(f"subprocess.run(['python', {literal!r}])")
        assert _invoked_scripts(tree, "scripts/other/caller.py") == expected


class TestCommentedHookLinesDoNotSeedReachability:
    """A commented-out hook command must not count as an entry point.

    `_entry_points` builds one corpus from workflow `run:` bodies, hook
    configs, and SKILL.md files. Workflow bodies were comment-stripped from
    the start; hook configs were not, so a `#` line in `lefthook.yml` or a
    `.githooks/*` script that named a `*.py` path could mark a script
    reachable when nothing ran it. That is the false-green this whole module
    exists to prevent.
    """

    def test_a_commented_hook_line_is_stripped(self) -> None:
        body = "# uv run python scripts/validation/ghost.py --ci\nreal --flag\n"

        assert "ghost.py" not in _strip_commented_lines(body)

    def test_an_indented_comment_is_stripped(self) -> None:
        # lefthook.yml nests commands, so a comment is rarely at column zero.
        body = "    #   python3 -m scripts.validation.ghost\n    run: real\n"

        assert "scripts.validation.ghost" not in _strip_commented_lines(body)

    def test_a_live_hook_line_survives(self) -> None:
        # The converse: stripping must not swallow the commands that do run.
        body = "  run: uv run python scripts/validation/live.py --ci\n"

        assert "scripts/validation/live.py" in _strip_commented_lines(body)

    def test_markdown_headings_are_not_treated_as_comments(self) -> None:
        # SKILL.md text is deliberately NOT stripped: `#` opens a heading
        # there, and a heading can sit above a live script reference.
        skill_body = "## Scripts\n\nRun `scripts/validation/live.py` to check.\n"

        assert "scripts/validation/live.py" in skill_body

    def test_the_hook_corpus_is_stripped_in_the_entry_point_builder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A commented hook line does not reach `_entry_points`.

        Behavioral, not textual: the helper being imported is not the same as
        the helper being applied, and that gap is the state this module
        shipped in before the fix.
        """
        guarded = next(iter(_source_paths()))
        module = "tests.ci.test_validation_scripts_are_reachable"
        monkeypatch.setattr(f"{module}._live_run_blocks", lambda: ())
        monkeypatch.setattr(
            f"{module}._text_of",
            lambda patterns: f"# uv run python {guarded}\n" if "lefthook.yml" in patterns else "",
        )
        _entry_points.cache_clear()
        try:
            assert guarded not in _entry_points(), (
                f"{guarded} was named only in a comment but counted as an entry point"
            )
        finally:
            _entry_points.cache_clear()


class TestUnreadableEntrySurfacesNameTheFile:
    """An unreadable entry surface reports its path, not a bare decode error.

    `_text_of` wrapped its reads from the start. The per-skill SKILL.md scan in
    `_entry_points` used a raw `read_text`, so a file with a bad encoding failed
    there with no indication of which surface broke. Both now go through
    `_read_text`, which also collapsed the two passes over the SKILL.md corpus
    into one.
    """

    def test_a_decode_error_names_the_path(self) -> None:
        bad = _REPO_ROOT / "tests" / "ci" / "__unreadable_probe__.md"
        bad.write_bytes(b"\xff\xfe\x00 not utf-8 \xc3\x28")
        try:
            with pytest.raises(RuntimeError, match=r"__unreadable_probe__\.md"):
                _read_text(bad, "entry surface")
        finally:
            bad.unlink()

    def test_the_message_carries_the_surface_label(self) -> None:
        """The label distinguishes a workflow surface from a skill surface."""
        bad = _REPO_ROOT / "tests" / "ci" / "__labelled_probe__.md"
        bad.write_bytes(b"\xff\xfe\x00 \xc3\x28")
        try:
            with pytest.raises(RuntimeError, match=r"skill entry surface"):
                _read_text(bad, "skill entry surface")
        finally:
            bad.unlink()

    def test_a_readable_file_returns_its_text(self) -> None:
        good = _REPO_ROOT / "tests" / "ci" / "__readable_probe__.md"
        good.write_text("# heading\n", encoding="utf-8")
        try:
            assert _read_text(good, "entry surface") == "# heading\n"
        finally:
            good.unlink()

    def test_each_skill_md_is_read_once(self, monkeypatch) -> None:
        """`_entry_points` reads the SKILL.md corpus in a single pass.

        The earlier shape called `_text_of(skill_patterns)` and then re-globbed
        the same files in the per-skill loop, reading every SKILL.md twice.
        Counting the reads is what proves the second pass is gone.
        """
        counts: dict[str, int] = {}
        real = _read_text

        def counting(path: Path, surface: str) -> str:
            if path.name == "SKILL.md":
                counts[path.as_posix()] = counts.get(path.as_posix(), 0) + 1
            return real(path, surface)

        monkeypatch.setattr("tests.ci.test_validation_scripts_are_reachable._read_text", counting)
        _entry_points.cache_clear()
        try:
            _entry_points()
        finally:
            _entry_points.cache_clear()

        assert counts, "no SKILL.md was read; the scan patterns matched nothing"
        repeated = {rel: n for rel, n in counts.items() if n != 1}
        assert not repeated, f"SKILL.md files read more than once: {repeated}"
