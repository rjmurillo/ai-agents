"""The one leading-YAML-frontmatter parser for this repository.

Every script that finds or loads a ``---`` fenced block at the top of a
Markdown file calls this module: validators and generators in ``scripts/`` and
``build/``, and the skill scripts that ship inside the plugin roots. Before it,
the repository carried dozens of hand-rolled parsers with at least 11 distinct
closing-fence rules, so one file could pass one gate and crash another (issues
#5275 and #5592).

The fence rule is ``python-frontmatter``'s ``YAMLHandler.FM_BOUNDARY``,
``^-{3,}\\s*$`` with ``re.MULTILINE``. Detection is that handler's ``detect``
(an anchored ``match``) and the split is its ``split`` (the first two boundary
matches). The same pattern through the same ``re`` calls gives the same answer
on every input. ``tests/test_frontmatter_block.py`` pins the
pattern and the split against the installed library, which stays a test-only
oracle.

The module is stdlib-only. It ships in the plugin ``lib`` trees, and the
``shipped-lib-no-runtime-dependencies`` import-linter contract forbids a
``yaml`` import there. A caller that loads YAML passes its own ``yaml`` module
in, the pattern issue #7082 set for shipped lib code.

Entry points, one fence rule:

- :func:`split_frontmatter` finds the block and returns its raw text, the body,
  and where the body starts. No YAML. Use it to strip or locate a block.
- :func:`decode_frontmatter_yaml` loads raw block text a caller already
  extracted, with the same pinned loader choice. No fence handling.
- :func:`parse_frontmatter` splits, then loads the block with a pinned
  ``SafeLoader`` (or a loader the caller names) and reports why a block is
  unusable.
- :func:`load_frontmatter` returns only the mapping, or ``None``.

``parse_frontmatter`` and ``decode_frontmatter_yaml`` reject duplicate keys
by default. ``load_frontmatter`` allows them by default, because its callers
were last-one-wins. A caller whose contract is last-one-wins passes
``allow_duplicate_keys=True``. YAML merge keys (``<<: *anchor``) load under
both policies; only explicitly repeated keys count as duplicates.

EXIT CODES: none. This module raises or returns; callers own their exit codes
per ADR-035.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from types import ModuleType
from typing import Any

__all__ = [
    "FM_BOUNDARY",
    "FM_BOUNDARY_PATTERN",
    "FrontmatterError",
    "FrontmatterResult",
    "FrontmatterSplit",
    "FrontmatterStatus",
    "decode_frontmatter_yaml",
    "load_frontmatter",
    "parse_frontmatter",
    "split_frontmatter",
]

FM_BOUNDARY_PATTERN = r"^-{3,}\s*$"
FM_BOUNDARY = re.compile(FM_BOUNDARY_PATTERN, re.MULTILINE)


class FrontmatterStatus(Enum):
    """Why a frontmatter block is or is not usable.

    ABSENT means add a block, UNTERMINATED means the block never closed,
    MALFORMED means fix the YAML. :func:`split_frontmatter` reports only VALID,
    ABSENT, and UNTERMINATED, because it reads no YAML.
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
class FrontmatterSplit:
    """Where the block is, before any YAML is read.

    ``raw`` is the text between the fences. ``body`` is the text after the
    closing fence, minus the one newline that ends the fence line.
    ``FM_BOUNDARY``'s ``\\s*`` is greedy, so the closing fence absorbs blank
    lines that follow it. ``body`` therefore does not keep those lines.

    The offsets index the source text, so a caller that needs original bytes or
    a line number slices the source instead of re-finding a fence:

    - ``open_end``: just past the opening fence line. The fence match can run on
      over whitespace-only lines, so ``text[open_end:raw_end]`` is the full
      payload, tab-only lines included, for a caller that must see them.
    - ``raw_start``: where ``raw`` begins (the end of the opening fence match).
    - ``raw_end``: where ``raw`` ends, which is the start of the closing fence.
    - ``fence_end``: just past the closing fence line and its newline, before
      any blank lines. ``text[fence_end:]`` is the body with those lines kept.
    - ``body_start``: where ``body`` begins.

    When no block is found, ``raw`` is ``""``, ``body`` is the whole text, and
    every offset is 0.
    """

    status: FrontmatterStatus
    raw: str
    body: str
    body_start: int
    raw_start: int = 0
    raw_end: int = 0
    fence_end: int = 0
    open_end: int = 0

    @property
    def found(self) -> bool:
        """True when both fences were found."""
        return self.status is FrontmatterStatus.VALID


@dataclass(frozen=True, slots=True)
class FrontmatterResult:
    """Outcome of one parse.

    ``metadata`` is the parsed mapping. It is ``None`` for every status except
    VALID and EMPTY. EMPTY yields ``{}``, because a block that closed and held
    nothing did parse. ``raw`` and ``body`` follow :class:`FrontmatterSplit`.
    ``value_type`` names the type YAML produced when the block is
    NOT_A_MAPPING (for example ``list``), and is ``None`` otherwise.
    """

    status: FrontmatterStatus
    metadata: dict[str, Any] | None
    raw: str
    body: str
    error: str | None = None
    value_type: str | None = None

    @property
    def ok(self) -> bool:
        """True when a mapping was parsed, including an empty one."""
        return self.status in (FrontmatterStatus.VALID, FrontmatterStatus.EMPTY)

    @property
    def present(self) -> bool:
        """True when the text opens a block, whether or not that block parsed."""
        return self.status is not FrontmatterStatus.ABSENT


def split_frontmatter(text: str) -> FrontmatterSplit:
    """Find the leading frontmatter block of ``text`` without reading YAML."""
    if not FM_BOUNDARY.match(text):
        return FrontmatterSplit(FrontmatterStatus.ABSENT, "", text, 0)
    boundaries = FM_BOUNDARY.finditer(text)
    opening = next(boundaries)
    closing = next(boundaries, None)
    if closing is None:
        return FrontmatterSplit(FrontmatterStatus.UNTERMINATED, "", text, 0)
    raw = text[opening.end() : closing.start()]
    body_start = closing.end()
    # The boundary match stops before the newline that ends the fence line.
    if text.startswith("\n", body_start):
        body_start += 1
    line_end = text.find("\n", closing.start())
    fence_end = len(text) if line_end < 0 else line_end + 1
    return FrontmatterSplit(
        FrontmatterStatus.VALID,
        raw,
        text[body_start:],
        body_start,
        raw_start=opening.end(),
        raw_end=closing.start(),
        fence_end=fence_end,
        open_end=text.index("\n") + 1,
    )


_STRICT_LOADERS: dict[ModuleType, type] = {}


def _strict_loader(yaml: ModuleType) -> type:
    """Return a ``SafeLoader`` subclass that rejects a repeated mapping key.

    Built from the caller's ``yaml`` module so this file never imports it, and
    cached per module object.
    Keys are compared with ``==`` in a list, not a set, because a YAML key need
    not be hashable (``? [a, b]`` builds a list key). A ``TypeError`` there
    would escape the caller's ``yaml.YAMLError`` handling.
    """
    cached = _STRICT_LOADERS.get(yaml)
    if cached is not None:
        return cached

    def reject_repeats(loader: Any, node: Any) -> None:  # noqa: ANN401 - yaml is untyped here
        # Each mapping node is checked once per load, before PyYAML flattens it in
        # place. That also stops a self-referencing merge (`a: &x {<<: *x}`).
        checked: set[int] = loader.__dict__.setdefault("_frontmatter_checked", set())
        if id(node) in checked:
            return
        checked.add(id(node))
        # A quoted `"<<"` constructs to the same string as a merge, so each entry
        # records whether it was a merge. Only like compares with like. The keys
        # compare with bare `==`, never as tuples: tuple equality tests identity
        # first, which would make PyYAML's shared NaN a duplicate here.
        seen: list[tuple[bool, Any]] = []
        for key_node, value_node in node.value:
            is_merge = key_node.tag == "tag:yaml.org,2002:merge"
            if is_merge:
                # construct_mapping flattens `<<` without this constructor, so an
                # inline merged mapping is checked here or not at all. A second
                # `<<` at one level is a repeated key like any other.
                key: Any = "<<"
                merged = (
                    value_node.value if isinstance(value_node, yaml.SequenceNode) else [value_node]
                )
                for source in merged:
                    if isinstance(source, yaml.MappingNode):
                        reject_repeats(loader, source)
            else:
                key = loader.construct_object(key_node, deep=True)
            if any(is_merge == merge and key == earlier for merge, earlier in seen):
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r} in frontmatter mapping", key_node.start_mark
                )
            seen.append((is_merge, key))

    def no_duplicate_keys(loader: Any, node: Any) -> dict[Any, Any]:  # noqa: ANN401 - yaml is untyped here
        reject_repeats(loader, node)
        mapping: dict[Any, Any] = loader.construct_mapping(node, deep=True)
        return mapping

    # Any: the class derives from the caller's SafeLoader, which this file
    # cannot import, so its add_constructor classmethod is invisible to mypy.
    built: Any = type("StrictFrontmatterLoader", (yaml.SafeLoader,), {})
    built.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_duplicate_keys)
    strict: type = built
    _STRICT_LOADERS[yaml] = strict
    return strict


def decode_frontmatter_yaml(
    raw: str,
    yaml: ModuleType,
    *,
    allow_duplicate_keys: bool = False,
    loader: type | None = None,
) -> Any:  # noqa: ANN401 - YAML yields whatever the document holds
    """Load YAML text that a caller already extracted, with the pinned loader.

    ``raw`` is the text between the fences, as :attr:`FrontmatterSplit.raw`
    holds it. No fence is searched for or added. The result is whatever YAML
    produces (mapping, list, scalar, or ``None``), and a ``yaml.YAMLError``
    propagates unchanged with its marks. Loader choice and the ``SafeLoader``
    guard are the ones :func:`parse_frontmatter` applies, because it calls this.
    """
    chosen = loader or (yaml.SafeLoader if allow_duplicate_keys else _strict_loader(yaml))
    if not issubclass(chosen, yaml.SafeLoader):
        # A non-safe loader would build arbitrary Python objects from !!python tags.
        raise TypeError(f"loader must subclass yaml.SafeLoader, got {chosen.__name__}")
    return yaml.load(raw, Loader=chosen)


def parse_frontmatter(
    text: str,
    yaml: ModuleType,
    *,
    allow_duplicate_keys: bool = False,
    loader: type | None = None,
    strict: bool = False,
) -> FrontmatterResult:
    """Split and load the leading frontmatter block of ``text``.

    ``yaml`` is the caller's PyYAML module. ``loader`` overrides the loader
    class; without it the loader is ``yaml.SafeLoader`` when
    ``allow_duplicate_keys`` is True and a duplicate-rejecting ``SafeLoader``
    otherwise. The loader is pinned rather than environment-selected, so the C
    loader never answers differently on a machine with libyaml.

    ``strict`` raises :class:`FrontmatterError` instead of returning a failing
    status. ABSENT never raises, because a file with no block is routine.
    """
    split = split_frontmatter(text)
    if split.status is FrontmatterStatus.ABSENT:
        return FrontmatterResult(FrontmatterStatus.ABSENT, None, "", text)
    if split.status is FrontmatterStatus.UNTERMINATED:
        result = FrontmatterResult(
            FrontmatterStatus.UNTERMINATED,
            None,
            "",
            text,
            "opens with '---' but has no closing '---' fence",
        )
        return _maybe_raise(result, strict)

    try:
        parsed = decode_frontmatter_yaml(
            split.raw, yaml, allow_duplicate_keys=allow_duplicate_keys, loader=loader
        )
    except yaml.YAMLError as exc:
        result = FrontmatterResult(
            FrontmatterStatus.MALFORMED,
            None,
            split.raw,
            split.body,
            f"invalid YAML frontmatter: {exc}",
        )
        return _maybe_raise(result, strict)

    if parsed is None:
        return FrontmatterResult(FrontmatterStatus.EMPTY, {}, split.raw, split.body)
    if not isinstance(parsed, dict):
        result = FrontmatterResult(
            FrontmatterStatus.NOT_A_MAPPING,
            None,
            split.raw,
            split.body,
            f"frontmatter is not a mapping (got {type(parsed).__name__})",
            value_type=type(parsed).__name__,
        )
        return _maybe_raise(result, strict)
    return FrontmatterResult(FrontmatterStatus.VALID, parsed, split.raw, split.body)


def load_frontmatter(
    text: str,
    yaml: ModuleType,
    *,
    allow_duplicate_keys: bool = True,
    loader: type | None = None,
) -> dict[str, Any] | None:
    """Return the frontmatter mapping, or ``None`` when no usable one exists.

    Only VALID returns a mapping. EMPTY returns ``None``, matching
    ``isinstance(yaml.safe_load(""), dict)``, which is what the replaced
    helpers returned for an empty block. The default tolerates duplicate keys,
    last-one-wins, because that is ``yaml.safe_load``'s behavior and every
    replaced helper with this signature used it.
    """
    result = parse_frontmatter(text, yaml, allow_duplicate_keys=allow_duplicate_keys, loader=loader)
    if result.status is not FrontmatterStatus.VALID:
        return None
    return result.metadata


def _maybe_raise(result: FrontmatterResult, strict: bool) -> FrontmatterResult:
    """Return ``result``, or raise when ``strict`` and the block is unusable."""
    if strict and not result.ok and result.status is not FrontmatterStatus.ABSENT:
        raise FrontmatterError(result.error or f"frontmatter {result.status.value}")
    return result
