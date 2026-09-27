"""Tests for scripts/validation/effective_context_write_ceilings.py (issue #4880).

Coordinator finding (post-rebase review): every entry in
``effective_context_ceilings.py``'s two maps was a hand-typed byte count
equal to some earlier measurement, and nothing regenerated them. This file
covers ``--write-ceilings``'s three required properties: it round-trips
(write, then ``--ci`` passes against exactly what it wrote), it is
byte-stable across two runs with no repository change between them, and the
ratchet's own breach messages name it as the command that accepts a
reviewed change.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context as ec
import scripts.validation.effective_context_write_ceilings as ecwc
from scripts.validation.effective_context_resolvers import GitUnavailableError
from scripts.validation.effective_context_write_ceilings import (
    render_ceilings_module,
    write_ceilings_module,
)
from scripts.validation.instruction_budget_globs import UnsupportedApplyToError
from tests.validation._effective_context_helpers import (
    FakeCompletedProcess,
    _commit_all,
    _init_git_repo,
    _write,
)


def _load_generated_ceilings(path: Path) -> types.ModuleType:
    """Import the file ``write_ceilings_module`` wrote, as a fresh module.

    Loads from the on-disk path rather than trusting the in-memory
    ``CeilingMap`` this test built: the point of the round-trip test is that
    the *written bytes*, re-parsed by Python, are what ``--ci`` accepts.
    """
    spec = importlib.util.spec_from_file_location("generated_ceilings", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_small_tree(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write(tmp_path, "CLAUDE.md", "root\n")
    _write(tmp_path, "a/CLAUDE.md", "nested\n")
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "target.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "v1")


class TestWriteCeilingsRoundTrip:
    def test_write_then_ci_passes_against_the_generated_ceilings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _build_small_tree(tmp_path)
        monkeypatch.setattr(ec, "FROZEN_TARGETS", ("a/b/target.py",))

        ceilings_path = tmp_path / "generated_ceilings.py"
        write_ceilings_module(tmp_path, ceilings_path)
        generated = _load_generated_ceilings(ceilings_path)

        monkeypatch.setattr(ec, "CEILINGS_BYTES", generated.CEILINGS_BYTES)
        monkeypatch.setattr(
            ec, "PATH_LOCAL_DIRECTORY_CEILINGS", generated.PATH_LOCAL_DIRECTORY_CEILINGS
        )
        assert ec.main(["--ci"], repo_root=tmp_path) == 0

    def test_output_is_byte_stable_on_a_second_run_with_no_repository_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _build_small_tree(tmp_path)
        monkeypatch.setattr(ec, "FROZEN_TARGETS", ("a/b/target.py",))

        first_path = tmp_path / "first.py"
        second_path = tmp_path / "second.py"
        write_ceilings_module(tmp_path, first_path)
        write_ceilings_module(tmp_path, second_path)

        assert first_path.read_bytes() == second_path.read_bytes()

    def test_generated_module_is_syntactically_valid_and_carries_the_label(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _build_small_tree(tmp_path)
        monkeypatch.setattr(ec, "FROZEN_TARGETS", ())

        ceilings_path = tmp_path / "generated_ceilings.py"
        write_ceilings_module(tmp_path, ceilings_path)
        generated = _load_generated_ceilings(ceilings_path)

        assert isinstance(generated.CEILINGS_BYTES, dict)
        assert isinstance(generated.PATH_LOCAL_DIRECTORY_CEILINGS, dict)
        assert generated.CEILING_LABEL == ec.CEILING_LABEL
        assert generated.PATH_LOCAL_DIRECTORY_CEILINGS[("a", "claude")] > 0

    def test_write_ceilings_via_main_exits_zero_and_names_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _build_small_tree(tmp_path)
        monkeypatch.setattr(ec, "FROZEN_TARGETS", ("a/b/target.py",))

        code = ec.main(["--write-ceilings"], repo_root=tmp_path)
        assert code == 0
        out = capsys.readouterr().out
        assert "effective_context_ceilings.py" in out
        assert (tmp_path / "scripts" / "validation" / "effective_context_ceilings.py").is_file()


class TestMeasuredCommitFailureHandling:
    """`_measured_commit` must not silently label a broken `git` as measured."""

    def test_raises_git_unavailable_when_git_binary_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_run(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(ecwc.subprocess, "run", _fake_run)
        with pytest.raises(GitUnavailableError):
            ecwc._measured_commit(tmp_path)

    def test_raises_git_unavailable_on_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_run(*_args: object, **_kwargs: object) -> None:
            raise subprocess.TimeoutExpired(cmd="git", timeout=30)

        monkeypatch.setattr(ecwc.subprocess, "run", _fake_run)
        with pytest.raises(GitUnavailableError):
            ecwc._measured_commit(tmp_path)

    def test_raises_git_unavailable_on_nonzero_exit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(128, stderr="fatal: not a git repository")

        monkeypatch.setattr(ecwc.subprocess, "run", _fake_run)
        with pytest.raises(GitUnavailableError, match="not a git repository"):
            ecwc._measured_commit(tmp_path)


class TestRunWriteCeilingsCliErrorMapping:
    """`_run_write_ceilings` maps a git or frontmatter failure to ADR-035 exit codes."""

    def test_git_unavailable_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> str:
            raise GitUnavailableError("git is broken")

        monkeypatch.setattr(ec, "write_ceilings_module", _raise)
        code = ec.main(["--write-ceilings"], repo_root=tmp_path)
        assert code == 3
        assert "git is broken" in capsys.readouterr().err

    def test_unsupported_applyto_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> str:
            raise UnsupportedApplyToError("bad frontmatter")

        monkeypatch.setattr(ec, "write_ceilings_module", _raise)
        code = ec.main(["--write-ceilings"], repo_root=tmp_path)
        assert code == 2
        assert "bad frontmatter" in capsys.readouterr().err


class TestResolveOrReportGitUnavailable:
    """The non-`--ci` CLI path also maps a git failure during resolution to exit 3."""

    def test_git_unavailable_during_resolution_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> None:
            raise GitUnavailableError("git show timed out")

        monkeypatch.setattr(ec, "resolve_effective_context", _raise)
        code = ec.main(["--target", "target.py", "--harness", "claude"], repo_root=tmp_path)
        assert code == 3
        assert "git show timed out" in capsys.readouterr().err


class TestBreachMessagesNameWriteCeilings:
    def test_breach_message_names_the_flag(self) -> None:
        message = ec._format_breach("a/b/target.py", "claude", 20, 10)
        assert "--write-ceilings" in message

    def test_missing_ceiling_message_names_the_flag(self) -> None:
        message = ec._format_missing_ceiling("new_dir", "claude")
        assert "--write-ceilings" in message


# Module level, not inside the test method: at the method's indent the tuple
# literal plus its required suppression comment exceeds ruff's line length
# and gets wrapped across lines, separating the comment from the tuple's own
# line, which is exactly the shape `check_agents_write_targets.py` would
# then flag as unsuppressed.
_PER_DIRECTORY_WITH_AGENTS_KEY: dict[tuple[str, str], int] = {
    (".agents", "claude"): 5,  # agents-write-target: historical -- dict key
    (".agents", "copilot"): 5,  # agents-write-target: historical -- dict key
    (".agents/archive", "claude"): 7,
    ("src", "claude"): 9,
}


class TestAgentsJoinSuppression:
    """The `.agents` key trips `check_agents_write_targets.py`'s AST scan.

    Verified this session (`check_agents_write_targets.py` lines 203-213,
    `_find_agents_join`): a 2-element tuple literal whose first element is
    the literal string `.agents` immediately followed by another string
    constant reads as a `.agents/<name>` path join. Only the exact
    `".agents"` key matches; a longer path under it (`.agents/archive`) does
    not, so the writer must suppress on the first and not the second.
    """

    def test_agents_key_gets_the_suppression_comment_a_longer_path_does_not(self) -> None:
        text = render_ceilings_module({}, _PER_DIRECTORY_WITH_AGENTS_KEY, measured_commit="abc1234")

        agents_lines = [line for line in text.splitlines() if '(".agents", ' in line]
        assert len(agents_lines) == 2
        assert all("agents-write-target: historical" in line for line in agents_lines)

        other_lines = [
            line for line in text.splitlines() if '".agents/archive"' in line or '"src"' in line
        ]
        assert other_lines
        assert all("agents-write-target" not in line for line in other_lines)


class TestRenderNamesTheMeasuredCommit:
    def test_measured_commit_appears_in_the_rendered_module(self) -> None:
        text = render_ceilings_module({}, {}, measured_commit="abc1234")
        assert "abc1234" in text
