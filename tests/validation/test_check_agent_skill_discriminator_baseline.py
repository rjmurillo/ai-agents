"""Full-corpus baseline tests for check_agent_skill_discriminator.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_agent_skill_discriminator.py"


def _reference_body(lines: int = 30) -> str:
    rows = "\n".join(f"| key{i} | value{i} |" for i in range(lines // 2))
    bullets = "\n".join(f"- field{i}: required" for i in range(lines // 2))
    return f"## Schema\n\n| col | desc |\n|-----|------|\n{rows}\n\n## Rules\n{bullets}\n"


def _write_agent(repo: Path, name: str) -> str:
    content = "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: Test agent {name}.",
            "model: sonnet",
            "---",
            "",
            f"# {name} agent",
            "",
            _reference_body(),
        ]
    )
    rel = f".claude/agents/{name}.md"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return rel


def _write_command(repo: Path, agent: str) -> None:
    base = repo / ".claude" / "commands"
    base.mkdir(parents=True, exist_ok=True)
    (base / "build.md").write_text(
        f'Task(subagent_type="{agent}"): do work.\n'
        'Skill(skill="pre-mortem").\n',
        encoding="utf-8",
    )


def _scaffold(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".claude" / "commands").mkdir(parents=True)
    (repo / ".claude" / "agents").mkdir(parents=True)
    return repo


def _run_all(repo: Path, baseline: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--all",
            "--baseline",
            str(baseline),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_full_corpus_baseline_allows_existing_candidates(tmp_path: Path) -> None:
    """Full-corpus mode surfaces known candidates without failing the ratchet."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "shaped")
    _write_command(repo, "shaped")
    baseline = repo / "baseline.json"
    baseline.write_text(
        json.dumps({"_comment": "test baseline", "candidates": {rel: 1}}),
        encoding="utf-8",
    )

    proc = _run_all(repo, baseline)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Existing candidates recorded in baseline" in proc.stdout
    assert rel in proc.stdout


def test_full_corpus_baseline_fails_new_candidates(tmp_path: Path) -> None:
    """A candidate absent from the baseline trips the full-corpus ratchet."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "shaped")
    _write_command(repo, "shaped")
    baseline = repo / "baseline.json"
    baseline.write_text(
        json.dumps({"_comment": "test baseline", "candidates": {}}),
        encoding="utf-8",
    )

    proc = _run_all(repo, baseline)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "New unbaselined candidates" in proc.stdout
    assert rel in proc.stdout
