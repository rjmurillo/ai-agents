"""Canonical-authored versus generated-projection byte measurement (issue #5400).

Canonical means authored: the files a contributor edits. Generated means a
mirror the build renders from them. ADR-110 section 3 draws the line: "a file
under ``templates/`` is canonical and a file under [a projection root] is a
projection." The projection roots come from ``check_capability_graph`` through
``instruction_bytes_graph.projection_globs``, on this checkout:

    .claude/skills/*/SKILL.md      .claude/agents/*.md        .claude/rules/*.md
    src/claude/skills|agents|rules  src/copilot-cli/skills|agents|instructions
    .github/instructions/*.instructions.md   .github/agents/*.agent.md
    src/vs-code-agents/*.agent.md

Different than the capability graph gate: the gate's ``CANONICAL_GLOBS`` name only
the files that may carry a capability block (skill templates, shared agent
bodies, rules). This report counts every authored instruction source, so it also
counts the per-harness agent templates (``*.claude.md.tmpl``, ``*.copilot.md.tmpl``)
and the skill and agent ``partials/``. It adds governance Markdown
(``.agents/governance``) and the root ``AGENTS.md`` and ``CLAUDE.md``. It leaves
out ``templates/hooks``, ``templates/platforms``, and ``toolsets.yaml``, which
configure the build and are not instruction text. Projection counts cover the
instruction entrypoints the globs name, not every file under ``src/copilot-cli/``.

Sizes are raw on-disk bytes. Tokens come from ``token_budget.estimate_token_count``,
the estimator the existing instruction budget uses.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation.instruction_budget import _resolve_safe
from scripts.validation.instruction_bytes_graph import projection_globs
from scripts.validation.instruction_bytes_types import SizedFile, summarize
from scripts.validation.token_budget import estimate_token_count

__all__ = [
    "CorpusError",
    "canonical_files",
    "canonical_paths",
    "generated_files",
    "measure_corpus",
    "read_sized",
]

_CANONICAL_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("skills", (("templates/skills", "**/*"),)),
    ("agents", (("templates/agents", "**/*"),)),
    ("rules", (("templates/rules", "*.md"),)),
    ("governance", ((".agents/governance", "*.md"),)),
    ("root", ((".", "AGENTS.md"), (".", "CLAUDE.md"))),
)


class CorpusError(ValueError):
    """The tree cannot answer the measurement (ADR-035 exit code 2)."""


def read_sized(repo_root: Path, rel: str) -> SizedFile:
    """Measure one repository file, refusing a path that escapes the root (CWE-22)."""
    resolved = _resolve_safe(repo_root, rel)
    if resolved is None:
        raise CorpusError(f"{rel} resolves outside the repository")
    if not resolved.is_file():
        raise CorpusError(f"{rel} is not a file")
    data = resolved.read_bytes()
    return SizedFile(rel, len(data), estimate_token_count(data.decode("utf-8", errors="replace")))


def _expand(repo_root: Path, subdir: str, pattern: str) -> list[str]:
    tree = repo_root / subdir
    if not tree.is_dir():
        return []
    return sorted(p.relative_to(repo_root).as_posix() for p in tree.glob(pattern) if p.is_file())


def _measure_entries(
    repo_root: Path, entries: tuple[tuple[str, str], ...], seen: set[str]
) -> list[SizedFile]:
    files: list[SizedFile] = []
    for subdir, pattern in entries:
        for rel in _expand(repo_root, subdir, pattern):
            if rel not in seen:
                seen.add(rel)
                files.append(read_sized(repo_root, rel))
    return files


def canonical_paths(repo_root: Path) -> list[str]:
    """Return every authored file path, relative and sorted per group; empty groups are fine."""
    seen: set[str] = set()
    paths: list[str] = []
    for _label, entries in _CANONICAL_GROUPS:
        for subdir, pattern in entries:
            for rel in _expand(repo_root, subdir, pattern):
                if rel not in seen:
                    seen.add(rel)
                    paths.append(rel)
    return paths


def canonical_files(repo_root: Path) -> dict[str, list[SizedFile]]:
    """Return authored files by group. An empty group fails closed."""
    groups: dict[str, list[SizedFile]] = {}
    seen: set[str] = set()
    for label, entries in _CANONICAL_GROUPS:
        files = _measure_entries(repo_root, entries, seen)
        if not files:
            raise CorpusError(f"canonical group `{label}` holds no files")
        groups[label] = files
    return groups


def _family(subdir: str) -> str:
    parts = subdir.split("/")
    return "/".join(parts[:2]) if parts[0] == "src" else parts[0]


def generated_files(repo_root: Path) -> dict[str, list[SizedFile]]:
    """Return generated projection files by family. A missing tree counts as zero."""
    families: dict[str, list[SizedFile]] = {}
    seen: set[str] = set()
    for subdir, pattern in projection_globs():
        found = _measure_entries(repo_root, ((subdir, pattern),), seen)
        if found:
            families.setdefault(_family(subdir), []).extend(found)
    return dict(sorted(families.items()))


def measure_corpus(
    repo_root: Path,
) -> tuple[dict[str, list[SizedFile]], dict[str, list[SizedFile]]]:
    """Return ``(canonical, generated)`` file groups."""
    return canonical_files(repo_root), generated_files(repo_root)


def group_summary(groups: dict[str, list[SizedFile]]) -> dict[str, object]:
    """Return per-group totals plus a ``total`` over every group."""
    every = [f for files in groups.values() for f in files]
    return {
        "groups": {name: summarize(files) for name, files in groups.items()},
        "total": summarize(every),
    }
