"""Static checks behind the agentskills.io conformance catalog.

Each check takes a SkillDoc and returns a list of problems. An empty list is a
pass. A check raises NotApplicableError when the skill has nothing to check (no
compatibility field, no scripts directory) and NotEvaluatedError when it cannot
decide (the frontmatter did not parse). No check runs code from the skill.
"""

from __future__ import annotations

import functools
import posixpath
import re
import unicodedata
from collections.abc import Callable

from _conformance_parse import Scalar, SkillDoc, core_type
from _constants import (
    BODY_MAX_LINES,
    BODY_TOKEN_BUDGET,
    CHARS_PER_TOKEN_ESTIMATE,
    COMPATIBILITY_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
)

SPEC_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)

_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


class NotApplicableError(Exception):
    """The skill has nothing this rule checks."""


class NotEvaluatedError(Exception):
    """The rule could not be decided for this skill."""


def _fields(doc: SkillDoc) -> dict[str, object]:
    if not doc.has_frontmatter:
        raise NotEvaluatedError("SKILL.md has no frontmatter")
    if doc.parse_error:
        raise NotEvaluatedError(f"frontmatter did not parse: {doc.parse_error}")
    if doc.unsupported or doc.fields is None:
        raise NotEvaluatedError(f"frontmatter uses an unsupported construct: {doc.unsupported}")
    return doc.fields


def _string_field(doc: SkillDoc, key: str, *, required: bool) -> str:
    fields = _fields(doc)
    if key not in fields or fields[key] is None:
        if required:
            return ""
        raise NotApplicableError(f"no {key} field")
    value = fields[key]
    if not isinstance(value, str) or core_type(value) is not None:
        raise _FieldTypeError(f"{key} must be a string, got {_describe(value)}")
    return str(value)


class _FieldTypeError(Exception):
    pass


def _describe(value: object) -> str:
    if isinstance(value, dict):
        return "a mapping"
    if isinstance(value, list):
        return "a list"
    kind = core_type(value)
    return f"an unquoted {kind}" if kind else "a string"


Check = Callable[[SkillDoc], list[str]]


def _guard(check: Check) -> Check:
    """Turn a wrong field type into a reported problem instead of an exception."""

    @functools.wraps(check)
    def wrapper(doc: SkillDoc) -> list[str]:
        try:
            return check(doc)
        except _FieldTypeError as exc:
            return [str(exc)]

    return wrapper


def _name(doc: SkillDoc) -> str:
    return unicodedata.normalize("NFKC", _string_field(doc, "name", required=True).strip())


# Spec: SKILL.md and frontmatter -------------------------------------------


def skill_md_present(doc: SkillDoc) -> list[str]:
    return [] if doc.skill_md else ["no SKILL.md in the skill directory"]


def frontmatter_delimited(doc: SkillDoc) -> list[str]:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    return [doc.frontmatter_error] if doc.frontmatter_error else []


def frontmatter_mapping(doc: SkillDoc) -> list[str]:
    if not doc.has_frontmatter:
        raise NotEvaluatedError("SKILL.md has no frontmatter")
    if doc.unsupported:
        raise NotEvaluatedError(f"unsupported YAML construct: {doc.unsupported}")
    return [doc.parse_error] if doc.parse_error else []


def frontmatter_known_fields(doc: SkillDoc) -> list[str]:
    extra = sorted(set(_fields(doc)) - SPEC_FIELDS)
    if not extra:
        return []
    return [f"fields outside the spec: {', '.join(extra)}; move client properties under metadata"]


# Spec: name ----------------------------------------------------------------


@_guard
def name_present(doc: SkillDoc) -> list[str]:
    return [] if _name(doc) else ["name is missing or empty"]


@_guard
def name_max_length(doc: SkillDoc) -> list[str]:
    name = _name(doc)
    if len(name) > NAME_MAX_LENGTH:
        return [f"name has {len(name)} characters; the limit is {NAME_MAX_LENGTH}"]
    return []


@_guard
def name_charset(doc: SkillDoc) -> list[str]:
    name = _name(doc)
    if name != name.lower():
        return [f"name {name!r} must be lowercase"]
    bad = sorted({char for char in name if not (char.isalnum() or char == "-")})
    return (
        [f"name {name!r} has characters other than letters, digits, and hyphens: {''.join(bad)}"]
        if bad
        else []
    )


@_guard
def name_hyphen_edges(doc: SkillDoc) -> list[str]:
    name = _name(doc)
    return (
        [f"name {name!r} starts or ends with a hyphen"]
        if name[:1] == "-" or name[-1:] == "-"
        else []
    )


@_guard
def name_no_double_hyphen(doc: SkillDoc) -> list[str]:
    name = _name(doc)
    return [f"name {name!r} contains '--'"] if "--" in name else []


@_guard
def name_matches_directory(doc: SkillDoc) -> list[str]:
    name = _name(doc)
    directory = unicodedata.normalize("NFKC", doc.directory.name)
    if name and name != directory:
        return [f"name {name!r} does not match the directory name {directory!r}"]
    return []


# Spec: description, compatibility, metadata, allowed-tools -----------------


@_guard
def description_present(doc: SkillDoc) -> list[str]:
    value = _string_field(doc, "description", required=True)
    return [] if value.strip() else ["description is missing or empty"]


@_guard
def description_max_length(doc: SkillDoc) -> list[str]:
    value = _string_field(doc, "description", required=True)
    if len(value) > DESCRIPTION_MAX_LENGTH:
        return [f"description has {len(value)} characters; the limit is {DESCRIPTION_MAX_LENGTH}"]
    return []


@_guard
def compatibility_length(doc: SkillDoc) -> list[str]:
    value = _string_field(doc, "compatibility", required=False)
    if not value.strip():
        return ["compatibility is empty; omit the field instead"]
    if len(value) > COMPATIBILITY_MAX_LENGTH:
        return [
            f"compatibility has {len(value)} characters; the limit is {COMPATIBILITY_MAX_LENGTH}"
        ]
    return []


def metadata_string_map(doc: SkillDoc) -> list[str]:
    fields = _fields(doc)
    if fields.get("metadata") is None:
        raise NotApplicableError("no metadata field")
    metadata = fields["metadata"]
    if not isinstance(metadata, dict):
        return [f"metadata must be a mapping, got {_describe(metadata)}"]
    problems = []
    for key, value in metadata.items():
        if not isinstance(value, Scalar) or core_type(value):
            problems.append(f"metadata.{key} must be a string, got {_describe(value)}")
    return problems


def allowed_tools_string(doc: SkillDoc) -> list[str]:
    fields = _fields(doc)
    if fields.get("allowed-tools") is None:
        raise NotApplicableError("no allowed-tools field")
    value = fields["allowed-tools"]
    if not isinstance(value, Scalar):
        return [f"allowed-tools must be a space-separated string, got {_describe(value)}"]
    return []


# Spec: body and file references -------------------------------------------


def body_max_lines(doc: SkillDoc) -> list[str]:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    count = len(doc.text.splitlines())
    if count >= BODY_MAX_LINES:
        return [f"SKILL.md has {count} lines; keep it under {BODY_MAX_LINES}"]
    return []


def body_token_budget(doc: SkillDoc) -> list[str]:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    estimate = len(doc.body) // CHARS_PER_TOKEN_ESTIMATE
    if estimate >= BODY_TOKEN_BUDGET:
        return [
            f"body is about {estimate} tokens (characters / 4); keep it under {BODY_TOKEN_BUDGET}"
        ]
    return []


def strip_fenced_code(text: str) -> str:
    """Blank out fenced code blocks so links inside them are not read."""
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        match = _FENCE_RE.match(line)
        if fence is None and match:
            fence = match.group(2)[0] * len(match.group(2))
            out.append("")
            continue
        if fence is not None:
            if match and match.group(2).startswith(fence) and not match.group(3).strip():
                fence = None
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def local_links(markdown: str) -> list[str]:
    """Return relative link targets, without anchors, outside fenced code."""
    targets: list[str] = []
    for raw in _LINK_RE.findall(strip_fenced_code(markdown)):
        target = raw.split("#", 1)[0].split("?", 1)[0]
        if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
            continue
        if target not in targets:
            targets.append(target)
    return targets


def body_or_skip(doc: SkillDoc) -> str:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    return doc.body


def references_relative(doc: SkillDoc) -> list[str]:
    problems = []
    for target in local_links(body_or_skip(doc)):
        normalized = posixpath.normpath(target)
        if target.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", target):
            problems.append(f"absolute path in a link: {target}")
        elif normalized == ".." or normalized.startswith("../"):
            problems.append(f"link leaves the skill directory: {target}")
    return problems


def references_resolve(doc: SkillDoc) -> list[str]:
    problems = []
    for target in local_links(body_or_skip(doc)):
        normalized = posixpath.normpath(target)
        if target.startswith("/") or normalized.startswith(".."):
            continue
        if not (doc.directory / normalized).exists():
            problems.append(f"link target does not exist: {target}")
    return problems


def references_one_level(doc: SkillDoc) -> list[str]:
    direct: set[str] = set()
    problems = []
    for target in local_links(body_or_skip(doc)):
        normalized = posixpath.normpath(target)
        if normalized.startswith("..") or target.startswith("/"):
            continue
        direct.add(normalized)
        if len(normalized.split("/")) > 2:
            problems.append(f"link is nested more than one directory deep: {target}")
    for linked in sorted(direct):
        path = doc.directory / linked
        if path.suffix.lower() != ".md" or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for target in local_links(text):
            chained = posixpath.normpath(posixpath.join(posixpath.dirname(linked), target))
            if chained.endswith(".md") and chained not in direct and chained != "SKILL.md":
                if (doc.directory / chained).is_file():
                    problems.append(f"{chained} is reachable only through {linked}")
    return problems
