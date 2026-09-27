"""Tests for the user_prompt_transformed_memory hook (Copilot CLI recall).

Copilot CLI drops config-file UserPromptSubmit output (issue #4727). Recall
reaches Copilot through userPromptTransformed, whose documented output field
is ``modifiedTransformedPrompt``.
"""

from __future__ import annotations

import io
import json

import pytest

from memory_enhancement.hooks.user_prompt_transformed_memory import main

SUBMIT = "memory_enhancement.hooks.user_prompt_submit_memory"
CLOUD_VARS = ("COPILOT_AGENT_PROMPT", "GITHUB_COPILOT_API_TOKEN")
BLOCK = "<memory-context>hit</memory-context>"


def _run(monkeypatch, capsys, tmp_path, payload, recall=BLOCK, env=None):
    """Run the hook against a fake repo; return exit code, stdout, stderr, queries."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / ".serena" / "memories").mkdir(parents=True, exist_ok=True)
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    monkeypatch.setattr(f"{SUBMIT}._find_repo_root", lambda start=None: tmp_path)
    for name in CLOUD_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    seen: list[str] = []
    monkeypatch.setattr(
        f"{SUBMIT}._search_and_format", lambda query, *_a: (seen.append(query), recall)[1]
    )
    exit_code = main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err, seen


@pytest.mark.unit
def test_match_emits_one_envelope_appending_block(tmp_path, monkeypatch, capsys):
    payload = {"prompt": "dispatch groups", "transformedPrompt": "<ctx/>dispatch groups"}

    exit_code, out, err, seen = _run(monkeypatch, capsys, tmp_path, payload)

    assert exit_code == 0
    assert err == ""
    assert json.loads(out) == {"modifiedTransformedPrompt": f"<ctx/>dispatch groups\n\n{BLOCK}"}
    assert seen == ["dispatch groups"]


@pytest.mark.unit
def test_query_uses_prompt_not_transformed_content(tmp_path, monkeypatch, capsys):
    payload = {"prompt": "routing table", "transformedPrompt": "attachment noise routing table"}

    _, _, _, seen = _run(monkeypatch, capsys, tmp_path, payload)

    assert seen == ["routing table"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "recall"),
    [
        ({"prompt": "dispatch groups", "transformedPrompt": "dispatch groups"}, ""),
        ({"prompt": "is it the", "transformedPrompt": "is it the"}, BLOCK),
        ({"prompt": "dispatch groups"}, BLOCK),
        ({"prompt": "dispatch groups", "transformedPrompt": ""}, BLOCK),
        ({"prompt": "dispatch groups", "transformedPrompt": "   "}, BLOCK),
        ({"prompt": "dispatch groups", "transformedPrompt": 7}, BLOCK),
        ({"transformedPrompt": "dispatch groups"}, BLOCK),
        ({"prompt": None, "transformedPrompt": "dispatch groups"}, BLOCK),
        (["not", "an", "object"], BLOCK),
        ("not json", BLOCK),
        ("", BLOCK),
    ],
)
def test_no_match_or_bad_payload_writes_nothing(tmp_path, monkeypatch, capsys, payload, recall):
    exit_code, out, _, _ = _run(monkeypatch, capsys, tmp_path, payload, recall)

    assert exit_code == 0
    assert out == ""


@pytest.mark.unit
@pytest.mark.parametrize(
    ("env", "searched"),
    [
        ({"COPILOT_AGENT_PROMPT": "set"}, False),
        ({"GITHUB_COPILOT_API_TOKEN": "set"}, False),
        ({"COPILOT_AGENT_PROMPT": ""}, True),
    ],
)
def test_cloud_agent_sandbox_skips_recall(tmp_path, monkeypatch, capsys, env, searched):
    """Cloud agent runs unattended on a checked-out branch (ADR-068, #4727)."""
    payload = {"prompt": "dispatch groups", "transformedPrompt": "dispatch groups"}

    exit_code, out, _, seen = _run(monkeypatch, capsys, tmp_path, payload, env=env)

    assert exit_code == 0
    assert bool(seen) is searched
    assert ("modifiedTransformedPrompt" in out) is searched


@pytest.mark.unit
def test_undecodable_stdin_writes_nothing(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"\xff\xfe"), encoding="utf-8"))
    for name in CLOUD_VARS:
        monkeypatch.delenv(name, raising=False)

    assert main() == 0
    assert capsys.readouterr().out == ""
