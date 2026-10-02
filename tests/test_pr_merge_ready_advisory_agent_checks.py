"""Advisory agent checks never block a merge (owner policy, D4/D6).

The list comes from the trusted ref, so a PR cannot exempt its own failing
check by editing it (CWE-829). A listed check that the ruleset requires stays
blocking.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tests.test_test_pr_merge_ready import _OPEN_PR, _mod

check_merge_readiness = _mod.check_merge_readiness

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ".claude/skills/pr-review/pr-review-config.yaml"
AGENT_CHECK = "Validate Spec Coverage"


def _pr_with(*rows: dict) -> dict:
    pr_data = json.loads(json.dumps(_OPEN_PR))
    pr = pr_data["repository"]["pullRequest"]
    pr["mergeStateStatus"] = "UNSTABLE"
    rollup = pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
    rollup["contexts"]["nodes"] = list(rows)
    rollup["state"] = "FAILURE"
    return pr_data


def _row(name: str, conclusion: str | None, status: str = "COMPLETED", required: bool = False):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "isRequired": required,
    }


def _readiness(pr_data: dict, advisory: set[str], include_non_required: bool = False) -> dict:
    with (
        patch("test_pr_merge_ready.gh_graphql", return_value=pr_data),
        patch("test_pr_merge_ready._load_advisory_agent_checks", return_value=frozenset(advisory)),
    ):
        return check_merge_readiness("o", "r", 42, include_non_required=include_non_required)


# ---------------------------------------------------------------------------
# Positive: a listed agent check does not block in any state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("include_non_required", [False, True])
@pytest.mark.parametrize(
    ("status", "conclusion"),
    [
        ("COMPLETED", "FAILURE"),
        ("WAITING", None),
        ("PENDING", None),
        ("QUEUED", None),
        ("IN_PROGRESS", None),
        ("COMPLETED", "CANCELLED"),
        ("COMPLETED", "SKIPPED"),
        ("COMPLETED", "TIMED_OUT"),
    ],
)
def test_listed_agent_check_never_blocks(
    status: str, conclusion: str | None, include_non_required: bool
) -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, conclusion, status))
    result = _readiness(pr_data, {AGENT_CHECK}, include_non_required)
    assert result["CanMerge"] is True, result["Reasons"]
    assert result["UndisposedNonRequiredFailures"] == []
    assert result["CIPassing"] is True


# ---------------------------------------------------------------------------
# Negative: an unlisted non-required failure still blocks
# ---------------------------------------------------------------------------


def test_unlisted_nonrequired_failure_still_blocks() -> None:
    pr_data = _pr_with(_row("Run Python Tests", "FAILURE"))
    result = _readiness(pr_data, {AGENT_CHECK})
    assert result["CanMerge"] is False
    assert result["UndisposedNonRequiredFailures"] == ["Run Python Tests"]


def test_unlisted_pending_still_blocks_when_non_required_count() -> None:
    pr_data = _pr_with(_row("Run Python Tests", None, "IN_PROGRESS"))
    result = _readiness(pr_data, {AGENT_CHECK}, include_non_required=True)
    assert result["CanMerge"] is False


def test_listed_check_does_not_hide_an_unlisted_failure_beside_it() -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, "FAILURE"), _row("Run Python Tests", "FAILURE"))
    result = _readiness(pr_data, {AGENT_CHECK})
    assert result["CanMerge"] is False
    assert result["UndisposedNonRequiredFailures"] == ["Run Python Tests"]


def test_empty_list_exempts_nothing() -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, "FAILURE"))
    result = _readiness(pr_data, set())
    assert result["CanMerge"] is False


# ---------------------------------------------------------------------------
# Edge: listed but required still blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("status", "conclusion"), [("COMPLETED", "FAILURE"), ("WAITING", None)])
def test_listed_but_required_check_still_blocks(status: str, conclusion: str | None) -> None:
    pr_data = _pr_with(_row(AGENT_CHECK, conclusion, status, required=True))
    result = _readiness(pr_data, {AGENT_CHECK})
    assert result["CanMerge"] is False
    assert any(AGENT_CHECK in reason for reason in result["Reasons"])


# ---------------------------------------------------------------------------
# Edge: the list is read from the trusted ref, never the branch
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=30)


def _config(names: list[str]) -> str:
    items = "".join(f'  - "{name}"\n' for name in names)
    return f"scripts: {{}}\nadvisory_agent_checks:\n{items}\ntransport_preflight: {{}}\n"


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "t")
    target = work / CONFIG_PATH
    target.parent.mkdir(parents=True)
    target.write_text(_config([AGENT_CHECK]), encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "push", "-q", "origin", "HEAD:main")
    _git(work, "fetch", "-q", "origin", "main")
    return work


def test_loader_reads_the_trusted_ref(clone: Path) -> None:
    assert _mod._load_advisory_agent_checks(cwd=str(clone)) == {AGENT_CHECK}


def test_branch_edited_list_is_ignored(clone: Path) -> None:
    target = clone / CONFIG_PATH
    target.write_text(_config([AGENT_CHECK, "Run Python Tests"]), encoding="utf-8")
    _git(clone, "commit", "-qam", "branch edits the list")
    assert _mod._load_advisory_agent_checks(cwd=str(clone)) == {AGENT_CHECK}


def test_uncommitted_edit_is_ignored(clone: Path) -> None:
    (clone / CONFIG_PATH).write_text(_config(["Run Python Tests"]), encoding="utf-8")
    assert _mod._load_advisory_agent_checks(cwd=str(clone)) == {AGENT_CHECK}


def test_missing_trusted_ref_fails_closed(clone: Path) -> None:
    assert _mod._load_advisory_agent_checks(trusted_ref="origin/absent", cwd=str(clone)) == set()


def test_not_a_repository_fails_closed(tmp_path: Path) -> None:
    assert _mod._load_advisory_agent_checks(cwd=str(tmp_path)) == set()


def test_end_to_end_branch_edit_does_not_exempt_a_failing_check(clone: Path) -> None:
    (clone / CONFIG_PATH).write_text(_config([AGENT_CHECK, "Run Python Tests"]), encoding="utf-8")
    _git(clone, "commit", "-qam", "branch edits the list")
    trusted = _mod._load_advisory_agent_checks(cwd=str(clone))
    result = _readiness(_pr_with(_row("Run Python Tests", "FAILURE")), set(trusted))
    assert result["CanMerge"] is False


# ---------------------------------------------------------------------------
# Parser and shipped contract
# ---------------------------------------------------------------------------


def test_parser_reads_quoted_and_bare_items_and_stops_at_the_next_key() -> None:
    text = (
        "other: 1\nadvisory_agent_checks:\n"
        "  - \"Quoted Name\"\n  # a comment\n  - 'Single'\n  - bare name # note\n"
        "next_key: 2\n  - not-in-list\n"
    )
    assert _mod._parse_advisory_agent_checks(text) == {"Quoted Name", "Single", "bare name"}


def test_parser_returns_empty_without_the_key() -> None:
    assert _mod._parse_advisory_agent_checks("scripts: {}\n") == frozenset()


def _gated_check_names() -> set[str]:
    names: set[str] = set()
    for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, job in (doc.get("jobs") or {}).items():
            if job.get("environment") != "agent-approval":
                continue
            name = job.get("name", key)
            matrix = (job.get("strategy") or {}).get("matrix") or {}
            if "${{ matrix.os }}" in name:
                names.update(name.replace("${{ matrix.os }}", os_) for os_ in matrix["os"])
            else:
                names.add(name)
    return names


def test_shipped_list_equals_the_agent_approval_gated_jobs() -> None:
    shipped = yaml.safe_load((REPO_ROOT / CONFIG_PATH).read_text(encoding="utf-8"))
    listed = set(shipped["advisory_agent_checks"])
    assert listed == _gated_check_names()
    assert _mod._parse_advisory_agent_checks((REPO_ROOT / CONFIG_PATH).read_text("utf-8")) == listed


def test_claude_workflow_is_not_gated() -> None:
    text = (REPO_ROOT / ".github" / "workflows" / "claude.yml").read_text(encoding="utf-8")
    assert "agent-approval" not in text
