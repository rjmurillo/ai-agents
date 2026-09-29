"""Text scanning for the required-context lint.

Answers one question about a piece of workflow text: which outside sources does
it read. Three sources count, all named by ADR-101 requirement 1: another job's
output (`needs.*.outputs`), the event name, and the actor. The environment
spellings of the last two are matched as well, because a step body reads
`GITHUB_EVENT_NAME` and `GITHUB_ACTOR` without an expression, and that is how a
condition is relocated out of an `if:`.

Standard library only apart from the ``re`` and ``collections`` imports below, so
the caller keeps its own dependency surface.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

# Bracket forms (`needs['job'].outputs`) are equivalent to dotted access in the
# expression language, so both spellings are matched. `GITHUB_EVENT_NAME` and
# `GITHUB_ACTOR` are the environment spellings of the same two values; a step
# body reads them without an expression, which is how the relocation happens.
# The expression language is case-insensitive for context and property names, so
# `github.Actor` and `NEEDS.x.OUTPUTS` are the same reads and are matched too.
# `GITHUB_TRIGGERING_ACTOR` and `github.triggering_actor` are the actor of a
# re-run, which is a different value but the same kind of outside source.
FLAGS = re.IGNORECASE
NEEDS_OUTPUTS = re.compile(
    r"\bneeds(?:\.[A-Za-z0-9_-]+|\[\s*['\"][^'\"]+['\"]\s*\])\.outputs\b", FLAGS
)
EVENT_NAME = re.compile(
    r"\bgithub(?:\.event_name|\[\s*['\"]event_name['\"]\s*\])|\bGITHUB_EVENT_NAME\b",
    FLAGS,
)
ACTOR = re.compile(
    r"\bgithub(?:\.(?:triggering_)?actor|\[\s*['\"](?:triggering_)?actor['\"]\s*\])"
    r"|\bGITHUB_(?:TRIGGERING_)?ACTOR\b",
    FLAGS,
)
STEP_OUTPUT = re.compile(
    r"\bsteps(?:\.([A-Za-z0-9_-]+)|\[\s*['\"]([^'\"]+)['\"]\s*\])\.outputs\b", FLAGS
)
ENV_READ = re.compile(r"\benv\.([A-Za-z0-9_]+)\b", FLAGS)

SOURCES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("needs.*.outputs", NEEDS_OUTPUTS),
    ("github.event_name", EVENT_NAME),
    ("github.actor", ACTOR),
)
JOB_SOURCES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("needs.*.outputs", NEEDS_OUTPUTS),
)
STEP_BODY_KEYS = ("env", "with", "run", "if")


# `yaml.safe_load` expands an alias into a shared reference, so a small file can
# describe a structure whose `str()` is exponentially large. Walk the scalars
# under a node budget and a depth cap instead of stringifying the container.
MAX_NODES = 10_000
MAX_DEPTH = 32


def text(value: object) -> str:
    """Join the scalar leaves of ``value`` into one string, bounded in work done.

    A bare boolean or number is a valid `if:` value in YAML. It references
    nothing, so it is coerced to text rather than skipped as a type error.
    """
    parts: list[str] = []
    stack: list[tuple[object, int]] = [(value, 0)]
    budget = MAX_NODES
    while stack and budget > 0:
        node, depth = stack.pop()
        budget -= 1
        if isinstance(node, Mapping):
            if depth < MAX_DEPTH:
                stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            if depth < MAX_DEPTH:
                stack.extend((child, depth + 1) for child in node)
        else:
            parts.append(str(node))
    return "\n".join(parts)


def sources_in(text: str, sources: Sequence[tuple[str, re.Pattern[str]]]) -> list[str]:
    return [name for name, pattern in sources if pattern.search(text)]


def condition_sources(
    condition: object, sources: Sequence[tuple[str, re.Pattern[str]]]
) -> list[str]:
    return sources_in(text(condition), sources)


def step_body_text(step: Mapping[str, Any]) -> str:
    return "\n".join(text(step[key]) for key in STEP_BODY_KEYS if key in step)


def env_sources(text: str, tainted_env: Mapping[str, list[str]]) -> list[str]:
    found: list[str] = []
    for match in ENV_READ.finditer(text):
        for source in tainted_env.get(match.group(1), []):
            if source not in found:
                found.append(source)
    return found
