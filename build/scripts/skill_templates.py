#!/usr/bin/env python3
"""Compile ``templates/skills/*.SKILL.md.tmpl`` into ``.claude/skills/<name>/SKILL.md``.

ADR-108 (Template-Owned Skill Files Under ``.claude/skills/``) amends
REQ-003-010 and ADR-107 property 1 for exactly one artifact class: a skill
whose canonical source is a mustache template under ``templates/skills/``.
This module is that class's compile step, per
``.agents/specs/design/DESIGN-024-skill-guidance-excerpt-sync.md``, "Compile
module: ``build/scripts/skill_templates.py``":

    ``discover(repo_root) -> dict[str, Path]``
        ``{name: templates/skills/<name>.SKILL.md.tmpl}``; name is the
        filename minus ``.SKILL.md.tmpl``. Excludes a candidate whose name
        fails validation (two rounds of ADR-108 PR review, see
        :func:`_name_validation_error`): ``name`` MUST match
        ``^[a-z0-9]+(-[a-z0-9]+)*$``; ``.claude/skills/<name>/`` MUST
        already exist as a directory; it MUST NOT be a symlink; and its
        resolved path MUST lie inside the resolved ``.claude/skills/``
        root (CWE-22 defense). Any failure means that candidate never
        appears in this mapping, so it is never a target
        :func:`owned_targets` allowlists or :func:`compile_all` writes.
    ``discover_errors(repo_root) -> list[str]``
        One message per candidate :func:`discover` excluded, naming the
        template path and the reason. :func:`compile_all` grades each one
        exit 2.
    ``owned_targets(repo_root) -> set[Path]``
        ``{.claude/skills/<name>/SKILL.md}`` for every discovered
        (validated) template; the allowlist ``build_all.py`` passes to the
        guard.
    ``check_grammar(text) -> list[str]``
        Offending tags; empty when only partial and comment tags are
        present. Defined in the sibling ``skill_template_grammar`` module
        (see that module's docstring for the grammar and the ``render``
        contract) and re-exported here.
    ``render(tmpl_path, partials_dir) -> str``
        Recursive grammar check, partial existence check, and partial
        trailing-newline check over the template and every partial it
        (transitively) includes, with cycle detection, then
        ``chevron.render(text, {}, partials_path=...,
        partials_ext="mustache")``, then a ``{{`` scan of the output. Also
        defined in ``skill_template_grammar`` and re-exported here.
    ``compile_all(repo_root, *, validate, what_if) -> CompileResult``
        Reports each of :func:`discover_errors`'s findings as exit 2, then
        for each VALID template: skip (unchanged, WARN, exit 1) when
        ``regen_guard.detect_reason(target)`` is not ``None``; in validate
        mode compare and record drift; otherwise write when the bytes
        differ. Returns written, skipped, drifted, and an exit code (0
        pass, 1 drift, unresolved ``{{``, or a NO-REGEN skip, 2 grammar
        (template or any included partial), a missing or cyclic partial, an
        invalid template name, a symlinked or out-of-root
        ``.claude/skills/<name>/``, or a template with no existing
        ``.claude/skills/<name>/`` directory (all four of the name/skill-dir
        failures caught by :func:`discover_errors`, before this loop ever
        sees the template), or a partial missing its trailing newline).

Split from a single ``skill_templates.py`` into this module plus the sibling
``skill_template_grammar.py`` (taste-lint file-size ceiling; ADR review round
for #5706): that module holds everything that turns one template's TEXT into
rendered TEXT (grammar, partial-tree validation, ``render``); this module
holds everything that turns the FILESYSTEM into a set of templates to
compile (``discover``, ``owned_targets``, ``compile_all``) and re-exports the
sibling's public names (``render``, ``check_grammar``, and the four
exception classes) so every existing caller and test that reaches them
through ``skill_templates.<name>`` keeps working unchanged.

Stricter/looser/different than canonical: DESIGN-024's table above says a
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
in ADR review for #5706 after DESIGN-024 and ADR-108 were already recorded;
neither document is amended by this file, the divergence lives here.

EXIT CODES (per ``compile_all``, and surfaced by callers unchanged):
  0 - no templates, or every template renders clean (write mode) / matches
      the committed file (validate mode)
  1 - a rendered file drifted from the committed one (validate mode), the
      rendered text still contains an unresolved ``{{`` after render, or a
      NO-REGEN-skipped template-owned target (see the "Stricter/looser/
      different than canonical" section above)
  2 - a discovered template's name does not match ``^[a-z0-9]+(-[a-z0-9]+)*$``,
      names a skill with no existing ``.claude/skills/<name>/`` directory, or
      that directory is a symlink or resolves outside ``.claude/skills/``
      (CWE-22 defense; that template is excluded from every other check
      below, and its target directory is therefore guaranteed to exist AND
      be a real, in-root directory for every template the checks below DO
      run on); the template, or any partial it (transitively) includes,
      used a disallowed tag or named a partial
      that does not exist or forms an include cycle; or a referenced
      partial that does not end with exactly one trailing newline

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

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from regen_guard import detect_reason  # noqa: E402
from skill_template_grammar import (  # noqa: E402,F401 (F401: re-exported for callers)
    _SLUG,
    MissingPartialError,
    PartialNewlineError,
    TemplateGrammarError,
    UnresolvedTagError,
    check_grammar,
    render,
)

_TEMPLATE_SUFFIX = ".SKILL.md.tmpl"
_NAME_RE = re.compile(rf"^{_SLUG}$")


@dataclass
class CompileResult:
    """Outcome of one :func:`compile_all` run across every discovered template."""

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    exit_code: int = 0


def _iter_template_candidates(repo_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(name, path)`` for every ``templates/skills/*.SKILL.md.tmpl``.

    Unvalidated: ``name`` here is only the filename with the
    ``.SKILL.md.tmpl`` suffix stripped, not yet checked against
    :func:`_name_validation_error`. Shared by :func:`discover` and
    :func:`discover_errors` so the glob and the suffix-stripping live in one
    place instead of two.
    """
    templates_dir = repo_root / "templates" / "skills"
    if not templates_dir.is_dir():
        return
    for path in sorted(templates_dir.glob(f"*{_TEMPLATE_SUFFIX}")):
        yield path.name[: -len(_TEMPLATE_SUFFIX)], path


def _name_validation_error(repo_root: Path, name: str, tmpl_path: Path) -> str | None:
    """Return why ``name`` is not a valid template-owned skill name, or ``None``.

    Five checks, from three rounds of ADR-108 review. ``name`` MUST match the
    same slug pattern a partial's slug does (``^[a-z0-9]+(-[a-z0-9]+)*$``).
    ``.claude/skills/<name>/`` MUST already exist as a directory: the class
    boundary ADR-108 section 1 and section 7 both draw is that every
    template-owned skill converts an EXISTING skill directory; nothing in
    this class creates a new skill out of nothing, so a misspelled or
    freshly-invented name is a configuration error, not silently a new
    skill. ``.claude/skills/<name>/`` MUST NOT be a symlink, and its
    resolved path MUST lie inside the resolved ``.claude/skills/`` root
    (second ADR review round, CWE-22 defense): ``name`` cannot itself carry
    a path-traversal segment (the slug pattern admits no ``/`` or ``.``),
    but a symlink at that exact location could still point the directory
    the allowlist trusts at an arbitrary path outside ``.claude/skills/``,
    which is exactly the tree :func:`owned_targets` promises
    :func:`build_all.assert_no_claude_writes` a write is confined to.

    The ``.claude/skills/`` root itself MUST resolve inside ``repo_root``
    (CodeRabbit on PR #5726): an intermediate symlink at ``.claude`` or
    ``.claude/skills`` pointing at an external tree would make both the root
    and the skill directory resolve there, so the per-skill containment check
    below would pass while every write landed outside the repository.

    ``.claude/skills/<name>/SKILL.md`` itself MUST NOT be a symlink (third
    ADR review round, CodeRabbit on PR #5726, CWE-22/CWE-59 defense): the
    four checks above only ever look at the DIRECTORY. A real, non-symlinked
    directory can still hold a symlinked ``SKILL.md`` pointing anywhere on
    the filesystem, and :func:`compile_all`'s ``target.write_text(...)``
    follows a symlink the same way any ``open()`` call does, so without this
    check a symlinked file inside an otherwise-legitimate skill directory
    would let a render escape ``.claude/skills/`` even though the directory
    containment check above passed clean.
    """
    if not _NAME_RE.match(name):
        return f"{tmpl_path}: invalid template name {name!r}; must match {_NAME_RE.pattern!r}"

    skills_root = repo_root / ".claude" / "skills"
    skill_dir = skills_root / name

    if skill_dir.is_symlink():
        return f"{tmpl_path}: .claude/skills/{name}/ is a symlink, not a real directory"
    if not skill_dir.is_dir():
        return f"{tmpl_path}: no existing .claude/skills/{name}/ directory"

    resolved_root = skills_root.resolve()
    resolved_repo = repo_root.resolve()
    if not resolved_root.is_relative_to(resolved_repo):
        return (
            f"{tmpl_path}: .claude/skills/ resolves to {resolved_root}, "
            f"outside the repository root {resolved_repo}"
        )
    resolved_skill = skill_dir.resolve()
    if not resolved_skill.is_relative_to(resolved_root):
        return (
            f"{tmpl_path}: .claude/skills/{name}/ resolves to {resolved_skill}, "
            f"outside {resolved_root}"
        )

    if (skill_dir / "SKILL.md").is_symlink():
        return f"{tmpl_path}: .claude/skills/{name}/SKILL.md is a symlink, not a real file"

    return None


def discover(repo_root: Path) -> dict[str, Path]:
    """Return ``{name: template path}`` for every VALID ``templates/skills/*.SKILL.md.tmpl``.

    ``name`` is the filename with the ``.SKILL.md.tmpl`` suffix stripped.
    An absent ``templates/skills/`` directory yields an empty mapping rather
    than an error: membership in the template-owned class is read from the
    directory at run time (ADR-108 section 1), so "no templates yet" is a
    valid, non-error state during migration.

    A candidate whose name fails :func:`_name_validation_error` is excluded
    here entirely (PR review of ADR-108): it is never a value this function
    returns, so it can never reach :func:`owned_targets`'s allowlist or have
    a target computed for it. :func:`discover_errors` reports the same
    candidates as configuration errors, so the exclusion is not silent; it
    is silent only from THIS function's own return value, which is the
    point, since this function's return value is what the ``.claude/``
    write guard trusts.
    """
    return {
        name: path
        for name, path in _iter_template_candidates(repo_root)
        if _name_validation_error(repo_root, name, path) is None
    }


def discover_errors(repo_root: Path) -> list[str]:
    """Return one message per discovered template :func:`discover` excluded.

    :func:`compile_all` calls this to grade an invalid template name exit 2
    alongside its other per-template findings, naming the template's path,
    even though :func:`discover` itself never returns that template (and so
    never writes it, and never allowlists it).
    """
    errors: list[str] = []
    for name, path in _iter_template_candidates(repo_root):
        error = _name_validation_error(repo_root, name, path)
        if error is not None:
            errors.append(error)
    return errors


def owned_targets(repo_root: Path) -> set[Path]:
    """Return the allowlist :func:`build_all.assert_no_claude_writes` accepts.

    One absolute path per VALID discovered template:
    ``.claude/skills/<name>/SKILL.md``. Built from :func:`discover`, so an
    invalid template name never reaches this allowlist (see that function's
    docstring).
    """
    return {repo_root / ".claude" / "skills" / name / "SKILL.md" for name in discover(repo_root)}


def _try_render(tmpl_path: Path, partials_dir: Path, result: CompileResult) -> str | None:
    """Render one template, recording any failure onto ``result``.

    Returns the rendered text, or ``None`` when :func:`render` raised: the
    exception's message is printed and ``exit_code`` is raised to the floor
    that exception's own contract names (2 for a grammar, missing-partial,
    or newline defect; 1 for an unresolved tag). Extracted out of
    :func:`compile_all`'s loop body, alongside :func:`_report_discover_errors`,
    to hold that function's cyclomatic complexity down: four except clauses
    inline cost four branches there, one helper call costs one.
    """
    try:
        # str(...): mypy resolves the sibling sys.path import
        # `skill_template_grammar` as `scripts.skill_template_grammar` (its
        # build/scripts/__init__.py-derived qualified name) rather than the
        # bare name this module imports it as, so it cannot match the two
        # and treats `render`'s return as Any. Same shape as the int(...)
        # notes elsewhere in this codebase for the identical cross-module
        # pattern.
        return str(render(tmpl_path, partials_dir))
    except (TemplateGrammarError, MissingPartialError, PartialNewlineError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)
        return None
    except UnresolvedTagError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 1)
        return None


def _report_discover_errors(repo_root: Path, result: CompileResult) -> None:
    """Print each of :func:`discover_errors`'s findings and grade it exit 2.

    Extracted out of :func:`compile_all`'s own body (kept as a single
    statement there) to hold that function's cyclomatic complexity down;
    this loop's only job is turning a list of strings into stderr lines and
    an exit-code floor, with nothing else in :func:`compile_all` to weigh
    against it.
    """
    for error in discover_errors(repo_root):
        print(f"Error: {error}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)


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
    DESIGN-024's "skipped, NOTICE printed, exit 0" and from ADR-108 section
    4's own wording: a sentinel that could silence ADR-108's only gate and
    still report a clean run would make the gate advisory the moment anyone
    reached for it.
    """
    result = CompileResult()
    partials_dir = repo_root / "templates" / "skills" / "partials"

    _report_discover_errors(repo_root, result)

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

        rendered = _try_render(tmpl_path, partials_dir, result)
        if rendered is None:
            continue

        # No "target.parent.is_dir()" check here: discover() already
        # required .claude/skills/<name>/ to exist (PR review of ADR-108)
        # before `name` could appear in the mapping this loop iterates, so
        # target.parent is guaranteed to exist for every (name, tmpl_path)
        # reached this far.

        current = target.read_text(encoding="utf-8", newline="") if target.is_file() else None
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
