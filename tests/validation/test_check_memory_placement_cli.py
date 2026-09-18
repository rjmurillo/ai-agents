"""CLI tests for check_memory_placement.py, the issue #5391 placement validator.

Every test drives ``main()`` against a real git repository under ``tmp_path``:
new-vs-existing via ``--base HEAD``, the exit-code contract (0 clean or
warning, 1 new-normative under ``--ci``, 2 usage or environment error), the
README, ``*-index.md`` and non-``.md`` skip, ``--path`` directory-walk mode,
``--json`` output, symlink handling, and base-ref validation.

Nothing here touches this repository's own ``.serena/memories/`` tree. The
pure ``classify()`` tests live in ``test_check_memory_placement.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.validation._placement_fixtures import (
    EVIDENCE_INCIDENT,
    INVALID_SUPPRESSION,
    NORMATIVE_HEADING,
    SUSPECT_TERM_DENSITY,
    VALID_SUPPRESSION,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_memory_placement as checker
import memory_placement_git as placement_git

# --- git test-repo fixture ---------------------------------------------------


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
    )
    return env


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_git_env(),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repository with one commit, holding an empty memories dir."""
    _run_git(tmp_path, "init", "-q")
    (tmp_path / ".serena" / "memories").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# repo\n")
    _run_git(tmp_path, "add", "README.md")
    _run_git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
    return tmp_path


def _write(repo: Path, relpath: str, content: str) -> Path:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")


def _commit_all(repo: Path, message: str) -> None:
    _run_git(repo, "add", "-A")
    _run_git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message)


# --- CLI tests ----------------------------------------------------------------


def test_new_normative_memory_fails_under_ci(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/new.md"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert ".serena/memories/new.md: normative:" in out


def test_existing_normative_file_warns_and_exits_zero(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/old.md", NORMATIVE_HEADING)
    _commit_all(repo, "add old normative memory")
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", "--base", "HEAD", ".serena/memories/old.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert ".serena/memories/old.md: normative:" in out


def test_evidence_memory_exits_zero_with_no_finding(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/incident.md", EVIDENCE_INCIDENT)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/incident.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "incident.md" not in out


def test_suspect_new_file_is_a_warning_only(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/suspect.md", SUSPECT_TERM_DENSITY)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/suspect.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert ".serena/memories/suspect.md: suspect:" in out


def test_valid_suppression_downgrades_and_reports_suppressed(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/kept.md", VALID_SUPPRESSION)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/kept.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert ".serena/memories/kept.md: suppressed:" in out


def test_invalid_suppression_is_reported_and_still_fails(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/bad-marker.md", INVALID_SUPPRESSION)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/bad-marker.md"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "invalid-suppression" in out
    assert ".serena/memories/bad-marker.md: normative:" in out


def test_readme_and_index_files_are_skipped(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/README.md", NORMATIVE_HEADING)
    _write(repo, ".serena/memories/foo-index.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", "--path", ".serena/memories"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "README.md" not in out
    assert "foo-index.md" not in out
    assert "0 file(s) examined" in out


def test_non_markdown_files_are_ignored(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/notes.txt", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/notes.txt"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "0 file(s) examined" in out


def test_symlinked_new_memory_is_judged_by_its_own_path(repo: Path, monkeypatch, capsys):
    # The link target is committed elsewhere; the link under memories is new.
    _write(repo, "elsewhere/real.md", NORMATIVE_HEADING)
    _commit_all(repo, "target")
    link = repo / ".serena" / "memories" / "link.md"
    _symlink_or_skip(link, repo / "elsewhere" / "real.md")
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", ".serena/memories/link.md"])
    out = capsys.readouterr().out
    assert code == 1
    assert ".serena/memories/link.md: normative" in out


def test_symlink_target_outside_repo_exits_two(repo: Path, tmp_path_factory, monkeypatch, capsys):
    outside = tmp_path_factory.mktemp("outside") / "real.md"
    outside.write_text(NORMATIVE_HEADING)
    link = repo / ".serena" / "memories" / "escape.md"
    _symlink_or_skip(link, outside)
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", ".serena/memories/escape.md"])
    captured = capsys.readouterr()
    assert code == 2
    assert "symlink target is outside the repository" in captured.err
    assert "normative" not in captured.out


def test_option_shaped_base_ref_exits_two(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/new.md", EVIDENCE_INCIDENT)
    monkeypatch.chdir(repo)
    # argparse consumes "--base=--help" as the value; the validator must still
    # refuse it before git sees an option where a ref belongs.
    code = checker.main(["--ci", "--base=--help", ".serena/memories/new.md"])
    assert code == 2
    assert "could not read base ref" in capsys.readouterr().err


def test_valid_ref_rejects_blank_control_and_option_shapes():
    assert placement_git.valid_ref("HEAD") is True
    assert placement_git.valid_ref("origin/main") is True
    assert placement_git.valid_ref("") is False
    assert placement_git.valid_ref("   ") is False
    assert placement_git.valid_ref("-r") is False
    assert placement_git.valid_ref("HEAD\n--help") is False


def test_missing_positional_path_exits_two(repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", ".serena/memories/does-not-exist.md"])
    assert code == 2
    assert "missing or a dangling symlink" in capsys.readouterr().err


def test_dangling_symlink_exits_two(repo: Path, monkeypatch, capsys):
    link = repo / ".serena" / "memories" / "dangling.md"
    _symlink_or_skip(link, repo / "nowhere.md")
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", ".serena/memories/dangling.md"])
    assert code == 2
    assert "missing or a dangling symlink" in capsys.readouterr().err


def test_missing_readme_positional_is_still_skipped(repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", ".serena/memories/README.md"])
    assert code == 0
    assert "0 file(s) examined" in capsys.readouterr().out


def test_staged_mode_reads_the_index_blob_not_the_tree(repo: Path, monkeypatch, capsys):
    path = _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    _run_git(repo, "add", ".serena/memories/new.md")
    path.write_text(EVIDENCE_INCIDENT)  # re-edited after staging, not restaged
    monkeypatch.chdir(repo)
    tree_code = checker.main(["--ci", "--base", "HEAD", ".serena/memories/new.md"])
    staged_code = checker.main(["--ci", "--base", "HEAD", "--staged", ".serena/memories/new.md"])
    capsys.readouterr()
    assert tree_code == 0
    assert staged_code == 1


def test_staged_mode_rejects_an_unindexed_file(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/loose.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", "--staged", ".serena/memories/loose.md"])
    captured = capsys.readouterr()
    assert code == 2
    assert "staged path is not in the index" in captured.err


def test_staged_mode_rejects_a_symlink(repo: Path, monkeypatch, capsys):
    _write(repo, "elsewhere/real.md", NORMATIVE_HEADING)
    _commit_all(repo, "target")
    link = repo / ".serena" / "memories" / "link.md"
    _symlink_or_skip(link, repo / "elsewhere" / "real.md")
    _run_git(repo, "add", str(link.relative_to(repo)))
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", "--staged", ".serena/memories/link.md"])
    captured = capsys.readouterr()
    assert code == 2
    assert "staged symlink cannot be validated" in captured.err


def test_staged_mode_reads_a_deleted_worktree_file_from_the_index(
    repo: Path, monkeypatch, capsys
):
    path = _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    _run_git(repo, "add", ".serena/memories/new.md")
    path.unlink()
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", "--staged", ".serena/memories/new.md"])
    captured = capsys.readouterr()
    assert code == 1
    assert ".serena/memories/new.md: normative" in captured.out


def test_staged_mode_reads_index_file_when_worktree_path_is_directory(
    repo: Path, monkeypatch, capsys
):
    path = _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    _run_git(repo, "add", ".serena/memories/new.md")
    path.unlink()
    path.mkdir()
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", "--staged", ".serena/memories/new.md"])
    captured = capsys.readouterr()
    assert code == 1
    assert ".serena/memories/new.md: normative" in captured.out


def test_staged_mode_uses_the_active_alternate_index(repo: Path, monkeypatch, capsys):
    alternate_index = repo / ".git" / "alternate-index"
    _run_git(repo, "read-tree", f"--index-output={alternate_index}", "HEAD")
    path = _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    monkeypatch.setenv("GIT_INDEX_FILE", str(alternate_index))
    _run_git(repo, "add", ".serena/memories/new.md")
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", "--staged", str(path)])
    captured = capsys.readouterr()
    assert code == 1
    assert ".serena/memories/new.md: normative" in captured.out


def test_staged_mode_resolves_relative_alternate_index_from_caller_directory(
    repo: Path, monkeypatch, capsys
):
    alternate_index = repo / ".git" / "alternate-index"
    _run_git(repo, "read-tree", f"--index-output={alternate_index}", "HEAD")
    path = _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    monkeypatch.setenv("GIT_INDEX_FILE", str(alternate_index))
    _run_git(repo, "add", ".serena/memories/new.md")
    caller_dir = repo / "nested"
    caller_dir.mkdir()
    monkeypatch.setenv("GIT_INDEX_FILE", os.path.relpath(alternate_index, caller_dir))
    monkeypatch.chdir(caller_dir)
    code = checker.main(["--ci", "--base", "HEAD", "--staged", str(path)])
    captured = capsys.readouterr()
    assert code == 1
    assert ".serena/memories/new.md: normative" in captured.out


def test_staged_mode_git_failure_exits_two_instead_of_falling_back(repo: Path, monkeypatch, capsys):
    path = _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    _run_git(repo, "add", ".serena/memories/new.md")
    path.write_text(EVIDENCE_INCIDENT)
    real = placement_git._run_subprocess

    def failing_show(args, **kwargs):
        if args[:2] == ["git", "cat-file"]:
            return 128, "", "fatal: simulated"
        return real(args, **kwargs)

    monkeypatch.setattr(placement_git, "_run_subprocess", failing_show)
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", "--base", "HEAD", "--staged", ".serena/memories/new.md"])
    captured = capsys.readouterr()
    assert code == 2
    assert "git cat-file" in captured.err
    assert "examined" not in captured.out


def test_positional_directory_argument_exits_two(repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    code = checker.main(["--ci", ".serena/memories"])
    assert code == 2
    assert "use --path" in capsys.readouterr().err


def test_path_outside_repo_exits_two(repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--path", str(repo.parent)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "outside the repository" in err


def test_bad_base_ref_exits_two(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/x.md", EVIDENCE_INCIDENT)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--base", "not-a-real-ref-xyz", ".serena/memories/x.md"])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "base ref" in err


def test_not_a_git_repository_exits_two(tmp_path: Path, monkeypatch, capsys):
    plain_dir = tmp_path / "not-a-repo"
    plain_dir.mkdir()
    monkeypatch.chdir(plain_dir)

    exit_code = checker.main([])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "not a git repository" in err


def test_json_output_parses_and_has_counts(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/normative.md", NORMATIVE_HEADING)
    _write(repo, ".serena/memories/suspect.md", SUSPECT_TERM_DENSITY)
    _write(repo, ".serena/memories/suppressed.md", VALID_SUPPRESSION)
    monkeypatch.chdir(repo)

    exit_code = checker.main(
        [
            "--ci",
            "--json",
            ".serena/memories/normative.md",
            ".serena/memories/suspect.md",
            ".serena/memories/suppressed.md",
        ]
    )

    out = capsys.readouterr().out
    report = json.loads(out)
    assert exit_code == 1
    assert report["examined"] == 3
    assert report["counts"] == {"normative": 1, "suspect": 1, "suppressed": 1}
    assert report["failing"] == 1
    assert len(report["findings"]) == 3


def test_path_directory_mode_walks_recursively(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/sub/dir/nested.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", "--path", ".serena/memories"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert ".serena/memories/sub/dir/nested.md: normative:" in out


def test_without_ci_flag_never_fails_even_on_a_new_normative_file(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main([".serena/memories/new.md"])

    assert exit_code == 0
