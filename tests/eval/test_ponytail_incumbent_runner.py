"""Tests for evals/ponytail-incumbent/run.py (issue #5457)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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
    (plugin / ".git").mkdir()
    return plugin


def test_build_root_copies_plugin_and_cases(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    (cases / "c1").mkdir(parents=True)
    (cases / "c1/prompt.md").write_text(PROMPT)
    root = run.build_root(_plugin(tmp_path, "4.9.0"), cases, tmp_path / "work", "Rule.")
    assert (root / ".claude-plugin/plugin.json").is_file()
    assert not (root / ".in_use").exists()
    assert not (root / ".git").exists()
    assert "append_system_prompt: |\n  Rule." in (root / "evals/c1/prompt.md").read_text()


def test_build_root_refuses_other_plugin_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="4.9.0"):
        run.build_root(_plugin(tmp_path, "4.10.0"), tmp_path, tmp_path / "work", "Rule.")


def test_summarize_gates_on_deterministic_graders_only() -> None:
    """ADR-058: judge-backed graders (llm, baseline) never change `accepted`."""
    ok = {"name": "regex", "passed": True, "scored": True}
    bad = {"name": "regex", "passed": False, "scored": True}
    judge_no = {"name": "judge", "passed": False, "scored": True}
    judge_yes = {"name": "judge", "passed": True, "scored": True}
    indicator = {"name": "skill", "passed": False, "scored": False}
    baseline_no = {"name": "vs-baseline", "passed": False, "scored": True}
    result = {
        "cases": [
            {
                "name": "c1",
                "graders": [
                    {"name": "regex", "type": "regex"},
                    {"name": "judge", "type": "llm"},
                    {"name": "vs-baseline", "type": "baseline"},
                ],
                "arms": {
                    "with": [
                        {
                            "graders": [ok, judge_no, baseline_no, indicator],
                            "costUsd": 0.1,
                            "durationSeconds": 4,
                        },
                        {"graders": [bad, judge_yes], "costUsd": 0.2, "durationSeconds": 6},
                    ],
                    "without": [{"graders": [ok, judge_yes], "error": "timeout", "costUsd": None}],
                },
            }
        ]
    }
    with_row, without_row = run.summarize(result)
    assert with_row == {
        "case": "c1",
        "arm": "with",
        "runs": 2,
        "errors": 0,
        "accepted": 1,
        "failed_checks": 1,
        "advisory_judge_passed": 1,
        "cost_usd": 0.3,
        "seconds": 10,
    }
    assert without_row["accepted"] == 0, "an errored run never counts as accepted"
    assert without_row["errors"] == 1
    table = run.render([with_row])
    assert "| c1 | with | 1/2 | 1 | 0 | 0.3000 | 10 | 1/2 |" in table
    assert "Advisory: not part of the gated signal." in table


def test_build_root_refuses_output_inside_plugin(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, "4.9.0")
    with pytest.raises(ValueError, match="inside"):
        run.build_root(plugin, tmp_path, plugin / "results", "Rule.")


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, timeout=30
    )
    return done.stdout.strip()


def _checkout(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "a.txt")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_verify_plugin_accepts_clean_checkout_at_sha(tmp_path: Path) -> None:
    repo, sha = _checkout(tmp_path)
    run.verify_plugin(repo, sha)


def test_verify_plugin_rejects_other_commit_dirty_tree_and_non_git(tmp_path: Path) -> None:
    repo, sha = _checkout(tmp_path)
    with pytest.raises(ValueError, match="checkout at"):
        run.verify_plugin(repo, "0" * 40)
    (repo / "a.txt").write_text("changed\n")
    with pytest.raises(ValueError, match="local changes"):
        run.verify_plugin(repo, sha)
    (repo / "a.txt").write_text("a\n")
    (repo / ".gitignore").write_text("secret.js\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ignore")
    run.verify_plugin(repo, _git(repo, "rev-parse", "HEAD"))
    (repo / "secret.js").write_text("hook()\n")
    with pytest.raises(ValueError, match="ignored files"):
        run.verify_plugin(repo, _git(repo, "rev-parse", "HEAD"))
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ValueError, match="checkout at"):
        run.verify_plugin(plain, sha)


def _main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, out: Path) -> int:
    monkeypatch.setattr(run, "verify_plugin", lambda *_: None)
    monkeypatch.setattr(
        "sys.argv", ["run.py", "--plugin-dir", str(_plugin(tmp_path, "4.9.0")), "--out", str(out)]
    )
    return run.main()


def test_main_refuses_a_non_empty_output_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "result.json").write_text("{}")
    assert _main(monkeypatch, tmp_path, out) == 2


def test_main_reports_a_timed_out_eval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def expire(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("claude", run.EVAL_TIMEOUT_SECONDS)

    monkeypatch.setattr(run.subprocess, "run", expire)
    assert _main(monkeypatch, tmp_path, tmp_path / "out") == 3


def test_main_reports_a_missing_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run.subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess([], 1))
    assert _main(monkeypatch, tmp_path, tmp_path / "out") == 3
