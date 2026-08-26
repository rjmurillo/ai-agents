#!/usr/bin/env python3
"""Tests for the fix-markdown-fences deterministic fence scanner.

Covers the three defects that made the previous hand-run process necessary:
nested container fences must survive untouched, line endings and the trailing
newline must be preserved, and tilde fences must be tracked. Also asserts the
exit-code contract SKILL.md documents (claude-agents MUST-7).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
repair_markdown_fences = mod.repair_markdown_fences
find_fence_defects = mod.find_fence_defects
iter_markdown_files = mod.iter_markdown_files
main = mod.main
MALFORMED_CLOSING = mod.MALFORMED_CLOSING
UNCLOSED_BLOCK = mod.UNCLOSED_BLOCK


def kinds(content: str) -> list[str]:
    return [d.kind for d in find_fence_defects(content)]


class TestCleanContent:
    """Content with no defect must round-trip byte for byte."""

    def test_valid_block_is_unchanged(self) -> None:
        content = "```python\nprint('hello')\n```\n"
        assert repair_markdown_fences(content) == content
        assert find_fence_defects(content) == []

    def test_prose_with_no_fences_is_unchanged(self) -> None:
        content = "# Title\nSome text\nMore text\n"
        assert repair_markdown_fences(content) == content
        assert kinds(content) == []

    def test_empty_content_is_unchanged(self) -> None:
        assert repair_markdown_fences("") == ""
        assert find_fence_defects("") == []

    def test_multiple_valid_blocks_are_unchanged(self) -> None:
        content = "```python\ncode\n```\n\n```bash\nscript\n```\n"
        assert repair_markdown_fences(content) == content

    def test_inline_code_run_does_not_open_a_block(self) -> None:
        # CommonMark: a backtick fence info string may not contain a backtick.
        content = "``` `not a fence` ```\ntext\n"
        assert kinds(content) == []


class TestMalformedClosing:
    """A closing fence carrying a language identifier is the core defect."""

    def test_defect_is_reported_with_line_and_kind(self) -> None:
        content = "```python\ncode1\n```python\ncode2\n```\n"
        defects = find_fence_defects(content)
        assert [(d.line, d.kind) for d in defects] == [(3, MALFORMED_CLOSING)]

    def test_repair_inserts_a_bare_closing_fence_above(self) -> None:
        content = "```python\ncode1\n```python\ncode2\n```\n"
        result = repair_markdown_fences(content)
        assert result.split("\n")[2] == "```"
        assert find_fence_defects(result) == []

    def test_repair_preserves_indentation(self) -> None:
        content = "  ```python\n  code\n  ```python\n  more\n  ```\n"
        result = repair_markdown_fences(content)
        assert result.split("\n")[2] == "  ```"

    def test_repair_is_idempotent(self) -> None:
        content = "```python\ncode1\n```python\ncode2\n```\n"
        once = repair_markdown_fences(content)
        assert repair_markdown_fences(once) == once

    def test_malformed_line_that_cannot_open_leaves_no_open_block(self) -> None:
        # A backtick fence carrying a backtick in its info string cannot open
        # a block. Keeping the stale opener desynced the state machine, so a
        # second --write injected a fence into an unrelated section.
        content = "```text\n``` `not a fence` ```\n```\n"
        once = repair_markdown_fences(content)
        assert repair_markdown_fences(once) == once
        assert find_fence_defects(once) == []


class TestByteFidelity:
    """A repair must not touch a byte it did not set out to change."""

    def test_crlf_survives_the_cli(self, tmp_path: Path) -> None:
        # read_text() does universal-newline translation, so the pure-function
        # test could pass while the shipped CLI rewrote every line ending.
        target = tmp_path / "crlf.md"
        target.write_bytes(b"```py\r\nx\r\n```py\r\ny\r\n```\r\n")
        assert main([str(target), "--write"]) == 0
        out = target.read_bytes()
        assert b"\r\n" in out
        assert out.count(b"\n") == out.count(b"\r\n")

    def test_cr_only_endings_survive_the_cli(self, tmp_path: Path) -> None:
        target = tmp_path / "cr.md"
        target.write_bytes(b"```py\rx\r```py\ry\r```\r")
        assert main([str(target), "--write"]) == 0
        assert b"\n" not in target.read_bytes()

    @pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\x0c", "\x85"])
    def test_unicode_line_separators_survive(self, tmp_path: Path, separator: str) -> None:
        # str.splitlines() splits on all of these and would delete them.
        target = tmp_path / "sep.md"
        target.write_text(f"```py\nx\n```py\ny\n```\n\nSee A{separator}B.\n", encoding="utf-8")
        assert main([str(target), "--write"]) == 0
        assert separator in target.read_text(encoding="utf-8")

    def test_utf8_bom_survives_a_repair(self, tmp_path: Path) -> None:
        target = tmp_path / "bom.md"
        target.write_bytes(b"\xef\xbb\xbf```py\nx\n```py\ny\n```\n")
        assert main([str(target), "--write"]) == 0
        assert target.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_bom_does_not_hide_a_first_line_fence(self, tmp_path: Path) -> None:
        target = tmp_path / "bom_clean.md"
        original = b"\xef\xbb\xbf```python\nx = 1\n```\n"
        target.write_bytes(original)
        assert main([str(target)]) == 0
        assert target.read_bytes() == original


class TestIndentedCodeBlocks:
    """CommonMark stops treating a marker as a fence at four spaces."""

    def test_lone_fence_in_an_indented_block_is_not_an_opener(self) -> None:
        assert find_fence_defects("Like this:\n\n    ```\n\nDone.\n") == []

    def test_write_leaves_such_a_file_byte_identical(self, tmp_path: Path) -> None:
        target = tmp_path / "indented.md"
        original = "Like this:\n\n    ```\n\nDone.\n"
        target.write_text(original, encoding="utf-8")
        assert main([str(target), "--write"]) == 0
        assert target.read_text(encoding="utf-8") == original

    def test_three_space_indent_is_still_a_fence(self) -> None:
        assert kinds("   ```py\nx\n") == [UNCLOSED_BLOCK]

    def test_tab_counts_as_four_spaces(self) -> None:
        assert find_fence_defects("\t```py\nx\n") == []


class TestNestedContainerFences:
    """Regression: the old parser inserted a stray fence into example blocks."""

    def test_three_backtick_example_inside_four_backtick_container(self) -> None:
        content = "````markdown\n```py\na\n```js\nb\n```\n````\n"
        assert find_fence_defects(content) == []
        assert repair_markdown_fences(content) == content

    def test_shorter_fence_cannot_close_a_longer_one(self) -> None:
        content = "````text\n```\nstill inside\n````\n"
        assert find_fence_defects(content) == []

    def test_tilde_fence_cannot_close_a_backtick_fence(self) -> None:
        content = "```py\n~~~\n```\n"
        assert find_fence_defects(content) == []


class TestUnclosedBlock:
    """A file ending mid-block gets a closing fence, not a mangled tail."""

    def test_defect_is_reported(self) -> None:
        assert kinds("```python\nunclosed") == [UNCLOSED_BLOCK]

    def test_repair_preserves_trailing_newline(self) -> None:
        assert repair_markdown_fences("```py\nx\n") == "```py\nx\n```\n"

    def test_repair_without_trailing_newline_adds_none(self) -> None:
        assert repair_markdown_fences("```py\nx") == "```py\nx\n```"

    def test_tilde_block_is_closed_with_tildes(self) -> None:
        assert repair_markdown_fences("~~~py\nx\n") == "~~~py\nx\n~~~\n"

    def test_crlf_endings_are_preserved(self) -> None:
        result = repair_markdown_fences("```py\r\nx\r\n")
        assert result == "```py\r\nx\r\n```\r\n"


class TestFileDiscovery:
    """Directory expansion honors the pattern and skips vendor trees."""

    def test_respects_pattern_filter(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("x\n", encoding="utf-8")
        (tmp_path / "b.txt").write_text("x\n", encoding="utf-8")
        found = iter_markdown_files([tmp_path], "*.md")
        assert [p.name for p in found] == ["a.md"]

    def test_recurses_into_subdirectories(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.md").write_text("x\n", encoding="utf-8")
        assert [p.name for p in iter_markdown_files([tmp_path], "*.md")] == ["deep.md"]

    def test_skips_vendor_and_vcs_trees(self, tmp_path: Path) -> None:
        for skipped in ("node_modules", ".git", ".venv", "__pycache__"):
            d = tmp_path / skipped
            d.mkdir()
            (d / "x.md").write_text("x\n", encoding="utf-8")
        assert iter_markdown_files([tmp_path], "*.md") == []

    def test_skips_a_directory_whose_name_matches_the_pattern(self, tmp_path: Path) -> None:
        (tmp_path / "adir.md").mkdir()
        assert iter_markdown_files([tmp_path], "*.md") == []
        assert main([str(tmp_path)]) == 0

    def test_named_file_is_used_directly(self, tmp_path: Path) -> None:
        f = tmp_path / "only.md"
        f.write_text("x\n", encoding="utf-8")
        assert iter_markdown_files([f], "*.md") == [f]


class TestExitCodes:
    """The contract SKILL.md documents: 0 clean, 1 findings, 2 config error."""

    def test_exit_zero_when_clean(self, tmp_path: Path) -> None:
        (tmp_path / "ok.md").write_text("```py\nx\n```\n", encoding="utf-8")
        assert main([str(tmp_path)]) == 0

    def test_exit_one_when_report_mode_finds_defects(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text("```py\nx\n```py\ny\n```\n", encoding="utf-8")
        assert main([str(tmp_path)]) == 1

    def test_report_mode_does_not_write(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.md"
        original = "```py\nx\n```py\ny\n```\n"
        bad.write_text(original, encoding="utf-8")
        main([str(tmp_path)])
        assert bad.read_text(encoding="utf-8") == original

    def test_exit_zero_after_write_repairs(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.md"
        bad.write_text("```py\nx\n```py\ny\n```\n", encoding="utf-8")
        assert main([str(tmp_path), "--write"]) == 0
        assert find_fence_defects(bad.read_text(encoding="utf-8")) == []

    def test_exit_two_when_path_missing(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "nope")]) == 2

    def test_exit_two_when_file_unreadable(self, tmp_path: Path) -> None:
        bad = tmp_path / "bin.md"
        bad.write_bytes(b"\xff\xfe\x00bad")
        assert main([str(bad)]) == 2

    def test_exit_two_when_write_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "bad.md"
        target.write_text("```py\nx\n```py\ny\n```\n", encoding="utf-8")

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(Path, "write_bytes", refuse)
        assert main([str(tmp_path), "--write"]) == 2
        assert "cannot write" in capsys.readouterr().err

    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_unknown_flag_exits_two(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--bogus"])
        assert exc.value.code == 2


class TestOutput:
    """Report formats the agent reads."""

    def test_clean_run_says_so(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / "ok.md").write_text("text\n", encoding="utf-8")
        main([str(tmp_path)])
        assert "No fence defects found" in capsys.readouterr().out

    def test_report_lines_carry_file_line_and_kind(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "bad.md").write_text("```py\nx\n```py\ny\n```\n", encoding="utf-8")
        main([str(tmp_path)])
        out = capsys.readouterr().out
        assert f"bad.md:3: {MALFORMED_CLOSING}" in out

    def test_json_output_is_machine_readable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = tmp_path / "bad.md"
        bad.write_text("```py\nx\n```py\ny\n```\n", encoding="utf-8")
        main([str(tmp_path), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["defect_count"] == 1
        assert payload["repaired"] == []
        assert payload["files"][str(bad)][0]["kind"] == MALFORMED_CLOSING
