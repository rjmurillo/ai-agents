"""bootstrap_mine candidates --sweep-json: cross_source_incident seeds from a tally."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import bootstrap_friction
import bootstrap_sweep
import pytest
from sweep_helpers import dump, make_finding

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "skill-bootstrap"
    / "scripts"
    / "bootstrap_mine.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("bootstrap_mine_sweep_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    scripts = str(SCRIPT.resolve().parent)
    sys.path.insert(0, scripts)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)
    return module


mine = _load()


def candidates(capsys, repo: Path, *extra: str) -> tuple[int, dict[str, Any]]:
    code = mine.main(["candidates", "--repo", str(repo), *extra])
    return code, json.loads(capsys.readouterr().out)


def finding(**overrides):
    row = make_finding(**overrides)
    if row.get("gap") is None:
        row.pop("gap", None)
    return row


@pytest.fixture
def sweep_json(sweep) -> Path:
    sweep.ready()
    rows = [
        finding(
            finding_id="1",
            incident="slow-onboarding",
            evidence=["chat-1", "pr-1"],
            pattern="shadow-work",
            summary="SUMMARY-TEXT-MARKER one",
            suggestion={
                "action": "write-doc",
                "target": "TARGET-TEXT-MARKER",
                "rationale": "RATIONALE-TEXT-MARKER",
            },
        ),
        finding(
            finding_id="2",
            incident="hidden-owner",
            evidence=["chat-2"],
            type="human-process",
            gap=None,
        ),
    ]
    sweep.sweep(rows)
    return sweep.run_dir / "sweep.json"


def seeds_of(payload):
    return {s["identity"][2]: s for s in payload["candidate_seeds"]}


# ------------------------------------------------------------------ AC13


def test_one_seed_per_incident_with_unverified_disposition(sweep, sweep_json, repo, capsys):
    code, payload = candidates(capsys, repo, "--sweep-json", str(sweep_json))

    seeds = seeds_of(payload)
    assert code == 0
    assert sorted(seeds) == ["hidden-owner", "slow-onboarding"]
    seed = seeds["slow-onboarding"]
    assert seed["kind"] == "cross_source_incident"
    assert seed["identity"] == ["cross_source_incident", sweep.index_id(), "slow-onboarding"]
    assert seed["signal"] == "evidence_items"
    assert seed["count"] == 2
    assert seed["disposition"] == "candidate_unverified"
    assert seed["corroborated"] is True
    assert seed["corroboration"] == ["classes", "threads"]
    assert seed["primary_type"] == "knowledge-gap"
    assert seed["patterns"] == {"shadow-work": 4}
    assert seed["classes"] == ["chat", "code_review"]
    assert seed["suggestion_actions"] == ["write-doc"]
    assert seeds["hidden-owner"]["corroborated"] is False


def test_seed_sources_carry_input_digest_and_locator(sweep, sweep_json, repo, capsys):
    _, payload = candidates(capsys, repo, "--sweep-json", str(sweep_json))

    sources = sorted(s["sources"][0]["locator"] for s in payload["candidate_seeds"])
    assert sources == ["/incidents/0", "/incidents/1"]
    source = payload["candidate_seeds"][0]["sources"][0]
    assert source["input"] == str(sweep_json)
    assert source["sha256"] == hashlib.sha256(sweep_json.read_bytes()).hexdigest()
    [meta] = payload["seed_inputs"]
    assert len(meta["metadata"]["index_id"]) == 64
    assert meta["metadata"]["incomplete"] == 0
    assert meta["metadata"]["schema_version"] == 1


def test_examined_counts_incidents(sweep, sweep_json, repo, capsys):
    _, payload = candidates(capsys, repo, "--sweep-json", str(sweep_json))

    assert payload["examined"]["seed_sweep_incidents"] == 2
    assert payload["examined"]["seed_candidates"] == 2


def test_no_text_from_summaries_targets_or_rationale_reaches_output(
    sweep, sweep_json, repo, capsys
):
    code = mine.main(["candidates", "--repo", str(repo), "--sweep-json", str(sweep_json)])
    text = capsys.readouterr().out

    assert code == 0
    for marker in ("SUMMARY-TEXT-MARKER", "TARGET-TEXT-MARKER", "RATIONALE-TEXT-MARKER"):
        assert marker not in text
    assert "SUMMARY-TEXT-MARKER" in sweep_json.read_text()


def test_seed_keys_are_only_the_allowed_set(sweep, sweep_json, repo, capsys):
    _, payload = candidates(capsys, repo, "--sweep-json", str(sweep_json))

    assert sorted(payload["candidate_seeds"][0]) == [
        "classes",
        "corroborated",
        "corroboration",
        "count",
        "disposition",
        "identity",
        "kind",
        "patterns",
        "primary_type",
        "signal",
        "sources",
        "suggestion_actions",
    ]


def test_seeds_are_ranked_by_count_then_identity(sweep, sweep_json, repo, capsys):
    _, payload = candidates(capsys, repo, "--sweep-json", str(sweep_json))

    assert [s["identity"][2] for s in payload["candidate_seeds"]] == [
        "slow-onboarding",
        "hidden-owner",
    ]


def test_without_flag_output_is_unchanged(sweep, sweep_json, repo, capsys):
    _, plain = candidates(capsys, repo)
    _, with_flag = candidates(capsys, repo, "--sweep-json", str(sweep_json))

    assert "candidate_seeds" not in plain
    assert "seed_inputs" not in plain
    assert "seed_sweep_incidents" not in plain["examined"]
    for key, value in plain.items():
        if key != "examined":
            assert with_flag[key] == value


def test_sweep_with_incomplete_pairs_still_imports_and_reports_count(sweep, repo, capsys):
    sweep.ready()
    sweep.import_("friction", 1, sweep.batches()[0], [finding()])
    assert sweep.tally()[0] == 1

    code, payload = candidates(capsys, repo, "--sweep-json", str(sweep.run_dir / "sweep.json"))

    assert code == 0
    assert payload["seed_inputs"][0]["metadata"]["incomplete"] == 3
    assert payload["candidate_seeds"] == []


def test_sweep_json_records_one_seed_input(sweep, sweep_json, repo, capsys):
    code, payload = candidates(capsys, repo, "--sweep-json", str(sweep_json))

    assert code == 0
    assert len(payload["seed_inputs"]) == 1


# ------------------------------------------------------------------ malformed input


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def edit(sweep_json: Path, tmp_path: Path, mutate) -> Path:
    data = load(sweep_json)
    mutate(data)
    return dump(tmp_path / "edited.json", data)


MUTATIONS = {
    "schema_version": lambda d: d.update(schema_version=2),
    "missing_index_id": lambda d: d.pop("index_id"),
    "incidents_not_list": lambda d: d.update(incidents={}),
    "extra_incident_key": lambda d: d["incidents"][0].update(surprise=1),
    "removed_type": lambda d: d["incidents"][0].update(primary_type="ai-trust"),
    "type_not_in_types": lambda d: d["incidents"][0].update(primary_type="agent-tool"),
    "corroborated_mismatch": lambda d: d["incidents"][0].update(corroborated=False),
    "bad_corroboration_reason": lambda d: d["incidents"][0].update(corroboration=["vibes"]),
    "unknown_action": lambda d: d["incidents"][0]["suggestions"][0].update(action="wish"),
    "unknown_pattern": lambda d: d["incidents"][0].update(patterns={"vibes": 1}),
    "zero_pattern_count": lambda d: d["incidents"][0].update(patterns={"other": 0}),
    "unknown_class": lambda d: d["incidents"][0].update(classes=["mars"]),
    "empty_evidence": lambda d: d["incidents"][0].update(evidence=[]),
    "duplicate_evidence": lambda d: d["incidents"][0].update(evidence=["a", "a"]),
    "duplicate_incident": lambda d: d["incidents"].append(dict(d["incidents"][0])),
    "coverage_missing": lambda d: d.pop("coverage"),
    "incomplete_not_list": lambda d: d.update(incomplete=1),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_invalid_sweep_exits_2_and_adds_no_seeds(sweep, sweep_json, repo, capsys, tmp_path, name):
    bad = edit(sweep_json, tmp_path, MUTATIONS[name])

    code, payload = candidates(capsys, repo, "--sweep-json", str(bad))

    assert code == 2
    assert payload["error"] == "config"
    assert "invalid friction input" in payload["message"]
    assert "candidate_seeds" not in payload


def test_duplicate_json_keys_exit_2(sweep_json, repo, capsys, tmp_path):
    bad = tmp_path / "dup.json"
    bad.write_text('{"schema_version": 1, "schema_version": 1}')

    assert candidates(capsys, repo, "--sweep-json", str(bad))[0] == 2


def test_missing_sweep_file_exits_2(repo, capsys, tmp_path):
    assert candidates(capsys, repo, "--sweep-json", str(tmp_path / "none.json"))[0] == 2


def test_non_json_number_exits_2(repo, capsys, tmp_path):
    bad = tmp_path / "nan.json"
    bad.write_text('{"schema_version": NaN}')

    assert candidates(capsys, repo, "--sweep-json", str(bad))[0] == 2


# ------------------------------------------------------------------ conformance


def test_friction_enums_mirror_bootstrap_sweep():
    assert set(bootstrap_friction.SWEEP_TYPES) == set(bootstrap_sweep.TYPE_ORDER)
    assert bootstrap_friction.SWEEP_PATTERNS == bootstrap_sweep.PATTERNS
    assert bootstrap_friction.SWEEP_CLASSES == bootstrap_sweep.CLASSES
    assert bootstrap_friction.SWEEP_ACTIONS == bootstrap_sweep.ACTIONS


def test_incident_key_set_mirrors_what_tally_emits(sweep, sweep_json):
    incident = load(sweep_json)["incidents"][0]

    assert set(incident) == bootstrap_friction.SWEEP_INCIDENT_KEYS
