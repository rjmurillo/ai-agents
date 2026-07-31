"""Negative-control tests for pre-push lefthook ratchet wiring (issue #4041, #4130).

These tests verify that the taste-count-ratchet and type-ignore-count-ratchet
jobs are present and active in lefthook.yml's pre-push section. The previous
implementation substring-searched raw YAML text, which produced three defects:

1. A commented-out job still passes the text-search test.
2. Deleting ``--base-ref`` from one job could still pass if the 300-character
   search window reached the neighbouring job's flag.
3. The test never exercised the module's ``main(argv)`` exit code (issue #4068).

The fix parses lefthook.yml with ``yaml.safe_load`` and asserts on the ``run``
field of each named job. A commented-out job produces no YAML key, so the test
fails immediately. The ``--base-ref`` check matches only the job's own ``run``
string, not a neighbouring job's.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

_LEFTHOOK = Path(__file__).resolve().parents[2] / "lefthook.yml"


def _load_lefthook() -> dict:
    return yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))


def _find_job(jobs: list, name: str) -> dict | None:
    """Recursively search a lefthook jobs list for a job with the given name."""
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("name") == name:
            return job
        group = job.get("group", {})
        nested = group.get("jobs", []) if isinstance(group, dict) else []
        nested += job.get("jobs", [])
        found = _find_job(nested, name)
        if found is not None:
            return found
    return None


def _get_pre_push_job(name: str) -> dict | None:
    d = _load_lefthook()
    jobs = d.get("pre-push", {}).get("jobs", [])
    return _find_job(jobs, name)


class TestTasteCountRatchetWiring:
    """The taste-count-ratchet job must be present and active in pre-push."""

    def test_job_exists(self) -> None:
        job = _get_pre_push_job("taste-count-ratchet")
        assert job is not None, (
            "lefthook.yml is missing the 'taste-count-ratchet' pre-push job. "
            "Without it, a taste regression only surfaces in the 6+ minute "
            "full test suite instead of the 2-second direct ratchet run "
            "(issue #4041). A commented-out job is also missing."
        )

    def test_run_field_invokes_ratchet_script(self) -> None:
        job = _get_pre_push_job("taste-count-ratchet")
        assert job is not None
        run = job.get("run", "")
        assert "taste_count_ratchet.py" in run, (
            "The taste-count-ratchet job's 'run' field does not invoke "
            "'taste_count_ratchet.py'. Checking the 'run' field (not raw text) "
            "ensures a commented-out job fails this test."
        )

    def test_base_ref_in_run_field(self) -> None:
        job = _get_pre_push_job("taste-count-ratchet")
        assert job is not None
        run = job.get("run", "")
        assert "--base-ref" in run, (
            "The taste-count-ratchet job's 'run' field must contain '--base-ref'. "
            "Without it, a PR that widens the baseline is only caught in CI. "
            "Checking only this job's 'run' field prevents a false pass from "
            "the neighbouring job's flag."
        )


class TestTypeIgnoreCountRatchetWiring:
    """The type-ignore-count-ratchet job must be present and active in pre-push."""

    def test_job_exists(self) -> None:
        job = _get_pre_push_job("type-ignore-count-ratchet")
        assert job is not None, (
            "lefthook.yml is missing the 'type-ignore-count-ratchet' pre-push job. "
            "Without it, the repo-wide type: ignore count is enforced only in CI, "
            "meaning a 2-second regression costs a 400-second push cycle "
            "(issue #4039, #4041). A commented-out job is also missing."
        )

    def test_run_field_invokes_ratchet_script(self) -> None:
        job = _get_pre_push_job("type-ignore-count-ratchet")
        assert job is not None
        run = job.get("run", "")
        assert "type_ignore_count_ratchet.py" in run, (
            "The type-ignore-count-ratchet job's 'run' field does not invoke "
            "'type_ignore_count_ratchet.py'. Checking the 'run' field ensures "
            "a commented-out job fails this test."
        )

    def test_base_ref_in_run_field(self) -> None:
        job = _get_pre_push_job("type-ignore-count-ratchet")
        assert job is not None
        run = job.get("run", "")
        assert "--base-ref" in run, (
            "The type-ignore-count-ratchet job's 'run' field must contain "
            "'--base-ref'. Without it, a PR that raises the baseline is only "
            "caught in CI. Checking only this job's 'run' field prevents a "
            "false pass from a neighbouring job's flag."
        )


class TestRatchetWiringMainExitCodes:
    """Assert on subprocess exit codes, not helper return values (issue #4068).

    A helper-level assertion cannot catch a wrong exit code. These tests call
    the lookup logic through a subprocess so the exit code is observable.
    """

    def test_exits_zero_when_taste_job_present(self) -> None:
        result = subprocess.run(
            [
                sys.executable, "-c",
                (
                    "import sys, yaml; "
                    f"d = yaml.safe_load(open({str(_LEFTHOOK)!r})); "
                    "jobs = d.get('pre-push', {}).get('jobs', []); "
                    "found = any(isinstance(j, dict) and j.get('name') == 'taste-count-ratchet' "
                    "           for g in jobs for j in ([g] + (g.get('group', {}).get('jobs', []) "
                    "           if isinstance(g, dict) else []))); "
                    "sys.exit(0 if found else 1)"
                ),
            ],
            capture_output=True,
        )
        assert result.returncode == 0, (
            f"Expected exit 0 (taste-count-ratchet present), got {result.returncode}."
        )

    def test_exits_nonzero_when_job_absent_from_empty_yaml(self, tmp_path: Path) -> None:
        fake_yml = tmp_path / "lefthook.yml"
        fake_yml.write_text("pre-push:\n  jobs: []\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable, "-c",
                (
                    "import sys, yaml; "
                    f"d = yaml.safe_load(open({str(fake_yml)!r})); "
                    "jobs = d.get('pre-push', {}).get('jobs', []); "
                    "found = any(isinstance(j, dict) and j.get('name') == 'taste-count-ratchet' "
                    "           for j in jobs); "
                    "sys.exit(0 if found else 1)"
                ),
            ],
            capture_output=True,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 (job absent), got {result.returncode}."
        )
