"""Resolving the lefthook command (REQ-027 AC-07).

Split from test_gate_latency.py to mirror gate_latency_probe.py, the
module these exercise.
"""

from __future__ import annotations

from pathlib import Path

from scripts.metrics import gate_latency_probe as gl_probe

# --- Resolving the lefthook command ------------------------------------------


def test_positive_resolve_lefthook_command_prefers_explicit_override(tmp_path: Path) -> None:
    binary = tmp_path / "lefthook"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    assert gl_probe._resolve_lefthook_command(tmp_path, str(binary)) == [str(binary)]


def test_negative_resolve_lefthook_command_returns_none_when_nothing_resolves(
    tmp_path: Path,
) -> None:
    assert gl_probe._resolve_lefthook_command(tmp_path, "/definitely/does/not/exist") is None


def test_positive_resolve_lefthook_command_uses_in_repo_venv_binary(tmp_path: Path) -> None:
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    lefthook = venv_bin / "lefthook"
    lefthook.write_text("#!/bin/sh\n", encoding="utf-8")
    assert gl_probe._resolve_lefthook_command(tmp_path, None) == [str(lefthook)]
