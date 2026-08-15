#!/usr/bin/env python3
# taste-lint: ignore file-size - This contract suite keeps the manifest
# fixtures, omission matrix, and live-corpus checks together so one file
# still shows the full expansion contract.
"""Tests for the generator's dispatch-group expansion (#3075).

The Copilot tree must be generated from the PER-HOOK view, not the
consolidated dispatcher registrations, so `_expand_dispatch_groups` has to
reproduce the pre-consolidation command/timeout/statusMessage entries
exactly. These tests exercise the expansion against both fixtures and the
real committed settings + manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPTS = str(REPO_ROOT / "build" / "scripts")
if BUILD_SCRIPTS not in sys.path:
    sys.path.insert(0, BUILD_SCRIPTS)

from generate_hooks_events import (  # noqa: E402
    GenerateHooksError,
    _expand_dispatch_groups,
)

HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def _fixture_manifest(tmp_path: Path, groups: dict) -> Path:
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "dispatch_groups.json").write_text(
        json.dumps({"groups": groups}), encoding="utf-8"
    )
    return hooks_dir


def test_expands_dispatcher_registration_to_member_hooks(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {
            "g1": {
                "event": "PreToolUse",
                "mode": "gate",
                "matcher": "Bash",
                "shims": [
                    {"file": "a.py", "timeout": 5, "statusMessage": "A"},
                    {"file": "Sub/b.py"},
                ],
            }
        },
    )
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                        "timeout": 60,
                    }
                ],
            }
        ]
    }
    out = _expand_dispatch_groups(hooks_map, hooks_dir)
    groups = out["PreToolUse"]
    assert len(groups) == 1
    assert groups[0]["matcher"] == "Bash"
    assert groups[0]["hooks"] == [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/a.py",
            "timeout": 5,
            "statusMessage": "A",
        },
        {"type": "command", "command": "python3 -u .claude/hooks/Sub/b.py"},
    ]


def test_copilot_matcher_override_splits_partitions(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {
            "g1": {
                "event": "PreToolUse",
                "mode": "gate",
                "matcher": "^(Write|Edit)$",
                "shims": [
                    {"file": "a.py"},
                    {"file": "b.py", "copilotMatcher": "^(Edit|Write)$"},
                ],
            }
        },
    )
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "^(Write|Edit)$",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                    }
                ],
            }
        ]
    }
    out = _expand_dispatch_groups(hooks_map, hooks_dir)
    matchers = [g["matcher"] for g in out["PreToolUse"]]
    assert matchers == ["^(Write|Edit)$", "^(Edit|Write)$"]


def _copilot_exclude_fixture(tmp_path: Path, middle_shim: dict) -> Path:
    """Return a hooks dir for one dispatcher group of three shims: a, middle, c.

    The group declares ``surface: plugin`` unconditionally: every existing
    production group that ever sets ``copilotExclude`` does too (the only
    group without a ``surface`` key, ``sessionstart-1-context_loader``, never
    sets the flag), and the surface-rejection tests below build their own
    fixtures with a non-plugin (or absent) surface instead of reusing this
    one.
    """
    return _fixture_manifest(
        tmp_path,
        {
            "g1": {
                "event": "PreToolUse",
                "mode": "gate",
                "matcher": "Bash",
                "surface": "plugin",
                "shims": [
                    {"file": "a.py"},
                    middle_shim,
                    {"file": "c.py"},
                ],
            }
        },
    )


_ONE_GROUP_DISPATCHER_HOOKS_MAP = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                }
            ],
        }
    ]
}

# The two non-empty string metadata fields required whenever copilotExclude
# is literally true (ADR-085 Decision 7, generic field governance items 3-4).
_VALID_EXCLUDE_METADATA = {
    "copilotExcludeIssue": "#5013",
    "copilotExcludeDecision": "ADR-085",
}


@pytest.mark.parametrize(
    ("middle_shim", "expect_present"),
    [
        pytest.param(
            {"file": "b.py", "copilotExclude": True, **_VALID_EXCLUDE_METADATA},
            False,
            id="true-omits",
        ),
        pytest.param({"file": "b.py", "copilotExclude": False}, True, id="false-does-not-omit"),
        pytest.param({"file": "b.py"}, True, id="absent-does-not-omit"),
    ],
)
def test_copilot_exclude_controls_shim_omission(tmp_path, middle_shim, expect_present):
    """``copilotExclude: true`` omits a shim from Copilot expansion; ``false``
    or an absent key does not (issue #5013).

    Behavior verified: for a three-shim dispatcher group, the middle shim's
    ``b.py`` command is present in the expanded Copilot hooks exactly when
    ``copilotExclude`` is not literally ``True``. ``a.py`` and ``c.py`` are
    unaffected by ``b.py``'s value either way, so a regression that widens
    the omission to neighbors (rather than the flagged shim alone) fails
    here too. The ``false`` and ``absent`` cases carry no
    ``copilotExcludeIssue``/``copilotExcludeDecision`` metadata at all,
    proving that metadata requirement is scoped to ``copilotExclude: true``
    and never demanded of an inactive or absent flag.
    """
    hooks_dir = _copilot_exclude_fixture(tmp_path, middle_shim)

    out = _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)

    commands = [
        hook["command"] for group in out["PreToolUse"] for hook in group["hooks"]
    ]
    assert any("b.py" in command for command in commands) == expect_present
    assert any("a.py" in command for command in commands)
    assert any("c.py" in command for command in commands)


def test_copilot_exclude_shim_does_not_fragment_matcher_partitions(tmp_path):
    """An excluded shim must not split its neighbors into extra partitions.

    Behavior verified: ``b.py`` sits between ``a.py`` and ``c.py`` and is
    ``copilotExclude`` with a DIFFERENT ``copilotMatcher`` from the group's
    registration matcher. If the generator read that matcher before skipping
    the shim, ``a.py`` and ``c.py`` would land in two separate partitions
    (with an empty one for ``b.py`` in between). Skipping ``b.py`` before any
    matcher or partition logic runs keeps ``a.py`` and ``c.py`` in ONE
    partition, in their original order, exactly as if ``b.py`` had never been
    in the manifest.
    """
    hooks_dir = _copilot_exclude_fixture(
        tmp_path,
        {
            "file": "b.py",
            "copilotExclude": True,
            "copilotMatcher": "^(Agent|Task)$",
            **_VALID_EXCLUDE_METADATA,
        },
    )

    out = _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)

    groups = out["PreToolUse"]
    assert len(groups) == 1, f"expected one surviving partition, got: {groups}"
    assert groups[0]["matcher"] == "Bash"
    assert [hook["command"] for hook in groups[0]["hooks"]] == [
        "python3 -u .claude/hooks/a.py",
        "python3 -u .claude/hooks/c.py",
    ]


def test_non_object_shim_entry_raises(tmp_path):
    """A shim entry that is not a JSON object must fail closed, not be skipped.

    ``copilotExclude`` is read with ``shim.get(...)``, so a malformed
    manifest whose shim is a bare string (or any other non-dict) must raise
    before that lookup runs, not be silently treated as excluded or as an
    ordinary shim.
    """
    hooks_dir = _fixture_manifest(
        tmp_path,
        {
            "g1": {
                "event": "PreToolUse",
                "mode": "gate",
                "matcher": "Bash",
                "shims": ["not-a-dict"],
            }
        },
    )

    with pytest.raises(GenerateHooksError, match="non-object shim entry"):
        _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)


def _plugin_group_fixture(
    tmp_path: Path,
    shim: dict,
    *,
    surface: object = "plugin",
    sibling_shims: tuple[dict, ...] = (),
) -> Path:
    """Return a hooks dir for one PreToolUse dispatcher group containing ``shim``.

    ``surface`` defaults to the only value the generator accepts for
    exclusion (``"plugin"``); the surface-rejection tests below override it
    to prove the OTHER value is rejected. Passing ``surface=None`` omits the
    key entirely, matching a real group (like ``sessionstart-1-
    context_loader``) that never declares one. ``sibling_shims`` are
    ordinary, never-excluded shims placed alongside ``shim`` so a caller can
    prove an excluded shim's neighbors are unaffected.
    """
    group_spec: dict[str, Any] = {
        "event": "PreToolUse",
        "mode": "gate",
        "matcher": "Bash",
        "shims": [*sibling_shims, shim],
    }
    if surface is not None:
        group_spec["surface"] = surface
    return _fixture_manifest(tmp_path, {"g1": group_spec})


@pytest.mark.parametrize(
    "raw_value",
    ["true", 1, 0, -1, None, [], {}],
    ids=["string", "int-one", "int-zero", "negative-int", "null", "list", "object"],
)
def test_copilot_exclude_rejects_non_boolean_types(tmp_path, raw_value):
    """``copilotExclude`` must be a strict boolean (issue #5013).

    ADR-085 Decision 7, generic field governance item 1, requires the
    generator to reject "any ``copilotExclude`` value that is not literally
    ``true`` or ``false``". Python's ``bool`` is an ``int`` subclass, so a
    naive ``if value:`` truthiness check would silently accept ``1`` as
    excluded and ``0``/``-1`` as not excluded; this proves every one of a
    string, an int (truthy OR falsy), ``null``, a list, and an object raises
    ``GenerateHooksError`` instead of being coerced.
    """
    hooks_dir = _plugin_group_fixture(
        tmp_path,
        {"file": "b.py", "copilotExclude": raw_value, **_VALID_EXCLUDE_METADATA},
    )

    with pytest.raises(GenerateHooksError, match="copilotExclude"):
        _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"copilotExcludeIssue": "#5013"},
        {"copilotExcludeDecision": "ADR-085"},
        {"copilotExcludeIssue": "", "copilotExcludeDecision": "ADR-085"},
        {"copilotExcludeIssue": "#5013", "copilotExcludeDecision": "   "},
        {"copilotExcludeIssue": 5013, "copilotExcludeDecision": "ADR-085"},
        {"copilotExcludeIssue": "#5013", "copilotExcludeDecision": None},
    ],
    ids=[
        "both-missing",
        "decision-missing",
        "issue-missing",
        "issue-empty-string",
        "decision-whitespace-only",
        "issue-non-string",
        "decision-null",
    ],
)
def test_copilot_exclude_true_requires_issue_and_decision_metadata(tmp_path, metadata):
    """``copilotExclude: true`` requires non-empty issue+decision metadata.

    ADR-085 Decision 7, generic field governance items 3-4, require the
    record to name the authorizing issue and the owning ADR. This proves
    the generator enforces it at generation time: a missing, empty,
    whitespace-only, non-string, or null value for either
    ``copilotExcludeIssue`` or ``copilotExcludeDecision`` fails generation.
    """
    hooks_dir = _plugin_group_fixture(
        tmp_path,
        {"file": "b.py", "copilotExclude": True, **metadata},
    )

    with pytest.raises(GenerateHooksError, match="copilotExclude"):
        _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)


@pytest.mark.parametrize(
    "metadata",
    [
        {"copilotExcludeIssue": "none", "copilotExcludeDecision": "ADR-085"},
        {"copilotExcludeIssue": "5013", "copilotExcludeDecision": "ADR-085"},
        {"copilotExcludeIssue": "#5013", "copilotExcludeDecision": "temporary"},
        {"copilotExcludeIssue": "#5013", "copilotExcludeDecision": "adr-085"},
    ],
    ids=[
        "issue-word",
        "issue-missing-hash",
        "decision-word",
        "decision-lowercase",
    ],
)
def test_copilot_exclude_true_requires_traceable_issue_and_decision_formats(
    tmp_path, metadata
):
    """``copilotExclude`` metadata must use traceable issue and ADR formats.

    ADR-085 Decision 7, generic field governance items 3-4, require these
    fields to name the authorizing issue and the owning ADR. A non-empty
    placeholder such as ``none`` or ``temporary`` still fails because it is
    not a traceable ``#<issue>`` or ``ADR-<decision>`` reference.
    """
    hooks_dir = _plugin_group_fixture(
        tmp_path,
        {"file": "b.py", "copilotExclude": True, **metadata},
    )

    with pytest.raises(GenerateHooksError, match="traceable reference"):
        _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)


@pytest.mark.parametrize(
    "surface",
    [None, "repo", "vendored", "plugin "],
    ids=["absent", "repo", "vendored", "plugin-with-trailing-space"],
)
def test_copilot_exclude_requires_plugin_surface(tmp_path, surface):
    """``copilotExclude: true`` is only allowed on a ``surface: plugin`` group.

    ADR-085 Decision 7, generic field governance item 2, requires the
    record to name which generated surface loses the shim. A dispatch group
    that is not part of the Copilot plugin surface has no Copilot
    generation path to exclude a shim from, so setting the flag there is a
    manifest authoring error. ``"plugin "`` (trailing space) proves this is
    an exact string match, not a stripped or case-insensitive one.
    """
    hooks_dir = _plugin_group_fixture(
        tmp_path,
        {"file": "b.py", "copilotExclude": True, **_VALID_EXCLUDE_METADATA},
        surface=surface,
    )

    with pytest.raises(GenerateHooksError, match="surface"):
        _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)


def test_copilot_exclude_accepts_valid_plugin_shim_end_to_end(tmp_path):
    """The positive control: a fully valid exclusion is accepted and omitted.

    Strict boolean, both metadata fields, and ``surface: plugin`` all
    satisfied together must NOT raise, and the shim must still be omitted
    from the expanded Copilot hooks while its sibling ``a.py`` survives --
    proving the three new governance checks are gates in front of the
    existing omission, not a replacement for it.
    """
    hooks_dir = _plugin_group_fixture(
        tmp_path,
        {"file": "b.py", "copilotExclude": True, **_VALID_EXCLUDE_METADATA},
        sibling_shims=({"file": "a.py"},),
    )

    out = _expand_dispatch_groups(_ONE_GROUP_DISPATCHER_HOOKS_MAP, hooks_dir)

    commands = [hook["command"] for group in out.get("PreToolUse", []) for hook in group["hooks"]]
    assert not any("b.py" in command for command in commands)
    assert any("a.py" in command for command in commands)


def test_non_dispatcher_groups_pass_through_unchanged(tmp_path):
    hooks_dir = _fixture_manifest(tmp_path, {})
    original = {
        "PreToolUse": [
            {
                "matcher": "Grep",
                "hooks": [
                    {"type": "command", "command": "python3 -u .claude/hooks/x.py"}
                ],
            }
        ]
    }
    out = _expand_dispatch_groups(original, hooks_dir)
    assert out == original


def test_unknown_group_raises(tmp_path):
    hooks_dir = _fixture_manifest(tmp_path, {})
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "python3 -u .claude/hooks/invoke_dispatch_claude.py "
                            "--group nope"
                        ),
                    }
                ],
            }
        ]
    }
    with pytest.raises(GenerateHooksError):
        _expand_dispatch_groups(hooks_map, hooks_dir)


def test_event_mismatch_raises(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {"g1": {"event": "Stop", "mode": "gate_all", "matcher": None, "shims": []}},
    )
    hooks_map = {
        "PreToolUse": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                    }
                ]
            }
        ]
    }
    with pytest.raises(GenerateHooksError):
        _expand_dispatch_groups(hooks_map, hooks_dir)


def test_dispatcher_mixed_with_sibling_hook_raises(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {"g1": {"event": "PreToolUse", "mode": "gate", "matcher": "Bash", "shims": []}},
    )
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                    },
                    {"type": "command", "command": "python3 -u .claude/hooks/other.py"},
                ],
            }
        ]
    }
    with pytest.raises(GenerateHooksError):
        _expand_dispatch_groups(hooks_map, hooks_dir)


def test_real_settings_expand_cleanly_with_no_dispatcher_residue():
    settings = json.loads(
        (REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    out = _expand_dispatch_groups(settings["hooks"], HOOKS_DIR)
    commands = [
        hook.get("command", "")
        for groups in out.values()
        for group in groups
        if isinstance(group, dict)
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    ]
    assert commands, "expansion must not empty the hook map"
    assert not any("invoke_dispatch_claude.py" in cmd for cmd in commands)
