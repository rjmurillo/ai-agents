"""Fixture builders for the skill artifact flow gate tests (ADR-123)."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_artifact_flow as gate  # re-exported to the test modules

__all__ = ["gate"]

Overrides = Mapping[str, Mapping[str, object] | None]


def _handoff(writes: list[str], next_skill: str | None) -> str:
    names = ", ".join(f"`{name}`" for name in writes) or "none"
    target = f"`/{next_skill}`" if next_skill else "none"
    return f"Writes: {names}. Next: {target}."


def _in(artifact: str, **extra: object) -> dict[str, object]:
    return {"artifact": artifact, **extra}


def _out(artifact: str, **extra: object) -> dict[str, object]:
    return {"artifact": artifact, **extra}


# Lifecycle chain: spec-helper -> requirements-spec (credited to spec) ->
# plan -> execution-plan -> build -> implementation-change -> test, review ->
# review-marker -> ship.
_DEFAULTS: dict[str, dict[str, object]] = {
    "spec": {"handoff": _handoff(["requirements-spec"], "plan")},
    "spec-helper": {"invoker": "spec", "outputs": [_out("requirements-spec")]},
    "plan": {
        "inputs": [_in("requirements-spec", required=False)],
        "outputs": [_out("execution-plan", path="plans/active/")],
        "handoff": _handoff(["execution-plan"], "build"),
    },
    "build": {
        "inputs": [_in("execution-plan")],
        "outputs": [_out("implementation-change")],
        "handoff": _handoff(["implementation-change"], "test"),
    },
    "test": {
        "inputs": [_in("implementation-change")],
        "handoff": _handoff([], "review"),
    },
    "review": {
        "inputs": [_in("implementation-change")],
        "outputs": [_out("review-marker")],
        "handoff": _handoff(["review-marker"], "ship"),
    },
    "ship": {
        "inputs": [_in("review-marker")],
        "handoff": _handoff([], None),
    },
}


def _keyed(entries: object) -> object:
    """Convert `_in`/`_out` dicts to the artifact-keyed mapping ADR-123 requires.

    Anything that is not a list of such dicts passes through unchanged, so a
    negative test can write a malformed shape on purpose.
    """
    if not isinstance(entries, list) or not entries:
        return entries
    if not all(isinstance(e, dict) and "artifact" in e for e in entries):
        return entries
    keyed: dict[str, object] = {}
    for entry in entries:
        assert isinstance(entry, dict)
        options = {k: v for k, v in entry.items() if k != "artifact"}
        keyed[str(entry["artifact"])] = options or None
    return keyed


_PLAIN_KEY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


def _block_yaml(value: object, indent: int) -> list[str]:
    """Emit block-style YAML inside the subset skillforge's stdlib parser reads.

    Keys that are not plain are double-quoted, which the subset refuses on
    purpose; a negative test relies on that to exercise invariant 0.
    """
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            name = key if isinstance(key, str) and _PLAIN_KEY.fullmatch(key) else json.dumps(key)
            if item is None:
                lines.append(f"{pad}{name}:")
            elif isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}{name}:")
                lines.extend(_block_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{name}: {_scalar(item)}")
        return lines
    assert isinstance(value, list)
    for item in value:
        lines.append(f"{pad}- {_scalar(item)}")
    return lines


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return json.dumps(str(value)) if isinstance(value, str) else str(value)


def _write_skill(
    root: Path,
    name: str,
    *,
    invoker: str = "autoplan",
    inputs: object = None,
    outputs: object = None,
    repo_local: bool = False,
    handoff: str | None = None,
) -> Path:
    """Write one skill template. `handoff=None` omits the `## Handoff` section."""
    routing = {"role": "front-door", "invoker": invoker, "trigger": "explicit", "user-facing": True}
    lines = [
        "---",
        f"name: {name}",
        f"description: {json.dumps(f'Use when you say {name}.')}",
        "metadata:",
        "  routing:",
        *_block_yaml(routing, 4),
    ]
    for field, value in (("inputs", _keyed(inputs)), ("outputs", _keyed(outputs))):
        if not value:
            continue
        if isinstance(value, (dict, list)):
            lines.append(f"  {field}:")
            lines.extend(_block_yaml(value, 4))
        else:
            lines.append(f"  {field}: {_scalar(value)}")
    if repo_local:
        lines.append("  distribution: repo-local")
    lines += ["---", "", f"# {name}", "", "Body text."]
    if handoff is not None:
        lines += ["", "## Handoff", "", handoff]
    path = root / gate.TEMPLATE_DIR / f"{name}{gate.TEMPLATE_SUFFIX}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _corpus(root: Path, overrides: Overrides | None = None) -> Path:
    """Write the valid corpus. An override value of None drops that skill."""
    overrides = overrides or {}
    for name, params in _DEFAULTS.items():
        if name in overrides and overrides[name] is None:
            continue
        options: dict[str, Any] = {**params, **(overrides.get(name) or {})}
        _write_skill(root, name, **options)
    return root


def _run(root: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = gate.main(["--repo-root", str(root), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err
