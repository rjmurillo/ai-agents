#!/usr/bin/env python3
"""Tests for ``--require-security-review`` in detect_infrastructure.py (issue #5636, D9).

The intended exception is a CRITICAL change whose HEAD is a ``/review`` marker
commit binding the security axis to its parent. The forbidden silent pass is a
CRITICAL change with no marker, a stale marker, a marker without the security
axis, a marker that changes files, or a git failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/security-detection/detect_infrastructure.py",
    module_name="detect_infrastructure_marker_under_test",
)

CRITICAL_FILE = ".github/workflows/ci.yml"
SHA_A = "a" * 40


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


# find_security_review_marker (real git) ---------------------------------------


def test_marker_binding_parent_with_security_axis_is_satisfied(repo: Path) -> None:
    tip = _marker(repo)
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is True
    assert tip[:12] in detail


def test_new_commit_after_marker_invalidates_it(repo: Path) -> None:
    _marker(repo)
    (repo / "b.txt").write_text("two", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "more code")
    ok, _ = mod.find_security_review_marker("HEAD", repo)
    assert ok is False


def test_marker_naming_a_different_sha_is_rejected(repo: Path) -> None:
    _marker(repo, sha=SHA_A)
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is False
    assert "no 'Reviewed-By" in detail


def test_marker_without_security_axis_is_rejected(repo: Path) -> None:
    _marker(repo, axes="analyst,qa")
    ok, _ = mod.find_security_review_marker("HEAD", repo)
    assert ok is False


def test_security_substring_axis_is_not_security(repo: Path) -> None:
    _marker(repo, axes="analyst,security-scan")
    ok, _ = mod.find_security_review_marker("HEAD", repo)
    assert ok is False


def test_marker_that_changes_files_is_rejected(repo: Path) -> None:
    tip = _git(repo, "rev-parse", "HEAD")
    (repo / "b.txt").write_text("two", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "x", "--trailer", f"Reviewed-By: /review@security on {tip}")
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is False
    assert "changes files" in detail


def test_plain_commit_without_trailer_is_rejected(repo: Path) -> None:
    ok, _ = mod.find_security_review_marker("HEAD", repo)
    assert ok is False


def test_malformed_trailer_is_rejected(repo: Path) -> None:
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "m",
        "--trailer",
        "Reviewed-By: /review@security on not-a-sha",
    )
    ok, _ = mod.find_security_review_marker("HEAD", repo)
    assert ok is False


def test_root_commit_has_no_parent_and_is_rejected(repo: Path) -> None:
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is False
    assert "0 parents" in detail


def test_merge_commit_is_rejected(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "s.txt").write_text("s", encoding="utf-8")
    _git(repo, "add", "s.txt")
    _git(repo, "commit", "-q", "-m", "side")
    _git(repo, "checkout", "-q", "main")
    (repo / "m.txt").write_text("m", encoding="utf-8")
    _git(repo, "add", "m.txt")
    _git(repo, "commit", "-q", "-m", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "side")
    ok, detail = mod.find_security_review_marker("HEAD", repo)
    assert ok is False
    assert "2 parents" in detail


def test_option_like_ref_raises(repo: Path) -> None:
    with pytest.raises(mod.GitReadError, match="must not start with"):
        mod.find_security_review_marker("--all", repo)


def test_unknown_ref_raises(repo: Path) -> None:
    with pytest.raises(mod.GitReadError):
        mod.find_security_review_marker("no-such-ref", repo)


# _git failure modes (mocked I/O) ------------------------------------------------


def test_git_missing_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    with pytest.raises(mod.GitReadError, match="not found"):
        mod._git(["status"], tmp_path)


def test_git_timeout_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(mod.subprocess, "run", boom)
    with pytest.raises(mod.GitReadError, match="timed out"):
        mod._git(["log"], tmp_path)


def test_git_bad_utf8_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    with pytest.raises(mod.GitReadError, match="UTF-8"):
        mod._git(["log"], tmp_path)


def test_git_nonzero_exit_raises_with_stderr(tmp_path: Path) -> None:
    with pytest.raises(mod.GitReadError, match="failed"):
        mod._git(["rev-parse", "--verify", "nope"], tmp_path)


# enforce_security_review --------------------------------------------------------


def _result(risk: str) -> dict[str, object]:
    return {"findings": [], "highest_risk": risk, "file_count": 1}


@pytest.mark.parametrize("risk", ["none", "high"])
def test_non_critical_does_not_require_marker(risk: str, tmp_path: Path) -> None:
    result = _result(risk)
    assert mod.enforce_security_review(result, "HEAD", tmp_path) == 0
    assert result["security_review"]["required"] is False


def test_critical_without_marker_exits_1(repo: Path) -> None:
    result = _result("critical")
    assert mod.enforce_security_review(result, "HEAD", repo) == 1
    assert result["security_review"]["satisfied"] is False


def test_critical_with_marker_exits_0(repo: Path) -> None:
    _marker(repo)
    result = _result("critical")
    assert mod.enforce_security_review(result, "HEAD", repo) == 0
    assert result["security_review"]["satisfied"] is True


def test_critical_with_git_failure_exits_3(tmp_path: Path) -> None:
    result = _result("critical")
    assert mod.enforce_security_review(result, "no-such-ref", tmp_path) == 3
    assert result["security_review"]["satisfied"] is False


# main() CLI ---------------------------------------------------------------------


def _run_main(monkeypatch: pytest.MonkeyPatch, repo: Path, *extra: str) -> int:
    argv = ["detect_infrastructure.py", "--repo-root", str(repo), "--files", CRITICAL_FILE, *extra]
    monkeypatch.setattr(sys, "argv", argv)
    return int(mod.main())


def test_main_critical_without_flag_still_exits_0(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    assert _run_main(monkeypatch, repo) == 0


def test_main_critical_with_flag_and_no_marker_exits_1(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(monkeypatch, repo, "--require-security-review") == 1
    err = capsys.readouterr().err
    assert "[FAIL]" in err
    assert "/review" in err


def test_main_critical_with_flag_and_marker_exits_0(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    _marker(repo)
    assert _run_main(monkeypatch, repo, "--require-security-review") == 0


def test_main_git_failure_with_flag_exits_3_and_says_blocked(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run_main(monkeypatch, repo, "--require-security-review", "--ref", "no-such-ref")
    assert rc == 3
    assert "[BLOCKED]" in capsys.readouterr().err


def test_main_json_mode_carries_exit_code_and_review_state(
    monkeypatch: pytest.MonkeyPatch, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run_main(monkeypatch, repo, "--require-security-review", "--json")
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["security_review"] == {
        "required": True,
        "satisfied": False,
        "detail": payload["security_review"]["detail"],
    }


def test_main_no_findings_with_flag_exits_0(
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
    assert mod.main() == 0
    assert "No infrastructure" in capsys.readouterr().out


def test_main_high_finding_with_flag_exits_0(monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    argv = [
        "detect_infrastructure.py",
        "--repo-root",
        str(repo),
        "--files",
        "Dockerfile",
        "--require-security-review",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert mod.main() == 0


def test_lefthook_pre_push_job_requires_marker_and_pre_commit_does_not() -> None:
    import yaml

    root = Path(__file__).resolve().parents[3]
    config = yaml.safe_load((root / "lefthook.yml").read_text(encoding="utf-8"))

    def jobs(stage: str) -> list[dict[str, object]]:
        found: list[dict[str, object]] = []

        def walk(items: list[dict[str, object]]) -> None:
            for item in items:
                if item.get("name") == "infrastructure-advisory":
                    found.append(item)
                group = item.get("group")
                if isinstance(group, dict):
                    walk(group.get("jobs", []))

        walk(config[stage]["jobs"])
        return found

    assert [j["run"] for j in jobs("pre-push")]
    assert all("--require-security-review" in str(j["run"]) for j in jobs("pre-push"))
    assert jobs("pre-commit")
    assert all("--require-security-review" not in str(j["run"]) for j in jobs("pre-commit"))
