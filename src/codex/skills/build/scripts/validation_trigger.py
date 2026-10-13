#!/usr/bin/env python3
"""Decide whether a change can alter validation semantics (``/build`` Phase 2b).

`/build` Phase 3 lets an implementer edit any file, including a validator, a
generated mirror of one, or a baseline snapshot. Nothing before Phase 3 asks
who owns the failing check first. This script decides, from verified changed
paths and diff effects, whether the change needs the provenance-and-authority
gate (`analysis-provenance` then `validation-authority`) before Phase 3 edits
anything. It is a pure function of its arguments, so the same change always
gets the same decision.

A **path cue** flags a path that plausibly changes validation semantics on
its own: validator code, a ratchet or baseline file, a known validator config
file, or a validation test fixture. A **generated-output** cue flags a path
under a generated root, read from ``OWNED_PREFIXES`` in
``build/scripts/build_all.py`` (parsed with ``ast.literal_eval``, never
imported or executed), or a ``.claude/skills/<name>/SKILL.md`` whose template
``templates/skills/<name>.SKILL.md.tmpl`` exists. The generated-output cue
alone never activates the gate: a generated mirror of an ordinary skill is
not a validation target. It activates only paired with a path cue, or when
the caller passes the ``generated-validator`` effect for a diff-verified
generated-validator change the path cues cannot see.

An **effect** is a diff effect the caller verified in the diff body (for
example, a change to pass/fail semantics with no path cue to name it). Any
known effect activates the gate outright. An unknown effect, or an empty
changed-path list, is a caller error: this script fails closed by refusing
to guess (ADR-035 exit 2), unlike a sibling classifier (`test`'s
``dx_trigger.py``) that activates rather than erroring on those inputs,
because a validation-semantics false negative here can leave a mis-owned
validator edit unrecorded.

``build/scripts/build_all.py`` is optional: this script is also shipped in a
vendored plugin install with no ``build/`` directory. When it cannot be
found, the generated-output cue is skipped (every other cue still runs) and
``generated_roots_source`` is reported as ``null`` with a note.

EXIT CODES (ADR-035):
    0 - A decision was emitted on stdout as JSON.
    2 - Config error: no changed paths were supplied, or an unknown effect
        name was passed.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Sequence
from pathlib import Path

# Path cues that, alone, signal a validation-semantics location. Distinct
# from "generated-output", which never activates the gate by itself.
_VALIDATION_CUES = frozenset(
    {"validator-code", "ratchet-or-baseline", "validator-config", "validation-fixture"}
)

EFFECTS: frozenset[str] = frozenset(
    {
        "pass-fail-semantics",
        "severity-change",
        "baseline-update",
        "fixture-redefines-case",
        "validator-config",
        "vendored-logic",
        "generated-validator",
    }
)

_VALIDATOR_CODE_DIR_NAMES = frozenset({"validators", "linters"})
_VALIDATOR_STEM_PREFIXES = ("validat", "verify", "check", "lint", "scan")

_VALIDATOR_CONFIG_EXACT = frozenset(
    {
        "ruff.toml",
        "psscriptanalyzersettings.psd1",
        ".qualityrc.json",
        ".pre-commit-config.yaml",
        "lefthook.yml",
        ".gitleaks.toml",
    }
)
_VALIDATOR_CONFIG_PREFIXES = (".markdownlint", ".yamllint")

_BUILD_ALL_RELATIVE = Path("build") / "scripts" / "build_all.py"
_SKILL_MD_TEMPLATE_DIR = Path("templates") / "skills"


class TriggerConfigError(ValueError):
    """The caller passed input this script cannot decide from (ADR-035 exit 2)."""


def _segments(path: str) -> list[str]:
    parts = path.replace("\\", "/").strip().split("/")
    return [segment for segment in parts if segment and segment != "."]


def normalize_path(path: str) -> str:
    """Return ``path`` with forward slashes and no empty or ``.`` segments.

    ``./scripts/x.py``, ``.\\scripts\\x.py``, and ``scripts/./x.py`` all name
    ``scripts/x.py``. A ``..`` segment is kept; this script never resolves a
    caller-supplied path on disk.
    """
    return "/".join(_segments(path))


def _stem(name: str) -> str:
    """Name up to its first dot, keeping a leading dot: ``.pre-commit-config``."""
    if name.startswith("."):
        return "." + name[1:].split(".", 1)[0]
    return name.split(".", 1)[0]


def _is_validator_code(segments: list[str]) -> bool:
    if segments[:2] == ["scripts", "validation"]:
        return True
    if _VALIDATOR_CODE_DIR_NAMES & set(segments[:-1]):
        return True
    name = segments[-1]
    if segments[-2:-1] != ["scripts"]:
        return False
    return _stem(name).lower().startswith(_VALIDATOR_STEM_PREFIXES)


def _is_ratchet_or_baseline(segments: list[str]) -> bool:
    stem = _stem(segments[-1]).lower()
    return "ratchet" in stem or "baseline" in stem


def _is_validator_config(segments: list[str]) -> bool:
    name = segments[-1].lower()
    if name in _VALIDATOR_CONFIG_EXACT:
        return True
    return name.startswith(_VALIDATOR_CONFIG_PREFIXES)


def _is_validation_fixture(segments: list[str]) -> bool:
    if segments[:2] == ["tests", "validation"]:
        return True
    if "fixtures" not in segments:
        return False
    index = segments.index("fixtures")
    return "validation" in segments[:index]


def find_build_all(start: Path) -> Path | None:
    """Walk up from ``start`` to the first directory holding ``build_all.py``."""
    candidates = [start, *start.resolve().parents]
    for candidate in candidates:
        target = candidate / _BUILD_ALL_RELATIVE
        if target.is_file():
            return target
    return None


def read_owned_prefixes(build_all_path: Path) -> tuple[str, ...]:
    """Read ``OWNED_PREFIXES`` from ``build_all.py`` without importing it.

    ``OWNED_PREFIXES`` is declared as an annotated assignment
    (``OWNED_PREFIXES: tuple[str, ...] = (...)``), so this looks for an
    ``ast.AnnAssign`` (or plain ``ast.Assign``, for resilience) whose target
    is the name ``OWNED_PREFIXES`` and evaluates its value with
    ``ast.literal_eval``.
    """
    tree = ast.parse(build_all_path.read_text(encoding="utf-8"), filename=str(build_all_path))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "OWNED_PREFIXES" and node.value is not None:
                return tuple(ast.literal_eval(node.value))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "OWNED_PREFIXES":
                    return tuple(ast.literal_eval(node.value))
    raise ValueError(f"OWNED_PREFIXES assignment not found in {build_all_path}")


def _matches_owned_prefix(path: str, owned_prefixes: tuple[str, ...]) -> bool:
    normalized = normalize_path(path)
    for prefix in owned_prefixes:
        if prefix.endswith("/"):
            if normalized.startswith(prefix):
                return True
        elif normalized == prefix:
            return True
    return False


def _is_generated_skill_md(segments: list[str], repo_root: Path) -> bool:
    if len(segments) != 4 or segments[0] != ".claude" or segments[1] != "skills":
        return False
    if segments[3] != "SKILL.md":
        return False
    skill_name = segments[2]
    template = repo_root / _SKILL_MD_TEMPLATE_DIR / f"{skill_name}.SKILL.md.tmpl"
    return template.is_file()


class _GeneratedRoots:
    """Resolved ``OWNED_PREFIXES`` state: found, absent, or unparseable."""

    def __init__(self, source: Path | None, prefixes: tuple[str, ...], note: str | None) -> None:
        self.source = source
        self.prefixes = prefixes
        self.note = note

    @classmethod
    def resolve(cls, search_start: Path) -> _GeneratedRoots:
        build_all_path = find_build_all(search_start)
        if build_all_path is None:
            return cls(None, (), "build/scripts/build_all.py not found; vendored install assumed")
        try:
            prefixes = read_owned_prefixes(build_all_path)
        except (OSError, SyntaxError, ValueError) as exc:
            return cls(None, (), f"OWNED_PREFIXES unreadable in {build_all_path}: {exc}")
        return cls(build_all_path, prefixes, None)

    def is_generated(self, path: str, segments: list[str]) -> bool:
        if self.source is None:
            return False
        if _matches_owned_prefix(path, self.prefixes):
            return True
        # build_all.py lives at <root>/build/scripts/, so parents[2] is <root>.
        return _is_generated_skill_md(segments, self.source.parents[2])


def resolve_generated_roots(repo_root: Path) -> _GeneratedRoots:
    """Resolve ``OWNED_PREFIXES`` once so a caller can reuse it for many paths."""
    return _GeneratedRoots.resolve(repo_root)


def classify_path(path: str, repo_root: Path, roots: _GeneratedRoots | None = None) -> list[str]:
    """Return the path cues matching ``path`` alone (see module docstring).

    Used by ``validation-authority``'s ``validation_record.py`` to check
    "every path the trigger would flag" (DESIGN-039 Record rule 8) without
    duplicating the cue definitions in a second module.
    """
    return _cues_for_path(path, roots or _GeneratedRoots.resolve(repo_root))


def is_validation_target(path: str, repo_root: Path, roots: _GeneratedRoots | None = None) -> bool:
    """Return True when ``path`` alone, ignoring diff effects, needs a record entry.

    Mirrors the non-effect half of :func:`decide`'s per-path activation rule:
    a bare ``generated-output`` cue is not enough (AC4).
    """
    return bool(set(classify_path(path, repo_root, roots)) & _VALIDATION_CUES)


def _cues_for_path(path: str, roots: _GeneratedRoots) -> list[str]:
    segments = _segments(path)
    cues: list[str] = []
    if _is_validator_code(segments):
        cues.append("validator-code")
    if _is_ratchet_or_baseline(segments):
        cues.append("ratchet-or-baseline")
    if _is_validator_config(segments):
        cues.append("validator-config")
    if _is_validation_fixture(segments):
        cues.append("validation-fixture")
    if roots.is_generated(path, segments):
        cues.append("generated-output")
    return cues


def _normalize_paths(changed_paths: Sequence[str]) -> list[str]:
    return [normalize_path(path) for path in changed_paths if _segments(path)]


def _normalize_effects(effects: Sequence[str]) -> list[str]:
    normalized = [effect.strip().lower() for effect in effects]
    unknown = sorted({effect for effect in normalized if effect not in EFFECTS})
    if unknown:
        raise TriggerConfigError("unknown effect: " + ", ".join(unknown))
    return normalized


def _reason(targets: list[dict[str, object]], effects: list[str], skipped: list[str]) -> str:
    if targets and effects:
        names = ", ".join(str(t["path"]) for t in targets)
        return f"activate - validation target(s): {names}; effect(s): {', '.join(sorted(effects))}"
    if targets:
        names = ", ".join(str(t["path"]) for t in targets)
        return f"activate - validation target(s): {names}"
    if effects:
        return f"activate - verified effect(s): {', '.join(sorted(effects))}"
    return "skip - no validation target and no activating effect: " + ", ".join(skipped)


def decide(
    changed_paths: Sequence[str], effects: Sequence[str], repo_root: Path
) -> dict[str, object]:
    """Return the Phase 2b activation decision for one change.

    ``repo_root`` is the directory to start walking up from when looking for
    ``build/scripts/build_all.py`` (mirrors "walking up from cwd" in
    DESIGN-039; a caller passes its own repo root here for determinism).
    """
    paths = _normalize_paths(changed_paths)
    if not paths:
        raise TriggerConfigError("no changed paths supplied")
    normalized_effects = _normalize_effects(effects)

    roots = _GeneratedRoots.resolve(repo_root)
    generated_effect = "generated-validator" in normalized_effects

    targets: list[dict[str, object]] = []
    skipped: list[str] = []
    for path in paths:
        cues = _cues_for_path(path, roots)
        cue_set = set(cues)
        is_target = bool(cue_set & _VALIDATION_CUES) or (
            "generated-output" in cue_set and generated_effect
        )
        if is_target:
            targets.append({"path": path, "cues": sorted(cue_set)})
        else:
            skipped.append(path)

    activate = bool(targets) or bool(normalized_effects)
    return {
        "decision": "activate" if activate else "skip",
        "targets": sorted(targets, key=lambda t: str(t["path"])),
        "effects": sorted(normalized_effects),
        "reason": _reason(targets, normalized_effects, skipped),
        "generated_roots_source": str(roots.source) if roots.source else None,
        "generated_roots_note": roots.note,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        metavar="PATH",
        help="A path from the planned or verified changed-path list. Repeatable.",
    )
    parser.add_argument(
        "--effect",
        action="append",
        default=[],
        metavar="NAME",
        help="A diff effect verified in the diff body. Known values: "
        + ", ".join(sorted(EFFECTS))
        + ". An unknown value is a config error.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Directory to start searching upward for build/scripts/build_all.py. "
        "Defaults to the current working directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = args.repo_root or Path.cwd()
    try:
        result = decide(args.changed_path, args.effect, repo_root)
    except TriggerConfigError as exc:
        print(f"validation_trigger: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
