"""Tests for build/scripts/validate_plugin_version_bump.py.

Covers:
- positive: source changed + strictly-greater bump passes
- positive: nothing relevant changed passes
- positive: manifest-only change (no other source file) does not require a bump
- positive: bump with no other change passes
- positive: new plugin (no version at base) passes
- negative: source changed + version unchanged fails (not-bumped)
- negative: source changed + version decreased fails (not-increased)
- negative: per-plugin isolation (one plugin flagged, siblings clean)
- edge: ``.claude`` prefix does not match ``.claude-plugin`` sibling
- edge: unparseable version is a config error
- edge: pre-release / build suffixes parse and compare
- CLI: --files mode + monkeypatched versions, text and json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_plugin_version_bump as vpb  # noqa: E402

CLAUDE = ".claude/.claude-plugin/plugin.json"
SRC_CLAUDE = "src/claude/.claude-plugin/plugin.json"
COPILOT = "src/copilot-cli/.claude-plugin/plugin.json"


def _pairs(**kw: tuple[str | None, str | None]) -> dict[str, tuple[str | None, str | None]]:
    """Build a version-pair map keyed by manifest path.

    Keys: ``claude`` -> CLAUDE, ``src_claude`` -> SRC_CLAUDE, ``copilot`` -> COPILOT.
    Unspecified manifests default to ('0.0.0', '0.0.0') so an irrelevant
    plugin never trips the check unless the test names it.
    """
    base = {
        CLAUDE: ("0.0.0", "0.0.0"),
        SRC_CLAUDE: ("0.0.0", "0.0.0"),
        COPILOT: ("0.0.0", "0.0.0"),
    }
    mapping = {"claude": CLAUDE, "src_claude": SRC_CLAUDE, "copilot": COPILOT}
    for key, val in kw.items():
        base[mapping[key]] = val
    return base


# --- parse_version -------------------------------------------------------


def test_parse_version_plain():
    assert vpb.parse_version("0.3.1") == (0, 3, 1)


def test_parse_version_drops_suffix():
    assert vpb.parse_version("1.2.3-rc1") == (1, 2, 3)
    assert vpb.parse_version("1.2.3+build9") == (1, 2, 3)


def test_parse_version_rejects_non_numeric():
    assert vpb.parse_version("1.x.0") is None
    assert vpb.parse_version("") is None
    assert vpb.parse_version("   ") is None


def test_version_ordering_via_tuple():
    assert vpb.parse_version("0.3.1") > vpb.parse_version("0.3.0")
    assert vpb.parse_version("0.4.0") > vpb.parse_version("0.3.9")


# --- evaluate: positive --------------------------------------------------


def test_source_changed_with_bump_passes():
    v, errs = vpb.evaluate(
        [".claude/skills/foo/SKILL.md"], _pairs(claude=("0.3.0", "0.3.1"))
    )
    assert v == []
    assert errs == []


def test_nothing_relevant_changed_passes():
    v, errs = vpb.evaluate(["README.md", "docs/x.md"], _pairs())
    assert v == []
    assert errs == []


def test_manifest_only_change_does_not_require_bump():
    # Only plugin.json changed (e.g. description edit), no other source file.
    v, errs = vpb.evaluate([CLAUDE], _pairs(claude=("0.3.0", "0.3.0")))
    assert v == []
    assert errs == []


def test_bump_with_no_other_change_passes():
    v, errs = vpb.evaluate([CLAUDE], _pairs(claude=("0.3.0", "0.4.0")))
    assert v == []
    assert errs == []


def test_new_plugin_no_base_version_passes():
    v, errs = vpb.evaluate(
        ["src/claude/newagent.md"], _pairs(src_claude=(None, "0.1.0"))
    )
    assert v == []
    assert errs == []


# --- evaluate: negative --------------------------------------------------


def test_source_changed_without_bump_fails():
    v, errs = vpb.evaluate(
        [".claude/skills/foo/SKILL.md"], _pairs(claude=("0.3.0", "0.3.0"))
    )
    assert errs == []
    assert len(v) == 1
    assert v[0].reason == "not-bumped"
    assert v[0].manifest == CLAUDE
    assert v[0].touched == (".claude/skills/foo/SKILL.md",)


def test_source_changed_with_decrease_fails():
    v, errs = vpb.evaluate(
        ["src/copilot-cli/skills/x/SKILL.md"], _pairs(copilot=("0.4.1", "0.4.0"))
    )
    assert errs == []
    assert len(v) == 1
    assert v[0].reason == "not-increased"
    assert v[0].manifest == COPILOT


def test_per_plugin_isolation():
    # src/claude changed without bump; .claude bumped correctly; copilot untouched.
    v, errs = vpb.evaluate(
        [".claude/agents/x.md", "src/claude/y.md"],
        _pairs(claude=("0.3.0", "0.3.1"), src_claude=("0.3.0", "0.3.0")),
    )
    assert errs == []
    assert [x.manifest for x in v] == [SRC_CLAUDE]


# --- evaluate: edge ------------------------------------------------------


def test_dot_claude_prefix_does_not_match_claude_plugin():
    # Top-level marketplace.json lives under .claude-plugin/, NOT .claude/.
    v, errs = vpb.evaluate(
        [".claude-plugin/marketplace.json"], _pairs(claude=("0.3.0", "0.3.0"))
    )
    assert v == []
    assert errs == []


def test_src_claude_not_matched_by_copilot_dir():
    v, errs = vpb.evaluate(
        ["src/copilot-cli/skills/x/SKILL.md"],
        _pairs(copilot=("0.4.1", "0.4.2"), src_claude=("0.3.0", "0.3.0")),
    )
    assert v == []
    assert errs == []


def test_unparseable_current_version_is_config_error():
    v, errs = vpb.evaluate([".claude/x.md"], _pairs(claude=("0.3.0", "garbage")))
    assert v == []
    assert len(errs) == 1
    assert CLAUDE in errs[0]


def test_missing_current_version_is_config_error():
    v, errs = vpb.evaluate([".claude/x.md"], _pairs(claude=("0.3.0", None)))
    assert v == []
    assert len(errs) == 1


def test_backslash_paths_normalized():
    v, errs = vpb.evaluate(
        [".claude\\skills\\foo\\SKILL.md"], _pairs(claude=("0.3.0", "0.3.0"))
    )
    assert len(v) == 1


# --- CLI -----------------------------------------------------------------


def test_cli_files_mode_pass(monkeypatch, capsys):
    monkeypatch.setattr(
        vpb, "_version_pairs", lambda *a, **k: _pairs(claude=("0.3.0", "0.3.1"))
    )
    rc = vpb.main(["--files", ".claude/skills/foo/SKILL.md", "--base", "x"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_files_mode_fail(monkeypatch, capsys):
    monkeypatch.setattr(
        vpb, "_version_pairs", lambda *a, **k: _pairs(claude=("0.3.0", "0.3.0"))
    )
    rc = vpb.main(["--files", ".claude/skills/foo/SKILL.md", "--base", "x"])
    assert rc == 1
    assert "NOT BUMPED" in capsys.readouterr().out


def test_cli_config_error_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(
        vpb, "_version_pairs", lambda *a, **k: _pairs(claude=("0.3.0", "bad"))
    )
    rc = vpb.main(["--files", ".claude/x.md", "--base", "x"])
    assert rc == 2
    assert "CONFIG ERROR" in capsys.readouterr().out


def test_cli_json_format(monkeypatch, capsys):
    monkeypatch.setattr(
        vpb, "_version_pairs", lambda *a, **k: _pairs(claude=("0.3.0", "0.3.0"))
    )
    rc = vpb.main(
        ["--files", ".claude/skills/foo/SKILL.md", "--base", "x", "--format", "json"]
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["bumped"] is False
    assert payload["violations"][0]["manifest"] == CLAUDE
    assert payload["violations"][0]["reason"] == "not-bumped"


def test_cli_bad_repo_root_returns_2(capsys):
    rc = vpb.main(["--files", "x", "--repo-root", "/no/such/dir/xyz"])
    assert rc == 2
    assert "repo root not found" in capsys.readouterr().err
