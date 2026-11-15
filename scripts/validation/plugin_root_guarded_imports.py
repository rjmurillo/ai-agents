"""Rule 2 exceptions for guarded imports, and the repo-local gate for the `uv` form.

ADR-121 decision 13: rule 2 of ``check_plugin_root_interpreter.py`` walks a target's
import closure and counts a guarded import as a dependency. A target listed in
``GUARDED_IMPORT_ALLOWANCES`` may reach the named module, but only while every
import of that module in the target's closure survives the module being absent,
by rule 5's test (``plugin_root_interpreter_rules.unguarded_third_party_imports``).
An entry covers one module; any other third-party module still fails.

ADR-121 decision 12: the locator's ``uv run --frozen python`` form is allowed only
in a skill whose template or ``SKILL.md`` sets ``distribution: repo-local``. The
flag is read through ``build/scripts/skill_distribution.py``. A site whose skill
cannot be named, or whose flag is missing, counts as shipped.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

_BUILD_SCRIPTS = Path(__file__).resolve().parents[2] / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))

import skill_distribution  # noqa: E402

from scripts.validation import check_doc_interpreter_portability as _doc  # noqa: E402
from scripts.validation import plugin_root_interpreter_rules as _rules  # noqa: E402

GuardedKey = tuple[str, str]  # (target under `.claude/`, third-party module)

# ADR-121 decision 13. Keyed by the target as rule 2 maps it (`.claude/<tail>`) and
# the module. The value names the sites the entry unblocks and the fallback, which
# tests/validation/test_plugin_root_guarded_imports.py runs with the module blocked.
# Entries arrive with the sites they unblock: an entry that no site applies is stale
# and fails the run, so one cannot land before its site migrates.
GUARDED_IMPORT_ALLOWANCES: dict[GuardedKey, str] = {}

_SKILL_FROM_TEMPLATE = re.compile(r"^templates/skills/(?P<name>[^/]+)\.SKILL\.md\.tmpl$")
_SKILL_FROM_TREE = re.compile(r"^(?:\.claude|src/[^/]+(?:/[^/]+)?)/skills/(?P<name>[^/]+)/")

ModuleResolver = Callable[[str, str, set[str]], list[str] | None]


def skill_name_of(rel: str) -> str | None:
    """Return the skill a site's file belongs to, or ``None`` when it names none."""
    match = _SKILL_FROM_TEMPLATE.match(rel) or _SKILL_FROM_TREE.match(rel)
    return match.group("name") if match else None


def is_repo_local_site(repo_root: Path, rel: str) -> bool:
    """Return whether ``rel`` belongs to a skill flagged ``distribution: repo-local``.

    A file outside a skill, a skill with no flag, and a flag that fails to parse all
    count as shipped, because a shipped site with the `uv` form fails for consumers.
    """
    name = skill_name_of(rel)
    if name is None:
        return False
    try:
        return bool(skill_distribution.is_repo_local(repo_root, name))
    except (skill_distribution.SkillDistributionError, OSError, ValueError):
        return False


def closure_files(target: str, repo_root: Path, tracked_py: set[str]) -> list[str]:
    """Return ``target`` and every tracked file rule 2's walk reaches from it.

    The edges come from ``check_doc_interpreter_portability.dependency_files``:
    import-time imports and tracked scripts started through ``sys.executable``.
    """
    seen: list[str] = []
    queue = [_doc.canonical_path(target, repo_root, tracked_py)]
    while queue:
        rel = queue.pop(0)
        if rel in seen:
            continue
        seen.append(rel)
        queue.extend(_doc.dependency_files(rel, repo_root, tracked_py))
    return seen


def unguarded_in_closure(
    target: str, module: str, repo_root: Path, tracked_py: set[str], resolve: ModuleResolver
) -> list[str]:
    """Return the closure files that import ``module`` with no surviving fallback."""
    found: list[str] = []
    for rel in closure_files(target, repo_root, tracked_py):
        source = (repo_root / rel).read_text(encoding="utf-8")

        def is_repo_module(name: str, importer: str = rel) -> bool:
            return resolve(name, importer, tracked_py) is not None

        names = {name for _, name in _rules.unguarded_third_party_imports(source, is_repo_module)}
        if module in names:
            found.append(rel)
    return found


def allowed_modules(
    target: str,
    external: list[str],
    repo_root: Path,
    tracked_py: set[str],
    resolve: ModuleResolver,
) -> tuple[list[str], set[GuardedKey], list[str]]:
    """Split ``external`` into what still fails and what an allowance covers.

    Returns ``(remaining, used, problems)``. An allowance whose import lost its
    guard does not cover the module, and ``problems`` says where the guard is gone.
    """
    remaining: list[str] = []
    used: set[GuardedKey] = set()
    problems: list[str] = []
    for module in external:
        key = (target, module)
        if key not in GUARDED_IMPORT_ALLOWANCES:
            remaining.append(module)
            continue
        unguarded = unguarded_in_closure(target, module, repo_root, tracked_py, resolve)
        if unguarded:
            remaining.append(module)
            problems.append(
                f"allowance for {target} and {module} needs a guarded import, but "
                f"{', '.join(unguarded)} imports it with no fallback (ADR-121 decision 13)"
            )
            continue
        used.add(key)
    return remaining, used, problems
