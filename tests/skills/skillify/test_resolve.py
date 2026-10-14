"""Destination resolution: explicit > env var > cwd. Unresolved writes nothing."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
import skillify


def make_repo(base: Path, *roots: str) -> Path:
    repo = base / "unrelated repo"
    (repo / ".git").mkdir(parents=True)
    for root in roots:
        (repo / root).mkdir(parents=True)
    return repo


def resolve(explicit=None, env_vars=(), cwd=Path("."), environ=None):
    return skillify.resolve_destination(explicit, list(env_vars), cwd, environ or {})


def test_explicit_wins_over_env_and_cwd(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills")
    target = tmp_path / "chosen"
    target.mkdir()
    payload, code = resolve(str(target), ["SKILLS"], repo, {"SKILLS": str(tmp_path)})
    assert code == skillify.EXIT_OK
    assert payload["source"] == "explicit"
    assert payload["path"] == str(target)
    assert payload["exists"] is True


def test_explicit_path_with_spaces_is_kept_whole(tmp_path):
    target = tmp_path / "my skills dir"
    payload, code = resolve(str(target), cwd=tmp_path)
    assert code == skillify.EXIT_OK
    assert payload["path"] == str(target)
    assert payload["exists"] is False


def test_blank_explicit_falls_through(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills")
    payload, _ = resolve("   ", cwd=repo)
    assert payload["source"] == "cwd"


def test_env_var_used_when_no_explicit(tmp_path):
    target = tmp_path / "env-root"
    payload, code = resolve(None, ["MISSING", "SKILLS"], tmp_path, {"SKILLS": str(target)})
    assert code == skillify.EXIT_OK
    assert payload["source"] == "env"
    assert payload["env_var"] == "SKILLS"
    assert payload["path"] == str(target)


def test_env_vars_checked_in_given_order(tmp_path):
    environ = {"FIRST": str(tmp_path / "a"), "SECOND": str(tmp_path / "b")}
    payload, _ = resolve(None, ["FIRST", "SECOND"], tmp_path, environ)
    assert payload["env_var"] == "FIRST"


def test_empty_env_var_is_skipped(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills")
    payload, _ = resolve(None, ["SKILLS"], repo, {"SKILLS": "  "})
    assert payload["source"] == "cwd"


def test_env_wins_over_cwd(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills")
    payload, _ = resolve(None, ["SKILLS"], repo, {"SKILLS": str(tmp_path / "elsewhere")})
    assert payload["source"] == "env"


def test_cwd_detects_claude_skills_from_unrelated_directory(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills")
    payload, code = resolve(cwd=repo)
    assert code == skillify.EXIT_OK
    assert payload["source"] == "cwd"
    assert payload["harness"] == "claude-code"
    assert Path(payload["path"]) == (repo / ".claude" / "skills").resolve()


def test_cwd_detects_github_skills(tmp_path):
    repo = make_repo(tmp_path, ".github/skills")
    payload, _ = resolve(cwd=repo)
    assert payload["harness"] == "copilot-cli"


def test_cwd_detection_walks_up_to_repository_root(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills")
    nested = repo / "src" / "deep"
    nested.mkdir(parents=True)
    payload, _ = resolve(cwd=nested)
    assert payload["source"] == "cwd"


def test_cwd_detection_accepts_worktree_git_file(tmp_path):
    repo = tmp_path / "wt"
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    payload, _ = resolve(cwd=repo)
    assert payload["source"] == "cwd"


def test_nearest_root_wins_over_outer_root(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills")
    inner = repo / "pkg"
    (inner / ".github" / "skills").mkdir(parents=True)
    payload, _ = resolve(cwd=inner)
    assert payload["harness"] == "copilot-cli"


def test_both_roots_in_one_directory_is_ambiguous(tmp_path):
    repo = make_repo(tmp_path, ".claude/skills", ".github/skills")
    payload, code = resolve(cwd=repo)
    assert code == skillify.EXIT_CONFIG
    assert payload["status"] == "needs_clarification"
    assert len(payload["candidates"]) == 2
    assert payload["writes"] == "none"


def test_no_root_found_asks_and_writes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    before = sorted(p for p in repo.rglob("*"))
    payload, code = resolve(None, ["SKILLS"], repo, {})
    assert code == skillify.EXIT_CONFIG
    assert payload["status"] == "needs_clarification"
    assert payload["candidates"] == []
    assert payload["env_vars_checked"] == ["SKILLS"]
    assert "question" in payload
    assert sorted(p for p in repo.rglob("*")) == before


def test_no_git_boundary_searches_only_cwd(tmp_path):
    outer = tmp_path / "outer"
    (outer / ".claude" / "skills").mkdir(parents=True)
    inner = outer / "scratch"
    inner.mkdir()
    payload, code = resolve(cwd=inner)
    assert code == skillify.EXIT_CONFIG
    assert payload["status"] == "needs_clarification"


def test_no_git_boundary_finds_root_in_cwd(tmp_path):
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    payload, _ = resolve(cwd=tmp_path)
    assert payload["source"] == "cwd"


def test_resolved_path_that_is_a_file_is_invalid(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    payload, code = resolve(str(target), cwd=tmp_path)
    assert code == skillify.EXIT_CONFIG
    assert payload["status"] == "invalid"
    assert payload["writes"] == "none"


def test_home_expansion_in_explicit_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    payload, _ = resolve("~/skills", cwd=tmp_path)
    assert Path(payload["path"]) == tmp_path / "skills"


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        (PureWindowsPath(r"C:\Users\dev\proj\.claude\skills"), "claude-code"),
        (PureWindowsPath(r"C:\Users\dev\proj\.CLAUDE\skills"), "custom"),
        (PureWindowsPath(r"C:\Users\dev\proj\.claude\Skills"), "custom"),
        (PureWindowsPath(r"D:\work tree\.github\skills"), "copilot-cli"),
        (PureWindowsPath(r"C:\custom\skills"), "custom"),
        (PurePosixPath("/home/dev/proj/.claude/skills"), "claude-code"),
        (PurePosixPath("/home/dev/proj/.github/skills"), "copilot-cli"),
        (PurePosixPath("/skills"), "custom"),
        (PurePosixPath("/"), "custom"),
    ],
)
def test_root_kind_is_independent_of_path_flavour(path, kind):
    assert skillify.skills_root_kind(path) == kind


def test_relative_explicit_resolves_against_cwd_and_is_absolute(tmp_path):
    payload, code = resolve("sub/../skills here", cwd=tmp_path)
    assert code == skillify.EXIT_OK
    assert Path(payload["path"]).is_absolute()
    assert Path(payload["path"]) == tmp_path.resolve() / "skills here"


def test_relative_env_var_resolves_against_cwd(tmp_path):
    payload, _ = resolve(None, ["S"], tmp_path, {"S": "rel/skills"})
    assert Path(payload["path"]) == tmp_path.resolve() / "rel" / "skills"
    assert payload["confirm_before_create"] is True


def test_existing_root_needs_no_creation_confirmation(tmp_path):
    payload, _ = resolve(str(tmp_path), cwd=tmp_path)
    assert payload["confirm_before_create"] is False


def test_relative_explicit_via_cli_cwd(tmp_path, capsys):
    (tmp_path / "skills").mkdir()
    code = skillify.main(["resolve", "--explicit", "skills", "--cwd", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert (out["exists"], Path(out["path"])) == (True, tmp_path.resolve() / "skills")
