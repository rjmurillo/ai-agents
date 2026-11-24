"""Tests for scripts/eval/measure_actionability_band.py (plan M1-T2, M1-T3)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "measure_actionability_band.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("measure_actionability_band", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mab = _load_module()

_NOW = datetime.now(UTC).isoformat()


def _node(body: str, login: str = "reviewer", created_at: str = _NOW) -> dict[str, Any]:
    return {"body": body, "author": {"login": login}, "createdAt": created_at, "path": "a.py"}


def _thread(*nodes: dict[str, Any], resolved: bool = False) -> dict[str, Any]:
    return {"isResolved": resolved, "isOutdated": False, "comments": {"nodes": list(nodes)}}


def _pr(number: int, *threads: dict[str, Any], author: str = "owner") -> dict[str, Any]:
    return {
        "number": number,
        "author": {"login": author},
        "reviewThreads": {"nodes": list(threads)},
    }


class TestIsInBand:
    def test_band_edges_are_inclusive(self) -> None:
        assert mab.is_in_band(0.4)
        assert mab.is_in_band(0.6)

    def test_scores_outside_band_are_excluded(self) -> None:
        assert not mab.is_in_band(0.39)
        assert not mab.is_in_band(0.61)


class TestMeasureBand:
    def test_comment_with_no_pattern_counts_as_neutral_in_band(self) -> None:
        prs = [_pr(1, _thread(_node("Consider a helper here.")))]

        report = mab.measure_band(prs)

        assert report.total == 1
        assert report.in_band == 1
        assert report.neutral_no_signal == 1
        assert report.band_share == 1.0

    def test_high_severity_comment_scores_outside_band(self) -> None:
        prs = [_pr(1, _thread(_node("Critical security vulnerability: injection.")))]

        report = mab.measure_band(prs)

        assert report.in_band == 0
        assert report.neutral_no_signal == 0

    def test_replies_are_counted_separately_from_openers(self) -> None:
        opener = _node("Consider a helper here.", created_at="2026-11-20T00:00:00Z")
        reply = _node("Sounds good.", login="other", created_at="2026-11-21T00:00:00Z")
        prs = [_pr(1, _thread(opener, reply))]

        report = mab.measure_band(prs)

        assert report.openers.total == 1
        assert report.replies.total == 1
        assert report.unknown_position.total == 0

    def test_self_comments_on_own_pr_are_excluded_like_production(self) -> None:
        prs = [_pr(1, _thread(_node("note to self", login="owner")), author="owner")]

        report = mab.measure_band(prs)

        assert report.total == 0
        assert report.kill_criterion_1_fired is None

    def test_kill_criterion_1_fires_when_band_share_is_under_threshold(self) -> None:
        severe = [_thread(_node(f"Critical security issue {i}")) for i in range(20)]
        prs = [_pr(1, *severe, _thread(_node("Consider a helper here.")))]

        report = mab.measure_band(prs)

        assert report.band_share < mab.KILL_CRITERION_1_THRESHOLD
        assert report.kill_criterion_1_fired is True

    def test_kill_criterion_1_clears_at_or_above_threshold(self) -> None:
        prs = [_pr(1, _thread(_node("Consider a helper here.")))]

        assert mab.measure_band(prs).kill_criterion_1_fired is False


class TestThreadPosition:
    def test_returns_unknown_when_comment_is_not_in_its_thread(self) -> None:
        comment = mab.CommentData(
            pr_number=1,
            body="missing",
            created_at="x",
            path="a.py",
            is_resolved=False,
            is_outdated=False,
            thread_comments=[{"body": "other", "createdAt": "y"}],
        )

        assert mab.thread_position(comment) == mab.UNKNOWN_POSITION


class TestCountTruncation:
    def test_flags_pr_at_thread_limit_and_thread_at_comment_limit(self) -> None:
        full_thread = _thread(*[_node(f"c{i}") for i in range(mab.COMMENTS_PER_THREAD_LIMIT)])
        threads = [_thread(_node("x"))] * (mab.THREADS_PER_PR_LIMIT - 1) + [full_thread]
        prs = [_pr(7, *threads), _pr(8, _thread(_node("y")))]

        truncation = mab.count_truncation(prs)

        assert truncation.prs_at_thread_limit == [7]
        assert truncation.threads_at_comment_limit == 1

    def test_reports_nothing_below_limits(self) -> None:
        truncation = mab.count_truncation([_pr(1, _thread(_node("x")))])

        assert truncation.prs_at_thread_limit == []
        assert truncation.threads_at_comment_limit == 0

    def test_tolerates_null_connections(self) -> None:
        prs = [
            {"number": 1, "reviewThreads": None},
            {"number": 2, "reviewThreads": {"nodes": [{"comments": None}]}},
        ]

        truncation = mab.count_truncation(prs)

        assert truncation.prs_at_thread_limit == []


class TestMain:
    def test_writes_result_from_json_and_returns_zero(self, tmp_path: Path) -> None:
        source = tmp_path / "prs.json"
        source.write_text(
            json.dumps([_pr(1, _thread(_node("Consider a helper.")))]), encoding="utf-8"
        )
        output = tmp_path / "out" / "result.json"

        code = mab.main(["--from-json", str(source), "--output", str(output)])

        assert code == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["total"] == 1
        assert payload["source"] == "file"
        assert payload["kill_criterion_1_fired"] is False

    def test_returns_two_on_unreadable_input(self, tmp_path: Path) -> None:
        code = mab.main(
            ["--from-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "o.json")]
        )

        assert code == 2

    def test_returns_two_when_input_is_not_a_list(self, tmp_path: Path) -> None:
        source = tmp_path / "prs.json"
        source.write_text("{}", encoding="utf-8")

        assert mab.main(["--from-json", str(source), "--output", str(tmp_path / "o.json")]) == 2

    def test_returns_two_on_out_of_range_days_back(self, tmp_path: Path) -> None:
        assert mab.main(["--days-back", "0", "--output", str(tmp_path / "o.json")]) == 2

    def test_returns_three_when_github_fetch_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail(*_args: object, **_kwargs: object) -> list[dict[str, Any]]:
            raise RuntimeError("Pagination exceeded")

        monkeypatch.setattr(
            mab,
            "resolve_repo_params",
            lambda owner, repo: type("P", (), {"owner": "o", "repo": "r"})(),
        )
        monkeypatch.setattr(mab, "get_all_prs_with_comments", _fail)
        output = tmp_path / "o.json"

        code = mab.main(["--output", str(output)])

        assert code == 3
        assert not output.exists()

    def test_github_source_records_window_semantics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            mab,
            "resolve_repo_params",
            lambda owner, repo: type("P", (), {"owner": "o", "repo": "r"})(),
        )
        monkeypatch.setattr(mab, "get_all_prs_with_comments", lambda owner, repo, since: [])
        output = tmp_path / "o.json"

        assert mab.main(["--output", str(output)]) == 0

        payload = json.loads(output.read_text(encoding="utf-8"))
        assert "updatedAt" in payload["window"]
        assert payload["kill_criterion_1_fired"] is None


class TestSavePrs:
    def test_save_prs_writes_the_fetched_nodes_to_the_named_file(self, tmp_path: Path) -> None:
        """Hygiene 6d: --save-prs persists the PR nodes the run scored."""
        prs = [_pr(1, _thread(_node("Consider a helper.")))]
        source = tmp_path / "prs.json"
        source.write_text(json.dumps(prs), encoding="utf-8")
        saved = tmp_path / "saved" / "prs.json"

        code = mab.main(
            [
                "--from-json",
                str(source),
                "--save-prs",
                str(saved),
                "--output",
                str(tmp_path / "result.json"),
            ]
        )

        assert code == 0
        assert json.loads(saved.read_text(encoding="utf-8")) == prs


class TestHeadSha:
    def test_returns_unknown_when_git_cannot_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hygiene 6d: a missing git binary yields "unknown", not a crash."""

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("no git")

        monkeypatch.setattr(subprocess, "run", _boom)

        assert mab.head_sha() == "unknown"

    def test_returns_unknown_when_git_times_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hygiene 6d: a hung git yields "unknown"."""

        def _timeout(*_args: object, **_kwargs: object) -> None:
            raise subprocess.TimeoutExpired(cmd="git", timeout=10)

        monkeypatch.setattr(subprocess, "run", _timeout)

        assert mab.head_sha() == "unknown"

    def test_returns_unknown_when_git_prints_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hygiene 6d: empty stdout yields "unknown"."""
        done = subprocess.CompletedProcess(args=["git"], returncode=128, stdout="", stderr="x")
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: done)

        assert mab.head_sha() == "unknown"

    def test_returns_the_trimmed_sha_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hygiene 6d: the happy path strips the trailing newline."""
        done = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="abc123\n")
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: done)

        assert mab.head_sha() == "abc123"


class TestFetchErrorText:
    def test_github_fetch_failure_logs_the_class_name_never_the_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Group 3d: a GraphQL error can embed a response body, so only its class is logged."""

        def _leak(*_args: object, **_kwargs: object) -> list[dict[str, Any]]:
            raise RuntimeError("response body SECRETWORD ghp_leaked")

        monkeypatch.setattr(
            mab,
            "resolve_repo_params",
            lambda owner, repo: type("P", (), {"owner": "o", "repo": "r"})(),
        )
        monkeypatch.setattr(mab, "get_all_prs_with_comments", _leak)

        code = mab.main(["--output", str(tmp_path / "o.json")])

        assert code == 3
        assert "RuntimeError" in caplog.text
        assert "SECRETWORD" not in caplog.text
        assert "ghp_leaked" not in caplog.text


class TestFromJsonProvenance:
    def test_from_json_records_only_the_basename(self, tmp_path: Path) -> None:
        """Group 5c: the result must not leak the operator's directory layout."""
        nested = tmp_path / "private" / "scratch"
        nested.mkdir(parents=True)
        source = nested / "prs.json"
        source.write_text(json.dumps([]), encoding="utf-8")
        out = tmp_path / "result.json"

        code = mab.main(["--from-json", str(source), "--output", str(out)])

        text = out.read_text(encoding="utf-8")
        payload = json.loads(text)
        assert code == 0
        assert payload["path"] == "prs.json"
        assert "private" not in text
        assert str(tmp_path) not in text


class TestKillCriterionOnTheExactRatio:
    """Plan M1-T5, review finding 2: decide on in_band / total, round for display only."""

    @pytest.mark.parametrize(
        ("in_band", "total", "expected"),
        [
            (1999, 40000, True),
            (2000, 40000, False),
            (0, 100, True),
            (5, 100, False),
            (4, 100, True),
            (1, 1, False),
        ],
    )
    def test_threshold_decision_uses_the_unrounded_share(
        self, in_band: int, total: int, expected: bool
    ) -> None:
        """1999 of 40000 is 4.9975 percent. It rounds to 5.00 and must still fire."""
        assert mab.kill_criterion_1_fired(in_band, total) is expected

    def test_no_comments_means_no_decision(self) -> None:
        """An empty set cannot clear or fire the criterion."""
        assert mab.kill_criterion_1_fired(0, 0) is None

    def _patch_scores(self, monkeypatch: pytest.MonkeyPatch, total: int, in_band: int) -> None:
        comments = [
            mab.CommentData(
                pr_number=1,
                body=f"c{i}",
                created_at="2026-11-20T00:00:00Z",
                path="a.py",
                is_resolved=False,
                is_outdated=False,
                thread_comments=[],
            )
            for i in range(total)
        ]
        stats = type("S", (), {"comments": comments})()
        monkeypatch.setattr(mab, "get_comments_by_reviewer", lambda _prs: {"r": stats})
        position = {"i": 0}

        def _score(_comment: object, llm_classifier: object = None) -> object:
            position["i"] += 1
            score = 0.5 if position["i"] <= in_band else 0.9
            return type("R", (), {"score": score, "reasons": ["x"]})()

        monkeypatch.setattr(mab, "get_actionability_score", _score)

    def test_measure_band_fires_at_1999_of_40000_though_the_share_rounds_to_five_percent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The displayed share is 0.05, the decision is still 'fired'."""
        self._patch_scores(monkeypatch, total=40000, in_band=1999)

        report = mab.measure_band([])

        assert report.total == 40000
        assert report.in_band == 1999
        assert report.band_share == 0.05
        assert report.kill_criterion_1_fired is True

    def test_main_writes_the_exact_decision_and_the_rounded_share(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Driven through main(argv): the result file carries both values."""
        self._patch_scores(monkeypatch, total=40000, in_band=1999)
        source = tmp_path / "prs.json"
        source.write_text("[]", encoding="utf-8")
        out = tmp_path / "result.json"

        code = mab.main(["--from-json", str(source), "--output", str(out)])

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert payload["band_share"] == 0.05
        assert payload["kill_criterion_1_fired"] is True

    def test_measure_band_does_not_fire_at_exactly_five_percent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """2000 of 40000 is exactly 0.05, which is not under the threshold."""
        self._patch_scores(monkeypatch, total=40000, in_band=2000)

        assert mab.measure_band([]).kill_criterion_1_fired is False
