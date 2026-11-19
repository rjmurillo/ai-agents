"""Non-redundancy ignores syntax that every member repeats (issue #7454)."""

import importlib.util
from pathlib import Path

import pytest

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


def _xunit_method(name: str) -> str:
    return (
        "    [Fact]\n"
        f"    public void {name}()\n"
        "    {\n"
        f"        using var stream{name} = new MemoryStream();\n"
        f"        Assert.Equal(0, stream{name}.Length);\n"
        "    }\n"
    )


def _xunit_suite(count: int) -> str:
    names = [f"Case{i}" for i in range(count)]
    return (
        "using System.IO;\nusing Xunit;\n\npublic sealed class SampleTests\n{\n"
        + "\n".join(_xunit_method(name) for name in names)
        + "}\n"
    )


# The repro from issue #7454: four tests, each disposing a fixture.
_XUNIT_SUITE = _xunit_suite(4)

# A rebuild of the issue's documented enum. The issue gave no source text, so
# this keeps its failure shape: repeated `/// <summary>` lines per member.
_DOCUMENTED_ENUM = (
    "/// <summary>Kinds.</summary>\npublic enum Kind\n{\n"
    + "".join(
        f"    /// <summary>\n    /// {word}.\n    /// </summary>\n    {member},\n"
        for word, member in (("First", "A"), ("Second", "B"), ("Third", "C"))
    )
    + "}\n"
)

# Copy-pasted statements are still duplication once syntax is ignored.
_COPY_PASTE = (
    "class C\n{\n    void M()\n    {\n" + "        Total += Price * Quantity;\n" * 6 + "    }\n}\n"
)


def test_xunit_suite_from_issue_scores_above_default_minimum() -> None:
    """The issue repro counts two imports and clears nonRedundancy min 8."""
    assessment = assess_content(Path("SampleTests.cs"), _XUNIT_SUITE)

    assert assessment.coupling.reasons[0] == "2 import/dependency statements"
    assert assessment.non_redundancy.value >= 8
    assert assessment.non_redundancy.confidence == 0.5


@pytest.mark.parametrize("count", [9, 20, 40])
def test_large_xunit_suite_is_not_penalized_for_repeated_fact(count: int) -> None:
    """A class with many `[Fact]` tests scores like a small one (was 7.9 at 9)."""
    score = assess_content(Path("SampleTests.cs"), _xunit_suite(count)).non_redundancy

    assert score.value == 10.0


def test_xml_doc_comments_do_not_count_as_duplicates() -> None:
    """Repeated `/// <summary>` lines are comments, not copied knowledge."""
    score = assess_content(Path("Kind.cs"), _DOCUMENTED_ENUM).non_redundancy

    assert score.value == 10.0
    assert score.reasons[0] == "4/4 unique lines (line comments and 2 syntax-only lines skipped)"


def test_copy_pasted_statements_still_lower_the_score() -> None:
    """Negative control: real duplication still reads as duplication."""
    score = assess_content(Path("Copy.cs"), _COPY_PASTE).non_redundancy

    assert score.value < 7
    assert "High duplication detected" in score.reasons


@pytest.mark.parametrize(
    "line",
    ["}", "{", "});", "],", ")", "{ }", "};", "@Override", "@Test", "[Fact]", "[TestMethod]"],
)
def test_syntax_only_lines_are_ignored(line: str) -> None:
    """Adding a bracket-only or bare attribute line never changes the score."""
    base = "class C\n{\n    int Total() { return 1; }\n"
    with_syntax = base + f"{line}\n" * 5

    assert (
        assess_content(Path("C.java"), with_syntax).non_redundancy.value
        == assess_content(Path("C.java"), base).non_redundancy.value
        == 10.0
    )


@pytest.mark.parametrize(
    "line",
    [
        "} else {",
        "{ x }",
        "return;",
        "[InlineData(1, 2)]",
        "@Test(expected = IOException.class)",
        "[Fact, Trait]",
        "@Override public int x;",
    ],
)
def test_lines_with_code_or_arguments_still_count(line: str) -> None:
    """Edge: brackets next to code, or an attribute with arguments, still count."""
    # Java scores with a line pattern, so the fragment need not parse.
    score = assess_content(Path("Edge.java"), f"{line}\n" * 4).non_redundancy

    assert score.value == 2.5


def test_python_hash_comments_are_ignored() -> None:
    """Comment prefixes come from the file's language."""
    source = "# note\n# note\n# note\ndef f():\n    return 1\n"

    assert assess_content(Path("m.py"), source).non_redundancy.value == 10.0


def test_hash_is_code_in_csharp() -> None:
    """A `#` line is a preprocessor directive in C#, not a comment."""
    source = "#region A\n#endregion\n#region A\n#endregion\nclass C { }\n"

    assert assess_content(Path("C.cs"), source).non_redundancy.value == 6.0


def test_file_with_only_comments_and_brackets_has_no_lines_to_compare() -> None:
    """Edge: nothing left to compare scores 10 and says why."""
    score = assess_content(Path("Empty.cs"), "// a\n// a\n{\n}\n").non_redundancy

    assert score.value == 10.0
    assert score.reasons == ["No lines left to compare, no duplication"]


def test_untuned_language_counts_comments_and_says_so() -> None:
    """Edge: an untuned language has no comment prefix, so `#` lines count."""
    score = assess_content(Path("m.rb"), "# a\n# a\nend\n}\n}\n").non_redundancy

    assert score.confidence == 0.0
    assert score.reasons[0] == "2/3 unique lines (2 syntax-only lines skipped)"


@pytest.mark.parametrize("count", [4, 20])
def test_cli_passes_xunit_suite_in_tests_dir_under_default_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    """The issue repro and a 20-test class exit 0 as test files in absolute mode."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "SampleTests.cs"
    target.parent.mkdir()
    target.write_text(_xunit_suite(count), encoding="utf-8")

    assert _mod.main(["--target", str(target), "--gate-mode", "absolute"]) == 0


def test_cli_passes_issue_repro_as_authored_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A .NET test project path such as Foo.Tests/ classifies as authored."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "Foo.Tests" / "SampleTests.cs"
    target.parent.mkdir()
    target.write_text(_XUNIT_SUITE, encoding="utf-8")

    assert _mod.classify_file_category(target) == "authored"
    assert _mod.main(["--target", str(target), "--gate-mode", "absolute"]) == 0


@pytest.mark.parametrize("subdir", ["", "tests"])
def test_cli_still_fails_copy_paste_under_default_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], subdir: str
) -> None:
    """Negative control: duplicated statements still exit 11, test file or not."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / subdir / "Copy.cs"
    target.parent.mkdir(exist_ok=True)
    target.write_text(_COPY_PASTE, encoding="utf-8")

    assert _mod.main(["--target", str(target), "--gate-mode", "absolute"]) == 11
    assert "Non-Redundancy" in capsys.readouterr().err
