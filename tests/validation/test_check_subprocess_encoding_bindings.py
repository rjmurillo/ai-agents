"""Binding-order regression tests for the subprocess encoding gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_subprocess_encoding import find_violations


@pytest.mark.parametrize(
    "source",
    [
        ('def run(argv, **kwargs):\n    return None\nrun(["x"], text=True, encoding="utf-8")\n'),
        (
            "import subprocess\n"
            "PIPE = object()\n"
            'subprocess.run(["x"], stdout=PIPE, encoding="utf-8")\n'
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "runner = lambda *args, **kwargs: None\n"
            'runner(["x"], text=True, encoding="utf-8")\n'
        ),
        (
            "import subprocess as sp\n"
            "pipe = sp.PIPE\n"
            "pipe = object()\n"
            'sp.run(["x"], stdout=pipe, encoding="utf-8")\n'
        ),
        (
            "import subprocess as sp\n"
            "def make_alias():\n"
            "    runner = sp.run\n"
            "def use_other_runner():\n"
            "    runner = lambda *args, **kwargs: None\n"
            '    runner(["x"], text=True, encoding="utf-8")\n'
        ),
    ],
)
def test_unrelated_or_rebound_names_do_not_leak_subprocess_bindings(
    source: str,
) -> None:
    """Mutation control: removing scope or clear operations makes these fail."""
    assert find_violations(source) == []


def test_outer_subprocess_alias_remains_visible_in_nested_scope() -> None:
    source = (
        'import subprocess as sp\ndef invoke():\n    sp.run(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [3]


@pytest.mark.parametrize(
    "source",
    [
        (
            "import subprocess as sp\n"
            "def invoke(runner=sp.run):\n"
            '    runner(["x"], text=True, encoding="utf-8")\n'
        ),
        (
            "import subprocess as sp\n"
            "def invoke(*, pipe=sp.PIPE):\n"
            '    sp.run(["x"], stdout=pipe, encoding="utf-8")\n'
        ),
    ],
)
def test_subprocess_parameter_defaults_are_flagged(source: str) -> None:
    assert find_violations(source) == [3]
