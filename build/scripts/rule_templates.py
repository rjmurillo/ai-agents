#!/usr/bin/env python3
r"""Compile ``templates/rules/<name>.md`` templates into ``src/claude/rules/``.

ADR-109 (Template-First Plugin Distribution) step B2 generalizes ADR-108's
compile-and-drift-gate shape, already applied to skills and to agents
(``build/scripts/agent_templates.py``, B1), to the rules class. Per
``.agents/specs/design/DESIGN-025-template-first-compiler-and-binplace.md``,
"Per-class compile modules" section, this module is rules' half of the same
split ADR-108 established for skills: this file (discovery, allowlist,
compile orchestration) plus the shared ``skill_template_grammar.py``
(grammar, partial-tree validation, render), reused unchanged (import and
call, never copy), quoted verbatim from DESIGN-025, "Per-class compile
modules" table:

    ``check_grammar(text) -> list[str]`` (agents, rules only)
        Delegates to ``skill_template_grammar.check_grammar``
    ``render(tmpl_path, partials_dir) -> str`` (agents, rules only)
        Delegates to ``skill_template_grammar.render``

This module is a SINGLE-VARIANT twin of ``agent_templates.py``: one template
renders to one target, the same one-path-per-name shape
``skill_templates.discover`` uses, not the two-templates-per-name pair
``agent_templates.discover`` returns. Rules have no Claude/Copilot template
split the way agents do: one ``templates/rules/<name>.md`` file is the
canonical source both `src/claude/rules/<name>.md` (this module's target,
via the binplace manifest's `rules` row) AND the Copilot instruction
mirrors (`.github/instructions/`, `src/copilot-cli/instructions/`,
rendered by ``build/scripts/generate_rules.py`` from whatever
`sourceDir` its platform config names) derive from, once this module's
compile step runs upstream of that read (module docstring cross-reference:
TASK-032 Implementation Notes, "this task inserts the compile step upstream
of that existing read, so the mirror generation logic itself needs no
change; only its input's provenance changes from hand-maintained to
compiled").

Stricter/looser/different than canonical (``agent_templates.py``):

- Different: :func:`discover` returns ``dict[str, Path]`` (one template per
  name), not ``dict[str, tuple[Path, Path]]`` (a pair), because this class
  renders one file per name instead of composing two variants.
- Different: the render target is ``src/claude/rules/<name>.md``, not
  ``src/claude/agents/<stem>.md``; both are ``src/`` paths already covered by
  ``build_all.OWNED_PREFIXES``'s staleness/restore machinery, widened for
  this class in the same commit that adds this module.
- Same in shape, with one difference: the target-side symlink and
  resolved-containment checks (CWE-22/CWE-59) follow
  ``agent_templates._name_validation_error``, but there is no "incomplete
  pair" check here (no second variant to be missing); the only name-shape
  check is the slug pattern. This module adds one check neither sibling
  has: the SOURCE ``templates/rules/<name>.md`` itself MUST NOT be a
  symlink and MUST be a regular file, refused rather than rendered
  (CodeRabbit review).
- Same as canonical: a NO-REGEN sentinel on a rendered target is skipped
  (never written, never drift), reported at WARN, and floors ``exit_code``
  to at least 1 in both modes, exactly as ``agent_templates.compile_all``
  documents.
- Same as canonical: a name with no template at all (an untemplated rule
  during migration, TASK-032's "Rule with no template during migration:
  untouched" edge case) is simply absent from :func:`discover`'s mapping;
  the compile step never touches it. Every rule in this repository is
  templated as of ADR-109 B2: ``testing.md`` carries a literal
  ``${{ a && b }}`` GitHub Actions example and writes it as ``$\{{``,
  the literal-brace escape ``skill_template_grammar`` added for exactly
  this case (ADR-108, amended 2026-09-14).

EXIT CODES (per :func:`compile_all`; ``0=ok|1=logic|2=config`` per
``AGENTS.md`` Standards, worst-code-wins across every discovered name):
  0 - no templates found, or every template renders clean (write mode) /
      matches the committed target (validate mode)
  1 - a rendered target drifted from the committed one (validate mode), the
      rendered text still contains an unresolved ``{{``, or a
      NO-REGEN-skipped target (see "Same as canonical" above)
  2 - a discovered name does not match ``^[a-z0-9]+(-[a-z0-9]+)*$``, the
      source ``templates/rules/<name>.md`` is a symlink or not a regular
      file, the ``src/claude/rules/`` root or a name's target resolves
      outside the repository or through a symlink, or the template (or a
      partial it transitively includes) used a disallowed tag, named a
      missing or cyclic partial, or referenced a partial missing its
      trailing newline
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

from atomic_write import publish_bytes_atomically  # noqa: E402
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

_TEMPLATE_SUFFIX = ".md"
_NAME_RE = re.compile(rf"^{_SLUG}$")


@dataclass
class CompileResult:
    """Outcome of one :func:`compile_all` run across every discovered name."""

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    exit_code: int = 0


def _iter_template_candidates(repo_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(name, template_path)`` for every ``templates/rules/*.md`` file.

    An absent ``templates/rules/`` directory yields nothing (mirrors
    ``agent_templates._iter_pair_candidates``): "no templates yet" is a
    valid, non-error state during migration.
    """
    rules_dir = repo_root / "templates" / "rules"
    if not rules_dir.is_dir():
        return
    for path in sorted(rules_dir.glob(f"*{_TEMPLATE_SUFFIX}")):
        yield path.stem, path


def _name_validation_error(repo_root: Path, name: str, tmpl_path: Path) -> str | None:
    """Return why ``name`` is not a valid rule template, or ``None``.

    Five checks, mirroring ``agent_templates._name_validation_error``'s
    shape minus the incomplete-pair check (this class has no second
    variant): ``name`` MUST match the slug pattern; the SOURCE
    ``templates/rules/<name>.md`` MUST NOT be a symlink and MUST be a
    regular file (a symlinked or non-regular candidate is refused, not
    rendered); the ``src/claude/rules/`` root MUST NOT be a symlink and
    MUST resolve inside the repository root (CWE-22); the specific target
    ``src/claude/rules/<name>.md`` MUST NOT itself be a symlink (CWE-59).

    The containment check resolves ``rules_root`` unconditionally, not only
    when it already exists: ``Path.resolve()`` follows symlinks in existing
    ancestors and appends any missing leaf literally, so this also catches
    ``src`` or ``src/claude`` being a symlink to outside the repository
    while ``rules`` itself has not been created yet, a gap the earlier
    ``if rules_root.exists():`` guard left open (the write that creates
    ``rules`` would otherwise land outside the repository, unchecked).
    """
    if not _NAME_RE.match(name):
        return f"{tmpl_path}: invalid rule name {name!r}; must match {_NAME_RE.pattern!r}"

    if tmpl_path.is_symlink():
        return f"{tmpl_path}: templates/rules/{name}.md is a symlink, not a real file"
    if not tmpl_path.is_file():
        return f"{tmpl_path}: templates/rules/{name}.md is not a regular file"

    rules_root = repo_root / "src" / "claude" / "rules"
    resolved_repo = repo_root.resolve()

    if rules_root.is_symlink():
        return f"{tmpl_path}: src/claude/rules/ is a symlink, not a real directory"
    resolved_root = rules_root.resolve()
    if not resolved_root.is_relative_to(resolved_repo):
        return (
            f"{tmpl_path}: src/claude/rules/ resolves to {resolved_root}, "
            f"outside the repository root {resolved_repo}"
        )

    target = rules_root / f"{name}.md"
    if target.is_symlink():
        return f"{tmpl_path}: src/claude/rules/{name}.md is a symlink, not a real file"

    return None


def discover(repo_root: Path) -> dict[str, Path]:
    """Return ``{name: templates/rules/<name>.md}`` for every VALID template.

    An absent ``templates/rules/`` directory yields an empty mapping, not
    an error (mirrors ``agent_templates.discover``, ``skill_templates.discover``).
    """
    return {
        name: tmpl_path
        for name, tmpl_path in _iter_template_candidates(repo_root)
        if _name_validation_error(repo_root, name, tmpl_path) is None
    }


def discover_errors(repo_root: Path) -> list[str]:
    """Return one message per discovered name :func:`discover` excluded."""
    errors: list[str] = []
    for name, tmpl_path in _iter_template_candidates(repo_root):
        error = _name_validation_error(repo_root, name, tmpl_path)
        if error is not None:
            errors.append(error)
    return errors


def owned_targets(repo_root: Path) -> set[Path]:
    """Return every ``src/claude/rules/<name>.md`` this class renders.

    Used by ``build/scripts/build_all.py``'s OWNED_PREFIXES-based staleness
    check and by callers wanting the full render-target set without
    re-deriving it from :func:`discover`.
    """
    return {repo_root / "src" / "claude" / "rules" / f"{name}.md" for name in discover(repo_root)}


def _try_render(tmpl_path: Path, partials_dir: Path, result: CompileResult) -> str | None:
    """Render one template, recording any failure onto ``result``.

    Mirrors ``agent_templates._try_render`` exactly: the same three
    exception classes are graded the same floors, extracted to hold this
    module's compile loop under the cyclomatic-complexity ceiling.
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


def _compile_one(
    repo_root: Path,
    name: str,
    tmpl_path: Path,
    partials_dir: Path,
    *,
    validate: bool,
    what_if: bool,
    result: CompileResult,
) -> None:
    """Render, and (unless validating) write, one name's rendered rule.

    Extracted out of :func:`compile_all`'s loop body to hold that
    function's cyclomatic complexity down, mirroring
    ``agent_templates._compile_one_pair``.
    """
    target = repo_root / "src" / "claude" / "rules" / f"{name}.md"

    reason = detect_reason(target)
    if reason is not None:
        print(
            f"WARN: skipped {target} (NO-REGEN: {reason}); "
            "template-owned file exempt from drift gate"
        )
        result.skipped.append(str(target))
        result.exit_code = max(result.exit_code, 1)
        return

    rendered = _try_render(tmpl_path, partials_dir, result)
    if rendered is None:
        return

    current = target.read_text(encoding="utf-8", newline="") if target.is_file() else None
    if current == rendered:
        return

    if validate:
        print(f"DRIFT: {target} differs from its template ({tmpl_path})", file=sys.stderr)
        result.drifted.append(str(target))
        result.exit_code = max(result.exit_code, 1)
        return

    if what_if:
        print(f"  Would write: {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    publish_bytes_atomically(target, rendered.encode("utf-8"))
    result.written.append(str(target))


def compile_all(repo_root: Path, *, validate: bool, what_if: bool = False) -> CompileResult:
    """Compile every discovered rule template; write when the render differs.

    ``validate=True``: never writes ``src/claude/rules/<name>.md``. A
    target whose committed bytes differ from a fresh render is recorded as
    drift, exit 1. ``validate=False``: writes when the render differs,
    unless ``what_if`` is set, in which case it reports what it would write
    without touching the filesystem. Mirrors ``agent_templates.compile_all``'s
    modes exactly.

    An absent ``templates/rules/`` directory (or one with no valid
    template) is not an error: ``result`` stays at its zero-value
    defaults, exit 0, per DR5 in DESIGN-025 ("an unmigrated class is
    untouched"). A name with no template is likewise untouched: it is
    simply absent from :func:`discover`'s mapping.
    """
    result = CompileResult()
    partials_dir = repo_root / "templates" / "rules" / "partials"

    _report_discover_errors(repo_root, result)

    for name, tmpl_path in sorted(discover(repo_root).items()):
        _compile_one(
            repo_root,
            name,
            tmpl_path,
            partials_dir,
            validate=validate,
            what_if=what_if,
            result=result,
        )

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI: ``--validate`` renders in memory and reports drift; default writes.

    Exit codes are :func:`compile_all`'s (module docstring). The
    ``Rule Template Drift`` pre-PR gate wraps ``--validate`` the same way
    the agent and skill gates wrap their own compile modules.
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
