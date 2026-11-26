"""Python dependency counting from a Tree-sitter syntax tree (issue #7436)."""

import subprocess
import sys
from pathlib import Path

import pytest

from .test_assess import _commit, _init_repo, _mod, _regression_argv, _run_git

assess_content = _mod.assess_content


@pytest.mark.parametrize(
    ("source", "statements"),
    [
        ("import requests", 1),
        ("import requests as r", 1),
        ("import requests, flask", 1),
        ("import a.b.c", 1),
        ("from requests import get", 1),
        ("from requests import (\n    get,\n    post,\n)", 1),
        ("from requests import *", 1),
        ("from . import sibling", 1),
        ("from ..pkg.mod import thing", 1),
        ("def f():\n    import requests\n    from flask import Flask", 2),
        ("class C:\n    import requests", 1),
        ("try:\n    import yaml\nexcept ImportError:\n    yaml = None", 1),
        ("if TYPE_CHECKING:\n    from requests import Session", 1),
        ("x = 1; import requests", 1),
    ],
)
def test_python_counts_each_dependency_statement_form(source: str, statements: int) -> None:
    """Every import and from-import statement counts, at any nesting depth."""
    coupling = assess_content(Path("forms.py"), source + "\n").coupling

    assert coupling.reasons[0] == f"{statements} import/dependency statements"
    assert coupling.value == 10.0 - statements


@pytest.mark.parametrize(
    "source",
    [
        's = "import requests"\n',
        "# import requests\n",
        '"""\nimport requests\nfrom flask import Flask\n"""\n',
        "def f():\n    '''\n    import requests\n    '''\n",
        'query = f"from {table} import rows"\n',
    ],
)
def test_python_ignores_import_text_in_strings_and_comments(source: str) -> None:
    """Text that only looks like an import is not a dependency."""
    coupling = assess_content(Path("text.py"), source).coupling

    assert coupling.reasons[0] == "0 import/dependency statements"
    assert coupling.value == 10.0


def test_python_keeps_the_standard_library_exclusion() -> None:
    """Standard-library statements are reported but not scored (issue #7354)."""
    source = "import os\nfrom __future__ import annotations\nimport requests\n"

    coupling = assess_content(Path("mixed.py"), source).coupling

    assert coupling.value == 9.0
    assert coupling.reasons[:2] == [
        "3 import/dependency statements",
        "2 Python standard library (not scored), 1 application or third-party (scored)",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "import os .path\n",
        "import os . path as p, json\n",
        "import os.\\\n    path\n",
        "from os . path import join\n",
    ],
)
def test_python_spacing_around_dots_keeps_the_stdlib_exemption(source: str) -> None:
    """Whitespace or a line continuation inside a dotted name is not part of it."""
    coupling = assess_content(Path("spaced.py"), source).coupling

    assert coupling.value == 10.0


@pytest.mark.parametrize(
    ("source", "module"),
    [
        ("from . json import y\n", ".json"),
        ("from .. import z\n", ".."),
        ("from .a . b import c\n", ".a.b"),
    ],
)
def test_python_relative_module_keeps_its_dots(source: str, module: str) -> None:
    """A relative module is named by its dots plus its identifiers."""
    statement = _mod._dependency_nodes(source, _mod._PYTHON_GRAMMAR)[0]

    assert _mod._python_statement_modules(statement) == [module]


def test_python_relative_import_named_like_stdlib_is_scored() -> None:
    """``from .json import x`` is first-party even though ``json`` is stdlib."""
    coupling = assess_content(Path("rel.py"), "from .json import thing\n").coupling

    assert coupling.value == 9.0


@pytest.mark.parametrize(
    "source",
    ["import (\n", "def f(:\n    pass\n", "from import x\n", "lazy import json\n"],
)
def test_python_parse_error_fails_instead_of_guessing(source: str) -> None:
    """A file the pinned grammar cannot parse raises, never scores."""
    with pytest.raises(_mod.PythonParserError, match="tree-sitter-python==0.25.0"):
        assess_content(Path("broken.py"), source)


def test_invalid_python_fails_cli_without_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 1 names the file and the grammar, and prints no report."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "invalid.py"
    target.write_text("def f(:\n    pass\n", encoding="utf-8")

    result = _mod.main(["--target", str(target), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "Python" in output.err
    assert target.name in output.err
    assert not output.out


@pytest.mark.parametrize("module_name", ["tree_sitter", "tree_sitter_python"])
def test_missing_python_parser_fails_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
) -> None:
    """A missing package exits 1 with install guidance, never a passing score."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, module_name, None)
    target = tmp_path / "example.py"
    target.write_text("def example():\n    return 1\n", encoding="utf-8")

    result = _mod.main(["--target", str(target), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "tree-sitter-python==0.25.0" in output.err
    assert "install" in output.err.lower()
    assert not output.out


def test_missing_python_grammar_does_not_affect_csharp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each language imports only its own grammar."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "tree_sitter_python", None)
    target = tmp_path / "Imports.cs"
    target.write_text("using System.IO;\n", encoding="utf-8")

    assert _mod.main(["--target", str(target), "--format", "json"]) == 0


def test_missing_core_package_fails_csharp_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both grammars share tree-sitter, so its absence fails C# as well."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    target = tmp_path / "Imports.cs"
    target.write_text("using System.IO;\n", encoding="utf-8")

    assert _mod.main(["--target", str(target), "--format", "json"]) == 1
    assert "tree-sitter-c-sharp==0.23.5" in capsys.readouterr().err


def test_parser_startup_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A grammar that cannot load raises a parser error naming the pins."""
    import tree_sitter_python

    def broken_language() -> object:
        raise OSError("grammar library failed to load")

    monkeypatch.setattr(tree_sitter_python, "language", broken_language)

    with pytest.raises(_mod.PythonParserError, match="failed to start or run"):
        assess_content(Path("startup.py"), "import os\n")


def test_python_parse_error_at_base_names_the_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression mode fails closed on an unparsable base and says where."""
    _init_repo(tmp_path)
    _commit(tmp_path, "legacy.py", "def f(:\n    pass\n", "broken base")
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "legacy.py", "def f():\n    pass\n", "fixed head")
    monkeypatch.chdir(tmp_path)

    result = _mod.main(_regression_argv())
    err = capsys.readouterr().err

    assert result == 1
    assert f"legacy.py at {base_sha}" in err


class _FromImportWithoutModule:
    """A parse-tree node shape the grammar should never produce."""

    type = "import_from_statement"
    start_point = (4, 0)

    def child_by_field_name(self, name: str) -> None:
        return None


def test_from_import_without_a_module_fails_closed() -> None:
    """An unexpected node shape raises the parser error, so the scan exits 1."""
    with pytest.raises(_mod.PythonParserError, match="line 5"):
        _mod._python_statement_modules(_FromImportWithoutModule())


@pytest.mark.parametrize("failure", [AttributeError("no name"), StopIteration()])
def test_unexpected_node_shapes_fail_closed(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    """Any malformed statement node raises the parser error, never an unscored file."""

    def malformed(node: object) -> list[str]:
        raise failure

    monkeypatch.setattr(_mod, "_python_statement_modules", malformed)

    with pytest.raises(_mod.PythonParserError, match="unexpected parse-tree shape"):
        _mod._count_python_imports("import os\n")
