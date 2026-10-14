"""The hook fetches main's testmon database when none exists (issue #6239).

The fetch itself is covered in test_testmon_seed.py; these tests cover how the
hook uses it: fetch then run, fall back on failure, never fetch for the full-suite
opt-in or the CI seed job.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy, testmon_seed
from scripts.validation.testmon_seed_archive import SQLITE_MAGIC
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
    testmon,
)

pytestmark = pytest.mark.usefixtures("default_environment")

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_database_fetches_the_seed_before_the_first_partition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `.testmondata`: fetch, then run testmon over the seeded database."""
    events: list[str] = []

    def fetch(root: Path, **_kw: object) -> testmon_seed.SeedResult:
        events.append("fetch")
        (root / ".testmondata").write_bytes(SQLITE_MAGIC)
        return testmon_seed.SeedResult(True, "seeded .testmondata from testmon-db-abc")

    monkeypatch.setattr(testmon_seed, "fetch_seed", fetch)

    def run(command: list[str], *_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        events.append("run")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", run)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert events == ["fetch", "run", "run", "run", "run"]
    assert "seeded .testmondata" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("detail", "announced"),
    [("gh is not installed", True), ("a local database already exists", False)],
)
def test_a_failed_fetch_falls_back_to_the_full_testmon_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    detail: str,
    announced: bool,
) -> None:
    """A real failure is announced; an already-present database is not a failure."""
    monkeypatch.setattr(
        testmon_seed, "fetch_seed", lambda _root, **_kw: testmon_seed.SeedResult(False, detail)
    )
    seen = record_runs(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert seen == testmon(tmp_path)
    err = capsys.readouterr().err
    assert (f"no testmon seed ({detail}); this push collects the suite" in err) is announced


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        (git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1"),
        (git_hook_policy.TESTMON_NO_SEED_ENV, "1"),
    ],
)
def test_the_full_suite_opt_in_and_the_ci_seed_job_never_fetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variable: str, value: str
) -> None:
    """The opt-in has no testmon to seed, and the CI seed job must start empty."""
    monkeypatch.setenv(variable, value)
    monkeypatch.setattr(
        testmon_seed, "fetch_seed", lambda *_a, **_k: pytest.fail("this path must not fetch")
    )
    record_runs(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 0
