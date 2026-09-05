#!/usr/bin/env python3
# taste-lint: ignore file-size, kept whole while PR #5526 scopes edits to two files.
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

The body is not copied verbatim either. Each destination declares a
`transforms` tuple that `transformed_body` applies in order, rewriting the
source body into that tree's own vocabulary. Both current destinations declare
the same single transform: strip the literal `mcp__github__` prefix, so
`mcp__github__pull_request_read` reaches a mirror as `pull_request_read`.
Measured on this branch with `grep -rhoE "mcp__[a-z0-9]+__" <tree>/*.md`,
`src/claude/` holds 26 `mcp__github__` occurrences against 0 in each
destination tree, while `mcp__serena__` appears in all three (83, 31, 40) and
is left alone.

Most divergence is not mechanizable, so the copy is refused rather than
attempted wherever the two disagree. Of the 48 line pairs the trees currently
replace, exactly 10 are that one prefix rule; the other 38 are destination
wording no transform reproduces, including the `mcp__deepwiki__` and
`mcp__context7__` sentences the mirrors reworded instead of stripping.
`reconciliation_blockages` compares each destination body against its
transformed source body with `difflib.SequenceMatcher` and treats `replace`
and `delete` as blocking. `--write` then exits 2 and writes nothing, naming
every blocked file and line. `--check` reports those same files as drift it
cannot mechanize, counted apart from drift it can apply.

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
        the checkout, or opens a `---` block it never closes; or a destination
        carries body wording the transforms cannot reproduce; or `--write` was
        invoked from outside the checkout that holds this script
    3 - external failure: a read or write raised OSError or UnicodeDecodeError

A destination is published with a temp file plus `os.replace`, so a failed
write leaves the previous content in place rather than an empty or partial
agent.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TextIO

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


@dataclass(frozen=True, slots=True)
class Transform:
    """One mechanical rewrite a destination applies to the source body.

    `why` records the evidence for the rule rather than restating the rule. A
    transform nobody measured is a guess about what a mirror wants, and a wrong
    guess here rewrites nine agent files in two trees at once.
    """

    pattern: re.Pattern[str]
    replacement: str
    why: str

    def apply(self, text: str) -> str:
        return self.pattern.sub(self.replacement, text)


# Both mirror trees take this one rule, and only this one.
MIRROR_TRANSFORMS: tuple[Transform, ...] = (
    Transform(
        pattern=re.compile(r"mcp__github__"),
        replacement="",
        why=(
            'grep -rhoE "mcp__[a-z0-9]+__" over the three trees counts 26'
            " mcp__github__ in src/claude/ against 0 in templates/agents/ and 0"
            " in .github/agents/, so both mirrors strip that prefix with no"
            " exception. mcp__serena__ is deliberately not here: it appears in"
            " all three trees (83, 31, 40), so stripping it would rewrite 71"
            " mirror lines that are already correct."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Destination:
    """One hand-maintained mirror of an agent body."""

    label: str
    directory: Path
    suffix: str
    transforms: tuple[Transform, ...]

    def path_for(self, name: str) -> Path:
        return self.directory / f"{name}{self.suffix}"


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


def _opens_frontmatter(text: str) -> bool:
    """True when the text starts with a line that is exactly `---`.

    A file whose entire content is `---` opens a block with no newline after
    it. Requiring the newline would classify that file as having no
    frontmatter, and `--write` would then replace the whole thing with the
    source body instead of refusing it.
    """
    return text.startswith("---\n") or text == "---"


def _frontmatter_end(text: str) -> int | None:
    """Return the index just past the closing `---` line, or None if absent.

    The search starts at the newline that closes the opening delimiter, not
    past it, so an empty block (`---` on one line and `---` on the next) is
    terminated rather than unterminated. A closing delimiter that ends the
    file with no trailing newline counts too. Both shapes are legal
    frontmatter, and `main` now rejects an unterminated block outright, so
    misreading either one would refuse to sync a valid file.
    """
    if not _opens_frontmatter(text):
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
    return _opens_frontmatter(text) and _frontmatter_end(text) is None


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


def transformed_body(source_body: str, destination: Destination) -> str:
    """Return the source body rewritten into `destination`'s own vocabulary.

    Transforms apply in declaration order, so a later rule sees what an earlier
    one produced. Every read of a source body on its way to a mirror goes
    through here, which is what keeps `--check` and `--write` from disagreeing
    about what a destination should hold.
    """
    for transform in destination.transforms:
        source_body = transform.apply(source_body)
    return source_body


@dataclass(frozen=True, slots=True)
class Blockage:
    """One destination line the transform layer cannot reproduce.

    `line` is 1-based and indexes the destination file, frontmatter included,
    so it matches what an editor shows. `source_text` is None when the source
    has no counterpart at all, which is the `delete` case below; an empty
    string there would be indistinguishable from a blank source line.
    """

    line: int
    destination_text: str
    source_text: str | None


def reconciliation_blockages(
    destination_body: str, source_body: str, line_offset: int = 0
) -> tuple[Blockage, ...]:
    """Return the destination lines a copy of `source_body` would lose.

    `difflib.SequenceMatcher` over the two line lists yields three non-equal
    opcodes, and exactly one of them is safe to write through:

    - `insert`: the source has lines the destination lacks. When inserts are
      the only opcodes, the destination body is exactly the transformed source
      minus some lines, so writing the transformed source adds content and
      loses nothing. Safe.
    - `replace`: the destination says the same thing in wording the transforms
      did not produce. Writing would overwrite a hand-made adaptation with the
      Claude phrasing. Blocking.
    - `delete`: the destination carries a line the source does not, such as the
      `vendor-portability` declaration comment in
      `templates/agents/implementer.shared.md`. Writing would drop it.
      Blocking.

    A blocking opcode reports one entry per destination line it covers, paired
    with the source line at the same offset when the block has one. Naming
    `insert` in the safe set is a statement of policy rather than the
    mechanism that enforces it: an insert covers no destination line, so the
    loop below would emit nothing for one even if it were not filtered out. `autojunk`
    is off because its heuristic drops lines that repeat in more than 1% of a
    long sequence, and a blank line or a `| --- |` table rule qualifies; a
    dropped line cannot be reported as blocking.
    """
    destination_lines = destination_body.splitlines()
    source_lines = source_body.splitlines()
    matcher = difflib.SequenceMatcher(
        None, destination_lines, source_lines, autojunk=False
    )
    blocked: list[Blockage] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("replace", "delete"):
            continue
        for offset in range(i2 - i1):
            paired = j1 + offset
            blocked.append(
                Blockage(
                    line=line_offset + i1 + offset + 1,
                    destination_text=destination_lines[i1 + offset],
                    source_text=source_lines[paired] if paired < j2 else None,
                )
            )
    return tuple(blocked)


@dataclass(frozen=True, slots=True)
class Comparison:
    """One destination file, what it would become, and whether it may change."""

    target: Path
    in_sync: bool
    updated: str
    blockages: tuple[Blockage, ...]


def compare(agents: tuple[str, ...]) -> list[Comparison]:
    """Classify every declared destination file in one pass.

    Both modes read this list, so a file `--check` calls unmechanizable is the
    same file `--write` refuses, computed the same way from the same bytes.
    """
    comparisons: list[Comparison] = []
    for name in agents:
        _, source_body = split_frontmatter(_read(AGENT_SOURCE / f"{name}.md"))
        for destination in DESTINATIONS:
            target = destination.path_for(name)
            current = _read(target)
            frontmatter, current_body = split_frontmatter(current)
            body = transformed_body(source_body, destination)
            updated = rendered_content(body, current)
            comparisons.append(
                Comparison(
                    target=target,
                    in_sync=updated == current,
                    updated=updated,
                    blockages=reconciliation_blockages(
                        current_body, body, frontmatter.count("\n")
                    ),
                )
            )
    return comparisons


@dataclass(frozen=True, slots=True)
class Drift:
    """The three outcomes `--check` has to tell apart.

    Reporting only "drifted" merges the last two, and they call for opposite
    actions: one is cleared by running `--write`, the other is cleared by a
    person reconciling wording `--write` refuses to touch.
    """

    in_sync: tuple[str, ...]
    applicable: tuple[str, ...]
    blocked: tuple[Comparison, ...]

    @property
    def examined(self) -> int:
        return len(self.in_sync) + len(self.applicable) + len(self.blocked)


def collect_drift(agents: tuple[str, ...]) -> Drift:
    """Sort every destination file into the three outcomes, in one pass."""
    comparisons = compare(agents)
    return Drift(
        in_sync=tuple(
            _relative(item.target) for item in comparisons if item.in_sync
        ),
        applicable=tuple(
            _relative(item.target)
            for item in comparisons
            if not item.in_sync and not item.blockages
        ),
        blocked=tuple(item for item in comparisons if item.blockages),
    )


def apply_sync(agents: tuple[str, ...]) -> list[str]:
    """Write the transformed Claude body into every destination.

    Returns the repo-relative paths changed. A blocked file is skipped rather
    than written. `_preflight` already refused the whole run in that case, so
    the skip is unreachable from the CLI; it is here so that a direct caller
    of this function cannot lose destination wording either.
    """
    changed: list[str] = []
    for comparison in compare(agents):
        if comparison.in_sync or comparison.blockages:
            continue
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


def _report(label: str, paths: list[str], total: int) -> None:
    print(f"{label}: {len(paths)} of {total} destination files")
    for path in paths:
        print(f"  {path}")


# A mirror body carries markdown table rows several hundred characters wide.
# Printed whole, one of them scrolls every other finding off the screen.
_EXCERPT_WIDTH = 76


def _excerpt(text: str) -> str:
    """Trim one reported line so a long row cannot bury the rest of the report."""
    if len(text) <= _EXCERPT_WIDTH:
        return text
    return text[: _EXCERPT_WIDTH - 3] + "..."


def _print_blockages(blockages: Iterable[Blockage], stream: TextIO) -> None:
    """Print both sides of every blocked line, so the reader can reconcile them."""
    for blockage in blockages:
        source = (
            "(no matching source line)"
            if blockage.source_text is None
            else _excerpt(blockage.source_text)
        )
        print(
            f"    line {blockage.line} destination: "
            f"{_excerpt(blockage.destination_text)}",
            file=stream,
        )
        print(f"    line {blockage.line} source:      {source}", file=stream)


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
        _print_blockages(comparison.blockages, sys.stderr)
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
        blocked = collect_drift(SLIMMED_AGENTS).blocked
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
    for path in drift.applicable:
        print(f"  can apply: {path}")
    for comparison in drift.blocked:
        print(f"  cannot mechanize: {_relative(comparison.target)}")
        _print_blockages(comparison.blockages, sys.stdout)
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

    return _report_check(collect_drift(SLIMMED_AGENTS))


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
