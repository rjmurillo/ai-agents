# taste-lint: ignore file-size, one suite owns the shared sweep fixtures for this subcommand.
"""bootstrap_sweep tally: agreement, incidents, corroboration, ranking, gaps, outputs."""

from __future__ import annotations

import json
import shutil
from typing import Any

import pytest
from sweep_helpers import (
    JUDGES,
    cov,
    default_coverage,
    dump,
    make_finding,
    make_item,
)


def finding(**overrides):
    base = make_finding()
    for key, value in overrides.items():
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value
    return base


def plain(**overrides):
    """A non-gap finding."""
    return finding(**{"type": "human-tool", "gap": None, **overrides})


def prepare(sweep, items=None, texts=None, *extra):
    assert sweep.plan()[0] == 0
    sweep.evidence(items, None, texts)
    code, payload = sweep.index(*extra)
    assert code == 0, payload


def import_runs(sweep, findings, overrides=None, skip=()):
    batch = sweep.batches()[0]
    for judge in JUDGES:
        for run in (1, 2):
            if (judge, run) in skip:
                continue
            rows = (overrides or {}).get((judge, run), findings)
            code, payload = sweep.import_(judge, run, batch, rows)
            assert code == 0, payload


def incident_map(payload):
    return {i["incident"]: i for i in payload["incidents"]}


def sweep_of(sweep, findings, **kw):
    import_runs(sweep, findings, **kw)
    code, payload = sweep.tally()
    assert code == 0, payload
    return payload


def shared_thread_items():
    return [
        make_item("chat-1", thread="shared"),
        make_item("chat-2", thread="shared", date="2026-10-02"),
        make_item("pr-1", "code_review", date="2026-10-03"),
        make_item("mem-1", "memory"),
    ]


# ------------------------------------------------------------------ agreement (D)


def test_agreed_findings_form_an_incident(sweep):
    sweep.ready()

    payload = sweep_of(sweep, [finding()])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["findings"] == 4
    assert incident["judges"] == list(JUDGES)
    assert incident["primary_type"] == "knowledge-gap"
    assert incident["evidence"] == ["chat-1"]
    assert payload["single_reader"] == []
    assert payload["examined"] == {
        "items": 4,
        "batches": 1,
        "findings": 4,
        "incidents": 1,
        "corroborated": 0,
    }


def test_finding_seen_by_one_run_only_is_single_reader_and_not_an_incident(sweep):
    sweep.ready()
    other = {("friction", 2): [plain(finding_id="x9", incident="different-key")]}

    payload = sweep_of(sweep, [finding()], overrides=other)

    assert "different-key" not in incident_map(payload)
    assert {
        "judge": "friction",
        "run": 2,
        "batch_id": sweep.batches()[0],
        "finding_id": "x9",
        "incident": "different-key",
    } in payload["single_reader"]
    friction_one = [
        r for r in payload["single_reader"] if r["run"] == 1 and r["judge"] == "friction"
    ]
    assert [r["finding_id"] for r in friction_one] == ["f1"]
    assert incident_map(payload)["slow-onboarding"]["judges"] == ["knowledge-gap"]


def test_same_type_but_disjoint_evidence_does_not_agree(sweep):
    sweep.ready()
    other = {("friction", 2): [finding(evidence=["chat-2"])]}

    payload = sweep_of(sweep, [finding()], overrides=other)

    assert [r["run"] for r in payload["single_reader"]] == [1, 2]
    assert {r["judge"] for r in payload["single_reader"]} == {"friction"}


def test_overlapping_evidence_with_same_type_agrees(sweep):
    sweep.ready()
    other = {("friction", 2): [finding(evidence=["chat-1", "chat-2"])]}

    payload = sweep_of(sweep, [finding()], overrides=other)

    assert payload["single_reader"] == []
    assert incident_map(payload)["slow-onboarding"]["evidence"] == ["chat-1", "chat-2"]


def test_agreement_never_crosses_judges(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    # Each judge reads once with a finding of its own type, so no judge agrees with itself.
    for judge, run, kind in (("friction", 1, "human-tool"), ("friction", 2, "agent-tool")):
        sweep.import_(judge, run, batch, [plain(type=kind)])
    for run in (1, 2):
        sweep.import_("knowledge-gap", run, batch, [plain(type="human-tool")])

    code, payload = sweep.tally()

    assert code == 0
    assert incident_map(payload)["slow-onboarding"]["judges"] == ["knowledge-gap"]
    assert len(payload["single_reader"]) == 2


def test_single_reader_findings_never_reach_knowledge_gaps(sweep):
    sweep.ready()
    other: dict[tuple[str, int], list[Any]] = {(j, r): [] for j in JUDGES for r in (1, 2)}

    payload = sweep_of(sweep, [finding()], overrides=other)

    assert payload["incidents"] == []
    assert payload["knowledge_gaps"] == []


# ------------------------------------------------------------------ AC10 corroboration (G)


def test_two_classes_corroborate(sweep):
    sweep.ready()

    payload = sweep_of(sweep, [plain(evidence=["chat-1", "pr-1"])])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["corroborated"] is True
    assert incident["corroboration"] == ["classes", "threads"]
    assert incident["classes"] == ["chat", "code_review"]


def test_two_threads_in_one_class_corroborate(sweep):
    sweep.ready()

    payload = sweep_of(sweep, [plain(evidence=["chat-1", "chat-2"])])

    assert incident_map(payload)["slow-onboarding"]["corroboration"] == ["threads"]


def test_two_items_in_the_same_thread_do_not_corroborate(sweep):
    prepare(sweep, shared_thread_items())

    payload = sweep_of(sweep, [plain(evidence=["chat-1", "chat-2"])])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["corroborated"] is False
    assert incident["corroboration"] == []
    assert incident["threads"] == ["shared"]
    assert len(incident["locators"]) == 2


def test_tracked_path_in_evidence_text_corroborates(sweep):
    prepare(sweep, texts={"chat-1": "The steps live in README.md today."})

    payload = sweep_of(sweep, [plain(repo_paths=["README.md"])])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["corroboration"] == ["repo_path"]
    assert incident["repo_paths"] == ["README.md"]


def test_untracked_path_does_not_corroborate(sweep):
    prepare(sweep, texts={"chat-1": "see nowhere/ghost.py for it"})

    payload = sweep_of(sweep, [plain(repo_paths=["nowhere/ghost.py"])])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["corroborated"] is False
    assert incident["repo_paths"] == []


def test_tracked_path_absent_from_evidence_text_does_not_corroborate(sweep):
    prepare(sweep)

    payload = sweep_of(sweep, [plain(repo_paths=["README.md"])])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["corroborated"] is False
    assert incident["repo_paths"] == ["README.md"]


def test_tracked_directory_does_not_corroborate_or_count_as_tracked(sweep):
    prepare(sweep, texts={"chat-1": "look in .claude/skills"})

    payload = sweep_of(sweep, [plain(repo_paths=[".claude/skills"])])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["corroborated"] is False
    assert incident["repo_paths"] == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see README.md for it", True),
        ("see README.md.", True),
        ("(README.md)", True),
        ("`README.md`, then", True),
        ("MyREADME.md", False),
        ("docs/README.md", False),
        ("README.md.bak", False),
        ("README.mdx", False),
        ("README.md/more", False),
        ("a-README.md", False),
    ],
)
def test_path_match_needs_boundaries(text, expected):
    import bootstrap_sweep

    assert bootstrap_sweep.names_path(text, "README.md") is expected


def test_name_inside_a_longer_word_does_not_corroborate(sweep, repo):
    from bootstrap_helpers import run_git, write

    write(repo, "Makefile", "all:\n")
    run_git(repo, "add", "Makefile")
    run_git(repo, "commit", "-q", "-m", "chore: add makefile")
    prepare(sweep, texts={"chat-1": "see MyMakefile and transcripts"})

    payload = sweep_of(sweep, [plain(repo_paths=["Makefile", "scripts"])])

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["corroborated"] is False
    assert incident["repo_paths"] == ["Makefile"]


def test_evidence_changed_after_indexing_exits_2_when_text_is_needed(sweep):
    prepare(sweep, texts={"chat-1": "see README.md"})
    import_runs(sweep, [plain(repo_paths=["README.md"])])
    (sweep.run_dir / "evidence" / "chat-1.md").write_text("tampered README.md")

    code, payload = sweep.tally()

    assert code == 2
    assert "changed since indexing" in payload["message"]


# ------------------------------------------------------------------ ranking (H) and types


def ranked(sweep, findings):
    return [i["incident"] for i in sweep_of(sweep, findings)["incidents"]]


def test_ranking_corroborated_then_gap_then_threads_then_evidence_then_key(sweep):
    prepare(sweep, shared_thread_items())
    findings = [
        finding(
            finding_id="1",
            incident="d-plain",
            type="human-tool",
            gap=None,
            evidence=["chat-1", "chat-2"],
        ),
        finding(finding_id="2", incident="a-gap", evidence=["chat-1"]),
        finding(
            finding_id="3",
            incident="b-corr",
            type="human-tool",
            gap=None,
            evidence=["chat-1", "pr-1"],
        ),
        finding(finding_id="4", incident="c-gap-corr", evidence=["chat-1", "pr-1", "mem-1"]),
        finding(
            finding_id="5", incident="e-plain", type="human-tool", gap=None, evidence=["chat-2"]
        ),
    ]

    assert ranked(sweep, findings) == ["c-gap-corr", "b-corr", "a-gap", "d-plain", "e-plain"]


def test_more_threads_outrank_more_evidence(sweep):
    sweep.ready()
    findings = [
        plain(finding_id="1", incident="two-threads", evidence=["chat-1", "pr-1"]),
        plain(finding_id="2", incident="three-threads", evidence=["chat-1", "pr-1", "mem-1"]),
    ]

    assert ranked(sweep, findings) == ["three-threads", "two-threads"]


def test_equal_threads_more_evidence_first_then_key(sweep):
    prepare(sweep, shared_thread_items())
    findings = [
        plain(finding_id="1", incident="zz-one", evidence=["chat-1"]),
        plain(finding_id="2", incident="aa-one", evidence=["chat-2"]),
        plain(finding_id="3", incident="mm-two", evidence=["chat-1", "chat-2"]),
    ]

    assert ranked(sweep, findings) == ["mm-two", "aa-one", "zz-one"]


def test_people_is_reported_but_not_ranked(sweep):
    sweep.ready()
    findings = [
        plain(finding_id="1", incident="many-people", people=50, evidence=["chat-1"]),
        plain(finding_id="2", incident="few-people", people=1, evidence=["chat-1", "pr-1"]),
    ]
    payload = sweep_of(sweep, findings)

    assert [i["incident"] for i in payload["incidents"]] == ["few-people", "many-people"]
    assert incident_map(payload)["many-people"]["people"] == 50


def test_primary_type_tie_follows_fixed_order(sweep):
    sweep.ready()
    findings = [
        plain(finding_id="1", type="human-human"),
        plain(finding_id="2", type="agent-tool"),
    ]
    payload = sweep_of(sweep, findings)

    incident = incident_map(payload)["slow-onboarding"]
    assert incident["primary_type"] == "agent-tool"
    assert incident["types"] == {"agent-tool": 4, "human-human": 4}


def test_primary_type_prefers_the_most_frequent(sweep):
    batch_findings = [
        plain(finding_id="1", type="human-human"),
        plain(finding_id="2", type="human-human", evidence=["chat-2"]),
        plain(finding_id="3", type="knowledge-gap", evidence=["chat-1"], gap=finding()["gap"]),
    ]
    sweep.ready()

    payload = sweep_of(sweep, batch_findings)

    assert incident_map(payload)["slow-onboarding"]["primary_type"] == "human-human"


def test_patterns_counted_per_incident_and_across_incidents(sweep):
    sweep.ready()
    findings = [
        plain(finding_id="1", incident="one", pattern="shadow-work"),
        plain(finding_id="2", incident="one", pattern="shadow-work"),
        plain(finding_id="3", incident="one", pattern="unstable-checks"),
        plain(finding_id="4", incident="two", pattern="shadow-work"),
    ]
    payload = sweep_of(sweep, findings)

    assert incident_map(payload)["one"]["patterns"] == {"shadow-work": 8, "unstable-checks": 4}
    counts = payload["pattern_counts"]
    assert counts["shadow-work"] == 2
    assert counts["unstable-checks"] == 1
    assert counts["other"] == 0
    assert len(counts) == 14


def test_suggestions_deduped_by_action_and_target(sweep):
    sweep.ready()
    findings = [
        plain(finding_id="1"),
        plain(
            finding_id="2",
            suggestion={"action": "write-doc", "target": "docs/onboarding", "rationale": "again"},
        ),
        plain(
            finding_id="3",
            suggestion={"action": "fix-process", "target": "docs/onboarding", "rationale": "x"},
        ),
    ]
    payload = sweep_of(sweep, findings)

    suggestions = incident_map(payload)["slow-onboarding"]["suggestions"]
    assert [(s["action"], s["target"]) for s in suggestions] == [
        ("fix-process", "docs/onboarding"),
        ("write-doc", "docs/onboarding"),
    ]


# ------------------------------------------------------------------ AC12 gaps (I)


def gap(location, documented):
    return {"question": "How?", "answer_location": location, "documented": documented}


@pytest.mark.parametrize(
    ("location", "documented", "expected"),
    [
        ("person", False, "unresolved"),
        ("person", True, "unresolved"),
        ("unknown", True, "unresolved"),
        ("repo", False, "document"),
        ("chat", True, "document"),
        ("meeting", False, "document"),
        ("repo", True, "covered"),
        ("maintained_doc", True, "covered"),
    ],
)
def test_gap_disposition(sweep, location, documented, expected):
    sweep.ready()

    payload = sweep_of(sweep, [finding(gap=gap(location, documented))])

    [entry] = payload["knowledge_gaps"]
    assert entry["disposition"] == expected
    assert entry["incident"] == "slow-onboarding"
    assert entry["answer_locations"] == [location]
    assert entry["questions"] == ["How?"]


def test_covered_requires_every_finding_documented_in_repo_or_doc(sweep):
    sweep.ready()
    rows = [
        finding(finding_id="1", gap=gap("repo", True)),
        finding(finding_id="2", gap=gap("maintained_doc", False)),
    ]

    assert sweep_of(sweep, rows)["knowledge_gaps"][0]["disposition"] == "document"


def test_any_person_or_unknown_location_makes_incident_unresolved(sweep):
    sweep.ready()
    rows = [
        finding(finding_id="1", gap=gap("repo", True)),
        finding(finding_id="2", gap=gap("unknown", True)),
    ]

    assert sweep_of(sweep, rows)["knowledge_gaps"][0]["disposition"] == "unresolved"


def test_gaps_sorted_unresolved_then_document_then_covered(sweep):
    sweep.ready()
    rows = [
        finding(finding_id="1", incident="a-covered", gap=gap("repo", True)),
        finding(finding_id="2", incident="b-document", gap=gap("chat", False)),
        finding(finding_id="3", incident="c-unresolved", gap=gap("person", False)),
    ]

    gaps = sweep_of(sweep, rows)["knowledge_gaps"]

    assert [g["disposition"] for g in gaps] == ["unresolved", "document", "covered"]


def test_incident_without_gap_findings_has_no_gap_entry(sweep):
    sweep.ready()

    assert sweep_of(sweep, [plain()])["knowledge_gaps"] == []


# ------------------------------------------------------------------ AC11 incomplete


def test_missing_triples_are_listed_and_exit_1(sweep):
    sweep.ready()
    batch = sweep.batches()[0]
    import_runs(sweep, [finding()], skip={("friction", 2), ("knowledge-gap", 1)})

    code, payload = sweep.tally()

    assert code == 1
    assert payload["incomplete"] == [
        {"judge": "friction", "run": 2, "batch_id": batch},
        {"judge": "knowledge-gap", "run": 1, "batch_id": batch},
    ]
    assert (sweep.run_dir / "sweep.json").is_file()


def test_every_batch_judge_run_pair_is_required(sweep):
    sweep.ready("--batch-size", "2")
    first = sweep.batches()[0]
    sweep.import_all([finding()], first)

    code, payload = sweep.tally()

    assert code == 1
    assert len(payload["incomplete"]) == 4
    assert {p["batch_id"] for p in payload["incomplete"]} == {sweep.batches()[1]}


def test_empty_findings_import_counts_as_complete(sweep):
    sweep.ready()
    import_runs(sweep, [])

    code, payload = sweep.tally()

    assert code == 0
    assert payload["incomplete"] == []
    assert payload["incidents"] == []


def test_tally_without_accepted_file_exits_2(sweep):
    sweep.ready()

    code, payload = sweep.tally()

    assert code == 2
    assert "does not exist" in payload["message"]


def test_tampered_accepted_rows_exit_2(sweep):
    sweep.ready()
    import_runs(sweep, [finding()])
    accepted = json.loads(sweep.accepted.read_text())
    accepted["rows"][0]["people"] = 99
    dump(sweep.accepted, accepted)

    assert sweep.tally()[0] == 2


def test_accepted_row_citing_evidence_outside_its_batch_exits_2(sweep):
    sweep.ready("--batch-size", "2")
    import_runs(sweep, [finding()])
    accepted = json.loads(sweep.accepted.read_text())
    accepted["rows"][0]["evidence"] = ["mem-1"]
    findings = [
        {k: v for k, v in r.items() if k not in ("judge", "run", "batch_id")}
        for r in accepted["rows"]
        if (r["judge"], r["run"]) == (accepted["rows"][0]["judge"], accepted["rows"][0]["run"])
    ]
    import bootstrap_sweep

    accepted["imported"][0]["rows_sha256"] = bootstrap_sweep.rows_digest(findings)
    dump(sweep.accepted, accepted)

    code, payload = sweep.tally()

    assert code == 2
    assert "is invalid" in payload["message"]


# ------------------------------------------------------------------ coverage rows


def test_coverage_has_one_row_per_source_class(sweep):
    sweep.ready()

    payload = sweep_of(sweep, [finding()])

    rows = payload["coverage"]
    assert [r["class"] for r in rows] == [
        "code_review",
        "work_tracking",
        "chat",
        "email",
        "documents",
        "meetings",
        "build_ops",
        "memory",
        "work_intelligence",
        "agent_sessions",
        "other",
    ]
    by_class = {r["class"]: r for r in rows}
    assert by_class["email"]["state"] == "not_connected"
    assert by_class["email"]["items_read"] == 0
    assert by_class["chat"]["state"] == "read"
    assert by_class["chat"]["indexed_items"] == 2
    assert by_class["code_review"]["indexed_items"] == 1


def test_declared_coverage_row_for_unconnected_class_is_kept(sweep):
    assert sweep.plan()[0] == 0
    sweep.evidence(
        coverage=default_coverage() + [cov("email", state="declined", reason="owner said no")]
    )
    sweep.index()
    import_runs(sweep, [finding()])

    payload = sweep.tally()[1]

    email = next(r for r in payload["coverage"] if r["class"] == "email")
    assert email["state"] == "declined"
    assert email["reason"] == "owner said no"


# ------------------------------------------------------------------ aliases (E)


def alias_file(sweep, aliases, **overrides):
    doc = {"schema_version": 1, "index_id": sweep.index_id(), "aliases": aliases}
    doc.update(overrides)
    return dump(sweep.tmp / "aliases.json", doc)


def two_keys():
    return [
        plain(finding_id="1", incident="slow-onboarding"),
        plain(finding_id="2", incident="onboarding-is-slow"),
    ]


def test_aliases_merge_incident_keys_before_tallying(sweep):
    sweep.ready()
    import_runs(sweep, two_keys())
    path = alias_file(sweep, {"onboarding-is-slow": "slow-onboarding"})

    code, payload = sweep.tally("--aliases", str(path))

    assert code == 0
    assert list(incident_map(payload)) == ["slow-onboarding"]
    assert incident_map(payload)["slow-onboarding"]["findings"] == 8


def test_without_aliases_keys_stay_separate(sweep):
    sweep.ready()

    payload = sweep_of(sweep, two_keys())

    assert len(payload["incidents"]) == 2


@pytest.mark.parametrize(
    "aliases",
    [
        {"ghost-key": "slow-onboarding"},
        {"onboarding-is-slow": "Not Kebab"},
        {"onboarding-is-slow": "onboarding-is-slow"},
        {"onboarding-is-slow": "slow-onboarding", "slow-onboarding": "other-key"},
        {"onboarding-is-slow": "slow-onboarding", "slow-onboarding": "onboarding-is-slow"},
    ],
    ids=["unknown-key", "non-kebab", "self", "chain", "cycle"],
)
def test_bad_aliases_exit_2(sweep, aliases):
    sweep.ready()
    import_runs(sweep, two_keys())

    code, payload = sweep.tally("--aliases", str(alias_file(sweep, aliases)))

    assert code == 2
    assert payload["error"] == "config"


def test_aliases_for_another_index_exit_2(sweep):
    sweep.ready()
    import_runs(sweep, two_keys())
    path = alias_file(sweep, {}, index_id="0" * 64)

    assert sweep.tally("--aliases", str(path))[0] == 2


def test_aliases_with_wrong_schema_exit_2(sweep):
    sweep.ready()
    import_runs(sweep, two_keys())

    assert sweep.tally("--aliases", str(alias_file(sweep, {}, schema_version=2)))[0] == 2


# ------------------------------------------------------------------ paths, drift, determinism


def test_judge_drift_exits_2(sweep, skill_dir):
    sweep.ready()
    import_runs(sweep, [finding()])
    (skill_dir / "judges" / "friction.md").write_text("changed\n")

    code, payload = sweep.tally()

    assert code == 2
    assert "changed since plan" in payload["message"]


def test_out_inside_repo_exits_2_and_writes_nothing(sweep, repo):
    sweep.ready()
    import_runs(sweep, [finding()])

    code, payload = sweep.tally("--out", str(repo / "sweep.json"))

    assert code == 2
    assert "inside the repository" in payload["message"]
    assert not (repo / "sweep.json").exists()
    assert not (sweep.run_dir / "sweep.json").exists()


def test_out_outside_repo_matches_stdout_and_sweep_json(sweep, tmp_path):
    sweep.ready()
    import_runs(sweep, [finding()])
    target = tmp_path / "copy" / "sweep.json"

    code, payload = sweep.tally("--out", str(target))

    assert code == 0
    assert json.loads(target.read_text()) == payload
    assert json.loads((sweep.run_dir / "sweep.json").read_text()) == payload


def test_tally_run_dir_inside_repo_exits_2(sweep, repo):
    sweep.ready()
    import_runs(sweep, [finding()])
    moved = repo / "copied-run"
    shutil.copytree(sweep.run_dir, moved)

    code, payload = sweep.cli(
        "tally",
        "--index",
        str(moved / "index.json"),
        "--accepted",
        str(moved / "accepted.json"),
        "--repo",
        str(repo),
    )

    assert code == 2
    assert "inside the repository" in payload["message"]
    assert not (moved / "sweep.json").exists()


def test_tally_is_deterministic(sweep):
    sweep.ready()
    import_runs(sweep, [finding(), plain(finding_id="2", incident="other-one")])
    sweep.tally()
    first = (
        (sweep.run_dir / "sweep.json").read_bytes(),
        (sweep.run_dir / "friction-map.md").read_bytes(),
    )

    sweep.tally()

    assert (sweep.run_dir / "sweep.json").read_bytes() == first[0]
    assert (sweep.run_dir / "friction-map.md").read_bytes() == first[1]


def test_sweep_top_level_keys(sweep):
    sweep.ready()

    payload = sweep_of(sweep, [finding()])

    assert sorted(payload) == [
        "coverage",
        "examined",
        "friction_map",
        "incidents",
        "incomplete",
        "index_id",
        "knowledge_gaps",
        "outliers",
        "outliers_not_computed",
        "pattern_counts",
        "plan_id",
        "schema_version",
        "single_reader",
    ]
    assert payload["index_id"] == sweep.index_id()
    assert payload["plan_id"] == sweep.load_plan()["plan_id"]


# ------------------------------------------------------------------ friction map


def test_friction_map_has_one_row_per_system_with_evidence(sweep):
    sweep.ready()
    findings = [
        plain(finding_id="1", incident="one", pattern="shadow-work", evidence=["chat-1", "pr-1"]),
        finding(finding_id="2", incident="two", evidence=["chat-2"]),
    ]
    payload = sweep_of(sweep, findings)

    rows = {r["server"]: r for r in payload["friction_map"]}
    assert sorted(rows) == ["Slack", "github", "memory-search"]
    slack = rows["Slack"]
    assert slack["classes"] == ["chat"]
    assert slack["items"] == 2
    assert slack["incidents"] == 2
    assert slack["knowledge_gaps"] == 1
    assert slack["patterns"]["shadow-work"] == 1
    assert slack["patterns"]["fragmented-context"] == 1
    assert len(slack["patterns"]) == 14
    assert rows["github"]["incidents"] == 1
    assert rows["memory-search"]["incidents"] == 0
    assert rows["memory-search"]["top_incidents"] == []
    assert [r["server"] for r in payload["friction_map"]] == sorted(rows)


def test_top_incidents_capped_at_five_in_rank_order(sweep):
    sweep.ready()
    findings = [plain(finding_id=f"f{n}", incident=f"inc-{n}") for n in range(7)]

    rows = {r["server"]: r for r in sweep_of(sweep, findings)["friction_map"]}

    assert rows["Slack"]["top_incidents"] == [f"inc-{n}" for n in range(5)]
    assert rows["Slack"]["incidents"] == 7


def test_friction_map_markdown_has_sections_and_no_free_text(sweep):
    sweep.ready()
    findings = [
        plain(finding_id="1", incident="link-rot", pattern="inconsistent-linking"),
        finding(
            finding_id="2", incident="ghost-owner", pattern="shadow-work", gap=gap("person", False)
        ),
        plain(finding_id="3", incident="drifty", pattern="work-item-drift"),
        plain(finding_id="4", incident="plain-one", pattern="other"),
    ]
    sweep_of(sweep, findings)

    text = (sweep.run_dir / "friction-map.md").read_text()

    assert text.startswith("# Friction map\n")
    header = ["System", "Classes", "Items", "Incidents"]
    header += ["inconsistent-linking", "work-item-drift", "shadow-work", "other"]
    assert "| " + " | ".join([*header, "Knowledge gaps"]) + " |" in text
    assert "fragmented-context" not in text.split("## Knowledge gaps")[0].split("\n")[2]
    assert "- `ghost-owner`: unresolved (person)" in text
    conventions = text.split("## Missing conventions")[1].split("##")[0]
    assert "`link-rot`: inconsistent-linking" in conventions
    assert "`drifty`: work-item-drift" in conventions
    assert "plain-one" not in conventions
    assert "## Outliers\n\n- none" in text
    assert "0 judge runs not imported" in text
    assert "0 findings without a matching second run" in text
    assert "People ask the same onboarding question" not in text
    assert "docs/onboarding" not in text


def test_friction_map_markdown_empty_sections_say_none(sweep):
    sweep.ready()
    import_runs(sweep, [])
    sweep.tally()

    text = (sweep.run_dir / "friction-map.md").read_text()

    assert text.count("- none") == 3
    assert text.endswith("\n")


def test_friction_map_markdown_counts_incomplete_and_single_reader(sweep):
    sweep.ready()
    other = {("friction", 2): [plain(finding_id="x", incident="solo")]}
    import_runs(sweep, [finding()], overrides=other, skip={("knowledge-gap", 2)})
    sweep.tally()

    text = (sweep.run_dir / "friction-map.md").read_text()

    assert "1 judge runs not imported" in text
    assert "3 findings without a matching second run" in text


# ------------------------------------------------------------------ outliers and metrics


def metric_items(count=10):
    items = []
    for n in range(1, count + 1):
        metrics = {"review_rounds": n, "linked_issue": n != 2, "stacked": False}
        items.append(make_item(f"pr-{n}", "code_review", metrics=metrics))
    return items + [make_item("chat-1")]


def outlier_sweep(sweep, items):
    prepare(sweep, items, None, "--batch-size", "100")
    return sweep_of(sweep, [plain()])


def test_outliers_use_the_index_threshold_and_strictly_greater(sweep):
    payload = outlier_sweep(sweep, metric_items())

    entry = payload["outliers"]["metrics"]["review_rounds"]
    index = json.loads(sweep.index_path.read_text())
    assert entry["threshold"] == index["metric_thresholds"]["review_rounds"]["threshold"] == 9
    assert entry["items"] == [{"id": "pr-10", "server": "github", "value": 10}]


def test_outliers_sorted_by_value_desc_then_id(sweep):
    items = metric_items(17)
    items.append(make_item("pr-a", "code_review", metrics={"review_rounds": 50}))
    items.append(make_item("pr-b", "code_review", metrics={"review_rounds": 50}))
    items.append(make_item("pr-c", "code_review", metrics={"review_rounds": 40}))
    payload = outlier_sweep(sweep, items)

    entry = payload["outliers"]["metrics"]["review_rounds"]
    assert [i["id"] for i in entry["items"]] == ["pr-a", "pr-b"]
    assert entry["threshold"] == 40


def test_fewer_than_five_items_go_to_not_computed(sweep):
    items = [
        make_item(f"pr-{n}", "code_review", metrics={"commits": n, "idle_days": n})
        for n in range(1, 5)
    ]
    items += [make_item(f"pr-x{n}", "code_review", metrics={"idle_days": n}) for n in range(1, 3)]
    payload = outlier_sweep(sweep, items + [make_item("chat-1")])

    assert payload["outliers_not_computed"] == {"commits": 4}
    assert sorted(payload["outliers"]["metrics"]) == ["idle_days"]


def test_missing_lists_items_where_expected_boolean_is_false(sweep):
    payload = outlier_sweep(sweep, metric_items())

    assert payload["outliers"]["missing"] == {"linked_issue": ["pr-2"]}


def test_stacked_false_is_not_a_missing_signal(sweep):
    payload = outlier_sweep(sweep, metric_items())

    assert "stacked" not in payload["outliers"]["missing"]


def test_no_metrics_means_empty_outliers(sweep):
    sweep.ready()

    payload = sweep_of(sweep, [finding()])

    assert payload["outliers"] == {"metrics": {}, "missing": {}}
    assert payload["outliers_not_computed"] == {}


def test_friction_map_lists_outlier_items_per_system(sweep):
    payload = outlier_sweep(sweep, metric_items())

    rows = {r["server"]: r for r in payload["friction_map"]}
    assert rows["github"]["outlier_items"] == ["pr-10", "pr-2"]
    assert rows["Slack"]["outlier_items"] == []


def test_outliers_section_has_one_line_per_key_sorted(sweep):
    items = metric_items()
    items += [make_item(f"pr-y{n}", "code_review", metrics={"commits": n}) for n in range(1, 4)]
    outlier_sweep(sweep, items)

    text = (sweep.run_dir / "friction-map.md").read_text()

    section = text.split("## Outliers")[1].split("## Incomplete")[0]
    assert [line for line in section.splitlines() if line] == [
        "- `commits`: not computed (3 items)",
        "- `linked_issue`: 1 missing",
        "- `review_rounds`: threshold 9, 1 above",
    ]


def test_no_metric_values_leak_into_seeds_or_ids_in_markdown(sweep):
    outlier_sweep(sweep, metric_items())

    text = (sweep.run_dir / "friction-map.md").read_text()

    assert "pr-10" not in text
