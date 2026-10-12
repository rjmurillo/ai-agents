#!/usr/bin/env python3
"""Pin the native Bash output ceiling in the rendered settings (issue #5851).

`bashOutputMaxChars` is a Claude Code setting, not a hook. It sizes how many
characters of a successful Bash call the model receives inline. Past the
ceiling Claude Code saves the result to a file and returns a path plus a short
preview. Docs: https://code.claude.com/docs/en/settings-reference.md (key
clamped to 4000-128000, default 30000, top level only) and
https://code.claude.com/docs/en/env-vars.md (the setting overrides
`BASH_MAX_OUTPUT_LENGTH`).

The value and its measurement live in
`.project-toolkit/analysis/5851-harness-output-containment-inventory.md`.
ADR-097 forbids a per-call hook for this, so a regression to the default
would otherwise go unnoticed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERED = REPO_ROOT / ".claude" / "settings.json"
TEMPLATE = REPO_ROOT / "templates" / "hooks" / "settings.tmpl"

KEY = "bashOutputMaxChars"
CHOSEN = 15000
DOC_MIN = 4000
DOC_MAX = 128000
DOC_DEFAULT = 30000


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", [RENDERED, TEMPLATE], ids=["rendered", "template"])
def test_positive_ceiling_is_the_measured_value(path: Path) -> None:
    assert _load(path)[KEY] == CHOSEN


@pytest.mark.parametrize("path", [RENDERED, TEMPLATE], ids=["rendered", "template"])
def test_positive_ceiling_is_a_top_level_integer_inside_the_documented_clamp(
    path: Path,
) -> None:
    value = _load(path)[KEY]
    assert isinstance(value, int) and not isinstance(value, bool)
    assert DOC_MIN <= value <= DOC_MAX


@pytest.mark.parametrize("path", [RENDERED, TEMPLATE], ids=["rendered", "template"])
def test_positive_ceiling_is_below_the_default_so_it_cuts_something(path: Path) -> None:
    assert _load(path)[KEY] < DOC_DEFAULT


@pytest.mark.parametrize("path", [RENDERED, TEMPLATE], ids=["rendered", "template"])
def test_negative_ceiling_is_not_set_through_env(path: Path) -> None:
    """`env` takes `BASH_MAX_OUTPUT_LENGTH`, which the setting overrides."""
    env = _load(path).get("env", {})
    assert "BASH_MAX_OUTPUT_LENGTH" not in env
    assert KEY not in env


def test_negative_rendered_matches_template() -> None:
    assert _load(RENDERED)[KEY] == _load(TEMPLATE)[KEY]
