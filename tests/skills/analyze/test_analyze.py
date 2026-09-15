"""Tests for analyze.py's --thoughts / --thoughts-file mutual exclusivity.

--thoughts-file exists so request text never has to pass through a shell
heredoc (a request line reading exactly "EOF" would terminate a heredoc
early and let the rest of the request parse as shell commands). These tests
cover: positive (each flag alone works), negative (both flags, neither flag,
a missing --thoughts-file path), and edge (an empty file, a file whose
content contains a line that is literally "EOF").
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "analyze" / "scripts"
MODULE_PATH = SCRIPTS / "analyze.py"
SPEC = importlib.util.spec_from_file_location(
    f"analyze_script_{abs(hash(MODULE_PATH))}", MODULE_PATH
)
assert SPEC and SPEC.loader
analyze = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyze
SPEC.loader.exec_module(analyze)

BASE_ARGS = ["--step-number", "1", "--total-steps", "6"]


class TestThoughtsFlagPositive:
    def test_inline_thoughts(self, capsys):
        analyze.main([*BASE_ARGS, "--thoughts", "hello world"])
        assert "hello world" in capsys.readouterr().out

    def test_thoughts_file(self, tmp_path, capsys):
        thoughts_path = tmp_path / "thoughts.txt"
        thoughts_path.write_text("from a file", encoding="utf-8")
        analyze.main([*BASE_ARGS, "--thoughts-file", str(thoughts_path)])
        assert "from a file" in capsys.readouterr().out


class TestThoughtsFlagNegative:
    def test_both_flags_rejected(self, tmp_path):
        thoughts_path = tmp_path / "thoughts.txt"
        thoughts_path.write_text("x", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            analyze.main([*BASE_ARGS, "--thoughts", "x", "--thoughts-file", str(thoughts_path)])
        assert exc.value.code == 2

    def test_neither_flag_rejected(self):
        with pytest.raises(SystemExit) as exc:
            analyze.main(BASE_ARGS)
        assert exc.value.code == 2

    def test_missing_thoughts_file_exits_1(self, tmp_path, capsys):
        missing = tmp_path / "does-not-exist.txt"
        with pytest.raises(SystemExit) as exc:
            analyze.main([*BASE_ARGS, "--thoughts-file", str(missing)])
        assert exc.value.code == 1
        assert "cannot read" in capsys.readouterr().err


class TestThoughtsFlagEdge:
    def test_empty_file(self, tmp_path, capsys):
        thoughts_path = tmp_path / "empty.txt"
        thoughts_path.write_text("", encoding="utf-8")
        analyze.main([*BASE_ARGS, "--thoughts-file", str(thoughts_path)])
        assert "YOUR ACCUMULATED STATE:" in capsys.readouterr().out

    def test_file_containing_eof_line_is_read_literally(self, tmp_path, capsys):
        thoughts_path = tmp_path / "eof.txt"
        thoughts_path.write_text("first line\nEOF\nsecond line after EOF\n", encoding="utf-8")
        analyze.main([*BASE_ARGS, "--thoughts-file", str(thoughts_path)])
        out = capsys.readouterr().out
        assert "first line" in out
        assert "second line after EOF" in out
