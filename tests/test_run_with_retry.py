"""Tests for .github/scripts/run_with_retry.py

Validates ADR-035 exit code handling: retry on exit 3, fail-fast on 2/4.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "scripts"
    / "run_with_retry.py"
)


def _run(
    inner_exit_code: int | str,
    *,
    max_retries: int = 2,
    retry_delay: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Run the wrapper around a command that exits with a specific code."""
    inner = f"raise SystemExit({inner_exit_code})"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--max-retries",
            str(max_retries),
            "--retry-delay",
            str(retry_delay),
            "--",
            sys.executable,
            "-c",
            inner,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestExitCodeZeroSuccess:
    def test_returns_zero_on_success(self) -> None:
        result = _run(0)
        assert result.returncode == 0


class TestExitCodeOnePassthrough:
    def test_returns_one_for_logic_error(self) -> None:
        result = _run(1)
        assert result.returncode == 1


class TestExitCodeTwoConfigError:
    def test_fails_fast_with_exit_two(self) -> None:
        result = _run(2)
        assert result.returncode == 2
        assert "Configuration error" in result.stdout

    def test_no_retry_on_config_error(self) -> None:
        """Config errors must not retry. Verify via a counter file."""
        result = _run(2, max_retries=2, retry_delay=0)
        assert result.returncode == 2
        assert "Retry" not in result.stdout


class TestExitCodeThreeTransientRetry:
    def test_retries_then_fails(self) -> None:
        result = _run(3, max_retries=1, retry_delay=0)
        assert result.returncode == 3  # ADR-035: preserve exit code
        assert "Transient failure" in result.stdout

    def test_succeeds_after_transient_recovery(self, tmp_path: Path) -> None:
        counter = tmp_path / "counter"
        counter.write_text("0")
        script = (
            f"import pathlib; "
            f"p = pathlib.Path(r'{counter}'); "
            f"c = int(p.read_text()) + 1; "
            f"p.write_text(str(c)); "
            f"raise SystemExit(3 if c <= 1 else 0)"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--max-retries",
                "2",
                "--retry-delay",
                "0",
                "--",
                sys.executable,
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

    def test_exhausts_all_retries(self) -> None:
        result = _run(3, max_retries=2, retry_delay=0)
        assert result.returncode == 3  # ADR-035: preserve exit code
        assert "after 3 attempts" in result.stdout


class TestExitCodeFourAuthError:
    def test_fails_fast_with_exit_four(self) -> None:
        result = _run(4, max_retries=2, retry_delay=0)
        assert result.returncode == 4  # ADR-035: preserve exit code
        assert "Authentication error" in result.stdout

    def test_no_retry_on_auth_error(self) -> None:
        result = _run(4, max_retries=2, retry_delay=0)
        assert "Retry" not in result.stdout


class TestUnknownExitCode:
    def test_passthrough_unknown_code(self) -> None:
        result = _run(42)
        assert result.returncode == 42


class TestCliParsing:
    def test_no_command_exits_with_error(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_command_without_separator(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), sys.executable, "-c", "pass"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
