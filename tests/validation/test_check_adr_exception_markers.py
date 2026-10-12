"""Tests for scripts/validation/check_adr_exception_markers.py (issue #5199).

Pins the runner-exception marker gate:

- pos: a marker naming a live ADR passes; a tree with no markers passes
- neg: a marker naming a missing ADR, or a superseded, deprecated, or
  rejected ADR, exits 1 and names file, line, and ADR
- edge: marker spelling variants, `.yaml` files, an ADR with no frontmatter
  (status unknown, existence still checked), a `# ADR-NNN:` line that is not
  an exception marker, missing directories (exit 2 per ADR-035)
- wiring: the pre-PR adapter returns a bool that follows the exit code
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_adr_exception_markers.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validation import check_adr_exception_markers as gate


def _adr(repo: Path, number: int, status: str | None) -> None:
    adr_dir = repo / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True, exist_ok=True)
    front = f"---\nid: ADR-{number:03d}\nstatus: {status}\n---\n\n" if status else ""
    (adr_dir / f"ADR-{number:03d}-runner.md").write_text(
        f"{front}# ADR-{number:03d}: Runner\n", encoding="utf-8"
    )


def _workflow(repo: Path, comment: str, name: str = "ci.yml") -> Path:
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    path = wf_dir / name
    path.write_text(
        textwrap.dedent(
            f"""\
            name: ci
            jobs:
              build:
                {comment}
                runs-on: windows-latest
            """
        ),
        encoding="utf-8",
    )
    return path


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


# --- pos --------------------------------------------------------------------


def test_marker_naming_accepted_adr_passes(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# ADR-055 Exception: Windows-only dependency")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 marker" in result.stdout


def test_proposed_adr_is_live(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "proposed")
    _workflow(tmp_path, "# ADR-055 Exception: Windows-only dependency")
    assert _run(tmp_path).returncode == 0


def test_no_markers_passes_and_reports_zero_examined(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain comment")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "0 marker" in result.stdout


# --- neg --------------------------------------------------------------------


def test_marker_naming_missing_adr_fails(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# ADR-999 Exception: Windows-only dependency")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "ci.yml:4" in result.stdout
    assert "ADR-999" in result.stdout
    assert "does not exist" in result.stdout


@pytest.mark.parametrize("status", ["superseded", "deprecated", "rejected"])
def test_marker_naming_retired_adr_fails(tmp_path: Path, status: str) -> None:
    _adr(tmp_path, 24, status)
    _workflow(tmp_path, "# ADR-024 Exception: x64 runner required")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "ADR-024" in result.stdout
    assert status in result.stdout


def test_gate_cannot_tell_a_live_adr_is_about_runners(tmp_path: Path) -> None:
    # ADR-014 was the pre-renumber runner record; the number now means handoff.
    # Only existence and status are machine-checkable, so a live record passes.
    # The topic of the cited ADR stays a review question, not a gate.
    _adr(tmp_path, 14, "accepted")
    _workflow(tmp_path, "# ADR-014 Exception: Windows runner required")
    assert _run(tmp_path).returncode == 0


def test_every_bad_marker_is_reported(tmp_path: Path) -> None:
    _adr(tmp_path, 24, "superseded")
    _workflow(tmp_path, "# ADR-024 Exception: a", name="a.yml")
    _workflow(tmp_path, "# ADR-998 Exception: b", name="b.yaml")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "a.yml" in result.stdout
    assert "b.yaml" in result.stdout


# --- edge -------------------------------------------------------------------


@pytest.mark.parametrize(
    "comment",
    [
        "#ADR-055 Exception: no space after hash",
        "#   ADR-055   Exception : wide spacing",
        "# adr-055 exception: lowercase",
    ],
)
def test_marker_spelling_variants_are_read(tmp_path: Path, comment: str) -> None:
    _adr(tmp_path, 55, "superseded")
    _workflow(tmp_path, comment)
    assert _run(tmp_path).returncode == 1


def test_trailing_comment_on_a_key_line_is_read(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "superseded")
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "x.yml").write_text(
        "runs-on: windows-latest  # ADR-055 Exception: reason\n", encoding="utf-8"
    )
    assert _run(tmp_path).returncode == 1


def test_adr_reference_without_exception_word_is_ignored(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "superseded")
    _workflow(tmp_path, "# ADR-055: ARM runner for cost optimization")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "0 marker" in result.stdout


def test_adr_without_frontmatter_passes_on_existence(tmp_path: Path) -> None:
    _adr(tmp_path, 55, None)
    _workflow(tmp_path, "# ADR-055 Exception: reason")
    assert _run(tmp_path).returncode == 0


def test_adr_with_malformed_frontmatter_passes_on_existence(tmp_path: Path) -> None:
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-055-runner.md").write_text("---\nstatus: [oops\n---\n", encoding="utf-8")
    _workflow(tmp_path, "# ADR-055 Exception: reason")
    assert _run(tmp_path).returncode == 0


def test_status_case_and_padding_are_normalised(tmp_path: Path) -> None:
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-055-runner.md").write_text(
        "---\nstatus: ' Superseded '\n---\n", encoding="utf-8"
    )
    _workflow(tmp_path, "# ADR-055 Exception: reason")
    assert _run(tmp_path).returncode == 1


def test_non_workflow_files_are_not_scanned(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    (tmp_path / ".github" / "workflows" / "notes.md").write_text(
        "# ADR-999 Exception: documentation example\n", encoding="utf-8"
    )
    assert _run(tmp_path).returncode == 0


def test_scalar_status_types_do_not_crash(tmp_path: Path) -> None:
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-055-runner.md").write_text("---\nstatus:\n  - a\n---\n", encoding="utf-8")
    _workflow(tmp_path, "# ADR-055 Exception: reason")
    assert _run(tmp_path).returncode == 0


def test_missing_workflow_dir_is_config_error(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "workflows" in result.stderr


def test_missing_adr_dir_is_config_error(tmp_path: Path) -> None:
    _workflow(tmp_path, "# ADR-055 Exception: reason")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "architecture" in result.stderr


def test_non_utf8_workflow_is_reported_not_crashed(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# plain")
    (tmp_path / ".github" / "workflows" / "bad.yml").write_bytes(b"\xff\xfe# ADR-055 Exception\n")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "bad.yml" in result.stderr


# --- wiring -----------------------------------------------------------------


def test_adapter_returns_true_on_clean_tree(tmp_path: Path) -> None:
    _adr(tmp_path, 55, "accepted")
    _workflow(tmp_path, "# ADR-055 Exception: reason")
    assert gate.validate_adr_exception_markers(tmp_path) is True


def test_adapter_returns_false_on_violation_and_on_config_error(tmp_path: Path) -> None:
    assert gate.validate_adr_exception_markers(tmp_path) is False
    _adr(tmp_path, 24, "superseded")
    _workflow(tmp_path, "# ADR-024 Exception: reason")
    assert gate.validate_adr_exception_markers(tmp_path) is False


def test_real_corpus_passes() -> None:
    """Rule 13: the gate passes against the full corpus on this branch."""
    assert gate.main(["--repo-root", str(REPO_ROOT)]) == 0
