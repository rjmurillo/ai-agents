#!/usr/bin/env python3
# taste-lint: ignore file-size
# This file covers a wide surface (inventory, changed-files filter, link checks,
# freshness, symlink, real-git integration). 522 lines for 48 test cases is the
# right granularity; splitting the file would spread related fixtures.
"""Tests for doc_accuracy module."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy",
)
SourceSymbol = mod.SourceSymbol
DocFile = mod.DocFile
Claim = mod.Claim
Finding = mod.Finding
run_assessment = mod.run_assessment
run_claim_extraction = mod.run_claim_extraction
run_compilability_check = mod.run_compilability_check
check_gate = mod.check_gate
generate_markdown_report = mod.generate_markdown_report
main = mod.main
_should_exclude = mod._should_exclude
_repo_files = mod._repo_files
_GIT_EXCLUDE_DIRS = mod._GIT_EXCLUDE_DIRS
_detect_language = mod._detect_language
_extract_identifiers = mod._extract_identifiers
_extract_quantitative_claims = mod._extract_quantitative_claims
_extract_python_symbols = mod._extract_python_symbols
_extract_csharp_symbols = mod._extract_csharp_symbols
_count_code_blocks = mod._count_code_blocks
_get_changed_files = mod._get_changed_files
_git_env = mod._git_env
_list_git_files = mod._list_git_files
_repo_relative = mod._repo_relative


def test_exit_code_documentation_covers_the_cli_contract() -> None:
    """Canonical skill cites its bundled script and lists every exit code."""
    contract = """Exit Codes:
    0: No findings at or above severity threshold
    1: Error or inconclusive run, including no source symbols for Phase 3
    2: Configuration error, including an invalid --diff-base
    3: External dependency failure, including unavailable or failed Git
    10: Findings at or above severity threshold"""
    skill_path = Path(mod.__file__).resolve().parents[1] / "SKILL.md"
    skill_docs = skill_path.read_text(encoding="utf-8")
    source_citation = (
        "Canonical source bundled with this skill:\n\n```text\nscripts/doc_accuracy.py\n```"
    )

    assert contract in (mod.__doc__ or "")
    assert source_citation in skill_docs
    assert (skill_path.parent / "scripts" / "doc_accuracy.py").is_file()
    assert f"```text\n{contract}\n```" in skill_docs


class TestShouldExclude:
    def test_excludes_git(self) -> None:
        assert _should_exclude(Path(".git/config"))

    def test_excludes_node_modules(self) -> None:
        assert _should_exclude(Path("node_modules/pkg/index.js"))

    def test_allows_normal_path(self) -> None:
        assert not _should_exclude(Path("src/main.py"))

    def test_excludes_doc_accuracy_output(self) -> None:
        assert _should_exclude(Path(".doc-accuracy/report.json"))


class TestShouldExcludeGitMode:
    def test_git_mode_keeps_build_directory(self) -> None:
        assert not _should_exclude(Path("build/scripts/README.md"), None, _GIT_EXCLUDE_DIRS)

    def test_git_mode_keeps_bin_obj_dist_target(self) -> None:
        for name in ("bin", "obj", "dist", "target"):
            assert not _should_exclude(Path(name, "README.md"), None, _GIT_EXCLUDE_DIRS)

    def test_git_mode_still_excludes_git_and_output_dirs(self) -> None:
        assert _should_exclude(Path(".git/config"), None, _GIT_EXCLUDE_DIRS)
        assert _should_exclude(Path(".doc-accuracy/report.json"), None, _GIT_EXCLUDE_DIRS)

    def test_default_set_still_excludes_build(self) -> None:
        assert _should_exclude(Path("build/scripts/README.md"))


def _git_repo(path: Path) -> Path:
    """Create a git repo with a committed .gitignore for build output."""
    path.mkdir()
    for args in (
        ["init", "--initial-branch=main"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    (path / ".gitignore").write_text("dist/\nnode_modules/\n")
    return path


def _commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


class TestTrackedBuildDirectories:
    """Issue #6202: tracked files under build/ must be inventoried in git mode."""

    def test_tracked_build_doc_is_inventoried(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "repo")
        (repo / "build" / "scripts" / "perf").mkdir(parents=True)
        (repo / "build" / "scripts" / "perf" / "README.md").write_text("# Perf\n")
        _commit_all(repo, "base")

        result = run_assessment(repo)

        doc_paths = [d["path"] for d in result["documentation_files"]]
        assert "build/scripts/perf/README.md" in doc_paths

    def test_diff_base_inventories_changed_doc_under_build(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "repo")
        (repo / "build" / "scripts" / "perf").mkdir(parents=True)
        readme = repo / "build" / "scripts" / "perf" / "README.md"
        readme.write_text("# Perf\n")
        (repo / "main.py").write_text("def foo():\n    pass\n")
        _commit_all(repo, "base")
        readme.write_text("# Perf warmup\n")
        _commit_all(repo, "change build doc")

        result = run_assessment(repo, diff_base="HEAD~1")

        doc_paths = [d["path"] for d in result["documentation_files"]]
        assert doc_paths == ["build/scripts/perf/README.md"]

    def test_tracked_build_source_is_indexed(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "repo")
        (repo / "build").mkdir()
        (repo / "build" / "tool.py").write_text("def BuildTool():\n    pass\n")
        _commit_all(repo, "base")

        result = run_assessment(repo)

        assert any(s["name"] == "BuildTool" for s in result["source_symbols"])

    def test_gitignored_output_stays_excluded(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "repo")
        (repo / "README.md").write_text("# Root\n")
        (repo / "dist").mkdir()
        (repo / "dist" / "OUT.md").write_text("# generated\n")
        (repo / "node_modules" / "pkg").mkdir(parents=True)
        (repo / "node_modules" / "pkg" / "README.md").write_text("# dep\n")
        _commit_all(repo, "base")

        result = run_assessment(repo)

        doc_paths = [d["path"] for d in result["documentation_files"]]
        assert doc_paths == ["README.md"]

    def test_doc_accuracy_output_dir_stays_excluded_in_git_mode(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "repo")
        (repo / "README.md").write_text("# Root\n")
        (repo / ".doc-accuracy").mkdir()
        (repo / ".doc-accuracy" / "report.md").write_text("# report\n")

        result = run_assessment(repo)

        doc_paths = [d["path"] for d in result["documentation_files"]]
        assert doc_paths == ["README.md"]

    def test_non_git_fallback_still_excludes_build(self, tmp_path: Path) -> None:
        (tmp_path / ".git").write_text("gitdir: missing\n")
        (tmp_path / "README.md").write_text("# Root\n")
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "README.md").write_text("# build\n")

        result = run_assessment(tmp_path)

        doc_paths = [d["path"] for d in result["documentation_files"]]
        assert doc_paths == ["README.md"]

    def test_repo_files_git_mode_lists_build_and_drops_git_dirs(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path / "repo")
        (repo / "build").mkdir()
        (repo / "build" / "a.md").write_text("# a\n")
        (repo / ".doc-accuracy").mkdir()
        (repo / ".doc-accuracy" / "b.md").write_text("# b\n")
        _commit_all(repo, "base")

        rel = {p.relative_to(repo).as_posix() for p in _repo_files(repo)}

        assert "build/a.md" in rel
        assert ".doc-accuracy/b.md" not in rel

    def test_repo_files_require_git_outside_repo_raises(self, tmp_path: Path) -> None:
        (tmp_path / ".git").write_text("gitdir: missing\n")
        try:
            _repo_files(tmp_path, require_git=True)
        except mod._GitError as exc:
            assert exc.exit_code == 3
        else:
            raise AssertionError("expected _GitError")


class TestDetectLanguage:
    def test_python(self) -> None:
        assert _detect_language("python") == "python"

    def test_py_alias(self) -> None:
        assert _detect_language("py") == "python"

    def test_csharp(self) -> None:
        assert _detect_language("csharp") == "csharp"

    def test_cs_alias(self) -> None:
        assert _detect_language("cs") == "csharp"

    def test_empty_string(self) -> None:
        assert _detect_language("") == ""

    def test_csharp_hash_alias(self) -> None:
        assert _detect_language("c#") == "csharp"

    def test_unknown_returns_token(self) -> None:
        assert _detect_language("fortran") == "fortran"


class TestExtractIdentifiers:
    def test_camel_case(self) -> None:
        result = _extract_identifiers("var x = MyClass.DoSomething();")
        assert "MyClass" in result
        assert "DoSomething" in result

    def test_method_calls(self) -> None:
        result = _extract_identifiers("obj.process(data)")
        assert "process" in result

    def test_named_params(self) -> None:
        result = _extract_identifiers("Foo(name: value)")
        assert "name" in result


class TestCsharpPreprocessorSymbols:
    """Issue #7453: SDK preprocessor symbols are not repository symbols."""

    DIRECTIVES = (
        ("#elif NET472", "NET472"),
        ("#define TRACE", "TRACE"),
        ("#undef DEBUG", "DEBUG"),
        ("    #if NETFRAMEWORK", "NETFRAMEWORK"),
        ("# if Net472", "Net472"),
        ("#if DEBUG && !NETFRAMEWORK", "NETFRAMEWORK"),
        ("#region SetupHelpers", "SetupHelpers"),
        ("#pragma warning disable CS0618", "CS0618"),
        ("#warning ObsoleteApi is going away", "ObsoleteApi"),
        ("#error UnsupportedTarget", "UnsupportedTarget"),
    )

    def test_if_symbol_is_not_extracted(self) -> None:
        code = "#if NETFRAMEWORK\nvar x = new RealWidget();\n#endif"

        result = _extract_identifiers(code, "csharp")

        assert "NETFRAMEWORK" not in result
        assert "RealWidget" in result

    def test_directive_line_symbols_are_not_extracted(self) -> None:
        for directive, symbol in self.DIRECTIVES:
            code = f"{directive}\nvar x = new RealWidget();"

            result = _extract_identifiers(code, "csharp")

            assert symbol not in result, directive
            assert "RealWidget" in result, directive

    def test_directive_shaped_line_is_kept_for_other_languages(self) -> None:
        """A TypeScript private method line matches the directive shape."""
        code = "class Counter {\n  #parse(input: RealWidget) {}\n}"

        result = _extract_identifiers(code, "typescript")

        # ``input`` is a parameter the example declares, so binding drops it.
        assert "RealWidget" in result

    def test_unlabeled_snippet_keeps_directive_text(self) -> None:
        result = _extract_identifiers("#if NETFRAMEWORK")

        assert "NETFRAMEWORK" in result

    def test_hash_inside_a_code_line_is_not_a_directive(self) -> None:
        code = 'var tag = "#if"; var y = new FakeWidget();'

        result = _extract_identifiers(code, "csharp")

        assert "FakeWidget" in result


class TestCsharpLiteralAndAttributeArguments:
    """Names in C# literals and attribute arguments are data, not symbols."""

    LITERALS = (
        ('var s = "Hello WidgetFactory";', "WidgetFactory"),
        ('var s = @"C:\\Temp\\VerbatimName";', "VerbatimName"),
        ('var s = @"say ""QuotedName"" now";', "QuotedName"),
        ('var s = $"Hi InterpText {x}";', "InterpText"),
        ('var s = $@"Path InterpVerbatim {x}";', "InterpVerbatim"),
        ('var s = """\nRawBlockName\n""";', "RawBlockName"),
        ('var s = "Escaped \\" StillString";', "StillString"),
        ("var c = 'Q'; var d = '\\''; var e = \"CharTail\";", "CharTail"),
        ('var s = $"Total {total:N2} at {when:HH:mm}";', "N2"),
        ('var s = $"{when:HH:mm} done";', "HH"),
        ('var s = $$"""\n{{price:Currency}}\n""";', "Currency"),
        ('var s = $"{order?.Total:N2}";', "N2"),
        ('var s = $"{a ?? b:C2}";', "C2"),
        ('var s = $"{items?[0]:X8}";', "X8"),
        ('var s = $"{d:HH\\"mm}";', "HH"),
        ('var s = $@"{d:HH""mm}";', "HH"),
        ('var s = $"{record.Total:N2}";', "N2"),
        ('foreach (var record in rs) { var s = $"{record.Total:D5}"; }', "D5"),
        ('var s = $"{where:N2} {var:F1} {item.record:C2} {this.@class:X4}";', "N2"),
        ('var s = $"{item.record:C2} {this.@class:X4}";', "X4"),
        ('var s = $"{var:F1}";', "F1"),
    )

    def test_names_in_literals_are_not_extracted(self) -> None:
        for line, name in self.LITERALS:
            code = f"{line}\nvar w = new RealWidget();"

            result = _extract_identifiers(code, "csharp")

            assert name not in result, line
            assert "RealWidget" in result, line

    def test_interpolation_hole_stays_code(self) -> None:
        code = 'var s = $"Total {Ledger.Sum()} and {{Braced}}";'

        result = _extract_identifiers(code, "csharp")

        assert "Ledger" in result
        assert "Total" not in result
        assert "Braced" not in result

    def test_unterminated_string_stays_visible(self) -> None:
        """A string with no closing quote is a typo; its text is not hidden."""
        for code in (
            'var s = "open TrailingName\nvar w = new FakeWidget();',
            'var c = "x; var w = new FakeWidget();',
            "var c = 'x; var w = new FakeWidget();",
        ):
            result = _extract_identifiers(code, "csharp")

            assert "FakeWidget" in result, code
        assert "TrailingName" in _extract_identifiers('var s = "open TrailingName', "csharp")

    def test_attribute_named_arguments_are_not_extracted(self) -> None:
        code = '[DllImport("k32", EntryPoint = "Beep", SetLastError: true)]\nvoid F() {}'

        result = _extract_identifiers(code, "csharp")

        assert "EntryPoint" not in result
        assert "SetLastError" not in result
        assert "Beep" not in result

    def test_attribute_name_and_typeof_argument_stay_code(self) -> None:
        code = "[TypeConverter(typeof(FakeConverter), Mode = Kind.Fast)]\nclass C {}"

        result = _extract_identifiers(code, "csharp")

        assert "TypeConverter" in result
        assert "FakeConverter" in result
        assert "Kind" in result
        assert "Mode" not in result

    def test_parameter_attribute_named_argument_is_not_extracted(self) -> None:
        code = "void F([Range(Minimum = 1)] int count) {}"

        result = _extract_identifiers(code, "csharp")

        assert "Minimum" not in result
        assert "Range" in result

    # Each case keeps a made-up name in real code visible next to a literal.
    REAL_CODE_STAYS_VISIBLE = (
        ('var s = $"""\n{FakeWidget.Make()}\n""";', "FakeWidget"),
        ('var s = $$"""\n{x} {{FakeWidget.Make()}}\n""";', "FakeWidget"),
        ('var s = @"open\nvar w = new FakeWidget();', "FakeWidget"),
        ('var s = """\nvar w = new FakeWidget();', "FakeWidget"),
        ("var c = '\\\nvar w = new FakeWidget(); var d = 'x';", "FakeWidget"),
        ('var s = $"{F("}")} tail"; var w = new FakeWidget();', "FakeWidget"),
        ("Run([Build(Size: 3)]);", "Size"),
        ("var r = xs switch { [Point(MissingX: 1)] @rest => 1, _ => 0 };", "MissingX"),
        ("var r = xs switch { [Point(MissingY: 1)] get => 1, _ => 0 };", "MissingY"),
        ("[1, Build(MissingSize: 3)]", "MissingSize"),
        ("var r = xs switch { [Point(MissingZ: 1)] rest 1, _ => 0 };", "MissingZ"),
        ("Use([Pick(flag ? FakeType : other)]);", "FakeType"),
        ("List<object> l =\n[\n    Make(flag ? MadeUpType : null),\n];", "MadeUpType"),
        ("Run(\n    [Build(Size: 3)],\n    other);", "Size"),
        ("Run(\n    other,\n    [Build(Size: 3)]\n);", "Size"),
        ("Run(\n    [Build(Size: 3)] // note\n);", "Size"),
        ("Process(\n    [\n        Create(name: x, FakeOpt: y),\n    ]\n);", "FakeOpt"),
        ("Process(\n    [\n        Make(new W { A = 1, FakeProp = 2 }),\n    ]\n);", "FakeProp"),
        ("Process(\n    [\n        Items.Select(FakeType => 1),\n    ]\n);", "FakeType"),
        ("var r = arr switch {\n    [Point(FakeX: 1), ..] when flag => 1,\n};", "FakeX"),
        ("if (grid[i][Find(FakeArg: 2)] is null) {}", "FakeArg"),
        ("var v = grid[i][Compute(FakeArg: 2)]\n    is int n;", "FakeArg"),
        ("var d = new Dictionary<K, int> {\n    [Key(FakeName: 1)] = 2,\n};", "FakeName"),
        ("handlers[i](FakeParam: 1);", "FakeParam"),
        ('var s = $"{\n/* " */ var z = FakeWidget.Go();', "FakeWidget"),
        ("var r = arr switch {\n    [Point(FakeX: 1), ..] rest => 1,\n};", "FakeX"),
        ("var r = xs switch { [] => 0,\n    [Point(FakeX: 1)] one when ok => 1 };", "FakeX"),
        ("if (t is (1, [Point(FakeX: 1)] rest)) {}", "FakeX"),
        ("if (t is ([Point(FakeX: 1)] rest, 2)) {}", "FakeX"),
        ("var r = (a, b) switch { ([Point(FakeX: 1)] xs, _) => 1 };", "FakeX"),
        ("if (o is [_, [Point(FakeX: 1)] inner]) {}", "FakeX"),
        ("if (o is { Items: [_, [Point(FakeX: 1)] w] }) {}", "FakeX"),
        ("var r = x switch { [Point(FakeX: 1)] v and { Length: 1 } => 1 };", "FakeX"),
        ("if (o is Pair([Point(FakeX: 1)] v and var w, _)) {}", "FakeX"),
        ("var r = x switch { [Point(FakeX: 1)] v or [] => 1 };", "FakeX"),
        ("var q = '\"'; var w = new FakeWidget();", "FakeWidget"),
        ('var s = $"{Ledger.Sum():N2} {(ok ? FakeWidget.A : 0)}";', "FakeWidget"),
        ('var s = $"{Ledger.Sum():N2}";', "Ledger"),
        ('var s = $"{global::FakeWidget.Name}";', "FakeWidget"),
        ('$"{\nvar e = cond ? [Z(A: 1)] : [];\nvar a = new FakeWidget(); }', "FakeWidget"),
        ("var d = '\\''; var w = new FakeWidget();", "FakeWidget"),
        ('var s = $"{F(name: FakeWidget.A)}";', "FakeWidget"),
        ('var s = $"{(ok ? 0 : FakeWidget.A)}";', "FakeWidget"),
        ('var s = $"{ok ? RealY.A : FakeWidget.B}";', "FakeWidget"),
        ('var s = $"{\nvar e = cond ? a : new FakeWidget(); }";', "FakeWidget"),
        ('var s = $"{value\nlabel: FakeWidget.Go(); }";', "FakeWidget"),
        ('var s = $"{name; class A : FakeBase { }', "FakeBase"),
        ('var s = $"{x; done: FakeWidget.Go(); }', "FakeWidget"),
        ('var s = $"{a ?? b ? c : FakeWidget.B}";', "FakeWidget"),
        ('var s = $"{x:N2\nvar w = new FakeWidget(); }";', "FakeWidget"),
        ('var s = $"{d:HH\\"mm}"; } var w = new FakeWidget();', "FakeWidget"),
        ('var s = $"{a?.b class A : FakeBase { }', "FakeBase"),
        ('var s = $"{a ?? b class A : FakeBase { }', "FakeBase"),
        ('var s = $"{x: {new FakeWidget()} }";', "FakeWidget"),
        ('var s = $"{c ?[1] : FakeWidget.B}";', "FakeWidget"),
        ('var s = $"{x /* a\n */ class A : FakeBase { }', "FakeBase"),
        ('var s = $"{x?[0] case 1: FakeWidget.Go(); }', "FakeWidget"),
        ('var s = $"{d:a\\}"; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $"{d"; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $"{d:a"; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $"{F("x")} {d"; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $$"""{{x}"""; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $$"""{{x:N2}"""; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $"{c ??.case 1: FakeWidget.Go(); }', "FakeWidget"),
        ('var s = $"{d"; var w = new FakeWidget("x");', "FakeWidget"),
        ('var s = $"{d:N2"; var w = new FakeWidget("x");', "FakeWidget"),
        ('var s = $"{d"; var w = new FakeWidget(); var t = "x";', "FakeWidget"),
        ('var s = $"{d"; var w = new FakeWidget($"{y}");', "FakeWidget"),
        ('var s = $"{d"; [FakeAttr("x")] class C {}', "FakeAttr"),
        ('Console.WriteLine($"T: {o.Total"); var v = new FakeService("db");', "FakeService"),
        ('var s = $@"{d"; var w = new FakeWidget();', "FakeWidget"),
        ('var s = @$"{d"; var w = new FakeWidget();', "FakeWidget"),
        ('var p = $@"C:\\{dir"; var v = new FakeService();', "FakeService"),
        ('var s = $"{d"; var w = new FakeWidget(); // C:\\"', "FakeWidget"),
        ('var s = $"{\n    FakeWidget.Make() }";', "FakeWidget"),
        ('var s = $"{F("x)}"; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $"{ $"{x "\n} FakeWidget.Go(); var t = "y";', "FakeWidget"),
        ('var s = $"{ $"{x"\nvar a = 1;\n} var t = new FakeThing("x");', "FakeThing"),
        ('var s = $"{F(@"FakeLit")}"; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $"{\n    F("x")\n}"; FakeWidget.Go();', "FakeWidget"),
        ('var s = $"{x:N2\n}"; FakeWidget.Go();', "FakeWidget"),
        ('var s = $"{d"; var w = new FakeWidget();\nif (x) { y(); }\n}', "FakeWidget"),
        ('var s = $@"{x}\nVerbatimTail" + Fake.A; var w = new FakeWidget();', "FakeWidget"),
        ('var s = $$"""\n{{done: FakeWidget.Go(); }\n"""', "FakeWidget"),
        ('var s = $@"{a // don\'t\n} {FakeWidget.Go()}";', "FakeWidget"),
    )

    # Real attribute sections whose named arguments are blanked.
    ATTRIBUTE_FORMS = (
        ('[DllImport("k", EntryPoint = "B")] /* x */ static extern void F();', "DllImport"),
        ('[DllImport("k", @EntryPoint = "B")]\nstatic extern void G();', "DllImport"),
        ('[assembly: Marker(EntryPoint = "B")]', "Marker"),
        ("int P { [Attr(EntryPoint = 1)] get => 1; }", "Attr"),
        ("[Attr(EntryPoint = 1)] @event E;", "Attr"),
        ("[Benchmark(EntryPoint = true)]\n(int, int) Compute() {}", "Benchmark"),
        ("class C {\n    [Attr(EntryPoint = 1)]\n    ~C() {}\n}", "Attr"),
        ("// leading comment\n[Attr(EntryPoint = 1)]\npublic void M() {}", "Attr"),
        ("void A() {}\n[Other]\n[Attr(EntryPoint = 1)]\npublic void M() {}", "Attr"),
        ('enum E {\n    [Display(EntryPoint = "r")] Red,\n}', "Display"),
        ('enum E { Red, [Display(EntryPoint = "g")] Green }', "Display"),
        ('int P {\n    [Obsolete(EntryPoint = "X")] get => _p;\n}', "Obsolete"),
        ('int P { get => 1; [Obsolete(EntryPoint = "X")] set => _p = value; }', "Obsolete"),
        ("void F([Range(EntryPoint = 1)] int count, [In] Foo p) {}", "Range"),
        ("[Attr(\n    EntryPoint\n        = 1)]\npublic void M() {}", "Attr"),
    )

    def test_attribute_forms_blank_named_arguments(self) -> None:
        for code, attribute in self.ATTRIBUTE_FORMS:
            result = _extract_identifiers(code, "csharp")

            assert "EntryPoint" not in result, code
            assert attribute in result, code

    def test_unclosed_string_leaves_the_snippet_unblanked(self, caplog) -> None:
        """Accepted over-report: a string that never closes stops all blanking."""
        code = 'x = $"{a\n' * 200 + '[Conditional("DEBUG")]\nvar w = new FakeWidget();'
        closed = '[Conditional("DEBUG")]\nvar w = new FakeWidget();'

        with caplog.at_level("WARNING"):
            result = _extract_identifiers(code, "csharp")
            control = _extract_identifiers(closed, "csharp")

        assert "DEBUG" in result
        assert "FakeWidget" in result
        assert "DEBUG" not in control
        assert "could not read the snippet" in caplog.text

    def test_valid_raw_verbatim_and_char_literals_still_blank(self) -> None:
        cases = (
            ('var a = """\n    RawLine\n    """;\nvar w = new FakeWidget();', "RawLine"),
            ('var a = """Single RawWord""";\nvar w = new FakeWidget();', "RawWord"),
            ('var a = @"single VerbWord";\nvar w = new FakeWidget();', "VerbWord"),
            ('var s = $"""{"""x"""} RawNest""";\nvar w = new FakeWidget();', "RawNest"),
            ('var a = $@"one {x} VerbHole ""q""";\nvar w = new FakeWidget();', "VerbHole"),
            ('var u = @"one LineHid"u8;\nvar w = new FakeWidget();', "LineHid"),
            (
                "var c = '\\x41'; var d = '\\u00e9'; var e = '\\''; var f = 'Q';\n"
                "var w = new FakeWidget();",
                "x41",
            ),
            ("var c = '\\U0001F600'; var e = 'Q'; var w = new FakeWidget();", "U0001F600"),
        )
        for code, literal in cases:
            result = _extract_identifiers(code, "csharp")

            assert literal not in result, code
            assert "FakeWidget" in result, code

    def test_multi_line_verbatim_leaves_the_snippet_unblanked(self) -> None:
        """Accepted over-report: a verbatim string that spans lines is not blanked.

        Its close may be a later literal's quote, borrowed because its own
        close is missing, so the whole snippet is scanned as raw code.
        """
        cases = (
            ('var a = @"first\nVerbLine";\nvar w = new FakeWidget();', "VerbLine"),
            ('var a = $@"first\nTotal = {x} VerbHole";\nvar w = new FakeWidget();', "VerbHole"),
            (
                "var q = @\"SELECT SqlCol\n FROM Users\n WHERE Status = 'Active'\";\n"
                "var w = new FakeWidget();",
                "SqlCol",
            ),
            ('var j = @"{\n  ""JsonKey"": 1\n}";\nvar w = new FakeWidget();', "JsonKey"),
            ('var a = @"x\nVerbTail"; var b = "HidAq";\nvar w = new FakeWidget();', "HidAq"),
            ('var q = @"SqlB\nWHERE (x)";\nvar w = new FakeWidget();', "SqlB"),
        )
        for code, literal in cases:
            result = _extract_identifiers(code, "csharp")

            assert literal in result, code
            assert "FakeWidget" in result, code

    def test_nested_verbatim_string_in_hole_is_blanked(self) -> None:
        result = _extract_identifiers('var s = $"{F(@"FakeLit")}";', "csharp")

        assert "FakeLit" not in result

    def test_hole_over_the_line_cap_is_left_visible(self) -> None:
        body = "    a +\n" * 17
        code = 'var s = $"{\n' + body + '    FakeOperand\n} LitText";'
        short = 'var s = $"{\n' + "    a +\n" * 3 + '    FakeOperand\n} LitText";'

        over = _extract_identifiers(code, "csharp")
        under = _extract_identifiers(short, "csharp")

        assert "FakeOperand" in over
        assert "FakeOperand" in under
        assert "LitText" not in under

    def test_recursion_limit_falls_back_to_unblanked_code(self, caplog) -> None:
        code = '$"{' * 2000 + '"Quoted" [Attr(Named = 1)]' + '}"' * 2000

        with caplog.at_level("WARNING"):
            result = _extract_identifiers(code, "csharp")

        assert "Quoted" in result
        assert "Named" in result
        assert "could not read the snippet" in caplog.text

    def test_real_code_beside_literals_stays_visible(self) -> None:
        for code, name in self.REAL_CODE_STAYS_VISIBLE:
            result = _extract_identifiers(code, "csharp")

            assert name in result, code

    def test_raw_interpolated_text_is_blanked_around_holes(self) -> None:
        code = 'var s = $$"""\nRawText {Literal} {{Ledger.Sum()}}\n""";'

        result = _extract_identifiers(code, "csharp")

        assert "Ledger" in result
        assert "RawText" not in result
        assert "Literal" not in result

    def test_unterminated_verbatim_and_raw_stay_visible(self) -> None:
        """A verbatim or raw string with no close is a typo; nothing is hidden."""
        for code in (
            'var s = @"open OpeningName\nvar w = new FakeWidget();',
            'var s = """open OpeningName var w = new FakeWidget();',
            'var s = $"{x?.y : $$"""{{ var a = new FakeWidget(); }',
            'var a = """x;\nvar w = new FakeWidget();\nvar b = """\nok\n""";',
            'var a = """\n    text\nvar w = new FakeWidget();\nvar b = """\n    x\n    """;',
            'var s = $"""\n    {Order.Total\n    """;\n'
            'FakeWidget.Go();\nvar t = """\n    x\n    """;',
            'var a = """abc;\nFakeWidget.Go();\nvar b = """\n    x\n    """;',
            'var p = @"C:\\temp;\nvar w = new FakeWidget();\nConsole.WriteLine("done");',
            'var a = @"say ""hi"";\nFakeWidget.Go();\nvar b = "x";',
            "var c = 'ab; var w = new FakeWidget(); var d = 'x';",
            'Log(@"line one\nline two", Level.Info, "tag"); FakeWidget.Go();',
            'var s = @"a\nb" + FakeWidget.Name + "c";',
            'Foo(@"a\nb"); FakeWidget.Bar(MadeUp1.X, "y");',
            'Assert.Equal(@"line1\nline2", FakeWidget(Expected, "x"));',
            "var a = "
            + '"""'
            + "\ntext\nvar w = new FakeWidget();\nvar b = "
            + '"""'
            + "\nx\n"
            + '"""'
            + ";",
            "M('a,FakeWidget,'b');",
            'Log($@"first\nsee http://host/{id}\nthird", FakeWidget.X, "y");',
            'var a = @"x;\nvar w = new FakeWidget();\nLog(p + " done");',
            'var a = @"x;\nFakeWidget.Go();\nvar s = a + ", " + b;',
            'var a = @"x;\nFakeWidget.Go();\nstring Sep() => " ";',
            'var a = @"x;\nFakeWidget.Go();\nswitch (k) { case ".": break; }',
            'var a = @"x;\nFakeWidget.Go();\nreturn a + " ";',
            'var a = $@"x {y};\nFakeWidget.Go();\nvar s = a + " ";',
            'var a = @"x;\nvar b = "lit"; FakeWidget.Go(); var c = "z";',
            'var a = @"x;\nM("lit", FakeWidget.Go(), "z");',
            'var a = @"say ""hi"";\nvar b = "x"; FakeWidget.Go("y");',
            'var a = @"say ""hi"";\nFakeWidget.Go();\nvar b = c + ", ";',
            "var s = $"
            + '"""'
            + '\n    {Wrap(\n        $"x", FakeWidget.Name)}\n    '
            + '"""'
            + ";",
            'var s4 = $@"x {A.X} ""q"";\nFakeWidget.Go();\nvar s5 = '
            + '"""'
            + "\n    raw\n    "
            + '"""'
            + ";",
            'var s0 = $@"x {A.X} ""q"";\nFakeWidget.Go();\nvar s1 = $"""\n    q\n    """;',
            'var s0 = @"x ""q"";\nFakeWidget.Go();\nvar s1 = "y";',
            'var s0 = @"a ""q"" b;\nFakeWidget.Go();\n/* " { */ Other.Go();',
            'var s0 = @"a ""q"" b;\nFakeWidget.Go();\nvar c5 = \'"\';',
            'var s1 = $@"x {A.X} ""q"";\nFakeWidget.Go();\nvar c2 = \'{\';',
            'var sql = @"SELECT *\nFROM t WHERE a = (" + @"SELECT id\nFROM u)"; '
            'FakeWidget.Run(sql); Log("done");',
            'var a = @"x\nk=" + y; /* a\nsay "hi */ FakeWidget.Go(); var s = "z";',
            'var a = @"SELECT\nWHERE x ="; var b = @"multi\nline" + FakeWidget.Go() + @"z";',
            'var b = @"x\ny =" + $@"multi {\nk} line" + FakeWidget.Go() + "z";',
            'var a = @"x\ny =" + @"p\nq" + FakeWidget.Go() + "z";',
            'Run(@"a\nb)", @"\nc"); FakeWidget.Go("x");',
            'var a = @"x;\nvar b = @"multi\nline" + FakeWidget.Go() + @"z";',
            'var a = @"x;\nM(); var b = @"line1\nline2"; FakeWidget.Run(); var c = "z";',
            'var a = @"x;\nFakeWidget.Go();\nLog(\n    ".");',
            'var a = @"x;\nLog(" + @");\nFakeWidget.Go();\nLog(\n    ".");',
            'var a = @"x;\nFakeWidget.Go();\nvar q = from c in xs select ".";',
            "var s = $" + '"""' + '\n    {"unclosed FakeWidget();\n    }\n    ' + '"""' + ";",
        ):
            result = _extract_identifiers(code, "csharp")

            assert "FakeWidget" in result, code
            assert "OpeningName" in result or "OpeningName" not in code, code

    def test_literal_nested_in_a_hole_is_blanked(self) -> None:
        code = 'var s = $"{Get("NestedKey")} and {Ledger.Sum()}";'

        result = _extract_identifiers(code, "csharp")

        assert "NestedKey" not in result
        assert "Get" in result
        assert "Ledger" in result

    def test_empty_strings_and_block_comment_quotes_open_nothing(self) -> None:
        code = 'var a = ""; /* don\'t " */ var w = new FakeWidget(); var b = @"";'

        result = _extract_identifiers(code, "csharp")

        assert "FakeWidget" in result

    def test_chained_attribute_named_argument_is_not_extracted(self) -> None:
        code = '[Fact][Trait(Category = "x")]\nvoid F() {}'

        result = _extract_identifiers(code, "csharp")

        assert "Category" not in result
        assert "Trait" in result

    def test_attribute_before_comment_and_declaration_is_blanked(self) -> None:
        code = '[Obsolete(DiagnosticId = "X")] // old\npublic void M() {}'

        result = _extract_identifiers(code, "csharp")

        assert "DiagnosticId" not in result
        assert "Obsolete" in result

    def test_long_marker_run_finishes_quickly(self) -> None:
        code = "$" * 20000 + "\n" + "([" * 20000 + "\nvar w = new FakeWidget();"

        result = _extract_identifiers(code, "csharp")

        assert "FakeWidget" in result

    def test_many_switch_arm_sections_stay_fast(self) -> None:
        """Sections sharing one switch brace check it once, so the pass stays linear."""
        code = "x;\n" * 200000 + " switch {" + "[a(B: 1)] get => 1, " * 4000 + "};"
        code += "\nvar w = new FakeWidget();"
        started = time.monotonic()

        result = _extract_identifiers(code, "csharp")

        assert time.monotonic() - started < 2
        assert "FakeWidget" in result

    def test_crafted_hole_nesting_stays_fast_and_safe(self) -> None:
        cases = (
            '$@"{\n' * 40 + "var w = new FakeWidget();",
            '$"{' * 2000 + "FakeWidget" + '}"' * 2000,
            '$$"""' + "{{x}}" * 50000 + '"""; var w = new FakeWidget();',
            "[a]\n" + "//,[b]//\n" * 20000 + ")\nvar w = new FakeWidget();",
            " " * 50000 + "[" * 20000 + "\nvar w = new FakeWidget();",
            '$"{' + "a:" * 50000 + "\nvar w = new FakeWidget();",
            '$$"""' + "{{x:N}}" * 50000 + '"""; var w = new FakeWidget();',
            '$"{x; ' + "a: {b} " * 20000 + "\nvar w = new FakeWidget();",
            '$"{d"\n' * 20000 + "var w = new FakeWidget();",
            '$"{a"' * 20000 + "\nvar w = new FakeWidget();",
            '$@"{d\n' * 3000 + "var w = new FakeWidget();",
            '$"{/*\n' * 20000 + "var w = new FakeWidget();",
            '$"{@"q\n' * 20000 + "var w = new FakeWidget();",
            'x = $"{a\n' * 3000 + "var w = new FakeWidget();",
            "x = "
            + '"""'
            + "\n" * 1
            + ("x = " + '"""' + "\n") * 20000
            + "var w = new FakeWidget();",
            ("x = $$" + '"""' + "\n{{ a\n") * 3000 + "var w = new FakeWidget();",
            "var x = " + '$@"{' * 60 + "q" + '\n}"a' * 60 + ";\nvar w = new FakeWidget();",
            "x = $"
            + '"""'
            + "\n"
            + ("    {/*\n    " + '"""' + "*/x}\n") * 20000
            + "var w = new FakeWidget();",
            '"""a""" ' * 320000 + "\nvar w = new FakeWidget();",
        )
        for code in cases:
            started = time.monotonic()

            result = _extract_identifiers(code, "csharp")

            assert time.monotonic() - started < 10, code[:20]
            assert "FakeWidget" in result, code[:20]

    def test_unclosed_bracket_does_not_reach_later_statements(self) -> None:
        code = "[Broken(\nvar a = 1;\nvar w = Build(Size: 3);"

        result = _extract_identifiers(code, "csharp")

        assert "Size" in result

    def test_named_argument_in_ordinary_call_stays_code(self) -> None:
        code = "var w = Build(Size: 3);"

        result = _extract_identifiers(code, "csharp")

        assert "Size" in result

    def test_comment_quote_does_not_open_a_literal(self) -> None:
        code = "// don't\nvar w = new FakeWidget();"

        result = _extract_identifiers(code, "csharp")

        assert "FakeWidget" in result

    def test_other_languages_keep_string_text(self) -> None:
        result = _extract_identifiers('s := "Hello WidgetFactory"', "go")

        assert "WidgetFactory" in result


class TestExtractQuantitativeClaims:
    def test_percentage(self) -> None:
        result = _extract_quantitative_claims("Achieves 95.5% accuracy")
        assert any("95.5%" in c for c in result)

    def test_timing(self) -> None:
        result = _extract_quantitative_claims("Response time is 100ms")
        assert any("100ms" in c for c in result)

    def test_no_claims(self) -> None:
        assert _extract_quantitative_claims("No numbers here") == []

    def test_comparison(self) -> None:
        result = _extract_quantitative_claims("Latency <5%")
        assert len(result) > 0


class TestCountCodeBlocks:
    def test_counts_fenced_blocks(self) -> None:
        md = "```python\ncode\n```\n\n```js\nmore\n```\n"
        # Counts both opening and closing fence lines matching the pattern
        assert _count_code_blocks(md) == 4

    def test_no_blocks(self) -> None:
        assert _count_code_blocks("Just text") == 0


class TestExtractPythonSymbols:
    def test_extracts_class(self) -> None:
        code = "class MyClass:\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 1
        assert symbols[0].name == "MyClass"
        assert symbols[0].kind == "class"

    def test_extracts_function(self) -> None:
        code = "def process_data(x):\n    return x\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 1
        assert symbols[0].name == "process_data"
        assert symbols[0].kind == "function"

    def test_skips_private(self) -> None:
        code = "def _private():\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 0

    def test_records_line_number(self) -> None:
        code = "\n\ndef foo():\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert symbols[0].line == 3


class TestExtractCsharpSymbols:
    def test_extracts_class(self) -> None:
        code = "    public class Foo\n    {\n    }\n"
        symbols = _extract_csharp_symbols(code, "Foo.cs")
        assert len(symbols) == 1
        assert symbols[0].name == "Foo"
        assert symbols[0].kind == "class"

    def test_extracts_method(self) -> None:
        code = "    public void DoWork(int x)\n    {\n    }\n"
        symbols = _extract_csharp_symbols(code, "Bar.cs")
        assert len(symbols) == 1
        assert symbols[0].name == "DoWork"
        assert symbols[0].kind == "method"


class TestSourceSymbol:
    def test_to_dict(self) -> None:
        sym = SourceSymbol(
            name="Foo",
            kind="class",
            file="a.py",
            line=1,
            signature="class Foo:",
        )
        d = sym.to_dict()
        assert d["name"] == "Foo"
        assert d["visibility"] == "public"


class TestSourceCoupling:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("The output is deterministic.", []),
            ("class Local:\n    def __init__(self): pass\n", []),
            ("Use `output.py`.", ["scripts/github_core/output.py"]),
            ("Use `scripts/github_core/output.py`.", ["scripts/github_core/output.py"]),
            ("Use `github_core.output`.", ["scripts/github_core/output.py"]),
            ("Call `write_outputs()`.", ["scripts/github_core/output.py"]),
            ("Call `client.write_outputs()`.", ["scripts/github_core/output.py"]),
            ("Use `my_write_outputs_helper()`.", []),
            ("See `output.py.old` and `missing_output.py`.", []),
            ("See `github_core.output_backup`.", []),
            ("See `scripts/github_core/__init__.py`.", ["scripts/github_core/__init__.py"]),
            ("The main branch holds releases.", []),
            ("Call `alpha.main()`.", ["alpha.py"]),
        ],
    )
    def test_coupling_requires_a_source_reference(
        self, tmp_path: Path, content: str, expected: list[str]
    ) -> None:
        """D3: prose substrings must not create source coupling."""
        package = tmp_path / "scripts" / "github_core"
        package.mkdir(parents=True)
        (package / "output.py").write_text(
            "def write_outputs():\n    return {}\n", encoding="utf-8"
        )
        (package / "__init__.py").write_text("class GithubClient:\n    pass\n", encoding="utf-8")
        (tmp_path / "alpha.py").write_text("def main():\n    return 1\n", encoding="utf-8")
        (tmp_path / "beta.py").write_text("def main():\n    return 2\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(content, encoding="utf-8")

        result = run_assessment(tmp_path)

        assert len(result["documentation_files"]) == 1
        assert len(result["source_symbols"]) == 4
        assert result["documentation_files"][0]["mapped_source_files"] == expected

    @pytest.mark.parametrize(
        ("language", "content", "exit_code"),
        [
            ("python", "class EmailValidator:\n    pass\nEmailValidator()", 0),
            ("python", "MissingWidget()", 10),
            ("python", "from missing_package import MissingWidget", 10),
            ("csharp", "// CORRECT MissingWidget\nnew ExistingWidget();", 0),
            ("csharp", "new MissingWidget(); // CORRECT", 10),
            ("csharp", "// CORRECT MissingWidget\nnew ExistingWidget();", 0),
            ("csharp", "/* CORRECT MissingWidget\nstill comment */ new ExistingWidget();", 0),
            ("csharp", 'var url = "https://host"; // MissingWidget', 0),
            ("csharp", 'var path = @"folder//file"; // MissingWidget', 0),
            ("csharp", "Configure(timeout: 1);", 0),
            ("csharp", "Configure(timeout: 1); // Configure(wrong: 2);", 0),
            ("csharp", "Configure(wrong: 1);", 10),
            ("csharp", "Configure(wrong: 1); // Configure(timeout: 2);", 10),
        ],
    )
    def test_cli_keeps_symbol_and_parameter_failures(
        self, tmp_path: Path, language: str, content: str, exit_code: int
    ) -> None:
        """D3: false findings must clear without making real errors pass."""
        (tmp_path / "widget.cs").write_text(
            "public class ExistingWidget {\n    public void Configure(int timeout) { }\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(f"```{language}\n{content}\n```\n", encoding="utf-8")
        output = tmp_path / ".doc-accuracy"

        assert main(["--target", str(tmp_path), "--output-dir", str(output)]) == exit_code
        report = (output / "compilability-findings.json").read_text(encoding="utf-8")
        findings = json.loads(report)["findings"]
        if exit_code:
            assert len(findings) == 1
            assert findings[0]["severity"] == (
                "critical" if content.startswith("Configure(wrong:") else "high"
            )
        else:
            assert findings == []


class TestRunAssessment:
    def test_scans_directory(self, tmp_path: Path) -> None:
        (tmp_path / ".git").write_text("gitdir: missing\n")
        (tmp_path / "README.md").write_text("# Hello\n`MyFunc`\n")
        (tmp_path / "main.py").write_text("def MyFunc():\n    pass\n")

        result = run_assessment(tmp_path)

        assert len(result["documentation_files"]) >= 1
        assert len(result["source_symbols"]) >= 1
        assert "coverage_summary" in result
        assert result["changed_files"] is None

    def test_diff_base_scopes_doc_inventory_to_changed_files(self, tmp_path: Path) -> None:
        """diff_base must restrict assessed docs to files changed since that ref.

        Regression for issue #4520: changed_files was computed but never used
        to filter the doc inventory, so --diff-base reported the full backlog
        even when no documentation files changed.
        """
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Base commit: two markdown docs and one Python source
        (repo / "old.md").write_text("# Old doc\n")
        (repo / "unchanged.md").write_text("# Unchanged doc\n")
        (repo / "main.py").write_text("def foo():\n    pass\n")
        subprocess.run(
            ["git", "add", "old.md", "unchanged.md", "main.py"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "base"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Second commit: only old.md changed; unchanged.md not touched
        (repo / "old.md").write_text("# Old doc updated\n")
        subprocess.run(
            ["git", "add", "old.md"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "update doc"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = run_assessment(repo, diff_base="HEAD~1")

        doc_paths = [d["path"] for d in result["documentation_files"]]
        # Only old.md changed since HEAD~1; unchanged.md must be excluded.
        assert "old.md" in doc_paths
        assert "unchanged.md" not in doc_paths
        # Source files are always indexed regardless of diff_base.
        assert any(s["name"] == "foo" for s in result["source_symbols"])

    def test_diff_base_no_changed_docs_yields_empty_inventory(self, tmp_path: Path) -> None:
        """When only non-doc files changed, the doc inventory is empty."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        (repo / "doc.md").write_text("# Doc\n")
        (repo / "script.sh").write_text("#!/bin/bash\necho hi\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "base"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        # Only the shell script changed, not the doc
        (repo / "script.sh").write_text("#!/bin/bash\necho bye\n")
        subprocess.run(
            ["git", "add", "script.sh"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "update script"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        result = run_assessment(repo, diff_base="HEAD~1")

        doc_paths = [d["path"] for d in result["documentation_files"]]
        # doc.md was not changed; must not appear in the scoped inventory.
        assert "doc.md" not in doc_paths

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = run_assessment(tmp_path)
        assert result["documentation_files"] == []
        assert result["source_symbols"] == []
        assert result["coverage_summary"]["coverage_pct"] == 100.0

    def test_diff_base_scopes_docs_to_changed_files(self, tmp_path: Path) -> None:
        (tmp_path / "changed.md").write_text("# Changed\n`PublicThing`\n")
        (tmp_path / "unchanged.md").write_text("# Unchanged\n")
        (tmp_path / "code.py").write_text("def PublicThing():\n    pass\n")
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "t"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )

        with patch.object(mod, "_get_changed_diff", return_value=({"changed.md"}, {})):
            result = run_assessment(
                tmp_path,
                doc_globs=["*.md"],
                diff_base="origin/main",
            )

        doc_paths = {doc["path"] for doc in result["documentation_files"]}
        source_names = {symbol["name"] for symbol in result["source_symbols"]}
        assert doc_paths == {"changed.md"}
        assert result["changed_files"] == ["changed.md"]
        assert "PublicThing" in source_names

    def test_diff_base_empty_change_set_yields_no_docs(self, tmp_path: Path) -> None:
        (tmp_path / "unchanged.md").write_text("# Unchanged\n")
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "t"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )

        with patch.object(mod, "_get_changed_diff", return_value=(set(), {})):
            result = run_assessment(
                tmp_path,
                doc_globs=["*.md"],
                diff_base="origin/main",
            )

        assert result["documentation_files"] == []
        assert result["changed_files"] == []


class TestGetChangedFiles:
    """Tests for _get_changed_files and its integration via main()."""

    @staticmethod
    def _init_repo(path: Path) -> None:
        """Create a minimal git repo with one empty commit."""
        import os

        subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(path), "config", "user.name", "t"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.email", "t@t"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"],
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )

    def test_invalid_ref_exits_2(self, tmp_path: Path) -> None:
        """Invalid --diff-base is config error => exit 2 (ADR-035)."""
        self._init_repo(tmp_path)
        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base",
                "no-such-ref",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 2

    def test_corrupt_object_db_exits_3(self, tmp_path: Path) -> None:
        """Valid ref but object-DB failure (rc 128) => exit 3."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def corrupt_verify(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--verify" in cmd:
                raise subprocess.CalledProcessError(
                    128,
                    cmd,
                    stderr="fatal: unable to read object: permission denied",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=corrupt_verify):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3

    def test_ref_to_missing_object_exits_3(self, tmp_path: Path) -> None:
        """A resolved ref with a missing object is an external Git failure."""
        self._init_repo(tmp_path)
        missing_oid = "1234567890abcdef1234567890abcdef12345678"
        ref = tmp_path / ".git" / "refs" / "heads" / "missing-object"
        ref.write_text(f"{missing_oid}\n")

        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base",
                "missing-object",
                "--phases",
                "1",
            ]
        )

        assert exit_code == 3

    def test_localized_stderr_invalid_ref_exits_2(self, tmp_path: Path) -> None:
        """Localized git with rc1 (unresolved ref) => exit 2, not pattern match."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def localized_verify(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--verify" in cmd:
                # Non-English stderr, but rc 1 signals unresolved ref
                raise subprocess.CalledProcessError(
                    1,
                    cmd,
                    stderr="fatale: unbekannte Revision 'no-such-ref'",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=localized_verify):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "no-such-ref",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 2

    def test_invalid_git_directory_exits_3(self, tmp_path: Path) -> None:
        """Invalid Git metadata is an environment error => exit 3."""
        repo = tmp_path / "not-a-repo"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: missing\n")

        exit_code = main(
            [
                "--target",
                str(repo),
                "--diff-base",
                "HEAD",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 3

    def test_bare_repo_exits_3(self, tmp_path: Path) -> None:
        """Bare repo returns rc0 with stdout 'false'; must still exit 3."""
        subprocess.run(
            ["git", "init", "--bare", str(tmp_path / "bare.git")],
            capture_output=True,
            check=True,
        )
        exit_code = main(
            [
                "--target",
                str(tmp_path / "bare.git"),
                "--diff-base",
                "HEAD",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 3

    def test_worktree_false_stdout_exits_3(self, tmp_path: Path) -> None:
        """rev-parse rc0 but stdout 'false' (bare/non-worktree) => exit 3."""
        real_run = subprocess.run

        def mock_worktree_false(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--is-inside-work-tree" in cmd:
                result = MagicMock()
                result.stdout = "false\n"
                result.returncode = 0
                return result
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        self._init_repo(tmp_path)
        with patch.object(subprocess, "run", side_effect=mock_worktree_false):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3

    def test_missing_git_exits_3(self, tmp_path: Path) -> None:
        """Missing git binary is an environment error => exit 3."""
        with patch.object(
            subprocess,
            "run",
            side_effect=FileNotFoundError("git not found"),
        ):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3

    def test_rev_parse_timeout_exits_3(self, tmp_path: Path) -> None:
        """Timeout during rev-parse is an environment error => exit 3."""
        with patch.object(
            subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("git", 60),
        ):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3

    def test_ls_files_timeout_exits_3(self, tmp_path: Path) -> None:
        """Timeout during ls-files (after diff succeeds) => exit 3."""
        self._init_repo(tmp_path)
        real_run = subprocess.run
        ls_files_timeout_seen: list[object] = []

        def selective_timeout(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "ls-files" in cmd:
                ls_files_timeout_seen.append(kwargs.get("timeout"))
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=selective_timeout):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3
        # Verify timeout kwarg was actually passed to ls-files subprocess call
        assert ls_files_timeout_seen, "ls-files was never called"
        assert all(t is not None for t in ls_files_timeout_seen), (
            "ls-files subprocess.run called without timeout kwarg"
        )

    def test_ls_files_error_with_diff_base_exits_3(self, tmp_path: Path) -> None:
        """ls-files CalledProcessError in diff-base mode => exit 3, not rglob fallback."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def fail_ls_files(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "ls-files" in cmd:
                raise subprocess.CalledProcessError(
                    128,
                    cmd,
                    stderr="fatal: index corrupted",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=fail_ls_files):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3

    def test_no_diff_base_ls_files_fallback_works(self, tmp_path: Path) -> None:
        """Without diff-base, ls-files failure falls back to rglob (exit 0)."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def fail_ls_files(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "ls-files" in cmd:
                raise subprocess.CalledProcessError(
                    128,
                    cmd,
                    stderr="fatal: index corrupted",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=fail_ls_files):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 0

    def test_valid_empty_diff_exits_0(self, tmp_path: Path) -> None:
        """Valid diff-base with no changed files passes (exit 0)."""
        self._init_repo(tmp_path)
        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base",
                "HEAD",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 0

    def test_changed_diff_exits_0(self, tmp_path: Path) -> None:
        """Valid diff-base with actual changes still passes."""
        import os

        self._init_repo(tmp_path)
        (tmp_path / "README.md").write_text("# Hello\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "README.md"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add readme"],
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )
        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base",
                "HEAD~1",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 0

    def test_ignores_blank_diff_lines(self, tmp_path: Path) -> None:
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def selective_mock(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "diff" in cmd and "--name-only" in cmd:
                result = MagicMock()
                result.stdout = b"doc.md\x00\x00script.py\x00"
                result.returncode = 0
                return result
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=selective_mock):
            result = _get_changed_files("HEAD", tmp_path)

        assert result == {"doc.md", "script.py"}

    def test_unicode_and_newline_paths(self, tmp_path: Path) -> None:
        """Files with Unicode and special chars are returned via -z output."""
        self._init_repo(tmp_path)
        unicode_file = tmp_path / "\u00e9l\u00e8ve.md"
        newline_file = tmp_path / "line\nbreak.md"
        unicode_file.write_text("# Unicode\n")
        newline_file.write_text("# Newline\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "unicode"],
            check=True,
            capture_output=True,
        )
        changed = _get_changed_files("HEAD~1", tmp_path)
        assert "\u00e9l\u00e8ve.md" in changed
        assert "line\nbreak.md" in changed
        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base",
                "HEAD~1",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 0

    def test_non_utf8_path_round_trips_through_nul_output(self, tmp_path: Path) -> None:
        """NUL-delimited Git bytes use filesystem surrogate decoding."""
        import os

        if os.name == "nt":
            return
        self._init_repo(tmp_path)
        raw_name = b"invalid-\xff.md"
        raw_path = os.fsencode(tmp_path) + b"/" + raw_name
        fd = os.open(raw_path, os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, b"# Invalid bytes\n")
        finally:
            os.close(fd)
        subprocess.run(
            [b"git", b"-C", os.fsencode(tmp_path), b"add", b"."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [b"git", b"-C", os.fsencode(tmp_path), b"commit", b"-m", b"bytes"],
            check=True,
            capture_output=True,
        )

        expected = os.fsdecode(raw_name)
        assert expected in _get_changed_files("HEAD~1", tmp_path)
        tracked = {
            _repo_relative(path, tmp_path) for path in _list_git_files(tmp_path, require_git=True)
        }
        assert expected in tracked

    def test_foreign_git_dir_ignored(self, tmp_path: Path) -> None:
        """GIT_DIR env var pointing elsewhere does not affect result."""
        self._init_repo(tmp_path)
        (tmp_path / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add a"],
            check=True,
            capture_output=True,
        )
        # Set GIT_DIR to a bogus location; should be sanitized
        import os as _os

        old = _os.environ.get("GIT_DIR")
        _os.environ["GIT_DIR"] = "/nonexistent/.git"
        try:
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD~1",
                    "--phases",
                    "1",
                ]
            )
        finally:
            if old is None:
                _os.environ.pop("GIT_DIR", None)
            else:
                _os.environ["GIT_DIR"] = old
        assert exit_code == 0

    def test_git_config_count_injection_blocked(self, tmp_path: Path) -> None:
        """Malicious core.fsmonitor via GIT_CONFIG_COUNT cannot execute."""
        self._init_repo(tmp_path)
        (tmp_path / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )
        sentinel = tmp_path / "pwned_sentinel"
        sentinel.unlink(missing_ok=True)
        import os as _os

        injections = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": f"echo pwned > {sentinel}",
        }
        old_vals: dict[str, str | None] = {}
        for k, v in injections.items():
            old_vals[k] = _os.environ.get(k)
            _os.environ[k] = v
        try:
            subprocess.run(
                ["git", "-C", str(tmp_path), "status", "--porcelain"],
                check=True,
                capture_output=True,
            )
            assert sentinel.exists(), "config-count fsmonitor probe did not execute"
            sentinel.unlink()
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD~1",
                    "--phases",
                    "1",
                ]
            )
        finally:
            for k in injections:
                old_value = old_vals[k]
                if old_value is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = old_value
        assert exit_code == 0
        assert not sentinel.exists(), "fsmonitor injection executed despite env sanitization"

    def test_global_fsmonitor_config_is_ignored(self, tmp_path: Path) -> None:
        """User-level core.fsmonitor cannot execute during the scan."""
        import os

        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo)
        (repo / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add a"],
            check=True,
            capture_output=True,
        )

        sentinel = tmp_path / "global-fsmonitor-ran"
        hook = tmp_path / "global-fsmonitor.py"
        hook.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran')\n",
        )
        hook.chmod(0o755)
        home = tmp_path / "home"
        home.mkdir()
        subprocess.run(
            [
                "git",
                "config",
                "--file",
                str(home / ".gitconfig"),
                "core.fsmonitor",
                str(hook),
            ],
            check=True,
            capture_output=True,
        )
        inherited_env = os.environ.copy()
        inherited_env["HOME"] = str(home)
        inherited_env.pop("GIT_CONFIG_GLOBAL", None)
        inherited_env.pop("GIT_CONFIG_NOSYSTEM", None)
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True,
            capture_output=True,
            env=inherited_env,
        )
        assert sentinel.exists(), "global fsmonitor probe did not execute"
        sentinel.unlink()

        with patch.dict(os.environ, inherited_env, clear=True):
            exit_code = main(
                [
                    "--target",
                    str(repo),
                    "--diff-base",
                    "HEAD~1",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 0
        assert not sentinel.exists()

    def test_system_fsmonitor_config_is_ignored(self, tmp_path: Path) -> None:
        """System-level core.fsmonitor cannot execute during the scan."""
        import os

        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo)
        (repo / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add a"],
            check=True,
            capture_output=True,
        )

        sentinel = tmp_path / "system-fsmonitor-ran"
        hook = tmp_path / "system-fsmonitor.py"
        hook.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran')\n",
        )
        hook.chmod(0o755)
        system_config = tmp_path / "system.gitconfig"
        subprocess.run(
            [
                "git",
                "config",
                "--file",
                str(system_config),
                "core.fsmonitor",
                str(hook),
            ],
            check=True,
            capture_output=True,
        )
        inherited_env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": str(system_config),
        }
        inherited_env.pop("GIT_CONFIG_NOSYSTEM", None)
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True,
            capture_output=True,
            env=inherited_env,
        )
        assert sentinel.exists(), "system fsmonitor probe did not execute"
        sentinel.unlink()

        with patch.dict(os.environ, inherited_env, clear=True):
            exit_code = main(
                [
                    "--target",
                    str(repo),
                    "--diff-base",
                    "HEAD~1",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 0
        assert not sentinel.exists()

    def test_repository_fsmonitor_config_is_disabled(self, tmp_path: Path) -> None:
        """Repository-local core.fsmonitor cannot execute during the scan."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo)
        (repo / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add a"],
            check=True,
            capture_output=True,
        )

        sentinel = tmp_path / "local-fsmonitor-ran"
        hook = tmp_path / "local-fsmonitor.py"
        hook.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('ran')\n",
        )
        hook.chmod(0o755)
        subprocess.run(
            ["git", "-C", str(repo), "config", "core.fsmonitor", str(hook)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True,
            capture_output=True,
        )
        assert sentinel.exists(), "repository fsmonitor probe did not execute"
        sentinel.unlink()

        exit_code = main(
            [
                "--target",
                str(repo),
                "--diff-base",
                "HEAD~1",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 0
        assert not sentinel.exists()

    def test_graft_replace_shallow_overrides_ignored(self, tmp_path: Path) -> None:
        """GIT_GRAFT_FILE/REPLACE_REF_BASE/SHALLOW_FILE do not alter results."""
        self._init_repo(tmp_path)
        (tmp_path / "a.md").write_text("# A\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True,
            capture_output=True,
        )
        import os as _os

        overrides = {
            "GIT_GRAFT_FILE": "/nonexistent/grafts",
            "GIT_REPLACE_REF_BASE": "refs/replace-evil/",
            "GIT_SHALLOW_FILE": "/nonexistent/shallow",
        }
        old_vals: dict[str, str | None] = {}
        for k, v in overrides.items():
            old_vals[k] = _os.environ.get(k)
            _os.environ[k] = v
        try:
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD~1",
                    "--phases",
                    "1",
                ]
            )
        finally:
            for k in overrides:
                old_value = old_vals[k]
                if old_value is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = old_value
        assert exit_code == 0

    def test_git_env_sanitizes_local_and_config_vars_case_insensitively(
        self,
    ) -> None:
        """Git overrides cannot survive with Windows-style key casing."""
        import os as _os

        local_vars = [
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CONFIG",
            "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_COUNT",
            "GIT_OBJECT_DIRECTORY",
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_IMPLICIT_WORK_TREE",
            "GIT_GRAFT_FILE",
            "GIT_INDEX_FILE",
            "GIT_NO_REPLACE_OBJECTS",
            "GIT_REPLACE_REF_BASE",
            "GIT_PREFIX",
            "GIT_SHALLOW_FILE",
            "GIT_COMMON_DIR",
            "git_dir",
            "Git_Work_Tree",
            "git_object_directory",
        ]
        prefix_vars = [
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
            "Git_Config_Arbitrary",
            "git_config_key_99",
        ]
        all_test = local_vars + prefix_vars
        saved: dict[str, str | None] = {k: _os.environ.get(k) for k in all_test}
        for k in all_test:
            _os.environ[k] = "injected"
        try:
            env = _git_env()
        finally:
            for k in all_test:
                saved_value = saved[k]
                if saved_value is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = saved_value
        forced = {
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
            "GIT_GRAFT_FILE",
            "GIT_NO_REPLACE_OBJECTS",
            "GIT_SHALLOW_FILE",
        }
        for key in env:
            normalized = key.upper()
            if normalized.startswith("GIT_CONFIG_"):
                assert normalized in forced
        assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert env["GIT_GRAFT_FILE"] == _os.devnull
        assert env["GIT_SHALLOW_FILE"] == _os.devnull

    def test_repository_replace_ref_cannot_hide_changed_file(self, tmp_path: Path) -> None:
        """A repository replace ref cannot rewrite the diff-base tree."""
        self._init_repo(tmp_path)
        base = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (tmp_path / "changed.md").write_text("# Changed\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "changed"],
            check=True,
            capture_output=True,
        )
        head_tree = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD^{tree}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        replacement = subprocess.run(
            ["git", "-C", str(tmp_path), "commit-tree", head_tree],
            check=True,
            capture_output=True,
            text=True,
            input="replacement\n",
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(tmp_path), "replace", base, replacement],
            check=True,
            capture_output=True,
        )
        unsanitized = subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "diff",
                "--name-only",
                base,
                "HEAD",
                "--",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert unsanitized.stdout == "", "replace ref probe did not hide the file"

        assert "changed.md" in _get_changed_files(base, tmp_path)

    def test_repository_graft_and_shallow_files_are_ignored(self, tmp_path: Path) -> None:
        """Repository graft and shallow metadata cannot hide HEAD's parent."""
        self._init_repo(tmp_path)
        (tmp_path / "changed.md").write_text("# Changed\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "changed"],
            check=True,
            capture_output=True,
        )
        head = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        git_dir = tmp_path / ".git"
        (git_dir / "info" / "grafts").write_text(f"{head}\n")
        (git_dir / "shallow").write_text(f"{head}\n")
        unsanitized = subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "rev-parse",
                "--verify",
                "--quiet",
                "HEAD~1^{commit}",
            ],
            capture_output=True,
        )
        assert unsanitized.returncode != 0, "graft/shallow probe did not hide HEAD's parent"

        assert "changed.md" in _get_changed_files("HEAD~1", tmp_path)

    def test_blob_and_tree_revision_expressions_exit_2(self, tmp_path: Path) -> None:
        """Valid non-commit revisions are invalid diff-base configuration."""
        self._init_repo(tmp_path)
        (tmp_path / "README.md").write_text("# Readme\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "README.md"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add readme"],
            check=True,
            capture_output=True,
        )

        for revision in ("HEAD^{tree}", "HEAD:README.md"):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    revision,
                    "--phases",
                    "1",
                ]
            )
            assert exit_code == 2

    def test_annotated_tag_and_symbolic_ref_are_accepted(self, tmp_path: Path) -> None:
        """Commitish tags and symbolic refs resolve to immutable commit IDs."""
        self._init_repo(tmp_path)
        subprocess.run(
            ["git", "-C", str(tmp_path), "tag", "-a", "base", "-m", "base"],
            check=True,
            capture_output=True,
        )
        branch = subprocess.run(
            ["git", "-C", str(tmp_path), "symbolic-ref", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "symbolic-ref",
                "refs/heads/base-symbolic",
                f"refs/heads/{branch}",
            ],
            check=True,
            capture_output=True,
        )

        assert _get_changed_files("base", tmp_path) == set()
        assert _get_changed_files("base-symbolic", tmp_path) == set()

    @staticmethod
    def _git(path: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(path), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _commit_file(self, path: Path, name: str) -> None:
        (path / name).write_text(f"# {name}\n")
        self._git(path, "add", name)
        self._git(path, "commit", "-m", name)

    def test_base_that_advanced_after_fork_is_not_counted(self, tmp_path: Path) -> None:
        """Commits on the base after the fork are not this branch's changes."""
        self._init_repo(tmp_path)
        base = self._git(tmp_path, "symbolic-ref", "--short", "HEAD")
        self._git(tmp_path, "switch", "-c", "feature")
        self._commit_file(tmp_path, "feature.md")
        self._git(tmp_path, "switch", base)
        self._commit_file(tmp_path, "base-only.md")
        self._git(tmp_path, "switch", "feature")

        assert _get_changed_files(base, tmp_path) == {"feature.md"}

    def test_base_that_advanced_after_fork_scopes_cli_inventory(self, tmp_path: Path) -> None:
        """main() reports only the branch's doc when the base moved on."""
        self._init_repo(tmp_path)
        base = self._git(tmp_path, "symbolic-ref", "--short", "HEAD")
        self._git(tmp_path, "switch", "-c", "feature")
        self._commit_file(tmp_path, "feature.md")
        self._git(tmp_path, "switch", base)
        self._commit_file(tmp_path, "base-only.md")
        self._git(tmp_path, "switch", "feature")
        out_dir = tmp_path / "out"

        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base",
                base,
                "--phases",
                "1",
                "--output-dir",
                str(out_dir),
            ]
        )

        assert exit_code == 0
        assessment = json.loads((out_dir / "assessment.json").read_text())
        assert assessment["changed_files"] == ["feature.md"]

    def test_unrelated_history_exits_2(self, tmp_path: Path) -> None:
        """A base sharing no history with HEAD is a config error."""
        self._init_repo(tmp_path)
        base = self._git(tmp_path, "symbolic-ref", "--short", "HEAD")
        self._git(tmp_path, "switch", "--orphan", "island")
        self._commit_file(tmp_path, "island.md")

        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base",
                base,
                "--phases",
                "1",
            ]
        )

        assert exit_code == 2

    def test_merge_base_git_failure_exits_3(self, tmp_path: Path) -> None:
        """A merge-base failure other than 'no history' is external."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def failing_merge_base(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "merge-base" in cmd:
                raise subprocess.CalledProcessError(
                    128,
                    cmd,
                    output=b"",
                    stderr=b"fatal: bad object",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=failing_merge_base):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )

        assert exit_code == 3

    def test_malformed_merge_base_stdout_exits_3(self, tmp_path: Path) -> None:
        """Successful merge-base with malformed output is a tool failure."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def malformed(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "merge-base" in cmd:
                return subprocess.CompletedProcess(cmd, 0, b"not-an-oid", b"")
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=malformed):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )

        assert exit_code == 3

    def test_option_like_revision_exits_2(self, tmp_path: Path) -> None:
        """An option-like diff base remains data after --end-of-options."""
        self._init_repo(tmp_path)
        exit_code = main(
            [
                "--target",
                str(tmp_path),
                "--diff-base=--help",
                "--phases",
                "1",
            ]
        )
        assert exit_code == 2

    def test_malformed_rev_parse_stdout_exits_3(self, tmp_path: Path) -> None:
        """Successful rev-parse with malformed output is a tool failure."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def malformed(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "--verify" in cmd:
                return subprocess.CompletedProcess(cmd, 0, b"--output=owned", b"")
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=malformed):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3

    def test_every_git_boundary_call_is_isolated_and_timed(self, tmp_path: Path) -> None:
        """Every scanner-owned Git subprocess disables inherited execution."""
        import os

        self._init_repo(tmp_path)
        real_run = subprocess.run
        observed: list[tuple[list[str], object, dict[str, str]]] = []

        def recording_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            observed.append(
                (cmd, kwargs.get("timeout"), kwargs.get("env", {})),
            )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=recording_run):
            _get_changed_files("HEAD", tmp_path)
            list(_list_git_files(tmp_path, require_git=True))

        assert observed
        for command, timeout, env in observed:
            assert timeout == mod._GIT_TIMEOUT
            assert command[0] == "git"
            assert "--no-replace-objects" in command
            config_index = command.index("-c")
            assert command[config_index + 1] == "core.fsmonitor=false"
            assert env["GIT_CONFIG_NOSYSTEM"] == "1"
            assert env["GIT_CONFIG_GLOBAL"] == os.devnull
            assert env["GIT_CONFIG_SYSTEM"] == os.devnull

    def test_windows_paths_normalize_to_git_separators(self) -> None:
        """Repository-relative paths use slashes on Windows."""
        from pathlib import PureWindowsPath

        path = PureWindowsPath(r"C:\repo\docs\guide.md")
        root = PureWindowsPath(r"C:\repo")
        assert _repo_relative(path, root) == "docs/guide.md"

    def test_resolved_oid_missing_object_exits_3(self, tmp_path: Path) -> None:
        """OID resolved but cat-file fails (object gone) => exit 3."""
        self._init_repo(tmp_path)
        real_run = subprocess.run

        def fail_cat_file(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "cat-file" in cmd:
                raise subprocess.CalledProcessError(
                    1,
                    cmd,
                    stderr=b"fatal: Not a valid object name",
                )
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        with patch.object(subprocess, "run", side_effect=fail_cat_file):
            exit_code = main(
                [
                    "--target",
                    str(tmp_path),
                    "--diff-base",
                    "HEAD",
                    "--phases",
                    "1",
                ]
            )
        assert exit_code == 3


class TestRunClaimExtraction:
    def test_extracts_code_example(self, tmp_path: Path) -> None:
        md = "# Doc\n\n```python\nMyClass()\n```\n"
        (tmp_path / "doc.md").write_text(md)

        assessment = {
            "documentation_files": [
                {
                    "path": "doc.md",
                    "mapped_source_files": [],
                    "referenced_symbols": [],
                }
            ],
            "source_symbols": [],
        }
        result = run_claim_extraction(tmp_path, assessment)
        assert len(result["claims"]) >= 1
        assert result["claims"][0]["type"] == "code_example"
        assert result["claims"][0]["language"] == "python"

    def test_extracts_quantitative_claim(self, tmp_path: Path) -> None:
        md = "Performance is 99.9% uptime.\n"
        (tmp_path / "perf.md").write_text(md)

        assessment = {
            "documentation_files": [
                {
                    "path": "perf.md",
                    "mapped_source_files": [],
                    "referenced_symbols": [],
                }
            ],
            "source_symbols": [],
        }
        result = run_claim_extraction(tmp_path, assessment)
        quant = [c for c in result["claims"] if c["type"] == "quantitative"]
        assert len(quant) >= 1

    def test_csharp_hash_fence_detected(self, tmp_path: Path) -> None:
        """A ```c# fence must be detected as csharp, not truncated to 'c'."""
        md = "# Doc\n\n```c#\nvar x = new MyWidget();\n```\n"
        (tmp_path / "doc.md").write_text(md)

        assessment = {
            "documentation_files": [
                {
                    "path": "doc.md",
                    "mapped_source_files": [],
                    "referenced_symbols": [],
                }
            ],
            "source_symbols": [],
        }
        result = run_claim_extraction(tmp_path, assessment)
        code_claims = [c for c in result["claims"] if c["type"] == "code_example"]
        assert len(code_claims) == 1
        assert code_claims[0]["language"] == "csharp"


class TestRunCompilabilityCheck:
    def test_no_findings_when_symbol_exists(self) -> None:
        assessment = {
            "source_symbols": [
                {
                    "name": "MyClass",
                    "kind": "class",
                    "file": "a.py",
                    "line": 1,
                    "signature": "class MyClass:",
                    "visibility": "public",
                }
            ],
        }
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "doc.md",
                    "line": 1,
                    "type": "code_example",
                    "language": "python",
                    "content": "x = MyClass()",
                    "symbols_referenced": ["MyClass"],
                    "mapped_source": "a.py",
                }
            ],
        }
        result = run_compilability_check(assessment, claims)
        assert result["status"] == "COMPLETED"
        assert result["findings"] == []

    def test_finds_unresolved_symbol(self) -> None:
        assessment = {
            "source_symbols": [
                {
                    "name": "ExistingWidget",
                    "kind": "class",
                    "file": "a.py",
                    "line": 1,
                    "signature": "class ExistingWidget:",
                    "visibility": "public",
                }
            ],
        }
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "doc.md",
                    "line": 1,
                    "type": "method_signature",
                    "language": "",
                    "content": "MyWidget does things",
                    "symbols_referenced": ["MyWidget"],
                    "mapped_source": "",
                }
            ],
        }
        result = run_compilability_check(assessment, claims)
        assert result["status"] == "COMPLETED"
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "unresolved_symbol"

    def test_skips_framework_types(self) -> None:
        assessment = {
            "source_symbols": [
                {
                    "name": "ExistingWidget",
                    "kind": "class",
                    "file": "a.py",
                    "line": 1,
                    "signature": "class ExistingWidget:",
                    "visibility": "public",
                }
            ],
        }
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "doc.md",
                    "line": 1,
                    "type": "method_signature",
                    "language": "",
                    "content": "Returns a List",
                    "symbols_referenced": ["List"],
                    "mapped_source": "",
                }
            ],
        }
        result = run_compilability_check(assessment, claims)
        assert result["status"] == "COMPLETED"
        assert result["findings"] == []

    def test_does_not_run_without_source_symbols(self) -> None:
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "doc.md",
                    "line": 1,
                    "type": "method_signature",
                    "language": "",
                    "content": "MyWidget does things",
                    "symbols_referenced": ["MyWidget"],
                    "mapped_source": "",
                }
            ],
        }

        result = run_compilability_check({"source_symbols": []}, claims)

        assert result["status"] == "DID_NOT_RUN"
        assert result["findings"] == []
        assert "No source symbols found" in result["reason"]

    def test_does_not_run_without_source_symbols_or_claims(self) -> None:
        result = run_compilability_check(
            {"source_symbols": []},
            {"claims": []},
        )

        assert result["status"] == "DID_NOT_RUN"
        assert result["findings"] == []

    def test_skips_text_fence_ascii_diagram(self) -> None:
        """text fences (ASCII diagrams) must not produce unresolved-symbol findings."""
        assessment = {
            "source_symbols": [
                {
                    "name": "ExistingClass",
                    "kind": "class",
                    "file": "a.cs",
                    "line": 1,
                    "signature": "class ExistingClass",
                    "visibility": "public",
                }
            ],
        }
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "workflow.md",
                    "line": 5,
                    "type": "code_example",
                    "language": "text",
                    "content": "P1 --> P2 --> P3\nEvaluation\nREADY",
                    "symbols_referenced": ["Evaluation", "READY"],
                    "mapped_source": "a.cs",
                }
            ],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []

    def test_skips_powershell_code_example(self) -> None:
        """PowerShell examples must not resolve against the C# symbol index."""
        assessment = {
            "source_symbols": [
                {
                    "name": "ExistingClass",
                    "kind": "class",
                    "file": "a.cs",
                    "line": 1,
                    "signature": "class ExistingClass",
                    "visibility": "public",
                }
            ],
        }
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "ops.md",
                    "line": 10,
                    "type": "code_example",
                    "language": "powershell",
                    "content": "Search-WorkItems.ps1 -FailOnTruncation -SearchText foo",
                    "symbols_referenced": ["FailOnTruncation", "SearchText"],
                    "mapped_source": "a.cs",
                }
            ],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []

    def test_still_checks_csharp_code_example(self) -> None:
        """C# code examples must still be verified (positive control)."""
        assessment = {
            "source_symbols": [
                {
                    "name": "RealClass",
                    "kind": "class",
                    "file": "a.cs",
                    "line": 1,
                    "signature": "class RealClass",
                    "visibility": "public",
                }
            ],
        }
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "api.md",
                    "line": 3,
                    "type": "code_example",
                    "language": "csharp",
                    "content": "var x = new FakeWidget();",
                    "symbols_referenced": ["FakeWidget"],
                    "mapped_source": "a.cs",
                }
            ],
        }
        result = run_compilability_check(assessment, claims)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "unresolved_symbol"

    def test_skips_unlabeled_fence_code_example(self) -> None:
        """Fences with no language label (empty string) are skipped."""
        assessment = {
            "source_symbols": [
                {
                    "name": "ExistingClass",
                    "kind": "class",
                    "file": "a.cs",
                    "line": 1,
                    "signature": "class ExistingClass",
                    "visibility": "public",
                }
            ],
        }
        claims = {
            "claims": [
                {
                    "id": "claim-0001",
                    "file": "doc.md",
                    "line": 1,
                    "type": "code_example",
                    "language": "",
                    "content": "SomeIdentifier here",
                    "symbols_referenced": ["SomeIdentifier"],
                    "mapped_source": "a.cs",
                }
            ],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []


class TestCheckGate:
    def test_pass_no_findings(self) -> None:
        result = check_gate({"findings": []}, "high")
        assert result["verdict"] == "PASS"
        assert result["blocking_findings"] == 0

    def test_pass_none(self) -> None:
        result = check_gate(None, "high")
        assert result["verdict"] == "PASS"

    def test_did_not_run_is_inconclusive(self) -> None:
        result = check_gate(
            {
                "status": "DID_NOT_RUN",
                "reason": "No source symbols found.",
                "findings": [],
            },
            "high",
        )

        assert result["verdict"] == "DID_NOT_RUN"
        assert result["reason"] == "No source symbols found."
        assert result["total_findings"] == 0

    def test_fail_critical(self) -> None:
        findings = {
            "findings": [
                {
                    "severity": "critical",
                    "id": "f1",
                }
            ]
        }
        result = check_gate(findings, "high")
        assert result["verdict"] == "FAIL"
        assert result["blocking_findings"] == 1

    def test_pass_below_threshold(self) -> None:
        findings = {
            "findings": [
                {
                    "severity": "low",
                    "id": "f1",
                }
            ]
        }
        result = check_gate(findings, "high")
        assert result["verdict"] == "PASS"

    def test_severity_counts(self) -> None:
        findings = {
            "findings": [
                {"severity": "critical", "id": "f1"},
                {"severity": "critical", "id": "f2"},
                {"severity": "medium", "id": "f3"},
            ]
        }
        result = check_gate(findings, "critical")
        assert result["by_severity"]["critical"] == 2
        assert result["by_severity"]["medium"] == 1
        assert result["total_findings"] == 3


class TestGenerateMarkdownReport:
    def test_writes_report(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "PASS",
            "threshold": "high",
            "blocking_findings": 0,
            "total_findings": 0,
            "by_severity": {},
        }
        report_path = tmp_path / "report.md"
        generate_markdown_report(None, None, None, gate, report_path)

        content = report_path.read_text()
        assert "# Documentation Accuracy Report" in content
        assert "PASS" in content

    def test_includes_findings(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "FAIL",
            "threshold": "high",
            "blocking_findings": 1,
            "total_findings": 1,
            "by_severity": {"critical": 1},
        }
        comp = {
            "findings": [
                {
                    "severity": "critical",
                    "file": "doc.md",
                    "line": 10,
                    "description": "Bad symbol reference",
                }
            ]
        }
        report_path = tmp_path / "report.md"
        generate_markdown_report(None, None, comp, gate, report_path)

        content = report_path.read_text()
        assert "Bad symbol reference" in content
        assert "FAIL" in content

    def test_includes_did_not_run_reason(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "DID_NOT_RUN",
            "threshold": "high",
            "reason": "No source symbols found.",
            "blocking_findings": 0,
            "total_findings": 0,
            "by_severity": {},
        }
        report_path = tmp_path / "report.md"

        generate_markdown_report(None, None, None, gate, report_path)

        content = report_path.read_text()
        assert "DID_NOT_RUN" in content
        assert "No source symbols found." in content


class TestMain:
    def test_invalid_target(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nope"
        rc = main(["--target", str(nonexistent)])
        assert rc == 1

    def test_scan_docs_only_repo_is_inconclusive(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "```python\nMyWidget()\n```\n",
        )

        rc = main(["--target", str(tmp_path)])

        assert rc == 1
        output_dir = tmp_path / ".doc-accuracy"
        findings = json.loads(
            (output_dir / "compilability-findings.json").read_text(),
        )
        gate = json.loads((output_dir / "gate-result.json").read_text())
        assert findings["status"] == "DID_NOT_RUN"
        assert findings["findings"] == []
        assert gate["verdict"] == "DID_NOT_RUN"
        assert gate["total_findings"] == 0

    def test_scan_with_unresolved_symbol_fails(self, tmp_path: Path) -> None:
        subprocess.run(
            ["git", "init", str(tmp_path)],
            check=True,
            capture_output=True,
        )
        (tmp_path / "main.py").write_text(
            "def ExistingWidget():\n    pass\n",
        )
        (tmp_path / "README.md").write_text(
            "```python\nMyWidget()\n```\n",
        )

        rc = main(["--target", str(tmp_path)])

        assert rc == 10
        gate = json.loads(
            (tmp_path / ".doc-accuracy" / "gate-result.json").read_text(),
        )
        assert gate["verdict"] == "FAIL"
        assert gate["blocking_findings"] == 1

    def test_markdown_format(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Test\n")
        rc = main(["--target", str(tmp_path), "--format", "markdown"])
        assert rc == 1
        report = tmp_path / ".doc-accuracy" / "report.md"
        assert report.exists()
        assert "Documentation Accuracy Report" in report.read_text()
        assert "DID_NOT_RUN" in report.read_text()

    def test_summary_format(self, tmp_path: Path, capsys) -> None:
        rc = main(["--target", str(tmp_path), "--format", "summary"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Gate: DID_NOT_RUN" in captured.out
        assert "No source symbols found" in captured.out

    def test_json_format_emits_did_not_run_payload(self, tmp_path: Path, capsys) -> None:
        rc = main(["--target", str(tmp_path), "--format", "json"])
        assert rc == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["gate_result"]["verdict"] == "DID_NOT_RUN"
        assert payload["compilability_data"]["status"] == "DID_NOT_RUN"

    def test_json_format_emits_fail_payload(self, tmp_path: Path, capsys) -> None:
        subprocess.run(
            ["git", "init", str(tmp_path)],
            check=True,
            capture_output=True,
        )
        (tmp_path / "main.py").write_text(
            "def ExistingWidget():\n    pass\n",
        )
        (tmp_path / "README.md").write_text(
            "```python\nMyWidget()\n```\n",
        )

        rc = main(["--target", str(tmp_path), "--format", "json"])
        assert rc == 10
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["gate_result"]["verdict"] == "FAIL"
        assert payload["gate_result"]["blocking_findings"] == 1

    def test_json_format_emits_pass_payload(self, tmp_path: Path, capsys) -> None:
        subprocess.run(
            ["git", "init", str(tmp_path)],
            check=True,
            capture_output=True,
        )
        (tmp_path / "main.py").write_text(
            "def ExistingWidget():\n    pass\n",
        )
        (tmp_path / "README.md").write_text(
            "```python\nExistingWidget()\n```\n",
        )

        rc = main(["--target", str(tmp_path), "--format", "json"])
        assert rc == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["gate_result"]["verdict"] == "PASS"
        assert payload["gate_result"]["blocking_findings"] == 0

    @staticmethod
    def _csharp_repo(tmp_path: Path, body: str) -> None:
        subprocess.run(
            ["git", "init", str(tmp_path)],
            check=True,
            capture_output=True,
        )
        (tmp_path / "Widget.cs").write_text(
            "namespace Demo;\npublic class RealWidget\n{\n}\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            f"```csharp\n{body}\n```\n",
            encoding="utf-8",
        )

    def test_preprocessor_symbol_passes_gate(self, tmp_path: Path, capsys) -> None:
        """Issue #7453: '#if NETFRAMEWORK' must not fail the gate."""
        self._csharp_repo(
            tmp_path,
            "#if NETFRAMEWORK\nvar w = new RealWidget();\n#elif NET472\n#endif",
        )

        rc = main(["--target", str(tmp_path), "--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["gate_result"]["verdict"] == "PASS"
        assert payload["gate_result"]["blocking_findings"] == 0

    def test_unknown_type_beside_directive_still_fails_gate(self, tmp_path: Path, capsys) -> None:
        """Control: the same block with a phantom type is still checked."""
        self._csharp_repo(
            tmp_path,
            "#if NETFRAMEWORK\nvar w = new FakeWidget();\n#endif",
        )

        rc = main(["--target", str(tmp_path), "--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert rc == 10
        assert payload["gate_result"]["blocking_findings"] == 1
        symbols = [f["evidence"]["symbol"] for f in payload["compilability_data"]["findings"]]
        assert symbols == ["FakeWidget"]

    @staticmethod
    def _csharp_attribute_repo(tmp_path: Path, body: str) -> None:
        TestMain._csharp_repo(tmp_path, body)
        (tmp_path / "Marker.cs").write_text(
            "namespace Demo;\npublic class Marker : Attribute\n{\n"
            "    public Marker(string symbol) { }\n"
            "    public string Label { get; set; }\n}\n",
            encoding="utf-8",
        )

    def test_names_in_strings_and_attribute_arguments_pass_gate(
        self, tmp_path: Path, capsys
    ) -> None:
        """Names that sit only in literals or attribute arguments are data."""
        self._csharp_attribute_repo(
            tmp_path,
            "public class Demo\n{\n"
            '    [Marker("DEBUG", Label = "MadeUpLabel")]\n'
            "    public void Run()\n    {\n"
            '        var w = new RealWidget();\n        var s = "Hello WidgetFactory";\n'
            "    }\n}",
        )

        rc = main(["--target", str(tmp_path), "--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["compilability_data"]["findings"] == []
        assert rc == 0
        assert payload["gate_result"]["verdict"] == "PASS"

    def test_unknown_type_beside_string_and_attribute_still_fails_gate(
        self, tmp_path: Path, capsys
    ) -> None:
        """Control: a made-up type in real code in the same block still fails."""
        self._csharp_attribute_repo(
            tmp_path,
            "public class Demo\n{\n"
            '    [Marker("DEBUG", Label = "MadeUpLabel")]\n'
            "    public void Run()\n    {\n"
            '        var w = new FakeWidget();\n        var s = "Hello WidgetFactory";\n'
            "    }\n}",
        )

        rc = main(["--target", str(tmp_path), "--format", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert rc == 10
        assert payload["gate_result"]["blocking_findings"] == 1
        symbols = [f["evidence"]["symbol"] for f in payload["compilability_data"]["findings"]]
        assert symbols == ["FakeWidget"]

    def test_custom_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "custom-output"
        rc = main(
            [
                "--target",
                str(tmp_path),
                "--output-dir",
                str(out),
            ]
        )
        assert rc == 1
        assert (out / "gate-result.json").exists()

    def test_phases_selection(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("# Hi\n")
        rc = main(["--target", str(tmp_path), "--phases", "1"])
        assert rc == 0
        assert (tmp_path / ".doc-accuracy" / "assessment.json").exists()
        # claims.json should not exist when only phase 1 runs
        assert not (tmp_path / ".doc-accuracy" / "claims.json").exists()


class TestGateFormatDropsTheSymbolIndex:
    """`--format gate` exists so `/review` does not pay for the symbol index.

    `source_symbols` is the whole tracked-source index, built even for a
    diff-scoped run because claim checking needs it. Measured on this
    repository with `--diff-base origin/main`: 8,561,547 bytes of JSON, of
    which source_symbols is 8,456,923 (98.8%, 36,975 entries), against 43,513
    bytes of documentation_files. `/review` reads only `gate_result.verdict`
    and `assessment.documentation_files`, and a payload that large is liable to
    be truncated in transit, which turns a completed scan into a parse failure.
    """

    def _repo(self, tmp_path: Path) -> Path:
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        (tmp_path / "main.py").write_text("def ExistingWidget():\n    pass\n")
        (tmp_path / "README.md").write_text("```python\nExistingWidget()\n```\n")
        return tmp_path

    def test_gate_omits_source_symbols(self, tmp_path: Path, capsys) -> None:
        rc = main(["--target", str(self._repo(tmp_path)), "--format", "gate"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert "source_symbols" not in payload["assessment"]

    def test_gate_keeps_what_review_consumes(self, tmp_path: Path, capsys) -> None:
        """The two fields the adapter reads must survive the projection."""
        rc = main(["--target", str(self._repo(tmp_path)), "--format", "gate"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["gate_result"]["verdict"] == "PASS"
        assert payload["assessment"]["documentation_files"]

    def test_gate_verdict_matches_json_verdict(self, tmp_path: Path, capsys) -> None:
        """Dropping the index must not change the gate outcome."""
        repo = self._repo(tmp_path)
        assert main(["--target", str(repo), "--format", "json"]) == 0
        full = json.loads(capsys.readouterr().out)
        assert main(["--target", str(repo), "--format", "gate"]) == 0
        gate = json.loads(capsys.readouterr().out)
        assert gate["gate_result"] == full["gate_result"]
        assert (
            gate["assessment"]["documentation_files"] == full["assessment"]["documentation_files"]
        )

    def test_json_still_carries_the_symbol_index(self, tmp_path: Path, capsys) -> None:
        """Negative control: the full report is unchanged for other callers."""
        rc = main(["--target", str(self._repo(tmp_path)), "--format", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert "source_symbols" in payload["assessment"]


class TestDeletedDocsLeaveChangedFiles:
    """A deleted doc is not in changed_files, so the review adapter can PASS.

    Before the fix a branch that deleted one Markdown file and edited another
    listed both in ``changed_files``. Only the edited one can be inventoried,
    so ``adapt_local_axis_verdict`` read the clean run as a partial inventory
    and returned UNKNOWN, which blocks the /review PASS marker.
    """

    @staticmethod
    def _branch_that_deletes_and_edits(tmp_path: Path) -> Path:
        repo = _git_repo(tmp_path / "repo")
        (repo / "kept.md").write_text("# Kept\n", encoding="utf-8")
        (repo / "gone.md").write_text("# Gone\n", encoding="utf-8")
        (repo / "main.py").write_text("def foo():\n    pass\n", encoding="utf-8")
        _commit_all(repo, "base")
        (repo / "gone.md").unlink()
        (repo / "kept.md").write_text("# Kept, edited\n", encoding="utf-8")
        _commit_all(repo, "delete one doc, edit another")
        return repo

    def test_changed_files_omits_deleted_path(self, tmp_path: Path) -> None:
        repo = self._branch_that_deletes_and_edits(tmp_path)

        changed = _get_changed_files("HEAD~1", repo)

        assert changed == {"kept.md"}
