"""The ``security_review`` object and stderr lines carry a typed state and reason.

Issue #5636, decision D17 item 2. ``detect_infrastructure.py`` cannot import the
repository's ``evidence.py`` (it ships as a self-contained skill), so it mirrors
the vocabulary. These tests pin what each path reports. The exit codes are
covered in ``test_security_review_marker.py`` and must not change.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/security-detection/detect_infrastructure.py",
    module_name="detect_infrastructure_typed_under_test",
)

CRITICAL_FILE = ".github/workflows/ci.yml"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
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
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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


def _marker(repo: Path, axes: str = "analyst,security", sha: str | None = None) -> str:
    tip = _git(repo, "rev-parse", "HEAD")
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "review: /review PASS marker",
        "--trailer",
        f"Reviewed-By: /review@{axes} on {sha or tip}",
    )
    return tip


def _result(risk: str) -> dict[str, Any]:
    return {"findings": [], "highest_risk": risk, "file_count": 1}


def _run_main(monkeypatch: pytest.MonkeyPatch, repo: Path, *extra: str) -> int:
    argv = ["detect_infrastructure.py", "--repo-root", str(repo), "--files", CRITICAL_FILE, *extra]
    monkeypatch.setattr(sys, "argv", argv)
    return int(mod.main())


# typed result on the security_review object (issue #5636) -----------------------


@pytest.mark.parametrize("risk", ["none", "high"])
def test_non_critical_is_a_typed_skip(risk: str, tmp_path: Path) -> None:
    result = _result(risk)
    mod.enforce_security_review(result, "HEAD", tmp_path)
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("SKIP", "policy.exempt")


def test_a_bound_marker_is_a_pass_with_no_reason(repo: Path) -> None:
    _marker(repo)
    result = _result("critical")
    mod.enforce_security_review(result, "HEAD", repo)
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("PASS", "")


def test_a_missing_marker_is_a_typed_fail(repo: Path) -> None:
    result = _result("critical")
    mod.enforce_security_review(result, "HEAD", repo)
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("FAIL", "violations.found")


def test_an_unresolvable_ref_is_a_typed_blocked_lookup_failure(tmp_path: Path) -> None:
    result = _result("critical")
    assert mod.enforce_security_review(result, "no-such-ref", tmp_path) == 3
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("BLOCKED", "lookup.failed")


def test_a_missing_git_binary_is_blocked_with_tool_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    result = _result("critical")
    assert mod.enforce_security_review(result, "HEAD", tmp_path) == 3
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("BLOCKED", "tool.absent")


def test_a_git_timeout_is_blocked_with_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise mod.subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(mod.subprocess, "run", boom)
    result = _result("critical")
    assert mod.enforce_security_review(result, "HEAD", tmp_path) == 3
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("BLOCKED", "timeout")


def test_undecodable_git_output_is_unknown_with_output_malformed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    result = _result("critical")
    assert mod.enforce_security_review(result, "HEAD", tmp_path) == 3
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("UNKNOWN", "output.malformed")


def test_a_spawn_failure_is_blocked_with_tool_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise PermissionError("git not executable")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    result = _result("critical")
    assert mod.enforce_security_review(result, "HEAD", tmp_path) == 3
    review = result["security_review"]
    assert (review["state"], review["reason"]) == ("BLOCKED", "tool.absent")


def test_a_non_critical_push_prints_a_typed_skip_on_stderr(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "detect_infrastructure.py",
        "--repo-root",
        str(repo),
        "--files",
        "README.md",
        "--require-security-review",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    rc = int(mod.main())

    err = capsys.readouterr().err
    assert rc == 0
    assert err.startswith("[SKIP] detect_infrastructure reason=policy.exempt scope=")


def test_the_default_invocation_prints_no_typed_skip(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["detect_infrastructure.py", "--repo-root", str(repo), "--files", "README.md"]
    )

    assert int(mod.main()) == 0
    assert capsys.readouterr().err == ""


def test_json_mode_prints_no_typed_skip_line(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "detect_infrastructure.py",
        "--repo-root",
        str(repo),
        "--files",
        "README.md",
        "--require-security-review",
        "--json",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    assert int(mod.main()) == 0
    assert capsys.readouterr().err == ""


def test_the_blocked_stderr_line_is_typed_and_names_the_reason(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run_main(monkeypatch, repo, "--require-security-review", "--ref", "no-such-ref")
    first = capsys.readouterr().err.splitlines()[0]
    assert rc == 3
    assert first.startswith("[BLOCKED] detect_infrastructure reason=lookup.failed scope=")


def test_the_fail_stderr_line_is_typed_and_names_the_reason(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run_main(monkeypatch, repo, "--require-security-review")
    first = capsys.readouterr().err.splitlines()[0]
    assert rc == 1
    assert first.startswith("[FAIL] detect_infrastructure reason=violations.found scope=")
