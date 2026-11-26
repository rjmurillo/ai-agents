"""JavaScript dependency counting from a Tree-sitter syntax tree (issue #7434).

JavaScript reuses the pinned TSX grammar from tree-sitter-typescript.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from .shipped_assess import assert_shipped_scanner_counts
from .test_assess import _commit, _init_repo, _mod, _regression_argv, _run_git

assess_content = _mod.assess_content


@pytest.mark.parametrize(
    "statement",
    [
        'import a from "a";',
        "import 'side-effect';",
        'import * as ns from "ns";',
        'import { x, y as z } from "./x.js";',
        'import a, { b } from "a";',
        'import\n  {\n    x,\n  }\n  from "./multi.js";',
        'export { x } from "./x.js";',
        'export * from "./all.js";',
        'export * as all from "./all.js";',
        'const fs = require("fs");',
        "const { join } = require('path');",
        'require("side-effect");',
        'const lazy = import("./lazy.js");',
        'async function f() { return await import("./later.js"); }',
        'const view = <div>{require("./component")}</div>;',
    ],
)
def test_javascript_dependency_statements_count(statement: str) -> None:
    """Each import, re-export, require(), and import() form is one dependency."""
    coupling = assess_content(Path("deps.js"), statement).coupling

    assert coupling.reasons[0] == "1 import/dependency statements"
    assert coupling.value == 9.0
    assert coupling.confidence == 0.6


@pytest.mark.parametrize(
    "source",
    [
        '// import a from "a";',
        '/* const b = require("b"); */',
        "const text = \"import a from 'a'\";",
        'const text = `require("b")`;',
        'obj.require("member-call");',
        "const r = require;",
        "export const value = 1;",
        "export { value };",
        "export default function f() {}",
        'const importer = "import";',
    ],
)
def test_javascript_non_dependencies_do_not_count(source: str) -> None:
    """Comments, strings, member calls, and local exports are not dependencies."""
    coupling = assess_content(Path("plain.js"), source).coupling

    assert coupling.reasons[0] == "0 import/dependency statements"
    assert coupling.value == 10.0


@pytest.mark.parametrize("suffix", [".js", ".jsx", ".mjs", ".cjs"])
def test_every_javascript_suffix_uses_the_parser(suffix: str) -> None:
    """Only the parser counts both statements; the old line regex counted 1."""
    source = 'import a from "a"; export * from "b";\n'

    coupling = assess_content(Path(f"module{suffix}"), source).coupling

    assert coupling.reasons[0] == "2 import/dependency statements"
    assert coupling.value == 8.0


def test_javascript_counts_nodes_not_lines() -> None:
    """Two statements on one line count twice; a line-based regex counted once."""
    source = 'import a from "a"; import b from "b";\nconst c = require("c"), d = require("d");\n'

    coupling = assess_content(Path("dense.js"), source).coupling

    assert coupling.reasons[0] == "4 import/dependency statements"
    assert coupling.value == 6.0


def test_flow_annotated_javascript_parses() -> None:
    """The TSX grammar accepts Flow-style annotations common in published .js files."""
    source = '// @flow\nimport type { T } from "./types";\nfunction f(x: number): ?T {}\n'

    coupling = assess_content(Path("flow.js"), source).coupling

    assert coupling.reasons[0] == "1 import/dependency statements"


def test_javascript_adds_no_parser_import_to_the_scanner() -> None:
    """Reusing the TSX grammar adds no grammar package of its own.

    The set holds the C#, TypeScript, and Python (issue #7436) grammars only.
    """
    assert _mod._python_external_imports(Path(_mod.__file__)) == {
        "tree_sitter",
        "tree_sitter_c_sharp",
        "tree_sitter_python",
        "tree_sitter_typescript",
    }


@pytest.mark.parametrize("module_name", ["tree_sitter", "tree_sitter_typescript"])
def test_missing_javascript_parser_fails_cli_without_affecting_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
) -> None:
    """Missing parser packages fail explicitly, never report a JavaScript score."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, module_name, None)
    javascript = tmp_path / "deps.js"
    javascript.write_text('import a from "a";\n', encoding="utf-8")
    python = tmp_path / "example.py"
    python.write_text("def example():\n    return 1\n", encoding="utf-8")

    result = _mod.main(["--target", str(javascript), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "tree-sitter-typescript==0.23.2" in output.err
    assert "install" in output.err.lower()
    assert javascript.name in output.err
    assert not output.out
    # Python shares tree_sitter (issue #7436), so only a missing TypeScript
    # grammar leaves Python scoring intact.
    python_exit = 0 if module_name == "tree_sitter_typescript" else 1
    assert _mod.main(["--target", str(python), "--format", "json"]) == python_exit


@pytest.mark.parametrize(
    "source",
    [
        "import {\n",
        'const x = ;\nimport a from "a";\n',
        'interface.on("line", handle);\n',
    ],
)
def test_unparseable_javascript_fails_cli_instead_of_reporting_a_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source: str,
) -> None:
    """A syntax error, or a TypeScript keyword as an identifier, is never guessed."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "broken.js"
    target.write_text(source, encoding="utf-8")

    result = _mod.main(["--target", str(target), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "tree-sitter-typescript==0.23.2" in output.err
    assert "could not parse" in output.err
    assert target.name in output.err
    assert not output.out


def test_unparseable_base_javascript_blob_fails_regression_mode_with_path_and_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "base.js", "import {\n", "base is invalid")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "base.js", 'import a from "a";\n', "head is valid")
    monkeypatch.chdir(tmp_path)

    result = _mod.main(_regression_argv())
    output = capsys.readouterr()

    assert result == 1
    assert "base.js at " in output.err
    assert "could not parse" in output.err
    assert not output.out


@pytest.mark.parametrize(
    "error_type", [OSError, ValueError, TypeError, RuntimeError, AttributeError, KeyError]
)
def test_broken_javascript_parser_fails_cli_without_a_success_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_type: type[Exception],
) -> None:
    """Native-load and grammar-initialization errors cannot pass the gate."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "deps.js"
    target.write_text('import a from "a";\n', encoding="utf-8")
    report = tmp_path / "report.json"

    def broken_parser(_language: object) -> None:
        raise error_type("Parser initialization failed")

    monkeypatch.setattr(importlib.import_module("tree_sitter"), "Parser", broken_parser)

    result = _mod.main(["--target", str(target), "--format", "json", "--output", str(report)])
    output = capsys.readouterr()

    assert result == 1
    assert "JavaScript parser failed to start or run" in output.err
    assert "Parser initialization failed" in output.err
    assert target.name in output.err
    assert not output.out
    assert not report.exists()


@pytest.mark.parametrize(
    "plugin_parts",
    [
        ("claude",),
        ("copilot-cli",),
        ("codex",),
        ("cursor",),
        ("hermes", "project-toolkit-delivery"),
        ("muse",),
    ],
)
def test_shipped_javascript_parser_runs_from_consumer_directory(
    tmp_path: Path, plugin_parts: tuple[str, ...]
) -> None:
    """Every shipped scanner parses JavaScript outside its own plugin directory."""
    target = tmp_path / "consumer.mjs"
    target.write_text(
        'import a from "a"; export * from "./all.js";\n// import b from "b";\n'
        'const text = "require(\'c\')";\nconst lazy = await import("./lazy.js");\n',
        encoding="utf-8",
    )

    assert_shipped_scanner_counts(plugin_parts, target, 7.0, 3)
