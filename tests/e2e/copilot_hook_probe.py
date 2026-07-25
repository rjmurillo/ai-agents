#!/usr/bin/env python3
"""Shared Copilot ``--plugin-dir`` fired-hook probe (issue #3148).

A fired hook is the version-agnostic proof that the Copilot CLI loaded a
``--plugin-dir`` plugin and dispatched its ``UserPromptSubmit`` hook. It does not
depend on how ``copilot skill list --json`` labels plugin skills, which the CLI
has changed twice: 1.0.69 through 1.0.72 omit ``--plugin-dir`` skills from
``source: plugin`` (issues #2990, #3014, #3090, #3135), and a machine with
globally installed plugins surfaces those under ``source: plugin`` with
``pluginName: null``. Keying the load signal on a fired hook removes both the
per-version allowlist churn and the environment-dependent enumeration flake.

Both ``tests/e2e/test_cli_hook_e2e.py`` and ``tests/e2e/test_plugin_load_smoke.py``
import this module so the fired-hook probe has ONE source of truth.

The probe binds to ``UserPromptSubmit``, NOT ``SessionStart``: ``copilot -p``
does not dispatch ``SessionStart`` (issue #2378), so a ``SessionStart`` marker
would never appear under ``-p`` even when the plugin loads. Empirically verified
against Copilot CLI 1.0.72-0: ``copilot --plugin-dir <probe> -p`` fires the
probe's ``UserPromptSubmit`` hook (marker written), and an empty ``--plugin-dir``
does not (marker absent), so the marker discriminates load from no-load.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
    import generate_hooks  # noqa: E402
finally:
    sys.path[:] = _original_sys_path

_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cli_exec import resolve_executable  # noqa: E402
finally:
    sys.path[:] = _original_sys_path

# copilot -p does NOT dispatch SessionStart; UserPromptSubmit does fire there.
# See tests/e2e/test_cli_hook_e2e.py module docstring and issue #2378.
PROBE_EVENT = "UserPromptSubmit"
PROBE_PROMPT = "Reply with exactly the word: ok"

# A parent Claude session or the pre-push hook may export these; strip them so
# the CLI under test resolves the plugin from ``--plugin-dir``, not from an
# inherited root that points at a different tree.
PLUGIN_ROOT_ENV_KEYS = {"CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "COPILOT_PLUGIN_ROOT"}


def clean_env() -> dict[str, str]:
    """Env for the CLI subprocess with inherited plugin-root vars stripped."""
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in PLUGIN_ROOT_ENV_KEYS:
            env.pop(key, None)
    return env


def copilot_command(*args: str) -> list[str]:
    """Build a Copilot command that cannot auto-update past the tested pin."""
    return [resolve_executable("copilot"), "--no-auto-update", *args]


def probe_name() -> str:
    """A unique plugin name so parallel or repeated runs do not collide."""
    return f"hook-e2e-probe-{uuid.uuid4().hex[:12]}"


def manifest(name: str) -> str:
    """A minimal plugin manifest body for a probe plugin."""
    return json.dumps(
        {"name": name, "description": "e2e probe", "version": "0.0.1", "author": {"name": "e2e"}}
    )


def write_probe_script(path: Path, marker: Path) -> None:
    """Write a hook script that records where and how it was launched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import os, sys\n"
        f"with open({str(marker)!r}, 'a', encoding='utf-8') as f:\n"
        "    f.write('MARKER\\n')\n"
        "    f.write('script=' + os.path.abspath(__file__) + '\\n')\n"
        "    f.write('cwd=' + os.getcwd() + '\\n')\n"
        "    f.write('COPILOT_PLUGIN_ROOT=' + str(os.environ.get('COPILOT_PLUGIN_ROOT')) + '\\n')\n"
        "    f.write('CLAUDE_PLUGIN_ROOT=' + str(os.environ.get('CLAUDE_PLUGIN_ROOT')) + '\\n')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )


def write_marker_probe_plugin(plugin_dir: Path, marker: Path) -> str:
    """Create a synthetic ``--plugin-dir`` plugin that fires a marker hook.

    Lays down ``plugin.json``, the ``UserPromptSubmit`` probe script, and a
    ``hooks.json`` built with the SAME generator entry the shipped plugin uses
    (``generate_hooks._build_copilot_entry``), so a firing failure here tracks
    the real command shape. Returns the probe plugin name.
    """
    name = probe_name()
    write_probe_script(plugin_dir / "hooks" / PROBE_EVENT / "probe.py", marker)
    (plugin_dir / "plugin.json").write_text(manifest(name), encoding="utf-8")
    entry = generate_hooks._build_copilot_entry(PROBE_EVENT, "probe.py")
    (plugin_dir / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {PROBE_EVENT: [entry]}, "version": 1}), encoding="utf-8"
    )
    return name


# Auth-absent detection (issue #3275). A missing or empty smoke auth secret
# expands to an empty COPILOT_GITHUB_TOKEN, so the CLI aborts at its own auth
# gate before it loads any plugin or fires any hook. The downstream marker-miss
# and rc=1 assertions then misdiagnose a dead secret as a plugin-load or
# hook-resolution bug. These pure predicates let each smoke lead with an
# accurate headline instead. Kept pytest-free so they unit-test as plain
# functions and impose no test-framework dependency on this probe primitive.
COPILOT_AUTH_ABSENT_MARKERS = (
    "no authentication information found",
    "set the copilot_github_token",
)


def copilot_auth_absent(result: subprocess.CompletedProcess[str]) -> bool:
    """True when the Copilot CLI aborted because no auth token was provided.

    Copilot prints ``No authentication information found`` and names the
    ``COPILOT_GITHUB_TOKEN`` env var on stderr when the token is empty. Matches
    case-insensitively across both stderr and stdout so the signal survives a
    stream swap or a wrapper that folds stderr into stdout. Tolerates ``None``
    streams (a timed-out or not-yet-run process). See issue #3275.

    Missing auth is an error path: the CLI aborts non-zero. Gate the marker scan
    on ``returncode != 0`` so a healthy run (rc=0) that happens to echo a marker
    string in its output is never misclassified as an auth failure.
    """
    if result.returncode == 0:
        return False
    haystack = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
    return any(marker in haystack for marker in COPILOT_AUTH_ABSENT_MARKERS)


def copilot_auth_absent_headline(result: subprocess.CompletedProcess[str]) -> str:
    """Accurate failure headline for a Copilot run that aborted with no auth.

    Leads with the real cause (dead auth secret), not the misdiagnosed symptom
    (missing hook marker / rc=1), so the dogfood failure is actionable at a
    glance. Surfaces rc and both streams because the detector scans stdout too
    (stream-swap resilience), so a stdout-only auth failure stays actionable.
    See issue #3275.
    """
    return (
        "Copilot auth token is empty; the shipped-base dogfood never ran. "
        "Provision COPILOT_GITHUB_TOKEN for the smoke job (issue #3275). "
        f"rc={result.returncode} "
        f"stderr={(result.stderr or '')[-400:]!r} "
        f"stdout={(result.stdout or '')[-400:]!r}"
    )


def run_copilot_plugin_dir(
    plugin_dir: Path,
    *,
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run ``copilot --plugin-dir <plugin_dir> -p`` from a neutral ``cwd``.

    ``--allow-all-tools`` and ``--allow-all-paths`` keep the non-interactive run
    from stalling on a permission prompt. Raises ``subprocess.TimeoutExpired`` on
    CLI/infra latency so the caller can skip loud rather than false-fail.
    """
    return subprocess.run(
        copilot_command(
            "--plugin-dir",
            str(plugin_dir),
            "-p",
            PROBE_PROMPT,
            "--allow-all-tools",
            "--allow-all-paths",
        ),
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=clean_env(),
    )
