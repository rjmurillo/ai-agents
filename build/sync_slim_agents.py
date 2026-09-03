#!/usr/bin/env python3
"""Propagate a slimmed agent body from `.claude/agents/` to its sibling copies.

`build/AGENTS.md` Rule 2 states the manual procedure this automates: when a
Claude agent receives a universal change, the same change is duplicated into
`templates/agents/{name}.shared.md`. `.serena/memories/decision-two-pipeline-agent-mirror-recipe.md`
widens that to all three hand-maintained copies. This script performs the body
copy for the agents listed in `SLIMMED_AGENTS` and leaves each destination's own
frontmatter alone, because the four trees do not share a frontmatter schema:
`.claude/agents/` and `src/claude/` carry `model:` and `mcp__`-prefixed tool
names, `.github/agents/` carries slash-namespaced tool names, and
`templates/agents/` carries the `tools_vscode` and `tools_copilot` pair that
`build/generate_agents.py` fans out.

It does NOT regenerate the derived trees. After a `--write` run, run
`uv run python build/generate_agents.py` to refresh `src/copilot-cli/` and
`src/vs-code-agents/`.

Default mode is `--check`: report drift and exit non-zero, mutating nothing.
`--write` performs the copy. The asymmetry is deliberate. Four of the nine
agents currently differ between `.claude/agents/` and `templates/agents/`, so a
tool that wrote by default would turn an inspection into a large content change.

Exit codes follow ADR-035:
    0 - no drift (--check), or the sync completed (--write)
    1 - drift found (--check only)
    2 - configuration error: a declared agent or tree is missing
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source of truth for the body. Every destination below takes its body from here.
CLAUDE_AGENTS = REPO_ROOT / ".claude" / "agents"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2


@dataclass(frozen=True, slots=True)
class Destination:
    """One hand-maintained mirror of an agent body."""

    label: str
    directory: Path
    suffix: str

    def path_for(self, name: str) -> Path:
        return self.directory / f"{name}{self.suffix}"


DESTINATIONS: tuple[Destination, ...] = (
    Destination("src/claude", REPO_ROOT / "src" / "claude", ".md"),
    Destination("templates/agents", REPO_ROOT / "templates" / "agents", ".shared.md"),
    Destination(".github/agents", REPO_ROOT / ".github" / "agents", ".agent.md"),
)

# Agents whose bodies are kept in lockstep by this script.
#
# `spec-generator` was carried here by an earlier draft and removed: it is a
# skill at `.claude/skills/spec-generator/`, not an agent, and exists in none of
# the four agent trees. The stale entry produced a SKIP line and exit 0, which
# is indistinguishable from a clean run.
SLIMMED_AGENTS: tuple[str, ...] = (
    "analyst",
    "critic",
    "explainer",
    "implementer",
    "issue-feature-review",
    "milestone-planner",
    "orchestrator",
    "roadmap",
    "skillbook",
)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Frontmatter includes both `---` delimiters.

    A file with no leading `---` block yields an empty frontmatter and the whole
    text as body, so a caller can tell the two shapes apart.
    """
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    boundary = end + len("\n---\n")
    return text[:boundary], text[boundary:]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_missing_paths(agents: tuple[str, ...]) -> list[str]:
    """Return repo-relative paths that every declared agent should have."""
    missing: list[str] = []
    for name in agents:
        source = CLAUDE_AGENTS / f"{name}.md"
        if not source.is_file():
            missing.append(str(source.relative_to(REPO_ROOT)))
        for destination in DESTINATIONS:
            target = destination.path_for(name)
            if not target.is_file():
                missing.append(str(target.relative_to(REPO_ROOT)))
    return missing


def rendered_content(source_body: str, target_text: str) -> str:
    """Return what `target_text` becomes once it carries `source_body`."""
    frontmatter, _ = split_frontmatter(target_text)
    return frontmatter + source_body if frontmatter else source_body


def collect_drift(agents: tuple[str, ...]) -> list[str]:
    """Return repo-relative paths whose body differs from the Claude source."""
    drifted: list[str] = []
    for name in agents:
        _, source_body = split_frontmatter(_read(CLAUDE_AGENTS / f"{name}.md"))
        for destination in DESTINATIONS:
            target = destination.path_for(name)
            current = _read(target)
            if rendered_content(source_body, current) != current:
                drifted.append(str(target.relative_to(REPO_ROOT)))
    return drifted


def apply_sync(agents: tuple[str, ...]) -> list[str]:
    """Write the Claude body into every destination. Return paths changed."""
    changed: list[str] = []
    for name in agents:
        _, source_body = split_frontmatter(_read(CLAUDE_AGENTS / f"{name}.md"))
        for destination in DESTINATIONS:
            target = destination.path_for(name)
            current = _read(target)
            updated = rendered_content(source_body, current)
            if updated == current:
                continue
            target.write_text(updated, encoding="utf-8")
            changed.append(str(target.relative_to(REPO_ROOT)))
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync slimmed agent bodies from .claude/agents/ to its mirrors."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply the sync. Without this flag the script only reports drift.",
    )
    return parser


def _report(label: str, paths: list[str], total: int) -> None:
    print(f"{label}: {len(paths)} of {total} destination files")
    for path in paths:
        print(f"  {path}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    missing = find_missing_paths(SLIMMED_AGENTS)
    if missing:
        print("sync-slim-agents: declared agent files are missing:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        print(
            "Update SLIMMED_AGENTS or restore the files. Refusing to sync a"
            " partial set.",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    total = len(SLIMMED_AGENTS) * len(DESTINATIONS)

    if args.write:
        changed = apply_sync(SLIMMED_AGENTS)
        _report("sync-slim-agents: wrote", changed, total)
        print(
            "Next: run `uv run python build/generate_agents.py` to refresh"
            " src/copilot-cli/ and src/vs-code-agents/."
        )
        return EXIT_OK

    drifted = collect_drift(SLIMMED_AGENTS)
    _report("sync-slim-agents: drifted", drifted, total)
    if drifted:
        print("Run with --write to propagate the .claude/agents/ bodies.")
        return EXIT_DRIFT
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
