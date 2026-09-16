"""Credential redaction and the hook timeout (REQ-027 security section).

The measurement artifact is committed, so a remote URL carrying a token would
land in git history permanently; redaction runs before either the hook args or
the recorded command is written. The timeout stops a hung hook from hanging
the sampler, which is the module's own stated reason for existing.

Split from test_gate_latency_classes.py for the cohesion reason recorded in
test_gate_latency_provenance.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.metrics import gate_latency_sampler as gls_sampler
from tests.metrics.gate_latency_helpers import _FakeCompleted

REAL_CAPTURED_STDOUT = (
    "  \x1b[38;2;56;56;56m  ----\x1b[m\n"
    "summary: (done in 0.19 seconds)\n"
    "\u2713 security-suppressions-staged (0.19 seconds)\n"
)


def _capturing_fake(seen: dict[str, object]) -> object:
    """A ``subprocess.run`` fake that records the kwargs the lefthook call received."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        seen["input"] = kwargs.get("input")
        return _FakeCompleted(0, REAL_CAPTURED_STDOUT)

    return _fake


def _argv_capturing_fake(seen: dict[str, object]) -> object:
    """A ``subprocess.run`` fake that records the lefthook argument vector."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        seen["cmd"] = list(cmd)
        return _FakeCompleted(0, REAL_CAPTURED_STDOUT)

    return _fake


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://x-access-token:ghp_secret@github.com/o/r.git",
            "https://<redacted>@github.com/o/r.git",
        ),
        ("https://user:pw@example.invalid/a.git", "https://<redacted>@example.invalid/a.git"),
        ("ssh://git:key@host/r.git", "ssh://<redacted>@host/r.git"),
        ("https://github.com/rjmurillo/ai-agents.git", "https://github.com/rjmurillo/ai-agents.git"),
        ("origin", "origin"),
        ("", ""),
    ],
)
def test_url_userinfo_is_redacted_but_credential_free_text_is_untouched(
    raw: str, expected: str
) -> None:
    """A committed artifact records hook args, and git history is permanent."""
    assert gls_sampler._redact_url_userinfo(raw) == expected


def test_positive_report_redacts_a_credentialed_remote_before_writing_it(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """The pre-push measurement needs --hook-arg <remote> <url>, and the artifact is committed."""
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake({}))

    report = gls_sampler.build_report(
        repo,
        "gate_latency.py --hook-arg https://tok:s3cret@github.com/o/r.git",
        "pre-push",
        "none",
        (),
        1,
        ["lefthook"],
        None,
        ("origin", "https://tok:s3cret@github.com/o/r.git"),
    )

    assert "s3cret" not in " ".join(report.hook_args)
    assert "s3cret" not in report.command
    assert "<redacted>" in report.hook_args[1]


def test_negative_a_hook_that_times_out_is_a_recorded_repetition_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """A hung hook must not hang the sampler, and must not lose the other repetitions."""

    def _timing_out(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        raise subprocess.TimeoutExpired(cmd, 1.0, output=b"partial output")

    monkeypatch.setattr(subprocess, "run", _timing_out)

    run = gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", (), 0)

    assert run.exit_code == gls_sampler._TIMEOUT_EXIT_CODE
    assert run.jobs_parsed == 0


def test_positive_the_lefthook_call_carries_a_timeout(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """Without one, a hung job blocks the run with no diagnostic."""
    seen: dict[str, object] = {}

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        seen["timeout"] = kwargs.get("timeout")
        return _FakeCompleted(0, REAL_CAPTURED_STDOUT)

    monkeypatch.setattr(subprocess, "run", _fake)

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", (), 0)

    assert seen["timeout"] == gls_sampler._HOOK_TIMEOUT_SECONDS
