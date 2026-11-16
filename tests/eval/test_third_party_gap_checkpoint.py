"""Tests for scripts/eval/_third_party_gap_checkpoint.py: repairing a checkpoint tail."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.eval._third_party_gap_test_support import eval_path

with eval_path():
    import _third_party_gap_checkpoint as checkpoint


class TestRepairTail:
    def test_a_broken_last_line_is_cut_off(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"a": 1}\n{"revision": "TG00')

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b'{"a": 1}\n'

    def test_a_whole_last_record_gets_its_newline(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"a": 1}\n{"b": 2}')

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b'{"a": 1}\n{"b": 2}\n'

    def test_a_clean_file_is_left_alone(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"a": 1}\n')

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b'{"a": 1}\n'

    def test_an_empty_file_is_left_alone(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b"")

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b""

    def test_a_broken_last_line_that_ends_in_a_newline_is_cut_off(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"a": 1}\n{"revision": "TG\n')

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b'{"a": 1}\n'

    def test_a_broken_last_line_before_blank_crlf_lines_is_cut_off(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"a": 1}\r\n{"revision": "TG\r\n\r\n')

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b'{"a": 1}\r\n'

    def test_trailing_blank_lines_after_a_whole_record_are_left_alone(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"a": 1}\n\n')

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b'{"a": 1}\n\n'

    def test_a_single_broken_line_leaves_an_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_bytes(b'{"revision": "TG')

        checkpoint.repair_tail(path)

        assert path.read_bytes() == b""


class TestRepairTailInPlace:
    def test_repair_never_rewrites_the_whole_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*_a: object, **_k: object) -> None:
            raise AssertionError("repair_tail rewrote the whole file")

        broken = tmp_path / "broken.jsonl"
        broken.write_bytes(b'{"a": 1}\n{"revision": "TG00')
        whole = tmp_path / "whole.jsonl"
        whole.write_bytes(b'{"a": 1}\n{"b": 2}')
        monkeypatch.setattr(Path, "write_bytes", refuse)
        monkeypatch.setattr(Path, "write_text", refuse)

        checkpoint.repair_tail(broken)
        checkpoint.repair_tail(whole)

        assert broken.read_bytes() == b'{"a": 1}\n'
        assert whole.read_bytes() == b'{"a": 1}\n{"b": 2}\n'
