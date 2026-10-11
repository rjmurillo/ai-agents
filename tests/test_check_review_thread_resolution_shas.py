"""Tests for check_review_thread_resolution_shas.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import yaml

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


def _completed_process(
    argv: list[str], returncode: int, *, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def _check_ancestor_run(
    *,
    verify_rc: int,
    verify_stdout: str = "",
    merge_base_rc: int | None = None,
    disambiguate_stdout: str = "",
):
    def _run(argv, **kwargs):
        command = [str(part) for part in argv]
        assert command[:3] == ["git", "-C", "."]
        git_args = command[3:]
        if git_args[:2] == ["rev-parse", "--verify"]:
            return _completed_process(command, verify_rc, stdout=verify_stdout)
        if git_args[:2] == ["merge-base", "--is-ancestor"]:
            assert merge_base_rc is not None
            return _completed_process(command, merge_base_rc)
        if git_args[:1] == ["rev-parse"] and any(
            arg.startswith("--disambiguate=") for arg in git_args[1:]
        ):
            return _completed_process(command, 0, stdout=disambiguate_stdout)
        raise AssertionError(f"unexpected subprocess call: {command}")

    return _run


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


def test_ignores_coderabbit_comment_marker() -> None:
    body = "Confirmed in 49f5d79 and 2d9e16f.\n\n<!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 -->"
    assert extract_shas(body) == ["49f5d79", "2d9e16f"]


def test_ignores_multiline_html_comment() -> None:
    full = "b" * 40
    body = f"<!--\nrelated: deadbee\n-->\nFixed in {full}."
    assert extract_shas(body) == [full]


def test_unclosed_block_comment_hides_rest_like_github() -> None:
    assert extract_shas("Fixed in abc1234.\n\n<!-- draft\nreverted deadbee") == ["abc1234"]


def test_comment_opener_in_fence_does_not_hide_prose() -> None:
    body = (
        "```\n<!-- sample\n```\n"
        "Reverted in fedcba9.\n"
        "<!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 -->"
    )
    assert extract_shas(body) == ["fedcba9"]


def test_html_comment_does_not_join_adjacent_hex() -> None:
    assert extract_shas("abc<!-- x -->1234567") == ["1234567"]


def test_comment_opener_in_inline_code_does_not_hide_prose() -> None:
    body = (
        "Avoid `<!--` in prose. Reverted in fedcba9.\n"
        "<!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 -->"
    )
    assert extract_shas(body) == ["fedcba9"]


def test_sha_in_inline_code_is_checked() -> None:
    assert extract_shas("Fixed in `abc1234` and ``def5678``.") == ["abc1234", "def5678"]


def test_unmatched_backtick_is_literal() -> None:
    body = "Stray ` tick <!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 --> fixed abc1234"
    assert extract_shas(body) == ["abc1234"]


def test_many_backticks_stay_fast() -> None:
    assert extract_shas("` " * 20000 + "abc1234") == ["abc1234"]


def test_unmatched_wide_backtick_run_is_cached() -> None:
    body = "a `` b " * 5000 + "abc1234"
    assert extract_shas(body) == ["abc1234"]


def test_many_unclosed_openers_stay_linear() -> None:
    assert extract_shas("abc1234\n\n" + "<!--" * 20000) == ["abc1234"]


_MARKER = "<!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 -->"


def test_fence_line_inside_comment_does_not_hide_prose() -> None:
    assert extract_shas("<!--\n```\n-->\nFixed in abc1234") == ["abc1234"]


def test_code_span_does_not_cross_blank_line() -> None:
    body = f"Use the ` char.\n\n{_MARKER}\n\n`code` fixed in abc1234"
    assert extract_shas(body) == ["abc1234"]


def test_code_span_within_paragraph_spans_lines() -> None:
    assert extract_shas("See `abc1234\n<!-- x -->` here") == ["abc1234"]


def test_short_comments_end_immediately() -> None:
    assert extract_shas("<!-->Fixed in abc1234 -->") == ["abc1234"]
    assert extract_shas("<!--->Fixed in def5678 -->") == ["def5678"]


def test_escaped_comment_opener_is_literal() -> None:
    assert extract_shas("\\<!-- Fixed in abc1234 -->") == ["abc1234"]


def test_escaped_backslash_before_comment_still_strips() -> None:
    assert extract_shas(f"Path C:\\\\{_MARKER} abc1234") == ["abc1234"]


def test_escaped_backtick_does_not_open_code_span() -> None:
    body = f"A \\` tick {_MARKER} and ` fixed in abc1234"
    assert extract_shas(body) == ["abc1234"]


def test_indented_code_is_skipped_like_fences() -> None:
    assert extract_shas("Fixed in abc1234\n\n    git show deadbee\n") == ["abc1234"]


def test_tilde_fence_is_code() -> None:
    body = "~~~\n<!--\n~~~\nFixed in abc1234\n<!-- end -->"
    assert extract_shas(body) == ["abc1234"]


def test_fence_closes_only_with_same_char_and_width() -> None:
    body = "````\ndeadbee\n```\n~~~~\nbeefcaf\n````\nFixed in abc1234"
    assert extract_shas(body) == ["abc1234"]


def test_backtick_fence_info_with_backtick_is_not_fence() -> None:
    assert extract_shas("```a`b abc1234") == ["abc1234"]


def test_unclosed_fence_runs_to_end_like_github() -> None:
    assert extract_shas("Fixed in abc1234\n``` x\ndeadbee") == ["abc1234"]


def test_code_span_wins_over_later_comment_opener() -> None:
    body = "x ` y <!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 ` --> abc1234"
    assert extract_shas(body) == ["75f6c599dff6a5b0a7422ab3", "abc1234"]


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
    assert report["ambiguous_count"] == 0


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


def test_ambiguous_sha_blocks_report() -> None:
    with patch(
        "check_review_thread_resolution_shas.check_ancestor",
        return_value=(False, "ambiguous"),
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
    assert report["ambiguous_count"] == 1
    assert report["references"][0]["status"] == "ambiguous"


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
    with patch(
        "subprocess.run",
        side_effect=_check_ancestor_run(
            verify_rc=0,
            verify_stdout="abc1234\n",
            merge_base_rc=0,
        ),
    ):
        assert check_ancestor("abc1234", "b" * 40, ".") == (True, "reachable")
    with patch(
        "subprocess.run",
        side_effect=_check_ancestor_run(
            verify_rc=0,
            verify_stdout="abc1234\n",
            merge_base_rc=1,
        ),
    ):
        assert check_ancestor("abc1234", "b" * 40, ".") == (False, "unreachable")
    with patch(
        "subprocess.run",
        side_effect=_check_ancestor_run(
            verify_rc=128,
            disambiguate_stdout="abc1234\ndef5678\n",
        ),
    ):
        assert check_ancestor("abc1234", "b" * 40, ".") == (False, "ambiguous")
    with patch(
        "subprocess.run",
        side_effect=_check_ancestor_run(
            verify_rc=128,
            disambiguate_stdout="",
        ),
    ):
        assert check_ancestor("abc1234", "b" * 40, ".") == (False, "invalid")


def test_main_exits_zero_and_emits_raw_json(capsys) -> None:
    with (
        patch("check_review_thread_resolution_shas.assert_gh_authenticated"),
        patch(
            "check_review_thread_resolution_shas.resolve_repo_params",
            return_value=type("Repo", (), {"owner": "o", "repo": "r"})(),
        ),
        patch(
            "check_review_thread_resolution_shas.fetch_review_threads",
            return_value=("b" * 40, [_thread("T1", True, "Fixed in abc1234")], True),
        ),
        patch(
            "check_review_thread_resolution_shas.check_ancestor",
            return_value=(True, "reachable"),
        ),
    ):
        rc = main(["--pull-request", "99"])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["sha_reference_count"] == 1
    assert output["unreachable_count"] == 0
    assert output["invalid_count"] == 0
    assert output["ambiguous_count"] == 0


def test_pr_review_config_contains_resolution_sha_gate() -> None:
    config_path = _ROOT / ".claude" / "skills" / "pr-review" / "pr-review-config.yaml"
    config = yaml.safe_load(config_path.read_text())
    criteria = config["completion_criteria"]
    sha_gate = next(
        item
        for item in criteria
        if item["name"] == "Resolved thread commit references are reachable"
    )
    assert (
        sha_gate["command"] == 'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
        '/skills/github/scripts/pr/check_review_thread_resolution_shas.py" --pull-request {pr}'
    )
    assert sha_gate["pass_when"] == (
        "stdout-json.unreachable_count == 0 AND "
        "stdout-json.invalid_count == 0 AND "
        "stdout-json.ambiguous_count == 0 AND "
        "stdout-json.fetched_pages_complete == true"
    )


def test_crlf_fence_closes() -> None:
    assert extract_shas("```\r\ndeadbee\r\n```\r\nFixed in abc1234") == ["abc1234"]


def test_crlf_blank_line_ends_code_span() -> None:
    body = f"Use the ` char.\r\n\r\n{_MARKER}\r\n\r\n`code` fixed in abc1234"
    assert extract_shas(body) == ["abc1234"]


def test_fence_inside_html_block_is_raw_html() -> None:
    body = "<details>\n```\n</details>\n\nFixed in abc1234\n```"
    assert extract_shas(body) == ["abc1234"]


def test_html_block_text_is_visible_but_comment_is_not() -> None:
    body = f"<details><summary>Fixed in abc1234</summary>\n{_MARKER}\n</details>"
    assert extract_shas(body) == ["abc1234"]


def test_inline_comment_cannot_cross_blank_line() -> None:
    assert extract_shas("Text <!-- a\n\nFixed in abc1234 -->") == ["abc1234"]


def test_inline_comment_with_double_dash_is_visible() -> None:
    assert extract_shas("Text <!-- a -- fixed in abc1234 --> end") == ["abc1234"]


def test_blockquote_indented_code_is_skipped() -> None:
    assert extract_shas(">     git show deadbee\n\nFixed in abc1234") == ["abc1234"]


def test_marker_in_table_cell_is_ignored() -> None:
    body = f"| fix |\n| --- |\n| abc1234 {_MARKER} |"
    assert extract_shas(body) == ["abc1234"]


def test_distinct_backtick_widths_stay_fast() -> None:
    body = "x " + "".join("`" * width + " " for width in range(1, 1700)) + "abc1234"
    started = time.perf_counter()
    assert extract_shas(body)[-1] == "abc1234"
    assert time.perf_counter() - started < 5


def test_missing_parser_scans_raw_body() -> None:
    with patch.object(_mod, "_MARKDOWN", None):
        assert extract_shas(f"Fixed in abc1234 {_MARKER}") == [
            "abc1234",
            "75f6c599dff6a5b0a7422ab3",
        ]


def test_link_text_and_soft_breaks_are_visible() -> None:
    body = "[fix](https://example.com) in abc1234\nand def5678"
    assert extract_shas(body) == ["abc1234", "def5678"]


def test_nesting_past_parser_limit_scans_raw_body() -> None:
    body = "\n".join(" " * (2 * depth) + "- x" for depth in range(40)) + " deadbee"
    assert extract_shas(body) == ["deadbee"]


def test_nesting_below_parser_limit_uses_parser() -> None:
    body = ">" * 10 + f" Fixed in abc1234 {_MARKER}"
    assert extract_shas(body) == ["abc1234"]


def test_commit_link_target_is_checked() -> None:
    body = "Fixed in [the fix](https://github.com/o/r/commit/abc1234)."
    assert extract_shas(body) == ["abc1234"]


def test_reference_link_definition_is_checked() -> None:
    body = "Fixed in [the fix][r].\n\n[r]: https://github.com/o/r/commit/abc1234"
    assert extract_shas(body) == ["abc1234"]


def test_footnote_definition_is_checked() -> None:
    assert extract_shas("Fixed.[^1]\n\n[^1]: abc1234") == ["abc1234"]


def test_main_warns_when_parser_missing(capsys) -> None:
    with (
        patch.object(_mod, "_MARKDOWN", None),
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(_mod, "resolve_repo_params", side_effect=SystemExit(9)),
    ):
        try:
            main(["--pull-request", "1"])
        except SystemExit as exc:
            assert exc.code == 9
    assert "markdown-it-py not installed" in capsys.readouterr().err


def test_repeated_sha_is_reported_once() -> None:
    assert extract_shas("abc1234 then ABC1234 and def5678") == ["abc1234", "def5678"]
