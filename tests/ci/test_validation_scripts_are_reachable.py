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
reachable from anything that runs? Reachability follows imports and script-path
mentions transitively from three entry surfaces, which between them are every
way a script in this repository gets executed:

- a live ``run:`` body in a workflow or composite action
- a git hook, via ``lefthook.yml`` or ``.githooks/``
- a skill, via its ``SKILL.md`` or the text of a script under its ``scripts/``

A script is an entry point when the text of one of those surfaces names it. A
script under a skill's ``scripts/`` is read as text that can name something, not
seeded as a root: it becomes reachable only when a ``SKILL.md`` or another
surface names it.

Under that model the same 89 scripts yield seven unreachable, each of which is a
real decision recorded in ``_NO_CALLER`` below rather than a bulk exemption.

What this does not do: prove the caller is correct, or that the script would
pass if run. Three of the entries below are unreachable precisely because
they fail against the current tree, which is tracked separately. Reachability
is the floor, not the ceiling.
"""

from __future__ import annotations

import ast
import functools
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.ci.test_ci_scripts_are_wired import _live_run_blocks, _strip_commented_lines

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARDED_DIRS = ("scripts/validation", "build/scripts")

# AST nodes that can own a docstring as the first statement of their body.
_DOCSTRING_OWNERS = (
    ast.Module,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
)

# Spelled-out counts, so the module docstring can be checked against reality.
# Covers the full range test_the_allowlist_stays_small_enough_to_read permits,
# so growth inside that bound fails with the docstring assertion rather than a
# KeyError from this table.
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

# The most entries _NO_CALLER may hold before the allowlist stops being
# readable. _NUMBER_WORDS must span this whole range; a test pins that.
_ALLOWLIST_CEILING = 12

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
    "validate_templates_schema.py": (
        "No caller on any entry surface. It looked wired only because "
        "build/scripts/yaml_loader.py names it in a module docstring, an edge "
        "that points from the library to its own consumer. templates/README.md "
        "said it runs in build-validation.yml, a workflow that no longer "
        "exists. Exits 0 today, so wiring it cannot turn CI red on arrival. "
        "Tracked in #3366."
    ),
    "check_skill_portability.py": (
        "No caller on any entry surface. Its only references are the docstrings "
        "of check_skill_md_portability.py and checks_spec.py. It carries a "
        "drift baseline of 173 and measures 166, and a ratchet nothing runs "
        "does not ratchet. Exits 0 today. Tracked in #3366."
    ),
    "validate_seed_parity.py": (
        "Forensic tool, and its own module docstring says so: 'This is a "
        "FORENSIC TOOL, not a regression gate. Do NOT add it to CI.' It answers "
        "a one-time historical question about how the review axes under "
        "REQ-008 were seeded. Wiring it would make it a gate it was explicitly "
        "written not to be."
    ),
    "check_dual_priority_labels.py": (
        "Queries the GitHub issue and PR label sets, so it needs a token and "
        "network and gates nothing in a diff. It is a triage report for #2623, "
        "not a code gate: a PR cannot introduce a duplicate priority label on "
        "an issue. Belongs on a schedule, which does not exist yet."
    ),
    "consistency.py": (
        "Fails against the current tree: `--all --ci` exits 1 with 4 of 7 "
        "feature checks failing. Wiring it as-is would red main. The protocol "
        "it implements (.agents/governance/consistency-protocol.md) is live and "
        "there are 23 requirement and 19 design artifacts to check, so the fix "
        "is to resolve the findings and then wire it. Tracked in #3360."
    ),
    "traceability.py": (
        "Fails against the current tree: `--ci` exits 1, reporting TASK-011 "
        "complete while its DESIGN reference is not. Same shape as "
        "consistency.py: the schema it implements "
        "(.agents/governance/traceability-schema.md) is live, so the fix is to "
        "resolve the findings and then wire it. Tracked in #3360."
    ),
    "hook_contracts.py": (
        "Fails against the current tree: `--ci` exits 1 on hook docstrings that "
        "do not document their exit-code semantics. This one is worth wiring "
        "once the docstrings are fixed, because it guards the hook contract "
        "that #3247 and #3295 both turned on. Tracked in #3360."
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
    """Every Python file a call site could live in.

    Cached and immutable: three cached builders below walk this, and an
    uncached list would mean three full rglob scans of the tree per session
    and a shared mutable result between them.
    """
    skip = ("__pycache__", ".venv", ".cache", "worktrees", "node_modules")
    sources: list[Path] = []
    for root in _CALLER_ROOTS:
        base = _REPO_ROOT / root
        if not base.is_dir():
            continue
        sources.extend(p for p in base.rglob("*.py") if not any(s in p.parts for s in skip))
    return tuple(sources)


def _imported_names(source: str) -> set[str]:
    """Every module and symbol name an import statement in this source binds."""
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:  # validate_python_syntax.py owns reporting this
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[-1] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[-1])
            names |= {alias.name for alias in node.names}
    return names


def _scannable_text(source: str) -> str:
    """String literals that are not docstrings, joined for substring search.

    The substring scan exists for subprocess invocations, where a script is
    named by a string literal rather than imported. Scanning the raw file
    instead lets a comment or a docstring manufacture reachability, which is
    the same defect `_strip_commented_lines` exists to prevent on the
    workflow side: `yaml_loader.py` lists `validate_templates_schema.py` in
    its module docstring, and that mention alone made an unwired script look
    wired, with the edge pointing from the library to its own consumer.

    Comments never reach the AST, so excluding them is free. Docstrings are
    excluded explicitly. Everything else a string literal can hold, including
    the pieces of an f-string, is kept.

    Falls back to the raw source when the file does not parse, because
    over-approximating reachability is safer than dropping a real edge.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:  # validate_python_syntax.py owns reporting this
        return source
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        if not isinstance(node, _DOCSTRING_OWNERS):
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return "\n".join(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    )


@functools.lru_cache(maxsize=1)
def _source_index() -> dict[str, tuple[str, ...]]:
    """Every in-repo Python source under `_CALLER_ROOTS`, keyed by module stem."""
    index: dict[str, list[str]] = {}
    for path in _python_sources():
        index.setdefault(path.stem, []).append(path.relative_to(_REPO_ROOT).as_posix())
    return {stem: tuple(paths) for stem, paths in index.items()}


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
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names = _imported_names(source)
        scannable = _scannable_text(source)
        reached: set[str] = set()
        for stem, targets in index.items():
            if stem in names or f"{stem}.py" in scannable:
                reached.update(targets)
        graph[rel] = frozenset(reached - {rel})
    return graph


def _module_path(rel: str) -> str:
    """`scripts/validation/x.py` as `scripts.validation.x`, the `-m` spelling."""
    return rel[: -len(".py")].replace("/", ".")


def _unchanged(text: str) -> str:
    """The default cleaner: read the file as written."""
    return text


def _text_of(
    patterns: tuple[str, ...],
    clean: Callable[[str], str] = _unchanged,
) -> str:
    """Concatenate the matched files, running ``clean`` over each one first.

    Per file, not over the joined result: a cleaner that parses (``_scannable_text``)
    cannot parse a concatenation of unrelated modules, and one that scans line by
    line (``_strip_commented_lines``) would still be reading the wrong file's
    syntax. Getting this backwards silently over-approximates, because both
    cleaners fall back to returning the text unchanged.
    """
    chunks: list[str] = []
    for pattern in patterns:
        for path in _REPO_ROOT.glob(pattern):
            if path.is_file():
                chunks.append(clean(path.read_text(encoding="utf-8", errors="replace")))
    return "\n".join(chunks)


@functools.lru_cache(maxsize=2)
def _entry_points(*, clean_sources: bool = True) -> frozenset[str]:
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
    hook_text = _text_of(
        ("lefthook.yml", ".config/lefthook.yml", ".githooks/*"),
        clean=_strip_commented_lines if clean_sources else _unchanged,
    )
    skill_code_text = _text_of(
        (
            ".claude/skills/*/scripts/**/*.py",
            "src/copilot-cli/skills/*/scripts/**/*.py",
        ),
        clean=_scannable_text if clean_sources else _unchanged,
    )
    # SKILL.md prose is read raw on purpose. A workflow comment naming a script
    # does not run it, but a skill telling its agent to run one is the
    # invocation; there is no other spelling. "#" also opens a heading here,
    # not a comment, so the line-based cleaner would delete real instructions.
    skill_prose_text = _text_of(
        (".claude/skills/*/SKILL.md", "src/copilot-cli/skills/*/SKILL.md"),
    )
    corpus = "\n".join((workflow_text, hook_text, skill_code_text, skill_prose_text))
    named: set[str] = set()
    for path in _python_sources():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        if rel in corpus or path.name in corpus or _module_path(rel) in corpus:
            named.add(rel)
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
    if script.name in _NO_CALLER:
        pytest.skip(_NO_CALLER[script.name])
    rel = script.relative_to(_REPO_ROOT).as_posix()
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


def test_no_caller_entries_are_still_unreachable() -> None:
    """An entry that gains a caller has to lose its exemption.

    The parametrized case skips every name in ``_NO_CALLER``, so once a script
    is listed nothing re-examines it. Wire one of these up and the guard keeps
    reporting a skip forever, which reproduces the #3329 defect the allowlist
    exists to bound: a script whose own tests stay green while nothing checks
    whether it still needs the exemption.

    The sibling assertion in ``TestTheReachabilityProbeWorks`` covers the other
    direction, that every unreachable script is listed. Together they pin the
    allowlist to exactly the unreachable set.
    """
    reachable = _reachable()
    wired = []
    for script in _guarded_scripts():
        if script.name not in _NO_CALLER:
            continue
        rel = script.relative_to(_REPO_ROOT).as_posix()
        if rel in reachable:
            wired.append(rel)
    assert not wired, (
        f"{wired} have callers now but are still in _NO_CALLER, so the "
        f"reachability case skips them instead of checking them. Delete their "
        f"entries."
    )


def test_every_no_caller_entry_still_exists() -> None:
    """A stale entry silently exempts nothing and hides a deleted script."""
    present = {p.name for p in _guarded_scripts()}
    stale = sorted(set(_NO_CALLER) - present)
    assert not stale, (
        f"_NO_CALLER names scripts that no longer exist: {stale}. Remove them, "
        f"or the list stops describing the repository."
    )


def test_the_allowlist_stays_small_enough_to_read() -> None:
    """The failure this guards is a list nobody reads.

    59 entries would be the literal-reference model's answer. The bound is
    generous against the seven real entries so that ordinary churn does not trip
    it, and tight enough that a bulk exemption has to argue for itself.
    """
    assert len(_NO_CALLER) <= _ALLOWLIST_CEILING, (
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

    def test_an_import_is_detected(self) -> None:
        assert "pre_pr" in _imported_names("from scripts.validation import pre_pr")
        assert "checks_dash" in _imported_names("import checks_dash")
        assert "run_all" in _imported_names("from pre_pr import run_all")

    def test_a_mention_in_a_comment_is_not_an_import(self) -> None:
        assert _imported_names("# import ghost_module\nx = 1") == set()

    def test_a_syntax_error_does_not_crash_the_probe(self) -> None:
        assert _imported_names("def (:") == set()

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


class TestTheDocstringMatchesTheAllowlist:
    """A hardcoded count in prose drifts the moment the list changes."""

    def test_the_stated_unreachable_count_is_the_real_one(self) -> None:
        stated = f"yield {_NUMBER_WORDS[len(_NO_CALLER)]} unreachable"
        assert __doc__ is not None
        assert stated in __doc__, (
            f"module docstring should say {stated!r}; it drifts every time "
            f"_NO_CALLER changes unless something checks it"
        )

    def test_the_word_table_covers_every_size_the_allowlist_may_reach(self) -> None:
        """Otherwise growth inside the permitted range dies on a KeyError.

        The two bounds are set in different places and drifted apart once
        already: the table stopped at eight while the cap allowed twelve, so
        the ninth allowlist entry would have crashed this class instead of
        reporting the stale docstring it exists to report.
        """
        assert set(range(_ALLOWLIST_CEILING + 1)) <= set(_NUMBER_WORDS), (
            f"_NUMBER_WORDS covers up to {max(_NUMBER_WORDS)} but the allowlist "
            f"may reach {_ALLOWLIST_CEILING}"
        )


class TestProseDoesNotManufactureReachability:
    """A script named in a comment is discussed, not run."""

    def test_a_comment_does_not_create_an_edge(self) -> None:
        source = "# see scripts/validation/pre_pr.py for the gate\nx = 1\n"
        assert "pre_pr.py" not in _scannable_text(source)

    def test_a_module_docstring_does_not_create_an_edge(self) -> None:
        source = '"""Consumers:\n\n- pre_pr.py (REQ-001)\n"""\n\nx = 1\n'
        assert "pre_pr.py" not in _scannable_text(source)

    def test_a_function_docstring_does_not_create_an_edge(self) -> None:
        source = 'def f():\n    """Mirrors pre_pr.py."""\n    return 1\n'
        assert "pre_pr.py" not in _scannable_text(source)

    def test_a_subprocess_argument_still_creates_an_edge(self) -> None:
        """The scan exists for this shape, so it must survive the filter."""
        source = 'run(["python3", "scripts/validation/pre_pr.py", "--ci"])\n'
        assert "pre_pr.py" in _scannable_text(source)

    def test_an_f_string_argument_still_creates_an_edge(self) -> None:
        source = 'run(f"python3 scripts/validation/pre_pr.py {flag}")\n'
        assert "pre_pr.py" in _scannable_text(source)

    def test_an_unparseable_file_falls_back_to_the_raw_source(self) -> None:
        """Over-approximating beats dropping a real edge on a syntax error."""
        source = "def broken(:\n    pre_pr.py\n"
        assert _scannable_text(source) == source

    def test_the_yaml_loader_docstring_no_longer_reaches_its_consumer(self) -> None:
        """The concrete case: the edge pointed library to consumer, backwards."""
        loader = _REPO_ROOT / "build" / "scripts" / "yaml_loader.py"
        if not loader.is_file():
            pytest.skip("yaml_loader.py has moved")
        edges = _reference_graph().get("build/scripts/yaml_loader.py", frozenset())
        assert "build/scripts/validate_templates_schema.py" not in edges


class TestEntryPointsComeFromInvocationsNotComments:
    """A hook comment names a script; it does not run one.

    The reachability scan learned this for Python sources first. `_entry_points`
    read hooks and skill code raw for one round longer, which left the same hole
    one layer up: an entry point manufactured here seeds the closure, so it can
    hide an unwired script rather than merely mislabel one file.
    """

    def test_the_cleaners_are_actually_engaged(self) -> None:
        """A canary, because deleting `clean=` leaves every other test green.

        Measured when this landed: reading hooks and skill code raw produces 492
        entry points against 479 cleaned. All 13 of the difference are also
        reached by a real import, which is why the allowlist did not move and
        why nothing else here notices. That makes this the only test that fails
        when the argument is dropped, so it asserts the mechanism rather than
        the outcome: at least one name must reach the corpus only through a
        comment, or the cleaning is not happening.
        """
        cleaned = _entry_points(clean_sources=True)
        raw = _entry_points(clean_sources=False)

        assert cleaned < raw, (
            "hook and skill-code comments are seeding entry points again; "
            "_text_of is being called without its cleaner"
        )

    def test_the_cleaner_runs_per_file_not_over_the_concatenation(self) -> None:
        """Both cleaners degrade to identity, so the wrong order fails silently.

        `_scannable_text` cannot parse two unrelated modules joined by a newline
        and falls back to the raw text, which is exactly the behaviour the
        cleaner exists to prevent. The only visible difference is that the
        per-file form strips and the joined form does not.
        """
        seen: list[str] = []

        def record(text: str) -> str:
            seen.append(text)
            return text

        _text_of((".claude/skills/*/scripts/**/*.py",), clean=record)
        assert len(seen) > 1, "cleaner should be called once per matched file"
        assert not any("\x00" in chunk for chunk in seen)

    def test_skill_code_comments_do_not_seed_entry_points(self) -> None:
        source = "# run scripts/validation/nonexistent_probe.py nightly\nx = 1\n"
        assert "nonexistent_probe.py" not in _scannable_text(source)

    def test_skill_prose_still_seeds_entry_points(self) -> None:
        """Deliberate asymmetry: a skill instructing its agent is the invocation."""
        prose = _text_of((".claude/skills/*/SKILL.md", "src/copilot-cli/skills/*/SKILL.md"))
        assert "python" in prose.lower(), "SKILL.md corpus should be read raw"

    def test_every_script_dropped_as_a_false_entry_point_is_still_reachable(self) -> None:
        """The cleaner removed 13 comment-only entry points and no script fell out.

        That is the result worth pinning. Each of those files is genuinely
        imported by something, so the closure keeps them; had any been reachable
        only through the comment, the allowlist would have had to grow, and this
        guard's answer would have been quietly wrong before the fix.
        """
        unreachable = {
            script.name
            for script in _guarded_scripts()
            if script.relative_to(_REPO_ROOT).as_posix() not in _reachable()
        }
        assert unreachable <= set(_NO_CALLER), (
            f"{sorted(unreachable - set(_NO_CALLER))} fell out of the closure "
            f"when comment-only entry points stopped counting"
        )
