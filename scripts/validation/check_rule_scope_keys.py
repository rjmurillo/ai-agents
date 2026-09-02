#!/usr/bin/env python3
"""Gate: every `.claude/rules/*.md` must scope itself with `paths:`.

Claude Code reads `paths:` from rule frontmatter. It ignores `applyTo:`,
`globs:`, and `alwaysApply:`. `build/scripts/generate_rules.py` accepts all of
them (`_SCOPE_KEYS = ("paths", "applyTo", "globs")` plus an `alwaysApply:` drop),
and each wrong key fails in its own way. Measured by generating one rule per
shape through the real generator:

  - `paths: '**/*.py'`         -> mirror `applyTo: '**/*.py'`. Both trees scoped.
  - `applyTo: '**/*.py'`       -> mirror `applyTo: '**/*.py'`. Only the mirror is
    scoped; the Claude source declares nothing and the rule loads every turn.
  - `globs: '**/*.py'`         -> mirror `globs: '**/*.py'`, preserved verbatim.
    `templates/platforms/copilot-cli.yaml` remaps only `paths`, so no `applyTo:`
    is ever produced and NEITHER tree is scoped.
  - `alwaysApply: true`        -> mirror `applyTo: '**'`. The key is dropped and
    the universal scope is synthesized, so both trees load on every turn and a
    code-only rule has no way to state its scope.

That is not a hypothetical. `pragmatic-programmer.md` declared 18 code globs
under `applyTo:` and loaded on doc-only sessions anyway; `code-quality.md`
declared `alwaysApply: true` and did the same. Together they cost 25,527 bytes
(about 6,381 tokens) on every session that touched no code (issue #4871).
`scripts/validation/instruction_budget.py` cannot see the `applyTo:` case: it
measures the generated `.github/instructions/` tree, where that rule looks
correctly scoped.

The check is therefore on the source tree only:

  - a rule MUST declare `paths:`
  - `paths:` MUST hold a non-empty list of non-empty glob strings. `paths:`
    with no value parses as `None`, and `paths: []` parses as an empty list;
    both declare a key with no usable scope, which is the same leak the key
    name was supposed to close.
  - a rule MUST NOT declare `applyTo:`, `globs:`, or `alwaysApply:`

This gate is deliberately stricter than `generate_rules.py`, which still
accepts all four shapes. Why the generator is not the place to fix it: it has
downstream consumers that pass it frontmatter this repository does not own, and
tightening it would fail their builds on a key that is merely useless here
rather than wrong everywhere. The narrow fix is a source-tree gate over
`.claude/rules/` alone, which is the only tree whose loader semantics this
repository controls. The generator keeps accepting `applyTo:` so that its
contract with those consumers is unchanged.

Exit codes (ADR-035):
    0 - Success (every rule scopes itself with `paths:` and nothing else)
    1 - Logic error (a rule uses an ignored scope key, or declares no scope)
    2 - Config error (invalid repository root, or a rules directory with no
        rule files, which would make a PASS vacuous)
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from yaml_utils import _parse_yaml_frontmatter  # noqa: E402

RULES_SUBDIR = Path(".claude") / "rules"
SCOPE_KEY = "paths"
IGNORED_SCOPE_KEYS = ("applyTo", "globs", "alwaysApply")


def _scope_value_defect(value: object) -> str | None:
    """Return why `paths:` declares no usable scope, or None when it does.

    Key presence is not scope. `paths:` (empty), `paths: []`, `paths: {}`, and
    `paths: [""]` all satisfy a `key in frontmatter` test while telling the
    loader nothing, so the rule falls back to loading everywhere.
    """
    if not isinstance(value, list):
        return f"declares `paths:` as {type(value).__name__}, not a list of globs"
    if not value:
        return "declares an empty `paths:` list, so it declares no scope"
    if not all(isinstance(entry, str) and entry.strip() for entry in value):
        return "declares a `paths:` entry that is empty or not a string"
    return None


class RulesDirectoryError(Exception):
    """The rules tree cannot answer the question this gate asks."""


def rule_files(repo_root: Path) -> list[Path]:
    """Return every rule file, or raise when the tree cannot be surveyed.

    Raises `RulesDirectoryError` for a missing directory and for a directory
    holding no rule files. Either would make an empty finding list mean "no
    rules were checked" while reading as "every rule passed".
    """
    rules_dir = repo_root / RULES_SUBDIR
    if not rules_dir.is_dir():
        raise RulesDirectoryError(f"{RULES_SUBDIR.as_posix()} is not a directory")
    files = sorted(rules_dir.glob("*.md"))
    if not files:
        raise RulesDirectoryError(f"{RULES_SUBDIR.as_posix()} holds no *.md rule files")
    return files


def find_scope_key_violations(repo_root: Path) -> list[tuple[Path, str]]:
    """Return one `(path, reason)` for every rule Claude Code would misread.

    One finding per rule, not one per key. A rule that declares `applyTo:` and
    no `paths:` has one defect with one fix; reporting it twice buries the file
    count that tells the reader how much of the tree is wrong.
    """
    findings: list[tuple[Path, str]] = []
    for path in rule_files(repo_root):
        front = _parse_yaml_frontmatter(path.read_text(encoding="utf-8")) or {}
        ignored = [key for key in IGNORED_SCOPE_KEYS if key in front]
        if ignored:
            keys = ", ".join(f"`{key}:`" for key in ignored)
            findings.append((path, f"declares {keys}, which Claude Code ignores; use `paths:`"))
        elif SCOPE_KEY not in front:
            findings.append((path, "declares no `paths:` key, so it loads on every session"))
        else:
            defect = _scope_value_defect(front[SCOPE_KEY])
            if defect:
                findings.append((path, defect))
    return findings


def validate_rule_scope_keys(repo_root: Path) -> bool:
    """Return True when every rule scopes itself with `paths:` alone.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    findings = find_scope_key_violations(repo_root)
    if not findings:
        return True
    print(
        f"[FAIL] {len(findings)} rule scope declaration(s) Claude Code does not honor:",
        file=sys.stderr,
    )
    for path, reason in findings:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel.as_posix()}: {reason}", file=sys.stderr)
    print(
        "\nFix: write the scope as a `paths:` list of globs "
        '(`paths: ["**"]` for a rule that really does load on every turn), '
        "then regenerate the mirrors with build/scripts/generate_rules.py.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        ok = validate_rule_scope_keys(repo_root)
    except RulesDirectoryError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
