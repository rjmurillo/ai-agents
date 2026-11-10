"""Preserve omitted-middle skill invocations until project discovery finishes."""

import json
import subprocess
from urllib.parse import quote

import pytest
from session_test_helpers import run_collector, write_jsonl


@pytest.mark.parametrize("harness", ["pi", "grok"])
def test_all_conversations_recovers_project_skill_outside_retained_transcript(tmp_path, harness):
    repo, home = tmp_path / "project", tmp_path / harness
    skill = repo / ".claude" / "skills" / "alpha" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\ndescription: Synthetic alpha\n---\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    records = []
    if harness == "pi":
        path = home / "sessions" / "project" / "journal.jsonl"
        records.append({"type": "session", "id": "long", "cwd": str(repo)})
    else:
        path = home / "sessions" / quote(str(repo), safe="") / "long" / "chat_history.jsonl"
    for index in range(400):
        name = "alpha" if index == 200 else "not-installed"
        arguments = {"path": str(skill.parent.parent / name / "SKILL.md")}
        if harness == "pi":
            content = [{"type": "text", "text": f"entry {index}"}]
            if index in (200, 210):
                content.append({"type": "toolCall", "name": "read", "arguments": arguments})
            records.append(
                {"type": "message", "message": {"role": "assistant", "content": content}}
            )
        else:
            message = {"type": "assistant", "content": f"entry {index}"}
            if index in (200, 210):
                message["tool_calls"] = [{"name": "read", "arguments": json.dumps(arguments)}]
            records.append(message)
    write_jsonl(path, records)
    result = run_collector(
        tmp_path,
        tmp_path / "unused",
        "--harness",
        harness,
        f"--{harness}-home",
        str(home),
        "--all-conversations",
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["skill_usage"] == {"alpha": 1}
    assert inventory["sessions"][0]["skills_used"] == ["alpha"]
    transcript = (tmp_path / "report" / "transcripts" / f"{harness}-long.md").read_text(
        encoding="utf-8"
    )
    assert "entries omitted" in transcript
    assert "tool:read" not in transcript
