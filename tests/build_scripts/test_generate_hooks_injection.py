"""Security tests for hook-generator injection hardening.

Covers #3212 (CWE-78 shell command injection) and #3213 (CWE-22 path
traversal). The remapped event name and the script basename both flow into a
filesystem path (the on-disk target write) and a shell command string (the
emitted bash/powershell command). These tests assert that hostile values are
rejected at generation time and never reach a path or a command, with
positive, negative, and edge coverage for every guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_hooks  # noqa: E402
import generate_hooks_shim  # noqa: E402
from generate_hooks_emit import (  # noqa: E402
    GenerateHooksError,
    _build_copilot_entry,
    _relative_script_target,
    _require_within,
    _validate_event_name,
    _validate_event_target,
    _validate_matcher,
    _validate_script_name,
)

# Shell metacharacters and traversal payloads reused across the negative
# cases. The same validator guards both the command string (#3212) and the
# path join (#3213), so one hostile corpus exercises both vulnerabilities.
_HOSTILE_EVENTS = [
    "$(id)",
    "`id`",
    "Pre;rm -rf /",
    "Pre|cat /etc/passwd",
    "Pre&whoami",
    "Pre Use",
    'Pre"Use',
    "Pre'Use",
    "Pre$IFS",
    "Pre\nUse",
    "../escaped",
    "../../etc",
    "/abs/evil",
    "Pre/Use",
    "PreToolUse/..",
    "..",
    ".",
    "",
    "1Pre",
    "Pr\u00e9",
]

_HOSTILE_SCRIPTS = [
    "$(id).py",
    "`id`.py",
    "owner.py;rm -rf /",
    "owner.py|cat",
    "owner bar.py",
    "../owner.py",
    "sub/owner.py",
    "owner.txt",
    ".py",
    "owner.py\n",
    "\u00f3wner.py",
    "",
]

_VALID_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "PreCompact",
    "Notification",
    "postToolUse",
]

_VALID_SCRIPTS = [
    "invoke_security_gate.py",
    "owner.py",
    "a_b-c.d.py",
    "invoke_x__Bash_git_commit_a1b2c3.py",
    # Real generator emits these underscore-prefixed helpers; the validator
    # must not reject them (regression: leading-underscore rejection broke
    # generation of _dispatch.py and _bootstrap.py).
    "_dispatch.py",
    "_bootstrap.py",
]


# --- validator positives ---------------------------------------------------


@pytest.mark.parametrize("name", _VALID_EVENTS)
def test_validate_event_name_accepts_canonical(name: str) -> None:
    assert _validate_event_name(name) == name


@pytest.mark.parametrize("name", _VALID_SCRIPTS)
def test_validate_script_name_accepts_real_filenames(name: str) -> None:
    assert _validate_script_name(name) == name


@pytest.mark.parametrize("name", _VALID_EVENTS)
def test_validate_event_target_accepts_canonical(name: str) -> None:
    assert _validate_event_target(name) == name


def test_validate_event_target_allows_empty_drop_sentinel() -> None:
    # An empty eventRemap value means "drop this event"; it is the one
    # falsey target the loop skips before any path or command is built.
    assert _validate_event_target("") == ""


# --- validator negatives ---------------------------------------------------


@pytest.mark.parametrize("name", _HOSTILE_EVENTS)
def test_validate_event_name_rejects_hostile(name: str) -> None:
    with pytest.raises(GenerateHooksError):
        _validate_event_name(name)


@pytest.mark.parametrize("name", [n for n in _HOSTILE_EVENTS if n != ""])
def test_validate_event_target_rejects_hostile_nonempty(name: str) -> None:
    with pytest.raises(GenerateHooksError):
        _validate_event_target(name)


@pytest.mark.parametrize("name", _HOSTILE_SCRIPTS)
def test_validate_script_name_rejects_hostile(name: str) -> None:
    with pytest.raises(GenerateHooksError):
        _validate_script_name(name)


# --- CWE-78: hostile values never reach a command string ------------------


def test_build_copilot_entry_valid_renders_commands() -> None:
    entry = _build_copilot_entry("PreToolUse", "owner.py")
    assert "hooks/PreToolUse/owner.py" in entry["bash"]
    assert "hooks/PreToolUse/owner.py" in entry["powershell"]


@pytest.mark.parametrize("event", [n for n in _HOSTILE_EVENTS if n != ""])
def test_build_copilot_entry_rejects_hostile_event(event: str) -> None:
    with pytest.raises(GenerateHooksError):
        _build_copilot_entry(event, "owner.py")


@pytest.mark.parametrize("script", _HOSTILE_SCRIPTS)
def test_build_copilot_entry_rejects_hostile_script(script: str) -> None:
    with pytest.raises(GenerateHooksError):
        _build_copilot_entry("PreToolUse", script)


# --- CWE-22: write-side containment guard ---------------------------------


def test_relative_script_target_valid_stays_in_root(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    target = _relative_script_target(root, "PreToolUse", "owner.py")
    assert target == root / "PreToolUse" / "owner.py"


@pytest.mark.parametrize("event", [n for n in _HOSTILE_EVENTS if n != ""])
def test_relative_script_target_rejects_hostile_event(
    tmp_path: Path, event: str
) -> None:
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(GenerateHooksError):
        _relative_script_target(root, event, "owner.py")


def test_require_within_accepts_in_root(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    ok = root / "PreToolUse" / "owner.py"
    assert _require_within(root, ok) == ok


def test_require_within_rejects_dotdot_escape(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    escaped = root / ".." / "evil" / "owner.py"
    with pytest.raises(GenerateHooksError):
        _require_within(root, escaped)


def test_require_within_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted on this platform")
    escaped = link / "owner.py"
    with pytest.raises(GenerateHooksError):
        _require_within(root, escaped)


# --- end-to-end generation refusal ----------------------------------------


def _write_generation_fixture(tmp_path: Path, remap_value: str) -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\n'
        'provider: "test"\n'
        "artifacts:\n"
        "  hooks:\n"
        '    settingsSource: "settings.json"\n'
        '    scriptSource: "hooks_src"\n'
        '    outputConfig: "out/hooks.json"\n'
        '    outputScripts: "out"\n'
        "    eventRemap:\n"
        f"      PreToolUse: {json.dumps(remap_value)}\n"
        "    eventDrop: []\n"
        '    matcherPolicy: "inline-script-shim"\n'
        "    versionField: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "settings.json").write_text(
        json.dumps({"hooks": {}}), encoding="utf-8"
    )
    (tmp_path / "hooks_src").mkdir()
    return cfg


def test_generation_accepts_valid_remap(tmp_path: Path) -> None:
    cfg = _write_generation_fixture(tmp_path, "PreToolUse")
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0


@pytest.mark.parametrize(
    "hostile",
    [
        "../escaped",
        "../../etc",
        "/abs/evil",
        "$(touch pwned)",
        "`id`",
        "Pre;rm -rf /",
        "Pre Use",
        "PreToolUse/..",
    ],
)
def test_generation_rejects_hostile_event_remap(
    tmp_path: Path, hostile: str
) -> None:
    cfg = _write_generation_fixture(tmp_path, hostile)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 2
    # Nothing escaped outputScripts: the traversal leaf, an absolute-path
    # leaf, and the command-injection artifact must all be absent.
    assert not (tmp_path / "escaped").exists()
    assert not (tmp_path / "etc").exists()
    assert not (tmp_path / "pwned").exists()
    assert not (tmp_path / "out" / "hooks.json").exists()


# --- CWE-94: matcher control-character injection into the shim ------------
#
# The matcher (settings.json "matcher") is embedded into the generated shim
# source. A newline in the matcher, raw-interpolated into the "# Matcher:"
# header comment, would terminate the comment and inject a live top-level
# Python statement that runs on every hook invocation. The boundary rejects
# control characters; the render binds the matcher via repr() as belt and
# suspenders.


_VALID_MATCHERS = [
    "Bash(git commit*)",
    "^(Edit|Write)$",
    "Bash",
    "mcp__serena__write_memory",
    "Bash(npm test*|pytest*)",
    "Bash(git*)",
]

_CONTROL_MATCHERS = [
    "Bash(git*)\nimport os; os.system('id')",
    "a\rb",
    "a\x00b",
    "a\x1fb",
    "a\x7fb",
    "\n",
    "\t",
]


@pytest.mark.parametrize("matcher", _VALID_MATCHERS)
def test_validate_matcher_accepts_normal(matcher: str) -> None:
    assert _validate_matcher(matcher) == matcher


@pytest.mark.parametrize("matcher", _CONTROL_MATCHERS)
def test_validate_matcher_rejects_control_characters(matcher: str) -> None:
    with pytest.raises(GenerateHooksError):
        _validate_matcher(matcher)


def test_build_shim_neutralizes_matcher_newline_injection() -> None:
    payload = "Bash(git*)\nINJECTED_MATCHER_TOKEN = 1"
    src = generate_hooks_shim._build_shim(payload)
    lines = src.splitlines()
    # The injection payload never survives as its own top-level statement.
    assert not any(line.startswith("INJECTED_MATCHER_TOKEN") for line in lines)
    # repr() binding keeps the newline escaped on a single physical line for
    # both the header comment and the runtime literal.
    comment_lines = [line for line in lines if line.startswith("# Matcher:")]
    assert len(comment_lines) == 1
    assert "\\n" in comment_lines[0]
    literal_lines = [line for line in lines if line.startswith("_MATCHER =")]
    assert len(literal_lines) == 1
    assert "\\n" in literal_lines[0]


def test_build_shim_valid_matcher_renders_single_line_comment() -> None:
    src = generate_hooks_shim._build_shim("Bash(git commit*)")
    comment_lines = [
        line for line in src.splitlines() if line.startswith("# Matcher:")
    ]
    assert comment_lines == ["# Matcher: 'Bash(git commit*)'"]
