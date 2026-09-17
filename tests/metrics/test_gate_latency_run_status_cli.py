"""``build_report`` end-to-end run-status classification (REQ-027 D1 and D1 follow-up).

Split from ``test_gate_latency_run_status.py``, which holds the unit-level
``_classify_run_status`` and ``_build_summaries`` coverage plus the
backward-compatibility construction tests. The CLI-driven markdown/JSON
rendering tests and the ``_exclusion_sentence`` unit coverage live in
``test_gate_latency_run_status_markdown.py``, split out for the same
file-size reason the other ``test_gate_latency_*`` modules document in
their own docstrings.

``subprocess.run`` is monkeypatched throughout; no test here runs a real
lefthook hook.

The shared ``repo`` fixture's ``pre-commit`` hook declares ``piped: true``
(see ``tests/metrics/gate_latency_helpers.py``'s ``_LEFTHOOK_YML``), which is
exactly the shape the D1 follow-up's absolute trigger targets: a non-zero
exit on THAT hook is now classified ``truncated`` regardless of job count.
Tests that need the OLD "failed but measured" distinction (a non-zero exit
on a full job set still ``complete``) use the local ``non_piped_repo``
fixture below instead, whose hook explicitly declares ``piped: false``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.metrics import gate_latency as gl
from scripts.metrics import gate_latency_sampler as gls_sampler
from tests.gc_real_git import git


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


_TWO_JOB_STDOUT = (
    "summary: (done in 0.30 seconds)\n✓ job-a (0.10 seconds)\n✓ job-b (0.20 seconds)\n"
)
_ONE_JOB_STDOUT = "summary: (done in 0.10 seconds)\n✓ job-a (0.10 seconds)\n"

_HookResponse = _FakeCompleted | Callable[[list[str]], _FakeCompleted]


def _git_aware(hook_response: _HookResponse) -> Callable[..., _FakeCompleted]:
    """A ``subprocess.run`` fake: git calls succeed; everything else is ``hook_response``."""

    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd[:2] == ["git", "status"]:
            return _FakeCompleted(0, "")
        if cmd[:2] == ["git", "rev-parse"]:
            return _FakeCompleted(0, "deadbeef\n")
        if callable(hook_response):
            return hook_response(cmd)
        return hook_response

    return _fake


_NON_PIPED_LEFTHOOK_YML = """\
pre-commit:
  piped: false
  jobs:
    - name: job-a
      run: echo a
      timeout: 10s
    - name: job-b
      run: echo b
      timeout: 5s
"""

_NO_PIPED_KEY_LEFTHOOK_YML = """\
pre-commit:
  jobs:
    - name: job-a
      run: echo a
      timeout: 10s
    - name: job-b
      run: echo b
      timeout: 5s
"""


def _fixture_repo(root: Path, lefthook_yml: str) -> Path:
    """A small git repo with the given ``lefthook.yml`` content, committed."""
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "lefthook.yml").write_text(lefthook_yml, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


@pytest.fixture
def non_piped_repo(tmp_path: Path) -> Path:
    """A repo whose ``pre-commit`` hook explicitly declares ``piped: false``.

    The shared ``repo`` fixture's ``pre-commit`` is ``piped: true`` on
    purpose (it doubles as the D1-follow-up regression fixture below), so a
    test that needs the pre-D1-follow-up "failed but measured" distinction
    needs a hook the absolute trigger cannot reach.
    """
    return _fixture_repo(tmp_path / "non-piped-repo", _NON_PIPED_LEFTHOOK_YML)


@pytest.fixture
def no_piped_key_repo(tmp_path: Path) -> Path:
    """A repo whose ``pre-commit`` hook declares no ``piped`` key at all.

    Distinct from ``non_piped_repo``: this hook never states its piped-ness,
    so ``_resolve_piped_flag`` MUST record ``piped=None`` (unknown, not
    "false") and fall back to the relative check alone.
    """
    return _fixture_repo(tmp_path / "no-piped-key-repo", _NO_PIPED_KEY_LEFTHOOK_YML)


# --- build_report end to end: classification after every repetition ----------


def test_positive_a_non_piped_hooks_nonzero_exit_with_full_job_set_is_complete(
    monkeypatch: pytest.MonkeyPatch, non_piped_repo: Path
) -> None:
    """The "failed but measured" case must not regress on a non-piped hook.

    Both repetitions parse the same 2-job summary; only their exit code
    differs, and the hook declares ``piped: false``, so the absolute
    trigger cannot fire regardless of exit code.
    """
    calls = {"n": 0}

    def _hook_response(_cmd: list[str]) -> _FakeCompleted:
        calls["n"] += 1
        return _FakeCompleted(0 if calls["n"] == 1 else 1, _TWO_JOB_STDOUT)

    monkeypatch.setattr(subprocess, "run", _git_aware(_hook_response))

    report = gls_sampler.build_report(
        non_piped_repo, "cmd", "pre-commit", "none", (), 2, ["lefthook"]
    )

    assert report.piped is False
    assert report.run_status_counts == {"complete": 2}
    hook_summary = next(s for s in report.summaries if s.scope == "__hook__")
    assert hook_summary.n == 2


def test_negative_a_piped_hooks_identical_truncation_is_never_classified_complete(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """D1 follow-up regression test: fails against the classifier with no absolute trigger.

    Reproduces the reported failure shape directly: a ``piped: true`` hook
    (``repo``'s ``pre-commit``) aborts at the SAME job on every repetition,
    so both repetitions parse the identical 1-job summary and both exit
    non-zero. The relative trigger alone sees ``jobs_parsed == max`` for
    both and would classify both ``complete``, exactly the D1 shape the
    absolute trigger exists to catch: both MUST be ``truncated``, the
    summaries MUST be empty, and the CLI MUST still exit 0 (C2, proven
    end to end in ``test_gate_latency_run_status_markdown.py``'s sibling
    all-timed-out test).
    """

    def _hook_response(_cmd: list[str]) -> _FakeCompleted:
        return _FakeCompleted(1, _ONE_JOB_STDOUT)

    monkeypatch.setattr(subprocess, "run", _git_aware(_hook_response))

    report = gls_sampler.build_report(repo, "cmd", "pre-commit", "none", (), 2, ["lefthook"])

    assert report.piped is True
    assert report.run_status_counts == {"truncated": 2}
    assert report.summaries == []


def test_positive_a_piped_hooks_zero_exit_is_complete(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """The absolute trigger requires a non-zero exit; a clean piped run is unaffected."""
    monkeypatch.setattr(subprocess, "run", _git_aware(_FakeCompleted(0, _TWO_JOB_STDOUT)))

    report = gls_sampler.build_report(repo, "cmd", "pre-commit", "none", (), 1, ["lefthook"])

    assert report.piped is True
    assert report.run_status_counts == {"complete": 1}


def test_edge_missing_piped_key_falls_back_to_the_relative_check_with_no_traceback(
    monkeypatch: pytest.MonkeyPatch, no_piped_key_repo: Path, tmp_path: Path
) -> None:
    """No ``piped`` key: the absolute trigger is disabled, not assumed either way.

    A non-zero exit on this hook must NOT be classified ``truncated`` by
    the absolute trigger (it is disabled because ``piped`` is unknown, not
    ``false``), and the markdown must say the relative check alone applied.
    No exception escapes ``build_report`` or ``main``.
    """
    monkeypatch.setattr(subprocess, "run", _git_aware(_FakeCompleted(1, _TWO_JOB_STDOUT)))
    md_path = tmp_path / "out.md"
    json_path = tmp_path / "out.json"

    rc = gl.main(
        [
            "--repo",
            str(no_piped_key_repo),
            "--hook",
            "pre-commit",
            "--repetitions",
            "1",
            "--markdown",
            str(md_path),
            "--json",
            str(json_path),
        ]
    )

    assert rc == 0
    body = md_path.read_text(encoding="utf-8")
    assert "Hook `piped` flag: unknown" in body
    assert "classification used the relative check alone" in body
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["piped"] is None
    assert data["runs"][0]["status"] == "complete"


def test_edge_unreadable_config_falls_back_to_the_relative_check_with_no_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No ``lefthook.yml`` at all: ``build_report`` itself must not raise.

    The CLI's own validation (``_validate_hook``) refuses this case before
    ``build_report`` is ever called, so this drives ``build_report``
    directly to exercise the fallback ``_resolve_piped_flag`` takes when
    ``_load_lefthook_config`` returns ``None``.
    """
    root = tmp_path / "no-lefthook-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("placeholder\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "no lefthook.yml")
    monkeypatch.setattr(subprocess, "run", _git_aware(_FakeCompleted(1, _TWO_JOB_STDOUT)))

    report = gls_sampler.build_report(root, "cmd", "pre-commit", "none", (), 1, ["lefthook"])

    assert report.piped is None
    assert any(entry["field"] == "piped" for entry in report.exclusions)
    assert report.run_status_counts == {"complete": 1}


def test_negative_build_report_classifies_timeout_and_excludes_it(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    def _hook_response(cmd: list[str]) -> _FakeCompleted:
        raise subprocess.TimeoutExpired(cmd, 1.0, output=b"")

    monkeypatch.setattr(subprocess, "run", _git_aware(_hook_response))

    report = gls_sampler.build_report(repo, "cmd", "pre-commit", "none", (), 1, ["lefthook"])

    assert report.run_status_counts == {"timeout": 1}
    assert report.summaries == []
