"""Git subprocess isolation for the count ratchets (issue #4914).

A ``git push`` from a linked worktree exports ``GIT_DIR`` into the pre-push
hook environment. An exported ``GIT_DIR`` outranks the ``-C <root>`` argument,
so every counter subprocess reads the pushing worktree instead of the root it
was handed. ``merge_tree_ratchet_check`` calls ``current_count(<scratch>)``, so
the effect is a file list from the wrong tree: the linter is handed scratch
paths that do not exist, the counter returns None, and the push is blocked.

These run git itself. A stand-in for ``subprocess.run`` would assert that some
dict was passed and would pass just as happily if git ignored it, which is the
whole question here. The negative control is a real second repository whose
index holds a file the tree under test does not: if isolation regresses, that
foreign path appears in the listing.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.ci import count_ratchet
from scripts.ci import ruff_count_ratchet as ruff_ratchet
from tests.ci.count_ratchet_git_harness import commit_all as _commit_all
from tests.ci.count_ratchet_git_harness import init_repo as _init_repo

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

_FOREIGN_ONLY = "scripts/validation/only_in_foreign.py"
_SHARED = "keep.py"


def _foreign_repo(tmp_path: Path) -> Path:
    """A repository whose index holds ``_FOREIGN_ONLY``; stands in for the pusher.

    Its gitdir is what a linked-worktree push exports as ``GIT_DIR``. Whether
    it is literally a linked worktree does not change the mechanism: git reads
    the variable, and any gitdir that is not the tree under test proves the
    override. Using a plain repository keeps the fixture readable and portable.
    """
    repo = tmp_path / "foreign"
    repo.mkdir()
    _init_repo(repo)
    (repo / _SHARED).write_text("y = 2\n", encoding="utf-8")
    target = repo / _FOREIGN_ONLY
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")
    _commit_all(repo, "foreign tree")
    return repo


def _tree_under_test(tmp_path: Path) -> Path:
    """The scratch tree the ratchet was pointed at. It never holds ``_FOREIGN_ONLY``."""
    repo = tmp_path / "scratch"
    repo.mkdir()
    _init_repo(repo)
    (repo / _SHARED).write_text("y = 2\n", encoding="utf-8")
    _commit_all(repo, "scratch snapshot")
    return repo


def _gitdir(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout.strip()


# --------------------------------------------------------------------------
# git_environment() itself
# --------------------------------------------------------------------------


def test_git_variables_are_removed(monkeypatch):
    """Every variable git uses to relocate the repository is dropped.

    Not just ``GIT_DIR``. ``GIT_WORK_TREE``, ``GIT_INDEX_FILE``,
    ``GIT_OBJECT_DIRECTORY`` and ``GIT_COMMON_DIR`` redirect the same lookups,
    and git exports more than one of them into a hook. Stripping the prefix
    closes the class rather than the one instance that was reported.
    """
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_CEILING_DIRECTORIES",
    ):
        monkeypatch.setenv(name, "/somewhere/else")

    env = count_ratchet.git_environment()

    assert [name for name in env if name.upper().startswith("GIT_")] == []


def test_non_git_variables_survive(monkeypatch):
    """The strip is narrow on purpose.

    ``PATH`` has to survive or git cannot be launched at all, and ``HOME`` has
    to survive because ``actions/checkout`` records ``safe.directory`` in the
    global config; dropping it invites "detected dubious ownership" on a
    runner. This is the documented divergence from
    ``merge_tree_materialization.isolated_git_environment``, which drops both.
    """
    monkeypatch.setenv("GIT_DIR", "/somewhere/else")
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("DIGIT_COUNT", "keep-me")

    env = count_ratchet.git_environment()

    assert env["HOME"] == "/home/tester"
    assert env["DIGIT_COUNT"] == "keep-me"
    assert "PATH" in env
    assert "GIT_DIR" not in env


def test_lowercase_git_prefix_is_removed(monkeypatch):
    """``name.upper()`` is load-bearing, and is what the canonical helper does.

    Windows folds environment names case-insensitively, so ``git_dir`` set
    there is the same variable git reads. Matching on the raw name would leave
    it in place on exactly the platform that created it.
    """
    monkeypatch.setenv("git_dir", "/somewhere/else")

    assert "git_dir" not in count_ratchet.git_environment()


def test_returns_a_copy_not_a_view(monkeypatch):
    """Mutating the result must not reach back into the process environment."""
    monkeypatch.setenv("GIT_DIR", "/somewhere/else")
    monkeypatch.setenv("RATCHET_PROBE", "original")

    env = count_ratchet.git_environment()
    env["RATCHET_PROBE"] = "mutated"

    assert os.environ["RATCHET_PROBE"] == "original"
    assert os.environ["GIT_DIR"] == "/somewhere/else"


def test_clean_environment_is_passed_through(monkeypatch):
    """With no ``GIT_*`` set, the result is the ambient environment unchanged.

    The positive control for the strip: it must not be quietly deleting things
    when there is nothing to fix.
    """
    for name in [n for n in os.environ if n.upper().startswith("GIT_")]:
        monkeypatch.delenv(name, raising=False)

    assert count_ratchet.git_environment() == dict(os.environ)


# --------------------------------------------------------------------------
# tracked_files(): the call site that blocked PR #4912
# --------------------------------------------------------------------------


@requires_git
def test_tracked_files_reads_the_named_root_without_git_dir(tmp_path, monkeypatch):
    """Positive: ordinary push, no ``GIT_DIR``, correct listing."""
    for name in [n for n in os.environ if n.upper().startswith("GIT_")]:
        monkeypatch.delenv(name, raising=False)
    scratch = _tree_under_test(tmp_path)

    assert count_ratchet.tracked_files(scratch, ["*.py"]) == [_SHARED]


@requires_git
def test_tracked_files_ignores_a_foreign_git_dir(tmp_path, monkeypatch):
    """Negative control: the reported bug, asserted directly.

    ``GIT_DIR`` names a repository that tracks ``_FOREIGN_ONLY``; the tree
    under test does not. Before the fix this returned the foreign path, which
    was then handed to ruff as ``<scratch>/scripts/validation/...`` and failed
    to open. The listing must be identical to the clean-environment listing.
    """
    scratch = _tree_under_test(tmp_path)
    foreign = _foreign_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", _gitdir(foreign))

    listed = count_ratchet.tracked_files(scratch, ["*.py", "scripts/**/*.py"])

    assert _FOREIGN_ONLY not in listed
    assert listed == [_SHARED]


@requires_git
def test_foreign_git_dir_would_win_without_isolation(tmp_path, monkeypatch):
    """The mechanism, pinned. Without this the test above proves nothing.

    If a future git release made ``-C`` outrank ``GIT_DIR``, the negative
    control would pass for a reason unrelated to the fix and would stop
    guarding it. This asserts the override is still real by running the same
    command with the ambient environment.
    """
    scratch = _tree_under_test(tmp_path)
    foreign = _foreign_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", _gitdir(foreign))

    proc = subprocess.run(
        ["git", "-C", str(scratch), "ls-files", "-z"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    leaked = [path for path in proc.stdout.split("\0") if path]

    assert _FOREIGN_ONLY in leaked, (
        "git no longer honours GIT_DIR over -C; the isolation tests above have "
        "stopped testing anything and need to be re-derived"
    )


@requires_git
def test_tracked_files_still_reports_failure_under_isolation(tmp_path, monkeypatch):
    """Edge: isolation must not convert a git failure into an empty listing.

    A directory that is not a repository has to stay None. Returning [] would
    read as "no files match" and score the tree as zero violations, which is a
    ratchet that passes by failing.
    """
    monkeypatch.setenv("GIT_DIR", _gitdir(_foreign_repo(tmp_path)))
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()

    assert count_ratchet.tracked_files(not_a_repo, ["*.py"]) is None


@requires_git
def test_tracked_files_returns_none_when_git_cannot_launch(tmp_path, monkeypatch):
    """Edge: the launch-failure contract survives the refactor to ``_git_run``."""

    def _explode(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(count_ratchet.subprocess, "run", _explode)

    assert count_ratchet.tracked_files(tmp_path, ["*.py"]) is None


# --------------------------------------------------------------------------
# The remaining git call sites
# --------------------------------------------------------------------------


@requires_git
def test_baseline_at_ref_ignores_a_foreign_git_dir(tmp_path, monkeypatch):
    """``git show <ref>:<path>`` resolves in the named root, not in ``GIT_DIR``.

    Both repositories record ``base.txt`` at HEAD with different values. The
    wrong one being readable at all is the defect; reading 7 instead of 3 is
    how it would surface, as a ceiling copied from an unrelated tree.
    """
    scratch = _tree_under_test(tmp_path)
    (scratch / "base.txt").write_text("3\n", encoding="utf-8")
    _commit_all(scratch, "scratch baseline 3")

    foreign = _foreign_repo(tmp_path)
    (foreign / "base.txt").write_text("7\n", encoding="utf-8")
    _commit_all(foreign, "foreign baseline 7")
    monkeypatch.setenv("GIT_DIR", _gitdir(foreign))

    assert count_ratchet.baseline_at_ref(scratch, "HEAD", scratch / "base.txt") == 3


@requires_git
def test_baseline_absent_at_ref_ignores_a_foreign_git_dir(tmp_path, monkeypatch):
    """The bootstrap probe must not read absence from the wrong repository.

    ``base.txt`` is absent in the tree under test and present in the foreign
    one. An unisolated probe reads the foreign tree, answers "recorded", and
    the first run of a new ratchet is compared against a ceiling that branch
    never had.
    """
    scratch = _tree_under_test(tmp_path)
    foreign = _foreign_repo(tmp_path)
    (foreign / "base.txt").write_text("7\n", encoding="utf-8")
    _commit_all(foreign, "foreign baseline 7")
    monkeypatch.setenv("GIT_DIR", _gitdir(foreign))

    assert count_ratchet.baseline_absent_at_ref(scratch, "HEAD", scratch / "base.txt") is True


@requires_git
def test_changed_files_ignores_a_foreign_git_dir(tmp_path, monkeypatch):
    """The diagnostic-ordering probe reads the named root too.

    This one only orders output, so a wrong answer does not block a push. It
    is isolated anyway: a diagnostic that promotes files from another
    repository is worse than no ordering, because it reads as a claim about
    the branch under test.
    """
    scratch = _tree_under_test(tmp_path)
    (scratch / "touched.py").write_text("z = 3\n", encoding="utf-8")
    _commit_all(scratch, "scratch touches a file")

    foreign = _foreign_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", _gitdir(foreign))

    changed = count_ratchet.changed_files(scratch, "HEAD~1")

    assert "touched.py" in changed
    assert _FOREIGN_ONLY not in changed


@requires_git
def test_ruff_ratchet_baseline_at_ref_ignores_a_foreign_git_dir(tmp_path, monkeypatch):
    """The duplicate in ``ruff_count_ratchet`` carries the same defect.

    It shadows nothing and is called by its own test rather than by ``main``,
    but it is the same ``git show`` against a caller-supplied root. Leaving a
    known-identical failure in the same ratchet family is how the next
    diagnosis starts over.
    """
    scratch = _tree_under_test(tmp_path)
    (scratch / "base.txt").write_text("3\n", encoding="utf-8")
    _commit_all(scratch, "scratch baseline 3")

    foreign = _foreign_repo(tmp_path)
    (foreign / "base.txt").write_text("7\n", encoding="utf-8")
    _commit_all(foreign, "foreign baseline 7")
    monkeypatch.setenv("GIT_DIR", _gitdir(foreign))

    assert ruff_ratchet.baseline_at_ref(scratch, "HEAD", scratch / "base.txt") == 3


# --------------------------------------------------------------------------
# Regression guard
# --------------------------------------------------------------------------


def _git_run_calls_without_env(source: Path) -> list[int]:
    """Line numbers of ``subprocess.run`` calls launching git without ``env=``."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "run"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue
        if not _launches_git(node):
            continue
        if not any(kw.arg == "env" for kw in node.keywords):
            offenders.append(node.lineno)
    return offenders


def _launches_git(call: ast.Call) -> bool:
    """True when the first positional argument is a list literal starting ``"git"``."""
    if not call.args:
        return False
    argv = call.args[0]
    if not isinstance(argv, ast.List) or not argv.elts:
        return False
    head = argv.elts[0]
    return isinstance(head, ast.Constant) and head.value == "git"


@pytest.mark.parametrize(
    "module",
    [count_ratchet, ruff_ratchet],
    ids=["count_ratchet", "ruff_count_ratchet"],
)
def test_every_git_subprocess_passes_an_env(module):
    """No git call site may fall back to the ambient environment.

    The fix is one keyword argument per call site, so the way it regresses is
    a new call site that omits it, added by someone who never saw issue #4914.
    Reading the source is the only check that covers a site no test exercises.
    """
    source = Path(module.__file__)

    assert _git_run_calls_without_env(source) == []


def test_guard_detects_a_missing_env(tmp_path):
    """The guard's own negative control.

    An AST walk that matched nothing would report a clean module forever. This
    feeds it a call site that is exactly what the guard exists to catch.
    """
    offender = tmp_path / "offender.py"
    offender.write_text(
        "import subprocess\n"
        'subprocess.run(["git", "-C", "x", "ls-files"], check=False)\n'
        'subprocess.run(["git", "status"], check=False, env={})\n'
        'subprocess.run(["ruff", "check"], check=False)\n',
        encoding="utf-8",
    )

    assert _git_run_calls_without_env(offender) == [2]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
