"""One push-lock path, enforced over tracked prescriptions (issue #4366).

``flock`` excludes only processes that open the same path, so a second lock name
is not a second lock. Three schemes were live at once and only a ``ps`` census
found them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_push_lock_paths as checker

CANONICAL_LINE = 'flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push origin "$BR"'


def test_canonical_path_is_accepted() -> None:
    assert checker.scan_text(CANONICAL_LINE) == []


def test_braced_home_is_accepted() -> None:
    line = 'flock "${HOME}/src/scratch/locks/push-lock-fix-foo.lock" git push'

    assert checker.scan_text(line) == []


def test_tmp_path_is_rejected() -> None:
    findings = checker.scan_text('flock "/tmp/push-lock-$SLUG.lock" git push')

    assert findings == [(1, "/tmp/push-lock-$SLUG.lock")]


def test_hashed_slot_scheme_is_rejected() -> None:
    findings = checker.scan_text("flock /tmp/aiagents-push-$SLOT.lock git push")

    assert [path for _line, path in findings] == ["/tmp/aiagents-push-$SLOT.lock"]


def test_literal_home_directory_is_rejected() -> None:
    findings = checker.scan_text(
        'flock "/home/richard/src/GitHub/rjmurillo/ai-agents-pushpol2-push-${SLUG}.lock" git push'
    )

    assert len(findings) == 1


def test_unquoted_canonical_path_is_accepted() -> None:
    assert checker.scan_text("flock $HOME/src/scratch/locks/push-lock-x.lock git push") == []


def test_a_lock_path_outside_the_canonical_directory_is_rejected() -> None:
    findings = checker.scan_text('flock "$HOME/locks/push-lock-x.lock" git push')

    assert len(findings) == 1


def test_a_line_without_flock_is_not_scanned() -> None:
    assert checker.scan_text("the old global lock lived at /tmp/aiagents-push.lock") == []


def test_a_fenced_block_marked_historical_is_skipped() -> None:
    text = "\n".join(
        [
            "```bash",
            "# push-lock-historical: the superseded scheme",
            "flock /tmp/aiagents-push.lock git push origin main",
            "```",
        ]
    )

    assert checker.scan_text(text) == []


def test_the_historical_marker_does_not_leak_past_its_block() -> None:
    text = "\n".join(
        [
            "```bash",
            "# push-lock-historical",
            "flock /tmp/aiagents-push.lock git push",
            "```",
            "",
            "```bash",
            "flock /tmp/push-lock-other.lock git push",
            "```",
        ]
    )

    findings = checker.scan_text(text)

    assert [path for _line, path in findings] == ["/tmp/push-lock-other.lock"]


def test_line_numbers_point_at_the_offending_line() -> None:
    text = "\n".join(["intro", "more prose", "flock /tmp/bad.lock git push"])

    assert checker.scan_text(text)[0][0] == 3


def _init_repo(repo: Path, files: dict[str, str]) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)


def test_main_exits_1_and_names_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": "flock /tmp/push-lock-a.lock git push\n"})

    assert checker.main(["--repo-root", str(repo)]) == 1

    captured = capsys.readouterr()
    assert "docs/push.md:1" in captured.err
    assert "1 violation(s) in 1 tracked Markdown file(s)" in captured.out


def test_main_exits_0_and_reports_the_examined_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": CANONICAL_LINE + "\n"})

    assert checker.main(["--repo-root", str(repo)]) == 0
    assert "0 violation(s) in 1 tracked Markdown file(s)" in capsys.readouterr().out


def test_retrospectives_are_out_of_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(
        repo,
        {".agents/retrospective/old.md": "flock /tmp/aiagents-push.lock git push\n"},
    )

    assert checker.main(["--repo-root", str(repo)]) == 0


def test_main_exits_2_outside_a_git_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert checker.main(["--repo-root", str(tmp_path)]) == 2
    assert "ERROR" in capsys.readouterr().err


def test_pre_pr_runs_the_push_lock_check() -> None:
    """Wiring: the checker is dead code unless the pre-PR sequence calls it."""
    source = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "validation"
        / "pre_pr_sequence.py"
    ).read_text(encoding="utf-8")

    assert "from check_push_lock_paths import validate_push_lock_paths" in source
    assert "validate_push_lock_paths(repo_root)" in source


def test_validate_entry_point_returns_false_on_a_violation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": "flock /tmp/push-lock-a.lock git push\n"})

    assert checker.validate_push_lock_paths(repo) is False


def test_validate_entry_point_returns_true_on_a_clean_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": CANONICAL_LINE + "\n"})

    assert checker.validate_push_lock_paths(repo) is True


def test_the_shipped_corpus_has_no_violation() -> None:
    """The gate must be green against the whole tree before it can block a push."""
    repo_root = Path(__file__).resolve().parents[2]

    violations, examined = checker.check_paths(
        repo_root, checker.tracked_markdown(repo_root)
    )

    assert violations == []
    assert examined > 0
