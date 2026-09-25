"""Unit tests for scripts/eval/eval_model_routing.py (the per-agent rollup).

Offline: no network, no subprocess, no live eval run. Builds a synthetic
``evals/<agent>-spike/{fixtures,reports}`` tree under ``tmp_path`` and points
the module's ``REPO_ROOT`` at it, so nothing under the real ``evals/`` tree is
ever read or written. Covers ladder/skill argument parsing, the fixture-set
identity hash, the agent-vs-skill report scoping rules, the zero/ambiguous
match guards, the routing decision wiring, and the CLI's exit codes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
ROUTING_SCRIPT = EVAL_DIR / "eval_model_routing.py"

# eval_model_routing imports sibling modules via plain `from X import Y` at
# import time, and its own run() re-loads eval-model-sweep.py the same way at
# call time (see _load_sweep_module). EVAL_DIR must stay on sys.path for the
# life of this test module, not just for the initial load.
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

_spec = importlib.util.spec_from_file_location("eval_model_routing", ROUTING_SCRIPT)
assert _spec and _spec.loader
routing = importlib.util.module_from_spec(_spec)
# Register before exec: the module defines dataclasses at top level, and
# dataclass() resolves forward-referenced type hints via
# sys.modules[cls.__module__], which is None until this is set.
sys.modules["eval_model_routing"] = routing
_spec.loader.exec_module(routing)

FIXTURE_IDS = tuple(f"f{i}" for i in range(6))


# --- fixture/report builders -----------------------------------------------


def _write_fixtures(root: Path, agent: str, ids: tuple[str, ...] = FIXTURE_IDS) -> Path:
    fixtures_dir = root / "evals" / f"{agent}-spike" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    for fid in ids:
        (fixtures_dir / f"{fid}.json").write_text(
            json.dumps({"id": fid, "prompt": f"prompt for {fid}"}), encoding="utf-8"
        )
    return fixtures_dir


def _reports_dir(root: Path, agent: str) -> Path:
    reports_dir = root / "evals" / f"{agent}-spike" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def _report_dict(
    model_id: str,
    sha: str,
    rate: float,
    *,
    ids: tuple[str, ...] = FIXTURE_IDS,
    error_count: int = 0,
    skill_rate: float | None = None,
    skill_agent_rate: float | None = None,
) -> dict:
    """Synthetic report.json dict with every field parse_report requires."""
    agent_rate = rate if skill_agent_rate is None else skill_agent_rate
    per_fixture: dict[str, dict] = {}
    for fid in ids:
        per_fixture[fid] = {"agent": [agent_rate], "baseline": [0.4]}
    report: dict = {
        "fixture_set_sha": sha,
        "agent_recall": agent_rate,
        "per_fixture_pass_rates": per_fixture,
        "error_count": error_count,
        "model_id": model_id,
        "flaky_fixtures_excluded": [],
        "total_tokens_in": 1200,
        "total_tokens_out": 600,
        "cost_estimate_usd": 0.02,
        "cost_basis": "usd",
        "baseline_recall": 0.4,
    }
    if skill_rate is not None:
        report["form_factor"] = {"skill_recall": skill_rate}
        # Real reports omit per-fixture skill rates; the rollup rebuilds them
        # from runs.jsonl, so the builder hands them to _write_report there.
        report["_skill_records"] = [
            {
                "fixture_id": fid,
                "variant": "skill",
                "run_index": 0,
                "outcome": "success",
                "assertions": [{"passed": True}] * round(skill_rate * 4)
                + [{"passed": False}] * (4 - round(skill_rate * 4)),
            }
            for fid in ids
        ]
    return report


def _write_report(reports_dir: Path, run_id: str, report: dict) -> None:
    report = dict(report)
    skill_records = report.pop("_skill_records", [])
    run_dir = reports_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    runs_dir = reports_dir.parent / "runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in skill_records]
    (runs_dir / "runs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ladder(name: str, *models: str) -> routing.Ladder:
    return routing.Ladder(name=name, models=tuple(models))


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
    fixtures_dir = _write_fixtures(tmp_path, "demo")
    sha1 = routing.fixture_set_sha(fixtures_dir)
    sha2 = routing.fixture_set_sha(fixtures_dir)
    assert sha1 == sha2
    assert len(sha1) == 64


def test_fixture_set_sha_changes_when_fixture_changes(tmp_path):
    fixtures_dir = _write_fixtures(tmp_path, "demo")
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
    fixtures_dir = _write_fixtures(tmp_path, agent)
    current_sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = _reports_dir(tmp_path, agent)
    _write_report(
        reports_dir,
        "sweep-claude-haiku-4-5-old",
        _report_dict("claude-haiku-4-5", "a-stale-sha-value", 0.9),
    )
    subject = routing.Subject(name=agent, agent=agent, variant="agent")
    with pytest.raises(routing.RollupError, match="found 0"):
        routing.find_report(reports_dir, subject, "claude-haiku-4-5", current_sha)


def test_route_subject_skill_matches_only_its_own_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "analyst"
    fixtures_dir = _write_fixtures(tmp_path, agent)
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = _reports_dir(tmp_path, agent)
    ladder = _ladder("claude", "claude-haiku-4-5", "claude-sonnet-5")

    for skill in ("analyze", "review"):
        for model, rate in (("claude-haiku-4-5", 0.9), ("claude-sonnet-5", 1.0)):
            report = _report_dict(model, sha, 0.3, skill_rate=rate, skill_agent_rate=0.3)
            _write_report(reports_dir, f"sweep-skill-{skill}-{model}-r1", report)

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


# --- main(): agent subject ignores skill dirs, routes independently -----------


def test_main_routes_agent_and_skill_subjects_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    agent = "analyst"
    fixtures_dir = _write_fixtures(tmp_path, agent)
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = _reports_dir(tmp_path, agent)

    # Agent variant: haiku ties the best (opus/sonnet at 1.0) within margin.
    _write_report(
        reports_dir, "sweep-claude-haiku-4-5-a1", _report_dict("claude-haiku-4-5", sha, 0.95)
    )
    _write_report(
        reports_dir, "sweep-claude-sonnet-5-a1", _report_dict("claude-sonnet-5", sha, 1.0)
    )
    _write_report(
        reports_dir, "sweep-claude-opus-5-5-a1", _report_dict("claude-opus-5-5", sha, 1.0)
    )

    # Skill variant (analyze): haiku clearly trails. Same model ids and sha
    # as the agent rows above, so a broken skill-prefix filter would collide.
    _write_report(
        reports_dir,
        "sweep-skill-analyze-claude-haiku-4-5-s1",
        _report_dict("claude-haiku-4-5", sha, 0.3, skill_rate=0.5, skill_agent_rate=0.3),
    )
    _write_report(
        reports_dir,
        "sweep-skill-analyze-claude-sonnet-5-s1",
        _report_dict("claude-sonnet-5", sha, 0.3, skill_rate=1.0, skill_agent_rate=0.3),
    )
    _write_report(
        reports_dir,
        "sweep-skill-analyze-claude-opus-5-5-s1",
        _report_dict("claude-opus-5-5", sha, 0.3, skill_rate=1.0, skill_agent_rate=0.3),
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
    _write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = _reports_dir(tmp_path, agent)

    # haiku: exactly one match, reused by both ladders below.
    _write_report(
        reports_dir, "sweep-claude-haiku-4-5-r1", _report_dict("claude-haiku-4-5", sha, 0.9)
    )
    # sonnet: two matches (ambiguous).
    _write_report(
        reports_dir, "sweep-claude-sonnet-5-r1", _report_dict("claude-sonnet-5", sha, 1.0)
    )
    _write_report(
        reports_dir, "sweep-claude-sonnet-5-r2", _report_dict("claude-sonnet-5", sha, 0.8)
    )
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
    _write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = _reports_dir(tmp_path, agent)
    _write_report(
        reports_dir,
        "sweep-claude-haiku-4-5-r1",
        _report_dict("claude-haiku-4-5", sha, 0.9, error_count=1),
    )
    _write_report(
        reports_dir, "sweep-claude-sonnet-5-r1", _report_dict("claude-sonnet-5", sha, 1.0)
    )

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
    _write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = _reports_dir(tmp_path, agent)
    _write_report(
        reports_dir, "sweep-claude-haiku-4-5-r1", _report_dict("claude-haiku-4-5", sha, 0.95)
    )
    _write_report(
        reports_dir, "sweep-claude-sonnet-5-r1", _report_dict("claude-sonnet-5", sha, 1.0)
    )

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
    _write_fixtures(tmp_path, agent)
    fixtures_dir = tmp_path / "evals" / f"{agent}-spike" / "fixtures"
    sha = routing.fixture_set_sha(fixtures_dir)
    reports_dir = _reports_dir(tmp_path, agent)
    _write_report(
        reports_dir, "sweep-claude-haiku-4-5-r1", _report_dict("claude-haiku-4-5", sha, 0.5)
    )
    _write_report(
        reports_dir, "sweep-claude-sonnet-5-r1", _report_dict("claude-sonnet-5", sha, 1.0)
    )
    _write_report(
        reports_dir, "sweep-claude-opus-5-5-r1", _report_dict("claude-opus-5-5", sha, 1.0)
    )

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
        _ladder("claude", "claude-haiku-4-5", "claude-sonnet-5"),
        _ladder("gpt", "gpt-a", "gpt-b"),
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
                "candidates": [{"model_id": "claude-haiku-4-5", "sufficient": True}],
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


# --- flaky rescoring, relative paths, loader guard -----------------------------


def test_find_report_rescores_flaky_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "REPO_ROOT", tmp_path)
    fixtures = _write_fixtures(tmp_path, "critic")
    sha = routing.fixture_set_sha(fixtures)
    reports = _reports_dir(tmp_path, "critic")
    report = _report_dict("claude-haiku-4-5", sha, 0.5)
    report["flaky_fixtures_excluded"] = ["f0", "f1"]
    _write_report(reports, "sweep-claude-haiku-4-5-aaaaaaaa", report)
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
    fixtures = _write_fixtures(tmp_path, "critic")
    reports = _reports_dir(tmp_path, "critic")
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
