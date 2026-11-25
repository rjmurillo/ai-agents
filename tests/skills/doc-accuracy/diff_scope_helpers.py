"""Shared fixtures for the diff-scope tests: real git repos and gate runs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy_diff_scope",
)

FENCE = "```"
WHOLE_FILE_END = 2**31 - 1
FILLER = "".join(f"filler {n}\n" for n in range(8))


# A parsed doc-accuracy JSON artifact.
Json = dict[str, Any]


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit(repo: Path, message: str = "c") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def make_repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    """Create a repo with a base commit holding ``src.py`` plus ``files``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "--initial-branch=main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "src.py").write_text("class Real:\n    pass\n")
    for name, data in files.items():
        raw = data.encode() if isinstance(data, str) else data
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes(raw)
    commit(repo, "base")
    return repo


def example(symbol: str) -> str:
    """A python example whose only CamelCase symbol is ``symbol``."""
    return f"{FENCE}python\nx = {symbol}()\n{FENCE}\n"


def run_gate(repo: Path, tmp_path: Path, *extra: str) -> tuple[int, Json]:
    """Run the CLI; return the exit code and the compilability data."""
    out = tmp_path / "out"
    code = mod.main(["--target", str(repo), "--output-dir", str(out), "--format", "gate", *extra])
    data: Json = json.loads((out / "compilability-findings.json").read_text())
    return code, data


def gate_result(tmp_path: Path) -> Json:
    result: Json = json.loads((tmp_path / "out" / "gate-result.json").read_text())
    return result


def by_symbol(data: Json) -> dict[str, Json]:
    return {f["evidence"]["symbol"]: f for f in data["findings"]}


def gate_diff(repo: Path, tmp_path: Path) -> tuple[int, Json]:
    """Run the gate against ``HEAD~1``."""
    return run_gate(repo, tmp_path, "--diff-base", "HEAD~1")


def edit_and_commit(repo: Path, name: str, text: str | bytes) -> None:
    raw = text.encode() if isinstance(text, str) else text
    (repo / name).write_bytes(raw)
    commit(repo)


def edit_files_and_commit(repo: Path, files: dict[str, str]) -> None:
    """Write every file in ``files`` and commit them as one head commit."""
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    commit(repo)


def run_same_pr(repo: Path, tmp_path: Path, *extra: str) -> tuple[int, Json, Json]:
    """Run ``--same-pr`` against ``HEAD~1``; return exit code, findings, checklist."""
    out = tmp_path / "out"
    argv = ["--target", str(repo), "--output-dir", str(out), "--format", "summary"]
    code = mod.main([*argv, "--same-pr", "--diff-base", "HEAD~1", *extra])
    findings: Json = json.loads((out / "same-pr-findings.json").read_text(encoding="utf-8"))
    checklist: Json = json.loads((out / "same-pr-checklist.json").read_text(encoding="utf-8"))
    return code, findings, checklist


def line_of(text: str, needle: str) -> int:
    """1-based line of the first line containing ``needle``."""
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not in fixture")


def checklist_entry(checklist: Json, path: str, needle: str) -> Json:
    hits = [e for e in checklist["entries"] if e["prose_file"] == path and needle in e["text"]]
    assert len(hits) == 1, [e["text"] for e in checklist["entries"]]
    return cast(Json, hits[0])
