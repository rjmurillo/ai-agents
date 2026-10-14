#!/usr/bin/env python3
"""The `--write` post-condition: a repair never turns a balanced file unclosed.

Issue #5351. A fence carrying an info string inside an open block is read as a
mistaken closer, and a raw HTML block hides the next fence from CommonMark but
not from this scanner. On `.serena/memories/prompting/` a tracked file that
combines the two, `--write` inserted a closer and appended another at EOF. The
appended one is a fresh opener, so a balanced file came out unclosed.

Narrowing the mistaken-closer divergence does not close it: with the divergence
removed outright the same file is still grown by one fence, because the scanner
reads the fence after `</example>` as an opener. So the guard is a
post-condition on the written result, judged by the CommonMark reference
parser, and it refuses the write instead of patching either shape.

`repair_markdown_fences` is left unchanged on purpose. The known-corruption
pins measure what the repair does, and the guard sits in front of the write.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script
from commonmark_fence_cases import CASES as FENCE_CASES

# Same directory, but pytest's rootdir-based import does not put it on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported as a MODULE, not by name, so pytest collects the class once.
import test_fix_fences_contracts as contracts
import test_fix_fences_known_corruptions as corruptions

_has_unclosed_fence = contracts._has_unclosed_fence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / ".claude/skills/fix-markdown-fences/scripts/fix_fences.py"

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
main = mod.main

# Balanced for CommonMark: the `</example>` line starts an HTML block that
# swallows the last fence. The scanner reads that fence as an opener.
BALANCED_NESTED = "```markdown\n<example>\n```json\n{}\n```\n</example>\n```\n\nafter\n"

# A mistaken closer on a document that stays balanced. The repair rewrites
# the middle and the result is still balanced, so it must still be written.
MIDDLE_REWRITE = "```python\nx = 1\n```python\ny = 2\n```\n"

# A genuine unclosed block at EOF.
GENUINE_UNCLOSED = "text\n\n```python\nx = 1\n"

# Three backticks inside four are literal text and need no repair.
LENGTH_RULE = "````markdown\n```python\nx = 1\n```\n````\n"

TRACKED = Path(".serena/memories/prompting/prompt-engineering-merge-conflict-analysis.md")


def _write(tmp_path: Path, text: str, name: str = "doc.md") -> Path:
    target = tmp_path / name
    target.write_bytes(text.encode("utf-8"))
    return target


class TestTheShapeIsReal:
    """The inputs below are what they claim, judged by the reference parser."""

    def test_the_reproducer_is_balanced_and_the_repair_breaks_it(self) -> None:
        assert not _has_unclosed_fence(BALANCED_NESTED)
        assert _has_unclosed_fence(mod.repair_markdown_fences(BALANCED_NESTED))

    def test_the_tracked_file_is_present_and_balanced(self) -> None:
        """Without this, deleting the file makes the refusal test vacuous."""
        path = PROJECT_ROOT / TRACKED
        assert path.is_file(), f"{path} is gone; the real-file test below proves nothing"
        assert not _has_unclosed_fence(path.read_text(encoding="utf-8"))

    def test_the_repair_still_breaks_the_tracked_file(self) -> None:
        """Pins that the guard, not a scanner change, is what protects it."""
        text = (PROJECT_ROOT / TRACKED).read_text(encoding="utf-8")
        assert _has_unclosed_fence(mod.repair_markdown_fences(text))


class TestRefusal:
    def test_write_refuses_and_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write(tmp_path, BALANCED_NESTED)
        before = target.read_bytes()

        assert main([str(target), "--write"]) == 1

        assert target.read_bytes() == before
        out = capsys.readouterr().out
        assert "refused" in out.lower()
        assert str(target) in out

    def test_the_real_tracked_file_is_refused_and_left_untouched(self, tmp_path: Path) -> None:
        copy = _write(tmp_path, (PROJECT_ROOT / TRACKED).read_text(encoding="utf-8"))
        before = copy.read_bytes()

        assert main([str(copy), "--write"]) == 1

        assert copy.read_bytes() == before

    def test_report_mode_is_unchanged(self, tmp_path: Path) -> None:
        target = _write(tmp_path, BALANCED_NESTED)
        assert main([str(target)]) == 1
        assert target.read_bytes() == BALANCED_NESTED.encode("utf-8")

    def test_json_names_the_refused_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write(tmp_path, BALANCED_NESTED)

        assert main([str(target), "--write", "--json"]) == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["refused"] == [str(target)]
        assert payload["repaired"] == []

    def test_a_refusal_does_not_block_the_other_files(self, tmp_path: Path) -> None:
        refused = _write(tmp_path, BALANCED_NESTED, "a.md")
        fixed = _write(tmp_path, MIDDLE_REWRITE, "b.md")

        assert main([str(tmp_path), "--write"]) == 1

        assert refused.read_bytes() == BALANCED_NESTED.encode("utf-8")
        assert fixed.read_text(encoding="utf-8") == "```python\nx = 1\n```\n```python\ny = 2\n```\n"

    def test_crlf_and_bom_survive_a_refusal(self, tmp_path: Path) -> None:
        raw = b"\xef\xbb\xbf" + BALANCED_NESTED.replace("\n", "\r\n").encode("utf-8")
        target = tmp_path / "crlf.md"
        target.write_bytes(raw)

        assert main([str(target), "--write"]) == 1

        assert target.read_bytes() == raw

    def test_the_exit_code_holds_for_the_process(self, tmp_path: Path) -> None:
        target = _write(tmp_path, BALANCED_NESTED)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(target), "--write"],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )
        assert result.returncode == 1, result.stderr
        assert target.read_bytes() == BALANCED_NESTED.encode("utf-8")


class TestRepairsThatAreStillWritten:
    """Negative controls: the guard must not become a blanket refusal."""

    def test_a_genuine_malformed_closer_is_still_repaired(self, tmp_path: Path) -> None:
        target = _write(tmp_path, MIDDLE_REWRITE)
        assert _has_unclosed_fence(MIDDLE_REWRITE) is False

        assert main([str(target), "--write"]) == 0

        assert target.read_text(encoding="utf-8") != MIDDLE_REWRITE
        assert not _has_unclosed_fence(target.read_text(encoding="utf-8"))

    def test_a_genuine_unclosed_block_is_still_repaired(self, tmp_path: Path) -> None:
        target = _write(tmp_path, GENUINE_UNCLOSED)
        assert _has_unclosed_fence(GENUINE_UNCLOSED)

        assert main([str(target), "--write"]) == 0

        assert not _has_unclosed_fence(target.read_text(encoding="utf-8"))

    def test_the_length_rule_still_holds(self, tmp_path: Path) -> None:
        """Three backticks inside four stay literal. Asserted, not assumed."""
        target = _write(tmp_path, LENGTH_RULE)

        assert main([str(target), "--write"]) == 0

        assert target.read_text(encoding="utf-8") == LENGTH_RULE
        assert mod.find_fence_defects(LENGTH_RULE) == []

    def test_a_file_with_no_defect_is_not_a_refusal(self, tmp_path: Path) -> None:
        target = _write(tmp_path, "```python\nx\n```\n")
        assert main([str(target), "--write"]) == 0


class TestSetextUnderAListItemIsRefused:
    """Issue #5347: `--write` never grows a balanced setext-under-item file.

    The repair FUNCTION still appends a closer to six of the nine shapes held
    in `TestSetextUnderAListItemIsDestructive`, and that class pins it. This
    class drives `main(argv)` and asserts what the process does: it refuses
    each of those six, leaves the bytes alone, and exits 1.
    """

    SHAPES = corruptions.TestSetextUnderAListItemIsDestructive.SHAPES

    #: Balanced going in, unclosed coming out of the repair function.
    REFUSED = (
        "trailing dedent",
        "body then dedent",
        "dedent then prose",
        "ordered marker",
        "single equals",
        "nested item",
    )
    #: The scanner reads no defect, so there is nothing to write.
    UNTOUCHED = ("fence closed in item", "no lazy line")
    #: Genuinely unclosed input: the repair is correct and must be written.
    REPAIRED = ("no trailing dedent",)

    def test_the_three_groups_partition_the_nine_shapes(self) -> None:
        """Held as data, so emptying a group cannot disarm the tests below."""
        groups = self.REFUSED + self.UNTOUCHED + self.REPAIRED
        assert sorted(groups) == sorted(self.SHAPES)
        assert (len(self.REFUSED), len(self.UNTOUCHED), len(self.REPAIRED)) == (6, 2, 1)

    @pytest.mark.parametrize("name", REFUSED)
    def test_each_refused_shape_is_balanced_and_its_repair_is_not(self, name: str) -> None:
        """Judged by the reference parser, so the refusal below is not vacuous."""
        text = self.SHAPES[name]
        assert not _has_unclosed_fence(text)
        assert _has_unclosed_fence(mod.repair_markdown_fences(text))

    @pytest.mark.parametrize("name", REFUSED)
    def test_write_refuses_leaves_the_bytes_and_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
    ) -> None:
        target = _write(tmp_path, self.SHAPES[name])
        before = target.read_bytes()

        assert main([str(target), "--write", "--json"]) == 1

        assert target.read_bytes() == before
        payload = json.loads(capsys.readouterr().out)
        assert payload["refused"] == [str(target)]
        assert payload["repaired"] == []

    def test_the_smallest_shape_is_refused_by_the_process(self, tmp_path: Path) -> None:
        target = _write(tmp_path, self.SHAPES["trailing dedent"])
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(target), "--write"],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )
        assert result.returncode == 1, result.stderr
        assert "balanced file into an unclosed one" in result.stdout
        assert target.read_bytes() == self.SHAPES["trailing dedent"].encode("utf-8")

    @pytest.mark.parametrize("name", UNTOUCHED)
    def test_a_shape_with_no_defect_exits_zero_unchanged(self, tmp_path: Path, name: str) -> None:
        target = _write(tmp_path, self.SHAPES[name])

        assert main([str(target), "--write"]) == 0

        assert target.read_bytes() == self.SHAPES[name].encode("utf-8")

    @pytest.mark.parametrize("name", REPAIRED)
    def test_a_genuinely_unclosed_shape_is_still_repaired(self, tmp_path: Path, name: str) -> None:
        text = self.SHAPES[name]
        target = _write(tmp_path, text)
        assert _has_unclosed_fence(text)

        assert main([str(target), "--write"]) == 0

        assert not _has_unclosed_fence(target.read_text(encoding="utf-8"))


class TestBlockquoteInterruptingAParagraphIsRefused:
    """Issue #5348: `--write` never grows a balanced blockquote-interrupt file.

    The repair FUNCTION still appends a closer to five of the twelve shapes
    held in `TestBlockquoteInterruptingAParagraphIsDestructive`, and that
    class pins it. This class drives `main(argv)` and asserts what the process
    does: it refuses each of those five, leaves the bytes alone, and exits 1.
    A fence INSIDE a quote stays a miss, and the repair function writes
    nothing for it, so those shapes sit in the untouched group.
    """

    SHAPES = corruptions.TestBlockquoteInterruptingAParagraphIsDestructive.SHAPES

    #: Balanced going in, unclosed coming out of the repair function.
    REFUSED = (
        "interrupts, ordered 2",
        "interrupts, two quote lines",
        "quote at start, no paragraph",
        "interrupts, tilde fence",
        "interrupts, deeper indent",
    )
    #: The scanner reads no defect, so there is nothing to write.
    UNTOUCHED = (
        "interrupts, ordered 1",
        "interrupts, bullet",
        "interrupts, no lazy line",
        "fence inside the quote",
        "fence inside quote, unclosed",
        "quote then plain fence",
    )
    #: Genuinely unclosed input: the repair is correct and must be written.
    REPAIRED = ("no quote at all",)

    def test_the_three_groups_partition_the_twelve_shapes(self) -> None:
        """Held as data, so emptying a group cannot disarm the tests below."""
        groups = self.REFUSED + self.UNTOUCHED + self.REPAIRED
        assert sorted(groups) == sorted(self.SHAPES)
        assert (len(self.REFUSED), len(self.UNTOUCHED), len(self.REPAIRED)) == (5, 6, 1)

    @pytest.mark.parametrize("name", REFUSED)
    def test_each_refused_shape_is_balanced_and_its_repair_is_not(self, name: str) -> None:
        """Judged by the reference parser, so the refusal below is not vacuous."""
        text = self.SHAPES[name]
        assert not _has_unclosed_fence(text)
        assert _has_unclosed_fence(mod.repair_markdown_fences(text))

    @pytest.mark.parametrize("name", REFUSED)
    def test_write_refuses_leaves_the_bytes_and_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
    ) -> None:
        target = _write(tmp_path, self.SHAPES[name])
        before = target.read_bytes()

        assert main([str(target), "--write", "--json"]) == 1

        assert target.read_bytes() == before
        payload = json.loads(capsys.readouterr().out)
        assert payload["refused"] == [str(target)]
        assert payload["repaired"] == []

    def test_the_smallest_shape_is_refused_by_the_process(self, tmp_path: Path) -> None:
        text = self.SHAPES["interrupts, ordered 2"]
        target = _write(tmp_path, text)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(target), "--write"],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )
        assert result.returncode == 1, result.stderr
        assert "balanced file into an unclosed one" in result.stdout
        assert target.read_bytes() == text.encode("utf-8")

    @pytest.mark.parametrize("name", UNTOUCHED)
    def test_a_shape_with_no_defect_exits_zero_unchanged(self, tmp_path: Path, name: str) -> None:
        target = _write(tmp_path, self.SHAPES[name])

        assert main([str(target), "--write"]) == 0

        assert target.read_bytes() == self.SHAPES[name].encode("utf-8")

    @pytest.mark.parametrize("name", REPAIRED)
    def test_a_genuinely_unclosed_shape_is_still_repaired(self, tmp_path: Path, name: str) -> None:
        text = self.SHAPES[name]
        target = _write(tmp_path, text)
        assert _has_unclosed_fence(text)

        assert main([str(target), "--write"]) == 0

        assert not _has_unclosed_fence(target.read_text(encoding="utf-8"))


class TestWithoutTheReferenceParser:
    """The skill is vendored; `markdown-it-py` is optional there."""

    @pytest.fixture
    def no_reference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "_load_reference", lambda: None)

    @pytest.mark.usefixtures("no_reference")
    def test_write_proceeds_and_says_the_check_was_skipped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write(tmp_path, MIDDLE_REWRITE)

        assert main([str(target), "--write"]) == 0

        assert target.read_text(encoding="utf-8") != MIDDLE_REWRITE
        err = capsys.readouterr().err
        assert "markdown-it-py" in err
        assert "skipped" in err

    @pytest.mark.usefixtures("no_reference")
    def test_report_mode_stays_silent_about_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write(tmp_path, MIDDLE_REWRITE)

        assert main([str(target)]) == 1

        assert capsys.readouterr().err == ""

    def test_the_loader_returns_none_when_the_import_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "markdown_it", None)
        assert mod._load_reference() is None


class TestThePredicate:
    """`leaves_fence_open` agrees with the independent test-side predicate."""

    def test_it_agrees_on_every_curated_case(self) -> None:
        reference = mod._load_reference()
        assert reference is not None
        disagreements = [
            name
            for name, text in FENCE_CASES.items()
            if mod.leaves_fence_open(reference, text) != _has_unclosed_fence(text)
        ]
        assert disagreements == []

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("", False),
            ("plain\n", False),
            ("```\ncode\n```\n", False),
            ("```\ncode\n", True),
            ("```\ncode", True),
            ("- ```\n  code\n", True),
            ("~~~\ncode\n", True),
            ("```\n", True),
        ],
    )
    def test_known_shapes(self, text: str, expected: bool) -> None:
        reference = mod._load_reference()
        assert mod.leaves_fence_open(reference, text) is expected

    @pytest.mark.parametrize(
        ("before", "after", "safe"),
        [
            ("```\nx\n```\n", "```\nx\n```\n```\n", False),
            ("```\nx\n", "```\nx\n```\n", True),
            ("```\nx\n", "```\nx\n", True),
            ("a\n", "a\n", True),
            ("```\nx\n```\n", "```\nx\n```\n", True),
        ],
    )
    def test_only_balanced_to_unclosed_is_unsafe(self, before: str, after: str, safe: bool) -> None:
        reference = mod._load_reference()
        assert mod.repair_is_safe(reference, before, after) is safe

    def test_no_reference_means_safe(self) -> None:
        assert mod.repair_is_safe(None, "```\nx\n```\n", "```\nx\n```\n```\n") is True
