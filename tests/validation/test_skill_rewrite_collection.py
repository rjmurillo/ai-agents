"""Which tests pytest collects (``skill_rewrite_collection.py``), checked against real pytest."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

from tests.validation import skill_rewrite_helpers
from tests.validation.skill_rewrite_collection_cases import (
    COLLECTED,
    FAIL_CLOSED,
    HIDDEN,
    KEPT,
    REBINDS,
)

# The helpers module puts scripts/validation on sys.path for this import.
__all__ = ["skill_rewrite_helpers"]

import skill_rewrite_collection as collection

_REPO_ROOT = Path(__file__).resolve().parents[2]


_TESTS = """
def test_top():
    pass


def make_thing():
    pass


class Helpers:
    def test_h(self):
        pass


class TestA:
    def test_a(self):
        pass

    def helper(self):
        pass

    async def test_async(self):
        pass

    class TestInner:
        def test_inner(self):
            pass


class TestB:
    def test_b(self):
        pass
"""


class TestCollectionSwitchedOff:
    """``__test__ = False`` makes pytest skip a module, class, or function."""

    @pytest.mark.parametrize(
        ("source", "classes", "func"),
        [
            ("__test__ = False\ndef test_a():\n    pass\n", [], "test_a"),
            ("def test_a():\n    pass\ntest_a.__test__ = False\n", [], "test_a"),
            (
                "class TestA:\n    __test__ = False\n    def test_a(self):\n        pass\n",
                ["TestA"],
                "test_a",
            ),
            (
                "class TestA:\n    def test_a(self):\n        pass\nTestA.__test__ = False\n",
                ["TestA"],
                "test_a",
            ),
            (
                "class TestA:\n    __test__: bool = False\n    def test_a(self):\n        pass\n",
                ["TestA"],
                "test_a",
            ),
            ("__test__ = 0\ndef test_a():\n    pass\n", [], "test_a"),
            ("__test__ = None\ndef test_a():\n    pass\n", [], "test_a"),
        ],
    )
    def test_switched_off_tests_are_not_defined(
        self, source: str, classes: list[str], func: str
    ) -> None:
        assert not collection.defines_test(source, classes, func)

    def test_unrelated_false_assignments_keep_the_test(self) -> None:
        source = (
            "flag = False\n"
            "other.__test__ = False\n"
            "class TestA:\n    __test__ = True\n    def test_a(self):\n        pass\n"
        )
        assert collection.defines_test(source, ["TestA"], "test_a")


def _rebound_source(rebind: str) -> str:
    return (
        "def test_t():\n    pass\n\n"
        "class TestR:\n    def test_r(self):\n        pass\n\n"
        f"{rebind}\n"
    )


def _kept_source(other: str) -> str:
    return f"def test_t():\n    pass\n\n{other}"


class TestDefinesTest:
    @pytest.mark.parametrize(
        ("classes", "func"),
        [
            ([], "test_top"),
            (["TestA"], "test_a"),
            (["TestA"], "test_async"),
            (["TestA", "TestInner"], "test_inner"),
        ],
    )
    def test_defined_in_the_named_chain(self, classes: list[str], func: str) -> None:
        assert collection.defines_test(_TESTS, classes, func)

    @pytest.mark.parametrize(
        ("classes", "func"),
        [
            (["TestB"], "test_a"),
            ([], "test_a"),
            (["TestInner"], "test_inner"),
            (["TestInner", "TestA"], "test_inner"),
            (["TestA"], "test_top"),
            ([""], "test_a"),
            (["TestA"], ""),
            (["TestNope"], "test_a"),
            (["TestB"], "test_b[case-1]"),
            ([], "test_top[x]"),
            ([], "make_thing"),
            (["TestA"], "helper"),
            (["Helpers"], "test_h"),
        ],
    )
    def test_not_defined_in_the_named_chain(self, classes: list[str], func: str) -> None:
        assert not collection.defines_test(_TESTS, classes, func)

    @pytest.mark.parametrize(
        "constructor",
        [
            "def __init__(self):\n        pass",
            "def __new__(cls):\n        return super().__new__(cls)",
            "async def __init__(self):\n        pass",
        ],
    )
    def test_class_with_its_own_constructor_is_not_collected(self, constructor: str) -> None:
        source = f"class TestC:\n    {constructor}\n\n    def test_c(self):\n        pass\n"
        assert not collection.defines_test(source, ["TestC"], "test_c")

    def test_constructor_on_an_outer_class_blocks_the_nested_test(self) -> None:
        source = (
            "class TestOuter:\n    def __init__(self):\n        pass\n\n"
            "    class TestInner:\n        def test_i(self):\n            pass\n"
        )
        assert not collection.defines_test(source, ["TestOuter", "TestInner"], "test_i")

    @pytest.mark.parametrize(("rebind", "classes", "func"), REBINDS)
    def test_a_rebound_name_is_not_collected(
        self, rebind: str, classes: list[str], func: str
    ) -> None:
        assert not collection.defines_test(_rebound_source(rebind), classes, func)

    @pytest.mark.parametrize(
        "rebind",
        [
            "    test_r = None",
            "    if True:\n        test_r = None",
            "    try:\n        pass\n    finally:\n        test_r = None",
        ],
    )
    def test_a_method_rebound_in_its_class_is_not_collected(self, rebind: str) -> None:
        source = f"class TestR:\n    def test_r(self):\n        pass\n{rebind}\n"
        assert not collection.defines_test(source, ["TestR"], "test_r")

    @pytest.mark.parametrize(("source", "classes", "func"), HIDDEN)
    def test_a_test_pytest_skips_is_not_collected(
        self, source: str, classes: list[str], func: str
    ) -> None:
        assert not collection.defines_test(source, classes, func)

    @pytest.mark.parametrize(("source", "classes", "func"), COLLECTED)
    def test_a_marked_or_switched_on_test_is_collected(
        self, source: str, classes: list[str], func: str
    ) -> None:
        assert collection.defines_test(source, classes, func)

    @pytest.mark.parametrize("other", KEPT)
    def test_a_def_that_stays_the_final_binding_is_collected(self, other: str) -> None:
        assert collection.defines_test(_kept_source(other), [], "test_t")

    def test_a_def_inside_a_block_fails_closed(self) -> None:
        """pytest collects it, but no static read proves the branch runs."""
        source = "if True:\n    def test_t():\n        pass\n"
        assert not collection.defines_test(source, [], "test_t")

    def test_the_checker_agrees_with_pytest_collection(self, tmp_path: Path) -> None:
        """Every corpus case, against a real ``pytest --collect-only`` run.

        The checker may fail closed, never open. Each fail-closed case is listed
        in FAIL_CLOSED, so a new disagreement in either direction fails here.
        """
        expected: dict[str, bool] = {}
        closed: set[str] = set()
        cases = [(r, _rebound_source(r), c, f) for r, c, f in REBINDS]
        cases += [(o, _kept_source(o), [], "test_t") for o in KEPT]
        cases += [(src, src, c, f) for src, c, f in [*HIDDEN, *COLLECTED]]
        for index, (case, source, classes, func) in enumerate(cases):
            name = f"test_case_{index}.py"
            (tmp_path / name).write_text(source, encoding="utf-8")
            node = "::".join([name, *classes, func])
            expected[node] = collection.defines_test(source, classes, func)
            closed |= {node} if case in FAIL_CLOSED else set()
        (tmp_path / "pytest.ini").write_text(
            "[pytest]\npython_files = test_*.py\n"
            "python_classes = Test*\npython_functions = test_*\n",
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        lines = result.stdout.splitlines()
        collected = {line.split("[")[0] for line in lines if line.startswith("test_case_")}
        actual = {node: node in collected for node in expected}
        assert any(actual.values()), result.stdout + result.stderr
        fail_open = {n for n in expected if expected[n] and not actual[n]}
        fail_closed = {n for n in expected if actual[n] and not expected[n]}
        assert (fail_open, fail_closed) == (set(), closed), result.stdout + result.stderr

    def test_constructor_in_a_sibling_class_does_not_block(self) -> None:
        source = (
            "class TestA:\n    def test_a(self):\n        pass\n\n"
            "class TestB:\n    def __init__(self):\n        pass\n"
        )
        assert collection.defines_test(source, ["TestA"], "test_a")

    def test_unparseable_source_is_not_defined(self) -> None:
        assert not collection.defines_test("def test_x(:\n", [], "test_x")


class TestCollectionRules:
    def test_constants_match_pyproject(self) -> None:
        config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        pytest_config = config["tool"]["pytest"]["ini_options"]
        assert pytest_config["python_files"] == [collection.PYTEST_FILE_GLOB]
        assert pytest_config["python_classes"] == [f"{collection.PYTEST_CLASS_PREFIX}*"]
        assert pytest_config["python_functions"] == [f"{collection.PYTEST_FUNC_PREFIX}*"]
        assert pytest_config["testpaths"] == [collection.PYTEST_ROOT]

    @pytest.mark.parametrize("path", ["tests/test_a.py", "tests/skills/demo/test_demo.py"])
    def test_collected_files(self, path: str) -> None:
        assert collection.is_collected_file(path)

    @pytest.mark.parametrize(
        "path",
        [
            "tests/helpers.py",
            "tests/conftest.py",
            "tests/skills/demo/demo_test.py",
            "tests/test_demo.txt",
            "scripts/test_demo.py",
            "test_demo.py",
            "tests/../scripts/test_demo.py",
            "tests",
            "",
        ],
    )
    def test_files_pytest_does_not_collect(self, path: str) -> None:
        assert not collection.is_collected_file(path)
