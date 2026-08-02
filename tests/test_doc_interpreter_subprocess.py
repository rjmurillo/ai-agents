"""Tests for reachable Python subprocess target detection."""

import ast

from scripts.validation.doc_interpreter_subprocess import python_subprocess_targets


def test_unused_subprocess_helper_is_not_reachable() -> None:
    tree = ast.parse(
        "import subprocess\nimport sys\n"
        "def unused():\n"
        "    subprocess.run([sys.executable, 'validate.py'], check=False)\n"
        "print('ready')\n"
    )

    assert python_subprocess_targets(tree, {"validate.py"}) == set()


def test_assignment_after_call_does_not_resolve_target() -> None:
    tree = ast.parse(
        "import subprocess\nimport sys\n"
        "subprocess.run([sys.executable, target], check=False)\n"
        "target = 'validate.py'\n"
    )

    assert python_subprocess_targets(tree, {"validate.py"}) == set()
