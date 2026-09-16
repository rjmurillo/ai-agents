"""Core tests for lefthook_summary.py and gate_latency.py (REQ-027 T7).

Parser, percentile, and single-repetition sampling coverage: positive,
negative, and edge cases. ``subprocess.run`` is monkeypatched throughout: no
test invokes a real lefthook hook (that is ``gate_latency.py``'s own
proof-of-life run, done manually, not here). Fakes dispatch on the argument
vector (testing.md SHOULD-11), not on call order, so a git call and a
lefthook call are never confused.

Split, per the project's 500-line taste-lint ceiling, into three files
mirroring this repository's ``test_control_plane_baseline*.py`` precedent
for splitting a large test module by concern rather than by mechanical
line count: CLI-level behavior (argument validation, the never-gates
matrix, AC-13) lives in ``test_gate_latency_cli.py``; the JSON/markdown
writer and the symlink-refusing open live in ``test_gate_latency_io.py``.
No test case was dropped in the split.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.metrics import gate_latency as gl
from scripts.metrics import gate_latency_stats as gls
from scripts.metrics import lefthook_summary as ls
from tests.gc_real_git import git

# --- Fixtures ---------------------------------------------------------------

_DIVIDER = "\x1b[38;2;56;56;56m" + "─" * 40 + "\x1b[0m"

# Real captured output, this session: `.venv/bin/lefthook run pre-merge-commit
# --no-tty --colors off --force --no-stage-fixed` against this repository's own
# lefthook.yml. A divider line carries a truecolor escape that --colors off
# does not strip; the summary line and job line follow. The pass marker is
# bare U+2713, not the U+2714 U+FE0F an earlier draft of this module assumed
# on the strength of an unverified claim (see lefthook_summary.py's module
# docstring for both captures and the correction).
REAL_CAPTURED_STDOUT = (
    f"{_DIVIDER}\n"
    "summary: (done in 0.20 seconds)\n"
    "✓ security-suppressions-staged (0.20 seconds)\n"
)

# Real captured output, this session, from a disposable throwaway repo (never
# committed to this repository) whose pre-commit hook declared one job that
# exits 0 and one that exits 1: `✓` for the pass, `✗` for the fail.
NEGATIVE_CONTROL_STDOUT = (
    "summary: (done in 0.01 seconds)\n"
    "✓ good-job (0.00 seconds)\n"
    "✗ bad-job (0.00 seconds)\n"
)

# Not observed in this environment (see lefthook_summary.py's module
# docstring): U+2714 with the emoji-style variation selector, a documented
# synonym this module accepts defensively. Tests classification robustness,
# not a ground-truth capture.
UNVERIFIED_SYNONYM_MARKER_STDOUT = (
    "summary: (done in 0.05 seconds)\n"
    "✔️ some-other-job (0.05 seconds)\n"
)

_LEFTHOOK_YML = """\
pre-commit:
  piped: true
  jobs:
    - name: job-a
      run: echo a
      timeout: 10s
    - name: job-b
      run: echo b
      timeout: 5s
pre-push:
  piped: true
  jobs:
    - name: job-c
      group:
        parallel: true
        jobs:
          - name: job-c1
            run: echo c1
            timeout: 20s
          - name: job-c2
            run: echo c2
            timeout: 30s
"""


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small git repo with a real lefthook.yml and every change-class path."""
    root = tmp_path / "fixture-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    _write(root, "lefthook.yml", _LEFTHOOK_YML)
    for rel in gl.CHANGE_CLASSES.values():
        for path in rel:
            _write(root, path, "placeholder\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _dispatching_fake(
    responses: dict[tuple[str, ...], _FakeCompleted],
    default_git: _FakeCompleted | None = None,
) -> object:
    """A ``subprocess.run`` fake dispatched on argv, per testing.md SHOULD-11."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        key = tuple(cmd)
        if key in responses:
            return responses[key]
        if cmd and cmd[0] == "git" and default_git is not None:
            return default_git
        raise AssertionError(f"unstubbed subprocess call: {cmd!r}")

    return _fake


# --- lefthook_summary.py: parser (positive, negative, edge) -----------------


def test_positive_real_captured_output_yields_one_pass_sample() -> None:
    samples, reported = ls.parse_summary(REAL_CAPTURED_STDOUT)
    assert reported == 0.20
    assert len(samples) == 1
    sample = samples[0]
    assert sample.name == "security-suppressions-staged"
    assert sample.seconds == 0.20
    assert sample.status == "pass"
    assert sample.marker == "✓"
    assert sample.depth == 0


def test_positive_real_negative_control_yields_one_pass_and_one_fail() -> None:
    """Real capture from a disposable throwaway repo (never committed here)."""
    samples, reported = ls.parse_summary(NEGATIVE_CONTROL_STDOUT)
    assert reported == 0.01
    assert [(s.name, s.status, s.marker) for s in samples] == [
        ("good-job", "pass", "✓"),
        ("bad-job", "fail", "✗"),
    ]


def test_edge_documented_synonym_marker_not_observed_here_still_classifies() -> None:
    """U+2714 U+FE0F is a documented synonym, not a capture from this environment."""
    samples, _reported = ls.parse_summary(UNVERIFIED_SYNONYM_MARKER_STDOUT)
    assert samples == [
        ls.JobSample(name="some-other-job", seconds=0.05, status="pass", marker="✔️", depth=0)
    ]


def test_negative_absent_summary_yields_zero_samples_and_does_not_raise() -> None:
    samples, reported = ls.parse_summary("no summary here at all\njust noise\n")
    assert samples == []
    assert reported is None


def test_negative_malformed_summary_line_yields_zero_samples() -> None:
    samples, reported = ls.parse_summary("summary: this is not the expected shape\n")
    assert samples == []
    assert reported is None


def test_edge_nested_group_parses_all_rows_with_correct_depths() -> None:
    stdout = (
        "summary: (done in 0.50 seconds)\n"
        "✔️ group-name (0.50 seconds)\n"
        "  ✔️ member-one (0.20 seconds)\n"
        "  ✖️ member-two (0.30 seconds)\n"
    )
    samples, reported = ls.parse_summary(stdout)
    assert reported == 0.50
    assert [(s.name, s.depth, s.status) for s in samples] == [
        ("group-name", 0, "pass"),
        ("member-one", 2, "pass"),
        ("member-two", 2, "fail"),
    ]


def test_edge_marker_classification_covers_pass_fail_and_unknown() -> None:
    # Verified this session (real lefthook 2.1.12 captures):
    assert ls.classify_marker("✓") == "pass"  # bare check mark
    assert ls.classify_marker("✗") == "fail"  # bare ballot X
    # Documented synonyms, not observed in this environment:
    assert ls.classify_marker("✔️") == "pass"
    assert ls.classify_marker("✔") == "pass"
    assert ls.classify_marker("✅") == "pass"
    assert ls.classify_marker("✖️") == "fail"
    assert ls.classify_marker("✖") == "fail"
    assert ls.classify_marker("✘") == "fail"
    assert ls.classify_marker("❌") == "fail"
    assert ls.classify_marker("?") == "unknown"
    assert ls.classify_marker("") == "unknown"


def test_edge_trailing_non_job_line_after_summary_stops_parsing() -> None:
    stdout = (
        "summary: (done in 0.10 seconds)\n"
        "✔️ only-job (0.10 seconds)\n"
        "some trailing prose that is not a job line\n"
        "✔️ never-reached (9.99 seconds)\n"
    )
    samples, _reported = ls.parse_summary(stdout)
    assert [s.name for s in samples] == ["only-job"]


# --- _run_repetition and build_report (mocked subprocess) -------------------


def test_positive_run_repetition_records_all_four_fields(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    lefthook_cmd = ["lefthook"]
    expected_cmd = (
        *lefthook_cmd,
        "run",
        "pre-commit",
        "--no-tty",
        "--colors",
        "off",
        "--no-stage-fixed",
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        _dispatching_fake(
            {expected_cmd: _FakeCompleted(0, REAL_CAPTURED_STDOUT)},
            default_git=_FakeCompleted(0, ""),
        ),
    )
    run = gl._run_repetition(repo, lefthook_cmd, "pre-commit", (), 0)
    assert run.repetition_index == 0
    assert run.exit_code == 0
    assert run.wall_clock_seconds >= 0.0
    assert run.lefthook_reported_seconds == 0.20
    assert run.jobs_parsed == 1
    assert run.tree_mutated is False
    assert run.unknown_status_count == 0
    assert run.samples[0].name == "security-suppressions-staged"


def test_positive_unknown_marker_is_surfaced_via_unknown_status_count(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """A marker outside every known glyph family is counted, never silently absorbed."""
    stdout = "summary: (done in 0.01 seconds)\n? mystery-job (0.01 seconds)\n"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: (
            _FakeCompleted(0, "") if cmd[:2] == ["git", "status"] else _FakeCompleted(0, stdout)
        ),
    )
    run = gl._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)
    assert run.jobs_parsed == 1
    assert run.samples[0].status == "unknown"
    assert run.unknown_status_count == 1


def test_positive_run_repetition_passes_change_class_files_as_file_args(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    lefthook_cmd = ["lefthook"]
    expected_cmd = (
        *lefthook_cmd,
        "run",
        "pre-commit",
        "--no-tty",
        "--colors",
        "off",
        "--no-stage-fixed",
        "--file",
        "README.md",
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        _dispatching_fake(
            {expected_cmd: _FakeCompleted(0, REAL_CAPTURED_STDOUT)},
            default_git=_FakeCompleted(0, ""),
        ),
    )
    run = gl._run_repetition(repo, lefthook_cmd, "pre-commit", ("README.md",), 0)
    assert run.jobs_parsed == 1


def test_edge_tree_mutated_true_when_digest_changes(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    call_count = {"git_status": 0}

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd[:2] == ["git", "status"]:
            call_count["git_status"] += 1
            # First call (before): clean. Second call (after): dirty.
            porcelain = "" if call_count["git_status"] == 1 else " M some-file.txt\n"
            return _FakeCompleted(0, porcelain)
        return _FakeCompleted(0, REAL_CAPTURED_STDOUT)

    monkeypatch.setattr(subprocess, "run", _fake)
    run = gl._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)
    assert run.tree_mutated is True


def test_edge_tree_mutated_false_when_digest_unchanged(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd[:2] == ["git", "status"]:
            return _FakeCompleted(0, "")
        return _FakeCompleted(0, REAL_CAPTURED_STDOUT)

    monkeypatch.setattr(subprocess, "run", _fake)
    run = gl._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)
    assert run.tree_mutated is False


def test_positive_build_summaries_includes_reserved_hook_scope(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: (
            _FakeCompleted(0, "")
            if cmd[:2] == ["git", "status"]
            else _FakeCompleted(0, REAL_CAPTURED_STDOUT)
        ),
    )
    runs = [gl._run_repetition(repo, ["lefthook"], "pre-commit", (), i) for i in range(3)]
    summaries = gls._build_summaries(runs)
    scopes = {s.scope for s in summaries}
    assert "__hook__" in scopes
    assert "security-suppressions-staged" in scopes
    hook_summary = next(s for s in summaries if s.scope == "__hook__")
    assert hook_summary.n == 3


# --- Resolving the lefthook command ------------------------------------------


def test_positive_resolve_lefthook_command_prefers_explicit_override(tmp_path: Path) -> None:
    binary = tmp_path / "lefthook"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    assert gl._resolve_lefthook_command(tmp_path, str(binary)) == [str(binary)]


def test_negative_resolve_lefthook_command_returns_none_when_nothing_resolves(
    tmp_path: Path,
) -> None:
    assert gl._resolve_lefthook_command(tmp_path, "/definitely/does/not/exist") is None


def test_positive_resolve_lefthook_command_uses_in_repo_venv_binary(tmp_path: Path) -> None:
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    lefthook = venv_bin / "lefthook"
    lefthook.write_text("#!/bin/sh\n", encoding="utf-8")
    assert gl._resolve_lefthook_command(tmp_path, None) == [str(lefthook)]
