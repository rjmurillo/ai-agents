"""Tests for scripts/run_with_receipt.py (issue #5851)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_with_receipt import (
    EXIT_EXTERNAL,
    EXIT_USAGE,
    main,
    resolve_out_dir,
)

GITHUB_TOKEN = "ghp_" + "A1b2C3d4E5" * 4  # 40 chars after prefix, matches github-token rule
BEARER = "Bearer abcDEF123456xyz+/="


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def run(args: list[str], out_dir: Path, *, inline: int = 16384) -> int:
    return main(["run", "--max-inline-bytes", str(inline), "--out-dir", str(out_dir), "--", *args])


def artifacts(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("*.log")) if out_dir.exists() else []


def artifact_from(stdout: str) -> Path:
    line = next(item for item in stdout.splitlines() if item.startswith("artifact: "))
    return Path(line.removeprefix("artifact: "))


class TestSmallOutput:
    def test_passes_through_unchanged_without_artifact(self, tmp_path, capfd):
        code = run(py("import sys; print('hello'); print('oops', file=sys.stderr)"), tmp_path)
        captured = capfd.readouterr()
        assert code == 0
        assert captured.out == "hello\n"
        assert captured.err == "oops\n"
        assert artifacts(tmp_path) == []

    def test_propagates_nonzero_exit(self, tmp_path, capfd):
        code = run(py("import sys; print('x'); sys.exit(7)"), tmp_path)
        assert code == 7
        assert capfd.readouterr().out == "x\n"

    def test_signal_death_maps_to_128_plus_signal(self, tmp_path):
        code = run(py("import os, signal; os.kill(os.getpid(), signal.SIGTERM)"), tmp_path)
        assert code == 128 + 15

    def test_secret_redacted_even_when_small(self, tmp_path, capfd):
        run(py(f"print('{GITHUB_TOKEN}')"), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert "[redacted: github-token]" in out


class TestLargeOutput:
    def test_truncates_with_receipt_and_saves_full_output(self, tmp_path, capfd):
        code = run(py("print('line-%05d' % 0); [print('x' * 99) for _ in range(2000)]"), tmp_path)
        out = capfd.readouterr().out
        assert code == 0
        assert out.startswith("[output contained")
        assert "exit_code: 0" in out
        assert "truncated: true" in out
        assert "duration_s:" in out
        assert len(out.encode()) < 8000
        saved = artifact_from(out).read_bytes()
        assert f"total_bytes: {len(saved)}" in out
        assert saved.count(b"x" * 99) == 2000

    def test_receipt_reports_exposed_bytes(self, tmp_path, capfd):
        run(py("print('y' * 50000)"), tmp_path)
        out = capfd.readouterr().out
        exposed = int(
            next(i for i in out.splitlines() if i.startswith("exposed_bytes: ")).split(": ")[1]
        )
        assert 0 < exposed < 5000

    def test_just_over_threshold_triggers_receipt_and_not_truncated(self, tmp_path, capfd):
        run(py("print('z' * 99)"), tmp_path, inline=50)
        out = capfd.readouterr().out
        assert "truncated: false" in out
        assert artifacts(tmp_path)

    def test_exactly_at_threshold_passes_through(self, tmp_path, capfd):
        run(py("import sys; sys.stdout.write('a' * 50)"), tmp_path, inline=50)
        assert capfd.readouterr().out == "a" * 50
        assert artifacts(tmp_path) == []

    def test_nonzero_exit_shows_stderr_tail_and_propagates_code(self, tmp_path, capfd):
        script = (
            "import sys\n"
            "print('o' * 40000)\n"
            "print('E-BEGIN', file=sys.stderr)\n"
            "print('boom: disk full', file=sys.stderr)\n"
            "sys.exit(4)\n"
        )
        code = run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert code == 4
        assert "exit_code: 4" in out
        assert "--- stderr tail (nonzero exit) ---" in out
        assert "boom: disk full" in out.split("--- stderr tail")[1]

    def test_zero_exit_has_no_failure_section(self, tmp_path, capfd):
        run(py("print('o' * 40000)"), tmp_path)
        assert "stderr tail" not in capfd.readouterr().out

    def test_mixed_stdout_stderr_keep_arrival_order_in_artifact(self, tmp_path, capfd):
        script = (
            "import sys, time\n"
            "for i in range(6):\n"
            "    stream = sys.stdout if i % 2 == 0 else sys.stderr\n"
            "    stream.write(f'{i}:' + 'p' * 3000 + '\\n'); stream.flush()\n"
            "    time.sleep(0.15)\n"
        )
        run(py(script), tmp_path)
        saved = artifact_from(capfd.readouterr().out).read_text()
        order = [line.split(":")[0] for line in saved.splitlines()]
        assert order == ["0", "1", "2", "3", "4", "5"]

    def test_invalid_utf8_does_not_crash_and_is_replaced(self, tmp_path, capfd):
        script = "import sys; sys.stdout.buffer.write(b'ok\\xff\\xfe' + b'q' * 40000)"
        code = run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert code == 0
        assert "�" in out
        assert "�" in artifact_from(out).read_text(encoding="utf-8")

    def test_invalid_utf8_small_passthrough(self, tmp_path, capfd):
        code = run(py("import sys; sys.stdout.buffer.write(b'a\\xffb')"), tmp_path)
        assert code == 0
        assert capfd.readouterr().out == "a�b"


class TestSecrets:
    def test_secret_absent_from_receipt_and_artifact(self, tmp_path, capfd):
        script = (
            "import sys\n"
            f"print('{GITHUB_TOKEN}')\n"
            f"print('{BEARER}', file=sys.stderr)\n"
            "print('filler' * 10000)\n"
            f"print('{GITHUB_TOKEN}', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        saved = artifact_from(out).read_text()
        for blob in (out, saved):
            assert GITHUB_TOKEN not in blob
            assert "abcDEF123456xyz" not in blob
        assert "[redacted: github-token]" in saved

    def test_secret_in_argv_redacted_in_command_line(self, tmp_path, capfd):
        run(py(f"x = '{GITHUB_TOKEN}'; print('n' * 40000)"), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert "command:" in out

    def test_exact_env_secret_value_redacted(self, tmp_path, capfd, monkeypatch):
        value = "plainvalue-not-a-known-shape-12345"
        monkeypatch.setenv("MY_SERVICE_TOKEN", value)
        run(py(f"print('{value}'); print('n' * 40000)"), tmp_path)
        out = capfd.readouterr().out
        assert value not in out
        assert value not in artifact_from(out).read_text()

    def test_artifact_permissions_are_private(self, tmp_path, capfd):
        run(py("print('n' * 40000)"), tmp_path / "sub")
        path = artifact_from(capfd.readouterr().out)
        assert (path.stat().st_mode & 0o777) == 0o600


class TestRetrieval:
    def make_artifact(self, tmp_path, capfd) -> tuple[Path, bytes]:
        run(
            py("import sys; sys.stdout.write(''.join(chr(97 + i % 26) for i in range(100000)))"),
            tmp_path,
        )
        path = artifact_from(capfd.readouterr().out)
        return path, path.read_bytes()

    def test_reads_requested_range(self, tmp_path, capfd):
        path, saved = self.make_artifact(tmp_path, capfd)
        code = main(
            ["read", str(path), "--offset", "100", "--length", "50", "--out-dir", str(tmp_path)]
        )
        cap = capfd.readouterr()
        assert code == 0
        assert cap.out == saved[100:150].decode()
        assert "next_offset=150" in cap.err

    def test_reports_end_of_artifact(self, tmp_path, capfd):
        path, saved = self.make_artifact(tmp_path, capfd)
        main(["read", str(path), "--offset", str(len(saved) - 5), "--out-dir", str(tmp_path)])
        assert "end_of_artifact" in capfd.readouterr().err

    def test_caps_oversized_length(self, tmp_path, capfd):
        path, _ = self.make_artifact(tmp_path, capfd)
        main(["read", str(path), "--length", "999999", "--out-dir", str(tmp_path)])
        assert len(capfd.readouterr().out) == 65536

    def test_rejects_path_outside_out_dir(self, tmp_path, capfd):
        outside = tmp_path / "secret.txt"
        outside.write_text("nope")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        assert main(["read", str(outside), "--out-dir", str(out_dir)]) == EXIT_USAGE
        assert "nope" not in capfd.readouterr().out

    def test_rejects_traversal(self, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (tmp_path / "x.log").write_text("hidden")
        assert (
            main(["read", str(out_dir / ".." / "x.log"), "--out-dir", str(out_dir)]) == EXIT_USAGE
        )

    def test_rejects_symlink_escape(self, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        target = tmp_path / "x.log"
        target.write_text("hidden")
        (out_dir / "link.log").symlink_to(target)
        assert main(["read", str(out_dir / "link.log"), "--out-dir", str(out_dir)]) == EXIT_USAGE

    @pytest.mark.parametrize(("offset", "length"), [("-1", "10"), ("0", "0")])
    def test_rejects_bad_range(self, tmp_path, offset, length):
        path = tmp_path / "a.log"
        path.write_text("data")
        argv = [
            "read",
            str(path),
            "--offset",
            offset,
            "--length",
            length,
            "--out-dir",
            str(tmp_path),
        ]
        assert main(argv) == EXIT_USAGE

    def test_missing_artifact_is_external_failure(self, tmp_path):
        assert (
            main(["read", str(tmp_path / "gone.log"), "--out-dir", str(tmp_path)]) == EXIT_EXTERNAL
        )


class TestArgvSafety:
    def test_shell_metacharacters_are_literal_arguments(self, tmp_path, capfd):
        marker = tmp_path / "pwned"
        payload = f"; touch {marker}; echo $(touch {marker}) `touch {marker}` | cat"
        code = run(py("import sys; print(sys.argv[1])") + [payload], tmp_path)
        assert code == 0
        assert capfd.readouterr().out == payload + "\n"
        assert not marker.exists()

    def test_unknown_command_is_external_failure(self, tmp_path, capfd):
        assert run(["/nonexistent/definitely-not-a-binary"], tmp_path) == EXIT_EXTERNAL
        assert "cannot launch" in capfd.readouterr().err

    def test_missing_command_is_usage_error(self, tmp_path, capfd):
        assert main(["run", "--out-dir", str(tmp_path)]) == EXIT_USAGE
        assert "usage" in capfd.readouterr().err

    def test_negative_threshold_is_usage_error(self, tmp_path):
        assert main(["run", "--max-inline-bytes", "-1", "--", "true"]) == EXIT_USAGE

    def test_unknown_subcommand_is_usage_error(self, capfd):
        assert main(["bogus"]) == EXIT_USAGE

    def test_wrapper_flags_after_dashes_belong_to_child(self, tmp_path, capfd):
        code = run(py("import sys; print(sys.argv[1:])") + ["--out-dir", "x"], tmp_path)
        assert code == 0
        assert capfd.readouterr().out == "['--out-dir', 'x']\n"


class TestOutDirResolution:
    def test_explicit_wins_over_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TOOL_OUTPUT_DIR", str(tmp_path / "env"))
        assert resolve_out_dir(str(tmp_path / "flag")) == (tmp_path / "flag").resolve()

    def test_env_used_when_no_flag(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TOOL_OUTPUT_DIR", str(tmp_path / "env"))
        assert resolve_out_dir(None) == (tmp_path / "env").resolve()

    def test_default_is_gitignored_dir_under_repo_root(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TOOL_OUTPUT_DIR", raising=False)
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert resolve_out_dir(None) == tmp_path.resolve() / ".project-toolkit/temp/tool-output"

    def test_default_falls_back_to_cwd_without_git(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TOOL_OUTPUT_DIR", raising=False)
        isolated = tmp_path / "iso"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        if any((p / ".git").exists() for p in (isolated.resolve(), *isolated.resolve().parents)):
            pytest.skip("temp root sits inside a git checkout")
        assert resolve_out_dir(None) == isolated.resolve() / ".project-toolkit/temp/tool-output"


class TestFailureAndEntryPoint:
    def test_unwritable_out_dir_is_external_failure(self, tmp_path, capfd):
        blocker = tmp_path / "file"
        blocker.write_text("x")
        assert run(py("print('n' * 40000)"), blocker / "sub") == EXIT_EXTERNAL
        assert "cannot write artifact" in capfd.readouterr().err

    def test_script_entry_point_propagates_exit_code(self, tmp_path):
        script = Path(__file__).resolve().parents[1] / "scripts" / "run_with_receipt.py"
        result = subprocess.run(
            [sys.executable, str(script), "run", "--out-dir", str(tmp_path), "--"]
            + py("import sys; print('hi'); sys.exit(5)"),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert result.returncode == 5
        assert result.stdout == "hi\n"


class TestRedactionBypasses:
    def receipt_command(self, tmp_path, capfd, extra: list[str]) -> str:
        run(py("print('n' * 40000)") + extra, tmp_path)
        out = capfd.readouterr().out
        return next(i for i in out.splitlines() if i.startswith("command: "))

    @pytest.mark.parametrize(
        "extra",
        [
            ["--token", "plainsecretvalue99"],
            ["--password=plainsecretvalue99"],
            ["--api-key", "plainsecretvalue99"],
            ["-H", "Authorization: Basic plainsecretvalue99"],
            ["https://user:plainsecretvalue99@example.com/x"],
        ],
    )
    def test_secret_flag_values_absent_from_command_echo(self, tmp_path, capfd, extra):
        assert "plainsecretvalue99" not in self.receipt_command(tmp_path, capfd, extra)

    def test_short_env_secret_value_redacted(self, tmp_path, capfd, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "hunter2")
        run(py("print('pw=hunter2')"), tmp_path)
        assert "hunter2" not in capfd.readouterr().out
        run(py("print('pw=hunter2'); print('n' * 40000)"), tmp_path)
        out = capfd.readouterr().out
        assert "hunter2" not in out
        assert "hunter2" not in artifact_from(out).read_text()

    def test_secret_split_across_read_boundary_redacted(self, tmp_path, capfd):
        script = (
            "import sys, time\n"
            f"t = '{GITHUB_TOKEN}'\n"
            "sys.stdout.write('a' * 100 + ' ' + t[:20]); sys.stdout.flush()\n"
            "time.sleep(0.3)\n"
            "sys.stdout.write(t[20:] + ' ' + 'b' * 40000); sys.stdout.flush()\n"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert GITHUB_TOKEN not in artifact_from(out).read_text()

    def test_read_redacts_even_a_planted_unredacted_artifact(self, tmp_path, capfd):
        planted = tmp_path / "planted.log"
        planted.write_text(f"leak {GITHUB_TOKEN}\n")
        assert main(["read", str(planted), "--out-dir", str(tmp_path)]) == 0
        assert GITHUB_TOKEN not in capfd.readouterr().out

    def test_secret_in_invalid_utf8_stream_redacted(self, tmp_path, capfd):
        script = (
            f"import sys; sys.stdout.buffer.write(b'\\xff {GITHUB_TOKEN} \\xfe' + b'q' * 40000)"
        )
        run(py(script), tmp_path)
        out = capfd.readouterr().out
        assert GITHUB_TOKEN not in out
        assert GITHUB_TOKEN not in artifact_from(out).read_text(encoding="utf-8")

    def test_no_temp_file_left_beside_artifact(self, tmp_path, capfd):
        run(py("print('n' * 40000)"), tmp_path)
        capfd.readouterr()
        assert [p.suffix for p in tmp_path.iterdir()] == [".log"]

    def test_grandchild_holding_pipe_does_not_hang(self, tmp_path, capfd):
        script = (
            "import subprocess, sys\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "print('done')\n"
        )
        assert run(py(script), tmp_path) == 0
        assert capfd.readouterr().out == "done\n"
