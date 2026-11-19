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


# The repro from issue #7454: four tests, each disposing a fixture.
_XUNIT_SUITE = (
    "using System.IO;\nusing Xunit;\n\npublic sealed class SampleTests\n{\n"
    + "\n".join(_xunit_method(name) for name in "ABCD")
    + "}\n"
)

# The issue's documented enum: three members with XML doc comments.
_DOCUMENTED_ENUM = (
    "/// <summary>Kinds.</summary>\npublic enum Kind\n{\n"
    + "".join(
        f"    /// <summary>\n    /// {word}.\n    /// </summary>\n    {member},\n"
        for word, member in (("First", "A"), ("Second", "B"), ("Third", "C"))
    )
    + "}\n"
)

# Copy-pasted statements are still duplication once braces are ignored.
_COPY_PASTE = (
    "class C\n{\n    void M()\n    {\n" + "        Total += Price * Quantity;\n" * 6 + "    }\n}\n"
)


def test_xunit_suite_from_issue_scores_above_default_minimum() -> None:
    """The issue repro counts two imports and clears nonRedundancy min 8."""
    assessment = assess_content(Path("SampleTests.cs"), _XUNIT_SUITE)

    assert assessment.coupling.reasons[0] == "2 import/dependency statements"
    assert assessment.non_redundancy.value >= 8
    assert assessment.non_redundancy.confidence == 0.5


def test_xml_doc_comments_do_not_count_as_duplicates() -> None:
    """Repeated `/// <summary>` lines are comments, not copied knowledge."""
    score = assess_content(Path("Kind.cs"), _DOCUMENTED_ENUM).non_redundancy

    assert score.value == 10.0
    assert score.reasons[0].startswith("4/4 unique code lines")


def test_copy_pasted_statements_still_lower_the_score() -> None:
    """Negative control: real duplication still reads as duplication."""
    score = assess_content(Path("Copy.cs"), _COPY_PASTE).non_redundancy

    assert score.value < 7
    assert "High duplication detected" in score.reasons


@pytest.mark.parametrize("line", ["}", "{", "});", "],", ")", "{ }", "};"])
def test_bracket_only_lines_are_ignored(line: str) -> None:
    """Adding a bracket-only line never changes the score."""
    base = "class C\n{\n    int Total() { return 1; }\n"
    with_brackets = base + f"{line}\n" * 5

    assert (
        assess_content(Path("C.java"), with_brackets).non_redundancy.value
        == assess_content(Path("C.java"), base).non_redundancy.value
        == 10.0
    )


@pytest.mark.parametrize("line", ["} else {", "{ x }", "[Fact]", "return;"])
def test_lines_with_code_still_count(line: str) -> None:
    """Edge: brackets next to code or a word are code, so repeats count."""
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


def test_file_with_only_comments_and_brackets_has_no_code_lines() -> None:
    """Edge: nothing left to compare scores 10 and says why."""
    score = assess_content(Path("Empty.cs"), "// a\n// a\n{\n}\n").non_redundancy

    assert score.value == 10.0
    assert score.reasons == ["No code lines, no duplication"]


def test_untuned_language_ignores_brackets_and_stays_ungated() -> None:
    """Edge: an untuned language has no comment prefix and confidence 0.0."""
    score = assess_content(Path("m.rb"), "# a\n# a\nend\n}\n}\n").non_redundancy

    assert score.confidence == 0.0
    assert score.reasons[0].startswith("2/3 unique code lines")


def test_cli_passes_issue_repro_under_default_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The issue repro exits 0 in absolute mode with the built-in defaults."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "SampleTests.cs"
    target.write_text(_XUNIT_SUITE, encoding="utf-8")

    assert _mod.main(["--target", str(target), "--gate-mode", "absolute"]) == 0


def test_cli_still_fails_copy_paste_under_default_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Negative control: duplicated statements still exit 11."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "Copy.cs"
    target.write_text(_COPY_PASTE, encoding="utf-8")

    assert _mod.main(["--target", str(target), "--gate-mode", "absolute"]) == 11
    assert "Non-Redundancy" in capsys.readouterr().err
