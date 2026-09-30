"""Runtime-contract tests for the reflect Stop hook (issue #5817).

Every case drives the command registered in .claude/settings.json through a
shell and asserts on the process exit status and stdout, never on a helper's
return value (testing.md MUST-8). This is the check the deleted Stop hook
lacked: its suites never sent the real payload (#3184).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.hooks.reflect_nudge_support import (
    HOOK,
    REPO_ROOT,
    human,
    run_hook,
    tool_result,
    write_transcript,
)

CORRECTIONS = [human("No, use the skill script instead"), human("wrong, that's the old path")]


def _payload(transcript: Path, session_id: str = "sess-1") -> dict:
    return {"session_id": session_id, "transcript_path": str(transcript), "cwd": str(REPO_ROOT)}


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state"


def _blocked(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0
    return json.loads(result.stdout)


def test_registration_points_at_generated_hook() -> None:
    from tests.hooks.reflect_nudge_support import registered_command

    assert ".claude/hooks/Stop/invoke_reflect_nudge.py" in registered_command()
    assert HOOK.is_file()


def test_two_corrections_block_with_counts(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    decision = _blocked(run_hook(_payload(transcript), state))
    assert decision["decision"] == "block"
    assert "2 correction" in decision["reason"]
    assert "reflect" in decision["reason"]


def test_reason_never_quotes_transcript_text(tmp_path: Path, state: Path) -> None:
    secret = "No, the token is hunter2-secret-value"
    transcript = write_transcript(tmp_path / "t.jsonl", [human(secret)])
    result = run_hook(_payload(transcript), state)
    assert "hunter2" not in result.stdout
    assert "hunter2" not in result.stderr
    marker_text = "".join(p.read_text() for p in state.rglob("*.json"))
    assert "hunter2" not in marker_text


def test_two_praise_signals_block(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(
        tmp_path / "t.jsonl", [human("Perfect, thanks"), human("exactly what I needed")]
    )
    assert _blocked(run_hook(_payload(transcript), state))["decision"] == "block"


def test_one_praise_signal_stays_silent(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", [human("Perfect, thanks")])
    result = run_hook(_payload(transcript), state)
    assert (result.returncode, result.stdout) == (0, "")


def test_no_signal_is_silent_and_reports_examined_counts(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", [human("please add a test")])
    result = run_hook(_payload(transcript), state)
    assert (result.returncode, result.stdout) == (0, "")
    assert "1 human turns, 0 HIGH, 0 MED" in result.stderr
    assert "(silent)" in result.stderr


def test_tool_result_text_is_not_human_speech(tmp_path: Path, state: Path) -> None:
    records = [tool_result("No. wrong. incorrect. never do that"), human("carry on")]
    transcript = write_transcript(tmp_path / "t.jsonl", records)
    result = run_hook(_payload(transcript), state)
    assert (result.returncode, result.stdout) == (0, "")
    assert "0 HIGH" in result.stderr


def test_nudge_check_discriminates_tool_result_from_human(tmp_path: Path, state: Path) -> None:
    """Negative control: the same words as a human turn must block."""
    transcript = write_transcript(tmp_path / "t.jsonl", [human("No. wrong. incorrect.")])
    assert _blocked(run_hook(_payload(transcript), state))["decision"] == "block"


def test_missing_transcript_path_fails_open(state: Path) -> None:
    result = run_hook({"session_id": "sess-1", "cwd": "/x"}, state)
    assert (result.returncode, result.stdout) == (0, "")
    assert "no transcript_path" in result.stderr


def test_missing_transcript_path_negative_control(tmp_path: Path, state: Path) -> None:
    """Same case with the key present and valid must block (#3184 discriminator)."""
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    assert _blocked(run_hook(_payload(transcript), state))["decision"] == "block"


def test_legacy_messages_field_alone_does_not_nudge(state: Path) -> None:
    payload = {"session_id": "s", "messages": [{"role": "user", "content": "No, wrong"}]}
    result = run_hook(payload, state)
    assert (result.returncode, result.stdout) == (0, "")


def test_unreadable_transcript_fails_open(tmp_path: Path, state: Path) -> None:
    result = run_hook(_payload(tmp_path / "absent.jsonl"), state)
    assert (result.returncode, result.stdout) == (0, "")
    assert "unreadable" in result.stderr


@pytest.mark.parametrize("stdin", ["", "not json", "[]", "null"])
def test_bad_stdin_fails_open(stdin: str, state: Path) -> None:
    result = run_hook(stdin, state)
    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.parametrize("session_id", ["", "../evil", "a/b", "x" * 200, None, 7])
def test_invalid_session_id_fails_open(tmp_path: Path, state: Path, session_id: object) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    payload = _payload(transcript)
    payload["session_id"] = session_id
    result = run_hook(payload, state)
    assert (result.returncode, result.stdout) == (0, "")
    assert not state.exists()


def test_malformed_line_is_skipped_and_counted(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS, extra_lines=["{bad", "[1]"])
    result = run_hook(_payload(transcript), state)
    assert _blocked(result)["decision"] == "block"
    assert "2 skipped" in result.stderr


def test_stop_hook_active_reentry_exits_silently(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    payload = _payload(transcript) | {"stop_hook_active": True}
    result = run_hook(payload, state)
    assert (result.returncode, result.stdout) == (0, "")
    assert not state.exists()


def test_disabled_via_config_env(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    result = run_hook(_payload(transcript), state, {"REFLECT_NUDGE_DISABLE": "1"})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not state.exists()


def test_disable_zero_leaves_hook_enabled(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    result = run_hook(_payload(transcript), state, {"REFLECT_NUDGE_DISABLE": "0"})
    assert _blocked(result)["decision"] == "block"


def test_second_stop_with_same_signals_is_silent(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    assert _blocked(run_hook(_payload(transcript), state))["decision"] == "block"
    second = run_hook(_payload(transcript), state)
    assert (second.returncode, second.stdout) == (0, "")


def test_new_correction_after_nudge_nudges_again(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    run_hook(_payload(transcript), state)
    write_transcript(transcript, [*CORRECTIONS, human("never do that again")])
    assert _blocked(run_hook(_payload(transcript), state))["decision"] == "block"


def test_other_session_is_not_deduped(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    run_hook(_payload(transcript, "sess-a"), state)
    assert _blocked(run_hook(_payload(transcript, "sess-b"), state))["decision"] == "block"


def test_marker_is_owner_only_outside_repo(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    run_hook(_payload(transcript), state)
    marker_dir = state / "ai-agents" / "reflect-nudge"
    assert marker_dir.stat().st_mode & 0o777 == 0o700
    markers = list(marker_dir.glob("*.json"))
    assert [m.stat().st_mode & 0o777 for m in markers] == [0o600]


def test_run_writes_nothing_under_repo(tmp_path: Path, state: Path) -> None:
    def porcelain() -> str:
        return subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    before = porcelain()
    run_hook(_payload(transcript), state)
    assert porcelain() == before


def test_symlinked_state_dir_refuses_to_write(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(target)
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    result = run_hook(_payload(transcript), link)
    assert (result.returncode, result.stdout) == (0, "")
    assert list(target.rglob("*.json")) == []


def test_torn_marker_fails_open_to_no_nudge(tmp_path: Path, state: Path) -> None:
    marker_dir = state / "ai-agents" / "reflect-nudge"
    marker_dir.mkdir(parents=True)
    (marker_dir / "sess-1.json").write_text("{torn", encoding="utf-8")
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    result = run_hook(_payload(transcript), state)
    assert (result.returncode, result.stdout) == (0, "")


def test_generated_hook_matches_template() -> None:
    template = REPO_ROOT / "templates" / "hooks" / "Stop" / "invoke_reflect_nudge.py"
    assert template.read_bytes() == HOOK.read_bytes()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_scan_fault_exits_zero_through_wrapper(tmp_path: Path, state: Path) -> None:
    transcript = write_transcript(tmp_path / "t.jsonl", CORRECTIONS)
    transcript.chmod(0o000)
    result = run_hook(_payload(transcript), state)
    assert (result.returncode, result.stdout) == (0, "")
    assert "[WARNING] reflect-trigger error" in result.stderr
