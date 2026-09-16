"""Change-class coverage and stdin provenance for gate_latency.py (REQ-027).

Split from ``test_gate_latency.py`` to keep both modules under the project's
500-line taste-lint ceiling, the same reason the CLI and io tests are their
own modules. The concern here is narrower than the core module's: what the
``CHANGE_CLASSES`` table has to contain for AC-08's job coverage to hold, and
whether the ref line git gives a real pre-push hook reaches the subprocess.

``subprocess.run`` is monkeypatched throughout: no test in this module runs a
real lefthook hook.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.metrics import gate_latency as gl
from tests.gc_real_git import git

REAL_CAPTURED_STDOUT = (
    "  \x1b[38;2;56;56;56m  ----\x1b[m\n"
    "summary: (done in 0.19 seconds)\n"
    "\u2713 security-suppressions-staged (0.19 seconds)\n"
)


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    _write(root, "lefthook.yml", "pre-commit:\n  jobs:\n    - name: a-job\n      run: 'true'\n")
    for paths in gl.CHANGE_CLASSES.values():
        for rel in paths:
            _write(root, rel, "placeholder\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

# --- stdin provenance and the hooks change class -----------------------------


def _capturing_fake(seen: dict[str, object]) -> object:
    """A ``subprocess.run`` fake that records the kwargs the lefthook call received."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        seen["input"] = kwargs.get("input")
        return _FakeCompleted(0, REAL_CAPTURED_STDOUT)

    return _fake


def test_positive_stdin_ref_line_reaches_the_subprocess(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """Jobs declaring use_stdin: true can exit early on empty stdin, understating cost."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _capturing_fake(seen))

    gl._run_repetition(
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

    gl._run_repetition(repo, ["lefthook"], "pre-push", (), 0, "a b c d\n")

    assert seen["input"] == "a b c d\n"


def test_negative_absent_stdin_ref_line_sends_empty_stdin(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _capturing_fake(seen))

    gl._run_repetition(repo, ["lefthook"], "pre-push", (), 0)

    assert seen["input"] == ""


def test_positive_report_records_whether_a_ref_line_was_supplied(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """The artifact must distinguish a faithful capture from a bare one."""
    monkeypatch.setattr(subprocess, "run", _capturing_fake({}))

    supplied = gl.build_report(
        repo, "cmd", "pre-commit", "none", (), 1, ["lefthook"], "a b c d"
    )
    bare = gl.build_report(repo, "cmd", "pre-commit", "none", (), 1, ["lefthook"])

    assert supplied.stdin_ref_line_supplied is True
    assert bare.stdin_ref_line_supplied is False


def test_positive_change_classes_cover_every_glob_gated_job_issue_5318_names() -> None:
    """AC-08: each of the five pre-push jobs #5318 item 1 names must be reachable.

    ``security-scan`` declares no glob, so it runs on every pre-push and needs
    no class of its own. The other four are glob-gated, and each needs a class
    whose file list matches its glob.
    """
    assert set(gl.CHANGE_CLASSES) >= {"python", "skills", "workflows", "hooks"}
    assert gl.CHANGE_CLASSES["hooks"] == ("build/scripts/generate_hooks.py",)


def test_positive_hooks_change_class_path_is_in_hook_anchoring_e2e_glob_list() -> None:
    """The hooks class is worthless if lefthook.yml stops naming that path."""
    config = yaml.safe_load(Path("lefthook.yml").read_text(encoding="utf-8"))
    globs: list[str] = []

    def _walk(entries: list[Any]) -> None:
        for entry in entries:
            group = entry.get("group")
            if isinstance(group, dict):
                _walk(group.get("jobs", []))
            if entry.get("name") == "hook-anchoring-e2e":
                declared = entry.get("glob", [])
                globs.extend(declared if isinstance(declared, list) else [declared])

    _walk(config["pre-push"]["jobs"])
    assert "build/scripts/generate_hooks.py" in globs


def test_positive_smallest_scope_n_drives_the_percentile_note() -> None:
    """A 20-run report with one under-sampled job still needs the note (AC-05)."""
    summaries = [
        gl.LatencySummary(scope="__hook__", n=20, p50=1.0, p95=2.0, min=1.0, max=2.0),
        gl.LatencySummary(scope="late-job", n=3, p50=1.0, p95=2.0, min=1.0, max=2.0),
    ]

    assert gl._smallest_scope_n(summaries, 20) == 3
    assert gl._percentile_note(gl._smallest_scope_n(summaries, 20)) is not None


def _argv_capturing_fake(seen: dict[str, object]) -> object:
    """A ``subprocess.run`` fake that records the lefthook argument vector."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        seen["cmd"] = list(cmd)
        return _FakeCompleted(0, REAL_CAPTURED_STDOUT)

    return _fake


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

    gl._run_repetition(
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

    gl._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:4] == ["lefthook", "run", "pre-commit", "--no-tty"]


def test_positive_report_records_the_hook_args_it_used(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """A reader must be able to tell a faithful pre-push capture from a bare one."""
    monkeypatch.setattr(subprocess, "run", _argv_capturing_fake({}))

    report = gl.build_report(
        repo, "cmd", "pre-push", "none", (), 1, ["lefthook"], None, ("origin", "url")
    )

    assert report.hook_args == ["origin", "url"]
