# taste-lint: ignore file-size, shared harness checks both generated workflows.
"""Regression tests for the late pr-autofix live-state gate.

Issue #4349 reproduced twice when a PR merged after review work but before a
base refresh. The initial live-state result was still ACT, so the session
started a merge into a deleted branch and left reviewed commits unpushed.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARDED_DOCS = (
    ".claude/commands/pr-autofix.md",
    "src/copilot-cli/skills/pr-autofix/SKILL.md",
)
_GUARD_START = "# late-live-state-guard:start"
_GUARD_END = "# late-live-state-guard:end"
_RENEWAL_START = "# lease-renewal:start"
_RENEWAL_END = "# lease-renewal:end"


def _process_is_live(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2]
    except FileNotFoundError:
        return False
    return state != "Z"


def _extract_guard(text: str) -> str:
    start = text.find(_GUARD_START)
    end = text.find(_GUARD_END)
    assert start >= 0, f"missing {_GUARD_START}"
    assert end > start, f"missing {_GUARD_END}"
    return text[start : end + len(_GUARD_END)]


def _extract_renewal(text: str) -> str:
    start = text.find(_RENEWAL_START)
    end = text.find(_RENEWAL_END)
    assert start >= 0, f"missing {_RENEWAL_START}"
    assert end > start, f"missing {_RENEWAL_END}"
    return text[start : end + len(_RENEWAL_END)]


def _write_fake_scripts(scripts_dir: Path) -> None:
    (scripts_dir / "check_pr_live_state.py").write_text(
        """\
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
""",
        encoding="utf-8",
    )
    (scripts_dir / "pr_autofix_lease.py").write_text(
        """\
import os
import sys
from pathlib import Path

count_file = Path(os.environ["LEASE_RENEW_COUNT_FILE"])
count = int(count_file.read_text(encoding="utf-8")) if count_file.exists() else 0
count += 1
count_file.write_text(str(count), encoding="utf-8")

with Path(os.environ["LEASE_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(" ".join(sys.argv[1:]) + "\\n")

if sys.argv[1] == "renew" and count > int(os.environ.get("LEASE_RENEW_FAIL_AFTER", "0")):
    print('{"Success": true, "Data": {"action": "SKIP", "reason": "held-by:other"}}')
    raise SystemExit(1)
print('{"Success": true}')
""",
        encoding="utf-8",
    )
    (scripts_dir / "mutation.py").write_text(
        """\
import os
import subprocess
import sys
import time
from pathlib import Path

child_log = os.environ.get("MUTATION_CHILD_LOG")
if child_log:
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import pathlib, sys, time; "
                "time.sleep(0.3); "
                "pathlib.Path(sys.argv[1]).write_text('child-ran\\\\n', encoding='utf-8')"
            ),
            child_log,
        ]
    )
    child_pid_log = os.environ.get("MUTATION_CHILD_PID_LOG")
    if child_pid_log:
        Path(child_pid_log).write_text(str(child.pid), encoding="utf-8")
    started_log = os.environ.get("MUTATION_STARTED_LOG")
    if started_log:
        Path(started_log).write_text("started\\n", encoding="utf-8")
time.sleep(float(os.environ.get("MUTATION_SLEEP_SECONDS", "0")))
Path(os.environ["MUTATION_LOG"]).write_text("ran\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    (scripts_dir / "final_poll_mutation.py").write_text(
        """\
import os
import time
from pathlib import Path

Path(os.environ["MUTATION_PID_FILE"]).write_text(str(os.getpid()), encoding="utf-8")
while True:
    time.sleep(1)
""",
        encoding="utf-8",
    )
    fake_sleep = scripts_dir / "sleep"
    fake_sleep.write_text(
        """#!/usr/bin/env python3
import os
import signal
import sys
import time
from pathlib import Path

duration = sys.argv[1]
if duration == "0.01" and os.environ.get("FINAL_POLL_EXIT"):
    count_file = Path(os.environ["FINAL_POLL_SLEEP_COUNT"])
    count = int(count_file.read_text(encoding="utf-8")) if count_file.exists() else 0
    count += 1
    count_file.write_text(str(count), encoding="utf-8")
    if count == 10:
        pid = int(Path(os.environ["MUTATION_PID_FILE"]).read_text(encoding="utf-8"))
        os.kill(pid, signal.SIGTERM)
        while True:
            try:
                state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2]
                if state == "Z":
                    break
            except (FileNotFoundError, ProcessLookupError):
                break
            time.sleep(0.001)
time.sleep(float(duration))
""",
        encoding="utf-8",
    )
    fake_sleep.chmod(0o755)
    fake_ps = scripts_dir / "ps"
    fake_ps.write_text(
        """#!/usr/bin/env python3
import os
import subprocess
import sys

if os.environ.get("FINAL_POLL_EXIT") and "pgid=" in sys.argv:
    print("1")
    raise SystemExit(0)
raise SystemExit(subprocess.run(["/usr/bin/ps", *sys.argv[1:]]).returncode)
""",
        encoding="utf-8",
    )
    fake_ps.chmod(0o755)


def _run_race(
    tmp_path: Path,
    late_state: str,
    guarded_doc: str,
    renewal_failure: bool = False,
    immediate_lease_failure: bool = False,
    mutation_command: str | None = None,
    spawn_delayed_child: bool = False,
    exit_on_final_setup_poll: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    _write_fake_scripts(scripts_dir)

    state_file = tmp_path / "state"
    check_log = tmp_path / "checks"
    lease_log = tmp_path / "leases"
    mutation_log = tmp_path / "mutation"
    mutation_child_log = tmp_path / "mutation-child"
    mutation_child_pid_log = tmp_path / "mutation-child-pid"
    mutation_started_log = tmp_path / "mutation-started"
    mutation_pid_file = tmp_path / "mutation-pid"
    final_poll_sleep_count = tmp_path / "final-poll-sleep-count"
    renew_count = tmp_path / "renew-count"
    guard_text = (REPO_ROOT / guarded_doc).read_text(encoding="utf-8")
    guard = _extract_guard(guard_text)
    renewal_sleep = "0.01" if renewal_failure else "0.05"
    renewal_fail_after = "1" if renewal_failure else "999999"
    mutation_sleep = "5" if renewal_failure else "0"
    if immediate_lease_failure and spawn_delayed_child:
        lease_failure_override = 'lease_renewal_failed() {\n    [ -e "$MUTATION_STARTED_LOG" ]\n}\n'
    elif immediate_lease_failure:
        lease_failure_override = (
            "lease_failure_checks=0\n"
            "lease_renewal_failed() {\n"
            "    lease_failure_checks=$((lease_failure_checks + 1))\n"
            '    [ "$lease_failure_checks" -ge 2 ]\n'
            "}\n"
        )
    else:
        lease_failure_override = ""
    if exit_on_final_setup_poll:
        mutation_invocation = 'python3 "$SCRIPTS_DIR/final_poll_mutation.py"'
    else:
        mutation_invocation = mutation_command or 'python3 "$SCRIPTS_DIR/mutation.py"'

    harness = f"""\
set -u
set -m
PR=4349
BASE=main
SESSION_ID=test-session
SCRIPTS_DIR={shlex.quote(scripts_dir.as_posix())}

printf '%s' OPEN > "$PR_STATE_FILE"
INITIAL=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" \
    --pull-request "$PR" --skip-fetch --output-format json)
test "$(printf '%s' "$INITIAL" | jq -r '.Data.action')" = "ACT"
EXPECTED_HEAD_SHA=$(printf '%s' "$INITIAL" | jq -r '.Data.head_sha')
EXPECTED_BASE_REF=$(printf '%s' "$INITIAL" | jq -r '.Data.base_ref')
EXPECTED_BASE_SHA=$(printf '%s' "$INITIAL" | jq -r '.Data.base_sha')

printf '%s' {late_state} > "$PR_STATE_FILE"
{guard}
{lease_failure_override}

LEASE_RENEWAL_INTERVAL_SECONDS={renewal_sleep}

if run_pr_mutation_if_live {mutation_invocation}; then
    printf '%s\n' mutation-ran
else
    printf 'mutation-skipped:%s\n' "$?"
fi
if grep -q '^release ' "$LEASE_LOG"; then
    printf '%s\n' lease-released-before-end
else
    printf '%s\n' lease-held-after-mutation
fi
"""
    env = {
        **os.environ,
        "PATH": f"{scripts_dir}{os.pathsep}{os.environ['PATH']}",
        "PR_STATE_FILE": str(state_file),
        "CHECK_LOG": str(check_log),
        "LEASE_LOG": str(lease_log),
        "MUTATION_LOG": str(mutation_log),
        "LEASE_RENEW_COUNT_FILE": str(renew_count),
        "LEASE_RENEW_FAIL_AFTER": renewal_fail_after,
        "MUTATION_SLEEP_SECONDS": mutation_sleep,
        "MUTATION_CHILD_LOG": str(mutation_child_log)
        if renewal_failure or spawn_delayed_child
        else "",
        "MUTATION_CHILD_PID_LOG": str(mutation_child_pid_log),
        "MUTATION_STARTED_LOG": str(mutation_started_log) if spawn_delayed_child else "",
        "MUTATION_PID_FILE": str(mutation_pid_file),
        "FINAL_POLL_SLEEP_COUNT": str(final_poll_sleep_count),
        "FINAL_POLL_EXIT": "1" if exit_on_final_setup_poll else "",
    }
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, check_log, lease_log, mutation_log


@pytest.fixture(params=GUARDED_DOCS)
def guarded_doc(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_renewal_starts_after_acquire_and_all_releases_stop_it(relative_path: str) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    renewal = _extract_renewal(text)
    acquire = text.index('LEASE=$(python3 "$SCRIPTS_DIR/pr_autofix_lease.py" acquire')
    start = text.index("\nstart_lease_renewal", acquire)
    live_state = text.index("# Step 2: Live-state gate", acquire)

    assert acquire < start < live_state
    assert "LEASE_RENEW_FAILURE_FILE" in renewal
    assert "LEASE_CLEANUP_DONE=0" in renewal
    assert 'pr_autofix_lease.py" renew' in renewal
    assert 'kill "$LEASE_RENEW_PID"' in renewal
    assert 'wait "$LEASE_RENEW_PID"' in renewal
    assert "lease_renewal_failed()" in renewal
    assert "cleanup_pr_autofix()" in renewal
    assert "release_pr_lease()" in renewal
    assert "prepare_lease_for_mutation()" in renewal
    assert "run_mutation_with_lease_monitor()" in renewal
    assert 'pr_autofix_lease.py" release' in renewal
    assert "trap cleanup_pr_autofix EXIT" in renewal
    assert "exit 130" in renewal
    assert "exit 143" in renewal


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_renewal_runs_periodically_and_stops_before_release(
    relative_path: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    renewal = _extract_renewal(text)
    assert "LEASE_RENEW_INTERVAL_SECONDS" in renewal
    assert 'sleep "$LEASE_RENEW_INTERVAL_SECONDS"' in renewal
    assert "cleanup_pr_autofix()" in renewal
    assert "release_pr_lease()" in renewal


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_release_stops_an_active_renewal_before_posting_tombstone(
    relative_path: str,
) -> None:
    renewal = _extract_renewal((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    assert "stop_lease_renewal()" in renewal
    assert "cleanup_pr_autofix()" in renewal
    assert 'kill -- "-$LEASE_RENEW_PID"' in renewal


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_unavailable_renewal_blocks_mutation(
    relative_path: str,
) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    guard = _extract_guard(text)
    assert "lease_renewal_failed" in guard
    assert "cleanup_pr_autofix" in guard
    assert "sleep 0.05" in guard


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
    assert "lease_renewal_failed" in guard
    assert "cleanup_pr_autofix" in text
    assert "release_pr_lease()" in text
    assert 'if [ "$MUTATION_RC" -ne 75 ]; then' in text


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


def test_merged_after_review_skips_base_refresh_and_releases_lease(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "MERGED",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "MERGED"]
    assert not mutation_log.exists()
    mutation_child_log = tmp_path / "mutation-child"
    assert not mutation_child_log.exists()
    assert "mutation-skipped:75" in result.stdout
    assert "Merged head SHA: abc123def456" in result.stdout
    assert "follow-up branch from current origin/main" in result.stdout


def test_closed_after_review_skips_and_reports_recovery_head(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "CLOSED",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "CLOSED"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout
    assert "Closed PR head SHA: abc123def456" in result.stdout
    assert "Preserve unpushed commits or a net patch" in result.stdout


def test_open_after_review_runs_mutation_and_keeps_lease(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "OPEN",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert mutation_log.read_text(encoding="utf-8") == "ran\n"
    assert "mutation-ran" in result.stdout
    assert "lease-held-after-mutation" in result.stdout


def test_inconclusive_supersession_preserves_fail_open_action(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "INCONCLUSIVE",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == [
        "OPEN",
        "INCONCLUSIVE",
    ]
    assert mutation_log.read_text(encoding="utf-8") == "ran\n"


def test_external_live_state_failure_skips_mutation_and_releases_lease(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "ERROR",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "ERROR"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout


def test_ownership_loss_during_mutation_stops_command(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "OPEN",
        guarded_doc,
        renewal_failure=True,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert not mutation_log.exists()
    child_pid_log = tmp_path / "mutation-child-pid"
    if child_pid_log.exists():
        child_pid = int(child_pid_log.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 1
        while _process_is_live(child_pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not _process_is_live(child_pid)
    assert "Stopping mutation for #4349: lease ownership lost" in result.stdout
    assert "mutation-skipped:75" in result.stdout


def test_fast_exit_reports_lease_loss_after_wait(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "OPEN",
        guarded_doc,
        immediate_lease_failure=True,
        mutation_command="true",
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert not mutation_log.exists()
    assert "Mutation completed as lease ownership was lost for #4349" in result.stdout
    assert "mutation-skipped:75" in result.stdout
    assert "mutation-ran" not in result.stdout


def test_fast_exit_stops_delayed_child_after_lease_loss(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, _mutation_log = _run_race(
        tmp_path,
        "OPEN",
        guarded_doc,
        immediate_lease_failure=True,
        spawn_delayed_child=True,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert (tmp_path / "mutation-started").read_text(encoding="utf-8") == "started\n"
    assert "mutation-skipped:75" in result.stdout
    assert "mutation-ran" not in result.stdout
    assert not (tmp_path / "mutation-child").exists()


def test_final_setup_poll_exit_reports_lease_loss(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, _lease_log, mutation_log = _run_race(
        tmp_path,
        "OPEN",
        guarded_doc,
        immediate_lease_failure=True,
        exit_on_final_setup_poll=True,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert not mutation_log.exists()
    assert "Mutation completed as lease ownership was lost for #4349" in result.stdout
    assert "mutation-skipped:75" in result.stdout
    assert "mutation-ran" not in result.stdout
