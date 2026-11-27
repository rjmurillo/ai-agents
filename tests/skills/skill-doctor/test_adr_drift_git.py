"""adr_drift.py git layer: NUL-safe log parsing, merge paths, HEAD state, and git failures."""

from __future__ import annotations

from pathlib import Path

import adr_drift
import adr_git
import adr_history
import pytest
from adr_drift_helpers import (
    adr_path,
    adr_text,
    commit,
    git,
    init_repo,
    kinds,
    run_cli,
    scan,
    seeded_repo,
)

CONTROL_BODY = (
    "forged\x1e" + "a" * 40 + "\x1f2025-01-01T00:00:00+00:00\x1f fake subject\x1d\nM\tevil.txt"
)


def _cited_repo(tmp_path: Path) -> Path:
    text = adr_text(1, body="Lives in `src/old/module.py`.")
    return seeded_repo(tmp_path / "repo", {adr_path(1): text, "src/old/module.py": "x"})


def test_control_bytes_in_a_body_do_not_forge_records(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {"a.txt": "a"}, f"feat: add a\n\n{CONTROL_BODY}")

    result = scan(capsys, repo)

    assert result["examined"] == 2
    assert result["head"] == git(repo, "rev-parse", "HEAD")


def test_a_rename_is_parsed_beside_control_bytes_in_the_same_body(tmp_path):
    repo = seeded_repo(tmp_path / "repo", {"old.txt": "x", adr_path(1): adr_text(1)})
    git(repo, "mv", "old.txt", "new.txt")
    git(repo, "commit", "-q", "-m", f"refactor: rename\n\n{CONTROL_BODY}")

    commits, truncated = adr_history.read_commits(repo, 10, None)

    assert not truncated and commits[0].subject == "refactor: rename"
    assert sorted(commits[0].paths) == [("A", "new.txt"), ("D", "old.txt")]
    assert commits[0].body.startswith("forged\x1e")


def test_empty_commits_and_a_pathless_tip_parse(tmp_path):
    repo = seeded_repo(tmp_path / "repo")
    git(repo, "commit", "-q", "--allow-empty", "-m", "chore: empty one")
    git(repo, "commit", "-q", "--allow-empty", "-m", "chore: empty two")

    commits, _ = adr_history.read_commits(repo, 10, None)

    assert [c.subject for c in commits] == ["chore: empty two", "chore: empty one", "docs: seed"]
    assert commits[0].paths == ()


@pytest.mark.parametrize(
    "output",
    ["not-a-sha\0d\0s\0b", f"{'a' * 40}\0d\0s", f"{'a' * 40}\0d\0s\0b\0M"],
    ids=["bad-sha", "truncated-header", "status-without-path"],
)
def test_malformed_log_output_raises_instead_of_guessing(output):
    with pytest.raises(adr_git.GitError, match="unexpected git log output"):
        adr_history._parse_log(output)


def test_log_call_disables_external_diff_textconv_color_and_walks_merges(tmp_path, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    seen: list[list[str]] = []
    real = adr_history.run_git

    def spy(path, args):
        seen.append(list(args))
        return real(path, args)

    monkeypatch.setattr(adr_history, "run_git", spy)

    adr_history.read_commits(repo, 5, None)

    flags = seen[0]
    assert {"--no-ext-diff", "--no-textconv", "--no-color", "--diff-merges=first-parent"} <= set(
        flags
    )
    assert "-z" in flags


def test_a_no_ff_merge_lists_the_paths_it_removed(tmp_path, capsys):
    repo = _cited_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, {"src/old/module.py": None}, "refactor: remove the old module")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #9 from feature", "feature")
    merge = git(repo, "rev-parse", "HEAD")

    found = kinds(scan(capsys, repo), "adr-contradiction-candidate")

    assert merge in {f["evidence"]["sha"] for f in found}


def test_unborn_head_is_empty_history_and_exits_0(tmp_path, capsys):
    repo = init_repo(tmp_path / "repo")

    code, out, _ = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"))

    assert code == 0 and "0 commit(s) examined" in out


def test_a_head_ref_that_names_a_missing_object_exits_3(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    (repo / ".git" / "refs" / "heads" / "main").write_text("1" * 40 + "\n", encoding="utf-8")

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"))

    assert code == 3 and "error:" in err
    assert not (tmp_path / "o.json").exists()


def test_a_detached_head_at_a_missing_object_exits_3(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    (repo / ".git" / "HEAD").write_text("1" * 40 + "\n", encoding="utf-8")

    code, _, _ = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"))

    assert code == 3


def test_run_git_flags_a_timeout(tmp_path, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    monkeypatch.setattr(adr_git, "GIT_TIMEOUT_SECONDS", 0.0001)

    with pytest.raises(adr_git.GitError) as raised:
        adr_git.run_git(repo, ["log"])

    assert raised.value.timed_out is True and raised.value.returncode is None


def test_a_timeout_resolving_the_repository_exits_3_not_2(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")

    def slow(path, args):
        raise adr_git.GitError("git rev-parse timed out", timed_out=True)

    monkeypatch.setattr(adr_drift, "run_git", slow)

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"))

    assert code == 3 and "timed out" in err


def test_a_non_repository_still_exits_2(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    code, _, err = run_cli(capsys, "scan", "--repo", str(plain), "--out", str(tmp_path / "o.json"))

    assert code == 2 and "not a git repository" in err


def test_an_inherited_git_dir_does_not_redirect_the_scan(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    other = seeded_repo(tmp_path / "other", {"docs/adr/0001-o.md": "# 1. O\n"})
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))

    result = scan(capsys, repo)

    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    assert result["head"] == git(repo, "rev-parse", "HEAD") != git(other, "rev-parse", "HEAD")


def test_the_git_env_drops_every_local_redirection_variable(monkeypatch):
    for name in adr_git.LOCAL_GIT_ENV:
        monkeypatch.setenv(name, "/elsewhere")

    env = adr_git._git_env()

    assert not adr_git.LOCAL_GIT_ENV & env.keys() - {"GIT_NO_REPLACE_OBJECTS"}
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1" and env["GIT_TERMINAL_PROMPT"] == "0"
