"""Tests for the artifact allowlist and argument validation in scripts/ci/open_bot_pr.py.

The publish job holds a write token, so the downloaded artifact is untrusted
input. `--artifact-dir` copies only the named `--path` entries out of it.
These tests use real files in a temp directory and fake only git and gh.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from open_bot_pr import import_artifact, main
finally:
    sys.path[:] = _original_path

_STATS = ".serena/memories/pr-review/stats.md"
_REPORT = ".project-toolkit/metrics/report.md"


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


def _artifact(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "artifact"
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def test_named_files_are_copied_to_their_repository_paths(tmp_path: Path, checkout: Path) -> None:
    root = _artifact(tmp_path, {_STATS: "stats", _REPORT: "report"})
    assert import_artifact(str(root), [_STATS, _REPORT]) == [_STATS, _REPORT]
    assert (checkout / _STATS).read_text(encoding="utf-8") == "stats"
    assert (checkout / _REPORT).read_text(encoding="utf-8") == "report"


def test_one_file_upload_layout_is_found_by_basename(tmp_path: Path, checkout: Path) -> None:
    root = _artifact(tmp_path, {"stats.md": "stats"})
    assert import_artifact(str(root), [_STATS, _REPORT]) == [_STATS]
    assert (checkout / _STATS).read_text(encoding="utf-8") == "stats"
    assert not (checkout / _REPORT).exists()


def test_files_outside_the_allowlist_are_never_written(tmp_path: Path, checkout: Path) -> None:
    root = _artifact(
        tmp_path,
        {
            _STATS: "stats",
            "scripts/ci/open_bot_pr.py": "print('owned')",
            "scripts/ci/json.py": "owned = True",
            ".git/hooks/pre-commit": "#!/bin/sh\nexit 0\n",
        },
    )
    import_artifact(str(root), [_STATS])
    assert (checkout / _STATS).exists()
    assert not (checkout / "scripts").exists()
    assert not (checkout / ".git").exists()


def test_a_symlink_source_is_skipped_not_followed(tmp_path: Path, checkout: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    root = tmp_path / "artifact"
    (root / ".serena/memories/pr-review").mkdir(parents=True)
    (root / _STATS).symlink_to(secret)
    assert import_artifact(str(root), [_STATS]) == []
    assert not (checkout / _STATS).exists()


def test_a_symlinked_directory_that_escapes_the_artifact_is_refused(
    tmp_path: Path, checkout: Path
) -> None:
    outside = tmp_path / "outside"
    (outside / "memories/pr-review").mkdir(parents=True)
    (outside / "memories/pr-review/stats.md").write_text("outside", encoding="utf-8")
    root = tmp_path / "artifact"
    root.mkdir()
    (root / ".serena").symlink_to(outside)
    with pytest.raises(RuntimeError, match="escapes"):
        import_artifact(str(root), [_STATS])
    assert not (checkout / _STATS).exists()


def test_a_symlink_destination_is_refused(tmp_path: Path, checkout: Path) -> None:
    target = tmp_path / "victim.txt"
    target.write_text("victim", encoding="utf-8")
    dest = checkout / _STATS
    dest.parent.mkdir(parents=True)
    dest.symlink_to(target)
    root = _artifact(tmp_path, {_STATS: "stats"})
    with pytest.raises(RuntimeError, match="symlink"):
        import_artifact(str(root), [_STATS])
    assert target.read_text(encoding="utf-8") == "victim"


def test_a_missing_artifact_directory_imports_nothing(tmp_path: Path, checkout: Path) -> None:
    assert import_artifact(str(tmp_path / "absent"), [_STATS]) == []


def test_main_exits_git_failed_when_the_import_hits_a_symlink_destination(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "victim.txt"
    target.write_text("victim", encoding="utf-8")
    dest = checkout / "stats.md"
    dest.symlink_to(target)
    root = _artifact(tmp_path, {"stats.md": "stats"})
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = main(_args("stats.md", artifact_dir=str(root)))
    assert rc == 1
    assert target.read_text(encoding="utf-8") == "victim"
    assert not [c for c in calls if c[0] == "gh"]


def _args(*paths: str, artifact_dir: str | None = None, branch: str = "automation/x") -> list[str]:
    args = ["--user-name", "bot", "--user-email", "bot@example.com"]
    for path in paths:
        args += ["--path", path]
    args += ["--message", "chore: update", "--branch", branch, "--issue", "1"]
    if artifact_dir:
        args += ["--artifact-dir", artifact_dir]
    return args


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.md", "a/../../b.md", ""])
def test_a_path_outside_the_checkout_is_a_usage_error(path: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(_args(path))
    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    "branch",
    [
        "automation/a..b",
        "automation/x.lock",
        "automation//x",
        "automation/x.",
        "automation/a/.b",
        "automation/x.lock/y",
    ],
)
def test_a_branch_name_git_would_reject_is_a_usage_error(branch: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(_args("a.md", branch=branch))
    assert exit_info.value.code == 2


def test_gh_pr_list_reads_stdout_only_so_a_stderr_warning_cannot_break_the_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[:3] == ["gh", "pr", "list"]:
            seen.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, "[]", "warning: update available")
        if argv[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(argv, 0, " M a.md\n")
        return subprocess.CompletedProcess(argv, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert main(_args("a.md")) == 0
    assert seen["stderr"] == subprocess.PIPE


def test_a_file_over_the_size_cap_is_refused(tmp_path: Path, checkout: Path) -> None:
    root = _artifact(tmp_path, {_STATS: "x" * (1024 * 1024 + 1)})
    with pytest.raises(RuntimeError, match="over"):
        import_artifact(str(root), [_STATS])
    assert not (checkout / _STATS).exists()


def test_a_file_that_is_not_utf8_is_refused(tmp_path: Path, checkout: Path) -> None:
    root = tmp_path / "artifact"
    (root / ".serena/memories/pr-review").mkdir(parents=True)
    (root / _STATS).write_bytes(b"\xff\xfe not utf-8 \x80")
    with pytest.raises(RuntimeError, match="UTF-8"):
        import_artifact(str(root), [_STATS])
    assert not (checkout / _STATS).exists()


def test_a_symlinked_destination_directory_is_refused_before_anything_is_created(
    tmp_path: Path, checkout: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (checkout / ".serena").symlink_to(outside)
    root = _artifact(tmp_path, {_STATS: "stats"})
    with pytest.raises(RuntimeError, match="leaves the checkout"):
        import_artifact(str(root), [_STATS])
    assert list(outside.iterdir()) == []


def test_an_io_failure_while_copying_is_reported_not_swallowed(
    tmp_path: Path, checkout: Path
) -> None:
    (checkout / ".serena").write_text("a file where a directory belongs", encoding="utf-8")
    root = _artifact(tmp_path, {_STATS: "stats"})
    with pytest.raises(RuntimeError, match="artifact import failed"):
        import_artifact(str(root), [_STATS])


def test_main_fails_loud_when_the_artifact_holds_none_of_the_named_paths(
    tmp_path: Path,
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _artifact(tmp_path, {"unrelated.txt": "nothing useful"})
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert main(_args("stats.md", artifact_dir=str(root))) == 1
    assert "held none of the named paths" in capsys.readouterr().err
    assert not [c for c in calls if c[0] == "gh"]
    assert not [c for c in calls if c[:2] == ["git", "push"]]


@pytest.mark.parametrize("char", ["\u202e", "\u200b", "\x00", "\x1b", "\ufeff"])
def test_a_file_with_control_or_format_characters_is_refused(
    tmp_path: Path, checkout: Path, char: str
) -> None:
    root = _artifact(tmp_path, {_STATS: f"looks fine{char}but is not"})
    with pytest.raises(RuntimeError, match="control or format"):
        import_artifact(str(root), [_STATS])
    assert not (checkout / _STATS).exists()


def test_tabs_and_newlines_are_allowed(tmp_path: Path, checkout: Path) -> None:
    root = _artifact(tmp_path, {_STATS: "col\tcol\r\nrow\n"})
    assert import_artifact(str(root), [_STATS]) == [_STATS]


def test_the_size_is_checked_before_the_file_is_read(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _artifact(tmp_path, {_STATS: "x" * (1024 * 1024 + 1)})
    reads: list[Path] = []
    real_read = Path.read_bytes

    def spy(self: Path) -> bytes:
        reads.append(self)
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    with pytest.raises(RuntimeError, match="over"):
        import_artifact(str(root), [_STATS])
    assert reads == []


@pytest.mark.parametrize(
    "path", [".git/hooks/pre-commit", ".github/workflows/x.yml", "a/.git/config"]
)
def test_a_path_inside_git_or_github_is_a_usage_error(path: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(_args(path))
    assert exit_info.value.code == 2


@pytest.mark.parametrize("issue", ["", "12a", "1 2", "#12", "\u0661\u0662", "12\n## Changes"])
def test_a_non_numeric_issue_is_a_usage_error(issue: str) -> None:
    args = _args("a.md")
    args[args.index("--issue") + 1] = issue
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    assert exit_info.value.code == 2
