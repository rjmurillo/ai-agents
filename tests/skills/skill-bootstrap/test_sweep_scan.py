"""bootstrap_sweep round 3: verb classification, prose-safe scanning, caps, --out, typed loads."""

from __future__ import annotations

import json
import os
import re
import time

import bootstrap_sweep
import pytest
from sweep_helpers import (
    SENSITIVE_SAMPLES,
    build,
    dump,
    make_finding,
    make_item,
)


def access(name: str, server: str = "") -> str:
    tool = {"name": name, "description": "", "access": None}
    verdict: str = bootstrap_sweep.tool_access(tool, server)[0]
    return verdict


# ------------------------------------------------------------------ classification


def test_noun_verbs_are_write_verbs_and_the_docstring_is_true():
    assert bootstrap_sweep.NOUN_VERBS <= bootstrap_sweep.WRITE_VERBS


@pytest.mark.parametrize(
    "verb",
    [
        *("untrash", "restore", "modify", "mute", "unmute", "unlock", "unassign"),
        *("dispatch", "queue", "start", "enqueue", "rename", "move"),
    ],
)
def test_added_write_verbs_exclude_the_tool(verb):
    assert access(f"{verb}_thing") == "write"
    assert access(f"get_and_{verb}") == "write"


@pytest.mark.parametrize(
    "name",
    [
        "comment_on_issue",
        "review_pull_request",
        "issue_create",
        "commit_files",
        "start_export",
        "queue_download",
        "get_and_dispatch",
        "read_and_comment",
        "fetch_then_review",
        "list_and_issue",
        "get_and_commit",
        "read_and_reply",
        "search_and_replace",
    ],
)
def test_mixed_and_leading_noun_verb_names_fail_closed(name):
    assert access(name) == "write"


@pytest.mark.parametrize(
    "name",
    [
        "issue_read",
        "pull_request_read",
        "get_label",
        "search_public_and_private",
        "recall",
        "get_pull_request",
        "list_pull_requests",
        "search_pull_requests",
        "get_workflow_run",
        "get_review_comments",
        "list_commits",
        "get_commit",
        "list_issue_types",
    ],
)
def test_reads_stay_reads(name):
    assert access(name) == "read"


def test_a_server_prefix_never_hides_a_verb():
    assert access("push_files", "github-push") == "write"
    assert access("search_docs", "search") == "read"
    assert access("slack_read_channel", "Slack") == "read"
    assert access("github_push_files", "github") == "write"


# ------------------------------------------------------------------ scanning


FALSE_POSITIVES = [
    "password: must rotate every 90 days",
    "Reset password: see runbook",
    "the password policy is documented",
    "https://wiki.example/viewspace.action?key=ENG",
    "OAuth docs: append ?code=abc to the redirect",
    "build number 2026.111.1234",
    "ticket 12345 678 9012 was reopened",
    "token budget and key results",
    "password: rotatedweekly via vault",
]


@pytest.mark.parametrize("text", FALSE_POSITIVES)
def test_prose_and_identifiers_are_not_flagged(text):
    assert bootstrap_sweep.sensitive_hits(text) == []


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("password: hunter22", "password_assignment"),
        ("pwd=Sup3rS3cret!\nnext", "password_assignment"),
        ('password = "hunter22"', "password_assignment"),
        ("https://x.example/p?access_token=abcdefgh12", "url_secret_param"),
        ("https://x.example/p?sig=abcdefgh12&x=1", "url_secret_param"),
        ("https://x.example/p?key=" + "A" * 20, "url_secret_param"),
        ("https://x.example/p?code=" + "B" * 24, "url_secret_param"),
        ("call 415-555-0123 now", "phone_us"),
        ("call (415) 555-0123 now", "phone_us"),
        ("call 123 456 7890 now", "phone_us"),
        ("call +14155550123", "phone_e164"),
        ("call +1415555012", "phone_e164"),
        ("x" + build("sk_", "test_", "a1" * 10), "stripe_key"),
        (build("rk_", "live_", "a1" * 10), "stripe_key"),
        (build("sk_", "live_", "a1" * 10), "stripe_key"),
    ],
)
def test_true_positives_are_still_caught(text, name):
    assert name in [hit[0] for hit in bootstrap_sweep.sensitive_hits(text)]


@pytest.mark.parametrize("text", ["call +141555501", "call ++14155550123", "pin +1234567890123456"])
def test_e164_needs_10_to_15_digits_and_a_clean_boundary(text):
    assert "phone_e164" not in [hit[0] for hit in bootstrap_sweep.sensitive_hits(text)]


def test_phone_choice_is_documented_by_tests_a_longer_digit_run_is_not_a_phone():
    assert bootstrap_sweep.sensitive_hits("12345 678 9012") == []
    assert bootstrap_sweep.sensitive_hits("1234-567-8901") == []
    assert [h[0] for h in bootstrap_sweep.sensitive_hits("tel 234 567 8901")] == ["phone_us"]


def test_hits_report_class_and_offset_never_the_match():
    token = SENSITIVE_SAMPLES["github_token"]

    hits = bootstrap_sweep.sensitive_hits("abc " + token)

    assert hits == [("github_token", 4)]
    assert token not in repr(hits)


def test_scan_is_cut_to_the_documented_cap():
    text = "x" * 10 + SENSITIVE_SAMPLES["github_token"]

    assert bootstrap_sweep.sensitive_hits(text, limit=10) == []
    assert bootstrap_sweep.sensitive_hits(text, limit=1000) != []


def test_pathological_input_scans_in_bounded_time():
    nasty = "eyJ" + "a" * 200000 + " Bearer " + "b" * 200000 + " password:" + " " * 100000
    started = time.perf_counter()

    bootstrap_sweep.sensitive_hits(nasty, limit=1000)
    bootstrap_sweep.sensitive_hits(nasty[:70000])

    assert time.perf_counter() - started < 5


def test_every_sensitive_pattern_quantifier_is_bounded():
    for name, pattern in bootstrap_sweep.SENSITIVE.items():
        bare = re.sub(r"\\.", "", pattern.pattern)
        bare = re.sub(r"\[[^\]]*\]", "", bare)
        assert "+" not in bare, name
        assert "*" not in bare, name
        assert ",}" not in bare, name


# ------------------------------------------------------------------ fields


def planned(sweep):
    assert sweep.plan()[0] == 0


def test_message_id_thread_may_hold_an_at_sign(sweep):
    planned(sweep)
    sweep.evidence([make_item("chat-1", thread="<CAF3x9ab@mail.example.com>")])

    assert sweep.index()[0] == 0


@pytest.mark.parametrize("value", ["jane.doe" + "@example.com", "<a@b.c> extra", "x<a@b.c>"])
def test_other_threads_with_email_shapes_are_flagged(sweep, value):
    planned(sweep)
    sweep.evidence([make_item("chat-1", thread=value.replace(" ", "-"))])

    code, payload = sweep.index()

    assert code == 1
    assert any(
        v.startswith("chat-1: thread holds sensitive pattern email at offset")
        for v in payload["violations"]
    )


def test_message_id_shape_is_not_allowed_in_the_locator(sweep):
    planned(sweep)
    sweep.evidence([make_item("chat-1", locator="<CAF3x9ab@mail.example.com>")])

    assert sweep.index()[0] == 1


def inventory_with(name="Slack", description=None):
    server = {"name": name, "tools": []}
    if description is not None:
        server["description"] = description
    return {"schema_version": 1, "servers": [server], "skills": []}


@pytest.mark.parametrize(
    "text",
    [
        "contact " + "ops" + "@example.com",
        "set password: hunter22",
        "see https://x.example/p?token=abcdefgh12",
        "call 415-555-0123",
        "call +14155550123",
    ],
)
def test_descriptions_may_discuss_prose_shaped_secrets(sweep, text):
    assert sweep.plan(inventory_with(description=text))[0] == 0


@pytest.mark.parametrize("name", ["github_token", "private_key", "jwt", "aws_key", "stripe_key"])
def test_descriptions_still_reject_token_shaped_secrets(sweep, name):
    code, payload = sweep.plan(inventory_with(description=f"x {SENSITIVE_SAMPLES[name]}"))

    assert code == 2
    assert f"holds sensitive pattern {name} at offset 2" in payload["message"]
    assert SENSITIVE_SAMPLES[name] not in json.dumps(payload)


@pytest.mark.parametrize("name", ["email", "password_assignment", "phone_us", "url_secret_param"])
def test_names_get_the_full_pattern_set(sweep, name):
    code, payload = sweep.plan(inventory_with(name=f"Srv {SENSITIVE_SAMPLES[name]}\n"))

    assert code == 2
    assert f"holds sensitive pattern {name}" in payload["message"]


def test_inventory_names_and_descriptions_have_length_caps(sweep):
    assert sweep.plan(inventory_with(name="n" * 501))[0] == 2
    assert sweep.plan(inventory_with(description="d" * 1001))[0] == 2


def test_inventory_name_at_the_cap_is_accepted(sweep):
    assert sweep.plan(inventory_with(name="n" * 500))[0] == 0


# ------------------------------------------------------------------ path match lead-ins


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://github.com/o/r/blob/main/src/foo.py", True),
        ("github.com/o/r/blob/main/src/foo.py#L10", True),
        ("github.com/o/r/tree/v1.2.3/src/foo.py", True),
        ("github.com/o/r/blob/0123abcd/src/foo.py.", True),
        ("run ./src/foo.py now", True),
        ("run x./src/foo.py now", False),
        ("github.com/o/r/blob/main/other/src/foo.py", False),
        ("github.com/o/r/blame/main/src/foo.py", False),
        ("the src/foo.py file", True),
        ("lib/src/foo.py", False),
    ],
)
def test_path_lead_ins(text, expected):
    assert bootstrap_sweep.names_path(text, "src/foo.py") is expected


# ------------------------------------------------------------------ caps


@pytest.mark.parametrize(
    ("flag", "value", "code"),
    [
        ("--window-days", "3650", 0),
        ("--window-days", "3651", 2),
        ("--window-days", "0", 2),
        ("--judge-runs", "5", 0),
        ("--judge-runs", "6", 2),
        ("--judge-runs", "1", 2),
        ("--judge-runs", "2", 0),
    ],
)
def test_plan_caps(sweep, flag, value, code):
    got, _ = sweep.plan(None, flag, value)

    assert got == code
    assert sweep.run_dir.exists() is (code == 0)


# ------------------------------------------------------------------ --out guards


def tallied(sweep):
    sweep.ready()
    sweep.import_all([make_finding()])


@pytest.mark.parametrize("name", ["plan.json", "index.json", "accepted.json", "evidence.json"])
def test_out_never_replaces_run_files(sweep, name):
    tallied(sweep)
    target = sweep.run_dir / name
    before = target.read_bytes()

    code, payload = sweep.tally("--out", str(target))

    assert code == 2
    assert "inside the run directory" in payload["message"]
    assert target.read_bytes() == before


def test_out_never_replaces_a_rows_file_kept_in_the_run_dir(sweep):
    tallied(sweep)
    rows = sweep.run_dir / "rows-friction-1.json"
    rows.write_text('{"findings": []}', encoding="utf-8")

    assert sweep.tally("--out", str(rows))[0] == 2
    assert rows.read_text(encoding="utf-8") == '{"findings": []}'


def test_out_may_be_sweep_json_itself(sweep):
    tallied(sweep)
    assert sweep.tally()[0] == 0

    code, _ = sweep.tally("--out", str(sweep.run_dir / "sweep.json"))

    assert code == 0


def test_out_inside_run_dir_subfolder_is_refused(sweep):
    tallied(sweep)

    assert sweep.tally("--out", str(sweep.run_dir / "sub" / "x.json"))[0] == 2


@pytest.mark.parametrize("missing", ["incidents", "coverage", "index_id", "schema_version"])
def test_out_prior_sweep_needs_every_marker_key(sweep, tmp_path, missing):
    tallied(sweep)
    prior = {"schema_version": 1, "index_id": "x", "incidents": [], "coverage": []}
    del prior[missing]
    target = dump(tmp_path / "prior.json", prior)
    before = target.read_bytes()

    code, payload = sweep.tally("--out", str(target))

    assert code == 2
    assert "not a prior sweep" in payload["message"]
    assert target.read_bytes() == before


def test_out_replaces_a_complete_prior_sweep(sweep, tmp_path):
    tallied(sweep)
    prior = {"schema_version": 1, "index_id": "x", "incidents": [], "coverage": []}
    target = dump(tmp_path / "prior.json", prior)

    assert sweep.tally("--out", str(target))[0] == 0
    assert json.loads(target.read_text(encoding="utf-8"))["index_id"] == sweep.index_id()


# ------------------------------------------------------------------ typed loads exit 2


def edited_accepted(sweep, mutate):
    tallied(sweep)
    accepted = json.loads(sweep.accepted.read_text(encoding="utf-8"))
    mutate(accepted)
    dump(sweep.accepted, accepted)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a["rows"][0].update(run="1"),
        lambda a: a["rows"][0].update(judge=5),
        lambda a: a["rows"][0].update(batch_id=None),
        lambda a: a["rows"][0].update(finding_id=7),
        lambda a: a["imported"][0].update(judge=5),
        lambda a: a["imported"][0].update(run=True),
        lambda a: a["imported"][0].update(rows_sha256=3),
        lambda a: a.update(rows="x"),
        lambda a: a.update(imported={}),
    ],
)
def test_malformed_accepted_file_exits_2_without_traceback(sweep, mutate):
    edited_accepted(sweep, mutate)

    code, payload = sweep.tally()

    assert code == 2
    assert payload["error"] == "config"


def reindexed(sweep, mutate):
    sweep.ready()
    index = json.loads(sweep.index_path.read_text(encoding="utf-8"))
    mutate(index)
    body = {
        k: index[k] for k in ("schema_version", "plan_id", "items", "coverage", "metric_thresholds")
    }
    index["index_id"] = bootstrap_sweep.digest(body)
    index["batches"] = bootstrap_sweep.make_batches(index["index_id"], index["items"], 20)
    dump(sweep.index_path, index)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda i: i["items"][0].update(bytes="12"),
        lambda i: i["items"][0].update(sha256=None),
        lambda i: i["items"][0].update(date="yesterday"),
        lambda i: i["items"][0].update({"class": "mars"}),
        lambda i: i["items"][0].update(visibility="secret"),
        lambda i: i["items"][0].update(metrics=[1]),
        lambda i: i["coverage"].append("row"),
    ],
)
def test_malformed_index_items_exit_2_without_traceback(sweep, mutate):
    reindexed(sweep, mutate)

    code, payload = sweep.tally()

    assert code == 2
    assert payload["error"] == "config"


# ------------------------------------------------------------------ open flags


def test_evidence_is_opened_nonblocking_and_nofollow(tmp_path, monkeypatch):
    seen = []
    real_open = os.open

    def spy(path, flags, *args, **kwargs):
        seen.append(flags)
        return real_open(path, flags, *args, **kwargs)

    target = tmp_path / "a.md"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(os, "open", spy)

    assert bootstrap_sweep._read_regular_file(target) == b"hello"

    for name in ("O_NONBLOCK", "O_NOFOLLOW"):
        if hasattr(os, name):
            assert seen[0] & getattr(os, name)
