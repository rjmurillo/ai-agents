#!/usr/bin/env python3
"""Measure and gate the always-on instruction budget per file language.

Issue #3419: editing a single ``.py`` file loads ~218 KB of always-on
instruction text (every ``.github/instructions/*.instructions.md`` whose
``applyTo`` matches that language regardless of directory). The IFScale
benchmark (arXiv:2507.11538) shows even the strongest models omit instructions
as the always-loaded set grows; omission, not modification, is the failure mode.
Without an instrument this corpus grows silently on every rule addition.

This validator computes the *language-baseline always-on budget*: the summed
bytes of instruction files whose ``applyTo`` includes a language-universal
pattern (``**``, ``**/*``, or ``**/*.<ext>``) for a representative extension. Directory
scoped rules (for example ``tests/**``) are situational, not always-on, so they
are excluded by design.

The per-extension ceilings are a NON-REGRESSION RATCHET seeded just above the
current measured bytes. Phase 1 (this instrument) makes the budget visible in CI
and blocks silent growth, for example adding a new all-language rule. The
follow-up rescope (#3419 AC #2) lowers these ceilings as book-derived rules move
to task-invoked skills. Lower a ceiling when the corpus shrinks; never raise one
without recording why in the same change.

Gate is on bytes (exact and reproducible). Estimated tokens are informational
and reuse the shared estimator from ``token_budget``.

Exit codes follow ADR-035:
    0 - Success (all extensions within budget, or non-CI mode)
    1 - Logic error (budget exceeded, CI mode only)
    2 - Configuration error (invalid path or missing instructions directory)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Hashable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from scripts.validation.token_budget import estimate_token_count

INSTRUCTIONS_SUBDIR = ".github/instructions"
INSTRUCTION_GLOB = "*.instructions.md"

# Non-regression ratchet ceilings in bytes, seeded just above current measured
# values (see module docstring). Lower these as the corpus shrinks.
DEFAULT_CEILINGS_BYTES: dict[str, int] = {
    ".py": 220_000,
    ".cs": 220_000,
    ".ps1": 220_000,
    ".md": 83_000,
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class UnsupportedApplyToError(ValueError):
    """A frontmatter ``applyTo`` cannot be resolved to a concrete glob set.

    Raised for malformed or ambiguous frontmatter: invalid YAML, a duplicate
    top-level key (the YAML spec requires unique keys; a second ``applyTo``
    would silently win under a permissive loader), or an ``applyTo`` that is
    neither a string nor a list of strings. Silently excluding such a file
    would under-count the always-on budget and let a malformed rule bypass the
    ceiling, so this fails closed as a configuration error (ADR-035 exit code 2)
    rather than being swallowed.
    """


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects duplicate mapping keys instead of last-wins.

    PyYAML (like most YAML parsers) silently keeps the last value when a key
    repeats. A rule with two ``applyTo`` keys would then be scored on whichever
    came last, so a universal ``applyTo`` could be masked by a trailing
    directory-scoped one and dodge the budget. Fail closed on any duplicate.
    """


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    """Build a mapping, raising ``UnsupportedApplyToError`` on a duplicate key."""
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        # SafeLoader.construct_mapping rejects an unhashable key (a YAML complex
        # key such as ``? [a, b]``) with a ConstructorError; the raw ``key in
        # mapping`` below would instead raise an uncaught TypeError and escape as
        # exit 1. Guard it so malformed frontmatter fails closed as exit 2.
        if not isinstance(key, Hashable):
            msg = f"unhashable key in frontmatter: {key!r}"
            raise UnsupportedApplyToError(msg)
        if key in mapping:
            msg = f"duplicate key {key!r} in frontmatter"
            raise UnsupportedApplyToError(msg)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


# VS Code's matcher special-cases these three globs as matching every file even
# with no editor open, so a rule scoped to any of them is always-on for every
# language. Raw ``minimatch`` would read bare ``*`` as root-only; the harness
# does not (pinned source lines 294-310), so ``*`` belongs here. These are the
# only forms whose universality cannot be decided by matching probe paths (bare
# ``*`` compiles to ``^[^/]*$``, which no multi-segment path can satisfy), so
# they are recognized directly.
_ALL_FILES_FORMS = frozenset({"**", "**/*", "*"})


def _probe_paths(ext: str) -> tuple[str, ...]:
    """Absolute sample paths of ``ext`` spanning depth, directory, and basename.

    ``is_language_universal`` calls a glob universal for the language when it
    matches *every* probe. The direction is safe for an upper-bound budget: a
    truly universal glob matches all paths, so it can never be misjudged
    non-universal (under-count, the dangerous direction); only a scoped glob that
    happens to match every probe could be over-counted (the safe direction). The
    probes therefore span the discriminating axes a scope could restrict:

    - depth, including a root-level file, so a glob requiring an intermediate
      literal directory segment (``**/src/*.py``) fails the depth-1 probe;
    - directory names, so a glob pinned to a named tree fails;
    - basename stems (short, dotted, punctuated), so a filename-scoped glob
      (``**/foo*.py``) fails.
    """
    stems = ("probe", "X", "a.b.c", "weird-name_123")
    dirs = ("", "a/", "a/b/c/d/e/", "zzz/")
    paths = [f"/{directory}{stem}{ext}" for directory in dirs for stem in stems]
    return tuple(dict.fromkeys(paths))


def _split_glob_aware(pattern: str, split_char: str) -> list[str]:
    """Split ``pattern`` on ``split_char`` outside ``{...}`` and ``[...]``.

    Port of VS Code ``splitGlobAware`` (glob.ts, pinned SHA
    018354116a88cb1264790f93663de42198a44594): a leading separator yields an
    empty leading segment (kept, so a slash-anchored regex starts with a
    separator), a trailing separator yields an empty trailing segment (dropped),
    and a separator inside a brace or bracket group does not split. Used for both
    the comma split of an ``applyTo`` scope list and the ``/`` split of a single
    glob into path segments.
    """
    if not pattern:
        return []
    segments: list[str] = []
    in_braces = False
    in_brackets = False
    current: list[str] = []
    for char in pattern:
        if char == split_char and not in_braces and not in_brackets:
            segments.append("".join(current))
            current = []
            continue
        if char == "{":
            in_braces = True
        elif char == "}":
            in_braces = False
        elif char == "[":
            in_brackets = True
        elif char == "]":
            in_brackets = False
        current.append(char)
    if current:
        segments.append("".join(current))
    return segments


def expand_braces(pattern: str) -> list[str]:
    """Expand a glob brace group into its alternatives.

    ``**/*.{py,pyi}`` -> ``['**/*.py', '**/*.pyi']``. Handles multiple and
    nested groups by recursion. An unbalanced brace is left untouched.
    """
    start = pattern.find("{")
    if start == -1:
        return [pattern]
    depth = 0
    end = -1
    for i in range(start, len(pattern)):
        if pattern[i] == "{":
            depth += 1
        elif pattern[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return [pattern]
    prefix, suffix = pattern[:start], pattern[end + 1 :]
    options = _split_glob_aware(pattern[start + 1 : end], ",")
    expanded: list[str] = []
    for opt in options:
        expanded.extend(expand_braces(prefix + opt + suffix))
    return expanded


def _vscode_effective_glob(pattern: str) -> str:
    """Fold an ``applyTo`` glob to the effective form the harness matches on.

    Mirrors the one string transformation VS Code's instruction matcher applies
    before matching: a pattern that is neither absolute (``/...``) nor already
    ``**/``-anchored gets ``**/`` prepended, so ``*.py`` means ``**/*.py`` and
    ``src/*.py`` becomes the scoped ``**/src/*.py``. Absolute patterns,
    ``**/``-anchored patterns, and the all-files wildcards are returned
    unchanged. Every other equivalence (zero-segment globstars, ``?`` wildcards,
    absolute-root anchoring) is decided later by matching probe paths in
    ``is_language_universal``, not by rewriting the string here, so the model
    stays faithful to the harness rather than chasing glob spellings. Source,
    pinned:
    https://github.com/microsoft/vscode/blob/018354116a88cb1264790f93663de42198a44594/src/vs/workbench/contrib/chat/common/promptSyntax/computeAutomaticInstructions.ts#L294-L310
    """
    p = pattern.strip()
    if p in _ALL_FILES_FORMS:
        return p
    if not p.startswith("/") and not p.startswith("**/"):
        p = "**/" + p
    return p


# Faithful port of VS Code's glob-to-regex separator semantics (glob.ts
# ``parseRegExp``/``starsToRegExp``), pinned at SHA
# 018354116a88cb1264790f93663de42198a44594
# (src/vs/base/common/glob.ts L44-L253). Hand-rolling the minimatch->regex
# translation diverged from the harness at separator edges: the dropped
# mandatory ``/`` before a non-terminal ``**`` let ``/*/**/*.py`` match a root
# file ``/probe.py``. Porting VS Code's own segment walker ends that class of
# drift. Two simplifications are safe here: braces are already expanded by
# ``expand_braces`` before a pattern reaches this compiler, and ``[...]``
# character classes are treated as literal text rather than parsed. A char
# class is scoped by construction (it constrains a character), so it can never
# match the diverse probe set and is correctly classified non-universal for the
# upper-bound budget without bracket parsing; treating ``[`` literally only ever
# makes the regex more restrictive, never falsely universal.
_GLOB_STAR = "**"
_PATH_REGEX = r"[/\\]"  # any path separator (slash or backslash)
_NO_PATH_REGEX = r"[^/\\]"  # any non-separator character


def _stars_to_regexp(star_count: int, *, is_last_segment: bool) -> str:
    """Translate a run of ``*`` to regex, mirroring VS Code ``starsToRegExp``.

    ``star_count == 1`` is a single ``*`` (any run of non-separator characters,
    non-greedy). ``star_count == 2`` is a whole ``**`` segment (zero or more
    complete path segments); as the last segment it additionally matches a
    trailing ``separator + segment`` so ``a/**`` covers ``a/b``.
    """
    if star_count == 0:
        return ""
    if star_count == 1:
        return _NO_PATH_REGEX + "*?"
    tail = f"|{_PATH_REGEX}{_NO_PATH_REGEX}+" if is_last_segment else ""
    return f"(?:{_PATH_REGEX}|{_NO_PATH_REGEX}+{_PATH_REGEX}{tail})*?"


def _segment_to_regex(segment: str) -> str:
    """Translate one non-globstar path segment to a regex fragment.

    Each ``*`` becomes a single-star run (``starsToRegExp(1)``), ``?`` matches
    one non-separator character, and every other character is escaped literally.
    """
    out: list[str] = []
    for char in segment:
        if char == "*":
            out.append(_stars_to_regexp(1, is_last_segment=False))
        elif char == "?":
            out.append(_NO_PATH_REGEX)
        else:
            out.append(re.escape(char))
    return "".join(out)


@cache
def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile an ``applyTo`` glob to an anchored case-insensitive regex.

    Faithful port of VS Code's ``parseRegExp`` segment walker (see the module
    note above the constants). Path-segment semantics match the harness:

    - ``**`` as a whole segment matches zero or more complete path segments;
    - ``*`` matches zero or more non-separator characters within one segment;
    - ``?`` matches exactly one non-separator character;
    - a literal separator is emitted after a segment unless the following
      segment is a *terminal* ``**`` (VS Code's "Tail" rule), so ``some/**/*.js``
      keeps the ``/`` after ``some`` and a sibling folder ``something`` cannot
      match, while ``/*/**/*.py`` requires a real first directory and does not
      match a root file.

    Case-insensitive because VS Code matches ``applyTo`` with ``ignoreCase:
    true``. ``is_language_universal`` uses this to decide universality by
    *matching* diverse probe paths instead of enumerating glob spellings.
    """
    segments = _split_glob_aware(pattern, "/")
    if segments and all(segment == _GLOB_STAR for segment in segments):
        return re.compile("^.*$", re.IGNORECASE)
    body: list[str] = []
    last = len(segments) - 1
    previous_was_globstar = False
    for index, segment in enumerate(segments):
        if segment == _GLOB_STAR:
            if previous_was_globstar:
                continue
            body.append(_stars_to_regexp(2, is_last_segment=index == last))
            previous_was_globstar = True
            continue
        body.append(_segment_to_regex(segment))
        if index < last and (segments[index + 1] != _GLOB_STAR or index + 2 < len(segments)):
            body.append(_PATH_REGEX)
        previous_was_globstar = False
    return re.compile("^" + "".join(body) + "$", re.IGNORECASE)


def _iter_applyto_globs(value: object) -> list[str]:
    """Flatten a parsed YAML ``applyTo`` value into raw comma-split globs.

    Accepts a single glob string (the repo convention, possibly comma joined)
    or a YAML list of such strings. Any other shape is a configuration error.
    """
    if isinstance(value, str):
        return _split_glob_aware(value, ",")
    if isinstance(value, list):
        globs: list[str] = []
        for item in value:
            if not isinstance(item, str):
                msg = f"applyTo list entries must be strings, got {type(item).__name__}"
                raise UnsupportedApplyToError(msg)
            globs.extend(_split_glob_aware(item, ","))
        return globs
    msg = f"applyTo must be a string or list of strings, got {type(value).__name__}"
    raise UnsupportedApplyToError(msg)


def parse_applyto(text: str) -> set[str]:
    """Extract the ``applyTo`` glob set from a rule file's frontmatter.

    Parses the frontmatter as YAML so quoting, inline comments, flow lists, and
    block-style lists are handled by the parser rather than a line regex (a
    regex that grabbed everything after ``applyTo:`` would fold a trailing
    ``# comment`` into the glob and would miss a block-style list entirely).
    Splits the comma-separated scope list without breaking brace groups, then
    expands each brace group so ``**/*.{py,pyi}`` becomes two concrete globs.

    Fails closed: invalid YAML or a duplicate top-level key raises
    ``UnsupportedApplyToError`` rather than yielding an empty set, so a file the
    parser cannot resolve cannot silently contribute zero bytes and slip past
    the ceiling. A file with no frontmatter block, or frontmatter without an
    ``applyTo`` key, is legitimately unscoped and returns an empty set.
    """
    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match is None:
        return set()
    try:
        data = yaml.load(fm_match.group(1), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        msg = f"frontmatter is not valid YAML: {exc}"
        raise UnsupportedApplyToError(msg) from exc
    if not isinstance(data, dict) or "applyTo" not in data:
        return set()
    patterns: set[str] = set()
    for glob in _iter_applyto_globs(data["applyTo"]):
        cleaned = glob.strip()
        if cleaned:
            patterns.update(expand_braces(cleaned))
    return patterns


def is_language_universal(patterns: set[str], ext: str) -> bool:
    """True when the rule's ``applyTo`` scopes it to every file of ``ext``.

    Universality is a property of the *union* of the comma-split patterns, not
    of any single pattern. VS Code's instruction matcher (``_matches`` in
    computeAutomaticInstructions.ts, pinned line 293-327) splits ``applyTo`` on
    commas and attaches the rule to a file if *any* one pattern matches it. So
    the rule loads for every file of the language exactly when *every* probe
    path is matched by *at least one* pattern:
    ``all(any(pattern matches probe) for probe in probes)``. Checking each
    pattern in isolation would under-count a rule whose depths are split across
    disjoint globs (``/*.py, /*/*.py, /*/**/*.py``), letting a large rule dodge
    the always-on budget. Under-count is the dangerous direction for an upper
    bound, so the union model is required, not merely more precise.

    Each pattern is first reduced to its harness-effective form
    (``_vscode_effective_glob`` prepends ``**/`` to a relative pattern) and then,
    unless it is an all-files wildcard, compiled to a faithful VS Code regex
    (``_glob_to_regex``) and tested against every probe (``_probe_paths``).
    Deciding by *matching* rather than enumerating spellings closes the whole
    class of broad forms an exact-form table missed (``?`` wildcards,
    zero-segment globstars, absolute anchors, any-dotted-basename) while keeping
    scoped globs such as ``**/src/*.py`` out of the baseline. Matching is
    case-insensitive to mirror the harness (``ignoreCase: true``).
    """
    probes = _probe_paths(ext)
    regexes: list[re.Pattern[str]] = []
    for pattern in patterns:
        effective = _vscode_effective_glob(pattern)
        if effective in _ALL_FILES_FORMS:
            return True
        regexes.append(_glob_to_regex(effective))
    if not regexes:
        return False
    return all(any(regex.match(path) for regex in regexes) for path in probes)


@dataclass(frozen=True)
class InstructionFile:
    """A single instruction file with its measured size and scope."""

    name: str
    size_bytes: int
    estimated_tokens: int
    patterns: frozenset[str]


@dataclass(frozen=True)
class ExtensionResult:
    """Always-on budget measurement for one representative extension."""

    extension: str
    matched_files: tuple[str, ...]
    total_bytes: int
    estimated_tokens: int
    ceiling_bytes: int

    @property
    def usage_percent(self) -> float:
        if self.ceiling_bytes <= 0:
            return 0.0
        return round((self.total_bytes / self.ceiling_bytes) * 100, 1)

    @property
    def over_budget(self) -> bool:
        return self.total_bytes > self.ceiling_bytes


def _resolve_safe(repo_root: Path, relative: str) -> Path | None:
    """Resolve a relative path safely within repo_root (CWE-22 protection)."""
    candidate = (repo_root / relative).resolve()
    root_resolved = repo_root.resolve()
    if not candidate.is_relative_to(root_resolved):
        return None
    return candidate


def load_instruction_files(repo_root: Path) -> list[InstructionFile]:
    """Read every instruction file, measuring size and parsing ``applyTo``."""
    instructions_dir = _resolve_safe(repo_root, INSTRUCTIONS_SUBDIR)
    if instructions_dir is None or not instructions_dir.is_dir():
        return []
    files: list[InstructionFile] = []
    for path in sorted(instructions_dir.rglob(INSTRUCTION_GLOB)):
        content = path.read_text(encoding="utf-8", errors="replace")
        files.append(
            InstructionFile(
                name=path.name,
                size_bytes=len(content.encode("utf-8")),
                estimated_tokens=estimate_token_count(content),
                patterns=frozenset(parse_applyto(content)),
            )
        )
    return files


def measure_extension(
    files: list[InstructionFile],
    ext: str,
    ceiling_bytes: int,
) -> ExtensionResult:
    """Sum the always-on budget for one extension across all instruction files."""
    matched = [f for f in files if is_language_universal(set(f.patterns), ext)]
    return ExtensionResult(
        extension=ext,
        matched_files=tuple(f.name for f in matched),
        total_bytes=sum(f.size_bytes for f in matched),
        estimated_tokens=sum(f.estimated_tokens for f in matched),
        ceiling_bytes=ceiling_bytes,
    )


def evaluate(repo_root: Path, ceilings: dict[str, int]) -> list[ExtensionResult]:
    """Measure the always-on budget for every configured extension."""
    files = load_instruction_files(repo_root)
    return [
        measure_extension(files, ext, ceilings[ext])
        for ext in sorted(ceilings)
    ]


def format_table(results: list[ExtensionResult]) -> str:
    """Format results as a readable table."""
    lines: list[str] = []
    header = (
        f"{'Ext':<6} {'Files':>6} {'Bytes':>9} "
        f"{'Ceiling':>9} {'Tokens~':>9} {'Usage':>8} {'Status':>7}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in results:
        status = "FAIL" if r.over_budget else "PASS"
        lines.append(
            f"{r.extension:<6} {len(r.matched_files):>6} {r.total_bytes:>9} "
            f"{r.ceiling_bytes:>9} {r.estimated_tokens:>9} {r.usage_percent:>7.1f}% {status:>7}"
        )
    return "\n".join(lines)


def format_json(results: list[ExtensionResult]) -> str:
    """Format results as JSON for machine consumption."""
    data = [
        {
            "extension": r.extension,
            "matched_files": list(r.matched_files),
            "file_count": len(r.matched_files),
            "total_bytes": r.total_bytes,
            "estimated_tokens": r.estimated_tokens,
            "ceiling_bytes": r.ceiling_bytes,
            "usage_percent": r.usage_percent,
            "over_budget": r.over_budget,
        }
        for r in results
    ]
    return json.dumps(data, indent=2)


def parse_ceiling_override(value: str) -> tuple[str, int]:
    """Parse a '.ext:bytes' ceiling override string."""
    parts = value.rsplit(":", 1)
    if len(parts) != 2:
        msg = f"Invalid ceiling format '{value}'. Expected '.ext:bytes'."
        raise argparse.ArgumentTypeError(msg)
    ext = parts[0] if parts[0].startswith(".") else f".{parts[0]}"
    try:
        ceiling = int(parts[1])
    except ValueError:
        msg = f"Invalid byte count in '{value}'. Must be an integer."
        raise argparse.ArgumentTypeError(msg) from None
    if ceiling <= 0:
        msg = f"Ceiling must be positive, got {ceiling}."
        raise argparse.ArgumentTypeError(msg)
    return ext, ceiling


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Measure and gate the always-on instruction budget per language.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("REPO_PATH", "."),
        help="Path to the repository root (env: REPO_PATH, default: '.')",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit 1 on any budget exceeded (env: CI)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        dest="output_format",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--ceiling",
        action="append",
        type=parse_ceiling_override,
        default=[],
        metavar="EXT:BYTES",
        help="Override ceiling for an extension (e.g., '.py:200000'). Repeatable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_path = Path(args.path).resolve()
    if not repo_path.is_dir():
        print(f"Error: path is not a directory: {args.path}", file=sys.stderr)
        return 2

    if _resolve_safe(repo_path, INSTRUCTIONS_SUBDIR) is None or not (
        repo_path / INSTRUCTIONS_SUBDIR
    ).is_dir():
        print(f"Error: instructions directory not found: {INSTRUCTIONS_SUBDIR}", file=sys.stderr)
        return 2

    ceilings = dict(DEFAULT_CEILINGS_BYTES)
    for ext, ceiling in args.ceiling:
        ceilings[ext] = ceiling

    try:
        results = evaluate(repo_path, ceilings)
    except UnsupportedApplyToError as exc:
        print(f"Error: unsupported applyTo in an instruction file: {exc}", file=sys.stderr)
        return 2
    any_over = any(r.over_budget for r in results)

    if args.output_format == "json":
        print(format_json(results))
    else:
        print("Always-On Instruction Budget (language baseline)")
        print()
        print(format_table(results))
        if any_over:
            print()
            print("FAIL: One or more languages exceed the always-on instruction ceiling.")
            print()
            print("Action Required:")
            print("  1. Move situational or book-derived rules to task-invoked skills (#3419).")
            print("  2. Scope rules with a narrower applyTo instead of '**' or '**/*.<ext>'.")
            print("  3. If a raise is truly justified, edit DEFAULT_CEILINGS_BYTES and say why.")
        else:
            print()
            print("PASS: All languages within the always-on instruction ceiling.")

    if any_over and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
