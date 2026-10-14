"""Read-back verification of a written SKILL.md for the skillify helper."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skillify_text import (
    ParsedSteps,
    Section,
    SkillifyError,
    Step,
    approval_prose,
    count_items,
    first_sections,
    outside_step_lines,
    parse_frontmatter,
    parse_steps,
    procedure_section,
    split_sections,
    step_section_count,
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

RECOVERY_RE = re.compile(r"\b(optional|recovery)\b", re.IGNORECASE)
# The author marks each step that acts on an external or public system with
# this literal tag (fenced text under the step counts). The tag is the contract; EXTERNAL_RE below is only a
# backstop that makes a missing tag loud.
TAG_RE = re.compile(r"\(external\)", re.IGNORECASE)
# A step that asks the user for approval carries this tag. Only prose counts,
# never fenced text, and the step must come strictly before the external step.
APPROVAL_TAG_RE = re.compile(r"\(approval\)", re.IGNORECASE)
_GAP = r"(?:[\w-]+\s+){0,4}?"
_PR_NOUNS = r"(?:pr|mr|pull[\s-]request|issue|ticket|bug)s?"
_SHARED_NOUNS = (
    r"(?:cache|state|memory|drive|folder|fixtures?|librar(?:y|ies)|config"
    r"|modules?|code|helpers?|utils?)"
)
# Backstop for steps that look external but carry no tag. It errs broad: a
# false positive asks the author to tag or reword a step, a miss only costs
# the loud failure. Hyphenated forms ("force-push", "auto-merge") match on
# purpose. The only exclusions are exact noun phrases ("merge conflicts",
# "release notes", "shared cache"), which never hide a verb.
EXTERNAL_RE = re.compile(
    r"\b(?:(?:publish|push|send|upload|comment|e-?mail|mail|post)(?:s|es|ed|ing)?|sent|deploy\w*"
    r"|delet(?:e|es|ed|ing)"
    r"|\w*merg(?:e|es|ed|ing)(?!\s+(?:conflicts?|base)\b)"
    r"|releas(?:e|es|ed|ing)(?!\s+notes?\b)"
    r"|shar(?:e|es|ing)"
    rf"|shared(?!\s+{_SHARED_NOUNS}\b)"
    rf"|(?:re-?)?(?:open|fil|creat|submitt?|rais)\w*\s+{_GAP}{_PR_NOUNS}"
    r"|gh\s+(?:pr|issue)\s+(?:create|merge|close|comment|edit)"
    r"|clos(?:e|es|ed|ing)|repl(?:y|ies|ied|ying)|notif(?:y|ies|ied|ying)"
    r"|announc(?:e|es|ed|ing)|ship(?:s|ped|ping)?|appl(?:y|ies|ied|ying)"
    r"|tag(?:s|ged|ging)?\s+(?:[\w-]+\s+){0,2}?releases?)\b",
    re.IGNORECASE,
)
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
OUTSIDE_ITEM_RE = re.compile(r"^\d+[.)]\s")


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
    checks.append(_single_section_check(body, patching))
    parsed = _procedure_steps(sections, patching)
    if external_actions:
        checks.append(_approval_check(parsed.steps, patching))
        checks.append(_untagged_check(parsed.steps))
        outside = _outside_lines(body, patching)
        checks.append(_outside_steps_check(parsed, outside, patching))
    if external_actions or not patching:
        checks.append(_numbering_check(parsed.steps))
    if recovery_paths:
        checks.append(_recovery_check(parsed.steps, patching))
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


def _procedure_steps(sections: Mapping[str, Section], patching: bool) -> ParsedSteps:
    section = procedure_section(sections, allow_process=patching)
    return parse_steps(section.lines if section else [])


def _outside_lines(body: str, patching: bool) -> list[str]:
    """Lines outside the step section that the backstop scans.

    Create mode scans every instruction line. Patch mode keeps only numbered
    items: a host skill's tables and prose are reference text, but a numbered
    list in another section is still a procedure an agent follows.
    """
    lines = outside_step_lines(body, patching)
    return [line for line in lines if OUTSIDE_ITEM_RE.match(line)] if patching else lines


def _single_section_check(body: str, patching: bool) -> dict[str, Any]:
    count = step_section_count(split_sections(body), allow_process=patching)
    return _check(
        "single_step_section",
        count <= 1,
        f"the {_where(patching)} heading appears {count} times; keep one steps section",
    )


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


def _approval_problem(steps: tuple[Step, ...], where: str) -> str | None:
    """Return why the approval gate fails, or None when it holds.

    Every step tagged `(external)` needs a step tagged `(approval)` strictly
    before it, never the same step. No step carries both tags.
    """
    external = [i for i, step in enumerate(steps) if TAG_RE.search(step.full)]
    approval = [
        i for i, step in enumerate(steps) if APPROVAL_TAG_RE.search(approval_prose(step.text))
    ]
    both = [i for i in external if i in approval]
    if both:
        return f"step {both[0] + 1} is tagged both (external) and (approval); split it"
    if not external:
        return f"tag each external step with (external) in a numbered {where} step"
    if not approval:
        return "tag the step that asks the user with (approval)"
    late = next((i for i in external if not any(j < i for j in approval)), None)
    if late is not None:
        return f"step {late + 1} is tagged (external) but no (approval) step comes before it"
    return None


def _approval_check(steps: tuple[Step, ...], patching: bool = False) -> dict[str, Any]:
    where = _where(patching)
    problem = _approval_problem(steps, where)
    return _check(
        "approval_gate_present",
        problem is None,
        problem or f"every (external) step has an (approval) step before it in a {where} step",
    )


def _untagged_check(steps: tuple[Step, ...]) -> dict[str, Any]:
    untagged = [
        str(i + 1)
        for i, step in enumerate(steps)
        if EXTERNAL_RE.search(step.full) and not TAG_RE.search(step.full)
    ]
    return _check(
        "external_step_untagged",
        not untagged,
        f"step {', '.join(untagged)} looks external: add (external) or reword the step"
        if untagged
        else "no untagged step looks external",
    )


def _outside_steps_check(
    parsed: ParsedSteps, outside: list[str], patching: bool = False
) -> dict[str, Any]:
    """Patch mode reads only loose lines in the step section; create mode reads the whole body."""
    headings = [] if patching else parsed.headings
    stray = [line for line in [*parsed.loose, *headings, *outside] if EXTERNAL_RE.search(line)]
    return _check(
        "external_outside_steps",
        not stray,
        f"external action outside a numbered step ({stray[0][:60]!r}): "
        "move the action into a numbered Procedure step and tag it"
        if stray
        else "no external action outside numbered steps",
    )


def _numbering_check(steps: tuple[Step, ...]) -> dict[str, Any]:
    """Numerals run 1, 2, 3 in order within each subheading group.

    A group starts at 1 (phases restart) or continues from the previous group.
    """
    groups: dict[int, list[int]] = {}
    for step in steps:
        groups.setdefault(step.group, []).append(step.number)
    bad = _bad_numbering(list(groups.values()))
    return _check(
        "steps_numbered_in_order",
        not bad,
        f"step numerals must run 1, 2, 3 in order; found {bad}" if bad else "numerals in order",
    )


def _bad_numbering(groups: list[list[int]]) -> list[int]:
    previous_end = 0
    for numbers in groups:
        first = numbers[0]
        run = list(range(first, first + len(numbers)))
        if numbers != run or first not in (1, previous_end + 1):
            return numbers
        previous_end = numbers[-1]
    return []


def _recovery_check(steps: tuple[Step, ...], patching: bool = False) -> dict[str, Any]:
    return _check(
        "recovery_path_marked",
        any(RECOVERY_RE.search(step.text) for step in steps),
        f"recovery paths must be marked 'optional' or 'recovery' in a numbered "
        f"{_where(patching)} step",
    )
