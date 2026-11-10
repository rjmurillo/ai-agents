"""Origin filter for Tier 1 (ADR-041 amendment, debate log 4).

Only alerts whose most recent instance came from an analysis uploaded by
``.github/workflows/codeql-analysis.yml`` under a ``/language:<lang>`` category count.
Another job with ``security-events: write`` can upload SARIF whose content sets the
tool name to ``CodeQL``, so the tool name is never the filter.

The recorded list below has the shape observed on rjmurillo/ai-agents on 2026-11-09:
two CodeQL uploads and a ``pytest.yml`` ``security`` job upload (``ruff-security``).
The spoof case gives that upload the tool name ``CodeQL``, which the amendment says
SARIF content can do.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from code_scanning_fakes import (
    BASE_SHA,
    HEAD_SHA,
    MERGE_SHA,
    OWNER,
    REPO,
    FakeGitHub,
    alert,
    analysis,
    sarif,
    sarif_result,
    sha,
)
from test_helpers import import_skill_script

_lib_dir = Path(__file__).resolve().parents[3] / ".claude" / "lib"
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

mod = import_skill_script("get_pr_code_scanning_alerts", "pr")
import code_scanning_scope as scope

PYTEST_KEY = ".github/workflows/pytest.yml:security"
CHANGED = frozenset({"src/a.py"})


def read(fake, head=HEAD_SHA):
    return mod.read_outcome(
        fake,
        owner=OWNER,
        repo=REPO,
        pull_request=7,
        head_sha=head,
        tree_clean=True,
        changed_files=CHANGED,
    )


def recorded_list(spoof_tool: str = "CodeQL"):
    """The recorded shape: CodeQL python and actions, plus a ruff-security upload."""
    return [
        analysis(
            103,
            category="ruff-security",
            analysis_key=PYTEST_KEY,
            tool=spoof_tool,
            created_at="2026-11-10T04:20:00Z",
        ),
        analysis(102, category="/language:actions", created_at="2026-11-10T04:10:00Z"),
        analysis(101, category="/language:python", created_at="2026-11-10T04:00:00Z"),
    ]


def world(analyses, results=(), alerts=()):
    fake = FakeGitHub()
    fake.analyses(analyses)
    fake.commit(MERGE_SHA, [BASE_SHA, HEAD_SHA])
    for item in analyses:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            fake.sarif[item["id"]] = sarif(*results)
    fake.alerts(list(alerts))
    return fake


OK_KEY = ".github/workflows/codeql-analysis.yml:analyze"


class TestIsCodeqlOrigin:
    @pytest.mark.parametrize("lang", ["python", "actions", "javascript-typescript", "c-cpp"])
    def test_accepts_the_analyze_job_under_a_language_category_from_codeql(self, lang):
        assert scope.is_codeql_origin(OK_KEY, f"/language:{lang}", "CodeQL") is True

    @pytest.mark.parametrize(
        ("key", "category", "tool"),
        [
            (PYTEST_KEY, "ruff-security", "CodeQL"),
            (PYTEST_KEY, "/language:python", "CodeQL"),
            (".github/workflows/codeql-analysis.yml:other-job", "/language:python", "CodeQL"),
            (".github/workflows/codeql-analysis.yml:analyze2", "/language:python", "CodeQL"),
            (".github/workflows/codeql-analysis.yml:Analyze", "/language:python", "CodeQL"),
            (".github/workflows/codeql-analysis.yml:analyze ", "/language:python", "CodeQL"),
            (".github/workflows/codeql-analysis.yaml:analyze", "/language:python", "CodeQL"),
            ("x/.github/workflows/codeql-analysis.yml:analyze", "/language:python", "CodeQL"),
            (".github/workflows/CodeQL-Analysis.yml:analyze", "/language:python", "CodeQL"),
            (".github/workflows/codeql-analysis.yml", "/language:python", "CodeQL"),
            (".github/workflows/codeql-analysis.yml:", "/language:python", "CodeQL"),
            ("", "/language:python", "CodeQL"),
            (None, "/language:python", "CodeQL"),
            (7, "/language:python", "CodeQL"),
            (OK_KEY, "ruff-security", "CodeQL"),
            (OK_KEY, "/language:", "CodeQL"),
            (OK_KEY, "language:python", "CodeQL"),
            (OK_KEY, "/language:python/extra", "CodeQL"),
            (OK_KEY, "/language:python-extra suffix", "CodeQL"),
            (OK_KEY, "/language:python\n", "CodeQL"),
            (OK_KEY, "/language:Python", "CodeQL"),
            (OK_KEY, "/language:py_thon", "CodeQL"),
            (OK_KEY, "/language:python,/language:actions", "CodeQL"),
            (OK_KEY, "x/language:python", "CodeQL"),
            (OK_KEY, "", "CodeQL"),
            (OK_KEY, None, "CodeQL"),
            (OK_KEY, ["/language:python"], "CodeQL"),
            (OK_KEY, "/language:python", "Ruff"),
            (OK_KEY, "/language:python", "codeql"),
            (OK_KEY, "/language:python", "CodeQL "),
            (OK_KEY, "/language:python", ""),
            (OK_KEY, "/language:python", None),
            (OK_KEY, "/language:python", ["CodeQL"]),
        ],
    )
    def test_rejects_everything_else(self, key, category, tool):
        assert scope.is_codeql_origin(key, category, tool) is False

    @pytest.mark.parametrize(
        "record",
        [None, "x", 3, [], {}, {"category": "/language:python"}, {"analysis_key": OK_KEY}],
    )
    def test_is_origin_analysis_rejects_records_missing_a_field(self, record):
        assert scope.is_origin_analysis(record) is False

    def test_an_analysis_without_a_tool_object_is_ignored(self):
        row = analysis(101)
        del row["tool"]
        assert scope.is_origin_analysis(row) is False

    def test_the_tool_name_alone_never_qualifies(self):
        row = analysis(101, analysis_key=PYTEST_KEY, category="ruff-security", tool="CodeQL")
        assert scope.is_origin_analysis(row) is False


class TestAnalysesAreFiltered:
    def test_a_ruff_security_upload_named_codeql_is_ignored(self):
        fake = world(recorded_list(), results=[sarif_result(5)], alerts=[alert(5)])
        out = read(fake)
        assert out["outcome"] == "CURRENT"
        assert out["analysis_ids"] == [101, 102]
        assert [c for c in fake.calls if c[0].endswith("/analyses/103")] == []

    def test_the_spoofed_upload_cannot_make_a_current_analysis_stale(self):
        spoof = analysis(
            103,
            category="ruff-security",
            analysis_key=PYTEST_KEY,
            commit_sha=sha("e"),
            created_at="2026-11-10T05:00:00Z",
        )
        fake = world([spoof, analysis(101), analysis(102, category="/language:actions")])
        assert read(fake)["outcome"] == "CURRENT"

    def test_only_other_workflows_analyzed_the_ref_is_not_analyzed(self):
        only_ruff = [analysis(103, category="ruff-security", analysis_key=PYTEST_KEY)]
        out = read(world(only_ruff))
        assert out["outcome"] == "NOT ANALYZED"
        assert out["status_line"] == "CodeQL: NOT ANALYZED"

    def test_a_ruff_upload_named_codeql_alone_is_not_analyzed(self):
        spoof = [analysis(103, category="ruff-security", analysis_key=PYTEST_KEY, tool="CodeQL")]
        assert read(world(spoof))["outcome"] == "NOT ANALYZED"

    def test_an_analysis_missing_analysis_key_is_ignored(self):
        fake = world([analysis(101, analysis_key=None)])
        assert read(fake)["outcome"] == "NOT ANALYZED"

    def test_an_analysis_missing_category_is_ignored(self):
        row = analysis(101)
        del row["category"]
        assert read(world([row]))["outcome"] == "NOT ANALYZED"

    def test_a_different_job_in_the_same_workflow_file_is_ignored(self):
        key = ".github/workflows/codeql-analysis.yml:other-job"
        assert read(world([analysis(101, analysis_key=key)]))["outcome"] == "NOT ANALYZED"

    def test_a_category_with_extra_suffix_text_is_ignored(self):
        row = analysis(101, category="/language:python-and-more text")
        assert read(world([row]))["outcome"] == "NOT ANALYZED"

    def test_a_non_codeql_tool_name_is_ignored(self):
        assert read(world([analysis(101, tool="Ruff")]))["outcome"] == "NOT ANALYZED"

    def test_an_analysis_with_the_wrong_category_is_ignored(self):
        assert read(world([analysis(101, category="ruff-security")]))["outcome"] == "NOT ANALYZED"

    def test_a_yaml_variant_of_the_workflow_path_is_not_the_origin(self):
        key = ".github/workflows/codeql-analysis.yaml:analyze"
        assert read(world([analysis(101, analysis_key=key)]))["outcome"] == "NOT ANALYZED"

    def test_malformed_foreign_rows_do_not_skip_the_read(self):
        rows = [
            "junk",
            None,
            {"id": "x"},
            analysis(101),
            analysis(102, category="/language:actions"),
        ]
        assert read(world(rows))["outcome"] == "CURRENT"

    def test_a_malformed_origin_row_still_skips(self):
        bad = analysis(101)
        bad["id"] = "not-an-int"
        with pytest.raises(mod.SkipError, match="unexpected shape"):
            read(world([bad]))


class TestAlertsAreFiltered:
    def _fake(self, alerts, results):
        return world(recorded_list(), results=results, alerts=alerts)

    def test_an_alert_from_the_ruff_upload_is_excluded(self):
        ruff = alert(6, rule_id="ruff/S101", analysis_key=PYTEST_KEY, category="ruff-security")
        fake = self._fake([alert(5), ruff], [sarif_result(5), sarif_result(6)])
        out = read(fake)
        assert [a["rule_id"] for a in out["alerts"]] == ["py/path-injection"]
        assert out["counts"]["other_origin"] == 1
        assert "ruff/S101" not in json.dumps(out)

    def test_an_alert_from_the_ruff_upload_is_excluded_even_with_no_sarif_result(self):
        ruff = alert(6, analysis_key=PYTEST_KEY, category="ruff-security")
        out = read(self._fake([ruff], []))
        assert out["alerts"] == []
        assert out["counts"] == {
            "open": 0,
            "other_origin": 1,
            "invalid_rule_id": 0,
            "not_in_current_analysis": 0,
        }

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"analysis_key": None},
            {"category": None},
            {"analysis_key": None, "category": None},
            {"category": "ruff-security"},
            {"analysis_key": PYTEST_KEY},
            {"analysis_key": ".github/workflows/codeql-analysis.yaml:analyze"},
            {"analysis_key": ".github/workflows/codeql-analysis.yml:other-job"},
            {"category": "/language:python-and-more text"},
            {"tool": "Ruff"},
            {"tool": None},
        ],
    )
    def test_an_alert_missing_or_failing_either_field_is_ignored(self, kwargs):
        fake = self._fake([alert(5, **kwargs)], [sarif_result(5)])
        out = read(fake)
        assert out["alerts"] == []
        assert out["counts"]["other_origin"] == 1
        assert out["other_total"] == 0

    def test_an_alert_with_no_instance_object_is_ignored(self):
        bare = alert(5)
        del bare["most_recent_instance"]
        out = read(self._fake([bare], [sarif_result(5)]))
        assert out["counts"]["other_origin"] == 1

    def test_the_origin_alert_still_attaches_beside_ignored_ones(self):
        spoof = alert(7, analysis_key=PYTEST_KEY, category="ruff-security")
        out = read(self._fake([spoof, alert(5)], [sarif_result(5), sarif_result(7)]))
        assert len(out["alerts"]) == 1
        assert out["counts"]["open"] == 1
        assert "1 alert(s) in diff files" in out["status_line"]
