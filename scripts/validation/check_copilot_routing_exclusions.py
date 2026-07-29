#!/usr/bin/env python3
"""Validate that shipped Copilot skill surfaces do not route to excluded skills.

The Copilot CLI platform can exclude canonical skills from the public shipping
set via templates/platforms/copilot-cli.yaml artifacts.skills.excludeFilenames.
A shipped Copilot skill must not still tell users to invoke one of those names
as a skill. Agent references remain valid when an agent with the same name ships.

Exit codes:
    0 - no violations found
    1 - violations found
    2 - configuration error
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class RoutingConfigError(ValueError):
    """Invalid Copilot routing exclusion configuration."""


@dataclass(frozen=True)
class RoutingViolation:
    """One excluded skill reference found in a shipped Copilot skill file."""

    path: Path
    line_number: int
    skill_name: str
    line: str

    def format(self, repo_root: Path) -> str:
        rel_path = self.path.relative_to(repo_root)
        return f"{rel_path}:{self.line_number}: {self.skill_name}: {self.line.strip()}"


def load_excluded_skill_names(repo_root: Path) -> set[str]:
    """Return excluded entries that are canonical skill directory names."""
    config_path = repo_root / "templates" / "platforms" / "copilot-cli.yaml"
    config = _load_yaml_mapping(config_path)
    skills = _skills_stanza(config)
    excluded = skills.get("excludeFilenames", [])
    if not isinstance(excluded, list):
        raise RoutingConfigError("artifacts.skills.excludeFilenames must be a list")

    source_dir = skills.get("sourceDir", ".claude/skills")
    if not isinstance(source_dir, str):
        raise RoutingConfigError("artifacts.skills.sourceDir must be a string")
    canonical_root = repo_root / source_dir

    return {
        name
        for item in excluded
        if isinstance(item, str)
        for name in [item.strip()]
        if name and _is_canonical_skill_name(canonical_root, name)
    }


def scan_copilot_skill_files(
    repo_root: Path,
    excluded_skill_names: set[str],
) -> list[RoutingViolation]:
    """Scan shipped Copilot skill markdown for excluded skill routes."""
    skills_root = repo_root / "src" / "copilot-cli" / "skills"
    if not skills_root.is_dir() or not excluded_skill_names:
        return []

    violations: list[RoutingViolation] = []
    for path in sorted(skills_root.rglob("*.md")):
        violations.extend(_scan_file(repo_root, path, excluded_skill_names))
    return violations


def validate_copilot_routing_exclusions(repo_root: Path) -> bool:
    """Return True when shipped Copilot skills do not route to excluded skills."""
    try:
        excluded = load_excluded_skill_names(repo_root)
    except RoutingConfigError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise

    violations = scan_copilot_skill_files(repo_root, excluded)
    if not violations:
        return True

    print("Copilot routing exclusion violations detected:", file=sys.stderr)
    for violation in violations:
        print(f"  - {violation.format(repo_root)}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Use Agent: <name> or '<name> agent' phrasing for excluded skills "
        "when a Copilot agent ships with that name.",
        file=sys.stderr,
    )
    return False


def _load_yaml_mapping(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise RoutingConfigError(f"missing config: {config_path}")
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RoutingConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise RoutingConfigError(f"expected YAML mapping in {config_path}")
    return loaded


def _skills_stanza(config: dict[str, Any]) -> dict[str, Any]:
    artifacts = config.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RoutingConfigError("missing artifacts mapping")
    skills = artifacts.get("skills")
    if not isinstance(skills, dict):
        raise RoutingConfigError("missing artifacts.skills mapping")
    return skills


def _is_canonical_skill_name(canonical_root: Path, name: str) -> bool:
    if name.endswith(".md") or "/" in name or "\\" in name:
        return False
    return (canonical_root / name / "SKILL.md").is_file()


def _scan_file(
    repo_root: Path,
    path: Path,
    excluded_skill_names: set[str],
) -> list[RoutingViolation]:
    violations: list[RoutingViolation] = []
    in_code_fence = False
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        for skill_name in excluded_skill_names:
            if _routes_to_excluded_skill(raw_line, skill_name):
                violations.append(RoutingViolation(path, line_number, skill_name, raw_line))
    return violations


def _routes_to_excluded_skill(line: str, skill_name: str) -> bool:
    if not _contains_skill_name(line, skill_name):
        return False
    if _contains_agent_reference(line, skill_name):
        return False
    return _has_skill_invocation(line, skill_name) or _has_routing_table_reference(line)


def _contains_skill_name(line: str, skill_name: str) -> bool:
    return re.search(rf"(?<![\w-])`?{re.escape(skill_name)}`?(?![\w-])", line) is not None


def _contains_agent_reference(line: str, skill_name: str) -> bool:
    escaped = re.escape(skill_name)
    patterns = (
        rf"\bAgent:\s*`?{escaped}`?\b",
        rf"\b`?{escaped}`?\s+agent\b",
    )
    return any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)


def _has_skill_invocation(line: str, skill_name: str) -> bool:
    escaped = re.escape(skill_name)
    patterns = (
        rf"\bSkill:\s*`?{escaped}`?\b",
        rf"\b(?:use|invoke|load|run|route to|routes to|resolve via)\s+`?{escaped}`?\b",
    )
    return any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)


def _has_routing_table_reference(line: str) -> bool:
    return "|" in line


def main(argv: list[str] | None = None) -> int:
    args = argv or []
    if len(args) > 1:
        print("Usage: check_copilot_routing_exclusions.py [repo-root]", file=sys.stderr)
        return 2
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parent.parent.parent
    try:
        return 0 if validate_copilot_routing_exclusions(repo_root) else 1
    except RoutingConfigError:
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
