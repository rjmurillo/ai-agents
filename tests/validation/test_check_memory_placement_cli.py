"""CLI-level tests for scripts/validation/check_memory_placement.py (#5391).

Split out of ``test_check_memory_placement.py`` at the project's 500-line
ceiling (`.claude/rules/code-quality.md`). Memory fixtures and the process
helpers are imported from that sibling rather than duplicated, matching the
pattern used by ``test_agent_skill_discriminator_baseline.py``.

Covers every ADR-035 exit the CLI can produce: 0 for a clean run and for each
escape hatch, 1 for a flagged memory and for a baseline regression, 2 for each
config error.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import scripts.validation.check_memory_placement as cmod
from tests.validation.test_check_memory_placement import (
    EVIDENCE_MEMORY,
    MAXIMAL_MEMORY,
    NORMATIVE_MEMORY,
    SCRIPT,
    run_cli,
    scaffold,
    write_baseline,
    write_memory,
)

# ---------------------------------------------------------------------------
# Exit 1: violations
# ---------------------------------------------------------------------------


def test_cli_flags_normative_memory(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "protocol/release.md", NORMATIVE_MEMORY)
    proc = run_cli(repo, [rel])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL: 1 placement violations in 1 memory files examined" in proc.stdout
    assert rel in proc.stdout
    assert cmod.RULE_PATH in proc.stdout


def test_cli_reads_changed_files_from_environment(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "protocol/release.md", NORMATIVE_MEMORY)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={**os.environ, "CHANGED_FILES": rel},
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert rel in proc.stdout


# ---------------------------------------------------------------------------
# Exit 0: clean runs and escape hatches
# ---------------------------------------------------------------------------


def test_cli_passes_evidence_memory(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "ci/aggregate.md", EVIDENCE_MEMORY)
    proc = run_cli(repo, [rel])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS: 0 placement violations in 1 memory files examined" in proc.stdout


def test_cli_reports_zero_examined_when_nothing_changed(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    write_memory(repo, "ci/aggregate.md", EVIDENCE_MEMORY)
    proc = run_cli(repo, ["AGENTS.md"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Examined 0 memory files" in proc.stdout


def test_cli_honors_frontmatter_exception(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    content = "---\nplacement_exception: verbatim copy of a deleted rule\n---\n"
    rel = write_memory(repo, "protocol/release.md", content + NORMATIVE_MEMORY)
    proc = run_cli(repo, [rel])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "exception=verbatim copy of a deleted rule" in proc.stdout


def test_cli_honors_pr_body_override(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "protocol/release.md", NORMATIVE_MEMORY)
    proc = run_cli(repo, [rel], pr_body="[memory-placement: rule lands in #5392]")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PR override present: rule lands in #5392" in proc.stdout


def test_paths_outside_the_memory_root_are_filtered_before_resolution(
    tmp_path: Path,
) -> None:
    """A traversal that is not a memory path never reaches the resolver."""
    repo = scaffold(tmp_path)
    proc = run_cli(repo, ["../.serena/memories/evil.md"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Examined 0 memory files" in proc.stdout


# ---------------------------------------------------------------------------
# Baseline ratchet
# ---------------------------------------------------------------------------


def test_baseline_allows_recorded_score(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "protocol/release.md", NORMATIVE_MEMORY)
    baseline = write_baseline(repo, {rel: 3})
    proc = run_cli(repo, [rel], extra=["--baseline", baseline])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "baseline=3" in proc.stdout


def test_baseline_fails_a_rise_above_the_recorded_score(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "protocol/release.md", MAXIMAL_MEMORY)
    baseline = write_baseline(repo, {rel: 3})
    proc = run_cli(repo, [rel], extra=["--baseline", baseline])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "(regression)" in proc.stdout


def test_baseline_absent_entry_uses_the_plain_threshold(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "protocol/release.md", NORMATIVE_MEMORY)
    baseline = write_baseline(repo, {".serena/memories/other.md": 3})
    proc = run_cli(repo, [rel], extra=["--baseline", baseline])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "baseline=new" in proc.stdout


# ---------------------------------------------------------------------------
# Exit 2: config errors
# ---------------------------------------------------------------------------


def test_missing_repo_root_is_config_error(tmp_path: Path) -> None:
    proc = run_cli(tmp_path / "nope", [])
    assert proc.returncode == 2
    assert "Repo root not found" in proc.stderr


def test_missing_memories_directory_is_config_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    proc = run_cli(repo, [])
    assert proc.returncode == 2
    assert "Memories directory not found" in proc.stderr


def test_missing_changed_memory_is_config_error(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    proc = run_cli(repo, [".serena/memories/ghost.md"])
    assert proc.returncode == 2
    assert "Config error" in proc.stderr


def test_path_traversal_is_config_error(tmp_path: Path) -> None:
    """A path that passes the memory filter but escapes the root is refused."""
    repo = scaffold(tmp_path)
    proc = run_cli(repo, [".serena/memories/../../../outside/evil.md"])
    assert proc.returncode == 2
    assert "escapes repo root" in proc.stderr


def test_missing_baseline_file_is_config_error(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "ci/aggregate.md", EVIDENCE_MEMORY)
    proc = run_cli(repo, [rel], extra=["--baseline", "scripts/validation/absent.json"])
    assert proc.returncode == 2
    assert "Could not read baseline" in proc.stderr


def test_invalid_baseline_score_is_config_error(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "ci/aggregate.md", EVIDENCE_MEMORY)
    baseline = write_baseline(repo, {rel: 9})
    proc = run_cli(repo, [rel], extra=["--baseline", baseline])
    assert proc.returncode == 2
    assert "outside the valid range" in proc.stderr


def test_baseline_outside_repo_root_is_config_error(tmp_path: Path) -> None:
    repo = scaffold(tmp_path)
    rel = write_memory(repo, "ci/aggregate.md", EVIDENCE_MEMORY)
    outside = tmp_path / "outside.json"
    outside.write_text('{"files": {}}\n', encoding="utf-8")
    proc = run_cli(repo, [rel], extra=["--baseline", str(outside)])
    assert proc.returncode == 2


def test_full_corpus_without_git_is_config_error(tmp_path: Path) -> None:
    """--all reads a named ref and refuses to fall back to a directory walk."""
    repo = scaffold(tmp_path)
    write_memory(repo, "ci/aggregate.md", EVIDENCE_MEMORY)
    proc = run_cli(repo, [], extra=["--all"])
    assert proc.returncode == 2
    assert "Cannot list the files tracked at HEAD" in proc.stderr
