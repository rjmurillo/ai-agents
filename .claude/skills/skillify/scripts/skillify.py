#!/usr/bin/env python3
"""Deterministic helper for the skillify skill.

Four subcommands turn the skillify procedure into checkable steps. Each prints
one JSON object on stdout.

    gate     audit JSON -> PROCEED or REJECT (one-off, trivial, no procedure)
    resolve  where may a skill be written: explicit > env var > cwd detection
    overlap  score existing skills against the workflow: PATCH or CREATE
    verify   read back a written SKILL.md and check the contract

Stdlib only. Paths use pathlib so the script behaves the same on Linux and
Windows. Nothing here writes a skill file; the harness file tools do that.

Exit codes:
    0  ok. A gate REJECT, an overlap CREATE or PATCH, and a verify PASS are
       all answers, not failures.
    1  logic failure: unreadable or malformed input, or verify found a defect.
    2  config: no destination resolved (`needs_clarification`) or the resolved
       destination is not a directory. Nothing is written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from skillify_text import (
    SkillifyError,
    parse_frontmatter,
    split_sections,
    tokenize,
)
from skillify_verify import resolve_skill_file, verify_skill

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

MIN_TOOL_CALLS = 2
PROACTIVE_TOOL_CALLS = 5
PATCH_THRESHOLD_PERCENT = 70
TOP_MATCHES = 5

# Project skill roots by harness: a hidden config directory plus `skills`.
# Claude Code reads the first, Copilot CLI the second (agent-harness-reference,
# probe-evidence.md section 10).
CLAUDE_CONFIG_DIR = ".claude"
GITHUB_CONFIG_DIR = ".github"
SKILLS_DIR = "skills"
SKILL_ROOT_SUFFIXES: tuple[tuple[str, str], ...] = (
    (CLAUDE_CONFIG_DIR, SKILLS_DIR),
    (GITHUB_CONFIG_DIR, SKILLS_DIR),
)


@dataclass(frozen=True)
class SkillInfo:
    """One scanned skill: identity plus the text that routes to it."""

    name: str
    root: str
    path: str
    tokens: frozenset[str]


# ---------------------------------------------------------------- input helpers


def load_json(source: str) -> Any:
    """Read JSON from a file path, or from stdin when `source` is `-`."""
    try:
        if source == "-":
            return json.loads(sys.stdin.read())
        return json.loads(Path(source).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillifyError(f"cannot read {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SkillifyError(f"malformed JSON in {source}: {exc}") from exc


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _count_of(value: Any, field: str) -> int:
    if isinstance(value, list):
        return len(value)
    if _is_count(value):
        return int(value)
    raise SkillifyError(f"audit field '{field}' must be a count or a list")


# ------------------------------------------------------------------------- gate


def evaluate_gate(audit: Any) -> dict[str, Any]:
    """Apply the Phase 0 gate to an audit of the completed workflow."""
    if not isinstance(audit, dict):
        raise SkillifyError("audit must be a JSON object")
    missing = [
        key
        for key in (
            "tool_call_count",
            "reusable_class",
            "decision_points",
            "gotchas",
            "trigger_phrase",
        )
        if key not in audit
    ]
    if missing:
        raise SkillifyError(f"audit is missing: {', '.join(missing)}")
    calls = audit["tool_call_count"]
    if not _is_count(calls):
        raise SkillifyError("audit field 'tool_call_count' must be a non-negative integer")
    if not isinstance(audit["reusable_class"], bool):
        raise SkillifyError("audit field 'reusable_class' must be true or false")
    decisions = _count_of(audit["decision_points"], "decision_points")
    gotchas = _count_of(audit["gotchas"], "gotchas")
    trigger = audit["trigger_phrase"]
    if not isinstance(trigger, str):
        raise SkillifyError("audit field 'trigger_phrase' must be a string")
    reasons = _gate_reasons(calls, audit["reusable_class"], decisions, gotchas, trigger)
    proceed = not reasons
    return {
        "status": "PROCEED" if proceed else "REJECT",
        "reasons": reasons,
        "approval_gate_required": audit.get("external_actions") is True,
        "proactive_eligible": proceed and calls >= PROACTIVE_TOOL_CALLS,
    }


def _gate_reasons(
    calls: int, reusable: bool, decisions: int, gotchas: int, trigger: str
) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if not reusable:
        reasons.append(
            {"code": "one_off", "detail": "not a class of work that will recur; do nothing"}
        )
    if calls < MIN_TOOL_CALLS:
        reasons.append(
            {
                "code": "trivial_wrapper",
                "detail": f"{calls} tool call(s); a single call is a tool, not a skill",
            }
        )
    if decisions == 0 and gotchas == 0:
        reasons.append(
            {
                "code": "no_real_procedure",
                "detail": "no decision point and no gotcha a future run would hit",
            }
        )
    if not trigger.strip():
        reasons.append(
            {"code": "no_trigger_phrase", "detail": "no phrase a user would actually say"}
        )
    return reasons


# ---------------------------------------------------------------------- resolve


def skills_root_kind(path: PurePath) -> str:
    """Name the harness whose project layout `path` matches, else `custom`.

    Works on PurePath so Windows-style paths classify the same on any OS.
    """
    tail = tuple(part.lower() for part in path.parts[-2:])
    if tail == SKILL_ROOT_SUFFIXES[0]:
        return "claude-code"
    if tail == SKILL_ROOT_SUFFIXES[1]:
        return "copilot-cli"
    return "custom"


def detect_cwd_roots(cwd: Path) -> list[Path]:
    """Find skills roots in `cwd` and its ancestors up to the repository root.

    The walk stops at the first directory holding `.git` (a directory or a
    worktree file). With no `.git` above, only `cwd` is searched, so a scratch
    directory under a home folder never picks up a user-scope tree by accident.
    """
    start = cwd.resolve()
    boundary = _repository_root(start)
    chain = [start] if boundary is None else _chain_to(start, boundary)
    found: list[Path] = []
    for directory in chain:
        for parent, leaf in SKILL_ROOT_SUFFIXES:
            candidate = directory / parent / leaf
            if candidate.is_dir():
                found.append(candidate)
        if found:
            break
    return found


def _repository_root(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _chain_to(start: Path, boundary: Path) -> list[Path]:
    lineage = (start, *start.parents)
    return list(lineage[: lineage.index(boundary) + 1])


def resolve_destination(
    explicit: str | None,
    env_vars: Sequence[str],
    cwd: Path,
    environ: Mapping[str, str],
) -> tuple[dict[str, Any], int]:
    """Resolve the skills root in order: explicit, env var, cwd detection."""
    if explicit is not None and explicit.strip():
        return _resolved("explicit", Path(explicit.strip()).expanduser(), None)
    for name in env_vars:
        value = environ.get(name, "").strip()
        if value:
            return _resolved("env", Path(value).expanduser(), name)
    roots = detect_cwd_roots(cwd)
    if len(roots) == 1:
        return _resolved("cwd", roots[0], None)
    return _needs_clarification(roots, list(env_vars))


def _resolved(source: str, path: Path, env_var: str | None) -> tuple[dict[str, Any], int]:
    if path.exists() and not path.is_dir():
        invalid = {
            "status": "invalid",
            "source": source,
            "path": str(path),
            "reason": "path exists and is not a directory",
            "writes": "none",
        }
        return invalid, EXIT_CONFIG
    payload: dict[str, Any] = {
        "status": "resolved",
        "source": source,
        "path": str(path),
        "exists": path.is_dir(),
        "harness": skills_root_kind(path),
    }
    if env_var is not None:
        payload["env_var"] = env_var
    return payload, EXIT_OK


def _needs_clarification(roots: list[Path], env_vars: list[str]) -> tuple[dict[str, Any], int]:
    ambiguous = len(roots) > 1
    payload = {
        "status": "needs_clarification",
        "reason": (
            "more than one skills root found; choose one"
            if ambiguous
            else "no explicit path, no set env var, no skills root found from the working directory"
        ),
        "candidates": [str(path) for path in roots],
        "env_vars_checked": env_vars,
        "question": "Which directory should hold the skill? Give a path.",
        "writes": "none",
    }
    return payload, EXIT_CONFIG


# ---------------------------------------------------------------------- overlap


def read_skill(skill_file: Path, root: Path) -> SkillInfo | None:
    """Parse one SKILL.md into routing tokens, or None when it has no frontmatter name."""
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta, body = parse_frontmatter(text)
    name = meta.get("name", "").strip()
    if not name:
        return None
    triggers = next((s for s in split_sections(body) if s.name == "triggers"), None)
    trigger_text = "\n".join(triggers.lines) if triggers else ""
    tokens = tokenize(f"{name.replace('-', ' ')} {meta.get('description', '')} {trigger_text}")
    return SkillInfo(name=name, root=str(root), path=str(skill_file), tokens=tokens)


def scan_roots(roots: Sequence[Path]) -> tuple[list[SkillInfo], list[str], list[str]]:
    """Scan `<root>/*/SKILL.md`. Returns skills, unparseable files, missing roots."""
    skills: list[SkillInfo] = []
    skipped: list[str] = []
    missing: list[str] = []
    for root in roots:
        if not root.is_dir():
            missing.append(str(root))
            continue
        for skill_file in sorted(root.glob("*/SKILL.md")):
            info = read_skill(skill_file, root)
            if info is None:
                skipped.append(str(skill_file))
            else:
                skills.append(info)
    return skills, skipped, missing


def workflow_tokens(workflow: Any) -> frozenset[str]:
    """Tokens from the workflow's `actions`, `terms`, and `trigger_phrase`."""
    if not isinstance(workflow, dict):
        raise SkillifyError("workflow must be a JSON object")
    texts: list[str] = []
    for key in ("actions", "terms"):
        value = workflow.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SkillifyError(f"workflow field '{key}' must be a list of strings")
        texts.extend(value)
    phrase = workflow.get("trigger_phrase", "")
    if not isinstance(phrase, str):
        raise SkillifyError("workflow field 'trigger_phrase' must be a string")
    tokens = tokenize(" ".join([*texts, phrase]))
    if not tokens:
        raise SkillifyError("workflow has no actions, terms, or trigger_phrase to compare")
    return tokens


def evaluate_overlap(workflow: Any, roots: Sequence[Path]) -> dict[str, Any]:
    """Score every scanned skill and recommend PATCH at 70 percent coverage."""
    wanted = workflow_tokens(workflow)
    skills, skipped, missing = scan_roots(roots)
    scored = sorted(
        (_score(wanted, skill) for skill in skills),
        key=lambda row: (-row["hits"], row["name"], row["path"]),
    )
    best = scored[0] if scored else None
    patch = best is not None and best["hits"] * 100 >= len(wanted) * PATCH_THRESHOLD_PERCENT
    return {
        "status": "PATCH" if patch else "CREATE",
        "skill": best["name"] if patch and best else None,
        "path": best["path"] if patch and best else None,
        "threshold": PATCH_THRESHOLD_PERCENT / 100,
        "workflow_terms": len(wanted),
        "scanned": len(skills),
        "matches": scored[:TOP_MATCHES],
        "skipped": skipped,
        "missing_roots": missing,
    }


def _score(wanted: frozenset[str], skill: SkillInfo) -> dict[str, Any]:
    covered = sorted(wanted & skill.tokens)
    return {
        "name": skill.name,
        "path": skill.path,
        "coverage": round(len(covered) / len(wanted), 3),
        "hits": len(covered),
        "covered": covered,
    }


# -------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skillify helper. JSON on stdout.")
    sub = parser.add_subparsers(dest="command", required=True)
    gate = sub.add_parser("gate", help="Phase 0 gate on an audit JSON")
    gate.add_argument("--audit", required=True, help="audit JSON file, or - for stdin")
    resolve = sub.add_parser("resolve", help="resolve the skills destination")
    resolve.add_argument("--explicit", help="path the user named")
    resolve.add_argument("--env-var", action="append", default=[], help="env var name, repeatable")
    resolve.add_argument("--cwd", help="directory to detect from (default: current directory)")
    overlap = sub.add_parser("overlap", help="score existing skills against the workflow")
    overlap.add_argument("--workflow", required=True, help="workflow JSON file, or - for stdin")
    overlap.add_argument("--root", action="append", required=True, help="skills root, repeatable")
    verify = sub.add_parser("verify", help="read back and check a written SKILL.md")
    verify.add_argument("--skill", required=True, help="SKILL.md path or its directory")
    verify.add_argument("--trigger", required=True, help="trigger phrase to report and check")
    verify.add_argument(
        "--external-actions", action="store_true", help="the skill takes external or public actions"
    )
    return parser


def run(args: argparse.Namespace, environ: Mapping[str, str]) -> tuple[dict[str, Any], int]:
    if args.command == "gate":
        return evaluate_gate(load_json(args.audit)), EXIT_OK
    if args.command == "resolve":
        cwd = Path(args.cwd) if args.cwd else Path.cwd()
        return resolve_destination(args.explicit, args.env_var, cwd, environ)
    if args.command == "overlap":
        roots = [Path(r).expanduser() for r in args.root]
        return evaluate_overlap(load_json(args.workflow), roots), EXIT_OK
    skill_file = resolve_skill_file(Path(args.skill))
    result = verify_skill(skill_file, args.trigger, args.external_actions)
    return result, EXIT_LOGIC if result["status"] == "FAIL" else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload, code = run(args, os.environ)
    except SkillifyError as exc:
        payload, code = {"status": "error", "error": str(exc)}, EXIT_LOGIC
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
