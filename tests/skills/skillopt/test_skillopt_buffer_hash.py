"""Tests for the skillopt rejected-edit buffer and sha256 hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import skillopt
from skillopt import SkillOptError
from skillopt_helpers import (
    Capture,
    write_json,
)


class TestBuffer:
    PATCHES = [{"op": "append", "text": "x"}]

    def test_signature_stable_across_key_order(self) -> None:
        a = skillopt.edit_signature([{"op": "replace", "anchor": "z", "text": "t"}])
        b = skillopt.edit_signature([{"text": "t", "anchor": "z", "op": "replace"}])
        assert a == b

    def test_signature_differs_on_content(self) -> None:
        a = skillopt.edit_signature([{"op": "append", "text": "a"}])
        b = skillopt.edit_signature([{"op": "append", "text": "b"}])
        assert a != b

    def test_missing_buffer_is_not_known_bad(self, tmp_path: Path) -> None:
        assert skillopt.is_known_bad(tmp_path / "none.jsonl", self.PATCHES) is False

    def test_append_then_known_bad(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        assert skillopt.is_known_bad(buf, self.PATCHES) is False
        skillopt.append_rejected(buf, self.PATCHES, 0.5, 0.6, "regressed", 3)
        assert skillopt.is_known_bad(buf, self.PATCHES) is True

    def test_other_patches_are_novel_after_append(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        skillopt.append_rejected(buf, self.PATCHES, 0.5, 0.6, "n", 1)
        assert skillopt.is_known_bad(buf, [{"op": "append", "text": "other"}]) is False

    def test_append_is_idempotent(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        skillopt.append_rejected(buf, self.PATCHES, 0.5, 0.6, "n", 1)
        skillopt.append_rejected(buf, self.PATCHES, 0.5, 0.6, "n", 1)
        assert len(buf.read_text(encoding="utf-8").splitlines()) == 1

    def test_append_creates_parent_dir(self, tmp_path: Path) -> None:
        buf = tmp_path / "deep" / "dir" / "buf.jsonl"
        skillopt.append_rejected(buf, self.PATCHES, 0.5, 0.6, "n", 1)
        assert buf.is_file()

    def test_buffer_blank_lines_ignored(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        buf.write_text("\n\n", encoding="utf-8")
        assert skillopt.is_known_bad(buf, self.PATCHES) is False

    def test_malformed_line_names_line_number(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        buf.write_text('{"edit_signature": "x"}\n\n{not json\n', encoding="utf-8")
        with pytest.raises(SkillOptError, match=r"line 3 is not valid JSON"):
            skillopt.is_known_bad(buf, self.PATCHES)

    def test_non_object_line_names_line_number(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        buf.write_text("[1, 2]\n", encoding="utf-8")
        with pytest.raises(SkillOptError, match=r"line 1 is not a JSON object"):
            skillopt.is_known_bad(buf, self.PATCHES)


class TestHash:
    def test_file_sha256_matches_hashlib(self, tmp_path: Path) -> None:
        f = tmp_path / "a.bin"
        f.write_bytes(b"a\r\nb\x00")
        assert skillopt.file_sha256(f) == hashlib.sha256(b"a\r\nb\x00").hexdigest()
        assert skillopt.file_sha256(str(f)) == skillopt.file_sha256(f)

    def test_cli_prints_digest_and_path(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "a.txt"
        f.write_bytes(b"hello")
        assert skillopt.main(["hash", str(f)]) == 0
        assert capsys.readouterr().out == f"{hashlib.sha256(b'hello').hexdigest()}  {f}\n"

    def test_cli_multiple_files(self, tmp_path: Path, capsys: Capture) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        a.write_bytes(b"1")
        b.write_bytes(b"2")
        assert skillopt.main(["hash", str(a), str(b)]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert [line.split("  ", 1)[1] for line in lines] == [str(a), str(b)]
        assert lines[0].split("  ")[0] != lines[1].split("  ")[0]

    def test_expect_match_exits_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "a"
        f.write_bytes(b"x")
        digest = hashlib.sha256(b"x").hexdigest()
        assert skillopt.main(["hash", str(f), "--expect", digest.upper() + "\n"]) == 0

    def test_expect_mismatch_exits_one(self, tmp_path: Path, capsys: Capture) -> None:
        f = tmp_path / "a"
        f.write_bytes(b"x")
        assert skillopt.main(["hash", str(f), "--expect", "0" * 64]) == 1
        assert "MISMATCH" in capsys.readouterr().out

    def test_expect_with_multiple_files_is_usage_error(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        a.write_bytes(b"1")
        b.write_bytes(b"2")
        assert skillopt.main(["hash", str(a), str(b), "--expect", "0" * 64]) == 2
        assert "exactly one file" in capsys.readouterr().err

    def test_missing_file_exits_two(self, tmp_path: Path, capsys: Capture) -> None:
        assert skillopt.main(["hash", str(tmp_path / "nope")]) == 2
        assert capsys.readouterr().err.startswith("skillopt: ")


class TestBufferCli:
    @staticmethod
    def _patches(tmp_path: Path, patches: object | None = None) -> Path:
        return write_json(
            tmp_path / "p.json", [{"op": "append", "text": "x"}] if patches is None else patches
        )

    def test_check_novel_exit_one(self, tmp_path: Path, capsys: Capture) -> None:
        rc = skillopt.main(
            [
                "buffer-check",
                "--buffer",
                str(tmp_path / "buf.jsonl"),
                "--patches",
                str(self._patches(tmp_path)),
            ]
        )
        assert rc == 1
        assert capsys.readouterr().out.strip() == "NOVEL"

    def test_add_then_check_known_bad_exit_zero(self, tmp_path: Path, capsys: Capture) -> None:
        buf = tmp_path / "buf.jsonl"
        patches = self._patches(tmp_path)
        add = ["buffer-add", "--buffer", str(buf), "--patches", str(patches)]
        add += ["--score", "0.4", "--incumbent", "0.6", "--note", "regressed", "--step", "2"]
        assert skillopt.main(add) == 0
        capsys.readouterr()
        check = ["buffer-check", "--buffer", str(buf), "--patches", str(patches)]
        assert skillopt.main(check) == 0
        assert capsys.readouterr().out.strip() == "KNOWN-BAD"

    def test_add_twice_is_idempotent(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        patches = self._patches(tmp_path)
        add = [
            "buffer-add",
            "--buffer",
            str(buf),
            "--patches",
            str(patches),
            "--score",
            "0.4",
            "--incumbent",
            "0.6",
        ]
        assert skillopt.main(add) == 0
        assert skillopt.main(add) == 0
        assert len(buf.read_text(encoding="utf-8").splitlines()) == 1
        assert json.loads(buf.read_text(encoding="utf-8"))["step"] == 0

    def test_key_order_insensitive_signature_through_cli(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        first = write_json(tmp_path / "a.json", [{"op": "replace", "anchor": "z", "text": "t"}])
        second = tmp_path / "b.json"
        second.write_text('[{"text": "t", "anchor": "z", "op": "replace"}]', encoding="utf-8")
        skillopt.main(
            [
                "buffer-add",
                "--buffer",
                str(buf),
                "--patches",
                str(first),
                "--score",
                "0",
                "--incumbent",
                "1",
            ]
        )
        assert skillopt.main(["buffer-check", "--buffer", str(buf), "--patches", str(second)]) == 0

    def test_malformed_buffer_line_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        buf = tmp_path / "buf.jsonl"
        buf.write_text('{"edit_signature": "x"}\nnot json\n', encoding="utf-8")
        rc = skillopt.main(
            ["buffer-check", "--buffer", str(buf), "--patches", str(self._patches(tmp_path))]
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "line 2" in err
        assert "Traceback" not in err

    def test_malformed_buffer_blocks_add(self, tmp_path: Path) -> None:
        buf = tmp_path / "buf.jsonl"
        buf.write_text("oops\n", encoding="utf-8")
        add = [
            "buffer-add",
            "--buffer",
            str(buf),
            "--patches",
            str(self._patches(tmp_path)),
            "--score",
            "0",
            "--incumbent",
            "1",
        ]
        assert skillopt.main(add) == 2
        assert buf.read_text(encoding="utf-8") == "oops\n"

    def test_missing_patches_file_exit_two(self, tmp_path: Path) -> None:
        rc = skillopt.main(
            [
                "buffer-check",
                "--buffer",
                str(tmp_path / "b"),
                "--patches",
                str(tmp_path / "gone.json"),
            ]
        )
        assert rc == 2
