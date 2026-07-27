#!/usr/bin/env python3
"""Validate SKIP clauses for multi-member skill families.

Exit codes follow ADR-035:
  0 - every multi-member family member routes to a real sibling
  1 - one or more SKIP-clause violations found
  2 - configuration error
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import yaml

_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_SKIP_CLAUSE_PATTERN = re.compile(
    r"Do NOT use\b.*?(?:\.(?=\s+[A-Z]|$)|$)",
    re.DOTALL,
)
_PAREN_USE_PATTERN = re.compile(r"\(use\s+([^)]*)\)", re.IGNORECASE)
_USE_INSTEAD_PATTERN = re.compile(
    r"\buse\s+`?([A-Za-z0-9][A-Za-z0-9-]*)`?\s+instead\b",
    re.IGNORECASE,
)
_SEMICOLON_USE_PATTERN = re.compile(
    r";\s*use\s+`?([A-Za-z0-9][A-Za-z0-9-]*)`?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path
    description: str
    frontmatter_error: str | None = None


@dataclass(frozen=True)
class Violation:
    code: str
    family: str
    skill: str
    message: str


def leading_token(skill_name: str) -> str:
    """Return the enforceable family token for a skill name."""
    return skill_name.split("-", 1)[0]


def parse_skill_file(path: Path) -> Skill:
    """Parse a SKILL.md file without raising on malformed frontmatter."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        return Skill(path.parent.name, path, "", "missing YAML frontmatter")

    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return Skill(path.parent.name, path, "", f"invalid YAML frontmatter: {exc}")

    if not isinstance(data, dict):
        return Skill(path.parent.name, path, "", "frontmatter is not a mapping")

    description = data.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        return Skill(path.parent.name, path, "", "description is not a string")

    return Skill(path.parent.name, path, description)


def load_skills(skills_dir: Path) -> list[Skill]:
    """Load all skill frontmatter records from a skills directory."""
    if not skills_dir.exists():
        return []
    if not skills_dir.is_dir():
        raise NotADirectoryError(f"skills path is not a directory: {skills_dir}")

    return [
        parse_skill_file(path)
        for path in sorted(skills_dir.glob("*/SKILL.md"))
        if path.is_file()
    ]


def group_families(skills: list[Skill]) -> dict[str, list[Skill]]:
    """Group skills by leading-token family, keeping only multi-member families."""
    grouped: dict[str, list[Skill]] = defaultdict(list)
    for skill in skills:
        grouped[leading_token(skill.name)].append(skill)
    return {
        family: sorted(members, key=lambda skill: skill.name)
        for family, members in grouped.items()
        if len(members) > 1
    }


def _skill_name_pattern(skill_name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![A-Za-z0-9-])`?{re.escape(skill_name)}`?(?![A-Za-z0-9-])"
    )


def _targets_in_text(text: str, known_skill_names: set[str]) -> set[str]:
    targets: set[str] = set()
    for skill_name in known_skill_names:
        if _skill_name_pattern(skill_name).search(text):
            targets.add(skill_name)
    return targets


def extract_skip_targets(description: str, known_skill_names: set[str]) -> set[str]:
    """Extract route targets from validator-recognized SKIP clause forms."""
    targets: set[str] = set()
    for clause in _SKIP_CLAUSE_PATTERN.findall(description):
        for parenthetical in _PAREN_USE_PATTERN.findall(clause):
            targets.update(_targets_in_text(parenthetical, known_skill_names))
        for match in _USE_INSTEAD_PATTERN.finditer(clause):
            target = match.group(1)
            if target in known_skill_names:
                targets.add(target)
        for match in _SEMICOLON_USE_PATTERN.finditer(clause):
            target = match.group(1)
            if target in known_skill_names:
                targets.add(target)
    return targets


def _connected_members(members: list[Skill], edges: set[tuple[str, str]]) -> set[str]:
    if not members:
        return set()

    adjacency: dict[str, set[str]] = {skill.name: set() for skill in members}
    for source, target in edges:
        adjacency[source].add(target)
        adjacency[target].add(source)

    seen = {members[0].name}
    queue: deque[str] = deque([members[0].name])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current] - seen:
            seen.add(neighbor)
            queue.append(neighbor)
    return seen


def validate_skills(skills: list[Skill]) -> list[Violation]:
    """Return all SKIP-clause violations for multi-member skill families."""
    known_skill_names = {skill.name for skill in skills}
    violations: list[Violation] = []

    for family, members in sorted(group_families(skills).items()):
        member_names = {skill.name for skill in members}
        edges: set[tuple[str, str]] = set()

        for skill in members:
            if skill.frontmatter_error:
                violations.append(
                    Violation(
                        "frontmatter",
                        family,
                        skill.name,
                        skill.frontmatter_error,
                    )
                )
                continue

            targets = extract_skip_targets(skill.description, known_skill_names)
            if not targets:
                violations.append(
                    Violation(
                        "missing-skip-clause",
                        family,
                        skill.name,
                        "description has no well-formed SKIP route",
                    )
                )
                continue

            sibling_targets = targets & (member_names - {skill.name})
            if not sibling_targets:
                violations.append(
                    Violation(
                        "no-sibling-target",
                        family,
                        skill.name,
                        f"SKIP routes do not name a sibling: {', '.join(sorted(targets))}",
                    )
                )
                continue

            for sibling in sibling_targets:
                edges.add((skill.name, sibling))

        connected = _connected_members(members, edges)
        disconnected = sorted(member_names - connected)
        if disconnected:
            violations.append(
                Violation(
                    "disconnected-family",
                    family,
                    ",".join(disconnected),
                    "sibling routing graph is not connected",
                )
            )

    return violations


def _resolve_repo_root(repo_root: Path | None) -> Path:
    if repo_root is not None:
        return repo_root.resolve()
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to the parent of scripts/validation.",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="Skills directory. Defaults to .claude/skills under repo root.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _resolve_repo_root(args.repo_root)
    skills_dir = args.skills_dir or repo_root / ".claude" / "skills"

    try:
        skills = load_skills(skills_dir)
    except (OSError, NotADirectoryError) as exc:
        print(f"Could not read skills from {skills_dir}: {exc}", file=sys.stderr)
        return 2

    violations = validate_skills(skills)
    if violations:
        print("Skill SKIP-clause violations:")
        for violation in violations:
            print(
                f"  [{violation.code}] {violation.family}: "
                f"{violation.skill}: {violation.message}"
            )
        print(f"Found {len(violations)} violation(s) across {len(skills)} skill(s).")
        return 1

    family_count = len(group_families(skills))
    print(
        f"Skill SKIP clauses OK: {len(skills)} skill(s), "
        f"{family_count} multi-member family/families."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
