"""tally subcommand: label validation, quote checks, weighted estimates. Synthetic data only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from replies_helpers import (
    CONTROL_TOKEN,
    evidence_rows,
    plant_control,
    prepare_ok,
    replies_sample,
    replies_tally,
    run_cli,
    simple_session,
    write_session,
)

SCHEMA = "reply-friction/labels/v1"
OFFER = "Want me to"


def make_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """A run with a planted offer-tail control, one clean reply, and a typed follow-up."""
    store = tmp_path / "projects" / "proj-a"
    plant_control(store)
    recs = simple_session(
        "synthetic prompt wording rho for tally", ["Plain finished statement.", "Second one."], 10
    )
    write_session(store, "main-a", recs)
    run_dir = tmp_path / "run"
    prepare_ok(capsys, store, run_dir)
    return run_dir


def good_labels(run_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in evidence_rows(run_dir):
        if OFFER in row["reply"]:
            out.append(
                {
                    "id": row["id"],
                    "label": "friction",
                    "category": "offer_tail",
                    "quote_source": "reply",
                    "quote": OFFER,
                }
            )
        else:
            out.append({"id": row["id"], "label": "none"})
    return out


def write_labels(path: Path, labels: list[Any], schema: str = SCHEMA) -> Path:
    path.write_text(json.dumps({"schema": schema, "labels": labels}), encoding="utf-8")
    return path


def tally(
    capsys: pytest.CaptureFixture[str], run_dir: Path, labels: Path
) -> tuple[int, dict[str, Any], str]:
    return run_cli(capsys, ["tally", "--run-dir", str(run_dir), "--labels", str(labels)])


def problem_codes(payload: dict[str, Any]) -> set[str]:
    return {p["code"] for p in payload["problems"]}


def test_valid_labels_tally_and_control_counts_as_friction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, capsys)
    code, payload, out = tally(
        capsys, run_dir, write_labels(tmp_path / "l.json", good_labels(run_dir))
    )
    assert code == 0
    assert payload["labeled"] == 3
    assert payload["label_counts"] == {"friction": 1, "none": 2}
    assert payload["overall"]["estimated_friction"] == 0.0
    assert payload["overall"]["estimated_by_category"] == {}
    assert payload["control"] == {"rows": 1, "friction": 1}
    assert payload["followed_by_typed_turn"]["rate"] == 0.0
    assert CONTROL_TOKEN not in out and OFFER not in out


def test_weighted_estimate_matches_hand_computation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def rec(key: str, flags: list[str]) -> Any:
        return replies_sample.ReplyRec(key, "final_reply", flags, f"reply {key}", "none")

    flagged = [rec(f"f{i}", ["offer_tail"]) for i in range(10)]
    clean = [rec(f"c{i}", []) for i in range(90)]
    groups = replies_sample.strata_of(flagged + clean)
    picked = flagged[:2] + clean[:3]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    replies_sample.write_run(run_dir, picked, groups, seed=1, per_kind=5)
    rows = evidence_rows(run_dir)
    labels = [
        {
            "id": r["id"],
            "label": "friction",
            "category": "other",
            "quote_source": "reply",
            "quote": "reply",
        }
        if r["flagged"]
        else {"id": r["id"], "label": "none"}
        for r in rows
    ]
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "l.json", labels))
    assert code == 0
    assert payload["overall"]["rate"] == 0.1
    assert payload["overall"]["estimated_friction"] == 10.0
    assert payload["overall"]["coverage"] == 1.0
    # Hand computation. Flagged stratum: N=10, m=2, x=2 (all friction), so the variance
    # term uses p=(2+0.5)/(2+1)=0.833333. Term = 10^2 * (1-2/10) * 0.833333*0.166667 / 1
    # = 11.1111. Clean stratum: N=90, m=3, x=0, p=(0+0.5)/(3+1)=0.125. Term = 90^2 *
    # (1-3/90) * 0.125*0.875 / 2 = 428.2031. var = 439.3142, sd = 20.9598.
    # half = 1.96 * 20.9598 / 100 = 0.4108. Interval = [max(0, 0.1-0.4108), 0.1+0.4108].
    low, high = payload["overall"]["ci95"]
    assert [low, high] == [0.0, 0.5108]
    assert high - low > 0
    labels[-1] = {"id": rows[-1]["id"], "label": "unclear"}
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "l2.json", labels))
    assert code == 0 and payload["overall"]["rate"] == 0.1


def test_unresolved_stratum_lowers_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, capsys)
    rows = evidence_rows(run_dir)
    labels = [
        e if e["label"] == "friction" else {"id": e["id"], "label": "unclear"}
        for e in good_labels(run_dir)
    ]
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "l.json", labels))
    assert code == 0
    assert payload["overall"]["rate"] is None and payload["overall"]["coverage"] == 0.0
    control = next(r for r in rows if CONTROL_TOKEN in r["reply"])
    labels = good_labels(run_dir)
    labels = [
        e if e["id"] != control["id"] else {"id": e["id"], "label": "unclear"} for e in labels
    ]
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "l2.json", labels))
    assert code == 1 and problem_codes(payload) == {"control_not_flagged"}


def mutate(labels: list[dict[str, Any]], index: int, **change: Any) -> list[dict[str, Any]]:
    edited = [dict(e) for e in labels]
    edited[index].update(change)
    return edited


def control_index(run_dir: Path) -> int:
    return next(i for i, r in enumerate(evidence_rows(run_dir)) if CONTROL_TOKEN in r["reply"])


@pytest.mark.parametrize(
    ("change", "code_name"),
    [
        ({"label": "maybe"}, "bad_label"),
        ({"category": "invented"}, "bad_category"),
        ({"quote_source": "elsewhere"}, "bad_quote_source"),
        ({"quote": "ab"}, "bad_quote"),
        ({"quote": "x" * 401}, "quote_too_long"),
        ({"quote": "text that was never written"}, "quote_not_in_source"),
        ({"quote_source": "next_human"}, "quote_source_empty"),
        ({"extra": 1}, "unknown_field"),
    ],
)
def test_invalid_friction_entries_are_rejected_by_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: dict[str, Any], code_name: str
) -> None:
    run_dir = make_run(tmp_path, capsys)
    labels = good_labels(run_dir)
    ok_code, _, _ = tally(capsys, run_dir, write_labels(tmp_path / "ok.json", labels))
    assert ok_code == 0
    bad = mutate(labels, control_index(run_dir), **change)
    code, payload, out = tally(capsys, run_dir, write_labels(tmp_path / "bad.json", bad))
    assert code == 1
    assert problem_codes(payload) == {code_name}
    assert CONTROL_TOKEN not in out


def test_quote_must_come_from_the_named_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "projects" / "proj-a"
    plant_control(store)
    recs = simple_session(
        "synthetic prompt wording sigma for source test", ["Plain first.", "Plain second."], 10
    )
    write_session(store, "main-a", recs)
    run_dir = tmp_path / "run"
    prepare_ok(capsys, store, run_dir)
    rows = evidence_rows(run_dir)
    answered = next(r for r in rows if r["next_human"])
    labels = good_labels(run_dir)
    index = next(i for i, r in enumerate(rows) if r["id"] == answered["id"])
    follow = "synthetic follow-up number 0"
    good = mutate(
        labels, index, label="friction", category="other", quote_source="next_human", quote=follow
    )
    assert tally(capsys, run_dir, write_labels(tmp_path / "a.json", good))[0] == 0
    wrong = mutate(good, index, quote_source="reply")
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "b.json", wrong))
    assert code == 1 and problem_codes(payload) == {"quote_not_in_source"}


def test_none_and_unclear_entries_must_not_carry_quotes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, capsys)
    labels = good_labels(run_dir)
    assert tally(capsys, run_dir, write_labels(tmp_path / "ok.json", labels))[0] == 0
    other = next(i for i, e in enumerate(labels) if e["label"] == "none")
    bad = mutate(labels, other, quote="Plain")
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "bad.json", bad))
    assert code == 1 and problem_codes(payload) == {"unexpected_field_for_label"}


def test_coverage_must_be_complete_and_exact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, capsys)
    labels = good_labels(run_dir)
    assert tally(capsys, run_dir, write_labels(tmp_path / "ok.json", labels))[0] == 0
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "m.json", labels[:-1]))
    assert code == 1 and problem_codes(payload) == {"missing_label"}
    dup = labels + [dict(labels[0])]
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "d.json", dup))
    assert code == 1 and problem_codes(payload) == {"duplicate_id"}
    extra = labels + [{"id": "e9999", "label": "none"}]
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "x.json", extra))
    assert code == 1 and problem_codes(payload) == {"unknown_id"}
    code, payload, _ = tally(capsys, run_dir, write_labels(tmp_path / "n.json", labels + ["junk"]))
    assert code == 1 and problem_codes(payload) == {"bad_entry"}


def test_modified_evidence_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = make_run(tmp_path, capsys)
    labels = write_labels(tmp_path / "l.json", good_labels(run_dir))
    assert tally(capsys, run_dir, labels)[0] == 0
    evidence = run_dir / replies_sample.EVIDENCE_NAME
    evidence.write_text(
        evidence.read_text(encoding="utf-8").replace(OFFER, "Shall we"), encoding="utf-8"
    )
    code, payload, _ = tally(capsys, run_dir, labels)
    assert (code, payload["message"]) == (2, "evidence_modified")


def test_unusable_inputs_are_config_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, capsys)
    good = write_labels(tmp_path / "ok.json", good_labels(run_dir))
    assert tally(capsys, run_dir, good)[0] == 0
    cases = [
        (run_dir, tmp_path / "missing.json", "labels_unreadable"),
        (run_dir, write_labels(tmp_path / "s.json", [], schema="other"), "labels_schema"),
        (tmp_path / "no-run", good, "run_dir_unreadable"),
    ]
    garbage = tmp_path / "g.json"
    garbage.write_text("{not json", encoding="utf-8")
    cases.append((run_dir, garbage, "labels_not_json"))
    for target, labels, message in cases:
        code, payload, _ = tally(capsys, target, labels)
        assert (code, payload["message"]) == (2, message)


def stratum(population: int, sampled: int, friction: int) -> dict[str, Any]:
    cell = {"n": sampled, "unclear": 0, "friction": friction}
    return {"population": population, "cell": cell}


def test_interval_adjusts_only_all_none_and_all_friction_strata() -> None:
    # All none: p=(0+0.5)/(4+1)=0.1, var = 100^2 * (1-4/100) * 0.09 / 3 = 288.
    # half = 1.96 * sqrt(288) / 100 = 0.3326.
    assert replies_tally._interval([stratum(100, 4, 0)], 0.0, 100) == [0.0, 0.3326]
    # All friction mirrors it around 1.
    assert replies_tally._interval([stratum(100, 4, 4)], 1.0, 100) == [0.6674, 1.0]
    # Mixed (x=1, m=4): unadjusted p=0.25, var = 100^2 * 0.96 * 0.1875 / 3 = 600.
    # half = 1.96 * sqrt(600) / 100 = 0.4801, so the interval is [0, 0.7301].
    assert replies_tally._interval([stratum(100, 4, 1)], 0.25, 100) == [0.0, 0.7301]
    # A stratum of one resolved label gives no interval.
    assert replies_tally._interval([stratum(100, 1, 0)], 0.0, 100) is None


def test_malformed_evidence_row_with_a_rewritten_hash_is_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(tmp_path, capsys)
    labels = write_labels(tmp_path / "l.json", good_labels(run_dir))
    evidence = run_dir / replies_sample.EVIDENCE_NAME
    blob = evidence.read_bytes() + b"{not json\n"
    evidence.write_bytes(blob)
    manifest_path = run_dir / replies_sample.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence_sha256"] = hashlib.sha256(blob).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    code, payload, _ = tally(capsys, run_dir, labels)
    assert code == 2
    assert payload == {"error": "config", "message": "run_dir_unreadable"}
