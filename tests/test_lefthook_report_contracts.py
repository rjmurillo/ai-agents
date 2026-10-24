"""Contract guards for the failed-hook report (issue #6734, item 5).

Coverage:

- security: a credential in a remote URL argument never reaches the report, in any
  shape (userinfo with `@`, `/`, `?`, or `#`, a query token, a fragment token).
- negative: a non-URL argument such as `git@host:o/r.git` is printed unchanged.
- edge: a child that closed its stdin does not crash the runner.
- config: no `lefthook.yml` job name holds the `": "` separator the report splits on,
  and every job declares a timeout, because the runner waits on Lefthook.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from scripts.validation import lefthook_runner as runner

# The runner imports its sibling by bare name; use the module object it holds.
report_module = importlib.import_module(runner.run_hook_with_report.__module__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMAND = ["uv", "run", "--frozen", "lefthook"]


def test_no_lefthook_job_name_contains_the_reason_separator() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    def names(jobs: list[dict[str, object]]) -> list[str]:
        found: list[str] = []
        for job in jobs:
            if "name" in job:
                found.append(str(job["name"]))
            group = job.get("group")
            if isinstance(group, dict):
                found.extend(names(group.get("jobs", [])))
        return found

    every = [
        name
        for hook in config.values()
        if isinstance(hook, dict) and "jobs" in hook
        for name in names(hook["jobs"])
    ]

    assert len(every) > 50
    assert [name for name in every if ": " in name] == []


def test_report_never_prints_credentials_embedded_in_a_remote_url() -> None:
    url = "https://user:ghp_secrettoken@github.com/o/r.git"

    report = report_module.failure_report(
        COMMAND, ["run", "pre-push", "origin", url], 1, ["a"], ["r"]
    )

    assert "ghp_secrettoken" not in report
    assert "user:" not in report
    assert "origin https://github.com/o/r.git" in report


@pytest.mark.parametrize(
    ("url", "secret", "expected"),
    [
        ("https://user:p@ss@github.com/o/r.git", "ss@", "https://github.com/o/r.git"),
        ("https://user:p%40ss@github.com/o/r.git", "p%40ss", "https://github.com/o/r.git"),
        ("https://github.com/o/r.git?token=abc#frag", "token=abc", "https://github.com/o/r.git"),
        ("https://x-access-token:ghs_abc@host/r.git#ghs_x", "ghs_", "https://host/r.git"),
        ("https://user:p/ss@github.com/o/r.git", "p/ss", "https://github.com/o/r.git"),
        ("https://user:p?ss@github.com/o/r.git", "p?ss", "https://github.com/o/r.git"),
        ("https://user:p#ss@github.com/o/r.git", "p#ss", "https://github.com/o/r.git"),
    ],
)
def test_report_drops_every_credential_shape_from_a_remote_url(
    url: str, secret: str, expected: str
) -> None:
    report = report_module.failure_report(
        COMMAND, ["run", "pre-push", "origin", url], 1, ["a"], ["r"]
    )

    assert secret not in report
    assert f"origin {expected}" in report


def test_report_keeps_a_non_url_argument_unchanged() -> None:
    report = report_module.failure_report(
        COMMAND, ["run", "pre-push", "origin", "git@github.com:o/r.git"], 1, ["a"], ["r"]
    )

    assert "origin git@github.com:o/r.git" in report


def test_every_lefthook_job_declares_a_timeout() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    def untimed(jobs: list[dict[str, object]]) -> list[str]:
        missing: list[str] = []
        for job in jobs:
            group = job.get("group")
            if isinstance(group, dict):
                missing.extend(untimed(group.get("jobs", [])))
            elif "timeout" not in job:
                missing.append(str(job.get("name")))
        return missing

    missing = [
        name
        for hook in config.values()
        if isinstance(hook, dict) and "jobs" in hook
        for name in untimed(hook["jobs"])
    ]

    assert missing == [], "the runner waits on Lefthook, so every job needs its own bound"


class _BrokenStream:
    def write(self, data: bytes) -> None:
        raise BrokenPipeError

    def close(self) -> None:
        raise OSError("already closed")


def test_feed_stdin_swallows_a_child_that_closed_its_end() -> None:
    report_module._feed_stdin(_BrokenStream(), b"refs/heads/x a refs/heads/x b\n")
