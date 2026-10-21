"""Policy flags and the ``gh api`` transport of the breach helper (issue #6757).

Coverage:
* Flags: the environment fills the defaults, unusable flags raise.
* Transport: success, retry, attempt cap, missing binary and timeout.
All subprocess I/O is faked.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.ci import consecutive_breach as cb
from tests.test_consecutive_breach import GATE, REPO, WORKFLOW, FakeApi


class TestPolicyFlags:
    def _args(self, *argv: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        cb.add_policy_arguments(parser)
        return parser.parse_args(list(argv))

    def test_strict_is_the_default_and_needs_nothing(self) -> None:
        assert cb.policy_from_args(self._args(), {}).mode == cb.MODE_STRICT

    def test_the_environment_fills_the_defaults(self, tmp_path: Path) -> None:
        env = {
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": cb.MAIN_REF,
            "GITHUB_RUN_ID": "77",
            "GITHUB_SHA": "cafe",
            "GITHUB_REPOSITORY": REPO,
        }
        out = tmp_path / cb.RECORD_FILE
        policy = cb.policy_from_args(
            self._args(
                "--breach-policy",
                "consecutive-main",
                "--workflow",
                WORKFLOW,
                "--breach-record-out",
                str(out),
            ),
            env,
        )
        assert policy.mode == cb.MODE_CONSECUTIVE
        assert (policy.run_id, policy.sha, policy.repository) == (77, "cafe", REPO)

    def test_a_pull_request_needs_no_record_path(self) -> None:
        env = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/pull/1/merge"}
        policy = cb.policy_from_args(
            self._args("--breach-policy", "consecutive-main", "--run-id", "5"), env
        )
        assert policy.mode == cb.MODE_ADVISORY

    @pytest.mark.parametrize(
        ("argv", "env", "message"),
        [
            (["--breach-policy", "consecutive-main"], {}, "event and the ref"),
            (
                ["--breach-policy", "consecutive-main"],
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": cb.MAIN_REF},
                "run id",
            ),
            (
                ["--breach-policy", "consecutive-main"],
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": cb.MAIN_REF, "GITHUB_RUN_ID": "x"},
                "not an integer",
            ),
            (
                ["--breach-policy", "consecutive-main"],
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": cb.MAIN_REF, "GITHUB_RUN_ID": "1"},
                "repository",
            ),
            (
                ["--breach-policy", "consecutive-main", "--repository", REPO],
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": cb.MAIN_REF, "GITHUB_RUN_ID": "1"},
                "workflow",
            ),
            (
                [
                    "--breach-policy",
                    "consecutive-main",
                    "--repository",
                    REPO,
                    "--workflow",
                    "a.yml",
                ],
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": cb.MAIN_REF, "GITHUB_RUN_ID": "1"},
                "breach-record.json",
            ),
        ],
    )
    def test_unusable_flags_raise(self, argv: list[str], env: dict[str, str], message: str) -> None:
        with pytest.raises(ValueError, match=message):
            cb.policy_from_args(self._args(*argv), env)

    def test_apply_policy_requires_a_record_path_on_main(self, tmp_path: Path) -> None:
        policy = cb.Policy(
            name=cb.POLICY_CONSECUTIVE,
            event="push",
            ref=cb.MAIN_REF,
            run_id=1,
            repository=REPO,
            workflow=WORKFLOW,
        )
        with pytest.raises(ValueError, match="breach-record-out"):
            cb.apply_policy(GATE, {}, policy, FakeApi({}))


def _no_sleep(_seconds: float) -> None:
    return None


class TestGhFetch:
    def test_it_returns_stdout_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[list[str]] = []

        def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[bytes]:
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, b"body", b"")

        monkeypatch.setattr(cb.subprocess, "run", fake_run)
        assert cb.gh_fetch("repos/x", sleep=_no_sleep) == b"body"
        assert seen == [["gh", "api", "repos/x"]]

    def test_a_nonzero_exit_raises_with_the_last_stderr_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(cmd, 1, b"", b"noise\nHTTP 403: forbidden\n")

        monkeypatch.setattr(cb.subprocess, "run", fake_run)
        with pytest.raises(cb.PriorStateError, match="HTTP 403"):
            cb.gh_fetch("repos/x", sleep=_no_sleep)

    def test_a_nonzero_exit_with_no_stderr_still_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            cb.subprocess,
            "run",
            lambda cmd, **_kw: subprocess.CompletedProcess(cmd, 1, b"", b""),
        )
        with pytest.raises(cb.PriorStateError, match="no output"):
            cb.gh_fetch("repos/x", sleep=_no_sleep)

    @pytest.mark.parametrize(
        "exc", [FileNotFoundError("gh"), subprocess.TimeoutExpired(["gh"], 1.0)]
    )
    def test_a_missing_binary_or_timeout_raises(
        self, monkeypatch: pytest.MonkeyPatch, exc: Exception
    ) -> None:
        def boom(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[bytes]:
            raise exc

        monkeypatch.setattr(cb.subprocess, "run", boom)
        with pytest.raises(cb.PriorStateError, match="did not run"):
            cb.gh_fetch("repos/x", sleep=_no_sleep)

    def test_a_transient_failure_is_retried_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        results = [(1, b"", b"HTTP 502"), (1, b"", b"HTTP 502"), (0, b"ok", b"")]
        naps: list[float] = []

        def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[bytes]:
            code, out, err = results.pop(0)
            return subprocess.CompletedProcess(cmd, code, out, err)

        monkeypatch.setattr(cb.subprocess, "run", fake_run)
        assert cb.gh_fetch("repos/x", sleep=naps.append) == b"ok"
        assert naps == [2.0, 4.0]

    def test_it_gives_up_after_the_attempt_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, b"", b"HTTP 502")

        monkeypatch.setattr(cb.subprocess, "run", fake_run)
        with pytest.raises(cb.PriorStateError, match="HTTP 502"):
            cb.gh_fetch("repos/x", sleep=_no_sleep)
        assert len(calls) == cb.FETCH_ATTEMPTS
