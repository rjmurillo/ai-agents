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
        Grammar check, partial existence check,
        ``chevron.render(text, {}, partials_path=..., partials_ext="mustache")``,
        then a ``{{`` scan of the output.
    ``compile_all(repo_root, *, validate, what_if) -> CompileResult``
        For each template: skip with NOTICE when
        ``regen_guard.detect_reason(target)`` is not ``None``; in validate
        mode compare and record drift; otherwise write when the bytes
        differ. Returns written, skipped, drifted, and an exit code (0
        pass, 1 drift or unresolved ``{{``, 2 grammar, missing partial, or
        missing target directory).

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
``"{{x}}"`` in the output. This is why :func:`check_grammar` and
:func:`_missing_partials` run BEFORE ``chevron.render`` in :func:`render`
below: chevron itself has no failure mode for either case, so it cannot be
the thing that turns a typo'd slug or a disallowed tag into a build failure.

EXIT CODES (per ``compile_all``, and surfaced by callers unchanged):
  0 - no templates, or every template renders clean (write mode) / matches
      the committed file (validate mode)
  1 - a rendered file drifted from the committed one (validate mode), or the
      rendered text still contains an unresolved ``{{`` after render
  2 - a template used a disallowed tag, named a partial that does not exist,
      or its target's parent directory does not exist

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


def _missing_partials(text: str, partials_dir: Path) -> list[str]:
    return [
        slug
        for slug in _partial_slugs(text)
        if not (partials_dir / f"{slug}.{_PARTIAL_EXT}").is_file()
    ]


def render(tmpl_path: Path, partials_dir: Path) -> str:
    """Render one template to text, per the compile module's ``render`` contract.

    Order: grammar check (exit 2), partial existence check (exit 2), chevron
    render, then a ``{{`` scan of the OUTPUT (exit 1). The output scan exists
    because chevron renders a missing partial and an unknown variable as
    empty text with no error (DESIGN-020, "Template grammar"), so a partial
    file that itself carries literal ``{{`` text (unlikely, but not excluded
    by the grammar check, which only scans the template) would otherwise
    leak an unresolved tag into the rendered ``SKILL.md`` undetected.
    """
    text = tmpl_path.read_text(encoding="utf-8")

    offending = check_grammar(text)
    if offending:
        raise TemplateGrammarError(
            f"{tmpl_path}: disallowed tag(s) outside {{> slug}} / {{! comment}}: "
            f"{', '.join(offending)}"
        )

    missing = _missing_partials(text, partials_dir)
    if missing:
        raise MissingPartialError(
            f"{tmpl_path}: missing partial(s) under {partials_dir}: {', '.join(missing)}"
        )

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
    ``generate_skills._copy_skill_tree`` skips a protected file at
    ``build/scripts/generate_skills.py:105-109``.
    """
    result = CompileResult()
    partials_dir = repo_root / "templates" / "skills" / "partials"

    for name, tmpl_path in sorted(discover(repo_root).items()):
        target = repo_root / ".claude" / "skills" / name / "SKILL.md"

        reason = detect_reason(target)
        if reason is not None:
            print(f"  NOTICE: skipped {target} (NO-REGEN: {reason})")
            result.skipped.append(str(target))
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
        except UnresolvedTagError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            result.exit_code = max(result.exit_code, 1)
            continue

        if not target.parent.is_dir():
            print(f"Error: target directory missing: {target.parent}", file=sys.stderr)
            result.exit_code = max(result.exit_code, 2)
            continue

        current = target.read_text(encoding="utf-8") if target.is_file() else None
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

        target.write_text(rendered, encoding="utf-8")
        result.written.append(str(target))

    return result
