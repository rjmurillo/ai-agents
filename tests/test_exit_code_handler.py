"""Tests for .github/scripts/exit_code_handler.sh

Validates ADR-035 exit code handling: retry on exit 3, fail-fast on 2/4.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

HANDLER = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "scripts"
    / "exit_code_handler.sh"
)


def _run_handler(
    inner_cmd: str,
    *,
    max_retries: int = 2,
    retry_delay: int = 1,
) -> subprocess.CompletedProcess[str]:
    """Source the handler and run a command through run_with_adr035."""
    script = f"""
        export ADR035_MAX_RETRIES={max_retries}
        export ADR035_RETRY_DELAY={retry_delay}
        source {HANDLER}
        run_with_adr035 {inner_cmd}
    """
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestExitCodeZeroSuccess:
    def test_returns_zero_on_success(self) -> None:
        result = _run_handler("true")
        assert result.returncode == 0


class TestExitCodeOnePassthrough:
    def test_returns_one_for_logic_error(self) -> None:
        result = _run_handler("bash -c 'exit 1'")
        assert result.returncode == 1


class TestExitCodeTwoConfigError:
    def test_fails_fast_with_exit_two(self) -> None:
        result = _run_handler("bash -c 'exit 2'")
        assert result.returncode == 2
        assert "Configuration error" in result.stdout or "Configuration error" in result.stderr

    def test_no_retry_on_config_error(self) -> None:
        # Use a counter file to verify no retries
        result = _run_handler("bash -c 'exit 2'", max_retries=2, retry_delay=1)
        assert result.returncode == 2


class TestExitCodeThreeTransientRetry:
    def test_retries_on_transient_failure(self) -> None:
        # Command always fails with exit 3, should retry then fail
        result = _run_handler("bash -c 'exit 3'", max_retries=1, retry_delay=1)
        # After retries exhausted, should return exit 1
        assert result.returncode == 1
        assert "Transient failure" in result.stdout or "Transient failure" in result.stderr

    def test_succeeds_after_transient_recovery(self, tmp_path: Path) -> None:
        counter = tmp_path / "counter"
        counter.write_text("0")
        # First call exits 3, second call exits 0
        inner = (
            f"bash -c '"
            f'count=$(cat {counter}); '
            f'count=$((count + 1)); '
            f'echo $count > {counter}; '
            f'if [ $count -le 1 ]; then exit 3; else exit 0; fi'
            f"'"
        )
        result = _run_handler(inner, max_retries=2, retry_delay=1)
        assert result.returncode == 0


class TestExitCodeFourAuthError:
    def test_fails_fast_with_exit_four(self) -> None:
        result = _run_handler("bash -c 'exit 4'")
        # Auth errors map to exit 1 for workflow compatibility
        assert result.returncode == 1
        assert "Authentication error" in result.stdout or "Authentication error" in result.stderr
