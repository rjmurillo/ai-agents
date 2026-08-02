# taste-lint: ignore file-size -- PR #4181 keeps the harness and tests paired.

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Generator, Sequence
from pathlib import Path

import pytest

from scripts.testing.mutation_harness import (
    EXIT_EXTERNAL_ERROR,
    GIT_ROOT_TIMEOUT_SECONDS,
    BatteryConfigError,
    MutationEntry,
    MutationRunner,
    MutationTimeoutError,
    _find_containment_root,
    _resolve_entry_path,
    main,
    validate_battery,
)

_WORKSPACE = Path(".pytest_tmp/mutation_harness")


@pytest.fixture(autouse=True)
def clean_workspace() -> Generator[None]:
    if _WORKSPACE.exists():
        shutil.rmtree(_WORKSPACE)
    _WORKSPACE.mkdir(parents=True)
    yield
    if _WORKSPACE.exists():
        shutil.rmtree(_WORKSPACE)


def _case_dir(name: str) -> Path:
    path = _WORKSPACE / name
    path.mkdir(parents=True)
    return path


def _entry(
    source: Path,
    *,
    old: str = "return True",
    new: str = "return False",
    command: tuple[str, ...] = (sys.executable, "-c", "raise SystemExit(1)"),
    timeout_seconds: int | float = 300,
) -> MutationEntry:
    return MutationEntry("case", source, old, new, command, timeout_seconds)


def _write_module(path: Path, return_value: str) -> None:
    source = f'def identity() -> str:\n    return "{return_value}"\n'
    path.write_text(source, encoding="utf-8")


def _prime_cache(module_path: Path) -> float:
    original_mtime = os.stat(module_path).st_mtime
    probe = (
        "import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('subject', {str(module_path)!r}); "
        "module = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module)"
    )
    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        env=env,
        check=True,
        timeout=30,
    )
    assert (module_path.parent / "__pycache__").exists()
    return original_mtime


def _run_cli(battery: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.testing.mutation_harness", str(battery)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )


class TestBatteryValidation:
    def test_refuses_anchor_occurring_zero_times(self) -> None:
        workspace = _case_dir("zero")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")

        problems = validate_battery([_entry(source, old="return False", new="return None")])

        assert len(problems) == 1
        assert "count is 0" in problems[0].message

    def test_refuses_anchor_occurring_more_than_once(self) -> None:
        workspace = _case_dir("multiple")
        source = workspace / "subject.py"
        source.write_text("return True\nreturn True\n", encoding="utf-8")

        problems = validate_battery([_entry(source)])

        assert len(problems) == 1
        assert "count is 2" in problems[0].message

    def test_accepts_anchor_occurring_exactly_once(self) -> None:
        workspace = _case_dir("once")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")

        problems = validate_battery([_entry(source)])

        assert problems == []

    def test_refuses_identity_mutation(self) -> None:
        workspace = _case_dir("identity")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")

        problems = validate_battery([_entry(source, old="return True", new="return True")])

        assert len(problems) == 1
        assert "identity mutation" in problems[0].message

    def test_rejects_relative_path_escape(self) -> None:
        workspace = _case_dir("relative_escape")

        with pytest.raises(BatteryConfigError):
            _resolve_entry_path(workspace, "../../../../..", Path.cwd())

    def test_rejects_absolute_path_escape(self) -> None:
        workspace = _case_dir("absolute_escape")
        outside = Path.cwd().parent / "outside.py"

        with pytest.raises(BatteryConfigError):
            _resolve_entry_path(workspace, str(outside), Path.cwd())

    def test_accepts_path_inside_containment_root(self) -> None:
        workspace = _case_dir("inside_root")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")

        resolved = _resolve_entry_path(workspace, "subject.py", Path.cwd())

        assert resolved == source.resolve()


class TestMutationResults:
    def test_reports_caught_when_command_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        workspace = _case_dir("caught")
        source = workspace / "subject.py"
        original = "def guard() -> bool:\n    return True\n"
        source.write_text(original, encoding="utf-8")
        runner = MutationRunner(cwd=workspace)

        results = runner.run_all([_entry(source)])

        assert results[0].caught is True
        assert "CAUGHT case returncode=1" in capsys.readouterr().out

    def test_reports_missed_when_command_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        workspace = _case_dir("missed")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")
        runner = MutationRunner(cwd=workspace)

        results = runner.run_all([_entry(source, command=(sys.executable, "-c", ""))])

        assert results[0].caught is False
        assert "MISSED case returncode=0" in capsys.readouterr().out

    def test_run_command_reports_timeout_with_command_and_limit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = _case_dir("timeout")
        runner = MutationRunner(cwd=workspace)
        observed: dict[str, object] = {}

        def timeout_run(
            command: Sequence[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            observed.update(kwargs)
            timeout = kwargs["timeout"]
            assert isinstance(timeout, int | float)
            raise subprocess.TimeoutExpired(command, timeout)

        monkeypatch.setattr(subprocess, "run", timeout_run)

        with pytest.raises(MutationTimeoutError) as exc_info:
            runner._run_command(("python", "-c", "pass"), timeout_seconds=7)

        assert "command timed out after 7s: python -c pass" in str(
            exc_info.value
        ), "timeout diagnostic should name the command and limit"
        assert observed["timeout"] == 7, "subprocess timeout should use entry limit"
        assert observed["encoding"] == "utf-8"
        assert observed["errors"] == "replace", "subprocess decode errors should be replaced"

    def test_find_containment_root_replaces_decode_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        observed: dict[str, object] = {}

        def fake_run(
            command: Sequence[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            observed.update(kwargs)
            return subprocess.CompletedProcess(command, 0, stdout=str(Path.cwd().resolve()))

        monkeypatch.setattr(subprocess, "run", fake_run)

        root = _find_containment_root()

        assert root == Path.cwd().resolve()
        assert observed["timeout"] == GIT_ROOT_TIMEOUT_SECONDS
        assert observed["encoding"] == "utf-8"
        assert observed["errors"] == "replace", "git decode errors should be replaced"

    def test_find_containment_root_rejects_redirected_worktree(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = _case_dir("redirected_root")

        def fake_run(
            command: Sequence[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, stdout=str(workspace.resolve()))

        monkeypatch.setattr(subprocess, "run", fake_run)

        try:
            _find_containment_root()
        except BatteryConfigError as exc:
            message = str(exc)
        else:
            pytest.fail("redirected git roots should fail before mutations can write")

        assert "is outside git top-level" in message, (
            "redirected git roots should fail before mutations can write"
        )

    def test_find_containment_root_reports_timeout(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def timeout_run(
            command: Sequence[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            timeout = kwargs["timeout"]
            assert isinstance(timeout, int | float)
            raise subprocess.TimeoutExpired(command, timeout)

        monkeypatch.setattr(subprocess, "run", timeout_run)

        with pytest.raises(MutationTimeoutError) as exc_info:
            _find_containment_root()

        assert "command timed out after 10s: git rev-parse --show-toplevel" in str(
            exc_info.value
        ), "git timeout diagnostic should name the command and limit"


class TestRestoreSafety:
    def test_restores_source_after_normal_run(self) -> None:
        workspace = _case_dir("restore_normal")
        source = workspace / "subject.py"
        original = "def guard() -> bool:\n    return True\n"
        source.write_text(original, encoding="utf-8")
        runner = MutationRunner(cwd=workspace)

        runner.run_all([_entry(source)])

        assert source.read_text(encoding="utf-8") == original

    def test_restores_source_after_failing_run(self) -> None:
        workspace = _case_dir("restore_failure")
        source = workspace / "subject.py"
        original = "def guard() -> bool:\n    return True\n"
        source.write_text(original, encoding="utf-8")
        runner = MutationRunner(cwd=workspace)

        runner.run_all([_entry(source, command=(sys.executable, "-c", "raise RuntimeError"))])

        assert source.read_text(encoding="utf-8") == original

    def test_restores_source_after_interrupt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        workspace = _case_dir("restore_interrupt")
        source = workspace / "subject.py"
        original = "def guard() -> bool:\n    return True\n"
        source.write_text(original, encoding="utf-8")
        runner = MutationRunner(cwd=workspace)

        def interrupt(
            command: tuple[str, ...],
            timeout_seconds: int | float = 300,
        ) -> subprocess.CompletedProcess[str]:
            raise KeyboardInterrupt

        monkeypatch.setattr(runner, "_run_command", interrupt)

        with pytest.raises(KeyboardInterrupt):
            runner.run_all([_entry(source)])

        assert source.read_text(encoding="utf-8") == original

    def test_restores_source_after_command_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        workspace = _case_dir("restore_exception")
        source = workspace / "subject.py"
        original = "def guard() -> bool:\n    return True\n"
        source.write_text(original, encoding="utf-8")
        runner = MutationRunner(cwd=workspace)

        def fail(
            command: tuple[str, ...],
            timeout_seconds: int | float = 300,
        ) -> subprocess.CompletedProcess[str]:
            raise OSError("process failed before exit code")

        monkeypatch.setattr(runner, "_run_command", fail)

        with pytest.raises(OSError):
            runner.run_all([_entry(source)])

        assert source.read_text(encoding="utf-8") == original


class TestBytecodeIsolation:
    def test_same_length_mutation_does_not_reuse_stale_bytecode(self) -> None:
        workspace = _case_dir("bytecode")
        module = workspace / "subject.py"
        _write_module(module, "a")
        original_mtime = _prime_cache(module)
        os.utime(module, (original_mtime, original_mtime))
        command = (
            sys.executable,
            "-c",
            (
                "import importlib.util; "
                "spec = importlib.util.spec_from_file_location"
                f"('subject', {str(module.resolve())!r}); "
                "module = importlib.util.module_from_spec(spec); "
                "spec.loader.exec_module(module); "
                "raise SystemExit(0 if module.identity() == 'b' else 1)"
            ),
        )
        runner = MutationRunner(cwd=workspace)

        result = runner.run_all([_entry(module, old='"a"', new='"b"', command=command)])[0]

        assert result.caught is False

    def test_child_process_receives_no_bytecode_environment(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = _case_dir("env")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")
        monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
        command = (
            sys.executable,
            "-c",
            "import os; "
            "raise SystemExit(0 if os.environ.get('PYTHONDONTWRITEBYTECODE') == '1' else 1)",
        )
        runner = MutationRunner(cwd=workspace)

        result = runner.run_all([_entry(source, command=command)])[0]

        assert result.caught is False
        assert "MISSED case returncode=0" in capsys.readouterr().out


class TestStreaming:
    def test_flushes_after_each_result_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        workspace = _case_dir("flush")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")
        runner = MutationRunner(cwd=workspace)
        flush_values: list[bool] = []

        def capture_print(*args: object, **kwargs: object) -> None:
            flush_values.append(kwargs.get("flush") is True)

        monkeypatch.setattr("builtins.print", capture_print)

        runner.run_all([_entry(source)])

        assert flush_values == [True]


class TestCli:
    def test_timeout_has_external_error_exit_code(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = _case_dir("cli_timeout")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")
        battery = workspace / "battery.json"
        battery.write_text(
            json.dumps(
                {
                    "command": [sys.executable, "-c", "pass"],
                    "timeout_seconds": 7,
                    "entries": [
                        {
                            "name": "timeout",
                            "path": "subject.py",
                            "old": "return True",
                            "new": "return False",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        def timeout(
            self: MutationRunner,
            command: Sequence[str],
            timeout_seconds: int | float = 300,
        ) -> subprocess.CompletedProcess[str]:
            raise MutationTimeoutError(command, timeout_seconds)

        monkeypatch.setattr(MutationRunner, "_run_command", timeout)

        exit_code = main([str(battery)])

        assert exit_code == EXIT_EXTERNAL_ERROR, "timeout should map to external error"
        assert "EXTERNAL_ERROR command timed out after 7s" in capsys.readouterr().err

    def test_real_timeout_has_external_error_exit_code(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        workspace = _case_dir("cli_real_timeout")
        source = workspace / "subject.py"
        original = "def guard() -> bool:\n    return True\n"
        source.write_text(original, encoding="utf-8")
        battery = workspace / "battery.json"
        battery.write_text(
            json.dumps(
                {
                    "command": [sys.executable, "-c", "import time; time.sleep(1)"],
                    "timeout_seconds": 0.01,
                    "entries": [
                        {
                            "name": "real-timeout",
                            "path": "subject.py",
                            "old": "return True",
                            "new": "return False",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        exit_code = main([str(battery)])

        assert exit_code == EXIT_EXTERNAL_ERROR, "real timeout should map to exit 3"
        assert "EXTERNAL_ERROR command timed out after 0.01s" in capsys.readouterr().err
        assert source.read_text(encoding="utf-8") == original

    def test_valid_battery_runs_without_config_error(self) -> None:
        workspace = _case_dir("cli_valid")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")
        battery = workspace / "battery.json"
        battery.write_text(
            json.dumps(
                {
                    "command": [sys.executable, "-c", "raise SystemExit(1)"],
                    "entries": [
                        {
                            "name": "caught",
                            "path": "subject.py",
                            "old": "return True",
                            "new": "return False",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = _run_cli(battery)

        assert result.returncode == 0

    def test_config_error_has_distinct_exit_code(self) -> None:
        workspace = _case_dir("cli_config")
        source = workspace / "subject.py"
        source.write_text("def guard() -> bool:\n    return True\n", encoding="utf-8")
        battery = workspace / "battery.json"
        battery.write_text(
            json.dumps(
                {
                    "command": [sys.executable, "-c", "pass"],
                    "entries": [
                        {
                            "name": "bad",
                            "path": "subject.py",
                            "old": "missing",
                            "new": "mutated",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = _run_cli(battery)

        assert result.returncode == 2
        assert "CONFIG_ERROR" in result.stderr

    def test_malformed_json_battery_has_config_exit_code(self) -> None:
        workspace = _case_dir("cli_malformed_json")
        battery = workspace / "battery.json"
        battery.write_text('{"entries": [', encoding="utf-8")

        result = _run_cli(battery)

        assert result.returncode == 2

    def test_empty_battery_file_has_config_exit_code(self) -> None:
        workspace = _case_dir("cli_empty_json")
        battery = workspace / "battery.json"
        battery.write_text("", encoding="utf-8")

        result = _run_cli(battery)

        assert result.returncode == 2

    def test_json_scalar_battery_has_config_exit_code(self) -> None:
        workspace = _case_dir("cli_scalar_json")
        battery = workspace / "battery.json"
        battery.write_text("[]", encoding="utf-8")

        result = _run_cli(battery)

        assert result.returncode == 2

    def test_path_escape_battery_has_config_exit_code(self) -> None:
        workspace = _case_dir("cli_path_escape")
        battery = workspace / "battery.json"
        battery.write_text(
            json.dumps(
                {
                    "command": [sys.executable, "-c", "pass"],
                    "entries": [
                        {
                            "name": "escape",
                            "path": "../../../../..",
                            "old": "x",
                            "new": "y",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = _run_cli(battery)

        assert result.returncode == 2
