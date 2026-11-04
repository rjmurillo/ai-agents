"""AC-24 (state root refusal) and AC-15 (clean git tree) for the reflect nudge.

REQ-048 TASK-004. A refusal creates no directory or file, emits no
systemMessage, writes one stderr line, and exits 0. The subprocess tests run
the rendered hook in a real temporary git repository.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from tests.hooks.friction_nudge_support import friction_records, run_env
from tests.hooks.reflect_nudge_safety_support import (
    RENDERED_HOOK,
    STATE_SUBDIR,
    child_env,
    correction_records,
    git,
    init_repo,
    isolated_home,  # noqa: F401  (pytest fixture)
    run_subprocess,
    stop_payload,
    tree_snapshot,
    write_transcript,
)
from tests.hooks.reflect_nudge_support import nudge, nudge_state

pytestmark = pytest.mark.usefixtures("isolated_home")

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="HOME rule and symlinks are POSIX")
REPO_REFUSAL = "state root inside a repository, refused"
LSTAT_REFUSAL = "state root check failed (lstat error), refused"


@pytest.fixture
def corrected(tmp_path: Path) -> Path:
    return write_transcript(tmp_path / "t.jsonl", correction_records())


def _assert_refused(code: int, out: str, err: str, reason: str) -> None:
    assert (code, out) == (0, "")
    assert reason in err
    assert len(err.strip().splitlines()) == 1


def _fake_repo(tmp_path: Path, as_file: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    if as_file:
        (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/w\n", encoding="utf-8")
    else:
        (repo / ".git").mkdir()
    return repo


class TestRepositoryRefusal:
    @pytest.mark.parametrize("as_file", [False, True], ids=[".git directory", ".git file"])
    def test_state_root_in_repository_creates_nothing(
        self, as_file: bool, corrected: Path, tmp_path: Path
    ) -> None:
        repo = _fake_repo(tmp_path, as_file)
        before = sorted(p.name for p in repo.iterdir())
        code, out, err = run_env(corrected, repo / "state")
        _assert_refused(code, out, err, REPO_REFUSAL)
        assert sorted(p.name for p in repo.iterdir()) == before

    def test_state_root_equal_to_the_repository_root_is_refused(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        repo = _fake_repo(tmp_path, as_file=False)
        code, out, err = run_env(corrected, repo)
        _assert_refused(code, out, err, REPO_REFUSAL)
        assert not (repo / STATE_SUBDIR).exists()

    def test_state_root_that_does_not_exist_yet_climbs_to_an_existing_ancestor(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        repo = _fake_repo(tmp_path, as_file=False)
        code, out, err = run_env(corrected, repo / "a" / "b" / "c")
        _assert_refused(code, out, err, REPO_REFUSAL)
        assert not (repo / "a").exists()

    def test_refusal_runs_before_any_mkdir(
        self, corrected: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _fake_repo(tmp_path, as_file=False)

        def forbidden(*_a: object, **_k: object) -> None:
            raise AssertionError("mkdir ran before the repository walk")

        monkeypatch.setattr(Path, "mkdir", forbidden)
        monkeypatch.setattr(os, "mkdir", forbidden)
        code, out, err = run_env(corrected, repo / "state")
        _assert_refused(code, out, err, REPO_REFUSAL)

    @POSIX_ONLY
    def test_symlinked_state_root_that_resolves_into_a_repository_is_refused(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        repo = _fake_repo(tmp_path, as_file=False)
        target = repo / "state"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target, target_is_directory=True)
        code, out, err = run_env(corrected, link)
        _assert_refused(code, out, err, REPO_REFUSAL)
        assert list(target.iterdir()) == []

    @POSIX_ONLY
    def test_symlinked_root_outside_any_repository_still_works(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "real-state"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target, target_is_directory=True)
        _, out, _ = run_env(corrected, link)
        assert "systemMessage" in out
        assert (target / STATE_SUBDIR).is_dir()

    def test_negative_control_root_outside_any_repository_nudges(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        _fake_repo(tmp_path, as_file=False)
        state = tmp_path / "elsewhere" / "state"
        code, out, _ = run_env(corrected, state)
        assert code == 0 and "systemMessage" in out
        assert (state / STATE_SUBDIR).is_dir()

    def test_safe_marker_dir_also_walks_before_mkdir(self, tmp_path: Path) -> None:
        repo = _fake_repo(tmp_path, as_file=False)
        assert nudge_state.safe_marker_dir(repo / "x" / "y") is None
        assert not (repo / "x").exists()

    def test_lstat_failure_other_than_not_found_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_lstat = os.lstat

        def deny(path: str | os.PathLike[str]) -> os.stat_result:
            if os.fspath(path).endswith(".git"):
                raise PermissionError("denied")
            return real_lstat(path)

        monkeypatch.setattr(os, "lstat", deny)
        root, reason = nudge_state.resolve_state_root({}, tmp_path / "s")
        assert (root, reason) == (None, LSTAT_REFUSAL)

    @POSIX_ONLY
    def test_symlink_loop_is_refused_not_raised(self, tmp_path: Path) -> None:
        loop = tmp_path / "loop"
        loop.symlink_to(loop)
        root, reason = nudge_state.resolve_state_root({}, loop)
        assert (root, reason) == (None, LSTAT_REFUSAL)

    def test_off_is_checked_before_the_walk(self, corrected: Path, tmp_path: Path) -> None:
        repo = _fake_repo(tmp_path, as_file=False)
        env = {"AI_AGENTS_RETRO_NUDGE_THRESHOLD": "off"}
        assert run_env(corrected, repo / "state", env) == (0, "", "")


class TestHomeUnset:
    @POSIX_ONLY
    @pytest.mark.parametrize("env", [{}, {"HOME": ""}], ids=["unset", "empty"])
    def test_unset_home_creates_nothing_even_with_xdg_set(
        self, env: dict[str, str], corrected: Path, tmp_path: Path
    ) -> None:
        xdg = tmp_path / "xdg"
        code, out, err = run_env(corrected, None, {**env, "XDG_STATE_HOME": str(xdg)})
        _assert_refused(code, out, err, "HOME unset, state root refused")
        assert not xdg.exists()

    @POSIX_ONLY
    def test_unset_home_without_xdg_creates_nothing(self, corrected: Path) -> None:
        home = Path(os.environ["HOME"])  # the isolated_home fixture's temp dir
        code, out, err = run_env(corrected, None, {})
        _assert_refused(code, out, err, "HOME unset, state root refused")
        assert list(home.iterdir()) == []

    @POSIX_ONLY
    def test_negative_control_home_set_nudges(self, corrected: Path, tmp_path: Path) -> None:
        env = {"HOME": str(tmp_path / "h"), "XDG_STATE_HOME": str(tmp_path / "xdg")}
        _, out, _ = run_env(corrected, None, env)
        assert "systemMessage" in out
        assert (tmp_path / "xdg" / STATE_SUBDIR).is_dir()

    def test_windows_does_not_apply_the_home_rule(self, tmp_path: Path) -> None:
        root, reason = nudge_state.resolve_state_root({"LOCALAPPDATA": str(tmp_path)}, None, "nt")
        assert (root, reason) == (tmp_path.resolve(), "")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestCleanGitTree:
    """AC-15: run the rendered hook in a real repository and prove it leaves no trace."""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        return init_repo(tmp_path / "work" / "repo")

    @pytest.mark.parametrize("kind", ["correction", "friction"])
    def test_hook_leaves_repository_untouched_and_marker_outside(
        self, kind: str, repo: Path, tmp_path: Path
    ) -> None:
        records = correction_records() if kind == "correction" else friction_records(4, 1)
        transcript = write_transcript(tmp_path / "t.jsonl", records)
        state_home = tmp_path / "state-home"
        git(repo, "status", "--porcelain")  # priming call: git may refresh .git/index
        snapshot = tree_snapshot(repo / ".git")
        env = child_env(tmp_path / "home", state_home)

        done = run_subprocess(RENDERED_HOOK, stop_payload(transcript, repo), env, repo)

        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)["systemMessage"]
        # Snapshot first: a write by the later git status must not mask the hook's.
        assert tree_snapshot(repo / ".git") == snapshot
        assert git(repo, "status", "--porcelain") == ""
        markers = list((state_home / STATE_SUBDIR).iterdir())
        assert markers and not any(repo in m.parents for m in markers)
        assert [p.name for p in repo.iterdir()] == [".git"]

    def test_hook_refuses_a_state_root_inside_the_repository(
        self, repo: Path, tmp_path: Path
    ) -> None:
        transcript = write_transcript(tmp_path / "t.jsonl", correction_records())
        git(repo, "status", "--porcelain")
        snapshot = tree_snapshot(repo / ".git")
        env = child_env(tmp_path / "home", repo / "state")

        done = run_subprocess(RENDERED_HOOK, stop_payload(transcript, repo), env, repo)

        assert (done.returncode, done.stdout) == (0, "")
        assert REPO_REFUSAL in done.stderr
        assert [p.name for p in repo.iterdir()] == [".git"]
        assert tree_snapshot(repo / ".git") == snapshot

    def test_hook_writes_no_bytecode_beside_itself(self, repo: Path, tmp_path: Path) -> None:
        transcript = write_transcript(tmp_path / "t.jsonl", correction_records())
        env = child_env(tmp_path / "home", tmp_path / "state-home")
        run_subprocess(RENDERED_HOOK, stop_payload(transcript, repo), env, repo)
        assert not list(RENDERED_HOOK.parent.rglob("__pycache__"))


def test_hook_module_exposes_the_refusal_entry_point() -> None:
    assert nudge.resolve_state_root is nudge_state.resolve_state_root


def test_marker_dir_refused_when_the_root_becomes_a_symlink_into_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The root swapped for a symlink between the walk and mkdir is caught after mkdir."""
    repo = _fake_repo(tmp_path, as_file=False)
    safe = tmp_path / "safe"
    safe.mkdir()
    real_mkdir = Path.mkdir

    def racing_mkdir(
        self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
    ) -> None:
        if self == safe / "late":
            (safe / "late").symlink_to(repo)  # the race: swap in a link, then mkdir follows it
            return
        real_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", racing_mkdir)
    assert nudge_state.safe_marker_dir(safe / "late") is None
