#!/usr/bin/env python3
"""Tests for Issue #2539: pre-push mypy partition logic avoids duplicate-module collision.

When a PR changes two Python files with the same basename (e.g.
``.github/scripts/foo.py`` and ``.claude/skills/bar/scripts/foo.py``), mypy
aborts with "Duplicate module named foo" if both are passed in one invocation.

The fix partitions PY_FILES into:
- PY_FILES_UNIQUE: basenames appearing exactly once -- checked in a single fast mypy call
- PY_FILES_COLLIDING: basenames appearing more than once -- each checked individually

These tests pin that partition logic at the script-content level (no subprocess
execution of pre-push itself).  One end-to-end smoke test runs mypy directly to
confirm that the duplicate-module error is real and that per-file invocations
avoid it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _make_hook_repo(tmp_path: Path) -> tuple[Path, str, str, dict[str, str]]:
    repo = tmp_path / "hook-repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "checkout", "-b", "main")
    _run_git(repo, "config", "user.name", "Pre Push Test")
    _run_git(repo, "config", "user.email", "pre-push-test@example.invalid")

    hook_dir = repo / ".githooks"
    hook_dir.mkdir()
    _write_executable(hook_dir / "pre-push", _text())
    build_scripts = repo / "build" / "scripts"
    build_scripts.mkdir(parents=True)
    (build_scripts / "generate_pr_quality_prompts.py").write_text(
        "import sys\nsys.exit(0)\n",
        encoding="utf-8",
    )

    (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: base")
    base_sha = _run_git(repo, "rev-parse", "HEAD")
    _run_git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    _run_git(repo, "checkout", "-b", "feature/duplicate-mypy")

    for directory, value in (("pkg_a", "1"), ("pkg_b", "2"), ("pkg_c", "3")):
        package_dir = repo / directory
        package_dir.mkdir()
        filename = "bar.py" if directory == "pkg_c" else "foo.py"
        (package_dir / filename).write_text(f"value: int = {value}\n", encoding="utf-8")

    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: add duplicate basenames")
    head_sha = _run_git(repo, "rev-parse", "HEAD")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "ruff",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    _write_executable(
        bin_dir / "mypy",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$MYPY_LOG"
if [ "${MYPY_FAIL_ON:-}" != "" ]; then
    case "$*" in
        *"$MYPY_FAIL_ON"*)
            echo "forced mypy failure for $MYPY_FAIL_ON"
            exit 1
            ;;
    esac
fi
exit 0
""",
    )

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["MYPY_LOG"] = str(repo / "mypy.log")
    env["TMPDIR"] = str(scratch)

    return repo, base_sha, head_sha, env


def _run_pre_push(
    repo: Path,
    base_sha: str,
    head_sha: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / ".githooks" / "pre-push")],
        cwd=repo,
        input=f"refs/heads/feature/duplicate-mypy {head_sha} "
        f"refs/heads/feature/duplicate-mypy {base_sha}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# 1. Partition logic exists
# ---------------------------------------------------------------------------


def test_partitions_by_basename() -> None:
    """Arrange/Act: read pre-push text.
    Assert: the script contains logic that partitions PY_FILES by basename into
    a unique set and a colliding set.
    """
    # Arrange
    text = _text()

    # Act -- nothing to run, purely content-level assertion

    # Assert: partition variable names exist
    assert "PY_FILES_UNIQUE" in text, (
        "Expected PY_FILES_UNIQUE partition variable in pre-push; "
        "partition-by-basename logic is missing"
    )
    assert "PY_FILES_COLLIDING" in text, (
        "Expected PY_FILES_COLLIDING partition variable in pre-push; "
        "partition-by-basename logic is missing"
    )
    # Assert: basename is used to build the partition (bash `basename` command
    # or parameter expansion ``${f##*/}``)
    assert ("basename" in text) or ("##*/" in text), (
        "Expected basename extraction (via 'basename' cmd or '##*/' expansion) "
        "in pre-push partition logic"
    )
    assert "declare -A" not in text, (
        "Associative arrays require Bash 4; the mypy partition must stay "
        "compatible with the ambient bash on macOS"
    )
    assert "mapfile " not in text, (
        "mapfile requires Bash 4; pre-push must keep file-list handling "
        "compatible with the ambient bash on macOS"
    )


# ---------------------------------------------------------------------------
# 2. Colliding files are checked per-file (not in one bulk invocation)
# ---------------------------------------------------------------------------


def test_per_file_mypy_for_collisions() -> None:
    """Assert pre-push iterates over PY_FILES_COLLIDING and invokes mypy once
    per file, so no two same-named modules are ever in the same mypy call.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: a quoted loop over PY_FILES_COLLIDING that calls mypy on one file.
    assert 'for col_file in "${PY_FILES_COLLIDING[@]}"; do' in text, (
        "Expected quoted per-file loop for colliding files"
    )
    assert "PY_FILES_COLLIDING" in text
    # mypy must be called with a single-file variable inside the colliding loop
    # Look for the pattern: mypy "$col_file" or mypy "${col_file}"
    assert ('"$col_file"' in text) or ("${col_file}" in text), (
        "Expected per-file mypy invocation (mypy \"$col_file\") for colliding "
        "files; found neither pattern in pre-push"
    )


# ---------------------------------------------------------------------------
# 3. Non-colliding files still use a single bulk mypy invocation (fast path)
# ---------------------------------------------------------------------------


def test_unique_files_still_bulk_checked() -> None:
    """Assert the fast path: when all basenames are unique, mypy is called once
    with all files, preserving the pre-#2539 single-invocation behavior.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: mypy is called with the full PY_FILES_UNIQUE array
    assert (
        'mypy "${PY_FILES_UNIQUE[@]}"' in text
        or "mypy ${PY_FILES_UNIQUE" in text
    ), (
        "Expected bulk mypy invocation on PY_FILES_UNIQUE array in pre-push; "
        "the non-colliding fast path appears to be missing"
    )


# ---------------------------------------------------------------------------
# 4. Aggregate failure: ALL invocation exits are checked
# ---------------------------------------------------------------------------


def test_aggregate_failure() -> None:
    """Assert that pre-push tracks success/failure across BOTH the unique-files
    mypy call AND every per-colliding-file call, recording a fail only when at
    least one invocation fails.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: a boolean accumulator (e.g. MYPY_OVERALL_PASS or MYPY_FAILED) is
    # present so partial failures are caught.
    assert ("MYPY_OVERALL_PASS" in text) or ("MYPY_FAILED" in text), (
        "Expected an aggregate pass/fail accumulator (MYPY_OVERALL_PASS or "
        "MYPY_FAILED) in pre-push mypy section; a single invocation result is "
        "insufficient when there are multiple mypy calls"
    )
    # Assert: record_pass and record_fail both reference the accumulator region
    # (a record_pass call must follow a successful aggregate check)
    mypy_section_start = text.find("# 7. Python type check (mypy)")
    mypy_section_end = text.find("# 8.", mypy_section_start)
    mypy_section = text[mypy_section_start:mypy_section_end]
    assert "record_pass" in mypy_section, (
        "Expected record_pass in mypy section of pre-push"
    )
    assert "record_fail" in mypy_section, (
        "Expected record_fail in mypy section of pre-push"
    )


# ---------------------------------------------------------------------------
# 5. Tempfile cleanup is preserved for new MYPY_OUTPUT tempfiles
# ---------------------------------------------------------------------------


def test_tempfile_cleanup_preserved() -> None:
    """Assert that any new MYPY_OUTPUT tempfile(s) created for the colliding
    path are added to TEMP_FILES so cleanup() removes them on exit.
    """
    # Arrange
    text = _text()

    # Act -- content-level only

    # Assert: every mktemp result used for mypy output is appended to TEMP_FILES.
    # Count mktemp lines in the mypy section and verify TEMP_FILES+= appears
    # the same number of times in proximity (within the section).
    mypy_section_start = text.find("# 7. Python type check (mypy)")
    mypy_section_end = text.find("# 8.", mypy_section_start)
    mypy_section = text[mypy_section_start:mypy_section_end]

    mktemp_count = mypy_section.count("$(mktemp)")
    temp_files_count = mypy_section.count("TEMP_FILES+=")
    assert mktemp_count > 0, "Expected at least one mktemp in mypy section"
    assert temp_files_count >= mktemp_count, (
        f"Expected at least {mktemp_count} TEMP_FILES+= in mypy section "
        f"(one per mktemp), found {temp_files_count}"
    )


# ---------------------------------------------------------------------------
# 6. Hook-level behavior: partitioning and aggregate failure
# ---------------------------------------------------------------------------


def test_pre_push_partitions_colliding_basenames_at_runtime(tmp_path: Path) -> None:
    repo, base_sha, head_sha, env = _make_hook_repo(tmp_path)

    result = _run_pre_push(repo, base_sha, head_sha, env)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "PASS: Python type check/mypy (3 files)" in output

    mypy_calls = (repo / "mypy.log").read_text(encoding="utf-8").splitlines()
    assert "pkg_c/bar.py" in mypy_calls
    assert "pkg_a/foo.py" in mypy_calls
    assert "pkg_b/foo.py" in mypy_calls
    assert not any("pkg_a/foo.py" in call and "pkg_b/foo.py" in call for call in mypy_calls)


def test_pre_push_fails_closed_when_colliding_file_mypy_fails(tmp_path: Path) -> None:
    repo, base_sha, head_sha, env = _make_hook_repo(tmp_path)
    env["MYPY_FAIL_ON"] = "pkg_b/foo.py"

    result = _run_pre_push(repo, base_sha, head_sha, env)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "forced mypy failure for pkg_b/foo.py" in output
    assert "ERROR: Python type check/mypy" in output
    assert "PASS: Python type check/mypy (3 files)" not in output


# ---------------------------------------------------------------------------
# End-to-end smoke test: proves WHY the partition is necessary
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("mypy") is None,
    reason="mypy not on PATH; skipping live duplicate-module smoke test",
)
def test_collision_reproduction(tmp_path: Path) -> None:
    """Prove that passing two same-basename files to a single mypy invocation
    triggers 'Duplicate module' and that separate invocations succeed.

    This test pins the root cause so that if mypy ever changes behavior the
    test breaks loudly and we can re-evaluate the partition strategy.
    """
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    # Arrange: two trivially type-clean files with the same basename
    (dir_a / "foo.py").write_text("x: int = 1\n", encoding="utf-8")
    (dir_b / "foo.py").write_text("y: str = 'hello'\n", encoding="utf-8")

    file_a = str(dir_a / "foo.py")
    file_b = str(dir_b / "foo.py")

    # Act + Assert (negative): one invocation with both files fails with
    # "Duplicate module"
    result_single = subprocess.run(
        ["mypy", file_a, file_b],
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = result_single.stdout + result_single.stderr
    assert result_single.returncode != 0, (
        "Expected mypy to fail when given two files with the same basename "
        f"in one invocation; exit code was {result_single.returncode}"
    )
    assert "Duplicate module" in combined or "duplicate module" in combined.lower(), (
        f"Expected 'Duplicate module' in mypy output; got:\n{combined}"
    )

    # Act + Assert (positive): separate invocations each succeed
    result_a = subprocess.run(
        ["mypy", file_a],
        capture_output=True,
        text=True,
        timeout=30,
    )
    result_b = subprocess.run(
        ["mypy", file_b],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result_a.returncode == 0, (
        f"mypy on {file_a} alone should pass; got:\n{result_a.stdout}{result_a.stderr}"
    )
    assert result_b.returncode == 0, (
        f"mypy on {file_b} alone should pass; got:\n{result_b.stdout}{result_b.stderr}"
    )
