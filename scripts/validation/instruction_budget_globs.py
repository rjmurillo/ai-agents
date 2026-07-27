"""VS Code applyTo glob parsing for instruction budget validation."""

from __future__ import annotations

import re
from collections.abc import Hashable
from functools import cache

import yaml

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
# drift. Braces are compiled inline as a regex alternation by
# ``_segment_to_regex`` (each choice re-parsed as a full glob, faithful to VS
# Code), so ``*``, ``?``, ``**``, and ``{...}`` are all translated here.
# Character classes (``[...]``) are the one glob construct this compiler does
# not model, and it fails closed on them. Dear future maintainer: an earlier
# revision treated ``[`` as a literal, reasoning a class is "scoped by
# construction" and can only over-restrict. That was wrong. ``[p]`` pins its
# character, so ``**/*.[p]y`` equals ``**/*.py`` and IS universal under the
# harness, but the literal-``[`` regex ``\[p\]y`` matches nothing and scores the
# rule non-universal -> the budget UNDER-counts (the one unsafe direction, it
# lets an always-loaded rule dodge the ceiling). Parsing brackets faithfully
# (ranges, negation, leading ``]``) is fragile, so instead any ``applyTo`` glob
# containing ``[`` raises ``UnsupportedApplyToError`` (exit 2). No repo rule uses
# a bracket class, so this blocks nothing today; a future author who needs one
# expands it into comma or brace alternatives (``*.[ch]`` -> ``*.c, *.h``).
# Fail-closed can only over-block (a scoped rule reddens the gate, never dodges
# it), keeping the budget an honest upper bound without a bracket parser.
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

    Mirrors VS Code's per-character walk inside a segment (``parseRegExp``,
    glob.ts): ``*`` becomes a single-star run (``starsToRegExp(1)``), ``?``
    matches one non-separator character, a ``{...}`` group compiles *inline* to a
    regex alternation whose choices are each parsed as a full glob
    (``{a,b}`` -> ``(?:<a>|<b>)``), and every other character is escaped
    literally. Compiling braces inline, rather than pre-expanding them into
    concrete strings, is what keeps the model faithful for options that carry
    path syntax (``{**/*}``), nest (``{a,{b,c}}``), or leave a trailing empty
    (``{x,}`` matches only ``x`` because VS Code's ``splitGlobAware`` drops the
    trailing empty, whereas ``{}`` is a real empty substitution). Bracket
    classes never reach here: ``_glob_to_regex`` fails closed on any ``[``.
    """
    out: list[str] = []
    in_braces = False
    brace_val: list[str] = []
    for char in segment:
        if char != "}" and in_braces:
            brace_val.append(char)
            continue
        if char == "{":
            in_braces = True
            continue
        if char == "}":
            choices = _split_glob_aware("".join(brace_val), ",")
            out.append("(?:" + "|".join(_parse_regexp(choice) for choice in choices) + ")")
            in_braces = False
            brace_val = []
            continue
        if char == "*":
            out.append(_stars_to_regexp(1, is_last_segment=False))
            continue
        if char == "?":
            out.append(_NO_PATH_REGEX)
            continue
        out.append(re.escape(char))
    return "".join(out)


def _parse_regexp(pattern: str) -> str:
    """Compile a single glob to a regex body, porting VS Code ``parseRegExp``.

    Splits the glob into path segments (brace- and bracket-aware), translates a
    whole-segment ``**`` to the globstar regex, and joins segments with the
    harness "Tail" separator rule. Returns the regex *body* (no anchors) so a
    brace choice can be spliced back into its parent segment; ``_glob_to_regex``
    wraps the result in ``^...$``. Recurses through ``_segment_to_regex`` for
    each brace alternative, so a choice may itself contain ``/`` and ``**``
    exactly as VS Code allows.
    """
    if not pattern:
        return ""
    segments = _split_glob_aware(pattern, "/")
    if segments and all(segment == _GLOB_STAR for segment in segments):
        return ".*"
    body: list[str] = []
    last = len(segments) - 1
    previous_was_globstar = False
    for index, segment in enumerate(segments):
        if segment == _GLOB_STAR:
            if not previous_was_globstar:
                body.append(_stars_to_regexp(2, is_last_segment=index == last))
            previous_was_globstar = True
            continue
        body.append(_segment_to_regex(segment))
        if index < last and (segments[index + 1] != _GLOB_STAR or index + 2 < len(segments)):
            body.append(_PATH_REGEX)
        previous_was_globstar = False
    return "".join(body)


@cache
def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile an ``applyTo`` glob to an anchored case-insensitive regex.

    Faithful port of VS Code's ``parseRegExp`` (see the module note above the
    constants). Fails closed on a character class before compiling: the compiler
    models ``*``, ``?``, ``**``, and ``{...}`` inline, but not ``[...]`` (see the
    note for why a literal ``[`` would under-count). Path-segment semantics match
    the harness:

    - ``**`` as a whole segment matches zero or more complete path segments;
    - ``*`` matches zero or more non-separator characters within one segment;
    - ``?`` matches exactly one non-separator character;
    - ``{a,b}`` compiles inline to ``(?:<a>|<b>)`` with each choice parsed as a
      full glob;
    - a literal separator is emitted after a segment unless the following
      segment is a *terminal* ``**`` (VS Code's "Tail" rule), so ``some/**/*.js``
      keeps the ``/`` after ``some`` and a sibling folder ``something`` cannot
      match, while ``/*/**/*.py`` requires a real first directory and does not
      match a root file.

    Case-insensitive because VS Code matches ``applyTo`` with ``ignoreCase:
    true``. ``is_language_universal`` uses this to decide universality by
    *matching* diverse probe paths instead of enumerating glob spellings.
    """
    if "[" in pattern:
        msg = (
            f"applyTo glob {pattern!r} uses a character class ('['); the budget "
            "gate does not model bracket expressions and fails closed rather than "
            "risk under-counting a universal pattern. Expand the class into comma "
            "or brace alternatives (e.g. '*.[ch]' -> '*.c, *.h')."
        )
        raise UnsupportedApplyToError(msg)
    return re.compile("^" + _parse_regexp(pattern) + "$", re.IGNORECASE)


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
    Splits the comma-separated scope list without breaking brace groups. Each
    glob keeps its brace group intact; ``is_language_universal`` compiles it with
    VS Code's inline brace semantics, so ``**/*.{py,pyi}`` is matched as one
    pattern rather than textually pre-expanded (which was unfaithful for nested
    or path-bearing brace options).

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
            patterns.add(cleaned)
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
    effectives = [_vscode_effective_glob(pattern) for pattern in patterns]
    if any(effective in _ALL_FILES_FORMS for effective in effectives):
        return True
    regexes = [_glob_to_regex(effective) for effective in effectives]
    if not regexes:
        return False
    return all(any(regex.match(path) for regex in regexes) for path in probes)
