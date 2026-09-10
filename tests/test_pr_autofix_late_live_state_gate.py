# taste-lint: ignore file-size, shared harness checks both generated workflows.
"""Regression tests for the late pr-autofix live-state gate.

Issue #4349 reproduced twice when a PR merged after review work but before a
base refresh. The initial live-state result was still ACT, so the session
started a merge into a deleted branch and left reviewed commits unpushed.

The gate re-polls ``check_pr_live_state.py`` immediately before every mutation
and binds the answer to the head and base identity captured by the current
readiness cycle, so a PR that moved underneath the session skips instead of
mutating.

The advisory branch-ownership lease that used to wrap these mutations was
removed (ADR-076 withdrawn): it wrote a marker comment per acquire, renew and
release, which produced roughly 500 comments on one PR over 33 hours. The
concurrency boundary is now the Force-Push Safety SHA gate, which is a hard
gate and is covered by ``tests/test_pr_autofix_force_push_lease.py``.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARDED_DOCS = (
    ".claude/skills/pr-autofix/SKILL.md",
    "src/copilot-cli/skills/pr-autofix/SKILL.md",
)
_GUARD_START = "# late-live-state-guard:start"
_GUARD_END = "# late-live-state-guard:end"

_LIVE_STATE_STUB = '''\
import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--pull-request")
parser.add_argument("--skip-fetch", action="store_true")
parser.add_argument("--output-format")
parser.add_argument("--expected-head-sha", default="")
parser.add_argument("--expected-base-ref", default="")
parser.add_argument("--expected-base-sha", default="")
args = parser.parse_args()

state = Path(os.environ["PR_STATE_FILE"]).read_text(encoding="utf-8").strip()
check_log = Path(os.environ["CHECK_LOG"])
is_initial = not check_log.exists()
with check_log.open("a", encoding="utf-8") as stream:
    stream.write(state + "\\n")

if state == "ERROR":
    print(json.dumps({"Success": False, "Data": None}))
    raise SystemExit(3)

expected = (
    args.expected_head_sha,
    args.expected_base_ref,
    args.expected_base_sha,
)
if not is_initial and expected != ("abc123def456", "main", "def456abc123"):
    action = "SKIP"
    reason = "PR identity changed since the readiness gate"
    exit_code = 1
elif state in {"MERGED", "CLOSED"}:
    action = "SKIP"
    reason = f"PR is {state.lower()}"
    exit_code = 1
else:
    action = "ACT"
    reason = (
        "Supersession probe inconclusive; fail open"
        if state == "INCONCLUSIVE"
        else "PR is still open and actionable"
    )
    exit_code = 0

print(json.dumps({
    "Success": True,
    "Data": {
        "action": action,
        "reason": reason,
        "state": "OPEN" if state == "INCONCLUSIVE" else state,
        "head_sha": "abc123def456",
        "base_ref": "main",
        "base_sha": "def456abc123",
    },
}))
raise SystemExit(exit_code)
'''

_MUTATION_STUB = '''\
import os
from pathlib import Path

Path(os.environ["MUTATION_LOG"]).write_text("ran\\n", encoding="utf-8")
'''


def _extract_guard(text: str) -> str:
    start = text.find(_GUARD_START)
    end = text.find(_GUARD_END)
    assert start >= 0, f"missing {_GUARD_START}"
    assert end > start, f"missing {_GUARD_END}"
    return text[start : end + len(_GUARD_END)]


def _write_fake_scripts(scripts_dir: Path) -> None:
    (scripts_dir / "check_pr_live_state.py").write_text(_LIVE_STATE_STUB, encoding="utf-8")
    (scripts_dir / "mutation.py").write_text(_MUTATION_STUB, encoding="utf-8")


def _run_race(
    tmp_path: Path,
    late_state: str,
    guarded_doc: str,
    head_sha_override: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Drive the shipped guard through one readiness cycle plus one mutation."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    _write_fake_scripts(scripts_dir)

    state_file = tmp_path / "state"
    check_log = tmp_path / "checks"
    mutation_log = tmp_path / "mutation"
    guard = _extract_guard((REPO_ROOT / guarded_doc).read_text(encoding="utf-8"))
    override = (
        f'EXPECTED_HEAD_SHA={shlex.quote(head_sha_override)}\n'
        if head_sha_override is not None
        else ""
    )

    harness = f"""\
set -u
PR=4349
BASE=main
SCRIPTS_DIR={shlex.quote(scripts_dir.as_posix())}

printf '%s' OPEN > "$PR_STATE_FILE"
INITIAL=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" \
    --pull-request "$PR" --skip-fetch --output-format json)
test "$(printf '%s' "$INITIAL" | jq -r '.Data.action')" = "ACT"
EXPECTED_HEAD_SHA=$(printf '%s' "$INITIAL" | jq -r '.Data.head_sha')
EXPECTED_BASE_REF=$(printf '%s' "$INITIAL" | jq -r '.Data.base_ref')
EXPECTED_BASE_SHA=$(printf '%s' "$INITIAL" | jq -r '.Data.base_sha')
{override}
printf '%s' {late_state} > "$PR_STATE_FILE"
{guard}

if run_pr_mutation_if_live python3 "$SCRIPTS_DIR/mutation.py"; then
    printf '%s\n' mutation-ran
else
    printf 'mutation-skipped:%s\n' "$?"
fi
"""
    env = {
        **os.environ,
        "PATH": f"{scripts_dir}{os.pathsep}{os.environ['PATH']}",
        "PR_STATE_FILE": str(state_file),
        "CHECK_LOG": str(check_log),
        "MUTATION_LOG": str(mutation_log),
    }
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return result, check_log, mutation_log


@pytest.fixture(params=GUARDED_DOCS)
def guarded_doc(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_guard_is_shipped_in_each_agent_surface(relative_path: str) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    guard = _extract_guard(text)
    assert "run_pr_mutation_if_live()" in guard
    assert "check_pr_live_state.py" in guard
    assert '--expected-head-sha "${EXPECTED_HEAD_SHA:-}"' in guard
    assert '--expected-base-ref "${EXPECTED_BASE_REF:-}"' in guard
    assert '--expected-base-sha "${EXPECTED_BASE_SHA:-}"' in guard
    assert 'EXPECTED_HEAD_SHA=$(echo "$LIVE"' in text
    assert 'EXPECTED_BASE_SHA=$(echo "$LIVE"' in text
    assert 'if [ "$MUTATION_RC" -ne 75 ]; then' in text


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_retired_lease_is_absent_from_each_agent_surface(relative_path: str) -> None:
    """ADR-076 withdrawn: no surface may reintroduce the marker-comment lease.

    Negative control for the removal. ``--force-with-lease`` is git's own SHA
    pinning and is the surviving concurrency boundary, so it is exempt.
    """
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    retired = (
        "pr_autofix_lease.py",
        "cleanup_pr_autofix",
        "start_lease_renewal",
        "stop_lease_renewal",
        "lease_renewal_failed",
        "prepare_lease_for_mutation",
        "run_mutation_with_lease_monitor",
        "release_pr_lease",
        "lease-store-unavailable",
        "held-by:",
        "LEASE_RENEWAL_INTERVAL_SECONDS",
    )
    for token in retired:
        assert token not in text, f"{relative_path} still carries retired lease machinery: {token}"

    # Every surviving mention of "lease" must be git's --force-with-lease, which
    # lives only in the Force-Push Safety section and is the concurrency
    # boundary that replaced the advisory lease.
    force_push_heading = "## Force-Push Safety"
    assert force_push_heading in text
    body_before_force_push = text[: text.index(force_push_heading)]
    for line in body_before_force_push.splitlines():
        if "force-with-lease" in line or "force_push_lease" in line:
            continue
        assert "lease" not in line.lower(), f"{relative_path} still mentions a lease: {line}"


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_mutation_examples_use_the_late_guard(relative_path: str) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    expected = (
        'run_pr_mutation_if_live git fetch origin "$BASE"',
        'run_pr_mutation_if_live git merge origin/"$BASE" --no-edit',
        'run_pr_mutation_if_live git push origin "$BRANCH"',
        'run_pr_mutation_if_live python3 "$SCRIPTS_DIR/set_pr_auto_merge.py"',
        'run_pr_mutation_if_live python3 "$SCRIPTS_DIR/merge_pr.py"',
        "run_pr_mutation_if_live env FORCE_PUSH_OK=1 git push",
    )
    for command in expected:
        assert command in text, f"{relative_path} has an unguarded example: {command}"


def test_merged_after_review_skips_base_refresh(tmp_path: Path, guarded_doc: str) -> None:
    result, check_log, mutation_log = _run_race(tmp_path, "MERGED", guarded_doc)

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "MERGED"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout
    assert "Merged head SHA: abc123def456" in result.stdout
    assert "follow-up branch from current origin/main" in result.stdout


def test_closed_after_review_skips_and_reports_recovery_head(
    tmp_path: Path, guarded_doc: str
) -> None:
    result, check_log, mutation_log = _run_race(tmp_path, "CLOSED", guarded_doc)

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "CLOSED"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout
    assert "Closed PR head SHA: abc123def456" in result.stdout
    assert "Preserve unpushed commits or a net patch" in result.stdout


def test_open_after_review_runs_mutation(tmp_path: Path, guarded_doc: str) -> None:
    result, check_log, mutation_log = _run_race(tmp_path, "OPEN", guarded_doc)

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert mutation_log.read_text(encoding="utf-8") == "ran\n"
    assert "mutation-ran" in result.stdout


def test_inconclusive_supersession_preserves_fail_open_action(
    tmp_path: Path, guarded_doc: str
) -> None:
    result, check_log, mutation_log = _run_race(tmp_path, "INCONCLUSIVE", guarded_doc)

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "INCONCLUSIVE"]
    assert mutation_log.read_text(encoding="utf-8") == "ran\n"


def test_external_live_state_failure_skips_mutation(tmp_path: Path, guarded_doc: str) -> None:
    result, check_log, mutation_log = _run_race(tmp_path, "ERROR", guarded_doc)

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "ERROR"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout


def test_head_sha_drift_skips_mutation_on_an_open_pr(tmp_path: Path, guarded_doc: str) -> None:
    """An OPEN PR whose head moved is still a SKIP.

    Edge case that separates the live-state gate from a plain open/closed
    check: the identity binding, not the PR state, is what refuses the
    mutation here.
    """
    result, check_log, mutation_log = _run_race(
        tmp_path, "OPEN", guarded_doc, head_sha_override="0000000deadbeef"
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout
    assert "PR identity changed since the readiness gate" in result.stdout
