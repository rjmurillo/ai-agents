"""Tests for scripts/validation/effective_context_sources.py (issue #4880).

Split out of ``test_effective_context.py`` (1196 lines, over the taste-lints
500-line ERROR threshold) alongside the module split that motivated it. This
file covers what ``effective_context_sources`` holds: ``Repo`` (live and
``--rev`` reading), target-to-directory resolution, the directory chain, and
glob matching. Claude- and Copilot-specific resolution live in their own
split test files; CLI, ratchet, and observe tests stay in
``test_effective_context.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context_resolvers as ecr
import scripts.validation.effective_context_sources as ecs
from tests.validation._effective_context_helpers import _commit_all, _init_git_repo, _write

# --------------------------------------------------------------------------
# REQ-2: --rev reads every file and import at that commit with `git show`.
# --------------------------------------------------------------------------


class TestReq2RevReading:
    """REQ-2, T3: `--rev` reads files and imports through `git show`."""

    def test_rev_reads_content_from_the_named_commit_not_the_working_tree(
        self, tmp_path: Path
    ) -> None:
        """REQ-2: resolving at an old rev sees the old bytes, not current ones."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "@AGENTS.md\n")
        _write(tmp_path, "AGENTS.md", "old\n")
        old_sha = _commit_all(tmp_path, "v1")

        _write(tmp_path, "AGENTS.md", "new, much longer content than before\n")
        _commit_all(tmp_path, "v2")

        at_old = ecr.resolve_effective_context(tmp_path, "target.py", "claude", rev=old_sha)
        at_head = ecr.resolve_effective_context(tmp_path, "target.py", "claude")

        old_agents = next(f for f in at_old.files if f.path == "AGENTS.md")
        head_agents = next(f for f in at_head.files if f.path == "AGENTS.md")
        assert old_agents.size_bytes == len(b"old\n")
        assert head_agents.size_bytes == len(b"new, much longer content than before\n")

    def test_rev_reads_a_nested_directory_listing_via_git_ls_tree(self, tmp_path: Path) -> None:
        """REQ-2: scoped rules are listed at the rev, not the working tree."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(
            tmp_path,
            ".claude/rules/only-at-old-rev.md",
            '---\npaths: ["**"]\n---\nold rule\n',
        )
        old_sha = _commit_all(tmp_path, "v1")
        (tmp_path / ".claude" / "rules" / "only-at-old-rev.md").unlink()
        _write(tmp_path, ".claude/rules/new-rule.md", '---\npaths: ["**"]\n---\nnew rule\n')
        _commit_all(tmp_path, "v2")

        at_old = ecr.resolve_effective_context(tmp_path, "target.py", "claude", rev=old_sha)
        at_head = ecr.resolve_effective_context(tmp_path, "target.py", "claude")

        old_scoped = {f.path for f in at_old.files if f.layer == "scoped"}
        head_scoped = {f.path for f in at_head.files if f.layer == "scoped"}
        assert old_scoped == {".claude/rules/only-at-old-rev.md"}
        assert head_scoped == {".claude/rules/new-rule.md"}

    def test_invalid_rev_raises(self, tmp_path: Path) -> None:
        """REQ-2 / CLI: an unresolvable --rev is a config error (exit 2)."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _commit_all(tmp_path, "v1")
        with pytest.raises(ecr.InvalidRevError):
            ecr.resolve_effective_context(tmp_path, "target.py", "claude", rev="not-a-real-rev")


class TestGlobMatches:
    def test_universal_glob_matches_anything(self) -> None:
        assert ecr.glob_matches({"**"}, "any/path/at/all.py") is True

    def test_extension_glob_matches_same_extension_only(self) -> None:
        patterns = {"**/*.py"}
        assert ecr.glob_matches(patterns, "a/b/target.py") is True
        assert ecr.glob_matches(patterns, "a/b/target.cs") is False

    def test_empty_pattern_set_matches_nothing(self) -> None:
        assert ecr.glob_matches(set(), "a/b/target.py") is False


class TestDirectoryChain:
    def test_root_target_has_no_chain(self) -> None:
        assert ecr.directory_chain("") == []

    def test_single_level(self) -> None:
        assert ecr.directory_chain("scripts") == ["scripts"]

    def test_multi_level_is_cumulative(self) -> None:
        assert ecr.directory_chain(".github/workflows") == [".github", ".github/workflows"]


class TestResolveBaseDirectory:
    def test_file_target_resolves_to_parent(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "f.py").write_text("x\n", encoding="utf-8")
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "a/b/f.py") == "a/b"

    def test_directory_target_resolves_to_itself(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "a/b") == "a/b"

    def test_nonexistent_file_target_still_resolves_to_its_parent(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "a/does-not-exist.py") == "a"

    def test_root_target_resolves_to_empty_string(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "target.py") == ""

    def test_root_dot_target_resolves_to_empty_string_too(self, tmp_path: Path) -> None:
        """`resolve_base_directory` folds a "." target to the empty root string."""
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, ".") == ""

    def test_escaping_target_raises(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        with pytest.raises(ecr.TargetOutsideRepoError):
            ecr.resolve_base_directory(repo, "../../etc/passwd")


class TestRepoDirectAccessors:
    def test_read_bytes_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.read_bytes("nope.md") is None

    def test_list_dir_returns_empty_for_missing_directory(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.list_dir("nope") == []

    def test_is_dir_true_for_repo_root(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.is_dir("") is True

    def test_rev_is_valid_true_when_rev_is_none(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.rev_is_valid() is True

    def test_list_dir_at_a_rev_excludes_a_subdirectory_entry(self, tmp_path: Path) -> None:
        """`git ls-tree` at a rev must keep only blobs, matching `is_file()` in the live tree.

        A bare `--name-only` listing cannot distinguish a file from a
        subdirectory of the same listed name; without a type filter, a
        subdirectory under a scanned rules/instructions directory would be
        misread as a rule file.
        """
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/real.md", '---\npaths: ["**"]\n---\nbody\n')
        _write(tmp_path, ".claude/rules/nested/inner.md", '---\npaths: ["**"]\n---\nbody\n')
        sha = _commit_all(tmp_path, "v1")

        live = ecs.Repo(tmp_path, None).list_dir(".claude/rules")
        at_rev = ecs.Repo(tmp_path, sha).list_dir(".claude/rules")

        assert live == [".claude/rules/real.md"]
        assert at_rev == [".claude/rules/real.md"]

    def test_read_bytes_at_a_rev_treats_a_directory_as_absent(self, tmp_path: Path) -> None:
        """REQ-2: a path naming a tree at the rev reads as absent, as in the live tree.

        `git show <rev>:<dir>` exits 0 with a tree listing, so without a type
        check an `@dir` import would count that listing as file bytes.
        """
        _init_git_repo(tmp_path)
        _write(tmp_path, "docs/inner.md", "body\n")
        sha = _commit_all(tmp_path, "v1")

        assert ecs.Repo(tmp_path, None).read_bytes("docs") is None
        assert ecs.Repo(tmp_path, sha).read_bytes("docs") is None

    def test_rev_is_valid_refuses_an_option_shaped_rev(self, tmp_path: Path) -> None:
        """REQ-4: a `--rev` that starts with `-` never reaches git (CWE-88)."""
        repo = ecr.Repo(tmp_path, "--all")
        with mock.patch.object(ecs.subprocess, "run") as run:
            assert repo.rev_is_valid() is False
        run.assert_not_called()

    def test_ls_tree_failure_raises_instead_of_an_empty_listing(self, tmp_path: Path) -> None:
        """REQ-2: a failed `git ls-tree` raises; an empty list would undercount rules."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _commit_all(tmp_path, "v1")
        repo = ecr.Repo(tmp_path, "not-a-real-rev")
        with pytest.raises(ecs.GitUnavailableError, match="ls-tree"):
            repo.list_dir(".claude/rules")

    def test_ls_tree_of_a_missing_directory_is_empty(self, tmp_path: Path) -> None:
        """REQ-2: a directory absent at the rev lists as empty, not as a failure."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        sha = _commit_all(tmp_path, "v1")
        assert ecr.Repo(tmp_path, sha).list_dir(".claude/rules") == []


# --------------------------------------------------------------------------
# Coordinator finding (post-rebase review): a `--rev` `git show` failure read
# as "file absent" undercounted an inventory silently, and a
# `subprocess.TimeoutExpired` on any of this class's `git` calls escaped as
# an uncaught traceback instead of the ADR-035 exit-code-3 path every other
# `git` failure in this package already takes. `read_bytes` now probes
# existence with `git ls-tree <rev> -- <path>` first and requires a `blob`
# entry, so "absent at that rev" stays distinguishable from "present but
# unreadable" and a directory never reads as file bytes; a
# non-zero `git show` after that probe confirmed existence is a real git
# error, not absence. A non-zero exit from the existence probe itself is
# also a real git error now (an earlier `git cat-file -t` version treated
# any such exit as absence, undercounting the same way an unguarded `git
# show` failure once did); only empty `ls-tree` stdout means absent.
# `_ls_tree` and `rev_is_valid` share the same
# uncaught-timeout shape (subprocess.run to `git`, no `except
# TimeoutExpired`), so they get the same timeout-to-GitUnavailableError fix
# in the same diff; their existing non-zero-exit contract (`[]` / `False`)
# is untouched, since neither conflates absence with failure the way
# `read_bytes` did.
# --------------------------------------------------------------------------


def _fake_run_by_argv(responses: dict[str, object]) -> object:
    """Return a `subprocess.run` stand-in keyed by the git subcommand (argv[1]).

    ``responses[subcommand]`` is either a
    :class:`~tests.validation._effective_context_helpers.FakeCompletedProcess`
    or an exception instance to raise, so one fake can drive an existence
    probe's ``ls-tree`` call and a content ``show`` call differently in the
    same test.
    """

    def _run(argv: list[str], **_kwargs: object) -> object:
        response = responses[argv[1]]
        if isinstance(response, BaseException):
            raise response
        return response

    return _run


class TestReq2GitFailureHandling:
    """Post-rebase finding: distinguish absent from failed, never let a timeout escape."""

    def test_read_bytes_returns_none_for_a_path_absent_at_the_rev(self, tmp_path: Path) -> None:
        """Real git, no mocking: a path introduced after ``old_sha`` is absent there."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        old_sha = _commit_all(tmp_path, "v1")
        _write(tmp_path, "new-file.md", "new\n")
        _commit_all(tmp_path, "v2")

        repo = ecs.Repo(tmp_path, old_sha)
        assert repo.read_bytes("new-file.md") is None

    def test_read_bytes_returns_none_when_ls_tree_reports_absent(self, tmp_path: Path) -> None:
        """`git ls-tree`'s empty stdout is absence; `git show` must not even run."""
        from tests.validation._effective_context_helpers import FakeCompletedProcess

        run = mock.Mock(
            side_effect=_fake_run_by_argv({"ls-tree": FakeCompletedProcess(0, stdout="")})
        )
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            assert repo.read_bytes("gone.md") is None
        assert run.call_count == 1, "git show must not run once ls-tree said absent"

    def test_read_bytes_raises_when_show_fails_after_ls_tree_confirms_existence(
        self, tmp_path: Path
    ) -> None:
        """`git ls-tree` lists a blob, but `git show` still fails: a real git error."""
        from tests.validation._effective_context_helpers import FakeCompletedProcess

        run = mock.Mock(
            side_effect=_fake_run_by_argv(
                {
                    "ls-tree": FakeCompletedProcess(0, stdout="100644 blob abc123\tpresent.md\n"),
                    "show": FakeCompletedProcess(128, stderr="fatal: loose object corrupt"),
                }
            )
        )
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError, match="corrupt"):
                repo.read_bytes("present.md")

    def test_read_bytes_raises_on_ls_tree_timeout(self, tmp_path: Path) -> None:
        run = mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo.read_bytes("present.md")

    def test_read_bytes_raises_on_show_timeout(self, tmp_path: Path) -> None:
        from tests.validation._effective_context_helpers import FakeCompletedProcess

        run = mock.Mock(
            side_effect=_fake_run_by_argv(
                {
                    "ls-tree": FakeCompletedProcess(0, stdout="100644 blob abc123\tpresent.md\n"),
                    "show": subprocess.TimeoutExpired(cmd="git", timeout=30),
                }
            )
        )
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo.read_bytes("present.md")

    def test_exists_at_rev_true_for_a_blob_entry(self, tmp_path: Path) -> None:
        """Direct coverage: an `ls-tree` line whose type field is `blob`."""
        from tests.validation._effective_context_helpers import FakeCompletedProcess

        run = mock.Mock(return_value=FakeCompletedProcess(0, stdout="100644 blob abc\tf.md\n"))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            assert repo._exists_at_rev("deadbeef", "f.md") is True

    def test_exists_at_rev_false_for_a_tree_entry(self, tmp_path: Path) -> None:
        """Direct coverage: an `ls-tree` line whose type field is `tree` (a directory)."""
        from tests.validation._effective_context_helpers import FakeCompletedProcess

        run = mock.Mock(return_value=FakeCompletedProcess(0, stdout="040000 tree abc\tdir\n"))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            assert repo._exists_at_rev("deadbeef", "dir") is False

    def test_exists_at_rev_false_for_empty_output(self, tmp_path: Path) -> None:
        """Direct coverage: `ls-tree` exits 0 with nothing listed -- absent."""
        from tests.validation._effective_context_helpers import FakeCompletedProcess

        run = mock.Mock(return_value=FakeCompletedProcess(0, stdout=""))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            assert repo._exists_at_rev("deadbeef", "nope.md") is False

    def test_exists_at_rev_raises_on_nonzero_exit(self, tmp_path: Path) -> None:
        """Direct coverage: a non-zero `ls-tree` exit is a real git error, not absence."""
        from tests.validation._effective_context_helpers import FakeCompletedProcess

        run = mock.Mock(
            return_value=FakeCompletedProcess(128, stderr="fatal: not a valid object name")
        )
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError, match="not a valid object name"):
                repo._exists_at_rev("deadbeef", "whatever.md")

    def test_exists_at_rev_raises_on_timeout(self, tmp_path: Path) -> None:
        run = mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo._exists_at_rev("deadbeef", "whatever.md")

    def test_ls_tree_raises_on_timeout_instead_of_an_uncaught_traceback(
        self, tmp_path: Path
    ) -> None:
        run = mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo.list_dir(".claude/rules")

    def test_rev_is_valid_raises_on_timeout_instead_of_an_uncaught_traceback(
        self, tmp_path: Path
    ) -> None:
        run = mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo.rev_is_valid()

    # Coordinator finding: OSError (a missing `git` binary, `FileNotFoundError`
    # among other subclasses) escaped uncaught from every one of this class's
    # four `subprocess.run` calls, so the CLI could exit 1 (Python's own
    # default for an unhandled exception) instead of ADR-035 exit code 3. All
    # four now catch `(OSError, subprocess.TimeoutExpired)`, mirroring the
    # timeout tests above one call site at a time.

    def test_read_bytes_raises_when_git_binary_is_absent(self, tmp_path: Path) -> None:
        run = mock.Mock(side_effect=FileNotFoundError("no such file or directory: 'git'"))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo.read_bytes("present.md")

    def test_exists_at_rev_raises_when_git_binary_is_absent(self, tmp_path: Path) -> None:
        run = mock.Mock(side_effect=FileNotFoundError("no such file or directory: 'git'"))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo._exists_at_rev("deadbeef", "whatever.md")

    def test_ls_tree_raises_when_git_binary_is_absent(self, tmp_path: Path) -> None:
        run = mock.Mock(side_effect=FileNotFoundError("no such file or directory: 'git'"))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo.list_dir(".claude/rules")

    def test_rev_is_valid_raises_when_git_binary_is_absent(self, tmp_path: Path) -> None:
        run = mock.Mock(side_effect=FileNotFoundError("no such file or directory: 'git'"))
        with mock.patch.object(ecs.subprocess, "run", run):
            repo = ecs.Repo(tmp_path, "deadbeef")
            with pytest.raises(ecs.GitUnavailableError):
                repo.rev_is_valid()

    def test_git_unavailable_error_is_importable_from_the_resolvers_re_export(self) -> None:
        """`ecr.GitUnavailableError` (existing public import path) is the same type."""
        assert ecr.GitUnavailableError is ecs.GitUnavailableError

    def test_decode_strips_and_decodes_bytes_stderr(self) -> None:
        """A real (unmocked) `git show` failure's `stderr` is `bytes`, not `str`."""
        assert ecs._decode(b"  fatal: boom  \n") == "fatal: boom"

    def test_decode_strips_str_stderr(self) -> None:
        """A test double may hand back `str` directly; both shapes decode the same."""
        assert ecs._decode("  fatal: boom  \n") == "fatal: boom"
