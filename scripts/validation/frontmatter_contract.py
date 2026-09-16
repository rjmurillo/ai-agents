#!/usr/bin/env python3
r"""One frontmatter contract for every parser that can import a dependency.

Issue #5275 found three ADR parsers disagreeing on which closing fences they
accept, so the same file could pass the lifecycle gate and crash the index
build. A repo-wide sweep found at least 11 distinct fence contracts across
roughly 35 hand-rolled implementations. This module ends that by delegating
fence detection and YAML loading to ``python-frontmatter`` (pinned in
``pyproject.toml``), which the repo already depends on.

It deliberately contains **no regular expression and no fence arithmetic**. The
boundary comes from ``YAMLHandler.FM_BOUNDARY`` and the split from
``YAMLHandler.split``. A future upstream change to either is inherited rather
than re-derived, which is the whole point: the previous attempt to keep a gate
in step with this library by hand-copying its pattern is why
``scripts/validation/memory_index.py:888`` exists.

Not every caller can use this module. Scripts that ship inside a plugin root may
import only the standard library and ``yaml``
(``.claude/rules/plugin-self-containment.md``), so ``python-frontmatter`` is
unavailable to them. Those keep a stdlib mirror of the same contract, pinned to
this library's pattern by a parity test, rather than an import.

Why the library's boundary is the right contract
------------------------------------------------

``FM_BOUNDARY = re.compile(r"^-{3,}\s*$", re.MULTILINE)``, quoted verbatim from
.. citation-freshness: ignore -- cites the installed python-frontmatter
.. package, a pinned dependency in pyproject.toml that is deliberately not
.. tracked in this repo; the tests assert the quoted pattern against the
.. live library rather than against HEAD.
``frontmatter/default_handlers.py:252``. It accepts author slips that change no
meaning (a padded fence, a tab, four dashes, a missing final newline) and
rejects the one shape that signals a real mistake, ``--- trailing text``. The
strictest parser in the repo before this module rejected a closing fence with a
single trailing space, which is the crash issue #5275 reported.

Stricter/looser/different than canonical
----------------------------------------

Stricter than ``python-frontmatter``'s own ``frontmatter.loads``, which collapses
four distinct outcomes into an empty metadata dict: no frontmatter at all, an
opened-but-unterminated block, an empty block, and a block whose YAML is not a
mapping. Callers here must tell those apart. ``generate_adr_index.py`` raises a
named error for an unterminated block, because routing it into "Needs backfill"
hides a defect the author has to see. So this module reports a
:class:`FrontmatterStatus` instead of a bare dict, built from the library's own
``detect`` and ``split`` primitives.

Stricter on the loader. ``YAMLHandler.load`` binds ``CSafeLoader`` when libyaml
is present and the pure-Python ``SafeLoader`` otherwise, so the same document
can parse differently on a contributor's machine than in CI. This module pins
``yaml.SafeLoader`` explicitly, matching what ADR-073 mandates (``yaml.safe_load``)
and what duplicate-key detection requires, since the C loader does not honour the
constructor hook below. The pin cannot be spelled
``frontmatter.loads(text, Loader=...)``: that parameter means *default metadata*,
so the obvious spelling injects a ``Loader`` key into every parsed record.

Looser on body fidelity. ``FM_BOUNDARY``'s ``\s*`` is greedy, so the closing
fence absorbs blank lines that follow it and :attr:`FrontmatterResult.body`
does not round-trip those bytes. Every consumer in this repo reads the body to
find prose (an H1, a ``## Status`` section, a decision summary) or to compare two
revisions of it, and normalisation applies equally to both sides of such a
comparison. A caller that needs the original bytes must slice the source text
itself. Anything that rewrites a record in place must also avoid
``frontmatter.dumps``, which inserts a blank line after the closing fence and
drops the trailing newline.

EXIT CODES: none. This module raises or returns; callers own their exit codes
per ADR-035.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import yaml
from frontmatter.default_handlers import YAMLHandler

__all__ = [
    "FrontmatterError",
    "FrontmatterResult",
    "FrontmatterStatus",
    "parse_frontmatter",
]


class FrontmatterStatus(Enum):
    """Why a frontmatter block is or is not usable.

    Five of the six are failures, and they are kept apart because they send an
    author to different places: ABSENT means add a block, UNTERMINATED means the
    block you wrote never closed, MALFORMED means fix the YAML.
    """

    VALID = "valid"
    ABSENT = "absent"
    UNTERMINATED = "unterminated"
    EMPTY = "empty"
    NOT_A_MAPPING = "not_a_mapping"
    MALFORMED = "malformed"


class FrontmatterError(Exception):
    """Raised by :func:`parse_frontmatter` when ``strict`` rejects a result."""


@dataclass(frozen=True, slots=True)
class FrontmatterResult:
    """Outcome of one parse.

    ``metadata`` is the parsed mapping, and is ``None`` for every status except
    VALID and EMPTY (EMPTY yields an empty dict, because a block that closed and
    held nothing did parse). ``raw`` is the text between the fences, exactly as
    the library split it, and is ``""`` when no block was found. ``body`` is
    everything after the closing fence, subject to the normalisation named in
    this module's docstring.
    """

    status: FrontmatterStatus
    metadata: dict[str, Any] | None
    raw: str
    body: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when a mapping was parsed, including an empty one."""
        return self.status in (FrontmatterStatus.VALID, FrontmatterStatus.EMPTY)

    @property
    def present(self) -> bool:
        """True when the text opens a block, whether or not that block parsed.

        ABSENT is the only status where the author wrote no block at all. An
        unterminated or malformed block is present and broken, which is a
        different message.
        """
        return self.status is not FrontmatterStatus.ABSENT


class _StrictLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects a mapping declaring the same key twice."""


def _no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    """Reject a mapping that declares the same key twice.

    Mirrors ``build/scripts/generate_adr_index.py:202`` verbatim in behaviour,
    including its hard-won detail: keys are collected in a list and compared
    with ``==`` rather than kept in a set, because a YAML key need not be
    hashable (``? [a, b]`` builds a list key) and both ``in`` and ``add`` raise
    ``TypeError`` on it. That ``TypeError`` escapes the caller's
    ``yaml.YAMLError`` handling and produces a traceback instead of the
    documented exit code.
    """
    seen: list[Any] = []
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if any(key == earlier for earlier in seen):
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r} in frontmatter mapping", key_node.start_mark
            )
        seen.append(key)
    mapping: dict[Any, Any] = loader.construct_mapping(node, deep=True)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


class _PinnedHandler(YAMLHandler):
    """``YAMLHandler`` with the loader pinned instead of environment-selected."""

    def __init__(self, loader: type[yaml.SafeLoader]) -> None:
        super().__init__()
        self._loader = loader

    def load(self, fm: str, **kwargs: object) -> Any:  # noqa: ANN401 - matches supertype
        """Parse the block with the pinned loader.

        Upstream calls ``kwargs.setdefault("Loader", SafeLoader)``; setting the
        key here wins over that default without reaching into its internals.
        """
        kwargs["Loader"] = self._loader
        return super().load(fm, **kwargs)


def _strip_fence_newline(content: str) -> str:
    """Drop the single newline the closing fence leaves on the body.

    ``FM_BOUNDARY`` matches up to but not including the newline that ends the
    fence line, so every split body starts with it. Removing exactly one keeps a
    deliberate blank first line intact where the greedy ``\\s*`` did not already
    absorb it.

    There is deliberately no CRLF branch. ``\\s*`` absorbs the ``\\r`` before ``$``
    matches, so a CRLF document still yields a body starting with a bare ``\\n``;
    a ``content.startswith("\\r\\n")`` arm would be unreachable. Verified against
    five CRLF fence shapes, including a padded and a four-dash close.
    """
    if content.startswith("\n"):
        return content[1:]
    return content


def parse_frontmatter(
    text: str,
    *,
    allow_duplicate_keys: bool = False,
    strict: bool = False,
) -> FrontmatterResult:
    """Parse the leading frontmatter block of ``text``.

    ``allow_duplicate_keys`` defaults to False, matching the ADR gates, which
    treat a repeated key as a defect rather than last-one-wins. Set it True only
    for a caller whose existing contract tolerates duplicates.

    ``strict`` raises :class:`FrontmatterError` instead of returning a failing
    status, for callers that already propagate an exception.
    """
    handler = _PinnedHandler(yaml.SafeLoader if allow_duplicate_keys else _StrictLoader)

    if not handler.detect(text):
        result = FrontmatterResult(FrontmatterStatus.ABSENT, None, "", text)
        return _maybe_raise(result, strict)

    try:
        raw, content = handler.split(text)
    except ValueError:
        # detect() saw an opening fence that split() could not close.
        result = FrontmatterResult(
            FrontmatterStatus.UNTERMINATED,
            None,
            "",
            text,
            "opens with '---' but has no closing '---' fence",
        )
        return _maybe_raise(result, strict)

    body = _strip_fence_newline(content)

    try:
        parsed = handler.load(raw)
    except yaml.YAMLError as exc:
        result = FrontmatterResult(
            FrontmatterStatus.MALFORMED, None, raw, body, f"invalid YAML frontmatter: {exc}"
        )
        return _maybe_raise(result, strict)

    if parsed is None:
        return FrontmatterResult(FrontmatterStatus.EMPTY, {}, raw, body)
    if not isinstance(parsed, dict):
        result = FrontmatterResult(
            FrontmatterStatus.NOT_A_MAPPING,
            None,
            raw,
            body,
            f"frontmatter is not a mapping (got {type(parsed).__name__})",
        )
        return _maybe_raise(result, strict)
    return FrontmatterResult(FrontmatterStatus.VALID, parsed, raw, body)


def _maybe_raise(result: FrontmatterResult, strict: bool) -> FrontmatterResult:
    """Return ``result``, or raise when ``strict`` and the block is unusable.

    ABSENT never raises even under ``strict``: a file with no frontmatter is a
    routine input for every caller here, not a defect.
    """
    if strict and not result.ok and result.status is not FrontmatterStatus.ABSENT:
        raise FrontmatterError(result.error or f"frontmatter {result.status.value}")
    return result
