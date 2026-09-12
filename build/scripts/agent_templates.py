#!/usr/bin/env python3
"""Compile paired ``templates/agents/<stem>.{claude,copilot}.md.tmpl`` templates.

ADR-109 (Template-First Plugin Distribution) generalizes ADR-108's
compile-and-drift-gate shape from one artifact class (skills) to agents.
Per ``.agents/specs/design/DESIGN-025-template-first-compiler-and-binplace.md``,
"Per-class compile modules" section, this module is agents' half of the
same split ADR-108 already established for skills: ``skill_templates.py``
(discovery, allowlist, compile orchestration) plus the sibling
``skill_template_grammar.py`` (grammar, partial-tree validation, render).
Agents reuse the grammar module UNCHANGED (import and call, never copy):
quoted verbatim from DESIGN-025, "Per-class compile modules" table:

    ``check_grammar(text) -> list[str]`` (agents, rules only)
        Delegates to ``skill_template_grammar.check_grammar``
    ``render(tmpl_path, partials_dir) -> str`` (agents, rules only)
        Delegates to ``skill_template_grammar.render``

Discovery differs from skills' one-path-per-name shape because an agent
composes from TWO templates, not one. Quoted verbatim from DESIGN-025,
"Per-class compile modules" prose:

    "``agent_templates.py`` therefore discovers TWO NEW templates per agent,
    ``templates/agents/<stem>.claude.md.tmpl`` and
    ``templates/agents/<stem>.copilot.md.tmpl``... ``discover()`` for this
    class returns ``{stem: (claude_tmpl_path, copilot_tmpl_path)}``, a pair
    per agent rather than a single path, and ``compile_all`` renders both
    members of the pair in the same pass."

A stem with only one of its two variant templates present is a
configuration error (TASK-031 acceptance criteria, "Edge" row), not a
partial compile: :func:`discover` excludes it, and :func:`discover_errors`
reports it, the same shape ``skill_templates.discover``/``discover_errors``
already gives an invalid skill name.

Stricter/looser/different than canonical (``skill_templates.py``):

- Different: ``discover`` returns ``dict[str, tuple[Path, Path]]`` (a pair),
  not ``dict[str, Path]``, because this class composes two rendered files
  per name instead of one.
- Different: the render target is ``src/claude/agents/<stem>.md`` (a
  ``src/`` path already covered by ``build_all.OWNED_PREFIXES``'s
  staleness/restore machinery), not a ``.claude/`` path guarded by
  ``assert_no_claude_writes``. The name-validation checks
  ``skill_templates._name_validation_error`` runs against an EXISTING
  ``.claude/skills/<name>/`` directory (ADR-108 converts an existing skill,
  never invents one) have no analogue here: there is no existing
  ``src/claude/agents/<stem>.md`` requirement, because B1 IS the record that
  first populates that directory (ADR-109 section 2, "the flat-to-`agents/`
  layout move"). :func:`_name_validation_error` below therefore checks only
  the slug shape and the containment/symlink invariants, not directory
  pre-existence.
- Same as canonical, deliberately: the symlink and resolved-containment
  checks (CWE-22/CWE-59) mirror ``skill_templates._name_validation_error``'s
  shape one-for-one, per ADR-109 section 6's instruction that "each of B1
  through B4 MUST implement the same drift gate, NO-REGEN handling, and
  symlink and resolved-containment checks for its own class and install
  paths."
- Same as canonical: a NO-REGEN sentinel on a rendered target is skipped
  (never written, never drift), reported at WARN, and floors ``exit_code``
  to at least 1 in both modes, exactly as ``skill_templates.compile_all``
  documents for the reasoning behind that divergence from a routine skip.

EXIT CODES (per :func:`compile_all`; ``0=ok|1=logic|2=config`` per
``AGENTS.md`` Standards, worst-code-wins across every discovered stem):
  0 - no template pairs found, or every pair renders clean (write mode) /
      matches the committed target (validate mode)
  1 - a rendered target drifted from the committed one (validate mode), the
      rendered text still contains an unresolved ``{{``, or a
      NO-REGEN-skipped target (see "Same as canonical" above)
  2 - a discovered stem's name does not match ``^[a-z0-9]+(-[a-z0-9]+)*$``,
      only one of the two variant templates exists for a stem, the
      ``src/claude/agents/`` root or a stem's target resolves outside the
      repository or through a symlink, or the template (or a partial it
      transitively includes) used a disallowed tag, named a missing or
      cyclic partial, or referenced a partial missing its trailing newline
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

_CLAUDE_SUFFIX = ".claude.md.tmpl"
_COPILOT_SUFFIX = ".copilot.md.tmpl"
_NAME_RE = re.compile(rf"^{_SLUG}$")


@dataclass
class CompileResult:
    """Outcome of one :func:`compile_all` run across every discovered pair.

    ``copilot_rendered`` maps ``stem -> rendered .copilot.md.tmpl text``
    for every VALIDLY discovered pair, regardless of ``validate``/``what_if``
    (rendering in memory has no side effect, so this is always populated).
    ``build/generate_agents.py`` reads it as the Copilot-variant source body
    for the copilot-cli platform when a stem has one, falling back to
    ``<stem>.shared.md`` when it does not (mid-migration compatibility,
    TASK-031: ``templates/agents/*.copilot.md.tmpl`` does not exist yet for
    any stem until the sibling PR that populates all 31 pairs lands).
    """

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    exit_code: int = 0
    copilot_rendered: dict[str, str] = field(default_factory=dict)


def _iter_pair_candidates(repo_root: Path) -> Iterator[tuple[str, Path, Path]]:
    """Yield ``(stem, claude_path, copilot_path)`` for every discovered stem.

    A stem is discovered when EITHER variant file exists, so a stem missing
    one half still reaches :func:`discover_errors` as an incomplete-pair
    configuration error rather than silently vanishing the way a candidate
    that never appeared at all would. Unvalidated: mirrors
    ``skill_templates._iter_template_candidates``'s "collect first, validate
    in discover()/discover_errors() separately" split.
    """
    agents_dir = repo_root / "templates" / "agents"
    if not agents_dir.is_dir():
        return
    stems: set[str] = set()
    for path in agents_dir.glob(f"*{_CLAUDE_SUFFIX}"):
        stems.add(path.name[: -len(_CLAUDE_SUFFIX)])
    for path in agents_dir.glob(f"*{_COPILOT_SUFFIX}"):
        stems.add(path.name[: -len(_COPILOT_SUFFIX)])
    for stem in sorted(stems):
        yield (
            stem,
            agents_dir / f"{stem}{_CLAUDE_SUFFIX}",
            agents_dir / f"{stem}{_COPILOT_SUFFIX}",
        )


def _name_validation_error(
    repo_root: Path, stem: str, claude_path: Path, copilot_path: Path
) -> str | None:
    """Return why ``stem`` is not a valid agent template pair, or ``None``.

    Four checks, mirroring ``skill_templates._name_validation_error``'s
    shape (module docstring, "Stricter/looser/different than canonical"):
    ``stem`` MUST match the slug pattern; BOTH variant files MUST exist
    (TASK-031's "incomplete pair" edge case is a configuration error, not a
    partial compile); the ``src/claude/agents/`` root MUST NOT be a
    symlink and MUST resolve inside the repository root (CWE-22); the
    specific target ``src/claude/agents/<stem>.md`` MUST NOT itself be a
    symlink (CWE-59), the same "directory can be clean while the leaf file
    is a planted link" gap ADR-108 review closed for skills.
    """
    if not _NAME_RE.match(stem):
        return (
            f"{claude_path if claude_path.is_file() else copilot_path}: "
            f"invalid agent stem {stem!r}; must match {_NAME_RE.pattern!r}"
        )

    if not claude_path.is_file():
        return f"{stem}: missing {claude_path.name} (incomplete template pair)"
    if not copilot_path.is_file():
        return f"{stem}: missing {copilot_path.name} (incomplete template pair)"

    agents_root = repo_root / "src" / "claude" / "agents"
    resolved_repo = repo_root.resolve()

    if agents_root.is_symlink():
        return f"{claude_path}: src/claude/agents/ is a symlink, not a real directory"
    if agents_root.exists():
        resolved_root = agents_root.resolve()
        if not resolved_root.is_relative_to(resolved_repo):
            return (
                f"{claude_path}: src/claude/agents/ resolves to {resolved_root}, "
                f"outside the repository root {resolved_repo}"
            )

    target = agents_root / f"{stem}.md"
    if target.is_symlink():
        return f"{claude_path}: src/claude/agents/{stem}.md is a symlink, not a real file"

    return None


def discover(repo_root: Path) -> dict[str, tuple[Path, Path]]:
    """Return ``{stem: (claude_tmpl_path, copilot_tmpl_path)}`` for every VALID pair.

    An absent ``templates/agents/`` directory yields an empty mapping, not
    an error (mirrors ``skill_templates.discover``): membership is read from
    the directory at run time, so "no templates yet" is a valid, non-error
    state during migration (this repository's own state until the sibling
    PR populating all 31 pairs lands).
    """
    return {
        stem: (claude_path, copilot_path)
        for stem, claude_path, copilot_path in _iter_pair_candidates(repo_root)
        if _name_validation_error(repo_root, stem, claude_path, copilot_path) is None
    }


def discover_errors(repo_root: Path) -> list[str]:
    """Return one message per discovered stem :func:`discover` excluded."""
    errors: list[str] = []
    for stem, claude_path, copilot_path in _iter_pair_candidates(repo_root):
        error = _name_validation_error(repo_root, stem, claude_path, copilot_path)
        if error is not None:
            errors.append(error)
    return errors


def owned_targets(repo_root: Path) -> set[Path]:
    """Return every ``src/claude/agents/<stem>.md`` this class renders.

    Used by ``build/scripts/build_all.py``'s OWNED_PREFIXES-based staleness
    check (the target lives under ``src/``, already covered by that
    mechanism) and by callers wanting the full render-target set without
    re-deriving it from :func:`discover`.
    """
    return {repo_root / "src" / "claude" / "agents" / f"{stem}.md" for stem in discover(repo_root)}


def _try_render(tmpl_path: Path, partials_dir: Path, result: CompileResult) -> str | None:
    """Render one template, recording any failure onto ``result``.

    Mirrors ``skill_templates._try_render`` exactly (module docstring): the
    same three exception classes are graded the same floors, extracted to
    hold this module's compile loop under the cyclomatic-complexity ceiling.
    """
    try:
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
    """Print each of :func:`discover_errors`'s findings and grade it exit 2."""
    for error in discover_errors(repo_root):
        print(f"Error: {error}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)


def _compile_one_pair(
    repo_root: Path,
    stem: str,
    claude_tmpl: Path,
    copilot_tmpl: Path,
    partials_dir: Path,
    *,
    validate: bool,
    what_if: bool,
    result: CompileResult,
) -> None:
    """Render, and (unless validating) write, one stem's Claude variant.

    The Copilot variant is rendered but never written to disk by this
    module: it is a ``generate_agents.py`` input (module docstring,
    ``CompileResult.copilot_rendered``), not a target this class owns.
    Extracted out of :func:`compile_all`'s loop body to hold that function's
    cyclomatic complexity down, the same reason
    ``skill_templates._try_render``/``_report_discover_errors`` are
    separate functions rather than inlined.
    """
    copilot_rendered = _try_render(copilot_tmpl, partials_dir, result)
    if copilot_rendered is not None:
        result.copilot_rendered[stem] = copilot_rendered

    target = repo_root / "src" / "claude" / "agents" / f"{stem}.md"

    reason = detect_reason(target)
    if reason is not None:
        print(
            f"WARN: skipped {target} (NO-REGEN: {reason}); "
            "template-owned file exempt from drift gate"
        )
        result.skipped.append(str(target))
        result.exit_code = max(result.exit_code, 1)
        return

    rendered = _try_render(claude_tmpl, partials_dir, result)
    if rendered is None:
        return

    current = target.read_text(encoding="utf-8", newline="") if target.is_file() else None
    if current == rendered:
        return

    if validate:
        print(f"DRIFT: {target} differs from its template ({claude_tmpl})", file=sys.stderr)
        result.drifted.append(str(target))
        result.exit_code = max(result.exit_code, 1)
        return

    if what_if:
        print(f"  Would write: {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8", newline="\n")
    result.written.append(str(target))


def compile_all(repo_root: Path, *, validate: bool, what_if: bool = False) -> CompileResult:
    """Compile every discovered pair; render both variants, write the Claude one.

    ``validate=True``: never writes ``src/claude/agents/<stem>.md``. A
    target whose committed bytes differ from a fresh render is recorded as
    drift, exit 1. ``validate=False``: writes when the render differs,
    unless ``what_if`` is set, in which case it reports what it would write
    without touching the filesystem. Mirrors
    ``skill_templates.compile_all``'s modes exactly.

    An absent ``templates/agents/`` directory (or one with no valid pair)
    is not an error: ``result`` stays at its zero-value defaults, exit 0,
    per DR5 in DESIGN-025 ("an unmigrated class is untouched"). This is the
    state that holds in this repository until a later PR populates all 31
    ``.claude.md.tmpl``/``.copilot.md.tmpl`` pairs.
    """
    result = CompileResult()
    partials_dir = repo_root / "templates" / "agents" / "partials"

    _report_discover_errors(repo_root, result)

    for stem, (claude_tmpl, copilot_tmpl) in sorted(discover(repo_root).items()):
        _compile_one_pair(
            repo_root,
            stem,
            claude_tmpl,
            copilot_tmpl,
            partials_dir,
            validate=validate,
            what_if=what_if,
            result=result,
        )

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI: ``--validate`` renders in memory and reports drift; default writes.

    Exit codes are :func:`compile_all`'s (module docstring). The
    ``Agent Template Drift`` pre-PR gate wraps ``--validate`` the same way
    the skill gate wraps ``generate_skills.py --validate``.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=_SCRIPT_DIR.parent.parent)
    parser.add_argument("--validate", action="store_true", help="report drift, write nothing")
    parser.add_argument("--what-if", action="store_true", help="report writes, write nothing")
    args = parser.parse_args(argv)
    result = compile_all(args.repo_root.resolve(), validate=args.validate, what_if=args.what_if)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
