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
    import generate_hooks
finally:
    sys.path[:] = _original_sys_path

_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cli_exec import resolve_executable
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

# Auth-rejected detection. A populated but expired or revoked token reaches the
# CLI's auth gate and is turned away by GitHub, and the CLI still prints its
# "you can use any of the following methods" list naming COPILOT_GITHUB_TOKEN.
# That list matches COPILOT_AUTH_ABSENT_MARKERS, so a rejected token reads as an
# empty one and the headline sends the reader to provision a secret that is
# already provisioned. Only ``github returned: bad credentials`` is anchored to
# the CLI's own auth-gate 401 path. ``failed to fetch pat user login`` without
# ``bad credentials`` fires on network errors, 5xx, and rate limits too and is
# therefore not reliable as a standalone rejection marker (issue #4504).
COPILOT_AUTH_REJECTED_MARKERS = ("github returned: bad credentials",)

# Rate-limit detection (issue #4504). A 403 refusal from GitHub's rate limiter
# carries its own boilerplate that overlaps with both the absent and rejected
# markers. The CLI may also print "Your token may still be valid. Check your
# network connection and try again." A rate-limited run has healthy auth; the
# correct advice is to retry after the reset window, not to rotate the token.
# This predicate takes precedence over both auth predicates.
COPILOT_RATE_LIMIT_MARKERS = (
    "api rate limit exceeded",
    "secondary rate limit",
    "your token may still be valid",
    "check your network connection and try again",
)


def _copilot_haystack(result: subprocess.CompletedProcess[str]) -> str:
    """Lowercased concatenation of stderr and stdout for marker search."""
    return f"{result.stderr or ''}\n{result.stdout or ''}".lower()


def _head_tail_excerpt(text: str | None, head: int = 300, tail: int = 300) -> str:
    """Return a head+tail excerpt of ``text`` with a drop count in the middle.

    Captures both the leading diagnostic sentence (where GitHub puts the cause)
    and the trailing boilerplate. Replaces the tail-only slice that hid the
    cause while keeping the useless boilerplate (issue #4504).
    """
    s = text or ""
    total = len(s)
    if total <= head + tail:
        return repr(s)
    dropped = total - head - tail
    return repr(s[:head]) + f" ... [{dropped} chars dropped] ... " + repr(s[-tail:])


def copilot_rate_limited(result: subprocess.CompletedProcess[str]) -> bool:
    """True when the Copilot CLI was refused for rate limiting, not bad auth."""
    if result.returncode == 0:
        return False
    haystack = _copilot_haystack(result)
    return any(marker in haystack for marker in COPILOT_RATE_LIMIT_MARKERS)


def copilot_transient_failure(result: subprocess.CompletedProcess[str]) -> bool:
    """True when the CLI disclaimed the credential on an aborted run."""
    return copilot_rate_limited(result)


def copilot_transient_failure_headline(result: subprocess.CompletedProcess[str]) -> str:
    """Skip reason for a run the CLI aborted after disclaiming the credential."""
    return (
        "Copilot CLI aborted on a transient fault: it disclaimed the credential "
        "(reports the token may still be valid), and a GitHub rate limit is the "
        "usual cause. This is NOT an auth failure and no diff can fix it. Wait "
        "for the rate-limit reset and "
        f"re-run. rc={result.returncode} "
        f"stderr={_head_tail_excerpt(result.stderr, head=300, tail=300)} "
        f"stdout={_head_tail_excerpt(result.stdout, head=300, tail=300)}"
    )


def copilot_auth_rejected(result: subprocess.CompletedProcess[str]) -> bool:
    """True when the Copilot CLI presented a credential and GitHub refused it.

    Distinguishes an expired or revoked token from a missing one. Both abort the
    run before any plugin loads, so both gate the same failure, but they need
    different remediation: rotate the secret versus create it. Same rc and
    stream handling as :func:`copilot_auth_absent`.

    Rate-limited runs are excluded: the CLI may print the same auth-method list
    after a 403 refusal, so rate-limit detection takes precedence (issue #4504).
    """
    if result.returncode == 0:
        return False
    if copilot_transient_failure(result):
        return False
    haystack = _copilot_haystack(result)
    return any(marker in haystack for marker in COPILOT_AUTH_REJECTED_MARKERS)


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

    A rejected token is excluded, not merely deprioritized. The CLI prints the
    same "you can use any of the following methods" list after a refusal, so the
    absent markers match a token that plainly exists. Returning True there would
    make this predicate's own name false and would silently depend on every
    caller checking :func:`copilot_auth_rejected` first.

    Rate-limited runs are also excluded: they share auth-boilerplate wording but
    have healthy credentials (issue #4504).
    """
    if result.returncode == 0:
        return False
    if copilot_transient_failure(result) or copilot_auth_rejected(result):
        return False
    haystack = _copilot_haystack(result)
    return any(marker in haystack for marker in COPILOT_AUTH_ABSENT_MARKERS)


def copilot_run_blocked(result: subprocess.CompletedProcess[str]) -> bool:
    """True when the run was blocked for any reason (auth or rate limit).

    Use this as the gate in smoke tests that must not proceed when the CLI
    cannot complete a real run, regardless of cause. The specific cause
    can be diagnosed via the individual predicates.
    """
    return (
        copilot_transient_failure(result)
        or copilot_auth_rejected(result)
        or copilot_auth_absent(result)
    )


def copilot_auth_failed(result: subprocess.CompletedProcess[str]) -> bool:
    """True when the run died at the auth gate, whether absent or rejected.

    Does not include rate-limited runs: those have healthy auth and should
    not trigger a credential-rotation or provision headline.
    """
    return copilot_auth_rejected(result) or copilot_auth_absent(result)


def copilot_auth_failure_headline(result: subprocess.CompletedProcess[str]) -> str:
    """Accurate failure headline for a Copilot run that died at the auth gate.

    Leads with the real cause (dead auth secret), not the misdiagnosed symptom
    (missing hook marker / rc=1), so the dogfood failure is actionable at a
    glance. Names which of the two auth failures happened, because "provision
    the secret" is wrong advice for a secret that exists and has expired.
    Uses a head+tail excerpt so the leading diagnostic sentence (where GitHub
    puts the cause) is preserved alongside the trailing boilerplate (issue #4504).
    """
    cause = (
        "Copilot auth token was rejected (expired or revoked); rotate "
        "COPILOT_GITHUB_TOKEN for the smoke job"
        if copilot_auth_rejected(result)
        else "Copilot auth token is empty; provision COPILOT_GITHUB_TOKEN for the smoke job"
    )
    return (
        f"{cause}. The shipped-base dogfood never ran (issue #3275). "
        f"rc={result.returncode} "
        f"stderr={_head_tail_excerpt(result.stderr)} "
        f"stdout={_head_tail_excerpt(result.stdout)}"
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
