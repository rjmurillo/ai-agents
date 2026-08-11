from __future__ import annotations

import ast
from pathlib import Path

from scripts.ci.cli_exit_contract_coverage import covered_stems
from scripts.validation.check_subprocess_encoding import find_violations
from scripts.validation.check_unreachable_code import _find_in_block


def test_unreachable_gate_detects_nested_block_after_return() -> None:
    source = """
def f(flag):
    if flag:
        return 1
        print("dead")
    return 0
"""

    tree = ast.parse(source)
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)

    violations = _find_in_block(function.body, Path("nested_case.py"), function.name)

    assert violations == [(Path("nested_case.py"), "f", 5)]


def test_unreachable_gate_ignores_nested_function_body_for_outer_function() -> None:
    source = """
def outer():
    def inner():
        return 1
        print("dead")
    return inner()
"""

    tree = ast.parse(source)
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    violations = [
        finding
        for function in functions
        for finding in _find_in_block(
            function.body,
            Path("nested_function.py"),
            function.name,
        )
    ]

    assert [function_name for _, function_name, _ in violations] == ["inner"]


def test_subprocess_encoding_accepts_mixed_case_utf8_alias() -> None:
    source = """
import subprocess

def f():
    return subprocess.run(["cmd"], capture_output=True, text=True, encoding="Utf-8")
"""

    assert find_violations(source, "mixed_utf8.py") == [5]


def test_subprocess_encoding_respects_errors_handler() -> None:
    source = """
import subprocess

def f():
    return subprocess.run(
        ["cmd"], capture_output=True, text=True, encoding="UTF_8", errors="replace"
    )
"""

    assert find_violations(source, "handled_utf8.py") == []


def test_cli_exit_contract_does_not_credit_local_main_from_script_string() -> None:
    source = '''
SCRIPT = "scripts/ci/fake_gate.py"

def main(argv=None):
    return 1

def test_local_main_not_gate_main():
    assert main(["--bad"]) == 1
'''

    assert covered_stems(source, frozenset({"fake_gate"})) == set()


def test_cli_exit_contract_credits_assigned_module_main() -> None:
    source = '''
mod = _load_module("fake_gate")
main = mod.main

def test_gate_main():
    assert main(["--bad"]) == 1
'''

    assert covered_stems(source, frozenset({"fake_gate"})) == {"fake_gate"}
