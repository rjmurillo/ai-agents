#!/usr/bin/env python3
"""Gate: every skill template declares one valid routing role.

REQ-038 requires each `templates/skills/<name>.SKILL.md.tmpl` to carry a
`metadata.routing` block naming who selects it and how:

    metadata:
      routing:
        role: nested-helper
        invoker: pr-quality-all
        trigger: pr-quality-all runs the security axis
        user-facing: true

DESIGN-036 is the contract this module implements. Six roles exist:
`front-door`, `lifecycle`, `conditional-adjunct`, `nested-helper`,
`explicit-only`, `deprecated`. Each role restricts which `invoker` is legal
(a canonical skill name, a canonical agent name, the reserved token `user`,
or the reserved token `harness`), and the gate refuses a role/invoker
contradiction, an unresolved required key, and a malformed `deprecated` or
`explicit-only` declaration.

Reachability ("does the named invoker's own text mention this skill?") and
"inbound-zero" (does *any* skill or agent text mention this skill at all?)
are evidence, not refusals: DESIGN-036 states a route is prose, and a
common-word skill name makes an exact-token match an upper bound rather than
proof. Both are reported under `--report`, never turned into an exit-1
finding.

Exit codes (ADR-035):
    0 - Success (every declaration is well-formed and role/invoker agree)
    1 - Logic error (a routing declaration is missing, malformed, or
        contradicts its role)
    2 - Config error (invalid repository root, `templates/skills` absent, or
        it holds no skill templates, which would make a PASS vacuous)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import yaml  # noqa: E402

# scripts/validation/instruction_budget_globs.py:11 and :27 (read 2026-09-24):
#     _FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
#     class _UniqueKeySafeLoader(yaml.SafeLoader): ...
# Reused for the same reason check_capability_graph.py reuses it: PyYAML
# keeps the last value when a top-level key repeats, and nothing guarantees a
# harness resolves the duplicate the same way, so a duplicate `metadata:` key
# must be a defect rather than a silent overwrite.
from instruction_budget_globs import (  # noqa: E402
    _FRONTMATTER_RE,
    UnsupportedApplyToError,
    _UniqueKeySafeLoader,
)

ROLES: tuple[str, ...] = (
    "front-door",
    "lifecycle",
    "conditional-adjunct",
    "nested-helper",
    "explicit-only",
    "deprecated",
)

# The six lifecycle skills. autoplan routes to them (they are themselves
# `front-door`); a skill *they* select is `lifecycle` (DESIGN-036).
LIFECYCLE_SKILLS: frozenset[str] = frozenset({"spec", "plan", "build", "test", "review", "ship"})

RESERVED_INVOKERS: frozenset[str] = frozenset({"user", "harness"})

ROUTING_KEYS: tuple[str, ...] = (
    "role",
    "invoker",
    "trigger",
    "user-facing",
    "scenario",
    "rationale",
    "replaced-by",
    "removal-issue",
)

_SCENARIO_PREFIX = "tests/evals/"


class TreeError(Exception):
    """The canonical skill tree cannot answer the question this gate asks."""


@dataclass(frozen=True)
class SkillDecl:
    """One skill's best-effort parsed routing declaration.

    Fields hold ``None`` when the corresponding block value is absent or the
    wrong type; the shape defect itself is recorded separately by
    :func:`_block_defects` so a malformed field is never silently
    indistinguishable from an absent one. ``scenario`` always holds a usable
    path: the declared override when valid, otherwise the REQ-038 default.
    """

    name: str
    path: str
    role: str | None
    invoker: str | None
    replaced_by: str | None
    scenario: str


@dataclass(frozen=True)
class Evidence:
    """The three reported (non-refusing) evidence layers, sorted by name."""

    unresolved: tuple[str, ...]
    inbound_zero: tuple[str, ...]
    scenario_covered: tuple[str, ...]
    checked: tuple[str, ...]


def _frontmatter(text: str) -> dict[str, object]:
    """Parse frontmatter, rejecting duplicate top-level keys."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}
    data = yaml.load(match.group(1), Loader=_UniqueKeySafeLoader)
    return data if isinstance(data, dict) else {}


def _is_positive_int(value: object) -> bool:
    """Return True for a positive int. ``bool`` is an ``int`` subclass; reject it."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_scenario_path(value: str) -> bool:
    """Return True when ``value`` is a relative path under ``tests/evals/``."""
    if not value.strip() or value.startswith("/"):
        return False
    if ".." in PurePosixPath(value).parts:
        return False
    return value.startswith(_SCENARIO_PREFIX)


def _routing_or_defect(
    rel: str, front: dict[str, object]
) -> tuple[dict[str, object] | None, str | None]:
    """Return the `metadata.routing` mapping, or the shape defect naming why not."""
    metadata = front.get("metadata")
    if not isinstance(metadata, dict) or "routing" not in metadata:
        return None, f"{rel}: has no `metadata.routing` block"
    routing = metadata["routing"]
    if not isinstance(routing, dict):
        return None, f"{rel}: `metadata.routing` is {type(routing).__name__}, not a mapping"
    return routing, None


def _key_shape_defects(rel: str, block: dict[str, object]) -> list[str]:
    """Return defects for an unknown key and for a missing or invalid role."""
    defects: list[str] = []
    unknown = sorted(key for key in block if key not in ROUTING_KEYS)
    if unknown:
        keys = ", ".join(f"`{key}`" for key in unknown)
        defects.append(f"{rel}: unknown routing key(s) {keys}")
    role = block.get("role")
    if role is None:
        defects.append(f"{rel}: missing required routing key: role")
    elif role not in ROLES:
        defects.append(f"{rel}: role `{role}` is not one of {', '.join(ROLES)}")
    return defects


def _required_key_defects(rel: str, block: dict[str, object], role: str) -> list[str]:
    """Return defects for the keys every non-deprecated role must carry."""
    if role == "deprecated":
        return []
    defects: list[str] = []
    missing = [key for key in ("invoker", "trigger", "user-facing") if key not in block]
    if missing:
        defects.append(f"{rel}: missing required routing key(s): {', '.join(missing)}")
    invoker = block.get("invoker")
    if "invoker" in block and not isinstance(invoker, str):
        defects.append(f"{rel}: invoker is {type(invoker).__name__}, not a string")
    trigger = block.get("trigger")
    if "trigger" in block and (not isinstance(trigger, str) or not trigger.strip()):
        defects.append(f"{rel}: trigger must be a non-empty string")
    user_facing = block.get("user-facing")
    if "user-facing" in block and not isinstance(user_facing, bool):
        defects.append(f"{rel}: user-facing is {type(user_facing).__name__}, not a boolean")
    return defects


def _explicit_only_defects(rel: str, block: dict[str, object], role: str) -> list[str]:
    """Return the defect for a missing or empty `rationale` on `explicit-only`."""
    if role != "explicit-only":
        return []
    rationale = block.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        return [f"{rel}: explicit-only role requires a non-empty `rationale`"]
    return []


def _deprecated_defects(rel: str, block: dict[str, object], role: str) -> list[str]:
    """Return the defect for a `deprecated` skill naming neither retirement key."""
    if role != "deprecated":
        return []
    replaced_by = block.get("replaced-by")
    removal_issue = block.get("removal-issue")
    has_replaced = isinstance(replaced_by, str) and bool(replaced_by.strip())
    has_removal = _is_positive_int(removal_issue)
    if has_replaced or has_removal:
        return []
    if removal_issue is not None:
        return [f"{rel}: `removal-issue` value {removal_issue!r} is not a positive integer"]
    return [
        f"{rel}: deprecated skill declares neither a resolvable `replaced-by` "
        "nor a positive `removal-issue`"
    ]


def _scenario_defect(rel: str, block: dict[str, object]) -> str | None:
    """Return the defect for a malformed `scenario` override, or None."""
    if "scenario" not in block:
        return None
    value = block["scenario"]
    if not isinstance(value, str) or not value.strip():
        return f"{rel}: scenario must be a non-empty string"
    if not _valid_scenario_path(value):
        return f"{rel}: scenario `{value}` must be a relative path under tests/evals/"
    return None


def _user_facing_defect(rel: str, front: dict[str, object], block: dict[str, object]) -> str | None:
    """Return the defect for `user-facing: true` on a non-user-invocable skill."""
    if block.get("user-facing") is not True:
        return None
    if front.get("user-invocable", True) is False:
        return f"{rel}: user-facing is true but frontmatter sets user-invocable: false"
    return None


def _block_defects(rel: str, front: dict[str, object], block: dict[str, object]) -> list[str]:
    """Return every shape defect in one skill's routing declaration."""
    defects = _key_shape_defects(rel, block)
    role = block.get("role")
    if role not in ROLES:
        return defects
    defects.extend(_required_key_defects(rel, block, role))
    defects.extend(_explicit_only_defects(rel, block, role))
    defects.extend(_deprecated_defects(rel, block, role))
    scenario_defect = _scenario_defect(rel, block)
    if scenario_defect:
        defects.append(scenario_defect)
    user_facing_defect = _user_facing_defect(rel, front, block)
    if user_facing_defect:
        defects.append(user_facing_defect)
    return defects


def _decl_from_block(name: str, rel: str, block: dict[str, object]) -> SkillDecl:
    """Build a best-effort declaration from a parsed (possibly invalid) block."""
    role = block.get("role")
    role = role if role in ROLES else None
    invoker = block.get("invoker")
    invoker = invoker if isinstance(invoker, str) else None
    replaced_by = block.get("replaced-by")
    replaced_by = replaced_by if isinstance(replaced_by, str) and replaced_by.strip() else None
    scenario_raw = block.get("scenario")
    scenario = (
        scenario_raw
        if isinstance(scenario_raw, str) and _valid_scenario_path(scenario_raw)
        else f"{_SCENARIO_PREFIX}skill-scenarios/{name}.json"
    )
    return SkillDecl(
        name=name, path=rel, role=role, invoker=invoker, replaced_by=replaced_by, scenario=scenario
    )


def _skill_template_map(repo_root: Path) -> dict[str, Path]:
    """Map every canonical skill name to its template path."""
    tree = repo_root / "templates" / "skills"
    return {
        path.name.removesuffix(".SKILL.md.tmpl"): path
        for path in sorted(tree.glob("*.SKILL.md.tmpl"))
    }


def _agent_template_map(repo_root: Path) -> dict[str, Path]:
    """Map every canonical agent name to its shared-body path.

    Absent when `templates/agents` does not exist. Unlike `templates/skills`,
    a missing agents tree is not a config error here: the failure mode this
    gate exists for (REQ-038) is an uncategorized *skill*, and a skill whose
    invoker names a nonexistent agent still fails cleanly as an unknown
    invoker.
    """
    tree = repo_root / "templates" / "agents"
    if not tree.is_dir():
        return {}
    return {path.name.removesuffix(".shared.md"): path for path in sorted(tree.glob("*.shared.md"))}


def collect_skills(repo_root: Path) -> tuple[list[SkillDecl], list[str]]:
    """Return every skill's declaration, plus every shape defect found.

    A frontmatter parse failure is a defect, never a silently absent
    declaration: dropping the skill from the list would hide a real problem
    behind a clean run.
    """
    tree = repo_root / "templates" / "skills"
    if not tree.is_dir():
        raise TreeError("templates/skills is not a directory")
    files = sorted(tree.glob("*.SKILL.md.tmpl"))
    if not files:
        raise TreeError("templates/skills holds no *.SKILL.md.tmpl files")
    skills: list[SkillDecl] = []
    defects: list[str] = []
    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        name = path.name.removesuffix(".SKILL.md.tmpl")
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            front = _frontmatter(text)
        except (UnsupportedApplyToError, yaml.YAMLError) as exc:
            defects.append(f"{rel}: frontmatter cannot be parsed: {exc}")
            continue
        block, shape_defect = _routing_or_defect(rel, front)
        if shape_defect:
            defects.append(shape_defect)
            skills.append(
                SkillDecl(
                    name=name,
                    path=rel,
                    role=None,
                    invoker=None,
                    replaced_by=None,
                    scenario=f"{_SCENARIO_PREFIX}skill-scenarios/{name}.json",
                )
            )
            continue
        assert block is not None  # narrowed by _routing_or_defect's contract
        defects.extend(_block_defects(rel, front, block))
        skills.append(_decl_from_block(name, rel, block))
    return skills, defects


def _role_invoker_contradiction(role: str, invoker: str, name: str) -> str | None:
    """Return the DESIGN-036 role/invoker contradiction, or None when legal."""
    if role == "front-door" and invoker not in ("autoplan", "harness"):
        return f"role `front-door` must be invoked by `autoplan` or `harness`, not `{invoker}`"
    if role == "lifecycle" and invoker not in LIFECYCLE_SKILLS:
        lifecycle = ", ".join(sorted(LIFECYCLE_SKILLS))
        return f"role `lifecycle` must be invoked by one of {lifecycle}, not `{invoker}`"
    if role in ("conditional-adjunct", "nested-helper") and (
        invoker in RESERVED_INVOKERS or invoker == name
    ):
        return (
            f"role `{role}` must not be invoked by `user`, `harness`, "
            f"or itself (got `{invoker}`)"
        )
    if role == "explicit-only" and invoker != "user":
        return f"role `explicit-only` must be invoked by `user`, not `{invoker}`"
    return None


def _invoker_legality_defect(
    skill: SkillDecl, skill_names: frozenset[str], agent_names: frozenset[str]
) -> str | None:
    """Return the defect for an invoker that names no canonical target."""
    invoker = skill.invoker
    if invoker in skill_names or invoker in agent_names or invoker in RESERVED_INVOKERS:
        return None
    return (
        f"{skill.path}: invoker `{invoker}` is not a canonical skill, "
        "agent, `user`, or `harness`"
    )


def _replaced_by_resolution_defect(
    skill: SkillDecl, skill_names: frozenset[str], roles_by_name: dict[str, str | None]
) -> list[str]:
    """Return the defect for a `replaced-by` naming an unknown or deprecated skill."""
    target = skill.replaced_by
    if target not in skill_names:
        return [f"{skill.path}: replaced-by `{target}` names no known skill"]
    if roles_by_name.get(target) == "deprecated":
        return [f"{skill.path}: replaced-by `{target}` names a deprecated skill"]
    return []


def check_routing_graph(
    skills: list[SkillDecl], skill_names: frozenset[str], agent_names: frozenset[str]
) -> list[str]:
    """Return one finding per role/invoker contradiction or bad reference."""
    findings: list[str] = []
    roles_by_name = {skill.name: skill.role for skill in skills}
    for skill in skills:
        if skill.role == "deprecated":
            if skill.replaced_by:
                findings.extend(_replaced_by_resolution_defect(skill, skill_names, roles_by_name))
            continue
        if skill.role is None or skill.invoker is None:
            continue
        legality = _invoker_legality_defect(skill, skill_names, agent_names)
        if legality:
            findings.append(legality)
            continue
        contradiction = _role_invoker_contradiction(skill.role, skill.invoker, skill.name)
        if contradiction:
            findings.append(f"{skill.path}: {contradiction}")
    return sorted(findings)


_REACHABLE_ROLES = frozenset({"front-door", "lifecycle", "conditional-adjunct", "nested-helper"})


_ROUTING_BLOCK = re.compile(r"^  routing:\n(?:    .*\n|\n)*", re.MULTILINE)


def _names_token(name: str, text: str) -> bool:
    """Return True when `name` appears in `text` as an exact token."""
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def _strip_routing_block(text: str) -> str:
    """Drop the `metadata.routing` block so a declaration cannot certify itself.

    Without this, one skill's `invoker:` or `rationale:` naming another skill
    counts as an inbound reference, and the manifest would prove its own
    reachability. Only authored body and non-routing frontmatter count.
    """
    return _ROUTING_BLOCK.sub("", text, count=1)


def _skill_own_text(repo_root: Path, skill_path: Path, name: str) -> str:
    """Return a skill's canonical text: its template plus its reference files.

    DESIGN-036: "Canonical text is the invoker's template plus the Markdown
    files under `.claude/skills/<invoker>/` other than `SKILL.md`". The
    shipped `SKILL.md` there is a generated projection of the same template
    this function already reads, not a second authored source.
    """
    parts = [_strip_routing_block(skill_path.read_text(encoding="utf-8", errors="replace"))]
    ref_root = repo_root / ".claude" / "skills" / name
    if ref_root.is_dir():
        for md in sorted(ref_root.rglob("*.md")):
            if md.name != "SKILL.md":
                parts.append(md.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _canonical_texts(
    repo_root: Path, skill_templates: dict[str, Path], agent_templates: dict[str, Path]
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (skill name -> canonical text, agent name -> canonical text)."""
    skill_text = {
        name: _skill_own_text(repo_root, path, name) for name, path in skill_templates.items()
    }
    agent_text = {
        name: path.read_text(encoding="utf-8", errors="replace")
        for name, path in agent_templates.items()
    }
    return skill_text, agent_text


def _invoker_text(invoker: str, skill_text: dict[str, str], agent_text: dict[str, str]) -> str:
    """Return the canonical text attributed to one invoker name.

    A name can name both a skill and an agent (four names collide in this
    catalog: merge-resolver, negotiation, pr-comment-responder,
    retrospective). DESIGN-036 does not resolve that collision, so this gate
    treats it permissively: the union of both texts is searched, which can
    only make a name *more* likely to resolve, never less. A stricter
    resolution (skill text only, or agent text only) risked marking a real
    route unresolved on the ambiguous names.
    """
    parts = []
    if invoker in skill_text:
        parts.append(skill_text[invoker])
    if invoker in agent_text:
        parts.append(agent_text[invoker])
    return "\n".join(parts)


def _unresolved_skills(
    skills: list[SkillDecl], skill_text: dict[str, str], agent_text: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Return (checked names, unresolved names) for the four reachable roles."""
    checked: list[str] = []
    unresolved: list[str] = []
    for skill in skills:
        if skill.role not in _REACHABLE_ROLES or skill.invoker is None:
            continue
        checked.append(skill.name)
        if skill.invoker in RESERVED_INVOKERS:
            continue  # reachable by declaration (DESIGN-036)
        text = _invoker_text(skill.invoker, skill_text, agent_text)
        if not _names_token(skill.name, text):
            unresolved.append(skill.name)
    return checked, unresolved


def _inbound_zero_skills(
    skills: list[SkillDecl], skill_text: dict[str, str], agent_text: dict[str, str]
) -> list[str]:
    """Return names no other skill or agent's canonical text mentions at all."""
    inbound_zero: list[str] = []
    for skill in skills:
        corpus = "\n".join(
            text for other, text in skill_text.items() if other != skill.name
        )
        corpus = "\n".join([corpus, *agent_text.values()])
        if not _names_token(skill.name, corpus):
            inbound_zero.append(skill.name)
    return inbound_zero


def compute_evidence(
    repo_root: Path,
    skills: list[SkillDecl],
    skill_templates: dict[str, Path],
    agent_templates: dict[str, Path],
) -> Evidence:
    """Return the three reported evidence layers, sorted for determinism."""
    skill_text, agent_text = _canonical_texts(repo_root, skill_templates, agent_templates)
    checked, unresolved = _unresolved_skills(skills, skill_text, agent_text)
    inbound_zero = _inbound_zero_skills(skills, skill_text, agent_text)
    scenario_covered = [skill.name for skill in skills if (repo_root / skill.scenario).is_file()]
    return Evidence(
        unresolved=tuple(sorted(unresolved)),
        inbound_zero=tuple(sorted(inbound_zero)),
        scenario_covered=tuple(sorted(scenario_covered)),
        checked=tuple(sorted(checked)),
    )


def survey(repo_root: Path) -> tuple[list[SkillDecl], list[str], Evidence]:
    """Read the tree once and return every declaration, finding, and evidence layer."""
    skills, defects = collect_skills(repo_root)
    skill_templates = _skill_template_map(repo_root)
    agent_templates = _agent_template_map(repo_root)
    graph_findings = check_routing_graph(
        skills, frozenset(skill_templates), frozenset(agent_templates)
    )
    evidence = compute_evidence(repo_root, skills, skill_templates, agent_templates)
    return skills, sorted(defects) + graph_findings, evidence


def render(skills: list[SkillDecl], evidence: Evidence, fmt: str) -> str:
    """Emit the deterministic report. Two runs on one tree are byte-identical."""
    total = len(skills)
    by_role = {role: sum(1 for skill in skills if skill.role == role) for role in ROLES}
    classified = sum(by_role.values())
    checked = len(evidence.checked)
    reachable = checked - len(evidence.unresolved)
    if fmt == "json":
        return _render_json(skills, evidence, total, by_role, classified, reachable, checked)
    lines = [f"skills: {total}", f"classified: {classified}/{total}"]
    lines.extend(f"role {role}: {count}" for role, count in sorted(by_role.items()))
    lines.append(f"structurally reachable: {reachable}/{checked}")
    lines.append(f"unresolved: {len(evidence.unresolved)}")
    lines.extend(f"unresolved {name}" for name in evidence.unresolved)
    lines.append(f"scenario coverage: {len(evidence.scenario_covered)}/{total}")
    lines.append(f"inbound-zero: {len(evidence.inbound_zero)}")
    lines.extend(f"inbound-zero {name}" for name in evidence.inbound_zero)
    lines.append("scored accuracy: not measured")
    return "\n".join(lines)


def _render_json(
    skills: list[SkillDecl],
    evidence: Evidence,
    total: int,
    by_role: dict[str, int],
    classified: int,
    reachable: int,
    checked: int,
) -> str:
    """Render the JSON report shape (issue #5389 reads this)."""
    payload = {
        "skills": [
            {"name": skill.name, "path": skill.path, "role": skill.role, "invoker": skill.invoker}
            for skill in skills
        ],
        "counts": {
            "total": total,
            "by_role": by_role,
            "classified": classified,
            "structurally_reachable": reachable,
            "structurally_checked": checked,
            "scenario_covered": len(evidence.scenario_covered),
        },
        "unresolved": list(evidence.unresolved),
        "inbound_zero": list(evidence.inbound_zero),
        "scored_accuracy": "not measured",
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _report_findings(findings: list[str]) -> None:
    """Print findings to stderr in the gate's usual shape."""
    print(f"[FAIL] {len(findings)} skill routing violation(s):", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print(
        "\nFix: declare `metadata.routing` in the skill template with a valid "
        "role and invoker. Contract: "
        ".project-toolkit/specs/design/DESIGN-036-skill-routing-roles.md",
        file=sys.stderr,
    )


def validate_skill_routing_roles(repo_root: Path) -> bool:
    """Return True when every skill declares a valid, non-contradictory route.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract that
    ``pre_pr_sequence.py`` expects.
    """
    _skills, findings, _evidence = survey(repo_root)
    if not findings:
        return True
    _report_findings(findings)
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", dest="repo_root", default=None)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    )
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        skills, findings, evidence = survey(repo_root)
    except TreeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    if args.report:
        print(render(skills, evidence, args.format))
    if findings:
        _report_findings(findings)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
