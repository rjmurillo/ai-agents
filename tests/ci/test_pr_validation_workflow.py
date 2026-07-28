from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "ci"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-validation.yml"


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


description_mod = _load_module("map_pr_description_result")
qa_mod = _load_module("check_pr_qa_report")
report_mod = _load_module("build_pr_validation_report")
label_mod = _load_module("update_needs_split_label")
enforce_mod = _load_module("enforce_pr_validation")


def _set_output(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [(0, "PASS"), (1, "FAIL"), (2, "ERROR"), (99, "ERROR")],
)
def test_description_result_maps_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    expected: str,
):
    output = tmp_path / "github-output.txt"
    calls: list[list[str]] = []
    _set_output(monkeypatch, output)
    monkeypatch.setenv("PR_NUMBER", "42")

    def fake_run(args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert check is False
        calls.append(args)
        return subprocess.CompletedProcess(args, exit_code)

    monkeypatch.setattr(description_mod.subprocess, "run", fake_run)

    assert description_mod.main() == 0
    assert calls == [
        [
            "python3",
            "scripts/validation/pr_description.py",
            "--pr-number",
            "42",
            "--ci",
        ]
    ]
    assert output.read_text(encoding="utf-8") == f"validation_result={expected}\n"


def test_description_result_missing_output_is_config_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(
        description_mod.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0),
    )

    assert description_mod.main() == 2
    assert "::error::GITHUB_OUTPUT is required" in capsys.readouterr().err


def test_qa_report_detects_code_changes_and_existing_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    output = tmp_path / "github-output.txt"
    report_dir = tmp_path / ".agents" / "qa"
    report_dir.mkdir(parents=True)
    (report_dir / "qa-pr-42.md").write_text("ok\n", encoding="utf-8")
    _set_output(monkeypatch, output)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.chdir(tmp_path)

    def fake_run(
        args: list[str],
        *,
        check: bool,
        stdout: int,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert stdout is subprocess.PIPE
        assert text is True
        return subprocess.CompletedProcess(args, 0, "src/app.py\n.agents/note.md\n")

    monkeypatch.setattr(qa_mod.subprocess, "run", fake_run)

    assert qa_mod.main() == 0
    assert output.read_text(encoding="utf-8") == (
        "has_code_changes=True\n"
        "qa_report_exists=true\n"
        "qa_report=qa-pr-42.md\n"
    )
    assert "✓ QA report found: qa-pr-42.md" in capsys.readouterr().out


def test_qa_report_skips_when_only_agents_files_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "github-output.txt"
    _set_output(monkeypatch, output)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        qa_mod.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, ".agents/session.json\n"),
    )

    assert qa_mod.main() == 0
    assert output.read_text(encoding="utf-8") == (
        "has_code_changes=False\n"
        "qa_report_exists=N/A\n"
    )


def test_qa_report_warns_when_code_changes_lack_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    output = tmp_path / "github-output.txt"
    _set_output(monkeypatch, output)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        qa_mod.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "workflow.yml\n"),
    )

    assert qa_mod.main() == 0
    assert output.read_text(encoding="utf-8") == (
        "has_code_changes=True\n"
        "qa_report_exists=false\n"
    )
    assert "::warning::No QA report found for code changes" in capsys.readouterr().out


def test_report_builds_fail_status_and_outputs_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "github-output.txt"
    report = tmp_path / "pr-validation-report.md"
    _set_output(monkeypatch, output)
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.setenv("DESCRIPTION_RESULT", "FAIL")
    monkeypatch.setenv("HAS_CODE_CHANGES", "true")
    monkeypatch.setenv("QA_EXISTS", "false")
    monkeypatch.setenv("KEYWORDS_STATUS", "WARN")
    monkeypatch.setenv("TEMPLATE_STATUS", "WARN")
    monkeypatch.setenv("TEMPLATE_MESSAGE", "Template is missing")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    assert report_mod.main() == 0
    assert output.read_text(encoding="utf-8") == "overall_status=FAIL\n"
    text = report.read_text(encoding="utf-8")
    assert "> ❌ **Status: FAIL**" in text
    assert "- PR description does not match actual changes" in text
    assert "- No GitHub issue linking keywords found" in text
    assert "- Template is missing" in text
    assert "- QA report not found for code changes" in text


def test_report_empty_description_becomes_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "github-output.txt"
    report = tmp_path / "pr-validation-report.md"
    _set_output(monkeypatch, output)
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.delenv("DESCRIPTION_RESULT", raising=False)

    assert report_mod.main() == 0
    assert output.read_text(encoding="utf-8") == "overall_status=ERROR\n"
    assert "> ❌ **Status: ERROR**" in report.read_text(encoding="utf-8")


def test_report_surfaces_bypass_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "github-output.txt"
    report = tmp_path / "pr-validation-report.md"
    _set_output(monkeypatch, output)
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.setenv("DESCRIPTION_RESULT", "PASS")
    monkeypatch.setenv("BYPASS_USED", "true")
    monkeypatch.setenv("BYPASS_LABEL", "validation-bypass")
    monkeypatch.setenv("BYPASS_COUNT", "2")

    assert report_mod.main() == 0
    text = report.read_text(encoding="utf-8")
    assert output.read_text(encoding="utf-8") == "overall_status=BYPASSED\n"
    assert "BYPASSED (label override)" in text
    assert "validation-bypass" in text


def test_report_reads_powershell_boolean_output_case_insensitively(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "github-output.txt"
    report = tmp_path / "pr-validation-report.md"
    _set_output(monkeypatch, output)
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.setenv("DESCRIPTION_RESULT", "PASS")
    monkeypatch.setenv("BYPASS_USED", "True")
    monkeypatch.setenv("BYPASS_LABEL", "validation-bypass")
    monkeypatch.setenv("BYPASS_COUNT", "2")

    assert report_mod.main() == 0
    text = report.read_text(encoding="utf-8")
    assert output.read_text(encoding="utf-8") == "overall_status=BYPASSED\n"
    assert "BYPASSED (label override)" in text


def test_report_missing_output_is_config_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert report_mod.main() == 2


def test_workflow_delegates_first_pr_validation_blocks():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "python3 scripts/ci/map_pr_description_result.py" in workflow
    assert "python3 scripts/ci/check_pr_qa_report.py" in workflow
    assert "python3 scripts/ci/build_pr_validation_report.py" in workflow
    assert "python3 scripts/validation/pr_description.py --pr-number" not in workflow
    assert "Write-Host \"Checking for QA report...\"" not in workflow


def test_add_needs_split_label_posts_when_missing(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(
        args: list[str],
        *,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, input_text))
        if args[:2] == ["api", "repos/o/r/issues/42/labels"]:
            return subprocess.CompletedProcess(args, 0, "bug\n")
        return subprocess.CompletedProcess(args, 0, "")

    monkeypatch.setattr(label_mod, "_run_gh", fake_run)

    assert label_mod.add_label("o/r", "42") == 0
    assert calls == [
        (["api", "repos/o/r/issues/42/labels", "--jq", ".[].name"], None),
        (
            [
                "api",
                "-X",
                "POST",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/o/r/issues/42/labels",
                "--input",
                "-",
            ],
            '{"labels":["needs-split"]}',
        ),
    ]


def test_add_needs_split_label_skips_when_present(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "needs-split\n")

    monkeypatch.setattr(label_mod, "_run_gh", fake_run)

    assert label_mod.add_label("o/r", "42") == 0
    assert calls == [["api", "repos/o/r/issues/42/labels", "--jq", ".[].name"]]


def test_add_needs_split_label_fetch_failure_is_advisory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(
        label_mod,
        "_run_gh",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 3, ""),
    )

    assert label_mod.add_label("o/r", "42") == 0
    assert "skipping advisory 'needs-split' label" in capsys.readouterr().err


def test_remove_needs_split_label_deletes_when_present(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:2] == ["api", "repos/o/r/issues/42/labels"]:
            return subprocess.CompletedProcess(args, 0, "needs-split\n")
        return subprocess.CompletedProcess(args, 0, "")

    monkeypatch.setattr(label_mod, "_run_gh", fake_run)

    assert label_mod.remove_label("o/r", "42") == 0
    assert calls[-1] == [
        "api",
        "-X",
        "DELETE",
        "-H",
        "Accept: application/vnd.github+json",
        "repos/o/r/issues/42/labels/needs-split",
    ]


def test_remove_needs_split_label_skips_when_absent(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "bug\n")

    monkeypatch.setattr(label_mod, "_run_gh", fake_run)

    assert label_mod.remove_label("o/r", "42") == 0
    assert calls == [["api", "repos/o/r/issues/42/labels", "--jq", ".[].name"]]


def test_enforce_fails_on_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("OVERALL_STATUS", "ERROR")

    assert enforce_mod.main() == 1
    assert "::error::PR validation failed: ERROR" in capsys.readouterr().err


def test_enforce_blocks_commit_limit_without_bypass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("OVERALL_STATUS", "PASS")
    monkeypatch.setenv("COMMIT_STATUS", "BLOCKED")
    monkeypatch.setenv("COMMIT_COUNT", "21")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(
        enforce_mod,
        "_fetch_labels",
        lambda repository, pr_number: (0, ["bug"]),
    )

    assert enforce_mod.main() == 1
    assert "PR has 21 commits" in capsys.readouterr().err


def test_enforce_allows_commit_limit_bypass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("OVERALL_STATUS", "PASS")
    monkeypatch.setenv("COMMIT_STATUS", "BLOCKED")
    monkeypatch.setenv("COMMIT_COUNT", "21")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(
        enforce_mod,
        "_fetch_labels",
        lambda repository, pr_number: (0, ["commit-limit-bypass"]),
    )

    assert enforce_mod.main() == 0
    output = capsys.readouterr().out
    assert "::warning::Commit limit bypassed" in output
    assert "✓ PR validation passed" in output


def test_enforce_label_fetch_failure_is_blocking(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("OVERALL_STATUS", "PASS")
    monkeypatch.setenv("COMMIT_STATUS", "BLOCKED")
    monkeypatch.setenv("PR_NUMBER", "42")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(enforce_mod, "_fetch_labels", lambda repository, pr_number: (3, []))

    assert enforce_mod.main() == 1
    assert "Failed to fetch PR labels" in capsys.readouterr().err


def test_enforce_passes_when_no_blocking_inputs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("OVERALL_STATUS", "PASS")
    monkeypatch.setenv("COMMIT_STATUS", "OK")

    assert enforce_mod.main() == 0
    assert "✓ PR validation passed" in capsys.readouterr().out


def test_workflow_delegates_all_pr_validation_blocks():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "python3 scripts/ci/update_needs_split_label.py --mode add" in workflow
    assert "python3 scripts/ci/update_needs_split_label.py --mode remove" in workflow
    assert "python3 scripts/ci/enforce_pr_validation.py" in workflow
    assert "python3 scripts/ci/adr006_run_block_scanner.py --max 71" in workflow
    assert "gh api `\n            -X DELETE" not in workflow
    assert "Write-Error \"PR has $env:COMMIT_COUNT commits" not in workflow
