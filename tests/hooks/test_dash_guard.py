"""Em/en-dash prohibition guard tests (Issue #1923, REQ-006).

Test skeleton populated by M2 (TASK-006-2). Assertions for the pre-commit
section (M3a, TASK-006-3) and the commit-msg hook (M3b, TASK-006-4) land
in those milestones. This module currently verifies fixture integrity so
later milestones can rely on the fixture invariants.

Fixtures live under ``tests/hooks/fixtures/``. Each fixture is generated
programmatically with Python escape sequences (see M2 implementation) so
the source files of this repo do not themselves carry the prohibited
characters. The encoded UTF-8 bytes land in the fixture files only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# REPO_ROOT is the ai-agents checkout root. tests/hooks/test_dash_guard.py is
# three levels deep (tests/hooks/test_dash_guard.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "tests" / "hooks" / "fixtures"

# Compiled detection regex. The pattern itself uses Python escape sequences
# so this source file stays clean of the prohibited characters.
DASH_PATTERN = re.compile(r"[\u2013\u2014]")


@pytest.fixture(scope="module")
def fixture_dir() -> Path:
    """Locate the fixtures directory and assert it exists."""
    assert FIXTURES.is_dir(), f"Fixture directory missing: {FIXTURES}"
    return FIXTURES


def test_dash_violations_fixture_contains_both_dashes(fixture_dir: Path) -> None:
    """REQ-006-AC9 fixture invariant: dash_violations.md has U+2014 and U+2013."""
    text = (fixture_dir / "dash_violations.md").read_text(encoding="utf-8")
    assert "\u2014" in text, "fixture should contain U+2014 (em-dash)"
    assert "\u2013" in text, "fixture should contain U+2013 (en-dash)"


def test_no_dash_clean_fixture_has_neither_dash(fixture_dir: Path) -> None:
    """REQ-006-AC10 fixture invariant: no_dash_clean.md has neither dash."""
    text = (fixture_dir / "no_dash_clean.md").read_text(encoding="utf-8")
    assert not DASH_PATTERN.search(text), "clean fixture must not contain dashes"


def test_instructions_tree_fixture_has_em_dash(fixture_dir: Path) -> None:
    """REQ-006-AC4 + REQ-006-AC11 fixture invariant: mirror-tree fixture has U+2014."""
    text = (fixture_dir / "instructions_tree" / "dash_violations.md").read_text(
        encoding="utf-8",
    )
    assert "\u2014" in text, (
        "instructions-tree fixture should contain U+2014 to verify the guard"
        " applies identically to the .github/instructions/ tree (REQ-006-AC4)"
    )


def test_node_modules_fixture_has_em_dash(fixture_dir: Path) -> None:
    """REQ-006-AC5 fixture invariant: vendored fixture has U+2014.

    The fixture must contain a dash so we can prove the guard *skips*
    vendored paths; if the fixture were clean, the skip behavior would be
    indistinguishable from absence-of-violation.
    """
    text = (fixture_dir / "node_modules" / "dash_violations.md").read_text(
        encoding="utf-8",
    )
    assert "\u2014" in text, "vendored fixture should contain U+2014"


# ---------------------------------------------------------------------------
# M3a integration tests: pre-commit dash-check section
# ---------------------------------------------------------------------------
#
# The dash-check section in .githooks/pre-commit reuses two variables from
# earlier in the hook: IS_MERGE (line 136) and STAGED_MD_FILES (line 186).
# These tests reproduce that section in isolation by invoking bash with the
# two variables pre-set and capturing exit code and stderr.

import subprocess


# Bash fragment adapted from .githooks/pre-commit (the dash-check section).
# Intentionally simplified for testing:
#   - Omits informational output lines (file header, fix instructions,
#     rule reference) that don't affect detection logic.
#   - Redirects echo_error/echo_info to stderr for test assertions.
#   - Scans the WORKING TREE file (`grep -- "$dash_file"`) instead of the
#     STAGED BLOB (`git show ":$dash_file" | grep ...`). The canonical hook
#     uses `git show` so partial staging cannot fool the check; the test
#     fragment trades that fidelity for the ability to materialize files
#     in tmp_path without running `git init` and `git add` per test.
#     Integration tests that exercise the staged-blob path (a follow-up
#     not yet written) would init a temp repo, stage fixtures via
#     `git add`, then invoke the real hook script.
# The detection logic (regex pattern, exclusion paths, exit status) matches
# the canonical source byte-for-byte.
_HOOK_FRAGMENT = r"""
set -e
EXIT_STATUS=0
echo_error() { echo "ERROR: $1" >&2; }
echo_info() { echo "$1" >&2; }
if [ "$IS_MERGE" != "1" ] && [ -n "$STAGED_MD_FILES" ]; then
    # CRITICAL-001: Build array safely to preserve filenames with spaces
    DASH_HITS=()
    while IFS= read -r dash_file; do
        [ -z "$dash_file" ] && continue
        case "$dash_file" in
            node_modules/*|.venv/*|.serena/cache/*|tests/hooks/fixtures/*) continue ;;
        esac
        if [ -f "$dash_file" ] && LC_ALL=C.UTF-8 grep -qI $'[\xe2\x80\x93\xe2\x80\x94]' -- "$dash_file" 2>/dev/null; then
            DASH_HITS+=("$dash_file")
        fi
    done <<< "$STAGED_MD_FILES"
    if [ ${#DASH_HITS[@]} -gt 0 ]; then
        echo_error "Em/en-dash prohibition violated"
        for hit in "${DASH_HITS[@]}"; do
            echo_info "    $hit"
        done
        EXIT_STATUS=1
    fi
fi
exit $EXIT_STATUS
"""


def _run_hook_fragment(
    staged_md_files: str,
    is_merge: str = "0",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the dash-check fragment with controlled env."""
    return subprocess.run(  # noqa: S603 - controlled command, no user input
        ["bash", "-c", _HOOK_FRAGMENT],
        env={
            "IS_MERGE": is_merge,
            "STAGED_MD_FILES": staged_md_files,
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C.UTF-8",
        },
        cwd=cwd if cwd is not None else REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_hook_blocks_em_dash(fixture_dir: Path, tmp_path: Path) -> None:
    """REQ-006-AC1: hook exits 1 on em-dash (isolated, em-dash only).

    Materializes a file under tmp_path containing only U+2014 (no en-dash)
    so this test exercises em-dash detection independently from en-dash.
    """
    target = tmp_path / "src" / "doc.md"
    target.parent.mkdir(parents=True)
    target.write_text(f"em-dash {chr(0x2014)} here\n", encoding="utf-8")
    result = _run_hook_fragment("src/doc.md", cwd=tmp_path)
    assert result.returncode == 1
    assert "Em/en-dash prohibition" in result.stderr


def test_hook_blocks_en_dash(fixture_dir: Path, tmp_path: Path) -> None:
    """REQ-006-AC2: hook exits 1 on en-dash (isolated, en-dash only).

    Uses an en-dash-only fixture so this test cannot pass from em-dash
    detection alone; the hook must independently detect U+2013.
    """
    target = tmp_path / "src" / "range.md"
    target.parent.mkdir(parents=True)
    target.write_text(f"range 1{chr(0x2013)}10\n", encoding="utf-8")
    result = _run_hook_fragment("src/range.md", cwd=tmp_path)
    assert result.returncode == 1
    assert "Em/en-dash prohibition" in result.stderr


def test_hook_passes_clean_fixture(fixture_dir: Path, tmp_path: Path) -> None:
    """REQ-006-AC10: hook exits 0 on clean markdown.

    Materializes a clean file under tmp_path outside any exclusion prefix
    so grep actually runs on the content (not skipped by path filter).
    """
    target = tmp_path / "src" / "clean.md"
    target.parent.mkdir(parents=True)
    target.write_text("Clean markdown with no prohibited characters.\n", encoding="utf-8")
    result = _run_hook_fragment("src/clean.md", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == ""


def test_hook_blocks_instructions_tree_fixture(
    fixture_dir: Path, tmp_path: Path,
) -> None:
    """REQ-006-AC4: hook applies to .github/instructions/ paths.

    Materializes a real file under .github/instructions/ in tmp_path; the
    path-prefix filter must NOT exclude .github/instructions/, so the
    hook must detect the dash and exit 1.
    """
    target = tmp_path / ".github" / "instructions" / "dash_violations.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        f"Mirror tree with {chr(0x2014)} em-dash\n", encoding="utf-8",
    )
    result = _run_hook_fragment(
        ".github/instructions/dash_violations.md", cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "Em/en-dash prohibition" in result.stderr


def test_hook_skips_node_modules_fixture(
    fixture_dir: Path, tmp_path: Path,
) -> None:
    """REQ-006-AC5: hook skips vendored paths.

    Materializes a real file containing U+2014 under node_modules/ in
    tmp_path so the path-prefix filter is the only thing that can skip
    it (without this, the test would pass for the wrong reason: the
    `[ -f ]` guard fails before the prefix filter runs).
    """
    vendored = tmp_path / "node_modules" / "pkg" / "README.md"
    vendored.parent.mkdir(parents=True)
    vendored.write_text(
        f"upstream prose with {chr(0x2014)} em-dash\n", encoding="utf-8",
    )
    result = _run_hook_fragment(
        "node_modules/pkg/README.md", cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "Em/en-dash prohibition" not in result.stderr


def test_hook_skips_test_fixtures_dir(
    fixture_dir: Path, tmp_path: Path,
) -> None:
    """tests/hooks/fixtures/ is in the case-statement exclusion.

    Test fixtures intentionally contain U+2014 and U+2013 to exercise
    the detection logic. Flagging them would block every commit that
    touches the dash-guard test suite.
    """
    target = tmp_path / "tests" / "hooks" / "fixtures" / "doc.md"
    target.parent.mkdir(parents=True)
    target.write_text(f"intentional {chr(0x2014)}\n", encoding="utf-8")
    result = _run_hook_fragment(
        "tests/hooks/fixtures/doc.md", cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "Em/en-dash prohibition" not in result.stderr


def test_hook_skips_merge_commit(fixture_dir: Path, tmp_path: Path) -> None:
    """REQ-006-AC6: hook skips when IS_MERGE=1.

    Uses a real materialized file outside the fixtures-exclusion prefix so
    the test verifies the merge-commit short-circuit, not the
    fixtures-exclusion prefix.
    """
    target = tmp_path / "src" / "doc.md"
    target.parent.mkdir(parents=True)
    target.write_text(f"em-dash {chr(0x2014)} here\n", encoding="utf-8")
    result = _run_hook_fragment(
        "src/doc.md", is_merge="1", cwd=tmp_path,
    )
    assert result.returncode == 0


def test_hook_passes_with_no_staged_files(fixture_dir: Path) -> None:
    """Hook exits 0 (vacuous pass) when STAGED_MD_FILES is empty."""
    result = _run_hook_fragment("")
    assert result.returncode == 0


def test_hook_blocks_multiple_files(fixture_dir: Path, tmp_path: Path) -> None:
    """Hook reports all offending files when multiple are staged."""
    file_a = tmp_path / "doc-a.md"
    file_b = tmp_path / "doc-b.md"
    file_a.write_text(f"em-dash {chr(0x2014)} here\n", encoding="utf-8")
    file_b.write_text(f"en-dash {chr(0x2013)} here\n", encoding="utf-8")
    paths = "doc-a.md\ndoc-b.md"
    result = _run_hook_fragment(paths, cwd=tmp_path)
    assert result.returncode == 1
    assert "doc-a.md" in result.stderr
    assert "doc-b.md" in result.stderr


# ---------------------------------------------------------------------------
# M3b integration tests: .githooks/commit-msg hook
# ---------------------------------------------------------------------------
#
# The commit-msg hook receives the draft commit message file path as $1.
# These tests write a temporary file and invoke the hook directly.

COMMIT_MSG_HOOK = REPO_ROOT / ".githooks" / "commit-msg"


def _run_commit_msg_hook(
    message: str, tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the commit-msg hook with a draft message file."""
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text(message, encoding="utf-8")
    return subprocess.run(  # noqa: S603 - controlled command
        [str(COMMIT_MSG_HOOK), str(msg_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_commit_msg_hook_exists_and_executable() -> None:
    """The commit-msg hook file exists and is executable."""
    assert COMMIT_MSG_HOOK.is_file(), f"hook missing: {COMMIT_MSG_HOOK}"
    assert COMMIT_MSG_HOOK.stat().st_mode & 0o111, "hook must be executable"


def test_commit_msg_hook_passes_clean_message(tmp_path: Path) -> None:
    """Clean commit message exits 0."""
    result = _run_commit_msg_hook(
        "feat(scope): no prohibited characters here\n", tmp_path,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_commit_msg_hook_blocks_em_dash(tmp_path: Path) -> None:
    """REQ-006-AC3: commit message with U+2014 exits 1."""
    result = _run_commit_msg_hook(
        "feat: bad message \u2014 with em-dash\n", tmp_path,
    )
    assert result.returncode == 1
    assert "em-dash" in result.stderr.lower()


def test_commit_msg_hook_blocks_en_dash(tmp_path: Path) -> None:
    """REQ-006-AC3: commit message with U+2013 exits 1."""
    result = _run_commit_msg_hook(
        "feat: bad message \u2013 with en-dash\n", tmp_path,
    )
    assert result.returncode == 1
    assert "en-dash" in result.stderr.lower()


def test_commit_msg_hook_blocks_dash_in_subject_line(tmp_path: Path) -> None:
    """The subject line is checked, not just the body."""
    result = _run_commit_msg_hook(
        "feat: subject \u2014 line\n\nclean body\n", tmp_path,
    )
    assert result.returncode == 1


def test_commit_msg_hook_blocks_dash_in_body(tmp_path: Path) -> None:
    """The body is checked, not just the subject."""
    result = _run_commit_msg_hook(
        "feat: clean subject\n\nbody with \u2013 en-dash here\n",
        tmp_path,
    )
    assert result.returncode == 1


def test_commit_msg_hook_passes_when_file_path_missing(tmp_path: Path) -> None:
    """No-arg invocation fails open (returns 0). Infrastructure failure is not a violation."""
    result = subprocess.run(  # noqa: S603 - controlled command
        [str(COMMIT_MSG_HOOK)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


# M4 (pre_pr.py validate_dash_prohibition) tests extend this module in the
# next milestone.
