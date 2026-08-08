"""Regression tests for the late pr-autofix live-state gate.

Issue #4349 reproduced twice when a PR merged after review work but before a
base refresh. The initial live-state result was still ACT, so the session
started a merge into a deleted branch and left reviewed commits unpushed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARDED_DOCS = (
    ".claude/commands/pr-autofix.md",
    "src/copilot-cli/skills/pr-autofix/SKILL.md",
)
_GUARD_START = "# late-live-state-guard:start"
_GUARD_END = "# late-live-state-guard:end"


def _extract_guard(text: str) -> str:
    start = text.find(_GUARD_START)
    end = text.find(_GUARD_END)
    assert start >= 0, f"missing {_GUARD_START}"
    assert end > start, f"missing {_GUARD_END}"
    return text[start : end + len(_GUARD_END)]


def _write_fake_scripts(scripts_dir: Path) -> None:
    (scripts_dir / "check_pr_live_state.py").write_text(
        """\
import json
import os
from pathlib import Path

state = Path(os.environ["PR_STATE_FILE"]).read_text(encoding="utf-8").strip()
with Path(os.environ["CHECK_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(state + "\\n")

if state == "ERROR":
    print(json.dumps({"Success": False, "Data": None}))
    raise SystemExit(3)

if state in {"MERGED", "CLOSED"}:
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

with Path(os.environ["LEASE_LOG"]).open("a", encoding="utf-8") as stream:
    stream.write(" ".join(sys.argv[1:]) + "\\n")
print('{"Success": true}')
""",
        encoding="utf-8",
    )
    (scripts_dir / "mutation.py").write_text(
        """\
import os
from pathlib import Path

Path(os.environ["MUTATION_LOG"]).write_text("ran\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )


def _run_race(
    tmp_path: Path,
    late_state: str,
    guarded_doc: str,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    _write_fake_scripts(scripts_dir)

    state_file = tmp_path / "state"
    check_log = tmp_path / "checks"
    lease_log = tmp_path / "leases"
    mutation_log = tmp_path / "mutation"
    guard_text = (REPO_ROOT / guarded_doc).read_text(encoding="utf-8")
    guard = _extract_guard(guard_text)

    harness = f"""\
set -u
PR=4349
BASE=main
SESSION_ID=test-session
SCRIPTS_DIR={scripts_dir}

printf '%s' OPEN > "$PR_STATE_FILE"
INITIAL=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" \
    --pull-request "$PR" --skip-fetch --output-format json)
test "$(printf '%s' "$INITIAL" | jq -r '.Data.action')" = "ACT"

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
        "PR_STATE_FILE": str(state_file),
        "CHECK_LOG": str(check_log),
        "LEASE_LOG": str(lease_log),
        "MUTATION_LOG": str(mutation_log),
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
def test_guard_is_shipped_in_each_agent_surface(relative_path: str) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    guard = _extract_guard(text)
    assert "run_pr_mutation_if_live()" in guard
    assert "check_pr_live_state.py" in guard
    assert 'if [ "$MUTATION_RC" -ne 75 ]; then' in text


@pytest.mark.parametrize("relative_path", GUARDED_DOCS)
def test_mutation_examples_use_the_late_guard(relative_path: str) -> None:
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    expected = (
        'run_pr_mutation_if_live git fetch origin "$BASE"',
        'run_pr_mutation_if_live git merge origin/"$BASE" --no-edit',
        'run_pr_mutation_if_live git push origin "$BRANCH"',
        "run_pr_mutation_if_live python3 "
        '"$SCRIPTS_DIR/set_pr_auto_merge.py"',
        "run_pr_mutation_if_live python3 "
        '"$SCRIPTS_DIR/merge_pr.py"',
        "run_pr_mutation_if_live env FORCE_PUSH_OK=1 git push",
    )
    for command in expected:
        assert command in text, f"{relative_path} has an unguarded example: {command}"


def test_merged_after_review_skips_base_refresh_and_releases_lease(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, lease_log, mutation_log = _run_race(
        tmp_path,
        "MERGED",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "MERGED"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout
    assert "Merged head SHA: abc123def456" in result.stdout
    assert "follow-up branch from current origin/main" in result.stdout
    assert lease_log.read_text(encoding="utf-8").splitlines() == [
        "release --pull-request 4349 --session test-session --output-format json"
    ]


def test_closed_after_review_skips_and_reports_recovery_head(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, lease_log, mutation_log = _run_race(
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
    assert lease_log.read_text(encoding="utf-8").splitlines() == [
        "release --pull-request 4349 --session test-session --output-format json"
    ]


def test_open_after_review_runs_mutation_and_keeps_lease(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, lease_log, mutation_log = _run_race(
        tmp_path,
        "OPEN",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "OPEN"]
    assert mutation_log.read_text(encoding="utf-8") == "ran\n"
    assert "mutation-ran" in result.stdout
    assert not lease_log.exists()


def test_inconclusive_supersession_preserves_fail_open_action(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, lease_log, mutation_log = _run_race(
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
    assert not lease_log.exists()


def test_external_live_state_failure_skips_mutation_and_releases_lease(
    tmp_path: Path,
    guarded_doc: str,
) -> None:
    result, check_log, lease_log, mutation_log = _run_race(
        tmp_path,
        "ERROR",
        guarded_doc,
    )

    assert result.returncode == 0, result.stderr
    assert check_log.read_text(encoding="utf-8").splitlines() == ["OPEN", "ERROR"]
    assert not mutation_log.exists()
    assert "mutation-skipped:75" in result.stdout
    assert lease_log.read_text(encoding="utf-8").splitlines() == [
        "release --pull-request 4349 --session test-session --output-format json"
    ]
