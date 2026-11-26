"""Run a shipped copy of assess.py from a consumer's directory.

Each language's coupling tests check that every shipped scanner parses source
outside its own plugin tree, and that it fails loudly without its packages.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(script: Path, target: Path, *python_flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", *python_flags, str(script), "--target", str(target)]
        + ["--format", "json"],
        cwd=target.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )


def assert_shipped_scanner_counts(
    plugin_parts: tuple[str, ...], target: Path, value: float, statements: int
) -> None:
    """Assert the shipped scanner counts ``statements`` dependencies in ``target``.

    Runs from ``target``'s directory. A second run with ``-S`` hides
    site-packages and must exit 1 naming tree-sitter, with no report.
    """
    script = _REPO_ROOT.joinpath(
        "src", *plugin_parts, "skills", "code-qualities-assessment", "scripts", "assess.py"
    )

    result = _run(script, target)

    assert result.returncode == 0, result.stderr
    coupling = json.loads(result.stdout)["files"][0]["coupling"]
    assert coupling["value"] == value
    assert coupling["confidence"] == 0.6
    assert coupling["reasons"][0] == f"{statements} import/dependency statements"

    without_packages = _run(script, target, "-S")

    assert without_packages.returncode == 1
    assert "tree-sitter" in without_packages.stderr
    assert not without_packages.stdout
