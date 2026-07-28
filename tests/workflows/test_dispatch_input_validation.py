"""Runtime contract for the dispatch-input validation steps (issue #3652).

The hardening added in `43ac3fdb2` constrains free-form `workflow_dispatch`
inputs to digits before they reach a shell argument. The constraint lives in a
`case` statement inside a `run:` block, which nothing executed: the workflow
linters check YAML shape and the taint pass checks expression interpolation,
but neither runs the guard.

These tests extract the real `run:` body from the checked-in workflow and
execute it under `sh`, so a widened pattern or a message that overstates the
constraint fails here rather than in production.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# `on` is a YAML 1.1 boolean, so a plain safe_load turns the trigger key into
# True. Only the jobs tree matters here, so the quirk is harmless, but naming it
# keeps the next reader from "fixing" a bug that is not there.
#
# Neither step under test declares `shell:` and neither workflow sets a
# `defaults:` block, so GitHub runs these bodies under `bash -e`. Running them
# under `dash` instead would fail on Bash-only syntax that production accepts,
# so the default here matches the runner rather than the strictest shell.
_BASH = "/bin/bash"
_SH = "/bin/sh"


def _run_block(workflow: str, job: str, step_id: str) -> str:
    """Return the `run:` body of one step, as checked in."""
    data = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    for step in data["jobs"][job]["steps"]:
        if step.get("id") == step_id:
            return str(step["run"])
    raise AssertionError(f"no step {step_id!r} in {workflow}:{job}")


def _execute(
    body: str, env: dict[str, str], tmp_path: Path, shell: str = _BASH
) -> int:
    """Run a workflow `run:` body and return its exit code.

    GitHub interpolates `${{ }}` before the shell sees the body. The steps under
    test route every input through `env:` precisely so no interpolation lands in
    the script, so the body executes verbatim.

    `shell` defaults to bash because that is what the runner uses. Pass `_SH` to
    assert a body is POSIX-clean.
    """
    full_env = {
        "PATH": "/usr/bin:/bin",
        "GITHUB_OUTPUT": str(tmp_path / "out.txt"),
        **env,
    }
    result = subprocess.run(
        [shell, "-c", body],
        env=full_env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode


def _metrics_body() -> str:
    return _run_block("agent-metrics.yml", "collect-metrics", "period")


def _issue_body() -> str:
    return _run_block("copilot-context-synthesis.yml", "synthesize-single", "issue")


class TestAgentMetricsDaysValidation:
    """`days` reaches `collect_metrics.py --since`, so it must be a real count."""

    @pytest.mark.parametrize("days", ["1", "7", "30", "365", "999"])
    def test_accepts_a_positive_integer(self, days: str, tmp_path: Path) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": days,
               "INPUT_FORMAT": "markdown"}
        assert _execute(_metrics_body(), env, tmp_path) == 0

    @pytest.mark.parametrize("days", ["0", "00", "000"])
    def test_rejects_zero(self, days: str, tmp_path: Path) -> None:
        """The error message promises "positive integer"; zero is not one.

        `--since 0` resolves to today, so the report silently covers a same-day
        window while claiming to be a metrics run over a period.
        """
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": days,
               "INPUT_FORMAT": "markdown"}
        assert _execute(_metrics_body(), env, tmp_path) == 1

    @pytest.mark.parametrize("days", ["07", "0007"])
    def test_rejects_a_leading_zero(self, days: str, tmp_path: Path) -> None:
        """A leading zero is never what a human dispatcher typed."""
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": days,
               "INPUT_FORMAT": "markdown"}
        assert _execute(_metrics_body(), env, tmp_path) == 1

    @pytest.mark.parametrize(
        "days",
        ["", "7; rm -rf /", "$(id)", "7 8", "-1", "1e3", "seven", "7\nid"],
    )
    def test_rejects_a_non_digit(self, days: str, tmp_path: Path) -> None:
        """Negative control: the injection constraint must survive the change."""
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": days,
               "INPUT_FORMAT": "markdown"}
        assert _execute(_metrics_body(), env, tmp_path) == 1

    def test_the_scheduled_default_still_passes(self, tmp_path: Path) -> None:
        """Edge: on a non-dispatch event the step assigns its own values.

        A tightened pattern that rejected the hardcoded default would break
        every scheduled run, which no dispatch-input test would catch.
        """
        env = {"EVENT_NAME": "schedule", "INPUT_DAYS": "", "INPUT_FORMAT": ""}
        assert _execute(_metrics_body(), env, tmp_path) == 0


class TestContextSynthesisIssueNumberValidation:
    """`issue_number` reaches a `gh` call, so it must be a real issue number."""

    @pytest.mark.parametrize("number", ["1", "42", "3652", "999999"])
    def test_accepts_a_positive_integer(self, number: str, tmp_path: Path) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_ISSUE_NUMBER": number,
               "EVENT_ISSUE_NUMBER": ""}
        assert _execute(_issue_body(), env, tmp_path) == 0

    @pytest.mark.parametrize("number", ["0", "00", "012"])
    def test_rejects_zero_and_leading_zeros(self, number: str, tmp_path: Path) -> None:
        """GitHub issue numbers start at 1, so zero names nothing."""
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_ISSUE_NUMBER": number,
               "EVENT_ISSUE_NUMBER": ""}
        assert _execute(_issue_body(), env, tmp_path) == 1

    @pytest.mark.parametrize(
        "number",
        ["", "42; id", "$(id)", "42 43", "-1", "#42", "issue-42"],
    )
    def test_rejects_a_non_digit(self, number: str, tmp_path: Path) -> None:
        """Negative control: the injection constraint must survive the change."""
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_ISSUE_NUMBER": number,
               "EVENT_ISSUE_NUMBER": ""}
        assert _execute(_issue_body(), env, tmp_path) == 1

    def test_the_event_payload_path_still_passes(self, tmp_path: Path) -> None:
        """Edge: a non-dispatch event reads the number from the event payload."""
        env = {"EVENT_NAME": "issues", "INPUT_ISSUE_NUMBER": "",
               "EVENT_ISSUE_NUMBER": "3652"}
        assert _execute(_issue_body(), env, tmp_path) == 0


class TestGuardsArePosixClean:
    """Both guards do the same job, so they should be written the same way.

    GitHub runs these under `bash -e`, so Bash-only syntax works today. The two
    guards were nonetheless written differently: `agent-metrics.yml` used the
    POSIX `=` and `copilot-context-synthesis.yml` used the Bash-only `==`. That
    divergence costs nothing until someone adds `shell: sh` or lifts the block
    into a composite action, at which point one guard silently stops running and
    the input reaches the shell unvalidated.

    Running each body under `dash` pins the property rather than leaving it to
    whoever edits next.
    """

    def test_metrics_guard_runs_under_dash(self, tmp_path: Path) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": "7",
               "INPUT_FORMAT": "markdown"}
        assert _execute(_metrics_body(), env, tmp_path, shell=_SH) == 0

    def test_metrics_guard_still_rejects_under_dash(self, tmp_path: Path) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": "0",
               "INPUT_FORMAT": "markdown"}
        assert _execute(_metrics_body(), env, tmp_path, shell=_SH) == 1

    def test_issue_guard_runs_under_dash(self, tmp_path: Path) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_ISSUE_NUMBER": "42",
               "EVENT_ISSUE_NUMBER": ""}
        assert _execute(_issue_body(), env, tmp_path, shell=_SH) == 0

    def test_issue_guard_still_rejects_under_dash(self, tmp_path: Path) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_ISSUE_NUMBER": "0",
               "EVENT_ISSUE_NUMBER": ""}
        assert _execute(_issue_body(), env, tmp_path, shell=_SH) == 1


def _locale_available(name: str) -> bool:
    """True when the runner can actually switch to `name`.

    A locale that is not generated silently falls back, which would make the
    Unicode-digit tests below pass for the wrong reason.
    """
    probe = 'case "٧" in *[!0-9]*) echo ascii ;; *) echo unicode ;; esac'
    result = subprocess.run(
        [_BASH, "-c", probe],
        env={**os.environ, "LC_ALL": name},
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == "unicode"


_UNICODE_DIGIT_LOCALE = "en_US.UTF-8"
_needs_unicode_locale = pytest.mark.skipif(
    not _locale_available(_UNICODE_DIGIT_LOCALE),
    reason=f"{_UNICODE_DIGIT_LOCALE} is not generated on this machine",
)


class TestGuardsAreLocaleIndependent:
    """The guard verdict must not depend on the runner's locale.

    `[!0-9]` is a range, and Bash resolves ranges through the collation table,
    so under a locale like en_US.UTF-8 it treats every Unicode decimal digit as
    a member. Arabic-Indic and fullwidth digits then satisfy "all digits" and
    reach the consumer. Worse, a leading Arabic-Indic zero is not the ASCII `0`
    the `0*` arm matches, so the zero rejection is defeated too.

    GitHub-hosted Ubuntu images run C.UTF-8 today, so this is latent rather
    than live. It becomes live on a self-hosted runner, or the first time
    anyone sets LANG or LC_ALL in a `env:` block, and it fails open.

    An enumerated class is not a range, so it resolves the same way everywhere.
    """

    @pytest.mark.parametrize("value", ["٧", "٠٧", "０７", "1٧"])
    @_needs_unicode_locale
    def test_metrics_rejects_unicode_digits(self, tmp_path: Path, value: str) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": value,
               "INPUT_FORMAT": "markdown", "LC_ALL": _UNICODE_DIGIT_LOCALE}
        assert _execute(_metrics_body(), env, tmp_path) == 1

    @pytest.mark.parametrize("value", ["٧", "٠٧", "０７", "1٧"])
    @_needs_unicode_locale
    def test_issue_rejects_unicode_digits(self, tmp_path: Path, value: str) -> None:
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_ISSUE_NUMBER": value,
               "EVENT_ISSUE_NUMBER": "", "LC_ALL": _UNICODE_DIGIT_LOCALE}
        assert _execute(_issue_body(), env, tmp_path) == 1

    @pytest.mark.parametrize("value", ["7", "42", "999"])
    @_needs_unicode_locale
    def test_ascii_digits_still_accepted_under_that_locale(
        self, tmp_path: Path, value: str
    ) -> None:
        """Control: the fix must not reject the values that always worked."""
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": value,
               "INPUT_FORMAT": "markdown", "LC_ALL": _UNICODE_DIGIT_LOCALE}
        assert _execute(_metrics_body(), env, tmp_path) == 0

    @pytest.mark.parametrize("value", ["0", "07", "7a", "-1"])
    @_needs_unicode_locale
    def test_ascii_rejections_hold_under_that_locale(
        self, tmp_path: Path, value: str
    ) -> None:
        """Control: switching locale must not weaken the ASCII rejections."""
        env = {"EVENT_NAME": "workflow_dispatch", "INPUT_DAYS": value,
               "INPUT_FORMAT": "markdown", "LC_ALL": _UNICODE_DIGIT_LOCALE}
        assert _execute(_metrics_body(), env, tmp_path) == 1
