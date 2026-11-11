# taste-lint: ignore file-size, one suite owns the shared sweep fixtures for the hardening rules.
"""bootstrap_sweep hardening: tool verbs, free-text secrets, containment, caps, finding shape."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import bootstrap_sweep
import pytest
from bootstrap_helpers import symlink_or_skip
from sweep_helpers import (
    SENSITIVE_SAMPLES,
    cov,
    default_coverage,
    dump,
    make_finding,
    make_item,
)

DOC_REFERENCE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "skill-bootstrap"
    / "references"
    / "friction-sources.md"
)


def access(name: str, server: str = "") -> str:
    verdict: str = bootstrap_sweep.tool_access(
        {"name": name, "description": "", "access": None}, server
    )[0]
    return verdict


# ------------------------------------------------------------------ C2 tool classification


@pytest.mark.parametrize(
    "name",
    [
        "pull_request_read",
        "get_pull_request",
        "list_pull_requests",
        "search_pull_requests",
        "get_workflow_run",
        "get_label",
        "get_check_run",
        "issue_read",
        "list_commits",
        "get_commit",
        "actions_get",
        "actions_list",
        "get_job_logs",
        "list_issue_types",
        "search_public_and_private",
        "twilio_retrieve",
        "tavily_extract",
        "retrieve_document",
    ],
)
def test_noun_like_words_do_not_make_a_read_tool_a_write(name):
    assert access(name) == "read"


@pytest.mark.parametrize(
    "name",
    [
        "pull_request_review_write",
        "issue_write",
        "run_secret_scanning",
        "request_copilot_review",
        "label_message",
        "actions_run_trigger",
        "add_issue_comment",
        "update_pull_request",
        "get_or_create",
        "export_and_delete",
        "search_and_replace",
        "get_and_remove",
        "fetch_and_forward",
        "read_and_reply",
    ],
)
def test_write_verbs_win_over_read_verbs(name):
    assert access(name) == "write"


@pytest.mark.parametrize("name", ["search_and_replace", "get_and_remove", "fetch_and_forward"])
def test_compound_names_are_never_read(name):
    assert access(name) != "read"
    assert access("read_and_reply") != "read"


def test_read_needs_a_leading_or_trailing_read_verb():
    assert access("mystery_op") == "unknown"
    assert access("reflect") == "unknown"
    assert access("datasets") == "unknown"
    assert access("pull_request") == "write"


def test_server_name_prefix_is_stripped_before_reading_the_verb():
    assert access("slack_read_channel", "Slack") == "read"
    assert access("slack_send_message", "Slack") == "write"
    assert access("twilio__search", "Twilio") == "read"
    assert access("mcp__github__get_me", "github") == "read"


def test_leading_noun_verb_still_counts_as_a_verb():
    assert access("run_workflow") == "write"
    assert access("request_review") == "write"


# ------------------------------------------------------------------ S1 free text


def planned(sweep):
    assert sweep.plan()[0] == 0


@pytest.mark.parametrize("name", sorted(SENSITIVE_SAMPLES))
def test_inventory_strings_with_secrets_exit_2_without_echo(sweep, name):
    sample = SENSITIVE_SAMPLES[name]
    inventory = {
        "schema_version": 1,
        "servers": [{"name": f"Slack {sample}", "tools": []}],
        "skills": [],
    }

    code, payload = sweep.plan(inventory)

    assert code == 2
    assert f"holds sensitive pattern {name}" in payload["message"]
    assert sample not in json.dumps(payload)
    assert not sweep.run_dir.exists()


def test_inventory_tool_and_skill_names_are_scanned(sweep):
    secret = SENSITIVE_SAMPLES["github_token"]
    inventory = {
        "schema_version": 1,
        "servers": [{"name": "Slack", "tools": [secret]}],
        "skills": [],
    }

    assert sweep.plan(inventory)[0] == 2
    inventory = {"schema_version": 1, "servers": [], "skills": [secret]}
    assert sweep.plan(inventory)[0] == 2


@pytest.mark.parametrize("field", ["locator", "thread"])
@pytest.mark.parametrize("name", ["url_secret_param", "github_token", "email", "jwt"])
def test_locator_and_thread_are_scanned(sweep, field, name):
    planned(sweep)
    sample = SENSITIVE_SAMPLES[name].replace(" ", "")
    sweep.evidence([make_item("chat-1", **{field: sample})])

    code, payload = sweep.index()

    assert code == 1
    assert any(v.startswith(f"chat-1: {field}") and name in v for v in payload["violations"])
    assert sample not in json.dumps(payload)


@pytest.mark.parametrize("field", ["reason", "unread"])
def test_coverage_reason_and_unread_are_scanned(sweep, field):
    planned(sweep)
    extra = {"state": "partial", "reason": "rate limit", "unread": "older"}
    extra[field] = "see " + SENSITIVE_SAMPLES["github_token"]
    sweep.evidence(coverage=[cov("chat", **extra)] + default_coverage()[1:])

    code, payload = sweep.index()

    assert code == 1
    assert any(
        f"class chat {field} holds sensitive pattern github_token" in v
        for v in payload["violations"]
    )
    assert SENSITIVE_SAMPLES["github_token"] not in json.dumps(payload)


@pytest.mark.parametrize("field", ["reason", "unread"])
def test_coverage_text_is_capped_at_500_characters(sweep, field):
    planned(sweep)
    extra = {"state": "partial", "reason": "r", "unread": "u"}
    extra[field] = "x" * 501
    sweep.evidence(coverage=[cov("chat", **extra)] + default_coverage()[1:])

    code, payload = sweep.index()

    assert code == 1
    assert f"coverage: class chat {field} exceeds 500 characters" in payload["violations"]


def test_coverage_text_at_500_characters_passes(sweep):
    planned(sweep)
    row = cov("chat", state="partial", reason="x" * 500, unread="y" * 500)
    sweep.evidence(coverage=[row] + default_coverage()[1:])

    assert sweep.index()[0] == 0


@pytest.mark.parametrize("name", sorted(SENSITIVE_SAMPLES))
def test_every_sensitive_class_is_detected_in_evidence_text(sweep, name):
    planned(sweep)
    sweep.evidence([make_item("chat-1")], texts={"chat-1": f"note {SENSITIVE_SAMPLES[name]}\nend"})

    code, payload = sweep.index()

    assert code == 1
    assert any(
        re.fullmatch(rf"chat-1: sensitive pattern {name} at offset \d+", v)
        for v in payload["violations"]
    )


@pytest.mark.parametrize(
    "field", ["summary", "suggestion.target", "suggestion.rationale", "gap.question"]
)
@pytest.mark.parametrize("name", ["github_token", "email", "password_assignment"])
def test_finding_free_text_is_scanned(sweep, field, name):
    sweep.ready()
    sample = SENSITIVE_SAMPLES[name]
    row = make_finding()
    if "." in field:
        outer, inner = field.split(".")
        row[outer][inner] = f"x {sample}"
    else:
        row[field] = f"x {sample}"

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], [row])

    assert code == 1
    assert any(f"holds sensitive pattern {name}" in e for e in payload["errors"])
    assert sample not in json.dumps(payload)
    assert not sweep.accepted.exists()


def test_clean_text_with_near_misses_is_not_flagged():
    for text in ("passwords policy page", "token budget", "keys on a keyboard", "code review"):
        assert bootstrap_sweep.sensitive_classes(text) == []


# ------------------------------------------------------------------ C4 coverage state


@pytest.mark.parametrize("state", ["declined", "unavailable", "not_connected"])
def test_items_in_a_class_that_was_not_read_are_violations(sweep, state):
    planned(sweep)
    rows = [cov("chat", state=state, reason="owner said no")] + default_coverage()[1:]
    sweep.evidence([make_item("chat-1")], rows)

    code, payload = sweep.index()

    assert code == 1
    assert (
        f"chat-1: class chat coverage state is {state}; items need read or partial"
        in payload["violations"]
    )


@pytest.mark.parametrize("state", ["read", "partial"])
def test_items_in_read_or_partial_classes_pass(sweep, state):
    planned(sweep)
    rows = [cov("chat", state=state, reason="r", unread="u")] + default_coverage()[1:]
    sweep.evidence([make_item("chat-1")], rows)

    assert sweep.index()[0] == 0


# ------------------------------------------------------------------ containment, repo binding


def test_alias_of_the_repo_root_is_refused(tmp_path, repo, monkeypatch):
    seen = []

    def fake(left, right):
        seen.append(left)
        return left == tmp_path / "alias"

    monkeypatch.setattr(bootstrap_sweep, "_same_file", fake)

    with pytest.raises(bootstrap_sweep.ConfigError, match="inside the repository"):
        bootstrap_sweep.ensure_outside(repo, tmp_path / "alias" / "run", "run dir")
    assert tmp_path / "alias" in seen


def test_path_outside_the_repo_is_accepted(tmp_path, repo):
    assert (
        bootstrap_sweep.ensure_outside(repo, tmp_path / "elsewhere" / "run", "x")
        == (tmp_path / "elsewhere" / "run").resolve()
    )


def test_same_file_is_false_for_missing_paths(tmp_path):
    assert bootstrap_sweep._same_file(tmp_path / "nope", tmp_path / "nada") is False


def test_symlink_to_repo_is_refused(tmp_path, repo):
    link = tmp_path / "link"
    symlink_or_skip(link, repo)

    with pytest.raises(bootstrap_sweep.ConfigError):
        bootstrap_sweep.ensure_outside(repo, link / "child", "x")


def other_repo(make_repo, tmp_path):
    return make_repo(tmp_path / "other")


def test_index_with_a_different_repo_exits_2(sweep, make_repo, tmp_path):
    sweep.ready()
    other = other_repo(make_repo, tmp_path)

    code, payload = sweep.cli("index", "--plan", str(sweep.plan_path), "--repo", str(other))

    assert code == 2
    assert "differs from the repository in the plan" in payload["message"]


def test_import_with_a_different_repo_exits_2(sweep, make_repo, tmp_path):
    sweep.ready()
    other = other_repo(make_repo, tmp_path)
    rows = sweep.rows_file("friction", 1, sweep.batches()[0], [make_finding()])

    code, payload = sweep.cli(
        "import",
        "--index",
        str(sweep.index_path),
        "--repo",
        str(other),
        "--rows",
        str(rows),
        "--accepted",
        str(sweep.accepted),
    )

    assert code == 2
    assert "differs from the repository in the plan" in payload["message"]
    assert not sweep.accepted.exists()


def test_tally_with_a_different_repo_exits_2(sweep, make_repo, tmp_path):
    sweep.ready()
    sweep.import_all([make_finding()])
    other = other_repo(make_repo, tmp_path)

    code, payload = sweep.cli(
        "tally",
        "--index",
        str(sweep.index_path),
        "--accepted",
        str(sweep.accepted),
        "--repo",
        str(other),
    )

    assert code == 2
    assert "differs from the repository in the plan" in payload["message"]
    assert not (sweep.run_dir / "sweep.json").exists()


def test_repo_flag_is_required_for_index_and_import(sweep):
    sweep.ready()

    with pytest.raises(SystemExit) as exc:
        sweep.cli("index", "--plan", str(sweep.plan_path))
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        sweep.cli("import", "--index", str(sweep.index_path), "--rows", "r", "--accepted", "a")
    assert exc.value.code == 2


def test_repo_may_be_a_subdirectory_of_the_plan_repo(sweep, repo):
    sweep.ready()
    sub = repo / ".claude"

    code, _ = sweep.cli("index", "--plan", str(sweep.plan_path), "--repo", str(sub))

    assert code == 0


# ------------------------------------------------------------------ L1 markdown cells


def test_markdown_cells_keep_only_a_safe_alphabet(sweep):
    inventory = {
        "schema_version": 1,
        "servers": [{"name": "Evil|name`x\n[l](u)", "tools": ["get_x"]}],
        "skills": [],
    }
    assert sweep.plan(inventory)[0] == 0
    item = make_item("o-1", "other", server="Evil|name`x\n[l](u)")
    sweep.evidence([item], [cov("other")])
    assert sweep.index()[0] == 0
    sweep.import_all([make_finding(evidence=["o-1"])])

    code, _ = sweep.tally()

    text = (sweep.run_dir / "friction-map.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if "Evil" in line)
    assert code == 0
    assert row.startswith("| Evil_name_x__l_(u) |")
    assert "`x" not in row
    assert "[l]" not in row


def test_cell_function_replaces_disallowed_characters():
    assert (
        bootstrap_sweep._cell("Slack workspace.v2:a/b@c#d(e)+f-g")
        == "Slack workspace.v2:a/b@c#d(e)+f-g"
    )
    assert bootstrap_sweep._cell("a|b`c<d>e") == "a_b_c_d_e"


# ------------------------------------------------------------------ L3 caps


def test_manifest_over_5000_items_exits_2(sweep):
    planned(sweep)
    items = [make_item(f"i-{n}") for n in range(5001)]
    dump(
        sweep.run_dir / "evidence.json",
        {
            "schema_version": 1,
            "plan_id": sweep.load_plan()["plan_id"],
            "coverage": [],
            "items": items,
        },
    )

    code, payload = sweep.index()

    assert code == 2
    assert "more than 5000 items" in payload["message"]


def test_rows_file_over_500_findings_exits_2(sweep):
    sweep.ready()
    findings = [make_finding(finding_id=f"f{n}") for n in range(501)]

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], findings)

    assert code == 2
    assert "more than 500 findings" in payload["message"]
    assert not sweep.accepted.exists()


def test_rows_file_of_exactly_500_findings_is_accepted(sweep):
    sweep.ready()
    findings = [make_finding(finding_id=f"f{n}") for n in range(500)]

    assert sweep.import_("friction", 1, sweep.batches()[0], findings)[0] == 0


# ------------------------------------------------------------------ L4 --out


def test_out_must_end_in_json(sweep, tmp_path):
    sweep.ready()
    sweep.import_all([make_finding()])

    code, payload = sweep.tally("--out", str(tmp_path / "sweep.txt"))

    assert code == 2
    assert ".json" in payload["message"]
    assert not (tmp_path / "sweep.txt").exists()


def test_out_refuses_an_existing_file_that_is_not_a_prior_sweep(sweep, tmp_path):
    sweep.ready()
    sweep.import_all([make_finding()])
    target = tmp_path / "precious.json"
    target.write_text('{"keep": "me"}', encoding="utf-8")

    code, payload = sweep.tally("--out", str(target))

    assert code == 2
    assert "not a prior sweep" in payload["message"]
    assert target.read_text(encoding="utf-8") == '{"keep": "me"}'


def test_out_refuses_an_existing_non_json_file(sweep, tmp_path):
    sweep.ready()
    sweep.import_all([make_finding()])
    target = tmp_path / "notes.json"
    target.write_text("not json at all", encoding="utf-8")

    assert sweep.tally("--out", str(target))[0] == 2
    assert target.read_text(encoding="utf-8") == "not json at all"


def test_out_replaces_a_prior_sweep(sweep, tmp_path):
    sweep.ready()
    sweep.import_all([make_finding()])
    target = tmp_path / "sweep-copy.json"
    assert sweep.tally("--out", str(target))[0] == 0

    code, _ = sweep.tally("--out", str(target))

    assert code == 0
    assert json.loads(target.read_text(encoding="utf-8"))["index_id"] == sweep.index_id()


def test_out_refuses_a_directory(sweep, tmp_path):
    sweep.ready()
    sweep.import_all([make_finding()])
    folder = tmp_path / "folder.json"
    folder.mkdir()

    assert sweep.tally("--out", str(folder))[0] == 2


# ------------------------------------------------------------------ L5 run type


@pytest.mark.parametrize("run", [True, 1.0, "1", None, [1]])
def test_non_integer_run_exits_2_cleanly(sweep, run):
    sweep.ready()

    code, payload = sweep.import_("friction", 1, sweep.batches()[0], [make_finding()], run=run)

    assert code == 2
    assert payload["error"] == "config"
    assert not sweep.accepted.exists()


# ------------------------------------------------------------------ L2 evidence open


def test_regular_file_read_is_bounded(tmp_path):
    big = tmp_path / "big.md"
    big.write_bytes(b"a" * (bootstrap_sweep.MAX_EVIDENCE_BYTES + 1))
    ok = tmp_path / "ok.md"
    ok.write_bytes(b"a" * bootstrap_sweep.MAX_EVIDENCE_BYTES)

    with pytest.raises(bootstrap_sweep.EvidenceError, match="64 KiB"):
        bootstrap_sweep._read_regular_file(big)
    assert len(bootstrap_sweep._read_regular_file(ok)) == bootstrap_sweep.MAX_EVIDENCE_BYTES


def test_directory_is_not_a_regular_file(tmp_path):
    with pytest.raises(bootstrap_sweep.EvidenceError):
        bootstrap_sweep._read_regular_file(tmp_path)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="platform lacks O_NOFOLLOW")
def test_final_symlink_is_not_followed(tmp_path):
    target = tmp_path / "real.md"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link.md"
    symlink_or_skip(link, target)

    with pytest.raises(bootstrap_sweep.EvidenceError, match="unreadable"):
        bootstrap_sweep._read_regular_file(link)


# ------------------------------------------------------------------ C1 documented finding shape


def documented_example(index_id: str, batch: str) -> dict[str, Any]:
    text = DOC_REFERENCE.read_text(encoding="utf-8")
    section = text.split("## Finding contract", 1)[1]
    block = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert block is not None
    raw = block.group(1).replace("<index>", index_id).replace("<batch>", batch)
    raw = raw.replace("mail-004", "chat-1").replace("chat-011", "chat-2")
    document: dict[str, Any] = json.loads(raw)
    return document


def test_documented_rows_example_imports_verbatim(sweep):
    sweep.ready()
    doc = documented_example(sweep.index_id(), sweep.batches()[0])
    rows = dump(sweep.tmp / "documented.json", doc)

    code, payload = sweep.cli(
        "import",
        "--index",
        str(sweep.index_path),
        "--repo",
        str(sweep.repo),
        "--rows",
        str(rows),
        "--accepted",
        str(sweep.accepted),
    )

    assert code == 0, payload
    stored = json.loads(sweep.accepted.read_text(encoding="utf-8"))["rows"][0]
    assert "batch_id" in doc["findings"][0]
    assert stored["batch_id"] == sweep.batches()[0]
    assert stored["finding_id"] == "f1"


def test_per_finding_batch_id_is_dropped_before_merge(sweep):
    sweep.ready()
    batch = sweep.batches()[0]

    assert sweep.import_("friction", 1, batch, [make_finding(batch_id=batch)])[0] == 0

    accepted = json.loads(sweep.accepted.read_text(encoding="utf-8"))
    plain = make_finding()
    assert accepted["imported"][0]["rows_sha256"] == bootstrap_sweep.rows_digest([plain])
    assert list(accepted["rows"][0]).count("batch_id") == 1


def test_per_finding_batch_id_matches_the_same_import_without_it(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    sweep.import_("friction", 1, batch, [make_finding(batch_id=batch)])
    with_field = sweep.accepted.read_bytes()
    sweep.accepted.unlink()

    sweep.import_("friction", 1, batch, [make_finding()])

    assert sweep.accepted.read_bytes() == with_field


def test_per_finding_batch_id_that_differs_is_rejected(sweep):
    sweep.ready("--batch-size", "2")
    first, second = sweep.batches()[:2]

    code, payload = sweep.import_("friction", 1, first, [make_finding(batch_id=second)])

    assert code == 1
    assert "findings[0]: batch_id differs from the rows file batch_id" in payload["errors"]
    assert not sweep.accepted.exists()
