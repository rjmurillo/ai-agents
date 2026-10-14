"""Read-back verification of a written SKILL.md for the skillify helper."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skillify_text import Section, SkillifyError, count_items, parse_frontmatter, split_sections

DESCRIPTION_LEAD_CHARS = 200
MAX_NAME_CHARS = 64
MIN_LIST_ITEMS = 2

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

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def resolve_skill_file(target: Path) -> Path:
    """Accept a SKILL.md path or its directory."""
    skill_file = target / "SKILL.md" if target.is_dir() else target
    if not skill_file.is_file():
        raise SkillifyError(f"no SKILL.md at {target}")
    return skill_file


def verify_skill(skill_file: Path, trigger: str, external_actions: bool) -> dict[str, Any]:
    """Read back a written skill and check the structural contract."""
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillifyError(f"cannot read {skill_file}: {exc}") from exc
    meta, body = parse_frontmatter(text)
    sections = {s.name: s for s in split_sections(body)}
    checks = [
        *_name_checks(meta.get("name", ""), skill_file.parent.name),
        _description_check(meta.get("description", ""), trigger),
        *_section_checks(sections),
        _tool_name_check(text),
    ]
    if external_actions:
        checks.append(_approval_check(body))
    failures = [c["id"] for c in checks if not c["ok"]]
    return {
        "status": "FAIL" if failures else "PASS",
        "name": meta.get("name", ""),
        "trigger": trigger,
        "path": str(skill_file),
        "failures": failures,
        "checks": checks,
    }


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


def _approval_check(body: str) -> dict[str, Any]:
    return _check(
        "approval_gate_present",
        bool(APPROVAL_RE.search(body)),
        "external or public actions need an approval or confirmation gate in the text",
    )
