"""Shared fixtures for context-output CLI tests."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
    ),
)

import context_output_cli as cli
import extract_and_index as core
from test_extract_and_index import REPO_ROOT, SAMPLE_DOC

__all__ = ("REPO_ROOT", "SAMPLE_DOC", "cli", "cli_args", "cli_workspace", "core")

def cli_args(**overrides):
    """Return a namespace with all extractor CLI defaults."""
    values = {
        "check": False,
        "detail_dir": None,
        "detail_ref": None,
        "input": None,
        "manifest": None,
        "output": None,
        "staged": False,
        "verbose": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def cli_workspace(tmp_path):
    """Create one generated document and its manifest for CLI tests."""
    work_dir = REPO_ROOT / ".pytest_tmp" / f"cli_internal_{tmp_path.name}"
    output_root = work_dir / "output"
    detail_dir = output_root / "details"
    source = work_dir / "source.md"
    index_path = output_root / "index.md"
    manifest_path = work_dir / "manifest.json"
    work_dir.mkdir(parents=True, exist_ok=True)
    source.write_text(SAMPLE_DOC, encoding="utf-8")
    detail_ref = detail_dir.relative_to(REPO_ROOT).as_posix()
    result = core.extract_and_index(SAMPLE_DOC, detail_dir, detail_ref, repo_root=REPO_ROOT)
    index_path.write_text(result.index_content, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "output_root": output_root.relative_to(REPO_ROOT).as_posix(),
                "entries": [
                    {
                        "source": source.relative_to(REPO_ROOT).as_posix(),
                        "index": index_path.relative_to(REPO_ROOT).as_posix(),
                        "detail_dir": detail_ref,
                        "detail_ref": detail_ref,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return work_dir, source, detail_dir, index_path, manifest_path
