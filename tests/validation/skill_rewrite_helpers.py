"""Shared fixture repository for the ADR-127 evidence check tests.

Each test builds a throwaway git repository with a ``main`` branch and a
``feature`` branch, then runs the check against ``main``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_rewrite_evidence as checker
import skill_rewrite_evidence as sre

__all__ = [
    "EVID",
    "MOVED",
    "REF",
    "RUNNER",
    "SCEN",
    "SKILL",
    "_VALIDATION",
    "checker",
    "commit",
    "commit_evidence",
    "driver_change",
    "git",
    "on_main",
    "repo",
    "results",
    "run",
    "run_gated",
    "scenario_doc",
    "skill_md",
    "sre",
    "write",
]

RUNNER = sre.load_runner()
SKILL = "src/claude/skills/demo/SKILL.md"
REF = "src/claude/skills/demo/references/detail.md"
SCEN = "tests/evals/demo-scenarios.json"
EVID = "evals/skill-rewrites/demo"
MOVED = [f"Moved line number {i} carries enough text to count as a move." for i in range(4)]


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    ).stdout.strip()


def skill_md(shape: str | None = None, body: str = "Body.", tools: str = "Read") -> str:
    meta = f"metadata:\n  shape: {shape}\n" if shape else ""
    return f"---\nname: demo\nallowed-tools: {tools}\n{meta}---\n\n# Demo\n\n{body}\n"


def scenario_doc(n: int = 8) -> str:
    rows = [
        {"id": f"S{i}", "desc": "d", "input": "i", "expected_verdict": "GO"}
        for i in range(1, n + 1)
    ]
    return json.dumps({"scenarios": rows}, indent=2)


def write(root: Path, rel: str, text: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def commit(root: Path, msg: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    write(root, SKILL, skill_md(body="\n".join(MOVED)))
    write(root, REF, "Reference.\n")
    write(root, SCEN, scenario_doc())
    demo = "class TestX:\n    def test_replaces(self):\n        pass\n"
    write(root, "tests/skills/demo/test_demo.py", demo)
    commit(root, "base")
    git(root, "checkout", "-q", "-b", "feature")
    return root


def surface_sha(root: Path) -> str:
    """The sha the runner records, computed by the runner's own loader."""
    text = RUNNER.load_prompt_surface_from_file(str(root / SKILL))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def results(root: Path, table: dict[str, tuple[str, str]] | None = None, **over: Any) -> str:
    table = table or {}
    verdict = over.pop("verdict", "PASS")
    corpus = json.loads((root / SCEN).read_text(encoding="utf-8"))
    scenarios = corpus["scenarios"] if isinstance(corpus, dict) else corpus

    def per_run(pattern: str) -> list[dict[str, Any]]:
        return [{"verdict": "GO" if c == "P" else "STOP", "model_used": "m"} for c in pattern]

    rows: dict[str, list[dict[str, Any]]] = {"before": [], "after": []}
    for s in scenarios:
        b, a = table.get(s["id"], ("PPP", "PPP"))
        rows["before"].append({"scenario_id": s["id"], "per_run": per_run(b)})
        rows["after"].append({"scenario_id": s["id"], "per_run": per_run(a)})
    identity = {
        "prompt_path": SKILL,
        "prompt_surface_sha256": surface_sha(root),
        "scenarios_path": SCEN,
        "scenarios_sha256": hashlib.sha256((root / SCEN).read_bytes()).hexdigest(),
        "base_ref": "main",
        "base_commit": git(root, "rev-parse", "main"),
        "model": "m",
    }
    identity.update(over)
    doc = {
        "model": "m",
        "identity": identity,
        "runs_per_scenario": 3,
        "security_critical": False,
        "gate": {"verdict": verdict},
        "detail": rows,
    }
    return json.dumps(doc)


def run(root: Path, capsys: pytest.CaptureFixture[str], base: str = "main") -> tuple[int, str]:
    code = checker.main(["--repo-root", str(root), "--base-ref", base])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def commit_evidence(root: Path, msg: str = "evidence") -> str:
    """Commit one passing results file for the current skill surface."""
    write(root, f"{EVID}/run-1.json", results(root))
    return commit(root, msg)


def on_main(root: Path, files: dict[str, str], msg: str) -> None:
    """Commit *files* on main, then rebuild the feature branch from it."""
    git(root, "checkout", "-q", "main")
    for rel, text in files.items():
        write(root, rel, text)
    commit(root, msg)
    git(root, "checkout", "-q", "-B", "feature")


def run_gated(
    root: Path, capsys: pytest.CaptureFixture[str], evidence: bool = True
) -> tuple[int, str]:
    """Tag the skill a driver, optionally commit passing evidence, run the check."""
    driver_change(root)
    if evidence:
        commit_evidence(root)
    return run(root, capsys)


def driver_change(root: Path) -> None:
    """Make the skill a driver in its own commit, after the scenario commit."""
    write(root, SKILL, skill_md("driver", body="\n".join(MOVED)))
    commit(root, "driver")
