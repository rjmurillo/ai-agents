"""Regression tests for #2195 — `agent-review` must not cache malformed verdicts.

When the AI-review pipeline produces an empty verdict or one the parser cannot
recognize (returned as ``NEEDS_REVIEW``), the composite action previously
saved that result to the SHA-keyed cache. Subsequent reruns served the bad
result from cache, so a transient truncation/network blip became a sticky
failing check that could only be cleared by pushing a new commit or setting
``bypass-cache``.

The fix is in ``.github/actions/agent-review/action.yml`` — the
``Populate cache directory`` step must skip cache writes when the verdict
fails structural validation, on top of the existing infrastructure-failure
guard.

These tests parse the YAML and assert each guard is present in the script so
the regression cannot be reintroduced silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ACTION_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "actions"
    / "agent-review"
    / "action.yml"
)


@pytest.fixture(scope="module")
def action_yaml() -> dict:
    assert ACTION_PATH.is_file(), f"missing action file: {ACTION_PATH}"
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def populate_cache_step(action_yaml: dict) -> dict:
    steps = action_yaml["runs"]["steps"]
    matches = [s for s in steps if s.get("name") == "Populate cache directory"]
    assert len(matches) == 1, (
        "expected exactly one 'Populate cache directory' step; "
        f"found {len(matches)}"
    )
    return matches[0]


@pytest.fixture(scope="module")
def populate_cache_script(populate_cache_step: dict) -> str:
    run = populate_cache_step.get("run")
    assert isinstance(run, str) and run, "populate-cache step missing `run:` script"
    return run


def test_populate_cache_skips_infrastructure_failure(populate_cache_script: str) -> None:
    """Pre-existing guard — kept to prevent regression."""
    assert 'INFRA_FAILURE' in populate_cache_script
    assert '"$INFRA_FAILURE" = "true"' in populate_cache_script


def test_populate_cache_skips_empty_verdict(populate_cache_script: str) -> None:
    """#2195: empty verdict means the review never produced output — do NOT cache."""
    assert "-z \"${VERDICT}\"" in populate_cache_script or \
        '-z "$VERDICT"' in populate_cache_script, (
        "populate-cache step must skip caching when VERDICT is empty (#2195). "
        "Current script:\n" + populate_cache_script
    )


def test_populate_cache_skips_needs_review_verdict(populate_cache_script: str) -> None:
    """#2195: NEEDS_REVIEW is the parser's fallback for malformed/truncated output — do NOT cache."""
    assert 'NEEDS_REVIEW' in populate_cache_script, (
        "populate-cache step must skip caching when VERDICT == NEEDS_REVIEW (#2195). "
        "Current script:\n" + populate_cache_script
    )


def test_populate_cache_logs_skip_reason(populate_cache_script: str) -> None:
    """Operators need to see WHY caching was skipped so reruns are explainable."""
    assert 'Skipping cache save' in populate_cache_script


def test_no_save_cache_when_populate_skipped(action_yaml: dict) -> None:
    """The `Save cache` step must be skipped whenever populate-cache was skipped,
    otherwise actions/cache/save would persist a stale/empty cache directory."""
    steps = action_yaml["runs"]["steps"]
    save = [s for s in steps if s.get("name") == "Save cache"]
    assert len(save) == 1
    cond = save[0].get("if", "")
    # Must gate on the populate step having actually populated the cache dir.
    # We accept either a direct outputs check or a shared boolean.
    assert "steps.populate-cache" in cond or "cache_populated" in cond, (
        "Save cache `if:` must reference the populate-cache step's output so it "
        "is skipped when populate-cache bailed out (#2195). Got: " + cond
    )
