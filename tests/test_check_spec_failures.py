"""Tests for check_spec_failures.py consumer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("check_spec_failures")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults_to_empty(self, monkeypatch):
        monkeypatch.delenv("TRACE_VERDICT", raising=False)
        monkeypatch.delenv("COMPLETENESS_VERDICT", raising=False)
        args = build_parser().parse_args([])
        assert args.trace_verdict == ""
        assert args.completeness_verdict == ""

    def test_cli_args_override(self):
        args = build_parser().parse_args([
            "--trace-verdict", "PASS",
            "--completeness-verdict", "FAIL",
        ])
        assert args.trace_verdict == "PASS"
        assert args.completeness_verdict == "FAIL"

    def test_env_vars_used_as_defaults(self, monkeypatch):
        monkeypatch.setenv("TRACE_VERDICT", "WARN")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "PASS")
        args = build_parser().parse_args([])
        assert args.trace_verdict == "WARN"
        assert args.completeness_verdict == "PASS"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_both_pass_returns_0(self, capsys):
        rc = main(["--trace-verdict", "PASS", "--completeness-verdict", "PASS"])
        assert rc == 0
        assert "passed" in capsys.readouterr().out.lower()

    def test_trace_fail_returns_1(self):
        rc = main(["--trace-verdict", "FAIL", "--completeness-verdict", "PASS"])
        assert rc == 1

    def test_completeness_fail_returns_1(self):
        rc = main(["--trace-verdict", "PASS", "--completeness-verdict", "FAIL"])
        assert rc == 1

    def test_both_fail_returns_1(self):
        rc = main(["--trace-verdict", "FAIL", "--completeness-verdict", "FAIL"])
        assert rc == 1

    def test_critical_fail_returns_1(self):
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "PASS",
        ])
        assert rc == 1

    def test_both_empty_fails_closed(self, capsys):
        """Issue #5636: no verdict means the check left no evidence it ran."""
        rc = main(["--trace-verdict", "", "--completeness-verdict", ""])
        assert rc == 1
        output = capsys.readouterr().out
        assert "no verdict was recorded" in output
        assert "Spec validation passed" not in output

    def test_one_empty_verdict_fails_closed(self):
        assert main(["--trace-verdict", "PASS", "--completeness-verdict", ""]) == 1
        assert main(["--trace-verdict", "", "--completeness-verdict", "PASS"]) == 1

    def test_whitespace_verdict_fails_closed(self):
        assert main(["--trace-verdict", "  ", "--completeness-verdict", "PASS"]) == 1

    def test_warn_is_not_failure(self):
        rc = main(["--trace-verdict", "WARN", "--completeness-verdict", "WARN"])
        assert rc == 0

    def test_error_message_on_failure(self, capsys):
        main(["--trace-verdict", "FAIL", "--completeness-verdict", "PASS"])
        captured = capsys.readouterr()
        assert "Spec validation failed" in captured.out

    def test_both_infra_failures_fail_closed(self, capsys):
        """Issue #5738: a required check that could not run must not pass."""
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "CRITICAL_FAIL",
            "--trace-infra-failure", "true",
            "--completeness-infra-failure", "true",
        ])
        assert rc == 1
        output = capsys.readouterr().out
        assert "infrastructure failure" in output.lower()
        assert "check the ANTHROPIC_API_KEY secret" in output
        assert "fails closed" in output
        assert "Not blocking merge" not in output
        assert "Spec validation passed" not in output
        assert "::warning::" not in output

    def test_both_infra_failures_fail_closed_even_with_pass_verdicts(self, capsys):
        """Edge: the flag alone blocks, whatever the raw verdict text says."""
        rc = main([
            "--trace-verdict", "PASS",
            "--completeness-verdict", "PASS",
            "--trace-infra-failure", "1",
            "--completeness-infra-failure", "yes",
        ])
        assert rc == 1
        assert "Spec validation passed" not in capsys.readouterr().out

    def test_infra_flag_is_case_insensitive(self):
        rc = main([
            "--trace-verdict", "PASS",
            "--completeness-verdict", "PASS",
            "--trace-infra-failure", "TRUE",
        ])
        assert rc == 1

    def test_false_infra_flags_do_not_block_a_passing_run(self, capsys):
        """Negative control: flags that are not truthy leave a pass green."""
        rc = main([
            "--trace-verdict", "PASS",
            "--completeness-verdict", "PASS",
            "--trace-infra-failure", "false",
            "--completeness-infra-failure", "",
        ])
        assert rc == 0
        output = capsys.readouterr().out
        assert "Spec validation passed" in output
        assert "rotate" not in output

    def test_trace_infra_failure_only_fails_closed(self, capsys):
        """Half of validation missing is still missing evidence: block."""
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "PASS",
            "--trace-infra-failure", "true",
        ])
        assert rc == 1
        output = capsys.readouterr().out
        assert "Traceability check did not run" in output
        assert "check the ANTHROPIC_API_KEY secret" in output
        assert "Spec validation passed" not in output

    def test_completeness_infra_failure_only_fails_closed(self, capsys):
        rc = main([
            "--trace-verdict", "PASS",
            "--completeness-verdict", "CRITICAL_FAIL",
            "--completeness-infra-failure", "true",
        ])
        assert rc == 1
        output = capsys.readouterr().out
        assert "Completeness check did not run" in output
        assert "check the ANTHROPIC_API_KEY secret" in output
        assert "Spec validation passed" not in output

    def test_real_fail_not_masked_by_infra(self):
        """Real completeness failure should still block even if trace is infra."""
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "FAIL",
            "--trace-infra-failure", "true",
        ])
        assert rc == 1

    def test_real_fail_reports_failure_message_alongside_infra(self, capsys):
        """A genuine FAIL on the healthy side names the real failure."""
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "FAIL",
            "--trace-infra-failure", "true",
        ])
        assert rc == 1
        assert "Spec validation failed" in capsys.readouterr().out

    def test_findings_text_does_not_suppress_failures(self):
        """Free-form findings cannot override structured failure flags."""
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "CRITICAL_FAIL",
            "--trace-findings",
            "Copilot CLI infrastructure failure after 3 attempts",
            "--completeness-findings",
            "Copilot CLI infrastructure failure after 3 attempts",
        ])
        assert rc == 1

    def test_one_finding_with_infra_text_still_fails(self):
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "PASS",
            "--trace-findings",
            "Copilot CLI infrastructure failure after 3 attempts",
        ])
        assert rc == 1

    def test_findings_without_infra_keyword_still_fails(self):
        """Findings without infrastructure keyword do not suppress failure."""
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "PASS",
            "--trace-findings", "Some other error message",
        ])
        assert rc == 1


class TestStepOutcome:
    """continue-on-error hides a crashed step; the outcome is the survivor."""

    @staticmethod
    def _args(trace: str, completeness: str, **extra: str) -> list[str]:
        argv = ["--trace-verdict", trace, "--completeness-verdict", completeness]
        for flag, value in extra.items():
            argv += [f"--{flag.replace('_', '-')}", value]
        return argv

    def test_success_outcomes_with_verdicts_pass(self, capsys):
        rc = main(self._args(
            "PASS", "PASS", trace_outcome="success", completeness_outcome="success",
        ))
        assert rc == 0
        assert "Spec validation passed" in capsys.readouterr().out

    def test_failure_outcome_fails_closed_despite_pass_verdict(self, capsys):
        rc = main(self._args(
            "PASS", "PASS", trace_outcome="failure", completeness_outcome="success",
        ))
        assert rc == 1
        output = capsys.readouterr().out
        assert "step outcome was 'failure'" in output
        assert "Traceability check did not complete" in output
        assert "Spec validation passed" not in output

    def test_cancelled_completeness_outcome_fails_closed(self, capsys):
        rc = main(self._args(
            "PASS", "PASS", trace_outcome="success", completeness_outcome="cancelled",
        ))
        assert rc == 1
        assert "Completeness check did not complete" in capsys.readouterr().out

    def test_skipped_outcome_fails_closed(self):
        rc = main(self._args(
            "PASS", "PASS", trace_outcome="skipped", completeness_outcome="success",
        ))
        assert rc == 1

    def test_outcome_is_case_and_whitespace_insensitive(self):
        rc = main(self._args(
            "PASS", "PASS", trace_outcome=" Success ", completeness_outcome="SUCCESS",
        ))
        assert rc == 0

    def test_failure_outcome_with_empty_verdict_fails_closed(self):
        """The crash shape: outcome failure and no outputs at all."""
        rc = main(self._args(
            "", "", trace_outcome="failure", completeness_outcome="failure",
        ))
        assert rc == 1

    def test_success_outcome_with_empty_verdict_fails_closed(self):
        rc = main(self._args(
            "", "PASS", trace_outcome="success", completeness_outcome="success",
        ))
        assert rc == 1

    def test_real_fail_still_reports_failure_message(self, capsys):
        rc = main(self._args(
            "FAIL", "PASS", trace_outcome="success", completeness_outcome="failure",
        ))
        assert rc == 1
        assert "Spec validation failed" in capsys.readouterr().out

    def test_infra_flag_wins_over_gap_message(self, capsys):
        rc = main(self._args(
            "", "PASS",
            trace_outcome="failure", completeness_outcome="success",
            trace_infra_failure="true",
        ))
        assert rc == 1
        output = capsys.readouterr().out
        assert "check the ANTHROPIC_API_KEY secret" in output
        assert "Traceability check did not complete" not in output

    def test_outcomes_read_from_environment(self, monkeypatch, capsys):
        monkeypatch.setenv("TRACE_VERDICT", "PASS")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "PASS")
        monkeypatch.setenv("TRACE_OUTCOME", "failure")
        monkeypatch.setenv("COMPLETENESS_OUTCOME", "success")
        assert main([]) == 1
        assert "Traceability check did not complete" in capsys.readouterr().out

    def test_module_entrypoint_exits_nonzero(self):
        """main(argv) is driven through the process exit path, not a helper."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "check_spec_failures.py"),
             "--trace-verdict", "PASS", "--completeness-verdict", "PASS",
             "--trace-outcome", "failure"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=False,
        )
        assert result.returncode == 1
        assert "did not complete" in result.stdout
