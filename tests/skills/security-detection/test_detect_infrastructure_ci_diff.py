#!/usr/bin/env python3
"""Tests for the documented CI diff pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import SCRIPT_PATH


def test_documented_ci_diff_exposes_renamed_sensitive_source(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test User"],
        check=True,
    )
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "test: add workflow"],
        check=True,
    )
    base = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()
    destination = tmp_path / "docs" / "ci.yml"
    destination.parent.mkdir()
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "mv",
            ".github/workflows/ci.yml",
            "docs/ci.yml",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "test: move workflow"],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()

    changed = subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            base,
            head,
        ],
        check=True,
        capture_output=True,
    ).stdout
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--files-from-stdin", "--json"],
        input=changed,
        check=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["highest_risk"] == "critical"
    assert payload["file_count"] == 2
