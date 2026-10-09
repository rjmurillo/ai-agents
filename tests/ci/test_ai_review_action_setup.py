from __future__ import annotations

from scripts.ci import load_ai_review_prompt as prompt


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


def test_load_prompt_main_returns_config_error_for_unexpected_arguments(monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", "unused")

    assert prompt.main(["extra"]) == 2
