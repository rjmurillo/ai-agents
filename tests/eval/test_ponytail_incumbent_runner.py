"""Tests for evals/ponytail-incumbent/run.py (issue #5457)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "ponytail_run", REPO / "evals/ponytail-incumbent/run.py"
)
assert _SPEC and _SPEC.loader
run = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run)

PROMPT = "---\nname: x\nmax_turns: 3\n---\n\nDo the task.\n"


def _frontmatter(text: str) -> str:
    return text.split("\n---\n", 1)[0]


def test_inject_adds_indented_block_inside_frontmatter() -> None:
    out = run.inject_corpus(PROMPT, "Rule one.\n\n---\nRule two.")
    head = _frontmatter(out)
    assert "append_system_prompt: |\n  Rule one.\n\n  ---\n  Rule two." in head
    assert out.endswith("\n---\n\nDo the task.\n")
    assert "name: x\nmax_turns: 3\n" in head


def test_inject_rejects_prompt_without_frontmatter() -> None:
    with pytest.raises(ValueError):
        run.inject_corpus("Do the task.\n", "Rule.")


def test_every_committed_case_accepts_the_corpus() -> None:
    corpus = run.load_corpus(REPO)
    prompts = sorted(run.CASES.rglob("prompt.md"))
    assert len(prompts) == 13
    for prompt in prompts:
        assert "append_system_prompt" in _frontmatter(run.inject_corpus(prompt.read_text(), corpus))


def _plugin(tmp_path: Path, version: str) -> Path:
    plugin = tmp_path / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin/plugin.json").write_text(json.dumps({"version": version}))
    (plugin / ".in_use").mkdir()
    return plugin


def test_build_root_copies_plugin_and_cases(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    (cases / "c1").mkdir(parents=True)
    (cases / "c1/prompt.md").write_text(PROMPT)
    root = run.build_root(_plugin(tmp_path, "4.9.0"), cases, tmp_path / "work", "Rule.")
    assert (root / ".claude-plugin/plugin.json").is_file()
    assert not (root / ".in_use").exists()
    assert "append_system_prompt: |\n  Rule." in (root / "evals/c1/prompt.md").read_text()


def test_build_root_refuses_other_plugin_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="4.9.0"):
        run.build_root(_plugin(tmp_path, "4.10.0"), tmp_path, tmp_path / "work", "Rule.")


def test_summarize_counts_acceptance_burden_cost_and_errors() -> None:
    passed = {"passed": True, "scored": True}
    failed = {"passed": False, "scored": True}
    indicator = {"passed": False, "scored": False}
    result = {
        "cases": [
            {
                "name": "c1",
                "tags": ["decision"],
                "arms": {
                    "with": [
                        {
                            "graders": [passed, passed, indicator],
                            "costUsd": 0.1,
                            "durationSeconds": 4,
                        },
                        {"graders": [passed, failed], "costUsd": 0.2, "durationSeconds": 6},
                    ],
                    "without": [{"graders": [], "error": "timeout", "costUsd": None}],
                },
            }
        ]
    }
    with_row, without_row = run.summarize(result)
    assert with_row == {
        "case": "c1",
        "tags": ["decision"],
        "arm": "with",
        "runs": 2,
        "errors": 0,
        "accepted": 1,
        "failed_graders": 1,
        "cost_usd": 0.3,
        "seconds": 10,
    }
    assert without_row["accepted"] == 0
    assert without_row["errors"] == 1
    assert "| c1 | with | 1/2 | 1 | 0 | 0.3000 | 10 |" in run.render([with_row])
