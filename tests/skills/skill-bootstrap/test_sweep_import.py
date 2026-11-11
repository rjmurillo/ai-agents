"""bootstrap_sweep import: all-or-nothing rows, atomic accepted file, digest binding."""

from __future__ import annotations

import json
import shutil
from typing import Any

import bootstrap_sweep
import pytest
from sweep_helpers import dump, make_finding

BAD_FINDINGS: dict[str, dict[str, Any]] = {
    "evidence_outside_batch": {"evidence": ["not-in-batch"]},
    "evidence_empty": {"evidence": []},
    "evidence_duplicate": {"evidence": ["chat-1", "chat-1"]},
    "evidence_not_ids": {"evidence": [1]},
    "removed_ai_trust_type": {"type": "ai-trust", "gap": None},
    "unknown_type": {"type": "gossip"},
    "pattern_missing": {"pattern": None},
    "pattern_unknown": {"pattern": "vibes"},
    "summary_too_long": {"summary": "x" * 241},
    "summary_empty": {"summary": "  "},
    "summary_newline": {"summary": "a\nb"},
    "summary_email": {"summary": "ask jane" + "@" + "example.com"},
    "people_zero": {"people": 0},
    "people_bool": {"people": True},
    "incident_not_kebab": {"incident": "Bad Key"},
    "incident_too_long": {"incident": "a" * 81},
    "finding_id_bad": {"finding_id": "has space"},
    "repo_paths_absolute": {"repo_paths": ["/etc/hosts"]},
    "repo_paths_parent": {"repo_paths": ["a/../b"]},
    "repo_paths_windows": {"repo_paths": ["C:/x"]},
    "repo_paths_not_list": {"repo_paths": "src"},
    "action_unknown": {"suggestion": {"action": "wish", "target": "t", "rationale": "r"}},
    "target_too_long": {
        "suggestion": {"action": "write-doc", "target": "t" * 201, "rationale": "r"}
    },
    "rationale_too_long": {
        "suggestion": {"action": "write-doc", "target": "t", "rationale": "r" * 501}
    },
    "rationale_empty": {"suggestion": {"action": "write-doc", "target": "t", "rationale": ""}},
    "suggestion_extra_key": {
        "suggestion": {"action": "write-doc", "target": "t", "rationale": "r", "x": 1}
    },
    "gap_missing": {"gap": None},
    "gap_location_unknown": {
        "gap": {"question": "q", "answer_location": "pigeon", "documented": True}
    },
    "gap_documented_not_bool": {
        "gap": {"question": "q", "answer_location": "repo", "documented": "yes"}
    },
    "gap_question_too_long": {
        "gap": {"question": "q" * 301, "answer_location": "repo", "documented": True}
    },
    "gap_on_non_gap_type": {"type": "human-tool"},
    "extra_key": {"surprise": 1},
}


def finding(**overrides):
    base = make_finding()
    for key, value in overrides.items():
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value
    return base


def accepted_rows(sweep):
    return json.loads(sweep.accepted.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ AC9 success


def test_import_accepts_valid_rows_and_writes_accepted(sweep):
    sweep.ready()
    batch = sweep.batches()[0]

    code, payload = sweep.import_("friction", 1, batch, [finding()])

    accepted = accepted_rows(sweep)
    assert code == 0
    assert payload["imported"] == 1
    assert accepted["index_id"] == sweep.index_id()
    assert accepted["rows"][0]["judge"] == "friction"
    assert accepted["rows"][0]["run"] == 1
    assert accepted["rows"][0]["batch_id"] == batch
    assert accepted["imported"] == [
        {
            "judge": "friction",
            "run": 1,
            "batch_id": batch,
            "rows_sha256": bootstrap_sweep.rows_digest([finding()]),
        }
    ]
    assert payload["examined"] == {"findings": 1, "rows_total": 1, "imported_pairs": 1}


def test_identical_reimport_is_idempotent_byte_for_byte(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    sweep.import_("friction", 1, batch, [finding()])
    first = sweep.accepted.read_bytes()

    code, payload = sweep.import_("friction", 1, batch, [finding()])

    assert code == 0
    assert payload["replaced"] == 1
    assert sweep.accepted.read_bytes() == first


def test_reimport_with_different_content_replaces_that_triple_only(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    sweep.import_("friction", 1, batch, [finding()])
    sweep.import_("friction", 2, batch, [finding(finding_id="other")])

    sweep.import_("friction", 1, batch, [finding(finding_id="new", incident="other-key")])

    rows = accepted_rows(sweep)["rows"]
    assert sorted((r["run"], r["finding_id"]) for r in rows) == [(1, "new"), (2, "other")]


def test_rows_and_imported_are_sorted_deterministically(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    sweep.import_("knowledge-gap", 2, batch, [finding(finding_id="b"), finding(finding_id="a")])
    sweep.import_("friction", 1, batch, [finding()])

    accepted = accepted_rows(sweep)
    assert [(r["judge"], r["finding_id"]) for r in accepted["rows"]] == [
        ("friction", "f1"),
        ("knowledge-gap", "a"),
        ("knowledge-gap", "b"),
    ]
    assert [e["judge"] for e in accepted["imported"]] == ["friction", "knowledge-gap"]


@pytest.mark.parametrize(
    "kind",
    [
        "knowledge-gap",
        "human-agent",
        "agent-agent",
        "agent-tool",
        "agent-process",
        "human-process",
        "human-tool",
        "human-human",
    ],
)
def test_every_type_in_the_enum_is_accepted(sweep, kind):
    sweep.ready()
    row = finding(type=kind, gap=None) if kind != "knowledge-gap" else finding()

    assert sweep.import_("friction", 1, sweep.batches()[0], [row])[0] == 0


@pytest.mark.parametrize(
    "pattern",
    [
        "fragmented-context",
        "inconsistent-linking",
        "incomplete-evidence",
        "surface-switching",
        "review-gate-latency",
        "work-item-drift",
        "shadow-work",
        "lagging-indicator",
        "access-barrier",
        "oversized-change",
        "unclear-ownership",
        "missing-context",
        "unstable-checks",
        "other",
    ],
)
def test_every_pattern_in_the_enum_is_accepted(sweep, pattern):
    sweep.ready()

    assert sweep.import_("friction", 1, sweep.batches()[0], [finding(pattern=pattern)])[0] == 0


def test_pattern_enum_matches_the_spec_list():
    assert bootstrap_sweep.PATTERNS[-1] == "other"
    assert len(bootstrap_sweep.PATTERNS) == 14
    assert "ai-trust" not in bootstrap_sweep.TYPE_ORDER


def test_optional_repo_paths_accepted(sweep):
    sweep.ready()

    assert (
        sweep.import_("friction", 1, sweep.batches()[0], [finding(repo_paths=["README.md"])])[0]
        == 0
    )


def test_empty_findings_import_is_accepted_and_recorded(sweep):
    sweep.ready()
    batch = sweep.batches()[0]

    code, payload = sweep.import_("friction", 1, batch, [])

    accepted = accepted_rows(sweep)
    assert code == 0
    assert payload["imported"] == 0
    assert accepted["rows"] == []
    assert accepted["imported"][0]["batch_id"] == batch


# ------------------------------------------------------------------ rejections leave file unchanged


@pytest.mark.parametrize("name", sorted(BAD_FINDINGS))
def test_bad_finding_rejects_batch_and_leaves_accepted_byte_identical(sweep, name):
    sweep.ready()
    batch = sweep.batches()[0]
    sweep.import_("friction", 2, batch, [finding()])
    before = sweep.accepted.read_bytes()
    bad = finding(**BAD_FINDINGS[name])

    code, payload = sweep.import_("friction", 1, batch, [finding(finding_id="good"), bad])

    assert code == 1
    assert payload["errors"]
    assert all(e.startswith("findings[1]") for e in payload["errors"])
    assert sweep.accepted.read_bytes() == before


def test_rejection_with_no_prior_file_creates_nothing(sweep):
    sweep.ready()

    code, _ = sweep.import_("friction", 1, sweep.batches()[0], [finding(pattern="vibes")])

    assert code == 1
    assert not sweep.accepted.exists()


def test_all_errors_are_listed(sweep):
    sweep.ready()
    rows = [finding(pattern="vibes"), finding(finding_id="f2", people=0, summary="")]

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], rows)

    text = "\n".join(payload["errors"])
    assert code == 1
    assert "findings[0]: pattern must be one of" in text
    assert "findings[1]: people must be an integer >= 1" in text
    assert "findings[1]: summary must be nonempty text" in text


def test_duplicate_finding_ids_reject_the_batch(sweep):
    sweep.ready()

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], [finding(), finding()])

    assert code == 1
    assert "findings[1]: duplicate finding_id" in payload["errors"]


def test_same_finding_id_in_different_batches_is_allowed(sweep):
    sweep.ready("--batch-size", "2")
    first, second = sweep.batches()[:2]

    assert sweep.import_("friction", 1, first, [finding()])[0] == 0
    assert sweep.import_("friction", 1, second, [finding(evidence=["pr-1"])])[0] == 0


def test_non_object_finding_is_rejected(sweep):
    sweep.ready()

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], ["text"])

    assert code == 1
    assert payload["errors"] == ["findings[0]: finding must be an object"]


def test_evidence_from_another_batch_is_rejected(sweep):
    sweep.ready("--batch-size", "2")
    first = sweep.batches()[0]

    code, payload = sweep.import_("friction", 1, first, [finding(evidence=["mem-1"])])

    assert code == 1
    assert any("outside the batch" in e for e in payload["errors"])


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"judge": "unlisted"}, "unknown judge"),
        ({"run": 0}, "run must be between 1 and 2"),
        ({"run": 3}, "run must be between 1 and 2"),
        ({"batch_id": "b999-nope"}, "unknown batch_id"),
    ],
)
def test_unknown_judge_run_or_batch_is_rejected(sweep, overrides, needle):
    sweep.ready()
    batch = sweep.batches()[0]
    args = {"judge": "friction", "run": 1, "batch_id": batch, **overrides}

    code, payload = sweep.import_(args["judge"], args["run"], args["batch_id"], [finding()])

    assert code == 1
    assert needle in payload["errors"]
    assert not sweep.accepted.exists()


# ------------------------------------------------------------------ exit 2 cases


def test_rows_index_id_mismatch_exits_2(sweep):
    sweep.ready()

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], [finding()], index_id="0" * 64)

    assert code == 2
    assert "index_id" in payload["message"]


@pytest.mark.parametrize(
    "overrides",
    [{"schema_version": 2}, {"findings": "x"}, {"judge": 5}, {"run": "1"}, {"extra": 1}],
)
def test_malformed_rows_document_exits_2(sweep, overrides):
    sweep.ready()

    code, _ = sweep.import_("friction", 1, sweep.batches()[0], [finding()], **overrides)

    assert code == 2


def test_accepted_path_outside_run_dir_exits_2(sweep, tmp_path):
    sweep.ready()
    rows = sweep.rows_file("friction", 1, sweep.batches()[0], [finding()])
    elsewhere = tmp_path / "elsewhere.json"

    code, payload = sweep.cli(
        "import",
        "--index",
        str(sweep.index_path),
        "--repo",
        str(sweep.repo),
        "--rows",
        str(rows),
        "--accepted",
        str(elsewhere),
    )

    assert code == 2
    assert "inside the run directory" in payload["message"]
    assert not elsewhere.exists()


def test_import_with_run_dir_inside_repo_exits_2_and_writes_nothing(sweep, repo):
    sweep.ready()
    moved = repo / "copied-run"
    shutil.copytree(sweep.run_dir, moved)
    rows = sweep.rows_file("friction", 1, sweep.batches()[0], [finding()])

    code, payload = sweep.cli(
        "import",
        "--index",
        str(moved / "index.json"),
        "--repo",
        str(repo),
        "--rows",
        str(rows),
        "--accepted",
        str(moved / "accepted.json"),
    )

    assert code == 2
    assert "inside the repository" in payload["message"]
    assert not (moved / "accepted.json").exists()


def test_tampered_index_exits_2(sweep):
    sweep.ready()
    index = json.loads(sweep.index_path.read_text(encoding="utf-8"))
    index["items"][0]["bytes"] += 1
    dump(sweep.index_path, index)

    code, payload = sweep.cli(
        "import",
        "--index",
        str(sweep.index_path),
        "--repo",
        str(sweep.repo),
        "--rows",
        "x.json",
        "--accepted",
        str(sweep.accepted),
    )

    assert code == 2
    assert "index_id" in payload["message"]


def test_existing_accepted_for_another_index_exits_2(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    sweep.import_("friction", 1, batch, [finding()])
    accepted = accepted_rows(sweep)
    accepted["index_id"] = "f" * 64
    dump(sweep.accepted, accepted)
    before = sweep.accepted.read_bytes()

    code, _ = sweep.import_("friction", 2, batch, [finding()])

    assert code == 2
    assert sweep.accepted.read_bytes() == before


def test_existing_accepted_with_edited_rows_exits_2(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    sweep.import_("friction", 1, batch, [finding()])
    accepted = accepted_rows(sweep)
    accepted["rows"][0]["people"] = 99
    dump(sweep.accepted, accepted)

    code, payload = sweep.import_("friction", 2, batch, [finding()])

    assert code == 2
    assert "rows_sha256" in payload["message"]


# ------------------------------------------------------------------ rubric drift (F)


def test_judge_rubric_changed_since_plan_exits_2(sweep, skill_dir):
    sweep.ready()
    (skill_dir / "judges" / "friction.md").write_text("edited rubric\n", encoding="utf-8")

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], [finding()])

    assert code == 2
    assert "changed since plan" in payload["message"]
    assert not sweep.accepted.exists()


def test_judge_rubric_missing_exits_2(sweep, skill_dir):
    sweep.ready()
    (skill_dir / "judges" / "knowledge-gap.md").unlink()

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], [finding()])

    assert code == 2
    assert "missing" in payload["message"]


def test_new_judge_file_after_plan_does_not_break_import(sweep, skill_dir):
    sweep.ready()
    (skill_dir / "judges" / "late.md").write_text("late\n", encoding="utf-8")

    assert sweep.import_("friction", 1, sweep.batches()[0], [finding()])[0] == 0
