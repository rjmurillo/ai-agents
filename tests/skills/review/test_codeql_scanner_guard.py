"""Tests for codeql_scanner_guard.py: diff base, guarded paths, language map."""

from __future__ import annotations

import codeql_scanner_guard as guard
import pytest
from codeql_repo_fixture import git, make_repo, write


class TestIsGuardedPath:
    @pytest.mark.parametrize(
        "path",
        [
            ".codeql/scripts/invoke_codeql_scan.py",
            ".codeql/config.yml",
            ".github/codeql/codeql-config.yml",
            ".github/codeql/queries/x.ql",
            ".github/workflows/codeql-analysis.yml",
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
            ".github/workflows/ci.yml",
            ".github/workflows/codeql-analysis.yml.bak",
            ".github/actionsx/a.yml",
            "src/claude/skills/codeql-scan/SKILL.md",
            "src/claude/skills/codeql-scan/references/a.md",
            "src/claude/skills/other/scripts/codeql.py",
            "docs/codeql-scan/scripts/a.md",
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

    def test_workflow_yaml_maps_to_actions(self):
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
