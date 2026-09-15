"""Generated-mirror false positives in the security-suppression gate.

ADR-109 B3's follow-up (generate_skills.sync_claude_plugin_skill_support)
mirrors .claude/skills/ into src/claude/skills/ byte for byte. Git's rename
detector (-M) only pairs an ADDED path with a DELETED one; a mirror added
alongside its unchanged source has no deletion to pair with, so an
already-reviewed suppression comment (nosemgrep, nosec, noqa: S...) at the
source re-triggers `security-suppressions-staged` at the mirror path the
first time that mirror is populated. `_drop_verbatim_mirror_violations`
narrows that false positive: it drops a violation only when the CURRENT
mirror content is byte-identical, in full, to the source committed at the
comparison ref, so a genuinely new or diverged suppression is never dropped.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation import git_hook_policy as policy


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _write(repo: Path, relative_path: str, content: str) -> None:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


_NOSEMGREP = "# " + "nosem" + "grep"  # assembled so this file does not trip its own gate
SUPPRESSED_LINE = (
    "result = subprocess.run(  " + _NOSEMGREP + ": dangerous-subprocess-use-tainted-env-args\n"
)


# --- _drop_verbatim_mirror_violations: unit level -----------------------


def test_drops_violation_for_byte_identical_staged_mirror(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, ".claude/skills/foo/scripts/run.py", SUPPRESSED_LINE)
    _commit_all(repo, "seed reviewed source")
    _write(repo, "src/claude/skills/foo/scripts/run.py", SUPPRESSED_LINE)
    _git(repo, "add", "-A")

    violations = ["staged:src/claude/skills/foo/scripts/run.py:1"]
    kept = policy._drop_verbatim_mirror_violations(
        violations, repo, source_ref="HEAD", dest_ref=None
    )

    assert kept == []


def test_keeps_violation_when_mirror_diverges_from_source(tmp_path: Path) -> None:
    """A mirror that has NOT caught up to source drift keeps its own flag."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, ".claude/skills/foo/scripts/run.py", SUPPRESSED_LINE)
    _commit_all(repo, "seed reviewed source")
    _write(
        repo,
        "src/claude/skills/foo/scripts/run.py",
        SUPPRESSED_LINE + "extra_line = 1\n",
    )
    _git(repo, "add", "-A")

    violations = ["staged:src/claude/skills/foo/scripts/run.py:1"]
    kept = policy._drop_verbatim_mirror_violations(
        violations, repo, source_ref="HEAD", dest_ref=None
    )

    assert kept == violations


def test_keeps_violation_when_source_has_no_committed_history(tmp_path: Path) -> None:
    """A brand-new suppression with no canonical source to defer to stays flagged."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "README.md", "seed\n")
    _commit_all(repo, "seed")
    _write(repo, "src/claude/skills/foo/scripts/run.py", SUPPRESSED_LINE)
    _git(repo, "add", "-A")

    violations = ["staged:src/claude/skills/foo/scripts/run.py:1"]
    kept = policy._drop_verbatim_mirror_violations(
        violations, repo, source_ref="HEAD", dest_ref=None
    )

    assert kept == violations


def test_keeps_violation_for_a_non_mirror_path(tmp_path: Path) -> None:
    """A suppression outside every _GENERATED_MIRRORS prefix is never exempted."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "README.md", "seed\n")
    _commit_all(repo, "seed")
    _write(repo, "scripts/authored/run.py", SUPPRESSED_LINE)
    _git(repo, "add", "-A")

    violations = ["staged:scripts/authored/run.py:1"]
    kept = policy._drop_verbatim_mirror_violations(
        violations, repo, source_ref="HEAD", dest_ref=None
    )

    assert kept == violations


def test_malformed_violation_string_passes_through_unfiltered(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "README.md", "seed\n")
    _commit_all(repo, "seed")
    violations = ["not-a-well-formed-violation"]

    kept = policy._drop_verbatim_mirror_violations(
        violations, repo, source_ref="HEAD", dest_ref=None
    )

    assert kept == violations


def test_empty_violation_list_returns_empty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "README.md", "seed\n")
    _commit_all(repo, "seed")

    assert policy._drop_verbatim_mirror_violations([], repo, source_ref="HEAD", dest_ref=None) == []


# --- check_staged_suppressions: end-to-end gate --------------------------


def test_gate_passes_for_a_verbatim_new_mirror(tmp_path: Path) -> None:
    """The exact regression this record fixes: a first-time mirror of an
    already-reviewed suppression must not block the commit that adds it."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, ".claude/skills/foo/scripts/run.py", SUPPRESSED_LINE)
    _commit_all(repo, "seed reviewed source")
    _write(repo, "src/claude/skills/foo/scripts/run.py", SUPPRESSED_LINE)
    _git(repo, "add", "-A")

    assert policy.check_staged_suppressions(repo) == 0


def test_gate_still_blocks_a_genuinely_new_suppression(tmp_path: Path) -> None:
    """A suppression with no reviewed mirror source is still caught."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "README.md", "seed\n")
    _commit_all(repo, "seed")
    _write(repo, "scripts/authored/run.py", SUPPRESSED_LINE)
    _git(repo, "add", "-A")

    assert policy.check_staged_suppressions(repo) == 1


# --- _is_verbatim_mirror_on_disk: the same false positive, in run_mypy -----
#
# run_mypy's changed-line ratchet (_changed_line_map, _mypy_result_blocks)
# has no prior commit at a brand-new mirror path to compare against, so a
# pre-existing type error the mirror's already-reviewed .claude/skills/
# source carries reads as newly introduced the first time the build
# populates the mirror. _is_verbatim_mirror_on_disk lets run_mypy skip a
# mirror entirely when its on-disk bytes match its source: the source is
# still checked (or not) on its own schedule, but the identical copy is
# never a second, redundant finding of the same pre-existing issue.


def test_is_verbatim_mirror_on_disk_true_for_identical_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, ".claude/skills/foo/scripts/run.py", "x = 1\n")
    _write(repo, "src/claude/skills/foo/scripts/run.py", "x = 1\n")

    assert policy._is_verbatim_mirror_on_disk(repo, "src/claude/skills/foo/scripts/run.py")


def test_is_verbatim_mirror_on_disk_false_when_content_diverges(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, ".claude/skills/foo/scripts/run.py", "x = 1\n")
    _write(repo, "src/claude/skills/foo/scripts/run.py", "x = 2\n")

    assert not policy._is_verbatim_mirror_on_disk(repo, "src/claude/skills/foo/scripts/run.py")


def test_is_verbatim_mirror_on_disk_false_for_a_non_mirror_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "scripts/authored/run.py", "x = 1\n")

    assert not policy._is_verbatim_mirror_on_disk(repo, "scripts/authored/run.py")


def test_is_verbatim_mirror_on_disk_false_when_source_is_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "src/claude/skills/foo/scripts/run.py", "x = 1\n")

    assert not policy._is_verbatim_mirror_on_disk(repo, "src/claude/skills/foo/scripts/run.py")
