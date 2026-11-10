"""CLI-level Factory Droid collection for skill-doctor (issue 7188).

Fixtures are synthetic. They run the collector in a subprocess against both
plugin trees.
"""

import json

import pytest
from session_test_helpers import run_collector, write_jsonl
from test_droid_sessions import _working_session

TREES = ["claude", "copilot-cli"]


def _factory_home(tmp_path):
    home = tmp_path / "factory-home"
    repo = tmp_path / "repo"
    other = tmp_path / "other"
    repo.mkdir()
    other.mkdir()
    write_jsonl(
        home / "sessions" / "-repo" / "in-scope.jsonl",
        _working_session(str(repo), "in-scope"),
    )
    write_jsonl(
        home / "sessions" / "-other" / "out-of-scope.jsonl",
        _working_session(str(other), "out-of-scope"),
    )
    return home, repo


@pytest.mark.parametrize("root", TREES)
def test_cli_collects_only_sessions_inside_the_repo(tmp_path, root):
    home, repo = _factory_home(tmp_path)

    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--harness",
        "droid",
        "--factory-home",
        str(home),
        "--repo",
        str(repo),
        root=root,
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text())
    assert inventory["sources"]["droid"]["records_in_window"] == 2
    assert [s["meta"]["id"] for s in inventory["sessions"]] == ["in-scope"]
    assert inventory["sessions"][0]["harness"] == "droid"
    assert inventory["droid_home"] == str(home)


@pytest.mark.parametrize("root", TREES)
def test_cli_all_conversations_collects_every_droid_session(tmp_path, root):
    home, _repo = _factory_home(tmp_path)

    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--harness",
        "droid",
        "--factory-home",
        str(home),
        "--all-conversations",
        root=root,
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text())
    assert {s["meta"]["id"] for s in inventory["sessions"]} == {"in-scope", "out-of-scope"}


@pytest.mark.parametrize("root", TREES)
def test_cli_explicit_droid_harness_fails_when_home_is_missing(tmp_path, root):
    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--harness",
        "droid",
        "--factory-home",
        str(tmp_path / "absent"),
        root=root,
    )

    assert result.returncode == 1
    assert "Droid not found at" in result.stderr


@pytest.mark.parametrize("root", TREES)
def test_cli_auto_includes_droid_when_default_sessions_directory_exists(tmp_path, root):
    default_home = tmp_path / "isolated-home" / ".factory"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_jsonl(
        default_home / "sessions" / "-repo" / "auto.jsonl", _working_session(str(repo), "auto")
    )

    result = run_collector(tmp_path, tmp_path / "no-copilot", "--repo", str(repo), root=root)

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text())
    assert "droid" in inventory["sources"]
    assert [s["meta"]["id"] for s in inventory["sessions"]] == ["auto"]


@pytest.mark.parametrize("root", TREES)
def test_cli_auto_skips_droid_when_no_factory_home(tmp_path, root):
    other = tmp_path / "claude-home" / "projects" / "-repo"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_jsonl(
        other / "claude.jsonl",
        [
            {
                "type": "assistant",
                "sessionId": "claude-1",
                "cwd": str(repo),
                "timestamp": "2026-11-01T10:00:00Z",
                "uuid": "u1",
                "message": {
                    "role": "assistant",
                    "id": "a1",
                    "content": [{"type": "tool_use", "name": "Read", "input": {}}],
                },
            }
        ],
    )

    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--repo",
        str(repo),
        "--claude-home",
        str(tmp_path / "claude-home"),
        root=root,
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text())
    assert "droid" not in inventory["sources"]
    assert inventory["droid_home"] is None


@pytest.mark.parametrize("root", TREES)
def test_cli_discovers_droid_skills_from_the_factory_home(tmp_path, root):
    home, repo = _factory_home(tmp_path)
    skill = home / "skills" / "droid-only" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: droid-only\ndescription: Droid skill\n---\n")
    project_skill = repo / ".factory" / "skills" / "repo-droid" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("---\nname: repo-droid\ndescription: Repo Droid skill\n---\n")

    result = run_collector(
        tmp_path,
        tmp_path / "no-copilot",
        "--harness",
        "droid",
        "--factory-home",
        str(home),
        "--repo",
        str(repo),
        "--include-global-skills",
        root=root,
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text())
    assert {skill["name"] for skill in inventory["skills"]} == {"droid-only", "repo-droid"}


def test_cli_factory_home_flag_without_value_exits_2(tmp_path):
    result = run_collector(
        tmp_path, tmp_path / "no-copilot", "--harness", "droid", "--factory-home"
    )

    assert result.returncode == 2
    assert "expected one argument" in result.stderr
