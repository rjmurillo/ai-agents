# taste-lint: ignore file-size, crossed 500 lines adding the inert-hook and
# unreadable-hook cases to the dead-hooks class. This file is one gate's
# contract, and its classes define each other: the healthy path only means
# something read beside the dead-hook path it excludes. The split this file
# already supports is by environment, and those cases live in
# test_check_git_hook_health_environment.py. Issue #3779.
"""The pre-PR sequence refuses a push git would not gate (issue #5090).

Two claims, separable, both pinned.

The gate's own logic: a ``core.hooksPath`` that git cannot read ``pre-push``
from exits 1 and names the failed condition and repair; a healthy repository
exits 0 and says what it probed and where. Missing Git, timeouts, and unexpected
Git failures exit 3 because an unreadable hook state is not a verified pass.

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
- negative: a missing hooksPath directory, a directory with no pre-push, an
  unset hooksPath with no pre-push, an executable hook that dispatches nothing,
  one whose marker is commented out, one that echoes the marker, and an
  undecodable one all exit 1 and name the remedy; an unreadable hook fails
  closed through the OSError branch and reports the read failure rather than a
  wrong command; a configured hook type with no shim, a non-executable one, and
  one declared only in a `-local` overlay each fail, and that failure does not
  claim pre-push is dead; a linked worktree
  inherits the broken config; removing the gate fails the wiring test.
- edge: no lefthook config, non-repositories, and CI exit 0; missing Git and
  timeouts exit 3; the failure report stays inside a line budget.
"""

from __future__ import annotations

import io
import os
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
# Two hook types configured. With `no_auto_install: true` a newly added type
# keeps no shim until install runs again, and git runs nothing for it silently.
TWO_HOOK_CONFIG = (
    "pre-push:\n  commands:\n    noop:\n      run: true\n"
    "commit-msg:\n  commands:\n    noop:\n      run: true\n"
)


def _git_test_env() -> dict[str, str]:
    """Return a host-independent environment for scratch Git repositories."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }


@pytest.fixture(autouse=True)
def _exercise_local_clone_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep local-clone tests independent of the runner's ambient CI state."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_git_test_env(),
        capture_output=True,
        text=True,
        check=False,
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


# The shape Lefthook installs, reduced to the line this gate matches. The old
# fixture here was `#!/bin/sh\nexit 0`, an executable hook that dispatches
# nothing, so every "healthy" assertion in this file was satisfied by exactly
# the fail-open state the gate is meant to refuse (issue #4789).
DISPATCHING_PREPUSH = (
    "#!/bin/sh\n"
    "call_lefthook()\n"
    "{\n"
    '  lefthook "$@"\n'
    "}\n"
    'call_lefthook run "pre-push" "$@"\n'
)
# Executable, final command, contains the marker, dispatches nothing. Refused
# only by matching the complete generated command rather than a substring.
ECHOED_MARKER_PREPUSH = (
    "#!/bin/sh\n"
    "echo 'call_lefthook run \"pre-push\"'\n"
)
INERT_PREPUSH = "#!/bin/sh\nexit 0\n"
# Executable, mentions the marker, dispatches nothing. A whole-file substring
# search accepts this; anchoring to the final command refuses it (CWE-693).
COMMENTED_MARKER_PREPUSH = (
    "#!/bin/sh\n"
    '# call_lefthook run "pre-push" "$@"\n'
    "exit 0\n"
)


def _install_prepush(hooks_dir: Path, body: str = DISPATCHING_PREPUSH) -> None:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-push"
    hook.write_text(body, encoding="utf-8")
    hook.chmod(0o755)


def _run_cli(repo: Path, guard: Path = GUARD) -> subprocess.CompletedProcess[str]:
    """Drive the CLI in its own process, as a hook or a shell would.

    The environment is built from scratch rather than inherited so no CI-only
    variable can change the branch under test (testing.md SHOULD 12).
    """
    return subprocess.run(
        [sys.executable, str(guard), str(repo)],
        cwd=str(repo),
        env=_git_test_env(),
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

        assert "1 of 1 found" in out
        assert "pre-push live in" in out

    def test_a_healthy_repo_diagnoses_as_none(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "healthy")
        _install_prepush(repo / ".git" / "hooks")

        assert check_git_hook_health.diagnose(repo) is None


class TestDeadHooks:
    """Each way git skips pre-push exits non-zero and names the fix."""

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

    def test_an_executable_hook_that_dispatches_nothing_fails(
        self, tmp_path: Path
    ) -> None:
        """The fail-open case: executable, readable by git, and inert.

        Before this assertion existed, `#!/bin/sh` plus `exit 0` passed here,
        and it also passes the adjacent `Lefthook Installed` gate, which only
        proves the configured runtime starts. Together the two gates reported a
        gated push for a clone that runs no job at all (issue #4789).
        """
        repo = _make_repo(tmp_path, "inert")
        _install_prepush(repo / ".git" / "hooks", body=INERT_PREPUSH)

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "does not dispatch Lefthook" in result.stderr
        assert check_git_hook_health.REMEDY in result.stderr

    def test_a_commented_out_marker_does_not_count_as_dispatch(
        self, tmp_path: Path
    ) -> None:
        """Mentioning the marker is not dispatching it.

        The first version of this gate matched the marker anywhere in the file,
        so an inert hook carrying it in a comment above `exit 0` passed while
        running no guard. The check is anchored to the final command instead.
        """
        repo = _make_repo(tmp_path, "commented")
        _install_prepush(repo / ".git" / "hooks", body=COMMENTED_MARKER_PREPUSH)

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "does not dispatch Lefthook" in result.stderr

    def test_an_echoed_marker_does_not_count_as_dispatch(
        self, tmp_path: Path
    ) -> None:
        """Printing the dispatch is not running it.

        The prior version anchored to the final command but matched a
        substring, so `echo 'call_lefthook run "pre-push"'` passed: an
        executable final command that dispatches nothing. The check now
        compares against the complete generated command.
        """
        repo = _make_repo(tmp_path, "echoed")
        _install_prepush(repo / ".git" / "hooks", body=ECHOED_MARKER_PREPUSH)

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "does not dispatch Lefthook" in result.stderr

    def test_an_undecodable_hook_fails(self, tmp_path: Path) -> None:
        """A binary payload decodes under errors="replace" and has no marker.

        Named for what it actually exercises. It does not reach the OSError
        branch, which the test below covers.
        """
        repo = _make_repo(tmp_path, "undecodable")
        hooks_dir = repo / ".git" / "hooks"
        _install_prepush(hooks_dir)
        (hooks_dir / "pre-push").write_bytes(b"\x00\xff\xfe binary payload")
        (hooks_dir / "pre-push").chmod(0o755)

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "does not dispatch Lefthook" in result.stderr

    def test_an_unreadable_hook_reports_the_read_failure_not_a_wrong_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hook the gate cannot read is unverified, and says so.

        Drives the `except OSError` branch, which no on-disk payload reaches:
        production reads with `errors="replace"`, so decoding always succeeds.
        The earlier version collapsed this into the same boolean as a wrong
        final command, so the gate blamed the command when nothing had been
        read and the real permission fault was hidden.
        """
        repo = _make_repo(tmp_path, "unreadable")
        _install_prepush(repo / ".git" / "hooks")

        def deny(self: Path, *args: object, **kwargs: object) -> str:
            raise PermissionError(f"denied: {self}")

        monkeypatch.setattr(check_git_hook_health.Path, "read_text", deny)
        reason = check_git_hook_health.diagnose(repo)

        assert reason is not None
        assert "could not be read" in reason
        assert "state is unverifiable" in reason
        assert "does not dispatch Lefthook" not in reason

    def test_a_configured_hook_type_with_no_shim_fails(self, tmp_path: Path) -> None:
        """Probing pre-push alone misses the hook type someone just added.

        `no_auto_install: true` is what keeps one worktree from re-syncing the
        shims every other worktree reads, and the same setting leaves a newly
        configured hook type with no shim until install runs again. Git runs no
        hook it has no file for and prints no warning.
        """
        repo = _make_repo(tmp_path, "missing_type")
        (repo / "lefthook.yml").write_text(TWO_HOOK_CONFIG, encoding="utf-8")
        _install_prepush(repo / ".git" / "hooks")

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "commit-msg" in result.stderr
        assert check_git_hook_health._POST_PROBE_PREFIX in result.stderr

    def test_every_configured_hook_type_installed_passes(self, tmp_path: Path) -> None:
        """The positive control for the check above."""
        repo = _make_repo(tmp_path, "all_types")
        (repo / "lefthook.yml").write_text(TWO_HOOK_CONFIG, encoding="utf-8")
        hooks_dir = repo / ".git" / "hooks"
        _install_prepush(hooks_dir)
        commit_msg = hooks_dir / "commit-msg"
        commit_msg.write_text(
            DISPATCHING_PREPUSH.replace('"pre-push"', '"commit-msg"'),
            encoding="utf-8",
        )
        commit_msg.chmod(0o755)

        result = _run_cli(repo)

        assert result.returncode == 0
        # The count must track what was examined. It was hard-coded `1 of 1`,
        # which made the multi-hook check read as the old single probe.
        assert "2 of 2 found" in result.stdout
        assert "commit-msg" in result.stdout

    def test_a_local_overlay_hook_type_is_checked(self, tmp_path: Path) -> None:
        """A `-local` overlay adds hook types, and Lefthook installs them.

        Stopping at the first matching config filename read only the base file,
        so an overlay's hook type could have no shim while the gate reported
        healthy.
        """
        repo = _make_repo(tmp_path, "overlay")
        (repo / "lefthook-local.yml").write_text(
            "commit-msg:\n  commands:\n    noop:\n      run: true\n",
            encoding="utf-8",
        )
        _install_prepush(repo / ".git" / "hooks")

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "commit-msg" in result.stderr

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Git for Windows does not use POSIX execute bits"
    )
    def test_a_non_executable_configured_hook_fails(self, tmp_path: Path) -> None:
        """Text alone is not installation: git ignores a non-executable shim.

        Same platform skip as the `pre-push` case above: `chmod(0o644)` cannot
        create this state on Windows, so the test could not establish its own
        precondition there.
        """
        repo = _make_repo(tmp_path, "not_executable_type")
        (repo / "lefthook.yml").write_text(TWO_HOOK_CONFIG, encoding="utf-8")
        hooks_dir = repo / ".git" / "hooks"
        _install_prepush(hooks_dir)
        commit_msg = hooks_dir / "commit-msg"
        commit_msg.write_text(
            DISPATCHING_PREPUSH.replace('"pre-push"', '"commit-msg"'),
            encoding="utf-8",
        )
        commit_msg.chmod(0o644)

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "commit-msg" in result.stderr

    def test_a_missing_hook_type_does_not_claim_pre_push_is_dead(
        self, tmp_path: Path
    ) -> None:
        """The summary must match the condition that was detected.

        `_evaluate` used to append "pre-push does not run" to every failure,
        including one reached only after the pre-push probe passed.
        """
        repo = _make_repo(tmp_path, "summary")
        (repo / "lefthook.yml").write_text(TWO_HOOK_CONFIG, encoding="utf-8")
        _install_prepush(repo / ".git" / "hooks")

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "pre-push itself is live" in result.stderr
        assert check_git_hook_health._POST_PROBE_PREFIX in result.stderr
        assert "pre-push does not run" not in result.stderr

    def test_a_dead_pre_push_still_says_pushes_are_ungated(
        self, tmp_path: Path
    ) -> None:
        """The positive control for the branch above."""
        repo = _make_repo(tmp_path, "dead_prepush")

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "pre-push does not run" in result.stderr

    def test_an_unreadable_config_fails_instead_of_degrading(
        self, tmp_path: Path
    ) -> None:
        """An inventory the gate cannot obtain is unverifiable, not healthy.

        The first version returned None here and fell back to probing only
        `pre-push`, so a `.jsonc` overlay adding `commit-msg` left that shim
        absent while this gate passed. Unverifiable is not a pass, the same rule
        the unreadable-hook case follows.
        """
        repo = _make_repo(tmp_path, "unparseable")
        (repo / "lefthook.yml").write_text("pre-push: [unclosed\n", encoding="utf-8")
        _install_prepush(repo / ".git" / "hooks")

        result = _run_cli(repo)

        assert result.returncode == 1
        assert "could not be read" in result.stderr
        assert "pre-push does not run" not in result.stderr

    def test_validation_reuses_the_resolved_hooks_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path, "one_hooks_path_read")
        hooks_dir = repo / ".git" / "hooks"
        calls = 0

        def resolve_once(_repo_root: Path) -> Path | None:
            nonlocal calls
            calls += 1
            return hooks_dir if calls == 1 else None

        monkeypatch.setattr(check_git_hook_health, "_hooks_dir", resolve_once)

        assert check_git_hook_health.validate_git_hook_health(repo) is False
        assert calls == 1

    def test_failure_claims_only_that_pushes_are_not_gated(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, "no_prepush_claim")

        result = _run_cli(repo)

        assert "Pushes are not locally gated: pre-push does not run." in result.stderr
        assert "Every git hook is inert" not in result.stderr

    @pytest.mark.parametrize(
        "config_name",
        [".lefthook.toml", "lefthook-local.jsonc", ".config/lefthook.yaml"],
    )
    def test_supported_lefthook_config_names_activate_the_gate(
        self, tmp_path: Path, config_name: str
    ) -> None:
        repo = _make_repo(tmp_path, "alternate_config", lefthook=False)
        config = repo / config_name
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(LEFTHOOK_CONFIG, encoding="utf-8")

        assert _run_cli(repo).returncode == 1

    @pytest.mark.parametrize("scope", ["global", "system"])
    def test_nonlocal_scope_remedy_unsets_the_authoritative_scope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
    ) -> None:
        repo = _make_repo(tmp_path, f"{scope}_scope")
        monkeypatch.setattr(
            check_git_hook_health,
            "_configured_hooks_path",
            lambda _repo_root: (".dead-hooks", scope),
        )

        remedy = check_git_hook_health._remedy(repo)

        assert f"git config --{scope} --unset-all core.hooksPath" in remedy
        assert check_git_hook_health.REMEDY in remedy

    def test_command_scope_remedy_does_not_claim_it_can_persistently_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path, "command_scope")
        monkeypatch.setattr(
            check_git_hook_health,
            "_configured_hooks_path",
            lambda _repo_root: (".dead-hooks", "command"),
        )

        remedy = check_git_hook_health._remedy(repo)

        assert "remove the command-scoped core.hooksPath override" in remedy
        assert check_git_hook_health.REMEDY in remedy

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

    def test_a_worktree_scoped_override_reports_a_repair_that_clears_it(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path, "wt_main_scoped")
        _install_prepush(repo / ".git" / "hooks")
        _git(repo, "config", "extensions.worktreeConfig", "true")
        worktree = tmp_path / "wt_linked_scoped"
        _git(repo, "worktree", "add", "-q", str(worktree), "-b", "feature-scoped")
        (worktree / "lefthook.yml").write_text(LEFTHOOK_CONFIG, encoding="utf-8")
        _git(
            worktree,
            "config",
            "--worktree",
            "core.hooksPath",
            str(worktree / ".dead-hooks"),
        )

        broken = _run_cli(worktree)

        assert broken.returncode == 1
        assert "worktree scope" in broken.stderr
        assert check_git_hook_health.WORKTREE_REMEDY in broken.stderr

        _git(worktree, "config", "--worktree", "--unset-all", "core.hooksPath")

        repaired = _run_cli(worktree)
        assert repaired.returncode == 0
        assert "pre-push live in" in repaired.stdout


class TestOutOfScope:
    """Only explicit non-applicability passes; execution failures fail closed."""

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

    def test_no_git_binary_is_an_external_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path, "no_git")
        monkeypatch.setattr(check_git_hook_health.shutil, "which", lambda _name: None)

        assert check_git_hook_health.validate_git_hook_health(repo) is False
        assert check_git_hook_health.main([str(repo)]) == 3

    def test_git_timeout_is_an_external_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_repo(tmp_path, "git_timeout")
        monkeypatch.setattr(
            check_git_hook_health.subprocess,
            "run",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("git", 5)
            ),
        )

        assert check_git_hook_health.validate_git_hook_health(repo) is False
        assert check_git_hook_health.main([str(repo)]) == 3

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
        # Short-circuit the whole diagnosis rather than one of its guards. The
        # gate now has two failing conditions, unreachable hook and inert hook,
        # and neutering only the first leaves the second still failing this
        # repository, which would make the control pass for the wrong reason.
        target = (
            '    """Diagnose the already-resolved hooks directory'
            ' without querying git again."""\n'
        )
        assert original.count(target) == 1, (
            "mutation target moved; the control did not apply"
        )
        neutered = tmp_path / "neutered_gate.py"
        neutered.write_text(
            original.replace(target, target + "    return None\n"),
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
