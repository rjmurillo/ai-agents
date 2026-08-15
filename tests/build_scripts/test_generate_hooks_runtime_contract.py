#!/usr/bin/env python3
"""Runtime-contract regression guard for issue #2205 (Copilot CLI hook paths).

``test_generate_hooks_plugin_root.py`` asserts the *literal* command the
generator emits. That cannot prove the path RESOLVES at runtime, and it
cannot catch a wrong environment-variable name. A test that pins output to
itself is the canonical-source-mirror anti-pattern (see
``.claude/rules/canonical-source-mirror.md`` and the PR #1887 retro). The
original #2205 fix shipped exactly that kind of guard.

This test exercises the EMPIRICALLY VERIFIED Copilot CLI contract instead.
Measured against GitHub Copilot CLI 1.0.57 by installing a probe plugin
whose hook dumps its environment:

  * Copilot launches a plugin hook with ``cwd`` set to the user's working
    directory, NOT the plugin install dir.
  * It exports ``COPILOT_PLUGIN_ROOT`` and an alias ``CLAUDE_PLUGIN_ROOT``,
    both pointing at the plugin install dir (the directory that contains
    ``hooks/``).

The public hooks reference does not document these variables; the contract
is verified by experiment, not by the docs. This test reproduces that
contract: it generates hooks, then runs each emitted command from a
non-plugin ``cwd`` with the contract environment, and asserts the vendored
script is found. A negative control proves a bare ``./hooks/...`` command
fails the same harness, so the guard has teeth.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pytest

pytestmark = pytest.mark.windows_path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_hooks  # noqa: E402

# Faithful fixture: ``outputScripts`` ends in ``hooks`` exactly as the real
# ``templates/platforms/copilot-cli.yaml`` does, so the hardcoded ``hooks/``
# path prefix that ``_build_copilot_entry`` emits lines up with the on-disk
# script location. The plugin root is therefore ``<tmp>/plugin``.
_PLATFORM_YAML = """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  hooks:
    settingsSource: "settings.json"
    scriptSource: "hooks_src"
    outputConfig: "plugin/hooks/hooks.json"
    outputScripts: "plugin/hooks"
    eventRemap:
      SessionStart: SessionStart
      PreCompact: PreCompact
      UserPromptSubmit: UserPromptSubmit
      PreToolUse: PreToolUse
    eventDrop: []
    matcherPolicy: "inline-script-shim"
    versionField: 1
"""

# Writes a marker and emits branch-controlled text on both channels. Direct
# SessionStart rollback must preserve the side effect while suppressing the text.
_SCRIPT_BODY = """\
import os
import sys
from pathlib import Path

marker = os.environ.get("HOOK_MARKER")
if marker:
    Path(marker).write_text("HOOK_RAN", encoding="utf-8")
print("BRANCH_CONTROLLED_STDOUT")
print("BRANCH_CONTROLLED_STDERR", file=sys.stderr)
sys.exit(0)
"""

_USER_PROMPT_SCRIPT_BODY = """\
import json
import os
import sys
from pathlib import Path

raw = sys.stdin.read()
if raw:
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        print("BRANCH_CONTROLLED_PARSE_ERROR", file=sys.stderr)
        sys.exit(2)
marker = os.environ.get("HOOK_MARKER")
if marker:
    Path(marker).write_text("HOOK_RAN", encoding="utf-8")
sys.exit(0)
"""

_HOOK_SCRIPTS = [
    ("SessionStart", "init.py", None),
    ("PreCompact", "compact.py", None),
    ("UserPromptSubmit", "prompt.py", None),
    ("PreToolUse", "guard.py", "Bash"),  # matcher -> inline-script-shim
]


def _materialize(tmp_path: Path) -> Path:
    """Write platform config, settings.json, script tree, and a user cwd."""
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(_PLATFORM_YAML, encoding="utf-8")

    settings_hooks: dict[str, list[dict[str, object]]] = {}
    for event, fname, matcher in _HOOK_SCRIPTS:
        script = tmp_path / "hooks_src" / event / fname
        script.parent.mkdir(parents=True, exist_ok=True)
        body = _USER_PROMPT_SCRIPT_BODY if event == "UserPromptSubmit" else _SCRIPT_BODY
        script.write_text(body, encoding="utf-8")
        group: dict[str, object] = {
            "hooks": [{"type": "command", "command": f"python3 -u .claude/hooks/{event}/{fname}"}]
        }
        if matcher is not None:
            group["matcher"] = matcher
        settings_hooks.setdefault(event, []).append(group)

    (tmp_path / "settings.json").write_text(json.dumps({"hooks": settings_hooks}), encoding="utf-8")
    (tmp_path / "userland").mkdir()  # a cwd that is NOT the plugin root
    return cfg


def _generate(tmp_path: Path) -> dict[str, Any]:
    cfg = _materialize(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0, "generator returned non-zero"
    out = tmp_path / "plugin" / "hooks" / "hooks.json"
    return json.loads(out.read_text(encoding="utf-8"))


def _all_entries(doc: dict[str, Any]) -> list[dict[str, str]]:
    hooks = doc["hooks"]
    assert isinstance(hooks, dict), "hooks must be a dict"
    entries: list[dict[str, str]] = []
    for event_entries in hooks.values():
        entries.extend(event_entries)
    assert entries, "fixture produced no hook entries"
    return entries


def _first_bash_command(doc: dict[str, object], event: str) -> str:
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        raise AssertionError("hooks must be a dict")
    entries = hooks.get(event)
    if not isinstance(entries, list) or not entries:
        raise AssertionError(f"{event} must contain hook entries")
    entry = entries[0]
    if not isinstance(entry, dict):
        raise AssertionError(f"{event} entry must be a dict")
    command = entry.get("bash")
    if not isinstance(command, str):
        raise AssertionError(f"{event} entry must contain a bash command")
    return command


def _path_arg(command: str) -> str:
    """Return the single double-quoted argument from a generated command.

    Generated commands have exactly one double-quoted token (the script
    path); neither the launcher nor the path expression contains a quote.
    """
    parts = command.split('"')
    assert len(parts) == 3, f"expected one quoted arg in: {command!r}"
    return parts[1]


def _contract_env(*, copilot_root: str | None, claude_root: str | None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    if copilot_root is not None:
        env["COPILOT_PLUGIN_ROOT"] = copilot_root
    if claude_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = claude_root
    return env


_WSL_LAUNCHER_MARKER = "Windows Subsystem for Linux".encode("utf-16-le").decode("utf-8")


def _probe_failure(candidate: str) -> str | None:
    """Return why ``candidate`` cannot run a bash command, or None on success."""
    try:
        proc = subprocess.run(
            [candidate, "-c", 'printf "%s" ok'],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"{candidate}: probe timed out after 20 seconds"
    except OSError as exc:
        return f"{candidate}: could not start: {exc}"

    output = proc.stdout + proc.stderr
    if _WSL_LAUNCHER_MARKER in output:
        return f"{candidate}: rejected the Windows WSL launcher stub; use Git Bash instead"
    if proc.returncode != 0:
        return (
            f"{candidate}: probe exited {proc.returncode}; "
            f"stdout={proc.stdout[:200]!r}; stderr={proc.stderr[:200]!r}"
        )
    if proc.stdout != "ok":
        return f"{candidate}: probe did not execute the command; stdout={proc.stdout[:200]!r}"
    return None


def _probes_ok(candidate: str) -> bool:
    """Return True when ``candidate`` actually runs a bash command.

    Split out from ``_resolve_bash`` so the rejection behavior is testable: the
    stub this exists to reject cannot be installed on a Linux runner, so the
    only way to prove the guard has teeth is to hand this function a fake one.
    """
    return _probe_failure(candidate) is None


def _bash_candidates(platform: str, on_path: str | None) -> tuple[str, ...]:
    """Return ordered bash candidates for ``platform`` without duplicates."""
    candidates: list[str] = []
    if platform == "win32":
        # Git for Windows ships a real bash in both bin layouts. Probe these
        # before PATH, where windows-latest exposes the unusable WSL launcher.
        candidates.extend(
            [
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files\Git\usr\bin\bash.exe",
                r"C:\Program Files (x86)\Git\bin\bash.exe",
                r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
            ]
        )
    if on_path is not None:
        candidates.append(on_path)
    return tuple(dict.fromkeys(candidates))


def _resolve_bash(candidates: tuple[str, ...]) -> tuple[str | None, tuple[str, ...]]:
    """Return the first working bash plus diagnostics for rejected candidates.

    On Windows ``bash`` on PATH is ``C:\\Windows\\System32\\bash.exe``, the WSL
    launcher. With no distribution installed it exits non-zero and writes a
    UTF-16LE notice to stdout without running anything. ``shutil.which("bash")``
    finds that stub and reports bash present, so a which-based guard is not
    enough: every candidate has to be probed.
    """
    failures: list[str] = []
    for candidate in candidates:
        failure = _probe_failure(candidate)
        if failure is None:
            return candidate, tuple(failures)
        failures.append(failure)
    return None, tuple(failures)


_RESOLVED_BASH, _BASH_PROBE_FAILURES = _resolve_bash(
    _bash_candidates(sys.platform, shutil.which("bash"))
)


def _require_bash() -> str:
    """Return a working bash or fail closed without skipping contract tests."""
    if _RESOLVED_BASH is not None:
        return _RESOLVED_BASH

    details = "\n".join(f"- {failure}" for failure in _BASH_PROBE_FAILURES)
    if not details:
        details = "- no bash candidates were found"
    hint = (
        "Install Git Bash or repair its installation."
        if sys.platform == "win32"
        else "Install bash or make it available on PATH."
    )
    raise AssertionError(
        "no working bash resolved; refusing to skip the runtime contract. "
        f"{hint}\nProbe results:\n{details}"
    )


def _bash_resolve(path_expr: str, env: dict[str, str], cwd: Path) -> str:
    """Expand a bash path expression under ``env`` and ``cwd``."""
    proc = subprocess.run(
        [_require_bash(), "-c", f'printf "%s" "{path_expr}"'],
        env=env,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _slash(text: str) -> str:
    """Normalize path separators so Windows and POSIX compare the same.

    PowerShell echoes a root back with the separator it was handed and pathlib
    hands it native ones, so a raw string comparison fails on Windows for a
    reason that has nothing to do with the contract under test.

    Runs of backslashes collapse to a single forward slash. CPython renders the
    path in ``can't open file '...'`` with each separator doubled, so a
    one-for-one replacement yields ``C://Users//runneradmin`` and the
    comparison fails against a correctly resolved ``C:/Users/runneradmin``.
    """
    return re.sub(r"\\+", "/", text)


def _pwsh_resolve(path_expr: str, env: dict[str, str], cwd: Path) -> str:
    """Expand a PowerShell path expression under ``env`` and ``cwd``."""
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", f'[Console]::Out.Write("{path_expr}")'],
        env=env,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_every_bash_command_resolves_to_an_existing_script(tmp_path: Path) -> None:
    """Every emitted bash path resolves to a real file under the contract."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    for entry in _all_entries(doc):
        resolved = _bash_resolve(_path_arg(entry["bash"]), env, userland)
        assert Path(resolved).is_file(), f"unresolved: {resolved!r} from {entry['bash']!r}"


def test_bash_falls_back_to_claude_plugin_root(tmp_path: Path) -> None:
    """When COPILOT_PLUGIN_ROOT is unset, CLAUDE_PLUGIN_ROOT resolves it."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=None, claude_root=plugin_root)
    for entry in _all_entries(doc):
        resolved = _bash_resolve(_path_arg(entry["bash"]), env, userland)
        assert Path(resolved).is_file(), f"fallback failed: {resolved!r}"


@pytest.mark.parametrize("event", ["SessionStart", "PreCompact", "UserPromptSubmit"])
def test_direct_rollback_runs_silently_with_side_effects(
    tmp_path: Path,
    event: str,
) -> None:
    """A direct rollback command retains work without leaking repository prose."""
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    marker = tmp_path / f"{event}-ran.txt"
    env["HOOK_MARKER"] = str(marker)
    proc = subprocess.run(
        [_require_bash(), "-c", _first_bash_command(doc, event)],
        env=env,
        cwd=userland,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        input="",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert marker.read_text(encoding="utf-8") == "HOOK_RAN"
    assert proc.stdout == ""
    assert proc.stderr == ""


def test_user_prompt_direct_failure_is_silent_and_nonzero(tmp_path: Path) -> None:
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)

    proc = subprocess.run(
        [_require_bash(), "-c", _first_bash_command(doc, "UserPromptSubmit")],
        env=env,
        cwd=userland,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        input="{bad json",
        check=False,
    )

    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr == ""


def test_committed_pretooluse_timeout_includes_dispatcher_headroom() -> None:
    """The shipped dispatcher has time beyond its shim budgets."""
    hooks_root = REPO_ROOT / "src" / "copilot-cli" / "hooks"
    hooks_doc = json.loads((hooks_root / "hooks.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (hooks_root / "PreToolUse" / "_manifest.json").read_text(encoding="utf-8")
    )

    shim_timeouts = list(manifest["timeouts"].values())
    timeout_sec = hooks_doc["hooks"]["PreToolUse"][0]["timeoutSec"]

    assert shim_timeouts
    assert timeout_sec > sum(shim_timeouts)


def test_negative_control_bare_relative_path_fails(tmp_path: Path) -> None:
    """The pre-fix bare ``./hooks/...`` form fails the same harness (teeth)."""
    _generate(tmp_path)  # materialize the plugin tree; return value unused here
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=plugin_root, claude_root=plugin_root)
    # Reconstruct the regression: strip the plugin-root anchor, keep the path.
    bare = 'python3 -u "./hooks/SessionStart/init.py"'
    proc = subprocess.run(
        [_require_bash(), "-c", bare],
        env=env,
        cwd=userland,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        input="",
        check=False,
    )
    assert proc.returncode != 0, "bare relative path unexpectedly resolved"
    # Positive limb. A non-zero exit alone cannot tell "the command ran and
    # failed as designed" from "no shell ran at all": the Windows WSL launcher
    # stub also exits non-zero, so this control passed on Windows for months
    # while never invoking a shell. A shell that actually ran writes its
    # diagnostic to stderr; the stub writes a notice to stdout and leaves
    # stderr empty.
    assert proc.stderr.strip(), (
        f"no shell diagnostic on stderr, so the command may never have run. stdout={proc.stdout!r}"
    )


def test_anchor_is_load_bearing_when_no_plugin_root_var_set(tmp_path: Path) -> None:
    """With neither plugin-root var set, the anchored path must NOT resolve.

    This distinguishes "given the variable, the path resolves" (the positive
    tests, which set the variable themselves) from "the variable is what makes it
    resolve". With both vars unset the bash fallback expands to ``/hooks/...``
    (absolute, off the filesystem root), so the anchored suffix is no longer
    under any plugin root. Without this control the suite could pass while
    production breaks if a host CLI stopped exporting the variable (the variable
    would not actually be load-bearing).
    NB: this verifies path resolution, not that the host CLI *sets* the variable;
    only the real-CLI e2e (tests/e2e/test_cli_hook_e2e.py) verifies vendor behavior.
    """
    doc = _generate(tmp_path)
    userland = tmp_path / "userland"
    env = _contract_env(copilot_root=None, claude_root=None)
    command = _first_bash_command(doc, "SessionStart")
    resolved = _bash_resolve(_path_arg(command), env, userland)
    # Assert the fallback EXPANSION VALUE directly rather than probing the host
    # root filesystem (a /hooks/... file on the runner would otherwise flake the
    # test). With no plugin-root var the prefix collapses to empty, so the path
    # is rooted at /hooks/ instead of under the plugin root: that proves the var
    # is the load-bearing prefix.
    assert resolved.startswith("/hooks/"), (
        f"expected fallback to collapse to /hooks/..., got {resolved!r}; "
        "the env var is not load-bearing"
    )
    assert not resolved.startswith(str(userland)), (
        f"anchored path unexpectedly resolved under userland: {resolved!r}"
    )


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
def test_every_powershell_command_resolves_under_pwsh(tmp_path: Path) -> None:
    """Every emitted powershell path resolves under pwsh, incl. the fallback.

    Batches all Test-Path checks into a single pwsh invocation per scenario
    to avoid N subprocess spawns that flake under xdist load (issue #4928).
    """
    doc = _generate(tmp_path)
    plugin_root = str(tmp_path / "plugin")
    userland = tmp_path / "userland"
    scenarios = [
        _contract_env(copilot_root=plugin_root, claude_root=plugin_root),
        _contract_env(copilot_root=None, claude_root=plugin_root),  # fallback
    ]
    entries = _all_entries(doc)
    ps_exprs = [_path_arg(entry["powershell"]) for entry in entries]

    for env in scenarios:
        # Build a single script that checks every path and emits OK/MISSING
        checks = "; ".join(
            f'if (Test-Path "{expr}") {{ "OK:{expr}" }} else {{ "MISSING:{expr}" }}'
            for expr in ps_exprs
        )
        proc = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", checks],
            env=env,
            cwd=userland,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        lines = [ln for ln in proc.stdout.splitlines() if ln]
        assert len(lines) == len(ps_exprs), (
            f"pwsh emitted {len(lines)} lines, expected {len(ps_exprs)}"
        )
        for line in lines:
            assert line.startswith("OK:"), f"unresolved powershell path: {line}"


def test_stale_plugin_root_failure_names_the_missing_path(tmp_path: Path) -> None:
    """A stale plugin root fails closed AND the error names the full path.

    ``agent-harness-reference`` documents this failure mode and rejects an
    existence check in the launcher command strings on the grounds that the
    interpreter error already names the missing path (issues #3321, #3332).
    That rejection is only sound while the claim holds. This test makes the
    claim falsifiable: if a future interpreter or launcher shape stopped
    naming the path, the guard argument would have to be revisited and this
    goes red first.

    Uses the committed hooks.json dispatcher command (the shipped artifact)
    instead of the _generate() fixture, whose platform config does not enable
    consolidated dispatcher routing. This aligns the test with what actually
    ships (ADR-068).
    """
    # Read the committed hooks.json - the shipped artifact uses the dispatcher
    hooks_root = REPO_ROOT / "src" / "copilot-cli" / "hooks"
    hooks_doc = json.loads((hooks_root / "hooks.json").read_text(encoding="utf-8"))

    stale_root = tmp_path / "moved-away"
    assert not stale_root.exists()
    env = _contract_env(copilot_root=str(stale_root), claude_root=str(stale_root))
    userland = tmp_path / "userland"
    userland.mkdir(parents=True, exist_ok=True)

    command = _first_bash_command(hooks_doc, "PreToolUse")
    proc = subprocess.run(
        [_require_bash(), "-c", command],
        env=env,
        cwd=userland,
        input="{}",
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    # Post-fix (issue 4672): stale plugin root is infrastructure failure,
    # so the hook fails OPEN (exit 0 with warning) rather than denying.
    assert proc.returncode == 0, (
        f"stale plugin root must fail open (exit 0) per issue 4672, got {proc.returncode}"
    )
    assert "WARNING: hooks DISABLED" in proc.stderr, (
        "stale root must emit an actionable warning on stderr"
    )
    normalized_stderr = _slash(proc.stderr)
    assert stale_root.as_posix() in normalized_stderr, (
        "warning must name the missing path so the user can act on it. "
        f"stderr={proc.stderr!r}"
    )


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
def test_stale_plugin_root_powershell_failure_names_the_missing_path(
    tmp_path: Path,
) -> None:
    """The PowerShell launcher also exposes the stale path when it fails."""
    hooks_root = REPO_ROOT / "src" / "copilot-cli" / "hooks"
    hooks_doc = json.loads((hooks_root / "hooks.json").read_text(encoding="utf-8"))
    stale_root = tmp_path / "moved-away"
    env = _contract_env(copilot_root=str(stale_root), claude_root=str(stale_root))
    command = hooks_doc["hooks"]["PreToolUse"][0]["powershell"]

    # Linux CI has pwsh and python3, but not the Windows py launcher.
    if sys.platform != "win32":
        command = command.replace("py -3", "python3", 1)
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        env=env,
        cwd=tmp_path,
        input="{}",
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    # Post-fix (issue 4672): stale plugin root is infrastructure failure,
    # so the hook fails OPEN (exit 0 with warning) rather than denying.
    assert proc.returncode == 0, (
        f"stale plugin root must fail open (exit 0) per issue 4672, got {proc.returncode}"
    )
    # PowerShell Write-Host goes to stdout when captured by subprocess
    combined = proc.stdout + proc.stderr
    assert "WARNING: hooks DISABLED" in combined, (
        "stale root must emit an actionable warning"
    )
    normalized = _slash(combined)
    assert stale_root.as_posix() in normalized, (
        "PowerShell warning must name the missing path so the user can act on it. "
        f"output={combined!r}"
    )


class TestSubprocessDecoding:
    """Captured launcher output must be decoded explicitly, not by locale.

    This module drives real ``bash`` and ``pwsh`` and asserts on their stderr.
    On Windows an unset encoding decodes as cp1252, the reader thread dies
    mid-decode on a non-ASCII path, and ``proc.stderr`` comes back as None
    instead of raising. The stale-root assertion then fails with a NoneType
    error that says nothing about the contract it was guarding.
    """

    # Built from parts so the guard below does not match its own needle.
    _CAPTURING = "capture_output" + "=True,"
    _CODEC = 'encoding="' + 'utf-8",'
    _ERRORS = 'errors="' + 'replace",'
    _TEXT_MODE = "text" + "=True"

    def _source(self) -> str:
        return Path(__file__).read_text(encoding="utf-8")

    def test_every_capture_pins_the_codec(self) -> None:
        source = self._source()
        assert source.count(self._CAPTURING) == source.count(self._CODEC)

    def test_every_capture_tolerates_undecodable_bytes(self) -> None:
        source = self._source()
        assert source.count(self._CAPTURING) == source.count(self._ERRORS)

    def test_no_capture_relies_on_text_mode_alone(self) -> None:
        assert self._TEXT_MODE not in self._source()


class TestSeparatorNormalization:
    """The Windows separator fix, made falsifiable on any platform.

    On POSIX a Windows-shaped path never appears, so running the stale-root
    test on Linux cannot tell a working normalizer from a missing one. These
    feed the shapes directly.
    """

    def test_a_windows_resolved_path_is_converted(self) -> None:
        resolved = r"C:\Users\runneradmin\Temp\moved-away\hooks\PreToolUse\x.py"
        assert _slash(resolved) == "C:/Users/runneradmin/Temp/moved-away/hooks/PreToolUse/x.py"

    def test_a_posix_path_is_left_alone(self) -> None:
        resolved = "/tmp/pytest-0/moved-away/hooks/PreToolUse/x.py"
        assert _slash(resolved) == resolved

    def test_a_windows_root_then_matches_the_resolved_path(self) -> None:
        """The comparison the stale-root test makes, with Windows shapes."""
        root = PurePosixPath(PureWindowsPath(r"C:\Users\runneradmin\moved-away").as_posix())
        resolved = r"C:\Users\runneradmin\moved-away\hooks\PreToolUse\x.py"
        assert str(root) in _slash(resolved)

    def test_a_mismatched_root_still_fails(self) -> None:
        """Guard the guard: normalization must not make everything match."""
        root = PurePosixPath(PureWindowsPath(r"C:\Users\runneradmin\elsewhere").as_posix())
        resolved = r"C:\Users\runneradmin\moved-away\hooks\PreToolUse\x.py"
        assert str(root) not in _slash(resolved)

    def test_doubled_separators_collapse_to_one(self) -> None:
        """CPython doubles each separator inside ``can't open file '...'``.

        A one-for-one replacement turned ``C:\\\\Users`` into ``C://Users`` and
        the stale-root assertion failed on ``windows-latest`` while every POSIX
        run stayed green. Run 30878223824 is the observed failure.
        """
        assert _slash(r"C:\\Users\\runneradmin") == "C:/Users/runneradmin"

    def test_single_and_doubled_separators_agree(self) -> None:
        """The invariant the fix rests on, stated directly."""
        assert _slash(r"C:\Users\x.py") == _slash(r"C:\\Users\\x.py")

    def test_the_observed_windows_stderr_names_the_expected_path(self) -> None:
        """The verbatim failure from run 30878223824, as a regression test.

        The interpreter prefix carries single separators and the quoted path
        carries doubled ones, with a forward-slash tail from the launcher
        argument. All three shapes appear in one string.
        """
        stderr = (
            r"C:\hostedtoolcache\windows\Python\3.14.6\x64\python3.exe: "
            r"can't open file 'C:\\Users\\runneradmin\\AppData\\Local\\Temp"
            r"\\pytest-of-runneradmin\\pytest-0\\test_stale_plugin_root_failure0"
            r"\\moved-away/hooks/PreToolUse/_dispatch.py': "
            "[Errno 2] No such file or directory\n"
        )
        expected = (
            "C:/Users/runneradmin/AppData/Local/Temp/pytest-of-runneradmin/"
            "pytest-0/test_stale_plugin_root_failure0/moved-away/hooks/"
            "PreToolUse/_dispatch.py"
        )
        assert expected in _slash(stderr)

    def test_the_observed_stderr_rejects_a_path_it_does_not_name(self) -> None:
        """Guard the guard on the real shape, not just the synthetic one."""
        stderr = (
            r"can't open file 'C:\\Users\\runneradmin\\moved-away"
            r"/hooks/PreToolUse/_dispatch.py'"
        )
        absent = "C:/Users/runneradmin/still-here/hooks/PreToolUse/_dispatch.py"
        assert absent not in _slash(stderr)


class TestBashProbe:
    """The bash guard must reject a launcher that never runs a command.

    Issue #4516: on ``windows-latest`` ``bash`` resolves to the WSL launcher.
    With no distribution installed it exits non-zero and writes a UTF-16LE
    notice to stdout, so ``shutil.which("bash")`` reports bash present while
    every command in this file silently fails to run. Eight assertions here
    failed that way, and the negative control kept passing because a dead
    launcher also returns non-zero.
    """

    _WSL_NOTICE = "Windows Subsystem for Linux has no installed distributions.\n"

    def test_a_real_bash_probes_ok(self) -> None:
        """Positive: the probe accepts the interpreter the suite actually uses."""
        assert _probes_ok(_require_bash())

    def test_the_wsl_launcher_stub_is_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Negative: a UTF-16LE writer that exits non-zero is not a bash."""
        stub = r"C:\Windows\System32\bash.exe"
        notice = self._WSL_NOTICE.encode("utf-16-le").decode("utf-8")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda command, **_kwargs: subprocess.CompletedProcess(
                command,
                1,
                stdout=notice,
                stderr="",
            ),
        )
        failure = _probe_failure(stub)
        assert failure is not None
        assert stub in failure
        assert "Windows WSL launcher stub" in failure

    def test_windows_candidates_prefer_git_bash_over_path(self) -> None:
        """Windows probes Git Bash before the PATH WSL launcher."""
        wsl = r"C:\Windows\System32\bash.exe"
        candidates = _bash_candidates("win32", wsl)
        assert candidates == (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
            wsl,
        )

    def test_resolver_falls_through_a_rejected_candidate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A dead launcher cannot prevent a later working bash from running."""
        stub = r"C:\Windows\System32\bash.exe"
        working = r"C:\Program Files\Git\bin\bash.exe"
        notice = self._WSL_NOTICE.encode("utf-16-le").decode("utf-8")

        def fake_run(
            command: list[str],
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if command[0] == stub:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=notice,
                    stderr="",
                )
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        resolved, failures = _resolve_bash((stub, working))
        assert resolved == working
        assert len(failures) == 1
        assert stub in failures[0]

    def test_a_timeout_falls_through_to_the_next_candidate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A hanging launcher is diagnosed without blocking a later bash."""
        hanging = "hanging-bash"
        working = "working-bash"

        def fake_run(
            command: list[str],
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if command[0] == hanging:
                raise subprocess.TimeoutExpired(command, 20)
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        resolved, failures = _resolve_bash((hanging, working))
        assert resolved == working
        assert failures == (f"{hanging}: probe timed out after 20 seconds",)

    def test_a_zero_exit_that_runs_nothing_is_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Edge: exit 0 is not enough; the probe's output has to come back."""
        stub = "no-op-bash"
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda command, **_kwargs: subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="",
            ),
        )
        assert not _probes_ok(stub)

    def test_ok_on_stdout_with_a_nonzero_exit_is_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Negative: stdout is half the contract, the exit code is the other half.

        Adversarial review found that dropping ``proc.returncode == 0`` from the
        probe survives every other test in this class. A launcher can echo the
        probe text and still have failed.
        """
        stub = "failing-bash"
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda command, **_kwargs: subprocess.CompletedProcess(
                command,
                1,
                stdout="ok",
                stderr="",
            ),
        )
        assert not _probes_ok(stub)

    def test_a_missing_binary_is_rejected(self, tmp_path: Path) -> None:
        """Edge: a candidate path that does not exist must not raise."""
        missing = str(tmp_path / "no-such-bash")
        failure = _probe_failure(missing)
        assert failure is not None
        assert missing in failure

    def test_missing_bash_fails_each_contract_instead_of_skipping(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No candidate is a hard contract failure with actionable evidence."""
        marker = (
            r"C:\Windows\System32\bash.exe: rejected the Windows WSL launcher "
            "stub; use Git Bash instead"
        )
        monkeypatch.setitem(globals(), "_RESOLVED_BASH", None)
        monkeypatch.setitem(globals(), "_BASH_PROBE_FAILURES", (marker,))

        with pytest.raises(AssertionError, match="refusing to skip") as exc_info:
            _require_bash()

        assert "Windows WSL launcher stub" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("platform", "expected_hint"),
        [
            ("win32", "Install Git Bash or repair its installation."),
            ("linux", "Install bash or make it available on PATH."),
        ],
    )
    def test_missing_bash_hint_matches_the_platform(
        self,
        monkeypatch: pytest.MonkeyPatch,
        platform: str,
        expected_hint: str,
    ) -> None:
        """A missing interpreter reports an actionable platform-specific hint."""
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setitem(globals(), "_RESOLVED_BASH", None)
        monkeypatch.setitem(globals(), "_BASH_PROBE_FAILURES", ())

        with pytest.raises(AssertionError, match=expected_hint):
            _require_bash()

    def test_the_negative_control_requires_a_shell_diagnostic(self) -> None:
        """The control's stderr limb is what a dead launcher cannot satisfy.

        Without it the control asserts only ``returncode != 0``, which the stub
        satisfies. This pins the discriminator itself, so a future edit cannot
        drop the limb and leave a control that passes without a shell.
        """
        source = Path(__file__).read_text(encoding="utf-8")
        # Built from fragments on purpose. Spelled whole, this line would be a
        # second occurrence in the file, so the assertion below would survive
        # deletion of the limb it exists to protect.
        marker = "no shell diagnostic" + " on stderr"
        assert source.count(marker) == 1, (
            "expected exactly one occurrence of the stderr limb, found "
            f"{source.count(marker)}. Zero means "
            "test_negative_control_bare_relative_path_fails lost its positive "
            "limb and now passes under any launcher that exits non-zero. More "
            "than one means this guard can no longer tell the difference."
        )
