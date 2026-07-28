from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "ci"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ai-issue-triage.yml"
sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


apply_labels_mod = _load_module("apply_issue_triage_labels")
assign_milestone_mod = _load_module("assign_issue_triage_milestone")
prd_comment_mod = _load_module("post_issue_triage_prd_comment")
summary_comment_mod = _load_module("post_issue_triage_summary_comment")


class FakeGh:
    def __init__(
        self,
        *,
        existing: set[str] | None = None,
        failures: set[tuple[str, ...]] | None = None,
    ):
        self.existing = existing or set()
        self.failures = failures or set()
        self.calls: list[list[str]] = []

    def __call__(
        self,
        args: list[str],
        *,
        discard_stderr: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        key = tuple(args[:3])
        if key in self.failures or tuple(args) in self.failures:
            return subprocess.CompletedProcess(["gh", *args], 1, "")
        if args[:2] == ["label", "list"]:
            query = args[args.index("--search") + 1]
            matches = [label for label in self.existing if label.lower() == query.lower()]
            return subprocess.CompletedProcess(["gh", *args], 0, "\n".join(matches))
        if args[:2] == ["api", "repos/o/r/milestones"]:
            return subprocess.CompletedProcess(["gh", *args], 0, "v1.1\n")
        return subprocess.CompletedProcess(["gh", *args], 0, "")


def test_apply_labels_creates_and_adds_labels(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    fake = FakeGh()
    monkeypatch.setattr(apply_labels_mod, "_run_gh", fake)

    result = apply_labels_mod.apply_labels(
        issue_number="42",
        labels_json='["area-workflows"]',
        priority="P1",
    )

    assert result == 0
    assert [
        "label",
        "create",
        "area-workflows",
        "--description",
        "Auto-created by AI triage",
    ] in fake.calls
    assert ["issue", "edit", "42", "--add-label", "area-workflows"] in fake.calls
    assert [
        "label",
        "create",
        "priority:P1",
        "--description",
        "Priority level",
        "--color",
        "FFA500",
    ] in fake.calls
    assert "Creating label: area-workflows" in capsys.readouterr().out


def test_apply_labels_skips_invalid_label_and_bad_priority(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    fake = FakeGh()
    monkeypatch.setattr(apply_labels_mod, "_run_gh", fake)

    result = apply_labels_mod.apply_labels(
        issue_number="42",
        labels_json='["bad-"]',
        priority="P9",
    )

    assert result == 0
    assert fake.calls == []
    assert "WARNING: Skipping invalid label: bad-" in capsys.readouterr().out


def test_apply_labels_reports_create_and_add_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    fake = FakeGh(failures={("label", "create", "area-workflows"), ("issue", "edit", "42")})
    monkeypatch.setattr(apply_labels_mod, "_run_gh", fake)

    result = apply_labels_mod.apply_labels(
        issue_number="42",
        labels_json='["area-workflows"]',
        priority="",
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "Failed to create labels: area-workflows" in output
    assert "Failed to apply labels: area-workflows" in output


def test_apply_labels_bad_argv_returns_config_error():
    assert apply_labels_mod.main(["unexpected"]) == 2


def test_assign_milestone_edits_existing_milestone(monkeypatch: pytest.MonkeyPatch):
    fake = FakeGh()
    monkeypatch.setattr(assign_milestone_mod, "_run_gh", fake)

    result = assign_milestone_mod.assign_milestone(
        issue_number="42",
        milestone="v1.1",
        repository="o/r",
    )

    assert result == 0
    assert ["issue", "edit", "42", "--milestone", "v1.1"] in fake.calls


def test_assign_milestone_skips_invalid_milestone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    fake = FakeGh()
    monkeypatch.setattr(assign_milestone_mod, "_run_gh", fake)

    result = assign_milestone_mod.assign_milestone(
        issue_number="42",
        milestone="bad-",
        repository="o/r",
    )

    assert result == 0
    assert fake.calls == []
    assert "WARNING: Invalid milestone format: bad-" in capsys.readouterr().out


def test_assign_milestone_reports_missing_milestone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    fake = FakeGh()
    monkeypatch.setattr(assign_milestone_mod, "_run_gh", fake)

    result = assign_milestone_mod.assign_milestone(
        issue_number="42",
        milestone="v9",
        repository="o/r",
    )

    assert result == 0
    assert "::notice::Milestone not found: v9 (skipping assignment)" in capsys.readouterr().out


def test_assign_milestone_bad_argv_returns_config_error():
    assert assign_milestone_mod.main(["unexpected"]) == 2


def test_build_prd_comment_selects_depths():
    assert "Standard" in prd_comment_mod.build_prd_comment(
        prd_content="Body\n",
        complexity_score="4",
        escalation_criteria="none",
        repository="o/r",
        server_url="https://github.com",
        run_id="123",
    )
    assert "Detailed" in prd_comment_mod.build_prd_comment(
        prd_content="Body\n",
        complexity_score="7",
        escalation_criteria="none",
        repository="o/r",
        server_url="https://github.com",
        run_id="123",
    )
    assert "Comprehensive" in prd_comment_mod.build_prd_comment(
        prd_content="Body\n",
        complexity_score="10",
        escalation_criteria="none",
        repository="o/r",
        server_url="https://github.com",
        run_id="123",
    )


def test_prd_main_writes_comment_and_returns_post_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    output = tmp_path / "prd-comment.md"
    calls: list[Path] = []
    monkeypatch.setattr(prd_comment_mod, "DEFAULT_OUTPUT", output)
    monkeypatch.setenv("PRD_CONTENT", "Body\n")
    monkeypatch.setenv("COMPLEXITY_SCORE", "8")
    monkeypatch.setenv("ESCALATION_CRITERIA", "criteria")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("SERVER_URL", "https://github.com")
    monkeypatch.setenv("RUN_ID", "123")
    monkeypatch.setenv("ISSUE_NUMBER", "42")

    def fake_post_comment(*, issue_number: str, body_file: Path) -> int:
        assert issue_number == "42"
        calls.append(body_file)
        return 3

    monkeypatch.setattr(prd_comment_mod, "post_comment", fake_post_comment)

    assert prd_comment_mod.main() == 3
    assert calls == [output]
    text = output.read_text(encoding="utf-8")
    assert "Body\n" in text
    assert "<sub>Generated by [AI PRD Generation]" in text


def test_prd_main_invalid_complexity_score_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPLEXITY_SCORE", "not-int")

    with pytest.raises(ValueError):
        prd_comment_mod.main()


def test_prd_bad_argv_returns_config_error():
    assert prd_comment_mod.main(["unexpected"]) == 2


def test_summary_main_builds_then_posts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / "triage-comment.md"
    calls: list[list[str] | Path] = []
    monkeypatch.setattr(summary_comment_mod, "DEFAULT_OUTPUT", output)
    monkeypatch.setenv("ISSUE_NUMBER", "42")

    def fake_build_main(args: list[str]) -> int:
        calls.append(args)
        output.write_text("summary\n", encoding="utf-8")
        return 0

    def fake_post_comment(*, issue_number: str, body_file: Path) -> int:
        assert issue_number == "42"
        calls.append(body_file)
        return 0

    monkeypatch.setattr(summary_comment_mod.build_triage_summary_comment, "main", fake_build_main)
    monkeypatch.setattr(summary_comment_mod, "post_comment", fake_post_comment)

    assert summary_comment_mod.main() == 0
    assert calls == [["--output", str(output)], output]


def test_summary_main_returns_builder_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / "triage-comment.md"
    monkeypatch.setattr(summary_comment_mod, "DEFAULT_OUTPUT", output)
    monkeypatch.setattr(summary_comment_mod.build_triage_summary_comment, "main", lambda args: 2)

    assert summary_comment_mod.main() == 2


def test_summary_bad_argv_returns_config_error():
    assert summary_comment_mod.main(["unexpected"]) == 2


def test_workflow_delegates_issue_triage_run_blocks():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'python3 scripts/ci/apply_issue_triage_labels.py' in workflow
    assert 'python3 scripts/ci/assign_issue_triage_milestone.py' in workflow
    assert 'python3 scripts/ci/post_issue_triage_prd_comment.py' in workflow
    assert 'python3 scripts/ci/post_issue_triage_summary_comment.py' in workflow
