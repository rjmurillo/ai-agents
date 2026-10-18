"""Run the capability-script command lines SKILL.md documents, under the host contract.

Companion to test_runtime_contract.py, which runs the `bootstrap_boundary.py` lines.
This file runs the lines for the mine, forms, drift, and eval scripts.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from bootstrap_helpers import write

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_runtime_contract import (
    LINE_RE,
    PLUGIN_ROOT,
    SKILL_MD,
    SKILL_NAME,
    _bash,
    _host_env,
)

CAPABILITY_LINE_RE = re.compile(r'bootstrap_(mine|forms|drift|eval)\.py" (\w+)')


def _capability_commands(files: dict[str, Path]) -> list[tuple[str, str]]:
    """Return every documented non-boundary command, placeholders filled, in order."""
    commands: list[tuple[str, str]] = []
    for line in LINE_RE.findall(SKILL_MD.read_text(encoding="utf-8")):
        match = CAPABILITY_LINE_RE.search(line)
        if match is None:
            continue
        text = line
        for placeholder, value in (
            ("<new-skill>", SKILL_NAME),
            ("<output-root>", ".claude/skills"),
            ("<generated-prefix>", "src/"),
            ("<plan path>", str(files["plan"])),
            ("<cases path>", str(files["cases"])),
            ("<frozen path>", str(files["frozen"])),
            ("<results path>", str(files["results"])),
        ):
            text = text.replace(placeholder, value)
        assert "<" not in text, f"unfilled placeholder: {text}"
        commands.append((f"{match.group(1)} {match.group(2)}", text))
    return commands


def _seed_capability_run(repo: Path, scratch: Path) -> dict[str, Path]:
    """Write a consumer skill and the out-of-repo run files the documented lines read."""
    scratch.mkdir(parents=True, exist_ok=True)
    write(repo, f".claude/skills/{SKILL_NAME}/SKILL.md", "Run `README.md` first.\n")
    write(repo, f".claude/skills/{SKILL_NAME}/scripts/gates.py", "print('ok')\n")
    write(
        repo,
        f".claude/skills/{SKILL_NAME}/reverify.json",
        json.dumps({"checks": [{"id": "R1", "kind": "path_exists", "path": "README.md"}]}),
    )
    files = {name: scratch / f"{name}.json" for name in ("plan", "cases", "frozen")}
    files["results"] = scratch / "results.jsonl"
    files["plan"].write_text(
        json.dumps(
            {
                "project": "demo",
                "mode": "workflow",
                "items": [
                    {
                        "id": "I1",
                        "skill": SKILL_NAME,
                        "lens": "change-control",
                        "claim": "Each path maps to its gates",
                        "evidence": ["commit abc1234"],
                        "computable": True,
                        "form": "instrument",
                        "script": "scripts/gates.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    files["cases"].write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "C1",
                        "skill": SKILL_NAME,
                        "source": "outcome:demo",
                        "prompt": "Which gates run?",
                        "grader": {"kind": "contains_all", "terms": ["lint"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    files["results"].write_text(
        "\n".join(
            json.dumps({"case_id": "C1", "condition": condition, "output": output})
            for condition, output in (("baseline", "none"), ("with_skill", "lint runs"))
        )
        + "\n",
        encoding="utf-8",
    )
    return files


def test_skill_md_documents_every_capability_subcommand(tmp_path: Path) -> None:
    files = {name: tmp_path / name for name in ("plan", "cases", "frozen", "results")}

    documented = {name for name, _ in _capability_commands(files)}

    assert documented == {
        "mine candidates",
        "mine claims",
        "forms check",
        "eval freeze",
        "eval score",
        "drift check",
    }


def test_documented_capability_commands_run_from_a_consumer_repo(
    repo: Path, tmp_path: Path
) -> None:
    files = _seed_capability_run(repo, tmp_path / "scratch")
    env = _host_env(PLUGIN_ROOT)

    results = [(name, _bash(command, repo, env)) for name, command in _capability_commands(files)]

    failed = [(name, r.returncode, r.stdout + r.stderr) for name, r in results if r.returncode]
    assert failed == [], failed
    assert files["frozen"].is_file()


def test_documented_capability_commands_fail_without_a_plugin_root(
    repo: Path, tmp_path: Path
) -> None:
    files = _seed_capability_run(repo, tmp_path / "scratch")
    shutil.rmtree(repo / ".claude" / "skills" / "skill-bootstrap", ignore_errors=True)

    results = [_bash(command, repo, _host_env(None)) for _, command in _capability_commands(files)]

    assert all(r.returncode != 0 for r in results)
