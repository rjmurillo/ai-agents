#!/usr/bin/env python3
"""Hermetic guards for the security-review e2e helpers (issue #5619).

No CLI runs here. These pin the fixture, the parsers, the runner's failure paths,
and the scope assertion, including the negative control against canned output.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import security_review_probe
from security_review_probe import (
    EXPECTED_CHANGED_FILES,
    FIXTURE_DIFF,
    REVIEW_PROMPT,
    VERDICT_TOKENS,
    assert_read_artifact,
    assert_review_covers_scope,
    changed_files_in_diff,
    claude_review_args,
    clean_env,
    fail_on_timeout,
    parse_stream_events,
    read_paths,
    review_text,
    run_security_review,
)

_GOOD_REVIEW = (
    "Scope: artifact review.diff, 2 files (src/greeter.py, tests/test_greeter.py).\n"
    "No findings.\n\n**APPROVED**"
)


def _result_event(text: str) -> dict[str, object]:
    return {"type": "result", "result": text}


def _read_event(path: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": path}}]
        },
    }


def test_expected_files_are_exactly_the_files_in_the_fixture_diff() -> None:
    assert changed_files_in_diff(FIXTURE_DIFF) == EXPECTED_CHANGED_FILES


def test_fixture_diff_is_a_patch_git_accepts(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git, "git must be on PATH"
    (tmp_path / "review.diff").write_text(FIXTURE_DIFF, encoding="utf-8")
    subprocess.run([git, "init", "-q"], cwd=tmp_path, check=True)

    result = subprocess.run(
        [git, "apply", "--check", "review.diff"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_changed_files_in_diff_returns_nothing_for_an_empty_diff() -> None:
    assert changed_files_in_diff("") == ()


def test_review_prompt_does_not_name_the_expected_files() -> None:
    prompt = REVIEW_PROMPT.format(path="/tmp/x/review.diff")

    assert not [path for path in EXPECTED_CHANGED_FILES if path in prompt]


def test_good_review_passes_the_scope_assertion() -> None:
    assert_review_covers_scope(_GOOD_REVIEW, EXPECTED_CHANGED_FILES)


@pytest.mark.parametrize("token", VERDICT_TOKENS)
def test_each_taxonomy_token_counts_as_a_verdict(token: str) -> None:
    text = f"src/greeter.py and tests/test_greeter.py reviewed. {token}"

    assert_review_covers_scope(text, EXPECTED_CHANGED_FILES)


def test_verdict_with_no_enumerated_files_fails() -> None:
    """Negative control (AC5): a verdict over an empty enumeration is rejected."""
    with pytest.raises(AssertionError, match="never named these changed files"):
        assert_review_covers_scope("Nothing to review.\n\n**APPROVED**", EXPECTED_CHANGED_FILES)


def test_one_missing_file_fails_and_is_named() -> None:
    text = "Reviewed src/greeter.py only. APPROVED"

    with pytest.raises(AssertionError, match=r"tests/test_greeter\.py"):
        assert_review_covers_scope(text, EXPECTED_CHANGED_FILES)


def test_files_without_a_verdict_token_fail() -> None:
    text = "Reviewed src/greeter.py and tests/test_greeter.py. Looks fine."

    with pytest.raises(AssertionError, match="no verdict token"):
        assert_review_covers_scope(text, EXPECTED_CHANGED_FILES)


def test_lowercase_verdict_word_is_not_a_verdict() -> None:
    text = "Reviewed src/greeter.py and tests/test_greeter.py. It is approved."

    with pytest.raises(AssertionError, match="no verdict token"):
        assert_review_covers_scope(text, EXPECTED_CHANGED_FILES)


def test_cannot_evaluate_blocked_fails_even_when_files_are_named() -> None:
    text = (
        "[BLOCKED] Cannot evaluate: review scope not enumerable. "
        "Need src/greeter.py and tests/test_greeter.py as a diff artifact."
    )

    with pytest.raises(AssertionError, match="no-verdict answer"):
        assert_review_covers_scope(text, EXPECTED_CHANGED_FILES)


def test_review_text_prefers_the_result_event() -> None:
    events = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "draft"}]}},
        _result_event("final"),
    ]

    assert review_text(events) == "final"


def test_review_text_falls_back_to_assistant_text_without_a_result_event() -> None:
    events = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "partial"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}},
    ]

    assert review_text(events) == "partial"


def test_review_text_is_empty_for_an_empty_stream() -> None:
    assert review_text([]) == ""


def test_parse_stream_events_skips_blank_lines_and_decodes_objects() -> None:
    stdout = '{"type": "system"}\n\n{"type": "result", "result": "x"}\n'

    assert parse_stream_events(stdout) == [{"type": "system"}, {"type": "result", "result": "x"}]


def test_parse_stream_events_rejects_a_non_object_event() -> None:
    with pytest.raises(AssertionError, match="must be an object"):
        parse_stream_events("[1, 2]\n")


def test_read_paths_collects_only_read_tool_calls(tmp_path: Path) -> None:
    target = tmp_path / "review.diff"
    events = [
        _read_event(str(target)),
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Grep", "input": {"file_path": "/x"}}]
            },
        },
        {"type": "user", "message": {"content": []}},
    ]

    assert read_paths(events) == [target.resolve()]


def test_assert_read_artifact_passes_when_the_artifact_was_read(tmp_path: Path) -> None:
    artifact = tmp_path / "review.diff"

    assert_read_artifact([_read_event(str(artifact))], artifact)


def test_assert_read_artifact_fails_when_another_file_was_read(tmp_path: Path) -> None:
    artifact = tmp_path / "review.diff"

    with pytest.raises(AssertionError, match="never read the diff artifact"):
        assert_read_artifact([_read_event(str(tmp_path / "other.diff"))], artifact)


def test_assert_read_artifact_fails_when_nothing_was_read(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="never read the diff artifact"):
        assert_read_artifact([], tmp_path / "review.diff")


def test_review_args_pin_the_agent_the_read_only_tools_and_the_artifact_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security_review_probe, "resolve_executable", lambda name: name)
    artifact = tmp_path / "review.diff"

    args = claude_review_args(artifact)

    assert args[args.index("--agent") + 1] == "security"
    assert args[args.index("--allowedTools") + 1] == "Read,Glob,Grep"
    assert args[args.index("--add-dir") + 1] == str(tmp_path)
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert str(artifact) in args[-1]


def test_clean_env_strips_plugin_root_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("claude_plugin_root", "/x")
    monkeypatch.setenv("KEEP_ME", "1")

    env = clean_env()

    assert "claude_plugin_root" not in env
    assert env["KEEP_ME"] == "1"


def test_timeout_is_reported_as_a_failure_not_a_skip() -> None:
    exc = subprocess.TimeoutExpired(cmd=["claude"], timeout=180)

    with pytest.raises(AssertionError, match="exceeded 180s"):
        fail_on_timeout("claude security review", exc)


def test_run_security_review_returns_events_from_a_clean_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security_review_probe, "resolve_executable", lambda name: name)
    done = subprocess.CompletedProcess(
        [], 0, stdout='{"type": "result", "result": "ok"}\n', stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: done)

    events = run_security_review(tmp_path / "review.diff")

    assert review_text(events) == "ok"


def test_run_security_review_fails_on_a_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security_review_probe, "resolve_executable", lambda name: name)
    failed = subprocess.CompletedProcess([], 2, stdout="", stderr="boom")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: failed)

    with pytest.raises(AssertionError, match=r"failed \(rc=2\)"):
        run_security_review(tmp_path / "review.diff")


def test_run_security_review_fails_on_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security_review_probe, "resolve_executable", lambda name: name)

    def hang(*args: object, **kwargs: object) -> NoReturn:
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=1)

    monkeypatch.setattr(subprocess, "run", hang)

    with pytest.raises(AssertionError, match="exceeded 1s"):
        run_security_review(tmp_path / "review.diff")


def test_run_security_review_skips_a_spent_credit_balance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security_review_probe, "resolve_executable", lambda name: name)
    blocked = subprocess.CompletedProcess([], 1, stdout="", stderr="Credit balance is too low")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: blocked)

    with pytest.raises(pytest.skip.Exception):
        run_security_review(tmp_path / "review.diff")
