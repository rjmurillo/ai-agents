"""C# directive and resource classification regressions for issue #7406."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .test_assess import _commit, _init_repo, _regression_argv, _run_git

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
    / "assess.py"
)
_spec = importlib.util.spec_from_file_location("assess", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
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
    """AC2: Namespace, alias, static, and global directives remain dependencies."""
    coupling = assess_content(Path("Imports.cs"), directive).coupling

    assert coupling.reasons[0] == "1 import/dependency statements"
    assert coupling.value < 10
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
        ("using System.IO; using System.Text;", 2),
        ("namespace Example {\nusing System.IO;\nclass C {}\n}", 1),
        ("namespace Example;\nusing System.IO;\nclass C {}", 1),
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


@pytest.mark.parametrize("module_name", ["tree_sitter", "tree_sitter_c_sharp"])
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


@pytest.mark.parametrize("error_type", [OSError, ValueError, TypeError, RuntimeError])
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
    root = Path(__file__).resolve().parents[3]
    script = root.joinpath(
        "src", *plugin_parts, "skills", "code-qualities-assessment", "scripts", "assess.py"
    )
    target = tmp_path / "Consumer.cs"
    target.write_text(
        'global\nusing System.IO;\nclass C {\nstring text = @"\n'
        'using Not.AnImport;\nusing Another.NotImport;\n";\n'
        "void Cleanup() { using var stream = new MemoryStream(); }\n}\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-I", str(script), "--target", str(target), "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    coupling = json.loads(result.stdout)["files"][0]["coupling"]
    assert coupling["value"] == 9.0
    assert coupling["confidence"] == 0.6
    assert coupling["reasons"][0] == "1 import/dependency statements"

    without_packages = subprocess.run(
        [sys.executable, "-I", "-S", str(script), "--target", str(target), "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )

    assert without_packages.returncode == 1
    assert "tree-sitter" in without_packages.stderr
    assert not without_packages.stdout
