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
- live-corpus regression: classify every matcher in the live plugin manifest
"""

from __future__ import annotations

import errno
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_dispatcher  # noqa: E402
import generate_hooks  # noqa: E402
import generate_hooks_events  # noqa: E402
import generate_hooks_transaction  # noqa: E402
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
from generate_hooks_shim import (  # noqa: E402
    HOOK_STDIN_CEILING_MIB,
    MATCHED_SHIM_PAYLOAD_LIMIT_MIB,
)

# Byte-unit conversions of the shim's policy constants, computed once so the
# oversize-boundary tests below do not each redo `MIB * 1024 * 1024`.
_HOOK_STDIN_CEILING_BYTES = HOOK_STDIN_CEILING_MIB * 1024 * 1024
_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES = MATCHED_SHIM_PAYLOAD_LIMIT_MIB * 1024 * 1024

# Helpers -------------------------------------------------------------------


def _run_shim(
    transformed_source: str, payload: dict[str, Any]
) -> subprocess.CompletedProcess[str]:
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
            text=True, encoding="utf-8",
            timeout=15,
        )
    finally:
        os.unlink(path)


def _run_shim_raw(
    transformed_source: str, raw_input: bytes
) -> subprocess.CompletedProcess[bytes]:
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
            timeout=60,
        )
    finally:
        os.unlink(path)


def _raw_json_with_size(payload: dict[str, Any], size: int) -> bytes:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > size:
        raise ValueError(f"payload is {len(encoded)} bytes, larger than target {size}")
    return b" " * (size - len(encoded)) + encoded


def _write_settings(path: Path, hooks_obj: dict[str, Any]) -> Path:
    path.write_text(json.dumps({"hooks": hooks_obj}, indent=2), encoding="utf-8")
    return path


def _write_config(
    tmp_path: Path, *, hooks_stanza_overrides: dict[str, Any] | None = None
) -> Path:
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
      Stop: Stop
      SubagentStop: SubagentStop
      PermissionRequest: PermissionRequest
      SessionStart: SessionStart
      UserPromptSubmit: UserPromptSubmit
    eventDrop:
      - Notification
      - PreCompact
    matcherPolicy: "inline-script-shim"
    versionField: 1
"""
    if hooks_stanza_overrides:
        for key, value in hooks_stanza_overrides.items():
            body += f"    {key}: {json.dumps(value)}\n"
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


def test_inject_shim_denies_one_byte_above_read_ceiling():
    transformed = inject_shim(_TRACE_SCRIPT, "^(Write|Edit)$")
    ceiling = _HOOK_STDIN_CEILING_BYTES
    oversize = b" " * (ceiling + 1)

    proc = _run_shim_raw(transformed, oversize)

    assert proc.returncode == 2
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert "stdin exceeds" in stderr
    assert str(ceiling) in stderr
    assert "malformed JSON" not in stderr


def test_inject_shim_allows_exact_read_ceiling_when_unmatched():
    transformed = inject_shim(_TRACE_SCRIPT, "^(Write|Edit)$")
    ceiling = _HOOK_STDIN_CEILING_BYTES
    raw = _raw_json_with_size(
        {"tool_name": "apply_patch", "tool_input": {}},
        ceiling,
    )

    proc = _run_shim_raw(transformed, raw)

    assert len(raw) == ceiling
    assert proc.returncode == 0
    assert b"FIRED" not in proc.stdout


def test_inject_shim_allows_payload_above_matched_limit_when_unmatched():
    transformed = inject_shim(_TRACE_SCRIPT, "^(Write|Edit)$")
    matched_limit = _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES
    raw = _raw_json_with_size(
        {"tool_name": "apply_patch", "tool_input": {}},
        matched_limit + 1,
    )

    proc = _run_shim_raw(transformed, raw)

    assert proc.returncode == 0
    assert b"FIRED" not in proc.stdout
    assert proc.stderr == b""


def test_inject_shim_allows_matched_replay_at_limit():
    transformed = inject_shim(_TRACE_SCRIPT, "^(Write|Edit)$")
    matched_limit = _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES
    raw = _raw_json_with_size(
        {"tool_name": "Edit", "tool_input": {}},
        matched_limit,
    )

    proc = _run_shim_raw(transformed, raw)

    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stdout.startswith(b"FIRED:Edit")


def test_inject_shim_denies_matched_replay_above_limit_with_context():
    matcher = "^(Write|Edit)$"
    transformed = inject_shim(_TRACE_SCRIPT, matcher)
    matched_limit = _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES
    raw = _raw_json_with_size(
        {
            "tool_name": "Edit",
            "tool_input": {"marker": "payload-marker-do-not-log"},
        },
        matched_limit + 1,
    )

    proc = _run_shim_raw(transformed, raw)

    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 2
    assert matcher in stderr
    assert "tool_input" in stderr
    assert str(matched_limit) in stderr
    assert b"FIRED" not in proc.stdout
    assert "payload-marker-do-not-log" not in stderr
    assert b"payload-marker-do-not-log" not in proc.stdout


def test_inject_shim_replays_small_match_from_large_multi_call_event():
    transformed = inject_shim(_TRACE_SCRIPT, "^(Write|Edit)$")
    matched_limit = _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES
    payload = {
        "sessionId": "multi-call-regression",
        "toolCalls": [
            {
                "id": "call_patch",
                "name": "apply_patch",
                "args": "P" * (matched_limit + 1),
            },
            {
                "id": "call_edit",
                "name": "Edit",
                "args": {
                    "file_path": "README.md",
                    "old_string": "a",
                    "new_string": "b",
                },
            },
        ],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(raw) > matched_limit

    proc = _run_shim_raw(transformed, raw)

    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stdout.startswith(b"FIRED:Edit")


def test_inject_shim_rejects_mixed_top_level_and_toolcalls_selection():
    """A payload with both a top-level action and a toolCalls batch is
    ambiguous: the host precedence is unverified, so a benign top-level
    tool_name must not let a dangerous toolCalls entry slip through under a
    guessed interpretation. The shim rejects the mix outright (#3200). This
    replaces the former test that pinned silent toolCalls selection."""
    guard = (
        "import json\n"
        "import sys\n"
        "data = json.load(sys.stdin)\n"
        'command = data["tool_input"]["command"]\n'
        'print("EVALUATED:" + command, flush=True)\n'
        'if command == "git push origin feature/safe":\n'
        "    sys.exit(0)\n"
        'if command == "git push origin main --force":\n'
        "    sys.exit(2)\n"
        "sys.exit(1)\n"
    )
    transformed = inject_shim(guard, "Bash(git push*)")
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin feature/safe"},
        "toolCalls": [
            {
                "name": "Bash",
                "args": {"command": "git push origin main --force"},
            },
        ],
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "toolCalls conflicts with top-level action fields" in proc.stderr
    # The guard never ran: no candidate was ever evaluated.
    assert "EVALUATED:" not in proc.stdout


@pytest.mark.parametrize(
    ("invalid_call", "expected_error"),
    [
        ("not-an-object", "must be an object"),
        ({}, "name must be a non-empty string"),
        ({"name": 7}, "name must be a non-empty string"),
        ({"name": ""}, "name must be a non-empty string"),
        ({"name": " Edit"}, "must not have leading or trailing whitespace"),
        ({"name": "Edit "}, "must not have leading or trailing whitespace"),
        ({"name": "\tEdit\n"}, "must not have leading or trailing whitespace"),
    ],
)
def test_inject_shim_denies_malformed_toolcalls_before_dispatch(
    invalid_call, expected_error
):
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {
        "toolCalls": [invalid_call],
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "toolCalls[0]" in proc.stderr
    assert expected_error in proc.stderr
    assert "FIRED" not in proc.stdout


@pytest.mark.parametrize(
    "tool_calls",
    [
        {"name": "Edit", "args": {"file_path": "README.md"}},
        "not-a-list",
        7,
        False,
        None,
    ],
)
def test_inject_shim_denies_non_list_toolcalls_before_top_level_fallback(
    tool_calls,
):
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo safe"},
        "toolCalls": tool_calls,
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "toolCalls must be a list when present" in proc.stderr
    assert "FIRED" not in proc.stdout


@pytest.mark.parametrize("top_level_name_field", ["tool_name", "toolName"])
@pytest.mark.parametrize(
    ("top_level_name", "expected_error"),
    [
        ("", "must be a non-empty string"),
        (7, "must be a non-empty string"),
        (None, "must be a non-empty string"),
        (" Edit", "must not have leading or trailing whitespace"),
        ("Edit ", "must not have leading or trailing whitespace"),
        ("\tEdit\n", "must not have leading or trailing whitespace"),
    ],
)
def test_inject_shim_denies_malformed_top_level_name_before_dispatch(
    top_level_name_field, top_level_name, expected_error
):
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {
        top_level_name_field: top_level_name,
        "tool_input": {"file_path": "README.md"},
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert top_level_name_field in proc.stderr
    assert expected_error in proc.stderr
    assert "FIRED" not in proc.stdout


def test_inject_shim_denies_conflicting_top_level_names_before_dispatch():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {
        "tool_name": "Bash",
        "toolName": "Edit",
        "tool_input": {"file_path": "README.md"},
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "conflicting top-level tool_name/toolName values" in proc.stderr
    assert "FIRED" not in proc.stdout


def test_inject_shim_allows_matching_top_level_name_aliases():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {
        "tool_name": "Edit",
        "toolName": "Edit",
        "tool_input": {"file_path": "README.md"},
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 0
    assert proc.stdout.startswith("FIRED:Edit")


def test_inject_shim_rejects_mixed_top_level_and_nonempty_toolcalls():
    # Hardening (#3200): a payload carrying BOTH top-level action fields and a
    # non-empty toolCalls batch is ambiguous because the host precedence between
    # the two shapes is unverified. The shim must reject it before any guard
    # runs rather than silently drop the top-level aliases and dispatch the
    # batch. This flips the former silent-drop behavior, which let an attacker
    # hide a denied action behind a benign top-level alias (or vice versa).
    body = (
        "import json\n"
        "import sys\n"
        "data = json.load(sys.stdin)\n"
        "print(json.dumps(data, sort_keys=True), flush=True)\n"
    )
    transformed = inject_shim(body, "^Edit$")
    payload = {
        "sessionId": "canonical-batch",
        "tool_name": "Bash",
        "toolName": "Write",
        "tool_input": {"command": "echo snake"},
        "toolArgs": {"command": "echo camel"},
        "tool_call_id": "top-snake",
        "toolCallId": "top-camel",
        "toolCalls": [
            {
                "id": "batch-call",
                "name": "Edit",
                "args": {"file_path": "README.md"},
            },
        ],
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "toolCalls conflicts with top-level action fields" in proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize("top_level_name_field", ["tool_name", "toolName"])
@pytest.mark.parametrize("top_level_name", ["Edit", "", 7, None])
def test_inject_shim_denies_empty_toolcalls_with_top_level_tool_name(
    top_level_name_field, top_level_name
):
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {
        top_level_name_field: top_level_name,
        "tool_input": {"file_path": "README.md"},
        "toolCalls": [],
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "toolCalls conflicts with top-level action fields" in proc.stderr
    assert "FIRED" not in proc.stdout


def test_inject_shim_allows_empty_toolcalls_without_top_level_tool_name():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")

    proc = _run_shim(transformed, {"toolCalls": []})

    assert proc.returncode == 0
    assert proc.stderr == ""
    assert "FIRED" not in proc.stdout


def test_inject_shim_validates_entire_toolcalls_batch_before_dispatch():
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {
        "toolCalls": [
            {"name": "Edit", "args": {"file_path": "README.md"}},
            "not-an-object",
        ]
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "toolCalls[1]" in proc.stderr
    assert "FIRED" not in proc.stdout


def test_inject_shim_evaluates_all_matching_calls_until_denied():
    guard = (
        "import json\n"
        "import sys\n"
        "data = json.load(sys.stdin)\n"
        'command = data["tool_input"]["command"]\n'
        'print("EVALUATED:" + command, flush=True)\n'
        'if command == "git push origin feature/safe":\n'
        "    sys.exit(0)\n"
        'if command == "git push origin main --force":\n'
        "    sys.exit(2)\n"
        "sys.exit(1)\n"
    )
    transformed = inject_shim(guard, "Bash(git push*)")
    payload = {
        "toolCalls": [
            {
                "name": "Bash",
                "args": {"command": "git push origin feature/safe"},
            },
            {
                "name": "Bash",
                "args": {"command": "git push origin main --force"},
            },
            {
                "name": "Bash",
                "args": {"command": "git push origin feature/safe"},
            },
        ]
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert proc.stdout.splitlines() == [
        "EVALUATED:git push origin feature/safe",
        "EVALUATED:git push origin main --force",
    ]


# Independent test contract: the maximum permitted number of toolCalls
# entries per event. Not read from generate_hooks_shim.
_TOOL_CALLS_CANDIDATE_CAP = 256


def test_inject_shim_toolcalls_candidate_cap_boundary_fires_once():
    """Exactly 256 toolCalls entries must still pass; the guard fires once
    for the sole matching (final) entry."""
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    non_matching = [
        {"name": "Read", "args": {"file_path": f"f{i}.txt"}}
        for i in range(_TOOL_CALLS_CANDIDATE_CAP - 1)
    ]
    payload = {
        "toolCalls": non_matching
        + [{"name": "Edit", "args": {"file_path": "README.md"}}]
    }
    assert len(payload["toolCalls"]) == _TOOL_CALLS_CANDIDATE_CAP

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["FIRED:Edit"]


def test_inject_shim_toolcalls_candidate_cap_denies_one_above_boundary():
    """257 toolCalls entries must be denied before any candidate is
    evaluated: the guard must never fire, and payload contents (e.g. args
    markers) must not be disclosed on stdout or stderr."""
    guard = (
        "import json\n"
        "import sys\n"
        "data = json.load(sys.stdin)\n"
        "print('FIRED:' + json.dumps(data.get('tool_input')), flush=True)\n"
        "sys.exit(0)\n"
    )
    transformed = inject_shim(guard, "^Edit$")
    marker = "marker-do-not-disclose-cap-test"
    non_matching = [
        {"name": "Read", "args": {"file_path": f"f{i}.txt"}}
        for i in range(_TOOL_CALLS_CANDIDATE_CAP)
    ]
    payload = {
        "toolCalls": non_matching + [{"name": "Edit", "args": {"marker": marker}}]
    }
    assert len(payload["toolCalls"]) == _TOOL_CALLS_CANDIDATE_CAP + 1

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "toolCalls" in proc.stderr
    assert f"{_TOOL_CALLS_CANDIDATE_CAP + 1} entries" in proc.stderr
    assert f"limit is {_TOOL_CALLS_CANDIDATE_CAP}" in proc.stderr
    assert marker not in proc.stderr
    assert "FIRED" not in proc.stdout
    assert marker not in proc.stdout


def test_inject_shim_toolcalls_candidate_cap_denies_257_invalid_entries():
    """257 non-dict toolCalls entries must also be denied by the cap, since
    the cap must apply to the raw list length, not the post-filter
    candidate count."""
    transformed = inject_shim(_TRACE_SCRIPT, "^Edit$")
    payload = {"toolCalls": ["not-a-dict"] * (_TOOL_CALLS_CANDIDATE_CAP + 1)}
    assert len(payload["toolCalls"]) == _TOOL_CALLS_CANDIDATE_CAP + 1

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert "FIRED" not in proc.stdout


@pytest.mark.parametrize(
    ("exit_code", "expected_code"),
    [(None, 0), (0, 0), (2, 2), ("blocked", 1)],
)
def test_inject_shim_normalizes_system_exit_codes(exit_code, expected_code):
    guard = f"import sys\nsys.exit({exit_code!r})\n"
    transformed = inject_shim(guard, "Bash")

    proc = _run_shim(transformed, {"tool_name": "Bash"})

    assert proc.returncode == expected_code


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


def test_inject_shim_no_op_on_batched_toolcalls_without_match():
    transformed = inject_shim(_TRACE_SCRIPT, "Bash")
    proc = _run_shim(
        transformed,
        {
            "toolCalls": [
                {
                    "id": "custom_call_patch",
                    "name": "apply_patch",
                    "args": "*** Begin Patch\n*** Add File: example.txt\n+hi\n*** End Patch\n",
                }
            ]
        },
    )
    assert proc.returncode == 0
    assert "FIRED" not in proc.stdout
    assert proc.stderr == ""


def test_inject_shim_fires_on_batched_toolcalls_with_tool_glob_match():
    script = (
        "import sys, json\n"
        "data = json.load(sys.stdin) if sys.stdin else {}\n"
        'print("FIRED:" + data.get("tool_name", ""))\n'
        'print("COMMAND:" + data.get("tool_input", {}).get("command", ""))\n'
        "sys.exit(0)\n"
    )
    transformed = inject_shim(script, "Bash(git commit*)")
    proc = _run_shim(
        transformed,
        {
            "sessionId": "s1",
            "toolCalls": [
                {"id": "custom_call_patch", "name": "apply_patch", "args": "patch"},
                {
                    "id": "custom_call_bash",
                    "name": "Bash",
                    "args": {"command": "git commit -m example"},
                },
            ],
        },
    )
    assert proc.returncode == 0
    assert "FIRED:Bash" in proc.stdout
    assert "COMMAND:git commit -m example" in proc.stdout


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
    transformed_source: str, payload: dict[str, Any], env_extra: dict[str, str]
) -> subprocess.CompletedProcess[str]:
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
            text=True, encoding="utf-8",
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
            text=True, encoding="utf-8",
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
    _write_script(hooks_src, "SubagentStop", "subagent.py")
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


def _setup_skill_companion_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_owner: bool = True,
    include_loader: bool = True,
) -> Path:
    # Production _COMPANIONS_BY_OWNER is empty after issue #3184 removed every
    # real companion pairing, so exercise the copy mechanism with a synthetic,
    # fixture-local owner/companion mapping instead of a live production entry.
    monkeypatch.setattr(
        generate_hooks_events,
        "_COMPANIONS_BY_OWNER",
        {"Stop/invoke_owner.py": ("companion_module.py",)},
    )
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"
    hooks: dict[str, Any] = {}
    if include_owner:
        _write_script(
            hooks_src,
            "Stop",
            "invoke_owner.py",
            "try:\n"
            "    from companion_module import TOKEN\n"
            "except ModuleNotFoundError:\n"
            "    TOKEN = 'fallback'\n"
            "print(TOKEN)\n",
        )
        hooks = {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u .claude/hooks/Stop/"
                                "invoke_owner.py"
                            ),
                        }
                    ]
                }
            ]
        }
    if include_loader:
        _write_script(
            hooks_src,
            "Stop",
            "companion_module.py",
            "TOKEN = 'portable-import'\n",
        )
    _write_settings(tmp_path / "settings.json", hooks)
    return cfg


def test_generator_copies_skill_loader_without_dispatching_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    companion = tmp_path / "out" / "Stop" / "companion_module.py"
    assert companion.read_text(encoding="utf-8") == "TOKEN = 'portable-import'\n"
    generated = json.loads((tmp_path / "out" / "hooks.json").read_text())
    entries = generated["hooks"]["Stop"]
    assert len(entries) == 1
    assert "companion_module.py" not in json.dumps(entries)


def test_generated_skill_owner_imports_companion_portably(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    owner = tmp_path / "out" / "Stop" / "invoke_owner.py"

    process = subprocess.run(
        [sys.executable, str(owner)],
        cwd=tmp_path,
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
        timeout=30,
    )

    assert rc == 0
    assert process.returncode == 0
    assert process.stdout.strip() == "portable-import"


def test_generator_fails_when_declared_skill_loader_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch, include_loader=False)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "declared runtime companion is missing" in captured.err
    assert "companion_module.py" in captured.err
    assert not (tmp_path / "out" / "hooks.json").exists()
    # #9: validation must run BEFORE the owner is copied, so a missing
    # companion never leaves a half-written owner script with no matching
    # hooks.json.
    assert not (tmp_path / "out" / "Stop" / "invoke_owner.py").exists()


def test_generator_no_regen_owner_skip_validates_but_skips_companion_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NO-REGEN on the owner must not create or overwrite its companion (#2)."""
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    owner = tmp_path / "out" / "Stop" / "invoke_owner.py"
    companion = tmp_path / "out" / "Stop" / "companion_module.py"

    # Customer protects the owner and hand-edits the companion.
    owner.write_text("# NO-REGEN\nprint('customer fix')\n", encoding="utf-8")
    companion.write_text("TOKEN = 'customer-edit'\n", encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert owner.read_text().startswith("# NO-REGEN\n")
    # Declaration was still validated (source companion exists), but the
    # NO-REGEN-skipped owner must not trigger a companion (re)copy.
    assert companion.read_text() == "TOKEN = 'customer-edit'\n"


def test_generator_no_regen_owner_requires_existing_output_companion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A protected owner cannot emit an entry without its runtime companion."""
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch)
    owner = tmp_path / "out" / "Stop" / "invoke_owner.py"
    owner.parent.mkdir(parents=True)
    owner.write_text("# NO-REGEN\nprint('customer fix')\n", encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "NO-REGEN owner requires an existing runtime companion" in captured.err
    assert "companion_module.py" in captured.err
    assert owner.read_text(encoding="utf-8").startswith("# NO-REGEN\n")
    assert not (owner.parent / "companion_module.py").exists()
    assert not (tmp_path / "out" / "hooks.json").exists()


def test_generator_companion_only_no_regen_preserves_runtime_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A protected companion blocks all owner replacement before any write."""
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch)
    hooks_source = tmp_path / "hooks_src"
    early_source = _write_script(
        hooks_source,
        "PostToolUse",
        "early_owner.py",
        "print('old early owner')\n",
    )
    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    settings["PostToolUse"] = [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "python3 -u .claude/hooks/PostToolUse/early_owner.py"
                    ),
                }
            ]
        }
    ]
    _write_settings(settings_path, settings)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    early_target = tmp_path / "out" / "PostToolUse" / "early_owner.py"
    owner = tmp_path / "out" / "Stop" / "invoke_owner.py"
    companion = tmp_path / "out" / "Stop" / "companion_module.py"
    hooks_json = tmp_path / "out" / "hooks.json"
    original_early = early_target.read_bytes()
    original_owner = owner.read_bytes()
    original_hooks = hooks_json.read_bytes()
    companion.write_text(
        "# NO-REGEN\nTOKEN = 'customer-edit'\n",
        encoding="utf-8",
    )
    protected_companion = companion.read_bytes()
    early_source.write_text("print('new early owner')\n", encoding="utf-8")
    source_owner = (
        tmp_path / "hooks_src" / "Stop" / "invoke_owner.py"
    )
    source_owner.write_text("print('new owner')\n", encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "runtime companion target is NO-REGEN protected" in captured.err
    assert early_target.read_bytes() == original_early
    assert owner.read_bytes() == original_owner
    assert companion.read_bytes() == protected_companion
    assert hooks_json.read_bytes() == original_hooks


def test_generator_companion_copy_failure_restores_earlier_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A later staging failure rolls back an earlier published event."""
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch)
    hooks_source = tmp_path / "hooks_src"
    early_source = _write_script(
        hooks_source,
        "PostToolUse",
        "early_owner.py",
        "print('old early owner')\n",
    )
    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    settings["PostToolUse"] = [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "python3 -u .claude/hooks/PostToolUse/early_owner.py"
                    ),
                }
            ]
        }
    ]
    _write_settings(settings_path, settings)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    early_target = tmp_path / "out" / "PostToolUse" / "early_owner.py"
    owner = tmp_path / "out" / "Stop" / "invoke_owner.py"
    companion = tmp_path / "out" / "Stop" / "companion_module.py"
    hooks_json = tmp_path / "out" / "hooks.json"
    original_early = early_target.read_bytes()
    original_owner = owner.read_bytes()
    original_companion = companion.read_bytes()
    original_hooks = hooks_json.read_bytes()
    early_source.write_text("print('new early owner')\n", encoding="utf-8")
    source_owner = (
        tmp_path / "hooks_src" / "Stop" / "invoke_owner.py"
    )
    source_companion = (
        tmp_path / "hooks_src" / "Stop" / "companion_module.py"
    )
    source_owner.write_text("print('new owner')\n", encoding="utf-8")
    source_companion.write_text("TOKEN = 'new'\n", encoding="utf-8")
    real_copy_script = generate_hooks_events._copy_script

    def fail_companion_copy(
        source: Path,
        target: Path,
        *,
        matcher: str | None,
        what_if: bool,
    ) -> tuple[bool, str]:
        if source.name == "companion_module.py":
            raise OSError("simulated companion copy failure")
        return real_copy_script(
            source,
            target,
            matcher=matcher,
            what_if=what_if,
        )

    monkeypatch.setattr(
        generate_hooks_events,
        "_copy_script",
        fail_companion_copy,
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "failed to stage or publish hook group" in captured.err
    assert "simulated companion copy failure" in captured.err
    assert early_target.read_bytes() == original_early
    assert owner.read_bytes() == original_owner
    assert companion.read_bytes() == original_companion
    assert hooks_json.read_bytes() == original_hooks
    assert not list(tmp_path.rglob(".hook-stage-*.tmp"))


def _setup_orphan_event_fixture(tmp_path: Path) -> tuple[Path, Path]:
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash")
    text = cfg.read_text(encoding="utf-8")
    cfg.write_text(
        text.replace("PreToolUse: PreToolUse", "PreToolUse: PostToolUse"),
        encoding="utf-8",
    )
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    legacy_dir = tmp_path / "out" / "PostToolUse"
    assert legacy_dir.is_dir()
    cfg.write_text(text, encoding="utf-8")
    return cfg, legacy_dir


def test_generator_removes_owned_orphan_event_directory(tmp_path: Path) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    cache_dir = legacy_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "_bootstrap.cpython-314.pyc").write_bytes(b"bytecode")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert not legacy_dir.exists()


def test_generator_preserves_unknown_orphan_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    unknown = legacy_dir / "customer.txt"
    unknown.write_text("keep\n", encoding="utf-8")
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    output = capsys.readouterr().out

    assert rc == 0
    assert unknown.read_text(encoding="utf-8") == "keep\n"
    assert "preserved unknown orphan artifact" in output
    assert not (legacy_dir / "_manifest.json").exists()


def test_generator_preserves_protected_orphan_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    manifest = legacy_dir / "_manifest.json"
    manifest.with_suffix(".json.noregen").write_text("keep\n", encoding="utf-8")
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    output = capsys.readouterr().out

    assert rc == 0
    assert manifest.is_file()
    assert "NO-REGEN" in output


def test_generator_preserves_orphan_with_malformed_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    manifest = legacy_dir / "_manifest.json"
    manifest.write_text("{not json", encoding="utf-8")
    before = sorted(path.name for path in legacy_dir.iterdir())
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    output = capsys.readouterr().out

    assert rc == 0
    assert sorted(path.name for path in legacy_dir.iterdir()) == before
    assert "ownership manifest invalid" in output


def test_generator_preserves_symlinked_orphan_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    external = tmp_path / "external-legacy"
    legacy_dir.rename(external)
    legacy_dir.symlink_to(external, target_is_directory=True)
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert legacy_dir.is_symlink()
    assert (external / "_manifest.json").is_file()


def test_generator_preserves_orphan_manifest_path_escape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    manifest_path = legacy_dir / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["shims"] = ["../outside.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    outside = legacy_dir.parent / "outside.py"
    outside.write_text("customer owned\n", encoding="utf-8")
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    output = capsys.readouterr().out

    assert rc == 0
    assert outside.read_text(encoding="utf-8") == "customer owned\n"
    assert legacy_dir.is_dir()
    assert "manifest-listed shim ownership failed" in output


def test_generator_orphan_cleanup_rolls_back_on_later_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    before = {
        path.name: path.read_bytes()
        for path in legacy_dir.iterdir()
        if path.is_file()
    }
    real_publish_many = (
        generate_hooks_transaction.HookGenerationTransaction.publish_many
    )

    def fail_config_publish(
        transaction: generate_hooks_transaction.HookGenerationTransaction,
        pairs: Any,
    ) -> None:
        publish_pairs = list(pairs)
        if any(target.name == "hooks.json" for _staged, target in publish_pairs):
            raise OSError("simulated config publish failure")
        real_publish_many(transaction, publish_pairs)

    monkeypatch.setattr(
        generate_hooks_transaction.HookGenerationTransaction,
        "publish_many",
        fail_config_publish,
    )
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 1
    assert {
        path.name: path.read_bytes()
        for path in legacy_dir.iterdir()
        if path.is_file()
    } == before


def test_generator_orphan_cleanup_is_idempotent(tmp_path: Path) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)

    first_rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    second_rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert first_rc == second_rc == 0
    assert not legacy_dir.exists()


def test_generator_orphan_cleanup_what_if_does_not_delete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path, what_if=True)
    output = capsys.readouterr().out

    assert rc == 0
    assert legacy_dir.is_dir()
    assert "Would remove generated orphan" in output


def test_generator_orphan_discovery_failure_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, legacy_dir = _setup_orphan_event_fixture(tmp_path)
    before = {
        path.relative_to(tmp_path / "out"): path.read_bytes()
        for path in (tmp_path / "out").rglob("*")
        if path.is_file()
    }

    def fail_orphan_discovery(*args: Any, **kwargs: Any) -> None:
        raise OSError("simulated orphan discovery failure")

    monkeypatch.setattr(
        generate_dispatcher,
        "find_owned_orphan_artifacts",
        fail_orphan_discovery,
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    after = {
        path.relative_to(tmp_path / "out"): path.read_bytes()
        for path in (tmp_path / "out").rglob("*")
        if path.is_file()
    }
    assert rc == 1
    assert legacy_dir.is_dir()
    assert after == before


def test_orphan_directory_cleanup_ignores_already_removed_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generate_hooks_events._remove_empty_orphan_directories([tmp_path / "missing"])

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "artifact_name",
    ("_manifest.json", "_dispatch.py", "_bootstrap.py"),
)
def test_generator_dispatcher_no_regen_fails_before_any_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    artifact_name: str,
) -> None:
    """Every protected dispatcher artifact aborts before owner publication."""
    cfg = _write_config(
        tmp_path,
        hooks_stanza_overrides={"dispatcher": True},
    )
    _write_script(
        tmp_path / "hooks_src",
        "PreToolUse",
        "owner.py",
        "print('owner')\n",
    )
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u .claude/hooks/PreToolUse/owner.py"
                            ),
                        }
                    ]
                }
            ]
        },
    )
    protected = tmp_path / "out" / "PreToolUse" / artifact_name
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected_bytes = b"# NO-REGEN\ncustomer-owned\n"
    protected.write_bytes(protected_bytes)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "dispatcher artifact is NO-REGEN protected" in captured.err
    assert protected.read_bytes() == protected_bytes
    assert not (tmp_path / "out" / "PreToolUse" / "owner.py").exists()
    assert not (tmp_path / "out" / "hooks.json").exists()


def test_generator_dispatcher_ignores_protected_shell_only_event(
    tmp_path: Path,
) -> None:
    """A stale protected artifact is allowed when no Python hook emits."""
    cfg = _write_config(
        tmp_path,
        hooks_stanza_overrides={"dispatcher": True},
    )
    (tmp_path / "hooks_src").mkdir()
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo shell-only hook",
                        }
                    ]
                }
            ]
        },
    )
    protected = tmp_path / "out" / "PreToolUse" / "_manifest.json"
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected_bytes = b"# NO-REGEN\ncustomer-owned\n"
    protected.write_bytes(protected_bytes)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert protected.read_bytes() == protected_bytes
    generated = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert generated["hooks"] == {}


def _setup_dispatcher_matcher_fixture(tmp_path: Path, matcher: str) -> Path:
    cfg = _write_config(
        tmp_path,
        hooks_stanza_overrides={"dispatcher": True},
    )
    _write_script(
        tmp_path / "hooks_src",
        "PreToolUse",
        "owner.py",
        "print('owner')\n",
    )
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "matcher": matcher,
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u .claude/hooks/PreToolUse/owner.py"
                            ),
                        }
                    ],
                }
            ]
        },
    )
    return cfg


def _set_dispatcher_matcher(tmp_path: Path, matcher: str) -> None:
    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["matcher"] = matcher
    settings_path.write_text(json.dumps(settings), encoding="utf-8")


def _generated_owner_shims(tmp_path: Path) -> list[Path]:
    event_dir = tmp_path / "out" / "PreToolUse"
    return [
        candidate
        for candidate in sorted(event_dir.glob("owner*.py"))
        if is_shimmed(candidate.read_text(encoding="utf-8"))
    ]


def test_generator_dispatcher_removes_published_stale_matcher_shim(
    tmp_path: Path,
) -> None:
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash(git status*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    stale = _generated_owner_shims(tmp_path)
    assert len(stale) == 1

    _set_dispatcher_matcher(tmp_path, "Bash(git commit*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    current = _generated_owner_shims(tmp_path)
    assert len(current) == 1
    assert current[0] != stale[0]
    assert not stale[0].exists()


def _setup_owner_with_companions_and_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """One PreToolUse dispatcher group: an owner (two declared companions)
    plus an independent sibling owner sharing the same matcher.

    Synthetic, fixture-local ``_COMPANIONS_BY_OWNER`` entry -- per the
    convention in :func:`_setup_skill_companion_fixture` above -- rather
    than the real, production ``push_pr_script_identity_guard`` entry, so
    this test exercises the generic cleanup mechanism, not one wired to a
    single named owner.
    """
    monkeypatch.setattr(
        generate_hooks_events,
        "_COMPANIONS_BY_OWNER",
        {
            "PreToolUse/invoke_owner.py": (
                "owner_companion_a.py",
                "owner_companion_b.py",
            )
        },
    )
    cfg = _write_config(tmp_path, hooks_stanza_overrides={"dispatcher": True})
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "invoke_owner.py", "print('owner')\n")
    _write_script(hooks_src, "PreToolUse", "owner_companion_a.py", "TOKEN_A = 1\n")
    _write_script(hooks_src, "PreToolUse", "owner_companion_b.py", "TOKEN_B = 2\n")
    _write_script(hooks_src, "PreToolUse", "invoke_sibling.py", "print('sibling')\n")
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/invoke_owner.py",
                        },
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
                        },
                    ],
                }
            ]
        },
    )
    return cfg


def test_generator_dispatcher_removes_owner_and_companions_when_owner_excluded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regeneration must sweep a removed owner's companions too (issue #5013).

    ``find_stale_matcher_shims`` (the existing dispatcher-mode cleanup,
    exercised above) only recognizes shim-WRAPPED owner scripts
    (``is_shimmed``); a companion is a plain, never-shimmed helper module,
    so it was never a candidate for that scan. A companion left behind by
    a removed or ``copilotExclude``-d owner therefore lingered in
    ``src/copilot-cli`` forever even though the owner's own generated shim
    was correctly swept.

    Starting state (the "stale owner and companion artifacts" this test
    proves cleanup against): a first generation run publishes the owner's
    shim AND both declared companions, then an unrelated helper file is
    planted directly in the same output directory -- standing in for a
    file a prior, independent generation left there. The owner is then
    removed from the settings group (simulating a ``copilotExclude: true``
    flip, or a plain manifest edit) while a sibling hook keeps the
    PreToolUse event itself active. Regeneration must remove ONLY the
    owner's own shim (existing mechanism) and its two declared companions
    (new mechanism), while the unrelated helper and the sibling's own
    generated shim are untouched.
    """
    cfg = _setup_owner_with_companions_and_sibling(tmp_path, monkeypatch)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out_dir = tmp_path / "out" / "PreToolUse"
    companion_a = out_dir / "owner_companion_a.py"
    companion_b = out_dir / "owner_companion_b.py"
    assert companion_a.is_file()
    assert companion_b.is_file()
    owner_shims_before = [
        path
        for path in out_dir.glob("invoke_owner*.py")
        if is_shimmed(path.read_text(encoding="utf-8"))
    ]
    assert len(owner_shims_before) == 1

    unrelated = out_dir / "unrelated_helper.py"
    unrelated.write_text("KEEP = True\n", encoding="utf-8")

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert not companion_a.exists()
    assert not companion_b.exists()
    assert not owner_shims_before[0].exists()
    assert unrelated.read_text(encoding="utf-8") == "KEEP = True\n"
    sibling_shims = [
        path
        for path in out_dir.glob("invoke_sibling*.py")
        if is_shimmed(path.read_text(encoding="utf-8"))
    ]
    assert len(sibling_shims) == 1


def test_active_dispatchable_owners_skip_non_list_groups(tmp_path: Path) -> None:
    """Malformed event groups cannot become active companion owners."""
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "invoke_owner.py", "print('owner')\n")
    hooks_map = {
        "PostToolUse": {"hooks": []},
        "PreToolUse": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "python3 -u "
                            ".claude/hooks/PreToolUse/invoke_owner.py"
                        ),
                    }
                ]
            }
        ],
    }

    owners = list(
        generate_hooks_events._iter_active_dispatchable_owners(
            hooks_map,
            event_remap={
                "PostToolUse": "PostToolUse",
                "PreToolUse": "PreToolUse",
            },
            event_drop=set(),
            script_source=hooks_src,
        )
    )

    assert len(owners) == 1
    assert owners[0][0] == "PreToolUse"
    assert owners[0][2] == Path("PreToolUse/invoke_owner.py")


def _setup_single_companion_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """One PreToolUse owner (single declared companion) plus an independent
    sibling hook, direct mode (no dispatcher consolidation).

    Shared starting state for the four companion-cleanup tests below; each
    mutates ``settings.json`` and re-runs generation afterward its own way,
    so only this common setup is factored out here.
    """
    monkeypatch.setattr(
        generate_hooks_events,
        "_COMPANIONS_BY_OWNER",
        {"PreToolUse/invoke_owner.py": ("owner_companion.py",)},
    )
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "invoke_owner.py", "print('owner')\n")
    _write_script(hooks_src, "PreToolUse", "owner_companion.py", "TOKEN = 1\n")
    _write_script(hooks_src, "PreToolUse", "invoke_sibling.py", "print('sibling')\n")
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/invoke_owner.py",
                        },
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
                        },
                    ]
                }
            ]
        },
    )
    return cfg


def _setup_shared_companion_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Two active owners share one companion and each owns one unique file."""
    monkeypatch.setattr(
        generate_hooks_events,
        "_COMPANIONS_BY_OWNER",
        {
            "PreToolUse/invoke_owner_a.py": (
                "shared_companion.py",
                "owner_a_only.py",
            ),
            "PreToolUse/invoke_owner_b.py": (
                "shared_companion.py",
                "owner_b_only.py",
            ),
        },
    )
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "invoke_owner_a.py", "print('owner-a')\n")
    _write_script(hooks_src, "PreToolUse", "invoke_owner_b.py", "print('owner-b')\n")
    _write_script(hooks_src, "PreToolUse", "shared_companion.py", "SHARED = 1\n")
    _write_script(hooks_src, "PreToolUse", "owner_a_only.py", "OWNER_A = 1\n")
    _write_script(hooks_src, "PreToolUse", "owner_b_only.py", "OWNER_B = 1\n")
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/invoke_owner_a.py",
                        },
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/PreToolUse/invoke_owner_b.py",
                        },
                    ]
                }
            ]
        },
    )
    return cfg


def test_generator_direct_mode_removes_companions_of_missing_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Companion cleanup does not depend on dispatcher consolidation.

    Same shape as the dispatcher-mode test above, but WITHOUT
    ``dispatcher: true``. The owner's OWN shim removal is a dispatcher-mode
    feature (``find_stale_matcher_shims`` runs only from
    ``_stage_dispatcher_changes``) so it is out of scope for direct mode
    and not asserted here; this isolates and proves the companion cleanup
    itself is independent of that mode.
    """
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out_dir = tmp_path / "out" / "PreToolUse"
    companion = out_dir / "owner_companion.py"
    assert companion.is_file()

    unrelated = out_dir / "unrelated_helper.py"
    unrelated.write_text("KEEP = True\n", encoding="utf-8")

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert not companion.exists()
    assert unrelated.read_text(encoding="utf-8") == "KEEP = True\n"
    assert (out_dir / "invoke_sibling.py").is_file()


def test_generator_preserves_shared_companion_for_surviving_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing owner must not delete a companion another owner still needs."""
    cfg = _setup_shared_companion_fixture(tmp_path, monkeypatch)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out_dir = tmp_path / "out" / "PreToolUse"
    shared = out_dir / "shared_companion.py"
    owner_a_only = out_dir / "owner_a_only.py"
    owner_b_only = out_dir / "owner_b_only.py"
    assert shared.is_file()
    assert owner_a_only.is_file()
    assert owner_b_only.is_file()

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_owner_b.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert shared.is_file()
    assert not owner_a_only.exists()
    assert owner_b_only.is_file()
    assert (out_dir / "invoke_owner_b.py").is_file()


def test_generator_companion_cleanup_is_what_if_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--what-if`` reports the removal without deleting anything."""
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    companion = tmp_path / "out" / "PreToolUse" / "owner_companion.py"
    assert companion.is_file()

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path, what_if=True)

    assert rc == 0
    assert companion.is_file()


def test_generator_companion_cleanup_preserves_no_regen_protected_companion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A NO-REGEN-protected companion of a missing owner is preserved, not deleted.

    Mirrors the existing NO-REGEN preservation contract for stale matcher
    shims and stale event artifacts: a customer-modified companion must
    survive even though its owner is gone, and the run must still succeed
    (rc=0) with a NOTICE, not fail.
    """
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    companion = tmp_path / "out" / "PreToolUse" / "owner_companion.py"
    assert companion.is_file()
    companion.with_suffix(companion.suffix + ".noregen").write_text("preserve\n", encoding="utf-8")
    capsys.readouterr()

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 0
    assert companion.is_file()
    assert companion.name in captured.out
    assert "NO-REGEN" in captured.out


def test_generator_companion_cleanup_os_error_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An OSError while staging companion cleanup rolls back, not partial-commits.

    Mirrors ``test_generator_orphan_discovery_failure_rolls_back``: the
    failure is injected at the file-read boundary the production strict
    detector actually uses, so the test covers the fail-closed path rather
    than a monkeypatched wrapper alias.
    """
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    companion = tmp_path / "out" / "PreToolUse" / "owner_companion.py"
    assert companion.is_file()
    before = companion.read_bytes()

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    real_open = Path.open
    failed = False

    def fail_only_for_companion(
        path: Path, *args: Any, **kwargs: Any
    ):  # pragma: no cover - closure shape only
        nonlocal failed
        if not failed and path == companion:
            failed = True
            raise OSError("simulated companion cleanup failure")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_only_for_companion)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 1
    assert companion.is_file()
    assert companion.read_bytes() == before


def test_generator_companion_cleanup_rejects_symlinked_output_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlinked output root must abort companion cleanup before resolve()."""
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out_root = tmp_path / "out"
    out_dir = out_root / "PreToolUse"
    companion = out_dir / "owner_companion.py"
    sibling = out_dir / "invoke_sibling.py"
    assert companion.is_file()
    assert sibling.is_file()
    companion_before = companion.read_bytes()
    sibling_before = sibling.read_bytes()

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    real_lstat = Path.lstat
    symlink_stat = os.stat_result((stat.S_IFLNK, 0, 0, 0, 0, 0, 0, 0, 0, 0))

    def fake_lstat(path: Path) -> os.stat_result:
        if path == out_root:
            return symlink_stat
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "companion cleanup path validation failed" in captured.err
    assert "refusing symlinked hooks output root" in captured.err
    assert companion.is_file()
    assert companion.read_bytes() == companion_before
    assert sibling.is_file()
    assert sibling.read_bytes() == sibling_before


def test_generator_companion_cleanup_rejects_symlinked_event_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlinked event directory must abort companion cleanup, not follow it.

    Issue #5013 review fix (finding 2): ``_missing_owner_companion_targets``
    built ``event_dir`` (and every candidate path under it) without ever
    checking whether ``event_dir`` itself was a symlink. A symlinked
    ``out/PreToolUse`` could redirect
    ``HookGenerationTransaction.delete_many`` into deleting a file OUTSIDE
    the generated tree once the companion's declared owner went missing
    (CWE-59, symlink following).

    The fix reuses ``generate_dispatcher.validate_event_directory``, the
    SAME safety gate ``generate_dispatcher.find_stale_matcher_shims`` already
    applies. Quoted verbatim from that function (``build/scripts/
    generate_dispatcher.py``, read this session)::

        if stat.S_ISLNK(event_stat.st_mode):
            raise ValueError(f"refusing symlinked event directory: {event_dir}")

    This test injects the SAME fake-lstat technique
    ``test_stale_scan_rejects_symlinked_event_directory`` in
    ``test_generate_dispatcher.py`` uses against that function directly, but
    drives it end-to-end through ``generate_hooks`` so a symlinked directory
    is proven to abort the WHOLE run (exit 2), not just skip one check.
    """
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out_dir = tmp_path / "out" / "PreToolUse"
    companion = out_dir / "owner_companion.py"
    sibling = out_dir / "invoke_sibling.py"
    assert companion.is_file()
    assert sibling.is_file()
    companion_before = companion.read_bytes()
    sibling_before = sibling.read_bytes()

    # Remove the owner from settings.json (companion becomes orphaned) while
    # the sibling hook keeps the PreToolUse event itself active, matching
    # `_setup_single_companion_fixture`'s sibling-based cleanup tests above.
    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    real_lstat = Path.lstat
    symlink_stat = os.stat_result((stat.S_IFLNK, 0, 0, 0, 0, 0, 0, 0, 0, 0))

    def fake_lstat(path: Path) -> os.stat_result:
        if path == out_dir:
            return symlink_stat
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "companion cleanup path validation failed" in captured.err
    assert "refusing symlinked event directory" in captured.err
    # No partial artifact change: neither the orphaned companion nor the
    # still-active sibling's generated file was touched by the aborted run.
    assert companion.is_file()
    assert companion.read_bytes() == companion_before
    assert sibling.is_file()
    assert sibling.read_bytes() == sibling_before


def test_generator_companion_cleanup_rejects_symlinked_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlinked companion candidate must abort cleanup, not be deleted.

    Issue #5013 review fix (finding 2), the candidate-file half of the same
    gap: even with a legitimate (non-symlinked) event directory, the
    COMPANION FILE ITSELF could be a symlink planted at the exact path the
    generator expects its runtime companion to occupy. Deleting it via
    ``HookGenerationTransaction.delete_many`` would follow the symlink target,
    not the companion. ``generate_dispatcher.validate_candidate_file`` rejects
    this the same way ``find_stale_matcher_shims`` rejects a symlinked shim
    candidate. Quoted verbatim from that function (``build/scripts/
    generate_dispatcher.py``, read this session)::

        if stat.S_ISLNK(candidate_stat.st_mode):
            raise ValueError(f"refusing symlinked hook candidate: {candidate}")

    Mirrors ``test_stale_scan_rejects_symlinked_candidate`` in
    ``test_generate_dispatcher.py``, driven end-to-end through
    ``generate_hooks`` instead of calling the dispatcher function directly.
    """
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out_dir = tmp_path / "out" / "PreToolUse"
    companion = out_dir / "owner_companion.py"
    sibling = out_dir / "invoke_sibling.py"
    assert companion.is_file()
    companion_before = companion.read_bytes()
    sibling_before = sibling.read_bytes()

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/PreToolUse/invoke_sibling.py",
        }
    ]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    real_lstat = Path.lstat
    symlink_stat = os.stat_result((stat.S_IFLNK, 0, 0, 0, 0, 0, 0, 0, 0, 0))

    def fake_lstat(path: Path) -> os.stat_result:
        if path == companion:
            return symlink_stat
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "companion cleanup path validation failed" in captured.err
    assert "refusing symlinked hook candidate" in captured.err
    assert companion.is_file()
    assert companion.read_bytes() == companion_before
    assert sibling.is_file()
    assert sibling.read_bytes() == sibling_before


def test_generator_dispatcher_removes_stale_event_artifacts(tmp_path: Path) -> None:
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash(git status*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    stale_event = tmp_path / "out" / "PreToolUse"
    assert any(path.is_file() for path in stale_event.iterdir())

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"] = {"PostToolUse": settings["hooks"]["PreToolUse"]}
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert not stale_event.exists()


def test_generator_dispatcher_preserves_protected_stale_event(
    tmp_path: Path,
) -> None:
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash(git status*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    stale_event = tmp_path / "out" / "PreToolUse"
    manifest = stale_event / "_manifest.json"
    marker = manifest.with_suffix(manifest.suffix + ".noregen")
    marker.write_text("preserve\n", encoding="utf-8")
    existing = {path for path in stale_event.iterdir() if path.is_file()}

    settings_path = tmp_path / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"] = {"PostToolUse": settings["hooks"]["PreToolUse"]}
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert existing <= {path for path in stale_event.iterdir() if path.is_file()}


def test_generator_dispatcher_preserves_protected_published_stale_shim(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash(git status*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    stale = _generated_owner_shims(tmp_path)
    assert len(stale) == 1
    stale[0].with_suffix(stale[0].suffix + ".noregen").write_text(
        "preserve\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    _set_dispatcher_matcher(tmp_path, "Bash(git commit*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 0
    assert stale[0].is_file()
    assert stale[0].name in captured.out
    assert "NO-REGEN" in captured.out


def test_generator_dispatcher_rollback_restores_deleted_stale_shim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash(git status*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    stale = _generated_owner_shims(tmp_path)
    assert len(stale) == 1
    stale_bytes = stale[0].read_bytes()
    _set_dispatcher_matcher(tmp_path, "Bash(git commit*)")
    real_publish_many = (
        generate_hooks_transaction.HookGenerationTransaction.publish_many
    )

    def fail_dispatcher_publish(
        transaction: generate_hooks_transaction.HookGenerationTransaction,
        pairs: Any,
    ) -> None:
        publish_pairs = list(pairs)
        if any(
            target.name == "_dispatch.py"
            for _staged, target in publish_pairs
        ):
            raise OSError("simulated dispatcher publish failure")
        real_publish_many(transaction, publish_pairs)

    monkeypatch.setattr(
        generate_hooks_transaction.HookGenerationTransaction,
        "publish_many",
        fail_dispatcher_publish,
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 1
    assert "simulated dispatcher publish failure" in captured.err
    assert stale[0].read_bytes() == stale_bytes
    assert _generated_owner_shims(tmp_path) == stale


def test_generator_dispatcher_cleanup_path_failure_is_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Issue #5013 review fix: the companion-cleanup path now validates every
    # event directory it touches (see
    # test_generator_companion_cleanup_rejects_symlinked_event_directory and
    # test_generator_companion_cleanup_rejects_symlinked_candidate below).
    # Production `_COMPANIONS_BY_OWNER` declares an owner under PreToolUse,
    # the SAME event this fixture's dispatcher owner uses, so without this
    # override the companion-cleanup check -- not the dispatcher-cleanup
    # check this test targets -- would be the first to observe the faked
    # symlink. Emptying the mapping isolates the assertion below to
    # `_stage_dispatcher_artifacts`'s own `find_stale_matcher_shims` call.
    monkeypatch.setattr(generate_hooks_events, "_COMPANIONS_BY_OWNER", {})
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash(git status*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    stale = _generated_owner_shims(tmp_path)
    assert len(stale) == 1
    event_dir = stale[0].parent
    _set_dispatcher_matcher(tmp_path, "Bash(git commit*)")
    real_lstat = Path.lstat
    symlink_stat = os.stat_result(
        (stat.S_IFLNK, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    )

    def fake_lstat(path: Path) -> os.stat_result:
        if path == event_dir:
            return symlink_stat
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "dispatcher cleanup path validation failed" in captured.err
    assert stale[0].is_file()


def test_generator_dispatcher_staging_failure_restores_earlier_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A partial dispatcher stage cannot mutate live artifacts or owners."""
    cfg = _write_config(
        tmp_path,
        hooks_stanza_overrides={"dispatcher": True},
    )
    source = _write_script(
        tmp_path / "hooks_src",
        "PreToolUse",
        "owner.py",
        "print('old owner')\n",
    )
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u .claude/hooks/PreToolUse/owner.py"
                            ),
                        }
                    ]
                }
            ]
        },
    )
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    owner = tmp_path / "out" / "PreToolUse" / "owner.py"
    dispatcher_paths = [
        tmp_path / "out" / "PreToolUse" / name
        for name in ("_manifest.json", "_dispatch.py", "_bootstrap.py")
    ]
    hooks_json = tmp_path / "out" / "hooks.json"
    originals = {
        path: path.read_bytes()
        for path in [owner, *dispatcher_paths, hooks_json]
    }
    source.write_text("print('new owner')\n", encoding="utf-8")

    def fail_entrypoint(_event_dir: Path, _event: str) -> Path:
        raise OSError("simulated dispatcher staging failure")

    monkeypatch.setattr(
        generate_dispatcher,
        "write_entrypoint",
        fail_entrypoint,
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 1
    assert "simulated dispatcher staging failure" in captured.err
    for path, original in originals.items():
        assert path.read_bytes() == original
    assert not list(tmp_path.rglob(".hook-stage-*"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
def test_transaction_lock_directory_is_private(tmp_path: Path) -> None:
    """Shared temp storage cannot expose one user's lock directory."""
    lock_directory = generate_hooks_transaction._lock_path(tmp_path).parent

    assert stat.S_IMODE(lock_directory.stat().st_mode) == 0o700

def test_transaction_lock_serializes_processes(tmp_path: Path) -> None:
    """A second process waits until the first transaction releases its lock."""
    lock_target = tmp_path / "out"
    first = generate_hooks_transaction.HookGenerationTransaction(lock_target)
    started = tmp_path / "started"
    acquired = tmp_path / "acquired"
    child_code = "\n".join(
        (
            "import sys",
            "from pathlib import Path",
            "sys.path.insert(0, sys.argv[1])",
            "from generate_hooks_transaction import HookGenerationTransaction",
            "Path(sys.argv[3]).write_text('started', encoding='utf-8')",
            "transaction = HookGenerationTransaction(Path(sys.argv[2]))",
            "Path(sys.argv[4]).write_text('acquired', encoding='utf-8')",
            "raise SystemExit(bool(transaction.commit()))",
        )
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_code,
            str(REPO_ROOT / "build" / "scripts"),
            str(lock_target),
            str(started),
            str(acquired),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not started.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.05)
        assert started.exists()
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.5)
        assert not acquired.exists()
    finally:
        assert first.commit() == []

    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stdout + stderr
    assert acquired.exists()


def test_transaction_windows_lock_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ContendedMsvcrt:
        LK_NBLCK = 1

        def __init__(self) -> None:
            self.calls = 0

        def locking(
            self,
            _file_descriptor: int,
            _operation: int,
            _length: int,
        ) -> None:
            self.calls += 1
            if self.calls == 1:
                raise OSError(errno.EDEADLK, "busy")

    contended = ContendedMsvcrt()
    sleeps: list[float] = []
    monkeypatch.setattr(generate_hooks_transaction, "_IS_WINDOWS", True)
    monkeypatch.setitem(sys.modules, "msvcrt", contended)
    monkeypatch.setattr(generate_hooks_transaction.time, "sleep", sleeps.append)

    with tempfile.TemporaryFile("w+b") as handle:
        generate_hooks_transaction._lock_file(handle, timeout_seconds=1)

    assert contended.calls == 2
    assert sleeps == [generate_hooks_transaction._LOCK_RETRY_INTERVAL_SECONDS]


def test_transaction_lock_propagates_non_contention_error() -> None:
    error = OSError(errno.EBADF, "invalid file descriptor")

    def fail() -> None:
        raise error

    with pytest.raises(OSError) as exc_info:
        generate_hooks_transaction._retry_file_lock(fail, timeout_seconds=1)

    assert exc_info.value is error


def test_transaction_windows_lock_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BusyMsvcrt:
        LK_NBLCK = 1

        @staticmethod
        def locking(
            _file_descriptor: int,
            _operation: int,
            _length: int,
        ) -> None:
            raise OSError(errno.EACCES, "busy")

    monkeypatch.setattr(generate_hooks_transaction, "_IS_WINDOWS", True)
    monkeypatch.setitem(sys.modules, "msvcrt", BusyMsvcrt())

    with tempfile.TemporaryFile("w+b") as handle:
        with pytest.raises(TimeoutError, match="after 0 seconds") as exc_info:
            generate_hooks_transaction._lock_file(handle, timeout_seconds=0)

    assert isinstance(exc_info.value.__cause__, OSError)
    assert exc_info.value.__cause__.errno == errno.EACCES


def test_transaction_posix_lock_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BusyFcntl:
        LOCK_EX = 1
        LOCK_NB = 4
        LOCK_UN = 8

        def __init__(self) -> None:
            self.operations: list[int] = []

        def flock(self, _file_descriptor: int, operation: int) -> None:
            self.operations.append(operation)
            raise OSError(errno.EAGAIN, "busy")

    busy = BusyFcntl()
    monkeypatch.setattr(generate_hooks_transaction, "_IS_WINDOWS", False)
    monkeypatch.setitem(sys.modules, "fcntl", busy)

    with tempfile.TemporaryFile("w+b") as handle:
        with pytest.raises(TimeoutError, match="after 0 seconds"):
            generate_hooks_transaction._lock_file(handle, timeout_seconds=0)

    assert busy.operations == [busy.LOCK_EX | busy.LOCK_NB]


@pytest.mark.skipif(os.name != "nt", reason="NTFS alternate data streams only")
def test_transaction_windows_rollback_preserves_named_stream(
    tmp_path: Path,
) -> None:
    """ReplaceFileW journals the complete original Windows file object."""
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("old\n", encoding="utf-8")
    named_stream = Path(f"{target}:transaction-metadata")
    named_stream.write_text("preserved\n", encoding="utf-8")
    staged = transaction.new_stage_path(tmp_path)
    staged.write_text("new\n", encoding="utf-8")

    transaction.publish_many([(staged, target)])

    assert named_stream.read_text(encoding="utf-8") == "preserved\n"
    assert transaction.rollback() == []
    assert target.read_text(encoding="utf-8") == "old\n"
    assert named_stream.read_text(encoding="utf-8") == "preserved\n"

def test_transaction_repeated_windows_publish_keeps_original_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second publication cannot overwrite the run's first backup."""
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("old\n", encoding="utf-8")

    def replace_like_windows(
        source: Path,
        replacement_target: Path,
        backup: Path | None = None,
    ) -> None:
        if backup is not None:
            backup.unlink(missing_ok=True)
            replacement_target.replace(backup)
        source.replace(replacement_target)

    with monkeypatch.context() as windows:
        windows.setattr(generate_hooks_transaction, "_IS_WINDOWS", True)
        windows.setattr(
            generate_hooks_transaction,
            "_replace_target",
            replace_like_windows,
        )

        first = transaction.new_stage_path(tmp_path)
        first.write_text("first\n", encoding="utf-8")
        transaction.publish_many([(first, target)])
        second = transaction.new_stage_path(tmp_path)
        second.write_text("second\n", encoding="utf-8")
        transaction.publish_many([(second, target)])

    assert target.read_text(encoding="utf-8") == "second\n"
    assert transaction.rollback() == []
    assert target.read_text(encoding="utf-8") == "old\n"
    assert not list(tmp_path.glob(".hook-stage-*"))


def test_transaction_windows_delete_rollback_restores_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows deletion moves the original file object into the journal."""
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("old\n", encoding="utf-8")

    with monkeypatch.context() as windows:
        windows.setattr(generate_hooks_transaction, "_IS_WINDOWS", True)
        transaction.delete_many([target])

    assert not target.exists()
    assert transaction.rollback() == []
    assert target.read_text(encoding="utf-8") == "old\n"


def test_transaction_windows_publish_then_delete_keeps_original_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("old\n", encoding="utf-8")

    def replace_like_windows(
        source: Path,
        replacement_target: Path,
        backup: Path | None = None,
    ) -> None:
        if backup is not None:
            replacement_target.replace(backup)
        source.replace(replacement_target)

    with monkeypatch.context() as windows:
        windows.setattr(generate_hooks_transaction, "_IS_WINDOWS", True)
        windows.setattr(
            generate_hooks_transaction,
            "_replace_target",
            replace_like_windows,
        )
        staged = transaction.new_stage_path(tmp_path)
        staged.write_text("new\n", encoding="utf-8")
        transaction.publish_many([(staged, target)])
        transaction.delete_many([target, target])

    assert not target.exists()
    assert transaction.rollback() == []
    assert target.read_text(encoding="utf-8") == "old\n"


def test_transaction_windows_delete_after_creating_target_restores_absence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "target.py"
    staged = transaction.new_stage_path(tmp_path)
    staged.write_text("new\n", encoding="utf-8")

    with monkeypatch.context() as windows:
        windows.setattr(generate_hooks_transaction, "_IS_WINDOWS", True)
        transaction.publish_many([(staged, target)])
        transaction.delete_many([target])

    assert not target.exists()
    assert transaction.rollback() == []
    assert not target.exists()


def test_transaction_delete_many_ignores_missing_target(tmp_path: Path) -> None:
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)

    transaction.delete_many([tmp_path / "missing.py"])

    assert transaction.commit() == []


def test_transaction_delete_many_is_idempotent_after_removal(
    tmp_path: Path,
) -> None:
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "stale.py"
    missing = tmp_path / "missing.py"
    target.write_text("old\n", encoding="utf-8")

    transaction.delete_many([target, target, missing])
    transaction.delete_many([target, missing])

    assert not target.exists()
    assert transaction.rollback() == []
    assert target.read_text(encoding="utf-8") == "old\n"


def test_transaction_rolls_back_partial_windows_delete_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("old\n", encoding="utf-8")
    real_replace = os.replace

    def fail_after_moving_target(source: Path, destination: Path) -> None:
        real_replace(source, destination)
        raise OSError("simulated partial delete failure")

    with monkeypatch.context() as windows:
        windows.setattr(generate_hooks_transaction, "_IS_WINDOWS", True)
        windows.setattr(os, "replace", fail_after_moving_target)
        with pytest.raises(OSError, match="partial delete failure"):
            transaction.delete_many([target])

    assert transaction.rollback() == []
    assert target.read_text(encoding="utf-8") == "old\n"


def test_transaction_rolls_back_partial_windows_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ReplaceFileW partial failure is journaled before cleanup."""
    transaction = generate_hooks_transaction.HookGenerationTransaction(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("old\n", encoding="utf-8")
    staged = transaction.new_stage_path(tmp_path)
    staged.write_text("new\n", encoding="utf-8")

    def fail_after_moving_target(
        _source: Path,
        replacement_target: Path,
        backup: Path | None = None,
    ) -> None:
        assert backup is not None
        replacement_target.replace(backup)
        raise OSError(1177, "simulated partial ReplaceFileW failure")

    monkeypatch.setattr(
        generate_hooks_transaction,
        "_replace_target",
        fail_after_moving_target,
    )

    with pytest.raises(OSError, match="partial ReplaceFileW failure"):
        transaction.publish_many([(staged, target)])

    assert transaction.rollback() == []
    assert target.read_text(encoding="utf-8") == "old\n"
    assert not list(tmp_path.glob(".hook-stage-*"))

def test_generator_failed_rollback_retains_recovery_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed restore keeps the prior bytes in a named recovery file."""
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    owner = tmp_path / "out" / "Stop" / "invoke_owner.py"
    companion = tmp_path / "out" / "Stop" / "companion_module.py"
    hooks_json = tmp_path / "out" / "hooks.json"
    original_companion = companion.read_bytes()
    original_hooks = hooks_json.read_bytes()
    source_owner = (
        tmp_path / "hooks_src" / "Stop" / "invoke_owner.py"
    )
    source_companion = (
        tmp_path / "hooks_src" / "Stop" / "companion_module.py"
    )
    source_owner.write_text("print('new owner')\n", encoding="utf-8")
    source_companion.write_text("TOKEN = 'new'\n", encoding="utf-8")
    real_replace = generate_hooks_transaction._replace_target
    real_restore = generate_hooks_transaction._restore_backup

    def fail_owner_publish(
        source: Path,
        target: Path,
        backup: Path | None = None,
    ) -> None:
        if target == owner:
            raise OSError("simulated owner publish failure")
        real_replace(source, target, backup)

    def fail_companion_restore(backup: Path, target: Path) -> None:
        if target == companion:
            raise OSError("simulated companion rollback failure")
        real_restore(backup, target)

    monkeypatch.setattr(
        generate_hooks_transaction,
        "_replace_target",
        fail_owner_publish,
    )
    monkeypatch.setattr(
        generate_hooks_transaction,
        "_restore_backup",
        fail_companion_restore,
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "simulated owner publish failure" in captured.err
    assert "simulated companion rollback failure" in captured.err
    assert "recovery backup retained at" in captured.err
    assert hooks_json.read_bytes() == original_hooks
    recovery_files = list(
        (tmp_path / "out" / "Stop").glob(".hook-stage-*.tmp")
    )
    assert len(recovery_files) == 1
    assert recovery_files[0].read_bytes() == original_companion


def test_generator_does_not_copy_unowned_skill_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _setup_skill_companion_fixture(tmp_path, monkeypatch, include_owner=False)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert not (tmp_path / "out" / "Stop" / "companion_module.py").exists()


def test_generator_two_owner_missing_companion_leaves_no_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A later owner's missing companion must not let an earlier owner land (#9).

    Regression for a QA probe finding: per-owner validation inside
    ``_emit_one_hook`` only protected the owner it was currently
    processing, so ``PostToolUse/early_owner.py`` (alphabetically first,
    valid companion) was already copied to disk by the time
    ``PreToolUse/late_owner.py``'s (alphabetically second) missing
    companion aborted the run. The probe observed
    ``early_owner_exists=True``, ``missing_companion_owner_exists=False``,
    ``hooks_json_exists=False`` -- proof of a half-written output tree.

    ``generate_hooks.generate_hooks`` now runs
    ``generate_hooks_events._prevalidate_companions`` over BOTH owners
    before either is copied, so this run must fail with NEITHER owner
    NOR ``hooks.json`` on disk.
    """
    cfg = _write_config(tmp_path)
    hooks_src = tmp_path / "hooks_src"

    _write_script(hooks_src, "PostToolUse", "early_owner.py", "print('early')\n")
    _write_script(hooks_src, "PostToolUse", "early_companion.py", "TOKEN = 1\n")
    _write_script(hooks_src, "PreToolUse", "late_owner.py", "print('late')\n")
    # late_companion.py is declared below but intentionally never written.

    monkeypatch.setattr(
        generate_hooks_events,
        "_COMPANIONS_BY_OWNER",
        {
            "PostToolUse/early_owner.py": ("early_companion.py",),
            "PreToolUse/late_owner.py": ("late_companion.py",),
        },
    )

    _write_settings(
        tmp_path / "settings.json",
        {
            "PostToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u .claude/hooks/PostToolUse/"
                                "early_owner.py"
                            ),
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u .claude/hooks/PreToolUse/late_owner.py"
                            ),
                        }
                    ]
                }
            ],
        },
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "declared runtime companion is missing" in captured.err
    assert "late_companion.py" in captured.err
    assert not (tmp_path / "out" / "hooks.json").exists()
    assert not (tmp_path / "out" / "PostToolUse" / "early_owner.py").exists()
    assert not (tmp_path / "out" / "PostToolUse" / "early_companion.py").exists()
    assert not (tmp_path / "out" / "PreToolUse" / "late_owner.py").exists()


def test_generator_prevalidate_skips_owner_with_empty_remap_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An ``eventRemap`` target of ``""`` must be skipped like ``_process_event``.

    Regression for a QA probe finding: ``_prevalidate_companions``
    originally checked only ``claude_event not in event_remap``, so an
    event present as a key in ``event_remap`` but mapped to an empty
    string (``eventRemap: {Empty: ""}``) was still walked, and its
    declared companion's absence aborted the run with rc=2.

    ``_process_event`` (the normal traversal) uses
    ``event_remap.get(claude_event)`` and treats ANY falsey result
    (missing key OR empty-string value) as an unknown event, routing it
    to ``_handle_unknown_event`` and never reaching ``_emit_one_hook``
    for it. Prevalidation must reach the identical conclusion for the
    identical input: skip the event, and therefore never look at its
    companion declaration. Before this fix, the probe observed rc=2
    ("declared runtime companion is missing") for a configuration where
    normal processing emits nothing for the affected event.
    """
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
    eventRemap:
      Empty: ""
    eventDrop: []
    matcherPolicy: "inline-script-shim"
    versionField: 1
""",
        encoding="utf-8",
    )
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "Empty", "owner.py", "print('should not run')\n")
    # companion.py is declared but intentionally never written to disk.
    # If prevalidation still walked this event, it would abort with rc=2.

    monkeypatch.setattr(
        generate_hooks_events,
        "_COMPANIONS_BY_OWNER",
        {"Empty/owner.py": ("companion.py",)},
    )

    _write_settings(
        tmp_path / "settings.json",
        {
            "Empty": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/Empty/owner.py",
                        }
                    ]
                }
            ]
        },
    )

    rc, result = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 0
    assert "declared runtime companion is missing" not in captured.err
    assert result.dropped == 1
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert out["hooks"] == {}
    assert not (tmp_path / "out" / "Empty").exists()


def test_generator_emits_version_one_wrapper(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, result = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert out["version"] == 1
    assert "hooks" in out


@pytest.mark.parametrize("yaml_value", ["0", '""', "1.5", "true"])
def test_generator_fails_2_on_invalid_version_field(
    tmp_path: Path, yaml_value: str
) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    text = cfg.read_text(encoding="utf-8")
    cfg.write_text(
        text.replace("    versionField: 1", f"    versionField: {yaml_value}"),
        encoding="utf-8",
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 2


@pytest.mark.parametrize("dispatcher_value", ['"false"', '"true"', "0", "1", "null"])
def test_generator_fails_2_on_non_boolean_dispatcher(
    tmp_path: Path,
    dispatcher_value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    with cfg.open("a", encoding="utf-8") as handle:
        handle.write(f"    dispatcher: {dispatcher_value}\n")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "artifacts.hooks.dispatcher must be a boolean" in captured.err


def test_generator_remaps_event_names(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    assert "PreToolUse" in out["hooks"]
    assert "PostToolUse" in out["hooks"]
    assert "SessionStart" in out["hooks"]
    assert "Stop" not in out["hooks"]
    assert "SessionEnd" not in out["hooks"]
    assert "SubagentStop" in out["hooks"]


def test_generator_maps_stop_to_stop_not_session_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _write_config(
        tmp_path,
        hooks_stanza_overrides={"dispatcher": True},
    )
    _write_script(tmp_path / "hooks_src", "Stop", "stop.py")
    _write_settings(
        tmp_path / "settings.json",
        {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 -u .claude/hooks/Stop/stop.py",
                        }
                    ]
                }
            ]
        },
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    output = capsys.readouterr().out
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())

    assert rc == 0
    assert set(out["hooks"]) == {"Stop"}
    assert "ownership manifest invalid" not in output


def test_generator_multiple_permission_producers_returns_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _write_config(
        tmp_path,
        hooks_stanza_overrides={"dispatcher": True},
    )
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PermissionRequest", "first.py")
    _write_script(hooks_src, "PermissionRequest", "second.py")
    _write_settings(
        tmp_path / "settings.json",
        {
            "PermissionRequest": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u "
                                ".claude/hooks/PermissionRequest/first.py"
                            ),
                        },
                        {
                            "type": "command",
                            "command": (
                                "python3 -u "
                                ".claude/hooks/PermissionRequest/second.py"
                            ),
                        },
                    ]
                }
            ]
        },
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "requires exactly one decision producer" in captured.err
    assert not (tmp_path / "out" / "hooks.json").exists()
    assert not (tmp_path / "out" / "PermissionRequest" / "first.py").exists()
    assert not (tmp_path / "out" / "PermissionRequest" / "second.py").exists()


def test_generator_emits_subagent_stop_when_source_exists(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())

    assert rc == 0
    assert "SubagentStop" in out["hooks"]
    assert (tmp_path / "out" / "SubagentStop" / "subagent.py").is_file()


def test_generator_emits_python3_and_py3_invocation(tmp_path: Path) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "out" / "hooks.json").read_text())
    entry = out["hooks"]["PreToolUse"][0]
    assert entry["bash"].startswith("python3 -u")
    assert entry["powershell"].startswith("py -3 -u")
    assert entry["cwd"] == "."


@pytest.mark.parametrize("timeout_value", [0, "", 1.5, True])
def test_generator_fails_2_on_invalid_timeout(
    tmp_path: Path, timeout_value: object
) -> None:
    cfg, _ = _setup_full_fixture(tmp_path)
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = timeout_value
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 2


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


def test_generator_protected_hooks_config_freezes_artifact_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _setup_dispatcher_matcher_fixture(tmp_path, "Bash(git status*)")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0
    output_root = tmp_path / "out"
    hooks_json = output_root / "hooks.json"
    hooks_json.with_suffix(".json.noregen").write_text(
        "preserve generated hook artifact set\n",
        encoding="utf-8",
    )
    before = {
        path.relative_to(output_root): path.read_bytes()
        for path in output_root.rglob("*")
        if path.is_file() and path != hooks_json.with_suffix(".json.noregen")
    }
    _set_dispatcher_matcher(tmp_path, "Bash(git commit*)")
    capsys.readouterr()

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    output = capsys.readouterr().out
    after = {
        path.relative_to(output_root): path.read_bytes()
        for path in output_root.rglob("*")
        if path.is_file() and path != hooks_json.with_suffix(".json.noregen")
    }

    assert rc == 0
    assert after == before
    assert "preserved generated hook artifact set" in output


def _write_dispatch_group_settings_and_manifest(
    tmp_path: Path,
    shim: dict[str, Any],
    *,
    group_overrides: dict[str, Any] | None = None,
) -> Path:
    """Register one dispatch-group hook whose sole shim carries ``shim``.

    Shared setup for the two NO-REGEN/copilotExclude-validation-ordering
    tests below: both need a `settings.json` that registers an
    `invoke_dispatch_claude.py --group g1` command and a matching
    `dispatch_groups.json` manifest so `_expand_dispatch_groups` reaches
    the shim under test. ``group_overrides`` merges into the group spec
    (e.g. ``{"surface": "plugin"}``) for tests that need to pass the
    surface check (governance item 2) to reach the metadata checks
    (items 3-4).
    """
    _write_settings(
        tmp_path / "settings.json",
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1"
                            ),
                        }
                    ],
                }
            ]
        },
    )
    hooks_src = tmp_path / "hooks_src"
    _write_script(hooks_src, "PreToolUse", "guard.py", "print('guard')\n")
    group_spec = {"event": "PreToolUse", "shims": [shim], **(group_overrides or {})}
    (hooks_src / "dispatch_groups.json").write_text(
        json.dumps({"groups": {"g1": group_spec}}),
        encoding="utf-8",
    )
    return hooks_src


def _seed_protected_hooks_json(tmp_path: Path) -> bytes:
    """Write a pre-existing, NO-REGEN-sidecar-protected ``out/hooks.json``.

    Returns the seeded bytes so the caller can assert the file is
    byte-identical after a failed generation run.
    """
    output_config = tmp_path / "out" / "hooks.json"
    output_config.parent.mkdir(parents=True, exist_ok=True)
    stale_bytes = b'{\n  "version": 1,\n  "hooks": {}\n}\n'
    output_config.write_bytes(stale_bytes)
    output_config.with_suffix(".json.noregen").write_text("preserve\n", encoding="utf-8")
    return stale_bytes


def test_generator_no_regen_hooks_config_still_rejects_malformed_copilot_exclude(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A NO-REGEN-protected hooks.json must not bypass copilotExclude validation.

    Issue #5013 review fix: ``generate_hooks`` used to check
    ``output_config``'s NO-REGEN status BEFORE calling ``_load_hook_source``
    and ``_expand_dispatch_groups``, so a malformed ``copilotExclude`` value
    on a dispatch-group shim silently returned exit 0 whenever hooks.json
    carried a NO-REGEN sentinel: the bad manifest was never even parsed.
    Source loading and dispatch-group expansion (including copilotExclude
    validation, per ``generate_hooks_expand._copilot_exclude_flag``) now run
    unconditionally, so this must return exit 2 and leave the protected
    artifact byte-identical.
    """
    cfg = _write_config(tmp_path)
    _write_dispatch_group_settings_and_manifest(
        tmp_path,
        {
            "file": "guard.py",
            # Malformed: copilotExclude must be a strict boolean (ADR-085
            # Decision 7, governance item 1); a string is a config error,
            # not a truthy include/exclude.
            "copilotExclude": "true",
        },
    )
    stale_bytes = _seed_protected_hooks_json(tmp_path)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "copilotExclude" in captured.err
    assert "strict boolean" in captured.err
    assert (tmp_path / "out" / "hooks.json").read_bytes() == stale_bytes


def test_generator_no_regen_hooks_config_still_rejects_missing_exclude_governance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A NO-REGEN-protected hooks.json must not bypass exclude-governance checks.

    Same ordering bug as
    ``test_generator_no_regen_hooks_config_still_rejects_malformed_copilot_exclude``,
    exercised through the OTHER half of finding 1: a syntactically valid
    ``copilotExclude: true`` missing its required ADR-085 Decision 7
    governance metadata (``copilotExcludeIssue`` / ``copilotExcludeDecision``,
    enforced by ``generate_hooks_expand._require_copilot_exclude_governance``)
    must also fail generation instead of silently succeeding because
    hooks.json happened to be NO-REGEN protected.
    """
    cfg = _write_config(tmp_path)
    _write_dispatch_group_settings_and_manifest(
        tmp_path,
        {
            "file": "guard.py",
            "copilotExclude": True,
            "copilotExcludeIssue": "#5013",
            # copilotExcludeDecision is missing entirely.
        },
        group_overrides={"surface": "plugin"},
    )
    stale_bytes = _seed_protected_hooks_json(tmp_path)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    captured = capsys.readouterr()

    assert rc == 2
    assert "copilotExcludeDecision" in captured.err
    assert (tmp_path / "out" / "hooks.json").read_bytes() == stale_bytes


def test_generator_no_regen_hooks_config_preserves_before_event_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-existing NO-REGEN hooks.json stops the run before event processing."""
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    stale_bytes = _seed_protected_hooks_json(tmp_path)

    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("_process_event should not run for protected hooks.json")

    monkeypatch.setattr(generate_hooks_events, "_process_event", fail_if_called)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert (tmp_path / "out" / "hooks.json").read_bytes() == stale_bytes
    assert not (tmp_path / "out" / "PreToolUse").exists()


def test_generator_no_regen_hooks_config_rechecks_sidecar_created_mid_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sidecar created during generation must trigger the late recheck."""
    cfg = _setup_single_companion_fixture(tmp_path, monkeypatch)
    real_process_event = generate_hooks_events._process_event
    created_sidecar = False

    def create_sidecar_after_event(*args: Any, **kwargs: Any) -> Any:
        nonlocal created_sidecar
        emitted = real_process_event(*args, **kwargs)
        if not created_sidecar:
            created_sidecar = True
            output_config = tmp_path / "out" / "hooks.json"
            output_config.with_suffix(".json.noregen").write_text(
                "preserve\n", encoding="utf-8"
            )
        return emitted

    monkeypatch.setattr(generate_hooks_events, "_process_event", create_sidecar_after_event)

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc == 0
    assert (tmp_path / "out" / "hooks.json.noregen").is_file()
    assert not (tmp_path / "out" / "hooks.json").exists()
    event_dir = tmp_path / "out" / "PreToolUse"
    if event_dir.exists():
        assert not any(event_dir.iterdir())


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
    # Each carries a different matcher in its shim header. The matcher is
    # repr-bound in the header comment (CWE-94 hardening), so it appears
    # single-quoted.
    assert (
        "Matcher: 'Bash(git commit*)'" in body0
    ) != ("Matcher: 'Bash(git commit*)'" in body1)
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
    """Every matcher in the live plugin manifest classifies cleanly."""
    settings = REPO_ROOT / ".claude" / "hooks" / "hooks.json"
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
    # Unit tests cover every class. The live corpus only needs one valid matcher.
    assert seen_kinds


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


def test_main_epilogue_fail_closed_wrapper_preserves_exit_two() -> None:
    """Generated shims preserve source fail-closed wrappers."""
    body = (
        "#!/usr/bin/env python3\n"
        "import sys\n\n"
        "def main() -> int:\n"
        "    raise RuntimeError('boom')\n\n"
        'if __name__ == "__main__":\n'
        "    try:\n"
        "        main()\n"
        "    except Exception as exc:\n"
        "        print(f'error: {exc}', file=sys.stderr)\n"
        "        sys.exit(2)\n"
    )
    out = generate_hooks.inject_shim(body, "Edit")
    wrapped = out.split("def _original_main")[1].split("_shim_dispatch")[0]
    assert "(fail-closed)" in wrapped
    assert "        return 2\n" in wrapped
    proc = _run_shim(out, {"tool_name": "Edit"})
    assert proc.returncode == 2
    assert "fail-closed" in proc.stderr
    assert "boom" in proc.stderr


def test_main_epilogue_unrelated_exit_two_handler_is_not_fail_closed() -> None:
    """Unrelated ``sys.exit(2)`` handlers do not mark ``main()`` fail-closed."""
    body = (
        "#!/usr/bin/env python3\n"
        "import sys\n\n"
        "def parse_args() -> None:\n"
        "    raise ValueError('bad args')\n\n"
        "def main() -> int:\n"
        "    return 0\n\n"
        'if __name__ == "__main__":\n'
        "    try:\n"
        "        main()\n"
        "    finally:\n"
        "        pass\n"
        "    try:\n"
        "        parse_args()\n"
        "    except Exception:\n"
        "        sys.exit(2)\n"
    )
    out = generate_hooks.inject_shim(body, "Edit")
    wrapped = out.split("def _original_main")[1].split("_shim_dispatch")[0]
    assert "(fail-closed)" not in wrapped
    assert "    return main()\n" in wrapped
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
    non-zero exit and breaks a hook's fail-open contract.
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


def test_fail_open_source_shim_allows_malformed_input() -> None:
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
    transformed = generate_hooks.inject_shim(body, "Task")

    proc = _run_shim_raw(transformed, b"not json")

    assert proc.returncode == 0
    assert b"malformed JSON" in proc.stderr


def test_system_exit_fail_open_source_shim_allows_malformed_input() -> None:
    body = (
        "#!/usr/bin/env python3\n\n"
        "def main() -> int:\n"
        "    return 0\n\n"
        'if __name__ == "__main__":\n'
        "    try:\n"
        "        raise SystemExit(main())\n"
        "    except SystemExit:\n"
        "        raise\n"
        "    except Exception as err:\n"
        "        raise SystemExit(0) from err\n"
    )
    transformed = generate_hooks.inject_shim(body, "Task")

    proc = _run_shim_raw(transformed, b"not json")

    assert proc.returncode == 0
    assert b"malformed JSON" in proc.stderr
