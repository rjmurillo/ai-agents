#!/usr/bin/env python3
"""Behavioral tests for uv-first tool resolution in the git hooks.

Regression guards for #3136 (pre-commit ruff) and #3132 (pre-push mypy). Both
hooks used to gate Python lint / type check on ``command -v <tool>`` alone, so a
uv-managed checkout without the tool on the ambient ``PATH`` silently skipped a
declared check and deferred the finding to push or CI.

The fix builds a command array that prefers ``uv run --frozen --extra dev
<tool>`` when uv and the project metadata resolve the tool, and falls back to a
``PATH`` executable. To avoid duplicating the selector (which would drift from
the hook), these tests extract the exact selection block from each hook and run
it under bash against stubbed ``uv`` / tool executables and controlled project
metadata, asserting which command is chosen.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _extract_block(hook: Path, init_line: str, end_prefix: str) -> str:
    """Return the tool-selection block from a hook.

    Extracts from the ``<TOOL>_CMD=()`` init line up to (but excluding) the
    ``if [ ${#<TOOL>_CMD[@]} -gt 0 ]; then`` line that consumes the selection.
    """
    lines = hook.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == init_line:
            start = i
            break
    assert start is not None, f"{init_line!r} not found in {hook.name}"
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith(end_prefix):
            end = j
            break
    assert end is not None, f"{end_prefix!r} terminator not found in {hook.name}"
    return "\n".join(lines[start:end])


def _make_stub(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_selector(
    block: str,
    *,
    tool_var: str,
    bin_dir: Path,
    repo_root: Path,
    extra_env: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Run an extracted selector block and return (CMD, SOURCE).

    ``PATH`` is set to ``bin_dir`` only so stub presence fully controls
    ``command -v`` lookups; the block otherwise uses bash builtins.
    """
    script = (
        f'export PATH="{bin_dir}"\n'
        f'REPO_ROOT="{repo_root}"\n'
        f"{block}\n"
        f'echo "CMD=${{{tool_var}_CMD[*]}}"\n'
        f'echo "SOURCE=${{{tool_var}_SOURCE:-}}"\n'
    )
    env = {"PATH": os.environ.get("PATH", "")}
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"selector block errored: {proc.stderr}"
    cmd = source = ""
    for out_line in proc.stdout.splitlines():
        if out_line.startswith("CMD="):
            cmd = out_line[len("CMD=") :]
        elif out_line.startswith("SOURCE="):
            source = out_line[len("SOURCE=") :]
    return cmd, source


def _setup_bins(tmp_path: Path, *, uv: bool, tool: str | None, uv_probe_exit: int) -> Path:
    """Create a stub bin dir. ``uv`` and/or the named tool present as scripts."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if uv:
        # `uv run ... <tool> --version` exits uv_probe_exit; anything else 0.
        # Use /bin/sh (absolute interpreter) so the stub runs even when PATH is
        # narrowed to bin_dir only (no bash/env resolvable for a shebang lookup).
        _make_stub(
            bin_dir / "uv",
            "#!/bin/sh\n"
            'if [ "$1" = "run" ]; then exit ' + str(uv_probe_exit) + "; fi\nexit 0\n",
        )
    if tool:
        _make_stub(bin_dir / tool, "#!/bin/sh\nexit 0\n")
    return bin_dir


def _repo_with_metadata(tmp_path: Path, *, metadata: bool) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    if metadata:
        (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return root


# --- pre-commit ruff (#3136), no SOURCE var, assert on CMD ------------------

RUFF_BLOCK = _extract_block(
    PRE_COMMIT, "RUFF_CMD=()", "if [ ${#RUFF_CMD[@]} -gt 0 ]"
)
MYPY_BLOCK = _extract_block(
    PRE_PUSH, "MYPY_CMD=()", "if [ ${#MYPY_CMD[@]} -gt 0 ]"
)


class TestRuffResolution:
    """pre-commit RUFF_CMD selection (#3136)."""

    def test_uv_preferred_when_available(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=True, tool="ruff", uv_probe_exit=0)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, _ = _run_selector(
            RUFF_BLOCK, tool_var="RUFF", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == "uv run --frozen --extra dev ruff"

    def test_path_fallback_when_uv_absent(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=False, tool="ruff", uv_probe_exit=0)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, _ = _run_selector(
            RUFF_BLOCK, tool_var="RUFF", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == "ruff"

    def test_empty_when_neither_available(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=False, tool=None, uv_probe_exit=0)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, _ = _run_selector(
            RUFF_BLOCK, tool_var="RUFF", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == ""

    def test_path_fallback_on_uv_probe_failure(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=True, tool="ruff", uv_probe_exit=1)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, _ = _run_selector(
            RUFF_BLOCK, tool_var="RUFF", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == "ruff"

    def test_path_fallback_when_no_project_metadata(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=True, tool="ruff", uv_probe_exit=0)
        repo = _repo_with_metadata(tmp_path, metadata=False)
        cmd, _ = _run_selector(
            RUFF_BLOCK, tool_var="RUFF", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == "ruff"


class TestMypyResolution:
    """pre-push MYPY_CMD selection (#3132)."""

    def test_uv_preferred_when_available(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=True, tool="mypy", uv_probe_exit=0)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, source = _run_selector(
            MYPY_BLOCK, tool_var="MYPY", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == "uv run --frozen --extra dev mypy"
        assert source == "uv"

    def test_path_fallback_when_uv_absent(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=False, tool="mypy", uv_probe_exit=0)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, source = _run_selector(
            MYPY_BLOCK, tool_var="MYPY", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == "mypy"
        assert source == "path"

    def test_empty_when_neither_available(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=False, tool=None, uv_probe_exit=0)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, source = _run_selector(
            MYPY_BLOCK, tool_var="MYPY", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == ""
        assert source == ""

    def test_path_fallback_on_uv_probe_failure(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=True, tool="mypy", uv_probe_exit=1)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, source = _run_selector(
            MYPY_BLOCK, tool_var="MYPY", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == "mypy"
        assert source == "path"

    def test_empty_on_uv_probe_failure_and_no_path_tool(self, tmp_path: Path) -> None:
        bin_dir = _setup_bins(tmp_path, uv=True, tool=None, uv_probe_exit=1)
        repo = _repo_with_metadata(tmp_path, metadata=True)
        cmd, source = _run_selector(
            MYPY_BLOCK, tool_var="MYPY", bin_dir=bin_dir, repo_root=repo
        )
        assert cmd == ""
        assert source == ""


class TestHookStructure:
    """Structural guards that the silent-skip path is gone."""

    def test_pre_commit_no_bare_ruff_gate(self) -> None:
        text = PRE_COMMIT.read_text(encoding="utf-8")
        assert "ruff not available via uv or PATH" in text
        assert 'echo_info "  Install: pip install ruff"' not in text

    def test_pre_push_mypy_missing_fails_not_skips(self) -> None:
        text = PRE_PUSH.read_text(encoding="utf-8")
        assert 'record_skip "Python type check (mypy not installed)"' not in text
        assert "mypy unavailable via uv or PATH" in text

    def test_pre_push_no_bare_mypy_invocation(self) -> None:
        text = PRE_PUSH.read_text(encoding="utf-8")
        for bare in ('\n                if mypy "', '\n                    mypy "'):
            assert bare not in text, f"bare mypy invocation still present: {bare!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
