"""Evidence layers for the skill routing-role gate (DESIGN-036).

Reachability ("does the named invoker's own text mention this skill?"),
inbound-zero ("does any skill or agent text mention it?"), and scenario
coverage are reported, never refused: a route is prose, and a common-word
skill name makes an exact-token match an upper bound rather than proof.
Scored routing accuracy is not measured here; issue #5389 owns it.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import yaml  # noqa: E402
from skill_routing_model import RESERVED_INVOKERS, ROLES, SkillDecl  # noqa: E402


@dataclass(frozen=True)
class Evidence:
    """The three reported (non-refusing) evidence layers, sorted by name."""

    unresolved: tuple[str, ...]
    inbound_zero: tuple[str, ...]
    scenario_covered: tuple[str, ...]
    checked: tuple[str, ...]


_REACHABLE_ROLES = frozenset({"front-door", "lifecycle", "conditional-adjunct", "nested-helper"})


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _names_token(name: str, text: str) -> bool:
    """Return True when `name` appears in `text` as an exact token."""
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def _strip_routing_block(text: str) -> str:
    """Drop the `metadata.routing` block so a declaration cannot certify itself.

    Without this, one skill's `invoker:` or `rationale:` naming another skill
    counts as an inbound reference, and the manifest would prove its own
    reachability. The frontmatter is parsed, not pattern-matched, so any
    indentation or an inline `routing: {...}` mapping is removed alike. A
    frontmatter that does not parse is returned unchanged; the gate already
    reports it as a defect.
    """
    match = _FRONTMATTER.match(text)
    if match is None:
        return text
    try:
        front = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return text
    if not isinstance(front, dict):
        return text
    metadata = front.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("routing", None)
    remaining: str = yaml.safe_dump(front, sort_keys=True)
    return remaining + text[match.end() :]


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
