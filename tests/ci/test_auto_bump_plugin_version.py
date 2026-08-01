"""Tests for scripts/ci/auto_bump_plugin_version.py (ADR-091 post-merge bot).

Test structure
--------------
- Unit tests for pure helpers: ``_bump_patch``, ``_has_non_manifest_plugin_changes``,
  ``_read_version``, ``_write_version``.
- Integration tests for ``main()`` at the CLI boundary (exit-code level per issue #4068).
- Acceptance criterion: two PRs touching disjoint files both pass the gate without
  either author editing a version field (isolating negative control).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.ci.auto_bump_plugin_version as abv

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_V1 = ".claude/.claude-plugin/plugin.json"
_V2 = "src/copilot-cli/.claude-plugin/plugin.json"


def _make_manifest(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "test", "version": version}) + "\n", encoding="utf-8")


def _read_json_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["version"]


# ---------------------------------------------------------------------------
# _bump_patch
# ---------------------------------------------------------------------------


def test_bump_patch_increments_patch():
    assert abv._bump_patch("0.6.5446") == "0.6.5447"


def test_bump_patch_handles_zero():
    assert abv._bump_patch("1.0.0") == "1.0.1"


def test_bump_patch_strips_prerelease():
    assert abv._bump_patch("0.6.5446-rc1") == "0.6.5447"


def test_bump_patch_returns_none_on_malformed():
    assert abv._bump_patch("not-a-version") is None


def test_bump_patch_returns_none_on_two_part():
    assert abv._bump_patch("1.0") is None


# ---------------------------------------------------------------------------
# _has_non_manifest_plugin_changes
# ---------------------------------------------------------------------------


def test_has_non_manifest_returns_false_for_manifest_only():
    changed = [_V1, _V2]
    assert abv._has_non_manifest_plugin_changes(changed) is False


def test_has_non_manifest_returns_true_for_skill_change():
    changed = [".claude/skills/foo/SKILL.md", _V1]
    assert abv._has_non_manifest_plugin_changes(changed) is True


def test_has_non_manifest_returns_true_for_copilot_source():
    changed = ["src/copilot-cli/instructions/foo.instructions.md"]
    assert abv._has_non_manifest_plugin_changes(changed) is True


def test_has_non_manifest_returns_false_for_unrelated_files():
    changed = ["tests/ci/test_foo.py", "docs/README.md", "src/claude/agents/x.md"]
    assert abv._has_non_manifest_plugin_changes(changed) is False


def test_has_non_manifest_returns_false_for_empty_list():
    assert abv._has_non_manifest_plugin_changes([]) is False


# ---------------------------------------------------------------------------
# _read_version / _write_version
# ---------------------------------------------------------------------------


def test_read_version_parses_correctly(tmp_path: Path):
    path = tmp_path / "plugin.json"
    _make_manifest(path, "0.6.5446")
    assert abv._read_version(path) == "0.6.5446"


def test_read_version_returns_none_for_missing_file(tmp_path: Path):
    assert abv._read_version(tmp_path / "no-such.json") is None


def test_read_version_returns_none_for_missing_field(tmp_path: Path):
    path = tmp_path / "plugin.json"
    path.write_text(json.dumps({"name": "foo"}), encoding="utf-8")
    assert abv._read_version(path) is None


def test_write_version_updates_field(tmp_path: Path):
    path = tmp_path / "plugin.json"
    _make_manifest(path, "0.6.5446")
    assert abv._write_version(path, "0.6.5447") is True
    assert _read_json_version(path) == "0.6.5447"


def test_write_version_returns_false_for_missing_file(tmp_path: Path):
    assert abv._write_version(tmp_path / "no-such.json", "1.0.0") is False


# ---------------------------------------------------------------------------
# main() - isolating negative control
# ---------------------------------------------------------------------------


def test_main_isolating_negative_control_nothing_to_bump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Scanner must NOT bump when only non-parity files changed.

    If this passes WITHOUT the source-change check, the bump gate is unwired.
    """
    _make_manifest(tmp_path / _V1, "0.6.5446")
    _make_manifest(tmp_path / _V2, "0.6.5446")

    monkeypatch.setenv("PUSH_BEFORE_SHA", "aaa")
    monkeypatch.setenv("PUSH_AFTER_SHA", "bbb")

    # Simulate: only unrelated files changed.
    def _fake_git_diff(before: str, after: str, repo_root: Path) -> list[str]:
        return ["tests/ci/test_foo.py", "docs/README.md"]

    monkeypatch.setattr(abv, "_git_diff_files", _fake_git_diff)

    rc = abv.main(["--repo-root", str(tmp_path)])
    assert rc == 0
    # Versions must be unchanged: the scanner did not bump.
    assert _read_json_version(tmp_path / _V1) == "0.6.5446"
    assert _read_json_version(tmp_path / _V2) == "0.6.5446"


# ---------------------------------------------------------------------------
# main() - positive path
# ---------------------------------------------------------------------------


def test_main_bumps_both_manifests_on_plugin_source_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _make_manifest(tmp_path / _V1, "0.6.5446")
    _make_manifest(tmp_path / _V2, "0.6.5446")

    monkeypatch.setenv("PUSH_BEFORE_SHA", "aaa")
    monkeypatch.setenv("PUSH_AFTER_SHA", "bbb")

    def _fake_git_diff(before: str, after: str, repo_root: Path) -> list[str]:
        return [".claude/skills/foo/SKILL.md"]

    monkeypatch.setattr(abv, "_git_diff_files", _fake_git_diff)

    rc = abv.main(["--repo-root", str(tmp_path)])
    assert rc == 0
    assert _read_json_version(tmp_path / _V1) == "0.6.5447"
    assert _read_json_version(tmp_path / _V2) == "0.6.5447"


def test_main_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _make_manifest(tmp_path / _V1, "0.6.5446")
    _make_manifest(tmp_path / _V2, "0.6.5446")

    monkeypatch.setenv("PUSH_BEFORE_SHA", "aaa")
    monkeypatch.setenv("PUSH_AFTER_SHA", "bbb")

    def _fake_git_diff(before: str, after: str, repo_root: Path) -> list[str]:
        return [".claude/skills/bar/SKILL.md"]

    monkeypatch.setattr(abv, "_git_diff_files", _fake_git_diff)

    rc = abv.main(["--dry-run", "--repo-root", str(tmp_path)])
    assert rc == 0
    # Dry run must not write.
    assert _read_json_version(tmp_path / _V1) == "0.6.5446"
    assert _read_json_version(tmp_path / _V2) == "0.6.5446"


def test_main_returns_1_on_unreadable_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Primary manifest has no version field.
    primary = tmp_path / _V1
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text(json.dumps({"name": "no-version"}), encoding="utf-8")
    _make_manifest(tmp_path / _V2, "0.6.5446")

    monkeypatch.setenv("PUSH_BEFORE_SHA", "aaa")
    monkeypatch.setenv("PUSH_AFTER_SHA", "bbb")

    def _fake_git_diff(before: str, after: str, repo_root: Path) -> list[str]:
        return [".claude/skills/x.md"]

    monkeypatch.setattr(abv, "_git_diff_files", _fake_git_diff)

    rc = abv.main(["--repo-root", str(tmp_path)])
    assert rc == 1


def test_main_git_diff_failure_returns_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _make_manifest(tmp_path / _V1, "0.6.5446")
    _make_manifest(tmp_path / _V2, "0.6.5446")

    monkeypatch.setenv("PUSH_BEFORE_SHA", "aaa")
    monkeypatch.setenv("PUSH_AFTER_SHA", "bbb")

    monkeypatch.setattr(abv, "_git_diff_files", lambda *_a, **_kw: None)

    rc = abv.main(["--repo-root", str(tmp_path)])
    assert rc == 2


def test_main_missing_push_before_sha_env_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _make_manifest(tmp_path / _V1, "0.6.5446")
    _make_manifest(tmp_path / _V2, "0.6.5446")

    monkeypatch.delenv("PUSH_BEFORE_SHA", raising=False)
    monkeypatch.setenv("PUSH_AFTER_SHA", "bbb")

    rc = abv.main(["--repo-root", str(tmp_path)])
    assert rc == 2


# ---------------------------------------------------------------------------
# Acceptance criterion: two disjoint PRs pass the gate without touching version
# ---------------------------------------------------------------------------


def test_acceptance_two_disjoint_prs_need_no_version_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """ADR-091 acceptance criterion.

    Two PRs touching disjoint plugin source files can BOTH land without either
    author editing a version field. The post-merge bot handles the bump after
    each merge. This test exercises the bot script directly: both 'PR' pushes
    trigger a bump in isolation, and neither push requires the author to have
    pre-edited plugin.json.

    The isolating negative control is ``test_main_isolating_negative_control_*``
    above: the scanner returns 0 and makes no changes when only unrelated files
    changed. If that test passes before the source-change guard is in place,
    the acceptance criterion is vacuous.
    """
    # Simulated state of main after PR-A merges (bot bumped to 0.6.5447).
    _make_manifest(tmp_path / _V1, "0.6.5447")
    _make_manifest(tmp_path / _V2, "0.6.5447")

    # PR-B lands: touches a different skill, author did NOT touch plugin.json.
    monkeypatch.setenv("PUSH_BEFORE_SHA", "pr_b_before")
    monkeypatch.setenv("PUSH_AFTER_SHA", "pr_b_after")

    def _fake_git_diff(before: str, after: str, repo_root: Path) -> list[str]:
        # PR-B: only a skill file changed; no plugin.json in the diff.
        return [".claude/skills/pr_b_skill/SKILL.md"]

    monkeypatch.setattr(abv, "_git_diff_files", _fake_git_diff)

    rc = abv.main(["--repo-root", str(tmp_path)])
    assert rc == 0

    # Bot bumped the version; neither PR author had to edit plugin.json.
    assert _read_json_version(tmp_path / _V1) == "0.6.5448"
    assert _read_json_version(tmp_path / _V2) == "0.6.5448"
