"""Every pytest node id under ``tests/mutation/`` must name a test that exists.

Issue #5534. ``mutation_harness_4251.py`` selected
``TestAggregateLefthookDelegation::test_registry_contains_all_eight_ratchets``
after the test was renamed to ``test_registry_contains_every_registered_ratchet``.
The harness reached its own ``_assert_suite_ran`` guard, which raises on pytest
exit 4, so mutation M3 reported a harness error instead of proving that the
guard test catches the mutation. A mutation harness that cannot select its guard
test proves nothing, and it fails in a shape that reads as a harness bug rather
than a coverage hole.

Nothing else ties a harness selector to the test it names, so the rename rotted
it silently and would have rotted the next one the same way. This module is that
tie. It resolves selectors statically, with ``ast`` rather than a pytest
subprocess, so it costs milliseconds and can run in the fast lane.

``mutation_harness_4251.py`` is currently the only file under ``tests/mutation/``
that carries pytest node ids, but the scan is written against the directory so a
harness that adds them later is covered on arrival.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MUTATION_DIR = REPO_ROOT / "tests" / "mutation"


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings, which f-strings interpolate.

    Only plain string literals at module scope. A selector built from anything
    else is left unresolved rather than guessed at, and
    :func:`unresolved_selectors` reports it.
    """
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def _render(node: ast.expr, constants: dict[str, str]) -> str | None:
    """Flatten a literal or a simple f-string to text, or None if it is neither.

    Handles the two shapes selectors are written in: a bare literal, and
    ``f"{TEST}::Class::test_name"`` where ``TEST`` is a module-level string.
    Anything else (a call, an attribute, a name this module cannot resolve)
    returns None so the caller can decide, rather than being silently dropped.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for piece in node.values:
        if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
            parts.append(piece.value)
        elif isinstance(piece, ast.FormattedValue) and isinstance(piece.value, ast.Name):
            resolved = constants.get(piece.value.id)
            if resolved is None:
                return None
            parts.append(resolved)
        else:
            return None
    return "".join(parts)


def _selectors(tree: ast.Module) -> list[tuple[int, str]]:
    """Every string in the module that looks like a pytest node id.

    A node id here is a whitespace-free ``<path>.py::<segment>[::<segment>...]``.
    The ``.py`` head separates a selector from an unrelated string containing
    ``::``, such as a type annotation written out in text. The whitespace rule
    separates it from prose: this module's own docstrings describe the selector
    grammar, and a paragraph ending in ".py" one line above a "::" would
    otherwise be scanned as a broken test reference.
    """
    constants = _module_string_constants(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant | ast.JoinedStr):
            continue
        text = _render(node, constants)
        if text is None or "::" not in text or any(c.isspace() for c in text):
            continue
        if text.split("::", 1)[0].endswith(".py"):
            found.append((node.lineno, text))
    return found


def _declared_paths(tree: ast.Module) -> set[str]:
    """Every ``::``-joined name path pytest could select in a parsed test module.

    Classes contribute their own name (a class is selectable on its own) and
    every path beneath them, so nested classes resolve as ``Outer::Inner::test``
    exactly as pytest addresses them.
    """
    paths: set[str] = set()

    def walk(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                path = f"{prefix}{node.name}"
                paths.add(path)
                walk(node.body, f"{path}::")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                paths.add(f"{prefix}{node.name}")

    walk(tree.body, "")
    return paths


def unresolved_selectors(source: str, repo_root: Path) -> list[str]:
    """Selectors in ``source`` that name a file or test which does not exist.

    Returns one human-readable line per unresolved selector, empty when every
    selector resolves. Split out from the test so the negative controls below
    can drive it with synthetic sources instead of mutating the repository.

    A parametrized id keeps its case in the message but is matched on the name
    alone: ``test_x[case]`` is selectable whenever ``test_x`` is declared.
    """
    problems: list[str] = []
    for lineno, selector in _selectors(ast.parse(source)):
        rel, _, chain = selector.partition("::")
        target = repo_root / rel
        if not target.is_file():
            problems.append(f"line {lineno}: {selector} (no such file: {rel})")
            continue
        declared = _declared_paths(ast.parse(target.read_text(encoding="utf-8")))
        wanted = "::".join(part.split("[", 1)[0] for part in chain.split("::"))
        if wanted not in declared:
            problems.append(f"line {lineno}: {selector} (no such test: {chain})")
    return problems


# This module is excluded from its own scan. Its negative controls carry
# selectors that deliberately do not resolve ("tests/gone.py::...", and sample
# files written under tmp_path), which is the whole point of a negative control.
# Same carve-out shape as the dash guard's, which skips tests/hooks/fixtures/
# because those files intentionally carry the bytes it rejects.
_SCAN_EXEMPT = frozenset({"__init__.py", Path(__file__).name})


def _harness_sources() -> list[Path]:
    return sorted(p for p in MUTATION_DIR.rglob("*.py") if p.name not in _SCAN_EXEMPT)


class TestTheRepositoryResolves:
    """The rule applied to the real tree, which is what issue #5534 broke."""

    @pytest.mark.parametrize("path", _harness_sources(), ids=lambda p: p.name)
    def test_every_mutation_selector_resolves(self, path: Path) -> None:
        problems = unresolved_selectors(path.read_text(encoding="utf-8"), REPO_ROOT)
        assert not problems, (
            f"{path.relative_to(REPO_ROOT)} names tests that do not exist:\n" + "\n".join(problems)
        )

    def test_the_scan_actually_finds_the_known_selectors(self) -> None:
        """Guards against a rule that passes because it collected nothing.

        ``mutation_harness_4251.py`` carries eight selectors. If a refactor of
        :func:`_selectors` stopped matching the f-string shape, every assertion
        above would pass vacuously and the drift guard would be decoration.
        """
        source = (MUTATION_DIR / "mutation_harness_4251.py").read_text(encoding="utf-8")
        found = _selectors(ast.parse(source))
        assert len(found) == 8, f"expected 8 selectors, found {len(found)}: {found}"


class TestTheRuleDiscriminates:
    """Negative controls. A rule that never fails proves nothing either."""

    def test_a_renamed_test_is_reported(self, tmp_path: Path) -> None:
        """The exact shape of issue #5534: the file exists, the test does not."""
        target = tmp_path / "tests" / "sample_test.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "class TestThing:\n    def test_new_name(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        source = 'TEST = "tests/sample_test.py"\nNODE = f"{TEST}::TestThing::test_old_name"\n'
        problems = unresolved_selectors(source, tmp_path)
        assert len(problems) == 1
        assert "test_old_name" in problems[0]

    def test_a_missing_target_file_is_reported(self, tmp_path: Path) -> None:
        source = 'NODE = "tests/gone.py::TestThing::test_x"\n'
        problems = unresolved_selectors(source, tmp_path)
        assert len(problems) == 1
        assert "no such file" in problems[0]

    def test_a_resolving_selector_is_not_reported(self, tmp_path: Path) -> None:
        target = tmp_path / "tests" / "sample_test.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "class TestThing:\n    def test_kept(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        source = 'TEST = "tests/sample_test.py"\nNODE = f"{TEST}::TestThing::test_kept"\n'
        assert unresolved_selectors(source, tmp_path) == []


class TestSelectorShapes:
    """Edge cases the real harnesses use or could use next."""

    @staticmethod
    def _fixture(tmp_path: Path, body: str) -> Path:
        target = tmp_path / "tests" / "sample_test.py"
        target.parent.mkdir(parents=True)
        target.write_text(body, encoding="utf-8")
        return tmp_path

    def test_a_class_only_selector_resolves(self, tmp_path: Path) -> None:
        """``mutation_harness_4251`` selects two whole classes, not just methods."""
        root = self._fixture(
            tmp_path, "class TestThing:\n    def test_x(self) -> None:\n        pass\n"
        )
        source = 'TEST = "tests/sample_test.py"\nNODE = f"{TEST}::TestThing"\n'
        assert unresolved_selectors(source, root) == []

    def test_a_module_level_function_resolves(self, tmp_path: Path) -> None:
        root = self._fixture(tmp_path, "def test_loose() -> None:\n    pass\n")
        source = 'NODE = "tests/sample_test.py::test_loose"\n'
        assert unresolved_selectors(source, root) == []

    def test_a_nested_class_resolves(self, tmp_path: Path) -> None:
        root = self._fixture(
            tmp_path,
            "class Outer:\n    class Inner:\n        def test_x(self) -> None:\n            pass\n",
        )
        source = 'NODE = "tests/sample_test.py::Outer::Inner::test_x"\n'
        assert unresolved_selectors(source, root) == []

    def test_a_parametrized_case_matches_the_bare_name(self, tmp_path: Path) -> None:
        root = self._fixture(
            tmp_path,
            "class TestThing:\n    def test_x(self, case: int) -> None:\n        pass\n",
        )
        source = 'NODE = "tests/sample_test.py::TestThing::test_x[case0]"\n'
        assert unresolved_selectors(source, root) == []

    def test_a_string_with_colons_but_no_py_head_is_not_a_selector(self) -> None:
        """Keeps the scan from reporting prose and annotations as broken tests."""
        source = 'NOTE = "see ADR-042::rationale"\nHINT = "dict[str, str]::values"\n'
        assert _selectors(ast.parse(source)) == []

    def test_an_unresolvable_interpolation_is_not_guessed_at(self) -> None:
        """``f"{maybe}::x"`` with no module-level binding yields no selector."""
        source = 'NODE = f"{some_call()}::TestThing::test_x"\n'
        assert _selectors(ast.parse(source)) == []
