#!/usr/bin/env python3
"""Grammar, partial-tree validation, and rendering for the ADR-108 skill-template compile step.

Split out of ``build/scripts/skill_templates.py`` (taste-lint file-size
ceiling; ADR review round for #5706) along the seam ADR-108's own class
description draws: this module is everything that turns one template's TEXT
into rendered TEXT (or a config/logic error), and ``skill_templates.py``
keeps everything that turns the FILESYSTEM (``templates/skills/``,
``.claude/skills/``) into a set of templates to compile. ``skill_templates``
re-exports every public name here (``render``, ``check_grammar``, and the
four exception classes), so ``skill_templates.render(...)``,
``skill_templates.TemplateGrammarError``, etc. keep working unchanged for
every existing caller and test.

Template grammar, quoted verbatim from
``.agents/specs/design/DESIGN-024-skill-guidance-excerpt-sync.md``, "Template
grammar" section:

    A template is the current ``SKILL.md`` text with two kinds of tag and no
    others:

    - ``{{> slug}}`` on its own line, optionally indented: expands to the
      partial ``templates/skills/partials/<slug>.mustache``. Chevron
      preserves the indentation on every line of the partial (verified
      2026-09-11 with ``chevron==0.14.0``).
    - ``{{! text }}``: a comment, rendered as nothing.
    - ``\\{{`` (ADR-108 amended 2026-09-14): a literal ``{{`` in the output.
      Protected before every check, restored last; a backslash before a
      tag always escapes it.

    Any other tag is a configuration error (exit 2) before rendering:
    ``{{var}}``, ``{{{raw}}}``, ``{{#s}}``, ``{{^s}}``, ``{{/s}}``,
    ``{{=<% %>=}}``. Reason: chevron renders an unknown variable and a
    missing partial as empty text with no error (probed 2026-09-11), so the
    grammar check is the only thing that turns a typo into a failure. Slug
    pattern ``^[a-z0-9]+(-[a-z0-9]+)*$``.

Verified independently in this session, against ``chevron==0.14.0``, the same
silent-empty-text claim ADR-108 section 1 makes ("chevron renders a missing
partial and an unknown variable as empty text with no error") and section 4
relies on for why drift is caught by the compare-then-gate design here rather
than by chevron raising on its own:

    >>> chevron.render("A{{> nope}}B", {}, partials_dict={})
    'AB'
    >>> chevron.render("A{{x}}B", {})
    'AB'

Both return ``"AB"``, not an error and not a literal ``"{{> nope}}"`` or
``"{{x}}"`` in the output. This is why :func:`check_grammar` and the
partial-existence check inside :func:`_validate_partial_tree` run BEFORE
``chevron.render`` in :func:`render` below, and why they recurse through
every partial the template (transitively) includes rather than checking the
template text alone: chevron itself has no failure mode for either case, so
it cannot be the thing that turns a typo'd slug or a disallowed tag into a
build failure, wherever in the include chain it appears.

A third silent case, found in ADR review round 4 for #5706: a partial file
that does not end with exactly one trailing newline gets glued to whatever
template text follows its tag, with no error and no leftover ``{{`` for the
post-render scan to catch either. Reproduced against ``chevron==0.14.0``:

    >>> chevron.render("Line before.\n{{> p}}\nLine after.\n", {}, partials_dict={"p": "X"})
    'Line before.\nXLine after.\n'

``"Line after."`` is not on its own line; it is glued directly onto the
partial's content because the partial supplied no newline to separate them.
The identical call with ``partials_dict={"p": "X\n"}`` (the partial ending in
exactly one newline) returns ``'Line before.\nX\nLine after.\n'``, the
correct, separated result. Every ``templates/skills/partials/*.mustache``
file MUST therefore end with exactly one trailing newline; :func:`render`
checks every partial name a template references before calling
``chevron.render``, alongside the existence check, so a partial missing this
property is a configuration error (exit 2) naming the partial's path,
rather than glued prose nobody notices until it ships.

EXIT CODES (per :func:`render`; ``skill_templates.compile_all`` folds these
into its own aggregate, worst-code-wins exit code):
  (success) - the template and every partial it (transitively) includes is
      grammatically clean, every referenced partial exists, ends with
      exactly one trailing newline, and the rendered output carries no
      unresolved ``{{``
  1 - ``UnresolvedTagError``: rendered output still contains a literal ``{{``
  2 - ``TemplateGrammarError``: the template or a partial used a disallowed
      tag, chevron raised on a malformed tag, or a partial cycle was
      detected; ``MissingPartialError``: a referenced partial does not
      exist; ``PartialNewlineError``: a referenced partial does not end
      with exactly one trailing newline

Per AGENTS.md Standards (``0=ok|1=logic|2=config``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

import chevron  # type: ignore[import-untyped]

_PARTIAL_EXT = "mustache"

# Matches a triple-brace (raw) tag before the double-brace alternative, so
# `{{{raw}}}` is captured whole instead of leaving a trailing `}` behind.
_TAG_RE = re.compile(r"\{\{\{.*?\}\}\}|\{\{.*?\}\}", re.DOTALL)
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_PARTIAL_TAG_RE = re.compile(rf"^\{{\{{>\s*({_SLUG})\s*\}}\}}$")
_COMMENT_TAG_RE = re.compile(r"^\{\{!.*\}\}$", re.DOTALL)

# Literal-brace escape (ADR-108, amended 2026-09-14 for ADR-109 B2). A
# template or partial that must emit a literal ``{{`` (a GitHub Actions
# ``${{ expr }}`` in a fenced example, for instance) writes ``\{{``. The
# escape is swapped for a control-character marker before grammar checks
# and before chevron sees the text, so it is never read as a tag and never
# trips the post-render ``{{`` scan; the marker is swapped back to ``{{``
# as the final step. NUL cannot appear in a Markdown source file, so the
# marker cannot collide with template text (a NUL in a source is refused
# outright). A backslash directly before a tag always escapes it, so
# "backslash then a live tag" is not expressible; `\\{{` renders `\{{`.
_LITERAL_BRACE_ESCAPE = "\\{{"
_LITERAL_BRACE_MARKER = "\x00LBRACE\x00"


def _reject_nul(text: str, source: Path) -> None:
    """Refuse a source carrying NUL: it could forge the escape marker (exit 2)."""
    if "\x00" in text:
        raise TemplateGrammarError(f"{source}: NUL byte in template text")


def _protect_escapes(text: str) -> str:
    r"""Replace every ``\{{`` with the marker so no reader treats it as a tag."""
    return text.replace(_LITERAL_BRACE_ESCAPE, _LITERAL_BRACE_MARKER)


def _restore_escapes(text: str) -> str:
    """Turn every marker back into the literal ``{{`` the author asked for."""
    return text.replace(_LITERAL_BRACE_MARKER, "{{")


class TemplateGrammarError(Exception):
    """A template contains a tag outside the restricted grammar. Exit 2."""


class MissingPartialError(Exception):
    """A template names a partial with no matching ``.mustache`` file. Exit 2."""


class PartialNewlineError(Exception):
    """A referenced partial does not end with exactly one trailing newline. Exit 2.

    See the module docstring's ``chevron.render(..., partials_dict={"p": "X"})``
    probe: a partial with no trailing newline glues onto whatever template text
    follows its tag, silently, with no ``{{`` left over for the post-render scan.
    """


class UnresolvedTagError(Exception):
    """Rendered output still contains the literal ``{{``. Exit 1."""


def _iter_tags(text: str) -> Iterator[re.Match[str]]:
    # Callers that inspect match positions (``_is_standalone``) must scan
    # the same protected text, so the protection happens here, once.
    yield from _TAG_RE.finditer(_protect_escapes(text))


def _is_standalone(text: str, match: re.Match[str]) -> bool:
    """True when ``match`` is alone on its line in ``text``, apart from whitespace.

    The grammar (module docstring, "Template grammar", quoted from
    DESIGN-024) requires ``{{> slug}}`` "on its own line, optionally
    indented". ``_PARTIAL_TAG_RE`` on its own only checks the TAG STRING in
    isolation (``^\\{\\{>...\\}\\}$``), which is anchored against
    ``match.group(0)``, not against the line the tag sits on, so it matches
    identically whether the tag is alone on a line or embedded mid-sentence.
    This checks the surrounding text instead: the line containing the
    match, after stripping leading/trailing whitespace, must equal the
    matched tag text exactly.
    """
    text = _protect_escapes(text)
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip() == match.group(0)


def check_grammar(text: str) -> list[str]:
    """Return every tag in ``text`` outside the restricted grammar.

    A tag is allowed when it is a comment (``{{! ... }}``) or a partial
    reference (``{{> slug}}``, slug matching ``^[a-z0-9]+(-[a-z0-9]+)*$``)
    that also sits alone on its own line, optionally indented
    (:func:`_is_standalone`; CodeRabbit review, PR #5726, "own-line partial
    rule documented but not enforced": the grammar the module docstring
    quotes from DESIGN-024 requires this placement, but until this check
    existed only the tag's own syntax was validated, so ``See {{> greet}}
    for details.`` passed ``check_grammar`` clean even though the partial
    was never on its own line). Everything else (a variable, a section, an
    inverted section, a raw triple-brace, a set-delimiter change, a
    malformed partial tag, or a syntactically valid partial tag sharing its
    line with other text or another tag) is offending. Empty list means the
    template is clean.
    """
    offending: list[str] = []
    for match in _iter_tags(text):
        tag = match.group(0)
        if _COMMENT_TAG_RE.match(tag):
            continue
        if _PARTIAL_TAG_RE.match(tag) and _is_standalone(text, match):
            continue
        offending.append(tag)
    return offending


def _partial_slugs(text: str) -> list[str]:
    slugs: list[str] = []
    for match in _iter_tags(text):
        partial_match = _PARTIAL_TAG_RE.match(match.group(0))
        if partial_match:
            slugs.append(partial_match.group(1))
    return slugs


def _validate_partial_tree(
    text: str,
    partials_dir: Path,
    *,
    source: Path,
    visited: frozenset[Path],
) -> None:
    """Recursively validate grammar, partial existence, and trailing newlines.

    ``text`` is the content of ``source`` (the top-level template on the
    first call, one partial's content on every recursive call). Runs
    :func:`check_grammar` on it, then for each partial slug it references:
    the partial file must exist; it must not already be in ``visited`` (a
    partial that transitively includes itself is a config error, the same
    as any other malformed reference, not a silent infinite expansion); and
    its content must end with exactly one trailing newline (module
    docstring). Then recurses into that partial's own content with the same
    three checks.

    BLOCKING finding, ADR review round for #5706: the three checks
    originally ran on the top-level template only. A partial carrying
    ``{{name}}`` or referencing a nonexistent nested partial rendered
    silently (chevron drops both to empty text, per the module docstring's
    probe) and the file was written with exit 0. Recursing through every
    reachable partial, not only the ones the template names directly,
    closes that: the same three checks that already gated the template now
    gate everything the template pulls in.

    Raises on the first problem found, naming ``source``: the exact file
    (the template, or the specific partial) the offending text came from,
    not always the top-level ``tmpl_path``.
    """
    offending = check_grammar(text)
    if offending:
        raise TemplateGrammarError(
            f"{source}: disallowed tag(s) outside {{> slug}} / {{! comment}}: "
            f"{', '.join(offending)}"
        )

    seen_here: set[str] = set()
    for slug in _partial_slugs(text):
        if slug in seen_here:
            continue
        seen_here.add(slug)

        partial_path = partials_dir / f"{slug}.{_PARTIAL_EXT}"

        if partial_path.is_symlink():
            raise MissingPartialError(
                f"{source}: partial {slug!r} is a symlink; partials must be regular files"
            )
        if not partial_path.is_file():
            raise MissingPartialError(f"{source}: missing partial(s) under {partials_dir}: {slug}")
        if partial_path in visited:
            raise TemplateGrammarError(
                f"{source}: partial cycle detected: {partial_path} is already "
                "being expanded earlier in this include chain"
            )

        content = partial_path.read_text(encoding="utf-8", newline="")
        if not content.endswith("\n") or content.endswith("\n\n"):
            raise PartialNewlineError(
                f"{source}: partial missing exactly one trailing newline: {partial_path}"
            )

        _validate_partial_tree(
            content, partials_dir, source=partial_path, visited=visited | {partial_path}
        )


def _load_protected_partials(partials_dir: Path) -> dict[str, str]:
    """Read every ``*.mustache`` under ``partials_dir`` with escapes protected.

    chevron's ``partials_path`` reads partial files itself, which would hand
    an unprotected ``\\{{`` straight to the tokenizer. Loading them here and
    passing ``partials_dict`` keeps the escape contract identical for
    templates and partials. Keys are slugs (file stem); nested partial
    references resolve through the same dict.

    ``partials_dir`` itself MUST NOT be a symlink: every compile module
    (``agent_templates``, ``rule_templates``, ``skill_templates``) calls
    :func:`render`, which calls this unconditionally, so a symlinked
    partials directory would glob and read whatever real directory it
    points at, symlink target files included, none of which ``is_dir()``
    alone would catch (it follows the link). Refused with the same error
    type a refused individual partial already raises
    (:func:`_validate_partial_tree`'s ``partial_path.is_symlink()`` check
    above), so every caller gets the guard without a per-module change
    (CodeRabbit review).
    """
    if partials_dir.is_symlink():
        raise MissingPartialError(
            f"{partials_dir}: partials directory is a symlink, not a real directory"
        )
    if not partials_dir.is_dir():
        return {}
    loaded: dict[str, str] = {}
    for path in sorted(partials_dir.glob(f"*.{_PARTIAL_EXT}")):
        raw = path.read_text(encoding="utf-8", newline="")
        _reject_nul(raw, path)
        loaded[path.stem] = _protect_escapes(raw)
    return loaded


def render(tmpl_path: Path, partials_dir: Path) -> str:
    """Render one template to text, per the compile module's ``render`` contract.

    Order: recursive grammar / partial-existence / trailing-newline
    validation of the template and every partial it (transitively)
    includes (exit 2; see :func:`_validate_partial_tree`), then chevron
    render, then a ``{{`` scan of the OUTPUT (exit 1). The output scan
    exists because chevron renders a missing partial and an unknown
    variable as empty text with no error (module docstring, "Template
    grammar"), so a partial file that itself carries literal ``{{`` text
    (unlikely, but not excluded by the grammar check) would otherwise leak
    an unresolved tag into the rendered ``SKILL.md`` undetected.
    """
    text = tmpl_path.read_text(encoding="utf-8", newline="")

    _validate_partial_tree(text, partials_dir, source=tmpl_path, visited=frozenset())
    _reject_nul(text, tmpl_path)
    text = _protect_escapes(text)
    partials = _load_protected_partials(partials_dir)

    try:
        # chevron ships no type stubs (pyproject.toml's chevron.* mypy
        # override), so its return value is Any; str() pins the type this
        # function actually declares and is a no-op at runtime given
        # chevron.render always returns str.
        rendered = str(chevron.render(text, {}, partials_dict=partials))
    except chevron.ChevronError as exc:
        # Not one of the module docstring's three named failure classes:
        # probed 2026-09-11 against chevron==0.14.0, an unclosed tag anywhere
        # in the template or a partial it includes (a real typo, not one of
        # the six named disallowed constructs `check_grammar` already
        # rejects) raises `chevron.tokenizer.ChevronError` from inside the
        # renderer rather than emitting empty text the way a missing partial
        # or unknown variable does. Left uncaught this would surface as a
        # raw traceback instead of a controlled exit code. It is a
        # malformed-tag shape, so it is graded exit 2 alongside the grammar
        # and missing-partial failures rather than exit 1.
        raise TemplateGrammarError(f"{tmpl_path}: {exc}") from exc
    if "{{" in rendered:
        raise UnresolvedTagError(
            f"{tmpl_path}: rendered output still contains an unresolved '{{{{' tag"
        )
    return _restore_escapes(rendered)
