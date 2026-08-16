from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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


def test_report_builds_fail_status_and_outputs_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "github-output.txt"
    report = tmp_path / "pr-validation-report.md"
    _set_output(monkeypatch, output)
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.setenv("DESCRIPTION_RESULT", "FAIL")
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


def test_report_omits_retired_qa_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "github-output.txt"
    report = tmp_path / "pr-validation-report.md"
    _set_output(monkeypatch, output)
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.setenv("DESCRIPTION_RESULT", "PASS")
    monkeypatch.setenv("HAS_CODE_CHANGES", "True")
    monkeypatch.setenv("QA_EXISTS", "false")
    monkeypatch.setenv("QA_REPORT", "qa-pr-42.md")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    assert report_mod.main() == 0
    text = report.read_text(encoding="utf-8")
    assert "### QA Validation" not in text
    assert "Code changes detected" not in text
    assert "QA report exists" not in text
    assert "qa-pr-42.md" not in text
    assert "QA report not found for code changes" not in text


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


def test_a_config_error_writes_no_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Required config is validated before the report file is created.

    ``main`` used to write ``REPORT_PATH`` and only then check
    ``GITHUB_OUTPUT``, so the config-error path still left a report on disk.
    In this repo that landed as an untracked ``pr-validation-report.md`` at
    the root every time the suite ran, which a careless ``git add -A`` would
    have committed. On a runner it leaves an artifact for a step that is
    about to fail.
    """
    report = tmp_path / "report.md"
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    assert report_mod.main() == 2
    assert not report.exists()


def test_a_valid_config_still_writes_the_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Negative control: moving the check must not stop the success path."""
    report = tmp_path / "report.md"
    output = tmp_path / "out.txt"
    output.write_text("", encoding="utf-8")
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert report_mod.main() == 0
    assert "PR Validation Report" in report.read_text(encoding="utf-8")


def test_argv_rejection_still_precedes_every_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Negative control: the argv guard already ran first and still does."""
    report = tmp_path / "report.md"
    output = tmp_path / "out.txt"
    output.write_text("", encoding="utf-8")
    monkeypatch.setattr(report_mod, "REPORT_PATH", report)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert report_mod.main(["unexpected"]) == 2
    assert not report.exists()
    assert output.read_text(encoding="utf-8") == ""


def test_workflow_delegates_first_pr_validation_blocks():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "python3 scripts/ci/map_pr_description_result.py" in workflow
    assert "python3 scripts/ci/build_pr_validation_report.py" in workflow
    assert "Check QA Report Exists" not in workflow
    assert "scripts/ci/check_pr_qa_report.py" not in workflow
    assert "steps.check-qa.outputs" not in workflow
    assert "HAS_CODE_CHANGES:" not in workflow
    assert "QA_EXISTS:" not in workflow
    assert "QA_REPORT:" not in workflow
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
    assert "python3 scripts/ci/adr006_run_block_scanner.py --max 0" in workflow
    assert "gh api `\n            -X DELETE" not in workflow
    assert "Write-Error \"PR has $env:COMMIT_COUNT commits" not in workflow


class TestBlockedMessageNamesTheLimitThatWasApplied:
    """The block message must report the ceiling the check actually used.

    The main-merge relief lifts the ceiling from 20 to 40 for a branch that
    merges its base (issue #3596), and `pr_commit_count` publishes the applied
    value as
    the `commit_limit` output. The workflow already binds it into the
    environment as COMMIT_LIMIT. This script ignored it and printed a literal
    20, so a branch blocked at 41 commits was told the limit was 20 and that
    splitting to 25 would clear it. It would not.

    The inline PowerShell this script replaced carried the same literal, and
    the fix to read the variable was written against that inline body. The
    extraction to Python landed separately and did not carry it across, so
    the defect survived the rewrite that removed the code it lived in.
    """

    @staticmethod
    def _run(monkeypatch: pytest.MonkeyPatch, capsys, **env: str) -> tuple[int, str]:
        for key in ("OVERALL_STATUS", "COMMIT_STATUS", "COMMIT_COUNT", "COMMIT_LIMIT"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("PR_NUMBER", "1")
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setattr(enforce_mod, "_fetch_labels", lambda *_: (0, []))
        code = enforce_mod.main([])
        return code, capsys.readouterr().err

    def test_the_widened_ceiling_is_reported(self, monkeypatch, capsys) -> None:
        """Positive: a main-merge branch is told 40, not 20."""
        code, err = self._run(
            monkeypatch,
            capsys,
            OVERALL_STATUS="PASS",
            COMMIT_STATUS="BLOCKED",
            COMMIT_COUNT="41",
            COMMIT_LIMIT="40",
        )
        assert code == enforce_mod.LOGIC_ERROR
        assert "limit: 40" in err
        assert "limit: 20" not in err

    def test_the_default_ceiling_is_reported(self, monkeypatch, capsys) -> None:
        """Positive: the ordinary case still reads 20, from the variable."""
        _, err = self._run(
            monkeypatch,
            capsys,
            OVERALL_STATUS="PASS",
            COMMIT_STATUS="BLOCKED",
            COMMIT_COUNT="21",
            COMMIT_LIMIT="20",
        )
        assert "limit: 20" in err

    @pytest.mark.parametrize("value", ["", "  "])
    def test_a_blank_limit_names_no_number(self, monkeypatch, capsys, value: str) -> None:
        """Negative: with nothing to report, do not invent a ceiling.

        Falling back to a literal 20 here would reintroduce the same wrong
        claim this change removes, just on a narrower path.
        """
        _, err = self._run(
            monkeypatch,
            capsys,
            OVERALL_STATUS="PASS",
            COMMIT_STATUS="BLOCKED",
            COMMIT_COUNT="41",
            COMMIT_LIMIT=value,
        )
        assert "limit:" not in err
        assert "41 commits" in err

    def test_an_absent_limit_names_no_number(self, monkeypatch, capsys) -> None:
        """Edge: unset is the same as blank, not a reason to guess."""
        _, err = self._run(
            monkeypatch,
            capsys,
            OVERALL_STATUS="PASS",
            COMMIT_STATUS="BLOCKED",
            COMMIT_COUNT="41",
        )
        assert "limit:" not in err
        assert "41 commits" in err

    def test_the_remediation_survives_every_shape(self, monkeypatch, capsys) -> None:
        """Edge: the actionable half of the message is never dropped.

        Since issue #4782 the actionable half is the split, and the label is
        named only as a maintainer's decision, so the prohibition on
        self-application is part of what this pins.
        """
        for limit in ("40", ""):
            _, err = self._run(
                monkeypatch,
                capsys,
                OVERALL_STATUS="PASS",
                COMMIT_STATUS="BLOCKED",
                COMMIT_COUNT="41",
                COMMIT_LIMIT=limit,
            )
            assert enforce_mod.BYPASS_LABEL in err
            assert "Split this PR" in err
            assert "do not apply it yourself" in err

    def test_the_workflow_still_supplies_the_variable(self) -> None:
        """Edge: the fix is inert unless the workflow binds COMMIT_LIMIT."""
        assert "COMMIT_LIMIT:" in WORKFLOW.read_text(encoding="utf-8")


class TestModelPinEnforcementIsWiredIntoCI:
    """The ADR-080 model-pin gate has to be able to fail a PR (Issue #2840).

    ``check_model_pins.py`` shipped a correct ``--mode enforce`` that exits 1 on
    a new or changed ``model:`` pin lacking a model-rationale field, and
    ``checks_spec.validate_model_pins`` documents that "enforcement stays in
    CI". Nothing under ``.github/`` invoked it. The only caller was the pre-PR
    runner in ``--mode warn``, which prints ``VIOLATION`` and exits 0 by
    design. A new unjustified pin was therefore detected, printed, and merged.
    These tests pin the wiring, not the script; the script's own exit codes are
    covered in ``tests/validation/test_check_model_pins.py``.
    """

    HOST_JOB = "validate-pr"

    @staticmethod
    def _jobs() -> dict:
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]

    @classmethod
    def _host_steps(cls) -> list:
        return cls._jobs()[cls.HOST_JOB]["steps"]

    @classmethod
    def _pin_steps(cls) -> list:
        return [
            step
            for step in cls._host_steps()
            if "check_model_pins.py" in str(step.get("run", ""))
        ]

    def test_ci_invokes_the_gate_in_enforce_mode(self) -> None:
        """Positive: the gate that can fail is the one CI actually runs."""
        steps = self._pin_steps()
        assert len(steps) == 1, "expected exactly one model-pin step"
        assert "--mode enforce" in steps[0]["run"]

    def test_ci_never_invokes_the_gate_in_warn_mode(self) -> None:
        """Negative: warn mode exits 0 on violations, so it cannot gate.

        Wiring warn mode here would look like enforcement in the checks list
        while blocking nothing, which is the exact defect this test guards.
        Parsed ``run`` blocks only: a comment may name warn mode to explain why
        it is the wrong choice, and that prose must not fail this test.
        """
        runs = [str(step.get("run", "")) for step in self._host_steps()]
        assert not [run for run in runs if "--mode warn" in run]

    def test_the_hosting_job_cannot_be_skipped(self) -> None:
        """Edge: a ``model:`` pin can land in any file, so no path filter.

        The gate is inert if its host job is conditional, because a PR that
        touches no filtered path would skip it. This job carries no job-level
        ``if`` on purpose; it is the required check that always reports status.
        """
        assert "if" not in self._jobs()[self.HOST_JOB]

    def test_enforce_mode_passes_against_the_current_tree(self) -> None:
        """Edge: wiring the gate must not red main on arrival.

        Enforce mode grandfathers the existing backlog through
        ``model_pin_baseline.json`` and fails only on new or changed pins. If
        this ever fails, the baseline and the tree have diverged and the gate
        would block every PR, including the one that tries to fix it.
        """
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "validation" / "check_model_pins.py"),
                "--mode",
                "enforce",
            ],
            capture_output=True,
            text=True, encoding="utf-8",
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestTheCommitCountGateCanReadMainsTrunk:
    """The commit-limit relief needs origin/main in the runner (issue #3997).

    ``pr_commit_count.contains_main_merge`` decides the 20 vs 40 ceiling by
    asking whether a merge parent sits on ``origin/main``'s first-parent trunk,
    and it reads that trunk with ``git rev-list`` against the checkout. A default
    ``actions/checkout`` is shallow and creates only ``refs/remotes/pull/<n>/
    merge``, so the read fails, the predicate fails closed, and a branch that
    genuinely merges main is capped at 20 in CI while the pre-push hook grants
    it 40. That is the divergence issue #3997 removed, so the checkout that
    hosts the gate has to carry the ref. These tests pin the wiring; the
    predicate itself is covered in tests/validation/test_commit_limit_parity.py.
    """

    HOST_JOB = "validate-pr"

    @staticmethod
    def _jobs() -> dict:
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]

    @classmethod
    def _host_steps(cls) -> list:
        return cls._jobs()[cls.HOST_JOB]["steps"]

    @classmethod
    def _gate_step(cls) -> dict:
        steps = [
            step for step in cls._host_steps() if "pr_commit_count.py" in str(step.get("run", ""))
        ]
        assert len(steps) == 1, "expected exactly one commit-count step"
        return steps[0]

    @classmethod
    def _checkout_steps(cls) -> list:
        """The checkouts that run on the same condition as the gate.

        This job also checks out on the *inverse* condition, to validate
        workflow YAML on PRs whose author suppressed the main path. That
        checkout never coexists with the gate, so it is not the one under test.
        """
        guard = cls._gate_step().get("if")
        return [
            step
            for step in cls._host_steps()
            if "actions/checkout" in str(step.get("uses")) and step.get("if") == guard
        ]

    def test_the_commit_count_gate_runs_in_the_checked_out_job(self) -> None:
        """Positive: the gate and the checkout it depends on share a job.

        The predicate resolves the repository from the process working
        directory, so a checkout in some other job would not reach it.
        """
        assert len(self._checkout_steps()) == 1

    def test_the_checkout_fetches_the_full_history(self) -> None:
        """Positive: fetch-depth 0 is what populates refs/remotes/origin/main.

        actions/checkout writes ``+refs/heads/*:refs/remotes/origin/*`` only on
        an unshallow fetch. Any positive depth leaves origin/main absent or
        truncated, and a truncated trunk is worse than an absent one because it
        answers wrongly instead of failing closed.
        """
        checkout = self._checkout_steps()[0]
        assert checkout.get("with", {}).get("fetch-depth") == 0

    def test_the_hosting_job_is_not_conditional(self) -> None:
        """Edge: a skipped host job would report no ceiling at all.

        ``validate-pr`` is a required check that always reports status, so it
        carries no job-level ``if``. A path filter here would let a PR skip the
        commit ceiling entirely.
        """
        assert "if" not in self._jobs()[self.HOST_JOB]


class TestBotSkipGuardClassification:
    """Every step behind the skip guard must have a documented classification.

    Issue #4151: the skip guard exempts dependabot[bot], github-actions[bot],
    and renovate[bot] for throughput reasons (dependency-bump PRs should not
    pay for the full validation suite). That reasoning holds for expensive
    advisory checks against the PR body or diff. It does not hold for gates
    whose job is to catch a class of change regardless of who authored it.

    Bots open workflow-only PRs (action SHA bumps). A correctness gate that is
    skip-guarded is invisible to exactly those PRs. The ADR-006 run-block
    ratchet was the only correctness gate still gated behind the skip guard; it
    is now unconditional.

    Classification rationale (throughput-motivated = OK to remain skip-guarded):
    - Checkout repository: bot PRs receive a separate unconditional checkout
    - Setup PowerShell: UI tooling for the skip-guarded steps
    - Validate PR Description vs Diff: meaningless for a bot dep-bump PR body
    - Validate PR Description Standards: same
    - Generate Validation Report: same
    - Post PR Comment: same
    - Set Job Summary: same
    - Check PR commit count: a single-commit dep-bump is never blocked
    - Enforce Blocking Issues: depends on outputs of skip-guarded steps above

    Security/correctness gates that MUST be unconditional:
    - Run ADR-006 run-block ratchet (moved here by Issue #4151 fix)
    """

    HOST_JOB = "validate-pr"
    BOT_SKIP_GUARD = "steps.should-run.outputs.skip != 'true'"

    @staticmethod
    def _jobs() -> dict:
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]

    @classmethod
    def _host_steps(cls) -> list:
        return cls._jobs()[cls.HOST_JOB]["steps"]

    @classmethod
    def _skip_guarded_steps(cls) -> list[dict]:
        return [
            step
            for step in cls._host_steps()
            if cls._has_bot_skip_guard_component(step.get("if"))
        ]

    @classmethod
    def _has_bot_skip_guard_component(cls, condition: object) -> bool:
        if not isinstance(condition, str):
            return False

        expression = condition.strip()
        if expression.startswith("${{") and expression.endswith("}}"):
            expression = expression[3:-2].strip()

        return any(
            component.strip().strip("()").strip() == cls.BOT_SKIP_GUARD
            for component in expression.split("&&")
        )

    def test_skip_guard_classifier_detects_compound_conditions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive: a step can add a condition and still stay bot-skipped."""
        guarded_step = {
            "name": "Compound guarded step",
            "if": f"{self.BOT_SKIP_GUARD} && github.event_name == 'push'",
        }
        monkeypatch.setattr(type(self), "_host_steps", classmethod(lambda cls: [guarded_step]))

        assert self._skip_guarded_steps() == [guarded_step]

    def test_skip_guard_classifier_rejects_negated_conditions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative: a negated occurrence is not a skip guard."""
        unguarded_step = {
            "name": "Negated guarded step",
            "if": f"!({self.BOT_SKIP_GUARD}) && github.event_name == 'push'",
        }
        monkeypatch.setattr(type(self), "_host_steps", classmethod(lambda cls: [unguarded_step]))

        assert self._skip_guarded_steps() == []

    def test_skip_guard_classifier_accepts_wrapped_expression(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: GitHub expressions may carry the optional wrapper."""
        guarded_step = {
            "name": "Wrapped guarded step",
            "if": f"${{{{ ({self.BOT_SKIP_GUARD}) && github.event_name == 'push' }}}}",
        }
        monkeypatch.setattr(type(self), "_host_steps", classmethod(lambda cls: [guarded_step]))

        assert self._skip_guarded_steps() == [guarded_step]

    # Exactly these step names are permitted behind the skip guard.
    # If this set grows, the new step must be justified as throughput-motivated.
    _ALLOWED_BEHIND_GUARD: frozenset[str] = frozenset(
        {
            "Checkout repository",
            # Tool setup is throughput-only. It cannot validate repository
            # contents, so skipping it on a bot PR removes no measurement. That
            # holds only because the unguarded half of this job installs uv for
            # itself; `test_unguarded_uv_consumers_have_an_unguarded_install`
            # enforces it, so this justification cannot rot silently.
            "Setup uv",
            "Setup PowerShell",
            "Validate PR Description vs Diff",
            "Validate PR Description Standards",
            "Generate Validation Report",
            "Post PR Comment",
            "Set Job Summary",
            "Check PR commit count",
            "Enforce Blocking Issues",
        }
    )

    def test_adr006_ratchet_is_unconditional(self) -> None:
        """Positive: the ADR-006 gate must run for bot-authored PRs.

        Renovate and Dependabot open workflow-only PRs. A run-block scanner
        that is skip-guarded is invisible to the actors most likely to touch
        workflow YAML. The comment in the workflow already says 'Runs on every
        PR because workflow YAML can change in any PR'; this test pins that.
        """
        adr006_steps = [
            step
            for step in self._host_steps()
            if "adr006_run_block_scanner.py" in str(step.get("run", ""))
        ]
        assert len(adr006_steps) == 1, "expected exactly one ADR-006 step"
        step = adr006_steps[0]
        assert "if" not in step, (
            f"ADR-006 ratchet must be unconditional, found: if: {step.get('if')!r}"
        )

    def _assert_unguarded_uv_consumers_have_an_unguarded_install(self) -> None:
        """Assert `Setup uv` self-serves the unguarded half of the job.

        The job installs uv twice on purpose. The guarded install serves the
        guarded prefix; a second, unguarded install serves the unguarded
        steps that follow it. That is what makes skipping the guarded one
        harmless on a bot PR.

        If someone deletes the second install as redundant, every unguarded
        `uv` step breaks on bot PRs and the `Setup uv` allowlist entry stops
        being justified. Pin the invariant rather than asserting it in a
        comment nobody re-checks.
        """
        steps = self._host_steps()
        installs = [
            i
            for i, step in enumerate(steps)
            if "setup-uv" in str(step.get("uses", ""))
            and not self._has_bot_skip_guard_component(step.get("if"))
        ]
        consumers = [
            (i, str(step.get("name", "")))
            for i, step in enumerate(steps)
            if "uv " in str(step.get("run", ""))
            and not self._has_bot_skip_guard_component(step.get("if"))
        ]
        assert consumers, "expected at least one unguarded uv consumer to protect"
        assert installs, (
            "no unguarded uv install in the job, so every unguarded uv step "
            f"breaks when the bot-skip guard fires: {[n for _, n in consumers]!r}"
        )
        first_install = min(installs)
        orphans = [name for i, name in consumers if i < first_install]
        assert not orphans, (
            f"unguarded uv steps run before the first unguarded uv install: {orphans!r}. "
            "They inherit the guarded install and break on bot PRs."
        )

    def test_unguarded_uv_consumers_have_an_unguarded_install(self) -> None:
        """`Setup uv` is allowlisted only while the unguarded half self-serves."""
        self._assert_unguarded_uv_consumers_have_an_unguarded_install()

    def test_unguarded_uv_install_must_precede_its_consumers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: an install that lands after a consumer does not serve it.

        Presence alone is not enough. A consumer sitting above the unguarded
        install inherits the guarded one, so it still breaks on a bot PR.
        """
        steps = [
            {"name": "Early consumer", "run": "uv run --frozen python x.py"},
            {"name": "Setup uv late", "uses": "astral-sh/setup-uv@abc"},
        ]
        monkeypatch.setattr(type(self), "_host_steps", classmethod(lambda cls: steps))

        with pytest.raises(AssertionError, match="Early consumer"):
            self._assert_unguarded_uv_consumers_have_an_unguarded_install()

    def test_unguarded_uv_check_requires_a_consumer_to_protect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: with no unguarded consumer the check is vacuous, so it fails.

        A job whose uv steps are all guarded would pass the install assertion
        for the wrong reason. Fail instead, so the guard cannot quietly stop
        measuring anything.
        """
        steps = [
            {
                "name": "Guarded consumer",
                "run": "uv run --frozen python x.py",
                "if": self.BOT_SKIP_GUARD,
            }
        ]
        monkeypatch.setattr(type(self), "_host_steps", classmethod(lambda cls: steps))

        with pytest.raises(AssertionError, match="at least one unguarded uv consumer"):
            self._assert_unguarded_uv_consumers_have_an_unguarded_install()

    def test_no_security_gate_is_skip_guarded(self) -> None:
        """Negative: every skip-guarded step must be throughput-motivated.

        A step whose name is not in _ALLOWED_BEHIND_GUARD and is behind the
        skip guard is a new security/correctness gate that slipped past the
        exemption check. Adding a name to _ALLOWED_BEHIND_GUARD requires a
        written justification showing the step is throughput-motivated, not
        correctness-motivated.
        """
        guarded = {str(step.get("name", "")) for step in self._skip_guarded_steps()}
        unknown = guarded - self._ALLOWED_BEHIND_GUARD
        assert unknown == set(), (
            f"Steps behind the bot-skip guard without a throughput justification: {unknown!r}. "
            "Add the name to _ALLOWED_BEHIND_GUARD with a comment explaining why it is "
            "throughput-motivated, not a correctness or security gate."
        )

    def test_all_allowed_guarded_steps_are_present(self) -> None:
        """Edge: the allowlist must not include names that no longer exist.

        A step removed from the workflow without pruning the allowlist leaves
        phantom permission in _ALLOWED_BEHIND_GUARD that is never exercised.
        This test requires every allowed name to actually exist in the workflow,
        either as a skip-guarded step or elsewhere in the job (the commit-count
        label steps are conditional on a different output, not on skip).
        """
        all_step_names = {str(step.get("name", "")) for step in self._host_steps()}
        for name in self._ALLOWED_BEHIND_GUARD:
            assert name in all_step_names, (
                f"_ALLOWED_BEHIND_GUARD contains {name!r} but no step with that name "
                "exists in the workflow. Remove the stale entry."
            )


def _pr_validation_steps() -> list[dict]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps: list[dict] = []
    for job in data.get("jobs", {}).values():
        steps.extend(job.get("steps", []) or [])
    return steps


def _pr_validation_jobs() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data.get("jobs", {})


def _validate_pr_steps() -> list[dict]:
    return _pr_validation_jobs()["validate-pr"]["steps"]


def _active_run_lines(step: dict) -> list[str]:
    run = step.get("run") or ""
    return [
        line.strip()
        for line in run.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _join_continuations(lines: list[str]) -> list[str]:
    """Join shell continuation lines (trailing backslash) into logical commands."""
    joined: list[str] = []
    buf = ""
    for line in lines:
        if line.endswith("\\"):
            buf += line[:-1] + " "
        else:
            buf += line
            joined.append(buf)
            buf = ""
    if buf:
        joined.append(buf)
    return joined


_MERGE_BASE_CONSUMERS = ("merge_tree_ratchet_check.py", "count_ratchet.py")


def _strip_shell_comments(script: str) -> str:
    return "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    )


def _step_dicts(job: dict) -> list[dict]:
    return [step for step in job.get("steps", []) if isinstance(step, dict)]


def _run_blocks(steps: list[dict]) -> list[str]:
    return [
        _strip_shell_comments(step["run"])
        for step in steps
        if isinstance(step.get("run"), str)
    ]


def _uses_merge_base(run_blocks: list[str]) -> bool:
    return any(
        consumer in block
        for consumer in _MERGE_BASE_CONSUMERS
        for block in run_blocks
    )


def _depth_limited_fetch_offenders(job_id: str, run_blocks: list[str]) -> list[str]:
    if any("--depth" in block for block in run_blocks):
        return [f"{job_id}: depth-limited fetch in run block"]
    return []


def _checkout_depth_offenders(job_id: str, steps: list[dict]) -> list[str]:
    offenders: list[str] = []
    for step in steps:
        uses = step.get("uses")
        if not isinstance(uses, str) or not uses.startswith("actions/checkout"):
            continue
        depth = (step.get("with") or {}).get("fetch-depth")
        if str(depth) == "0":
            continue
        name = step.get("name") or uses
        shown = "<default, depth 1>" if depth is None else repr(depth)
        offenders.append(f"{job_id}: checkout {name!r} has fetch-depth {shown}")
    return offenders


def _history_offenders_for_merge_base_jobs(jobs: dict) -> tuple[list[str], list[str]]:
    offenders: list[str] = []
    checked: list[str] = []
    for job_id, job in jobs.items():
        steps = _step_dicts(job)
        run_blocks = _run_blocks(steps)
        if not _uses_merge_base(run_blocks):
            continue

        checked.append(job_id)
        offenders.extend(_depth_limited_fetch_offenders(job_id, run_blocks))
        offenders.extend(_checkout_depth_offenders(job_id, steps))
    return offenders, checked


def test_merge_base_jobs_keep_complete_history() -> None:
    """Every job that needs a merge base must avoid shallow history.

    The graft is job-scoped, not step-scoped. One earlier shallow fetch writes
    .git/shallow, and the later merge-tree ratchet then fails with unrelated
    histories.
    """
    offenders, checked = _history_offenders_for_merge_base_jobs(_pr_validation_jobs())

    assert checked == ["validate-pr"]
    assert offenders == []


def test_merge_base_history_guard_catches_both_shallow_routes() -> None:
    """Negative control: the matcher catches a shallow checkout and fetch."""
    jobs = yaml.safe_load(
        "validate:\n"
        "  steps:\n"
        "    - name: Checkout repository\n"
        "      uses: actions/checkout@v7\n"
        "    - run: git fetch --depth=1 origin main\n"
        "    - run: python scripts/ci/merge_tree_ratchet_check.py\n"
    )

    offenders, checked = _history_offenders_for_merge_base_jobs(jobs)

    assert checked == ["validate"]
    assert any("depth-limited fetch" in item for item in offenders)
    assert any("fetch-depth <default, depth 1>" in item for item in offenders)


def test_merge_base_history_guard_ignores_unrelated_shallow_jobs() -> None:
    """Edge control: shallow fetches are out of scope without a consumer."""
    jobs = yaml.safe_load(
        "lint:\n"
        "  steps:\n"
        "    - uses: actions/checkout@v7\n"
        "    - run: git fetch --depth=1 origin main\n"
        "    - run: uv run --frozen ruff check .\n"
    )

    offenders, checked = _history_offenders_for_merge_base_jobs(jobs)

    assert checked == []
    assert offenders == []



def test_merge_tree_ratchet_fetches_base_at_full_depth() -> None:
    """Issue #4518: the merge-tree step's base fetch must not be shallow.

    A `--depth=1` fetch writes .git/shallow and severs history traversal, so
    `git merge-tree` aborts with "refusing to merge unrelated histories" on any
    branch behind the base. That is the only case this gate exists to judge, so
    a shallow fetch silences the gate instead of failing loudly.

    The sibling behaviour test in tests/ci/test_merge_tree_ratchet_check.py runs
    its own fetch, so it cannot see a regression here. This assertion is the one
    that catches a revert of the workflow line.
    """
    matching = [
        s
        for s in _pr_validation_steps()
        if "merge_tree_ratchet_check.py" in (s.get("run") or "")
    ]
    assert matching, "the merge-tree ratchet step is missing from pr-validation.yml"
    for step in matching:
        run = step["run"]
        fetch_lines = [
            ln.strip()
            for ln in run.splitlines()
            if ln.strip().startswith("git fetch") and not ln.strip().startswith("#")
        ]
        assert fetch_lines, f"step {step.get('name')!r} must fetch the base ref"
        for line in fetch_lines:
            assert "--depth" not in line, (
                f"step {step.get('name')!r} fetches the base shallowly ({line!r}); "
                "merge-tree needs a merge base. See issue #4518."
            )


def test_merge_tree_host_checkouts_fetch_full_history() -> None:
    """Issue #4572: every checkout in validate-pr must keep full history.

    `Run merge-tree ratchet` is unconditional, so it shares the job with both
    checkout legs. A default checkout is depth 1 and creates `.git/shallow`;
    a later full fetch does not remove that graft.
    """
    checkout_steps = [
        step for step in _validate_pr_steps() if "actions/checkout" in str(step.get("uses"))
    ]
    assert checkout_steps, "validate-pr must check out the repository"
    for step in checkout_steps:
        assert step.get("with", {}).get("fetch-depth") == 0, (
            f"checkout step {step.get('name')!r} can share a job with merge-tree "
            "and must use fetch-depth: 0"
        )


def test_steps_before_merge_tree_do_not_shallow_fetch() -> None:
    """Issue #4572: earlier validate-pr fetches must not poison merge-tree.

    The count ratchets only need a file at the base ref, but their shell runs in
    the same working tree as the later merge-tree step. A depth-limited fetch
    writes `.git/shallow` for the rest of the job.
    """
    steps = _validate_pr_steps()
    merge_indexes = [
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Run merge-tree ratchet"
    ]
    assert len(merge_indexes) == 1, "expected exactly one merge-tree step"

    offenders: list[str] = []
    for step in steps[: merge_indexes[0]]:
        for line in _join_continuations(_active_run_lines(step)):
            if line.startswith("git fetch") and "--depth" in line:
                offenders.append(f"{step.get('name')}: {line}")

    assert offenders == [], (
        "validate-pr fetches before merge-tree must not be shallow: "
        + "; ".join(offenders)
    )
