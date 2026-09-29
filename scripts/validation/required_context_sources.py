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
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
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
# `needs.*.outputs` is the object-filter spelling the ADR itself uses. A whole
# context dumped with `toJSON(needs)` or `toJSON(github)`, and a computed index
# such as `github[format('event_{0}', 'name')]`, reach the same values without
# naming them, so they count as reads of every source they could expose.
_DUMP_NEEDS = r"|\btoJSON\(\s*needs\b|\bneeds\[\s*(?!['\"\s])"
_DUMP_GITHUB = r"|\btoJSON\(\s*github\b|\bgithub\[\s*(?!['\"\s])"
NEEDS_OUTPUTS = re.compile(
    r"\bneeds(?:\.[A-Za-z0-9_*-]+|\[\s*['\"][^'\"]+['\"]\s*\])\.outputs\b" + _DUMP_NEEDS,
    FLAGS,
)
EVENT_NAME = re.compile(
    r"\bgithub(?:\.event_name\b|\[\s*['\"]event_name['\"]\s*\])|\bGITHUB_EVENT_NAME\b"
    + _DUMP_GITHUB,
    FLAGS,
)
ACTOR = re.compile(
    r"\bgithub(?:\.(?:triggering_)?actor\b|\[\s*['\"](?:triggering_)?actor['\"]\s*\])"
    r"|\bGITHUB_(?:TRIGGERING_)?ACTOR\b" + _DUMP_GITHUB,
    FLAGS,
)
STEP_OUTPUT = re.compile(
    r"\bsteps(?:\.([A-Za-z0-9_-]+)|\[\s*['\"]([^'\"]+)['\"]\s*\])\.outputs\b", FLAGS
)
# A read of an environment value, in the spellings a step body uses: the
# expression forms `env.NAME` and `env['NAME']`, and the shell forms `$NAME`,
# `${NAME}` and PowerShell's `$env:NAME`.
_NAME = r"([A-Za-z_][A-Za-z0-9_]*)"
ENV_READ = re.compile(
    rf"\benv\.{_NAME}\b"
    rf"|\benv\[\s*['\"]{_NAME}['\"]\s*\]"
    rf"|\$\{{env:{_NAME}\}}"
    rf"|\$env:{_NAME}"
    rf"|\$\{{?{_NAME}"
    rf"|\bprintenv\s+{_NAME}"
    rf"|\bos\.environ(?:\.get)?\s*[\[(]\s*['\"]{_NAME}['\"]"
    rf"|\bgetenv\(\s*['\"]{_NAME}['\"]",
    FLAGS,
)

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


_BUDGET: ContextVar[list[int] | None] = ContextVar("required_context_scan_budget", default=None)


@contextmanager
def scan_budget() -> Iterator[None]:
    """Share one node budget across every `text()` call inside the block.

    Without it the cap is per call, and a document that aliases one large
    anchor many times costs the cap multiplied by the alias count.
    """
    token = _BUDGET.set([MAX_NODES])
    try:
        yield
    finally:
        _BUDGET.reset(token)


class ScanTruncatedError(Exception):
    """A value exceeded the scan budget, so part of it was never read.

    Raised rather than returning a partial answer: a source hidden past the
    budget would otherwise read as absent.
    """


def text(value: object) -> str:
    """Join the scalar leaves of ``value`` into one string, bounded in work done.

    A bare boolean or number is a valid `if:` value in YAML. It references
    nothing, so it is coerced to text rather than skipped as a type error.
    """
    parts: list[str] = []
    stack: list[tuple[object, int]] = [(value, 0)]
    budget = _BUDGET.get() or [MAX_NODES]
    while stack:
        if budget[0] <= 0:
            raise ScanTruncatedError(f"more than {MAX_NODES} nodes")
        node, depth = stack.pop()
        budget[0] -= 1
        if isinstance(node, Mapping | list):
            if depth >= MAX_DEPTH:
                raise ScanTruncatedError(f"nesting deeper than {MAX_DEPTH}")
            children = node.values() if isinstance(node, Mapping) else node
            stack.extend((child, depth + 1) for child in children)
        else:
            parts.append(_scalar_text(node))
    return "\n".join(parts)


def _scalar_text(node: object) -> str:
    try:
        return str(node)
    except ValueError:
        # An integer scalar past Python's digit limit cannot be printed. Digits
        # carry no source, so it reads as empty rather than aborting the scan.
        return ""


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
        name = next(group for group in match.groups() if group)
        for source in tainted_env.get(name.lower(), []):
            if source not in found:
                found.append(source)
    return found
