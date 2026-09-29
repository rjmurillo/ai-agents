"""Tests for check_suppressed_review_findings.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
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


_mod = _import_script("check_suppressed_review_findings")
parse_suppressed_sections = _mod.parse_suppressed_sections
fetch_reviews = _mod.fetch_reviews
fetch_pr_head = _mod.fetch_pr_head
build_report = _mod.build_report
main = _mod.main


def _gh_api_run(
    *,
    reviews_completed: subprocess.CompletedProcess[str],
    pr_completed: subprocess.CompletedProcess[str],
):
    def _run(argv, **kwargs):
        command = [str(part) for part in argv]
        if command[:2] != ["gh", "api"]:
            raise AssertionError(f"unexpected subprocess call: {command}")
        endpoint = command[2]
        if endpoint.endswith("/reviews?per_page=100"):
            assert "--paginate" in command
            assert "--slurp" in command
            return reviews_completed
        if endpoint.endswith("/pulls/99"):
            return pr_completed
        raise AssertionError(f"unexpected subprocess call: {command}")

    return _run


def _review(
    review_id: int,
    body: str,
    author: str = "copilot-pull-request-reviewer[bot]",
    commit_id: str = "head",
) -> dict:
    review = {
        "id": review_id,
        "node_id": f"PRR_{review_id}",
        "user": {"login": author},
        "state": "COMMENTED",
        "body": body,
        "submitted_at": "2026-08-03T00:00:00Z",
        "html_url": f"https://github.test/review/{review_id}",
    }
    if commit_id:
        review["commit_id"] = commit_id
    return review


def test_parses_suppressed_findings_with_file_line_and_text() -> None:
    body = """<details>
<summary>Suppressed comments (2)</summary>

**src/app.py:10**
* First finding.

**docs/readme.md:42**
* Second finding.
</details>
"""
    sections = parse_suppressed_sections(body)
    assert sections[0]["declared_count"] == 2
    assert sections[0]["parsed_count"] == 2
    assert sections[0]["findings"][0] == {
        "path": "src/app.py",
        "line": 10,
        "text": "First finding.",
    }


def test_strips_whitespace_from_suppressed_finding_path() -> None:
    body = "<summary>Suppressed comments (1)</summary>\n**  src/app.py  :10**\n* Finding"
    sections = parse_suppressed_sections(body)
    assert sections[0]["findings"][0]["path"] == "src/app.py"


def test_returns_zero_when_suppressed_section_is_absent() -> None:
    report = build_report("o", "r", 1, [_review(1, "No suppressed comments here.")])
    assert report["suppressed_count"] == 0
    assert report["parsed_finding_count"] == 0
    assert report["count_mismatches"] == []


def test_zero_count_section_does_not_create_findings() -> None:
    sections = parse_suppressed_sections(
        "<details>\n<summary>Suppressed comments (0)</summary>\n</details>"
    )
    assert sections == [{"declared_count": 0, "parsed_count": 0, "findings": []}]


def test_malformed_section_reports_count_mismatch() -> None:
    report = build_report(
        "o",
        "r",
        1,
        [_review(1, "<summary>Suppressed comments (3)</summary>\nnot a finding")],
    )
    assert report["suppressed_count"] == 3
    assert report["parsed_finding_count"] == 0
    assert report["count_mismatches"] == [
        {"review_id": 1, "section_index": 0, "declared_count": 3, "parsed_count": 0}
    ]


def test_multiple_reviews_are_aggregated() -> None:
    report = build_report(
        "o",
        "r",
        7,
        [
            _review(1, "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A"),
            _review(2, "<summary>Suppressed comments: 2</summary>\n**b.py:2**\n* B"),
        ],
    )
    assert report["review_count"] == 2
    assert report["suppressed_review_count"] == 2
    assert report["suppressed_count"] == 3
    assert report["parsed_finding_count"] == 2


def test_classifies_suppressed_findings_by_head_sha() -> None:
    report = build_report(
        "o",
        "r",
        7,
        [
            _review(
                1,
                "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A",
                commit_id="head",
            ),
            _review(
                2,
                "<summary>Suppressed comments (2)</summary>\n**b.py:2**\n* B",
                commit_id="old",
            ),
            _review(
                3,
                "<summary>Suppressed comments (3)</summary>\n**c.py:3**\n* C",
                commit_id="",
            ),
        ],
        head_sha="head",
    )
    assert report["suppressed_count"] == 6
    assert report["active_suppressed_count"] == 1
    assert report["stale_suppressed_count"] == 2
    assert report["unknown_suppressed_count"] == 3


def test_ignores_non_copilot_suppressed_sections() -> None:
    report = build_report(
        "o",
        "r",
        7,
        [
            _review(
                1,
                "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A",
                author="human-reviewer",
            )
        ],
    )
    assert report["suppressed_count"] == 0
    assert report["parsed_finding_count"] == 0


def test_fetch_reviews_reports_missing_gh_as_runtime_error() -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError):
        try:
            fetch_reviews("o", "r", 1)
        except RuntimeError as exc:
            assert str(exc) == "gh executable not found"
        else:
            raise AssertionError("expected RuntimeError")


def test_fetch_reviews_reports_timeout_as_runtime_error() -> None:
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=60),
    ):
        try:
            fetch_reviews("o", "r", 1)
        except RuntimeError as exc:
            assert str(exc) == "gh api timed out after 60 seconds"
        else:
            raise AssertionError("expected RuntimeError")


def test_fetch_pr_head_reports_missing_sha() -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"head": {}}),
        stderr="",
    )
    with patch("subprocess.run", return_value=completed):
        try:
            fetch_pr_head("o", "r", 1)
        except RuntimeError as exc:
            assert str(exc) == "PR head sha missing from response"
        else:
            raise AssertionError("expected RuntimeError")


def test_main_exits_zero_and_emits_raw_json(capsys) -> None:
    page = [
        _review(
            1,
            "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A",
            commit_id="head",
        )
    ]
    reviews_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps([page]),
        stderr="",
    )
    pr_completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"head": {"sha": "head"}}),
        stderr="",
    )
    with (
        patch("check_suppressed_review_findings.assert_gh_authenticated"),
        patch(
            "check_suppressed_review_findings.resolve_repo_params",
            return_value=type("Repo", (), {"owner": "o", "repo": "r"})(),
        ),
        patch(
            "subprocess.run",
            side_effect=_gh_api_run(
                reviews_completed=reviews_completed,
                pr_completed=pr_completed,
            ),
        ),
    ):
        rc = main(["--pull-request", "99"])

    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["suppressed_count"] == 1
    assert output["active_suppressed_count"] == 1
    assert output["fetched_pages_complete"] is True


def test_pr_review_config_contains_suppressed_gate() -> None:
    config_path = _ROOT / ".claude" / "skills" / "pr-review" / "pr-review-config.yaml"
    config = yaml.safe_load(config_path.read_text())
    criteria = config["completion_criteria"]
    suppressed_gate = next(
        item for item in criteria if item["name"] == "No suppressed Copilot review findings"
    )
    assert (
        suppressed_gate["command"] == "python3 .claude/skills/github/scripts/pr/"
        "check_suppressed_review_findings.py --pull-request {pr} "
        "--dispositions-file .project-toolkit/pr-checks/suppressed-finding-dispositions.json"
    )
    assert suppressed_gate["pass_when"] == (
        "stdout-json.undispositioned_suppressed_count == 0 AND "
        "stdout-json.fetched_pages_complete == true"
    )


_BODY_ONE = "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* Change Closes to Refs"
_GOOD = {"disposition": "addressed-by-pr-metadata", "reason": "PR body now says Refs #1"}


def _report(reviews, dispositions=None, head_sha="head"):
    return build_report("o", "r", 7, reviews, head_sha=head_sha, dispositions=dispositions)


def test_body_edit_finding_is_cleared_by_disposition_without_new_commit() -> None:
    report = _report([_review(11, _BODY_ONE)], {"11:0": _GOOD})
    assert report["head_sha"] == "head"
    assert report["active_suppressed_count"] == 1
    assert report["dispositioned_suppressed_count"] == 1
    assert report["undispositioned_suppressed_count"] == 0
    assert report["rejected_dispositions"] == []
    assert report["findings"][0]["finding_index"] == 0
    assert report["findings"][0]["disposition"] == _GOOD


def test_finding_without_disposition_still_fails_the_gate() -> None:
    report = _report([_review(11, _BODY_ONE)])
    assert report["undispositioned_suppressed_count"] == 1
    assert report["dispositioned_suppressed_count"] == 0
    assert report["findings"][0]["disposition"] is None


def test_disposition_clears_only_the_finding_it_names() -> None:
    body = (
        "<summary>Suppressed comments (2)</summary>\n"
        "**a.py:1**\n* First\n\n**b.py:2**\n* Second"
    )
    report = _report([_review(11, body)], {"11:1": _GOOD})
    assert report["active_suppressed_count"] == 2
    assert report["dispositioned_suppressed_count"] == 1
    assert report["undispositioned_suppressed_count"] == 1
    assert [f["disposition"] is not None for f in report["findings"]] == [False, True]


def test_finding_index_runs_across_sections_of_one_review() -> None:
    body = (
        "<details>\n<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A\n</details>\n"
        "<details>\n<summary>Suppressed comments (1)</summary>\n**b.py:2**\n* B\n</details>"
    )
    report = _report([_review(11, body)], {"11:1": _GOOD})
    assert [f["finding_index"] for f in report["findings"]] == [0, 1]
    assert report["undispositioned_suppressed_count"] == 1


@pytest.mark.parametrize(
    "entry",
    [
        {"disposition": "not-applicable", "reason": ""},
        {"disposition": "not-applicable", "reason": "   "},
        {"disposition": "not-applicable"},
        {"disposition": "not-applicable", "reason": 5},
        {"disposition": "made-up", "reason": "because"},
        {"disposition": "", "reason": "because"},
        {"disposition": 3, "reason": "because"},
        {"reason": "because"},
        "addressed",
        None,
        [],
    ],
)
def test_malformed_disposition_is_rejected_and_reported(entry) -> None:
    report = _report([_review(11, _BODY_ONE)], {"11:0": entry})
    assert report["undispositioned_suppressed_count"] == 1
    assert report["dispositioned_suppressed_count"] == 0
    assert report["findings"][0]["disposition"] is None
    assert [r["key"] for r in report["rejected_dispositions"]] == ["11:0"]


@pytest.mark.parametrize("name", ["addressed-by-pr-metadata", "not-applicable", "tracked-issue"])
def test_every_named_disposition_is_accepted(name) -> None:
    report = _report([_review(11, _BODY_ONE)], {"11:0": {"disposition": name, "reason": "r"}})
    assert report["undispositioned_suppressed_count"] == 0


def test_unknown_state_finding_can_be_dispositioned() -> None:
    review = _review(11, _BODY_ONE, commit_id="")
    assert _report([review])["unknown_suppressed_count"] == 1
    report = _report([review], {"11:0": _GOOD})
    assert report["unknown_suppressed_count"] == 1
    assert report["undispositioned_suppressed_count"] == 0


def test_disposition_for_missing_review_is_rejected_and_clears_nothing() -> None:
    report = _report([_review(11, _BODY_ONE)], {"999:0": _GOOD, "11:5": _GOOD})
    assert report["undispositioned_suppressed_count"] == 1
    assert [r["key"] for r in report["rejected_dispositions"]] == ["11:5", "999:0"]
    assert {r["reason"] for r in report["rejected_dispositions"]} == {"no such review finding"}


def test_disposition_on_stale_review_does_not_reduce_open_findings() -> None:
    stale = _review(10, _BODY_ONE, commit_id="old")
    active = _review(11, _BODY_ONE)
    report = _report([stale, active], {"10:0": _GOOD})
    assert report["stale_suppressed_count"] == 1
    assert report["dispositioned_suppressed_count"] == 0
    assert report["undispositioned_suppressed_count"] == 1
    assert report["rejected_dispositions"] == []


def test_unparsed_declared_finding_stays_undispositioned() -> None:
    body = "<summary>Suppressed comments (3)</summary>\n**a.py:1**\n* A"
    report = _report([_review(11, body)], {"11:0": _GOOD})
    assert report["dispositioned_suppressed_count"] == 1
    assert report["undispositioned_suppressed_count"] == 2


def test_report_without_dispositions_keeps_raw_counts() -> None:
    report = _report([_review(11, _BODY_ONE)], None)
    assert report["active_suppressed_count"] == 1
    assert report["undispositioned_suppressed_count"] == 1
    assert report["rejected_dispositions"] == []


def test_loader_returns_empty_without_a_file() -> None:
    assert _mod._load_finding_dispositions(None) == {}
    assert _mod._load_finding_dispositions("") == {}


def test_loader_refuses_an_untracked_registry(tmp_path) -> None:
    registry = tmp_path / "d.json"
    registry.write_text(json.dumps({"11:0": _GOOD}))
    assert _mod._load_finding_dispositions(str(registry)) == {}


def test_loader_reads_a_tracked_registry(tmp_path) -> None:
    registry = tmp_path / "d.json"
    registry.write_text(json.dumps({"11:0": _GOOD}))
    with patch("test_pr_merge_ready._dispositions_file_is_tracked", return_value=True):
        assert _mod._load_finding_dispositions(str(registry)) == {"11:0": _GOOD}


def test_shipped_registry_is_a_tracked_json_object() -> None:
    path = _ROOT / ".project-toolkit" / "pr-checks" / "suppressed-finding-dispositions.json"
    assert isinstance(json.loads(path.read_text()), dict)
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=_ROOT,
        capture_output=True,
        check=False,
    )
    assert tracked.returncode == 0


def test_main_passes_registry_through_and_reports_dispositioned(capsys, tmp_path) -> None:
    registry = tmp_path / "d.json"
    registry.write_text(json.dumps({"1:0": _GOOD}))
    page = [_review(1, _BODY_ONE, commit_id="head")]
    reviews_completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps([page]), stderr=""
    )
    pr_completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps({"head": {"sha": "head"}}), stderr=""
    )
    with (
        patch("check_suppressed_review_findings.assert_gh_authenticated"),
        patch(
            "check_suppressed_review_findings.resolve_repo_params",
            return_value=type("Repo", (), {"owner": "o", "repo": "r"})(),
        ),
        patch("test_pr_merge_ready._dispositions_file_is_tracked", return_value=True),
        patch(
            "subprocess.run",
            side_effect=_gh_api_run(
                reviews_completed=reviews_completed, pr_completed=pr_completed
            ),
        ),
    ):
        rc = main(["--pull-request", "99", "--dispositions-file", str(registry)])
    output = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert output["active_suppressed_count"] == 1
    assert output["undispositioned_suppressed_count"] == 0


def test_dispositions_beyond_the_declared_count_cannot_go_negative() -> None:
    body = "<summary>Suppressed comments (1)</summary>\n**a.py:1**\n* A\n**b.py:2**\n* B"
    report = _report([_review(11, body), _review(12, _BODY_ONE)], {"11:0": _GOOD, "11:1": _GOOD})
    assert report["parsed_finding_count"] == 3
    assert report["dispositioned_suppressed_count"] == 1
    assert report["undispositioned_suppressed_count"] == 1
