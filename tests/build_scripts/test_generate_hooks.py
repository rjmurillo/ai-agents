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
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_hooks  # noqa: E402
from generate_hooks import (  # noqa: E402
    MATCHER_BARE,
    MATCHER_REGEX,
    MATCHER_TOOL_GLOB,
    classify_matcher,
    glob_or_match,
    inject_shim,
    is_shimmed,
    normalize_tool_args,
    strip_shim,
    _matcher_suffix,
    _SHIM_BEGIN,
    _SHIM_END,
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
      PreToolUse: preToolUse
      PostToolUse: postToolUse
      Stop: sessionEnd
      SessionStart: sessionStart
      UserPromptSubmit: userPromptSubmitted
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
            'print("FIRED:" + (data.get("toolName") or ""))\n'
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
    'print("FIRED:" + (data.get("toolName") or ""))\n'
    "sys.exit(0)\n"
)


def test_inject_shim_fires_on_regex_match():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    proc = _run_shim(transformed, {"toolName": "Edit"})
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Edit")


def test_inject_shim_no_op_on_regex_miss():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    proc = _run_shim(transformed, {"toolName": "Read"})
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_fires_on_tool_glob_match():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {"toolName": "Bash", "toolArgs": {"command": "git commit -m 'x'"}},
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_no_op_on_tool_glob_args_miss():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {"toolName": "Bash", "toolArgs": {"command": "git push"}},
    )
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_no_op_on_tool_glob_wrong_tool():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(transformed, {"toolName": "Edit"})
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_fires_on_bare_match_any_args():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(
        transformed,
        {"toolName": "Bash", "toolArgs": {"command": "anything goes"}},
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_no_op_on_bare_miss():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(transformed, {"toolName": "Edit"})
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_fires_on_mcp_namespaced_bare():
    transformed = inject_shim(_TRACE_SCRIPT, "mcp__serena__write_memory")
    proc = _run_shim(transformed, {"toolName": "mcp__serena__write_memory"})
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:mcp__serena__write_memory")


def test_inject_shim_multi_pipe_glob_first_branch():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(npm test*|pytest*)")
    proc = _run_shim(
        transformed, {"toolName": "Bash", "toolArgs": {"command": "npm test"}}
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_multi_pipe_glob_second_branch():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(npm test*|pytest*)")
    proc = _run_shim(
        transformed, {"toolName": "Bash", "toolArgs": {"command": "pytest -v"}}
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


def test_inject_shim_multi_pipe_glob_neither_branch():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(npm test*|pytest*)")
    proc = _run_shim(
        transformed, {"toolName": "Bash", "toolArgs": {"command": "cargo build"}}
    )
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout


def test_inject_shim_whitespace_normalization_double_space():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {"toolName": "Bash", "toolArgs": {"command": "git  commit  -m  foo"}},
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Bash")


# --- inject_shim crash policy --------------------------------------------


def test_inject_shim_exits_2_on_missing_tool_name():
    """A payload without `toolName` is a config error: exit 2 to stderr."""
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(transformed, {"foo": "bar"})
    assert proc.returncode == 2
    assert "matcher-shim" in proc.stderr


def test_inject_shim_error_message_includes_matcher():
    """Shim crash messages MUST include the _MATCHER value (P1-4).

    Customer can't tell which of 28 generated scripts crashed without
    the matcher in the error. Prove the rendered stderr carries
    ``[<matcher>]`` so support tickets can identify the offending hook.
    """
    transformed = inject_shim(_TRACE_SCRIPT, "Bash(git commit*)")
    proc = _run_shim(transformed, {"foo": "bar"})  # missing toolName
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
    proc_match = _run_shim(twice, {"toolName": "Edit"})
    assert proc_match.returncode == 0
    assert "FIRED" in proc_match.stdout
    proc_miss = _run_shim(twice, {"toolName": "Bash"})
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
        'print("TOOL:" + data["toolName"])\n'
    )
    transformed = inject_shim(body, "Bash")
    payload = {"toolName": "Bash", "extra": "x" * 50}
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


def test_generator_remaps_event_names(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert "preToolUse" in out["hooks"]
    assert "postToolUse" in out["hooks"]
    assert "sessionStart" in out["hooks"]
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
    entry = out["hooks"]["preToolUse"][0]
    assert entry["bash"].startswith("python3 -u")
    assert entry["powershell"].startswith("py -3 -u")
    assert entry["cwd"] == "."


def _find_shimmed_alpha(tmp_path: Path) -> Path:
    """Locate the shimmed copy of alpha.py (suffix encodes the matcher)."""
    candidates = list((tmp_path / "out" / "preToolUse").glob("alpha*.py"))
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
    targets = sorted((tmp_path / "out" / "preToolUse").glob("guard*.py"))
    # Two distinct files, one per matcher.
    assert len(targets) == 2
    body0 = targets[0].read_text()
    body1 = targets[1].read_text()
    # Each carries a different matcher in its shim header.
    assert ("Matcher: Bash(git commit*)" in body0) != ("Matcher: Bash(git commit*)" in body1)
    # And hooks.json points at both distinct filenames.
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    bash_paths = {entry["bash"] for entry in out["hooks"]["preToolUse"]}
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
    targets = sorted((tmp_path / "out" / "postToolUse").glob("guard*.py"))
    assert len(targets) == 2, f"expected 2 distinct files, got {targets}"


# --- generator config errors (negative) ----------------------------------


def test_generator_fails_2_on_missing_eventRemap(tmp_path: Path) -> None:
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


def test_generator_fails_1_on_missing_settings_file(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    (tmp_path / "hooks_src").mkdir()
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 1


# --- live-corpus regression ----------------------------------------------


def test_live_corpus_every_matcher_classifies(tmp_path: Path) -> None:
    """Every matcher in the live .claude/settings.json classifies cleanly."""
    settings = REPO_ROOT / ".claude" / "settings.json"
    if not settings.is_file():
        pytest.skip("live settings.json not present in this checkout")
    data = json.loads(settings.read_text())
    hooks = data.get("hooks", {})
    seen_kinds: set[str] = set()
    for event, groups in hooks.items():
        for group in groups:
            matcher = group.get("matcher")
            if matcher is None:
                continue
            kind, params = classify_matcher(matcher)
            assert kind in (MATCHER_REGEX, MATCHER_TOOL_GLOB, MATCHER_BARE)
            seen_kinds.add(kind)
    # The live corpus exercises all three classes.
    assert seen_kinds == {MATCHER_REGEX, MATCHER_TOOL_GLOB, MATCHER_BARE}
