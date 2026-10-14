#!/usr/bin/env python3
"""The raw HTML write guard: `--write` never edits a file with a fence in HTML.

Issue #5346. A raw HTML block hides the fences inside it from CommonMark, so
the document is balanced, but the scanner reads them as fences and `--write`
appends a closer. The scanner does not model HTML blocks, so the write is
refused instead. The check is `wraps_fence_in_html`; it needs no third-party
package, which matters because vendored trees do not carry `markdown-it-py`.

The oracle for every claim here is `markdown-it-py`. The predicate under test
is never used to build its own expected value.
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

# Same directory, but pytest's rootdir-based import does not put it on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported as MODULES, not by name, so pytest collects each class once.
import test_fix_fences_contracts as contracts
import test_fix_fences_known_corruptions as known

_has_unclosed_fence = contracts._has_unclosed_fence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / ".claude/skills/fix-markdown-fences/scripts/fix_fences.py"
SPEC_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "commonmark-spec-0.31.2.json"

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
main = mod.main
# The guard lives beside the script and is importable once the script has loaded.
import fence_write_guard as guard


def wraps(text: str) -> bool:
    return guard.wraps_fence_in_html(text, mod.fence_match)


_RAW_HTML = known.TestRawHtmlIsADestructiveGap()
SHAPES = _RAW_HTML._shapes()
HTML_REASON = "raw HTML block"

# An HTML banner that a blank line closes, then a real malformed closer. The
# block never touches a fence, so the repair is a genuine one.
BANNER_THEN_DEFECT = '<div align="center">\n<img src="a.png">\n</div>\n\n```python\nx = 1\n'

# A fence shown as an example inside a fenced block, then an unclosed block.
HTML_INSIDE_A_FENCE = "````html\n<div>\n```\n````\n\n```python\nx = 1\n"


def _write(tmp_path: Path, text: str, name: str = "doc.md") -> Path:
    target = tmp_path / name
    target.write_bytes(text.encode("utf-8"))
    return target


def _oracle_wraps(text: str) -> bool:
    """True when the reference parser reads a fence-looking line as HTML."""
    from hook_utilities.commonmark_containers import fence_match

    reference = mod._load_reference()
    assert reference is not None
    return any(
        fence_match(line) is not None
        for token in reference.parse(text)
        if token.type == "html_block"
        for line in token.content.split("\n")
    )


class TestTheShapesAreReal:
    """Without these the refusal tests below could pass on the wrong input."""

    def test_there_are_twenty_shapes(self) -> None:
        assert len(SHAPES) == 20

    @pytest.mark.parametrize("text", SHAPES)
    def test_the_reference_parser_reads_the_shape_as_balanced(self, text: str) -> None:
        assert not _has_unclosed_fence(text)

    @pytest.mark.parametrize("text", SHAPES)
    def test_the_repair_would_edit_it(self, text: str) -> None:
        assert mod.repair_markdown_fences(text) != text


class TestEveryShapeIsRefused:
    @pytest.mark.parametrize("text", SHAPES)
    def test_write_refuses_and_exits_one(
        self, text: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write(tmp_path, text)

        assert main([str(target), "--write"]) == 1

        assert target.read_bytes() == text.encode("utf-8")
        out = capsys.readouterr().out
        assert f"Refused {target}" in out
        assert HTML_REASON in out

    @pytest.mark.parametrize("text", SHAPES)
    def test_the_predicate_agrees_with_the_reference_parser(self, text: str) -> None:
        assert wraps(text) is _oracle_wraps(text) is True

    def test_the_exit_code_holds_for_the_process(self, tmp_path: Path) -> None:
        target = _write(tmp_path, "<div>\n```\nAfter.\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(target), "--write"],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )
        assert result.returncode == 1, result.stderr
        assert target.read_bytes() == b"<div>\n```\nAfter.\n"
        assert HTML_REASON in result.stdout

    def test_json_names_the_file_and_the_reason(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write(tmp_path, "<pre>\n```\nAfter.\n")

        assert main([str(target), "--write", "--json"]) == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["refused"] == [str(target)]
        assert HTML_REASON in payload["refusal_reasons"][str(target)]
        assert payload["repaired"] == []

    def test_report_mode_is_unchanged(self, tmp_path: Path) -> None:
        text = "<div>\n```\nAfter.\n"
        target = _write(tmp_path, text)
        assert main([str(target)]) == 1
        assert target.read_bytes() == text.encode("utf-8")

    def test_crlf_and_bom_survive_a_refusal(self, tmp_path: Path) -> None:
        raw = b"\xef\xbb\xbf<div>\r\n```\r\nAfter.\r\n"
        target = tmp_path / "crlf.md"
        target.write_bytes(raw)

        assert main([str(target), "--write"]) == 1

        assert target.read_bytes() == raw

    def test_a_refusal_does_not_block_the_other_files(self, tmp_path: Path) -> None:
        refused = _write(tmp_path, "<div>\n```\nAfter.\n", "a.md")
        fixed = _write(tmp_path, "```python\nx = 1\n", "b.md")

        assert main([str(tmp_path), "--write"]) == 1

        assert refused.read_bytes() == b"<div>\n```\nAfter.\n"
        assert fixed.read_text(encoding="utf-8") == "```python\nx = 1\n```\n"


class TestTheGuardNeedsNoReferenceParser:
    """The skill is vendored; `markdown-it-py` is optional there."""

    @pytest.fixture
    def no_reference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "_load_reference", lambda: None)

    @pytest.mark.usefixtures("no_reference")
    @pytest.mark.parametrize("text", SHAPES)
    def test_every_shape_is_still_refused(self, text: str, tmp_path: Path) -> None:
        target = _write(tmp_path, text)

        assert main([str(target), "--write"]) == 1

        assert target.read_bytes() == text.encode("utf-8")


class TestRepairsThatAreStillWritten:
    """Negative controls: the guard must not become a blanket HTML refusal."""

    @pytest.mark.parametrize("text", [BANNER_THEN_DEFECT, HTML_INSIDE_A_FENCE])
    def test_html_that_never_wraps_a_fence_does_not_block_a_repair(
        self, text: str, tmp_path: Path
    ) -> None:
        target = _write(tmp_path, text)
        assert not wraps(text)

        assert main([str(target), "--write"]) == 0

        assert target.read_text(encoding="utf-8") != text
        assert not _has_unclosed_fence(target.read_text(encoding="utf-8"))

    def test_a_defect_free_file_with_html_is_not_a_refusal(self, tmp_path: Path) -> None:
        target = _write(tmp_path, "<div>\n```\nAfter.\n```\n")
        assert main([str(target), "--write"]) == 0


class TestThePredicate:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # One start condition each, unterminated so the fence is inside.
            ("<script>\n```\n", True),
            ("<PRE>\n```\n", True),
            ("<style type='x'>\n```\n", True),
            ("<textarea>\n```\n", True),
            ("<!-- c\n```\n", True),
            ("<?php\n```\n", True),
            ("<!DOCTYPE\n```\n", True),
            ("<![CDATA[\n```\n", True),
            ("<div>\n~~~\n", True),
            ("</div>\n```\n", True),
            ('<x-tag a="b">\n```\n', True),
            ("<br/>\n```\n", True),
            ("   <div>\n```\n", True),
            ("<div>\ntext\n```\n", True),
            # An end marker closes conditions 1 to 5; a blank line closes 6 and 7.
            ("<pre>x</pre>\n```\n", False),
            ("<script>\n</script>\n```\n", False),
            ("<!-- c -->\n```\n", False),
            ("<?php ?>\n```\n", False),
            ("<!DOCTYPE html>\n```\n", False),
            ("<![CDATA[x]]>\n```\n", False),
            ("<div>\n\n```\n", False),
            ("<x-tag>\n\n```\n", False),
            # Not an HTML block start.
            ("    <div>\n```\n", False),
            ("< div>\n```\n", False),
            ("a <span>b</span>\n```\n", False),
            ("<notclosed\n```\n", False),
            ("<1tag>\n```\n", False),
            ("text <div>\n```\n", False),
            # Fenced code is skipped, so HTML shown as an example is not HTML.
            ("```html\n<div>\n```\n\n```\n", False),
            ("~~~\n<div>\n~~~\n", False),
            # A longer fence is not closed by a shorter one.
            ("````\n```\n<div>\n````\n```\n", False),
            # No fence anywhere.
            ("<div>\ntext\n", False),
            ("", False),
        ],
    )
    def test_known_shapes(self, text: str, expected: bool) -> None:
        assert wraps(text) is expected

    @pytest.mark.parametrize("sep", ["\r\n", "\r", "\n"])
    def test_every_line_terminator_is_split(self, sep: str) -> None:
        assert wraps(f"<div>{sep}```{sep}After.{sep}") is True
        assert wraps(f"<div>{sep}{sep}```{sep}After.{sep}") is False

    def test_a_form_feed_is_not_a_line_break(self) -> None:
        """`str.splitlines` would split here and shift the blank-line test."""
        assert wraps("<div>\x0c\n```\n") is True


class TestAgreementWithTheReferenceParser:
    """Measured, not assumed: the predicate and the oracle see the same files."""

    def test_the_spec_fixture_is_present(self) -> None:
        assert len(json.loads(SPEC_FIXTURE.read_text(encoding="utf-8"))) > 600

    def test_it_agrees_on_every_commonmark_spec_example(self) -> None:
        examples = json.loads(SPEC_FIXTURE.read_text(encoding="utf-8"))
        disagreements = [
            ex["example"]
            for ex in examples
            if wraps(ex["markdown"]) != _oracle_wraps(ex["markdown"])
        ]
        assert disagreements == []

    def test_it_agrees_on_the_curated_fence_cases(self) -> None:
        from commonmark_fence_cases import CASES

        disagreements = [name for name, text in CASES.items() if wraps(text) != _oracle_wraps(text)]
        assert disagreements == []

    @pytest.mark.parametrize("text", ["- item\n\n    <div>\n    ```\n", "> <div>\n> ```\n"])
    def test_the_known_blind_spot_is_a_block_inside_a_container(self, text: str) -> None:
        """Documented, not fixed: HTML in a list item or blockquote is not seen.

        If this starts failing, the predicate learned containers; delete the
        "inside a list item or blockquote" caveat in SKILL.md with it.
        """
        assert _oracle_wraps(text) is True
        assert wraps(text) is False
