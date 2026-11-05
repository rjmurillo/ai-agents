"""Tests that a branch cannot hide a finding from check_unused_arguments.py.

Each bypass fixture first proves the hole is real: it runs the argv the gate
used before ``--isolated`` and expects no finding. Then it expects the gate to
exit 1 on the same repository.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from check_unused_arguments import GateConfigError, scan

from scripts.validation.unused_arguments_owner import owning_function
from tests.validation.unused_arguments_helpers import (
    UNUSED,
    UNUSED_KEY,
    add_file,
    make_repo,
    run_gate,
    scan_keys,
    write_baseline,
)

PRE_ISOLATED_ARGV = ["check", "--select", "ARG", "--output-format", "json", "--no-cache"]

BYPASSES = {
    "per-file-ignores in pyproject.toml": {
        "pyproject.toml": '[tool.ruff.lint.per-file-ignores]\n"scripts/mod.py" = ["ARG"]\n',
    },
    "exclude in pyproject.toml": {
        "pyproject.toml": '[tool.ruff]\nexclude = ["scripts/mod.py"]\n',
    },
    "extend-exclude in pyproject.toml": {
        "pyproject.toml": '[tool.ruff]\nextend-exclude = ["scripts/mod.py"]\n',
    },
    "dummy-variable-rgx in pyproject.toml": {
        "pyproject.toml": '[tool.ruff.lint]\ndummy-variable-rgx = "^path$"\n',
    },
    "root ruff.toml per-file-ignores": {
        "ruff.toml": '[lint.per-file-ignores]\n"scripts/mod.py" = ["ARG"]\n',
    },
    "nested scripts/ruff.toml dummy-variable-rgx": {
        "scripts/ruff.toml": '[lint]\ndummy-variable-rgx = "^path$"\n',
    },
    "nested scripts/ruff.toml extend-exclude": {
        "scripts/ruff.toml": 'extend-exclude = ["mod.py"]\n',
    },
}


def _old_argv_findings(repo: Path) -> list[object]:
    """Run ruff as the gate did before ``--isolated``, and return its JSON rows."""
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", *PRE_ISOLATED_ARGV, "--ignore-noqa", "--force-exclude"]
        + ["--", "scripts/mod.py"],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return list(json.loads(completed.stdout))


@pytest.mark.parametrize("name", sorted(BYPASSES))
def test_a_ruff_config_edit_cannot_hide_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    repo = make_repo(tmp_path)
    for relpath, text in BYPASSES[name].items():
        add_file(repo, relpath, text)

    assert _old_argv_findings(repo) == [], "the fixture no longer hides a finding"
    assert run_gate(repo, write_baseline(tmp_path)) == 1
    assert f"new unused argument: {UNUSED_KEY}" in capsys.readouterr().err


def test_a_shadowing_ruff_module_in_the_repo_cannot_hide_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    add_file(repo, "ruff.py", "print('[]')\n")
    shadowed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "ARG", "--output-format", "json"],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert shadowed.stdout.strip() == "[]", "the fixture no longer shadows ruff"
    assert run_gate(repo, write_baseline(tmp_path)) == 1
    assert f"new unused argument: {UNUSED_KEY}" in capsys.readouterr().err


def test_isolated_ruff_reads_no_repository_config(tmp_path: Path) -> None:
    # A config that selects nothing but a different rule must not change the result.
    repo = make_repo(tmp_path)
    add_file(repo, "pyproject.toml", '[tool.ruff.lint]\nselect = ["E"]\nignore = ["ARG"]\n')

    assert scan_keys(repo) == [UNUSED_KEY]


@pytest.mark.parametrize(
    "source",
    [
        "def f(path):\n    pass\n",
        "def f(path):\n    ...\n",
        'def f(path):\n    """Only a docstring."""\n',
        "def f(path):\n    raise NotImplementedError\n",
        "def f(path):\n    raise NotImplementedError('later')\n",
        "import typing\nclass C:\n    @typing.override\n    def m(self, p):\n        return 1\n",
        "import abc\nclass C:\n    @abc.abstractmethod\n    def m(self, p):\n        return 1\n",
        "from typing import overload\n@overload\ndef f(path: int) -> int: ...\n",
        "class C:\n    def __eq__(self, other):\n        return True\n",
        "def f(path):\n    return locals()\n",
        "def f(_path, __other, _):\n    return 1\n",
    ],
    ids=[
        "pass-stub",
        "ellipsis-stub",
        "docstring-stub",
        "raise-not-implemented",
        "raise-not-implemented-with-message",
        "override",
        "abstractmethod",
        "overload",
        "dunder-method",
        "locals-call",
        "underscore-names",
    ],
)
def test_the_exemptions_the_docstring_lists_are_not_findings(tmp_path: Path, source: str) -> None:
    repo = make_repo(tmp_path, source=source)

    assert scan_keys(repo) == []


@pytest.mark.parametrize(
    ("source", "key"),
    [
        ("def f(*args):\n    return 1\n", "scripts/mod.py: ARG001 args in f"),
        ("def f(**kwargs):\n    return 1\n", "scripts/mod.py: ARG001 kwargs in f"),
        (
            "class C:\n    def m(self, extra):\n        return 1\n",
            "scripts/mod.py: ARG002 extra in C.m",
        ),
        (
            "class C:\n    @staticmethod\n    def m(extra):\n        return 1\n",
            "scripts/mod.py: ARG004 extra in C.m",
        ),
    ],
)
def test_shapes_next_to_the_exemptions_are_still_findings(
    tmp_path: Path, source: str, key: str
) -> None:
    repo = make_repo(tmp_path, source=source)

    assert scan_keys(repo) == [key]


def test_a_finding_in_a_file_with_default_excluded_directory_name_is_still_scanned(
    tmp_path: Path,
) -> None:
    # ruff's default exclude list names build/, dist/, and similar. With
    # --isolated and no --force-exclude, an explicit path is always checked.
    repo = make_repo(tmp_path)
    add_file(repo, "scripts/build/mod.py", UNUSED)

    assert scan(repo).keys == ["scripts/build/mod.py: ARG001 path in f", UNUSED_KEY]


def _owner(source: str, name: str, row: int, column: int = 1) -> str:
    return owning_function(textwrap.dedent(source), "mod.py", row, column, name)


def test_owner_of_a_top_level_function() -> None:
    assert _owner("def f(path):\n    return 1\n", "path", 1) == "f"


def test_owner_of_a_method_names_the_class() -> None:
    assert _owner("class C:\n    def m(self, path):\n        return 1\n", "path", 2) == "C.m"


def test_owner_of_a_nested_function_names_the_outer_function() -> None:
    source = "def outer():\n    def inner(path):\n        return 1\n    return inner\n"

    assert _owner(source, "path", 2) == "outer.inner"


def test_owner_of_an_async_function() -> None:
    assert _owner("async def f(path):\n    return 1\n", "path", 1) == "f"


def test_owner_of_a_lambda() -> None:
    assert _owner("g = lambda path: 1\n", "path", 1) == "<lambda>"


def test_owner_tiebreak_uses_the_column_when_two_functions_share_a_row() -> None:
    source = "def f(path): return lambda path: 1\n"

    assert _owner(source, "path", 1, column=source.index("path") + 1) == "f"
    assert _owner(source, "path", 1, column=source.rindex("path") + 1) == "f.<lambda>"


def test_owner_column_counts_characters_not_bytes() -> None:
    source = 'e = "\u00e9"; f = lambda path: (lambda path: 1)\n'

    assert _owner(source, "path", 1, column=source.index("path") + 1) == "<lambda>"
    assert _owner(source, "path", 1, column=source.rindex("path") + 1) == "<lambda>.<lambda>"


def test_owner_raises_when_no_argument_is_at_the_location() -> None:
    with pytest.raises(GateConfigError, match="no argument `path` at mod.py:9"):
        _owner("def f(path):\n    return 1\n", "path", 9)


def test_owner_raises_on_source_the_parser_rejects() -> None:
    with pytest.raises(GateConfigError, match="cannot parse mod.py"):
        owning_function("def broken(:\n", "mod.py", 1, 1, "path")
