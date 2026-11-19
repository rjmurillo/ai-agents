"""TypeScript dependency counting from a syntax tree (issue #7435)."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .test_assess import _commit, _init_repo, _regression_argv, _run_git
from .test_csharp_coupling import _mod

assess_content = _mod.assess_content

_SUFFIXES = [".ts", ".tsx"]


def _dependencies(source: str, suffix: str) -> int:
    coupling = assess_content(Path(f"module{suffix}"), source).coupling
    assert coupling.confidence == 0.6
    count = int(coupling.reasons[0].split()[0])
    assert coupling.value == max(1.0, 10.0 - count)
    return count


@pytest.mark.parametrize("suffix", _SUFFIXES)
@pytest.mark.parametrize(
    "statement",
    [
        'import x from "a";',
        'import type { A } from "a";',
        'import "side-effect";',
        'import * as ns from "a";',
        'import x = require("a");',
        'export * from "a";',
        'export { a } from "a";',
        'export type { T } from "a";',
        'const x = require("a");',
        'function load() { return require("a"); }',
        'const m = await import("a");',
        'type M = typeof import("a");',
        'let value: import("a").T;',
        'import {\n  a,\n  b,\n} from "a";',
    ],
)
def test_each_typescript_dependency_form_counts_once(statement: str, suffix: str) -> None:
    """AC1/AC2: Every issue statement form is one dependency, in .ts and .tsx."""
    assert _dependencies(statement, suffix) == 1


@pytest.mark.parametrize("suffix", _SUFFIXES)
@pytest.mark.parametrize(
    "source",
    [
        "export { a };",
        "export const a = 1;",
        'load("a");',
        'require.resolve("a");',
        "function require(parts: TemplateStringsArray) { return parts[0]; }\nrequire`a`;",
        "const text = \"import x from 'y'; require('z')\";",
        "const text = `\nimport a from 'b';\nrequire('c');\n`;",
        '/*\nimport x from "y";\nrequire("z");\n*/',
        '// import x from "y"',
    ],
)
def test_lookalike_text_is_not_a_dependency(source: str, suffix: str) -> None:
    """Strings, comments, local exports, and other calls name no module."""
    assert _dependencies(source, suffix) == 0


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('export * from "a";\nexport { b } from "b";', 2),
        ('const m = await import("a");', 1),
        ('const text = "x = require(1)";\nimport a from "a";', 1),
        ("const text = `\nimport a from 'b';\n`;", 0),
    ],
)
def test_syntax_counts_differ_from_the_line_regex(source: str, expected: int) -> None:
    """The old JavaScript regex miscounts each of these TypeScript sources."""
    regex = _mod._IMPORT_PATTERNS["javascript"]
    regex_count = sum(1 for line in source.split("\n") if regex.search(line))

    assert regex_count != expected
    assert _dependencies(source, ".ts") == expected


@pytest.mark.parametrize(
    ("suffix", "source", "parses"),
    [
        (".ts", "const x = <Foo>bar;", True),
        (".tsx", "const x = <Foo>bar;", False),
        (".tsx", "const e = <div />;", True),
        (".ts", "const e = <div />;", False),
        (".TSX", "const e = <div />;", True),
    ],
)
def test_file_suffix_selects_the_typescript_or_tsx_grammar(
    suffix: str, source: str, parses: bool
) -> None:
    """A type cast parses only as .ts, JSX only as .tsx, and suffix case is ignored."""
    path = Path(f"View{suffix}")
    if parses:
        assert assess_content(path, source).coupling.reasons[0] == "0 import/dependency statements"
    else:
        with pytest.raises(_mod.TypeScriptParserError, match="could not parse"):
            assess_content(path, source)


def _scan_fails_closed(target: Path, capsys: pytest.CaptureFixture[str]) -> str:
    result = _mod.main(["--target", str(target), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert target.name in output.err
    assert not output.out
    return output.err


@pytest.mark.parametrize("module_name", ["tree_sitter", "tree_sitter_typescript"])
def test_missing_typescript_parser_fails_cli_without_affecting_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
) -> None:
    """AC2: A missing package exits 1 and names the install, never a regex count."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, module_name, None)
    target = tmp_path / "imports.ts"
    target.write_text('import x from "a";\n', encoding="utf-8")
    python = tmp_path / "example.py"
    python.write_text("def example():\n    return 1\n", encoding="utf-8")

    err = _scan_fails_closed(target, capsys)

    assert "tree-sitter-typescript==0.23.2" in err
    assert "install" in err.lower()
    assert "references/typescript-parser.md" in err
    assert _mod.main(["--target", str(python), "--format", "json"]) == 0


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ('import x from "a"\nconst = ;\n', "syntax error"),
        ('export type * from "a";\n', "valid TypeScript that the grammar does not support"),
        ("type T<in out U> = U;\n", "valid TypeScript that the grammar does not support"),
    ],
)
def test_unparseable_typescript_fails_cli_with_a_grammar_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source: str,
    message: str,
) -> None:
    """AC2: A parse error, or syntax the pinned grammar lacks, exits 1 without a report."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "Invalid.ts"
    target.write_text(source, encoding="utf-8")

    err = _scan_fails_closed(target, capsys)

    assert "tree-sitter-typescript==0.23.2" in err
    assert message in err


@pytest.mark.parametrize("error_type", [OSError, ValueError, TypeError, RuntimeError, KeyError])
def test_broken_typescript_parser_fails_cli_without_a_success_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_type: type[Exception],
) -> None:
    """AC2: Native-load and parser-startup errors cannot pass the gate."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "imports.tsx"
    target.write_text('import x from "a";\n', encoding="utf-8")
    report = tmp_path / "report.json"

    def broken_parser(_language: object) -> None:
        raise error_type("Parser initialization failed")

    monkeypatch.setattr(importlib.import_module("tree_sitter"), "Parser", broken_parser)

    result = _mod.main(["--target", str(target), "--format", "json", "--output", str(report)])
    output = capsys.readouterr()

    assert result == 1
    assert "TypeScript parser failed to start or run" in output.err
    assert "Parser initialization failed" in output.err
    assert target.name in output.err
    assert not output.out
    assert not report.exists()


def test_unparseable_base_typescript_blob_fails_regression_mode_with_path_and_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "base.ts", "const = ;\n", "base is invalid")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "base.ts", 'import x from "a";\n', "head is valid")
    monkeypatch.chdir(tmp_path)

    result = _mod.main(_regression_argv())
    output = capsys.readouterr()

    assert result == 1
    assert "base.ts at " in output.err
    assert "could not parse" in output.err
    assert not output.out


def test_typescript_parser_failure_is_not_recorded_as_an_unscored_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory scan stops on the bad file instead of reporting the others."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "good.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bad.ts").write_text("const = ;\n", encoding="utf-8")

    result = _mod.main(["--target", str(tmp_path), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "bad.ts" in output.err
    assert not output.out


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
def test_shipped_typescript_parser_runs_from_consumer_directory(
    tmp_path: Path, plugin_parts: tuple[str, ...]
) -> None:
    """AC3: Every shipped scanner parses TypeScript outside its own plugin directory."""
    root = Path(__file__).resolve().parents[3]
    script = root.joinpath(
        "src", *plugin_parts, "skills", "code-qualities-assessment", "scripts", "assess.py"
    )
    target = tmp_path / "Consumer.tsx"
    target.write_text(
        'import React from "react";\nexport * from "./types";\n'
        "const text = \"require('not-a-dependency')\";\n"
        "export const View = () => <div>{text}</div>;\n",
        encoding="utf-8",
    )

    def scan(*flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *flags, str(script), "--target", str(target), "--format", "json"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )

    result = scan("-I")

    assert result.returncode == 0, result.stderr
    coupling = json.loads(result.stdout)["files"][0]["coupling"]
    assert coupling["value"] == 8.0
    assert coupling["confidence"] == 0.6
    assert coupling["reasons"][0] == "2 import/dependency statements"

    without_packages = scan("-I", "-S")

    assert without_packages.returncode == 1
    assert "tree-sitter-typescript" in without_packages.stderr
    assert not without_packages.stdout
