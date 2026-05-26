"""Tests for scripts/validation/check_spec_id_uniqueness.py (Issue #2068).

Pins behaviour of the duplicate-spec-id gate:

- pos: a unique-ID tree returns exit 0
- neg: a tree with a colliding `id:` returns exit 1
- edge: README files are excluded; non-frontmatter `id:` mentions are ignored;
  missing specs directory returns exit 2 (config error per ADR-035)
- branch: each of the three category directories is independently checked
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_spec_id_uniqueness.py"


def _make_spec(dir_path: Path, name: str, spec_id: str, body: str = "") -> Path:
    """Write a minimal spec file with the given `id:` in YAML frontmatter."""
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / name
    path.write_text(
        textwrap.dedent(
            f"""\
            ---
            id: {spec_id}
            title: test
            ---

            # {spec_id}
            {body}
            """
        ),
        encoding="utf-8",
    )
    return path


def _run(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )


def _scaffold(tmp_path: Path) -> Path:
    """Create the three category dirs under tmp_path/.agents/specs/."""
    specs = tmp_path / ".agents" / "specs"
    for cat in ("requirements", "design", "tasks"):
        (specs / cat).mkdir(parents=True)
    return specs


# ---- positive ----------------------------------------------------------------


def test_unique_ids_pass(tmp_path: Path) -> None:
    """All-unique tree exits 0 with a [PASS] line."""
    specs = _scaffold(tmp_path)
    _make_spec(specs / "requirements", "REQ-001-a.md", "REQ-001")
    _make_spec(specs / "requirements", "REQ-002-b.md", "REQ-002")
    _make_spec(specs / "design", "DESIGN-001-a.md", "DESIGN-001")
    _make_spec(specs / "tasks", "TASK-001-a.md", "TASK-001")

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "[PASS]" in result.stdout


# ---- negative ----------------------------------------------------------------


def test_duplicate_requirement_ids_fail(tmp_path: Path) -> None:
    """Two REQ files with the same `id:` exits 1 and names both files."""
    specs = _scaffold(tmp_path)
    a = _make_spec(specs / "requirements", "REQ-009-a.md", "REQ-009")
    b = _make_spec(specs / "requirements", "REQ-009-b.md", "REQ-009")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "REQ-009" in result.stdout
    assert a.name in result.stdout
    assert b.name in result.stdout


def test_duplicate_design_ids_fail(tmp_path: Path) -> None:
    """Design-category duplicate is detected independently of requirements."""
    specs = _scaffold(tmp_path)
    _make_spec(specs / "design", "DESIGN-009-a.md", "DESIGN-009")
    _make_spec(specs / "design", "DESIGN-009-b.md", "DESIGN-009")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "DESIGN-009" in result.stdout


def test_duplicate_task_ids_fail(tmp_path: Path) -> None:
    """Task-category duplicate is detected independently."""
    specs = _scaffold(tmp_path)
    _make_spec(specs / "tasks", "TASK-009-a.md", "TASK-009")
    _make_spec(specs / "tasks", "TASK-009-b.md", "TASK-009")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "TASK-009" in result.stdout


# ---- edge: README / non-frontmatter / missing dir / category isolation -------


def test_readme_files_excluded(tmp_path: Path) -> None:
    """A README.md without a unique `id:` MUST NOT cause a duplicate flag."""
    specs = _scaffold(tmp_path)
    (specs / "requirements" / "README.md").write_text(
        "# Requirements\nid: REQ-NNN (placeholder text not in frontmatter)\n",
        encoding="utf-8",
    )
    _make_spec(specs / "requirements", "REQ-001-a.md", "REQ-001")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_non_frontmatter_id_mention_ignored(tmp_path: Path) -> None:
    """`id:` text in the prose body does not count as a declared id."""
    specs = _scaffold(tmp_path)
    _make_spec(specs / "requirements", "REQ-001-a.md", "REQ-001",
               body="\nSee related id: REQ-001 reference in prose.\n")
    # Second file references REQ-001 in prose but declares REQ-002.
    _make_spec(specs / "requirements", "REQ-002-b.md", "REQ-002",
               body="\nThis discusses id: REQ-001 historically.\n")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_specs_directory_returns_config_error(tmp_path: Path) -> None:
    """Per ADR-035: missing config returns exit 2, not 1."""
    # tmp_path has no .agents/specs/ at all
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "specs directory not found" in result.stderr


def test_category_isolation(tmp_path: Path) -> None:
    """REQ-001 and DESIGN-001 sharing the suffix is NOT a duplicate."""
    specs = _scaffold(tmp_path)
    _make_spec(specs / "requirements", "REQ-001-a.md", "REQ-001")
    _make_spec(specs / "design", "DESIGN-001-a.md", "DESIGN-001")
    _make_spec(specs / "tasks", "TASK-001-a.md", "TASK-001")

    result = _run(tmp_path)
    assert result.returncode == 0


# ---- integration: real repo passes after the renumber -----------------------


def test_real_repo_has_unique_spec_ids() -> None:
    """Regression: the actual repo tree must satisfy the gate post-#2068."""
    result = _run(REPO_ROOT)
    assert result.returncode == 0, (
        "Real spec catalog has duplicate IDs:\n"
        + result.stdout + result.stderr
    )
