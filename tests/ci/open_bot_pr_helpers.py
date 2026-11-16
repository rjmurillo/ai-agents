"""Shared fakes for the open_bot_pr unit tests."""

from __future__ import annotations

import json
import subprocess

_BRANCH = "automation/reviewer-stats"
_ARGS = [
    "--path",
    "a.md",
    "--path",
    "b.json",
    "--user-name",
    "bot",
    "--user-email",
    "bot@example.com",
    "--message",
    "chore(stats): update reviewer signal statistics",
    "--message",
    "body",
    "--branch",
    _BRANCH,
    "--issue",
    "234",
]


_REAL_RUN = subprocess.run


def _done(argv: list[str], code: int, out: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, code, out)


class _World:
    """Fake git + gh keyed on argv. Constructor arguments pick the replies."""

    def __init__(
        self,
        *,
        dirty: bool = True,
        dirty_paths: set[str] | None = None,
        open_prs: list[dict[str, str | bool]] | None = None,
        pr_list_rc: int = 0,
        pr_list_out: str | None = None,
        remote_branch: bool = False,
        ls_remote_rc: int | None = None,
        failing: tuple[str, ...] | None = None,
        pr_create_rc: int = 0,
        merge_base_rc: int = 0,
        pr_create_out: str = "https://github.com/o/r/pull/9\n",
    ) -> None:
        self._dirty = dirty
        self._dirty_paths = dirty_paths
        self._pr_list_rc = pr_list_rc
        self._pr_list_out = pr_list_out if pr_list_out is not None else json.dumps(open_prs or [])
        self._ls_remote_rc = (
            ls_remote_rc if ls_remote_rc is not None else (0 if remote_branch else 2)
        )
        self._failing = failing
        self._pr_create_rc = pr_create_rc
        self._merge_base_rc = merge_base_rc
        self._pr_create_out = pr_create_out
        self._calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self._calls.append(list(argv))
        tool, verb = argv[0], argv[1]
        if self._failing and tuple(argv[: len(self._failing)]) == self._failing:
            return _done(argv, 1, "boom")
        if tool == "git":
            return self._git(argv, verb)
        if tool == "gh":
            return self._gh(argv)
        raise AssertionError(f"unexpected command: {argv}")

    def _git(self, argv: list[str], verb: str) -> subprocess.CompletedProcess[str]:
        idx = 1
        while idx < len(argv) and argv[idx] == "-c":
            idx += 2
        subverb = argv[idx] if idx < len(argv) else verb
        if subverb == "status":
            if self._dirty_paths is not None:
                asked = set(argv[argv.index("--") + 1 :])
                return _done(argv, 0, " M x\n" if asked & self._dirty_paths else "")
            return _done(argv, 0, " M a.md\n" if self._dirty else "")
        if subverb == "ls-remote":
            code = self._ls_remote_rc
            return _done(argv, code, "sha\trefs/heads/x\n" if code == 0 else "")
        if subverb == "merge-base":
            return _done(argv, self._merge_base_rc)
        if subverb in {"checkout", "add", "commit", "push"}:
            return _done(argv, 0)
        raise AssertionError(f"unexpected git command: {argv}")

    def _gh(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        match argv[1:3]:
            case ["pr", "list"]:
                return _done(argv, self._pr_list_rc, self._pr_list_out)
            case ["pr", "create"]:
                return _done(argv, self._pr_create_rc, self._pr_create_out)
        raise AssertionError(f"unexpected gh command: {argv}")

    def argvs(self) -> list[list[str]]:
        return list(self._calls)

    def issued(self, *prefix: str) -> list[list[str]]:
        return [c for c in self._calls if tuple(c[: len(prefix)]) == prefix]
