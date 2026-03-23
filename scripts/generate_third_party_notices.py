#!/usr/bin/env python3
"""Generate THIRD-PARTY-NOTICES.TXT from shipped plugin components.

Scans the plugin source paths defined in .claude-plugin/marketplace.json
to identify third-party components that are redistributed. Only shipped
components require license attribution. Dev-only tools, test frameworks,
and CI infrastructure are excluded.

Usage:
    python3 scripts/generate_third_party_notices.py [--output THIRD-PARTY-NOTICES.TXT]

Exit codes per ADR-035:
    0 - Success
    1 - Logic error (missing license data)
    2 - Configuration error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ShippedComponent:
    name: str
    version: str
    license_type: str
    author: str
    url: str
    license_text: str = ""
    category: str = "forked"


# Forked or vendored components shipped in plugin source paths.
# Each entry must include the license text or a path to a LICENSE file.
FORKED_COMPONENTS: dict[str, dict[str, str]] = {
    "SkillForge": {
        "license": "MIT",
        "url": "https://github.com/tripleyak/SkillForge",
        "author": "tripleyak",
        "local_path": ".claude/skills/SkillForge",
        "license_text": (
            "MIT License\n"
            "\n"
            "Copyright (c) 2025\n"
            "\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            'of this software and associated documentation files (the "Software"), to deal\n'
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n"
            "\n"
            "The above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n"
            "\n"
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
            "SOFTWARE.\n"
        ),
    },
}

# Runtime dependencies declared in requirements.txt files within shipped paths.
# These are packages users must install to use the shipped hooks/scripts.
# Attribution is required because the dependency declaration ships with the plugin.
RUNTIME_DEPENDENCIES: dict[str, dict[str, str]] = {
    "anthropic": {
        "license": "MIT",
        "url": "https://github.com/anthropics/anthropic-sdk-python",
        "author": "Anthropic",
        "declared_in": ".claude/hooks/requirements.txt",
        "license_text": (
            "MIT License\n"
            "\n"
            "Copyright (c) 2023 Anthropic, PBC\n"
            "\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            'of this software and associated documentation files (the "Software"), to deal\n'
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n"
            "\n"
            "The above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n"
            "\n"
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
            "SOFTWARE.\n"
        ),
    },
}


def load_marketplace_config(project_root: Path) -> list[dict[str, str]]:
    """Load plugin definitions from .claude-plugin/marketplace.json."""
    marketplace_path = project_root / ".claude-plugin" / "marketplace.json"
    if not marketplace_path.exists():
        print(
            f"ERROR: {marketplace_path} not found. Cannot determine shipped components.",
            file=sys.stderr,
        )
        sys.exit(2)

    with open(marketplace_path) as f:
        data = json.load(f)

    return data.get("plugins", [])


def get_shipped_source_paths(project_root: Path, plugins: list[dict[str, str]]) -> list[Path]:
    """Resolve plugin source paths to absolute paths."""
    paths: list[Path] = []
    for plugin in plugins:
        source = plugin.get("source", "")
        if source:
            resolved = (project_root / source).resolve()
            if resolved.exists():
                paths.append(resolved)
            else:
                print(
                    f"WARNING: Plugin source path does not exist: {source}",
                    file=sys.stderr,
                )
    return paths


def find_forked_components(project_root: Path, shipped_paths: list[Path]) -> list[ShippedComponent]:
    """Identify forked/vendored components within shipped paths."""
    components: list[ShippedComponent] = []

    for name, info in sorted(FORKED_COMPONENTS.items()):
        local_path = info.get("local_path", "")
        if not local_path:
            continue

        component_path = (project_root / local_path).resolve()
        is_shipped = any(str(component_path).startswith(str(sp)) for sp in shipped_paths)

        if is_shipped:
            components.append(
                ShippedComponent(
                    name=name,
                    version="(fork)",
                    license_type=info["license"],
                    author=info["author"],
                    url=info["url"],
                    license_text=info.get("license_text", ""),
                    category="forked",
                )
            )
        else:
            print(
                f"NOTE: {name} at {local_path} is not in a shipped plugin path. Skipping.",
                file=sys.stderr,
            )

    return components


def find_runtime_dependencies(
    project_root: Path, shipped_paths: list[Path]
) -> list[ShippedComponent]:
    """Find requirements.txt files in shipped paths and resolve dependencies."""
    components: list[ShippedComponent] = []

    for shipped_path in shipped_paths:
        for req_file in shipped_path.rglob("requirements.txt"):
            deps = _parse_requirements(req_file)
            for dep_name in deps:
                normalized = dep_name.lower().replace("-", "_")
                info = RUNTIME_DEPENDENCIES.get(dep_name) or RUNTIME_DEPENDENCIES.get(normalized)
                if info:
                    components.append(
                        ShippedComponent(
                            name=dep_name,
                            version="(declared dependency)",
                            license_type=info["license"],
                            author=info["author"],
                            url=info["url"],
                            license_text=info.get("license_text", ""),
                            category="runtime-dependency",
                        )
                    )
                else:
                    components.append(
                        ShippedComponent(
                            name=dep_name,
                            version="(declared dependency)",
                            license_type="Unknown",
                            author="Unknown",
                            url="",
                            category="runtime-dependency",
                        )
                    )

    # Deduplicate by name
    seen: set[str] = set()
    unique: list[ShippedComponent] = []
    for c in components:
        if c.name not in seen:
            seen.add(c.name)
            unique.append(c)

    return sorted(unique, key=lambda c: c.name.lower())


def _parse_requirements(req_file: Path) -> list[str]:
    """Extract package names from a requirements.txt file."""
    names: list[str] = []
    for line in req_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = re.split(r"[>=<!\[;@ ]", line, maxsplit=1)[0]
        if name:
            names.append(name)
    return names


def format_notices(
    forked: list[ShippedComponent],
    runtime: list[ShippedComponent],
) -> str:
    """Format shipped components into THIRD-PARTY-NOTICES.TXT content."""
    lines: list[str] = []

    lines.append("THIRD-PARTY SOFTWARE NOTICES AND INFORMATION")
    lines.append("")
    lines.append("This project incorporates components from the projects listed below.")
    lines.append("The original copyright notices and the licenses under which")
    lines.append("the components were provided are set forth below for informational")
    lines.append("purposes. The project licensors do not grant you any additional")
    lines.append("rights, express or implied.")
    lines.append("")
    lines.append("Scope: This file covers components shipped as part of the plugins")
    lines.append("defined in .claude-plugin/marketplace.json. Dev-only tools, test")
    lines.append("frameworks, CI infrastructure, and build dependencies are excluded.")
    lines.append("")
    lines.append("=" * 72)
    lines.append("")

    section_num = 0

    if forked:
        lines.append("FORKED/VENDORED COMPONENTS")
        lines.append("-" * 40)
        lines.append("")
        for dep in forked:
            section_num += 1
            lines.extend(_format_entry(section_num, dep))

    if runtime:
        lines.append("RUNTIME DEPENDENCIES")
        lines.append("-" * 40)
        lines.append("")
        for dep in runtime:
            section_num += 1
            lines.extend(_format_entry(section_num, dep))

    lines.append("=" * 72)
    lines.append("")
    lines.append("END OF THIRD-PARTY SOFTWARE NOTICES AND INFORMATION")
    lines.append("")

    return "\n".join(lines)


def _format_entry(num: int, dep: ShippedComponent) -> list[str]:
    """Format a single component entry."""
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
    elif dep.url:
        lines.append(
            f"   License text not embedded. See project URL for license details: {dep.url}"
        )
        lines.append("")
    else:
        lines.append(
            "   License text not available. See project documentation for license details."
        )
        lines.append("")

    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate THIRD-PARTY-NOTICES.TXT for shipped plugin components"
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

    plugins = load_marketplace_config(project_root)
    shipped_paths = get_shipped_source_paths(project_root, plugins)

    forked = find_forked_components(project_root, shipped_paths)
    runtime = find_runtime_dependencies(project_root, shipped_paths)

    content = format_notices(forked, runtime)

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

    forked_count = len(forked)
    runtime_count = len(runtime)
    total = forked_count + runtime_count

    print(f"Generated {args.output} with {total} shipped components:")
    print(f"  Forked/vendored:      {forked_count}")
    print(f"  Runtime dependencies: {runtime_count}")

    # Flag unknown licenses
    all_components = forked + runtime
    unknown = [c for c in all_components if c.license_type in ("Unknown", "?", "UNKNOWN")]
    if unknown:
        print(f"\nWARNING: {len(unknown)} components have unknown licenses:")
        for c in unknown:
            print(f"  - {c.name} ({c.version})")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
