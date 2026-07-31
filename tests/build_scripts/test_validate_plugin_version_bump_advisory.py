"""Advisory tests for plugin version-bump validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_plugin_version_bump as vpb  # noqa: E402

CLAUDE = ".claude/.claude-plugin/plugin.json"
SRC_CLAUDE = "src/claude/.claude-plugin/plugin.json"
COPILOT = "src/copilot-cli/.claude-plugin/plugin.json"


def _pairs(**kw: tuple[str | None, str | None]) -> dict[str, tuple[str | None, str | None]]:
    base = {
        CLAUDE: ("0.0.0", "0.0.0"),
        SRC_CLAUDE: ("0.0.0", "0.0.0"),
        COPILOT: ("0.0.0", "0.0.0"),
    }
    mapping = {"claude": CLAUDE, "src_claude": SRC_CLAUDE, "copilot": COPILOT}
    for key, val in kw.items():
        base[mapping[key]] = val
    return base



def test_manifest_bump_with_scripts_change_warns():
    advisories = vpb.find_advisories(
        ["scripts/tool.py", CLAUDE, COPILOT],
        _pairs(claude=("0.3.0", "0.3.1"), copilot=("0.3.0", "0.3.1")),
    )
    assert [a.manifest for a in advisories] == [CLAUDE, COPILOT]


def test_project_toolkit_content_bump_has_no_advisory():
    advisories = vpb.find_advisories(
        [".claude/skills/foo/SKILL.md", CLAUDE, COPILOT],
        _pairs(claude=("0.3.0", "0.3.1"), copilot=("0.3.0", "0.3.1")),
    )
    assert advisories == []


def test_bump_only_release_has_no_advisory():
    advisories = vpb.find_advisories(
        [CLAUDE, SRC_CLAUDE, COPILOT],
        _pairs(
            claude=("0.3.0", "0.3.1"),
            src_claude=("0.3.0", "0.3.1"),
            copilot=("0.3.0", "0.3.1"),
        ),
    )
    assert advisories == []


def test_src_claude_content_warns_for_unrelated_manifest_bumps():
    advisories = vpb.find_advisories(
        ["src/claude/agents/foo.md", CLAUDE, SRC_CLAUDE, COPILOT],
        _pairs(
            claude=("0.3.0", "0.3.1"),
            src_claude=("0.3.0", "0.3.1"),
            copilot=("0.3.0", "0.3.1"),
        ),
    )
    assert [a.manifest for a in advisories] == [CLAUDE, COPILOT]


def test_advisory_does_not_change_cli_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        vpb,
        "_version_pairs",
        lambda *a, **k: _pairs(claude=("0.3.0", "0.3.1")),
    )
    rc = vpb.main(["--files", "scripts/tool.py", CLAUDE, "--base", "x"])
    assert rc == 0
    assert "WARNING:" in capsys.readouterr().out


def test_cli_json_includes_warning_advisory(monkeypatch, capsys):
    monkeypatch.setattr(
        vpb,
        "_version_pairs",
        lambda *a, **k: _pairs(claude=("0.3.0", "0.3.1")),
    )
    rc = vpb.main(
        ["--files", "scripts/tool.py", CLAUDE, "--base", "x", "--format", "json"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["advisories"][0]["level"] == "WARNING"
    assert payload["advisories"][0]["manifest"] == CLAUDE

