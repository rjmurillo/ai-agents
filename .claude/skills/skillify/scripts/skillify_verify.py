"""Read-back verification of a written SKILL.md for the skillify helper."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skillify_text import (
    Section,
    SkillifyError,
    count_items,
    first_sections,
    numbered_steps,
    parse_frontmatter,
    procedure_section,
)

DESCRIPTION_LEAD_CHARS = 200
MAX_NAME_CHARS = 64
MIN_LIST_ITEMS = 2
MODE_CREATE = "create"
MODE_PATCH = "patch"
MODES = (MODE_CREATE, MODE_PATCH)

REQUIRED_SECTIONS: tuple[str, ...] = (
    "triggers",
    "contract",
    "procedure",
    "anti-patterns",
    "pitfalls",
    "verification",
)

LIST_SECTIONS: tuple[str, ...] = ("anti-patterns", "pitfalls")

SOURCE_ONLY_TOOLS: tuple[str, ...] = ("skills_list", "skill_view", "skill_manage")

APPROVAL_RE = re.compile(r"\b(approv\w*|confirm\w*|consent|authori[sz]\w*)\b", re.IGNORECASE)

RECOVERY_RE = re.compile(r"\b(optional|recovery)\b", re.IGNORECASE)
# Verbs that act on an external or public system. A release or merge noun in a
# step is a false positive the author fixes by rewording the step.
EXTERNAL_RE = re.compile(
    r"\b(?:(?:publish|push|post|send|deploy|upload|comment|email)(?:s|es|ed|ing)?"
    r"|(?:merg|releas|shar)(?:e|es|ed|ing)"
    r"|open(?:s|ed|ing)? (?:a |the )?(?:pr|pull request)s?)\b",
    re.IGNORECASE,
)
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def resolve_skill_file(target: Path) -> Path:
    """Accept a SKILL.md path or its directory."""
    skill_file = target / "SKILL.md" if target.is_dir() else target
    if not skill_file.is_file():
        raise SkillifyError(f"no SKILL.md at {target}")
    return skill_file


def verify_skill(
    skill_file: Path,
    trigger: str,
    external_actions: bool,
    recovery_paths: bool = False,
    mode: str = MODE_CREATE,
) -> dict[str, Any]:
    """Read back a skill and check it.

    `create` checks the whole skeleton. `patch` is for an existing host skill
    that was edited. It keeps the name, description presence, the trigger
    anywhere in the description, source-only tool names, and the audit-driven
    approval and recovery checks. It skips the skeleton sections and the
    description-lead check, because host skills use their own layout. In patch mode a `Process` section stands in for a
    missing `Procedure` section.
    """
    if mode not in MODES:
        raise SkillifyError(f"mode must be one of: {', '.join(MODES)}")
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillifyError(f"cannot read {skill_file}: {exc}") from exc
    meta, body = parse_frontmatter(text)
    sections = first_sections(body)
    patching = mode == MODE_PATCH
    checks = [
        *_name_checks(meta.get("name", ""), skill_file.parent.name),
        *(_patch_checks(meta, trigger) if patching else _create_checks(meta, trigger, sections)),
        _tool_name_check(text),
    ]
    steps = _procedure_steps(sections, patching)
    if external_actions:
        checks.append(_approval_check(steps, patching))
    if recovery_paths:
        checks.append(_recovery_check(steps, patching))
    failures = [c["id"] for c in checks if not c["ok"]]
    return {
        "status": "FAIL" if failures else "PASS",
        "name": meta.get("name", ""),
        "trigger": trigger,
        "mode": mode,
        "path": str(skill_file),
        "failures": failures,
        "checks": checks,
    }


def _create_checks(
    meta: Mapping[str, str], trigger: str, sections: Mapping[str, Section]
) -> list[dict[str, Any]]:
    return [_description_check(meta.get("description", ""), trigger), *_section_checks(sections)]


def _patch_checks(meta: Mapping[str, str], trigger: str) -> list[dict[str, Any]]:
    description = _squash(meta.get("description", ""))
    wanted = _squash(trigger)
    return [
        _check("description_present", bool(description), "description must not be empty"),
        _check(
            "description_has_trigger",
            bool(wanted) and wanted in description,
            "the trigger phrase must appear in the description (anywhere, not only the lead)",
        ),
    ]


def _procedure_steps(sections: Mapping[str, Section], patching: bool) -> list[str]:
    section = procedure_section(sections, allow_process=patching)
    return numbered_steps(section.lines) if section else []


def _check(check_id: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"id": check_id, "ok": ok, "detail": detail}


def _name_checks(name: str, directory: str) -> list[dict[str, Any]]:
    shape = bool(NAME_RE.match(name)) and len(name) <= MAX_NAME_CHARS
    return [
        _check(
            "name_kebab_case",
            shape,
            f"name '{name}' must be kebab-case and at most {MAX_NAME_CHARS} characters",
        ),
        _check(
            "name_matches_directory",
            bool(name) and name == directory,
            f"name '{name}' vs directory '{directory}'",
        ),
    ]


def _description_check(description: str, trigger: str) -> dict[str, Any]:
    lead = _squash(description)[:DESCRIPTION_LEAD_CHARS]
    wanted = _squash(trigger)
    ok = bool(description.strip()) and bool(wanted) and wanted in lead
    return _check(
        "description_leads_with_trigger",
        ok,
        f"trigger phrase must appear in the first {DESCRIPTION_LEAD_CHARS} description characters",
    )


def _squash(text: str) -> str:
    return " ".join(text.lower().split())


def _section_checks(sections: Mapping[str, Section]) -> list[dict[str, Any]]:
    checks = [
        _check(f"section_{name}", name in sections, f"section '{name}' present")
        for name in REQUIRED_SECTIONS
    ]
    for name in LIST_SECTIONS:
        found = count_items(sections[name].lines) if name in sections else 0
        checks.append(
            _check(
                f"items_{name}",
                found >= MIN_LIST_ITEMS,
                f"'{name}' has {found} item(s); needs {MIN_LIST_ITEMS}",
            )
        )
    return checks


def _tool_name_check(text: str) -> dict[str, Any]:
    leaked = [tool for tool in SOURCE_ONLY_TOOLS if tool in text]
    return _check(
        "no_source_only_tool_names",
        not leaked,
        f"source-only tool names present: {', '.join(leaked)}" if leaked else "none present",
    )


def _where(patching: bool) -> str:
    return "Procedure (or Process)" if patching else "Procedure"


def _approval_problem(steps: list[str]) -> str | None:
    """Return why approval is missing or late, or None when it precedes the first external step."""
    index = next((i for i, step in enumerate(steps) if EXTERNAL_RE.search(step)), None)
    if index is None:
        return "name the external or public action (for example publish or push) in a numbered step"
    verb = EXTERNAL_RE.search(steps[index])
    earlier = [*steps[:index], steps[index][: verb.start()] if verb else ""]
    if any(APPROVAL_RE.search(text) for text in earlier):
        return None
    return "an approval or confirmation word must come before the first external action"


def _approval_check(steps: list[str], patching: bool = False) -> dict[str, Any]:
    problem = _approval_problem(steps)
    return _check(
        "approval_gate_present",
        problem is None,
        problem or f"approval precedes the first external action in a {_where(patching)} step",
    )


def _recovery_check(steps: list[str], patching: bool = False) -> dict[str, Any]:
    return _check(
        "recovery_path_marked",
        any(RECOVERY_RE.search(step) for step in steps),
        f"recovery paths must be marked 'optional' or 'recovery' in a numbered "
        f"{_where(patching)} step",
    )
