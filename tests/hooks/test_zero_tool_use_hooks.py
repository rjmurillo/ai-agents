#!/usr/bin/env python3
"""Re-accretion ratchet for ADR-097: zero tool-call hooks stay zero.

ADR-097 retired every `PreToolUse`, `PostToolUse`, `PermissionRequest`, and
`PostToolUseFailure` registration, and with them the ~20 dispatcher-hardening
tests, including the #5013 regression pin
(`test_pretooluse_bash_payload_never_launches_push_pr_guard`). That pin guarded
a wrong deny on a hot tool matcher, which once denied 127 unrelated Bash
commands over 21 minutes before the owner contained it.

Its justification was an absence of failure mode, which holds only while zero
hooks are registered. That is a STATE, not an invariant, and nothing else in the
tree notices the state changing: the anchoring gate now accepts an empty
manifest, and the installed-plugin gate treats zero events as the shipped state.
So this file is what makes the state observable. Adding a tool-use hook back
fails here, which forces the author through a deliberate test deletion and a
fresh ADR review rather than letting the surface re-accrete silently, which
ADR-084 names as the reason a written bar was needed at all.

This is not a bar on hooks generally. `SessionStart`, `UserPromptSubmit`,
`SessionEnd`, and `PreCompact` fire once per session or per turn rather than
once per tool call, and ADR-097 leaves them untouched.

If you are here because this test failed: read ADR-097's "Re-evaluation
Triggers", clear `.claude/rules/tool-use-hook-bar.md` MUST 1 through 5 for the
new hook, and rebuild the hardening-test bar ADR-097 retired. Then delete the
relevant assertion here, in the same change, with that reasoning recorded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

# ADR-097 scope, matching `.claude/rules/tool-use-hook-bar.md`: every per-call
# event. Naming fewer would leave the ratchet evadable by event choice.
PER_CALL_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "PostToolUseFailure",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("event", PER_CALL_EVENTS)
def test_plugin_manifest_registers_no_tool_use_hooks(event: str) -> None:
    """The vendored surface (`.claude/hooks/hooks.json`) carries zero."""
    hooks = _load(HOOKS_DIR / "hooks.json").get("hooks", {})

    assert hooks.get(event, []) == [], (
        f"{event} re-registered in .claude/hooks/hooks.json. ADR-097 retired "
        f"every tool-call hook from the vendored surface; re-adding one ships "
        f"a per-call process spawn to every consumer. See this file's docstring."
    )


@pytest.mark.parametrize("event", PER_CALL_EVENTS)
def test_dispatch_groups_carry_no_plugin_surface_tool_use_group(event: str) -> None:
    """No `surface: "plugin"` group targets a per-call event."""
    groups = _load(HOOKS_DIR / "dispatch_groups.json")["groups"]
    offenders = sorted(
        group_id
        for group_id, spec in groups.items()
        if spec.get("event") == event and spec.get("surface") == "plugin"
    )

    assert offenders == [], (
        f"plugin-surface {event} group(s) re-added to dispatch_groups.json: "
        f"{offenders}. See this file's docstring."
    )


@pytest.mark.parametrize("event", PER_CALL_EVENTS)
def test_repo_settings_register_no_tool_use_hooks(event: str) -> None:
    """This repository's own settings carry zero too.

    ADR-097 retired the two repo-local hooks (`observation_sync`,
    `memory_capture`) alongside the three vendored ones. They never reached a
    consumer, so re-adding one costs no vendor anything, but it does reinstate
    a per-tool-call spawn on the owner's machine, which is the measured
    Windows/Defender cost the whole decision exists to remove.
    """
    hooks = _load(REPO_ROOT / ".claude" / "settings.json")["hooks"]

    assert hooks.get(event, []) == [], (
        f"{event} re-registered in .claude/settings.json. See this file's docstring."
    )


def test_the_ratchet_examines_the_files_it_claims_to() -> None:
    """Guard the guard: a missing or renamed file must not pass vacuously.

    Every assertion above reads through `.get(...)` with a permissive default,
    so a moved manifest would make all of them pass while examining nothing.
    This is the same vacuity failure the deleted
    `test_the_customer_value_check_examines_a_nonempty_surface` existed to
    prevent, applied to its replacement.
    """
    for path in (
        HOOKS_DIR / "hooks.json",
        HOOKS_DIR / "dispatch_groups.json",
        REPO_ROOT / ".claude" / "settings.json",
    ):
        assert path.is_file(), f"ratchet input missing: {path}"

    # The manifests must still be structurally what the assertions assume.
    assert isinstance(_load(HOOKS_DIR / "hooks.json").get("hooks"), dict)
    assert isinstance(_load(HOOKS_DIR / "dispatch_groups.json").get("groups"), dict)
    assert isinstance(_load(REPO_ROOT / ".claude" / "settings.json").get("hooks"), dict)


def test_session_scoped_events_are_still_allowed() -> None:
    """Negative control: this ratchet must not read as a ban on all hooks.

    Without this, a future contributor could satisfy the file by deleting the
    session-scoped hooks too, which ADR-097 explicitly leaves in place. It also
    proves the assertions above are reading a real, populated settings file
    rather than an empty one.
    """
    hooks = _load(REPO_ROOT / ".claude" / "settings.json")["hooks"]
    session_scoped = [event for event in hooks if event not in PER_CALL_EVENTS]

    assert session_scoped, (
        "no session-scoped hooks registered at all. ADR-097 retired the "
        "per-call events only; SessionStart, UserPromptSubmit, SessionEnd, and "
        "PreCompact were explicitly left in place."
    )
