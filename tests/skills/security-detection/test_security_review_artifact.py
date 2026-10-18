#!/usr/bin/env python3
"""The security-review gate requires the same review report as the marker validator (issue #6438).

``detect_infrastructure.py`` reimplements the report check because a skill
cannot import a sibling skill's script. The conformance test below runs both
implementations on one table of messages and fails when they disagree.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from tests.validation._review_artifact import (
    BEGIN,
    END,
    commit_marker,
    digest_of,
    report_lines,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"

mod = import_skill_script(
    ".claude/skills/security-detection/detect_infrastructure.py",
    module_name="detect_infrastructure_artifact_under_test",
)


def _load_validator():
    spec = importlib.util.spec_from_file_location("vrm_for_security_artifact", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vrm = _load_validator()
SHA = "a" * 40
OTHER = "b" * 40


def _block(rows: list[str]) -> str:
    return "\n".join(["subject", "", BEGIN, *rows, END, "", "Reviewed-By: x"])


def _case(axes: tuple[str, ...], rows: list[str], digest: str | None = None):
    return (_block(rows), [digest or digest_of(rows)], SHA, axes)


GOOD = report_lines("analyst,security", SHA)
CASES = {
    "valid": _case(("analyst", "security"), GOOD),
    "partial-on-security-axis": _case(
        ("analyst", "security"), [GOOD[0], "analyst: WARN", "security: PARTIAL"]
    ),
    "security-warn": _case(("security",), [GOOD[0], "security: WARN"]),
    "security-partial": _case(("security",), [GOOD[0], "security: PARTIAL"]),
    "security-compliant": _case(("security",), [GOOD[0], "security: COMPLIANT"]),
    "analyst-warn-security-pass": _case(
        ("analyst", "security"), [GOOD[0], "analyst: WARN", "security: PASS"]
    ),
    "no-block": ("subject", [digest_of(GOOD)], SHA, ("analyst", "security")),
    "no-digest": (_block(GOOD), [], SHA, ("analyst", "security")),
    "bad-digest-format": (_block(GOOD), ["sha256:xyz"], SHA, ("analyst", "security")),
    "wrong-digest": _case(("analyst", "security"), GOOD, digest_of(["other"])),
    "wrong-sha": _case(("analyst", "security"), report_lines("analyst,security", OTHER)),
    "missing-axis": _case(("analyst", "security"), report_lines("analyst", SHA)),
    "extra-axis": _case(("analyst",), GOOD),
    "failing-row": _case(("analyst", "security"), [GOOD[0], "analyst: PASS", "security: FAIL"]),
    "duplicate-row": _case(("analyst",), [*report_lines("analyst", SHA), "analyst: PASS"]),
    "junk-line": _case(("analyst",), [*report_lines("analyst", SHA), "junk"]),
    "two-blocks": (
        _block(GOOD) + "\n" + _block(GOOD),
        [digest_of(GOOD)],
        SHA,
        ("analyst", "security"),
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_both_implementations_agree(name: str) -> None:
    message, digests, parent, axes = CASES[name]
    canonical_failure = vrm.check_review_artifact(message, digests, parent, axes)
    assert mod.check_review_artifact(message, digests, parent, axes) is (canonical_failure is None)


def test_the_valid_case_is_accepted_by_both() -> None:
    message, digests, parent, axes = CASES["valid"]
    assert vrm.check_review_artifact(message, digests, parent, axes) is None
    assert mod.check_review_artifact(message, digests, parent, axes) is True


def test_constants_match_the_validator() -> None:
    assert mod.REPORT_BEGIN == vrm.REPORT_BEGIN
    assert mod.REPORT_END == vrm.REPORT_END
    assert mod.ARTIFACT_TRAILER_KEY == vrm.ARTIFACT_TRAILER_KEY
    assert mod.PASSING_VERDICTS == vrm.PASSING_VERDICTS
    assert mod.SECURITY_PASSING_VERDICTS == vrm.SECURITY_PASSING_VERDICTS
    assert mod.SECURITY_AXIS == vrm.SECURITY_AXIS


@pytest.mark.parametrize("verdict", ["WARN", "PARTIAL"])
def test_a_security_row_with_an_open_finding_does_not_back_a_marker(verdict: str) -> None:
    """Issue #6506: WARN and PARTIAL pass other axes but never the security axis."""
    message, digests, parent, axes = _case(("security",), [GOOD[0], f"security: {verdict}"])
    assert mod.check_review_artifact(message, digests, parent, axes) is False
    failure = vrm.check_review_artifact(message, digests, parent, axes)
    assert failure is not None
    assert "security" in failure


@pytest.mark.parametrize("verdict", ["PASS", "COMPLIANT"])
def test_a_clean_security_row_backs_a_marker(verdict: str) -> None:
    message, digests, parent, axes = _case(("security",), [GOOD[0], f"security: {verdict}"])
    assert mod.check_review_artifact(message, digests, parent, axes) is True
    assert vrm.check_review_artifact(message, digests, parent, axes) is None


def test_a_warn_on_a_non_security_axis_still_backs_a_marker() -> None:
    message, digests, parent, axes = CASES["analyst-warn-security-pass"]
    assert mod.check_review_artifact(message, digests, parent, axes) is True
    assert vrm.check_review_artifact(message, digests, parent, axes) is None


# find_security_review_marker (real git) ---------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # subprocess-encoding: strict-ok
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "code")
    return tmp_path


def test_bare_security_trailer_is_rejected(repo: Path) -> None:
    """The issue repro: a typed trailer with no report must not satisfy the gate."""
    tip = _git(repo, "rev-parse", "HEAD")
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "self review",
        "--trailer",
        f"Reviewed-By: /review@security on {tip}",
    )
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is False
    assert "no valid review report" in detail


def test_security_marker_with_report_is_accepted(repo: Path) -> None:
    tip = _git(repo, "rev-parse", "HEAD")
    commit_marker(repo, "analyst,security", tip)
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is True
    assert tip[:12] in detail


def test_security_marker_with_altered_report_is_rejected(repo: Path) -> None:
    tip = _git(repo, "rev-parse", "HEAD")
    rows = report_lines("analyst,security", tip)
    commit_marker(repo, "analyst,security", tip, report=rows, digest=digest_of(rows[:-1]))
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is False
    assert "no valid review report" in detail
