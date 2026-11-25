"""AC-DUP-4: Shared conversion preserves dry runs, statistics, and errors."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src/claude/skills/memory/scripts"))

from memory_link_processing import ConversionOptions, _find_project_root, process_link_files


@pytest.mark.parametrize("discovery", ["absolute", "relative", "failed", "missing"])
def test_root_discovery_preserves_git_and_fallback_paths(discovery: str, tmp_path: Path) -> None:
    """AC-DUP-4: Discover the same root with git or ancestor traversal."""
    root = tmp_path / "project"
    (root / ".git").mkdir(parents=True)
    nested = root / "nested"
    nested.mkdir()
    stdout = str(root / ".git") if discovery == "absolute" else os.path.relpath(root / ".git")
    result = subprocess.CompletedProcess(
        ["git", "rev-parse", "--git-common-dir"],
        128 if discovery == "failed" else 0,
        stdout=stdout,
    )

    with patch(
        "memory_link_processing.subprocess.run",
        return_value=result,
        side_effect=FileNotFoundError if discovery == "missing" else None,
    ) as run:
        assert _find_project_root(nested) == root

    run.assert_called_once_with(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_default_root_search_starts_beside_the_shipped_consumers() -> None:
    """AC-DUP-4: Failed git discovery retains the consumers' default search."""
    result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
        ["git", "rev-parse", "--git-common-dir"], 128
    )
    with patch("memory_link_processing.subprocess.run", return_value=result):
        assert _find_project_root() == Path(__file__).resolve().parents[3]


def test_root_search_fails_when_no_ancestor_can_contain_git() -> None:
    """AC-DUP-4: Missing roots retain the original configuration failure."""
    result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
        ["git", "rev-parse", "--git-common-dir"], 128
    )
    with patch("memory_link_processing.subprocess.run", return_value=result):
        with pytest.raises(SystemExit, match="Could not find project root"):
            _find_project_root(Path(Path.cwd().anchor))


@pytest.mark.parametrize(
    "entrypoint",
    [
        "convert_index_table_links.py",
        "convert_memory_references.py",
        "improve_memory_graph_density.py",
    ],
)
def test_memory_cli_delegates_shared_root_lookup(entrypoint: str, tmp_path: Path) -> None:
    scripts = Path(__file__).resolve().parents[3] / "src/claude/skills/memory/scripts"
    target = tmp_path / entrypoint
    shutil.copyfile(scripts / entrypoint, target)
    helper = (scripts / "memory_link_processing.py").read_text(encoding="utf-8")
    (tmp_path / "memory_link_processing.py").write_text(
        helper + "\n\ndef _find_project_root(fallback_dir=None):\n    raise SystemExit(73)\n",
        encoding="utf-8",
    )
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PATH"] = str(tmp_path / "no-external-tools")

    result = subprocess.run(
        [sys.executable, str(target), "--output-json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )

    assert result.returncode == 73, result.stderr


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("output_json", [False, True])
def test_link_processing_preserves_output_and_continues_after_read_errors(
    dry_run: bool, output_json: bool, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target.md"
    target.write_text("`note`", encoding="utf-8")
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    missing = tmp_path / "missing.md"
    options = ConversionOptions(
        (lambda content, names: content.replace("`note`", "[note](note.md)"),),
        output_json,
        dry_run,
    )

    stats = process_link_files([missing, empty, target], {"note": True}, options)

    assert stats["FilesProcessed"] == 3
    assert stats["FilesModified"] == 1
    assert stats["LinksAdded"] == 1
    assert len(stats["Errors"]) == 1
    assert stats["Errors"][0].startswith("Error processing missing.md:")
    assert stats.get("DryRun", False) == dry_run
    assert target.read_text(encoding="utf-8") == ("`note`" if dry_run else "[note](note.md)")
    captured = capsys.readouterr()
    assert ("WARNING:" in captured.err) != output_json
    expected = "Would update: target.md" if dry_run else "Updated: target.md"
    assert (expected in captured.out) != output_json
