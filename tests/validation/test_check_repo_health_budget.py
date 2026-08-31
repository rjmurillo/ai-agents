"""The gate reports before lefthook's ``timeout:`` can replace its diagnosis.

Issue #4698's whole value is one accurate message arriving ahead of the four
unrelated-looking failures the corruption would otherwise be blamed for. A
lefthook cap firing first destroys exactly that: measured on lefthook 2.1.10
(``.claude/rules/ci-scripts.md`` MUST-19), a ``timeout:`` kill lands on the
job's shell before any guard in it runs, so the reader gets a generic timeout
line instead of the repair command.

A per-call watchdog does not prevent it. ``GIT_TIMEOUT_SECONDS`` bounds one
git call, and the corrupted path runs up to five sequentially: the scoped
config read, common-dir discovery, the worktree listing, effective-bare, and
the worktree-config read. Five slow-but-successful calls fit inside every
per-call watchdog and still exceed the job's 10s cap, which is the shape this
file exists to refuse.

``GitBudget`` is therefore one deadline for the whole evaluation, clamping each
call's watchdog to what is left, and failing closed with exit 3 and a named
command when it runs out.

Coverage:

- positive: a healthy checkout spends a small fraction of the budget, and the
  budget is threaded rather than re-read per call, so five calls draw down one
  clock.
- negative: an exhausted budget exits 3 and names the command it stopped at,
  through ``main`` and through ``diagnose``; a budget with a little time left
  clamps the per-call timeout below ``GIT_TIMEOUT_SECONDS``.
- edge: the arithmetic against ``lefthook.yml``. The budget must sit under
  every declared ``repo-health`` cap with room for interpreter startup, and the
  per-call watchdog times the maximum call count must exceed the budget, or the
  budget would never be the binding constraint and this file would pass
  vacuously.

The cap is read by parsing ``lefthook.yml`` into its object graph, per
``.claude/rules/testing.md`` MUST-9: a substring search for ``timeout: 10s``
matches any job in the file.

Refs #4698.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LEFTHOOK = REPO_ROOT / "lefthook.yml"

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_repo_health

# The corrupted path's git calls, in order. Named rather than counted so a new
# call added to `diagnose` without revisiting the budget fails a test that says
# which sequence changed.
_CORRUPTED_PATH_CALLS = (
    "config --show-scope --type=bool --get-all core.bare",
    "rev-parse --path-format=absolute --git-common-dir",
    "worktree list --porcelain",
    "rev-parse --is-bare-repository",
    "config --type=bool --get extensions.worktreeConfig",
)

# Warm `uv run --frozen python` startup measured on this checkout at 0.077s and
# 0.130s, and 0.944s on the run that also built the venv. Two seconds of
# headroom is more than fifteen times the worst of those.
_STARTUP_HEADROOM_SECONDS = 2


def _git_test_env() -> dict[str, str]:
    """Return a host-independent environment for scratch Git repositories."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }


def _git(cwd: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_git_test_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"


@pytest.fixture(autouse=True)
def _use_scratch_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the gate's own git calls off the host's global and system config."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)


def _make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "tracked.txt").write_text("content\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _seconds(declared: str) -> int:
    """Parse a lefthook ``timeout:`` scalar such as ``10s`` or ``2m``."""
    unit, value = declared[-1], declared[:-1]
    assert unit in {"s", "m"}, f"unhandled lefthook timeout unit in {declared!r}"
    return int(value) * (60 if unit == "m" else 1)


def _repo_health_timeouts() -> dict[str, int]:
    """Return the declared ``repo-health`` cap per hook, from the object graph."""
    config: dict[str, Any] = yaml.safe_load(LEFTHOOK.read_text(encoding="utf-8"))
    found: dict[str, int] = {}
    for hook, body in config.items():
        if not isinstance(body, dict):
            continue
        for job in body.get("jobs", []):
            if isinstance(job, dict) and job.get("name") == "repo-health":
                found[hook] = _seconds(str(job["timeout"]))
    return found


def _record_git_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], Any]]:
    """Record every git invocation the gate makes, still running the real one.

    Returns a list of ``(argv, timeout)``. ``monkeypatch.setattr`` rather than a
    bare assignment: it restores on teardown even when the test raises, and it
    rebinds a module attribute without a type suppression.
    """
    seen: list[tuple[list[str], Any]] = []
    real = check_repo_health.subprocess.run

    def _record(argv: list[str], **kwargs: Any) -> Any:
        seen.append((argv, kwargs.get("timeout")))
        return real(argv, **kwargs)

    monkeypatch.setattr(check_repo_health.subprocess, "run", _record)
    return seen


class TestTheDeclaredCapsAndTheBudgetAgree:
    """Edge: the arithmetic that makes the script, not lefthook, report first."""

    def test_the_job_is_wired_into_both_hook_stages(self) -> None:
        """The premise: a cap this file does not find cannot be reasoned about."""
        assert sorted(_repo_health_timeouts()) == ["pre-commit", "pre-push"]

    @pytest.mark.parametrize("hook", ["pre-commit", "pre-push"])
    def test_the_budget_plus_startup_stays_under_the_declared_cap(self, hook: str) -> None:
        cap = _repo_health_timeouts()[hook]

        assert check_repo_health.GIT_BUDGET_SECONDS + _STARTUP_HEADROOM_SECONDS <= cap, (
            f"the {hook} repo-health cap is {cap}s but the script may spend "
            f"{check_repo_health.GIT_BUDGET_SECONDS}s in git, so lefthook can kill "
            "the job before it prints the repair. Lower GIT_BUDGET_SECONDS or "
            "raise the cap, and read ADR-104 rule 7 before raising the cap."
        )

    def test_the_budget_is_the_binding_constraint(self) -> None:
        """Without this the test above could pass on a budget nothing enforces."""
        per_call_ceiling = check_repo_health.GIT_TIMEOUT_SECONDS * len(_CORRUPTED_PATH_CALLS)

        assert per_call_ceiling > check_repo_health.GIT_BUDGET_SECONDS, (
            f"{len(_CORRUPTED_PATH_CALLS)} calls at "
            f"{check_repo_health.GIT_TIMEOUT_SECONDS}s each already fit inside the "
            f"{check_repo_health.GIT_BUDGET_SECONDS}s budget, so the budget bounds "
            "nothing and the cap arithmetic above proves nothing"
        )

    def test_the_corrupted_path_issues_the_calls_this_file_counts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The count above is a claim about `diagnose`; this is the measurement.

        Read from a linked worktree, which is the longest path: the ancestor
        walk finds no marker naming the common directory there, so the worktree
        listing runs as well. A poisoned main checkout short-circuits that call
        and would measure four.
        """
        repo = _make_repo(tmp_path)
        linked = tmp_path / "linked"
        _git(repo, "worktree", "add", "-q", "--detach", str(linked))
        _git(repo, "config", "core.bare", "true")
        seen = _record_git_calls(monkeypatch)

        health = check_repo_health.diagnose(linked)

        assert health.status == "corrupted"
        assert [" ".join(argv[1:]) for argv, _timeout in seen] == list(_CORRUPTED_PATH_CALLS)


class TestAnExhaustedBudgetReportsInsteadOfRunningMoreGit:
    """Negative: the deadline fails closed, and names where it stopped."""

    def test_diagnose_raises_before_spawning_git(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path)
        spent = check_repo_health.GitBudget(total=0.0)
        seen = _record_git_calls(monkeypatch)

        with pytest.raises(check_repo_health.GitExecutionError) as caught:
            check_repo_health.diagnose(repo, budget=spent)

        # The isolating assertion: raising after spawning git would still leave
        # lefthook free to kill the job mid-call (`testing.md` SHOULD 7).
        assert seen == []
        assert "git budget ran out" in str(caught.value)
        assert "--get-all core.bare" in str(caught.value)

    def test_the_cli_exits_three_when_the_budget_is_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Exit 3 is ADR-035's external failure; a return value cannot block a hook."""
        repo = _make_repo(tmp_path)
        monkeypatch.setattr(check_repo_health, "GIT_BUDGET_SECONDS", 0)

        code = check_repo_health.main([str(repo)])

        assert code == 3
        err = capsys.readouterr().err
        assert "could not be verified" in err
        assert "git budget ran out" in err

    def test_a_healthy_checkout_still_exits_zero_on_the_real_budget(
        self, tmp_path: Path
    ) -> None:
        """The discriminating control for the two cases above."""
        repo = _make_repo(tmp_path)

        assert check_repo_health.main([str(repo)]) == 0

    def test_the_remaining_budget_clamps_the_per_call_watchdog(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A late call must not be handed the full per-call watchdog."""
        repo = _make_repo(tmp_path)
        nearly_spent = check_repo_health.GitBudget(total=0.25)
        seen = _record_git_calls(monkeypatch)

        check_repo_health.diagnose(repo, budget=nearly_spent)

        timeouts = [timeout for _argv, timeout in seen]
        assert timeouts, "no git call was made, so nothing was clamped"
        assert max(timeouts) <= 0.25
        assert max(timeouts) < check_repo_health.GIT_TIMEOUT_SECONDS


class TestTheBudgetIsSharedRatherThanPerCall:
    """Positive: one clock across the whole evaluation, not one per call."""

    def test_one_budget_object_reaches_every_call(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "core.bare", "true")
        budget = check_repo_health.GitBudget()
        before = budget.remaining()

        check_repo_health.diagnose(repo, budget=budget)

        assert budget.remaining() < before
        assert budget.remaining() > 0

    def test_a_default_budget_starts_fresh_each_evaluation(self, tmp_path: Path) -> None:
        """Two evaluations in one process must not share a clock."""
        repo = _make_repo(tmp_path)

        assert check_repo_health.diagnose(repo).status == "usable"
        assert check_repo_health.diagnose(repo).status == "usable"
