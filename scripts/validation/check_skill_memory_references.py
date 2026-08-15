#!/usr/bin/env python3
"""Fail when instructions command a Serena memory read that cannot resolve.

Issue #4897. The pr-comment-responder skill opened with a BLOCKING Phase 0
step that ran ``mcp__serena__read_memory(memory_file_name=
"pr-comment-responder-skills")``. Nothing resolves under that name: the file
is tracked at ``.serena/memories/pr-review/pr-comment-responder-skills.md``,
so Serena lists and reads it as ``pr-review/pr-comment-responder-skills``. An
agent following the instruction literally failed the blocking phase, and
nothing in the repository could tell, because a memory name inside a fenced
Markdown block is only executable when an agent reads it.

This gate makes that class of defect fail at pre-PR time instead.

Canonical contract
------------------
Name-to-path resolution is not invented here. It is copied from
``scripts/validation/memory_index.py::_resolve_memory_reference`` (lines
230-247 at the time of writing), quoted verbatim:

    normalized_name = file_name.replace("\\\\", "/")
    reference_path = memory_path / f"{normalized_name}.md"
    current_path = memory_path
    for path_part in Path(f"{normalized_name}.md").parts:
        current_path /= path_part
        if current_path.is_symlink():
            return None, reference_path, "symbolic link"

    resolved_ref = reference_path.resolve()
    if not resolved_ref.is_relative_to(resolved_memory):
        return None, resolved_ref, "Path traversal"

The memories root is the same default that module uses
(``memory_index.py`` line 1422):

    default=os.environ.get("MEMORY_PATH", ".serena/memories")

Stricter/looser/different than canonical
----------------------------------------
Stricter: ``memory_index.py`` resolves references found in memory index
tables. This gate resolves references found in *instruction* files, which
canonical never reads, and it fails the run rather than reporting an index
inconsistency.

Looser: canonical returns a distinct reason string for a symlinked component
and for path traversal and continues its index audit. This gate collapses both
into one refusal ("does not resolve"), because either shape means an agent
cannot safely read the named memory and the remedy is the same: name a
tracked memory.

Different: canonical is given one reference at a time by its caller. This gate
finds references itself, and it only looks at ``read_memory`` and
``edit_memory`` calls with a literal name. ``write_memory`` is excluded on
purpose: it names a memory to create, so a name that does not resolve yet is
its normal case, not a defect.

Stricter (existence): canonical resolves any safe in-root path without
requiring the target to exist (``memory_index.py:244-247``). This gate adds an
existence requirement: the resolved path must be present in the git index (or,
outside a repository, on the filesystem). A reference that would resolve
canonically but names no tracked file still fails, because an agent issuing
``read_memory`` against it will receive an error at runtime.

What counts as a reference
--------------------------
A ``read_memory`` or ``edit_memory`` call, with or without the
``mcp__serena__`` prefix, carrying a quoted literal ``memory_file_name=`` or
``memory_name=`` argument before the first closing parenthesis. Names holding
a placeholder metacharacter (``$ { } [ ] < > *``) are documentation templates,
not literals, and are skipped.

EXIT CODES (ADR-035):
  0 - every literal reference resolves, OR no corpus root is present, OR the
      memories root is absent (a vendored install ships instructions without
      the upstream memory tree; that is not this gate's failure)
  1 - at least one literal reference does not resolve
  2 - configuration error (the given repo root is not a directory)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tracked_paths import path_exists_in_repo

EXIT_OK = 0
EXIT_UNRESOLVED = 1
EXIT_CONFIG = 2

MEMORIES_ROOT = Path(".serena") / "memories"

# Instruction trees whose Markdown an agent executes verbatim. Skills first
# (the issue's wording), then every agent surface: 51 of the 53 references
# repaired for #4897 lived in agent copies, so a skills-only corpus would have
# left the same defect unguarded in the file where it was most common.
CORPUS_ROOTS: tuple[str, ...] = (
    ".claude/skills",
    "src/copilot-cli/skills",
    "templates/agents",
    ".claude/agents",
    ".github/agents",
    "src/claude",
    "src/copilot-cli/agents",
    "src/vs-code-agents",
)

# Operations that require the named memory to already exist. write_memory is
# deliberately absent; see the module docstring.
_CALL_RE = re.compile(
    r"(?:mcp__serena__)?(?P<operation>read_memory|edit_memory)"
    r"\s*\(\s*(?P<arguments>[^)]*)\)",
    re.DOTALL,
)
_NAME_ARGUMENT_RE = re.compile(
    r"\bmemory(?:_file)?_name\s*=\s*(?P<quote>['\"])(?P<name>[^'\"]*)(?P=quote)"
)

# A name carrying any of these is a template for the reader to fill in.
_PLACEHOLDER_CHARACTERS = frozenset("${}[]<>*")


@dataclass(frozen=True)
class MemoryReference:
    """One literal memory name an instruction file commands a read of."""

    source: Path
    line: int
    operation: str
    name: str


@dataclass(frozen=True)
class Finding:
    """A reference whose name does not resolve to a tracked memory."""

    reference: MemoryReference
    suggestions: tuple[str, ...]


def iter_instruction_files(repo_root: Path) -> list[Path]:
    """Return every Markdown file under a present corpus root, sorted."""
    files: list[Path] = []
    for relative in CORPUS_ROOTS:
        root = repo_root / relative
        if root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def extract_references(path: Path, text: str) -> list[MemoryReference]:
    """Return the literal read/edit memory references named in ``text``."""
    references: list[MemoryReference] = []
    for call in _CALL_RE.finditer(text):
        argument = _NAME_ARGUMENT_RE.search(call.group("arguments"))
        if argument is None:
            continue
        name = argument.group("name")
        if not name or _PLACEHOLDER_CHARACTERS & set(name):
            continue
        references.append(
            MemoryReference(
                source=path,
                line=text.count("\n", 0, call.start()) + 1,
                operation=call.group("operation"),
                name=name,
            )
        )
    return references


def _find_repo_root(start: Path) -> Path:
    """Walk up from start to find the git repository root."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return start.resolve()


def resolves(memories_root: Path, name: str) -> bool:
    """Return whether ``name`` resolves to a tracked memory file.

    Mirrors ``memory_index.py::_resolve_memory_reference``: a backslash is
    normalized to a forward slash, ``.md`` is appended, no path component may
    be a symlink, and the resolved path must stay inside the memories root.

    Existence is resolved from the git index so that untracked or ignored
    working-tree files cannot make the gate pass on a developer machine while
    the same commit fails in CI. Falls back to the filesystem only when the
    repository root is not a git checkout (scratch directories in tests).
    """
    normalized = name.replace("\\", "/")
    reference_path = memories_root / f"{normalized}.md"

    current = memories_root
    for part in Path(f"{normalized}.md").parts:
        current /= part
        if current.is_symlink():
            return False

    resolved_root = memories_root.resolve()
    resolved_reference = reference_path.resolve()
    if not resolved_reference.is_relative_to(resolved_root):
        return False

    # Resolve existence from git index; filesystem fallback for non-repos.
    repo_root = _find_repo_root(memories_root)
    rel_path = str(reference_path.relative_to(repo_root))
    return bool(path_exists_in_repo(repo_root, rel_path))


def index_by_basename(memories_root: Path) -> dict[str, list[str]]:
    """Map each memory's file stem to the scoped names that share it."""
    index: dict[str, list[str]] = defaultdict(list)
    for path in sorted(memories_root.rglob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        name = path.relative_to(memories_root).with_suffix("").as_posix()
        index[path.stem].append(name)
    return index


def collect_findings(
    repo_root: Path,
) -> tuple[int, int, list[Finding]]:
    """Return examined file count, examined reference count, and findings."""
    memories_root = repo_root / MEMORIES_ROOT
    index = index_by_basename(memories_root)

    files = iter_instruction_files(repo_root)
    reference_count = 0
    findings: list[Finding] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            print(
                f"[FAIL] Cannot decode {path.relative_to(repo_root)}: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_CONFIG) from exc
        except OSError as exc:
            print(
                f"[FAIL] Cannot read {path.relative_to(repo_root)}: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_CONFIG) from exc
        for reference in extract_references(path, text):
            reference_count += 1
            if resolves(memories_root, reference.name):
                continue
            basename = reference.name.rsplit("/", 1)[-1]
            findings.append(
                Finding(
                    reference=reference,
                    suggestions=tuple(index.get(basename, ())),
                )
            )
    return len(files), reference_count, findings


def format_report(
    repo_root: Path,
    file_count: int,
    reference_count: int,
    findings: list[Finding],
) -> str:
    """Render the examined counts and every unresolved reference."""
    header = (
        f"{len(findings)} unresolved reference(s) in {reference_count} "
        f"literal memory read(s) across {file_count} instruction file(s)."
    )
    if not findings:
        return f"[PASS] {header}"

    lines = [f"[FAIL] {header}", ""]
    for finding in findings:
        reference = finding.reference
        try:
            location = reference.source.relative_to(repo_root).as_posix()
        except ValueError:
            location = reference.source.as_posix()
        lines.append(
            f"  {location}:{reference.line}: "
            f"{reference.operation} names {reference.name!r}, "
            f"but {MEMORIES_ROOT.as_posix()}/{reference.name}.md is not a "
            f"tracked memory."
        )
        if finding.suggestions:
            options = ", ".join(repr(s) for s in finding.suggestions)
            lines.append(f"      tracked memory with that basename: {options}")
        else:
            lines.append(
                "      no tracked memory shares that basename; name a memory "
                "that exists or write it first."
            )
    lines.append("")
    lines.append(
        "A memory name is a path under "
        f"{MEMORIES_ROOT.as_posix()}/ without the .md suffix, so a memory "
        "in a scope directory must be named with its scope."
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Fail when a skill or agent instruction commands a Serena memory "
            "read whose name does not resolve."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to the script's grandparent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)
    repo_root: Path = args.repo_root

    if not repo_root.is_dir():
        print(f"[FAIL] repo root not found: {repo_root}", file=sys.stderr)
        return EXIT_CONFIG

    if not (repo_root / MEMORIES_ROOT).is_dir():
        print(
            f"[SKIP] {MEMORIES_ROOT.as_posix()} not present; "
            "0 memory references examined."
        )
        return EXIT_OK

    if not any((repo_root / root).is_dir() for root in CORPUS_ROOTS):
        print(
            "[SKIP] no instruction corpus root present "
            f"({', '.join(CORPUS_ROOTS)}); 0 memory references examined."
        )
        return EXIT_OK

    file_count, reference_count, findings = collect_findings(repo_root)
    print(format_report(repo_root, file_count, reference_count, findings))
    return EXIT_UNRESOLVED if findings else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
