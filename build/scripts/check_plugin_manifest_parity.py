#!/usr/bin/env python3
"""Validate the plugin manifests against the marketplace listings.

Two independent invariants are checked.

VERSION PARITY
--------------

The two project-toolkit manifests must carry identical version strings:

    .claude/.claude-plugin/plugin.json         (Claude plugin)
    src/copilot-cli/.claude-plugin/plugin.json (Copilot CLI plugin)

When a PR bumps the version on one but not the other, the installed plugins
report different versions to the host. This check gates that drift in CI
(fix for #2222).

NO COMPONENT COUNTS IN DESCRIPTIONS
-----------------------------------

A description that says "25 specialized agent definitions" is wrong the moment
somebody adds or deletes an agent, and nothing in the repository recomputes it.
PR #2187 acted on that: it stripped the drifting counts out of both marketplace
files and retired `validate_marketplace_counts.py`, the validator that had been
asserting a hard-coded count matched reality and firing on every PR that touched
a component (#2148).

That sweep closed only part of the loop. It rewrote the two marketplace files
and left `src/claude/.claude-plugin/plugin.json` carrying `25 specialized agent
definitions ...` while the entry publishing it carried the same sentence with
the count removed. The stale count then sat on main for 57 days (#3651).

This check is the missing stage of that closure. It scans every description this
repository publishes, in both marketplace files and in all three manifests, and
fails when one embeds a component count.

It is NOT a revival of the retired validator. That one counted the components on
disk and demanded the description match, so adding an agent broke unrelated PRs.
This one counts nothing and derives nothing. It asserts only that a description
carries no count to go stale, which is exactly the decision #2187 made.

WHAT THIS DELIBERATELY DOES NOT CHECK
-------------------------------------

An earlier draft required each marketplace entry to repeat its manifest's `name`
and `description` verbatim. Upstream contradicts that: a marketplace entry may
carry any field from the plugin manifest schema as catalog metadata, and under
`strict: false` the entry is the entire definition and the plugin may legitimately
ship no `plugin.json` at all. Equality is therefore a matter of house taste, not
correctness, and adversarial review found no evidence that this repository ever
decided it. Gating taste would block PRs on a rule nobody agreed to. The count
rule survives because #2187 is a real, cited decision with a commit behind it.

Exit codes (ADR-035):
    0 - All checks pass
    1 - Staleness: the manifests disagree on version, or a description embeds a
        component count
    2 - Configuration error: a file is missing, unreadable, or not the expected
        JSON shape
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MANIFESTS: tuple[Path, ...] = (
    _REPO_ROOT / ".claude" / ".claude-plugin" / "plugin.json",
    _REPO_ROOT / "src" / "copilot-cli" / ".claude-plugin" / "plugin.json",
)

_MARKETPLACES: tuple[Path, ...] = (
    _REPO_ROOT / ".claude-plugin" / "marketplace.json",
    _REPO_ROOT / ".github" / "plugin" / "marketplace.json",
)

_OK = 0
_STALENESS = 1
_CONFIG_ERROR = 2


def _rel(path: Path) -> str:
    """Repo-relative path for display, falling back to the absolute path."""
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _read_manifest(path: Path) -> dict[str, Any] | None:
    """Return the parsed JSON object, or None when unreadable or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        print(f"ERROR: cannot read {_rel(path)}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"ERROR: {_rel(path)} is not a JSON object", file=sys.stderr)
        return None
    return data


def _read_version(path: Path) -> str | None:
    """Return the version field or None on parse error."""
    data = _read_manifest(path)
    if data is None:
        return None
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        print(f"ERROR: {_rel(path)} has no valid 'version' field", file=sys.stderr)
        return None
    return version


def check_version_parity(manifests: tuple[Path, ...] = _MANIFESTS) -> int:
    """Both project-toolkit manifests must report the same version."""
    versions: dict[str, str] = {}

    for manifest in manifests:
        if not manifest.exists():
            print(f"ERROR: manifest not found: {_rel(manifest)}", file=sys.stderr)
            return _CONFIG_ERROR
        version = _read_version(manifest)
        if version is None:
            return _CONFIG_ERROR
        versions[_rel(manifest)] = version

    unique = set(versions.values())
    if len(unique) == 1:
        print(f"Plugin manifest versions match: {next(iter(unique))}")
        return _OK

    print("PLUGIN MANIFEST VERSION MISMATCH", file=sys.stderr)
    for path, ver in sorted(versions.items()):
        print(f"  {path}: {ver}", file=sys.stderr)
    print(
        "\nFix: bump both manifests to the same version and commit together.",
        file=sys.stderr,
    )
    return _STALENESS


# Every file in this repository that publishes a user-visible plugin description.
_DESCRIBED_FILES: tuple[Path, ...] = _MARKETPLACES + _MANIFESTS + (
    _REPO_ROOT / "src" / "claude" / ".claude-plugin" / "plugin.json",
)

# Count tokens. "one" is included: a description saying "one agent" goes stale the
# moment a second lands, exactly like "two agents" does. The prose that motivated
# excluding it ("one of the skills") is handled by the `of` exclusion below, which
# is precise where dropping the token was merely blunt.
_COUNT = (
    r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred"
)

# Only the component categories a plugin manifest actually declares, plus the unit
# a marketplace inventories. Keeping the list this short is what makes the rest of
# the pattern safe to loosen: "two workflows" and "three rules of thumb" are prose a
# description may legitimately contain, and neither is a component category, so
# neither can trip the gate. Singular is accepted because the count is what goes
# stale, not the grammar ("25-agent toolkit", "1 agent", "25 specialized agent
# definitions" are all inventories).
# Source: the component keys accepted by build/scripts/validate_plugin_manifests.py.
_COMPONENTS = r"agents?|skills?|commands?|hooks?|mcp[-\s]?servers?|plugins?"

# Up to three words may sit between the count and the category it quantifies, which
# is what "12 production-ready specialized review agents" needs. `of` may not be one
# of them: it marks a partitive ("one of the skills"), which names no inventory.
# The separator is `[-\s]` so hyphenated forms ("25-agent") are read as counts too.
_COUNT_IN_DESCRIPTION = re.compile(
    rf"\b({_COUNT})(?:[-\s]+(?!of\b)[A-Za-z][\w-]*){{0,3}}[-\s]+({_COMPONENTS})\b",
    re.IGNORECASE,
)


def _descriptions(path: Path, data: dict[str, Any]) -> list[tuple[str, str]]:
    """Every description string a file publishes, paired with a label.

    A marketplace file carries its own description plus one per plugin entry; a
    manifest carries exactly one. Both shapes are read from the same function so
    a new description field cannot be added on one side and skipped on the other.
    """
    found: list[tuple[str, str]] = []
    top = data.get("description")
    if isinstance(top, str):
        found.append((_rel(path), top))

    entries = data.get("plugins")
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            text = entry.get("description")
            if isinstance(text, str):
                name = entry.get("name")
                label = name if isinstance(name, str) and name else f"entry {index}"
                found.append((f"{_rel(path)} :: {label}", text))
    return found


def check_description_counts(files: tuple[Path, ...] = _DESCRIBED_FILES) -> int:
    """No published description may embed a component count.

    The count is not derived from anything, so it is stale as soon as a component
    is added or removed. #2187 decided counts do not belong in these strings; this
    is the gate that keeps a later edit from putting one back.
    """
    problems: list[str] = []
    scanned = 0

    for path in files:
        if not path.exists():
            print(f"ERROR: file not found: {_rel(path)}", file=sys.stderr)
            return _CONFIG_ERROR
        data = _read_manifest(path)
        if data is None:
            return _CONFIG_ERROR

        for label, text in _descriptions(path, data):
            scanned += 1
            match = _COUNT_IN_DESCRIPTION.search(text)
            if match:
                problems.append(f"{label}\n      {text!r}\n      embeds count: {match.group(0)!r}")

    if not problems:
        print(f"No component counts in plugin descriptions: {scanned} checked")
        return _OK

    print("COMPONENT COUNT IN A PLUGIN DESCRIPTION", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nFix: remove the count from the description. Nothing recomputes it, so "
        "it goes stale the next time a component is added or removed (#2187).",
        file=sys.stderr,
    )
    return _STALENESS


def main() -> int:
    results = (check_version_parity(), check_description_counts())
    if _CONFIG_ERROR in results:
        return _CONFIG_ERROR
    if _STALENESS in results:
        return _STALENESS
    return _OK


if __name__ == "__main__":
    sys.exit(main())
