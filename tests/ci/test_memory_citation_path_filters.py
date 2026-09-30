"""memory-health.yml and citation-verify.yml path filters cover what the verifiers read.

Issue #5636, decision D14. ``scripts/memory_enhancement/verification.py`` reads
three kinds of local target: a FILE or FUNCTION citation resolves to any
repo-relative path, an ADR citation resolves under
``.project-toolkit/architecture/``, and a MEMORY citation resolves under
``.serena/memories/``. ISSUE, PR, and URL citations read nothing local.

A file or function target has no bounded domain, so no fixed glob list is sound
for it in general. The guard here is therefore twofold: the bounded domains must
be covered, and every target a memory cites today must match a filter glob. The
corpus check is not vacuous: ``test_the_check_detects_an_uncovered_target`` runs
it against a synthetic memory. The corpus holds zero citations at the time of
writing, and the ``examined`` count in the failure message says so.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from memory_enhancement.models import SourceType  # noqa: E402
from memory_enhancement.serena_integration import load_memories  # noqa: E402

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CITATION_WORKFLOWS = ("memory-health.yml", "citation-verify.yml")
PATHS_FILTER_ACTION = "dorny/paths-filter@"
ADR_DIR = ".project-toolkit/architecture"
MEMORIES_DIR = ".serena/memories"
VERIFIER_CODE = "scripts/memory_enhancement/verification.py"
_FUNCTION_RE = re.compile(r"^(?P<path>[^:]+)::[\w][\w-]*$")
_LINE_RE = re.compile(r"^(?P<path>[^:]+)(?::\d+)?$")


def _filters(workflow: str) -> dict[str, list[str]]:
    document = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    steps = document["jobs"]["check-paths"]["steps"]
    step = next(s for s in steps if str(s.get("uses", "")).startswith(PATHS_FILTER_ACTION))
    return yaml.safe_load(step["with"]["filters"])


def _filter_keys_env(workflow: str) -> list[str]:
    document = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    determine = next(
        s for s in document["jobs"]["check-paths"]["steps"] if s.get("id") == "determine"
    )
    return [key.strip() for key in determine["env"]["FILTER_KEYS"].split(",")]


def _all_globs(workflow: str) -> list[str]:
    return [glob for globs in _filters(workflow).values() for glob in globs]


def _covered(path: str, globs: list[str]) -> bool:
    return any(PurePosixPath(path).full_match(glob) for glob in globs)


def _local_target_path(source_type: SourceType, target: str) -> str | None:
    """Repo-relative path a citation makes the verifier read, or None if none."""
    if source_type is SourceType.FUNCTION:
        match = _FUNCTION_RE.match(target)
    elif source_type is SourceType.FILE:
        match = _LINE_RE.match(target)
    elif source_type is SourceType.ADR:
        return f"{ADR_DIR}/{target}"
    elif source_type is SourceType.MEMORY:
        return f"{MEMORIES_DIR}/{target}"
    else:
        return None
    return match.group("path") if match else None


def uncovered_targets(memories_dir: Path, globs: list[str]) -> tuple[list[str], int]:
    """Return ``(uncovered targets, examined citation count)`` for a memory tree."""
    uncovered: list[str] = []
    examined = 0
    for memory in load_memories(memories_dir):
        for citation in memory.citations:
            examined += 1
            path = _local_target_path(citation.source_type, citation.target)
            if path is not None and not _covered(path, globs):
                uncovered.append(f"{memory.memory_id}: {citation.target}")
    return uncovered, examined


@pytest.mark.parametrize("workflow", CITATION_WORKFLOWS)
def test_filter_covers_the_memory_tree_and_the_adr_directory(workflow: str) -> None:
    globs = _all_globs(workflow)
    assert _covered(f"{MEMORIES_DIR}/any-memory.md", globs)
    assert _covered(f"{ADR_DIR}/ADR-042-python-migration-strategy.md", globs)


@pytest.mark.parametrize("workflow", CITATION_WORKFLOWS)
def test_filter_covers_the_verifier_code_it_executes(workflow: str) -> None:
    assert _covered(VERIFIER_CODE, _all_globs(workflow))


@pytest.mark.parametrize("workflow", CITATION_WORKFLOWS)
def test_filter_covers_python_file_targets_under_scripts(workflow: str) -> None:
    assert _covered("scripts/validation/check_example.py", _all_globs(workflow))


@pytest.mark.parametrize("workflow", CITATION_WORKFLOWS)
def test_every_filter_key_feeds_the_should_run_decision(workflow: str) -> None:
    """A filter key missing from FILTER_KEYS is computed and then ignored."""
    assert sorted(_filters(workflow)) == sorted(_filter_keys_env(workflow))


@pytest.mark.parametrize("workflow", CITATION_WORKFLOWS)
def test_filter_has_no_trigger_level_paths(workflow: str) -> None:
    document: dict[str, Any] = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    triggers = document.get("on", document.get(True))
    assert "paths" not in triggers["pull_request"]


@pytest.mark.parametrize("workflow", CITATION_WORKFLOWS)
def test_every_target_cited_by_a_memory_is_covered(workflow: str) -> None:
    uncovered, examined = uncovered_targets(REPO_ROOT / MEMORIES_DIR, _all_globs(workflow))
    assert uncovered == [], (
        f"{workflow} path filter omits {len(uncovered)} of {examined} cited target(s): "
        f"{uncovered[:5]}. Add the path to the cited_targets filter."
    )


def _write_memory(root: Path, citation: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "sample-memory.md").write_text(
        f"# Sample\n\nBody with a citation {citation}.\n", encoding="utf-8"
    )
    return root


def test_the_check_detects_an_uncovered_target(tmp_path: Path) -> None:
    """Positive control: the corpus check must not pass because it examined nothing."""
    root = _write_memory(tmp_path / "mem", "[cite:file](docs/elsewhere/guide.md:3)")
    uncovered, examined = uncovered_targets(root, _all_globs("memory-health.yml"))
    assert examined == 1
    assert uncovered == ["sample-memory: docs/elsewhere/guide.md:3"]


def test_the_check_accepts_a_covered_target(tmp_path: Path) -> None:
    root = _write_memory(tmp_path / "mem", "[cite:function](scripts/validation/x.py::check)")
    uncovered, examined = uncovered_targets(root, _all_globs("citation-verify.yml"))
    assert (uncovered, examined) == ([], 1)


def test_an_adr_citation_maps_under_the_adr_directory(tmp_path: Path) -> None:
    root = _write_memory(tmp_path / "mem", "[cite:adr](ADR-006-thin-workflows-testable-modules.md)")
    uncovered, examined = uncovered_targets(root, _all_globs("memory-health.yml"))
    assert (uncovered, examined) == ([], 1)


def test_an_issue_citation_reads_nothing_local(tmp_path: Path) -> None:
    root = _write_memory(tmp_path / "mem", "[cite:issue](5636)")
    uncovered, examined = uncovered_targets(root, [])
    assert (uncovered, examined) == ([], 1)


def test_a_malformed_function_target_is_not_treated_as_a_path() -> None:
    assert _local_target_path(SourceType.FUNCTION, "no-double-colon.py") is None
