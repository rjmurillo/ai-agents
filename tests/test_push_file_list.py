"""`push_file_list` builds the pre-push file list from git's ref lines (issue #6884).

Most tests build a real repository with a bare ``origin``, so the git commands
run as they do in a hook. A fake git runner covers the failures a real
repository cannot easily produce.

Coverage:

- positive: update, new branch against the default branch, several refs,
  ``HEAD:main`` level with the upstream, renames, deleted files.
- negative: malformed stdin lines, bad object ids, missing objects and git
  failures stop the push with :class:`PushFileListError`.
- edge: zero shas (delete-only uses the placeholder), 64-digit ids, spaces and
  leading dashes in paths, commas and long lists fall back to ``--all-files``,
  no tracking ref, unrelated history, a URL remote, empty stdin.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.validation import push_file_list as pfl

ZERO = "0" * 40


class Repo:
    """A clone with a bare ``origin``, driven with plain git."""

    def __init__(self, tmp_path: Path) -> None:
        origin = tmp_path / "origin.git"
        self.origin = origin
        self.path = tmp_path / "work"
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
        self.env = env
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", str(origin)],
            check=True,
            env=env,
            cwd=tmp_path,
        )
        self.path.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "T")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", str(self.origin))

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.path, env=self.env, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def runner(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments], cwd=self.path, env=self.env, capture_output=True, check=False
        )

    def commit(self, files: dict[str, str | None], message: str = "c") -> str:
        for name, content in files.items():
            target = self.path / name
            if content is None:
                self.git("rm", "-q", "--", name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            self.git("add", "--", name)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def files(self, lines: Sequence[str], remote: str | None = "origin") -> list[str]:
        updates = pfl.parse_ref_lines("".join(f"{line}\n" for line in lines).encode())
        return pfl.pushed_files(updates, remote, self.runner)

    def args(self, lines: Sequence[str], remote: str | None = "origin", **kw: int) -> list[str]:
        stdin = "".join(f"{line}\n" for line in lines).encode()
        return pfl.lefthook_file_args(stdin, remote, self.runner, **kw)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """A repository whose ``main`` holds two files and is pushed and fetched."""
    fixture = Repo(tmp_path)
    fixture.commit({"README.md": "r\n", "app.py": "a\n"}, "seed")
    fixture.git("push", "-q", "origin", "main")
    fixture.git("fetch", "-q", "origin")
    fixture.git("checkout", "-q", "-b", "feature/work")
    return fixture


def test_an_update_lists_the_files_between_the_remote_and_local_sha(repo: Repo) -> None:
    first = repo.commit({"src/a.py": "1\n"})
    second = repo.commit({"src/b.py": "2\n"})

    assert repo.files([f"refs/heads/feature/work {second} refs/heads/feature/work {first}"]) == [
        "src/b.py"
    ]


def test_a_new_branch_lists_the_files_since_the_default_branch(repo: Repo) -> None:
    head = repo.commit({"docs/n.md": "n\n"})

    assert repo.files([f"refs/heads/feature/work {head} refs/heads/feature/work {ZERO}"]) == [
        "docs/n.md"
    ]


def test_a_new_branch_prefers_the_remote_head_over_main(repo: Repo) -> None:
    repo.git("checkout", "-q", "-b", "trunk", "main")
    trunk = repo.commit({"trunk.txt": "t\n"})
    repo.git("push", "-q", "origin", "trunk")
    repo.git("fetch", "-q", "origin")
    repo.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    head = repo.commit({"more.txt": "m\n"})

    # Measured against main this would also list trunk.txt.
    assert trunk != head
    assert repo.files([f"refs/heads/x {head} refs/heads/x {ZERO}"]) == ["more.txt"]


def test_several_refs_give_the_sorted_union(repo: Repo) -> None:
    one = repo.commit({"z.txt": "z\n"})
    repo.git("checkout", "-q", "-b", "feature/two", "main")
    two = repo.commit({"a.txt": "a\n", "z.txt": "z\n"})

    assert repo.files(
        [
            f"refs/heads/feature/work {one} refs/heads/feature/work {ZERO}",
            f"refs/heads/feature/two {two} refs/heads/feature/two {ZERO}",
        ]
    ) == ["a.txt", "z.txt"]


def test_head_to_main_level_with_its_upstream_still_lists_the_branch_files(repo: Repo) -> None:
    head = repo.commit({"src/mod.py": "v\n"})
    repo.git("push", "-q", "-u", "origin", "HEAD")
    main = repo.git("rev-parse", "origin/main")

    # `git diff HEAD @{push}` is empty here, which is what made Lefthook skip.
    assert repo.git("diff", "--name-only", "HEAD", "@{push}") == ""
    assert repo.args([f"HEAD {head} refs/heads/main {main}"]) == ["--file=src/mod.py"]


def test_a_rename_lists_both_paths(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD")
    repo.git("mv", "app.py", "main.py")
    repo.git("commit", "-q", "-m", "mv")
    head = repo.git("rev-parse", "HEAD")

    assert repo.files([f"refs/heads/x {head} refs/heads/x {base}"]) == ["app.py", "main.py"]


def test_a_deleted_file_is_listed(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"app.py": None})

    assert repo.files([f"refs/heads/x {head} refs/heads/x {base}"]) == ["app.py"]


def test_paths_with_spaces_and_leading_dashes_stay_whole(repo: Repo) -> None:
    head = repo.commit({"docs/my notes.md": "n\n", "-dash.txt": "d\n", "café.txt": "c\n"})

    assert repo.args([f"refs/heads/x {head} refs/heads/x {ZERO}"]) == [
        "--file=-dash.txt",
        "--file=café.txt",
        "--file=docs/my notes.md",
    ]


def test_a_comma_in_a_path_falls_back_to_all_files(repo: Repo) -> None:
    head = repo.commit({"a,b.py": "x\n"})

    assert repo.args([f"refs/heads/x {head} refs/heads/x {ZERO}"]) == [pfl.ALL_FILES]


def test_a_list_over_the_budget_falls_back_to_all_files(repo: Repo) -> None:
    head = repo.commit({"one.txt": "1\n", "two.txt": "2\n"})
    line = f"refs/heads/x {head} refs/heads/x {ZERO}"

    assert repo.args([line], budget=10) == [pfl.ALL_FILES]
    assert repo.args([line], budget=10_000) == ["--file=one.txt", "--file=two.txt"]


def test_a_delete_only_push_names_the_placeholder(repo: Repo) -> None:
    assert repo.args([f"(delete) {ZERO} refs/heads/main {repo.git('rev-parse', 'main')}"]) == [
        f"--file={pfl.PLACEHOLDER}"
    ]


def test_a_delete_beside_an_update_needs_no_placeholder(repo: Repo) -> None:
    head = repo.commit({"x.txt": "x\n"})
    main = repo.git("rev-parse", "main")

    assert repo.args(
        [f"(delete) {ZERO} refs/heads/old {main}", f"refs/heads/x {head} refs/heads/x {ZERO}"]
    ) == ["--file=x.txt"]


def test_a_push_that_changes_no_file_names_the_placeholder(repo: Repo) -> None:
    main = repo.git("rev-parse", "main")

    assert repo.args([f"refs/heads/copy {main} refs/heads/copy {ZERO}"]) == [
        f"--file={pfl.PLACEHOLDER}"
    ]


def test_a_remote_sha_this_clone_lacks_uses_the_default_branch(repo: Repo) -> None:
    head = repo.commit({"new.txt": "n\n"})
    missing = "1" * 40

    assert repo.files([f"refs/heads/x {head} refs/heads/x {missing}"]) == ["new.txt"]


def test_no_tracking_ref_lists_every_file_in_the_commit(repo: Repo) -> None:
    head = repo.commit({"new.txt": "n\n"})
    repo.git("update-ref", "-d", "refs/remotes/origin/main")

    assert repo.files([f"refs/heads/x {head} refs/heads/x {ZERO}"]) == [
        "README.md",
        "app.py",
        "new.txt",
    ]


@pytest.mark.parametrize("remote", ["https://h/r.git", "-x", "a b", None, ""])
def test_a_remote_without_tracking_refs_lists_every_file(repo: Repo, remote: str | None) -> None:
    head = repo.commit({"new.txt": "n\n"})

    assert repo.files([f"refs/heads/x {head} refs/heads/x {ZERO}"], remote) == [
        "README.md",
        "app.py",
        "new.txt",
    ]


def test_unrelated_history_lists_every_file_in_the_commit(repo: Repo) -> None:
    repo.git("checkout", "-q", "--orphan", "lonely")
    repo.git("rm", "-q", "-rf", "--", ".")
    head = repo.commit({"only.txt": "o\n"})

    assert repo.files([f"refs/heads/lonely {head} refs/heads/lonely {ZERO}"]) == ["only.txt"]


def test_empty_stdin_is_no_push_and_adds_no_arguments(repo: Repo) -> None:
    assert repo.args([]) == []
    assert pfl.lefthook_file_args(b"\n\n", "origin", repo.runner) == []


def test_a_missing_local_object_stops_the_push(repo: Repo) -> None:
    with pytest.raises(pfl.PushFileListError, match="not in this clone"):
        repo.files([f"refs/heads/x {'2' * 40} refs/heads/x {repo.git('rev-parse', 'HEAD')}"])


def test_a_tag_on_a_tree_lists_every_file_in_the_tree(repo: Repo) -> None:
    tree = repo.git("rev-parse", "HEAD^{tree}")
    repo.git("tag", "odd", tree)

    assert repo.files([f"refs/tags/odd {tree} refs/tags/odd {ZERO}"]) == ["README.md", "app.py"]


def test_an_annotated_tag_on_a_tree_lists_every_file_in_the_tree(repo: Repo) -> None:
    repo.git("tag", "-a", "-m", "t", "odd", repo.git("rev-parse", "HEAD^{tree}"))
    tag = repo.git("rev-parse", "odd")

    assert repo.files([f"refs/tags/odd {tag} refs/tags/odd {ZERO}"]) == ["README.md", "app.py"]


def test_a_tag_on_a_blob_names_the_placeholder(repo: Repo) -> None:
    blob = repo.git("rev-parse", "HEAD:README.md")
    repo.git("tag", "odd", blob)

    assert repo.args([f"refs/tags/odd {blob} refs/tags/odd {ZERO}"]) == [
        f"--file={pfl.PLACEHOLDER}"
    ]


def test_an_annotated_tag_lists_the_files_of_its_commit(repo: Repo) -> None:
    repo.commit({"tagged.txt": "t\n"})
    repo.git("tag", "-a", "-m", "v", "v1")
    tag = repo.git("rev-parse", "v1")

    assert repo.files([f"refs/tags/v1 {tag} refs/tags/v1 {ZERO}"]) == ["tagged.txt"]


def test_an_update_from_a_remote_tree_compares_against_the_default_branch(repo: Repo) -> None:
    tree = repo.git("rev-parse", "HEAD^{tree}")
    head = repo.commit({"new.txt": "n\n"})

    assert repo.files([f"refs/tags/t {head} refs/tags/t {tree}"]) == ["new.txt"]


def test_a_local_ref_with_spaces_or_odd_bytes_still_parses() -> None:
    """Git writes the refspec source as typed, so field 1 may hold spaces."""
    sha = "c" * 40
    data = f"main@{{1 day ago}} {sha} refs/heads/x {ZERO}\n".encode() + (
        b"refs/heads/\xff " + sha.encode() + b" refs/heads/y " + ZERO.encode() + b"\n"
    )

    updates = pfl.parse_ref_lines(data)

    assert [update.local_ref for update in updates] == ["main@{1 day ago}", "refs/heads/\ufffd"]
    assert all(update.local_sha == sha for update in updates)


def test_parse_accepts_64_digit_ids_and_skips_blank_lines() -> None:
    sha = "b" * 64
    updates = pfl.parse_ref_lines(f"\nrefs/heads/x {sha} refs/heads/x {'0' * 64}\n".encode())

    assert updates == [pfl.RefUpdate("refs/heads/x", sha, "refs/heads/x", "0" * 64)]
    assert updates[0].is_new
    assert not updates[0].is_delete


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"refs/heads/x abc refs/heads/x 000\n", "invalid object id"),
        (f"refs/heads/x {'A' * 40} refs/heads/x {ZERO}\n".encode(), "invalid object id"),
        (f"refs/heads/x {'a' * 39} refs/heads/x {ZERO}\n".encode(), "invalid object id"),
        (b"only three fields\n", "3 fields"),
        (f"a {'a' * 40} b {ZERO} extra\n".encode(), "invalid object id"),
        (b"\xff\xfe\n", "1 fields"),
        (f"refs/heads/x {'a' * 40} refs/heads/x \xe9{'0' * 39}\n".encode(), "invalid object id"),
    ],
)
def test_a_malformed_line_stops_the_push(data: bytes, message: str) -> None:
    with pytest.raises(pfl.PushFileListError, match=message):
        pfl.lefthook_file_args(data, "origin", _fake_git({}))


def _fake_git(
    results: dict[str, tuple[int, bytes]],
) -> pfl.GitRunner:
    def run(arguments: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        code, out = results.get(arguments[0], (0, b""))
        return subprocess.CompletedProcess(list(arguments), code, stdout=out, stderr=b"boom")

    return run


def test_a_merge_base_error_stops_the_push() -> None:
    git = _fake_git(
        {"cat-file": (1, b""), "rev-parse": (0, b"c" * 40 + b"\n"), "merge-base": (128, b"")}
    )
    line = f"refs/heads/x {'a' * 40} refs/heads/x {ZERO}\n".encode()

    with pytest.raises(pfl.PushFileListError, match="merge-base"):
        pfl.lefthook_file_args(line, "origin", git)


def test_a_diff_error_stops_the_push() -> None:
    git = _fake_git({"cat-file": (0, b""), "diff-tree": (128, b"")})
    line = f"refs/heads/x {'a' * 40} refs/heads/x {'b' * 40}\n".encode()

    with pytest.raises(pfl.PushFileListError, match="diff-tree"):
        pfl.lefthook_file_args(line, "origin", git)


@pytest.mark.parametrize(
    "error", [FileNotFoundError("git"), subprocess.TimeoutExpired(["git"], 120)]
)
def test_git_that_cannot_start_or_finish_stops_the_push(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(pfl.subprocess, "run", broken)
    with pytest.raises(pfl.PushFileListError, match="cannot run git"):
        pfl.run_git(["status"])


@pytest.mark.parametrize(
    ("arguments", "chosen"),
    [
        (["--file=a.py", "origin"], True),
        (["--file", "a.py"], True),
        (["--all-files"], True),
        (["--files-from-stdin"], True),
        (["--force"], True),
        (["--job", "x", "origin", "url"], False),
        (["--filex", "origin"], False),
        ([], False),
    ],
)
def test_caller_chose_files(arguments: list[str], chosen: bool) -> None:
    assert pfl.caller_chose_files(arguments) is chosen


def test_arg_budget_is_a_quarter_of_arg_max_less_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pfl.os, "sysconf", lambda _name: 4_000_000, raising=False)
    monkeypatch.setattr(pfl.os, "environ", {"AB": "cd"})
    # "AB=cd" plus its NUL is 6 bytes, plus an 8-byte pointer.
    assert pfl.arg_budget() == 1_000_000 - 14


def test_a_huge_environment_leaves_no_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pfl.os, "sysconf", lambda _name: 400, raising=False)
    monkeypatch.setattr(pfl.os, "environ", {"BIG": "x" * 500})
    assert pfl.arg_budget() == 0


@pytest.mark.parametrize("error", [AttributeError, ValueError, OSError])
def test_arg_budget_without_sysconf_uses_the_windows_limit(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    def missing(_name: str) -> int:
        raise error("no")

    monkeypatch.setattr(pfl.os, "sysconf", missing, raising=False)
    assert pfl.arg_budget() == 30_000


def test_arg_budget_with_an_unknown_limit_uses_the_windows_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pfl.os, "sysconf", lambda _name: -1, raising=False)
    assert pfl.arg_budget() == 30_000
