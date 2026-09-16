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
from wcmatch import glob

from scripts.metrics import gate_latency as gl
from scripts.metrics import gate_latency_sampler as gls_sampler
from scripts.metrics import gate_latency_stats as gls
from scripts.metrics.gate_latency_models import LatencySummary
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


def test_positive_change_classes_cover_every_glob_gated_job_issue_5318_names() -> None:
    """AC-08: each of the five pre-push jobs #5318 item 1 names must be reachable.

    ``security-scan`` declares no glob, so it runs on every pre-push and needs
    no class of its own. The other four are glob-gated, and each needs a class
    whose file list matches its glob.
    """
    assert set(gl.CHANGE_CLASSES) >= {"python", "skills", "workflows", "hooks"}
    assert gl.CHANGE_CLASSES["hooks"] == ("build/scripts/generate_hooks.py",)


def _declared_globs(hook: str, job_name: str) -> list[str]:
    """Every glob `job_name` declares under `hook` in the real lefthook.yml."""
    config = yaml.safe_load(Path("lefthook.yml").read_text(encoding="utf-8"))
    globs: list[str] = []

    def _walk(entries: list[Any]) -> None:
        for entry in entries:
            group = entry.get("group")
            if isinstance(group, dict):
                _walk(group.get("jobs", []))
            if entry.get("name") == job_name:
                declared = entry.get("glob", [])
                globs.extend(declared if isinstance(declared, list) else [declared])

    _walk(config[hook]["jobs"])
    return globs


@pytest.mark.parametrize(
    ("change_class", "job_name"),
    [
        ("hooks", "hook-anchoring-e2e"),
        ("python", "python-type-check"),
        ("skills", "plugin-load-e2e"),
        ("workflows", "workflow-local-run"),
    ],
)
def test_positive_each_change_class_file_matches_its_job_glob(
    change_class: str, job_name: str
) -> None:
    """AC-08 holds only while each class's file still matches its job's glob.

    `gate_latency_classes.py` asserts these four mappings in prose, read off
    `lefthook.yml` once. Prose does not fail when the config moves. Without
    this, a glob change would silently stop a class from firing the job it
    exists to measure, and the suite would stay green while the artifact kept
    claiming coverage.
    """
    globs = _declared_globs("pre-push", job_name)
    assert globs, f"{job_name} declares no glob in lefthook.yml"

    files = gl.CHANGE_CLASSES[change_class]
    assert files, f"change class {change_class} names no file"

    # lefthook.yml sets `glob_matcher: doublestar`, so the patterns use `**`
    # and brace alternation. pathlib.PurePath.match understands neither, and
    # would report a false mismatch for `.github/workflows/**/*.{yml,yaml}`.
    flags = glob.GLOBSTAR | glob.BRACE
    for rel in files:
        assert any(
            glob.globmatch(rel, pattern, flags=flags) for pattern in globs
        ), f"{rel} matches none of {job_name}'s globs {globs}"


def test_positive_smallest_scope_n_drives_the_percentile_note() -> None:
    """A 20-run report with one under-sampled job still needs the note (AC-05)."""
    summaries = [
        LatencySummary(scope="__hook__", is_group=False, n=20, p50=1.0, p95=2.0, min=1.0, max=2.0),
        LatencySummary(scope="late-job", is_group=False, n=3, p50=1.0, p95=2.0, min=1.0, max=2.0),
    ]

    assert gls._smallest_scope_n(summaries, 20) == 3
    assert gls._percentile_note(gls._smallest_scope_n(summaries, 20)) is not None


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
