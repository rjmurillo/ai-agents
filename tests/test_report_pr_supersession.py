"""Tests for scripts/report_pr_supersession.py (issue #4355).

The load-bearing test is TestIssue4355Corpus: the four PRs the issue names,
with the payloads GitHub returned for them on 2026-08-03 and the base
distances `git rev-list --count <head>..origin/main` measured the same day.
Three must flag as candidates (#4164, #4102, #3979) and the fourth (#4163)
must flag and then survive review as a false positive, which the report
supports by printing its still-open linked issue next to the closed ones.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import report_pr_supersession as mod

REASON_CLOSED = mod.REASON_CLOSED_ISSUE
REASON_NONE = mod.REASON_NO_ISSUE
REASON_STALE = mod.REASON_STALE_BASE


def _pr(number=1, issues=None, title="t", base="main", head="a" * 40, draft=False):
    return {
        "number": number,
        "title": title,
        "isDraft": draft,
        "baseRefName": base,
        "headRefOid": head,
        "closingIssuesReferences": {"nodes": list(issues or [])},
    }


def _completed(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["gh"], returncode=rc, stdout=stdout, stderr=stderr)


# ===========================================================================
# classify_pull_request
# ===========================================================================


class TestClassify:
    def test_closed_linked_issue_flags(self):
        finding = mod.classify_pull_request(_pr(issues=[{"number": 9, "state": "CLOSED"}]), 0)
        assert finding.reasons == [REASON_CLOSED]
        assert finding.closed_issues == [9]
        assert finding.flagged

    def test_open_linked_issue_on_a_fresh_base_does_not_flag(self):
        finding = mod.classify_pull_request(_pr(issues=[{"number": 9, "state": "OPEN"}]), 3)
        assert finding.reasons == []
        assert not finding.flagged
        assert finding.open_issues == [9]

    def test_no_linked_issue_on_a_stale_base_flags(self):
        finding = mod.classify_pull_request(_pr(issues=[]), 40, stale_base=20)
        assert finding.reasons == [REASON_STALE, REASON_NONE]

    def test_no_linked_issue_on_a_fresh_base_does_not_flag(self):
        # A PR opened today with no linked issue is an issue-linkage
        # question, not a supersession candidate. Ungated, this reason
        # flagged 27 of 44 open PRs on 2026-08-03.
        finding = mod.classify_pull_request(_pr(issues=[]), 0)
        assert finding.reasons == []

    def test_stale_base_flags_at_the_threshold(self):
        finding = mod.classify_pull_request(
            _pr(issues=[{"number": 9, "state": "OPEN"}]), 20, stale_base=20
        )
        assert finding.reasons == [REASON_STALE]

    def test_one_commit_below_the_threshold_does_not_flag(self):
        finding = mod.classify_pull_request(
            _pr(issues=[{"number": 9, "state": "OPEN"}]), 19, stale_base=20
        )
        assert finding.reasons == []

    def test_unknown_base_distance_never_flags_stale(self):
        finding = mod.classify_pull_request(_pr(issues=[{"number": 9, "state": "OPEN"}]), None)
        assert finding.reasons == []
        assert finding.base_distance is None

    def test_mixed_issue_states_flag_and_keep_the_open_one_visible(self):
        finding = mod.classify_pull_request(
            _pr(issues=[{"number": 1, "state": "CLOSED"}, {"number": 2, "state": "OPEN"}]), 0
        )
        assert finding.reasons == [REASON_CLOSED]
        assert finding.open_issues == [2]

    def test_null_connection_reads_as_no_linked_issue(self):
        payload = _pr()
        payload["closingIssuesReferences"] = None
        assert mod.linked_issue_states(payload) == ([], [])
        assert mod.classify_pull_request(payload, 40).reasons == [REASON_STALE, REASON_NONE]

    def test_null_nodes_read_as_no_linked_issue(self):
        payload = _pr()
        payload["closingIssuesReferences"] = {"nodes": None}
        assert mod.linked_issue_states(payload) == ([], [])
        assert mod.classify_pull_request(payload, 40).reasons == [REASON_STALE, REASON_NONE]

    def test_malformed_issue_nodes_are_dropped(self):
        payload = _pr(issues=[{"state": "CLOSED"}, "junk", {"number": 7, "state": "CLOSED"}])
        finding = mod.classify_pull_request(payload, 0)
        assert finding.closed_issues == [7]

    def test_draft_state_is_reported_not_filtered(self):
        finding = mod.classify_pull_request(_pr(draft=True, issues=[]), 0)
        assert finding.is_draft is True


# ===========================================================================
# build_report and rendering
# ===========================================================================


class TestReport:
    def test_report_counts_examined_and_flagged(self):
        prs = [_pr(number=1, issues=[{"number": 9, "state": "OPEN"}]), _pr(number=2, issues=[])]
        report = mod.build_report(prs, {1: 0, 2: 40})
        assert report["examined"] == 2
        assert report["flagged"] == 1

    def test_empty_input_reports_zero_of_zero(self):
        report = mod.build_report([], {})
        assert (report["examined"], report["flagged"]) == (0, 0)
        assert "0 flagged of 0 open PRs examined" in mod.render_human(report)

    def test_human_output_states_the_examined_count_when_nothing_is_flagged(self):
        report = mod.build_report([_pr(issues=[{"number": 9, "state": "OPEN"}])], {1: 1})
        rendered = mod.render_human(report)
        assert "0 flagged of 1 open PRs examined" in rendered

    def test_human_output_names_the_false_positive_risk_when_flagging(self):
        report = mod.build_report([_pr(issues=[{"number": 9, "state": "CLOSED"}])], {1: 1})
        rendered = mod.render_human(report)
        assert "#1" in rendered
        assert "#4163" in rendered

    def test_missing_distance_renders_as_unknown(self):
        report = mod.build_report([_pr(issues=[{"number": 9, "state": "CLOSED"}])], {})
        assert "behind=unknown" in mod.render_human(report)


# ===========================================================================
# The corpus the issue requires the report to be validated against
# ===========================================================================


_CORPUS = {
    4164: (
        _pr(
            number=4164,
            title="fix(merge-resolver): make the leftover-marker gate merge-aware",
            issues=[{"number": 4058, "state": "CLOSED"}],
            head="205b7480583ea7e45d8f114cfb4d39d06fa22862",
        ),
        50,
    ),
    4102: (
        _pr(
            number=4102,
            title="fix(validation): skill_size full-scan measures both skill trees",
            issues=[{"number": 4015, "state": "CLOSED"}],
            head="ee309b0d69f3506c087c7badaa0b919a6c9c4aa0",
        ),
        24,
    ),
    3979: (
        _pr(
            number=3979,
            title="fix(protocol): teach the 8 investigation allowlist patterns",
            issues=[],
            head="66e7d3c6d39e6b3693fbcfd3cadf78844c3ecffa",
        ),
        167,
    ),
    4163: (
        _pr(
            number=4163,
            title="fix(memory): register the memory hooks and qualify memory ids",
            issues=[
                {"number": 4010, "state": "CLOSED"},
                {"number": 4011, "state": "CLOSED"},
                {"number": 4071, "state": "OPEN"},
            ],
            head="cf4ebd80901cc520b8df98380b3c893d48985a4f",
        ),
        12,
    ),
}


class TestIssue4355Corpus:
    @pytest.mark.parametrize("number", sorted(_CORPUS))
    def test_every_named_pr_is_flagged(self, number):
        payload, distance = _CORPUS[number]
        assert mod.classify_pull_request(payload, distance).flagged

    def test_pr_3979_is_flagged_without_any_linked_issue(self):
        # The closed-issue signal alone cannot see this one: it closes
        # nothing. Without the no-linked-issue reason the report misses a
        # third of the confirmed corpus.
        payload, distance = _CORPUS[3979]
        finding = mod.classify_pull_request(payload, distance)
        assert finding.closed_issues == []
        assert REASON_NONE in finding.reasons
        assert REASON_STALE in finding.reasons

    def test_pr_4163_flags_but_carries_its_own_refutation(self):
        # Known false positive: a different PR closed #4010 and #4011, and
        # #4071 is still open. The report must flag it and must print the
        # open issue so a reviewer can dismiss it in one read.
        payload, distance = _CORPUS[4163]
        finding = mod.classify_pull_request(payload, distance)
        assert finding.reasons == [REASON_CLOSED]
        assert finding.open_issues == [4071]
        assert finding.base_distance == 12

    def test_the_whole_corpus_reports_four_of_four(self):
        report = mod.build_report(
            [payload for payload, _ in _CORPUS.values()],
            {number: distance for number, (_, distance) in _CORPUS.items()},
        )
        assert (report["examined"], report["flagged"]) == (4, 4)


# ===========================================================================
# I/O adapter
# ===========================================================================


class TestIOAdapter:
    def test_fetch_open_prs_returns_nodes(self):
        payload = json.dumps({"data": {"repository": {"pullRequests": {"nodes": [_pr(number=5)]}}}})
        with patch.object(mod.subprocess, "run", return_value=_completed(stdout=payload)):
            prs = mod.fetch_open_pull_requests("o", "r", 10)
        assert prs[0]["number"] == 5

    def test_fetch_open_prs_raises_on_nonzero_exit(self):
        with patch.object(mod.subprocess, "run", return_value=_completed(rc=1, stderr="boom")):
            with pytest.raises(mod.GitHubReadError):
                mod.fetch_open_pull_requests("o", "r", 10)

    def test_fetch_open_prs_raises_on_unparseable_payload(self):
        with patch.object(mod.subprocess, "run", return_value=_completed(stdout="{}")):
            with pytest.raises(mod.GitHubReadError):
                mod.fetch_open_pull_requests("o", "r", 10)

    def test_fetch_open_prs_raises_when_gh_is_missing(self):
        with patch.object(mod.subprocess, "run", side_effect=OSError("gh missing")):
            with pytest.raises(mod.GitHubReadError):
                mod.fetch_open_pull_requests("o", "r", 10)

    def test_base_distance_parses_the_behind_count(self):
        with patch.object(mod.subprocess, "run", return_value=_completed(stdout="27\n")):
            assert mod.fetch_base_distance("o", "r", "main", "a" * 40) == 27

    def test_base_distance_is_unknown_when_the_compare_fails(self):
        with patch.object(mod.subprocess, "run", return_value=_completed(rc=1, stderr="404")):
            assert mod.fetch_base_distance("o", "r", "main", "a" * 40) is None

    def test_base_distance_is_unknown_on_a_non_numeric_payload(self):
        with patch.object(mod.subprocess, "run", return_value=_completed(stdout="null\n")):
            assert mod.fetch_base_distance("o", "r", "main", "a" * 40) is None

    def test_collect_distances_keys_by_pr_number(self):
        with patch.object(mod, "fetch_base_distance", return_value=4):
            assert mod.collect_distances("o", "r", [_pr(number=8)]) == {8: 4}


# ===========================================================================
# CLI exit codes
# ===========================================================================


class TestMain:
    def _repo(self):
        from types import SimpleNamespace

        return SimpleNamespace(owner="o", repo="r")

    def test_report_with_findings_still_exits_zero(self, capsys):
        with (
            patch.object(mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(
                mod,
                "fetch_open_pull_requests",
                return_value=[_pr(number=1, issues=[{"number": 9, "state": "CLOSED"}])],
            ),
            patch.object(mod, "collect_distances", return_value={1: 30}),
        ):
            rc = mod.main(["--output-format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["flagged"] == 1
        assert payload["findings"][0]["reasons"] == [REASON_CLOSED, REASON_STALE]

    def test_clean_fleet_exits_zero_and_reports_the_examined_count(self, capsys):
        with (
            patch.object(mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(
                mod,
                "fetch_open_pull_requests",
                return_value=[_pr(number=1, issues=[{"number": 9, "state": "OPEN"}])],
            ),
            patch.object(mod, "collect_distances", return_value={1: 1}),
        ):
            rc = mod.main([])
        assert rc == 0
        assert "0 flagged of 1 open PRs examined" in capsys.readouterr().out

    def test_api_failure_exits_three(self, capsys):
        with (
            patch.object(mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(mod, "fetch_open_pull_requests", side_effect=mod.GitHubReadError("down")),
        ):
            rc = mod.main([])
        assert rc == 3
        assert "down" in capsys.readouterr().err

    def test_stale_base_threshold_is_configurable(self, capsys):
        with (
            patch.object(mod, "resolve_repo_params", return_value=self._repo()),
            patch.object(
                mod,
                "fetch_open_pull_requests",
                return_value=[_pr(number=1, issues=[{"number": 9, "state": "OPEN"}])],
            ),
            patch.object(mod, "collect_distances", return_value={1: 5}),
        ):
            rc = mod.main(["--stale-base", "5", "--output-format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["findings"][0]["reasons"] == [REASON_STALE]


class TestWorkflowInvocation:
    """The `summarize` job of pr-maintenance.yml runs this file with bare `python3`.

    Under pytest the repo root is already on sys.path, so every test above passes
    whether or not the module can be imported the way CI imports it. These two
    reproduce the CI invocation instead (.claude/rules/ci-scripts.md MUST 16).
    """

    REPO_ROOT = Path(__file__).resolve().parents[1]
    WORKFLOW = REPO_ROOT / ".github/workflows/pr-maintenance.yml"
    SCRIPT = "scripts/report_pr_supersession.py"

    def _step_line(self) -> str:
        lines = [
            line
            for line in self.WORKFLOW.read_text(encoding="utf-8").splitlines()
            if self.SCRIPT in line and "run:" in line
        ]
        assert len(lines) == 1, f"expected one run: step invoking {self.SCRIPT}, got {lines}"
        return lines[0]

    def test_script_imports_under_a_bare_interpreter(self):
        # -S -E strips site-packages and PYTHONPATH, so the editable install of the
        # `scripts` package cannot stand in for the runner's ambient interpreter.
        result = subprocess.run(
            [sys.executable, "-S", "-E", self.SCRIPT, "--help"],
            cwd=self.REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, result.stderr
        assert "ModuleNotFoundError" not in result.stderr

    def test_step_does_not_pipe_away_the_exit_code(self):
        # The default `run:` shell is `bash -e {0}` with no pipefail, so a pipeline
        # reports the last command's status and a crash here reads as a green step.
        assert "|" not in self._step_line()
