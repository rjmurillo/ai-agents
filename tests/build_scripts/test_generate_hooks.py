"""Tests for build/scripts/generate_hooks.py (REQ-003-007, M5).

Coverage matrix (positive AND negative for every behavior branch):

- classify_matcher disambiguation (regex / tool-glob / bare)
- normalize_tool_args whitespace collapse + dict/scalar handling
- glob_or_match top-level `|` OR-fold
- inject_shim end-to-end via subprocess (shim fires when matched, no-op
  exit 0 when not matched, exit 2 on shim crash)
- inject_shim idempotency (single sentinel after repeat injection,
  byte-identical for same matcher)
- strip_shim restores body
- generate_hooks driver: eventRemap, eventDrop, version:1 wrapper,
  python3/py -3 invocation strings, NO-REGEN sentinel, malformed
  settings.json, missing eventRemap
- live-corpus regression: classify every matcher in the live
  .claude/settings.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_hooks  # noqa: E402
from generate_hooks import (  # noqa: E402
    _SHIM_BEGIN,
    _SHIM_END,
    MATCHER_BARE,
    MATCHER_REGEX,
    MATCHER_TOOL_GLOB,
    _ensure_exact_case_dir,
    _matcher_suffix,
    classify_matcher,
    glob_or_match,
    inject_shim,
    is_shimmed,
    normalize_tool_args,
    strip_shim,
)

# Helpers -------------------------------------------------------------------


def _run_shim(transformed_source: str, payload: dict) -> subprocess.CompletedProcess:
    """Execute a shimmed script with payload on stdin; return CompletedProcess.

    Each call writes to a fresh temp file so concurrent test workers do
    not race on a shared path.
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False
    ) as handle:
        handle.write(transformed_source)
        path = handle.name
    try:
        return subprocess.run(
            ["python3", path],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
        )
    finally:
        os.unlink(path)


def _run_shim_raw(transformed_source: str, raw_input: bytes) -> subprocess.CompletedProcess:
    """Execute a shimmed script with raw bytes on stdin.

    Used to exercise stdin-cap behavior where the input is intentionally
    not valid JSON (or simply too large) so the shim's cap path runs
    before any json.loads attempt.
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False
    ) as handle:
        handle.write(transformed_source)
        path = handle.name
    try:
        return subprocess.run(
            ["python3", path],
            input=raw_input,
            capture_output=True,
            timeout=20,
        )
    finally:
        os.unlink(path)


def _write_settings(path: Path, hooks_obj: dict) -> Path:
    path.write_text(json.dumps({"hooks": hooks_obj}, indent=2), encoding="utf-8")
    return path


def _write_config(tmp_path: Path, *, hooks_stanza_overrides: dict | None = None) -> Path:
    cfg = tmp_path / "platform.yaml"
    body = """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  hooks:
    settingsSource: "settings.json"
    scriptSource: "hooks_src"
    outputConfig: "out/hooks.json"
    outputScripts: "out"
    eventRemap:
      PreToolUse: PreToolUse
      PostToolUse: PostToolUse
      Stop: SessionEnd
      SessionStart: SessionStart
      UserPromptSubmit: UserPromptSubmit
    eventDrop:
      - SubagentStop
      - PermissionRequest
      - Notification
      - PreCompact
    matcherPolicy: "inline-script-shim"
    versionField: 1
"""
    cfg.write_text(body, encoding="utf-8")
    return cfg


def _write_script(scripts_dir: Path, event: str, name: str, body: str = "") -> Path:
    target = scripts_dir / event / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not body:
        body = (
            "import sys, json\n"
            "data = json.load(sys.stdin) if sys.stdin else {}\n"
            'print("FIRED:" + (data.get("tool_name") or ""))\n'
            "sys.exit(0)\n"
        )
    target.write_text(body, encoding="utf-8")
    return target


# --- classify_matcher (positive + negative) -------------------------------


@pytest.mark.parametrize(
    ("pattern", "expected_kind", "expected_params"),
    [
        # regex
        ("^Edit$", MATCHER_REGEX, {"pattern": "^Edit$"}),
        ("^(Edit|Write)$", MATCHER_REGEX, {"pattern": "^(Edit|Write)$"}),
        # tool-glob
        ("Bash(git commit*)", MATCHER_TOOL_GLOB, {"toolName": "Bash", "argsGlob": "git commit*"}),
        (
            "Bash(npm test*|pytest*)",
            MATCHER_TOOL_GLOB,
            {"toolName": "Bash", "argsGlob": "npm test*|pytest*"},
        ),
        # bare
        ("Bash", MATCHER_BARE, {"toolName": "Bash"}),
        (
            "mcp__serena__write_memory",
            MATCHER_BARE,
            {"toolName": "mcp__serena__write_memory"},
        ),
    ],
)
def test_classify_matcher_positive(pattern, expected_kind, expected_params):
    kind, params = classify_matcher(pattern)
    assert kind == expected_kind
    assert params == expected_params


def test_classify_matcher_anchored_only_one_side_is_bare():
    """A pattern with only `^` (no trailing `$`) is bare, not regex."""
    kind, params = classify_matcher("^Edit")
    assert kind == MATCHER_BARE
    assert params == {"toolName": "^Edit"}


def test_classify_matcher_paren_form_with_invalid_identifier_is_bare():
    """Parens following a non-identifier prefix don't classify as tool-glob."""
    kind, _ = classify_matcher("123(foo)")
    assert kind == MATCHER_BARE


# --- normalize_tool_args + glob_or_match ---------------------------------


def test_normalize_collapses_whitespace():
    assert normalize_tool_args({"command": "git  commit -m   foo"}) == "git commit -m foo"


def test_normalize_strips_leading_trailing():
    assert normalize_tool_args("  spaced  ") == "spaced"


def test_normalize_handles_tabs_and_newlines():
    assert normalize_tool_args("multi\tline\nval") == "multi line val"


def test_normalize_none_returns_empty():
    assert normalize_tool_args(None) == ""


def test_normalize_dict_without_command_falls_back_to_json():
    out = normalize_tool_args({"foo": "bar", "baz": 1})
    # Order is sorted; no guarantee on exact spacing, but sort_keys=True
    # stabilizes: '{"baz": 1, "foo": "bar"}'.
    assert out == '{"baz": 1, "foo": "bar"}'


def test_normalize_scalar_int():
    assert normalize_tool_args(42) == "42"


def test_glob_or_match_single_branch_positive():
    assert glob_or_match("git commit*", "git commit -m foo")


def test_glob_or_match_single_branch_negative():
    assert not glob_or_match("git commit*", "git push origin")


def test_glob_or_match_or_fold_positive_first_branch():
    assert glob_or_match("npm test*|pytest*|go test*", "npm test")


def test_glob_or_match_or_fold_positive_middle_branch():
    assert glob_or_match("npm test*|pytest*|go test*", "pytest -v")


def test_glob_or_match_or_fold_no_match():
    assert not glob_or_match("npm test*|pytest*", "cargo build")


def test_glob_or_match_empty_pattern_matches_empty_string():
    assert glob_or_match("", "")


# --- inject_shim end-to-end (subprocess) ---------------------------------


_TRACE_SCRIPT = (
    "import sys, json\n"
    "data = json.load(sys.stdin) if sys.stdin else {}\n"
    'print("FIRED:" + (data.get("tool_name") or ""))\n'
    "sys.exit(0)\n"
)


def test_inject_shim_caps_stdin_at_2mib():
    """The generated shim must reject oversized stdin BEFORE delegating
    to the wrapped script.

    push_guard_base.MAX_STDIN_BYTES (1 MiB) only applies after the shim
    has buffered everything; without the shim-level cap, an attacker
    could exhaust memory before any guard logic ran (CWE-400). The shim
    caps at _SHIM_MAX_STDIN_BYTES = 2 MiB and exits 2 with a stderr
    explanation. PR #1887 review thread PRRT_kwDOQoWRls5_r7WA.
    """
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    # 2 MiB + 1 byte: one over the cap. Use ASCII whitespace so the
    # bytes are valid stdin even though we never expect json.loads to run.
    oversize = b" " * (2 * 1024 * 1024 + 1)
    proc = _run_shim_raw(transformed, oversize)
    assert proc.returncode == 2
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert "stdin exceeds" in stderr
    assert "2097152" in stderr  # _SHIM_MAX_STDIN_BYTES literal value


def test_inject_shim_accepts_at_cap_boundary():
    """Exactly at the cap is allowed; one over rejects (boundary check)."""
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = json.dumps({"tool_name": "Read"}).encode("utf-8")  # no fire
    # Pad to exactly _SHIM_MAX_STDIN_BYTES; the read uses MAX+1 so this
    # path returns len == MAX (no overflow), shim proceeds normally.
    pad = b" " * (2 * 1024 * 1024 - len(payload))
    raw = pad + payload
    assert len(raw) == 2 * 1024 * 1024
    proc = _run_shim_raw(transformed, raw)
    # tool_name=Read does not match ^Edit$, so shim no-ops with rc=0.
    assert proc.returncode == 0


def test_inject_shim_fires_on_regex_match():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    proc = _run_shim(transformed, {"tool_name": "Edit"})
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Edit")


def test_inject_shim_no_op_on_regex_miss():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    proc = _run_shim(transformed, {"tool_name": "Read"})
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_fires_on_tool_glob_match():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'x'"}},
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_no_op_on_tool_glob_args_miss():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {"tool_name": "Bash", "tool_input": {"command": "git push"}},
    )
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_no_op_on_tool_glob_wrong_tool():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(transformed, {"tool_name": "Edit"})
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_fires_on_bare_match_any_args():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(
        transformed,
        {"tool_name": "Bash", "tool_input": {"command": "anything goes"}},
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_no_op_on_bare_miss():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(transformed, {"tool_name": "Edit"})
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_fires_on_mcp_namespaced_bare():
    transformed = inject_shim(_TRACE_SCRIPT, "mcp__serena__write_memory")
    proc = _run_shim(transformed, {"tool_name": "mcp__serena__write_memory"})
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:mcp__serena__write_memory")


def test_inject_shim_multi_pipe_glob_first_branch():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(npm test*|pytest*)")
    proc = _run_shim(
        transformed, {"tool_name": "Bash", "tool_input": {"command": "npm test"}}
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_multi_pipe_glob_second_branch():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(npm test*|pytest*)")
    proc = _run_shim(
        transformed, {"tool_name": "Bash", "tool_input": {"command": "pytest -v"}}
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_multi_pipe_glob_neither_branch():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(npm test*|pytest*)")
    proc = _run_shim(
        transformed, {"tool_name": "Bash", "tool_input": {"command": "cargo build"}}
    )
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_whitespace_normalization_double_space():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {"tool_name": "Bash", "tool_input": {"command": "git  commit  -m  foo"}},
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


# --- inject_shim crash policy --------------------------------------------


def test_inject_shim_exits_2_on_missing_tool_name():
    """A payload without `tool_name` is a config error: exit 2 to stderr."""
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(transformed, {"foo": "bar"})
    assert proc.returncode == 2
    assert "matcher-shim" in proc.stderr


def _run_shim_with_env(
    transformed_source: str, payload: dict, env_extra: dict
) -> subprocess.CompletedProcess:
    """Run a shimmed script with extra environment variables.

    Mirrors :func:`_run_shim` but threads through ``env_extra`` so tests
    can flip ``COPILOT_HOOK_DEBUG`` without leaking into other tests.
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False
    ) as handle:
        handle.write(transformed_source)
        path = handle.name
    try:
        merged = {**os.environ, **env_extra}
        return subprocess.run(
            ["python3", path],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
            env=merged,
        )
    finally:
        os.unlink(path)


def test_copilot_hook_debug_env_emits_trace():
    """When COPILOT_HOOK_DEBUG=1, shim writes a kind/fired trace to stderr (P2-2)."""
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim_with_env(
        transformed,
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m foo"}},
        env_extra={"COPILOT_HOOK_DEBUG": "1"},
    )
    assert proc.returncode == 0
    assert "kind=tool-glob" in proc.stderr
    assert "fired=True" in proc.stderr
    assert "Bash(git commit*)" in proc.stderr


def test_copilot_hook_debug_unset_emits_no_trace():
    """When COPILOT_HOOK_DEBUG is unset, no trace appears in stderr (P2-2)."""
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    # Explicitly clear the var via env_extra={"COPILOT_HOOK_DEBUG": ""}.
    proc = _run_shim_with_env(
        transformed,
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m foo"}},
        env_extra={"COPILOT_HOOK_DEBUG": ""},
    )
    assert proc.returncode == 0
    assert "kind=" not in proc.stderr
    assert "fired=" not in proc.stderr


def test_inject_shim_error_message_includes_matcher():
    """Shim crash messages MUST include the _MATCHER value (P1-4).

    Customer can't tell which of 28 generated scripts crashed without
    the matcher in the error. Prove the rendered stderr carries
    ``[<matcher>]`` so support tickets can identify the offending hook.
    """
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(transformed, {"foo": "bar"})  # missing tool_name
    assert proc.returncode == 2
    assert "[Bash(git commit*)]" in proc.stderr


def test_inject_shim_exits_2_on_malformed_json_stdin():
    """A non-JSON stdin payload is a config error: exit 2 to stderr."""
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as h:
        h.write(transformed)
        p = h.name
    try:
        proc = subprocess.run(
            ["python3", p],
            input="not json {",
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        os.unlink(p)
    assert proc.returncode == 2
    assert "matcher-shim" in proc.stderr


# --- inject_shim idempotency ---------------------------------------------


def test_inject_shim_single_sentinel_after_one_run():
    out = inject_shim(_TRACE_SCRIPT, "Bash")
    assert out.count(_SHIM_BEGIN) == 1
    assert out.count(_SHIM_END) == 1


def test_inject_shim_single_sentinel_after_repeat_with_different_matcher():
    once = inject_shim(_TRACE_SCRIPT, "Bash")
    twice = inject_shim(once, "^(Edit|Write)$")
    thrice = inject_shim(twice, "Bash(git push*)")
    assert once.count(_SHIM_BEGIN) == 1
    assert twice.count(_SHIM_BEGIN) == 1
    assert thrice.count(_SHIM_BEGIN) == 1


def test_inject_shim_byte_identical_for_same_matcher():
    once = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    twice = inject_shim(once, "Bash(git commit*)")
    assert once == twice


def test_inject_shim_re_runs_dispatch_correctly():
    """After re-injection with a different matcher, the new matcher fires."""
    once = inject_shim(_TRACE_SCRIPT, "Bash")
    twice = inject_shim(once, "^Edit$")
    proc_match = _run_shim(twice, {"tool_name": "Edit"})
    assert proc_match.returncode == 0
    assert "FIRED" in proc_match.stdout
    proc_miss = _run_shim(twice, {"tool_name": "Bash"})
    assert proc_miss.returncode == 0
    assert "FIRED" not in proc_miss.stdout


def test_strip_shim_restores_original_body():
    once = inject_shim(_TRACE_SCRIPT, "Bash")
    restored = strip_shim(once)
    # Restored body should NOT contain the sentinel.
    assert _SHIM_BEGIN not in restored
    assert "json.load" in restored
    # And re-injecting must equal the original first injection.
    re_injected = inject_shim(restored, "Bash")
    assert re_injected == once


def test_is_shimmed_predicate():
    assert not is_shimmed(_TRACE_SCRIPT)
    assert is_shimmed(inject_shim(_TRACE_SCRIPT, "Bash"))


# --- inject_shim stdin replay (regression for double-consume) ------------


def test_inject_shim_stdin_replay_lets_original_read_same_bytes():
    """The wrapped script must see the same bytes the shim inspected.

    The shim buffers stdin into _raw, dispatches, then replaces sys.stdin
    with a TextIOWrapper(BytesIO(_raw)) before calling _original_main.
    A script that does `sys.stdin.read()` after the shim must observe
    those original bytes verbatim.
    """
    body = (
        "import sys, json\n"
        "raw = sys.stdin.read()\n"
        'print("LEN:" + str(len(raw)))\n'
        "data = json.loads(raw)\n"
        'print("TOOL:" + data["tool_name"])\n'
    )
    transformed = inject_shim(body, "Bash")
    payload = {"tool_name": "Bash", "extra": "x" * 50}
    expected_len = len(json.dumps(payload))
    proc = _run_shim(transformed, payload)
    assert proc.returncode == 0
    assert f"LEN:{expected_len}" in proc.stdout
    assert "TOOL:Bash" in proc.stdout


# --- generate_hooks driver -----------------------------------------------


def _setup_full_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Materialize a complete fake repo: settings.json + hooks_src/ + config."""
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "alpha.py")
    _write_script(hooks_src, "PostToolUse", "beta.py")
    _write_script(hooks_src, "SubagentStop", "subagent.py")  # event-dropped
    _write_script(hooks_src, "SessionStart", "init.py")
    settings = tmp_path / "settings.json"
    _write_settings(
        settings,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash(git commit*)",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/alpha.py",
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "^(Edit|Write)$",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PostToolUse/beta.py",
                        }
                    ],
                }
            ],
            "SubagentStop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/SubagentStop/subagent.py",
                        }
                    ],
                }
            ],
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/SessionStart/init.py",
                        }
                    ],
                }
            ],
        },
    )
    return cfg, settings


def test_generator_emits_version_one_wrapper(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, result = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert out["version"] == 1
    assert "hooks" in out


def test_generator_preserves_explicit_zero_version_field(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    text = cfg.read_text(encoding="utf-8")
    cfg.write_text(text.replace("    versionField: 1", "    versionField: 0"), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert out["version"] == 0


def test_generator_remaps_event_names(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert "PreToolUse" in out["hooks"]
    assert "PostToolUse" in out["hooks"]
    assert "SessionStart" in out["hooks"]
    # SubagentStop dropped.
    assert "SubagentStop" not in out["hooks"]
    assert "subagentStop" not in out["hooks"]


def test_generator_drops_subagent_stop_with_warn(tmp_path: Path, capfd) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, result = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capfd.readouterr()
    assert rc == 0
    assert result.dropped >= 1
    assert "SubagentStop" in captured.err
    # The dropped script is still copied to disk for reference; only the
    # hooks.json entry is omitted.


def test_generator_emits_python3_and_py3_invocation(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    entry = out["hooks"]["PreToolUse"][0]
    assert entry["bash"].startswith("python3 -u")
    assert entry["powershell"].startswith("py -3 -u")
    assert entry["cwd"] == "."


def test_generator_preserves_explicit_zero_timeout(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 0
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert out["hooks"]["PreToolUse"][0]["timeoutSec"] == 0


def _find_shimmed_alpha(tmp_path: Path) -> Path:
    """Locate the shimmed copy of alpha.py (suffix encodes the matcher)."""
    candidates = list((tmp_path / "out" / "PreToolUse").glob("alpha*.py"))
    assert len(candidates) == 1, f"expected 1 alpha shim, got {candidates}"
    return candidates[0]


def test_generator_writes_shim_into_copied_script(tmp_path: Path) -> None:
    """A matcher in the source must produce a shimmed copy on disk."""
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    body = _find_shimmed_alpha(tmp_path).read_text()
    assert _SHIM_BEGIN in body
    assert "_MATCHER" in body


def test_generator_idempotency_on_rerun(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    generate_hooks.generate_hooks(cfg, tmp_path)
    first = _find_shimmed_alpha(tmp_path).read_text()
    generate_hooks.generate_hooks(cfg, tmp_path)
    second = _find_shimmed_alpha(tmp_path).read_text()
    assert first == second
    assert second.count(_SHIM_BEGIN) == 1


def test_generator_no_regen_sentinel_skips_overwrite(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    # First run produces the file.
    generate_hooks.generate_hooks(cfg, tmp_path)
    target = _find_shimmed_alpha(tmp_path)
    # Customer applies a NO-REGEN edit.
    target.write_text("# NO-REGEN\nprint('customer fix')\n", encoding="utf-8")
    # Re-run; file must be untouched.
    generate_hooks.generate_hooks(cfg, tmp_path)
    assert target.read_text().startswith("# NO-REGEN\n")


def test_generator_distinct_shim_per_matcher(tmp_path: Path) -> None:
    """Same source script under two matchers produces two distinct shimmed copies.

    Regression for the bug where the second matcher silently clobbered the
    first because both wrote to the same target filename.
    """
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "guard.py")
    settings = tmp_path / "settings.json"
    _write_settings(
        settings,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash(git commit*)",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/guard.py",
                        }
                    ],
                },
                {
                    "matcher": "Bash(gh pr create*)",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/guard.py",
                        }
                    ],
                },
            ]
        },
    )
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    targets = sorted((tmp_path / "out" / "PreToolUse").glob("guard*.py"))
    # Two distinct files, one per matcher.
    assert len(targets) == 2
    body0 = targets[0].read_text()
    body1 = targets[1].read_text()
    # Each carries a different matcher in its shim header.
    assert ("Matcher: Bash(git commit*)" in body0) != ("Matcher: Bash(git commit*)" in body1)
    # And hooks.json points at both distinct filenames.
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    bash_paths = {entry["bash"] for entry in out["hooks"]["PreToolUse"]}
    assert len(bash_paths) == 2


# --- _matcher_suffix collision prevention (P0) ---------------------------


def test_matcher_suffix_deterministic_same_input():
    """Same matcher must produce same suffix across calls (idempotency)."""
    a = _matcher_suffix("Bash(git commit*)")
    b = _matcher_suffix("Bash(git commit*)")
    assert a == b
    assert a  # non-empty


def test_matcher_suffix_path_traversal_vs_absolute_distinct():
    """Path-traversal and absolute-path matchers must NOT collide.

    Both sanitize to ``Bash_etc_passwd``; the hash suffix prevents the
    silent gate bypass where the second write would clobber the first.
    """
    a = _matcher_suffix("Bash(../../etc/passwd)")
    b = _matcher_suffix("Bash(/etc/passwd)")
    assert a != b


def test_matcher_suffix_regex_inversion_distinct():
    """Functionally-equivalent but textually-different regexes are distinct."""
    a = _matcher_suffix("^(Edit|Write)$")
    b = _matcher_suffix("^(Write|Edit)$")
    assert a != b


def test_matcher_suffix_long_matcher_unique():
    """Matcher longer than 48-char sanitization boundary still unique."""
    long_a = "Bash(" + "a" * 100 + ")"
    long_b = "Bash(" + "a" * 99 + "b)"
    a = _matcher_suffix(long_a)
    b = _matcher_suffix(long_b)
    # Both sanitized forms hit the 48-char cap and look identical without
    # the hash; the hash differentiates them.
    assert a != b


def test_matcher_suffix_empty_returns_empty():
    """None or empty matcher -> empty suffix (no shim file rename)."""
    assert _matcher_suffix(None) == ""
    assert _matcher_suffix("") == ""


def test_matcher_suffix_unicode_does_not_crash():
    """Unicode in matcher hashes cleanly without raising."""
    # Sanitization strips to "_" so suffix is just the hash.
    out = _matcher_suffix("Bash(café*)")
    assert out  # non-empty
    assert len(out) >= 6  # at least the hash


def test_generator_collision_resistant_filenames(tmp_path: Path) -> None:
    """Two functionally-equivalent regex matchers produce distinct files.

    Regression for P0 collision bug: a sanitized-suffix scheme without
    hashing would write both shimmed copies to the same path; the
    second silently overwrites the first and only one matcher fires.
    """
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PostToolUse", "guard.py")
    settings = tmp_path / "settings.json"
    _write_settings(
        settings,
        {
            "PostToolUse": [
                {
                    "matcher": "^(Edit|Write)$",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PostToolUse/guard.py",
                        }
                    ],
                },
                {
                    "matcher": "^(Write|Edit)$",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PostToolUse/guard.py",
                        }
                    ],
                },
            ]
        },
    )
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    targets = sorted((tmp_path / "out" / "PostToolUse").glob("guard*.py"))
    assert len(targets) == 2, f"expected 2 distinct files, got {targets}"


# --- generator config errors (negative) ----------------------------------


def test_generator_fails_2_on_missing_event_remap(tmp_path: Path) -> None:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  hooks:
    settingsSource: "settings.json"
    scriptSource: "hooks_src"
    outputConfig: "out/hooks.json"
    outputScripts: "out"
""",
        encoding="utf-8",
    )
    (tmp_path / "settings.json").write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    (tmp_path / "hooks_src").mkdir()
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 2


def test_generator_fails_2_on_malformed_settings_json(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    (tmp_path / "settings.json").write_text("{ not json", encoding="utf-8")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 2


def test_generator_fails_2_on_missing_hooks_stanza(tmp_path: Path) -> None:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  agents:
    sourceDir: "src"
    outputDir: "out"
""",
        encoding="utf-8",
    )
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 2


def test_generator_fails_2_on_path_traversal(tmp_path: Path) -> None:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  hooks:
    settingsSource: "../etc/passwd"
    scriptSource: "hooks_src"
    outputConfig: "out/hooks.json"
    outputScripts: "out"
    eventRemap: {}
""",
        encoding="utf-8",
    )
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 2


def test_resolve_script_path_rejects_command_path_traversal(tmp_path: Path) -> None:
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "alpha.py")
    (tmp_path / "outside.py").write_text("print('outside')\n", encoding="utf-8")

    with pytest.raises(generate_hooks.GenerateHooksError):
        generate_hooks._resolve_script_path(
            hooks_src,
            "python3 -u .claude/hooks/PreToolUse/../../outside.py",
            "PreToolUse",
        )


def test_resolve_script_path_allows_normalized_internal_path(tmp_path: Path) -> None:
    hooks_src = tmp_path / "hooks_src"
    alpha = _write_script(hooks_src, "PreToolUse", "alpha.py")

    resolved = generate_hooks._resolve_script_path(
        hooks_src,
        "python3 -u .claude/hooks/PreToolUse/../PreToolUse/alpha.py",
        "PreToolUse",
    )

    assert resolved == alpha


def test_generator_fails_1_on_missing_settings_file(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    (tmp_path / "hooks_src").mkdir()
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 1


# --- P2-1 coverage gaps --------------------------------------------------


def test_inject_shim_case_sensitive_tool_name():
    """Bash matcher does NOT fire on lowercase 'bash' (P2-1).

    Claude tool names are case-sensitive. Document and enforce it so
    customer hooks cannot be silently bypassed by case differences.
    """
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(transformed, {"tool_name": "bash"})
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_generator_unknown_event_emits_warn_and_drops(tmp_path: Path, capfd) -> None:
    """A Claude event not in eventRemap and not in eventDrop drops with WARN.

    Operator can extend the remap config; we do not crash the build.
    Regression for the unknown-event handler path.
    """
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "CustomEvent", "x.py")
    settings = tmp_path / "settings.json"
    _write_settings(
        settings,
        {
            "CustomEvent": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/CustomEvent/x.py",
                        }
                    ],
                }
            ],
        },
    )
    rc, result = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capfd.readouterr()
    assert rc == 0
    assert result.dropped == 1
    assert "CustomEvent" in captured.err
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    # No entry for unknown event.
    assert "CustomEvent" not in out["hooks"]
    assert "customEvent" not in out["hooks"]


def test_main_returns_zero_on_happy_path(tmp_path: Path) -> None:
    """``main(argv)`` happy path returns 0 (P2-1 main() coverage)."""
    cfg, _ = _setup_full_fixture(tmp_path)
    rc = generate_hooks.main(["--config", str(cfg), "--repo-root", str(tmp_path)])
    assert rc == 0


def test_main_returns_two_on_missing_config(tmp_path: Path) -> None:
    """``main(argv)`` returns 2 (config error) when --config does not exist."""
    missing = tmp_path / "does_not_exist.yaml"
    rc = generate_hooks.main(
        ["--config", str(missing), "--repo-root", str(tmp_path)]
    )
    assert rc == 2


def test_main_what_if_runs_without_writing(tmp_path: Path) -> None:
    """``main(argv)`` --what-if exits 0 and does not produce output files."""
    cfg, _ = _setup_full_fixture(tmp_path)
    rc = generate_hooks.main(
        [
            "--config",
            str(cfg),
            "--repo-root",
            str(tmp_path),
            "--what-if",
        ]
    )
    assert rc == 0
    assert not (tmp_path / "out" / "hooks.json").exists()


def test_matcher_suffix_long_unicode_no_crash():
    """A matcher with unicode + symbols + length >48 hashes cleanly."""
    out = _matcher_suffix("Bash(café✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓)")
    assert out  # non-empty
    # Suffix is filesystem-safe (alnum + underscore only).
    assert re.match(r"^[A-Za-z0-9_]+$", out)


def test_matcher_suffix_all_symbols_returns_only_hash():
    """A matcher of pure punctuation collapses to empty sanitization +
    hash-only suffix.

    Documented behavior: when the sanitization step yields an empty
    string we return just the 6-char hash so the file still gets a
    unique name.
    """
    out = _matcher_suffix("!!!---???")
    assert len(out) == 6
    assert re.match(r"^[a-f0-9]{6}$", out)


def test_matcher_suffix_whitespace_padded_matcher_normalizes():
    """A matcher with leading/trailing whitespace yields a non-empty suffix.

    Sanitization collapses whitespace runs to ``_`` and strips ends, so
    ``"  Bash  "`` and ``"Bash"`` produce the same SANITIZED form but
    differ in the hash because the hash is computed on the raw input.
    Documents the chosen behavior: distinct inputs -> distinct files.
    """
    a = _matcher_suffix(" Bash")
    b = _matcher_suffix("Bash")
    assert a and b
    # Distinct inputs MUST yield distinct suffixes (collision-resistant).
    assert a != b


def test_ensure_exact_case_dir_uses_collision_free_temp_name(tmp_path: Path) -> None:
    """A stale case-fix temp directory does not block casing repair."""
    parent = tmp_path / "hooks"
    lower_case_dir = parent / "pretooluse"
    stale_temp_dir = parent / "__case_fix_PreToolUse"
    lower_case_dir.mkdir(parents=True)
    stale_temp_dir.mkdir()

    _ensure_exact_case_dir(parent / "PreToolUse")

    entry_names = {entry.name for entry in parent.iterdir()}
    assert "PreToolUse" in entry_names
    assert "__case_fix_PreToolUse" in entry_names
    assert "pretooluse" not in entry_names


def test_ensure_exact_case_dir_rejects_file_blocking_target(
    tmp_path: Path,
) -> None:
    """A file at the target name fails loudly instead of being treated as ok."""
    target = tmp_path / "hooks" / "PreToolUse"
    target.parent.mkdir()
    target.write_text("not a directory", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        _ensure_exact_case_dir(target)


# --- live-corpus regression ----------------------------------------------


def test_live_corpus_every_matcher_classifies(tmp_path: Path) -> None:
    """Every matcher in the live .claude/settings.json classifies cleanly."""
    settings = REPO_ROOT / ".claude" / "settings.json"
    if not settings.is_file():
        pytest.skip("live settings.json not present in this checkout")
    data = json.loads(settings.read_text())
    hooks = data.get("hooks", {})
    seen_kinds: set[str] = set()
    for _event, groups in hooks.items():
        for group in groups:
            matcher = group.get("matcher")
            if matcher is None:
                continue
            kind, params = classify_matcher(matcher)
            assert kind in (MATCHER_REGEX, MATCHER_TOOL_GLOB, MATCHER_BARE)
            seen_kinds.add(kind)
    # The live corpus exercises all three classes.
    assert seen_kinds == {MATCHER_REGEX, MATCHER_TOOL_GLOB, MATCHER_BARE}


# Future-import hoist (CodeRabbit critical: PEP 236 violation) ---------------


def test_future_import_hoisted_above_shim() -> None:
    """``from __future__ import`` MUST land at module top, not inside the wrapper.

    PEP 236 requires future imports at module level; the wrapper would
    otherwise indent them into ``_original_main()`` and produce a
    SyntaxError. Regression: pre-fix output had 19/28 generated hooks
    failing ``py_compile`` for this exact reason.
    """
    body = (
        '#!/usr/bin/env python3\n"""docstring."""\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "print('hi')\n"
    )
    out = generate_hooks.inject_shim(body, "Bash(git commit*)")
    # First non-blank line must be the future import.
    first = next(line for line in out.splitlines() if line.strip())
    assert first == "from __future__ import annotations"
    # And it must NOT also appear indented inside _original_main.
    assert "    from __future__ import annotations" not in out
    # The generated module must parse.
    compile(out, "<generated>", "exec")


def test_future_import_round_trip_stable_after_strip() -> None:
    """strip_shim → inject_shim is byte-stable when body had future imports."""
    body = (
        '#!/usr/bin/env python3\n"""doc."""\n'
        "from __future__ import annotations\n"
        "import os\n"
        "print(os.getcwd())\n"
    )
    matcher = "^Edit$"
    once = generate_hooks.inject_shim(body, matcher)
    twice = generate_hooks.inject_shim(once, matcher)
    assert once == twice
    # Stripping then re-injecting yields the same artifact.
    restripped = generate_hooks.inject_shim(generate_hooks.strip_shim(once), matcher)
    assert once == restripped


def test_main_epilogue_emits_return_main_trailer() -> None:
    """Scripts with the canonical main+epilogue shape get ``return main()``.

    Without this, the wrapper falls through to the trailing ``return 0``
    and every shimmed guard reports success regardless of validator
    outcome (the bug fixed by PR #1887 generator update). Lock the
    behavior so a future refactor cannot silently re-break it.
    """
    body = (
        "#!/usr/bin/env python3\n"
        '"""guard."""\n'
        "import sys\n\n"
        "def main() -> int:\n"
        "    return 2\n\n"
        'if __name__ == "__main__":\n'
        "    sys.exit(main())\n"
    )
    out = generate_hooks.inject_shim(body, "Bash(git push*)")
    assert "    return main()" in out
    assert "    return 0\n" not in out.split("def _original_main")[1].split("_shim_dispatch")[0]
    compile(out, "<generated>", "exec")


def test_def_main_without_epilogue_keeps_return_zero() -> None:
    """def main() WITHOUT 'if __name__ == "__main__": sys.exit(main())' keeps return 0.

    The epilogue, not just the def, gates the return main() trailer.
    Without this gate a script that defines main() but invokes it inline
    at module level would get an unreachable return main() injected;
    harmless but confusing. _has_main_function_and_epilogue uses logical
    AND for exactly this reason; pin the contract.
    """
    body = (
        "import sys\n"
        "def main() -> int:\n"
        "    return 2\n"
        "main()\n"  # invoked inline, no epilogue
    )
    out = generate_hooks.inject_shim(body, "Edit")
    wrapped = out.split("def _original_main")[1].split("_shim_dispatch")[0]
    assert "    return 0\n" in wrapped
    assert "    return main()" not in wrapped
    compile(out, "<generated>", "exec")


def test_no_main_epilogue_keeps_return_zero_trailer() -> None:
    """Scripts that fall off the bottom keep the existing ``return 0`` trailer.

    Backwards compatibility: pre-fix scripts (and any future ones that
    legitimately use module-level statements without a main()) must not
    regress.
    """
    body = "import os\nprint(os.getcwd())\n"
    out = generate_hooks.inject_shim(body, "Edit")
    wrapped = out.split("def _original_main")[1].split("_shim_dispatch")[0]
    assert "    return 0\n" in wrapped
    assert "    return main()" not in wrapped
    compile(out, "<generated>", "exec")


def test_strip_round_trip_with_main_epilogue() -> None:
    """strip_shim then inject_shim is byte-stable for canonical-shape scripts.

    The strip helper must accept both ``return 0`` and ``return main()``
    trailers; otherwise the round-trip leaks the synthetic trailer back
    into the recovered body.
    """
    body = (
        "#!/usr/bin/env python3\n"
        '"""g."""\n'
        "import sys\n\n"
        "def main() -> int:\n"
        "    return 0\n\n"
        'if __name__ == "__main__":\n'
        "    sys.exit(main())\n"
    )
    matcher = "Bash(git push*)"
    once = generate_hooks.inject_shim(body, matcher)
    twice = generate_hooks.inject_shim(generate_hooks.strip_shim(once), matcher)
    assert once == twice


def test_inject_without_future_import_no_prefix() -> None:
    """Bodies without future imports get no leading blank line / prefix."""
    body = "import os\nprint(os.getcwd())\n"
    out = generate_hooks.inject_shim(body, "Edit")
    # Shim sentinel is the first content line (no future-import prefix).
    first = out.split("\n", 1)[0]
    assert first == "# AUTO-GENERATED MATCHER SHIM (REQ-003-007)"


def test_split_future_imports_handles_multiple() -> None:
    """All future imports get hoisted in source order; rest is preserved."""
    body = (
        "from __future__ import annotations\n"
        "from __future__ import division\n"
        "import os\n"
    )
    future_block, rest = generate_hooks._split_future_imports(body)
    assert future_block == (
        "from __future__ import annotations\n"
        "from __future__ import division\n"
    )
    assert rest == "import os\n"


def test_split_future_imports_only_future_yields_empty_rest() -> None:
    """Degenerate case: body of nothing but future imports.

    ``rest`` MUST be empty; ``future_block`` MUST contain every line.
    Without this, `inject_shim` would wrap an empty body and the
    generated `_original_main()` would be syntactically empty.
    """
    body = (
        "from __future__ import annotations\n"
        "from __future__ import division\n"
    )
    future_block, rest = generate_hooks._split_future_imports(body)
    assert rest == ""
    assert future_block == body
    # Sanity: a shim built from this MUST still parse (the wrapper has
    # `return 0` which alone is a valid function body).
    out = generate_hooks.inject_shim(body, "Edit")
    compile(out, "<empty-body>", "exec")


def test_shim_reads_snake_case_wire_format() -> None:
    """Shim reads ``tool_name``/``tool_input`` (VS Code-compatible, PascalCase events).

    Copilot CLI sends snake_case payloads when event names are PascalCase.
    Test by pasting a snake_case payload through the shim and asserting
    normal dispatch.
    """
    body = (
        "import sys, json\n"
        "data = json.load(sys.stdin)\n"
        'print("OK:" + data.get("tool_name", data.get("toolName", "")))\n'
    )
    transformed = generate_hooks.inject_shim(body, "Bash(git commit*)")
    payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
    proc = _run_shim(transformed, payload)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("OK:Bash")


def test_shim_reads_camelcase_wire_format() -> None:
    """Shim reads ``toolName``/``toolArgs`` (native Copilot, camelCase events).

    Copilot CLI sends camelCase payloads when event names are camelCase.
    The shim must accept both formats to survive event-name configuration
    changes without breaking every hook. Fixes issue #2290.
    """
    transformed = generate_hooks.inject_shim("import sys; sys.exit(0)\n", "Bash")
    proc = _run_shim(transformed, {"toolName": "Bash"})
    assert proc.returncode == 0, proc.stderr


def test_shim_camelcase_tool_glob_match() -> None:
    """Shim matches ``toolArgs`` in tool-glob mode with camelCase payload.

    Copilot CLI sends toolArgs as a JSON *string* (not a parsed object) in
    camelCase mode. The shim must JSON-parse it before extracting "command"
    for glob matching. Fixes issue #2290.
    """
    transformed = generate_hooks.inject_shim("import sys; sys.exit(0)\n", "Bash(git commit*)")
    # Real camelCase payload: toolArgs is a JSON string, not a dict
    proc = _run_shim(transformed, {
        "toolName": "Bash",
        "toolArgs": '{"command":"git commit -m x","description":"Commit"}'
    })
    assert proc.returncode == 0, proc.stderr


def test_shim_replays_canonical_payload_after_camelcase_match() -> None:
    """A camelCase match replays snake_case fields into the wrapped hook."""
    body = (
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "tool_input = data.get('tool_input')\n"
        "if not isinstance(tool_input, dict):\n"
        "    print('MISSING_TOOL_INPUT')\n"
        "    sys.exit(2)\n"
        "print('COMMAND:' + tool_input.get('command', ''))\n"
    )
    transformed = generate_hooks.inject_shim(body, "Bash(git commit*)")

    proc = _run_shim(
        transformed,
        {
            "toolName": "Bash",
            "toolArgs": '{"command":"git commit -m x","description":"Commit"}',
        },
    )

    assert proc.returncode == 0, proc.stderr
    assert "COMMAND:git commit -m x" in proc.stdout


def test_shim_rejects_payload_missing_both_formats() -> None:
    """A payload with neither ``tool_name`` nor ``toolName`` MUST fail loud
    with exit 2. Complements test_inject_shim_exits_2_on_missing_tool_name
    with the updated error message check."""
    transformed = generate_hooks.inject_shim("import sys; sys.exit(0)\n", "Bash")
    proc = _run_shim(transformed, {"foo": "bar"})
    assert proc.returncode == 2
    assert "tool_name" in proc.stderr
    assert "toolName" in proc.stderr


def test_shim_camelcase_tool_glob_non_match() -> None:
    """camelCase payload where tool matches but args do NOT match the glob.

    The hook must exit 0 (no fire), not crash. Guards against a regression
    where camelCase payloads always fire regardless of args.
    """
    transformed = generate_hooks.inject_shim("import sys; sys.exit(0)\n", "Bash(git commit*)")
    proc = _run_shim(transformed, {
        "toolName": "Bash",
        "toolArgs": '{"command":"git push origin main"}'
    })
    assert proc.returncode == 0, proc.stderr
    # The hook body should NOT have run (no "FIRED" output).
    assert "FIRED" not in proc.stdout


def test_shim_camelcase_malformed_json_toolargs() -> None:
    """Malformed JSON in toolArgs logs a warning and does not crash.

    The glob match operates on the raw string, which likely does not match
    a command-oriented pattern. The hook should not fire and not crash.
    """
    transformed = generate_hooks.inject_shim("import sys; sys.exit(0)\n", "Bash(git commit*)")
    proc = _run_shim(transformed, {
        "toolName": "Bash",
        "toolArgs": '{"command": "git commit'  # truncated JSON
    })
    assert proc.returncode == 0, f"should not crash; stderr={proc.stderr}"
    assert "toolArgs is not valid JSON" in proc.stderr


def test_shim_tool_glob_null_tool_input_falls_back_to_toolargs() -> None:
    """tool_input present-but-null MUST fall back to toolArgs (issue #2290).

    Regression guard for the asymmetry flagged on PR #2293: the tool_name
    read uses an explicit ``is None`` check, but tool_args used
    ``payload.get("tool_input", payload.get("toolArgs"))``. ``dict.get``
    returns the default only when the key is ABSENT, never when the value
    is JSON null. A host that sends ``tool_input: null`` alongside a real
    ``toolArgs`` string would otherwise drop the args, skip the glob match,
    and silently fail to fire a tool-glob hook (fail-open by omission).
    """
    body = 'print("FIRED")\n'
    transformed = generate_hooks.inject_shim(body, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {
            "tool_name": "Bash",
            "tool_input": None,
            "toolArgs": '{"command":"git commit -m x"}',
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "FIRED" in proc.stdout, (
        "shim dropped toolArgs when tool_input was null; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_shim_snake_case_takes_precedence_over_camelcase() -> None:
    """When both tool_name and toolName are present, snake_case wins."""
    transformed = generate_hooks.inject_shim("import sys; sys.exit(0)\n", "Bash")
    proc = _run_shim(transformed, {"tool_name": "Bash", "toolName": "Edit"})
    assert proc.returncode == 0, proc.stderr  # Bash matched, not Edit


def test_all_generated_hooks_parse_as_python() -> None:
    """Every checked-in generated hook MUST compile.

    Guards against the PEP 236 regression where ``from __future__`` lines
    were indented into the function wrapper. Without this gate, broken
    hooks ship and fail at first invocation.
    """
    hooks_dir = REPO_ROOT / "src" / "copilot-cli" / "hooks"
    if not hooks_dir.is_dir():
        pytest.skip("generated hooks not present in this checkout")
    failures: list[str] = []
    for path in sorted(hooks_dir.rglob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as err:
            failures.append(f"{path.relative_to(REPO_ROOT)}: {err}")
    assert not failures, "Generated hooks have syntax errors:\n" + "\n".join(failures)


def test_shim_strips_original_main_epilogue_no_double_exec() -> None:
    """Wrapped shim MUST NOT contain the original ``if __name__`` block.

    Refs cursor bugbot thread PRRT_kwDOQoWRls6Eef5O (PR #1763).
    Before the fix, regenerated matcher shims appended ``return main()``
    while the wrapped script still carried ``if __name__ == "__main__":
    main()``, so main ran twice when the shim ran as ``__main__``.
    Pin the contract: the synthetic ``return main()`` trailer is the
    ONLY path that invokes main inside _original_main.
    """
    body = (
        "#!/usr/bin/env python3\n"
        "import sys\n\n"
        "def main() -> int:\n"
        "    return 2\n\n"
        'if __name__ == "__main__":\n'
        "    sys.exit(main())\n"
    )
    out = generate_hooks.inject_shim(body, "Bash(git push*)")
    wrapped = out.split("def _original_main")[1].split("_shim_dispatch")[0]
    assert 'if __name__ == "__main__":' not in wrapped
    # sys.exit(main()) is the canonical original invocation site; it MUST
    # be stripped so only the synthetic ``return main()`` trailer remains.
    assert "sys.exit(main())" not in wrapped
    assert "return main()" in wrapped
    compile(out, "<generated>", "exec")


def test_shim_preserves_fail_open_handler() -> None:
    """Wrapped shim MUST preserve the fail-open contract.

    Refs cursor bugbot threads PRRT_kwDOQoWRls6Eekqj and Eep7i (PR #1763).
    When the original script wraps ``main()`` in a try/except that
    catches Exception and sys.exit(0)s, the shim MUST also wrap its
    synthetic ``return main()`` trailer in a try/except returning 0;
    otherwise an unexpected error from main() escapes the shim as a
    non-zero exit and breaks the fail-open contract for hooks like
    invoke_false_completion_gate and invoke_plan_state_sync.
    """
    body = (
        "#!/usr/bin/env python3\n"
        "import sys\n\n"
        "def main() -> int:\n"
        "    return 0\n\n"
        'if __name__ == "__main__":\n'
        "    try:\n"
        "        main()\n"
        "    except Exception as err:\n"
        "        sys.stderr.write(str(err))\n"
        "        sys.exit(0)\n"
    )
    out = generate_hooks.inject_shim(body, "Bash(git commit*)")
    wrapped = out.split("def _original_main")[1].split("_shim_dispatch")[0]
    # original main() call inside the if __name__ block is stripped
    assert 'if __name__ == "__main__":' not in wrapped
    # synthetic trailer wraps return main() in try/except returning 0
    assert "    try:\n        return main()" in wrapped
    assert "return 0" in wrapped
    compile(out, "<generated>", "exec")


def test_shim_preserves_fail_open_via_runtime_behavior() -> None:
    """End-to-end: a shim wrapping a fail-open script returns 0 on raise.

    The static checks above pin the shape of the generated trailer.
    This test pins the runtime contract: when main() raises an
    unexpected error, the shim still exits 0 because the fail-open
    handler caught it.
    """
    body = (
        "#!/usr/bin/env python3\n"
        "import sys\n\n"
        "def main() -> int:\n"
        '    raise RuntimeError("boom")\n\n'
        'if __name__ == "__main__":\n'
        "    try:\n"
        "        main()\n"
        "    except Exception as err:\n"
        "        sys.stderr.write(str(err))\n"
        "        sys.exit(0)\n"
    )
    transformed = generate_hooks.inject_shim(body, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
    )
    assert proc.returncode == 0
    assert "boom" in proc.stderr
