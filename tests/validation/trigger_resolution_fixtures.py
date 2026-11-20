"""Shared fixtures for the skill trigger resolution gate tests.

Fake skill trees live in tmp_path and follow the shape `_catalog` builds in
`tests/eval/test_eval_autoplan_routes.py`. The resolver under test is the real
`resolve_route.py`, loaded by the gate itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import check_skill_trigger_resolution as gate


def _skill(
    skills: Path,
    name: str,
    description: str,
    intents: list[str] | None = None,
    role: str = "front-door",
) -> None:
    folder = skills / name
    folder.mkdir(parents=True)
    lines = ["---", f"name: {name}", f"description: {json.dumps(description)}"]
    lines += ["metadata:", "  routing:", f"    role: {role}", "    invoker: autoplan"]
    lines += ["    trigger: t", "    user-facing: true"]
    if intents is not None:
        lines += ["    intents:"] + [f"      - {i}" for i in intents]
    lines += ["---", "", "Body."]
    (folder / "SKILL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _skills(repo: Path) -> Path:
    return repo / "src" / "claude" / "skills"


def _baseline(
    repo: Path,
    own: dict | None = None,
    sibling: dict | None = None,
    no_intents: dict | None = None,
) -> Path:
    path = repo / "baseline.json"
    payload = {
        "schema_version": "1",
        "violations": {
            gate.CHECK_OWN: own or {},
            gate.CHECK_SIBLING: sibling or {},
            gate.CHECK_NO_INTENTS: no_intents or {},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(repo: Path, baseline: Path | None = None, *extra: str) -> int:
    argv = ["--repo-root", str(repo), "--baseline", str(baseline or repo / "baseline.json")]
    return gate.main([*argv, *extra])
