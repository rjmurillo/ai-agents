from __future__ import annotations

from collections.abc import Sequence

from scripts.ci import install_copilot_cli as install
from scripts.ci import load_ai_review_prompt as prompt
from scripts.ci import verify_github_auth as auth


def test_install_copilot_cli_writes_version_output(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> install.CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "npm":
            return install.CommandResult(0, "installed\n", "")
        return install.CommandResult(0, "1.0.63\n", "")

    output_path = tmp_path / "github-output.txt"
    exit_code = install.install_copilot_cli(
        output_path=output_path,
        runner=runner,
        which=lambda name: "/usr/bin/copilot" if name == "copilot" else None,
    )

    assert exit_code == 0
    assert calls == [
        ("npm", "install", "-g", "@github/copilot@1.0.63"),
        ("copilot", "--no-auto-update", "--version"),
    ]
    assert output_path.read_text(encoding="utf-8") == "copilot_version=1.0.63\n"


def test_install_copilot_cli_warns_with_runbook_on_version_drift(tmp_path, capsys):
    def runner(argv: Sequence[str]) -> install.CommandResult:
        if argv[0] == "npm":
            return install.CommandResult(0, "installed\n", "")
        return install.CommandResult(0, "9.9.9\n", "")

    exit_code = install.install_copilot_cli(
        output_path=tmp_path / "github-output.txt",
        runner=runner,
        which=lambda name: "/usr/bin/copilot" if name == "copilot" else None,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "::warning::Expected version" in out
    assert (
        ".serena/memories/copilot/copilot-cli-frontmatter-regression-runbook.md" in out
    )
    assert "ADR-094" in out
    assert "ADR-044" not in out


def test_install_copilot_cli_returns_logic_error_when_binary_missing(tmp_path):
    exit_code = install.install_copilot_cli(
        output_path=tmp_path / "github-output.txt",
        runner=lambda _argv: install.CommandResult(0, "", ""),
        which=lambda _name: None,
    )

    assert exit_code == 1


def test_verify_github_auth_returns_logic_error_when_api_check_fails():
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> auth.CommandResult:
        calls.append(tuple(argv))
        if argv == ["gh", "auth", "status"]:
            return auth.CommandResult(0, "ok\n", "")
        return auth.CommandResult(1, "", "denied\n")

    assert auth.verify_github_auth(runner) == 1
    assert calls == [("gh", "auth", "status"), ("gh", "api", "user", "-q", ".login")]


def test_load_prompt_uses_explicit_prompt_and_writes_outputs(tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("custom prompt\n", encoding="utf-8")
    prompt_output = tmp_path / "ai-review-prompt.md"
    github_output = tmp_path / "github-output.txt"

    exit_code = prompt.load_prompt(
        prompt_file=str(prompt_file),
        github_output=github_output,
        prompt_output_path=prompt_output,
        default_prompt_path=tmp_path / "missing.md",
    )

    assert exit_code == 0
    assert prompt_output.read_text(encoding="utf-8") == "custom prompt\n"
    output = github_output.read_text(encoding="utf-8")
    assert f"prompt_source={prompt_file}" in output
    assert f"prompt_file={prompt_output}" in output
    assert "prompt_template<<EOF_PROMPT\ncustom prompt\nEOF_PROMPT" in output


def test_load_prompt_uses_fallback_when_no_file_exists(tmp_path):
    prompt_output = tmp_path / "ai-review-prompt.md"
    github_output = tmp_path / "github-output.txt"

    exit_code = prompt.load_prompt(
        prompt_file="",
        github_output=github_output,
        prompt_output_path=prompt_output,
        default_prompt_path=tmp_path / "missing.md",
    )

    assert exit_code == 0
    assert "Analyze the provided context" in prompt_output.read_text(encoding="utf-8")
    assert "prompt_source=generated" in github_output.read_text(encoding="utf-8")


def test_main_functions_return_config_error_for_unexpected_arguments(monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", "unused")

    assert install.main(["extra"]) == 2
    assert auth.main(["extra"]) == 2
    assert prompt.main(["extra"]) == 2


def test_install_run_command_catches_file_not_found_error():
    result = install.run_command(["__nonexistent_binary_xyz__"])

    assert result.returncode == 127
    assert "command not found" in result.stderr


def test_verify_auth_run_command_catches_file_not_found_error():
    result = auth.run_command(["__nonexistent_binary_xyz__"])

    assert result.returncode == 127
    assert "command not found" in result.stderr
