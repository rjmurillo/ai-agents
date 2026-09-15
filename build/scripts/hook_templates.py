#!/usr/bin/env python3
r"""Compile ``templates/hooks/`` into ``src/claude/hooks/`` and ``.claude/settings.json``.

ADR-109 (Template-First Plugin Distribution) step B4 generalizes ADR-108's
compile-and-drift-gate shape, already applied to skills, agents
(``build/scripts/agent_templates.py``, B1), and rules
(``build/scripts/rule_templates.py``, B2), to the hooks-and-settings class.
Per ``.agents/specs/design/DESIGN-025-template-first-compiler-and-binplace.md``,
"Per-class compile modules" section, hooks has no grammar step: "the compile
is a byte copy for scripts and a render for ``settings.json`` and
``hooks.json``, ... ADR-108's mustache grammar applies to the markdown
classes only" (ADR-109 section 6). This module therefore imports neither
``skill_template_grammar`` nor its ``rule_templates``/``agent_templates``
render path; every discovered template's bytes are copied verbatim to its
target after a JSON-parseability check for the JSON-shaped names
(``hooks.json``, ``dispatch_groups.json``, the settings template). A raw
byte copy guarantees the first render is byte-identical to today's
committed files trivially, without needing to replicate ``json.dumps``'s
exact formatting; DESIGN-025's "json.dumps after a dict merge" phrasing
describes a future per-platform-override capability this task's
single-source-single-target rows do not need yet (deviation recorded in
this task's PR body).

Three render targets, not one, because ADR-109 section 2 and 3 name three
different destinations for this one template tree:

1. ``templates/hooks/<name>`` (14 of the 16 hooks-class files: 13
   executables plus ``dispatch_groups.json`` and
   ``PreToolUse/markdownlint-safe-config.yaml``) renders to
   ``src/claude/hooks/<name>``, the plugin tree's ``hooks/`` subdirectory.
2. ``templates/hooks/hooks.json`` renders to ``src/claude/hooks.json``, at
   the PLUGIN ROOT rather than nested under ``hooks/``: ADR-109 section 2
   lists ``src/claude/``'s content as "agents/, skills/, rules/, hooks/
   plus hooks.json", a top-level sibling, and TASK-034's acceptance
   criteria pin ``test -f src/claude/hooks.json`` at that exact path. This
   is a deliberate deviation from DESIGN-025's binplace-manifest excerpt,
   which shows the ``hooks-json`` row with ``plugin_tree: null`` (a direct
   render straight to ``.claude/hooks/hooks.json``, no plugin-tree hop):
   that excerpt predates B1-B3 and conflicts with ADR-109 section 2's own
   text and with TASK-034's machine-checkable acceptance criterion, so this
   module follows the criterion and gives ``hooks.json`` a real plugin-tree
   file, ``src/claude/hooks.json``, mirroring every other migrated class
   instead of being the one class rendered with no plugin stage at all.
3. ``templates/hooks/settings.tmpl`` renders straight to
   ``.claude/settings.json``, with NO plugin-tree hop at all: ADR-109
   section 3 states ``.claude/settings.json`` "is repo-local dogfood
   configuration and ships in no plugin," so :func:`compile_all` writes it
   directly, the one target in this module that is not under ``src/``.

Stricter/looser/different than canonical (``rule_templates.py``):

- Different: no mustache grammar, no partials directory, no ``render()``
  delegation. ``check_grammar`` does not exist on this module (DESIGN-025:
  "hooks has no grammar step").
- Different: three target shapes instead of one (``src/claude/hooks/<rel>``,
  ``src/claude/hooks.json``, ``.claude/settings.json``), so
  :func:`discover` returns ``dict[str, Path]`` keyed by a POSIX-style
  relative name under ``templates/hooks/`` (e.g. ``"PreToolUse/_bootstrap.py"``),
  and :func:`_target_for` maps a name to its one target path.
- Same: NO-REGEN sentinel handling, CWE-22 (repository containment) and
  CWE-59 (no-symlink-follow write) defenses, and the write-through-
  ``publish_bytes_atomically`` write path mirror ``rule_templates.py``'s
  shape exactly, adapted for three target roots instead of one.
- Same: an absent ``templates/hooks/`` directory yields an empty mapping
  (DR5, "an unmigrated class is untouched"), not an error.

EXIT CODES (per :func:`compile_all`; ``0=ok|1=logic|2=config`` per
``AGENTS.md`` Standards, worst-code-wins across every discovered name):
  0 - no templates found, or every template renders clean (write mode) /
      matches the committed target (validate mode)
  1 - a rendered target drifted from the committed one (validate mode), or
      a NO-REGEN-skipped target
  2 - a discovered name resolves outside the repository, the template or a
      target is a symlink, a JSON-shaped template fails to parse as JSON,
      or ``templates/hooks/`` itself is a symlink or resolves outside the
      repository
"""

from __future__ import annotations

import json
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

# Names whose content must parse as JSON before being written (DESIGN-025:
# "a render for settings.json and hooks.json"; dispatch_groups.json is the
# same shape and gets the same cheap safety net).
_JSON_NAMES = frozenset({"hooks.json", "dispatch_groups.json"})
_SETTINGS_TEMPLATE_NAME = "settings.tmpl"


@dataclass
class CompileResult:
    """Outcome of one :func:`compile_all` run across every discovered name."""

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    exit_code: int = 0


def _templates_root(repo_root: Path) -> Path:
    return repo_root / "templates" / "hooks"


def _iter_template_candidates(repo_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(name, template_path)`` for every hooks-class template file.

    ``name`` is the POSIX-style path relative to ``templates/hooks/``.
    ``settings.tmpl`` is excluded here: it is a separate render (item 3 in
    the module docstring), handled by :func:`_compile_settings`, not part
    of the ``src/claude/hooks/`` plugin tree. An absent ``templates/hooks/``
    directory yields nothing (mirrors ``rule_templates._iter_template_candidates``).
    """
    root = _templates_root(repo_root)
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.name == _SETTINGS_TEMPLATE_NAME and path.parent == root:
            continue
        yield path.relative_to(root).as_posix(), path


def _target_for(repo_root: Path, name: str) -> Path:
    """Return the one render target for a discovered hooks-class ``name``.

    ``hooks.json`` is the plugin-root exception (module docstring, item 2);
    every other name renders under ``src/claude/hooks/`` at the same
    relative path it holds under ``templates/hooks/``.
    """
    if name == "hooks.json":
        return repo_root / "src" / "claude" / "hooks.json"
    return repo_root / "src" / "claude" / "hooks" / name


def _resolved_containment_error(repo_root: Path, label: str, path: Path) -> str | None:
    """Return why ``path`` escapes the repository root, or ``None``.

    Resolves unconditionally (not only when ``path`` exists): ``resolve()``
    follows symlinks in existing ancestors and appends any missing leaf
    literally, so this also catches an ancestor directory symlinked outside
    the repository before the leaf itself is ever created (mirrors
    ``rule_templates._name_validation_error``'s ``rules_root`` check).
    """
    resolved_repo = repo_root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_repo):
        return f"{label} {path} resolves to {resolved}, outside the repository root {resolved_repo}"
    return None


def _source_validation_error(repo_root: Path, name: str, tmpl_path: Path) -> str | None:
    """Return why ``templates/hooks/<name>`` is refused as a source, or ``None``."""
    if tmpl_path.is_symlink():
        return f"templates/hooks/{name} is a symlink, not a real file"
    if not tmpl_path.is_file():
        return f"templates/hooks/{name} is not a regular file"
    return _resolved_containment_error(repo_root, f"templates/hooks/{name}", tmpl_path)


def _target_validation_error(repo_root: Path, name: str, target: Path) -> str | None:
    """Return why ``target`` is refused as a render destination, or ``None``."""
    if target.parent.is_symlink():
        return f"{target.parent} is a symlink, not a real directory"
    parent_error = _resolved_containment_error(repo_root, f"{name} target parent", target.parent)
    if parent_error is not None:
        return parent_error
    if target.is_symlink():
        return f"{target} is a symlink, not a real file"
    if target.is_file():
        return _resolved_containment_error(repo_root, f"{name} target", target)
    return None


def _name_validation_error(repo_root: Path, name: str, tmpl_path: Path) -> str | None:
    """Return why ``name`` is not a valid hooks-class template, or ``None``."""
    source_error = _source_validation_error(repo_root, name, tmpl_path)
    if source_error is not None:
        return source_error
    target = _target_for(repo_root, name)
    return _target_validation_error(repo_root, name, target)


def discover(repo_root: Path) -> dict[str, Path]:
    """Return ``{name: templates/hooks/<name>}`` for every VALID template.

    An absent ``templates/hooks/`` directory yields an empty mapping
    (mirrors ``rule_templates.discover``, ``agent_templates.discover``).
    """
    root_error = _root_validation_error(repo_root)
    if root_error is not None:
        return {}
    return {
        name: tmpl_path
        for name, tmpl_path in _iter_template_candidates(repo_root)
        if _name_validation_error(repo_root, name, tmpl_path) is None
    }


def _root_validation_error(repo_root: Path) -> str | None:
    """Return why ``templates/hooks/`` itself is refused, or ``None``.

    Checked once, ahead of every candidate, the same reason
    ``rule_templates._partials_dir_error`` checks its shared partials
    directory once: a symlinked or escaping SOURCE ROOT is a single point
    of compromise for every name under it, not just one.
    """
    root = _templates_root(repo_root)
    if not root.is_dir():
        return None
    if root.is_symlink():
        return "templates/hooks is a symlink, not a real directory"
    return _resolved_containment_error(repo_root, "templates/hooks", root)


def discover_errors(repo_root: Path) -> list[str]:
    """Return one message per discovered name :func:`discover` excluded."""
    root_error = _root_validation_error(repo_root)
    if root_error is not None:
        return [root_error]
    errors: list[str] = []
    for name, tmpl_path in _iter_template_candidates(repo_root):
        error = _name_validation_error(repo_root, name, tmpl_path)
        if error is not None:
            errors.append(error)
    return errors


def owned_targets(repo_root: Path) -> set[Path]:
    """Return every path this class renders: the hooks plugin tree, its
    root-level ``hooks.json``, and the direct-rendered ``.claude/settings.json``.

    Used by ``build/scripts/build_all.py``'s OWNED_PREFIXES-based staleness
    check and by the binplace manifest's allowlist derivation.
    """
    targets = {_target_for(repo_root, name) for name in discover(repo_root)}
    settings_tmpl = _templates_root(repo_root) / _SETTINGS_TEMPLATE_NAME
    if _settings_source_error(repo_root, settings_tmpl) is None and settings_tmpl.is_file():
        targets.add(repo_root / ".claude" / "settings.json")
    return targets


def _validate_json_bytes(name: str, content: bytes, result: CompileResult) -> bool:
    """Return True when ``content`` is not JSON-shaped or parses cleanly.

    A JSON-shaped template (``hooks.json``, ``dispatch_groups.json``, or
    the settings template) that fails to parse is exit 2, never written
    (TASK-034 Testing Requirements: "a malformed JSON template (invalid
    after render) exits 2").
    """
    if name not in _JSON_NAMES and name != _SETTINGS_TEMPLATE_NAME:
        return True
    try:
        json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        print(f"Error: {name} is not valid JSON: {exc}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)
        return False
    return True


def _compile_one(
    repo_root: Path,
    name: str,
    tmpl_path: Path,
    target: Path,
    *,
    validate: bool,
    what_if: bool,
    result: CompileResult,
) -> None:
    """Render, and (unless validating) write, one name's rendered file.

    Extracted out of :func:`compile_all`'s loop body to hold that
    function's cyclomatic complexity down, mirroring
    ``rule_templates._compile_one``.
    """
    reason = detect_reason(target)
    if reason is not None:
        print(
            f"WARN: skipped {target} (NO-REGEN: {reason}); "
            "template-owned file exempt from drift gate"
        )
        result.skipped.append(str(target))
        result.exit_code = max(result.exit_code, 1)
        return

    content = tmpl_path.read_bytes()
    if not _validate_json_bytes(name, content, result):
        return

    current = target.read_bytes() if target.is_file() else None
    if current == content:
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
    mode = tmpl_path.stat().st_mode & 0o777
    publish_bytes_atomically(target, content, mode=mode)
    result.written.append(str(target))


def _settings_source_error(repo_root: Path, tmpl_path: Path) -> str | None:
    """Return why ``templates/hooks/settings.tmpl`` is refused, or ``None``."""
    if not tmpl_path.is_file():
        return None
    if tmpl_path.is_symlink():
        return "templates/hooks/settings.tmpl is a symlink, not a real file"
    return _resolved_containment_error(repo_root, "templates/hooks/settings.tmpl", tmpl_path)


def _compile_settings(
    repo_root: Path, *, validate: bool, what_if: bool, result: CompileResult
) -> None:
    """Render ``templates/hooks/settings.tmpl`` straight to ``.claude/settings.json``.

    No plugin-tree hop (module docstring, item 3): ``.claude/settings.json``
    ships in no plugin, so this writes the install target directly. A
    missing ``settings.tmpl`` is not an error, mirroring every other
    "no template yet" case in this module.
    """
    tmpl_path = _templates_root(repo_root) / _SETTINGS_TEMPLATE_NAME
    if not tmpl_path.is_file():
        return

    source_error = _settings_source_error(repo_root, tmpl_path)
    if source_error is not None:
        print(f"Error: {source_error}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)
        return

    target = repo_root / ".claude" / "settings.json"
    target_error = _target_validation_error(repo_root, "settings", target)
    if target_error is not None:
        print(f"Error: {target_error}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)
        return

    _compile_one(
        repo_root,
        _SETTINGS_TEMPLATE_NAME,
        tmpl_path,
        target,
        validate=validate,
        what_if=what_if,
        result=result,
    )


def compile_all(repo_root: Path, *, validate: bool, what_if: bool = False) -> CompileResult:
    """Compile every discovered hooks-class template and the settings template.

    ``validate=True``: never writes. A target whose committed bytes differ
    from the template is recorded as drift, exit 1. ``validate=False``:
    writes when the bytes differ, unless ``what_if`` is set, in which case
    it reports what it would write without touching the filesystem.
    Mirrors ``rule_templates.compile_all``'s modes exactly.

    An absent ``templates/hooks/`` directory (or one with no valid
    template) is not an error: ``result`` stays at its zero-value
    defaults, exit 0, per DR5 in DESIGN-025.
    """
    result = CompileResult()

    root_error = _root_validation_error(repo_root)
    if root_error is not None:
        print(f"Error: {root_error}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)
        return result

    for error in discover_errors(repo_root):
        print(f"Error: {error}", file=sys.stderr)
        result.exit_code = max(result.exit_code, 2)

    for name, tmpl_path in sorted(discover(repo_root).items()):
        _compile_one(
            repo_root,
            name,
            tmpl_path,
            _target_for(repo_root, name),
            validate=validate,
            what_if=what_if,
            result=result,
        )

    _compile_settings(repo_root, validate=validate, what_if=what_if, result=result)

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI: ``--validate`` renders in memory and reports drift; default writes.

    Exit codes are :func:`compile_all`'s (module docstring). The
    ``Hook Template Drift`` pre-PR gate wraps ``--validate`` the same way
    the agent, rule, and skill gates wrap their own compile modules.
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
