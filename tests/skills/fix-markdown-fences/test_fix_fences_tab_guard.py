#!/usr/bin/env python3
"""The escaped-tab gap driven through `fix_fences --write`.

Issue #5349. A backslash in a single-line link destination escapes whatever
follows it here, and `_relative` expands tabs to four-column stops before the
grammar sees the line. So an escaped TAB is eaten differently at each label
length, and 9 of 11 lengths turn a balanced document into an unclosed one when
the repair function runs.

The write guard from issue #5351 already covers that: `--write` checks the
repaired text against `markdown-it-py` and refuses a file that goes in
balanced and would come out unclosed. This module drives the shape through
`main(argv)` and a subprocess, so the refusal is exercised and not assumed.
The repair function is unchanged and its count stays pinned in
`TestEscapedTabInASingleLineDestinationIsDestructive`.

The oracle for every claim here is `markdown-it-py`, through
`_has_unclosed_fence`. The predicate under test never builds its own expected
value, and the refused and clean lengths are held as data.
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

# Imported as a MODULE, not by name, so pytest collects the class once.
import test_fix_fences_contracts as contracts
import test_fix_fences_known_corruptions as corruptions

_has_unclosed_fence = contracts._has_unclosed_fence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / ".claude/skills/fix-markdown-fences/scripts/fix_fences.py"

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
main = mod.main

PIN = corruptions.TestEscapedTabInASingleLineDestinationIsDestructive

TAIL = "\n2. ```\n   code\n   ```\n"

#: Lengths whose label lands on a tab stop, so the permissive rule eats nothing
#: that matters. Held as data, taken from the pin, not computed from the scanner.
CLEAN_LENGTHS = PIN.CLEAN_LENGTHS
REFUSED_LENGTHS = tuple(n for n in PIN.LABEL_LENGTHS if n not in CLEAN_LENGTHS)


def single_line(n: int) -> str:
    """The gap: the escaped tab sits on the definition line."""
    return "[" + "f" * n + "]: /u\\\trl" + TAIL


def next_line(n: int) -> str:
    """Control: the same escape measured from column zero."""
    return "[" + "f" * n + "]:\n/u\\\trl" + TAIL


def escaped_space(n: int) -> str:
    """Control: a space is one column wherever it sits."""
    return "[" + "f" * n + "]: /u\\ rl" + TAIL


def _write(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "doc.md"
    target.write_bytes(text.encode("utf-8"))
    return target


class TestTheSweepIsPinned:
    """Held as data, so shrinking a group cannot disarm the tests below."""

    def test_the_groups_partition_the_eleven_lengths(self) -> None:
        assert sorted(REFUSED_LENGTHS + CLEAN_LENGTHS) == list(PIN.LABEL_LENGTHS)
        assert (len(REFUSED_LENGTHS), len(CLEAN_LENGTHS)) == (9, 2)

    def test_the_clean_lengths_are_the_tab_stops(self) -> None:
        assert CLEAN_LENGTHS == (4, 8)


class TestEscapedTabInASingleLineDestinationIsRefused:
    """`--write` never grows a balanced escaped-tab document."""

    @pytest.mark.parametrize("n", REFUSED_LENGTHS)
    def test_each_refused_length_is_balanced_and_its_repair_is_not(self, n: int) -> None:
        """Judged by the reference parser, so the refusal below is not vacuous."""
        text = single_line(n)
        assert not _has_unclosed_fence(text)
        assert _has_unclosed_fence(mod.repair_markdown_fences(text))

    @pytest.mark.parametrize("n", REFUSED_LENGTHS)
    def test_write_refuses_leaves_the_bytes_and_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], n: int
    ) -> None:
        target = _write(tmp_path, single_line(n))
        before = target.read_bytes()

        assert main([str(target), "--write", "--json"]) == 1

        assert target.read_bytes() == before
        payload = json.loads(capsys.readouterr().out)
        assert payload["refused"] == [str(target)]
        assert payload["repaired"] == []

    def test_the_shortest_label_is_refused_by_the_process(self, tmp_path: Path) -> None:
        text = single_line(1)
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

    @pytest.mark.parametrize("n", CLEAN_LENGTHS)
    def test_a_tab_stop_length_has_no_defect_and_is_left_alone(
        self, tmp_path: Path, n: int
    ) -> None:
        text = single_line(n)
        assert not _has_unclosed_fence(text)
        target = _write(tmp_path, text)

        assert main([str(target), "--write"]) == 0

        assert target.read_bytes() == text.encode("utf-8")

    def test_a_refusal_does_not_block_another_file_in_the_run(self, tmp_path: Path) -> None:
        refused = _write(tmp_path, single_line(1))
        unclosed = tmp_path / "other.md"
        unclosed.write_text("text\n\n```python\nx = 1\n", encoding="utf-8")

        assert main([str(refused), str(unclosed), "--write"]) == 1

        assert refused.read_bytes() == single_line(1).encode("utf-8")
        assert not _has_unclosed_fence(unclosed.read_text(encoding="utf-8"))

    def test_a_genuinely_unclosed_file_with_the_shape_is_still_repaired(
        self, tmp_path: Path
    ) -> None:
        text = "[f]: /u\\\trl\n\n```python\nx = 1\n"
        target = _write(tmp_path, text)
        assert _has_unclosed_fence(text)

        assert main([str(target), "--write"]) == 0

        assert not _has_unclosed_fence(target.read_text(encoding="utf-8"))


class TestTheControlsStayClean:
    """Both controls corrupt 0 of 11; a fix that makes one write is a regression.

    The escaped-space control is already unclosed to the reference parser, so
    the repair there is a genuine one and is written. What must never happen is
    a balanced document coming out unclosed, which is the pin's own predicate.
    """

    @pytest.mark.parametrize("build", [next_line, escaped_space], ids=["next-line", "space"])
    @pytest.mark.parametrize("n", PIN.LABEL_LENGTHS)
    def test_the_control_never_goes_in_balanced_and_comes_out_unclosed(
        self, tmp_path: Path, build, n: int
    ) -> None:
        text = build(n)
        target = _write(tmp_path, text)

        assert main([str(target), "--write"]) in (0, 1)

        written = target.read_text(encoding="utf-8")
        assert not (not _has_unclosed_fence(text) and _has_unclosed_fence(written))
        assert PIN._corrupts(text) is False


class TestWithoutTheReferenceParser:
    """Vendored trees carry no `markdown-it-py`, so the refusal is not there."""

    @pytest.fixture
    def no_reference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "_load_reference", lambda: None)

    @pytest.mark.usefixtures("no_reference")
    @pytest.mark.parametrize("n", REFUSED_LENGTHS)
    def test_the_write_lands_and_the_file_comes_out_unclosed(self, tmp_path: Path, n: int) -> None:
        """Documents the cost the SKILL.md states, so the claim is measured."""
        target = _write(tmp_path, single_line(n))

        assert main([str(target), "--write"]) == 0

        assert _has_unclosed_fence(target.read_text(encoding="utf-8"))
