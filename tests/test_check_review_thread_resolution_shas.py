"""Tests for check_review_thread_resolution_shas.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_mod = _import_script("check_review_thread_resolution_shas")
extract_shas = _mod.extract_shas
check_ancestor = _mod.check_ancestor
build_report = _mod.build_report
main = _mod.main


def _thread(thread_id: str, resolved: bool, *bodies: str) -> dict:
    return {
        "id": thread_id,
        "isResolved": resolved,
        "path": "src/app.py",
        "line": 12,
        "comments": {
            "totalCount": len(bodies),
            "nodes": [
                {
                    "id": f"C{index}",
                    "databaseId": index,
                    "body": body,
                    "author": {"login": "agent"},
                    "createdAt": f"2026-08-03T00:00:{index:02d}Z",
                }
                for index, body in enumerate(bodies, start=1)
            ],
        },
    }


def test_extracts_short_and_full_shas() -> None:
    full = "a" * 40
    assert extract_shas(f"Fixed in abc1234 and {full}") == ["abc1234", full]


def test_ignores_shas_inside_fenced_code() -> None:
    body = "Fixed in abc1234.\n```\ngit show deadbee\n```"
    assert extract_shas(body) == ["abc1234"]


def test_ignores_unresolved_threads() -> None:
    with patch("check_review_thread_resolution_shas.check_ancestor") as check:
        report = build_report(
            "o",
            "r",
            1,
            "b" * 40,
            [_thread("T1", False, "Fixed in abc1234")],
            True,
            ".",
        )
    assert report["sha_reference_count"] == 0
    check.assert_not_called()


def test_unreachable_sha_blocks_report() -> None:
    with patch(
        "check_review_thread_resolution_shas.check_ancestor",
        return_value=(False, "unreachable"),
    ):
        report = build_report(
            "o",
            "r",
            1,
            "b" * 40,
            [_thread("T1", True, "Fixed in abc1234")],
            True,
            ".",
        )
    assert report["sha_reference_count"] == 1
    assert report["reachable_count"] == 0
    assert report["unreachable_count"] == 1
    assert report["invalid_count"] == 0


def test_invalid_sha_blocks_report() -> None:
    with patch(
        "check_review_thread_resolution_shas.check_ancestor",
        return_value=(False, "invalid"),
    ):
        report = build_report(
            "o",
            "r",
            1,
            "b" * 40,
            [_thread("T1", True, "Fixed in deadbee")],
            True,
            ".",
        )
    assert report["invalid_count"] == 1
    assert report["references"][0]["status"] == "invalid"


def test_uses_latest_comment_only() -> None:
    with patch(
        "check_review_thread_resolution_shas.check_ancestor",
        return_value=(True, "reachable"),
    ) as check:
        report = build_report(
            "o",
            "r",
            1,
            "b" * 40,
            [_thread("T1", True, "old abc1234", "new def5678")],
            True,
            ".",
        )
    assert report["sha_reference_count"] == 1
    assert report["references"][0]["sha"] == "def5678"
    check.assert_called_once_with("def5678", "b" * 40, ".")


def test_incomplete_comment_pagination_fails_closed() -> None:
    thread = _thread("T1", True, "Fixed in abc1234")
    thread["comments"]["totalCount"] = 2
    with patch(
        "check_review_thread_resolution_shas.check_ancestor",
        return_value=(True, "reachable"),
    ):
        report = build_report("o", "r", 1, "b" * 40, [thread], False, ".")
    assert report["success"] is False
    assert report["fetched_pages_complete"] is False


def test_check_ancestor_classifies_git_exit_codes() -> None:
    with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
        assert check_ancestor("abc1234", "b" * 40, ".") == (True, "reachable")
    with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
        assert check_ancestor("abc1234", "b" * 40, ".") == (False, "unreachable")
    with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 128)):
        assert check_ancestor("abc1234", "b" * 40, ".") == (False, "invalid")


def test_main_exits_zero_and_emits_raw_json(capsys) -> None:
    with patch("check_review_thread_resolution_shas.assert_gh_authenticated"), \
         patch(
             "check_review_thread_resolution_shas.resolve_repo_params",
             return_value=type("Repo", (), {"owner": "o", "repo": "r"})(),
         ), \
         patch(
             "check_review_thread_resolution_shas.fetch_review_threads",
             return_value=("b" * 40, [_thread("T1", True, "Fixed in abc1234")], True),
         ), \
         patch(
             "check_review_thread_resolution_shas.check_ancestor",
             return_value=(True, "reachable"),
         ):
        rc = main(["--pull-request", "99"])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["sha_reference_count"] == 1
    assert output["unreachable_count"] == 0
    assert output["invalid_count"] == 0


def test_pr_review_config_contains_resolution_sha_gate() -> None:
    config = (_ROOT / ".claude" / "commands" / "pr-review-config.yaml").read_text()
    assert "check_review_thread_resolution_shas.py --pull-request {pr}" in config
    assert "stdout-json.unreachable_count == 0" in config
