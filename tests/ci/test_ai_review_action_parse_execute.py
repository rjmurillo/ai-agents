from __future__ import annotations

from collections.abc import Sequence

from scripts.ci import execute_ai_review_post_script as execute
from scripts.ci import parse_ai_review_output as parse


def test_parse_output_uses_last_literal_verdict_and_writes_outputs(tmp_path):
    result = parse.parse_output(
        "VERDICT: WARN\n"
        'LABEL: bug\nLABEL: area-workflows\nMILESTONE: v1.1\n{"verdict":"FAIL"}\n'
        "VERDICT: PASS\n"
    )
    output_path = tmp_path / "github-output.txt"

    parse.publish_result(result, output_path)

    assert result == parse.ParseResult(
        verdict="PASS",
        labels='["bug","area-workflows"]',
        milestone="v1.1",
        exit_code=0,
    )
    assert output_path.read_text(encoding="utf-8") == (
        "verdict=PASS\n"
        'labels=["bug","area-workflows"]\n'
        "milestone=v1.1\n"
        "exit_code=0\n"
    )


def test_parse_output_falls_back_to_json_verdict_and_blocks_unknown(capsys):
    result = parse.parse_output('{"verdict":"UNKNOWN"}\nLABEL: technical-debt\n')

    assert result.verdict == "UNKNOWN"
    assert result.labels == '["technical-debt"]'
    assert result.exit_code == 1
    assert "Verdict extracted from JSON" in capsys.readouterr().out


def test_parse_output_returns_needs_review_for_template_or_missing_verdict(capsys):
    result = parse.parse_output("VERDICT: [PASS|WARN|CRITICAL_FAIL]\n")

    assert result.verdict == "NEEDS_REVIEW"
    assert result.exit_code == 1
    assert "No explicit VERDICT" in capsys.readouterr().out


def test_parse_main_returns_config_error_without_required_env(monkeypatch):
    monkeypatch.delenv("AI_REVIEW_OUTPUT_FILE", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert parse.main([]) == 2


def test_execute_post_script_invokes_python_script_with_expected_arguments(tmp_path):
    script = tmp_path / "post.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> execute.CommandResult:
        calls.append(tuple(argv))
        return execute.CommandResult(0)

    exit_code = execute.execute_post_script(
        env={
            "EXECUTE_SCRIPT": str(script),
            "PR_NUMBER": "123",
            "AI_VERDICT": "PASS",
            "AI_FINDINGS": "findings",
        },
        runner=runner,
    )

    assert exit_code == 0
    assert calls == [
        (
            "python3",
            str(script),
            "--pr-number",
            "123",
            "--verdict",
            "PASS",
            "--findings-json",
            "findings",
        )
    ]


def test_execute_post_script_returns_logic_error_for_unsupported_script(tmp_path):
    script = tmp_path / "post.txt"
    script.write_text("nope\n", encoding="utf-8")

    assert execute.execute_post_script(env={"EXECUTE_SCRIPT": str(script)}) == 1


def test_execute_post_script_returns_child_exit_code(tmp_path):
    script = tmp_path / "post.py"
    script.write_text("print('fail')\n", encoding="utf-8")

    exit_code = execute.execute_post_script(
        env={"EXECUTE_SCRIPT": str(script)},
        runner=lambda _argv: execute.CommandResult(4),
    )

    assert exit_code == 4


def test_execute_main_returns_config_error_for_unexpected_arguments():
    assert execute.main(["extra"]) == 2
