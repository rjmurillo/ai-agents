# taste-lint: ignore file-size, one suite owns the shared sweep fixtures for this subcommand.
"""bootstrap_sweep plan: classification, access, overrides, discovery, run-dir rules."""

from __future__ import annotations

import json
import shutil
from typing import Any

import bootstrap_sweep
import pytest
from bootstrap_helpers import symlink_or_skip
from sweep_helpers import INVENTORY, TODAY, dump


def inv(servers: list[Any] | None = None, skills: list[Any] | None = None, **extra: Any):
    return {"schema_version": 1, "servers": servers or [], "skills": skills or [], **extra}


def plan_of(sweep, inventory, *extra):
    code, payload = sweep.plan(inventory, *extra)
    return code, payload


# ------------------------------------------------------------------ AC1 classification


def test_plan_classifies_servers_and_skills_by_keyword(sweep):
    code, payload = sweep.plan()

    assert code == 0
    classes = payload["classes"]
    assert classes["chat"]["servers"] == ["Slack"]
    assert classes["code_review"]["servers"] == ["github"]
    assert classes["work_tracking"]["servers"] == ["github"]
    assert classes["memory"]["skills"] == ["memory-search"]
    assert classes["agent_sessions"]["skills"] == ["skill-doctor"]
    assert {s["class_source"] for s in payload["servers"]} == {"keyword"}
    assert payload["examined"]["servers"] == 2
    assert sweep.plan_path.is_file()


def test_plan_id_is_digest_of_body(sweep):
    _, payload = sweep.plan()

    body = {k: v for k, v in sweep.load_plan().items() if k != "plan_id"}
    assert payload["plan_id"] == bootstrap_sweep.digest(body)


def test_plan_is_deterministic_across_runs(sweep, tmp_path, repo, skill_dir, capsys):
    sweep.plan()
    other = type(sweep)(tmp_path / "second", repo, capsys)
    other.run_dir = tmp_path / "second" / "run"
    other.plan_path = other.run_dir / "plan.json"
    other.plan()

    assert other.plan_path.read_bytes() == sweep.plan_path.read_bytes()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("GitHub", {"code_review", "work_tracking"}),
        ("GoogleDrive", {"documents"}),
        ("Google_Calendar", {"meetings"}),
        ("azure-devops", {"code_review", "work_tracking"}),
        ("WorkIQ", {"work_intelligence"}),
        ("claude-mem", {"memory"}),
        ("Gmail", {"email"}),
        ("m365-copilot", {"email", "work_intelligence"}),
        ("circleci", {"build_ops"}),
        ("mattermost", {"chat"}),
    ],
)
def test_keyword_tables(name, expected):
    assert set(bootstrap_sweep.keyword_classes(name)) == expected


def test_keyword_ci_is_whole_token_not_substring():
    assert bootstrap_sweep.keyword_classes("social-ciphers") == []


def test_agent_sessions_keyword_applies_to_skills_only():
    assert bootstrap_sweep.keyword_classes("session-viewer", skill=True) == ["agent_sessions"]
    assert bootstrap_sweep.keyword_classes("session-viewer", skill=False) == []


# ------------------------------------------------------------------ AC2 tool access


def test_write_verb_tool_is_excluded_as_write(sweep):
    _, payload = sweep.plan()

    excluded = {(e["tool"], e["reason"]) for e in payload["excluded_tools"]}
    assert ("slack_send_message", "write") in excluded
    assert ("issue_write", "write") in excluded


def test_tool_without_known_verb_is_excluded_as_unknown(sweep):
    _, payload = sweep.plan()

    assert {"server": "github", "tool": "mystery_op", "reason": "unknown"} in payload[
        "excluded_tools"
    ]


def test_read_tools_carry_verb_access_source(sweep):
    _, payload = sweep.plan()

    tools = {t["tool"]: t["access_source"] for t in payload["classes"]["chat"]["read_tools"]}
    assert tools == {"slack_read_channel": "verb", "slack_search_public": "verb"}


@pytest.mark.parametrize(
    ("tool", "verdict"),
    [
        ("getMe", "read"),
        ("pull_request_review_write", "write"),
        ("export_report", "read"),
        ("export_and_delete", "write"),
        ("reflect", "unknown"),
        ("datasets", "unknown"),
    ],
)
def test_tool_access_verbs(tool, verdict):
    entry = {"name": tool, "description": "", "access": None}

    assert bootstrap_sweep.tool_access(entry)[0] == verdict


def test_declared_read_needs_description(sweep):
    servers = [
        {
            "name": "Notion",
            "tools": [
                {"name": "reflect", "access": "read", "description": "Summarizes a page"},
                {"name": "ponder", "access": "read"},
                {"name": "muse", "access": "read", "description": "   "},
            ],
        }
    ]
    _, payload = sweep.plan(inv(servers))

    reads = payload["classes"]["documents"]["read_tools"]
    assert reads == [{"server": "Notion", "tool": "reflect", "access_source": "declared"}]
    assert payload["declared_read_tools"] == [
        {"server": "Notion", "tool": "reflect", "description": "Summarizes a page"}
    ]
    reasons = {e["tool"]: e["reason"] for e in payload["excluded_tools"]}
    assert reasons == {"ponder": "unknown", "muse": "unknown"}


def test_declared_read_cannot_override_write_verb(sweep):
    tool = {"name": "delete_page", "access": "read", "description": "Looks harmless"}
    _, payload = sweep.plan(inv([{"name": "Notion", "tools": [tool]}]))

    assert payload["classes"]["documents"]["read_tools"] == []
    assert payload["excluded_tools"][0]["reason"] == "write"
    assert payload["declared_read_tools"] == []


def test_access_other_than_read_exits_2(sweep):
    tool = {"name": "reflect", "access": "write", "description": "x"}
    code, payload = sweep.plan(inv([{"name": "Notion", "tools": [tool]}]))

    assert code == 2
    assert payload["error"] == "config"


# ------------------------------------------------------------------ AC3 class resolution


def test_override_beats_declared_beats_keyword(sweep):
    servers = [
        {"name": "Slack", "tools": ["list_x"], "classes": ["email"]},
        {"name": "Jira", "tools": ["list_x"], "classes": ["chat"]},
        {"name": "Notion", "tools": ["list_x"]},
    ]
    _, payload = sweep.plan(inv(servers), "--class-override", "Jira=meetings")

    by_name = {s["name"]: s for s in payload["servers"]}
    assert by_name["Jira"] == {"name": "Jira", "classes": ["meetings"], "class_source": "override"}
    assert by_name["Slack"]["classes"] == ["email"]
    assert by_name["Slack"]["class_source"] == "declared"
    assert by_name["Notion"]["class_source"] == "keyword"


def test_override_can_name_several_classes_for_one_server(sweep):
    _, payload = sweep.plan(
        inv([{"name": "Foo", "tools": ["get_x"]}]),
        "--class-override",
        "Foo=chat",
        "--class-override",
        "Foo=email",
    )

    assert payload["servers"][0]["classes"] == ["chat", "email"]


@pytest.mark.parametrize(
    "override", ["Slack=nonsense", "Slack", "=chat", "Ghost=chat"], ids=lambda o: o or "empty"
)
def test_bad_override_exits_2_and_writes_nothing(sweep, override):
    code, _ = sweep.plan(INVENTORY, "--class-override", override)

    assert code == 2
    assert not sweep.run_dir.exists()


def test_invalid_declared_class_exits_2(sweep):
    code, _ = sweep.plan(inv([{"name": "Foo", "classes": ["bogus"]}]))

    assert code == 2


def test_empty_declared_classes_exits_2(sweep):
    code, _ = sweep.plan(inv([{"name": "Foo", "classes": []}]))

    assert code == 2


def test_unknown_server_lands_in_other_and_needs_classification(sweep):
    servers = [{"name": "Twilio", "tools": ["twilio__search"]}]
    _, payload = sweep.plan(inv(servers, ["frobnicate"]))

    assert payload["classes"]["other"]["servers"] == ["Twilio"]
    assert payload["classes"]["other"]["skills"] == ["frobnicate"]
    assert payload["classes"]["other"]["read_tools"][0]["tool"] == "twilio__search"
    assert payload["needs_classification"] == [
        {"kind": "server", "name": "Twilio"},
        {"kind": "skill", "name": "frobnicate"},
    ]
    assert payload["servers"][0]["class_source"] == "default"


def test_every_skill_appears_in_the_plan(sweep):
    skills = ["memory-search", {"name": "pr-review", "classes": ["code_review"]}, "frobnicate"]
    _, payload = sweep.plan(inv(skills=skills))

    assert sorted(s["name"] for s in payload["skills"]) == [
        "frobnicate",
        "memory-search",
        "pr-review",
    ]
    assert payload["classes"]["code_review"]["skills"] == ["pr-review"]


def test_skill_doctor_and_session_skills_map_to_agent_sessions(sweep):
    _, payload = sweep.plan(inv(skills=["skill-doctor", "my-session-tool"]))

    assert payload["classes"]["agent_sessions"]["skills"] == ["my-session-tool", "skill-doctor"]


# ------------------------------------------------------------------ connectivity


def test_not_connected_lists_empty_classes_except_agent_sessions_and_other(sweep):
    _, payload = sweep.plan(inv([{"name": "Slack", "tools": ["get_x"]}]))

    assert "chat" not in payload["not_connected"]
    assert "email" in payload["not_connected"]
    assert "agent_sessions" not in payload["not_connected"]
    assert "other" not in payload["not_connected"]


def test_connected_without_read_for_server_with_only_write_tools(sweep):
    _, payload = sweep.plan(inv([{"name": "Slack", "tools": ["slack_send_message"]}]))

    assert payload["connected_without_read"] == ["chat"]


def test_resources_count_as_read_routes(sweep):
    servers = [
        {
            "name": "Notion",
            "tools": [],
            "resources": ["notion://a", {"uri": "notion://b", "name": "B"}],
        }
    ]
    _, payload = sweep.plan(inv(servers))

    assert payload["connected_without_read"] == []
    assert payload["classes"]["documents"]["resources"] == [
        {"server": "Notion", "uri": "notion://a"},
        {"server": "Notion", "uri": "notion://b", "name": "B"},
    ]


def test_prompts_are_informational_not_read_routes(sweep):
    servers = [{"name": "Slack", "tools": [], "prompts": ["standup", {"name": "retro"}]}]
    _, payload = sweep.plan(inv(servers))

    assert payload["prompts"] == [
        {"server": "Slack", "name": "standup"},
        {"server": "Slack", "name": "retro"},
    ]
    assert payload["connected_without_read"] == ["chat"]


def test_discovery_recorded_verbatim(sweep):
    discovery = {"tools_list": "ok", "resources_list": "unsupported", "skills_list": "failed"}
    _, payload = sweep.plan(inv(discovery=discovery))

    assert payload["discovery"] == discovery


def test_invalid_discovery_state_exits_2(sweep):
    code, _ = sweep.plan(inv(discovery={"tools_list": "maybe"}))

    assert code == 2


def test_discovery_defaults_to_empty(sweep):
    _, payload = sweep.plan()

    assert payload["discovery"] == {}


# ------------------------------------------------------------------ seeds, judges, window


def test_query_seeds_use_repo_name_hotspots_and_signals(sweep, tmp_path):
    paths = [{"path": f"src/f{i}.py"} for i in range(15)]
    todo = [{"path": "src/f0.py"}] + [{"path": f"docs/d{i}.md"} for i in range(10)]
    candidates = dump(tmp_path / "cand.json", {"churn": paths, "todo_hotspots": todo})
    _, payload = sweep.plan(INVENTORY, "--candidates", str(candidates))

    seeds = payload["query_seeds"]
    assert seeds["repo_terms"] == ["repo"]
    assert len(seeds["hotspots"]) == 20
    assert seeds["hotspots"][:2] == ["src/f0.py", "src/f1.py"]
    assert len(set(seeds["hotspots"])) == 20
    assert "who owns" in seeds["signals"]["chat"]


def test_malformed_candidates_exits_2(sweep, tmp_path):
    bad = dump(tmp_path / "cand.json", {"churn": "nope"})
    code, _ = sweep.plan(INVENTORY, "--candidates", str(bad))

    assert code == 2


def test_judges_list_sorted_digests(sweep, skill_dir):
    _, payload = sweep.plan()

    names = [j["name"] for j in payload["judges"]]
    assert names == ["friction", "knowledge-gap"]
    assert all(len(j["sha256"]) == 64 for j in payload["judges"])


def test_judges_empty_when_directory_missing(sweep, skill_dir):
    shutil.rmtree(skill_dir / "judges")
    _, payload = sweep.plan()

    assert payload["judges"] == []


def test_window_from_today_and_days(sweep):
    _, payload = sweep.plan(INVENTORY, "--window-days", "10")

    assert payload["window"] == {"start": "2026-11-01", "end": TODAY}
    assert payload["judge_runs"] == 2


def test_window_defaults_to_180_days(sweep):
    _, payload = sweep.plan()

    assert payload["window"]["start"] == "2026-05-15"


@pytest.mark.parametrize("today", ["2026-13-01", "11/11/2026", "2026-11-1"])
def test_bad_today_exits_2(sweep, today):
    tools = dump(sweep.tmp / "t.json", INVENTORY)
    code, _ = sweep.cli(
        "plan",
        "--tools",
        str(tools),
        "--repo",
        str(sweep.repo),
        "--run-dir",
        str(sweep.run_dir),
        "--today",
        today,
    )

    assert code == 2


def test_default_today_is_a_real_utc_date(sweep):
    tools = dump(sweep.tmp / "t.json", INVENTORY)
    code, payload = sweep.cli(
        "plan", "--tools", str(tools), "--repo", str(sweep.repo), "--run-dir", str(sweep.run_dir)
    )

    assert code == 0
    assert len(payload["window"]["end"]) == 10


@pytest.mark.parametrize("flag", [("--judge-runs", "1"), ("--window-days", "0")])
def test_bad_numeric_flags_exit_2(sweep, flag):
    code, _ = sweep.plan(INVENTORY, *flag)

    assert code == 2


def test_judge_runs_flag_recorded(sweep):
    _, payload = sweep.plan(INVENTORY, "--judge-runs", "3")

    assert payload["judge_runs"] == 3


# ------------------------------------------------------------------ run dir rules


def test_run_dir_inside_repo_exits_2_and_writes_nothing(sweep, repo):
    tools = dump(sweep.tmp / "t.json", INVENTORY)
    inside = repo / "sweep-run"
    code, payload = sweep.cli(
        "plan",
        "--tools",
        str(tools),
        "--repo",
        str(repo),
        "--run-dir",
        str(inside),
        "--today",
        TODAY,
    )

    assert code == 2
    assert payload["error"] == "config"
    assert not inside.exists()


def test_run_dir_symlink_into_repo_exits_2(sweep, repo):
    link = sweep.tmp / "link"
    symlink_or_skip(link, repo)
    tools = dump(sweep.tmp / "t.json", INVENTORY)
    code, _ = sweep.cli(
        "plan",
        "--tools",
        str(tools),
        "--repo",
        str(repo),
        "--run-dir",
        str(link / "sub"),
        "--today",
        TODAY,
    )

    assert code == 2
    assert not (repo / "sub").exists()


def test_run_dir_is_never_reused(sweep):
    assert sweep.plan()[0] == 0
    before = sweep.plan_path.read_bytes()

    code, payload = sweep.plan()

    assert code == 2
    assert "not empty" in payload["message"]
    assert sweep.plan_path.read_bytes() == before


def test_existing_empty_run_dir_is_accepted(sweep):
    sweep.run_dir.mkdir()

    assert sweep.plan()[0] == 0


def test_not_a_git_repo_exits_2(sweep, tmp_path):
    tools = dump(tmp_path / "t.json", INVENTORY)
    plain = tmp_path / "plain"
    plain.mkdir()
    code, _ = sweep.cli(
        "plan", "--tools", str(tools), "--repo", str(plain), "--run-dir", str(sweep.run_dir)
    )

    assert code == 2


# ------------------------------------------------------------------ malformed inventory


@pytest.mark.parametrize(
    "inventory",
    [
        {"schema_version": 2, "servers": [], "skills": []},
        {"schema_version": 1, "servers": []},
        {"schema_version": 1, "servers": "x", "skills": []},
        inv([{"name": "A"}, {"name": "A"}]),
        inv([{"nope": 1}]),
        inv([{"name": "A", "tools": [{"description": "x"}]}]),
        inv([{"name": "A", "extra": 1}]),
        inv(skills=[{"name": "s", "extra": 1}]),
        inv(skills=[3]),
    ],
)
def test_malformed_inventory_exits_2(sweep, inventory):
    code, payload = sweep.plan(inventory)

    assert code == 2
    assert payload["error"] == "config"
    assert not sweep.run_dir.exists()


def test_duplicate_json_keys_exit_2(sweep, tmp_path):
    tools = tmp_path / "dup.json"
    tools.write_text('{"schema_version": 1, "schema_version": 1, "servers": [], "skills": []}')
    code, _ = sweep.cli(
        "plan", "--tools", str(tools), "--repo", str(sweep.repo), "--run-dir", str(sweep.run_dir)
    )

    assert code == 2


def test_missing_tools_file_exits_2(sweep, tmp_path):
    code, _ = sweep.cli(
        "plan",
        "--tools",
        str(tmp_path / "none.json"),
        "--repo",
        str(sweep.repo),
        "--run-dir",
        str(sweep.run_dir),
    )

    assert code == 2


def test_plan_stdout_matches_plan_file_body(sweep):
    _, payload = sweep.plan()

    written = json.loads(sweep.plan_path.read_text())
    assert {k: payload[k] for k in written} == written


def test_script_runs_under_python3_as_a_program(sweep, tmp_path):
    import subprocess
    import sys

    tools = dump(tmp_path / "t.json", INVENTORY)
    script = bootstrap_sweep.__file__

    proc = subprocess.run(
        [
            sys.executable,
            script,
            "plan",
            "--tools",
            str(tools),
            "--repo",
            str(sweep.repo),
            "--run-dir",
            str(sweep.run_dir),
            "--today",
            TODAY,
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["examined"]["servers"] == 2
