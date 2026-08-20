"""Tests for hook skip-during-merge configuration.

Verifies that taste-advisory and adr-review-policy both carry ``skip: merge``
in lefthook.yml so that merge commits importing large base-branch trees do not
trigger false authored-file violations.

Relates to: issue #4307, issue #4308.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"


def _flatten_jobs(items: Sequence[dict[str, object]]) -> Iterator[dict[str, object]]:
    for item in items:
        group = item.get("group")
        if isinstance(group, dict):
            jobs = group.get("jobs")
            assert isinstance(jobs, list)
            yield from _flatten_jobs(jobs)
            continue
        yield item


def _job_map(config: dict[str, object], hook: str) -> dict[str, dict[str, object]]:
    hook_cfg = config[hook]
    assert isinstance(hook_cfg, dict)
    jobs = hook_cfg["jobs"]
    assert isinstance(jobs, list)
    return {str(job["name"]): job for job in _flatten_jobs(jobs)}


def _load() -> dict[str, object]:
    return yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))


class TestTasteAdvisorySkipsMerge:
    """taste-advisory must not fire during a merge commit."""

    def test_skip_merge_present(self) -> None:
        config = _load()
        jobs = _job_map(config, "pre-commit")
        job = jobs["taste-advisory"]
        skip = cast(list[object], job.get("skip", []))
        assert "merge" in skip, (
            "taste-advisory is missing 'skip: merge'; it will block merge commits "
            "that import main-side files (issue #4308)"
        )

    def test_skip_is_list(self) -> None:
        config = _load()
        jobs = _job_map(config, "pre-commit")
        skip = cast(list[object], jobs["taste-advisory"].get("skip", []))
        assert isinstance(skip, list), "skip must be a list, not a scalar"


class TestAdrReviewPolicySkipsMerge:
    """adr-review-policy must not fire during a merge commit."""

    def test_skip_merge_present(self) -> None:
        config = _load()
        jobs = _job_map(config, "pre-commit")
        job = jobs["adr-review-policy"]
        skip = cast(list[object], job.get("skip", []))
        assert "merge" in skip, (
            "adr-review-policy is missing 'skip: merge'; it will block merge commits "
            "that touch ADR files inherited from main (issue #4307)"
        )

    def test_skip_is_list(self) -> None:
        config = _load()
        jobs = _job_map(config, "pre-commit")
        skip = cast(list[object], jobs["adr-review-policy"].get("skip", []))
        assert isinstance(skip, list), "skip must be a list, not a scalar"


class TestNegativeControl:
    """Confirm that removing skip: merge from the YAML would fail the test."""

    def test_session_policy_also_skips_merge(self) -> None:
        """session-policy already had skip: merge; this is a canary for the YAML parser."""
        config = _load()
        jobs = _job_map(config, "pre-commit")
        job = jobs["session-policy"]
        skip = cast(list[object], job.get("skip", []))
        assert "merge" in skip, "session-policy lost its skip: merge (parser regression)"
