#!/usr/bin/env python3
"""CLI and runtime-contract tests for check-failures (failure_loops.py)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from stuck_failure_events import entry, fail, kinds, mod, ok

main = mod.main


class FakeStdin(io.StringIO):
    def __init__(self, text: str, tty: bool = False) -> None:
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def write(tmp_path: Path, content: str | bytes) -> Path:
    path = tmp_path / "events.json"
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


class TestCli:
    def test_reads_stdin_and_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", FakeStdin(json.dumps([fail("Bash", "x")] * 3)))
        assert main([]) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is True

    def test_entry_point_dispatches(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = write(tmp_path, json.dumps([fail("Bash", "x")] * 3))
        assert entry.main(["check-failures", "--events", str(path)]) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is True

    def test_reads_file_with_bom(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = write(tmp_path, b"\xef\xbb\xbf" + json.dumps([ok("Bash")]).encode())
        assert main(["--events", str(path)]) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is False

    @pytest.mark.parametrize(
        ("flags", "events", "expected"),
        [
            (["--repeat", "2"], [fail("Bash", "x")] * 2, ["failure-repeat"]),
            (
                ["--churn", "2", "--repeat", "9"],
                [ok("Edit", "a.py"), fail("Bash", "x")] * 2,
                ["edit-churn"],
            ),
        ],
    )
    def test_threshold_flags(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        flags: list[str],
        events: list[dict[str, Any]],
        expected: list[str],
    ) -> None:
        path = write(tmp_path, json.dumps(events))
        assert main(["--events", str(path), *flags]) == 0
        assert kinds(json.loads(capsys.readouterr().out)) == expected

    def test_window_flag(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = write(tmp_path, json.dumps([ok("Bash")] * 9))
        assert main(["--events", str(path), "--window", "5"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert (result["events_total"], result["events_checked"]) == (9, 5)

    @pytest.mark.parametrize(
        ("content", "flags", "message"),
        [
            ("not json", [], "not valid JSON"),
            ("{}", [], "JSON array"),
            (b"\xff\xfe[]", [], "can't decode"),
            ("[]", ["--window", "1"], "window (1) must be >= 2"),
        ],
    )
    def test_bad_file_input_exits_two(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        content: str | bytes,
        flags: list[str],
        message: str,
    ) -> None:
        path = write(tmp_path, content)
        assert main(["--events", str(path), *flags]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("stuck-detection: ")
        assert message in captured.err

    def test_recursion_error_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Which error a deeply nested, unterminated array raises first (RecursionError or a
        # JSONDecodeError at end of input) depends on the interpreter's recursion settings,
        # so the handler is exercised directly instead of through such an input.
        def too_deep(_text: str) -> object:
            raise RecursionError("maximum recursion depth exceeded")

        monkeypatch.setattr(mod.json, "loads", too_deep)
        path = write(tmp_path, "[]")
        assert main(["--events", str(path)]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "stuck-detection: input JSON is nested too deeply to decode\n"

    def test_oversized_file_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(mod, "MAX_INPUT_BYTES", 10)
        path = write(tmp_path, json.dumps([ok("Bash")]))
        assert main(["--events", str(path)]) == 2
        assert "input limit" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("stdin", "message"),
        [
            (FakeStdin("not json"), "not valid JSON"),
            (FakeStdin("[]", tty=True), "stdin is a terminal"),
            (FakeStdin("[" + " " * 20), "input limit"),
        ],
    )
    def test_bad_stdin_exits_two(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        stdin: FakeStdin,
        message: str,
    ) -> None:
        monkeypatch.setattr(mod, "MAX_INPUT_BYTES", 10)
        monkeypatch.setattr(sys, "stdin", stdin)
        assert main([]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert message in captured.err

    def test_missing_file_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--events", str(tmp_path / "missing.json")]) == 2
        assert capsys.readouterr().err.startswith("stuck-detection: ")

    def test_non_integer_flag_is_an_argparse_usage_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--repeat", "abc"])
        assert exc.value.code == 2
        assert capsys.readouterr().out == ""

    def test_reads_binary_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        raw = b"\xef\xbb\xbf" + json.dumps([fail("Bash", "x")] * 3).encode()
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
        assert main([]) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is True


class TestRuntimeContract:
    """Run the shipped entry point as a consumer would: by plugin-root path, from another cwd."""

    SCRIPT = Path(__file__).resolve().parents[3] / "src/claude/skills/stuck-detection"

    def invoke(self, tmp_path: Path, stdin: bytes) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(self.SCRIPT / "stuck_detection.py"), "check-failures"],
            input=stdin,
            capture_output=True,
            cwd=tmp_path,
            timeout=60,
            check=False,
        )

    def test_detects_loop_from_outside_the_repo(self, tmp_path: Path) -> None:
        proc = self.invoke(tmp_path, json.dumps([fail("Bash", "x")] * 3).encode())
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["stuck"] is True

    def test_bad_input_exits_two_from_outside_the_repo(self, tmp_path: Path) -> None:
        proc = self.invoke(tmp_path, b"not json")
        assert proc.returncode == 2
        assert proc.stdout == b""
        assert proc.stderr.startswith(b"stuck-detection: ")


class TestRoundTwoCli:
    """Each test pins a /review round-2 finding."""

    def test_entry_point_accepts_global_flag_first(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        events = tmp_path / "events.json"
        events.write_text(json.dumps([fail("Bash", "x")] * 3), encoding="utf-8")
        argv = ["--history", str(tmp_path / "h.json"), "check-failures", "--events", str(events)]
        assert entry.main(argv) == 0
        assert json.loads(capsys.readouterr().out)["stuck"] is True

    def test_entry_point_help_lists_check_failures(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            entry.main(["--help"])
        assert "check-failures" in capsys.readouterr().out

    def test_entry_point_still_rejects_unknown_arguments(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            entry.main(["--history", str(tmp_path / "h.json"), "status", "--bogus"])
        assert exc.value.code == 2
        assert "unrecognized arguments: --bogus" in capsys.readouterr().err

    @pytest.mark.skipif(not os.path.exists("/dev/zero"), reason="needs /dev/zero")
    def test_special_file_read_is_bounded(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(mod, "MAX_INPUT_BYTES", 1024)
        assert main(["--events", "/dev/zero"]) == 2
        assert "input limit" in capsys.readouterr().err

    def test_closed_stdin_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", None)
        assert main([]) == 2
        assert "stdin is closed" in capsys.readouterr().err

    def test_missing_sibling_module_exits_two(self, tmp_path: Path) -> None:
        lone = tmp_path / "stuck_detection.py"
        lone.write_text((TestRuntimeContract.SCRIPT / "stuck_detection.py").read_text())
        proc = subprocess.run(
            [sys.executable, str(lone), "check-failures"],
            input=b"[]",
            capture_output=True,
            cwd=tmp_path,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 2
        assert proc.stdout == b""
        assert proc.stderr.startswith(b"stuck-detection: cannot load")

    def test_missing_shared_lib_exits_two(self, tmp_path: Path) -> None:
        skill = tmp_path / "skills" / "stuck-detection"
        skill.mkdir(parents=True)
        for name in ("stuck_detection.py", "failure_loops.py"):
            (skill / name).write_text((TestRuntimeContract.SCRIPT / name).read_text())
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT", "PYTHONPATH"}
        }
        proc = subprocess.run(
            [sys.executable, "-I", str(skill / "stuck_detection.py"), "check-failures"],
            input=b"[]",
            capture_output=True,
            cwd=tmp_path,
            env=env,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 2
        assert proc.stdout == b""
        assert proc.stderr.startswith(b"stuck-detection: cannot load")

    def test_loader_reports_unloadable_sibling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(entry, "__file__", str(tmp_path / "stuck_detection.py"))
        assert entry.main(["check-failures"]) == 2
        assert capsys.readouterr().err.startswith("stuck-detection: cannot load")

    def test_loader_reports_missing_spec(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(entry.importlib.util, "spec_from_file_location", lambda *a: None)
        assert entry.main(["check-failures"]) == 2
        assert capsys.readouterr().err.startswith("stuck-detection: cannot load")
