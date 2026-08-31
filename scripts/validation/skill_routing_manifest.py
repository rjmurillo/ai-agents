#!/usr/bin/env python3
"""Validate the canonical skill routing role manifest (issue #5384).

What this is
------------

`.config/skill-routing-manifest.yaml` assigns every canonical skill under
`.claude/skills/<name>/` exactly one PRIMARY routing role. This module is the
generator-plus-validator the issue asks for: the reviewed roles live in that one
config file, and everything else (the canonical skill list, the invocation graph
that measures structural reachability, the derived `user_facing` flag, and the
expected activation-scenario path) is computed here from the canonical tree.
There is no duplicate catalog in any mirror.

The validator fails (exit 1) when:

- a canonical skill has no manifest entry (a new skill added without a role),
- a manifest entry names no canonical skill (a stale entry),
- an entry's role is not one of the six valid roles,
- an entry's owner/invoker is unknown (not a command, skill, agent, or "user"),
- an entry's owner contradicts its role (e.g. front-door not owned by /autoplan),
- a conditional-adjunct entry has no trigger,
- an explicit-only entry has no rationale,
- a deprecated entry has no replacement reference.

Config errors (manifest missing, unparseable, or wrong shape; the `.claude`
tree missing) exit 2, per ADR-035.

Three measurements the report keeps separate
--------------------------------------------

The issue requires the report to distinguish three different things a skill can
lack. They are not the same and a skill can pass one while failing another:

1. **Structural reachability** -- is there any invocation route that reaches the
   skill? Measured here from the `.claude` prompt bodies (the `Skill(skill=...)`,
   `Skill: <name>`, and `Agent: <name>` invocation forms). A skill with zero
   inbound routes is reported as "inbound-zero". This never fails validation:
   several skills are classified with an INTENDED invoker that dependent issues
   (#5385-#5388) have not wired yet, so their inbound count is legitimately zero
   today and the report surfaces the gap rather than blocking on it.
2. **Activation-scenario coverage** -- does an activation-scenario fixture exist
   at `tests/evals/skill-scenarios/<name>.json`? That is what
   `scripts/validation/check_rule_activation_coverage.py` ratchets. Reported
   here as a count; not enforced by this validator.
3. **Scored routing accuracy** -- would a description-matching router actually
   pick the skill for its own request? That is a live-API measurement produced
   by `scripts/eval/eval_skill_router.py`. This validator does not compute it and
   says so, so the report is never mistaken for an accuracy score.

Relation to existing validators (paths cited, level-1 reads this session)
-------------------------------------------------------------------------

- `scripts/validation/check_shipped_skill_routes.py` answers a DIFFERENT
  question: for every plugin root, each `Skill: <name>` route in that root's
  markdown must resolve to `<root>/skills/<name>/SKILL.md`. That is a packaging
  reachability check across shipped roots; this module classifies routing roles
  in the canonical tree. No parity is claimed between them.
- `scripts/eval/eval_skill_router.py` is the scored-routing-accuracy eval named
  in measurement (3) above.

Invocation detection here is intentionally narrower than the CommonMark table
parser in `check_shipped_skill_routes.py`: it matches the three literal
invocation forms above with regexes and does not parse markdown tables. That is
sufficient for a reachability signal and keeps this gate dependency-free.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

# ADR-035 exit codes.
EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_CONFIG = 2

MANIFEST_RELPATH = Path(".config") / "skill-routing-manifest.yaml"
SKILLS_SUBDIR = Path(".claude") / "skills"
AGENTS_SUBDIR = Path(".claude") / "agents"
COMMANDS_SUBDIR = Path(".claude") / "commands"
SCENARIOS_SUBDIR = Path("tests") / "evals" / "skill-scenarios"

# Agent markdown files that are not agents (they are directory-level docs).
_NON_AGENT_STEMS = frozenset({"AGENTS", "CLAUDE"})

ROLES: tuple[str, ...] = (
    "front-door",
    "lifecycle",
    "conditional-adjunct",
    "nested-helper",
    "explicit-only",
    "deprecated",
)

LIFECYCLE_COMMANDS: frozenset[str] = frozenset(
    {"/spec", "/plan", "/build", "/test", "/ship", "/review"}
)

# Slash commands that route requests but have no file under `.claude/commands`
# because they are served by a skill of the same name: `/autoplan` is the
# autoplan skill, `/review` is the review skill. Added to the valid-invoker set
# so a manifest owner can name them.
_SKILL_BACKED_COMMANDS: frozenset[str] = frozenset({"/autoplan", "/review"})

# Whether a route in each role is directly user-facing. Derived from the role,
# recorded in the resolved manifest the report emits.
ROLE_USER_FACING: dict[str, bool] = {
    "front-door": True,
    "lifecycle": True,
    "conditional-adjunct": False,
    "nested-helper": False,
    "explicit-only": True,
    "deprecated": False,
}

# Invocation forms recognized as a structural route to a skill.
_CALL_RE = re.compile(r"""Skill\(skill=["']([a-z0-9][a-z0-9-]*)["']\)""")
_ROUTE_RE = re.compile(r"(?:Skill|Agent):\s*`?([a-z0-9][a-z0-9-]*)`?")


class ManifestError(Exception):
    """Raised for a config-level fault (missing, unparseable, wrong shape)."""


@dataclass(frozen=True)
class Finding:
    """One validation failure. ``code`` is a stable machine tag."""

    code: str
    skill: str
    message: str

    def render(self) -> str:
        return f"[{self.code}] {self.skill}: {self.message}"


# ---------------------------------------------------------------------------
# Discovery from the canonical tree
# ---------------------------------------------------------------------------


def discover_canonical_skills(repo_root: Path) -> set[str]:
    """Return the set of canonical skill names (dirs holding a SKILL.md)."""
    skills_dir = repo_root / SKILLS_SUBDIR
    if not skills_dir.is_dir():
        raise ManifestError(f"canonical skills directory not found: {skills_dir}")
    return {
        child.name
        for child in skills_dir.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    }


def discover_agents(repo_root: Path) -> set[str]:
    """Return the set of agent names under ``.claude/agents``."""
    agents_dir = repo_root / AGENTS_SUBDIR
    if not agents_dir.is_dir():
        return set()
    return {
        path.stem
        for path in agents_dir.glob("*.md")
        if path.stem not in _NON_AGENT_STEMS
    }


def discover_commands(repo_root: Path) -> set[str]:
    """Return slash-command tokens (``/build``, ``/spec``, ...) that have a file."""
    commands_dir = repo_root / COMMANDS_SUBDIR
    if not commands_dir.is_dir():
        return set()
    return {
        f"/{path.stem}"
        for path in commands_dir.glob("*.md")
        if path.stem not in _NON_AGENT_STEMS
    }


def _prompt_sources(repo_root: Path, skills: set[str]) -> dict[str, str]:
    """Map a source id to its concatenated prompt text.

    Sources are the lifecycle/command prompts, each skill body, and each agent
    body. The id records the origin so a skill's own body never counts as an
    inbound route to itself.
    """
    sources: dict[str, str] = {}
    for path in sorted((repo_root / COMMANDS_SUBDIR).glob("*.md")):
        sources[f"cmd:/{path.stem}"] = path.read_text(encoding="utf-8")
    for name in sorted(skills):
        body = "".join(
            f.read_text(encoding="utf-8")
            for f in sorted((repo_root / SKILLS_SUBDIR / name).rglob("*.md"))
        )
        sources[f"skill:{name}"] = body
    for path in sorted((repo_root / AGENTS_SUBDIR).glob("*.md")):
        sources[f"agent:{path.stem}"] = path.read_text(encoding="utf-8")
    return sources


def compute_inbound(repo_root: Path, skills: set[str]) -> dict[str, set[str]]:
    """Return, per skill, the set of source ids that route to it (structural).

    A route is any ``Skill(skill="X")``, ``Skill: X``, or ``Agent: X`` naming a
    canonical skill in a source that is not that skill's own body.
    """
    inbound: dict[str, set[str]] = {name: set() for name in skills}
    for source_id, text in _prompt_sources(repo_root, skills).items():
        self_name = source_id.split(":", 1)[1].lstrip("/")
        found = {m.group(1) for m in _CALL_RE.finditer(text)}
        found |= {m.group(1) for m in _ROUTE_RE.finditer(text)}
        for name in found & skills:
            if name != self_name:
                inbound[name].add(source_id)
    return inbound


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> dict[str, dict]:
    """Parse the manifest and return its ``skills`` mapping.

    Raises ``ManifestError`` on any config-level fault.
    """
    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest is not valid YAML: {exc}") from exc
    if not isinstance(data, dict) or "skills" not in data:
        raise ManifestError("manifest must be a mapping with a top-level 'skills' key")
    skills = data["skills"]
    if not isinstance(skills, dict):
        raise ManifestError("manifest 'skills' must be a mapping of name -> entry")
    return skills


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _check_owner(name: str, role: str, owner: str, valid_invokers: set[str],
                 skills: set[str], agents: set[str]) -> list[Finding]:
    """Owner must be known and must not contradict the role."""
    if owner not in valid_invokers:
        return [Finding("UNKNOWN_INVOKER", name,
                        f"owner {owner!r} is not a known command, skill, agent, or 'user'")]
    contradiction = _owner_role_contradiction(role, owner, skills, agents)
    if contradiction:
        return [Finding("CONTRADICTORY_ROLE", name, contradiction)]
    return []


def _owner_role_contradiction(role: str, owner: str, skills: set[str],
                              agents: set[str]) -> str:
    """Return a message when ``owner`` cannot pair with ``role``, else ''."""
    if role == "front-door" and owner != "/autoplan":
        return f"front-door must be owned by /autoplan, not {owner!r}"
    if role == "lifecycle" and owner not in LIFECYCLE_COMMANDS:
        return (f"lifecycle must be owned by a lifecycle command "
                f"{sorted(LIFECYCLE_COMMANDS)}, not {owner!r}")
    if role == "explicit-only" and owner != "user":
        return f"explicit-only must be owned by 'user', not {owner!r}"
    if role == "conditional-adjunct" and owner == "user":
        return "conditional-adjunct is composed into a route, so owner must not be 'user'"
    if role == "nested-helper" and owner not in (skills | agents):
        return f"nested-helper must be owned by a skill or agent, not {owner!r}"
    return ""


def _check_role_fields(name: str, role: str, entry: dict) -> list[Finding]:
    """Situational required fields per role."""
    findings: list[Finding] = []
    if role == "conditional-adjunct" and not str(entry.get("trigger", "")).strip():
        findings.append(Finding("MISSING_TRIGGER", name,
                                "conditional-adjunct requires a non-empty 'trigger'"))
    if role == "explicit-only" and not str(entry.get("rationale", "")).strip():
        findings.append(Finding("MISSING_RATIONALE", name,
                                "explicit-only requires a non-empty 'rationale'"))
    if role == "deprecated" and not str(entry.get("replacement", "")).strip():
        findings.append(Finding("MISSING_REPLACEMENT", name,
                                "deprecated requires a non-empty 'replacement' reference"))
    return findings


def _validate_entry(name: str, entry: object, valid_invokers: set[str],
                    skills: set[str], agents: set[str]) -> list[Finding]:
    if not isinstance(entry, dict):
        return [Finding("MALFORMED_ENTRY", name, "entry is not a mapping")]
    role = entry.get("role")
    if role not in ROLES:
        return [Finding("INVALID_ROLE", name,
                        f"role {role!r} is not one of {list(ROLES)}")]
    findings: list[Finding] = []
    owner = entry.get("owner")
    if not owner or not isinstance(owner, str):
        findings.append(Finding("MISSING_OWNER", name, "entry requires a string 'owner'"))
    else:
        findings.extend(_check_owner(name, role, owner, valid_invokers, skills, agents))
    findings.extend(_check_role_fields(name, role, entry))
    return findings


def validate(manifest: dict[str, dict], canonical_skills: set[str],
             agents: set[str], commands: set[str]) -> list[Finding]:
    """Return every validation finding (empty means the manifest is valid)."""
    valid_invokers = (
        set(commands)
        | LIFECYCLE_COMMANDS
        | _SKILL_BACKED_COMMANDS
        | canonical_skills
        | agents
        | {"user"}
    )
    findings: list[Finding] = []
    manifest_names = set(manifest)
    for skill in sorted(canonical_skills - manifest_names):
        findings.append(Finding("UNCLASSIFIED", skill,
                                "canonical skill has no manifest entry"))
    for skill in sorted(manifest_names - canonical_skills):
        findings.append(Finding("UNKNOWN_SKILL", skill,
                                "manifest entry names no canonical skill"))
    for name in sorted(manifest_names & canonical_skills):
        findings.extend(_validate_entry(name, manifest[name], valid_invokers,
                                        canonical_skills, agents))
    return findings


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _scenario_present(repo_root: Path, name: str) -> bool:
    return (repo_root / SCENARIOS_SUBDIR / f"{name}.json").is_file()


def build_report(repo_root: Path, manifest: dict[str, dict],
                 canonical_skills: set[str], inbound: dict[str, set[str]]) -> str:
    """Deterministic report: role totals, inbound-zero, scenario coverage."""
    lines: list[str] = ["=== Skill Routing Manifest Report ==="]
    classified = sorted(set(manifest) & canonical_skills)
    lines.append(f"Canonical skills: {len(canonical_skills)}")
    lines.append(f"Classified:       {len(classified)}")

    role_of = {name: manifest[name].get("role") for name in classified}
    counts = Counter(role_of.values())
    lines.append("")
    lines.append("Role totals:")
    for role in ROLES:
        lines.append(f"  {role:<20} {counts.get(role, 0)}")

    inbound_zero = sorted(name for name in classified if not inbound.get(name))
    reachable = len(classified) - len(inbound_zero)
    lines.append("")
    lines.append("Structural reachability (invocation graph over .claude prompts):")
    lines.append(f"  reachable (>=1 inbound route): {reachable}")
    lines.append(f"  inbound-zero:                  {len(inbound_zero)}")
    for name in inbound_zero:
        entry = manifest[name]
        lines.append(f"    {name} ({entry.get('role')}, owner {entry.get('owner')})")

    present = sorted(name for name in classified if _scenario_present(repo_root, name))
    lines.append("")
    lines.append("Activation-scenario coverage (tests/evals/skill-scenarios/<name>.json):")
    lines.append(f"  present: {len(present)}")
    lines.append(f"  missing: {len(classified) - len(present)}")

    lines.append("")
    lines.append("Scored routing accuracy: not computed here; measured by")
    lines.append("  scripts/eval/eval_skill_router.py (live-API eval). This report covers")
    lines.append("  structural reachability and activation-scenario coverage only.")
    return "\n".join(lines)


def resolve_manifest(repo_root: Path, manifest: dict[str, dict],
                     inbound: dict[str, set[str]]) -> dict[str, dict]:
    """Materialize the full machine-readable manifest (reviewed + derived).

    Each resolved entry carries the reviewed role/owner/trigger/rationale plus
    the derived ``user_facing`` flag, the expected activation-scenario path and
    whether it exists, and the structural inbound count and sources.
    """
    resolved: dict[str, dict] = {}
    for name in sorted(manifest):
        entry = dict(manifest[name])
        role = entry.get("role")
        scenario = SCENARIOS_SUBDIR / f"{name}.json"
        resolved[name] = {
            **entry,
            "user_facing": ROLE_USER_FACING.get(role, False),
            "activation_scenario": scenario.as_posix(),
            "activation_scenario_present": (repo_root / scenario).is_file(),
            "inbound_count": len(inbound.get(name, set())),
            "inbound_sources": sorted(inbound.get(name, set())),
        }
    return resolved


# ---------------------------------------------------------------------------
# Wiring entry point + CLI
# ---------------------------------------------------------------------------


def validate_skill_routing_manifest(repo_root: Path) -> bool:
    """pre-PR gate entry: print the report and return True when valid.

    Returns False on any validation finding or config fault so the pre-PR
    runner records a FAIL.
    """
    try:
        manifest = load_manifest(repo_root / MANIFEST_RELPATH)
        skills = discover_canonical_skills(repo_root)
    except ManifestError as exc:
        print(f"[FAIL] skill routing manifest: {exc}", file=sys.stderr)
        return False
    agents = discover_agents(repo_root)
    commands = discover_commands(repo_root)
    inbound = compute_inbound(repo_root, skills)
    print(build_report(repo_root, manifest, skills, inbound))
    findings = validate(manifest, skills, agents, commands)
    for finding in findings:
        print(finding.render(), file=sys.stderr)
    return not findings


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST_RELPATH).is_file():
            return candidate
    return start


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to the tree containing the manifest).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="text prints the report; json emits the resolved manifest.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root or _find_repo_root(Path(__file__).resolve().parent)
    try:
        manifest = load_manifest(repo_root / MANIFEST_RELPATH)
        skills = discover_canonical_skills(repo_root)
    except ManifestError as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return EXIT_CONFIG
    agents = discover_agents(repo_root)
    commands = discover_commands(repo_root)
    inbound = compute_inbound(repo_root, skills)
    findings = validate(manifest, skills, agents, commands)

    if args.format == "json":
        import json

        print(json.dumps(resolve_manifest(repo_root, manifest, inbound),
                         indent=2, sort_keys=True))
    else:
        print(build_report(repo_root, manifest, skills, inbound))

    if findings:
        print("", file=sys.stderr)
        print(f"FAIL: {len(findings)} manifest finding(s):", file=sys.stderr)
        for finding in findings:
            print(f"  {finding.render()}", file=sys.stderr)
        return EXIT_VALIDATION
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
