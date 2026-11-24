#!/usr/bin/env python3
"""Ratchet: a skill description's trigger phrases must route through autoplan.

On 2026-11-19 `adr-generator` was never selected while a session wrote an ADR.
Its description listed phrases such as "write an ADR", but the skill declared no
`metadata.routing.intents`, so the deterministic resolver
`src/claude/skills/autoplan/scripts/resolve_route.py` returned `none` for every
one of them. Nothing checked that the phrases a description advertises route.
This gate feeds each phrase to the real resolver and compares the answer.

Phrase extraction (deterministic, per skill, over the `description` string):

1. Take every double-quoted "..." segment and every backtick `...` segment.
2. Drop a segment that contains `/` or `.`, or starts with `/` (a path, a file
   name, or a slash command, not a request a user types).
3. Drop a segment with fewer than 2 word tokens (`[A-Za-z0-9]+`).
4. Drop a segment that starts after the first `Do NOT` (case-sensitive) in the
   description. Those clauses name other skills' work.
5. Keep first-seen order and drop exact repeats.

Checks, each named so the baseline tracks them separately:

- `own-phrase-unrouted`: a skill declaring `metadata.routing.intents` on a
  `front-door` role must have every extracted phrase resolve with kind
  `specialist` to that same skill.
- `phrase-routes-to-sibling`: for any skill, with or without intents, an
  extracted phrase must not resolve with kind `specialist` to a different
  skill. A skill with intents whose phrase lands on a sibling fires both
  checks, because each one answers its own question.
- `front-door-phrases-without-intents`: a `front-door` skill that advertises at
  least one phrase but declares no `intents`. The deterministic resolver cannot
  reach it, so every phrase routes only if a model happens to read the
  description. `adr-generator` sat in this state until 2026-11-19, when 56 of
  67 sessions that wrote an ADR never invoked it. The check records one
  identity per advertised phrase that does not route to the skill, so a
  baselined skill cannot add an unroutable phrase under an older entry.

Resolver use: the resolver's own `main` is loaded from its file path and called
with `--request` and `--skills-root`, the way `scripts/eval/eval_autoplan_routes.py`
does. Skills are listed from `.claude/skills`, but phrases resolve against
`src/claude/skills`, the catalog autoplan's default invocation reads. Routes may be namespaced
(`project-toolkit:adr-generator`); the bare name
after the colon is compared.

Ratchet: `skill_trigger_resolution_baseline.json` holds `(check, skill, phrase)`
identities. A violation outside the baseline fails. A baseline entry that no
longer fires is reported so it can be removed; it does not fail the run.
`--write-baseline` regenerates the file from the current tree.

Stricter/looser than `check_adr_lifecycle.py`: this gate uses the same
identity-ratchet shape but does not compare against the baseline at the merge
base, so a branch can raise its own ceiling with `--write-baseline`. Review of
the baseline diff is the control.

Exit codes (ADR-035):
    0 - no violation outside the baseline (stale entries are reported)
    1 - at least one violation identity is absent from the baseline
    2 - config error (unreadable skill, resolver load failure, bad baseline)
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a project dependency
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.hook_utilities.frontmatter_block import (  # noqa: E402
    FrontmatterStatus,
    parse_frontmatter,
)

RESOLVER = REPO_ROOT / "src" / "claude" / "skills" / "autoplan" / "scripts" / "resolve_route.py"
# The install tree holds every skill: shipped ones link into src/claude/skills
# (ADR-119) and repo-local ones live here only, so both are checked.
SKILLS_SUBDIR = Path(".claude") / "skills"
# Autoplan's default invocation resolves against the shipped plugin tree, so a
# phrase counts as routable only when that catalog routes it. A tree without
# one (a test fixture) resolves against the skills directory instead.
CATALOG_SUBDIR = Path("src") / "claude" / "skills"
BASELINE_RELATIVE = Path("scripts") / "validation" / "skill_trigger_resolution_baseline.json"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG = 2

CHECK_OWN = "own-phrase-unrouted"
CHECK_SIBLING = "phrase-routes-to-sibling"
CHECK_NO_INTENTS = "front-door-phrases-without-intents"
CHECKS: tuple[str, ...] = (CHECK_OWN, CHECK_SIBLING, CHECK_NO_INTENTS)
SCHEMA_VERSION = "1"

_QUOTED_RE = re.compile(r'"([^"]+)"|`([^`]+)`')
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_REDIRECT_MARKER = "Do NOT"
_MIN_WORDS = 2


class Root(Protocol):
    """The two fields of the resolver's `Root` this gate keys its cache on."""

    path: Path
    namespace: str


Identity = tuple[str, str, str]
_RESOLVER_CACHE: dict[Path, Callable[[list[str]], int]] = {}
_CATALOG_CACHE: dict[Any, Any] = {}


class ConfigError(Exception):
    """An input problem that must fail the run as exit 2."""


@dataclass(frozen=True, slots=True)
class Skill:
    """The slice of one skill this gate reads."""

    name: str
    description: str
    has_intents: bool
    front_door: bool = False
    skill_md: Path | None = None


def extract_phrases(description: str) -> list[str]:
    """Return the trigger phrases a description advertises, per the module rules."""
    cut = description.find(_REDIRECT_MARKER)
    phrases: list[str] = []
    for match in _QUOTED_RE.finditer(description):
        if cut != -1 and match.start() > cut:
            continue
        phrase = (match.group(1) or match.group(2)).strip()
        if "/" in phrase or "." in phrase:
            continue
        if len(_WORD_RE.findall(phrase)) < _MIN_WORDS:
            continue
        if phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _parse_frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: unreadable: {exc}") from exc
    result = parse_frontmatter(text, yaml, allow_duplicate_keys=True)
    if not result.present or result.status is FrontmatterStatus.UNTERMINATED:
        raise ConfigError(f"{path}: no YAML frontmatter")
    if result.status is FrontmatterStatus.MALFORMED:
        detail = (result.error or "").removeprefix("invalid YAML frontmatter: ")
        raise ConfigError(f"{path}: frontmatter does not parse: {detail}")
    if result.status is not FrontmatterStatus.VALID:
        raise ConfigError(f"{path}: frontmatter is not a mapping")
    return cast(dict[str, Any], result.metadata)


def _declares_intents(path: Path, data: dict[str, Any]) -> bool:
    metadata = data.get("metadata")
    routing = metadata.get("routing") if isinstance(metadata, dict) else None
    if not isinstance(routing, dict) or "intents" not in routing:
        return False
    intents = routing["intents"]
    if not isinstance(intents, list) or not all(isinstance(i, str) for i in intents):
        raise ConfigError(f"{path}: metadata.routing.intents must be a list of strings")
    return routing.get("role") == "front-door" and bool(intents)


def _is_front_door(data: dict[str, Any]) -> bool:
    metadata = data.get("metadata")
    routing = metadata.get("routing") if isinstance(metadata, dict) else None
    return isinstance(routing, dict) and routing.get("role") == "front-door"


def load_skills(skills_dir: Path) -> list[Skill]:
    """Read every `<skills_dir>/*/SKILL.md`. Any unreadable skill is a config error."""
    if not skills_dir.is_dir():
        raise ConfigError(f"skills directory does not exist: {skills_dir}")
    skills: list[Skill] = []
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        data = _parse_frontmatter(path)
        description = data.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ConfigError(f"{path}: description missing or not a string")
        skills.append(
            Skill(
                path.parent.name,
                description,
                _declares_intents(path, data),
                _is_front_door(data),
                path,
            )
        )
    if not skills:
        raise ConfigError(f"no SKILL.md files under {skills_dir}")
    return skills


def _memoize_catalog(module: ModuleType) -> None:
    """Parse the skill catalog once per run instead of once per phrase.

    The resolver's `main` rebuilds its catalog on every call, which costs
    about 27 s over the real tree. Wrapping its `_load_catalog` leaves matching
    untouched. If the resolver drops that name, calls fall back to the
    uncached (slower, still correct) path.
    """
    original = getattr(module, "_load_catalog", None)
    if not callable(original):
        return

    def cached(roots: list[Root]) -> object:
        key = tuple((str(r.path), r.namespace) for r in roots)
        if key not in _CATALOG_CACHE:
            _CATALOG_CACHE[key] = original(roots)
        return _CATALOG_CACHE[key]

    vars(module)["_load_catalog"] = cached


def _load_resolver_main() -> Callable[[list[str]], int]:
    """Import the resolver's own `main` from its file path (same as the eval)."""
    if RESOLVER in _RESOLVER_CACHE:
        return _RESOLVER_CACHE[RESOLVER]
    spec = importlib.util.spec_from_file_location("autoplan_resolve_route_gate", RESOLVER)
    if spec is None or spec.loader is None:
        raise ConfigError(f"cannot load resolver: {RESOLVER}")
    module = importlib.util.module_from_spec(spec)
    # The resolver defines dataclasses, which look their module up in sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # any import-time failure is a config error, not a crash
        sys.modules.pop(spec.name, None)
        raise ConfigError(f"cannot load resolver {RESOLVER}: {exc!r}") from exc
    main = getattr(module, "main", None)
    if not callable(main):
        sys.modules.pop(spec.name, None)
        raise ConfigError(f"resolver {RESOLVER} defines no callable main")
    _memoize_catalog(module)
    _RESOLVER_CACHE[RESOLVER] = cast(Callable[[list[str]], int], main)
    return _RESOLVER_CACHE[RESOLVER]


def resolve(request: str, skills_dir: Path) -> dict[str, Any]:
    """Run the real resolver on one request against `skills_dir`."""
    out, err = io.StringIO(), io.StringIO()
    argv = ["--request", request, "--skills-root", str(skills_dir)]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _load_resolver_main()(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
    except ConfigError:
        raise
    except Exception as exc:  # a resolver crash is a config error, never exit 1
        raise ConfigError(f"resolver crashed for {request!r}: {exc!r}") from exc
    if code != 0:
        raise ConfigError(f"resolver exited {code} for {request!r}: {err.getvalue().strip()[:200]}")
    try:
        result = json.loads(out.getvalue())
    except ValueError as exc:
        raise ConfigError(f"resolver output is not JSON for {request!r}") from exc
    if not isinstance(result, dict) or "kind" not in result:
        raise ConfigError(f"resolver output has no `kind` for {request!r}: {out.getvalue()[:200]}")
    return cast(dict[str, Any], result)


def _bare(route: object) -> str | None:
    return route.split(":", 1)[-1] if isinstance(route, str) else None


def find_violations(skills: list[Skill], skills_dir: Path) -> set[Identity]:
    """Resolve every skill's phrases against `skills_dir`, the catalog autoplan reads.

    Return the violating identities.
    """
    found: set[Identity] = set()
    _CATALOG_CACHE.clear()
    for skill in skills:
        for phrase in extract_phrases(skill.description):
            result = resolve(phrase, skills_dir)
            routed = _bare(result.get("route")) if result["kind"] == "specialist" else None
            # One identity per phrase, so a baselined skill cannot add an
            # unroutable phrase under an older entry.
            if skill.front_door and not skill.has_intents and routed != skill.name:
                found.add((CHECK_NO_INTENTS, skill.name, phrase))
            if skill.has_intents and routed != skill.name:
                found.add((CHECK_OWN, skill.name, phrase))
            if routed is not None and routed != skill.name:
                found.add((CHECK_SIBLING, skill.name, phrase))
    return found


def read_baseline(path: Path) -> set[Identity]:
    """Parse the baseline into identities, or raise ConfigError."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ConfigError(f"baseline {path} unreadable or not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"baseline {path} is not a JSON object")
    violations = payload.get("violations")
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(violations, dict):
        raise ConfigError(f"baseline {path} needs schema_version {SCHEMA_VERSION} and `violations`")
    if set(violations) != set(CHECKS):
        raise ConfigError(f"baseline {path} must hold exactly the checks {list(CHECKS)}")
    identities: set[Identity] = set()
    for check, by_skill in violations.items():
        if not isinstance(by_skill, dict):
            raise ConfigError(f"baseline {path} check {check} is not a mapping")
        for skill, phrases in by_skill.items():
            if not isinstance(phrases, list) or not all(isinstance(p, str) for p in phrases):
                raise ConfigError(f"baseline {path} {check}/{skill} is not a list of phrases")
            identities.update((check, skill, p) for p in phrases)
    return identities


def write_baseline(path: Path, identities: set[Identity]) -> None:
    """Write the baseline atomically, sorted so the file is byte-stable."""
    violations: dict[str, dict[str, list[str]]] = {check: {} for check in CHECKS}
    for check, skill, phrase in sorted(identities):
        violations[check].setdefault(skill, []).append(phrase)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "description": (
            "Skill description trigger phrases that do not route through autoplan as "
            "advertised, one entry per check, skill, and phrase. Every added entry needs "
            "reviewer approval in the PR. Regenerate with: uv run python "
            "scripts/validation/check_skill_trigger_resolution.py --write-baseline"
        ),
        "violations": violations,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _fmt(identity: Identity) -> str:
    check, skill, phrase = identity
    return f"{check}: {skill}: {phrase!r}"


def _report(
    new: list[Identity],
    stale: list[Identity],
    counts: tuple[int, int, int, int],
    paths: dict[str, Path | None],
) -> None:
    """Print findings, then one summary line that always names what was examined."""
    skills, phrases, found, base = counts
    for identity in new:
        where = paths.get(identity[1])
        suffix = f" ({where})" if where is not None else ""
        print(f"[FAIL] new violation: {_fmt(identity)}{suffix}")
    for identity in stale:
        print(f"[INFO] baseline entry no longer fires, remove it: {_fmt(identity)}")
    print(
        f"examined skills={skills} phrases={phrases} "
        f"violations={found} baseline={base} new={len(new)} stale={len(stale)}"
    )


def _count_phrases(skills: list[Skill]) -> int:
    return sum(len(extract_phrases(skill.description)) for skill in skills)


def _run(args: argparse.Namespace) -> int:
    if yaml is None:
        raise ConfigError("missing required module: yaml (PyYAML)")
    repo_root = Path(args.repo_root).resolve()
    skills_dir = Path(args.skills_dir) if args.skills_dir else repo_root / SKILLS_SUBDIR
    baseline_path = Path(args.baseline) if args.baseline else repo_root / BASELINE_RELATIVE
    skills = load_skills(skills_dir)
    phrase_count = _count_phrases(skills)
    if phrase_count == 0:
        raise ConfigError(
            f"examined {len(skills)} skills under {skills_dir} but found 0 trigger phrases; "
            "the check would examine nothing, so it cannot report success"
        )
    catalog = repo_root / CATALOG_SUBDIR
    found = find_violations(skills, catalog if catalog.is_dir() else skills_dir)
    if args.write_baseline:
        # ci-scripts MUST 7: a write into the resolved root needs cwd inside it.
        target = baseline_path.resolve()
        if target.is_relative_to(repo_root) and not Path.cwd().resolve().is_relative_to(repo_root):
            raise ConfigError(
                f"refusing to write {target}: current directory is outside {repo_root}"
            )
        write_baseline(baseline_path, found)
        by_check = {c: sum(1 for i in found if i[0] == c) for c in CHECKS}
        print(f"wrote {baseline_path}: {len(found)} entries {by_check}")
        return EXIT_OK
    baseline = read_baseline(baseline_path)
    new, stale = sorted(found - baseline), sorted(baseline - found)
    paths = {skill.name: skill.skill_md for skill in skills}
    _report(new, stale, (len(skills), phrase_count, len(found), len(baseline)), paths)
    return EXIT_VIOLATION if new else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--skills-dir", default=None, help="default: <repo-root>/.claude/skills")
    parser.add_argument("--baseline", default=None, help="default: the shipped baseline JSON")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except ConfigError as exc:
        print(f"[CONFIG] {exc}", file=sys.stderr)
        return EXIT_CONFIG


def validate_skill_trigger_resolution(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True when no violation falls outside the baseline.

    A config error (exit 2) returns False. A gate that cannot run has not
    passed, and reporting that as a pass is the silent-pass failure.
    """
    return main(["--repo-root", str(repo_root)]) == EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
