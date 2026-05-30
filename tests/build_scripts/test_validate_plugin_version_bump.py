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
    # Plain release: core tuple, is_release True, no pre-release identifiers.
    assert vpb.parse_version("0.3.1") == ((0, 3, 1), True, ())


def test_parse_version_prerelease():
    # Pre-release: is_release False; identifiers wrapped (rank, value).
    assert vpb.parse_version("1.2.3-rc1") == ((1, 2, 3), False, ((1, "rc1"),))
    # Numeric pre-release identifier ranks below alphanumeric.
    assert vpb.parse_version("1.2.3-1") == ((1, 2, 3), False, ((0, 1),))


def test_parse_version_drops_build_metadata():
    # Build metadata does not affect precedence: parses to the plain release.
    assert vpb.parse_version("1.2.3+build9") == ((1, 2, 3), True, ())
    assert vpb.parse_version("1.2.3-rc1+build9") == ((1, 2, 3), False, ((1, "rc1"),))


def test_parse_version_rejects_non_numeric():
    assert vpb.parse_version("1.x.0") is None
    assert vpb.parse_version("") is None
    assert vpb.parse_version("   ") is None


def test_parse_version_rejects_non_semver_core():
    # SemVer requires exactly three numeric core identifiers.
    assert vpb.parse_version("1") is None
    assert vpb.parse_version("1.2") is None
    assert vpb.parse_version("1.2.3.4") is None


def test_parse_version_rejects_leading_zeros():
    # Leading zeros are invalid in core and numeric pre-release identifiers.
    assert vpb.parse_version("01.2.3") is None
    assert vpb.parse_version("1.2.3-01") is None


def test_parse_version_rejects_empty_prerelease():
    assert vpb.parse_version("1.2.3-") is None
    assert vpb.parse_version("1.2.3-rc.") is None


def test_version_ordering_via_tuple():
    assert vpb.parse_version("0.3.1") > vpb.parse_version("0.3.0")
    assert vpb.parse_version("0.4.0") > vpb.parse_version("0.3.9")


def test_prerelease_precedes_release():
    # A pre-release has lower precedence than its associated release (SemVer 11).
    # Promoting 0.3.0-rc1 to 0.3.0 is therefore a strictly-greater bump.
    assert vpb.parse_version("0.3.0-rc1") < vpb.parse_version("0.3.0")
    assert vpb.parse_version("1.2.3-alpha") < vpb.parse_version("1.2.3")


def test_prerelease_identifier_ordering():
    # Numeric identifiers compare numerically and rank below alphanumerics.
    assert vpb.parse_version("1.2.3-alpha") < vpb.parse_version("1.2.3-beta")
    assert vpb.parse_version("1.2.3-alpha.1") < vpb.parse_version("1.2.3-alpha.2")
    assert vpb.parse_version("1.2.3-1") < vpb.parse_version("1.2.3-alpha")


def test_promote_prerelease_to_release_is_valid_bump():
    # Source change + promote 0.3.0-rc1 -> 0.3.0 must pass (release > prerelease).
    v, errs = vpb.evaluate(
        [".claude/skills/foo/SKILL.md"], _pairs(claude=("0.3.0-rc1", "0.3.0"))
    )
    assert v == []
    assert errs == []


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
    # Guard against normalization regressing into spurious config errors.
    assert errs == []


def test_non_semver_current_version_is_config_error():
    # A two-part version that the old parser accepted must now be rejected.
    v, errs = vpb.evaluate([".claude/x.md"], _pairs(claude=("0.3.0", "1.2")))
    assert v == []
    assert len(errs) == 1
    assert CLAUDE in errs[0]


def test_non_semver_base_version_is_config_error():
    v, errs = vpb.evaluate([".claude/x.md"], _pairs(claude=("1", "0.3.1")))
    assert v == []
    assert len(errs) == 1
    assert CLAUDE in errs[0]


def test_base_ref_error_is_config_error_not_new_plugin():
    # A git-level base read failure must not collapse into a new-plugin pass.
    err = vpb._BaseRefError("git show main:.claude/...: bad revision")
    v, errs = vpb.evaluate(
        [".claude/x.md"], {CLAUDE: (err, "0.3.0"), SRC_CLAUDE: ("0.0.0", "0.0.0"), COPILOT: ("0.0.0", "0.0.0")}
    )
    assert v == []
    assert len(errs) == 1
    assert CLAUDE in errs[0]


def test_json_bumped_false_on_config_error(monkeypatch, capsys):
    # bumped must be false when only config errors occurred (exit 2).
    monkeypatch.setattr(
        vpb, "_version_pairs", lambda *a, **k: _pairs(claude=("0.3.0", "bad"))
    )
    rc = vpb.main(["--files", ".claude/x.md", "--base", "x", "--format", "json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["bumped"] is False
    assert payload["config_errors"]


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


def test_cli_violation_outranks_config_error(monkeypatch):
    # claude has a real not-bumped violation; copilot has an unparseable
    # version (config error). The violation must win the exit code (block=1),
    # not be masked by the config error (warn=2).
    monkeypatch.setattr(
        vpb,
        "_version_pairs",
        lambda *a, **k: _pairs(claude=("0.3.0", "0.3.0"), copilot=("0.4.1", "bad")),
    )
    rc = vpb.main(
        ["--files", ".claude/x.md", "src/copilot-cli/y.md", "--base", "x"]
    )
    assert rc == 1


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


# --- Regression: divergent base must use merge-base (three-dot) -----------


def _git(repo: Path, *args: str) -> None:
    import subprocess

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _manifest(version: str) -> str:
    return json.dumps({"name": "project-toolkit", "version": version}) + "\n"


def test_divergent_base_uses_merge_base(tmp_path: Path):
    """A sibling change on the base ref after the branch point must not count.

    Reproduces the two-dot bug: ``main`` advances its own copy of a plugin
    file and bumps the version after the branch diverges. The feature branch
    bumps from the branch-point version. ``base..HEAD`` (two-dot) would pull in
    main's file and compare against main's bumped version, producing a false
    not-increased verdict. ``merge-base`` (three-dot) sees only the feature
    branch's change and passes.
    """
    repo = tmp_path
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, ".claude/.claude-plugin/plugin.json", _manifest("0.3.0"))
    _write(repo, ".claude/skills/x/SKILL.md", "# x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "base")

    _git(repo, "checkout", "-q", "-b", "feat")

    # main advances on its own side: edits x and bumps to 0.4.0 (sibling PR).
    _git(repo, "checkout", "-q", "main")
    _write(repo, ".claude/skills/x/SKILL.md", "# x edited on main\n")
    _write(repo, ".claude/.claude-plugin/plugin.json", _manifest("0.4.0"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "main advance")

    # feature branch adds y and bumps from the branch-point version (0.3.0->0.3.1).
    _git(repo, "checkout", "-q", "feat")
    _write(repo, ".claude/skills/y/SKILL.md", "# y\n")
    _write(repo, ".claude/.claude-plugin/plugin.json", _manifest("0.3.1"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "feat change + bump")

    rc = vpb.main(["--base", "main", "--repo-root", str(repo)])
    assert rc == 0  # three-dot: only feat's bump counts, 0.3.0 -> 0.3.1


def test_divergent_base_still_catches_missing_bump(tmp_path: Path):
    """The merge-base fix must not mask a real missing bump on the branch."""
    repo = tmp_path
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, ".claude/.claude-plugin/plugin.json", _manifest("0.3.0"))
    _write(repo, ".claude/skills/x/SKILL.md", "# x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "base")

    _git(repo, "checkout", "-q", "-b", "feat")
    # main advances (irrelevant to the branch's obligation).
    _git(repo, "checkout", "-q", "main")
    _write(repo, ".claude/skills/x/SKILL.md", "# edited\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "main advance")

    # feat changes a plugin file but never bumps the version.
    _git(repo, "checkout", "-q", "feat")
    _write(repo, ".claude/skills/z/SKILL.md", "# z\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "feat change no bump")

    rc = vpb.main(["--base", "main", "--repo-root", str(repo)])
    assert rc == 1  # 0.3.0 -> 0.3.0, not bumped
