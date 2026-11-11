# taste-lint: ignore file-size, one suite owns the shared sweep fixtures for this subcommand.
"""bootstrap_sweep index: manifest schema, evidence rules, coverage, consent, batches."""

from __future__ import annotations

import json
import re
import shutil

import bootstrap_sweep
import pytest
from bootstrap_helpers import symlink_or_skip
from sweep_helpers import cov, default_coverage, dump, make_item


def planned(sweep, inventory=None, *extra):
    assert sweep.plan(inventory, *extra)[0] == 0


def violations_of(sweep, **evidence):
    planned(sweep)
    sweep.evidence(**evidence)
    code, payload = sweep.index()
    assert code == 1, payload
    return payload["violations"]


# ------------------------------------------------------------------ success and determinism


def test_index_success_writes_digest_bound_index(sweep):
    sweep.ready()

    index = json.loads(sweep.index_path.read_text())
    keys = ("schema_version", "plan_id", "items", "coverage", "metric_thresholds")
    body = {k: index[k] for k in keys}
    assert index["index_id"] == bootstrap_sweep.digest(body)
    assert index["plan_id"] == sweep.load_plan()["plan_id"]
    assert [i["id"] for i in index["items"]] == ["chat-1", "chat-2", "pr-1", "mem-1"]
    assert all(len(i["sha256"]) == 64 and i["bytes"] > 0 for i in index["items"])


def test_index_reports_examined(sweep):
    planned(sweep)
    sweep.evidence()

    code, payload = sweep.index()

    assert code == 0
    assert payload["examined"]["items"] == 4
    assert payload["examined"]["batches"] == 1
    assert payload["examined"]["coverage_rows"] == 5


def test_index_is_deterministic(sweep):
    sweep.ready()
    first = sweep.index_path.read_bytes()
    batches = sweep.batches()

    assert sweep.index()[0] == 0

    assert sweep.index_path.read_bytes() == first
    assert sweep.batches() == batches


def test_items_ordered_by_class_date_id_and_chunked(sweep):
    planned(sweep)
    items = [
        make_item("z-1", date="2026-10-01"),
        make_item("a-2", date="2026-10-05"),
        make_item("b-1", date="2026-10-01"),
        make_item("pr-1", "code_review"),
        make_item("mem-1", "memory"),
    ]
    sweep.evidence(items)

    code, payload = sweep.index("--batch-size", "2")

    assert code == 0
    index = json.loads(sweep.index_path.read_text())
    assert [i["id"] for i in index["items"]] == ["b-1", "z-1", "a-2", "pr-1", "mem-1"]
    assert [b["items"] for b in index["batches"]] == [["b-1", "z-1"], ["a-2", "pr-1"], ["mem-1"]]
    assert [b["items"] for b in payload["batches"]] == [2, 2, 1]


def test_batch_id_format_and_binding(sweep):
    sweep.ready()

    index = json.loads(sweep.index_path.read_text())
    batch = index["batches"][0]
    assert re.fullmatch(r"b001-[0-9a-f]{12}", batch["batch_id"])
    assert batch["batch_id"] == bootstrap_sweep.batch_id(index["index_id"], 1, batch["items"])


def test_batch_ids_change_when_evidence_changes(sweep):
    sweep.ready()
    first = sweep.batches()

    sweep.evidence(texts={"chat-1": "different text"})
    sweep.index()

    assert sweep.batches() != first


def test_empty_items_index_has_no_batches(sweep):
    planned(sweep)
    sweep.evidence([], default_coverage())

    code, payload = sweep.index()

    assert code == 0
    assert payload["batches"] == []


def test_batch_size_must_be_positive(sweep):
    planned(sweep)
    sweep.evidence()

    assert sweep.index("--batch-size", "0")[0] == 2


def test_violation_exit_writes_no_index(sweep):
    violations_of(sweep, items=[make_item("chat-1", date="2020-01-01")])

    assert not sweep.index_path.exists()


# ------------------------------------------------------------------ AC5 plan binding


def test_manifest_plan_id_mismatch_exits_2(sweep):
    planned(sweep)
    sweep.evidence(plan_id="0" * 64)

    code, payload = sweep.index()

    assert code == 2
    assert "plan_id" in payload["message"]


def test_tampered_plan_exits_2(sweep):
    planned(sweep)
    sweep.evidence()
    plan = sweep.load_plan()
    plan["window"]["start"] = "2000-01-01"
    dump(sweep.plan_path, plan)

    code, payload = sweep.index()

    assert code == 2
    assert "plan_id" in payload["message"]


def test_replanning_after_evidence_invalidates_manifest(sweep, skill_dir):
    planned(sweep)
    sweep.evidence()
    (skill_dir / "judges" / "extra.md").write_text("new rubric\n")
    plan = sweep.load_plan()
    plan["judges"].append({"name": "extra", "sha256": "0" * 64})
    plan["plan_id"] = bootstrap_sweep.digest({k: v for k, v in plan.items() if k != "plan_id"})
    dump(sweep.plan_path, plan)

    assert sweep.index()[0] == 2


def test_missing_evidence_json_exits_2(sweep):
    planned(sweep)

    code, _ = sweep.index()

    assert code == 2


# ------------------------------------------------------------------ malformed manifest (exit 2)


def mutate(item_key, value):
    item = make_item("chat-1")
    if value is None:
        del item[item_key]
    else:
        item[item_key] = value
    return [item]


@pytest.mark.parametrize(
    "items",
    [
        mutate("thread", None),
        mutate("visibility", None),
        mutate("visibility", "secret"),
        mutate("class", "nonsense"),
        mutate("date", "10/01/2026"),
        mutate("date", "2026-02-31"),
        mutate("id", "has space"),
        mutate("id", "x" * 65),
        mutate("path", ""),
        mutate("locator", 5),
        [make_item("dup"), make_item("dup", path="evidence/other.md")],
    ],
)
def test_malformed_item_exits_2(sweep, items):
    planned(sweep)
    sweep.evidence(items)

    code, payload = sweep.index()

    assert code == 2
    assert payload["error"] == "config"


@pytest.mark.parametrize(
    "coverage",
    [
        [{"class": "chat", "state": "read"}],
        [{"class": "chat", "state": "maybe", "items_read": 0}],
        [{"class": "chat", "state": "read", "items_read": -1}],
        [{"class": "chat", "state": "read", "items_read": True}],
        [{"class": "chat", "state": "read", "items_read": 0, "consent": "yes"}],
        [{"class": "chat", "state": "read", "items_read": 0, "extra": 1}],
        [{"class": "nonsense", "state": "read", "items_read": 0}],
    ],
)
def test_malformed_coverage_exits_2(sweep, coverage):
    planned(sweep)
    sweep.evidence(coverage=coverage)

    assert sweep.index()[0] == 2


def test_manifest_with_wrong_schema_version_exits_2(sweep):
    planned(sweep)
    sweep.evidence(schema_version=2)

    assert sweep.index()[0] == 2


# ------------------------------------------------------------------ AC6 evidence rules


def test_every_violation_is_listed_not_just_the_first(sweep):
    items = [
        make_item("chat-1", date="2020-01-01"),
        make_item("chat-2", server="Elsewhere"),
        make_item("pr-1", "code_review", locator="has space"),
        make_item("mem-1", "memory", path="evidence/missing.md"),
    ]
    planned(sweep)
    sweep.evidence(items)
    (sweep.run_dir / "evidence" / "missing.md").unlink()

    code, payload = sweep.index()

    text = "\n".join(payload["violations"])
    assert code == 1
    assert "chat-1: date is outside the plan window" in text
    assert "chat-2: server is not a server or skill under class chat" in text
    assert "pr-1: locator must be nonempty without whitespace" in text
    assert "mem-1: file missing" in text
    assert len(payload["violations"]) == 4


def test_date_window_bounds_are_inclusive(sweep):
    planned(sweep)
    sweep.evidence(
        [make_item("chat-1", date="2026-05-15"), make_item("chat-2", date="2026-11-11")],
        [cov("chat")]
        + [cov(c) for c in ("code_review", "work_tracking", "memory", "agent_sessions")],
    )

    assert sweep.index()[0] == 0


@pytest.mark.parametrize("date", ["2026-05-14", "2026-11-12"])
def test_date_outside_window_is_violation(sweep, date):
    assert "date is outside" in "\n".join(
        violations_of(sweep, items=[make_item("chat-1", date=date)])
    )


def test_class_not_connected_in_plan_is_violation(sweep):
    found = violations_of(sweep, items=[make_item("x-1", "email", server="Gmail")])

    assert any("class email is not connected" in v for v in found)


def test_item_server_may_be_a_skill_under_the_class(sweep):
    planned(sweep)
    sweep.evidence([make_item("s-1", "agent_sessions", server="skill-doctor")])

    assert sweep.index()[0] == 0


@pytest.mark.parametrize(
    "path",
    [
        "../outside.md",
        "/etc/passwd",
        "evidence/../../x.md",
        "notes/a.md",
        "evidence\\a.md",
        "C:/x.md",
    ],
)
def test_path_escapes_are_violations(sweep, path):
    found = violations_of(sweep, items=[make_item("chat-1", path=path)])

    assert any(v.startswith("chat-1: ") and "path" in v for v in found)


def test_symlink_inside_evidence_resolving_outside_is_violation(sweep, tmp_path):
    planned(sweep)
    outside = tmp_path / "secret.md"
    outside.write_text("outside content")
    evidence = sweep.run_dir / "evidence"
    evidence.mkdir()
    symlink_or_skip(evidence / "chat-1.md", outside)
    sweep.evidence([make_item("chat-1")], texts={})
    # evidence() rewrote the file through the link; restore the escape for the check
    (evidence / "chat-1.md").unlink()
    (evidence / "chat-1.md").symlink_to(outside)

    code, payload = sweep.index()

    assert code == 1
    assert any("outside the evidence directory" in v for v in payload["violations"])


def test_evidence_directory_symlinked_outside_is_violation(sweep, tmp_path):
    planned(sweep)
    real = tmp_path / "real-evidence"
    real.mkdir()
    (real / "chat-1.md").write_text("ok")
    symlink_or_skip(sweep.run_dir / "evidence", real)
    sweep.evidence([make_item("chat-1")], texts={})

    code, payload = sweep.index()

    assert code == 1
    assert any("outside the evidence directory" in v for v in payload["violations"])


def test_directory_in_place_of_file_is_missing(sweep):
    planned(sweep)
    sweep.evidence([make_item("chat-1")])
    target = sweep.run_dir / "evidence" / "chat-1.md"
    target.unlink()
    target.mkdir()

    assert any("file missing" in v for v in sweep.index()[1]["violations"])


def test_size_limit_is_64_kib(sweep):
    planned(sweep)
    sweep.evidence(
        [make_item("chat-1"), make_item("chat-2")],
        texts={"chat-1": "a" * 65536, "chat-2": "a" * 65537},
    )

    code, payload = sweep.index()

    assert code == 1
    assert [v for v in payload["violations"] if "64 KiB" in v] == ["chat-2: file is over 64 KiB"]


def test_non_utf8_is_violation(sweep):
    found = violations_of(sweep, items=[make_item("chat-1")], texts={"chat-1": b"\xff\xfe\x00bad"})

    assert "chat-1: file is not valid UTF-8" in found


# ------------------------------------------------------------------ sensitive patterns


def build(*parts):
    return "".join(parts)


SENSITIVE_SAMPLES = {
    "email": "reach me at " + build("jane.doe", "@", "example.com"),
    "github_token": build("gh", "p_", "A1" * 12),
    "github_pat": build("github", "_pat_", "11ABC"),
    "slack_token": build("xo", "xb-", "123-456"),
    "aws_key": build("AK", "IA", "ABCDEFGHIJKLMNOP"),
    "private_key": build("-----BEGIN RSA ", "PRIVATE KEY-----"),
    "api_key": build("sk", "-", "a1" * 12),
    "phone_e164": "call " + build("+", "14155550123"),
    "phone_us": "call " + build("(415)", " 555", "-0123"),
    "user_mention": build("<@", "U01ABCDEF", ">"),
}


@pytest.mark.parametrize("name", sorted(SENSITIVE_SAMPLES))
def test_sensitive_pattern_reported_by_class_never_by_match(sweep, name):
    sample = SENSITIVE_SAMPLES[name]
    found = violations_of(
        sweep, items=[make_item("chat-1")], texts={"chat-1": f"note {sample} end"}
    )

    assert f"chat-1: sensitive pattern {name}" in found
    assert not any(sample in v or sample.strip() in v for v in found)
    assert not any(sample in json.dumps(v) for v in found)


def test_clean_text_with_near_misses_passes(sweep):
    planned(sweep)
    text = "version 1.2.3, id 12345, ghp short, sk-short, user at host"
    sweep.evidence([make_item("chat-1")], texts={"chat-1": text})

    assert sweep.index()[0] == 0


def test_multiple_patterns_in_one_file_each_listed(sweep):
    text = SENSITIVE_SAMPLES["email"] + " " + SENSITIVE_SAMPLES["aws_key"]
    found = violations_of(sweep, items=[make_item("chat-1")], texts={"chat-1": text})

    assert {"chat-1: sensitive pattern email", "chat-1: sensitive pattern aws_key"} <= set(found)


# ------------------------------------------------------------------ locator and thread


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("locator", "", "nonempty"),
        ("locator", "a b", "whitespace"),
        ("locator", "x" * 501, "500"),
        ("locator", "https://user:pw@host/path", "credentials"),
        ("thread", "https://tok@host/t", "credentials"),
        ("thread", " ", "nonempty"),
    ],
)
def test_locator_and_thread_rules(sweep, field, value, needle):
    found = violations_of(sweep, items=[make_item("chat-1", **{field: value})])

    assert any(field in v and needle in v for v in found)
    assert not any("pw" in v for v in found)


def test_locator_at_500_characters_passes(sweep):
    planned(sweep)
    sweep.evidence([make_item("chat-1", locator="x" * 500)])

    assert sweep.index()[0] == 0


# ------------------------------------------------------------------ consent


def private_cov(**extra):
    return [cov("chat", **extra)] + [
        cov(c) for c in ("code_review", "work_tracking", "memory", "agent_sessions")
    ]


def test_private_item_without_consent_is_violation(sweep):
    found = violations_of(sweep, items=[make_item("chat-1", visibility="private")])

    assert "chat-1: private item needs consent granted on class chat" in found


def test_private_item_with_not_needed_consent_is_violation(sweep):
    found = violations_of(
        sweep,
        items=[make_item("chat-1", visibility="private")],
        coverage=private_cov(consent="not_needed"),
    )

    assert any("needs consent granted" in v for v in found)


def test_private_item_with_granted_consent_passes(sweep):
    planned(sweep)
    sweep.evidence([make_item("chat-1", visibility="private")], private_cov(consent="granted"))

    assert sweep.index()[0] == 0


def test_public_item_needs_no_consent(sweep):
    planned(sweep)
    sweep.evidence([make_item("chat-1")], private_cov(consent="not_needed"))

    assert sweep.index()[0] == 0


# ------------------------------------------------------------------ AC7 coverage


def test_connected_class_without_coverage_row_is_violation(sweep):
    found = violations_of(sweep, coverage=[cov("chat")])

    assert "coverage: connected class code_review has no coverage row" in found
    assert "coverage: connected class memory has no coverage row" in found


def test_unconnected_class_may_have_a_row(sweep):
    planned(sweep)
    sweep.evidence(
        coverage=default_coverage() + [cov("email", state="not_connected", reason="none")]
    )

    assert sweep.index()[0] == 0


@pytest.mark.parametrize("state", ["declined", "unavailable", "not_connected", "partial"])
def test_non_read_state_needs_reason(sweep, state):
    rows = [cov("chat", state=state, unread="rest")] + default_coverage()[1:]
    found = violations_of(sweep, coverage=rows)

    assert f"coverage: class chat state {state} needs a reason" in found


def test_partial_needs_unread(sweep):
    rows = [cov("chat", state="partial", reason="rate limit")] + default_coverage()[1:]

    assert "coverage: class chat is partial and needs unread" in violations_of(sweep, coverage=rows)


def test_partial_with_reason_and_unread_passes(sweep):
    planned(sweep)
    rows = [cov("chat", state="partial", reason="rate limit", unread="older than June")]
    sweep.evidence(coverage=rows + default_coverage()[1:])

    assert sweep.index()[0] == 0


def test_duplicate_coverage_row_is_violation(sweep):
    found = violations_of(sweep, coverage=default_coverage() + [cov("chat")])

    assert "coverage: duplicate row for class chat" in found


def test_other_class_requires_coverage_when_populated(sweep):
    inventory = {
        **__import__("sweep_helpers").INVENTORY,
        "servers": [{"name": "Twilio", "tools": ["twilio__search"]}],
    }
    planned(sweep, inventory)
    sweep.evidence([], [cov(c) for c in ("memory", "agent_sessions")])

    code, payload = sweep.index()

    assert code == 1
    assert "coverage: connected class other has no coverage row" in payload["violations"]


def test_connected_without_read_requires_unavailable(sweep):
    inventory = {
        "schema_version": 1,
        "servers": [{"name": "Slack", "tools": ["slack_send_message"]}],
        "skills": [],
    }
    planned(sweep, inventory)
    sweep.evidence([], [cov("chat")])

    code, payload = sweep.index()

    assert code == 1
    assert (
        "coverage: class chat has no read route; state must be unavailable" in payload["violations"]
    )


def test_connected_without_read_accepts_unavailable_with_reason(sweep):
    inventory = {
        "schema_version": 1,
        "servers": [{"name": "Slack", "tools": ["slack_send_message"]}],
        "skills": [],
    }
    planned(sweep, inventory)
    sweep.evidence([], [cov("chat", state="unavailable", reason="no read tools")])

    assert sweep.index()[0] == 0


# ------------------------------------------------------------------ AC4 run dir inside repo


def test_index_with_run_dir_inside_repo_exits_2_and_writes_nothing(sweep, repo):
    sweep.ready()
    moved = repo / "copied-run"
    shutil.copytree(sweep.run_dir, moved)
    (moved / "index.json").unlink()

    code, payload = sweep.cli("index", "--plan", str(moved / "plan.json"))

    assert code == 2
    assert "inside the repository" in payload["message"]
    assert not (moved / "index.json").exists()


# ------------------------------------------------------------------ metrics and thresholds


def metric_items(values, key="review_rounds", **extra):
    return [
        make_item(f"pr-{n}", "code_review", metrics={key: value, **extra})
        for n, value in enumerate(values, start=1)
    ]


def code_review_coverage():
    return [cov(c) for c in ("code_review", "work_tracking", "chat", "memory", "agent_sessions")]


def test_metrics_are_copied_into_index_items_and_batches(sweep):
    planned(sweep)
    items = metric_items([1, 2], linked_issue=True)
    sweep.evidence(items + [make_item("chat-1")], code_review_coverage())

    code, _ = sweep.index()

    index = json.loads(sweep.index_path.read_text())
    assert code == 0
    by_id = {i["id"]: i for i in index["items"]}
    assert by_id["pr-1"]["metrics"] == {"review_rounds": 1, "linked_issue": True}
    assert "metrics" not in by_id["chat-1"]
    assert index["batches"][0]["metrics"]["pr-2"] == {"review_rounds": 2, "linked_issue": True}
    assert "chat-1" not in index["batches"][0]["metrics"]


def test_batch_without_metrics_has_no_metrics_key(sweep):
    sweep.ready()

    batch = json.loads(sweep.index_path.read_text())["batches"][0]
    assert "metrics" not in batch


@pytest.mark.parametrize(
    "metrics",
    [
        {"made_up": 1},
        {"commits": "3"},
        {"commits": True},
        {"commits": -1},
        {"linked_issue": 1},
        {"stacked": "yes"},
        {"commits": None},
    ],
)
def test_bad_metrics_are_violations(sweep, metrics):
    found = violations_of(sweep, items=[make_item("chat-1", metrics=metrics)])

    assert any(v.startswith("chat-1: metrics.") for v in found)


def test_metrics_that_is_not_an_object_exits_2(sweep):
    planned(sweep)
    sweep.evidence([make_item("chat-1", metrics=[1])])

    assert sweep.index()[0] == 2


def test_allowed_metric_names_and_float_values_pass(sweep):
    planned(sweep)
    metrics = {"hours_to_first_review": 1.5, "days_open": 0, "stacked": False, "reopen_count": 2}
    sweep.evidence([make_item("chat-1", metrics=metrics)])

    assert sweep.index()[0] == 0


def test_threshold_is_nearest_rank_p90_for_keys_with_five_or_more_items(sweep):
    planned(sweep)
    sweep.evidence(metric_items(range(1, 11)), code_review_coverage())

    sweep.index()

    thresholds = json.loads(sweep.index_path.read_text())["metric_thresholds"]
    assert thresholds == {"review_rounds": {"threshold": 9, "items": 10}}


def test_threshold_rank_for_five_items_is_the_maximum(sweep):
    assert bootstrap_sweep.nearest_rank_p90([1, 2, 3, 4, 100]) == 100
    assert bootstrap_sweep.nearest_rank_p90(list(range(1, 21))) == 18


def test_keys_with_fewer_than_five_items_have_no_threshold(sweep):
    planned(sweep)
    sweep.evidence(metric_items([1, 2, 3, 4]), code_review_coverage())

    sweep.index()

    assert json.loads(sweep.index_path.read_text())["metric_thresholds"] == {}


def test_no_metrics_means_empty_thresholds(sweep):
    sweep.ready()

    assert json.loads(sweep.index_path.read_text())["metric_thresholds"] == {}
