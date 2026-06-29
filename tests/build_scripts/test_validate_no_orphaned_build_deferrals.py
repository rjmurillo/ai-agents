"""Tests for scripts/validation/validate_no_orphaned_build_deferrals.py (#2770).

The validator polices staleness-deferral exemptions in build_all.py so an
orphaned deferral (one whose tracking issue has CLOSED) cannot be left behind.
Every test mocks the GitHub issue-state lookup at the boundary; none hit the
live API.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import validate_no_orphaned_build_deferrals as mod  # noqa: E402

# --- Block scanning --------------------------------------------------------


def test_find_deferral_blocks_empty_source_has_none() -> None:
    """A build_all.py with no deferral constant yields zero blocks."""
    source = "X = 1\n\n\ndef run():\n    return 0\n"
    assert mod.find_deferral_blocks(source) == []


def test_find_deferral_blocks_matches_named_constant() -> None:
    """A column-0 *_DEFERRALS constant is detected and its issues parsed."""
    source = (
        "OWNED = ('src/',)\n"
        "STALENESS_DEFERRALS = {\n"
        "    # cva-analysis broken upstream, see #1234\n"
        '    "src/copilot-cli/skills/cva-analysis/SKILL.md": "broken",\n'
        "}\n"
        "\n"
        "def run():\n"
        "    return 0\n"
    )
    blocks = mod.find_deferral_blocks(source)
    assert len(blocks) == 1
    assert blocks[0].name == "STALENESS_DEFERRALS"
    assert blocks[0].issues == [1234]


def test_find_deferral_blocks_ignores_indented_local_variable() -> None:
    """A deferral-shaped name indented inside a function is not a registry."""
    source = "def run():\n    STALENESS_DEFERRALS = []\n    return STALENESS_DEFERRALS\n"
    assert mod.find_deferral_blocks(source) == []


def test_find_deferral_blocks_matches_staleness_blocklist() -> None:
    """A STALENESS_* constant with an exemption marker is a deferral registry."""
    source = (
        "STALENESS_BLOCKLIST = {\n"
        "    # broken upstream, see #1234\n"
        '    "x": "broken",\n'
        "}\n"
    )
    blocks = mod.find_deferral_blocks(source)
    assert len(blocks) == 1
    assert blocks[0].name == "STALENESS_BLOCKLIST"
    assert blocks[0].issues == [1234]


def test_find_deferral_blocks_ignores_plain_staleness_threshold() -> None:
    """A numeric STALENESS threshold has no exemption marker, so it is not a registry."""
    source = "STALENESS_THRESHOLD_DAYS = 30\n"
    assert mod.find_deferral_blocks(source) == []


def test_block_extent_stops_at_next_top_level_statement() -> None:
    """A multi-line block ends at the next column-0 code line, not mid-literal."""
    source = (
        "STALENESS_EXEMPTIONS = [\n"
        "    # issue 4321\n"
        '    "a",\n'
        "]\n"
        "NEXT = 2\n"
    )
    blocks = mod.find_deferral_blocks(source)
    assert len(blocks) == 1
    assert blocks[0].issues == [4321]
    assert "NEXT = 2" not in blocks[0].text


# --- Issue-state lookup boundary -------------------------------------------


def _fake_runner(stdout: str, returncode: int = 0):
    def runner(argv, **kwargs):  # noqa: ANN001, ANN003
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    return runner


def test_lookup_issue_state_open() -> None:
    state = mod.lookup_issue_state(
        7, "owner/repo", runner=_fake_runner('{"state": "open"}')
    )
    assert state == "OPEN"


def test_lookup_issue_state_closed() -> None:
    state = mod.lookup_issue_state(
        7, "owner/repo", runner=_fake_runner('{"state": "CLOSED"}')
    )
    assert state == "CLOSED"


def test_lookup_issue_state_none_on_gh_failure() -> None:
    """A non-zero gh return (not found, auth, offline) yields None."""
    state = mod.lookup_issue_state(
        7, "owner/repo", runner=_fake_runner("", returncode=1)
    )
    assert state is None


def test_lookup_issue_state_none_on_subprocess_error() -> None:
    """gh missing from PATH (OSError) yields None, never raises."""

    def boom(argv, **kwargs):  # noqa: ANN001, ANN003
        raise OSError("gh not found")

    assert mod.lookup_issue_state(7, "owner/repo", runner=boom) is None


def test_lookup_issue_state_none_on_bad_json() -> None:
    state = mod.lookup_issue_state(
        7, "owner/repo", runner=_fake_runner("not json")
    )
    assert state is None


def test_lookup_issue_state_none_on_explicit_json_null() -> None:
    """An explicit JSON null state resolves to None, not a crash."""
    state = mod.lookup_issue_state(
        7, "owner/repo", runner=_fake_runner('{"state": null}')
    )
    assert state is None


def test_lookup_issue_state_none_on_non_dict_json() -> None:
    """A non-object JSON payload (e.g. a bare number) yields None, never raises."""
    state = mod.lookup_issue_state(
        7, "owner/repo", runner=_fake_runner("123")
    )
    assert state is None


# --- End-to-end validation -------------------------------------------------


def _write_build_all(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "build_all.py"
    target.write_text(body, encoding="utf-8")
    return target


def test_validate_empty_registry_passes(tmp_path: Path) -> None:
    """(a) No deferral constant: gate passes, lookup never invoked."""
    path = _write_build_all(tmp_path, "OWNED = ('src/',)\n\n\ndef run():\n    return 0\n")

    def fail_if_called(issue: int, repo: str) -> str | None:
        raise AssertionError("lookup must not run when there are no deferrals")

    assert mod.validate_no_orphaned_build_deferrals(
        path, "owner/repo", lookup=fail_if_called
    )


def test_validate_open_issue_deferral_passes(tmp_path: Path) -> None:
    """(b) Deferral whose issue is OPEN: gate passes."""
    path = _write_build_all(
        tmp_path,
        'STALENESS_DEFERRALS = {\n    "x": "broken, see #555",\n}\n',
    )
    assert mod.validate_no_orphaned_build_deferrals(
        path, "owner/repo", lookup=lambda issue, repo: "OPEN"
    )


def test_validate_closed_issue_deferral_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(c) Deferral whose issue is CLOSED: gate fails with remove message."""
    path = _write_build_all(
        tmp_path,
        'STALENESS_DEFERRALS = {\n    "x": "broken, see #555",\n}\n',
    )
    ok = mod.validate_no_orphaned_build_deferrals(
        path, "owner/repo", lookup=lambda issue, repo: "CLOSED"
    )
    assert ok is False
    err = capsys.readouterr().err
    assert "references closed issue #555" in err
    assert "remove the deferral and commit the now-valid mirror" in err


def test_validate_unknown_state_keeps_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(d) Offline / unknown issue state: kept with a warning, not a hard fail."""
    path = _write_build_all(
        tmp_path,
        'STALENESS_DEFERRALS = {\n    "x": "broken, see #555",\n}\n',
    )
    ok = mod.validate_no_orphaned_build_deferrals(
        path, "owner/repo", lookup=lambda issue, repo: None
    )
    assert ok is True
    err = capsys.readouterr().err
    assert "state could not be resolved" in err
    assert "keeping it" in err


def test_validate_deferral_without_issue_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A deferral that cites no issue is kept but warns it must reference one."""
    path = _write_build_all(
        tmp_path,
        'STALENESS_DEFERRALS = {\n    "x": "broken, no tracker",\n}\n',
    )
    ok = mod.validate_no_orphaned_build_deferrals(
        path, "owner/repo", lookup=lambda issue, repo: "OPEN"
    )
    assert ok is True
    assert "cites no tracking issue" in capsys.readouterr().err


def test_validate_mixed_open_and_closed_fails_on_closed(tmp_path: Path) -> None:
    """One OPEN and one CLOSED deferral: the CLOSED one fails the gate."""
    path = _write_build_all(
        tmp_path,
        "STALENESS_DEFERRALS = {\n"
        '    "a": "see #100",\n'
        "}\n"
        "STALENESS_EXEMPTIONS = [\n"
        "    # see #200\n"
        '    "b",\n'
        "]\n",
    )
    states = {100: "OPEN", 200: "CLOSED"}
    ok = mod.validate_no_orphaned_build_deferrals(
        path, "owner/repo", lookup=lambda issue, repo: states[issue]
    )
    assert ok is False


def test_validate_missing_build_all_raises(tmp_path: Path) -> None:
    """A missing build_all.py raises FileNotFoundError for a config-error exit."""
    with pytest.raises(FileNotFoundError):
        mod.validate_no_orphaned_build_deferrals(
            tmp_path / "nope.py", "owner/repo", lookup=lambda issue, repo: "OPEN"
        )


def test_validate_relative_traversal_path_rejected() -> None:
    """A relative build_all path that escapes the repo root is rejected (CWE-22).

    The lookup stub raises if reached, proving the traversal is refused before any
    gh call: the path check fails closed at the boundary, not over the network.
    """

    def fail_if_called(issue: int, repo: str) -> str | None:
        raise AssertionError("lookup must not run for a rejected traversal path")

    with pytest.raises(ValueError, match="escapes repo root"):
        mod.validate_no_orphaned_build_deferrals(
            Path("../../etc/passwd"), "owner/repo", lookup=fail_if_called
        )


def test_resolve_within_repo_anchors_relative_to_repo_root() -> None:
    """A safe relative path resolves under the repo root, not the cwd."""
    resolved = mod._resolve_within_repo(Path("build/scripts/build_all.py"))
    assert resolved == mod._REPO_ROOT / "build" / "scripts" / "build_all.py"


# --- CLI -------------------------------------------------------------------


def test_main_returns_zero_for_clean_build_all(tmp_path: Path) -> None:
    path = _write_build_all(tmp_path, "OWNED = ('src/',)\n")
    assert mod.main(["--build-all", str(path), "--repo", "owner/repo"]) == 0


def test_main_returns_two_for_missing_build_all(tmp_path: Path) -> None:
    rc = mod.main(["--build-all", str(tmp_path / "gone.py"), "--repo", "owner/repo"])
    assert rc == 2


def test_real_build_all_has_no_orphaned_deferrals() -> None:
    """The shipped build_all.py has zero deferrals, so the gate passes offline.

    Uses a lookup stub so the test never touches the network; with no deferral
    blocks the lookup is never called anyway.
    """
    build_all = REPO_ROOT / "build" / "scripts" / "build_all.py"
    assert mod.validate_no_orphaned_build_deferrals(
        build_all, "rjmurillo/ai-agents", lookup=lambda issue, repo: "OPEN"
    )
