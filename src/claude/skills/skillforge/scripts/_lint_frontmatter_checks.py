"""Constants, helpers, and rule checks for lint_skill_frontmatter.py.

Kept apart from the CLI so each file stays small. Every check takes a parsed
SkillDoc and returns a list of problems, or raises NotApplicableError or
NotEvaluatedError.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import _conformance_parse as subset

# --- limits and grammars ------------------------------------------------------
# These mirror the host repository's gates. In rjmurillo/ai-agents a test reads
# both sides and fails when they differ (tests/skills/skillforge/
# test_lint_skill_frontmatter_mirror.py), so a change to one cannot drift.

SKILL_BYTE_LIMIT = 24_576
# Generated mirrors (Copilot CLI, Codex, and others) rewrite tool names and
# paths, so they render about 100 bytes larger than the canonical SKILL.md.
# Leaving 256 bytes keeps a mirror under the cap when the canonical file fits.
SKILL_BYTE_HEADROOM = 256

ARTIFACT_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
PATH_RE = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*/?")
SOURCES: tuple[str, ...] = ("skill", "user", "repo")
INPUT_KEYS: frozenset[str] = frozenset({"source", "required"})
OUTPUT_KEYS: frozenset[str] = frozenset({"path"})

CAPABILITY_KINDS: tuple[str, ...] = (
    "orchestrator",
    "specialized-implementation",
    "reusable-primitive",
    "cross-cutting-rule",
)
CAPABILITY_KEYS: tuple[str, ...] = (
    "kind",
    "owns",
    "depends-on",
    "status",
    "replaced-by",
    "replacement-platform",
    "replacement-owner",
    "validation",
)

HANDOFF_HEADING = "## Handoff"
HANDOFF_RE = re.compile(
    r"Writes: (?P<writes>none|`[^`]+`(?:, `[^`]+`)*)\. Next: (?P<next>none|`/[a-z][a-z0-9-]*`)\."
)

_QUOTED = re.compile(r"\"([^\"]+)\"|`([^`]+)`")
_WORD = re.compile(r"[A-Za-z0-9]+")
_REDIRECT_MARKER = "Do NOT"
_MIN_PHRASE_WORDS = 2
_REDIRECT = re.compile(r"\b(?:do not|don't|not for)\b", re.IGNORECASE)

LEVELS = ("MUST", "SHOULD")


class NotApplicableError(Exception):
    """The skill declares nothing this rule checks."""


class NotEvaluatedError(Exception):
    """The rule could not decide."""


# --- helpers ------------------------------------------------------------------


def _fields(doc: subset.SkillDoc) -> dict[str, object]:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    if doc.unsupported or doc.parse_error or doc.frontmatter_error:
        raise NotEvaluatedError("frontmatter does not parse; see fm.subset-parse")
    if doc.fields is None:
        raise NotEvaluatedError("no frontmatter")
    return doc.fields


def _metadata(doc: subset.SkillDoc) -> dict[str, object]:
    metadata = _fields(doc).get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _routing(doc: subset.SkillDoc) -> dict[str, object]:
    routing = _metadata(doc).get("routing")
    return routing if isinstance(routing, dict) else {}


def _is_bool(value: object) -> bool:
    return subset.core_type(value) == "bool"


def _empty(value: object) -> bool:
    """An entry with nothing after the colon parses as None."""
    return value is None


# --- checks -------------------------------------------------------------------


def subset_parse(doc: subset.SkillDoc) -> list[str]:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    problem = doc.unsupported or doc.parse_error or doc.frontmatter_error
    if problem:
        return [
            f"{problem}; use block mappings and block lists of plain scalars, "
            "and key a list of records by name instead of listing mappings"
        ]
    return []


def _size_exception(doc: subset.SkillDoc) -> bool:
    """A skill may declare `size-exception: true`; the host's size gate audits its reason."""
    fields = doc.fields if isinstance(doc.fields, dict) else {}
    return (
        _is_bool(fields.get("size-exception")) and str(fields["size-exception"]).lower() == "true"
    )


def size_bytes(doc: subset.SkillDoc) -> list[str]:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    if _size_exception(doc):
        raise NotApplicableError("size-exception: true is declared")
    size = len(doc.text.encode("utf-8"))
    if size > SKILL_BYTE_LIMIT:
        return [
            f"SKILL.md is {size} bytes; the cap is {SKILL_BYTE_LIMIT}. Move procedure, "
            "tables, and examples to references/, or remove text another section repeats"
        ]
    return []


def size_headroom(doc: subset.SkillDoc) -> list[str]:
    if doc.skill_md is None:
        raise NotEvaluatedError("no SKILL.md")
    if _size_exception(doc):
        raise NotApplicableError("size-exception: true is declared")
    size = len(doc.text.encode("utf-8"))
    left = SKILL_BYTE_LIMIT - size
    if 0 <= left < SKILL_BYTE_HEADROOM:
        return [
            f"SKILL.md leaves {left} bytes under the cap; generated mirrors render "
            f"larger, so keep at least {SKILL_BYTE_HEADROOM}"
        ]
    return []


def _entry_problems(field: str, name: object, value: object) -> list[str]:
    if not isinstance(name, str) or not ARTIFACT_RE.fullmatch(name):
        return [f"{field} key {name!r} must be a lowercase kebab-case artifact name"]
    where = f"{field}.{name}"
    if _empty(value):
        return []
    if not isinstance(value, dict):
        return [f"{where} must be empty or a mapping of options, not {type(value).__name__}"]
    allowed = INPUT_KEYS if field == "inputs" else OUTPUT_KEYS
    problems = [f"{where} has unknown option {key!r}" for key in value if key not in allowed]
    if "path" in value:
        path = value["path"]
        if not isinstance(path, str) or not PATH_RE.fullmatch(path):
            problems.append(
                f"{where}.path {path!r} must be lowercase and relative to the artifact root"
            )
    if "source" in value and value["source"] not in SOURCES:
        problems.append(f"{where}.source {value['source']!r} must be one of {', '.join(SOURCES)}")
    if "required" in value and not _is_bool(value["required"]):
        problems.append(f"{where}.required must be true or false")
    return problems


def artifacts_shape(doc: subset.SkillDoc) -> list[str]:
    metadata = _metadata(doc)
    if "inputs" not in metadata and "outputs" not in metadata:
        raise NotApplicableError("no inputs or outputs")
    problems: list[str] = []
    for field in ("inputs", "outputs"):
        if field not in metadata:
            continue
        value = metadata[field]
        if not isinstance(value, dict):
            problems.append(f"{field} must be a mapping keyed by artifact name")
            continue
        for name, entry in value.items():
            problems.extend(_entry_problems(field, name, entry))
    return problems


def capability_shape(doc: subset.SkillDoc) -> list[str]:
    metadata = _metadata(doc)
    if "capability" not in metadata:
        raise NotApplicableError("no capability block")
    block = metadata["capability"]
    if not isinstance(block, dict):
        return ["capability must be a block mapping"]
    problems = [
        f"capability has unknown key {key!r}" for key in block if key not in CAPABILITY_KEYS
    ]
    if block.get("kind") not in CAPABILITY_KINDS:
        problems.append(f"capability.kind must be one of {', '.join(CAPABILITY_KINDS)}")
    return problems


def intents_role(doc: subset.SkillDoc) -> list[str]:
    routing = _routing(doc)
    if "intents" not in routing:
        raise NotApplicableError("no intents")
    if routing.get("role") != "front-door":
        return [f"intents are only valid on role front-door, not {routing.get('role')!r}"]
    intents = routing["intents"]
    if not isinstance(intents, list) or not intents:
        return ["intents must be a non-empty list"]
    return [
        f"intent {item!r} must be a non-empty string" for item in intents if not str(item).strip()
    ]


def _resolver() -> ModuleType:
    """Load autoplan's resolver from this plugin for its tokenizer and matcher."""
    script = Path(__file__).resolve().parents[2] / "autoplan" / "scripts" / "resolve_route.py"
    if not script.is_file():
        raise NotEvaluatedError("autoplan's resolve_route.py is not installed beside skillforge")
    spec = importlib.util.spec_from_file_location("_lint_resolve_route", script)
    if spec is None or spec.loader is None:
        raise NotEvaluatedError("cannot load resolve_route.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def trigger_phrases(description: str) -> tuple[str, ...]:
    """Return the trigger phrases a description advertises.

    The same grammar the host repository's Skill Trigger Phrase Resolution
    gate uses: every phrase in double quotes or backticks before the first
    "Do NOT", with two or more words, skipping any that holds `/` or `.`
    (a command or a path, not something a user says). Duplicates drop.
    """
    cut = description.find(_REDIRECT_MARKER)
    phrases: list[str] = []
    for match in _QUOTED.finditer(description):
        if cut != -1 and match.start() > cut:
            continue
        phrase = (match.group(1) or match.group(2)).strip()
        if "/" in phrase or "." in phrase:
            continue
        if len(_WORD.findall(phrase)) < _MIN_PHRASE_WORDS:
            continue
        if phrase not in phrases:
            phrases.append(phrase)
    return tuple(phrases)


def phrases_routable(doc: subset.SkillDoc) -> list[str]:
    routing = _routing(doc)
    intents = routing.get("intents")
    if not isinstance(intents, list) or not intents:
        raise NotApplicableError("no intents to route trigger phrases")
    description = _fields(doc).get("description")
    phrases = trigger_phrases(description if isinstance(description, str) else "")
    if not phrases:
        return [
            "description has intents but quotes no trigger phrase; quote the phrases "
            "users type so they can be checked against the intents"
        ]
    resolver = _resolver()
    tokenized = [resolver._tokenize(str(intent)) for intent in intents]
    problems = []
    for phrase in phrases:
        request = resolver._tokenize(phrase)
        if not any(resolver._matches_ordered(request, intent) for intent in tokenized):
            problems.append(f"trigger phrase {phrase!r} matches none of the skill's own intents")
    return problems


def handoff_shape(doc: subset.SkillDoc) -> list[str]:
    lines = doc.body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == HANDOFF_HEADING:
            following = [item.strip() for item in lines[index + 1 :] if item.strip()]
            first = following[0] if following else ""
            if not first.startswith("Writes:"):
                raise NotApplicableError("the Handoff section is prose, not a Writes/Next line")
            if HANDOFF_RE.fullmatch(first):
                return []
            return [f'Handoff line {first!r} must read "Writes: `a`, `b`. Next: `/skill`."']
    raise NotApplicableError("no Handoff section")


def description_redirect(doc: subset.SkillDoc) -> list[str]:
    description = _fields(doc).get("description")
    if not isinstance(description, str) or not description.strip():
        raise NotEvaluatedError("no description")
    user_facing = _routing(doc).get("user-facing")
    if _is_bool(user_facing) and str(user_facing).lower() == "false":
        raise NotApplicableError("not user-facing")
    if _REDIRECT.search(description):
        return []
    return [
        "description has no 'Do NOT use ... (use X)' sentence; name the sibling a user "
        "or model is most likely to confuse with this skill"
    ]
