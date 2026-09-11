#!/usr/bin/env python3
"""Compile ``templates/skills/*.SKILL.md.tmpl`` into ``.claude/skills/<name>/SKILL.md``.

ADR-108 (Template-Owned Skill Files Under ``.claude/skills/``) amends
REQ-003-010 and ADR-107 property 1 for exactly one artifact class: a skill
whose canonical source is a mustache template under ``templates/skills/``.
This module is that class's compile step, per
``.agents/specs/design/DESIGN-020-skill-guidance-excerpt-sync.md``, "Compile
module: ``build/scripts/skill_templates.py``":

    ``discover(repo_root) -> dict[str, Path]``
        ``{name: templates/skills/<name>.SKILL.md.tmpl}``; name is the
        filename minus ``.SKILL.md.tmpl``.
    ``owned_targets(repo_root) -> set[Path]``
        ``{.claude/skills/<name>/SKILL.md}`` for every discovered template;
        the allowlist ``build_all.py`` passes to the guard.
    ``check_grammar(text) -> list[str]``
        Offending tags; empty when only partial and comment tags are
        present.
    ``render(tmpl_path, partials_dir) -> str``
        Recursive grammar check, partial existence check, and partial
        trailing-newline check over the template and every partial it
        (transitively) includes, with cycle detection, then
        ``chevron.render(text, {}, partials_path=...,
        partials_ext="mustache")``, then a ``{{`` scan of the output.
    ``compile_all(repo_root, *, validate, what_if) -> CompileResult``
        For each template: skip (unchanged, WARN, exit 1) when
        ``regen_guard.detect_reason(target)`` is not ``None``; in validate
        mode compare and record drift; otherwise write when the bytes
        differ. Returns written, skipped, drifted, and an exit code (0
        pass, 1 drift, unresolved ``{{``, or a NO-REGEN skip, 2 grammar
        (template or any included partial), a missing or cyclic partial,
        a partial missing its trailing newline, or
        missing target directory).

Stricter/looser/different than canonical: DESIGN-020's table above says a
NO-REGEN skip on a template-owned target is "skipped, NOTICE printed, exit
0" and ADR-108 section 4 describes the same sentinel "the same way
``_copy_skill_tree`` skips it", both matching the plain ``NOTICE: skipped
...`` / exit-0 treatment ``generate_skills._copy_skill_tree`` already gives
the sentinel on every OTHER skill file. :func:`compile_all` diverges on
both counts for a template-owned target: it prints ``WARN: skipped ... ;
template-owned file exempt from drift gate`` instead of a NOTICE, and it
raises ``exit_code`` to at least 1 for that file, never 0, in ``compile_all``
itself under both its modes (write, ``validate=False``, and validate,
``validate=True``). That 1 reaches a caller unchanged through
``generate_skills.py`` (both the normal path and ``--validate``): neither
wraps or remaps ``compile_all``'s exit code. It does NOT surface as 1 through
``build_all.py --check``: ``build_all._build_skills`` coerces any nonzero
``generate_skills.generate_skills(..., validate=check)`` result to exit 2
when ``check`` is set (``build/scripts/build_all.py``, the
``if check and rc != 0: rc = 2`` line in ``_build_skills``), the same code
that function already uses for staleness and config errors under ``--check``.
So a NO-REGEN-skipped template-owned target is exit 1 from ``compile_all``
and ``generate_skills.py --validate``, but exit 2 as observed from
``build_all.py --check``.

The reason for both: for every OTHER file ``_copy_skill_tree`` mirrors, a
NO-REGEN skip means "this destination is not generated at all", the routine
case a silent, exit-0 NOTICE fits. For a template-owned target, the file IS
generated, so a NO-REGEN sentinel on it is the file's sole declared
exemption from ADR-108's only gate (the drift check this same function
performs in validate mode) and from the write this function otherwise
performs. Section 4 also says drift "is a gate, not a header": a gate that
a sentinel can silence and still report success is not closed, it degrades
to advisory the moment anyone reaches for the escape hatch. Fail closed
instead: the skip is unchanged (never written, never treated as drift
either), reported louder than a routine skip, and the run does not report
clean while a target-owned file sits outside the gate's coverage. This
diverges from issue #5706 step 10's own acceptance line by design, decided
in ADR review for #5706 after DESIGN-020 and ADR-108 were already recorded;
neither document is amended by this file, the divergence lives here.

Template grammar, quoted verbatim from the same design document's "Template
grammar" section:

    A template is the current ``SKILL.md`` text with two kinds of tag and no
    others:

    - ``{{> slug}}`` on its own line, optionally indented: expands to the
      partial ``templates/skills/partials/<slug>.mustache``. Chevron
      preserves the indentation on every line of the partial (verified
      2026-09-11 with ``chevron==0.14.0``).
    - ``{{! text }}``: a comment, rendered as nothing.

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

EXIT CODES (per ``compile_all``, and surfaced by callers unchanged):
  0 - no templates, or every template renders clean (write mode) / matches
      the committed file (validate mode)
  1 - a rendered file drifted from the committed one (validate mode), the
      rendered text still contains an unresolved ``{{`` after render, or a
      NO-REGEN-skipped template-owned target (see the "Stricter/looser/
      different than canonical" section below)
  2 - the template, or any partial it (transitively) includes, used a
      disallowed tag or named a partial that does not exist or forms an
      include cycle; a referenced partial that does not end with exactly
      one trailing newline; or the target's parent directory does not exist

Per AGENTS.md Standards (``0=ok|1=logic|2=config``); the worst code wins
across all discovered templates in one ``compile_all`` call, matching
``scripts/validation/evidence.py:exit_code_for``'s "worst class wins" idiom.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

import chevron  # type: ignore[import-untyped]

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from regen_guard import detect_reason  # noqa: E402

_TEMPLATE_SUFFIX = ".SKILL.md.tmpl"
_PARTIAL_EXT = "mustache"

# Matches a triple-brace (raw) tag before the double-brace alternative, so
# `{{{raw}}}` is captured whole instead of leaving a trailing `}` behind.
_TAG_RE = re.compile(r"\{\{\{.*?\}\}\}|\{\{.*?\}\}", re.DOTALL)
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_PARTIAL_TAG_RE = re.compile(rf"^\{{\{{>\s*({_SLUG})\s*\}}\}}$")
_COMMENT_TAG_RE = re.compile(r"^\{\{!.*\}\}$", re.DOTALL)


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


@dataclass
class CompileResult:
    """Outcome of one :func:`compile_all` run across every discovered template."""

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    exit_code: int = 0


def discover(repo_root: Path) -> dict[str, Path]:
    """Return ``{name: template path}`` for every ``templates/skills/*.SKILL.md.tmpl``.

    ``name`` is the filename with the ``.SKILL.md.tmpl`` suffix stripped.
    An absent ``templates/skills/`` directory yields an empty mapping rather
    than an error: membership in the template-owned class is read from the
    directory at run time (ADR-108 section 1), so "no templates yet" is a
    valid, non-error state during migration.
    """
    templates_dir = repo_root / "templates" / "skills"
    if not templates_dir.is_dir():
        return {}
    result: dict[str, Path] = {}
    for path in sorted(templates_dir.glob(f"*{_TEMPLATE_SUFFIX}")):
        name = path.name[: -len(_TEMPLATE_SUFFIX)]
        result[name] = path
    return result


def owned_targets(repo_root: Path) -> set[Path]:
    """Return the allowlist :func:`build_all.assert_no_claude_writes` accepts.

    One absolute path per discovered template: ``.claude/skills/<name>/SKILL.md``.
    """
    return {
        repo_root / ".claude" / "skills" / name / "SKILL.md" for name in discover(repo_root)
    }


def _iter_tags(text: str) -> Iterator[re.Match[str]]:
    yield from _TAG_RE.finditer(text)


def check_grammar(text: str) -> list[str]:
    """Return every tag in ``text`` outside the restricted grammar.

    A tag is allowed when it is a partial reference (``{{> slug}}``, slug
    matching ``^[a-z0-9]+(-[a-z0-9]+)*$``) or a comment (``{{! ... }}``).
    Everything else (a variable, a section, an inverted section, a raw
    triple-brace, a set-delimiter change, or a malformed partial tag) is
    offending. Empty list means the template is clean.
    """
    offending: list[str] = []
    for match in _iter_tags(text):
        tag = match.group(0)
        if _PARTIAL_TAG_RE.match(tag) or _COMMENT_TAG_RE.match(tag):
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
        if not partial_path.is_file():
            raise MissingPartialError(
                f"{source}: missing partial(s) under {partials_dir}: {slug}"
            )
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


def render(tmpl_path: Path, partials_dir: Path) -> str:
    """Render one template to text, per the compile module's ``render`` contract.

    Order: recursive grammar / partial-existence / trailing-newline
    validation of the template and every partial it (transitively)
    includes (exit 2; see :func:`_validate_partial_tree`), then chevron
    render, then a ``{{`` scan of the OUTPUT (exit 1). The output scan
    exists because chevron renders a missing partial and an unknown
    variable as empty text with no error (DESIGN-020, "Template grammar"),
    so a partial file that itself carries literal ``{{`` text (unlikely,
    but not excluded by the grammar check) would otherwise leak an
    unresolved tag into the rendered ``SKILL.md`` undetected.
    """
    text = tmpl_path.read_text(encoding="utf-8", newline="")

    _validate_partial_tree(text, partials_dir, source=tmpl_path, visited=frozenset())

    try:
        # chevron ships no type stubs (pyproject.toml's chevron.* mypy
        # override), so its return value is Any; str() pins the type this
        # function actually declares and is a no-op at runtime given
        # chevron.render always returns str.
        rendered = str(
            chevron.render(text, {}, partials_path=str(partials_dir), partials_ext=_PARTIAL_EXT)
        )
    except chevron.ChevronError as exc:
        # Not one of DESIGN-020's three named failure classes: probed
        # 2026-09-11 against chevron==0.14.0, an unclosed tag anywhere in the
        # template or a partial it includes (a real typo, not one of the six
        # named disallowed constructs `check_grammar` already rejects) raises
        # `chevron.tokenizer.ChevronError` from inside the renderer rather
        # than emitting empty text the way a missing partial or unknown
        # variable does. Left uncaught this would surface as a raw traceback
        # instead of a controlled exit code. It is a malformed-tag shape, so
        # it is graded exit 2 alongside the grammar and missing-partial
        # failures rather than exit 1.
        raise TemplateGrammarError(f"{tmpl_path}: {exc}") from exc
    if "{{" in rendered:
        raise UnresolvedTagError(
            f"{tmpl_path}: rendered output still contains an unresolved '{{{{' tag"
        )
    return rendered


def compile_all(repo_root: Path, *, validate: bool, what_if: bool = False) -> CompileResult:
    """Compile every discovered template into its ``.claude/skills/`` target.

    ``validate=True``: never writes. A target whose committed bytes differ
    from the fresh render is recorded as drift, exit 1. ``validate=False``:
    writes the rendered bytes when they differ from what's on disk, unless
    ``what_if`` is set, in which case it reports what it would write without
    touching the filesystem (mirrors ``generate_skills.py --what-if``).

    A target carrying a NO-REGEN sentinel (``regen_guard.detect_reason``) is
    skipped before rendering is attempted, in both modes, the same way
    ``generate_skills._copy_skill_tree`` skips a protected file (no line
    citation here: both functions' NO-REGEN branch moves as this module
    grows, and a stale ``path:line`` fails the pre-PR citation-freshness
    gate faster than either function's line count changes).

    The sentinel exempts a target from this class's only gate (ADR-108
    section 4: "A rendered file carrying a NO-REGEN sentinel ... is skipped
    with a NOTICE"), in validate mode as much as in write mode. Fails
    closed rather than open: the target is left unchanged, kept out of
    ``drifted`` (a hand edit the author marked NO-REGEN is a declared
    divergence, not drift), reported at WARN rather than the plain NOTICE a
    routine skip gets, and ``exit_code`` is raised to at least 1 for every
    such target in both of THIS function's modes (write, validate). That 1
    reaches ``generate_skills.py`` unchanged; it is ``build_all.py --check``
    specifically that turns it into exit 2, by coercion in
    ``build_all._build_skills``, not by anything this function does (module
    docstring's "Stricter/looser/different than canonical" section has the
    precise chain). This is a deliberate module-level divergence from
    DESIGN-020's "skipped, NOTICE printed, exit 0" and from ADR-108 section
    4's own wording: a sentinel that could silence ADR-108's only gate and
    still report a clean run would make the gate advisory the moment anyone
    reached for it.
    """
    result = CompileResult()
    partials_dir = repo_root / "templates" / "skills" / "partials"

    for name, tmpl_path in sorted(discover(repo_root).items()):
        target = repo_root / ".claude" / "skills" / name / "SKILL.md"

        reason = detect_reason(target)
        if reason is not None:
            print(
                f"WARN: skipped {target} (NO-REGEN: {reason}); "
                "template-owned file exempt from drift gate"
            )
            result.skipped.append(str(target))
            result.exit_code = max(result.exit_code, 1)
            continue

        try:
            rendered = render(tmpl_path, partials_dir)
        except TemplateGrammarError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            result.exit_code = max(result.exit_code, 2)
            continue
        except MissingPartialError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            result.exit_code = max(result.exit_code, 2)
            continue
        except PartialNewlineError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            result.exit_code = max(result.exit_code, 2)
            continue
        except UnresolvedTagError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            result.exit_code = max(result.exit_code, 1)
            continue

        if not target.parent.is_dir():
            print(f"Error: target directory missing: {target.parent}", file=sys.stderr)
            result.exit_code = max(result.exit_code, 2)
            continue

        current = (
            target.read_text(encoding="utf-8", newline="") if target.is_file() else None
        )
        if current == rendered:
            continue

        if validate:
            print(f"DRIFT: {target} differs from its template ({tmpl_path})", file=sys.stderr)
            result.drifted.append(str(target))
            result.exit_code = max(result.exit_code, 1)
            continue

        if what_if:
            print(f"  Would write: {target}")
            continue

        target.write_text(rendered, encoding="utf-8", newline="\n")
        result.written.append(str(target))

    return result
