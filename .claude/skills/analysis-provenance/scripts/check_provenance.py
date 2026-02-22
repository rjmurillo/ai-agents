#!/usr/bin/env python3
"""Check code provenance to determine if a file is upstream or local.

This script analyzes files to determine their ownership status before
modification. Prevents accidental modification of external dependencies.

Exit Codes:
    0: Provenance determined successfully
    1: Script error (file not found, invalid arguments)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ProvenanceCategory(Enum):
    """Categories of code ownership."""

    UPSTREAM = "UPSTREAM"
    LOCAL = "LOCAL"
    VENDOR = "VENDOR"
    UNKNOWN = "UNKNOWN"


class Confidence(Enum):
    """Confidence level for provenance determination."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Evidence:
    """Evidence for provenance determination."""

    signal: str
    value: Any
    weight: int = 1


@dataclass
class ProvenanceResult:
    """Result of provenance analysis."""

    target: str
    category: ProvenanceCategory
    confidence: Confidence
    evidence: list[Evidence] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "target": self.target,
            "category": self.category.value,
            "confidence": self.confidence.value,
            "evidence": [{"signal": e.signal, "value": e.value} for e in self.evidence],
            "recommendation": self.recommendation,
        }


# Directories that indicate upstream dependencies
UPSTREAM_DIRS = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "site-packages",
        ".nuget",
        "packages",
        "__pycache__",
        ".tox",
        ".nox",
        "dist-packages",
    }
)

# Directories that indicate vendored code
VENDOR_DIRS = frozenset({"vendor", "vendored", "third-party", "third_party", "external"})

# File header markers indicating generated or external code
GENERATED_MARKERS = frozenset(
    {
        "generated",
        "do not edit",
        "auto-generated",
        "automatically generated",
        "this file is generated",
        "machine generated",
    }
)

# Copyright patterns that may indicate external ownership
EXTERNAL_COPYRIGHT_PATTERNS = frozenset(
    {
        "copyright (c)",
        "copyright ©",
        "licensed under",
        "license:",
        "spdx-license-identifier:",
    }
)


def _get_relative_parts(target: Path, project_root: Path) -> tuple[str, ...]:
    """Get relative path parts or target parts if not relative to project root."""
    if target.is_relative_to(project_root):
        return target.relative_to(project_root).parts
    return target.parts


def check_directory_path(target: Path, project_root: Path) -> list[Evidence]:
    """Check if target is in an upstream or vendor directory."""
    evidence = []
    relative_parts = _get_relative_parts(target, project_root)

    for part in relative_parts:
        part_lower = part.lower()
        if part_lower in UPSTREAM_DIRS:
            evidence.append(Evidence(signal="upstream_directory", value=part, weight=10))
        elif part_lower in VENDOR_DIRS:
            evidence.append(Evidence(signal="vendor_directory", value=part, weight=8))

    return evidence


def check_file_header(target: Path) -> list[Evidence]:
    """Check file header for provenance indicators."""
    evidence = []

    if not target.is_file():
        return evidence

    try:
        with open(target, encoding="utf-8", errors="ignore") as f:
            header_lines = []
            for i, line in enumerate(f):
                if i >= 20:
                    break
                header_lines.append(line.lower())

        header_text = " ".join(header_lines)

        for marker in GENERATED_MARKERS:
            if marker in header_text:
                evidence.append(Evidence(signal="generated_marker", value=marker, weight=7))

        for pattern in EXTERNAL_COPYRIGHT_PATTERNS:
            if pattern in header_text:
                evidence.append(Evidence(signal="copyright_notice", value=pattern, weight=3))

    except (OSError, UnicodeDecodeError):
        pass

    return evidence


def check_git_submodule(target: Path, project_root: Path) -> list[Evidence]:
    """Check if target is in a git submodule."""
    evidence = []
    gitmodules = project_root / ".gitmodules"

    if not gitmodules.exists():
        return evidence

    try:
        content = gitmodules.read_text(encoding="utf-8")
        if target.is_relative_to(project_root):
            relative_path = target.relative_to(project_root)
        else:
            relative_path = target

        for line in content.splitlines():
            if line.strip().startswith("path"):
                path_value = line.split("=", 1)[-1].strip()
                if str(relative_path).startswith(path_value):
                    evidence.append(Evidence(signal="git_submodule", value=path_value, weight=9))

    except (OSError, UnicodeDecodeError):
        pass

    return evidence


def check_package_manifest(target: Path, project_root: Path) -> list[Evidence]:
    """Check package manifests for dependency information."""
    evidence = []

    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            content = json.loads(package_json.read_text(encoding="utf-8"))
            deps = {
                **content.get("dependencies", {}),
                **content.get("devDependencies", {}),
            }

            if target.is_relative_to(project_root):
                relative_path = target.relative_to(project_root)
            else:
                relative_path = target
            parts = relative_path.parts

            if len(parts) >= 2 and parts[0] == "node_modules":
                package_name = parts[1]
                if package_name.startswith("@") and len(parts) >= 3:
                    package_name = f"{parts[1]}/{parts[2]}"
                if package_name in deps:
                    evidence.append(
                        Evidence(
                            signal="package_json_dependency",
                            value=f"{package_name}@{deps[package_name]}",
                            weight=10,
                        )
                    )

        except (json.JSONDecodeError, OSError):
            pass

    return evidence


def check_git_tracked(target: Path, project_root: Path) -> list[Evidence]:
    """Check if file is tracked in git (indicates local ownership)."""
    evidence = []

    git_dir = project_root / ".git"
    if not git_dir.exists():
        return evidence

    import subprocess

    try:
        if target.is_relative_to(project_root):
            relative_path = target.relative_to(project_root)
        else:
            relative_path = target
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(relative_path)],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            evidence.append(Evidence(signal="git_tracked", value=True, weight=5))
        else:
            evidence.append(Evidence(signal="git_tracked", value=False, weight=-2))

    except (OSError, subprocess.SubprocessError):
        pass

    return evidence


def check_project_root(target: Path, project_root: Path) -> list[Evidence]:
    """Check if file is under project root (outside dependency dirs)."""
    evidence = []

    if not target.is_relative_to(project_root):
        evidence.append(Evidence(signal="outside_project", value=True, weight=-5))
        return evidence

    relative_parts = target.relative_to(project_root).parts

    in_dependency_dir = any(part.lower() in UPSTREAM_DIRS for part in relative_parts)

    if not in_dependency_dir:
        evidence.append(Evidence(signal="project_root", value=True, weight=6))

    return evidence


def determine_provenance(target: Path, project_root: Path) -> ProvenanceResult:
    """Determine the provenance of a file or directory."""
    all_evidence = []

    all_evidence.extend(check_directory_path(target, project_root))
    all_evidence.extend(check_file_header(target))
    all_evidence.extend(check_git_submodule(target, project_root))
    all_evidence.extend(check_package_manifest(target, project_root))
    all_evidence.extend(check_git_tracked(target, project_root))
    all_evidence.extend(check_project_root(target, project_root))

    upstream_signals = (
        "upstream_directory",
        "package_json_dependency",
        "git_submodule",
        "generated_marker",
    )
    upstream_score = sum(
        e.weight for e in all_evidence if e.signal in upstream_signals
    )

    vendor_score = sum(e.weight for e in all_evidence if e.signal == "vendor_directory")

    local_signals = ("project_root", "git_tracked")
    local_score = sum(
        e.weight for e in all_evidence
        if e.signal in local_signals and e.value is True
    )

    total_weight = sum(abs(e.weight) for e in all_evidence)

    if upstream_score >= 8:
        category = ProvenanceCategory.UPSTREAM
        confidence = Confidence.HIGH if upstream_score >= 15 else Confidence.MEDIUM
        recommendation = "Do NOT modify. Configure via local config files instead."
    elif vendor_score >= 6:
        category = ProvenanceCategory.VENDOR
        confidence = Confidence.HIGH if vendor_score >= 10 else Confidence.MEDIUM
        recommendation = "Avoid modification. Track upstream source for updates."
    elif local_score >= 5:
        category = ProvenanceCategory.LOCAL
        confidence = Confidence.HIGH if local_score >= 10 else Confidence.MEDIUM
        recommendation = "Safe to modify as needed."
    elif total_weight == 0:
        category = ProvenanceCategory.UNKNOWN
        confidence = Confidence.LOW
        recommendation = "Investigate ownership before modifying."
    else:
        max_score = max(upstream_score, vendor_score, local_score)
        if max_score == upstream_score:
            category = ProvenanceCategory.UPSTREAM
        elif max_score == vendor_score:
            category = ProvenanceCategory.VENDOR
        else:
            category = ProvenanceCategory.LOCAL
        confidence = Confidence.LOW
        recommendation = "Low confidence. Verify ownership manually."

    return ProvenanceResult(
        target=str(target),
        category=category,
        confidence=confidence,
        evidence=all_evidence,
        recommendation=recommendation,
    )


def find_project_root(start_path: Path) -> Path:
    """Find project root by looking for .git directory."""
    current = start_path.resolve()

    if current.is_file():
        current = current.parent

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    return start_path.resolve().parent if start_path.is_file() else start_path.resolve()


def format_text_output(result: ProvenanceResult) -> str:
    """Format result as human-readable text."""
    lines = [
        f"Provenance Check: {result.target}",
        "=" * (18 + len(result.target)),
        "",
        f"Category: {result.category.value}",
        f"Confidence: {result.confidence.value}",
        "",
        "Evidence:",
    ]

    for e in result.evidence:
        lines.append(f"  - {e.signal}: {e.value}")

    lines.extend(["", f"Recommendation: {result.recommendation}"])

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check code provenance for ownership determination."
    )
    parser.add_argument("--target", required=True, help="File or directory to analyze")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--verbose", action="store_true", help="Include detailed evidence")

    args = parser.parse_args()

    target = Path(args.target).resolve()

    if not target.exists():
        print(f"Error: Target not found: {target}", file=sys.stderr)
        return 1

    project_root = find_project_root(target)
    result = determine_provenance(target, project_root)

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_text_output(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
