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

_LEFTHOOK = Path(__file__).resolve().parents[2] / "lefthook.yml"


def _lefthook_content() -> str:
    return _LEFTHOOK.read_text(encoding="utf-8")


def _job_section(job_name: str) -> str:
    content = _lefthook_content()
    start = content.index(f"- name: {job_name}")
    end = content.find("\n          - name:", start + 1)
    return content[start:] if end == -1 else content[start:end]


class TestTasteCountRatchetWiring:
    """The taste-count-ratchet job must be present in the pre-push section."""

    def test_job_name_is_present(self) -> None:
        assert "taste-count-ratchet" in _lefthook_content(), (
            "lefthook.yml is missing the 'taste-count-ratchet' pre-push job. "
            "Without it, a taste regression only surfaces in the 6+ minute "
            "full test suite instead of the 2-second direct ratchet run "
            "(issue #4041)."
        )

    def test_ratchet_script_is_wired(self) -> None:
        content = _lefthook_content()
        assert "taste_count_ratchet.py" in content, (
            "lefthook.yml does not call 'taste_count_ratchet.py'. "
            "The job exists but does not invoke the ratchet script."
        )

    def test_base_ref_flag_is_present(self) -> None:
        job_section = _job_section("taste-count-ratchet")
        assert "--base-ref" in job_section, (
            "The taste-count-ratchet job must pass '--base-ref origin/main' "
            "so a PR that widens the baseline is blocked before merging."
        )

    def test_baseline_change_triggers_ratchet(self) -> None:
        job_section = _job_section("taste-count-ratchet")
        assert "scripts/ci/taste_count_baseline.txt" in job_section, (
            "The taste-count-ratchet job must run when only its baseline changes. "
            "Otherwise a widened baseline bypasses the fast pre-push gate."
        )


class TestTypeIgnoreCountRatchetWiring:
    """The type-ignore-count-ratchet job must be present in the pre-push section."""

    def test_job_name_is_present(self) -> None:
        assert "type-ignore-count-ratchet" in _lefthook_content(), (
            "lefthook.yml is missing the 'type-ignore-count-ratchet' pre-push job. "
            "Without it, the repo-wide type: ignore count is enforced only in CI, "
            "meaning a 2-second regression costs a 400-second push cycle (issue #4039). "
            "Note: git_hook_policy.py explicitly excludes type: ignore from the security "
            "suppression gate, so there is no changed-line fallback for this check."
        )

    def test_ratchet_script_is_wired(self) -> None:
        content = _lefthook_content()
        assert "type_ignore_count_ratchet.py" in content, (
            "lefthook.yml does not call 'type_ignore_count_ratchet.py'."
        )

    def test_base_ref_flag_is_present(self) -> None:
        job_section = _job_section("type-ignore-count-ratchet")
        assert "--base-ref" in job_section, (
            "The type-ignore-count-ratchet job must pass '--base-ref origin/main' "
            "so a PR that raises the baseline is blocked before merging."
        )

    def test_baseline_change_triggers_ratchet(self) -> None:
        job_section = _job_section("type-ignore-count-ratchet")
        assert "scripts/ci/type_ignore_count_baseline.txt" in job_section, (
            "The type-ignore-count-ratchet job must run when only its baseline changes. "
            "Otherwise a widened baseline bypasses the fast pre-push gate."
        )
