"""Environment probes for gate_latency.py: git state, host, lefthook resolution.

Split out to keep ``scripts/metrics/gate_latency.py`` under the project's
500-line taste-lint ceiling and its 400-line warning threshold. Raising the
taste ratchet baseline instead is forbidden by ci-scripts.md MUST NOT item 4.

Everything here reads the environment and returns a value: no measurement
arithmetic, no report assembly. Subprocess calls use an argument list with
``shell=False`` and capture text with an explicit encoding, per
``scripts/AGENTS.md``.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.ci.lefthook_budget_model import load_config
from scripts.metrics.gate_latency_models import HostProfile


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _tree_digest(repo: Path) -> str:
    """Hash ``git status --porcelain`` so two moments can be compared for drift (AC-12)."""
    porcelain = _run_git(repo, "status", "--porcelain").stdout
    return hashlib.sha256(porcelain.encode("utf-8")).hexdigest()


def _git_rev_parse_head(repo: Path) -> str:
    result = _run_git(repo, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _host_profile() -> HostProfile:
    return HostProfile(
        captured_at=datetime.now(UTC).isoformat(),
        cpu_count=os.cpu_count() or 1,
        platform=platform.platform(),
        python_version=platform.python_version(),
    )


def _load_lefthook_config(repo: Path) -> dict[str, Any] | None:
    """Parse ``repo``'s ``lefthook.yml``, or ``None`` if absent or invalid.

    Delegates to the shared ``lefthook_budget_model.load_config`` (AC-09);
    only the null-safety this script's exit-code contract needs is new
    here, mirroring ``control_plane_baseline.py``'s ``_lefthook_config``.
    """
    try:
        return load_config(repo / "lefthook.yml")
    except (OSError, yaml.YAMLError, AssertionError):
        return None


def _resolve_lefthook_command(repo: Path, override: str | None) -> list[str] | None:
    """Resolve the lefthook invocation prefix, or ``None`` if nothing is runnable.

    An explicit ``--lefthook-bin`` wins if it resolves (a file path, or a
    name found on ``PATH``). Otherwise this repository's own venv binary at
    ``.venv/bin/lefthook`` is used directly (verified this session: lefthook
    2.1.12). Failing that, ``uv run --frozen lefthook`` is the fallback,
    used only when ``uv`` itself resolves; if none of the three resolves,
    the caller reports "missing lefthook binary" (AC-07).
    """
    if override:
        if Path(override).is_file():
            return [override]
        resolved = shutil.which(override)
        return [resolved] if resolved else None
    venv_bin = repo / ".venv" / "bin" / "lefthook"
    if venv_bin.is_file():
        return [str(venv_bin)]
    uv_bin = shutil.which("uv")
    return ["uv", "run", "--frozen", "lefthook"] if uv_bin else None
