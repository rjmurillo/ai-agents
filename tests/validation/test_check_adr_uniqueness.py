"""Tests for scripts/validation/check_adr_uniqueness.py (Issue #2253).

Pins behaviour of the ADR-number-collision gate:

- pos: a unique-number tree returns exit 0
- neg: a tree with a colliding ADR number returns exit 1
- edge: README and non-ADR files are ignored; missing directory is a
  config error (exit 2 per ADR-035); the #2228 allowlist suppresses
  pre-existing duplicates (58/62/63) but not new ones
- branch: --print-next returns max(existing)+1, exit 0; empty tree
  yields 001; padding width is respected
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_adr_uniqueness.py"


def _make_adr(adr_dir: Path, number: int, slug: str = "thing") -> Path:
    adr_dir.mkdir(parents=True, exist_ok=True)
    path = adr_dir / f"ADR-{number:03d}-{slug}.md"
    path.write_text(
        textwrap.dedent(
            f"""\
            # ADR-{number:03d}: {slug}

            ## Status

            Proposed
            """
        ),
        encoding="utf-8",
    )
    return path


def _scaffold(tmp_path: Path) -> Path:
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    return adr_dir


def _run(
    repo_root: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo_root), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


# --- pos --------------------------------------------------------------------


def test_unique_numbers_pass(tmp_path: Path) -> None:
    adr_dir = _scaffold(tmp_path)
    _make_adr(adr_dir, 1, "alpha")
    _make_adr(adr_dir, 2, "beta")
    _make_adr(adr_dir, 3, "gamma")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[PASS]" in result.stdout
    assert "next free: 004" in result.stdout


# --- neg --------------------------------------------------------------------


def test_new_duplicate_fails(tmp_path: Path) -> None:
    adr_dir = _scaffold(tmp_path)
    _make_adr(adr_dir, 70, "first")
    _make_adr(adr_dir, 70, "second")

    result = _run(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[FAIL]" in result.stdout
    assert "ADR-070" in result.stdout
    # Remediation must point the author at the next free number.
    assert "next free ADR number: 071" in result.stdout


def test_duplicate_outside_allowlist_fails_even_when_allowlisted_present(
    tmp_path: Path,
) -> None:
    """Allowlist suppresses #2228 dupes but never new ones in the same tree."""
    adr_dir = _scaffold(tmp_path)
    # Pre-existing dupe (allowlisted)
    _make_adr(adr_dir, 58, "agent-eval")
    _make_adr(adr_dir, 58, "context-corpus")
    # New, post-merge dupe must fail.
    _make_adr(adr_dir, 80, "first")
    _make_adr(adr_dir, 80, "second")

    result = _run(tmp_path)
    assert result.returncode == 1
    assert "ADR-080" in result.stdout
    # The allowlisted number must not be listed as a failure.
    assert "ADR-058" not in result.stdout


# --- edge -------------------------------------------------------------------


def test_allowlist_suppresses_known_2228_duplicates(tmp_path: Path) -> None:
    adr_dir = _scaffold(tmp_path)
    for num in (58, 62, 63):
        _make_adr(adr_dir, num, "first")
        _make_adr(adr_dir, num, "second")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[PASS]" in result.stdout


def test_new_duplicate_of_allowlisted_number_fails(tmp_path: Path) -> None:
    adr_dir = _scaffold(tmp_path)
    _make_adr(adr_dir, 58, "agent-eval")
    _make_adr(adr_dir, 58, "context-corpus")
    _make_adr(adr_dir, 58, "third-one")

    result = _run(tmp_path)
    assert result.returncode == 1
    assert "ADR-058" in result.stdout
    assert "next free ADR number: 059" in result.stdout


def test_readme_and_non_adr_files_are_ignored(tmp_path: Path) -> None:
    adr_dir = _scaffold(tmp_path)
    _make_adr(adr_dir, 1, "alpha")
    (adr_dir / "README.md").write_text("# index\n", encoding="utf-8")
    (adr_dir / "DESIGN-REVIEW-something.md").write_text("# review\n", encoding="utf-8")
    (adr_dir / "ADR-EXAMPLE.md").write_text("# example\n", encoding="utf-8")

    result = _run(tmp_path)
    assert result.returncode == 0
    assert "[PASS]" in result.stdout


def test_missing_architecture_dir_is_config_error(tmp_path: Path) -> None:
    # No .agents/architecture created.
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "[CONFIG]" in result.stderr


def test_empty_architecture_dir_pass_next_is_one(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    result = _run(tmp_path, "--print-next")
    assert result.returncode == 0
    assert result.stdout.strip() == "001"


# --- branch (--print-next) --------------------------------------------------


def test_print_next_returns_max_plus_one(tmp_path: Path) -> None:
    adr_dir = _scaffold(tmp_path)
    _make_adr(adr_dir, 1)
    _make_adr(adr_dir, 5)
    _make_adr(adr_dir, 42)

    result = _run(tmp_path, "--print-next")
    assert result.returncode == 0
    assert result.stdout.strip() == "043"


def test_print_next_respects_padding(tmp_path: Path) -> None:
    adr_dir = _scaffold(tmp_path)
    _make_adr(adr_dir, 3)

    result = _run(tmp_path, "--print-next", "--print-next-padded", "5")
    assert result.returncode == 0
    assert result.stdout.strip() == "00004"


def test_print_next_ignores_existing_duplicates(tmp_path: Path) -> None:
    """--print-next must work even when the tree is currently broken."""
    adr_dir = _scaffold(tmp_path)
    _make_adr(adr_dir, 10, "first")
    _make_adr(adr_dir, 10, "second")
    _make_adr(adr_dir, 20)

    result = _run(tmp_path, "--print-next")
    assert result.returncode == 0
    assert result.stdout.strip() == "021"
