#!/usr/bin/env python3
"""Check the tool form of every verified item in a skill-bootstrap plan.

Each verified knowledge item a bootstrap run turns into a skill gets a tool
form:

    scaffold    Prose the model reasons with, a map: rationale, invariants,
                failure history.
    instrument  A deterministic script that computes the answer from
                repository state, a GPS: a gate lookup, a path check, a count.
    both        The script computes; prose explains why, and when the
                script's answer is not the whole story.

The rule: anything computable from repository state is never scaffold-only.

Subcommand:

    check --plan FILE [--skills-root DIR] [--require-scripts]
              Validate the plan JSON and report each violation as
              {item, rule, message}. With `--require-scripts` and
              `--skills-root`, also flag instrument or both items whose
              `<skills-root>/<skill>/<script>` file does not exist.
              The gate stays strict (owner decision D18, 2026-10-24). It
              loosens only when a named consumer needs it.

Plan shape:

    {"project": "acme", "mode": "workflow" | "knowledge",
     "items": [{"id": "I1", "skill": "acme-change-control",
                "lens": "change-control", "claim": "...",
                "evidence": ["commit abc123"], "computable": true | false,
                "form": "instrument" | "scaffold" | "both",
                "script": "scripts/gates_for_path.py", "why": "...",
                "baseline_case": "C3"}]}

Exit codes:

    0  The plan has no violation.
    1  The plan has at least one violation.
    2  Configuration error: bad arguments, unreadable or malformed JSON, a
       wrong top-level type, an unknown mode, `--require-scripts` without
       `--skills-root`, `--skills-root` without `--require-scripts`, or a
       `--skills-root` that is not a directory.

The payload always carries `examined` (items read, zero included), so a caller
can tell "zero violations in N items" from "nothing was examined". The script
only reads files and never writes into the repository. Stdlib only, so it runs
from any plugin root.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

NAME_RE = re.compile(r"[a-z](?:[a-z0-9-]*[a-z0-9])?")
# Same rule as `bootstrap_boundary.name_defects`: at most 64 characters, no `--`.
# Skill scripts do not import each other, so the rule is repeated here and a
# test asserts the three scripts agree.
MAX_SKILL_NAME = 64
OTHER_LENS_RE = re.compile(r"other:[a-z0-9]+(?:-[a-z0-9]+)*")
LENSES = frozenset(
    {
        "change-control",
        "debugging-playbook",
        "failure-archaeology",
        "architecture-contract",
        "domain-reference",
        "config-and-flags",
        "build-and-env",
        "run-and-operate",
        "diagnostics-and-tooling",
        "validation-and-qa",
        "docs-and-writing",
        "external-positioning",
        "hardest-problem-campaign",
        "proof-and-analysis-toolkit",
        "research-frontier",
        "research-methodology",
    }
)
FORMS = ("scaffold", "instrument", "both")
SCRIPT_FORMS = frozenset({"instrument", "both"})
MODES = ("workflow", "knowledge")
SCRIPT_PREFIX = "scripts"

Payload = dict[str, Any]
Violation = dict[str, str]


class ConfigError(Exception):
    """Bad input: exit 2."""


def _violation(item_id: str, rule: str, message: str) -> Violation:
    return {"item": item_id, "rule": rule, "message": message}


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def script_defect(script: Any) -> str | None:
    """Return why `script` is not a relative path under `scripts/`, or None when valid."""
    if not _is_text(script):
        return "script must be a non-empty string"
    text = script.strip()
    if PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute():
        return "script must be a relative path"
    parts = PurePosixPath(text.replace("\\", "/")).parts
    if ".." in parts:
        return "script must not contain '..'"
    if len(parts) < 2 or parts[0] != SCRIPT_PREFIX:
        return f"script must live under {SCRIPT_PREFIX}/"
    return None


def valid_skill_name(name: Any) -> bool:
    if not isinstance(name, str) or len(name) > MAX_SKILL_NAME or "--" in name:
        return False
    return NAME_RE.fullmatch(name) is not None


def _lens_ok(lens: Any) -> bool:
    return isinstance(lens, str) and (lens in LENSES or OTHER_LENS_RE.fullmatch(lens) is not None)


def _evidence_ok(evidence: Any) -> bool:
    return isinstance(evidence, list) and bool(evidence) and all(_is_text(e) for e in evidence)


def _identity_violations(item: Payload, label: str, seen: set[str]) -> list[Violation]:
    found: list[Violation] = []
    item_id = item.get("id")
    if not _is_text(item_id):
        found.append(_violation(label, "id-invalid", "id must be a non-empty string"))
    elif item_id in seen:
        found.append(_violation(label, "duplicate-id", f"id {item_id!r} appears more than once"))
    skill = item.get("skill")
    if not valid_skill_name(skill):
        found.append(
            _violation(
                label,
                "skill-name",
                f"skill {skill!r} is not lowercase hyphen-case, 64 characters or fewer, with no '--'",
            )
        )
    if not _lens_ok(item.get("lens")):
        found.append(
            _violation(
                label,
                "unknown-lens",
                f"lens {item.get('lens')!r} is not valid; use one of {', '.join(sorted(LENSES))} "
                "or other:<kebab-name>",
            )
        )
    return found


def _content_violations(item: Payload, label: str, mode: str) -> list[Violation]:
    found: list[Violation] = []
    if not _is_text(item.get("claim")):
        found.append(_violation(label, "claim-missing", "claim must be a non-empty string"))
    if not _evidence_ok(item.get("evidence")):
        found.append(
            _violation(label, "evidence-invalid", "evidence must be a non-empty list of strings")
        )
    if mode == "knowledge" and not _is_text(item.get("baseline_case")):
        found.append(
            _violation(label, "baseline-case-missing", "knowledge mode needs a baseline_case")
        )
    return found


def _form_violations(item: Payload, label: str) -> list[Violation]:
    form = item.get("form")
    computable = item.get("computable")
    found: list[Violation] = []
    if not isinstance(computable, bool):
        found.append(_violation(label, "computable-type", "computable must be true or false"))
    if form not in FORMS:
        found.append(_violation(label, "form-invalid", f"form {form!r} is not one of {FORMS}"))
        return found
    if computable is True and form == "scaffold":
        found.append(
            _violation(
                label,
                "computable-needs-instrument",
                "a computable item cannot be scaffold-only; use instrument or both",
            )
        )
    if form in SCRIPT_FORMS:
        defect = script_defect(item.get("script"))
        if defect:
            found.append(_violation(label, "script-path", defect))
    elif not _is_text(item.get("why")):
        found.append(
            _violation(label, "scaffold-needs-why", "scaffold must state why it cannot be computed")
        )
    return found


def _script_missing(item: Payload, label: str, skills_root: Path) -> list[Violation]:
    """Flag an instrument or both item whose script file is absent (path already valid)."""
    form = item.get("form")
    if not isinstance(form, str) or form not in SCRIPT_FORMS:
        return []
    if script_defect(item.get("script")) is not None:
        return []
    skill = item.get("skill")
    if not isinstance(skill, str) or not valid_skill_name(skill):
        return []
    parts = PurePosixPath(item["script"].strip().replace("\\", "/")).parts
    target = skills_root / skill / Path(*parts)
    if target.is_file():
        return []
    return [_violation(label, "script-missing", f"{target.as_posix()} does not exist")]


def check_item(
    item: Payload, label: str, mode: str, seen: set[str], skills_root: Path | None
) -> list[Violation]:
    """Return every violation for one plan item."""
    found = _identity_violations(item, label, seen)
    found += _content_violations(item, label, mode)
    found += _form_violations(item, label)
    if skills_root is not None:
        found += _script_missing(item, label, skills_root)
    if _is_text(item.get("id")):
        seen.add(item["id"])
    return found


def _load_plan(path: str) -> Payload:
    try:
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read plan {path}: {exc}") from exc
    if not isinstance(plan, dict):
        raise ConfigError("plan top level must be a JSON object")
    items = plan.get("items")
    if not isinstance(items, list):
        raise ConfigError("plan.items must be a list")
    if plan.get("mode") not in MODES:
        raise ConfigError(f"plan.mode must be one of {', '.join(MODES)}")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigError(f"plan.items[{index}] must be an object")
    return plan


def check(args: argparse.Namespace) -> tuple[int, Payload]:
    if args.require_scripts and not args.skills_root:
        raise ConfigError("--require-scripts needs --skills-root")
    if args.skills_root and not args.require_scripts:
        raise ConfigError("--skills-root has no effect without --require-scripts")
    if args.skills_root and not Path(args.skills_root).is_dir():
        raise ConfigError(f"--skills-root is not a directory: {args.skills_root}")
    plan = _load_plan(args.plan)
    skills_root = Path(args.skills_root) if args.require_scripts else None
    items = plan["items"]
    seen: set[str] = set()
    violations: list[Violation] = []
    for index, item in enumerate(items):
        label = item["id"] if _is_text(item.get("id")) else f"#{index}"
        violations += check_item(item, label, plan["mode"], seen, skills_root)
    forms = {name: sum(1 for i in items if i.get("form") == name) for name in FORMS}
    computable = sum(1 for i in items if i.get("computable") is True)
    return (1 if violations else 0), {
        "violations": violations,
        "forms": forms,
        "computable_share": (computable / len(items)) if items else 0.0,
        "examined": {"items": len(items)},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        allow_abbrev=False, prog="bootstrap_forms", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser(
        "check", allow_abbrev=False, help="validate tool forms in a bootstrap plan"
    )
    p_check.add_argument("--plan", required=True, help="plan JSON file")
    p_check.add_argument("--skills-root", help="skills directory that holds <skill>/<script>")
    p_check.add_argument(
        "--require-scripts",
        action="store_true",
        help="flag instrument or both items whose script file is missing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, payload = check(args)
    except ConfigError as exc:
        print(json.dumps({"error": "config", "message": str(exc)}))
        return 2
    print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
