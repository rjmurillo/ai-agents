"""Tests for codeql_scanner_guard.py: diff base, guarded paths, language map."""

from __future__ import annotations

import os

import codeql_scanner_guard as guard
import pytest
from codeql_repo_fixture import commit_symlinks, git, make_repo, make_symlink, write


class TestIsGuardedPath:
    @pytest.mark.parametrize(
        "path",
        [
            ".codeql/scripts/invoke_codeql_scan.py",
            ".codeql/config.yml",
            ".github/codeql/codeql-config.yml",
            ".github/codeql/queries/x.ql",
            ".github/workflows/codeql-analysis.yml",
            ".github/workflows/codeql-analysis.yaml",
            ".github/workflows/pytest.yml",
            ".github/workflows/anything.yaml",
            ".github/workflows/nested/reusable.yml",
            ".github/workflows/README.md",
            ".github/workflows",
            ".github/workflows/",
            "./.github/Workflows/Pytest.YML",
            ".github/actions/setup/action.yml",
            "src/claude/skills/codeql-scan/scripts/invoke_codeql_scan.py",
            ".claude/skills/codeql-scan/scripts/CLAUDE.md",
            "skills/codeql-scan/scripts/invoke_codeql_scan.py",
            "src/hermes/project-toolkit-delivery/skills/codeql-scan/scripts/x.py",
            ".CodeQL/scripts/x.py",
            ".GitHub/Workflows/CodeQL-Analysis.yml",
            ".github\\codeql\\codeql-config.yml",
            "./.codeql/x.py",
            "docs/../.codeql/x.py",
            ".codeql",
            ".codeql/",
            "./.codeql",
            ".CodeQL",
            ".github/codeql",
            ".github/codeql/",
            ".github/actions",
            "./.github/Actions/",
            "src/claude/skills/codeql-scan/scripts",
            "src/claude/skills/codeql-scan/scripts/",
            "skills/codeql-scan/scripts",
        ],
    )
    def test_guards_every_path_the_rules_file_lists(self, path):
        assert guard.is_guarded_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/app.py",
            "README.md",
            ".codeqlx/a.py",
            "codeql/a.py",
            ".github/codeql-notes.md",
            ".github/workflowsx/a.yml",
            ".github/workflow/a.yml",
            "docs/.github/workflows-notes.md",
            ".github/actionsx/a.yml",
            "src/claude/skills/codeql-scan/SKILL.md",
            "src/claude/skills/codeql-scan/references/a.md",
            "src/claude/skills/other/scripts/codeql.py",
            "docs/codeql-scan/scripts/a.md",
            ".github/codeqlx",
            ".github/actionsx",
            "x/.codeql",
            "",
        ],
    )
    def test_does_not_guard_look_alikes(self, path):
        assert guard.is_guarded_path(path) is False

    def test_guarded_paths_keeps_input_order(self):
        paths = ["a.py", ".codeql/b", "c.py", ".github/actions/d"]
        assert guard.guarded_paths(paths) == [".codeql/b", ".github/actions/d"]

    def test_guarded_paths_is_empty_for_an_ordinary_diff(self):
        assert guard.guarded_paths(["src/a.py", "README.md"]) == []


class TestLanguagesFor:
    def test_python_files_map_to_python(self):
        assert guard.languages_for(["src/a.py", "b/c.py"]) == ["python"]

    def test_workflow_yaml_still_maps_to_actions(self):
        assert guard.languages_for([".github/workflows/ci.yml"]) == ["actions"]
        assert guard.languages_for([".github/workflows/ci.yaml"]) == ["actions"]

    def test_both_languages_come_back_sorted_and_once(self):
        paths = [".github/workflows/a.yml", "x.py", "y.py", ".github/workflows/b.yml"]
        assert guard.languages_for(paths) == ["actions", "python"]

    @pytest.mark.parametrize(
        "paths",
        [[], ["README.md"], ["docs/a.yml"], [".github/workflows/notes.md"], ["x.pyc", "y.ps1"]],
    )
    def test_everything_else_is_the_empty_set(self, paths):
        assert guard.languages_for(paths) == []

    def test_matching_ignores_case(self):
        assert guard.languages_for(["SRC/A.PY"]) == ["python"]


class TestDiff:
    def test_lists_committed_changes_since_the_merge_base(self, tmp_path):
        repo = make_repo(tmp_path)
        assert guard.changed_files(repo, "origin/main") == ["src/new.py"]

    def test_includes_staged_unstaged_and_untracked_changes(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "src/app.py", "print(2)\n")
        write(repo, "staged.py")
        git(repo, "add", "staged.py")
        write(repo, "untracked.py")
        assert guard.changed_files(repo, "origin/main") == [
            "src/app.py",
            "src/new.py",
            "staged.py",
            "untracked.py",
        ]

    def test_a_rename_out_of_a_guarded_dir_lists_both_sides(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "mv", ".codeql/scripts/old.py", "src/moved.py")
        git(repo, "commit", "-m", "move")
        files = guard.changed_files(repo, "origin/main")
        assert ".codeql/scripts/old.py" in files
        assert "src/moved.py" in files
        assert guard.guarded_paths(files) == [".codeql/scripts/old.py"]

    def test_a_deleted_guarded_file_is_listed(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "rm", "-q", ".codeql/scripts/old.py")
        assert ".codeql/scripts/old.py" in guard.changed_files(repo, "origin/main")

    def test_uses_the_merge_base_not_the_base_tip(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "main")
        write(repo, "base_only.py")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "advance main")
        git(repo, "push", "-q", "origin", "main")
        git(repo, "checkout", "-q", "feature")
        assert guard.changed_files(repo, "origin/main") == ["src/new.py"]

    def test_paths_with_spaces_and_unicode_survive(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "dir with space/é.py")
        assert "dir with space/é.py" in guard.changed_files(repo, "origin/main")

    def test_an_unknown_base_ref_raises(self, tmp_path):
        repo = make_repo(tmp_path)
        with pytest.raises(guard.GitError):
            guard.changed_files(repo, "origin/nope")


class TestRepoState:
    def test_clean_after_commit(self, tmp_path):
        assert guard.tree_is_clean(make_repo(tmp_path)) is True

    @pytest.mark.parametrize("kind", ["unstaged", "staged", "untracked"])
    def test_any_kind_of_change_makes_the_tree_dirty(self, tmp_path, kind):
        repo = make_repo(tmp_path)
        if kind == "unstaged":
            write(repo, "src/app.py", "changed\n")
        elif kind == "staged":
            write(repo, "s.py")
            git(repo, "add", "s.py")
        else:
            write(repo, "u.py")
        assert guard.tree_is_clean(repo) is False

    def test_head_sha_is_the_full_commit_id(self, tmp_path):
        repo = make_repo(tmp_path)
        assert guard.head_sha(repo) == git(repo, "rev-parse", "HEAD")
        assert len(guard.head_sha(repo)) == 40

    def test_repo_toplevel_from_a_subdirectory(self, tmp_path):
        repo = make_repo(tmp_path)
        assert guard.repo_toplevel(repo / "src") == repo.resolve()

    def test_repo_toplevel_outside_a_repo_raises(self, tmp_path):
        outside = tmp_path / "plain"
        outside.mkdir()
        with pytest.raises(guard.GitError):
            guard.repo_toplevel(outside)


class TestResolveBaseRef:
    def test_explicit_branch_name(self, tmp_path):
        assert guard.resolve_base_ref(make_repo(tmp_path), "main") == "origin/main"

    def test_explicit_remote_prefixed_name(self, tmp_path):
        assert guard.resolve_base_ref(make_repo(tmp_path), "origin/main") == "origin/main"

    def test_default_comes_from_origin_head(self, tmp_path):
        assert guard.resolve_base_ref(make_repo(tmp_path), None) == "origin/main"

    def test_unknown_branch_raises_instead_of_guessing(self, tmp_path):
        with pytest.raises(guard.GitError):
            guard.resolve_base_ref(make_repo(tmp_path), "nope")

    def test_missing_origin_head_raises_instead_of_falling_back_to_main(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "remote", "set-head", "origin", "-d")
        with pytest.raises(guard.GitError):
            guard.resolve_base_ref(repo, None)


def test_run_git_reports_a_missing_git_binary(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(guard.subprocess, "run", boom)
    with pytest.raises(guard.GitError, match="could not run"):
        guard.run_git(tmp_path, ["status"])


symlink = make_symlink


class TestSymlinks:
    def _guarded(self, repo):
        files = guard.changed_files(repo, "origin/main")
        return guard.guarded_paths(files, guard.changed_symlinks(repo, "origin/main"))

    def test_a_symlink_with_an_innocent_name_to_a_guarded_file_is_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "src/innocent.py", "../.codeql/scripts/old.py")
        commit_symlinks(repo, "link")
        assert self._guarded(repo) == ["src/innocent.py"]

    def test_a_symlink_to_a_guarded_directory_is_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "tools", ".codeql/scripts")
        commit_symlinks(repo, "link")
        assert self._guarded(repo) == ["tools"]

    def test_a_symlink_chain_is_followed_to_the_guarded_target(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "b.link", ".codeql/scripts/old.py")
        symlink(repo, "a.link", "b.link")
        commit_symlinks(repo, "chain")
        assert self._guarded(repo) == ["a.link", "b.link"]

    def test_an_untracked_symlink_to_a_guarded_path_is_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "sneaky", ".github/workflows/codeql-analysis.yml")
        write(repo, ".github/workflows/codeql-analysis.yml")
        git(repo, "add", ".github/workflows/codeql-analysis.yml")
        git(repo, "commit", "-m", "wf")
        git(repo, "reset", "-q", "--soft", "HEAD~1")
        git(repo, "reset", "-q")
        links = guard.changed_symlinks(repo, "origin/main")
        assert links["sneaky"] == ".github/workflows/codeql-analysis.yml"

    def test_a_symlink_to_an_ordinary_file_is_not_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "alias.py", "src/app.py")
        commit_symlinks(repo, "alias")
        assert self._guarded(repo) == []

    def test_a_symlink_to_a_look_alike_is_not_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, ".codeqlx/a.py")
        symlink(repo, "alias", ".codeqlx/a.py")
        commit_symlinks(repo, "alias")
        assert self._guarded(repo) == []

    def test_a_symlink_pointing_outside_the_repository_has_no_target(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "out", "../../elsewhere")
        commit_symlinks(repo, "out")
        assert guard.changed_symlinks(repo, "origin/main")["out"] is None
        assert self._guarded(repo) == []

    def test_a_dangling_symlink_to_an_ordinary_path_is_not_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "dangling", "nothing-here")
        commit_symlinks(repo, "dangling")
        assert guard.changed_symlinks(repo, "origin/main")["dangling"] == "nothing-here"
        assert self._guarded(repo) == []

    def test_a_dangling_symlink_into_a_guarded_directory_is_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "dangling", ".codeql/not-created-yet.py")
        commit_symlinks(repo, "dangling")
        assert self._guarded(repo) == ["dangling"]

    def test_a_symlink_named_inside_a_guarded_directory_is_guarded_by_name(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, ".github/actions/setup", "../../src")
        commit_symlinks(repo, "link")
        assert ".github/actions/setup" in self._guarded(repo)

    def test_a_guarded_directory_replaced_by_a_symlink_is_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "rm", "-r", "-q", ".codeql")
        symlink(repo, ".codeql", "src")
        commit_symlinks(repo, "swap")
        guarded = self._guarded(repo)
        assert ".codeql" in guarded
        assert ".codeql/scripts/old.py" in guarded

    def test_a_deleted_symlink_is_seen_by_its_old_mode(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "main")
        symlink(repo, "gone.link", ".codeql/scripts/old.py")
        commit_symlinks(repo, "add link on main")
        git(repo, "push", "-q", "origin", "main")
        git(repo, "checkout", "-q", "feature")
        git(repo, "merge", "-q", "main", "--no-edit")
        git(repo, "rm", "-q", "gone.link")
        git(repo, "commit", "-m", "remove link")
        git(repo, "reset", "-q", "--hard", "HEAD")
        links = guard.changed_symlinks(repo, "origin/main")
        assert links == {"gone.link": None}

    def test_a_symlink_replaced_by_a_regular_file_still_counts_as_a_symlink_change(self, tmp_path):
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "main")
        symlink(repo, "was.link", "src/app.py")
        commit_symlinks(repo, "link on main")
        git(repo, "push", "-q", "origin", "main")
        git(repo, "checkout", "-q", "feature")
        git(repo, "merge", "-q", "main", "--no-edit")
        (repo / "was.link").unlink()
        write(repo, "was.link", "regular\n")
        commit_symlinks(repo, "swap to file")
        assert "was.link" in guard.changed_symlinks(repo, "origin/main")

    def test_no_symlinks_gives_an_empty_map(self, tmp_path):
        assert guard.changed_symlinks(make_repo(tmp_path), "origin/main") == {}

    def test_guarded_paths_without_a_map_uses_names_only(self):
        assert guard.guarded_paths(["alias.py"], None) == []
        assert guard.guarded_paths(["alias.py"], {"alias.py": ".codeql/x.py"}) == ["alias.py"]
        assert guard.guarded_paths(["alias.py"], {"alias.py": None}) == []

    def test_the_guarded_list_lives_in_named_constants(self):
        assert ".codeql" in guard.GUARDED_DIRS
        assert ".github/workflows" in guard.GUARDED_DIRS
        assert guard.GUARDED_SCRIPT_DIR == "skills/codeql-scan/scripts"


BAD_NAME = os.fsdecode(b"bad-\xff-name.py")


def make_bad_name(repo, directory=""):
    path = repo / directory / BAD_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text("x\n", encoding="utf-8")
    except OSError:
        pytest.skip("file system rejects non-UTF-8 names")
    return f"{directory}/{BAD_NAME}".lstrip("/")


class TestUndecodablePaths:
    def test_git_output_is_read_as_bytes_not_text(self, tmp_path, monkeypatch):
        repo = make_repo(tmp_path)
        seen = {}
        real = guard.subprocess.run

        def spy(command, **kwargs):
            seen.update(kwargs)
            return real(command, **kwargs)  # subprocess-encoding: strict-ok

        monkeypatch.setattr(guard.subprocess, "run", spy)
        guard.run_git(repo, ["status"])
        assert "text" not in seen
        assert "encoding" not in seen
        assert "errors" not in seen
        assert "universal_newlines" not in seen

    def test_a_non_utf8_name_round_trips_as_a_surrogate_escape(self, tmp_path):
        repo = make_repo(tmp_path)
        name = make_bad_name(repo, "src")
        files = guard.changed_files(repo, "origin/main")
        assert name in files
        assert os.fsencode(name) in [os.fsencode(f) for f in files]

    def test_a_non_utf8_name_is_guarded_even_in_a_benign_directory(self, tmp_path):
        repo = make_repo(tmp_path)
        name = make_bad_name(repo, "docs")
        files = guard.changed_files(repo, "origin/main")
        assert guard.guarded_paths(files) == [name]

    def test_a_replacement_character_is_guarded(self):
        assert guard.is_guarded_path("docs/bad�.py") is True

    @pytest.mark.parametrize("char", ["\udc80", "\udcff", "\ud800", "\udfff", "�"])
    def test_every_surrogate_and_replacement_char_is_unreadable(self, char):
        assert guard.is_unreadable(f"a{char}b") is True
        assert guard.is_guarded_path(f"docs/a{char}b.py") is True

    @pytest.mark.parametrize("text", ["", "plain.py", "café/日本.py", "emoji-\U0001f600.py"])
    def test_valid_unicode_is_not_unreadable(self, text):
        assert guard.is_unreadable(text) is False

    def test_display_escapes_bad_bytes_for_output(self):
        shown = guard.display(BAD_NAME)
        assert "\\udcff" in shown
        assert shown.isascii() or "�" not in shown

    def test_decode_falls_back_to_the_replacement_char_where_the_codec_raises(self, monkeypatch):
        def raises(raw):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

        monkeypatch.setattr(guard.os, "fsdecode", raises)
        decoded = guard.decode_path(b"a\xffb")
        assert "�" in decoded
        assert guard.is_guarded_path(decoded) is True


class TestUnresolvableSymlinks:
    def test_a_target_that_cannot_be_read_is_guarded(self, tmp_path, monkeypatch):
        repo = make_repo(tmp_path)
        symlink(repo, "alias.py", "src/app.py")
        commit_symlinks(repo, "alias")

        def denied(path):
            raise PermissionError("no")

        monkeypatch.setattr(guard.os, "readlink", denied)
        links = guard.changed_symlinks(repo, "origin/main")
        assert links["alias.py"] == guard.UNRESOLVABLE
        files = guard.changed_files(repo, "origin/main")
        assert guard.guarded_paths(files, links) == ["alias.py"]

    def test_a_target_that_cannot_be_resolved_is_guarded(self, tmp_path, monkeypatch):
        repo = make_repo(tmp_path)
        symlink(repo, "alias.py", "src/app.py")
        commit_symlinks(repo, "alias")

        def broken(path, strict=False):
            raise OSError("loop")

        monkeypatch.setattr(guard.os.path, "realpath", broken)
        assert guard.changed_symlinks(repo, "origin/main")["alias.py"] == guard.UNRESOLVABLE

    def test_a_target_with_undecodable_bytes_is_guarded(self, tmp_path):
        repo = make_repo(tmp_path)
        try:
            symlink(repo, "alias", os.fsdecode(b"target-\xff"))
        except OSError:
            pytest.skip("file system rejects non-UTF-8 names")
        commit_symlinks(repo, "alias")
        links = guard.changed_symlinks(repo, "origin/main")
        assert links["alias"] == guard.UNRESOLVABLE
        assert guard.guarded_paths(["alias"], links) == ["alias"]

    def test_a_deleted_link_is_not_unresolvable_it_is_judged_by_name(self, tmp_path):
        repo = make_repo(tmp_path)
        assert guard._symlink_target(repo, "never-existed") is None

    def test_a_readable_link_inside_the_repo_is_not_guarded_by_the_new_rule(self, tmp_path):
        repo = make_repo(tmp_path)
        symlink(repo, "alias.py", "src/app.py")
        commit_symlinks(repo, "alias")
        links = guard.changed_symlinks(repo, "origin/main")
        assert links["alias.py"] == "src/app.py"
        assert guard.guarded_paths(["alias.py"], links) == []
