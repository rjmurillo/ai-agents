"""Tests for vendor provenance validator exit codes."""

from __future__ import annotations

import subprocess
import sys


def test_missing_candidate_root_exits_nonzero() -> None:
    """Validator returns nonzero when candidate root does not exist."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ci/validate_vendor_provenance.py",
            "--candidate-root", "/nonexistent/path",
            "--vendor-rel", "vendor",
            "--verifier-rel", "v.py",
            "--mirror-rel", "m.py",
            "--config-rel", "c.yaml",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
