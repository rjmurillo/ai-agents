"""Tests for the final-pass fixes to check_unused_arguments.py.

Covers the scan coverage of generated copies, the shallow-clone probe under the
deadline, the unreadable-source paths, a UTF-8 BOM, a base-ref failure after the
scan, and the ruff command and version in the output.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

import check_unused_arguments
from check_unused_arguments import (
    EXCLUDED_PATHS,
    REPO_ROOT,
    Deadline,
    GateConfigError,
    _read_source,
    tracked_python_files,
    validate,
    validate_unused_arguments,
)

from tests.validation.unused_arguments_helpers import (
    UNUSED,
    UNUSED_KEY,
    add_file,
    commit_baseline,
    fail_git_subcommand,
    make_repo,
    run_gate,
    spy_run,
    time_out_ruff_version,
    write_baseline,
)

MIRRORED_PACKAGES = ("ai_review_common", "failure_classifier", "github_core", "hook_utilities")


def _tracked(*roots: str) -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", *roots],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [p for p in listing.stdout.split("\0") if p.endswith(".py")]


def _counterpart(path: str) -> str | None:
    """Return where the scanned original of an excluded generated copy lives."""
    lib = "src/claude/lib/"
    if path == f"{lib}bootstrap.py":
        return "scripts/hook_utilities/bootstrap.py"
    if path.startswith(lib) and path[len(lib) :].split("/")[0] in MIRRORED_PACKAGES:
        return f"scripts/{path[len(lib) :]}"
    if path.startswith(lib) and "/" not in path[len(lib) :]:
        return f".claude/lib/{path[len(lib) :]}"
    if path == "src/claude/skills/review/scripts/validate_review_marker.py":
        return "scripts/validation/validate_review_marker.py"
    return None


def test_every_excluded_generated_copy_has_a_scanned_original() -> None:
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in tracked_python_files(REPO_ROOT)}
    excluded = [
        path
        for path in _tracked("src/claude/lib", "src/claude/skills/review/scripts")
        if "tests" not in path.split("/")
        and any(
            path.startswith(entry) if entry.endswith("/") else path == entry
            for entry in EXCLUDED_PATHS
        )
    ]

    assert excluded, "no excluded generated copy found; the pin checks nothing"
    orphans = [path for path in excluded if _counterpart(path) not in scanned]
    assert orphans == []


@pytest.mark.parametrize("relpath", ["scripts/github_core/new_mod.py", ".claude/lib/new_mod.py"])
def test_a_new_unused_argument_in_a_scanned_original_exits_1(tmp_path: Path, relpath: str) -> None:
    repo = make_repo(tmp_path)
    add_file(repo, relpath, UNUSED)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 1


def test_the_shallow_probe_runs_under_the_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    seen: list[object] = []

    def record(argv: list[str], kwargs: dict[str, object]) -> None:
        if "--is-shallow-repository" in argv:
            seen.append(kwargs.get("timeout"))

    monkeypatch.setattr(check_unused_arguments.subprocess, "run", spy_run(subprocess.run, record))

    with pytest.raises(check_unused_arguments.GrowthCheckError):
        validate(repo, write_baseline(tmp_path, UNUSED_KEY), "no-such-ref", Deadline(5.0))

    assert len(seen) == 1
    assert isinstance(seen[0], int | float)
    assert 0 < seen[0] <= 5.0


def test_a_failed_shallow_probe_keeps_the_fork_point_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The probe only picks the remedy text. A probe that cannot start raises
    # GateConfigError, which main() maps to exit 2 unless the probe swallows it.
    repo = make_repo(tmp_path)

    def vanish(argv: list[str], kwargs: dict[str, object]) -> None:
        if "--is-shallow-repository" in argv:
            raise FileNotFoundError("git vanished")

    monkeypatch.setattr(check_unused_arguments.subprocess, "run", spy_run(subprocess.run, vanish))

    code = run_gate(repo, write_baseline(tmp_path, UNUSED_KEY), "--base-ref", "no-such-ref")

    assert code == 3
    err = capsys.readouterr().err
    assert "FORK POINT UNREADABLE" in err
    assert "is not fetched, is not a valid ref" in err


def test_the_pre_pr_entry_point_fails_closed_when_the_growth_check_cannot_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # "trunk" is in none of DEFAULT_BASE_REFS, so the growth check raises after
    # the scan. GrowthCheckError is outside the other handler's exception tuple.
    repo = make_repo(tmp_path, branch="trunk")
    commit_baseline(repo, UNUSED_KEY)

    assert validate_unused_arguments(repo) is False
    err = capsys.readouterr().err
    assert err.startswith("error: unused-argument gate: the scan ran")
    assert "growth check could not run" in err


def test_read_source_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(GateConfigError, match="cannot read .*gone.py to name an owner"):
        _read_source(tmp_path / "gone.py")


def test_read_source_reports_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_bytes(b"x = '\xff\xfe'\n")

    with pytest.raises(GateConfigError, match="cannot read .*bad.py to name an owner"):
        _read_source(bad)


def test_a_utf8_bom_file_reports_its_finding_instead_of_a_parse_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, source="﻿" + UNUSED)

    assert run_gate(repo, write_baseline(tmp_path)) == 1
    err = capsys.readouterr().err
    assert f"new unused argument: {UNUSED_KEY}" in err
    assert "U+FEFF" not in err


def test_a_utf8_bom_file_with_a_baselined_finding_passes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, source="﻿" + UNUSED)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0


def test_a_missing_base_ref_still_reports_the_scan_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No main, origin/main, or origin/HEAD resolves on branch trunk.
    repo = make_repo(tmp_path, branch="trunk")
    baseline = write_baseline(tmp_path, "scripts/gone.py: ARG001 x in f")

    assert run_gate(repo, baseline) == 2
    err = capsys.readouterr().err
    assert f"new unused argument: {UNUSED_KEY}" in err
    assert "stale baseline entry: scripts/gone.py: ARG001 x in f" in err
    assert "did not run" not in err
    assert "the scan ran" in err
    assert "baseline growth check could not run" in err
    assert "no base ref resolved" in err


def test_an_unreadable_merge_base_still_reports_the_scan_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setattr(
        check_unused_arguments.subprocess,
        "run",
        fail_git_subcommand(subprocess.run, "merge-base"),
    )

    assert run_gate(repo, write_baseline(tmp_path)) == 3
    err = capsys.readouterr().err
    assert f"new unused argument: {UNUSED_KEY}" in err
    assert "did not run" not in err
    assert "FORK POINT UNREADABLE" in err


def test_a_passing_run_names_the_ruff_command_and_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0
    assert re.search(r"ruff: .*-m ruff \(ruff \d+\.\d+\.\d+", capsys.readouterr().out)


def test_a_failing_run_names_the_ruff_command_and_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)

    assert run_gate(repo, write_baseline(tmp_path)) == 1
    assert re.search(r"ruff: .*-m ruff \(ruff \d+\.\d+\.\d+", capsys.readouterr().err)


def test_an_unreadable_ruff_version_reads_as_unknown_and_keeps_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setattr(
        check_unused_arguments.subprocess, "run", time_out_ruff_version(subprocess.run)
    )

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0
    assert "version unknown" in capsys.readouterr().out
