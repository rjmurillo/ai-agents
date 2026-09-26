"""Unit tests for scripts/eval/eval_model_routing.py: CLI and rendering.

Offline: no network, no subprocess, no live eval run. Covers main() routing
across subjects, undecided entries for missing or degraded reports, config
exit codes, and the Markdown and JSON renderers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_model_routing_helpers import (
    make_ladder,
    make_reports_dir,
    report_dict,
    routing,
    write_fixtures,
    write_report,
)

# --- main(): agent subject ignores skill dirs, routes independently -----------


def test_main_routes_agent_and_skill_subjects_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "analyst"
    fixtures_dir = write_fixtures(tmp_path, agent)
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = make_reports_dir(tmp_path, agent)

    # Agent variant: haiku ties the best (opus/sonnet at 1.0) within margin.
    write_report(
        reports_dir, "sweep-claude-haiku-4-5-a1", report_dict("claude-haiku-4-5", sha, 0.95)
    )
    write_report(reports_dir, "sweep-claude-sonnet-5-a1", report_dict("claude-sonnet-5", sha, 1.0))
    write_report(reports_dir, "sweep-claude-opus-5-5-a1", report_dict("claude-opus-5-5", sha, 1.0))

    # Skill variant (analyze): haiku clearly trails. Same model ids and sha
    # as the agent rows above, so a broken skill-prefix filter would collide.
    write_report(
        reports_dir,
        "sweep-skill-analyze-claude-haiku-4-5-s1",
        report_dict("claude-haiku-4-5", sha, 0.3, skill_rate=0.5, skill_agent_rate=0.3),
    )
    write_report(
        reports_dir,
        "sweep-skill-analyze-claude-sonnet-5-s1",
        report_dict("claude-sonnet-5", sha, 0.3, skill_rate=1.0, skill_agent_rate=0.3),
    )
    write_report(
        reports_dir,
        "sweep-skill-analyze-claude-opus-5-5-s1",
        report_dict("claude-opus-5-5", sha, 0.3, skill_rate=1.0, skill_agent_rate=0.3),
    )

    out_dir = tmp_path / "routing-out"
    rc = routing.main(
        [
            "--agents",
            agent,
            "--skill",
            f"analyze={agent}",
            "--ladder",
            "claude=claude-haiku-4-5,claude-sonnet-5,claude-opus-5-5",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == routing.EXIT_OK

    payload = json.loads((out_dir / "routing.json").read_text(encoding="utf-8"))
    by_kind = {(e["kind"], e["subject"]): e for e in payload["entries"]}
    agent_entry = by_kind[("agent", agent)]
    skill_entry = by_kind[("skill", "analyze")]
    assert "error" not in agent_entry
    assert "error" not in skill_entry
    # The agent variant's cheapest model ties the best; the skill variant's
    # cheapest model clearly trails, so the two subjects route differently
    # even though they share the same fixtures, models, and sha.
    assert agent_entry["routing"]["lightest_sufficient_model"] == "claude-haiku-4-5"
    assert skill_entry["routing"]["lightest_sufficient_model"] == "claude-sonnet-5"


# --- main(): zero and two matches produce an undecided entry, not a crash -----


def test_main_reports_zero_and_two_match_errors_but_still_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "analyst"
    write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = make_reports_dir(tmp_path, agent)

    # haiku: exactly one match, reused by both ladders below.
    write_report(
        reports_dir, "sweep-claude-haiku-4-5-r1", report_dict("claude-haiku-4-5", sha, 0.9)
    )
    # sonnet: two matches (ambiguous).
    write_report(reports_dir, "sweep-claude-sonnet-5-r1", report_dict("claude-sonnet-5", sha, 1.0))
    write_report(reports_dir, "sweep-claude-sonnet-5-r2", report_dict("claude-sonnet-5", sha, 0.8))
    # opus: zero matches, no report written for it at all.

    out_dir = tmp_path / "routing-out"
    rc = routing.main(
        [
            "--agents",
            agent,
            "--ladder",
            "zero=claude-haiku-4-5,claude-opus-5-5",
            "--ladder",
            "two=claude-haiku-4-5,claude-sonnet-5",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == routing.EXIT_LOGIC

    payload = json.loads((out_dir / "routing.json").read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == "1"
    entries = {e["ladder"]: e for e in payload["entries"]}
    assert "found 0" in entries["zero"]["error"]
    assert "found 2" in entries["two"]["error"]

    report_md = (out_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "undecided" in report_md


# --- main(): degraded reports (error_count > 0) yield an undecided entry ------


def test_main_reports_undecided_entry_for_degraded_report(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "demo"
    write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = make_reports_dir(tmp_path, agent)
    write_report(
        reports_dir,
        "sweep-claude-haiku-4-5-r1",
        report_dict("claude-haiku-4-5", sha, 0.9, error_count=1),
    )
    write_report(reports_dir, "sweep-claude-sonnet-5-r1", report_dict("claude-sonnet-5", sha, 1.0))

    out_dir = tmp_path / "routing-out"
    rc = routing.main(
        [
            "--agents",
            agent,
            "--ladder",
            "claude=claude-haiku-4-5,claude-sonnet-5",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == routing.EXIT_LOGIC

    payload = json.loads((out_dir / "routing.json").read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    assert "error" in entry
    assert "degraded" in entry["error"]


# --- main(): happy path artifact shape -----------------------------------------


def test_main_happy_path_writes_routing_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "demo"
    write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = make_reports_dir(tmp_path, agent)
    write_report(
        reports_dir, "sweep-claude-haiku-4-5-r1", report_dict("claude-haiku-4-5", sha, 0.95)
    )
    write_report(reports_dir, "sweep-claude-sonnet-5-r1", report_dict("claude-sonnet-5", sha, 1.0))

    out_dir = tmp_path / "routing-out"
    rc = routing.main(
        [
            "--agents",
            agent,
            "--ladder",
            "claude=claude-haiku-4-5,claude-sonnet-5",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == routing.EXIT_OK

    payload = json.loads((out_dir / "routing.json").read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == "1"
    assert len(payload["entries"]) == 1
    entry = payload["entries"][0]
    assert entry["routing"]["lightest_sufficient_model"] == "claude-haiku-4-5"

    report_md = (out_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "| Kind | Subject | Fixtures |" in report_md


def test_routing_skips_cheap_model_that_clearly_trails(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "demo"
    write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = make_reports_dir(tmp_path, agent)
    write_report(
        reports_dir, "sweep-claude-haiku-4-5-r1", report_dict("claude-haiku-4-5", sha, 0.5)
    )
    write_report(reports_dir, "sweep-claude-sonnet-5-r1", report_dict("claude-sonnet-5", sha, 1.0))
    write_report(reports_dir, "sweep-claude-opus-5-5-r1", report_dict("claude-opus-5-5", sha, 1.0))

    out_dir = tmp_path / "routing-out"
    rc = routing.main(
        [
            "--agents",
            agent,
            "--ladder",
            "claude=claude-haiku-4-5,claude-sonnet-5,claude-opus-5-5",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == routing.EXIT_OK

    payload = json.loads((out_dir / "routing.json").read_text(encoding="utf-8"))
    routing_block = payload["entries"][0]["routing"]
    # opus wins the tie for "best" (alphabetically first among the two 1.0
    # scores); haiku trails it by 0.5, well past the default 0.10 margin, so
    # the walk skips haiku and lands on sonnet, which ties the best exactly.
    assert routing_block["best_model"] == "claude-opus-5-5"
    assert routing_block["lightest_sufficient_model"] == "claude-sonnet-5"


# --- main(): config errors ------------------------------------------------------


def test_main_returns_config_error_with_no_subjects(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    rc = routing.main(["--ladder", "claude=claude-haiku-4-5,claude-sonnet-5"])
    assert rc == routing.EXIT_CONFIG


@pytest.mark.parametrize("margin_value", ["-0.1", "nan"])
def test_main_returns_config_error_for_invalid_margin(tmp_path, monkeypatch, margin_value):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    rc = routing.main(
        [
            "--agents",
            "demo",
            "--ladder",
            "claude=claude-haiku-4-5,claude-sonnet-5",
            "--margin",
            margin_value,
        ]
    )
    assert rc == routing.EXIT_CONFIG


# --- _fmt and render_markdown helpers -------------------------------------------


def test_fmt_formats_none_float_and_str():
    assert routing._fmt(None) == "n/a"
    assert routing._fmt(0.5) == "0.50"
    assert routing._fmt("claude-haiku-4-5") == "claude-haiku-4-5"


def test_render_markdown_marks_missing_combo_as_not_run():
    ladders = [
        make_ladder("claude", "claude-haiku-4-5", "claude-sonnet-5"),
        make_ladder("gpt", "gpt-a", "gpt-b"),
    ]
    entries = [
        {
            "subject": "analyst",
            "kind": "agent",
            "fixtures_agent": "analyst",
            "ladder": "claude",
            "routing": {
                "lightest_sufficient_model": "claude-haiku-4-5",
                "best_model": "claude-opus-5-5",
                "margin": 0.1,
                "resolved": False,
                "candidates": [
                    {"model_id": "claude-haiku-4-5", "mean_recall": 0.9, "sufficient": True}
                ],
                "reason": "test reason",
            },
            "models": [
                {
                    "model_id": "claude-haiku-4-5",
                    "agent_recall": 0.9,
                    "baseline_recall": 0.5,
                    "cost_usd": 0.01,
                }
            ],
        }
    ]
    markdown = routing.render_markdown(entries, ladders, 0.1)
    assert "not run" in markdown
    assert "claude-haiku-4-5 (gap unproven)" in markdown


def test_render_json_writes_one_entry_per_line_and_round_trips():
    entries = [{"subject": "critic", "ladder": "claude"}, {"subject": "qa", "ladder": "gpt6"}]

    text = routing.render_json(entries, margin=0.1, seed=42)

    assert json.loads(text) == {"schemaVersion": "1", "margin": 0.1, "seed": 42, "entries": entries}
    assert text.count("\n") == len(entries) + 2
    assert json.loads(routing.render_json([], margin=0.1, seed=42))["entries"] == []


def test_main_records_missing_skill_runs_as_undecided(tmp_path, monkeypatch):
    """A skill report whose runs.jsonl is gone must not abort the rollup."""
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "critic"
    fixtures_dir = write_fixtures(tmp_path, agent)
    sha = routing.fixture_set_sha(fixtures_dir)
    reports = make_reports_dir(tmp_path, agent)
    for model in ("claude-haiku-4-5", "claude-sonnet-5"):
        run_id = f"sweep-skill-review-{model}-r1"
        write_report(reports, run_id, report_dict(model, sha, 0.5, skill_rate=0.5))
    (reports.parent / "runs" / "sweep-skill-review-claude-sonnet-5-r1" / "runs.jsonl").unlink()
    out_dir = tmp_path / "routing-out"

    rc = routing.main(
        [
            "--skill",
            "review=critic",
            "--ladder",
            "claude=claude-haiku-4-5,claude-sonnet-5",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert rc == routing.EXIT_LOGIC
    entry = json.loads((out_dir / "routing.json").read_text(encoding="utf-8"))["entries"][0]
    assert "runs/sweep-skill-review-claude-sonnet-5-r1/runs.jsonl is missing" in entry["error"]
    assert (out_dir / "REPORT.md").is_file()


def test_detail_lines_show_routed_recall_not_headline_recall():
    entry = {
        "subject": "orchestrator",
        "kind": "agent",
        "ladder": "claude",
        "routing": {
            "candidates": [
                {"model_id": "claude-haiku-4-5", "mean_recall": 0.646, "sufficient": False}
            ]
        },
        "models": [
            {
                "model_id": "claude-haiku-4-5",
                "agent_recall": 0.71,
                "baseline_recall": 0.5,
                "cost_usd": 0.01,
            }
        ],
    }

    row = routing._detail_lines([entry])[-1]

    assert row.startswith("| orchestrator | claude | claude-haiku-4-5 | 0.65 | 0.71 | 0.50 |")
    assert row.endswith("| False |")
