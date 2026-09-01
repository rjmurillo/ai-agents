"""A ``core.bare`` true that git has already overridden is not the incident.

Split from ``test_check_repo_health.py``, which pins detection, to keep both
files under the 500-line taste ceiling. These cases pin the opposite obligation
to that file's: the configurations where ``true`` is present in some scope and
the repository is nevertheless usable, so the gate must not print a repair for
a condition nobody has.

``core.bare`` is single-valued. Git answers it with one value however many
scopes carry it, and that value is the last one in precedence order. Reading
"any scope says true" instead reported corruption for a repository whose
``git status`` works, and the repair it printed then wrote a value nothing
needed into a config file that was already correct.

Measured on git 2.43.0, with the ``--get`` column the property under test::

    git config --show-scope --type=bool --get-all core.bare   --get   status
    global true, local false                                  false   0
    local true, local false                                   false   0
    local false, local true                                   true    128
    local true, worktree false                                false   0

The fourth row is why the effective value alone cannot carry the verdict, and
it is the one row where the gate still fails: that is the state issue #4698
left behind, where the shared config poisons every sibling worktree while this
one carries the worktree-scoped ``false`` GOTCHAS prescribes.
``test_check_repo_health.py`` owns that case; this file owns the first three
and their controls.

Coverage:

- positive: a masked ``global true``, a masked earlier ``local true``, and a
  masked ``true`` under a worktree-scoped ``false`` in a genuinely bare
  repository each exit 0 and print no repair, through ``main`` and through the
  CLI process. The usable line names the masked value rather than claiming
  none was set.
- negative: the discriminating controls. Reversing the write order in each
  masked pair makes the same repository exit 1, so the exit-0 cases are not
  passing because the gate stopped reading config at all.
- edge: ``_effective_pair`` and ``_active_bare_scopes`` over the scope orders
  above, including the empty read and the ``ignore_worktree`` projection.

Every configuration here is asserted against git's own answer before the gate
is run, so a git version that changes precedence fails on the premise rather
than on the verdict.

Refs #4698.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_repo_health

GUARD = _VALIDATION_DIR / "check_repo_health.py"

_REPAIR = "--replace-all core.bare false"


def _git_test_env() -> dict[str, str]:
    """Return a host-independent environment for scratch Git repositories."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env or _git_test_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _git_rc(cwd: Path, *args: str, env: dict[str, str] | None = None) -> int:
    """Run git without asserting, for cases where the exit code is the evidence."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env or _git_test_env(),
        capture_output=True,
        text=True,
        check=False,
    ).returncode


@pytest.fixture(autouse=True)
def _use_scratch_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the gate's own git calls off the host's global and system config."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)


def _make_repo(root: Path, name: str = "repo") -> Path:
    """Create a scratch checkout with one commit."""
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "tracked.txt").write_text("content\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _global_config(tmp_path: Path, value: str) -> dict[str, str]:
    """Return an environment whose global config carries ``core.bare = value``."""
    path = tmp_path / "gitconfig"
    path.write_text(f"[core]\n\tbare = {value}\n", encoding="utf-8")
    return {**_git_test_env(), "GIT_CONFIG_GLOBAL": str(path)}


def _run_cli(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Drive the script as lefthook does, so the process exit code is asserted."""
    return subprocess.run(
        [sys.executable, str(GUARD), str(repo)],
        cwd=str(repo),
        env={**env, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )


class TestAGlobalTrueUnderALocalFalseIsNotTheIncident:
    """The masked pair that spans two config files."""

    @staticmethod
    def _repo_with(tmp_path: Path, local: str) -> tuple[Path, dict[str, str]]:
        repo = _make_repo(tmp_path)
        env = _global_config(tmp_path, "true")
        _git(repo, "config", "core.bare", local, env=env)
        return repo, env

    def test_git_itself_resolves_the_repository_usable(self, tmp_path: Path) -> None:
        """The premise: the gate must agree with this, not contradict it."""
        repo, env = self._repo_with(tmp_path, "false")

        read = ("config", "--show-scope", "--type=bool", "--get-all", "core.bare")
        scopes = _git(repo, *read, env=env)

        assert scopes.splitlines() == ["global\ttrue", "local\tfalse"]
        assert _git(repo, "config", "--get", "core.bare", env=env) == "false"
        assert _git(repo, "rev-parse", "--is-bare-repository", env=env) == "false"
        assert _git_rc(repo, "status", "--short", env=env) == 0

    def test_it_exits_zero_and_prints_no_repair(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo, env = self._repo_with(tmp_path, "false")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", env["GIT_CONFIG_GLOBAL"])

        code = check_repo_health.main([str(repo)])

        assert code == 0
        captured = capsys.readouterr()
        assert _REPAIR not in captured.out + captured.err
        assert "Fix:" not in captured.err

    def test_the_usable_line_names_the_masked_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A flat "none set true" would misdescribe a config that does say true."""
        repo, env = self._repo_with(tmp_path, "false")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", env["GIT_CONFIG_GLOBAL"])

        check_repo_health.main([str(repo)])

        out = capsys.readouterr().out
        assert "read in 2 config scope(s)" in out
        assert "global=true overridden by a later scope" in out
        assert "none set true" not in out

    def test_the_cli_process_exits_zero(self, tmp_path: Path) -> None:
        repo, env = self._repo_with(tmp_path, "false")

        result = _run_cli(repo, env)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _REPAIR not in result.stdout + result.stderr

    def test_a_local_true_over_the_same_global_still_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The discriminating control: only the local value differs."""
        repo, env = self._repo_with(tmp_path, "true")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", env["GIT_CONFIG_GLOBAL"])
        assert _git_rc(repo, "status", "--short", env=env) == 128

        code = check_repo_health.main([str(repo)])

        assert code == 1
        assert f"Fix: git config {_REPAIR}" in capsys.readouterr().err


class TestARepeatedLocalKeyIsResolvedByOrderNotByPresence:
    """The masked pair that sits inside one config file."""

    @staticmethod
    def _repo_with(tmp_path: Path, first: str, second: str) -> Path:
        repo = _make_repo(tmp_path)
        _git(repo, "config", "--unset-all", "core.bare")
        _git(repo, "config", "--add", "core.bare", first)
        _git(repo, "config", "--add", "core.bare", second)
        return repo

    def test_git_itself_resolves_a_trailing_false_usable(self, tmp_path: Path) -> None:
        """The premise: two local values, and only the last one counts."""
        repo = self._repo_with(tmp_path, "true", "false")

        scopes = _git(repo, "config", "--show-scope", "--type=bool", "--get-all", "core.bare")

        assert scopes.splitlines() == ["local\ttrue", "local\tfalse"]
        assert _git(repo, "config", "--get", "core.bare") == "false"
        assert _git_rc(repo, "status", "--short") == 0

    def test_a_trailing_false_exits_zero_and_prints_no_repair(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = self._repo_with(tmp_path, "true", "false")

        code = check_repo_health.main([str(repo)])

        assert code == 0
        captured = capsys.readouterr()
        assert _REPAIR not in captured.out + captured.err
        assert "local=true overridden by a later scope" in captured.out

    def test_a_trailing_true_still_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The discriminating control: same two values, written the other way."""
        repo = self._repo_with(tmp_path, "false", "true")
        assert _git_rc(repo, "status", "--short") == 128

        code = check_repo_health.main([str(repo)])

        assert code == 1
        assert f"Fix: git config {_REPAIR}" in capsys.readouterr().err


class TestAWorktreeScopedFalseOverABareRepositoryIsStillBareByDesign:
    """The worktree scope wins here too, and the shared value is not a work tree."""

    def test_a_bare_repository_immunizing_itself_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seed = _make_repo(tmp_path, "seed")
        bare = tmp_path / "origin.git"
        _git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
        _git(bare, "config", "extensions.worktreeConfig", "true")
        _git(bare, "config", "--worktree", "core.bare", "false")

        code = check_repo_health.main([str(bare)])

        assert code == 0
        assert _REPAIR not in capsys.readouterr().err


class TestTheResolverMatchesGitsPrecedenceRule:
    """Edge: the two pure functions, over the orders measured in the docstring."""

    @pytest.mark.parametrize(
        ("scoped", "expected", "shared"),
        [
            ((), None, None),
            ((("local", "false"),), ("local", "false"), ("local", "false")),
            (
                (("global", "true"), ("local", "false")),
                ("local", "false"),
                ("local", "false"),
            ),
            (
                (("local", "false"), ("local", "true")),
                ("local", "true"),
                ("local", "true"),
            ),
            (
                (("local", "true"), ("worktree", "false")),
                ("worktree", "false"),
                ("local", "true"),
            ),
            (
                (("local", "true"), ("worktree", "false"), ("command", "false")),
                ("command", "false"),
                ("command", "false"),
            ),
        ],
    )
    def test_the_last_pair_wins_and_ignore_worktree_drops_that_scope(
        self,
        scoped: tuple[tuple[str, str], ...],
        expected: tuple[str, str] | None,
        shared: tuple[str, str] | None,
    ) -> None:
        assert check_repo_health._effective_pair(scoped) == expected
        assert check_repo_health._effective_pair(scoped, ignore_worktree=True) == shared

    @pytest.mark.parametrize(
        ("scoped", "active"),
        [
            ((), ()),
            ((("local", "false"),), ()),
            ((("global", "true"), ("local", "false")), ()),
            ((("local", "true"), ("local", "false")), ()),
            ((("local", "true"),), (("local", "true"),)),
            ((("local", "false"), ("local", "true")), (("local", "true"),)),
            # The sibling check: the worktree-scoped false masks the value here
            # and nowhere else, so this must stay reported.
            ((("local", "true"), ("worktree", "false")), (("local", "true"),)),
            ((("worktree", "true"),), (("worktree", "true"),)),
            (
                (("global", "true"), ("local", "true")),
                (("global", "true"), ("local", "true")),
            ),
        ],
    )
    def test_only_a_value_in_force_is_reported(
        self,
        scoped: tuple[tuple[str, str], ...],
        active: tuple[tuple[str, str], ...],
    ) -> None:
        assert check_repo_health._active_bare_scopes(scoped) == active
