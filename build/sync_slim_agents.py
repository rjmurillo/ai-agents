#!/usr/bin/env python3
"""Propagate a slimmed agent body from `src/claude/` to its sibling copies.

`build/AGENTS.md` Rule 2 states the manual procedure this automates: when a
Claude agent receives a universal change, the same change is duplicated into
`templates/agents/{name}.shared.md`. `.serena/memories/decision-two-pipeline-agent-mirror-recipe.md`
widens that to the other hand-maintained copies. This script performs the body
copy for the agents listed in `SLIMMED_AGENTS`.

This module owns the files: which agents are mirrored, where they live, path
safety, the atomic write, the CLI and the exit codes. What a body becomes on
the way to a mirror belongs to the sibling `sync_slim_agents_reconcile.py`;
read its docstring for the frontmatter schemas, the `mcp__github__` rule and
its measurement, and the reconciliation opcodes.

A destination it cannot reproduce blocks the run: `--write` exits 2 and writes
nothing, and `--check` counts those files apart from the ones it can sync. On
the live tree that is 7 of the 18 declared files.

`src/claude/` is the source and never a destination. Its own `AGENTS.md`
tabulates `src/claude/` as the source for Claude Code agents, marked "Edit
here", against `.claude/agents/` as the installed runtime copy, marked "DO NOT
edit directly", and names copying the installed tree back over the source as a
common mistake that can drop blocking gates. So `.claude/agents/` is neither
read nor written here, and an edit that started in `src/claude/` still has to
reach that installed copy by its own route;
`build/scripts/check_agent_content_parity.py` compares those two trees
byte-for-byte on every PR through `pre_pr.py` and fails until it does.

Nor does this regenerate the derived trees. After a `--write` run, run
`uv run python build/generate_agents.py` to refresh `src/copilot-cli/` and
`src/vs-code-agents/`. Both follow-ups are printed after a write.

Default mode is `--check`: report drift and exit non-zero, mutating nothing.
`--write` performs the copy. The asymmetry is deliberate. Four of the nine
agents currently differ between `src/claude/` and `templates/agents/`, so a
tool that wrote by default would turn an inspection into a large content change.

Exit codes follow ADR-035:
    0 - no drift (--check), or the sync completed (--write)
    1 - drift found (--check only)
    2 - configuration error: a declared file is missing, is a symlink or escapes
        the checkout, or opens a `---` block it never closes; or a destination
        carries body wording the transforms cannot reproduce; or `--write` was
        invoked from outside the checkout that holds this script
    3 - external failure: a read or write raised OSError or UnicodeDecodeError
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
import sys
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePath
from types import ModuleType
from typing import TYPE_CHECKING

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source of truth for the body. Every destination below takes its body from here.
AGENT_SOURCE = REPO_ROOT / "src" / "claude"

# os.O_NOFOLLOW is absent on some platforms, notably Windows, and os.O_BINARY
# exists only there. Fall back to 0 so the flags compose either way. Follows
# src/copilot-cli/skills/spec/scripts/metrics_writer.py, whose module docstring
# records the reasoning: the kernel makes the no-follow decision atomically with
# the open, closing the CWE-367 window between the containment check and the
# access. O_BINARY keeps newline handling in the text wrapper alone, where
# Path.read_text and Path.write_text had it, instead of translating twice.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


class UnsafePathError(Exception):
    """A declared path is a symlink or resolves outside the repository root."""


def _load_reconcile() -> ModuleType:
    """Load the sibling text layer without mutating `sys.path`.

    Canonical source (`.claude/rules/canonical-source-mirror.md`):
    `build/generate_agents_common.py`'s `_load_model_pin_manifest_exports`,
    whose docstring states the contract verbatim, it "loads a sibling
    build-tree module via ``importlib.util.spec_from_file_location`` and
    ``exec_module`` specifically so that importing the *loading* module never
    touches ``sys.path``". A plain import would not resolve here anyway: this
    module is itself loaded by file location, by the three test modules under
    `tests/build_scripts/`.

    Different than canonical: it registers in `sys.modules` before executing.
    The sibling defines `@dataclass(slots=True)` classes, and building a
    slotted class runs `dataclasses._is_type`, which reads
    `sys.modules.get(cls.__module__).__dict__`. Unregistered that is None and
    the import dies with `'NoneType' object has no attribute '__dict__'`,
    nowhere near the line that caused it.
    """
    path = Path(__file__).resolve().parent / "sync_slim_agents_reconcile.py"
    spec = importlib.util.spec_from_file_location("_sync_slim_reconcile", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load build utility {path}: no import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        del sys.modules[spec.name]
        raise ImportError(f"Cannot load build utility {path}: {exc}") from exc
    return module


# Two readers. mypy takes the type-checking branch, where a plain import
# resolves because `build/` holds no `__init__.py`; nothing there runs, so the
# no-`sys.path` guarantee above still holds. Reading the sibling as a bare
# `ModuleType` instead leaves `Drift` a variable rather than a type and every
# attribute read on one unknown, 24 errors of that one shape, which
# `typing.cast` cannot fix because the missing thing is the type itself.
if TYPE_CHECKING:
    import sync_slim_agents_reconcile as _reconcile
else:
    _reconcile = _load_reconcile()

Comparison = _reconcile.Comparison
Destination = _reconcile.Destination
Drift = _reconcile.Drift
MIRROR_TRANSFORMS = _reconcile.MIRROR_TRANSFORMS
collect_drift = _reconcile.collect_drift
compare_file = _reconcile.compare_file
has_unterminated_frontmatter = _reconcile.has_unterminated_frontmatter
print_blockages = _reconcile.print_blockages
split_frontmatter = _reconcile.split_frontmatter


DESTINATIONS: tuple[Destination, ...] = (
    Destination(
        "templates/agents",
        REPO_ROOT / "templates" / "agents",
        ".shared.md",
        MIRROR_TRANSFORMS,
    ),
    Destination(
        ".github/agents",
        REPO_ROOT / ".github" / "agents",
        ".agent.md",
        MIRROR_TRANSFORMS,
    ),
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


def _relative(path: PurePath) -> str:
    """Return the repo-relative path with forward slashes on every platform.

    `str()` on a Windows path yields backslashes, which would make the drift
    report and the error output disagree with the repository-style paths this
    script documents and its tests assert.
    """
    return path.relative_to(REPO_ROOT).as_posix()


def _within_repo(path: Path) -> Path:
    """Return the resolved path, refusing a symlink or an escape from the root.

    A plain open follows symlinks, so a mirror file replaced by a link to
    somewhere else would let `--write` overwrite a file outside the checkout.
    Every read and write below goes through here and uses the returned resolved
    path, so the check and the access cannot disagree. This check is the
    portable first gate; `_read` and `_write` also pass `O_NOFOLLOW`, which
    closes the window between this check and the open itself.
    """
    resolved = path.resolve(strict=False)
    if path.is_symlink() or not resolved.is_relative_to(REPO_ROOT.resolve()):
        raise UnsafePathError(_relative(path))
    return resolved


def _read(path: Path) -> str:
    descriptor = os.open(_within_repo(path), os.O_RDONLY | _O_NOFOLLOW | _O_BINARY)
    with open(descriptor, encoding="utf-8") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    """Publish `text` at `path` atomically, following generate_adr_index.py.

    Truncating the destination and then writing into it leaves an empty or
    half-written agent behind if the write fails partway. A temp file in the
    same directory plus `os.replace` makes the destination change in one step
    or not at all. `os.replace` also does not follow a symlink at the
    destination: it swaps the directory entry, so it needs no `O_NOFOLLOW`
    counterpart the way `_read` does.
    """
    target = _within_repo(path)
    # The preflight proved this is an existing regular file, so its mode is
    # worth preserving: mkstemp creates at 0600 and os.replace publishes that
    # verbatim, which would silently narrow a world-readable agent.
    mode = target.stat().st_mode & 0o777
    descriptor, temporary = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            # Widened only after the write, so the file spends its writable
            # life at mkstemp's own restrictive default.
            os.chmod(temporary, mode)
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


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


def compare(agents: tuple[str, ...]) -> Drift:
    """Read every declared pair and sort it into the three outcomes.

    Both modes call this, so a file `--check` calls unmechanizable is the same
    file `--write` refuses, computed the same way from the same bytes.
    """
    comparisons: list[Comparison] = []
    for name in agents:
        _, source_body = split_frontmatter(_read(AGENT_SOURCE / f"{name}.md"))
        for destination in DESTINATIONS:
            target = destination.path_for(name)
            comparisons.append(
                compare_file(
                    target, source_body, _read(target), destination.transforms
                )
            )
    return collect_drift(comparisons)


def apply_sync(drift: Drift) -> list[str]:
    """Write the body into every destination that may take one.

    Returns the repo-relative paths changed. Takes the whole `Drift` and reads
    only `applicable`, so a blocked file is not skipped by a guard here, it is
    never handed over: the set this walks is by construction the set that is
    neither in sync nor blocked.
    """
    changed: list[str] = []
    for comparison in drift.applicable:
        _write(comparison.target, comparison.updated)
        changed.append(_relative(comparison.target))
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


def _config_error(header: str, paths: list[str], remedy: str) -> int:
    print(f"sync-slim-agents: {header}", file=sys.stderr)
    for path in paths:
        print(f"  {path}", file=sys.stderr)
    print(remedy, file=sys.stderr)
    return EXIT_CONFIG


def _blocked_error(blocked: tuple[Comparison, ...]) -> int:
    """Refuse the whole run and show every line that would be overwritten."""
    print(
        "sync-slim-agents: destinations carry body wording the transforms"
        " cannot reproduce:",
        file=sys.stderr,
    )
    for comparison in blocked:
        print(f"  {_relative(comparison.target)}", file=sys.stderr)
        print_blockages(comparison.blockages, sys.stderr)
    print(
        "Reconcile each line by hand, or declare a transform that produces the"
        " destination wording. Refusing to write anything.",
        file=sys.stderr,
    )
    return EXIT_CONFIG


def _preflight(for_write: bool) -> int:
    """Return EXIT_CONFIG when any declared file is unusable, else EXIT_OK.

    Ordered so no stage touches a file an earlier stage rejected: existence
    first, then path safety, then frontmatter shape and the reconciliation
    guard, which are the stages that read content. Runs before both modes, so
    a rejected tree is reported without a single write.

    The guard is the one stage scoped to `--write`. A destination the
    transforms cannot reproduce is a reason to refuse a copy, not a reason to
    refuse an inspection, so `--check` reports it as drift it cannot mechanize
    and still exits 1 rather than 2.
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

    if for_write:
        blocked = compare(SLIMMED_AGENTS).blocked
        if blocked:
            return _blocked_error(blocked)

    return EXIT_OK


def _report_check(drift: Drift) -> int:
    """Print the three counts and return the exit status.

    `.claude/rules/ci-scripts.md` MUST 12: the examined count is printed on
    every run, so a clean tree and an empty tree do not read the same.
    """
    print(
        f"sync-slim-agents: examined {drift.examined} destination files:"
        f" {len(drift.in_sync)} in sync, {len(drift.applicable)} with drift"
        f" --write can apply, {len(drift.blocked)} with drift it cannot"
        " mechanize"
    )
    for comparison in drift.applicable:
        print(f"  can apply: {_relative(comparison.target)}")
    for comparison in drift.blocked:
        print(f"  cannot mechanize: {_relative(comparison.target)}")
        print_blockages(comparison.blockages, sys.stdout)
    if drift.applicable:
        print("Run with --write to propagate the src/claude/ bodies.")
    if drift.blocked:
        print(
            "Reconcile the lines above by hand. --write refuses the whole run"
            " while any remain."
        )
    if drift.applicable or drift.blocked:
        return EXIT_DRIFT
    return EXIT_OK


def _run(args: argparse.Namespace) -> int:
    preflight = _preflight(for_write=args.write)
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
        changed = apply_sync(compare(SLIMMED_AGENTS))
        print(
            f"sync-slim-agents: wrote: {len(changed)} of {total}"
            " destination files"
        )
        for path in changed:
            print(f"  {path}")
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

    return _report_check(compare(SLIMMED_AGENTS))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except UnsafePathError as exc:
        # The preflight cleared every declared path, but a check and a later
        # access are separate operations: an entry can become a symlink in
        # between. That is a configuration failure, not drift, and exit 1
        # would read as drift.
        print(
            f"sync-slim-agents: path became unsafe after the preflight: {exc}",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    except (OSError, UnicodeDecodeError) as exc:
        # AGENTS.md reserves 3 for an external failure. Letting these escape
        # would exit 1, which this script's own contract reads as "drift
        # found", so a caller would report a drift that was never measured.
        # Same boundary and same pair as build/scripts/generate_adr_index.py.
        print(f"sync-slim-agents: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL


if __name__ == "__main__":
    sys.exit(main())
