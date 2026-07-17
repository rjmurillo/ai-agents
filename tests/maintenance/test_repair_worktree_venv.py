"""Tests for repair_worktree_venv module.

Moving a git worktree after ``uv`` writes ``.venv`` leaves absolute-path
shebangs in the launcher scripts pointing at the OLD worktree path, so direct
``.venv/bin/*`` calls fail with "bad interpreter". This module detects those
stale shebangs. Tests mock the filesystem (tmp_path); no real worktree move is
required. Both the POSIX ``.venv/bin`` and Windows ``.venv/Scripts`` launcher
paths are covered. Related: Issue #3170.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from scripts.maintenance.repair_worktree_venv import (
    StaleShebang,
    build_report,
    find_launcher_dir,
    interpreter_of_shebang,
    is_stale,
    main,
    parse_args,
    read_shebang,
    repair_command,
    run_repair,
    scan_launcher_dir,
)


def _make_launcher(bin_dir: Path, name: str, interpreter: str) -> Path:
    """Write a fake text launcher whose first line is an interpreter shebang."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / name
    script.write_text(f"#!{interpreter}\n# launcher body\n", encoding="utf-8")
    return script


class TestReadShebang:
    """First-line shebang extraction is defensive against binaries."""

    def test_returns_shebang_line_for_text_launcher(self, tmp_path: Path) -> None:
        script = _make_launcher(tmp_path, "pytest", "/old/root/.venv/bin/python")

        assert read_shebang(script) == "#!/old/root/.venv/bin/python"

    def test_returns_none_for_non_shebang_binary(self, tmp_path: Path) -> None:
        binary = tmp_path / "python"
        binary.write_bytes(b"\x7fELF\x02\x01\x01\x00\xff\xfe")

        assert read_shebang(binary) is None

    def test_returns_none_for_missing_or_broken_symlink(self, tmp_path: Path) -> None:
        broken = tmp_path / "python3"
        try:
            broken.symlink_to(tmp_path / "does-not-exist")
        except OSError:
            pytest.skip("symlink creation not permitted on this platform")

        assert read_shebang(broken) is None


class TestInterpreterOfShebang:
    """Interpreter token parsing, including the env indirection form."""

    def test_extracts_absolute_interpreter(self) -> None:
        interp = interpreter_of_shebang("#!/old/root/.venv/bin/python")
        assert interp == "/old/root/.venv/bin/python"

    def test_extracts_interpreter_ignoring_args(self) -> None:
        interp = interpreter_of_shebang("#!/old/root/.venv/bin/python -s")
        assert interp == "/old/root/.venv/bin/python"

    def test_env_form_returns_none(self) -> None:
        assert interpreter_of_shebang("#!/usr/bin/env python") is None

    def test_non_shebang_returns_none(self) -> None:
        assert interpreter_of_shebang("not a shebang") is None


class TestIsStale:
    """A shebang is stale when its absolute interpreter is not under root/.venv."""

    def test_interpreter_under_venv_is_not_stale(self) -> None:
        assert is_stale("/repo/wt/.venv/bin/python", Path("/repo/wt")) is False

    def test_interpreter_outside_root_is_stale(self) -> None:
        assert is_stale("/old/root/.venv/bin/python", Path("/repo/wt")) is True

    def test_sibling_prefix_is_stale_not_false_negative(self) -> None:
        # /repo/wt is a string prefix of /repo/wt-other but not a parent.
        assert is_stale("/repo/wt-other/.venv/bin/python", Path("/repo/wt")) is True

    def test_nested_old_venv_under_new_root_is_stale(self) -> None:
        # After moving from /data/wt to /data, the old shebang /data/wt/.venv/bin/python
        # is still under /data but is not under /data/.venv. This must be stale.
        assert is_stale("/data/wt/.venv/bin/python", Path("/data")) is True

    def test_relative_interpreter_is_not_stale(self) -> None:
        assert is_stale("python", Path("/repo/wt")) is False


class TestScanLauncherDir:
    """Scanning classifies stale, correct, and non-shebang launchers."""

    def test_flags_stale_absolute_shebang(self, tmp_path: Path) -> None:
        root = tmp_path / "wt"
        bin_dir = root / ".venv" / "bin"
        _make_launcher(bin_dir, "pytest", "/old/root/.venv/bin/python")

        hits = scan_launcher_dir(bin_dir, root)

        expected = StaleShebang(path=bin_dir / "pytest", interpreter="/old/root/.venv/bin/python")
        assert hits == [expected]

    def test_ignores_correct_shebang(self, tmp_path: Path) -> None:
        root = tmp_path / "wt"
        bin_dir = root / ".venv" / "bin"
        _make_launcher(bin_dir, "pytest", str(root / ".venv" / "bin" / "python"))

        assert scan_launcher_dir(bin_dir, root) == []

    def test_ignores_non_shebang_binary(self, tmp_path: Path) -> None:
        root = tmp_path / "wt"
        bin_dir = root / ".venv" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "python").write_bytes(b"\x7fELF binary")

        assert scan_launcher_dir(bin_dir, root) == []

    def test_windows_scripts_launcher_flagged(self, tmp_path: Path) -> None:
        # The Windows launcher dir is .venv/Scripts. Drive-letter absoluteness
        # is Windows-only, so use a POSIX-absolute stale interpreter to exercise
        # the Scripts-dir scan on any host.
        root = tmp_path / "wt"
        scripts_dir = root / ".venv" / "Scripts"
        _make_launcher(scripts_dir, "pytest", "/old/root/.venv/Scripts/python")

        hits = scan_launcher_dir(scripts_dir, root)

        assert len(hits) == 1
        assert hits[0].interpreter == "/old/root/.venv/Scripts/python"


class TestFindLauncherDir:
    """Launcher directory resolves to whichever layout exists."""

    def test_finds_posix_bin(self, tmp_path: Path) -> None:
        (tmp_path / ".venv" / "bin").mkdir(parents=True)

        assert find_launcher_dir(tmp_path / ".venv") == tmp_path / ".venv" / "bin"

    def test_finds_windows_scripts(self, tmp_path: Path) -> None:
        (tmp_path / ".venv" / "Scripts").mkdir(parents=True)

        assert find_launcher_dir(tmp_path / ".venv") == tmp_path / ".venv" / "Scripts"

    def test_returns_none_when_venv_absent(self, tmp_path: Path) -> None:
        assert find_launcher_dir(tmp_path / ".venv") is None


class TestBuildReport:
    """The report reflects stale hits and the venv-present state."""

    def test_reports_missing_venv(self, tmp_path: Path) -> None:
        report = build_report(tmp_path)

        assert report.venv_present is False
        assert report.stale == []

    def test_reports_stale_from_bin(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / ".venv" / "bin"
        _make_launcher(bin_dir, "ruff", "/old/root/.venv/bin/python")

        report = build_report(tmp_path)

        assert report.venv_present is True
        assert len(report.stale) == 1
        assert report.stale[0].path == bin_dir / "ruff"


class TestRepairCommand:
    """Check mode surfaces one exact repair command."""

    def test_repair_command_is_uv_sync_reinstall(self) -> None:
        # The repair command has three load-bearing flags:
        #   --reinstall  recreates the launchers (the actual shebang fix; a plain
        #                sync or --frozen alone is a no-op after a worktree move),
        #   --extra dev  keeps pytest/ruff/mypy in the repaired venv (reinstalling
        #                without it prunes the dev-only launchers people want),
        #   --frozen     reproduces uv.lock without re-resolving (matches CI).
        assert repair_command() == "uv sync --frozen --extra dev --reinstall"

    def test_run_repair_invokes_uv_sync_reinstall(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch(
            "scripts.maintenance.repair_worktree_venv.subprocess.run",
            side_effect=fake_run,
        ):
            run_repair(Path("/some/worktree"))

        # Regression guard: the launcher-rewriting command must keep --reinstall
        # (a no-op --frozen-only sync leaves shebangs stale) AND --extra dev (so
        # the repaired venv still contains pytest/ruff/mypy).
        assert captured["cmd"] == ["uv", "sync", "--frozen", "--extra", "dev", "--reinstall"]
        assert captured["cwd"] == Path("/some/worktree")

    def test_run_repair_routes_uv_output_to_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # uv writes progress to its stdout. run_repair must forward that to this
        # process's stderr, never stdout, so `--json` output stays parseable
        # (stdout is reserved for the report / JSON payload).
        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="Resolved 42 packages\n")

        with mock.patch(
            "scripts.maintenance.repair_worktree_venv.subprocess.run",
            side_effect=fake_run,
        ):
            run_repair(Path("/some/worktree"))

        streams = capsys.readouterr()
        assert "Resolved 42 packages" in streams.err
        assert "Resolved 42 packages" not in streams.out


class TestParseArgs:
    """CLI flags select repair versus check mode."""

    def test_defaults_to_repair(self) -> None:
        args = parse_args([])

        assert args.check is False

    def test_check_flag(self) -> None:
        args = parse_args(["--check"])

        assert args.check is True


class TestMainExitCodes:
    """main() maps the post-repair scan to an ADR-035 exit code."""

    _MODULE = "scripts.maintenance.repair_worktree_venv"

    def test_clean_worktree_returns_0(self, tmp_path: Path) -> None:
        # No .venv -> nothing stale -> success.
        with mock.patch(f"{self._MODULE}.worktree_root", return_value=tmp_path):
            assert main([]) == 0

    def test_check_mode_stale_returns_1(self, tmp_path: Path) -> None:
        _make_launcher(tmp_path / ".venv" / "bin", "ruff", "/old/root/.venv/bin/python")

        with mock.patch(f"{self._MODULE}.worktree_root", return_value=tmp_path):
            # --check mutates nothing; staleness surfaces as exit 1.
            assert main(["--check"]) == 1

    def test_default_repair_clears_stale_returns_0(self, tmp_path: Path) -> None:
        launcher = _make_launcher(
            tmp_path / ".venv" / "bin", "ruff", "/old/root/.venv/bin/python"
        )

        def fake_repair(root: Path) -> None:
            # Simulate a successful reinstall that rewrites the shebang in place.
            launcher.write_text(
                f"#!{tmp_path}/.venv/bin/python\n# launcher body\n", encoding="utf-8"
            )

        with (
            mock.patch(f"{self._MODULE}.worktree_root", return_value=tmp_path),
            mock.patch(f"{self._MODULE}.run_repair", side_effect=fake_repair),
        ):
            assert main([]) == 0

    def test_default_repair_still_stale_returns_3(self, tmp_path: Path) -> None:
        _make_launcher(tmp_path / ".venv" / "bin", "ruff", "/old/root/.venv/bin/python")

        with (
            mock.patch(f"{self._MODULE}.worktree_root", return_value=tmp_path),
            # A no-op repair leaves the shebang stale. `uv sync` reported success
            # yet the environment is still broken: an external repair failure per
            # ADR-035 -> exit 3, not success.
            mock.patch(f"{self._MODULE}.run_repair", return_value=None),
        ):
            assert main([]) == 3

    def test_worktree_root_failure_returns_2_config(self) -> None:
        # Not inside a git worktree -> configuration error per ADR-035 (exit 2).
        with mock.patch(
            f"{self._MODULE}.worktree_root",
            side_effect=RuntimeError("git rev-parse failed: not a git repository"),
        ):
            assert main([]) == 2

    def test_uv_sync_failure_returns_3_external(self, tmp_path: Path) -> None:
        # A stale venv whose repair shells out to `uv sync`, which fails -> the
        # subprocess/tool failure is an external-service error per ADR-035 (exit
        # 3), distinct from the config error (2) of not being in a git repo.
        _make_launcher(tmp_path / ".venv" / "bin", "ruff", "/old/root/.venv/bin/python")

        with (
            mock.patch(f"{self._MODULE}.worktree_root", return_value=tmp_path),
            mock.patch(
                f"{self._MODULE}.run_repair",
                side_effect=RuntimeError("uv sync --frozen --extra dev --reinstall exited 1"),
            ),
        ):
            assert main([]) == 3


class TestJsonOutput:
    """--json surfaces the repair command alongside the stale list."""

    _MODULE = "scripts.maintenance.repair_worktree_venv"

    def test_check_json_includes_repair_command_when_stale(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # --check --json must carry the same actionable command the human
        # --check path prints as "Repair with: ...", so a machine consumer does
        # not have to reconstruct it.
        _make_launcher(tmp_path / ".venv" / "bin", "ruff", "/old/root/.venv/bin/python")

        with mock.patch(f"{self._MODULE}.worktree_root", return_value=tmp_path):
            assert main(["--check", "--json"]) == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["repair_command"] == "uv sync --frozen --extra dev --reinstall"
        assert payload["stale"], "the actionable stale list must still be present"

    def test_json_omits_repair_command_when_clean(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # No .venv -> nothing stale -> no repair command to surface.
        with mock.patch(f"{self._MODULE}.worktree_root", return_value=tmp_path):
            assert main(["--json"]) == 0

        payload = json.loads(capsys.readouterr().out)
        assert "repair_command" not in payload
