"""Unit tests for scripts/eval/eval_model_routing.py: parsing and report lookup.

Offline: no network, no subprocess, no live eval run. Covers ladder and skill
argument parsing, the fixture-set identity hash, agent and skill report
scoping, flaky rescoring, and skill-variant rate reconstruction.
"""

from __future__ import annotations

import argparse
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

# --- parse_ladder ------------------------------------------------------------


def test_parse_ladder_valid():
    ladder = routing.parse_ladder("claude=claude-haiku-4-5,claude-sonnet-5,claude-opus-5-5")
    assert ladder.name == "claude"
    assert ladder.models == ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5-5")


def test_parse_ladder_missing_equals():
    with pytest.raises(argparse.ArgumentTypeError):
        routing.parse_ladder("claude-haiku-4-5,claude-sonnet-5")


def test_parse_ladder_too_few_models():
    with pytest.raises(argparse.ArgumentTypeError):
        routing.parse_ladder("claude=claude-haiku-4-5")


def test_parse_ladder_blank_name():
    with pytest.raises(argparse.ArgumentTypeError):
        routing.parse_ladder("=claude-haiku-4-5,claude-sonnet-5")


# --- parse_skill ---------------------------------------------------------------


def test_parse_skill_valid():
    subject = routing.parse_skill("analyze=analyst")
    assert subject.name == "analyze"
    assert subject.agent == "analyst"
    assert subject.variant == "skill"


def test_parse_skill_missing_equals():
    with pytest.raises(argparse.ArgumentTypeError):
        routing.parse_skill("analyzeanalyst")


def test_parse_skill_blank_skill():
    with pytest.raises(argparse.ArgumentTypeError):
        routing.parse_skill("=analyst")


def test_parse_skill_blank_agent():
    with pytest.raises(argparse.ArgumentTypeError):
        routing.parse_skill("analyze=")


# --- fixture_set_sha -----------------------------------------------------------


def test_fixture_set_sha_is_deterministic(tmp_path):
    fixtures_dir = write_fixtures(tmp_path, "demo")
    sha1 = routing.fixture_set_sha(fixtures_dir)
    sha2 = routing.fixture_set_sha(fixtures_dir)
    assert sha1 == sha2
    assert len(sha1) == 64


def test_fixture_set_sha_changes_when_fixture_changes(tmp_path):
    fixtures_dir = write_fixtures(tmp_path, "demo")
    original_sha = routing.fixture_set_sha(fixtures_dir)
    (fixtures_dir / "f0.json").write_text(
        json.dumps({"id": "f0", "prompt": "changed"}), encoding="utf-8"
    )
    changed_sha = routing.fixture_set_sha(fixtures_dir)
    assert changed_sha != original_sha


# --- as_variant ------------------------------------------------------------------


def test_as_variant_raises_without_form_factor():
    report = {"_path": "evals/demo-spike/reports/sweep-x", "per_fixture_pass_rates": {}}
    with pytest.raises(routing.RollupError, match="no skill variant"):
        routing.as_variant(report, "skill")


# --- find_report: stale sha, zero/two matches, skill prefix scoping ------------


def test_find_report_rejects_stale_fixture_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "demo"
    fixtures_dir = write_fixtures(tmp_path, agent)
    current_sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = make_reports_dir(tmp_path, agent)
    write_report(
        reports_dir,
        "sweep-claude-haiku-4-5-old",
        report_dict("claude-haiku-4-5", "a-stale-sha-value", 0.9),
    )
    subject = routing.Subject(name=agent, agent=agent, variant="agent")
    with pytest.raises(routing.RollupError, match="found 0"):
        routing.find_report(reports_dir, subject, "claude-haiku-4-5", current_sha)


def test_route_subject_skill_matches_only_its_own_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "analyst"
    fixtures_dir = write_fixtures(tmp_path, agent)
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = make_reports_dir(tmp_path, agent)
    ladder = make_ladder("claude", "claude-haiku-4-5", "claude-sonnet-5")

    for skill in ("analyze", "review"):
        for model, rate in (("claude-haiku-4-5", 0.9), ("claude-sonnet-5", 1.0)):
            report = report_dict(model, sha, 0.3, skill_rate=rate, skill_agent_rate=0.3)
            write_report(reports_dir, f"sweep-skill-{skill}-{model}-r1", report)

    parse = routing._load_sweep_module().parse_report
    for skill in ("analyze", "review"):
        subject = routing.Subject(name=skill, agent=agent, variant="skill")
        entry = routing.route_subject(
            subject, ladder, parse=parse, margin=routing.DEFAULT_ROUTING_MARGIN, seed=42
        )
        assert entry["subject"] == skill
        assert {row["model_id"] for row in entry["models"]} == {
            "claude-haiku-4-5",
            "claude-sonnet-5",
        }


# --- flaky rescoring, relative paths, loader guard -----------------------------


def test_find_report_rescores_flaky_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    fixtures = write_fixtures(tmp_path, "critic")
    sha = routing.fixture_set_sha(fixtures)
    reports = make_reports_dir(tmp_path, "critic")
    report = report_dict("claude-haiku-4-5", sha, 0.5)
    report["flaky_fixtures_excluded"] = ["f0", "f1"]
    write_report(reports, "sweep-claude-haiku-4-5-aaaaaaaa", report)
    subject = routing.Subject(name="critic", agent="critic", variant="agent")

    found = routing.find_report(reports, subject, "claude-haiku-4-5", sha)

    assert found["flaky_fixtures_excluded"] == []
    assert found["_flaky_count"] == 2
    assert routing._model_row(found)["flaky_fixtures_rescored"] == 2


def test_include_flaky_handles_missing_key():
    view = routing.include_flaky({"model_id": "m"})
    assert view["_flaky_count"] == 0
    assert view["flaky_fixtures_excluded"] == []


def test_find_report_error_names_repo_relative_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    fixtures = write_fixtures(tmp_path, "critic")
    reports = make_reports_dir(tmp_path, "critic")
    subject = routing.Subject(name="critic", agent="critic", variant="agent")

    with pytest.raises(routing.RollupError) as excinfo:
        routing.find_report(reports, subject, "claude-haiku-4-5", routing.fixture_set_sha(fixtures))

    assert "under evals/critic-spike/reports " in str(excinfo.value)
    assert str(tmp_path) not in str(excinfo.value)


def test_load_sweep_module_raises_when_spec_missing(monkeypatch):
    monkeypatch.setattr(routing.importlib.util, "spec_from_file_location", lambda *_a, **_k: None)
    with pytest.raises(routing.RollupError, match="cannot load"):
        routing._load_sweep_module()


def test_variant_rates_uses_aggregator_formula(tmp_path):
    runs = tmp_path / "runs.jsonl"
    records = [
        {
            "fixture_id": "f0",
            "variant": "skill",
            "run_index": 1,
            "outcome": "success",
            "assertions": [{"passed": True}, {"passed": False}],
        },
        {
            "fixture_id": "f0",
            "variant": "skill",
            "run_index": 0,
            "outcome": "error",
            "assertions": [{"passed": True}],
        },
        {
            "fixture_id": "f1",
            "variant": "skill",
            "run_index": 0,
            "outcome": "success",
            "assertions": [],
        },
        {
            "fixture_id": "f0",
            "variant": "agent",
            "run_index": 0,
            "outcome": "success",
            "assertions": [{"passed": True}],
        },
    ]
    runs.write_text("\n".join(json.dumps(r) for r in records) + "\n\n", encoding="utf-8")

    assert routing.variant_rates(runs, "skill") == {"f0": [0.0, 0.5], "f1": [0.0]}


def test_as_variant_raises_when_runs_have_no_skill_records(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    run_dir = tmp_path / "evals" / "critic-spike" / "runs" / "sweep-skill-review-m-aaaaaaaa"
    run_dir.mkdir(parents=True)
    (run_dir / "runs.jsonl").write_text("", encoding="utf-8")
    report = {
        "_path": "evals/critic-spike/reports/sweep-skill-review-m-aaaaaaaa",
        "form_factor": {"skill_recall": 0.5},
    }
    with pytest.raises(routing.RollupError, match="has no skill records"):
        routing.as_variant(report, "skill")
