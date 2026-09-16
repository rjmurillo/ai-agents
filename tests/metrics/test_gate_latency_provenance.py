"""What the artifact records about how a capture was taken (REQ-027).

A pre-push capture is only worth reading if a reader can tell a faithful one
from a bare one, so the report carries the stdin ref line, the hook args and
the force flag that produced it. These pin that, and pin the argv those
options build.

Split from test_gate_latency_classes.py, which had accumulated six unrelated
concerns and scored 1.0 cohesion against a test-context floor of 6.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.metrics import gate_latency as gl
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


def test_positive_stdin_ref_line_reaches_the_subprocess(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """Jobs declaring use_stdin: true can exit early on empty stdin, understating cost."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _capturing_fake(seen))

    gls_sampler._run_repetition(
        repo,
        ["lefthook"],
        "pre-push",
        (),
        0,
        "refs/heads/main abc123 refs/heads/main def456",
    )

    assert seen["input"] == "refs/heads/main abc123 refs/heads/main def456\n"


def test_edge_stdin_ref_line_is_newline_terminated_exactly_once(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """A caller who already terminated the line must not produce a blank second line."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _capturing_fake(seen))

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", (), 0, "a b c d\n")

    assert seen["input"] == "a b c d\n"


def test_negative_absent_stdin_ref_line_sends_empty_stdin(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _capturing_fake(seen))

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", (), 0)

    assert seen["input"] == ""


def test_positive_report_records_whether_a_ref_line_was_supplied(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """The artifact must distinguish a faithful capture from a bare one."""
    monkeypatch.setattr(subprocess, "run", _capturing_fake({}))

    supplied = gls_sampler.build_report(
        repo, "cmd", "pre-commit", "none", (), 1, ["lefthook"], "a b c d"
    )
    bare = gls_sampler.build_report(repo, "cmd", "pre-commit", "none", (), 1, ["lefthook"])

    assert supplied.stdin_ref_line_supplied is True
    assert bare.stdin_ref_line_supplied is False


def test_positive_hook_args_are_passed_positionally_right_after_the_hook_name(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """lefthook expands the first positional into '{1}', which push-ref-staleness reads.

    Measured this session: without them that job rejects the unexpanded
    placeholder, the piped pre-push hook aborts four jobs in, and the run
    reports 0.4 seconds for a hook that does minutes of work.
    """
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake(seen))

    gls_sampler._run_repetition(
        repo, ["lefthook"], "pre-push", (), 0, None, ("origin", "https://example.invalid/r.git")
    )

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:5] == ["lefthook", "run", "pre-push", "origin", "https://example.invalid/r.git"]


def test_negative_absent_hook_args_leave_the_argument_vector_unchanged(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake(seen))

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:4] == ["lefthook", "run", "pre-commit", "--no-tty"]


def test_positive_report_records_the_hook_args_it_used(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """A reader must be able to tell a faithful pre-push capture from a bare one."""
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake({}))

    report = gls_sampler.build_report(
        repo, "cmd", "pre-push", "none", (), 1, ["lefthook"], None, ("origin", "url")
    )

    assert report.hook_args == ["origin", "url"]


def test_negative_force_is_absent_by_default(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """--force defeats glob filtering, so a change class would stop selecting jobs.

    Measured this session: with --force, python-type-check (glob '**/*.py') ran
    against a markdown change class and failed, because mypy was handed a .md
    file. Without it the same job skips with "no matching push files", which is
    what makes a per-change-class measurement mean anything.
    """
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake(seen))

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", ("README.md",), 0)

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert "--force" not in cmd


def test_positive_force_is_passed_when_explicitly_requested(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake(seen))

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", (), 0, None, (), True)

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert "--force" in cmd


def test_positive_report_records_whether_the_run_was_forced(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """A forced run measures a different thing, so the artifact has to say so."""
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake({}))

    forced = gls_sampler.build_report(
        repo, "cmd", "pre-push", "none", (), 1, ["lefthook"], None, (), True
    )
    natural = gls_sampler.build_report(repo, "cmd", "pre-push", "none", (), 1, ["lefthook"])

    assert forced.forced is True
    assert natural.forced is False


# --- Credential redaction and the hook timeout -------------------------------

def test_positive_normalized_command_args_replaces_repo_value() -> None:
    args = ["--repo", "/home/alice/checkout", "--hook", "pre-commit", "--json", "out.json"]
    normalized = gl._normalized_command_args(args)
    assert normalized == ["--repo", "<repo>", "--hook", "pre-commit", "--json", "out.json"]

def test_edge_normalized_command_args_handles_repo_equals_form() -> None:
    args = ["--repo=/home/alice/checkout", "--hook", "pre-commit"]
    normalized = gl._normalized_command_args(args)
    assert normalized == ["--repo=<repo>", "--hook", "pre-commit"]

