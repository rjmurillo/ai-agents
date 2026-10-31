"""Worktree selection in pr-autofix must not trust the PR-author-chosen branch name (#6506).

Both selection blocks in ``templates/skills/pr-autofix.SKILL.md.tmpl`` sit between
``pr-worktree-select:begin`` and ``pr-worktree-select:end`` markers. These tests
pull each block out of the template and run it under bash against real git
repositories, so the shipped text is what is exercised.

- pos: ref, head SHA, and origin all match
- neg: same ref but another origin, or a head that lacks the live SHA
- edge: ssh and ``.git`` URL spellings, case, missing inputs fail closed, and
  the cleanup block demands an exact head (ahead of the merged head is kept)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = REPO_ROOT / "templates" / "skills" / "pr-autofix.SKILL.md.tmpl"
BASH = shutil.which("bash")
BRANCH = "fix/some-branch"
REPO = "owner/repo"

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required")


def _blocks() -> list[str]:
    text = TEMPLATE.read_text(encoding="utf-8")
    found = re.findall(
        r"^[ \t]*# pr-worktree-select:begin\n(.*?)^[ \t]*# pr-worktree-select:end\n",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    return [textwrap.dedent(block) for block in found]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, object]:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "a.txt").write_text("a")
    _git(main, "add", ".")
    _git(main, "commit", "-q", "-m", "base")
    _git(main, "remote", "add", "origin", f"https://github.com/{REPO}.git")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", "-b", BRANCH, str(wt))
    return {"main": main, "wt": wt, "head": _git(wt, "rev-parse", "HEAD"), "tmp": tmp_path}


def _run(block: str, cwd: Path, var: str, env: dict[str, str]) -> str:
    assignments = "\n".join(f"{k}={v!r}" for k, v in env.items())
    script = f'set -u\n{assignments}\n{var}=""\n{block}\nprintf \'%s\' "${var}"\n'
    result = subprocess.run(
        [BASH or "bash", "-c", script], cwd=cwd, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _dispatch(repos: dict[str, object], **overrides: str) -> str:
    env = {
        "PR_HEAD_REF": BRANCH,
        "PR_HEAD_REPO": REPO,
        "EXPECTED_HEAD_SHA": str(repos["head"]),
        **overrides,
    }
    return _run(_blocks()[0], Path(str(repos["main"])), "PR_WORKTREE", env)


def _cleanup(repos: dict[str, object], **overrides: str) -> str:
    env = {
        "PR_HEAD_REF": BRANCH,
        "PR_REPO": REPO,
        "MERGED_HEAD_SHA": str(repos["head"]),
        **overrides,
    }
    return _run(_blocks()[1], Path(str(repos["main"])), "WT", env)


def test_template_carries_both_selection_blocks() -> None:
    assert len(_blocks()) == 2


class TestDispatchSelection:
    def test_matching_ref_head_and_origin_selects_the_worktree(self, repos) -> None:
        assert _dispatch(repos) == str(repos["wt"])

    def test_worktree_ahead_of_the_live_head_is_selected(self, repos) -> None:
        wt = Path(str(repos["wt"]))
        (wt / "b.txt").write_text("unpushed")
        _git(wt, "add", ".")
        _git(wt, "commit", "-q", "-m", "unpushed")
        assert _dispatch(repos) == str(wt)

    def test_other_origin_with_the_same_branch_name_is_rejected(self, repos) -> None:
        _git(
            Path(str(repos["wt"])),
            "remote",
            "set-url",
            "origin",
            "https://github.com/evil/repo.git",
        )
        assert _dispatch(repos) == ""

    def test_origin_that_only_ends_like_the_repo_is_rejected(self, repos) -> None:
        _git(
            Path(str(repos["wt"])), "remote", "set-url", "origin", "https://github.com/xowner/repo"
        )
        assert _dispatch(repos) == ""

    def test_head_that_lacks_the_live_sha_is_rejected(self, repos) -> None:
        assert _dispatch(repos, EXPECTED_HEAD_SHA="1" * 40) == ""

    @pytest.mark.parametrize(
        "url",
        [
            "git@github.com:owner/repo.git",
            "git@github.com:owner/repo",
            "https://github.com/owner/repo/",
            "https://github.com/Owner/Repo.git",
        ],
    )
    def test_url_spellings_of_the_head_repo_match(self, repos, url: str) -> None:
        _git(Path(str(repos["wt"])), "remote", "set-url", "origin", url)
        assert _dispatch(repos) == str(repos["wt"])

    def test_head_repo_case_differences_match(self, repos) -> None:
        assert _dispatch(repos, PR_HEAD_REPO="Owner/Repo") == str(repos["wt"])

    @pytest.mark.parametrize("missing", ["PR_HEAD_REF", "PR_HEAD_REPO", "EXPECTED_HEAD_SHA"])
    def test_a_missing_input_fails_closed(self, repos, missing: str) -> None:
        assert _dispatch(repos, **{missing: ""}) == ""

    def test_a_branch_with_no_worktree_selects_nothing(self, repos) -> None:
        assert _dispatch(repos, PR_HEAD_REF="no/such-branch") == ""


class TestCleanupSelection:
    def test_matching_ref_exact_head_and_origin_selects_the_worktree(self, repos) -> None:
        assert _cleanup(repos) == str(repos["wt"])

    def test_head_ahead_of_the_merged_head_is_not_selected(self, repos) -> None:
        wt = Path(str(repos["wt"]))
        (wt / "b.txt").write_text("later")
        _git(wt, "add", ".")
        _git(wt, "commit", "-q", "-m", "later")
        assert _cleanup(repos) == ""

    def test_other_origin_is_not_selected(self, repos) -> None:
        _git(Path(str(repos["wt"])), "remote", "set-url", "origin", "git@github.com:evil/repo.git")
        assert _cleanup(repos) == ""

    def test_head_that_differs_from_the_merged_head_is_not_selected(self, repos) -> None:
        assert _cleanup(repos, MERGED_HEAD_SHA="2" * 40) == ""

    def test_ssh_spelling_matches(self, repos) -> None:
        _git(Path(str(repos["wt"])), "remote", "set-url", "origin", "git@github.com:owner/repo.git")
        assert _cleanup(repos) == str(repos["wt"])


def _guard() -> str:
    """The shipped keep guard: text after the select block up to the removal step."""
    text = TEMPLATE.read_text(encoding="utf-8")
    tail = text.rsplit("# pr-worktree-select:end\n", 1)[1]
    guard = tail.split("\nCOMMON=", 1)[0]
    assert "keep" in guard
    return guard


class TestCleanupKeepGuard:
    """No path-convention fallback: a same-named worktree with another origin is kept."""

    def _run_guard(self, repos: dict[str, object], **overrides: str) -> subprocess.CompletedProcess:
        env = {
            "PR_HEAD_REF": BRANCH,
            "PR_REPO": REPO,
            "MERGED_HEAD_SHA": str(repos["head"]),
            "HOME": str(Path(str(repos["tmp"])) / "home"),
            **overrides,
        }
        assignments = "\n".join(f"{k}={v!r}" for k, v in env.items())
        script = f'set -u\n{assignments}\nWT=""\n{_blocks()[1]}\n{_guard()}\necho "removable:$WT"\n'
        return subprocess.run(
            [BASH or "bash", "-c", script],
            cwd=Path(str(repos["main"])),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_matching_clean_worktree_passes_the_guard(self, repos) -> None:
        result = self._run_guard(repos)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"removable:{repos['wt']}"

    def test_other_origin_at_the_conventional_path_is_kept(self, repos) -> None:
        home = Path(str(repos["tmp"])) / "home"
        conventional = home / "worktrees" / "<repo>" / BRANCH
        conventional.parent.mkdir(parents=True)
        wt = Path(str(repos["wt"]))
        wt.rename(conventional)
        main = Path(str(repos["main"]))
        _git(main, "worktree", "repair", str(conventional))
        _git(conventional, "remote", "set-url", "origin", "https://github.com/evil/repo.git")

        result = self._run_guard(repos)

        assert result.returncode == 1
        assert "keep" in result.stdout
        assert "removable" not in result.stdout
        assert conventional.exists()

    def test_no_matching_worktree_is_kept_and_reported(self, repos) -> None:
        result = self._run_guard(repos, PR_HEAD_REF="no/such-branch")
        assert result.returncode == 1
        assert "keep <no matching worktree>" in result.stdout
