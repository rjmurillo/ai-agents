"""Control-character and table-cell neutralization in distill_artifact (issue #6506).

The digest quotes artifact lines and source names an attacker can choose. These
tests pin that no raw control character reaches the digest and that a pipe in a
diff path cannot add a table column.

Exit Codes:
    0: Success - All tests passed
    1: Error - One or more tests failed (set by pytest framework)

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).parent.parent.parent
scripts_dir = repo_root / ".claude" / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(scripts_dir))

import distill_artifact as da  # noqa: E402


def write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = da.main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def digest_text(out: str) -> str:
    return Path(out.strip()).read_text(encoding="utf-8")


class TestNeutralize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("plain text", "plain text"),
            ("tab\tkept", "tab\tkept"),
            ("\x1b[31mred\x1b[0m", "\\x1b[31mred\\x1b[0m"),
            ("nul\x00here", "nul\\x00here"),
            ("bell\x07", "bell\\x07"),
            ("del\x7f", "del\\x7f"),
            ("c1\x9b", "c1\\x9b"),
            ("new\nline\rcr", "new\\x0aline\\x0dcr"),
            ("sep\u2028para\u2029", "sep\\u2028para\\u2029"),
            ("unicode \u00e9 \u4e2d kept", "unicode \u00e9 \u4e2d kept"),
            ("", ""),
        ],
    )
    def test_control_characters_become_visible_escapes(self, raw: str, expected: str) -> None:
        assert da.neutralize(raw) == expected

    def test_clip_neutralizes_before_it_truncates(self) -> None:
        clipped = da.clip("\x1b" * 300)
        assert len(clipped) == 240
        assert "\x1b" not in clipped

    def test_cell_escapes_the_pipe(self) -> None:
        assert da.cell("a|b") == "a\\|b"
        assert da.cell("plain") == "plain"
        assert da.cell("a\x1b|b") == "a\\x1b\\|b"


class TestHostileInput:
    def test_ansi_escape_in_a_text_line_never_reaches_the_digest(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "t.txt", "error \x1b]0;owned\x07 \x1b[2J done\nok\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "\x1b" not in body
        assert "\x07" not in body
        assert "\\x1b[2J" in body

    def test_control_characters_never_reach_the_digest_from_any_section(
        self, tmp_path, capsys
    ) -> None:
        lines = "".join(f"error \x00\x1b\x7f{i}\n" for i in range(60))
        src = write(tmp_path, "t.txt", lines)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert not any(ord(ch) < 32 and ch not in "\n\t" for ch in body)
        assert "\x7f" not in body

    def test_newline_in_the_source_name_cannot_start_a_digest_line(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "evil\n# injected heading", "error x\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "\n# injected heading" not in body
        assert "\\x0a# injected heading" in body
        assert body.splitlines()[0].startswith("# Digest: ")
        assert sum(1 for line in body.splitlines() if line.startswith("# ")) == 1

    def test_pipe_in_a_diff_path_cannot_add_a_column(self, tmp_path, capsys) -> None:
        diff = "diff --git a/x|y.py b/x|y.py\n--- a/x|y.py\n+++ b/x|y.py\n@@ -1 +1 @@\n-a\n+b\n"
        src = write(tmp_path, "d.diff", diff)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        row = next(line for line in body.splitlines() if line.startswith("| x"))
        assert row == "| x\\|y.py | 1 | 1 | 1 |"

    def test_control_character_in_a_diff_path_is_escaped(self, tmp_path, capsys) -> None:
        diff = "diff --git a/a\x1bb b/a\x1bb\n--- a/a\x1bb\n+++ b/a\x1bb\n@@ -1 +1 @@\n-a\n+b\n"
        src = write(tmp_path, "d.diff", diff)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "\x1b" not in body
        assert "| a\\x1bb | 1 | 1 | 1 |" in body

    def test_signal_lines_keep_the_digits_of_a_control_character_escape(
        self, tmp_path, capsys
    ) -> None:
        src = write(tmp_path, "t.txt", "error \x1b[2J and \x01 end\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        signals = digest_text(out).split("## Signal lines")[1].split("##")[0]
        assert "\\x1b" in signals
        assert "\\x01" in signals
        assert "x#b" not in signals
        assert "\x1b" not in signals

    def test_signal_lines_with_different_numbers_still_group_around_an_escape(
        self, tmp_path, capsys
    ) -> None:
        src = write(tmp_path, "t.txt", "error 1 \x1b x\nerror 22 \x1b x\nerror 333 \x1b x\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        assert "- L1 (x3): error # \\x1b x" in digest_text(out)

    def test_signal_key_is_still_capped_after_digit_collapse(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "t.txt", "error " + "\x1b" * 300 + "\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        signals = digest_text(out).split("## Signal lines")[1].split("##")[0]
        key = signals.split("): ", 1)[1].strip()
        assert len(key) == da.LINE_CAP

    def test_clean_input_digest_is_unchanged(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "t.txt", "error x\nplain\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "1: error x" in body
        assert "2: plain" in body
