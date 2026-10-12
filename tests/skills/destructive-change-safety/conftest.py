"""Shared fixtures for the destructive-change-safety tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "destructive-change-safety" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

# Indirect path: CLI flag -> config -> adapter -> delete, across three modules.
INDIRECT_CLI = """
import argparse
from config import load_config
from pipeline import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--purge-stale", action="store_true")
    args = parser.parse_args()
    run(load_config(args))
"""
INDIRECT_CONFIG = """
def load_config(args):
    return {"purge": args.purge_stale, "root": "data"}
"""
INDIRECT_PIPELINE = """
from adapter import purge_files


def run(config):
    if config["purge"]:
        purge_files(config["root"])
"""
INDIRECT_ADAPTER = """
import shutil


def purge_files(root):
    shutil.rmtree(root)
"""
READ_ONLY = """
def summarize(path):
    with open(path) as handle:
        return len(handle.read().splitlines())
"""


@pytest.fixture
def indirect_repo(tmp_path: Path) -> Path:
    """A four-module repo whose only sink is two calls below the CLI flag."""
    files = {
        "cli.py": INDIRECT_CLI,
        "config.py": INDIRECT_CONFIG,
        "pipeline.py": INDIRECT_PIPELINE,
        "adapter.py": INDIRECT_ADAPTER,
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


@pytest.fixture
def read_only_repo(tmp_path: Path) -> Path:
    (tmp_path / "reader.py").write_text(READ_ONLY, encoding="utf-8")
    return tmp_path
