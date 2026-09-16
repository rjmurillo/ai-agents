from __future__ import annotations

from collections.abc import Sequence

from scripts.ci import diagnose_copilot_cli as diagnose


def test_run_diagnostics_writes_healthy_outputs(tmp_path, capsys):
    calls: list[tuple[tuple[str, ...], int | None]] = []

    def runner(argv: Sequence[str], timeout_seconds: int | None = None) -> diagnose.CommandResult:
        calls.append((tuple(argv), timeout_seconds))
        if argv == ["copilot", "--version"]:
            return diagnose.CommandResult(0, "copilot 1.2.3\n", "")
        if argv == ["copilot", "--help"]:
            return diagnose.CommandResult(0, "help", "")
        if argv == ["gh", "api", "user"]:
            return diagnose.CommandResult(0, '{"login":"octocat"}', "")
        if argv == ["gh", "api", "-i", "user"]:
            return diagnose.CommandResult(0, "x-oauth-scopes: repo, workflow\n", "")
        return diagnose.CommandResult(0, "OK", "")

    output_path = tmp_path / "github-output.txt"
    exit_code = diagnose.run_diagnostics(
        env={
            "COPILOT_AGENT": "reviewer",
            "COPILOT_MODEL": "gpt-5",
            "GH_TOKEN": "abc",
            "GITHUB_TOKEN": "defg",
            "HOME": "/home/runner",
            "PATH": "/usr/bin:/opt/npm/bin",
        },
        output_path=output_path,
        runner=runner,
        which=lambda name: "/usr/bin/copilot" if name == "copilot" else None,
    )

    assert exit_code == 0
    assert ("copilot", "--help") in [call[0] for call in calls]
    assert calls[-1][1] == diagnose.COPILOT_TEST_TIMEOUT_SECONDS
    assert "health_status=healthy" in output_path.read_text(encoding="utf-8")
    assert "auth_status=authenticated as octocat, scopes: repo,workflow" in output_path.read_text(
        encoding="utf-8"
    )
    assert "test_prompt: PASSED" in output_path.read_text(encoding="utf-8")
    assert "Health Status: healthy" in capsys.readouterr().out


def test_run_diagnostics_marks_missing_copilot_as_failed(tmp_path):
    def runner(argv: Sequence[str], timeout_seconds: int | None = None) -> diagnose.CommandResult:
        if argv == ["copilot", "--help"]:
            return diagnose.CommandResult(1, "", "missing")
        if argv == ["gh", "api", "user"]:
            return diagnose.CommandResult(1, "", "auth failed")
        return diagnose.CommandResult(1, "", "")

    output_path = tmp_path / "github-output.txt"
    exit_code = diagnose.run_diagnostics(
        env={"COPILOT_AGENT": "reviewer", "COPILOT_MODEL": "gpt-5"},
        output_path=output_path,
        runner=runner,
        which=lambda _name: None,
    )

    output = output_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "health_status=failed" in output
    assert "auth_status=authentication failed" in output
    assert "ERROR: copilot command not found" in output


def test_main_returns_config_error_without_github_output(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert diagnose.main([]) == 2


def test_run_command_catches_file_not_found_error():
    result = diagnose.run_command(["__nonexistent_binary_xyz__"])

    assert result.returncode == 127
    assert "command not found" in result.stderr
    assert result.stdout == ""


def test_health_status_not_downgraded_from_failed_to_degraded(tmp_path):
    """When copilot binary is missing (failed), subsequent checks must not downgrade to degraded."""

    def runner(argv: Sequence[str], timeout_seconds: int | None = None) -> diagnose.CommandResult:
        # All commands fail (binary not found)
        return diagnose.CommandResult(1, "", "not found")

    output_path = tmp_path / "github-output.txt"
    diagnose.run_diagnostics(
        env={"COPILOT_AGENT": "reviewer", "COPILOT_MODEL": "gpt-5"},
        output_path=output_path,
        runner=runner,
        which=lambda _name: None,
    )

    output = output_path.read_text(encoding="utf-8")
    assert "health_status=failed" in output
    # Must NOT contain degraded - once failed, stays failed
    assert "health_status=degraded" not in output


def test_diagnostics_floor_an_unset_model_to_the_cheap_default(tmp_path):
    """An unset COPILOT_MODEL must not reach the CLI as `--model ""`."""
    argv_seen: list[Sequence[str]] = []

    def runner(argv: Sequence[str], timeout_seconds: int | None = None) -> diagnose.CommandResult:
        argv_seen.append(argv)
        if argv[0] == "gh":
            return diagnose.CommandResult(0, "x-oauth-scopes: repo, workflow\n", "")
        return diagnose.CommandResult(0, "OK", "")

    diagnose.run_diagnostics(
        env={
            "COPILOT_AGENT": "reviewer",
            "GH_TOKEN": "abc",
            "HOME": "/home/runner",
            "PATH": "/usr/bin:/opt/npm/bin",
        },
        output_path=tmp_path / "github-output.txt",
        runner=runner,
        which=lambda name: "/usr/bin/copilot" if name == "copilot" else None,
    )

    copilot_calls = [list(argv) for argv in argv_seen if argv[0] == "copilot" and "--model" in argv]
    assert copilot_calls, "diagnostics never invoked copilot with a --model flag"
    for argv in copilot_calls:
        model_value = argv[argv.index("--model") + 1]
        assert model_value == diagnose.DEFAULT_COPILOT_MODEL
        assert model_value != ""
