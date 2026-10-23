"""Offline checks for spec.json S8, the withheld-endpoint scenario (issue #6737).

S7 named the endpoint, so the no-skill baseline chose it 12 of 12 times and the
run could not show uplift. S8 removes that sentence, so the baseline can fail.
It declares one proof point, `row_equality_check`, which the runner grades with
a fixed pattern. These tests pin the scenario shape, the loader's checks on
`proof_points`, and the pattern against known responses, including all 24
stored S7 responses. No model is called.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.test_spec_reframing_scenarios import DATA, SCENARIO_FILE, runner

REPO_ROOT = Path(__file__).resolve().parents[2]
S7_RECORD = (
    REPO_ROOT
    / ".project-toolkit"
    / "eval-results"
    / "2026-10-23-issue-6737-spec-option-free-claude-cli.json"
)
ENDPOINT_SENTENCE = (
    " The same service documents a read-only endpoint, GET /api/v1/failures?team=<id>,"
    " that returns those rows as JSON."
)

PASSES = [
    "Check: the endpoint's rows equal the dashboard's Export CSV for the same team and week.",
    "Validate by diffing one week's output against the manual CSV export.",
    "Success check: the generated list matches the dashboard export row for row.",
    "Compare the API result to the exported CSV for one week before switching over.",
    "Reconcile the counts against the dashboard export for the first two Mondays.",
    "Proof point: for one team, the API rows are identical to the Export CSV rows.",
]
FAILS = [
    "Parse the JSON and extract failing test names directly, no CSV/UI steps needed.",
    "Parse the CSV for failing tests, aggregate per team.",
    "Format results to match the existing report and post to Slack.",
    "Hit the dashboard's export endpoint directly each week.",
    "If no API exists, a headless browser script automating the Export CSV click is the fallback.",
    "Run Playwright every Monday: log in, pick the team, click Export CSV, parse the file.",
]


def _by_id(scenario_id: str) -> dict[str, Any]:
    return next(s for s in DATA["scenarios"] if s["id"] == scenario_id)


def _grade(text: str) -> bool:
    return runner.grade_proof_points(_by_id("S8"), text)["row_equality_check"]


def _write(tmp_path: Path, data: dict[str, Any]) -> str:
    target = tmp_path / "spec.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return str(target)


class TestShape:
    def test_judge_scored_positive_case(self) -> None:
        s8 = _by_id("S8")
        assert "decision" not in s8
        assert s8["expected_gate"] == _by_id("S7")["expected_gate"]

    def test_prompt_is_s7_without_the_endpoint_sentence(self) -> None:
        assert ENDPOINT_SENTENCE in _by_id("S7")["input"]
        assert _by_id("S8")["input"] == _by_id("S7")["input"].replace(ENDPOINT_SENTENCE, "")

    def test_prompt_names_no_machine_interface(self) -> None:
        text = _by_id("S8")["input"].lower()
        for token in ("api", "endpoint", "json", "get /", "interface", "database"):
            assert token not in text, f"S8 prompt cues the answer with {token!r}"

    def test_expected_signals_hold_no_doctrine_keywords(self) -> None:
        signals = " ".join(_by_id("S8")["expected_signals"]).lower()
        for banned in ("capability", "invention", "reframing", "architecture"):
            assert banned not in signals.split()

    def test_rationale_fails_browser_scripting_and_passes_the_row_check(self) -> None:
        rationale = " ".join(_by_id("S8")["rationale"].split())
        sentences = [s for s in rationale.split(". ") if s]
        failing = [s for s in sentences if "is the failure" in s]
        passing = [s for s in sentences if "is the pass" in s]
        assert len(failing) == 1
        assert len(passing) == 1
        assert "script the browser steps" in failing[0]
        assert "machine interface" in passing[0]
        assert "rows equal the dashboard export" in passing[0]

    def test_declares_one_proof_point(self) -> None:
        points = _by_id("S8")["proof_points"]
        assert [p["id"] for p in points] == ["row_equality_check"]
        assert runner._proof_point_spec_error(points) is None

    def test_scenario_ids_stay_unique(self) -> None:
        ids = [s["id"] for s in DATA["scenarios"]]
        assert len(ids) == len(set(ids))


class TestProofPointPattern:
    @pytest.mark.parametrize("text", PASSES)
    def test_names_a_row_equality_check(self, text: str) -> None:
        assert _grade(text)

    @pytest.mark.parametrize("text", FAILS)
    def test_mentions_without_a_check_do_not_count(self, text: str) -> None:
        assert not _grade(text)

    def test_case_insensitive(self) -> None:
        assert _grade("COMPARE THE OUTPUT WITH THE DASHBOARD EXPORT.")

    def test_matches_none_of_the_stored_s7_responses(self) -> None:
        """The S7 record was hand-checked: 0 of 24 responses name a row-equality check."""
        record = json.loads(S7_RECORD.read_text(encoding="utf-8"))
        responses = [cell["response"] for run in record["per_run"] for cell in run["arms"].values()]
        assert len(responses) == 24
        assert [r for r in responses if _grade(r)] == []


class TestLoader:
    def test_loader_accepts_the_file(self) -> None:
        loaded = runner._load_scenarios_file(str(SCENARIO_FILE))
        assert not isinstance(loaded, int), f"runner refused the file with exit {loaded}"

    @pytest.mark.parametrize(
        ("points", "message"),
        [
            ([], "non-empty list"),
            ("x", "non-empty list"),
            ([{"id": "a", "pattern": "("}], "does not compile"),
            ([{"id": "a", "pattern": "x"}, {"id": "a", "pattern": "y"}], "repeats"),
            ([{"id": " ", "pattern": "x"}], "id must be"),
            ([{"id": "a", "pattern": ""}], "pattern must be"),
            (["a"], "must be an object"),
        ],
    )
    def test_loader_refuses_a_bad_proof_point(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        points: object,
        message: str,
    ) -> None:
        broken = json.loads(json.dumps(DATA))
        next(s for s in broken["scenarios"] if s["id"] == "S8")["proof_points"] = points
        assert runner._load_scenarios_file(_write(tmp_path, broken)) == 2
        assert message in capsys.readouterr().err


class TestRunnerRecordsTheProofPoint:
    def test_each_cell_carries_the_graded_proof_point(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answers = iter(["Run Playwright to click Export CSV.", PASSES[0]])
        monkeypatch.setattr(runner, "_call_api", lambda *a, **k: next(answers))
        monkeypatch.setattr(
            runner,
            "score_response",
            lambda *a, **k: {
                "activation_score": 3,
                "citation_score": 3,
                "behavior_score": 3,
                "judge_failed": False,
            },
        )
        monkeypatch.setattr(runner, "RATE_LIMIT_SLEEP_SEC", 0)
        result = runner.eval_one_scenario(
            "",
            {"description": "d", "body": "b"},
            "spec",
            _by_id("S8"),
            "m",
            dry_run=False,
            arms=("baseline", "full"),
        )
        cells = result["mechanisms"]
        assert cells["baseline"]["proof_points"] == {"row_equality_check": False}
        assert cells["full"]["proof_points"] == {"row_equality_check": True}

    def test_scenario_without_proof_points_records_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner, "_call_api", lambda *a, **k: "answer")
        monkeypatch.setattr(
            runner,
            "score_response",
            lambda *a, **k: {
                "activation_score": 3,
                "citation_score": 3,
                "behavior_score": 3,
                "judge_failed": False,
            },
        )
        monkeypatch.setattr(runner, "RATE_LIMIT_SLEEP_SEC", 0)
        result = runner.eval_one_scenario(
            "", {"description": "d", "body": "b"}, "spec", _by_id("S7"), "m", dry_run=False
        )
        assert all("proof_points" not in cell for cell in result["mechanisms"].values())
