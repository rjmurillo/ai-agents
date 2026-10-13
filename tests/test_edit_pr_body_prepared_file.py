"""edit_pr_body.py reads --body-file only from a prepared private file (#6429)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.github_core.api import RepoInfo

_PR_DIR = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
_MOCK_REPO = RepoInfo(owner="testowner", repo="testrepo")


def _load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, _PR_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


_edit = _load("edit_pr_body", "_edit_prepared_edit_pr_body")
_prepare = _load("prepare_pr_body", "_edit_prepared_prepare_pr_body")


def _run(tmp_path: Path, body_file: str, *extra: str) -> tuple[int, MagicMock, MagicMock]:
    """Run main() against tmp_path as the repo root; return (rc, update, fetch)."""
    argv = ["--pull-request", "42", "--body-file", body_file, "--output-format", "json", *extra]
    with (
        patch.object(_edit, "assert_gh_authenticated"),
        patch.object(_edit, "resolve_repo_params", return_value=_MOCK_REPO),
        patch.object(_edit, "get_repo_root", return_value=tmp_path),
        patch.object(_edit, "fetch_current_body", return_value="old body") as fetch,
        patch.object(_edit, "update_body") as update,
    ):
        rc = _edit.main(argv)
    return rc, update, fetch


def _prepared(tmp_path: Path, content: str) -> str:
    relative = _prepare.prepare_pr_body(tmp_path)
    (tmp_path / relative).write_text(content, encoding="utf-8")
    return relative.as_posix()


def test_prepared_file_body_is_published(tmp_path: Path) -> None:
    relative = _prepared(tmp_path, "Fixes #1\nreal body")

    rc, update, fetch = _run(tmp_path, relative)

    assert rc == 0
    update.assert_called_once_with("testowner", "testrepo", 42, "Fixes #1\nreal body")


def test_fixed_name_file_in_scratch_is_refused(tmp_path: Path) -> None:
    scratch = tmp_path / ".project-toolkit" / "scratch"
    scratch.mkdir(parents=True)
    (scratch / "body.md").write_text("another session's body", encoding="utf-8")

    rc, update, fetch = _run(tmp_path, ".project-toolkit/scratch/body.md")

    assert rc == 2
    update.assert_not_called()
    fetch.assert_not_called()


def test_refusal_message_names_the_allocator(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc, update, fetch = _run(tmp_path, "body.md")

    error = json.loads(capsys.readouterr().out)["Error"]
    assert rc == 2
    assert error["Type"] == "InvalidParams"
    assert "--prepare-body-file" in error["Message"]


def test_absolute_path_outside_scratch_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "body.md"
    outside.write_text("shared scratchpad body", encoding="utf-8")

    rc, update, fetch = _run(tmp_path, str(outside))

    assert rc == 2
    update.assert_not_called()


def test_group_readable_prepared_file_is_refused(tmp_path: Path) -> None:
    relative = _prepared(tmp_path, "body")
    os.chmod(tmp_path / relative, 0o644)

    rc, update, fetch = _run(tmp_path, relative)

    assert rc == 2
    update.assert_not_called()


def test_unreplaced_placeholder_is_refused(tmp_path: Path) -> None:
    relative = _prepare.prepare_pr_body(tmp_path).as_posix()

    rc, update, fetch = _run(tmp_path, relative)

    assert rc == 2
    update.assert_not_called()


def test_missing_prepared_file_is_refused(tmp_path: Path) -> None:
    rc, update, fetch = _run(tmp_path, ".project-toolkit/scratch/pr-body-deadbeef.md")

    assert rc == 2
    update.assert_not_called()


def test_non_utf8_prepared_file_is_refused(tmp_path: Path) -> None:
    relative = _prepared(tmp_path, "")
    (tmp_path / relative).write_bytes(b"\xff\xfe\x00bad")

    rc, update, fetch = _run(tmp_path, relative)

    assert rc == 2
    update.assert_not_called()


def test_unresolvable_repo_root_is_refused(tmp_path: Path) -> None:
    argv = ["--pull-request", "42", "--body-file", "x.md", "--output-format", "json"]
    with (
        patch.object(_edit, "assert_gh_authenticated"),
        patch.object(_edit, "resolve_repo_params", return_value=_MOCK_REPO),
        patch.object(_edit, "get_repo_root", return_value=None),
        patch.object(_edit, "update_body") as update,
    ):
        rc = _edit.main(argv)

    assert rc == 2
    update.assert_not_called()


def test_prepared_file_dry_run_does_not_write(tmp_path: Path) -> None:
    relative = _prepared(tmp_path, "dry body")

    rc, update, fetch = _run(tmp_path, relative, "--dry-run")

    assert rc == 0
    update.assert_not_called()


def test_inline_body_still_needs_no_prepared_file() -> None:
    with (
        patch.object(_edit, "assert_gh_authenticated"),
        patch.object(_edit, "resolve_repo_params", return_value=_MOCK_REPO),
        patch.object(_edit, "get_repo_root") as root,
        patch.object(_edit, "fetch_current_body", return_value="old"),
        patch.object(_edit, "update_body") as update,
    ):
        rc = _edit.main(["--pull-request", "42", "--body", "inline", "--output-format", "json"])

    assert rc == 0
    root.assert_not_called()
    update.assert_called_once_with("testowner", "testrepo", 42, "inline")


def test_script_loads_prepare_module_under_isolated_mode() -> None:
    """python -I drops the script directory from sys.path; the sibling loads by path."""
    result = subprocess.run(
        [sys.executable, "-I", str(_PR_DIR / "edit_pr_body.py"), "--help"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--prepare-body-file" in "".join(result.stdout.split())
