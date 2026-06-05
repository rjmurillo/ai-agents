"""Tests for the in-process hook dispatcher (ADR-068, #2295).

These tests are the in-process dispatcher evidence: they prove it runs exactly
the manifest set, in order, with the host's stdin bytes, and preserves
fail-closed semantics (ADR-066). The installed-plugin harness covers host
environment variables, launcher behavior, and artifact layout.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / ".claude" / "lib" / "hook_dispatch.py"
_spec = importlib.util.spec_from_file_location("hook_dispatch", _LIB)
hook_dispatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook_dispatch)
run_dispatch = hook_dispatch.run_dispatch


def _write_shim(directory: Path, name: str, body: str) -> str:
    """Write a fake shim file and return its basename."""
    (directory / name).write_text(body, encoding="utf-8")
    return name


# A shim that records that it ran (appends its tag to a shared file) then exits
# with the given code. Reads stdin so we can assert it saw the payload.
def _recorder_shim(tag: str, record_path: Path, exit_code: int) -> str:
    return (
        "import sys, json\n"
        "raw = sys.stdin.buffer.read()\n"
        f"open(r'{record_path}', 'a').write({tag!r} + ':' + raw.decode() + '\\n')\n"
        f"sys.exit({exit_code})\n"
    )


class TestRunDispatch:
    def test_all_allow_returns_zero(self, tmp_path):
        rec = tmp_path / "rec.txt"
        names = [
            _write_shim(tmp_path, "a.py", _recorder_shim("a", rec, 0)),
            _write_shim(tmp_path, "b.py", _recorder_shim("b", rec, 0)),
        ]
        rc = run_dispatch(tmp_path, names, b'{"tool_name":"Read"}')
        assert rc == 0
        # Both ran, in order.
        lines = rec.read_text().splitlines()
        assert [ln.split(":")[0] for ln in lines] == ["a", "b"]

    def test_first_block_short_circuits(self, tmp_path):
        rec = tmp_path / "rec.txt"
        names = [
            _write_shim(tmp_path, "a.py", _recorder_shim("a", rec, 2)),
            _write_shim(tmp_path, "b.py", _recorder_shim("b", rec, 0)),
        ]
        rc = run_dispatch(tmp_path, names, b"{}")
        assert rc == 2
        # b must NOT run: the first denial denies the tool.
        assert rec.read_text().splitlines() == ["a:{}"]

    def test_block_in_middle_returns_block_code(self, tmp_path):
        rec = tmp_path / "rec.txt"
        names = [
            _write_shim(tmp_path, "a.py", _recorder_shim("a", rec, 0)),
            _write_shim(tmp_path, "b.py", _recorder_shim("b", rec, 2)),
            _write_shim(tmp_path, "c.py", _recorder_shim("c", rec, 0)),
        ]
        rc = run_dispatch(tmp_path, names, b"{}")
        assert rc == 2
        assert [ln.split(":")[0] for ln in rec.read_text().splitlines()] == ["a", "b"]

    def test_each_shim_sees_full_payload(self, tmp_path):
        rec = tmp_path / "rec.txt"
        payload = b'{"tool_name":"Bash","tool_input":{"command":"git push"}}'
        names = [
            _write_shim(tmp_path, "a.py", _recorder_shim("a", rec, 0)),
            _write_shim(tmp_path, "b.py", _recorder_shim("b", rec, 0)),
        ]
        run_dispatch(tmp_path, names, payload)
        # Both shims saw the exact same payload bytes (stdin replayed each time).
        for line in rec.read_text().splitlines():
            assert line.split(":", 1)[1] == payload.decode()

    def test_text_mode_stdin_decodes_utf8(self, tmp_path):
        rec = tmp_path / "rec.txt"
        payload_text = '{"message":"snowman ☃"}'
        names = [
            _write_shim(
                tmp_path,
                "text.py",
                "import sys\n"
                f"open(r'{rec}', 'w', encoding='utf-8').write(sys.stdin.read())\n",
            ),
        ]

        rc = run_dispatch(tmp_path, names, payload_text.encode("utf-8"))

        assert rc == 0
        assert rec.read_text(encoding="utf-8") == payload_text

    def test_invalid_utf8_stdin_fails_closed(self, tmp_path):
        names = [
            _write_shim(
                tmp_path,
                "text.py",
                "import sys\nsys.stdin.read()\n",
            ),
        ]

        rc = run_dispatch(tmp_path, names, b"\xff")

        assert rc == 2

    def test_missing_shim_fails_closed(self, tmp_path):
        names = [_write_shim(tmp_path, "a.py", _recorder_shim("a", tmp_path / "r", 0)),
                 "does_not_exist.py"]
        rc = run_dispatch(tmp_path, names, b"{}")
        assert rc == 2

    def test_shim_uncaught_exception_fails_closed(self, tmp_path):
        names = [_write_shim(tmp_path, "boom.py", "raise RuntimeError('kaboom')\n")]
        rc = run_dispatch(tmp_path, names, b"{}")
        assert rc == 2

    def test_invalid_shim_timeout_fails_closed(self, tmp_path):
        names = [_write_shim(tmp_path, "slow.py", "import sys; sys.exit(0)\n")]

        rc = run_dispatch(tmp_path, names, b"{}", {"slow.py": 0})

        assert rc == 2

    def test_orphan_file_not_in_manifest_is_not_run(self, tmp_path):
        rec = tmp_path / "rec.txt"
        # registered shim
        names = [_write_shim(tmp_path, "registered.py", _recorder_shim("reg", rec, 0))]
        # orphan on disk but NOT in the manifest -> must not execute
        _write_shim(tmp_path, "orphan.py", _recorder_shim("orphan", rec, 2))
        rc = run_dispatch(tmp_path, names, b"{}")
        assert rc == 0
        assert [ln.split(":")[0] for ln in rec.read_text().splitlines()] == ["reg"]

    def test_empty_manifest_allows(self, tmp_path):
        assert run_dispatch(tmp_path, [], b"{}") == 0

    def test_non_int_systemexit_is_denial(self, tmp_path):
        names = [_write_shim(tmp_path, "s.py", "import sys; sys.exit('nope')\n")]
        rc = run_dispatch(tmp_path, names, b"{}")
        assert rc == 1

    def test_shim_returning_without_exit_allows(self, tmp_path):
        rec = tmp_path / "rec.txt"
        names = [
            _write_shim(tmp_path, "a.py", f"open(r'{rec}','a').write('a\\n')\n"),
            _write_shim(tmp_path, "b.py", _recorder_shim("b", rec, 0)),
        ]
        rc = run_dispatch(tmp_path, names, b"{}")
        assert rc == 0
        assert rec.read_text().splitlines() == ["a", "b:{}"]

    def test_stdin_restored_after_dispatch(self, tmp_path):
        sentinel = sys.stdin
        names = [_write_shim(tmp_path, "a.py", _recorder_shim("a", tmp_path / "r", 0))]
        run_dispatch(tmp_path, names, b"{}")
        assert sys.stdin is sentinel
