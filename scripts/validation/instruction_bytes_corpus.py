"""Canonical-authored versus generated-projection byte measurement (issue #5400).

Classification comes from ``check_capability_graph`` (ADR-110, issue #5396),
not from a second list. Quoted from that module on this checkout:

    CANONICAL_GLOBS = (
        ("templates/skills", "*.SKILL.md.tmpl"),
        ("templates/agents", "*.md"),
        ("templates/rules", "*.md"),
    )

``PROJECTION_GLOBS`` there lists every generated mirror (``.claude/``,
``src/claude/``, ``src/copilot-cli/``, ``.github/instructions/``,
``.github/agents/``, ``src/vs-code-agents/``). ADR-110 section 3: "a file under
``templates/`` is canonical and a file under [a projection root] is a
projection."

Different than canonical: the graph gate reads frontmatter from those files. This
module only sizes them. It adds three canonical groups the graph gate has no
reason to read (``.agents/governance/*.md``, root ``AGENTS.md``, root
``CLAUDE.md``), because the issue lists governance Markdown as authored
instruction context. It measures the instruction entrypoints the globs name, not
every file under ``src/copilot-cli/``: skill support files (scripts, references)
are outside both lists.

Sizes use ``token_budget.estimate_token_count``, the estimator the existing
instruction budget already uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

# check_capability_graph imports its sibling `instruction_budget_globs` by bare
# name, so scripts/validation must be on sys.path. Importing it by that same bare
# name here, and never through the `scripts.validation.` package prefix, keeps one
# module name per file. The per-file mypy gate runs with MYPYPATH=scripts/validation
# and rejects a file it finds under two names.
_VALIDATION_DIR = str(Path(__file__).resolve().parent)
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

from check_capability_graph import CANONICAL_GLOBS, PROJECTION_GLOBS  # noqa: E402

from scripts.validation.instruction_bytes_types import SizedFile, summarize  # noqa: E402
from scripts.validation.token_budget import estimate_token_count  # noqa: E402

__all__ = [
    "CorpusError",
    "canonical_files",
    "generated_files",
    "measure_corpus",
    "read_sized",
]

_CANONICAL_LABELS = {
    "templates/skills": "skills",
    "templates/agents": "agents",
    "templates/rules": "rules",
}
_EXTRA_CANONICAL: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("governance", ((".agents/governance", "*.md"),)),
    ("root", ((".", "AGENTS.md"), (".", "CLAUDE.md"))),
)


class CorpusError(ValueError):
    """The tree cannot answer the measurement (ADR-035 exit code 2)."""


def _resolve_within(repo_root: Path, rel: str) -> Path | None:
    """Resolve ``rel`` under ``repo_root``, or ``None`` when it escapes (CWE-22).

    Same containment test as ``instruction_budget._resolve_safe``: resolve, then
    require the result to sit under the resolved root, so a symlink or ``..``
    segment cannot leave the repository.
    """
    candidate = (repo_root / rel).resolve()
    return candidate if candidate.is_relative_to(repo_root.resolve()) else None


def read_sized(repo_root: Path, rel: str) -> SizedFile:
    """Measure one repository file, refusing a path that escapes the root (CWE-22)."""
    resolved = _resolve_within(repo_root, rel)
    if resolved is None:
        raise CorpusError(f"{rel} resolves outside the repository")
    if not resolved.is_file():
        raise CorpusError(f"{rel} is not a file")
    content = resolved.read_text(encoding="utf-8", errors="replace")
    return SizedFile(rel, len(content.encode("utf-8")), estimate_token_count(content))


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


def canonical_files(repo_root: Path) -> dict[str, list[SizedFile]]:
    """Return authored files by group. An empty group fails closed."""
    groups: dict[str, list[SizedFile]] = {}
    seen: set[str] = set()
    graph_groups = [(_CANONICAL_LABELS[s], ((s, p),)) for s, p in CANONICAL_GLOBS]
    for label, entries in [*graph_groups, *_EXTRA_CANONICAL]:
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
    for subdir, pattern in PROJECTION_GLOBS:
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
