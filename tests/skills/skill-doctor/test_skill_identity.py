"""Usage detection keeps every installed name and never invents historical identity.

Covers issue 7185 (same-name definitions with different bytes) and issue 7190
(namespace-qualified invocations such as `project-toolkit:skill-doctor`).
All fixtures are synthetic.
"""

import json

import pytest
import session_common
from session_common import (
    SessionState,
    collect_diagnostics,
    collection_issue_counts,
    detect_skills_from_entries,
)
from session_discovery import discover_skills
from session_json import parse_claude_session
from session_test_helpers import run_collector, write_jsonl

ROOTS = ["claude", "copilot-cli"]
SPACED = '{ "skill" :  "%s" }'
COMPACT = '{"skill":"%s"}'


def recognized(argument, installed=frozenset({"skill-doctor"}), template=None):
    state = SessionState()
    text = template % argument if template else json.dumps({"skill": argument})
    state.tool("skill", text)
    entries = state.entries.finish()
    return (state.skills | detect_skills_from_entries(entries, installed)) & set(installed)


@pytest.mark.parametrize("template", [None, SPACED, COMPACT])
@pytest.mark.parametrize("argument", ["skill-doctor", "project-toolkit:skill-doctor"])
def test_bare_and_qualified_invocations_retain_the_installed_name(argument, template):
    assert recognized(argument, template=template) == {"skill-doctor"}


def test_issue_7190_synthetic_reproduction():
    assert recognized("skill-doctor") == {"skill-doctor"}
    assert recognized("project-toolkit:skill-doctor") == {"skill-doctor"}


@pytest.mark.parametrize(
    "argument",
    [
        "project-toolkit:other-skill",
        "project-toolkit:skill-doctor-extra",
        "a:b:skill-doctor",
        "skill-doctor:",
        ":skill-doctor",
        "project/toolkit:skill-doctor",
    ],
)
def test_qualified_names_that_do_not_resolve_to_an_installed_name_are_ignored(argument):
    assert recognized(argument) == set()


def test_logical_names_tolerate_non_string_values():
    assert session_common.logical_skill_name(7) == 7
    assert session_common.logical_skill_names(["ns:x", 7, None, ("a",), "y"]) == {"x", "y"}


@pytest.mark.parametrize("key", ["name", "label"])
def test_generic_keys_do_not_turn_a_label_into_skill_usage(key):
    state = SessionState()
    state.tool("view", json.dumps({key: "area:review"}))
    entries = state.entries.finish()
    installed = {"review"}
    assert (state.skills | detect_skills_from_entries(entries, installed)) & installed == set()


def test_bundled_skill_id_accepts_a_qualified_name():
    assert recognized("project-toolkit:skill-doctor", template='{"bundled_skill_id": "%s"}') == {
        "skill-doctor"
    }


def _claude_journal(path, skill):
    write_jsonl(
        path,
        [
            {
                "type": "assistant",
                "sessionId": "s1",
                "cwd": "/synthetic",
                "message": {
                    "id": "m1",
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": skill}}],
                },
            }
        ],
    )
    return parse_claude_session(path, (), False)


def test_claude_skill_tool_records_the_logical_name_for_a_qualified_call(tmp_path):
    parsed = _claude_journal(tmp_path / "s1.jsonl", "project-toolkit:skill-doctor")
    assert "skill-doctor" in parsed[3]


@pytest.mark.parametrize("skill", [["a"], 5, {"b": 1}, "", None])
def test_claude_skill_tool_ignores_a_non_string_skill_argument(tmp_path, skill):
    parsed = _claude_journal(tmp_path / "s1.jsonl", skill)
    assert parsed[3] == []


def test_usage_without_transcript_evidence_is_flagged_not_dropped():
    padding = [("assistant", "filler")] * 200
    session = {"skills_used": ["x"], "_entries": padding}
    session_common.resolve_session_usage([session], {"x": _installed("x")})
    assert session["skills_used"] == ["x"]
    assert session["skill_attribution"] == {
        "x": {"evidence": "unrecorded", "unresolved_because": ["evidence_not_in_transcript"]}
    }


def _installed(name):
    return {"name": name, "path": f"/{name}", "sha256": "0", "definitions": [{"sha256": "0"}]}


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([("tool:skill", json.dumps({"skill": "x"}))], "bare_name"),
        ([("tool:skill", json.dumps({"skill": "ns:x"}))], "qualified_name"),
        ([("tool:view", "/repo/.claude/skills/x/SKILL.md")], "path"),
        ([("tool:view", "C:\\repo\\.claude\\skills\\x\\SKILL.md")], "path"),
        (
            [
                ("tool:skill", json.dumps({"skill": "ns:x"})),
                ("tool:skill", json.dumps({"skill": "x"})),
            ],
            "bare_name",
        ),
        ([("user", "please use x")], "unrecorded"),
        ([("tool:skill", json.dumps({"skill": "xy"}))], "unrecorded"),
    ],
)
def test_skill_evidence_reports_the_strongest_signal(entries, expected):
    assert session_common.skill_evidence(entries, "x") == expected


def _skill(root, name, text):
    path = root / ".claude" / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def _journal(home, repo, arguments, session="one"):
    write_jsonl(
        home / "session-state" / session / "events.jsonl",
        [
            {"type": "session.start", "data": {"context": {"cwd": str(repo)}}},
            {"type": "assistant.message", "data": {"content": "Inspect"}},
            {
                "type": "tool.execution_start",
                "data": {"toolName": "skill", "arguments": arguments},
            },
        ],
    )


def _collect(tmp_path, root, *repos):
    args = ["--harness", "copilot"]
    for repo in repos:
        args += ["--repo", str(repo)]
    result = run_collector(tmp_path, tmp_path / "copilot", *args, root=root)
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    return inventory, result


@pytest.mark.parametrize("root", ROOTS)
def test_collector_records_a_qualified_call_in_skills_used(tmp_path, root):
    repo = tmp_path / "repo"
    _skill(repo, "skill-doctor", "Same")
    _journal(tmp_path / "copilot", repo, {"skill": "project-toolkit:skill-doctor"})
    inventory, _ = _collect(tmp_path, root, repo)
    session = inventory["sessions"][0]
    assert session["skills_used"] == ["skill-doctor"]
    assert inventory["skill_usage"]["skill-doctor"] == 1
    assert inventory["stats"]["skills_used"] == 1
    assert session["skill_attribution"] == {
        "skill-doctor": {
            "evidence": "qualified_name",
            "unresolved_because": ["namespace_unverified"],
        }
    }


@pytest.mark.parametrize("root", ROOTS)
def test_collector_leaves_a_bare_call_without_attribution_notes(tmp_path, root):
    repo = tmp_path / "repo"
    _skill(repo, "skill-doctor", "Same")
    _journal(tmp_path / "copilot", repo, {"skill": "skill-doctor"})
    inventory, _ = _collect(tmp_path, root, repo)
    session = inventory["sessions"][0]
    assert session["skills_used"] == ["skill-doctor"]
    assert "skill_attribution" not in session
    assert inventory["skill_variants"] == {}
    assert inventory["stats"]["ambiguous_skills"] == 0


@pytest.mark.parametrize("root", ROOTS)
def test_collector_ignores_a_qualified_call_to_a_missing_skill(tmp_path, root):
    repo = tmp_path / "repo"
    _skill(repo, "skill-doctor", "Same")
    _journal(tmp_path / "copilot", repo, {"skill": "project-toolkit:not-installed"})
    inventory, _ = _collect(tmp_path, root, repo)
    assert inventory["sessions"][0]["skills_used"] == []


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_definitions_keep_usage_and_leave_history_unresolved(tmp_path, root, reverse):
    first, second = tmp_path / "first", tmp_path / "second"
    first_md = _skill(first, "x", "first bytes")
    second_md = _skill(second, "x", "second bytes")
    _journal(tmp_path / "copilot", first, {"skill": "x"})
    _journal(tmp_path / "copilot", second, {"skill": "x"}, session="two")
    order = (second, first) if reverse else (first, second)
    inventory, result = _collect(tmp_path, root, *order)
    chosen = second_md if reverse else first_md
    assert [s["skills_used"] for s in inventory["sessions"]] == [["x"], ["x"]]
    assert inventory["skill_usage"]["x"] == 2
    assert inventory["stats"]["skills_used"] == 1
    assert inventory["collection_status"] == "complete"
    assert inventory["collection_issues"] == {}
    assert "partial collection" not in result.stderr
    assert inventory["stats"]["ambiguous_skills"] == 1
    variant = inventory["skill_variants"]["x"]
    assert variant["historical_attribution"] == "unresolved"
    assert variant["edit_target"]["path"] == str(chosen)
    assert next(s for s in inventory["skills"] if s["name"] == "x")["path"] == str(chosen)
    assert {path for d in variant["definitions"] for path in d["paths"]} == {
        str(first_md),
        str(second_md),
    }
    assert len({d["sha256"] for d in variant["definitions"]}) == 2
    assert variant["edit_target"]["sha256"] in {d["sha256"] for d in variant["definitions"]}
    for session in inventory["sessions"]:
        note = session["skill_attribution"]["x"]
        assert note == {"evidence": "bare_name", "unresolved_because": ["conflicting_definitions"]}
        assert "sha256" not in json.dumps(session["skill_attribution"])


@pytest.mark.parametrize("root", ROOTS)
def test_conflicting_definitions_with_a_foreign_namespace_record_both_reasons(tmp_path, root):
    first, second = tmp_path / "first", tmp_path / "second"
    _skill(first, "x", "first bytes")
    _skill(second, "x", "second bytes")
    _journal(tmp_path / "copilot", first, {"skill": "other-plugin:x"})
    inventory, _ = _collect(tmp_path, root, first, second)
    session = inventory["sessions"][0]
    assert session["skills_used"] == ["x"]
    assert session["skill_attribution"]["x"] == {
        "evidence": "qualified_name",
        "unresolved_because": ["conflicting_definitions", "namespace_unverified"],
    }


def test_discovery_keeps_first_seen_copy_and_every_content_distinct_definition(tmp_path):
    repos = [tmp_path / name for name in ("first", "second", "third")]
    paths = [
        _skill(repo, "shared", "Other" if index == 1 else "Same")
        for index, repo in enumerate(repos)
    ]
    with collect_diagnostics():
        skills = discover_skills(repos, tmp_path / "codex", [], False)
        assert collection_issue_counts() == {}
    shared = skills["shared"]
    assert shared["path"] == str(paths[0])
    definitions = {d["sha256"]: d["paths"] for d in shared["definitions"]}
    assert len(definitions) == 2
    assert shared["definitions"][0]["sha256"] == shared["sha256"]
    assert definitions[shared["sha256"]] == [str(paths[0]), str(paths[2])]
    assert [str(paths[1])] in definitions.values()


def test_discovery_gives_byte_identical_copies_one_fingerprint_with_all_aliases(tmp_path):
    repos = [tmp_path / name for name in ("first", "second")]
    paths = [_skill(repo, "shared", "Same") for repo in repos]
    skills = discover_skills(repos, tmp_path / "codex", [], False)
    (definition,) = skills["shared"]["definitions"]
    assert definition["paths"] == [str(path) for path in paths]
    assert definition["sha256"] == skills["shared"]["sha256"]


def test_discovery_lists_a_path_reached_through_two_roots_once(tmp_path):
    repo = tmp_path / "repo"
    path = _skill(repo, "shared", "Same")
    skills = discover_skills([repo], tmp_path / "codex", [repo / ".claude" / "skills"], False)
    assert skills["shared"]["definitions"][0]["paths"] == [str(path)]


def test_manifest_catalog_keeps_distinct_contents_and_collapses_identical_copies(tmp_path):
    import audit_manifest as am

    repos = [tmp_path / name for name in ("first", "second", "third")]
    for index, repo in enumerate(repos):
        _skill(repo, "shared", "Other" if index == 1 else "Same")
    skills = discover_skills(repos, tmp_path / "codex", [], False)

    catalog = am._catalog(sorted(skills.values(), key=lambda s: s["name"]), repos)

    assert len(catalog) == 2
    assert sorted(len(entry["aliases"]) for entry in catalog) == [0, 1]
