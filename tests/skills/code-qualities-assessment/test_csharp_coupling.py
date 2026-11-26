"""C# directive and resource classification regressions for issues #7406 and #7459."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from .shipped_assess import assert_shipped_scanner_counts
from .test_assess import _commit, _init_repo, _mod, _regression_argv, _run_git

assess_content = _mod.assess_content


@pytest.mark.parametrize(
    "directive",
    [
        "using System.IO;",
        "    using System . IO ; // namespace import",
        "using global::System.IO;",
        "using @namespace.IO;",
        "using Company.\u65e5\u672c\u8a9e;",
        "using System.IO /* streams */;",
        "using/* namespace */System /* scope */ . IO;",
        "using IO = System.IO;",
        "using \u03a9 = System.IO;",
        "using @var = System.IO.MemoryStream;",
        "using Streams = System.Collections.Generic.List<System.IO.Stream>;",
        "using unsafe Pointer = int*;",
        "using static System.Math;",
        "using static Example.Factory<System.IO.Stream>;",
        "global using System.IO;",
        "global using IO = global::System.IO;",
        "global using unsafe Pointer = int*;",
        "global using static System.Math;",
        "global /* shared */ using static System.Math;",
        "using\n    System.IO\n    ;",
        "global /* shared\n import */ using static\n System.Math;",
    ],
)
def test_csharp_directives_count_as_dependencies(directive: str) -> None:
    """AC2: Namespace, alias, static, and global directives remain dependencies.

    Whether a directive is scored depends on its namespace; see
    test_csharp_system_namespace_directives_are_reported_not_scored.
    """
    coupling = assess_content(Path("Imports.cs"), directive).coupling

    assert coupling.reasons[0] == "1 import/dependency statements"
    assert coupling.confidence == 0.6


@pytest.mark.parametrize(
    "resource",
    [
        "using var stream = new MemoryStream();",
        "    using Stream stream = new MemoryStream();",
        "using System.IO.Stream stream = new MemoryStream();",
        "using global::System.IO.Stream stream = new MemoryStream();",
        "using Resource<Stream> resource = Open();",
        "using @var resource = Open();",
        "using \u03a9 stream = Open();",
        "using /* cleanup */ System.IO.Stream /* variable */ stream = new MemoryStream();",
        "using (var stream = new MemoryStream()) { }",
        "using (Stream stream = new MemoryStream()) { }",
        "using (stream) { }",
        "await using var stream = new MemoryStream();",
        "await /* cleanup */ using var stream = new MemoryStream();",
        "await using Stream stream = new MemoryStream();",
        "await using (var stream = new MemoryStream()) { }",
        "await using (stream) { }",
    ],
)
def test_csharp_resources_are_not_dependencies(resource: str) -> None:
    """AC1: Resource declarations and statements add no dependency imports."""
    baseline = assess_content(Path("Resources.cs"), "using System.IO;\n").coupling
    with_resource = assess_content(Path("Resources.cs"), f"using System.IO;\n{resource}\n").coupling

    assert with_resource == baseline


def test_csharp_resource_cleanup_preserves_coupling() -> None:
    """AC1: The issue's eight resource declarations leave one dependency."""
    imports = "using System.IO;\n"
    resources = "".join(f"using var resource{i} = new MemoryStream();\n" for i in range(8))

    baseline = assess_content(Path("Resources.cs"), imports).coupling
    with_cleanup = assess_content(Path("Resources.cs"), imports + resources).coupling

    assert baseline.reasons[0] == "1 import/dependency statements"
    assert with_cleanup == baseline


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("using Company.IO; using Company.Text;", 2),
        ("namespace Example {\nusing Company.IO;\nclass C {}\n}", 1),
        ("namespace Example;\nusing Company.IO;\nclass C {}", 1),
        ("/*\nusing System.IO;\n*/", 0),
        ('class C { string text = @"\nusing System.IO;\n"; }', 0),
        ('class C { string text = """\nusing System.IO;\n"""; }', 0),
    ],
)
def test_csharp_counts_syntax_nodes_not_source_lines(source: str, expected: int) -> None:
    """AC1/AC2: Syntax determines dependencies, regardless of lines or literal text."""
    coupling = assess_content(Path("Syntax.cs"), source).coupling

    assert coupling.reasons[0] == f"{expected} import/dependency statements"
    assert coupling.value == 10.0 - expected


_SYSTEM_NOTE = "1 C# System namespace (not scored), 0 application or third-party (scored)"


@pytest.mark.parametrize(
    "directive",
    [
        "using System;",
        "using System.IO;",
        "using @System.IO;",
        "using global::System.Linq;",
        "using/* namespace */System /* scope */ . IO;",
        "using\n    System.IO\n    ;",
        "using static System.Math;",
        "using IO = System.IO;",
        "using SB = global::System.Text.StringBuilder;",
        "using Streams = System.Collections.Generic.List<Xunit.Fact>;",
        "global using System.IO;",
        "global /* shared */ using static System.Math;",
        "namespace Example {\nusing System.IO;\nclass C {}\n}",
    ],
)
def test_csharp_system_namespace_directives_are_reported_not_scored(directive: str) -> None:
    """Issue #7459: System namespace directives ship with .NET, like Python's stdlib."""
    coupling = assess_content(Path("Imports.cs"), directive).coupling

    assert coupling.reasons[:2] == ["1 import/dependency statements", _SYSTEM_NOTE]
    assert coupling.value == 10.0


@pytest.mark.parametrize(
    "directive",
    [
        "using Xunit;",
        "using global::Xunit;",
        "using Systematic.Tools;",
        "using @Systematic;",
        "using SystemX;",
        "using Microsoft.Extensions.Logging;",
        "using Company.System.IO;",
        "using Lib::System.IO;",
        "using System = Company.Core;",
        "using static Example.Factory<System.IO.Stream>;",
        "using Streams = List<System.IO.Stream>;",
        "using Point = (int X, int Y);",
        "using unsafe Pointer = int*;",
        "using Ints = System.Int32[];",
        "using MaybeInt = System.Int32?;",
        "using unsafe IntPointer = System.Int32*;",
    ],
)
def test_csharp_other_namespace_directives_are_scored(directive: str) -> None:
    """Issue #7459: Only a target rooted at System is exempt, by segment, not prefix."""
    coupling = assess_content(Path("Imports.cs"), directive).coupling

    assert coupling.reasons[0] == "1 import/dependency statements"
    assert "C# System namespace" not in " ".join(coupling.reasons)
    assert coupling.value == 9.0


_ISSUE_7459_TEST_FILE = (
    "using System;\nusing System.IO;\nusing System.Linq;\nusing Xunit;\n\n"
    "namespace Example.Tests;\n\npublic sealed class CollisionNamingContentTests\n{\n"
    + "".join(
        f"    [Fact]\n    public void Case{n}()\n    {{\n"
        "        using var ws = new TempWorkspace();\n"
        f"        Assert.True(ws.Check{n}());\n    }}\n\n"
        for n in "ABCDEF"
    )
    + "}\n"
)


def test_issue_7459_test_file_scores_only_its_third_party_directive() -> None:
    """Issue #7459: Four directives and six using var statements score one dependency."""
    coupling = assess_content(
        Path("CollisionNamingContentTests.cs"), _ISSUE_7459_TEST_FILE
    ).coupling

    assert coupling.reasons[:2] == [
        "4 import/dependency statements",
        "3 C# System namespace (not scored), 1 application or third-party (scored)",
    ]
    assert coupling.value == 9.0


_ISSUE_7459_GATE_FILE = (
    "using System;\nusing System.IO;\nusing System.Linq;\nusing Xunit;\n\n"
    "public sealed class CollisionNamingContentTests\n{\n"
    "    [Fact]\n    public void NamesDoNotCollide()\n    {\n"
    "        using var ws = new MemoryStream();\n"
    "        Assert.Empty(Array.Empty<int>().Where(x => x > ws.Length));\n"
    "    }\n}\n"
)


@pytest.mark.parametrize(
    ("source", "exit_code", "stderr_fragment"),
    [
        pytest.param(_ISSUE_7459_GATE_FILE, 0, "", id="issue-7459-file-passes"),
        pytest.param(
            "".join(f"using Vendor{i}.Api;\n" for i in range(4)) + "class C {}\n",
            11,
            "Coupling 6.0 < 7",
            id="third-party-control-fails",
        ),
    ],
)
def test_default_coupling_gate_scores_only_non_system_directives(
    tmp_path: Path, source: str, exit_code: int, stderr_fragment: str
) -> None:
    """Issue #7459: Under default thresholds (coupling min 7) only non-System directives gate.

    The issue's file passes. Four third-party directives still fail, so the
    exemption leaves the gate live. Neither body is repetitive, so only the
    coupling gate decides the exit code.
    """
    target = tmp_path / "tests" / "Example.cs"
    target.parent.mkdir()
    target.write_text(source, encoding="utf-8")
    assert not (tmp_path / ".qualityrc.json").exists()

    result = subprocess.run(
        [sys.executable, str(_mod.__file__), "--target", str(target), "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )

    assert result.returncode == exit_code, result.stderr
    assert stderr_fragment in result.stderr
    if exit_code == 0:
        reasons = json.loads(result.stdout)["files"][0]["coupling"]["reasons"]
        assert reasons[1] == (
            "3 C# System namespace (not scored), 1 application or third-party (scored)"
        )


def test_csharp_directive_without_target_fails_closed_with_its_line() -> None:
    """Issue #7459: A directive node with no target raises, naming its source line."""
    alias = SimpleNamespace(id=1, type="identifier")
    directive = SimpleNamespace(
        child_by_field_name=lambda field: alias if field == "name" else None,
        named_children=[alias, SimpleNamespace(id=2, type="comment")],
        start_point=(6, 0),
    )

    with pytest.raises(_mod.CSharpParserError, match="on line 7 has no target"):
        _mod._is_csharp_standard_directive(directive)


@pytest.mark.parametrize("source", ["using ;", "using A = ;", "global using ;"])
def test_csharp_directive_without_target_is_a_parse_error_first(source: str) -> None:
    """Issue #7459: The pinned grammar rejects an empty directive before classification."""
    with pytest.raises(_mod.CSharpParserError, match="could not parse this file"):
        _mod._count_csharp_imports(source + "\n")


@pytest.mark.parametrize("failure", [AttributeError("no text"), StopIteration()])
def test_unexpected_csharp_directive_shapes_fail_closed(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    """Issue #7459: A malformed directive node raises the parser error, never a guess."""

    def malformed(node: object) -> str | None:
        raise failure

    monkeypatch.setattr(_mod, "_csharp_root_namespace", malformed)

    with pytest.raises(_mod.CSharpParserError, match="unexpected parse-tree shape"):
        _mod._count_csharp_imports("using System.IO;\n")


@pytest.mark.parametrize("module_name", ["tree_sitter_c_sharp"])
def test_missing_csharp_parser_fails_cli_without_affecting_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
) -> None:
    """AC1: Missing parsing tools fail explicitly, never report a passing C# score."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, module_name, None)
    csharp = tmp_path / "Imports.cs"
    csharp.write_text("using System.IO;\n", encoding="utf-8")
    python = tmp_path / "example.py"
    python.write_text("def example():\n    return 1\n", encoding="utf-8")

    result = _mod.main(["--target", str(csharp), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "tree-sitter" in output.err
    assert "install" in output.err.lower()
    assert not output.out
    assert _mod.main(["--target", str(python), "--format", "json"]) == 0


def test_invalid_csharp_fails_cli_instead_of_reporting_no_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1: A syntax error must not become a successful zero-dependency assessment."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "Invalid.cs"
    target.write_text("using System.IO\n", encoding="utf-8")

    result = _mod.main(["--target", str(target), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "C#" in output.err
    assert "syntax" in output.err.lower()
    assert target.name in output.err
    assert not output.out


_SPLIT_SIGNATURE = (
    "using System;\nclass A {\n#if A\n    public void M(int a,\n#else\n"
    "    public void M(long a,\n#endif\n        int b) { }\n}\n"
)


def test_valid_csharp_the_grammar_cannot_parse_fails_with_a_grammar_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A method signature split across #if/#else is valid C# that the pinned grammar
    rejects. The scan stays fail closed, and the message names the grammar, not the source."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "Split.cs"
    target.write_text(_SPLIT_SIGNATURE, encoding="utf-8")

    result = _mod.main(["--target", str(target), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "tree-sitter-c-sharp==0.23.5" in output.err
    assert "could not parse" in output.err
    assert "valid C# that the grammar does not support" in output.err
    assert target.name in output.err
    assert not output.out


def test_unparseable_base_csharp_blob_fails_regression_mode_with_path_and_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "Base.cs", "using System.IO\n", "base is invalid")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "Base.cs", "using System;\n", "head is valid")
    monkeypatch.chdir(tmp_path)

    result = _mod.main(_regression_argv())
    output = capsys.readouterr()

    assert result == 1
    assert "Base.cs at " in output.err
    assert "could not parse" in output.err
    assert not output.out


@pytest.mark.parametrize(
    "error_type", [OSError, ValueError, TypeError, RuntimeError, AttributeError, KeyError]
)
def test_broken_csharp_parser_fails_cli_without_a_success_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_type: type[Exception],
) -> None:
    """AC1: Native-load and grammar-initialization errors cannot pass the gate."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "Imports.cs"
    target.write_text("using System.IO;\n", encoding="utf-8")
    report = tmp_path / "report.json"

    def broken_parser(_language: object) -> None:
        raise error_type("Parser initialization failed")

    monkeypatch.setattr(importlib.import_module("tree_sitter"), "Parser", broken_parser)

    result = _mod.main(["--target", str(target), "--format", "json", "--output", str(report)])
    output = capsys.readouterr()

    assert result == 1
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
def test_shipped_csharp_parser_runs_from_consumer_directory(
    tmp_path: Path, plugin_parts: tuple[str, ...]
) -> None:
    """AC1/AC2: Every shipped scanner parses source outside its own plugin directory."""
    target = tmp_path / "Consumer.cs"
    target.write_text(
        'global\nusing Company.IO;\nclass C {\nstring text = @"\n'
        'using Not.AnImport;\nusing Another.NotImport;\n";\n'
        "void Cleanup() { using var stream = new MemoryStream(); }\n}\n",
        encoding="utf-8",
    )

    assert_shipped_scanner_counts(plugin_parts, target, 9.0, 1)
