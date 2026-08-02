"""Tests for build/scripts/validate_plugin_version_bump.py.

The gate is inverted per ADR-092: a packaged plugin manifest must NOT carry a
``version`` field, because its presence pins Claude Code freshness to that
string (resolution step 1) instead of the git commit SHA (step 3) and re-creates
the merge conflict measured in issue #4080.

Covers:
- positive: manifests with no version field pass (exit 0)
- positive: the three shipped manifests pass the gate as committed
- positive: both shipped marketplace files carry no version (resolution step 2)
- negative: a version in a marketplace entry fails the CLI (exit 1), which is
  the only gate that runs on a marketplace-only change
- positive: a manifest absent at the ref is skipped
- negative: a manifest carrying a version fails (exit 1)
- negative: per-plugin isolation (one flagged, siblings clean)
- negative: a non-string or null version is still a present field
- negative: the gate reads the ref, not the working tree
- edge: malformed JSON, unreadable ref, and a missing repo root are config
  errors (exit 2)
- edge: --base and --files are accepted and do not change the verdict
- CLI: text and json output shapes, asserted through subprocess exit codes
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "build" / "scripts" / "validate_plugin_version_bump.py"

sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_plugin_version_bump as vpb  # noqa: E402

CLAUDE = ".claude/.claude-plugin/plugin.json"
SRC_CLAUDE = "src/claude/.claude-plugin/plugin.json"
COPILOT = "src/copilot-cli/.claude-plugin/plugin.json"

MARKET_CLAUDE = ".claude-plugin/marketplace.json"
MARKET_COPILOT = ".github/plugin/marketplace.json"

MARKETPLACES = (
    REPO_ROOT / MARKET_CLAUDE,
    REPO_ROOT / MARKET_COPILOT,
)


# --- fixtures ------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in an isolated temp repo: no user hooks, no signing, fixed identity."""
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            *args,
        ],
        capture_output=True,
        text=True, encoding="utf-8",
        check=True,
    )


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _manifest(name: str, version: object = ...) -> str:
    data: dict[str, object] = {"name": name, "description": "a plugin"}
    if version is not ...:
        data["version"] = version
    return json.dumps(data, indent=2) + "\n"


def _marketplace(name: str, version: object = ...) -> str:
    entry: dict[str, object] = {"name": name, "source": "./.claude"}
    if version is not ...:
        entry["version"] = version
    return json.dumps({"name": "ai-agents", "plugins": [entry]}, indent=2) + "\n"


def _make_repo(tmp_path: Path, **manifests: str | None) -> Path:
    """Build a committed repo whose manifests and marketplaces are the bodies given.

    Keys are ``claude``, ``src_claude``, ``copilot``, ``market_claude``, and
    ``market_copilot``. A value of None omits the file entirely. Unspecified
    files default to a version-free body.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")

    bodies: dict[str, str | None] = {
        CLAUDE: _manifest("project-toolkit"),
        SRC_CLAUDE: _manifest("claude-agents"),
        COPILOT: _manifest("project-toolkit"),
        MARKET_CLAUDE: _marketplace("project-toolkit"),
        MARKET_COPILOT: _marketplace("project-toolkit"),
    }
    keys = {
        "claude": CLAUDE,
        "src_claude": SRC_CLAUDE,
        "copilot": COPILOT,
        "market_claude": MARKET_CLAUDE,
        "market_copilot": MARKET_COPILOT,
    }
    for key, body in manifests.items():
        bodies[keys[key]] = body

    for rel, body in bodies.items():
        if body is not None:
            _write(repo, rel, body)
    _write(repo, "README.md", "seed\n")

    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


def _run(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo), *extra],
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
    )


# --- positive ------------------------------------------------------------


def test_version_free_manifests_pass(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = _run(repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "plugin-version-bump: OK" in result.stdout


def test_shipped_manifests_pass_as_committed() -> None:
    # The real repository at HEAD: the three manifests must carry no version.
    result = _run(REPO_ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "plugin-version-bump: OK" in result.stdout


def test_shipped_marketplaces_carry_no_version() -> None:
    # Marketplace entries are resolution step 2. A version there would re-pin
    # freshness ahead of the commit SHA even with plugin.json clean.
    for path in MARKETPLACES:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "version" not in data, f"{path} has a top-level version"
        for entry in data.get("plugins", []):
            assert "version" not in entry, (
                f"{path} entry {entry.get('name')!r} has a version; "
                "it would pin freshness ahead of the commit SHA (ADR-092)"
            )


def test_marketplace_entry_version_fails(tmp_path: Path) -> None:
    # A marketplace-only change touches no plugin source dir. The pytest
    # workflow filters on Python paths and never fires on marketplace.json, so
    # this gate is the only thing standing between the field and main.
    repo = _make_repo(tmp_path, market_claude=_marketplace("project-toolkit", "1.0.0"))

    result = _run(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "VERSION FIELD PRESENT" in result.stdout
    assert "marketplace-version-present" in result.stdout
    assert MARKET_CLAUDE in result.stdout


def test_copilot_marketplace_entry_version_fails(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, market_copilot=_marketplace("project-toolkit", "1.0.0"))

    result = _run(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert MARKET_COPILOT in result.stdout


def test_marketplace_version_is_reported_in_json(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, market_claude=_marketplace("project-toolkit", "1.0.0"))

    result = _run(repo, "--format", "json")

    payload = json.loads(result.stdout)
    assert payload["version_free"] is False
    reasons = {v["reason"] for v in payload["violations"]}
    assert reasons == {"marketplace-version-present"}


def test_absent_marketplace_is_skipped(tmp_path: Path) -> None:
    # Nothing published there; a repo without that marketplace still passes.
    repo = _make_repo(tmp_path, market_copilot=None)

    result = _run(repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_malformed_marketplace_is_a_config_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, market_claude="{not json")

    result = _run(repo)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "CONFIG ERROR" in result.stdout


def test_marketplace_without_plugins_list_is_a_config_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, market_claude='{"name": "ai-agents"}\n')

    result = _run(repo)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "no plugins list" in result.stdout


def test_absent_manifest_is_skipped(tmp_path: Path) -> None:
    # Nothing is published for that plugin, so there is nothing to pin.
    repo = _make_repo(tmp_path, src_claude=None)

    result = _run(repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "plugin-version-bump: OK" in result.stdout


# --- negative ------------------------------------------------------------


def test_version_field_fails(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, claude=_manifest("project-toolkit", "0.6.5448"))

    result = _run(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "VERSION FIELD PRESENT" in result.stdout
    assert CLAUDE in result.stdout
    assert "0.6.5448" in result.stdout


def test_only_the_offending_plugin_is_reported(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, copilot=_manifest("project-toolkit", "1.0.0"))

    result = _run(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert COPILOT in result.stdout
    assert CLAUDE not in result.stdout
    assert SRC_CLAUDE not in result.stdout


def test_non_string_version_still_fails(tmp_path: Path) -> None:
    # The host reads the key, not its type. A number is still a pinned version.
    repo = _make_repo(tmp_path, claude=_manifest("project-toolkit", 3))

    result = _run(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "VERSION FIELD PRESENT" in result.stdout


def test_null_version_still_fails(tmp_path: Path) -> None:
    # An explicit null is a present key, which is not the same as omitting it.
    repo = _make_repo(tmp_path, claude=_manifest("project-toolkit", None))

    result = _run(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "VERSION FIELD PRESENT" in result.stdout


def test_working_tree_cleanup_does_not_mask_the_committed_field(
    tmp_path: Path,
) -> None:
    # Deleting the line without committing must not flip the gate green: the
    # pushed commit is what the host resolves.
    repo = _make_repo(tmp_path, claude=_manifest("project-toolkit", "0.6.5448"))
    _write(repo, CLAUDE, _manifest("project-toolkit"))

    result = _run(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert CLAUDE in result.stdout


# --- edge: config errors -------------------------------------------------


def test_malformed_manifest_is_a_config_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, claude="{not json")

    result = _run(repo)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "CONFIG ERROR" in result.stdout


def test_non_object_manifest_is_a_config_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, claude="[]\n")

    result = _run(repo)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "not a JSON object" in result.stdout


def test_unreadable_head_ref_is_a_config_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = _run(repo, "--head", "no-such-ref")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "CONFIG ERROR" in result.stdout


def test_missing_repo_root_is_a_config_error(tmp_path: Path) -> None:
    result = _run(tmp_path / "nowhere")

    assert result.returncode == 2
    assert "repo root not found" in result.stderr


# --- edge: retained CLI flags -------------------------------------------


def test_base_and_files_are_accepted_and_do_not_change_the_verdict(
    tmp_path: Path,
) -> None:
    # Callers still pass these. The field's presence is not a function of the
    # diff, so naming an unrelated file cannot excuse a pinned version.
    repo = _make_repo(tmp_path, claude=_manifest("project-toolkit", "0.6.5448"))

    result = _run(repo, "--base", "HEAD", "--files", "README.md")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "VERSION FIELD PRESENT" in result.stdout


# --- CLI: json -----------------------------------------------------------


def test_json_reports_version_free_true(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = _run(repo, "--format", "json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["version_free"] is True
    assert payload["violations"] == []
    assert payload["config_errors"] == []


def test_json_reports_the_violation(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, src_claude=_manifest("claude-agents", "0.3.56"))

    result = _run(repo, "--format", "json")

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["version_free"] is False
    assert len(payload["violations"]) == 1
    violation = payload["violations"][0]
    assert violation["manifest"] == SRC_CLAUDE
    assert violation["reason"] == "version-present"
    assert violation["version"] == "0.3.56"


def test_json_never_reports_version_free_on_a_config_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, claude="{not json")

    result = _run(repo, "--format", "json")

    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["version_free"] is False
    assert payload["config_errors"]


# --- pure core -----------------------------------------------------------


def test_evaluate_flags_only_present_versions() -> None:
    states = {
        CLAUDE: vpb.ManifestState(exists=True, version="1.0.0"),
        SRC_CLAUDE: vpb.ManifestState(exists=True, version=None),
        COPILOT: vpb.ManifestState(exists=False, version=None),
    }

    violations, config_errors = vpb.evaluate(states)

    assert config_errors == []
    assert [v.manifest for v in violations] == [CLAUDE]
    assert violations[0].reason == "version-present"


def test_evaluate_reports_a_read_failure_as_a_config_error() -> None:
    states = {
        CLAUDE: vpb._RefError("git exploded"),
        SRC_CLAUDE: vpb.ManifestState(exists=True, version=None),
        COPILOT: vpb.ManifestState(exists=True, version=None),
    }

    violations, config_errors = vpb.evaluate(states)

    assert violations == []
    assert len(config_errors) == 1
    assert "git exploded" in config_errors[0]


def test_evaluate_reports_a_missing_state_as_a_config_error() -> None:
    # A caller that never read a plugin must not be reported as clean.
    violations, config_errors = vpb.evaluate({})

    assert violations == []
    assert len(config_errors) == len(vpb.PLUGINS)
