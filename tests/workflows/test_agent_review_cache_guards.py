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


def test_no_save_cache_when_populate_skipped(action_yaml: dict) -> None:
    steps = action_yaml["runs"]["steps"]
    save = [s for s in steps if s.get("name") == "Save cache"]
    assert len(save) == 1
    cond = save[0].get("if", "")
    assert "steps.populate-cache.outputs.cache_populated == 'true'" in cond


def test_get_repo_root_walks_up_to_repo_marker() -> None:
    """`get_repo_root()` resolves to a real repo dir containing `.git` or `.claude`."""
    root = get_repo_root()
    assert root.is_dir()
    assert (root / ".git").exists() or (root / ".claude").exists()


def test_populate_cache_default_cache_root_anchored_to_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default `cache_root` must resolve under the repo root, not CWD (#2224, CWE-22)."""
    # Run from an unrelated CWD to prove the default does NOT use it.
    monkeypatch.chdir(tmp_path)

    repo_root = get_repo_root()
    expected_cache = repo_root / "ai-review-cache"
    # Snapshot whether the dir existed before so we don't pollute the repo.
    pre_existed = expected_cache.exists()
    pre_existing_agents = (
        {p.name for p in expected_cache.iterdir()} if pre_existed else set()
    )

    github_output = tmp_path / "github-output.txt"
    # Use a recognizable, unique agent name that won't collide with a real one.
    test_agent = "_test_2224_agent"

    try:
        populated = populate_cache(
            agent=test_agent,
            verdict="PASS",
            findings="anchored-default",
            infra_failure="false",
            github_output=github_output,
        )
        assert populated is True
        # The agent dir MUST land under the repo-anchored default, not under CWD.
        assert (expected_cache / test_agent / "verdict.txt").read_text(
            encoding="utf-8"
        ) == "PASS"
        # And it MUST NOT have leaked into the CWD.
        assert not (tmp_path / "ai-review-cache").exists()
    finally:
        # Clean only what we created; never disturb pre-existing cache contents.
        agent_dir = expected_cache / test_agent
        if agent_dir.exists():
            shutil.rmtree(agent_dir, ignore_errors=True)
        if not pre_existed and expected_cache.exists():
            remaining = {p.name for p in expected_cache.iterdir()}
            if not remaining - pre_existing_agents:
                expected_cache.rmdir()
