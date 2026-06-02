#!/usr/bin/env python3
"""Tests for the pr-comment-responder cluster_threads.py Phase 0 step.

The headline regression fixture (``PR_1897_ROUND7_THREADS``) reconstructs the
PR #1897 round-7 unresolved-thread set described in
.agents/retrospective/2026-05-08-pr-1897-confident-incorrectness-recurrence.md
Phase 0: five gist clusters (asymmetry x 8, harmful x 2, session-log x 3,
aggregate x 1, evidence-drift x 2). The 8-thread asymmetry cluster
("model_tier=opus contradicts cheaper-tier reviewer claim" on different files)
is the single-source-of-truth violation the step exists to catch.

The retrospective's headline says "post-push 17" but its own per-cluster
breakdown (8 + 2 + 3 + 1 + 2) sums to 16. We hold the fixture to the
itemized per-cluster counts (the load-bearing detail for this test, since the
8-thread asymmetry cluster is what the step must detect) rather than the
headline total, so the fixture has 16 threads.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "cluster_threads.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("cluster_threads", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _thread(thread_id: str, path: str, body: str) -> dict:
    """Build a canonical flat thread dict (transform_review_thread shape)."""
    return {"thread_id": thread_id, "path": path, "first_comment_body": body}


# Eight restates of the same finding across eight files, each paraphrased the
# way Copilot/CodeRabbit re-word a finding on a rescan. The load-bearing tokens
# (model, tier, opus, contradicts/cheaper) recur; the filler varies.
_ASYMMETRY_BODIES = [
    "The model_tier is set to opus here but the template claims a cheaper "
    "reviewer model tier; this contradicts the stronger model wording.",
    "model_tier opus contradicts the cheaper model tier described for the "
    "reviewer in this template section.",
    "This sets model_tier to opus yet the prose says cheaper reviewer tier. "
    "The model tier wording contradicts the opus assignment.",
    "Reviewer model_tier opus contradicts the cheaper-tier claim. The model "
    "tier asymmetry framing is wrong.",
    "opus model_tier here contradicts the template's cheaper model tier "
    "reviewer framing.",
    "The model tier (opus) contradicts the cheaper reviewer model tier this "
    "template asserts.",
    "model_tier opus assignment contradicts cheaper model tier reviewer "
    "wording, an asymmetry framing problem.",
    "This opus model_tier contradicts the cheaper-tier reviewer model "
    "framing described nearby.",
]

_HARMFUL_BODIES = [
    "The harmful-content threshold here is too low and rejects benign "
    "fixtures; raise the harmful threshold boundary.",
    "harmful threshold boundary rejects benign input; the harmful content "
    "threshold value is misconfigured.",
]

_SESSION_LOG_BODIES = [
    "The session-log naming pattern violates the protocol; rename the session "
    "log file to the canonical session naming format.",
    "session log naming does not match the protocol session naming convention "
    "for the session log file.",
    "This session-log filename breaks the session naming protocol; the "
    "session log naming convention requires the dated slug.",
]

_EVIDENCE_DRIFT_BODIES = [
    "The evidence-standards section drifted from the canonical evidence "
    "hierarchy levels; sync the evidence section drift.",
    "evidence section drift: the evidence hierarchy levels documented here no "
    "longer match the canonical evidence standards.",
]


def _build_pr_1897_round7_threads() -> list[dict]:
    threads: list[dict] = []
    for index, body in enumerate(_ASYMMETRY_BODIES):
        threads.append(_thread(f"asym-{index}", f"templates/agents/file_{index}.md", body))
    for index, body in enumerate(_HARMFUL_BODIES):
        threads.append(_thread(f"harm-{index}", "guard-maturity/thresholds.py", body))
    for index, body in enumerate(_SESSION_LOG_BODIES):
        threads.append(_thread(f"sess-{index}", "scripts/session_log.py", body))
    threads.append(
        _thread(
            "agg-0",
            "guard-maturity/run_report.py",
            "The aggregate exit code returns zero on a partial aggregate "
            "failure; the aggregate exit-code branch swallows the failure.",
        )
    )
    for index, body in enumerate(_EVIDENCE_DRIFT_BODIES):
        threads.append(_thread(f"ev-{index}", "templates/agents/evidence.md", body))
    return threads


# 8 + 2 + 3 + 1 + 2 == 16, the retrospective's itemized per-cluster counts.
PR_1897_ROUND7_THREADS = _build_pr_1897_round7_threads()


class TestExtractGist:
    def test_splits_snake_case_into_load_bearing_parts(self):
        mod = _load_module()
        gist = mod.extract_gist("The model_tier is opus here.")
        assert "model" in gist
        assert "tier" in gist
        assert "opus" in gist

    def test_drops_short_tokens_and_stopwords(self):
        mod = _load_module()
        gist = mod.extract_gist("This should consider the change here.")
        # All tokens are stopwords or under the length floor; nothing survives.
        assert gist == frozenset()

    def test_empty_body_returns_empty_gist(self):
        mod = _load_module()
        assert mod.extract_gist("") == frozenset()

    def test_none_body_returns_empty_gist(self):
        mod = _load_module()
        assert mod.extract_gist(None) == frozenset()

    def test_backticked_token_matches_plain_token(self):
        mod = _load_module()
        backticked = mod.extract_gist("Fix `model_tier` opus assignment.")
        plain = mod.extract_gist("Fix model_tier opus assignment.")
        assert backticked == plain


class TestGistSimilarity:
    def test_identical_gists_score_one(self):
        mod = _load_module()
        gist = frozenset({"model", "tier", "opus"})
        assert mod.gist_similarity(gist, gist) == 1.0

    def test_disjoint_gists_score_zero(self):
        mod = _load_module()
        left = frozenset({"model", "tier"})
        right = frozenset({"harmful", "threshold"})
        assert mod.gist_similarity(left, right) == 0.0

    def test_empty_gist_scores_zero(self):
        mod = _load_module()
        assert mod.gist_similarity(frozenset(), frozenset({"opus"})) == 0.0

    def test_partial_overlap_is_jaccard(self):
        mod = _load_module()
        left = frozenset({"model", "tier", "opus"})
        right = frozenset({"model", "tier", "cheaper"})
        # intersection 2 (model, tier) over union 4 -> 0.5
        assert mod.gist_similarity(left, right) == 0.5


class TestClusterThreadsPr1897Regression:
    def test_detects_eight_thread_asymmetry_cluster(self):
        mod = _load_module()
        report = mod.cluster_threads(PR_1897_ROUND7_THREADS)
        assert report["warning"] is True
        sizes = [c["size"] for c in report["clusters"]]
        # The 8-thread asymmetry cluster is the single 4+ cluster; the other
        # round-7 clusters (2, 3, 1, 2) are below the warning threshold.
        assert 8 in sizes

    def test_asymmetry_cluster_leads_and_names_load_bearing_tokens(self):
        mod = _load_module()
        report = mod.cluster_threads(PR_1897_ROUND7_THREADS)
        top = report["clusters"][0]
        assert top["size"] == 8
        # The framing tokens that recur across all eight restates.
        assert "model" in top["shared_tokens"]
        assert "tier" in top["shared_tokens"]
        assert "opus" in top["shared_tokens"]

    def test_thread_count_matches_round7_itemized_breakdown(self):
        mod = _load_module()
        report = mod.cluster_threads(PR_1897_ROUND7_THREADS)
        # 8 asymmetry + 2 harmful + 3 session-log + 1 aggregate + 2 evidence.
        assert report["thread_count"] == 16

    def test_source_artifact_points_at_a_clustered_path(self):
        mod = _load_module()
        report = mod.cluster_threads(PR_1897_ROUND7_THREADS)
        top = report["clusters"][0]
        # Every asymmetry thread lives under templates/agents/; the named
        # artifact is one of those eight paths, not a non-cluster path.
        assert top["source_artifact"] in top["paths"]
        assert top["source_artifact"].startswith("templates/agents/")


class TestClusterThreadsThreshold:
    def test_no_warning_below_threshold(self):
        mod = _load_module()
        # Three identical-gist threads: a real group but under the 4 floor.
        threads = [
            _thread(f"t{index}", "a.py", "model_tier opus contradicts cheaper tier")
            for index in range(3)
        ]
        report = mod.cluster_threads(threads)
        assert report["warning"] is False
        assert report["cluster_count"] == 0
        assert report["clusters"] == []

    def test_warning_exactly_at_threshold(self):
        mod = _load_module()
        threads = [
            _thread(f"t{index}", "a.py", "model_tier opus contradicts cheaper tier")
            for index in range(4)
        ]
        report = mod.cluster_threads(threads)
        assert report["warning"] is True
        assert report["cluster_count"] == 1
        assert report["clusters"][0]["size"] == 4

    def test_empty_thread_list_produces_no_warning(self):
        mod = _load_module()
        report = mod.cluster_threads([])
        assert report["thread_count"] == 0
        assert report["warning"] is False
        assert report["clusters"] == []

    def test_token_poor_threads_do_not_cluster(self):
        mod = _load_module()
        # Bodies whose only words are stopwords/short: each gist is empty, so no
        # two can reach the similarity threshold and no cluster forms.
        threads = [
            _thread(f"t{index}", "a.py", "this should change here")
            for index in range(6)
        ]
        report = mod.cluster_threads(threads)
        assert report["warning"] is False

    def test_distinct_findings_stay_separate(self):
        mod = _load_module()
        # Four distinct findings, no shared load-bearing tokens: no cluster.
        threads = [
            _thread("t0", "a.py", "the harmful threshold boundary rejects benign fixtures"),
            _thread("t1", "b.py", "session log naming violates the dated slug protocol"),
            _thread("t2", "c.py", "aggregate exit code swallows partial failure branch"),
            _thread("t3", "d.py", "evidence hierarchy levels drifted from canonical standards"),
        ]
        report = mod.cluster_threads(threads)
        assert report["warning"] is False
        assert report["cluster_count"] == 0


class TestSourceArtifactIdentification:
    def test_most_common_path_wins(self):
        mod = _load_module()
        threads = [
            _thread("t0", "common.py", "model tier opus contradicts cheaper"),
            _thread("t1", "common.py", "model tier opus contradicts cheaper"),
            _thread("t2", "other.py", "model tier opus contradicts cheaper"),
        ]
        assert mod._identify_source_artifact(threads) == "common.py"

    def test_returns_none_when_no_paths(self):
        mod = _load_module()
        threads = [{"first_comment_body": "x"}, {"path": None, "first_comment_body": "y"}]
        assert mod._identify_source_artifact(threads) is None

    def test_tie_keeps_first_seen_path(self):
        mod = _load_module()
        threads = [
            _thread("t0", "first.py", "a"),
            _thread("t1", "second.py", "b"),
        ]
        assert mod._identify_source_artifact(threads) == "first.py"


class TestTransitiveClustering:
    def test_paraphrase_chain_links_into_one_cluster(self):
        mod = _load_module()
        # A-B share {model, tier}; B-C share {tier, opus}; A-C share only
        # {tier} (below 0.5 alone) but transitively join via B. Four members
        # so the cluster trips the warning.
        threads = [
            _thread("a", "f.py", "model tier framing"),
            _thread("b", "f.py", "model tier opus framing"),
            _thread("c", "f.py", "tier opus cheaper"),
            _thread("d", "f.py", "model tier opus cheaper"),
        ]
        report = mod.cluster_threads(threads)
        assert report["warning"] is True
        assert report["clusters"][0]["size"] == 4


class TestCli:
    def _run(self, args: list[str], input_text: str | None = None):
        return subprocess.run(
            [sys.executable, _SCRIPT, *args],
            capture_output=True,
            text=True,
            input=input_text,
        )

    def test_threads_file_path_produces_report(self, tmp_path):
        threads_file = tmp_path / "threads.json"
        threads_file.write_text(
            json.dumps({"threads": PR_1897_ROUND7_THREADS}), encoding="utf-8",
        )
        result = self._run(
            ["--pull-request", "1897", "--threads-file", str(threads_file)],
        )
        assert result.returncode == 0
        report = json.loads(result.stdout)
        assert report["pull_request"] == 1897
        assert report["warning"] is True
        assert 8 in [c["size"] for c in report["clusters"]]

    def test_bare_list_threads_file_is_accepted(self, tmp_path):
        threads_file = tmp_path / "threads.json"
        threads_file.write_text(
            json.dumps(PR_1897_ROUND7_THREADS), encoding="utf-8",
        )
        result = self._run(
            ["--pull-request", "1897", "--threads-file", str(threads_file)],
        )
        assert result.returncode == 0
        report = json.loads(result.stdout)
        assert report["thread_count"] == 16

    def test_nonpositive_pull_request_exits_2(self, tmp_path):
        threads_file = tmp_path / "threads.json"
        threads_file.write_text("[]", encoding="utf-8")
        result = self._run(
            ["--pull-request", "0", "--threads-file", str(threads_file)],
        )
        assert result.returncode == 2

    def test_missing_threads_file_exits_2(self):
        result = self._run(
            ["--pull-request", "1897", "--threads-file", "/no/such/file.json"],
        )
        assert result.returncode == 2

    def test_malformed_threads_file_exits_2(self, tmp_path):
        threads_file = tmp_path / "threads.json"
        threads_file.write_text("{not json", encoding="utf-8")
        result = self._run(
            ["--pull-request", "1897", "--threads-file", str(threads_file)],
        )
        assert result.returncode == 2

    def test_threads_file_wrong_shape_exits_2(self, tmp_path):
        threads_file = tmp_path / "threads.json"
        threads_file.write_text(json.dumps({"threads": 42}), encoding="utf-8")
        result = self._run(
            ["--pull-request", "1897", "--threads-file", str(threads_file)],
        )
        assert result.returncode == 2

    def test_missing_required_pull_request_exits_2(self):
        result = self._run([])
        # argparse exits 2 on a missing required argument.
        assert result.returncode == 2
