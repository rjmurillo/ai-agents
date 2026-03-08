#!/usr/bin/env python3
"""Generate THIRD-PARTY-NOTICES.TXT from project dependencies.

Scans Python package metadata and GitHub Actions references to produce
a notices file following the dotnet/runtime THIRD-PARTY-NOTICES.TXT format.

Usage:
    python3 scripts/generate_third_party_notices.py [--output THIRD-PARTY-NOTICES.TXT]

Exit codes per ADR-035:
    0 - Success
    1 - Logic error (missing license data)
    2 - Configuration error
"""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


@dataclass
class DependencyInfo:
    name: str
    version: str
    license_type: str
    author: str
    url: str
    license_text: str = ""
    category: str = "python"


# Known licenses for packages where metadata is incomplete
KNOWN_LICENSES: dict[str, str] = {
    "markdown-it-py": "MIT",
    "mdurl": "MIT",
    "anyio": "MIT",
    "annotated-types": "MIT",
    "filelock": "Unlicense",
    "idna": "BSD-3-Clause",
    "iniconfig": "MIT",
    "jiter": "MIT",
    "msgpack": "Apache-2.0",
    "mypy_extensions": "MIT",
    "packaging": "Apache-2.0",
    "pathspec": "MPL-2.0",
    "pip": "MIT",
    "pip-api": "Apache-2.0",
    "pip_audit": "Apache-2.0",
    "platformdirs": "MIT",
    "pydantic": "MIT",
    "pydantic-core": "MIT",
    "pydantic_core": "MIT",
    "httpcore": "BSD-3-Clause",
    "CacheControl": "Apache-2.0",
    "sniffio": "MIT",
    "pytest": "MIT",
    "pytest-cov": "MIT",
    "ruff": "MIT",
    "pyparsing": "MIT",
    "regex": "Apache-2.0",
    "tomli": "MIT",
    "tomli_w": "MIT",
    "typing-inspection": "MIT",
    "typing_extensions": "PSF",
    "urllib3": "MIT",
}

# GitHub Actions with their known licenses
ACTIONS_LICENSES: dict[str, dict[str, str]] = {
    "actions/cache": {
        "license": "MIT",
        "url": "https://github.com/actions/cache",
        "author": "GitHub",
    },
    "actions/checkout": {
        "license": "MIT",
        "url": "https://github.com/actions/checkout",
        "author": "GitHub",
    },
    "actions/download-artifact": {
        "license": "MIT",
        "url": "https://github.com/actions/download-artifact",
        "author": "GitHub",
    },
    "actions/github-script": {
        "license": "MIT",
        "url": "https://github.com/actions/github-script",
        "author": "GitHub",
    },
    "actions/labeler": {
        "license": "MIT",
        "url": "https://github.com/actions/labeler",
        "author": "GitHub",
    },
    "actions/setup-node": {
        "license": "MIT",
        "url": "https://github.com/actions/setup-node",
        "author": "GitHub",
    },
    "actions/setup-python": {
        "license": "MIT",
        "url": "https://github.com/actions/setup-python",
        "author": "GitHub",
    },
    "actions/upload-artifact": {
        "license": "MIT",
        "url": "https://github.com/actions/upload-artifact",
        "author": "GitHub",
    },
    "amannn/action-semantic-pull-request": {
        "license": "MIT",
        "url": "https://github.com/amannn/action-semantic-pull-request",
        "author": "Tobias Ammann",
    },
    "anthropics/claude-code-action": {
        "license": "MIT",
        "url": "https://github.com/anthropics/claude-code-action",
        "author": "Anthropic",
    },
    "dorny/paths-filter": {
        "license": "MIT",
        "url": "https://github.com/dorny/paths-filter",
        "author": "Michal Dorner",
    },
    "dorny/test-reporter": {
        "license": "MIT",
        "url": "https://github.com/dorny/test-reporter",
        "author": "Michal Dorner",
    },
    "github/codeql-action": {
        "license": "MIT",
        "url": "https://github.com/github/codeql-action",
        "author": "GitHub",
    },
    "ibiqlik/action-yamllint": {
        "license": "MIT",
        "url": "https://github.com/ibiqlik/action-yamllint",
        "author": "Ibrahim Biqlik",
    },
    "step-security/harden-runner": {
        "license": "Apache-2.0",
        "url": "https://github.com/step-security/harden-runner",
        "author": "StepSecurity",
    },
    "Factory-AI/droid-action": {
        "license": "MIT",
        "url": "https://github.com/Factory-AI/droid-action",
        "author": "Factory AI",
    },
}


def get_python_dependencies(project_root: Path) -> list[DependencyInfo]:
    """Extract license info from installed Python packages."""
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return []

    # Read direct dependency names from pyproject.toml using proper TOML parsing
    with open(pyproject, "rb") as f:
        pyproject_data = tomllib.load(f)

    direct_deps: set[str] = set()
    project = pyproject_data.get("project", {})
    for dep_spec in project.get("dependencies", []):
        dep_name = re.split(r"[>=<!\[;@ ]", dep_spec, maxsplit=1)[0]
        direct_deps.add(dep_name.lower())
    optional_deps = project.get("optional-dependencies", {})
    for dep_spec in optional_deps.get("dev", []):
        dep_name = re.split(r"[>=<!\[;@ ]", dep_spec, maxsplit=1)[0]
        direct_deps.add(dep_name.lower())

    deps: list[DependencyInfo] = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name.lower() == "ai-agents":
            continue

        version = dist.metadata["Version"]
        license_type = dist.metadata.get("License", "")
        author = dist.metadata.get("Author", "")
        if not author:
            author = dist.metadata.get("Author-email", "Unknown")

        # Extract URL
        url = dist.metadata.get("Home-page", "")
        if not url:
            project_urls = dist.metadata.get_all("Project-URL") or []
            for pu in project_urls:
                if "homepage" in pu.lower() or "repository" in pu.lower():
                    url = pu.split(",", 1)[-1].strip()
                    break

        # Clean up license - some packages embed full text
        if license_type and len(license_type) > 50:
            license_type = license_type.split("\n")[0].strip()

        # Use classifiers as fallback
        if not license_type or license_type == "?":
            classifiers = dist.metadata.get_all("Classifier") or []
            for c in classifiers:
                if "License" in c and "OSI" not in c:
                    license_type = c.split(" :: ")[-1]
                    break

        # Use known licenses as final fallback
        if not license_type or license_type in ("?", "UNKNOWN"):
            license_type = KNOWN_LICENSES.get(name, "Unknown")

        # Try to read license file from package
        license_text = ""
        try:
            files = dist.files or []
            for f in files:
                fname = str(f).split("/")[-1].upper()
                if fname in ("LICENSE", "LICENSE.TXT", "LICENSE.MD", "COPYING"):
                    license_text = f.read_text("utf-8")
                    break
        except (FileNotFoundError, PermissionError, UnicodeDecodeError) as exc:
            print(
                f"WARNING: Failed to read license file for {name}: {exc}",
                file=sys.stderr,
            )

        is_direct = name.lower() in direct_deps
        category = "python-direct" if is_direct else "python-transitive"

        deps.append(
            DependencyInfo(
                name=name,
                version=version,
                license_type=license_type,
                author=author,
                url=url,
                license_text=license_text,
                category=category,
            )
        )

    return sorted(deps, key=lambda d: (d.category, d.name.lower()))


def get_github_actions(project_root: Path) -> list[DependencyInfo]:
    """Extract GitHub Actions references from workflow files."""
    actions: dict[str, str] = {}
    workflow_dirs = [
        project_root / ".github" / "workflows",
        project_root / ".github" / "actions",
    ]

    for wdir in workflow_dirs:
        if not wdir.exists():
            continue
        for yml_file in wdir.rglob("*.yml"):
            content = yml_file.read_text()
            for match in re.finditer(r"uses:\s*([^@\s]+)@", content):
                action = match.group(1).strip()
                if not action.startswith("./"):
                    actions[action] = action

    deps: list[DependencyInfo] = []
    for action_name in sorted(actions):
        # Try exact match first, then parent action (e.g., actions/cache/restore -> actions/cache)
        info = ACTIONS_LICENSES.get(action_name, {})
        if not info:
            parts = action_name.split("/")
            if len(parts) > 2:
                parent = "/".join(parts[:2])
                info = ACTIONS_LICENSES.get(parent, {})
        deps.append(
            DependencyInfo(
                name=action_name,
                version="(SHA-pinned)",
                license_type=info.get("license", "Unknown"),
                author=info.get("author", "Unknown"),
                url=info.get("url", f"https://github.com/{action_name}"),
                category="github-action",
            )
        )

    return deps


def get_docker_images(project_root: Path) -> list[DependencyInfo]:
    """Extract Docker base image references."""
    deps: list[DependencyInfo] = []
    for dockerfile in project_root.rglob("Dockerfile*"):
        content = dockerfile.read_text()
        for match in re.finditer(r"FROM\s+([^\s]+)", content):
            image = match.group(1)
            if image.startswith("$"):
                continue
            deps.append(
                DependencyInfo(
                    name=image.split(":")[0],
                    version=image.split(":")[-1] if ":" in image else "latest",
                    license_type="Various",
                    author="See image documentation",
                    url=f"https://hub.docker.com/_/{image.split(':')[0]}",
                    category="docker",
                )
            )
    return deps


def format_notices(
    python_deps: list[DependencyInfo],
    action_deps: list[DependencyInfo],
    docker_deps: list[DependencyInfo],
) -> str:
    """Format all dependencies into THIRD-PARTY-NOTICES.TXT content."""
    lines: list[str] = []

    lines.append("THIRD-PARTY SOFTWARE NOTICES AND INFORMATION")
    lines.append("")
    lines.append(
        "This project incorporates components from the projects listed below."
    )
    lines.append(
        "The original copyright notices and the licenses under which"
    )
    lines.append(
        "the components were provided are set forth below for informational"
    )
    lines.append(
        "purposes. The project licensors do not grant you any additional"
    )
    lines.append("rights, express or implied.")
    lines.append("")
    lines.append("=" * 72)
    lines.append("")

    section_num = 0

    # Direct Python dependencies
    direct = [d for d in python_deps if d.category == "python-direct"]
    if direct:
        lines.append("DIRECT PYTHON DEPENDENCIES")
        lines.append("-" * 40)
        lines.append("")
        for dep in direct:
            section_num += 1
            lines.extend(_format_dep(section_num, dep))

    # Transitive Python dependencies
    transitive = [d for d in python_deps if d.category == "python-transitive"]
    if transitive:
        lines.append("TRANSITIVE PYTHON DEPENDENCIES")
        lines.append("-" * 40)
        lines.append("")
        for dep in transitive:
            section_num += 1
            lines.extend(_format_dep(section_num, dep))

    # GitHub Actions
    if action_deps:
        lines.append("GITHUB ACTIONS")
        lines.append("-" * 40)
        lines.append("")
        for dep in action_deps:
            section_num += 1
            lines.extend(_format_dep(section_num, dep))

    # Docker images
    if docker_deps:
        lines.append("DOCKER BASE IMAGES")
        lines.append("-" * 40)
        lines.append("")
        for dep in docker_deps:
            section_num += 1
            lines.extend(_format_dep(section_num, dep))

    lines.append("=" * 72)
    lines.append("")
    lines.append("END OF THIRD-PARTY SOFTWARE NOTICES AND INFORMATION")
    lines.append("")

    return "\n".join(lines)


def _format_dep(num: int, dep: DependencyInfo) -> list[str]:
    """Format a single dependency entry."""
    lines: list[str] = []
    lines.append(f"{num}. {dep.name} ({dep.version})")
    lines.append("")
    lines.append(f"   License: {dep.license_type}")
    lines.append(f"   Author:  {dep.author}")
    if dep.url:
        lines.append(f"   URL:     {dep.url}")
    lines.append("")

    if dep.license_text:
        lines.append("   " + "-" * 60)
        for text_line in dep.license_text.strip().splitlines():
            lines.append(f"   {text_line}")
        lines.append("   " + "-" * 60)
        lines.append("")
    else:
        if dep.url:
            lines.append(
                "   License text not embedded in package distribution."
                f" See project URL for license details: {dep.url}"
            )
        else:
            lines.append(
                "   License text not embedded in package distribution."
                " See project documentation for license details."
            )
        lines.append("")

    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate THIRD-PARTY-NOTICES.TXT"
    )
    parser.add_argument(
        "--output",
        default="THIRD-PARTY-NOTICES.TXT",
        help="Output file path (default: THIRD-PARTY-NOTICES.TXT)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: verify file is up to date without writing",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    python_deps = get_python_dependencies(project_root)
    action_deps = get_github_actions(project_root)
    docker_deps = get_docker_images(project_root)

    content = format_notices(python_deps, action_deps, docker_deps)

    output_path = project_root / args.output

    if args.check:
        if not output_path.exists():
            print(f"ERROR: {args.output} does not exist. Run without --check to generate.")
            return 1
        existing = output_path.read_text()
        if existing != content:
            print(f"ERROR: {args.output} is out of date. Run without --check to regenerate.")
            return 1
        print(f"OK: {args.output} is up to date.")
        return 0

    output_path.write_text(content)

    # Summary
    direct_count = len([d for d in python_deps if d.category == "python-direct"])
    transitive_count = len([d for d in python_deps if d.category == "python-transitive"])
    action_count = len(action_deps)
    docker_count = len(docker_deps)
    total = direct_count + transitive_count + action_count + docker_count

    print(f"Generated {args.output} with {total} components:")
    print(f"  Python direct:     {direct_count}")
    print(f"  Python transitive: {transitive_count}")
    print(f"  GitHub Actions:    {action_count}")
    print(f"  Docker images:     {docker_count}")

    # Flag unknown licenses
    unknown = [
        d for d in python_deps + action_deps + docker_deps
        if d.license_type in ("Unknown", "?", "UNKNOWN")
    ]
    if unknown:
        print(f"\nWARNING: {len(unknown)} components have unknown licenses:")
        for d in unknown:
            print(f"  - {d.name} ({d.version})")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
