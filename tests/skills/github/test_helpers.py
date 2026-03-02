"""Shared test helpers for GitHub skill script tests."""

import subprocess


def make_completed_process(
    stdout: str = "", stderr: str = "", returncode: int = 0,
):
    """Create a mock CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )
