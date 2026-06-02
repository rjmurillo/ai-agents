"""Regression tests for #2195: malformed verdicts must not be cached.

When the AI review pipeline produces an empty verdict or one the parser cannot
recognize (returned as ``NEEDS_REVIEW``), the composite action previously saved
that result to the SHA keyed cache. Subsequent reruns served the bad result
from cache, so a transient truncation or network blip became a sticky failing
check that could only be cleared by pushing a new commit or setting
``bypass-cache``.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

import scripts.ai_review_common.cache_guard as cache_guard
from scripts.ai_review_common.cache_guard import (
    get_repo_root,
    populate_cache,
    skip_cache_reason,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / ".github" / "actions" / "agent-review" / "action.yml"
SCRATCH_ROOT = REPO_ROOT / ".pytest_cache" / "agent_review_cache_guards"


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


@pytest.fixture
def scratch_dir() -> Path:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="case-", dir=SCRATCH_ROOT))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.parametrize(
    ("verdict", "infra_failure", "expected_reason"),
    [
        ("PASS", "true", "infrastructure failure"),
        ("", "false", "empty verdict (truncated or malformed AI output)"),
        ("NEEDS_REVIEW", "false", "verdict is NEEDS_REVIEW (malformed AI output)"),
    ],
)
def test_populate_cache_skips_non_cacheable_results(
    verdict: str,
    infra_failure: str,
    expected_reason: str,
) -> None:
    assert skip_cache_reason(verdict, infra_failure) == expected_reason


def test_populate_cache_writes_valid_review(scratch_dir: Path) -> None:
    github_output = scratch_dir / "github-output.txt"
    cache_root = scratch_dir / "ai-review-cache"

    populated = populate_cache(
        agent="qa",
        verdict="PASS",
        findings="No issues found.",
        infra_failure="false",
        github_output=github_output,
        cache_root=cache_root,
    )

    assert populated is True
    assert (cache_root / "qa" / "verdict.txt").read_text(encoding="utf-8") == "PASS"
    assert (
        cache_root / "qa" / "findings.txt"
    ).read_text(encoding="utf-8") == "No issues found."
    assert github_output.read_text(encoding="utf-8") == "cache_populated=true\n"


def test_populate_cache_does_not_write_skipped_review(scratch_dir: Path) -> None:
    github_output = scratch_dir / "github-output.txt"
    cache_root = scratch_dir / "ai-review-cache"

    populated = populate_cache(
        agent="qa",
        verdict="NEEDS_REVIEW",
        findings="Parser fallback.",
        infra_failure="false",
        github_output=github_output,
        cache_root=cache_root,
    )

    assert populated is False
    assert not (cache_root / "qa").exists()
    assert github_output.read_text(encoding="utf-8") == "cache_populated=false\n"


def test_populate_cache_step_delegates_to_python_script(populate_cache_step: dict) -> None:
    run = populate_cache_step.get("run")
    assert run == "python3 scripts/ai_review_common/cache_guard.py"


def test_get_repo_root_resolves_to_marker_ancestor() -> None:
    """get_repo_root walks up to an ancestor that holds .git or .claude."""
    root = get_repo_root()

    assert (root / ".git").exists() or (root / ".claude").exists()


def test_default_cache_root_anchors_to_repo_not_cwd(
    scratch_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for #2224: an unset cache_root anchors to the repo root, not
    the process CWD, so the cache cannot be diverted by the working directory
    a step happens to run from (CWE-22)."""
    anchored_root = scratch_dir / "repo"
    anchored_root.mkdir()
    elsewhere = scratch_dir / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(cache_guard, "get_repo_root", lambda: anchored_root)
    monkeypatch.chdir(elsewhere)
    github_output = scratch_dir / "github-output.txt"

    populated = populate_cache(
        agent="qa",
        verdict="PASS",
        findings="No issues found.",
        infra_failure="false",
        github_output=github_output,
    )

    assert populated is True
    assert (
        anchored_root / "ai-review-cache" / "qa" / "verdict.txt"
    ).read_text(encoding="utf-8") == "PASS"
    assert not (elsewhere / "ai-review-cache").exists()


def test_no_save_cache_when_populate_skipped(action_yaml: dict) -> None:
    steps = action_yaml["runs"]["steps"]
    save = [s for s in steps if s.get("name") == "Save cache"]
    assert len(save) == 1
    cond = save[0].get("if", "")
    assert "steps.populate-cache.outputs.cache_populated == 'true'" in cond
