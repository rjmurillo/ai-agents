from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import checks_plugin


def test_workflow_local_run_warns_on_missing_local_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path
    script = repo_root / "scripts" / "validation" / "run_workflow_local_test.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('stub')\n", encoding="utf-8")

    workflow = repo_root / ".github" / "workflows" / "secret.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: secret\n", encoding="utf-8")

    monkeypatch.setattr(checks_plugin, "_resolve_default_base_ref", lambda _root: "origin/main")

    def fake_run_subprocess(args: list[str], *_, **__) -> tuple[int, str, str]:
        if args[:4] == ["git", "-C", str(repo_root), "diff"]:
            return 0, ".github/workflows/secret.yml\n", ""
        return 4, "unrunnable-locally: actionlint passed\n", ""

    monkeypatch.setattr(checks_plugin, "_run_subprocess", fake_run_subprocess)

    assert checks_plugin.validate_workflow_local_run(repo_root) is True

    output = capsys.readouterr().out
    assert "unrunnable-locally: actionlint passed" in output
    assert "workflow local-run auth material unavailable locally" in output


def _git(root: Path, *args: str) -> str:
    """Run a git command in ``root`` with a hermetic identity and return stdout."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def workflow_repo(tmp_path: Path) -> tuple[Path, str]:
    """Isolated git repo with one committed workflow; returns (root, base_sha)."""
    root = tmp_path
    _git(root, "init", "-q")
    _write(root, ".github/workflows/base.yml", "name: base\n")
    _write(root, "README.md", "base\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base_sha = _git(root, "rev-parse", "HEAD").strip()
    return root, base_sha


def test_collect_detects_committed_workflow(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo
    _write(root, ".github/workflows/committed.yml", "name: committed\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "add committed workflow")

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed == [".github/workflows/committed.yml"]


def test_collect_detects_staged_workflow(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo
    _write(root, ".github/workflows/staged.yml", "name: staged\n")
    _git(root, "add", ".github/workflows/staged.yml")

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed is not None
    assert ".github/workflows/staged.yml" in changed


def test_collect_detects_unstaged_workflow(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo
    # Modify a tracked, committed workflow without staging it.
    _write(root, ".github/workflows/base.yml", "name: base\n# edited\n")

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed is not None
    assert ".github/workflows/base.yml" in changed


def test_collect_detects_untracked_workflow(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo
    _write(root, ".github/workflows/untracked.yml", "name: untracked\n")

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed is not None
    assert ".github/workflows/untracked.yml" in changed


def test_collect_drops_deleted_workflow(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo
    _git(root, "rm", "-q", ".github/workflows/base.yml")

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed is not None
    assert ".github/workflows/base.yml" not in changed


def test_collect_dedupes_across_states(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo
    # Commit a change, then stage and further edit the same path so it appears
    # in the committed range, the staged set, and the unstaged set at once.
    _write(root, ".github/workflows/dupe.yml", "name: dupe\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "add dupe")
    _write(root, ".github/workflows/dupe.yml", "name: dupe\n# staged\n")
    _git(root, "add", ".github/workflows/dupe.yml")
    _write(root, ".github/workflows/dupe.yml", "name: dupe\n# staged\n# unstaged\n")

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed is not None
    assert changed.count(".github/workflows/dupe.yml") == 1


def test_collect_ignores_non_workflow_paths(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo
    _write(root, "src/app.py", "print('x')\n")
    _write(root, ".github/workflows/notes.txt", "not a workflow\n")

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed == []


def test_collect_no_changes_returns_empty(workflow_repo: tuple[Path, str]) -> None:
    root, base_sha = workflow_repo

    changed = checks_plugin._collect_changed_workflow_files(root, base_sha)

    assert changed == []


def test_collect_returns_none_when_committed_diff_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_committed(args: list[str], *_: object, **__: object) -> tuple[int, str, str]:
        if "diff" in args and "nope...HEAD" in args:
            return 128, "", "bad revision"
        return 0, "", ""

    monkeypatch.setattr(checks_plugin, "_run_subprocess", fail_committed)

    assert checks_plugin._collect_changed_workflow_files(tmp_path, "nope") is None
