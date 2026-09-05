#!/usr/bin/env python3
"""Text layer for `build/sync_slim_agents.py`: parse, transform, reconcile.

Everything here works on strings alone. It opens no file, resolves no path,
and knows nothing about which agents are mirrored or where they live. The CLI
module beside it owns all of that, plus the atomic write and the exit codes.

The seam earns its keep twice. It keeps the reconciliation rules testable
without a temporary tree, and it keeps both files under the 500-line cohesion
limit that `.claude/skills/taste-lints/` enforces, with no size-lint escape in
either. The literal escape comment is spelled out nowhere in this file on
purpose: the checker scans the first ten lines for it, so quoting it in a
docstring near the top would suppress the rule it describes.

Three concerns live here.

**Frontmatter.** The three agent trees do not share a frontmatter schema:
`src/claude/` carries `model:` and `mcp__`-prefixed tool names, `.github/agents/`
carries slash-namespaced tool names, and `templates/agents/` carries the
`tools_vscode` and `tools_copilot` pair that `build/generate_agents.py` fans
out. So a sync replaces a destination's body and leaves its frontmatter alone.
`split_frontmatter` finds the boundary and `rendered_content` reassembles the
file.

**Transforms.** A body is not copied verbatim either. `MIRROR_TRANSFORMS` is
the rule set both destinations declare: strip the literal `mcp__github__`
prefix, so `mcp__github__pull_request_read` reaches a mirror as
`pull_request_read`. The evidence, from
`grep -rhoE "mcp__[a-z0-9]+__" <tree>/*.md | sort | uniq -c` on this branch, is
26 `mcp__github__` occurrences in `src/claude/` against 0 in `templates/agents/`
and 0 in `.github/agents/`, while `mcp__serena__` appears in all three (83, 31,
40) and is therefore left alone. Each `Transform` carries that measurement in
its own `why` field, next to the rule it justifies.

**Reconciliation.** Most divergence between the trees is not mechanizable, so
the copy has to be refused rather than attempted wherever the two disagree. Of
the 48 line pairs the trees currently replace, exactly 10 are that one prefix
rule; the other 38 are destination wording no transform reproduces, including
the `mcp__deepwiki__` and `mcp__context7__` sentences the mirrors reworded
instead of stripping. `reconciliation_blockages` compares a destination body
against its transformed source body and reports every line a copy would
overwrite or drop.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True, slots=True)
class Transform:
    """One mechanical rewrite a destination applies to the source body.

    `why` records the evidence for the rule rather than restating the rule. A
    transform nobody measured is a guess about what a mirror wants, and a wrong
    guess here rewrites nine agent files in two trees at once.
    """

    pattern: re.Pattern[str]
    replacement: str
    why: str

    def apply(self, text: str) -> str:
        return self.pattern.sub(self.replacement, text)


# Both mirror trees take this one rule, and only this one.
MIRROR_TRANSFORMS: tuple[Transform, ...] = (
    Transform(
        pattern=re.compile(r"mcp__github__"),
        replacement="",
        why=(
            'grep -rhoE "mcp__[a-z0-9]+__" over the three trees counts 26'
            " mcp__github__ in src/claude/ against 0 in templates/agents/ and 0"
            " in .github/agents/, so both mirrors strip that prefix with no"
            " exception. mcp__serena__ is deliberately not here: it appears in"
            " all three trees (83, 31, 40), so stripping it would rewrite 71"
            " mirror lines that are already correct."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Destination:
    """One hand-maintained mirror of an agent body.

    The shape of a mirror lives here, next to the transforms it declares.
    Which mirrors exist is the CLI module's `DESTINATIONS`, because that needs
    the repository root to locate them.
    """

    label: str
    directory: Path
    suffix: str
    transforms: tuple[Transform, ...]

    def path_for(self, name: str) -> Path:
        return self.directory / f"{name}{self.suffix}"


def transformed_body(source_body: str, transforms: Iterable[Transform]) -> str:
    """Return the source body rewritten by `transforms`, in declaration order.

    Takes the rule set rather than the `Destination` that declares it. A
    `Destination` carries a `Path` and belongs to the file layer, so accepting
    one here would make this module import the CLI module that imports it.
    """
    for transform in transforms:
        source_body = transform.apply(source_body)
    return source_body


def _opens_frontmatter(text: str) -> bool:
    """True when the text starts with a line that is exactly `---`.

    A file whose entire content is `---` opens a block with no newline after
    it. Requiring the newline would classify that file as having no
    frontmatter, and `--write` would then replace the whole thing with the
    source body instead of refusing it.
    """
    return text.startswith("---\n") or text == "---"


def _frontmatter_end(text: str) -> int | None:
    """Return the index just past the closing `---` line, or None if absent.

    The search starts at the newline that closes the opening delimiter, not
    past it, so an empty block (`---` on one line and `---` on the next) is
    terminated rather than unterminated. A closing delimiter that ends the
    file with no trailing newline counts too. Both shapes are legal
    frontmatter, and the CLI now rejects an unterminated block outright, so
    misreading either one would refuse to sync a valid file.
    """
    if not _opens_frontmatter(text):
        return None
    end = text.find("\n---\n", 3)
    if end != -1:
        return end + len("\n---\n")
    if text.endswith("\n---"):
        return len(text)
    return None


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Frontmatter includes both `---` delimiters.

    A file with no leading `---` block yields an empty frontmatter and the whole
    text as body. A file whose block never closes yields that same shape, so
    this return value alone cannot tell the two apart. The CLI runs
    `find_malformed_paths` first and refuses the second shape, which is what
    keeps the ambiguity away from the callers.
    """
    boundary = _frontmatter_end(text)
    if boundary is None:
        return "", text
    return text[:boundary], text[boundary:]


def has_unterminated_frontmatter(text: str) -> bool:
    """True when the text opens a `---` block that never closes."""
    return _opens_frontmatter(text) and _frontmatter_end(text) is None


def rendered_content(source_body: str, target_text: str) -> str:
    """Return what `target_text` becomes once it carries `source_body`."""
    frontmatter, _ = split_frontmatter(target_text)
    if not frontmatter:
        return source_body
    if not frontmatter.endswith("\n"):
        # A closing `---` that ended the file carries no newline of its own.
        # Concatenating straight onto it yields `---# Analyst`, which is no
        # longer a standalone YAML delimiter, so the block would not parse.
        frontmatter += "\n"
    return frontmatter + source_body


@dataclass(frozen=True, slots=True)
class Blockage:
    """One destination line the transform layer cannot reproduce.

    `line` is 1-based and indexes the destination file, frontmatter included,
    so it matches what an editor shows. `source_text` is None when the source
    has no counterpart at all, which is the `delete` case below; an empty
    string there would be indistinguishable from a blank source line.
    """

    line: int
    destination_text: str
    source_text: str | None


def reconciliation_blockages(
    destination_body: str, source_body: str, line_offset: int = 0
) -> tuple[Blockage, ...]:
    """Return the destination lines a copy of `source_body` would lose.

    `difflib.SequenceMatcher` over the two line lists yields three non-equal
    opcodes, and exactly one of them is safe to write through:

    - `insert`: the source has lines the destination lacks. When inserts are
      the only opcodes, the destination body is exactly the transformed source
      minus some lines, so writing the transformed source adds content and
      loses nothing. Safe.
    - `replace`: the destination says the same thing in wording the transforms
      did not produce. Writing would overwrite a hand-made adaptation with the
      Claude phrasing. Blocking.
    - `delete`: the destination carries a line the source does not, such as the
      `vendor-portability` declaration comment in
      `templates/agents/implementer.shared.md`. Writing would drop it.
      Blocking.

    A blocking opcode reports one entry per destination line it covers, paired
    with the source line at the same offset when the block has one. Naming
    `insert` in the safe set is a statement of policy rather than the
    mechanism that enforces it: an insert covers no destination line, so the
    loop below would emit nothing for one even if it were not filtered out.
    `autojunk` is off because its heuristic drops lines that repeat in more
    than 1% of a long sequence, and a blank line or a `| --- |` table rule
    qualifies; a dropped line cannot be reported as blocking.
    """
    destination_lines = destination_body.splitlines()
    source_lines = source_body.splitlines()
    matcher = difflib.SequenceMatcher(
        None, destination_lines, source_lines, autojunk=False
    )
    blocked: list[Blockage] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("replace", "delete"):
            continue
        for offset in range(i2 - i1):
            paired = j1 + offset
            blocked.append(
                Blockage(
                    line=line_offset + i1 + offset + 1,
                    destination_text=destination_lines[i1 + offset],
                    source_text=source_lines[paired] if paired < j2 else None,
                )
            )
    return tuple(blocked)


# A mirror body carries markdown table rows several hundred characters wide.
# Printed whole, one of them scrolls every other finding off the screen.
_EXCERPT_WIDTH = 76


def _excerpt(text: str) -> str:
    """Trim one reported line so a long row cannot bury the rest of the report."""
    if len(text) <= _EXCERPT_WIDTH:
        return text
    return text[: _EXCERPT_WIDTH - 3] + "..."


def print_blockages(blockages: Iterable[Blockage], stream: TextIO) -> None:
    """Print both sides of every blocked line, so the reader can reconcile them."""
    for blockage in blockages:
        source = (
            "(no matching source line)"
            if blockage.source_text is None
            else _excerpt(blockage.source_text)
        )
        print(
            f"    line {blockage.line} destination: "
            f"{_excerpt(blockage.destination_text)}",
            file=stream,
        )
        print(f"    line {blockage.line} source:      {source}", file=stream)


@dataclass(frozen=True, slots=True)
class Comparison:
    """One destination file, what it would become, and whether it may change."""

    target: Path
    in_sync: bool
    updated: str
    blockages: tuple[Blockage, ...]


def compare_file(
    target: Path,
    source_body: str,
    destination_text: str,
    transforms: Iterable[Transform],
) -> Comparison:
    """Classify one destination against the source body bound for it.

    Takes the destination's text rather than its path, so the caller owns
    every read and this stays a pure function of two strings and a rule set.
    `target` is carried through untouched, for the caller's report and write.
    """
    frontmatter, destination_body = split_frontmatter(destination_text)
    body = transformed_body(source_body, transforms)
    updated = rendered_content(body, destination_text)
    return Comparison(
        target=target,
        in_sync=updated == destination_text,
        updated=updated,
        blockages=reconciliation_blockages(
            destination_body, body, frontmatter.count("\n")
        ),
    )


@dataclass(frozen=True, slots=True)
class Drift:
    """The three outcomes `--check` has to tell apart.

    Reporting only "drifted" merges the last two, and they call for opposite
    actions: one is cleared by running `--write`, the other is cleared by a
    person reconciling wording `--write` refuses to touch.

    Each tuple holds `Comparison` records rather than rendered paths. Turning
    a path into the repo-relative form the report shows needs the repository
    root, which is the file layer's knowledge, not this module's.
    """

    in_sync: tuple[Comparison, ...]
    applicable: tuple[Comparison, ...]
    blocked: tuple[Comparison, ...]

    @property
    def examined(self) -> int:
        return len(self.in_sync) + len(self.applicable) + len(self.blocked)


def collect_drift(comparisons: Iterable[Comparison]) -> Drift:
    """Sort already-classified destinations into the three outcomes."""
    comparisons = tuple(comparisons)
    return Drift(
        in_sync=tuple(item for item in comparisons if item.in_sync),
        applicable=tuple(
            item for item in comparisons if not item.in_sync and not item.blockages
        ),
        blocked=tuple(item for item in comparisons if item.blockages),
    )
