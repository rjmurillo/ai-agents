"""Tests for the review report that backs a ``Reviewed-By`` marker (issue #6438).

A bare ``Reviewed-By`` trailer is a sentence any agent can type. The validator
now also requires the marker commit body to carry the review report and the
``Review-Artifact`` trailer to hold that report's digest. Every git case below
runs against a real temporary repository so the trailer and message readers are
exercised for real.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from tests.validation._review_artifact import (
    BEGIN,
    END,
    commit_marker,
    commit_message,
    digest_of,
    marker_message,
    report_lines,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCES_DIR = REPO_ROOT / ".claude" / "skills" / "review" / "references"
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"
SHA = "a" * 40
OTHER_SHA = "b" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_review_marker_artifact", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vrm = _load_module()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # subprocess-encoding: strict-ok
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-q", "-m", "feat: initial commit")
    return root


def _validate(repo: Path):
    return vrm.validate_ref("HEAD", repo, references_dir=REFERENCES_DIR)


def _tip(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


# --- the forgery from issue #6438 ------------------------------------------


def test_bare_trailer_marker_is_rejected(repo: Path) -> None:
    """The issue repro: an empty commit with only a typed trailer no longer passes."""
    tip = _tip(repo)
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: self",
        "--trailer",
        f"Reviewed-By: /review@security on {tip}",
    )
    outcome = _validate(repo)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "no valid review artifact" in outcome.message
    assert "exactly one" in outcome.message


def test_bare_trailer_cli_exits_one(repo: Path) -> None:
    tip = _tip(repo)
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: self",
        "--trailer",
        f"Reviewed-By: /review@security on {tip}",
    )
    result = subprocess.run(  # subprocess-encoding: strict-ok
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--repo-root",
            str(repo),
            "--references-dir",
            str(REFERENCES_DIR),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 1
    assert "[FAIL]" in result.stderr


# --- positive ---------------------------------------------------------------


def test_marker_with_report_and_digest_passes(repo: Path) -> None:
    commit_marker(repo, "analyst,security", _tip(repo))
    outcome = _validate(repo)
    assert outcome.ok is True
    assert outcome.exit_code == 0
    assert outcome.axes == ("analyst", "security")


@pytest.mark.parametrize("verdict", ["PASS", "COMPLIANT", "WARN", "PARTIAL"])
def test_passing_verdicts_are_accepted(repo: Path, verdict: str) -> None:
    tip = _tip(repo)
    commit_marker(repo, "analyst", tip, report=report_lines("analyst", tip, verdict))
    assert _validate(repo).ok is True


def test_digest_survives_trailing_whitespace_and_blank_lines(repo: Path) -> None:
    """Git cleans a message, so the digest ignores trailing space and blank lines."""
    tip = _tip(repo)
    canonical = report_lines("analyst,qa", tip)
    noisy = [canonical[0] + "  ", "", canonical[1], canonical[2] + "\t"]
    commit_marker(repo, "analyst,qa", tip, report=noisy, digest=digest_of(canonical))
    assert _validate(repo).ok is True


def test_digest_option_prints_the_digest_a_marker_accepts(repo: Path, tmp_path: Path) -> None:
    """The writer uses --digest, so its output must be what the validator accepts."""
    tip = _tip(repo)
    rows = report_lines("analyst,security", tip)
    report_file = tmp_path / "report.txt"
    report_file.write_text("\n".join([BEGIN, *rows, END]) + "\n", encoding="utf-8")
    result = subprocess.run(  # subprocess-encoding: strict-ok
        [sys.executable, str(SCRIPT_PATH), "--digest", str(report_file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0
    printed = result.stdout.strip()
    assert printed == digest_of(rows)
    commit_marker(repo, "analyst,security", tip, digest=printed)
    assert _validate(repo).ok is True


def test_a_second_matching_digest_trailer_is_enough(repo: Path) -> None:
    tip = _tip(repo)
    message = marker_message("analyst", tip) + f"Review-Artifact: sha256:{'0' * 64}\n"
    commit_message(repo, message)
    assert _validate(repo).ok is True


# --- negative: digest trailer ----------------------------------------------


def test_missing_digest_trailer_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    message = marker_message("analyst", tip).replace(
        f"Review-Artifact: {digest_of(report_lines('analyst', tip))}\n", ""
    )
    commit_message(repo, message)
    outcome = _validate(repo)
    assert outcome.exit_code == 1
    assert "Review-Artifact" in outcome.message


@pytest.mark.parametrize(
    "bad",
    ["sha256:abc", f"sha256:{'G' * 64}", f"sha256:{'A' * 64}", f"md5:{'a' * 64}", "nonsense"],
)
def test_malformed_digest_is_rejected(repo: Path, bad: str) -> None:
    commit_marker(repo, "analyst", _tip(repo), digest=bad)
    outcome = _validate(repo)
    assert outcome.exit_code == 1
    assert "well-formed" in outcome.message


def test_digest_of_different_text_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    other = digest_of(report_lines("qa", tip))
    commit_marker(repo, "analyst", tip, digest=other)
    outcome = _validate(repo)
    assert outcome.exit_code == 1
    assert "does not match" in outcome.message


def test_report_edited_after_digest_is_rejected(repo: Path) -> None:
    """Changing a verdict row without refreshing the digest fails."""
    tip = _tip(repo)
    original = digest_of(report_lines("analyst,qa", tip))
    edited = report_lines("analyst,qa", tip)
    edited[1] = "analyst: WARN"
    commit_marker(repo, "analyst,qa", tip, report=edited, digest=original)
    assert "does not match" in _validate(repo).message


# --- negative: report shape -------------------------------------------------


def test_missing_report_block_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    digest = digest_of(report_lines("analyst", tip))
    commit_message(
        repo,
        f"review: no report\n\nReviewed-By: /review@analyst on {tip}\nReview-Artifact: {digest}\n",
    )
    outcome = _validate(repo)
    assert outcome.exit_code == 1
    assert "exactly one" in outcome.message


def test_report_without_end_delimiter_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    rows = report_lines("analyst", tip)
    commit_message(
        repo,
        "review: open block\n\n"
        + "\n".join([BEGIN, *rows])
        + f"\n\nReviewed-By: /review@analyst on {tip}\nReview-Artifact: {digest_of(rows)}\n",
    )
    assert _validate(repo).exit_code == 1


def test_two_report_blocks_are_rejected(repo: Path) -> None:
    """Two blocks would let the writer and the reader hash different text."""
    tip = _tip(repo)
    rows = report_lines("analyst", tip)
    block = "\n".join([BEGIN, *rows, END])
    commit_message(
        repo,
        f"review: two blocks\n\n{block}\n\n{block}\n\n"
        f"Reviewed-By: /review@analyst on {tip}\nReview-Artifact: {digest_of(rows)}\n",
    )
    assert "exactly one" in _validate(repo).message


def test_end_before_begin_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    rows = report_lines("analyst", tip)
    commit_message(
        repo,
        f"review: reversed\n\n{END}\n"
        + "\n".join([*rows, BEGIN])
        + f"\n\nReviewed-By: /review@analyst on {tip}\nReview-Artifact: {digest_of(rows)}\n",
    )
    assert _validate(repo).exit_code == 1


def test_report_naming_another_sha_is_rejected(repo: Path) -> None:
    rows = report_lines("analyst", OTHER_SHA)
    commit_marker(repo, "analyst", _tip(repo), report=rows)
    outcome = _validate(repo)
    assert outcome.exit_code == 1
    assert "Reviewed-SHA" in outcome.message


def test_report_without_sha_line_is_rejected(repo: Path) -> None:
    commit_marker(repo, "analyst", _tip(repo), report=["analyst: PASS"])
    assert "Reviewed-SHA" in _validate(repo).message


def test_report_naming_sha_twice_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    commit_marker(
        repo, "analyst", tip, report=[*report_lines("analyst", tip), f"Reviewed-SHA: {tip}"]
    )
    assert "Reviewed-SHA" in _validate(repo).message


def test_report_missing_a_marker_axis_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    commit_marker(repo, "analyst,security", tip, report=report_lines("analyst", tip))
    outcome = _validate(repo)
    assert outcome.exit_code == 1
    assert "exactly the marker axes" in outcome.message


def test_report_with_an_extra_axis_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    commit_marker(repo, "analyst", tip, report=report_lines("analyst,security", tip))
    assert "exactly the marker axes" in _validate(repo).message


def test_report_repeating_an_axis_row_is_rejected(repo: Path) -> None:
    tip = _tip(repo)
    rows = [*report_lines("analyst", tip), "analyst: PASS"]
    commit_marker(repo, "analyst", tip, report=rows)
    assert "exactly the marker axes" in _validate(repo).message


@pytest.mark.parametrize(
    "verdict", ["FAIL", "CRITICAL_FAIL", "UNKNOWN", "REJECTED", "NEEDS_REVIEW"]
)
def test_failing_verdict_row_is_rejected(repo: Path, verdict: str) -> None:
    tip = _tip(repo)
    rows = report_lines("analyst,security", tip)
    rows[2] = f"security: {verdict}"
    commit_marker(repo, "analyst,security", tip, report=rows)
    outcome = _validate(repo)
    assert outcome.exit_code == 1
    assert "non-passing verdict for: security" in outcome.message


@pytest.mark.parametrize(
    "junk", ["free text", "analyst PASS", "analyst: pass", "analyst:PASS", "- analyst: PASS"]
)
def test_junk_report_line_is_rejected(repo: Path, junk: str) -> None:
    tip = _tip(repo)
    commit_marker(repo, "analyst", tip, report=[*report_lines("analyst", tip), junk])
    assert "neither Reviewed-SHA" in _validate(repo).message


def test_axis_error_is_reported_before_artifact_error(repo: Path) -> None:
    """An unknown axis stays an axis failure, whatever the report says."""
    commit_marker(repo, "bogus", _tip(repo))
    assert "invalid axis list" in _validate(repo).message


# --- git read failures ------------------------------------------------------


def test_unreadable_message_is_a_config_error(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit_marker(repo, "analyst", _tip(repo))
    real = vrm._run_git

    def fake(args: list[str], repo_root: Path) -> tuple[int, str, str]:
        if "--format=%B" in args:
            return 128, "", "fatal: bad object"
        return real(args, repo_root)

    monkeypatch.setattr(vrm, "_run_git", fake)
    outcome = _validate(repo)
    assert outcome.exit_code == 2
    assert "fatal: bad object" in outcome.message


def test_unreadable_digest_trailer_is_a_config_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit_marker(repo, "analyst", _tip(repo))
    real = vrm._run_git

    def fake(args: list[str], repo_root: Path) -> tuple[int, str, str]:
        if any("key=Review-Artifact" in arg for arg in args):
            return 128, "", "fatal: trailer failure"
        return real(args, repo_root)

    monkeypatch.setattr(vrm, "_run_git", fake)
    outcome = _validate(repo)
    assert outcome.exit_code == 2
    assert "fatal: trailer failure" in outcome.message


def test_read_commit_message_rejects_option_like_ref(repo: Path) -> None:
    message, error = vrm.read_commit_message("--format=%H", repo)
    assert message is None
    assert error is not None and "must not start with '-'" in error


# --- --digest ---------------------------------------------------------------


def test_digest_option_reports_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert vrm.main(["--digest", str(tmp_path / "absent.txt")]) == 2
    assert "cannot read report file" in capsys.readouterr().err


def test_digest_option_reports_file_without_a_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_file = tmp_path / "report.txt"
    report_file.write_text("no block here\n", encoding="utf-8")
    assert vrm.main(["--digest", str(report_file)]) == 1
    assert "exactly one" in capsys.readouterr().err


def test_digest_option_reports_undecodable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_file = tmp_path / "report.txt"
    report_file.write_bytes(b"\xff\xfe\xfa")
    assert vrm.main(["--digest", str(report_file)]) == 2
    assert "cannot read report file" in capsys.readouterr().err


# --- pure helpers -----------------------------------------------------------


def test_extract_report_drops_blank_lines_and_trailing_space() -> None:
    text = f"subject\n\n{BEGIN}\nline one  \n\nline two\n{END}\n\ntrailer: x\n"
    report, failure = vrm.extract_report(text)
    assert failure is None
    assert report == ["line one", "line two"]


def test_report_digest_matches_independent_hash() -> None:
    rows = report_lines("analyst", SHA)
    assert f"sha256:{vrm.report_digest(rows)}" == digest_of(rows)


def test_check_review_artifact_accepts_matching_inputs() -> None:
    rows = report_lines("analyst,qa", SHA)
    message = "\n".join([BEGIN, *rows, END])
    assert vrm.check_review_artifact(message, [digest_of(rows)], SHA, ("analyst", "qa")) is None


def test_check_review_artifact_uppercase_sha_in_report_matches_lowercase_parent() -> None:
    rows = report_lines("analyst", SHA.upper())
    message = "\n".join([BEGIN, *rows, END])
    assert vrm.check_review_artifact(message, [digest_of(rows)], SHA, ("analyst",)) is None
