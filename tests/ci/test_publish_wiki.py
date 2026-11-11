"""Tests for scripts/ci/publish_wiki.py (issue #7202, epic #7201).

The publisher mirrors docs/training/ to the GitHub wiki, one way. Each exit code
in its docstring has a test that drives ``main``:

  0  published, no-op, dry run, SKIP (no credential), SKIP (wiki repo missing)
  1  source tree cannot be mirrored
  2  configuration error
  3  external git failure
  4  auth rejected (BLOCKED)

The wiki remote is a local bare repository addressed by a ``file:`` URL, so push,
deletion, and idempotence are real git operations. No test reaches the network.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts.ci import publish_wiki as pw
from tests.ci.publish_wiki_helpers import (
    BLOB,
    REPO_URL,
    TREE,
    file_url,
    git,
    make_repo,
    make_wiki,
    symlink_or_skip,
    write,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    return make_wiki(tmp_path)


def run_main(repo: Path, wiki: Path | str, *extra: str, env: dict[str, str] | None = None) -> int:
    url = wiki if isinstance(wiki, str) else file_url(wiki)
    argv = ["--repo-root", str(repo), "--repo", "acme/widgets", "--wiki-url", url, *extra]
    return pw.main(argv, environ=env or {})


def wiki_files(wiki: Path, tmp_path: Path) -> dict[str, str]:
    view = tmp_path / "view"
    if view.exists():
        subprocess.run(["git", "-C", str(view), "pull", "-q"], check=True)
    else:
        git(["clone", "-q", str(wiki), str(view)], tmp_path)
    return {p.name: p.read_text(encoding="utf-8") for p in view.iterdir() if p.is_file()}


def commit_count(wiki: Path) -> int:
    return int(git(["rev-list", "--count", "main"], wiki).strip())


# --- link rewriting ------------------------------------------------------------


def rewrite(repo: Path, text: str, published: dict[str, str] | None = None) -> str:
    pages = published or {
        "README.md": "Home",
        "first-page.md": "first-page",
        "second-page.md": "second-page",
    }
    return pw.rewrite_links(text, repo_root=repo, repo_url=REPO_URL, published=pages)


def test_page_link_loses_extension_and_keeps_anchor(repo: Path) -> None:
    assert rewrite(repo, "[a](./second-page.md#part)") == "[a](second-page#part)"


def test_plain_sibling_link_is_rewritten(repo: Path) -> None:
    assert rewrite(repo, "[a](first-page.md)") == "[a](first-page)"


def test_readme_link_becomes_home(repo: Path) -> None:
    assert rewrite(repo, "[idx](README.md)") == "[idx](Home)"


def test_repo_file_link_becomes_absolute_blob_url(repo: Path) -> None:
    assert rewrite(repo, "[s](../../scripts/tool.py)") == f"[s]({BLOB}/scripts/tool.py)"


def test_directory_link_becomes_tree_url(repo: Path) -> None:
    assert rewrite(repo, "[d](../assets/)") == f"[d]({TREE}/docs/assets)"


def test_unpublished_template_links_to_blob(repo: Path) -> None:
    assert rewrite(repo, "[t](_template.md)") == f"[t]({BLOB}/docs/training/_template.md)"


def test_image_link_gets_raw_suffix(repo: Path) -> None:
    write(repo, "docs/training/shot.png", "x")
    assert rewrite(repo, "![s](shot.png)") == f"![s]({BLOB}/docs/training/shot.png?raw=true)"


@pytest.mark.parametrize(
    "link", ["https://example.com/a.md", "#local", "mailto:a@b.c", "//cdn.example.com/x"]
)
def test_external_and_fragment_links_are_untouched(repo: Path, link: str) -> None:
    assert rewrite(repo, f"[x]({link})") == f"[x]({link})"


def test_fenced_and_inline_code_are_untouched(repo: Path) -> None:
    text = "```md\n[a](first-page.md)\n```\n\nUse `[a](first-page.md)` here.\n"
    assert rewrite(repo, text) == text


def test_reference_definition_is_rewritten(repo: Path) -> None:
    assert rewrite(repo, "[ref]: ./first-page.md") == "[ref]: first-page"


def test_link_with_title_keeps_title(repo: Path) -> None:
    assert rewrite(repo, '[a](first-page.md "tip")') == '[a](first-page "tip")'


def test_missing_link_target_raises(repo: Path) -> None:
    with pytest.raises(pw.SourceError, match="does not exist"):
        rewrite(repo, "[x](nope.md)")


def test_link_escaping_the_repo_raises(repo: Path) -> None:
    with pytest.raises(pw.SourceError, match="leaves the repository"):
        rewrite(repo, "[x](../../../outside.md)")


# --- classify, redact, env -----------------------------------------------------


@pytest.mark.parametrize(
    ("stderr", "kind"),
    [
        ("remote: Repository not found.\nfatal: repository 'x' not found", "missing"),
        ("fatal: '/x' does not appear to be a git repository", "missing"),
        ("fatal: repository '/x' does not exist", "missing"),
        ("remote: Permission to a/b.wiki.git denied to bot.\nfatal: 403", "auth"),
        ("fatal: Authentication failed for 'https://github.com/a/b.wiki.git/'", "auth"),
        ("fatal: unable to access: Could not resolve host", "external"),
    ],
)
def test_classify_failure(stderr: str, kind: str) -> None:
    assert pw.classify_failure(stderr) == kind


def test_redact_masks_the_token() -> None:
    assert pw.redact("denied for s3cret here", "s3cret") == "denied for *** here"
    assert pw.redact("plain", None) == "plain"


def test_git_env_puts_token_in_header_not_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/dev/null")
    env = pw.git_env("s3cret", "https://github.com/a/b.wiki.git")
    assert env["GIT_CONFIG_COUNT"] == "2", "appends after the inherited pair"
    assert env["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert env["GIT_CONFIG_KEY_1"] == "http.extraheader"
    assert "s3cret" not in env["GIT_CONFIG_VALUE_1"]  # base64 encoded


def test_git_env_adds_no_header_for_a_local_remote_or_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GIT_CONFIG_COUNT", raising=False)
    assert "GIT_CONFIG_COUNT" not in pw.git_env("s3cret", "file:///x")
    assert "GIT_CONFIG_COUNT" not in pw.git_env(None, "https://github.com/a/b.wiki.git")
    assert pw.git_env("s3cret", "https://github.com/a/b.wiki.git")["GIT_CONFIG_COUNT"] == "1"


# --- main: exit 0 --------------------------------------------------------------


def test_first_publish_writes_pages_and_deletes_stale(
    repo: Path, wiki: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_main(repo, wiki) == 0
    files = wiki_files(wiki, tmp_path)
    assert {"Home.md", "_Sidebar.md", "first-page.md", "second-page.md"} <= set(files)
    assert "Old-Page.md" not in files
    assert files["Home.md"].startswith("> **This wiki is a read-only mirror.**")
    assert "image.png" in files, "non-Markdown wiki files are left alone"
    assert "PUBLISHED:" in capsys.readouterr().out


def test_second_run_makes_no_commit(
    repo: Path, wiki: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_main(repo, wiki) == 0
    before = commit_count(wiki)
    capsys.readouterr()
    assert run_main(repo, wiki) == 0
    assert commit_count(wiki) == before
    assert "0 changes in 4 files" in capsys.readouterr().out


def test_edited_source_page_updates_the_wiki(repo: Path, wiki: Path, tmp_path: Path) -> None:
    run_main(repo, wiki)
    write(repo, "docs/training/second-page.md", "# Second, edited\n")
    assert run_main(repo, wiki) == 0
    assert "Second, edited" in wiki_files(wiki, tmp_path)["second-page.md"]


def test_removed_source_page_is_deleted_from_the_wiki(
    repo: Path, wiki: Path, tmp_path: Path
) -> None:
    run_main(repo, wiki)
    (repo / "docs/training/second-page.md").unlink()
    write(repo, "docs/training/first-page.md", "# First steps\n\nNo links left.\n")
    write(repo, "docs/training/README.md", "# T\n\n- [First](first-page.md)\n")
    assert run_main(repo, wiki) == 0
    files = wiki_files(wiki, tmp_path)
    assert "second-page.md" not in files
    assert "second-page" not in files["_Sidebar.md"]


def test_a_wiki_edit_is_overwritten(repo: Path, wiki: Path, tmp_path: Path) -> None:
    run_main(repo, wiki)
    edit = tmp_path / "edit"
    git(["clone", "-q", str(wiki), str(edit)], tmp_path)
    write(edit, "first-page.md", "hand edit\n")
    git(["commit", "-qam", "wiki edit"], edit)
    git(["push", "-q", "origin", "HEAD:main"], edit)
    assert run_main(repo, wiki) == 0
    assert "hand edit" not in wiki_files(wiki, tmp_path)["first-page.md"]


def test_dry_run_prints_diff_and_pushes_nothing(
    repo: Path, wiki: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = commit_count(wiki)
    assert run_main(repo, wiki, "--dry-run") == 0
    out = capsys.readouterr().out
    assert commit_count(wiki) == before
    assert "DRY RUN: " in out
    assert "A\tfirst-page.md" in out
    assert "D\tOld-Page.md" in out
    assert "M\tHome.md" in out


def test_dry_run_env_var_matches_flag(repo: Path, wiki: Path) -> None:
    before = commit_count(wiki)
    assert run_main(repo, wiki, env={"WIKI_DRY_RUN": "true"}) == 0
    assert commit_count(wiki) == before


def test_missing_wiki_repo_skips_with_exit_0(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_main(repo, file_url(tmp_path / "nope.git")) == 0
    out = capsys.readouterr().out
    assert out.startswith("Planned 4 wiki files")
    assert "SKIP: the wiki repo does not exist yet" in out
    assert "PUBLISHED" not in out


def test_dry_run_with_missing_wiki_plans_against_empty(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_main(repo, file_url(tmp_path / "nope.git"), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "NOTE: the wiki repo does not exist yet" in out
    assert "A\tHome.md" in out
    assert "DRY RUN: 4 changes in 4 files" in out


def test_no_credential_for_https_skips_and_names_the_secret(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_main(repo, "https://github.com/acme/widgets.wiki.git") == 0
    out = capsys.readouterr().out
    assert "SKIP: no credential" in out
    assert pw.PUSH_SETTING_NAME in out


def test_step_summary_file_receives_the_outcome(repo: Path, wiki: Path, tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    assert run_main(repo, wiki, env={"GITHUB_STEP_SUMMARY": str(summary)}) == 0
    assert "PUBLISHED: " in summary.read_text(encoding="utf-8")


# --- main: exit 1, 2, 3, 4 -----------------------------------------------------


def test_unmirrorable_source_exits_1_and_publishes_nothing(
    repo: Path, wiki: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, "docs/training/orphan.md", "# Orphan\n")
    before = commit_count(wiki)
    assert run_main(repo, wiki) == 1
    assert commit_count(wiki) == before
    assert "orphan.md" in capsys.readouterr().err


def test_broken_link_exits_1(repo: Path, wiki: Path) -> None:
    write(repo, "docs/training/first-page.md", "# F\n\n[x](gone.md)\n")
    assert run_main(repo, wiki) == 1


def test_missing_source_dir_exits_2(tmp_path: Path, wiki: Path) -> None:
    assert run_main(tmp_path, wiki) == 2


def test_missing_repo_exits_2(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert pw.main(["--repo-root", str(repo)], environ={}) == 2


def test_missing_git_exits_2(repo: Path, wiki: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert run_main(repo, wiki) == 2


def failed(stderr: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr=stderr)


def test_clone_failure_other_than_missing_or_auth_exits_3(
    repo: Path, wiki: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pw, "run_git", lambda *_a, **_k: failed("fatal: Could not resolve host"))
    assert run_main(repo, wiki) == 3


def test_clone_auth_rejection_exits_4(
    repo: Path, wiki: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pw, "run_git", lambda *_a, **_k: failed("fatal: Authentication failed"))
    assert run_main(repo, wiki) == 4
    assert "BLOCKED: auth" in capsys.readouterr().out


def _push_fails_with(monkeypatch: pytest.MonkeyPatch, stderr: str) -> None:
    real = pw.run_git

    def fake(
        args: Sequence[str], cwd: Path | None, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "push":
            return failed(stderr)
        return real(args, cwd, env)

    monkeypatch.setattr(pw, "run_git", fake)


def test_push_auth_rejection_exits_4_and_names_the_secret(
    repo: Path, wiki: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _push_fails_with(monkeypatch, "remote: Permission denied\nfatal: 403")
    assert run_main(repo, wiki) == 4
    assert pw.PUSH_SETTING_NAME in capsys.readouterr().out


def test_push_rejected_for_other_reason_exits_3(
    repo: Path, wiki: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _push_fails_with(monkeypatch, "! [rejected] HEAD -> main (non-fast-forward)")
    assert run_main(repo, wiki) == 3


def test_token_never_reaches_output(
    repo: Path, wiki: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _push_fails_with(monkeypatch, "remote: denied, token s3cret-token rejected\nfatal: 403")
    assert run_main(repo, wiki, env={"WIKI_TOKEN": "s3cret-token"}) == 4
    captured = capsys.readouterr()
    assert "s3cret-token" not in captured.out + captured.err


# --- hostile wiki ------------------------------------------------------------------


def seed_wiki_change(wiki: Path, tmp_path: Path, change: str) -> None:
    """Push one extra commit to the wiki. ``change`` names the hostile setup."""
    work = tmp_path / "hostile"
    git(["clone", "-q", str(wiki), str(work)], tmp_path)
    if change == "home-symlink":
        (work / "Home.md").unlink()
        symlink_or_skip(work / "Home.md", tmp_path / "victim.txt")
    if change == "gitignore":
        write(work, ".gitignore", "*.md\n")
        write(work, "Home.md", "hand made\n")
    git(["add", "-A", "-f"], work)
    if change == "home-symlink":
        stored = git(["ls-files", "-s", "Home.md"], work)
        assert stored.startswith("120000"), "git did not store Home.md as a symlink"
    git(["commit", "-qm", change], work)
    git(["push", "-q", "origin", "HEAD:main"], work)


def test_wiki_side_symlink_is_not_written_through(repo: Path, wiki: Path, tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me\n", encoding="utf-8")
    seed_wiki_change(wiki, tmp_path, "home-symlink")
    assert run_main(repo, wiki) == 0
    assert victim.read_text(encoding="utf-8") == "keep me\n"
    assert wiki_files(wiki, tmp_path)["Home.md"].startswith(
        "> **This wiki is a read-only mirror.**"
    )


def test_wiki_gitignore_cannot_hide_new_pages(repo: Path, wiki: Path, tmp_path: Path) -> None:
    seed_wiki_change(wiki, tmp_path, "gitignore")
    assert run_main(repo, wiki) == 0
    assert "first-page.md" in wiki_files(wiki, tmp_path)


def test_redact_masks_the_base64_credential_too() -> None:
    creds = base64.b64encode(b"x-access-token:s3cret").decode()
    assert pw.redact(f"header {creds} and s3cret", "s3cret") == "header *** and ***"


def test_symlinked_source_page_exits_1(repo: Path, wiki: Path, tmp_path: Path) -> None:
    symlink_or_skip(repo / "docs/training/leak.md", tmp_path / "victim.txt")
    before = commit_count(wiki)
    assert run_main(repo, wiki) == 1
    assert commit_count(wiki) == before


def test_remote_error_text_cannot_inject_a_workflow_command(
    repo: Path, wiki: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _push_fails_with(monkeypatch, "::add-mask::boom\nremote: Permission denied 403")
    assert run_main(repo, wiki) == 4
    captured = capsys.readouterr()
    assert "::add-mask::" not in captured.out + captured.err
    assert "add-mask" in captured.out


# --- repository discovery ----------------------------------------------------------


def with_origin(repo: Path, url: str) -> None:
    git(["init", "-q"], repo)
    git(["remote", "add", "origin", url], repo)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/acme/widgets.git",
        "https://github.com/acme/widgets",
        "git@github.com:acme/widgets.git",
        "ssh://git@github.com/acme/widgets.git",
    ],
)
def test_repo_is_derived_from_the_origin_remote(repo: Path, url: str) -> None:
    with_origin(repo, url)
    assert pw.origin_repo(repo) == "acme/widgets"


def test_documented_command_works_with_no_flags_and_no_env(
    repo: Path, wiki: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """README step 4: ``publish_wiki.py --dry-run`` from a checkout with a github.com origin."""
    with_origin(repo, "https://github.com/acme/widgets.git")
    argv = ["--repo-root", str(repo), "--wiki-url", file_url(wiki), "--dry-run"]
    assert pw.main(argv, environ={}) == 0
    assert "DRY RUN:" in capsys.readouterr().out


def test_origin_repo_is_empty_without_a_github_remote(repo: Path) -> None:
    with_origin(repo, "https://example.com/acme/widgets.git")
    assert pw.origin_repo(repo) == ""


def test_no_repo_flag_env_or_origin_exits_2_even_with_a_wiki_url(
    repo: Path, wiki: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--repo-root", str(repo), "--wiki-url", file_url(wiki), "--dry-run"]
    assert pw.main(argv, environ={}) == 2
    assert "add a github.com origin remote" in capsys.readouterr().err


def test_file_url_is_a_three_slash_uri_even_for_a_drive_style_path(tmp_path: Path) -> None:
    """``file://`` plus a raw Windows path names a host, not a drive."""
    url = file_url(tmp_path / "wiki.git")
    assert url.startswith("file:///")
    assert "\\" not in url
