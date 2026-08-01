"""Negative-control tests for pre-push lefthook ratchet wiring (issue #4041).

These tests verify that the taste-count-ratchet and type-ignore-count-ratchet
jobs are present in lefthook.yml's pre-push section. If either job is removed,
a regression skips the 2-second fast gate and only surfaces in the 6+ minute
full test suite -- which is what issue #4041 describes.

Each test is a negative control: it asserts the presence of a structural
property. Removing the job from lefthook.yml makes the test fail immediately
rather than waiting for the full suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_LEFTHOOK = Path(__file__).resolve().parents[2] / "lefthook.yml"
_JOB_NAMES = ("taste-count-ratchet", "type-ignore-count-ratchet")
_SCRIPT_WIRING = (
    ("taste-count-ratchet", "taste_count_ratchet.py"),
    ("type-ignore-count-ratchet", "type_ignore_count_ratchet.py"),
)
_BASELINE_WIRING = (
    ("taste-count-ratchet", "scripts/ci/taste_count_baseline.txt"),
    ("type-ignore-count-ratchet", "scripts/ci/type_ignore_count_baseline.txt"),
)


def _lefthook_content() -> str:
    return _LEFTHOOK.read_text(encoding="utf-8")


def _job_section(job_name: str) -> str:
    content = _lefthook_content()
    start = content.index(f"- name: {job_name}")
    end = content.find("\n          - name:", start + 1)
    return content[start:] if end == -1 else content[start:end]


@pytest.mark.parametrize("job_name", _JOB_NAMES)
def test_job_name_is_present(job_name: str) -> None:
    assert job_name in _lefthook_content(), (
        f"lefthook.yml is missing the {job_name!r} pre-push job. "
        "Without it, a count regression only surfaces in the full test suite."
    )


@pytest.mark.parametrize(("job_name", "script_name"), _SCRIPT_WIRING)
def test_ratchet_script_is_wired(job_name: str, script_name: str) -> None:
    assert script_name in _job_section(job_name), (
        f"The {job_name} job does not call {script_name}."
    )


@pytest.mark.parametrize("job_name", _JOB_NAMES)
def test_base_ref_flag_is_present(job_name: str) -> None:
    assert "--base-ref" in _job_section(job_name), (
        f"The {job_name} job must pass '--base-ref origin/main' "
        "so a widened baseline is blocked before merging."
    )


@pytest.mark.parametrize(("job_name", "baseline_path"), _BASELINE_WIRING)
def test_baseline_change_triggers_ratchet(job_name: str, baseline_path: str) -> None:
    assert baseline_path in _job_section(job_name), (
        f"The {job_name} job must run when only {baseline_path} changes. "
        "Otherwise a widened baseline bypasses the fast pre-push gate."
    )
