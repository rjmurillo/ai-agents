#!/usr/bin/env python3
"""Propagate a slimmed agent body from `src/claude/` to its sibling copies.

`build/AGENTS.md` Rule 2 states the manual procedure this automates: when a
Claude agent receives a universal change, the same change is duplicated into
`templates/agents/{name}.shared.md`. `.serena/memories/decision-two-pipeline-agent-mirror-recipe.md`
widens that to the other hand-maintained copies. This script performs the body
copy for the agents listed in `SLIMMED_AGENTS` and leaves each destination's own
frontmatter alone, because the trees do not share a frontmatter schema:
`src/claude/` carries `model:` and `mcp__`-prefixed tool names,
`.github/agents/` carries slash-namespaced tool names, and `templates/agents/`
carries the `tools_vscode` and `tools_copilot` pair that
`build/generate_agents.py` fans out.

`src/claude/` is the source and never a destination. Its own `AGENTS.md`
tabulates `src/claude/` as the source for Claude Code agents, marked "Edit
here", against `.claude/agents/` as the installed runtime copy, marked "DO NOT
edit directly", and names copying the installed tree back over the source as a
common mistake that can drop blocking gates. So `.claude/agents/` is neither
read nor written here. Nothing is lost by leaving it out:
`build/scripts/check_agent_content_parity.py` already compares those two trees
byte-for-byte and runs on every PR through `pre_pr.py`.

It does NOT regenerate the derived trees. After a `--write` run, run
`uv run python build/generate_agents.py` to refresh `src/copilot-cli/` and
`src/vs-code-agents/`. It also does not touch `.claude/agents/`, so an edit
that started in `src/claude/` still has to reach that installed copy by its own
route; `check_agent_content_parity.py` compares the two byte-for-byte and fails
the PR until it does. Both steps are printed after a write.

Default mode is `--check`: report drift and exit non-zero, mutating nothing.
`--write` performs the copy. The asymmetry is deliberate. Four of the nine
agents currently differ between `src/claude/` and `templates/agents/`, so a
tool that wrote by default would turn an inspection into a large content change.

Exit codes follow ADR-035:
    0 - no drift (--check), or the sync completed (--write)
    1 - drift found (--check only)
    2 - configuration error: a declared file is missing, is a symlink or escapes
        the checkout, or opens a `---` block it never closes; or `--write` was
        invoked from outside the checkout that holds this script
    3 - external failure: a read or write raised OSError or UnicodeDecodeError
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePath

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source of truth for the body. Every destination below takes its body from here.
AGENT_SOURCE = REPO_ROOT / "src" / "claude"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


class UnsafePathError(Exception):
    """A declared path is a symlink or resolves outside the repository root."""


@dataclass(frozen=True, slots=True)
class Destination:
    """One hand-maintained mirror of an agent body."""

    label: str
    directory: Path
    suffix: str

    def path_for(self, name: str) -> Path:
        return self.directory / f"{name}{self.suffix}"


DESTINATIONS: tuple[Destination, ...] = (
    Destination("templates/agents", REPO_ROOT / "templates" / "agents", ".shared.md"),
    Destination(".github/agents", REPO_ROOT / ".github" / "agents", ".agent.md"),
)

# Agents whose bodies are kept in lockstep by this script.
#
# `spec-generator` was carried here by an earlier draft and removed: it is a
# skill at `.claude/skills/spec-generator/`, not an agent, and exists in none of
# the agent trees. The stale entry produced a SKIP line and exit 0, which is
# indistinguishable from a clean run.
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


def _frontmatter_end(text: str) -> int | None:
    """Return the index just past the closing `---` line, or None if absent.

    The search starts at the newline that closes the opening delimiter, not
    past it, so an empty block (`---` on one line and `---` on the next) is
    terminated rather than unterminated. A closing delimiter that ends the
    file with no trailing newline counts too. Both shapes are legal
    frontmatter, and `main` now rejects an unterminated block outright, so
    misreading either one would refuse to sync a valid file.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 3)
    if end != -1:
        return end + len("\n---\n")
    if text.endswith("\n---"):
        return len(text)
    return None


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Frontmatter includes both `---` delimiters.

    A file with no leading `---` block yields an empty frontmatter and the whole
    text as body. A file whose block never closes yields that same shape, so
    this return value alone cannot tell the two apart. `main` runs
    `find_malformed_paths` first and refuses the second shape, which is what
    keeps the ambiguity away from the callers below.
    """
    boundary = _frontmatter_end(text)
    if boundary is None:
        return "", text
    return text[:boundary], text[boundary:]


def has_unterminated_frontmatter(text: str) -> bool:
    """True when the text opens a `---` block that never closes."""
    return text.startswith("---\n") and _frontmatter_end(text) is None


def _relative(path: PurePath) -> str:
    """Return the repo-relative path with forward slashes on every platform.

    `str()` on a Windows path yields backslashes, which would make the drift
    report and the error output disagree with the repository-style paths this
    script documents and its tests assert.
    """
    return path.relative_to(REPO_ROOT).as_posix()


def _within_repo(path: Path) -> Path:
    """Return the resolved path, refusing a symlink or an escape from the root.

    `Path.read_text` and `Path.write_text` both follow symlinks, so a mirror
    file replaced by a link to somewhere else would let `--write` overwrite a
    file outside the checkout. Every read and write below goes through here and
    uses the returned resolved path, so the check and the access cannot disagree.
    """
    resolved = path.resolve(strict=False)
    if path.is_symlink() or not resolved.is_relative_to(REPO_ROOT.resolve()):
        raise UnsafePathError(_relative(path))
    return resolved


def _read(path: Path) -> str:
    return _within_repo(path).read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    _within_repo(path).write_text(text, encoding="utf-8")


def declared_paths(agents: Iterable[str]) -> Iterator[Path]:
    """Yield every file this script reads or writes, source first per agent."""
    for name in agents:
        yield AGENT_SOURCE / f"{name}.md"
        for destination in DESTINATIONS:
            yield destination.path_for(name)


def find_missing_paths(agents: tuple[str, ...]) -> list[str]:
    """Return repo-relative paths that every declared agent should have."""
    return [_relative(path) for path in declared_paths(agents) if not path.is_file()]


def find_unsafe_paths(agents: tuple[str, ...]) -> list[str]:
    """Return declared paths that are symlinks or escape the repository root."""
    unsafe: list[str] = []
    for path in declared_paths(agents):
        try:
            _within_repo(path)
        except UnsafePathError as exc:
            unsafe.append(str(exc))
    return unsafe


def find_malformed_paths(agents: tuple[str, ...]) -> list[str]:
    """Return declared paths that open a `---` block and never close it.

    Reads file content, so `find_unsafe_paths` runs before this one.
    """
    return [
        _relative(path)
        for path in declared_paths(agents)
        if has_unterminated_frontmatter(_read(path))
    ]


def rendered_content(source_body: str, target_text: str) -> str:
    """Return what `target_text` becomes once it carries `source_body`."""
    frontmatter, _ = split_frontmatter(target_text)
    if not frontmatter:
        return source_body
    if not frontmatter.endswith("\n"):
        # A closing `---` that ended the file carries no newline of its own.
        # Concatenating straight onto it yields `---# Analyst`, which is no
        # longer a standalone YAML delimiter, so the block would not parse.
        frontmatter += "\n"
    return frontmatter + source_body


def collect_drift(agents: tuple[str, ...]) -> list[str]:
    """Return repo-relative paths whose body differs from the Claude source."""
    drifted: list[str] = []
    for name in agents:
        _, source_body = split_frontmatter(_read(AGENT_SOURCE / f"{name}.md"))
        for destination in DESTINATIONS:
            target = destination.path_for(name)
            current = _read(target)
            if rendered_content(source_body, current) != current:
                drifted.append(_relative(target))
    return drifted


def apply_sync(agents: tuple[str, ...]) -> list[str]:
    """Write the Claude body into every destination. Return paths changed."""
    changed: list[str] = []
    for name in agents:
        _, source_body = split_frontmatter(_read(AGENT_SOURCE / f"{name}.md"))
        for destination in DESTINATIONS:
            target = destination.path_for(name)
            current = _read(target)
            updated = rendered_content(source_body, current)
            if updated == current:
                continue
            _write(target, updated)
            changed.append(_relative(target))
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync slimmed agent bodies from src/claude/ to its mirrors."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Report drift and exit non-zero, mutating nothing. The default.",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Apply the sync. Without this flag the script only reports drift.",
    )
    return parser


def _report(label: str, paths: list[str], total: int) -> None:
    print(f"{label}: {len(paths)} of {total} destination files")
    for path in paths:
        print(f"  {path}")


def _config_error(header: str, paths: list[str], remedy: str) -> int:
    print(f"sync-slim-agents: {header}", file=sys.stderr)
    for path in paths:
        print(f"  {path}", file=sys.stderr)
    print(remedy, file=sys.stderr)
    return EXIT_CONFIG


def _preflight() -> int:
    """Return EXIT_CONFIG when any declared file is unusable, else EXIT_OK.

    Ordered so no stage touches a file an earlier stage rejected: existence
    first, then path safety, then frontmatter shape, which is the only stage
    that reads content. Runs before both modes, so a rejected tree is reported
    without a single write.
    """
    missing = find_missing_paths(SLIMMED_AGENTS)
    if missing:
        return _config_error(
            "declared agent files are missing:",
            missing,
            "Update SLIMMED_AGENTS or restore the files. Refusing to sync a"
            " partial set.",
        )

    unsafe = find_unsafe_paths(SLIMMED_AGENTS)
    if unsafe:
        return _config_error(
            "declared agent files are symlinks or escape the repository root:",
            unsafe,
            "Restore them as regular files inside the checkout. Refusing to"
            " read or write through them.",
        )

    malformed = find_malformed_paths(SLIMMED_AGENTS)
    if malformed:
        return _config_error(
            "declared agent files open a `---` block that never closes:",
            malformed,
            "Close the frontmatter or remove it. Refusing to sync a file whose"
            " metadata cannot be located.",
        )

    return EXIT_OK


def _run(args: argparse.Namespace) -> int:
    preflight = _preflight()
    if preflight != EXIT_OK:
        return preflight

    total = len(SLIMMED_AGENTS) * len(DESTINATIONS)

    if args.write:
        # .claude/rules/ci-scripts.md MUST 7: a script that resolves the
        # repository root and then writes to it must confirm the caller's cwd
        # sits inside that root before the first write. REPO_ROOT comes from
        # __file__, so without this check, running the script from another
        # checkout silently rewrites the checkout that holds the script, with
        # no signal that the write landed somewhere the caller is not standing.
        # Scoped to this branch, following build/scripts/generate_adr_index.py:
        # the default check run is read-only and has nothing to protect.
        if not Path.cwd().resolve().is_relative_to(REPO_ROOT.resolve()):
            print(
                "sync-slim-agents: current directory is outside the repository"
                f" root: {Path.cwd()}",
                file=sys.stderr,
            )
            return EXIT_CONFIG
        changed = apply_sync(SLIMMED_AGENTS)
        _report("sync-slim-agents: wrote", changed, total)
        print(
            "Next: run `uv run python build/generate_agents.py` to refresh"
            " src/copilot-cli/ and src/vs-code-agents/."
        )
        print(
            "Then mirror any src/claude/ edit into .claude/agents/. This tool"
            " does not touch the installed copy, and"
            " check_agent_content_parity.py compares the two byte-for-byte."
        )
        return EXIT_OK

    drifted = collect_drift(SLIMMED_AGENTS)
    _report("sync-slim-agents: drifted", drifted, total)
    if drifted:
        print("Run with --write to propagate the src/claude/ bodies.")
        return EXIT_DRIFT
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (OSError, UnicodeDecodeError) as exc:
        # AGENTS.md reserves 3 for an external failure. Letting these escape
        # would exit 1, which this script's own contract reads as "drift
        # found", so a caller would report a drift that was never measured.
        # Same boundary and same pair as build/scripts/generate_adr_index.py.
        print(f"sync-slim-agents: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL


if __name__ == "__main__":
    sys.exit(main())
