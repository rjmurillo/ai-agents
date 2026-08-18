"""The pre-PR sequence refuses a push git would not gate (issue #5090).

Two claims, separable, both pinned.

The gate's own logic: a ``core.hooksPath`` that git cannot read hooks from
exits 1 and names the failed condition and the repair; a healthy repository
exits 0 and says what it probed and where; every indeterminate state exits 0,
because a state the gate cannot read is not evidence that hooks are dead.

The wiring: ``pre_pr_sequence`` reaches that logic. A validator nothing calls
is the shape that let ``check_skill_md_portability.py`` ship unwired (#4252),
so the wiring class drives the real sequence and spies on the module attribute
``_root_only`` resolves at call time.

Every repository under test is a scratch repository under ``tmp_path``. Running
``git config core.hooksPath /nonexistent`` against this checkout would write to
a ``.git/config`` shared with every live agent worktree and disable all 24
pre-push jobs for every concurrent agent, which is the incident this gate
exists to detect.

Coverage:

- positive: healthy repo exits 0 and prints the probed hook and its directory;
  a linked worktree resolving to the common directory's hooks is healthy.
- negative: a missing hooksPath directory, a directory with no pre-push, and an
  unset hooksPath with no pre-push all exit 1 and name the remedy; a linked
  worktree inherits the broken config; removing the gate fails the wiring test.
- edge: no lefthook config, not a git repository, and no git binary all exit 0;
  the failure report stays inside a line budget.
"""

from __future__ import annotations

import io
import subprocess
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_git_hook_health
import pre_pr_sequence

GATE_NAME = "Git Hook Health (core.hooksPath)"
GUARD = _VALIDATION_DIR / "check_git_hook_health.py"

LEFTHOOK_CONFIG = "pre-push:\n  commands:\n    noop:\n      run: true\n"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


def _make_repo(root: Path, name: str, *, lefthook: bool = True) -> Path:
    """Create a scratch git repository with an optional lefthook config."""
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    if lefthook:
        (repo / "lefthook.yml").write_text(LEFTHOOK_CONFIG, encoding="utf-8")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    return repo


def _install_prepush(hooks_dir: Path) -> None:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-push"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)


def _run_cli(repo: Path, guard: Path = GUARD) -> subprocess.CompletedProcess[str]:
    """Drive the CLI in its own process, as a hook or a shell would.

    The environment is built from scratch rather than inherited so no CI-only
    variable can change the branch under test (testing.md SHOULD 12).
    """
    return subprocess.run(
        [sys.executable, str(guard), str(repo)],
        cwd=str(repo),
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


class TestHealthy:
    """A repository whose hooks git will actually read passes, and says so."""

    def test_a_healthy_repo_exits_zero(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "healthy")
        _install_prepush(repo / ".git" / "hooks")

        assert _run_cli(repo).returncode == 0

    def test_a_healthy_repo_reports_what_it_probed_and_where(
        self, tmp_path: Path
    ) -> None:
        # MUST 12: "OK" is not verifiable. The examined count and the resolved
        # directory are, and they distinguish a real check from a no-op.
        repo = _make_repo(tmp_path, "healthy")
        _install_prepush(repo / ".git" / "hooks")

        out = _run_cli(repo).stdout

        assert "1 of 1 probed hook found" in out
        assert "pre-push present in" in out

    def test_a_healthy_repo_diagnoses_as_none(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "healthy")
        _install_prepush(repo / ".git" / "hooks")

        assert check_git_hook_health.diagnose(repo) is None


class TestDeadHooks:
    """Each way git ends up running no hook exits non-zero and names the fix."""

    def test_hooks_path_pointing_at_a_missing_directory_fails(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, "missing_dir")
        _install_prepush(repo / ".git" / "hooks")
        _git(repo, "config", "core.hooksPath", str(repo / ".githooks"))

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "does not exist" in result.stderr
        assert "core.hooksPath" in result.stderr
        assert check_git_hook_health.REMEDY in result.stderr

    def test_hooks_path_directory_without_pre_push_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "empty_dir")
        _install_prepush(repo / ".git" / "hooks")
        (repo / ".githooks").mkdir()
        _git(repo, "config", "core.hooksPath", str(repo / ".githooks"))

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "has no pre-push hook" in result.stderr
        assert check_git_hook_health.REMEDY in result.stderr

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Git for Windows does not use POSIX execute bits"
    )
    def test_non_executable_pre_push_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "non_executable")
        hook = repo / ".git" / "hooks" / "pre-push"
        _install_prepush(hook.parent)
        hook.chmod(0o644)

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "exists but is not executable" in result.stderr
        assert check_git_hook_health.REMEDY in result.stderr

    def test_missing_pre_push_with_hooks_path_unset_fails(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "no_prepush")

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "core.hooksPath is unset" in result.stderr
        assert check_git_hook_health.REMEDY in result.stderr

    def test_the_failure_report_stays_within_the_line_budget(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, "missing_dir")
        _git(repo, "config", "core.hooksPath", str(repo / ".githooks"))

        result = _run_cli(repo)

        assert len(result.stderr.rstrip("\n").split("\n")) <= 6


class TestLinkedWorktrees:
    """A linked worktree reads the common directory's hooks, not its own.

    ``git rev-parse --git-dir`` returns ``.git/worktrees/<name>`` there, whose
    ``hooks/`` is NOT where git looks. Measured on git 2.51.0: a push from a
    linked worktree runs the pre-push under the common directory, and stops
    when that file is removed. Both directions are pinned because this repo
    runs every agent in a linked worktree, so a gate that got this backwards
    would fire on every agent at once.
    """

    def test_a_worktree_with_a_common_dir_pre_push_is_healthy(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, "wt_main")
        _install_prepush(repo / ".git" / "hooks")
        worktree = tmp_path / "wt_linked"
        _git(repo, "worktree", "add", "-q", str(worktree), "-b", "feature")
        (worktree / "lefthook.yml").write_text(LEFTHOOK_CONFIG, encoding="utf-8")
        # The per-worktree git dir has no hooks/ of its own; a gate that looked
        # there instead of at the common directory would report a false failure.
        assert not (repo / ".git" / "worktrees" / "wt_linked" / "hooks").exists()

        result = _run_cli(worktree)

        assert result.returncode == 0
        assert result.stderr == ""

    def test_a_worktree_inherits_a_broken_hooks_path(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "wt_main")
        _install_prepush(repo / ".git" / "hooks")
        worktree = tmp_path / "wt_linked"
        _git(repo, "worktree", "add", "-q", str(worktree), "-b", "feature")
        (worktree / "lefthook.yml").write_text(LEFTHOOK_CONFIG, encoding="utf-8")
        _git(repo, "config", "core.hooksPath", str(repo / ".githooks"))

        result = _run_cli(worktree)

        assert result.returncode == 1
        assert "does not exist" in result.stderr


class TestOutOfScope:
    """States the gate cannot read, or has no business judging, pass."""

    def test_a_repo_without_lefthook_config_passes(self, tmp_path: Path) -> None:
        # The remedy is a lefthook command. A repository that runs no lefthook
        # and installs no hooks has chosen that; it is not broken.
        repo = _make_repo(tmp_path, "no_lefthook", lefthook=False)

        result = _run_cli(repo)

        assert result.returncode == 0
        assert "no lefthook config" in result.stdout

    def test_a_directory_that_is_not_a_git_repository_passes(
        self, tmp_path: Path
    ) -> None:
        plain = tmp_path / "not_a_repo"
        plain.mkdir()
        (plain / "lefthook.yml").write_text(LEFTHOOK_CONFIG, encoding="utf-8")

        result = _run_cli(plain)

        assert result.returncode == 0

    def test_no_git_binary_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path, "no_git")
        monkeypatch.setattr(check_git_hook_health.shutil, "which", lambda _name: None)

        assert check_git_hook_health.validate_git_hook_health(repo) is True

    def test_a_root_that_is_not_a_directory_is_a_config_error(
        self, tmp_path: Path
    ) -> None:
        assert check_git_hook_health.main([str(tmp_path / "nope")]) == 2


class TestNegativeControl:
    """Prove these tests fail if the gate stops detecting."""

    def test_a_neutered_gate_stops_failing_a_broken_repo(self, tmp_path: Path) -> None:
        # Without this, every pass assertion above could be passing because the
        # harness cannot observe the gate at all.
        repo = _make_repo(tmp_path, "missing_dir")
        _git(repo, "config", "core.hooksPath", str(repo / ".githooks"))
        original = GUARD.read_text(encoding="utf-8")
        target = (
            "    if hook.is_file() and os.access(hook, os.X_OK):\n"
            "        return None\n"
        )
        assert original.count(target) == 1, (
            "mutation target moved; the control did not apply"
        )
        neutered = tmp_path / "neutered_gate.py"
        neutered.write_text(
            original.replace(target, "    if True:\n        return None\n"),
            encoding="utf-8",
        )
        assert neutered.read_text(encoding="utf-8") != original

        live = _run_cli(repo)
        control = _run_cli(repo, guard=neutered)

        assert live.returncode == 1, "the unmutated gate must fail this repo"
        assert control.returncode == 0, "the mutated gate must stop failing it"


def _drive(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[Path]]:
    """Run the real sequence with a spy bound over the validator."""
    seen: list[Path] = []

    def spy(repo_root: Path) -> bool:
        seen.append(repo_root)
        return True

    monkeypatch.setattr(pre_pr_sequence, "validate_git_hook_health", spy)

    names: list[str] = []

    def fake_run_validation(
        name: str,
        _state: SimpleNamespace,
        callback: Callable[[], bool],
        skip: bool = False,
    ) -> bool:
        names.append(name)
        if name == GATE_NAME and not skip:
            callback()
        return True

    args = SimpleNamespace(quick=False, skip_tests=False, verbose=False)
    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    with redirect_stdout(io.StringIO()):
        pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    return names, seen


class TestSequenceWiring:
    """pre_pr.py must reach the validator, not merely be able to."""

    def test_the_sequence_emits_the_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        names, _seen = _drive(monkeypatch)

        assert GATE_NAME in names

    def test_the_gate_calls_the_validator_with_the_repo_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _names, seen = _drive(monkeypatch)

        assert seen == [REPO_ROOT]

    def test_the_gate_sits_next_to_the_lefthook_install_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # They answer the same question at two depths. Adjacent placement is
        # what stops the next reader from thinking one covers the other.
        names, _seen = _drive(monkeypatch)

        assert names.index(GATE_NAME) + 1 == names.index("Lefthook Installed")
