#!/usr/bin/env python3
"""End-to-end plugin-load smoke for the shipped CLI plugins (issue #2736).

PR #2735 was green on unit tests, schema checks, and generated-file checks, yet a
broken skill front-matter field (``argument-hint must be a string``) could still
reach a customer because nothing loaded the plugin in the real CLI and asserted
the skills loaded. These tests close that gap: they launch the REAL CLIs, load
the shipped plugin directory, list the plugin's skills, and assert the lifecycle
skills load.

  - Copilot: ``copilot --plugin-dir <repo>/src/copilot-cli skill list --json``
    from a neutral cwd. Assert returncode 0, no ``argument-hint`` loader warning
    in stderr, and the expected lifecycle skills load from ``source: plugin``.
  - Claude:  ``claude --plugin-dir <repo>/.claude plugin list`` and
    ``plugin details project-toolkit``. Assert returncode 0 and the manifest
    version from ``.claude/.claude-plugin/plugin.json`` appears in the output.

This is the plugin-LOAD smoke. The plugin-HOOK smoke (a hook resolves and runs
from the install tree) lives in ``tests/e2e/test_cli_hook_e2e.py``. Both run in
the same nightly workflow under ``RUN_CLI_E2E=1``; each has its own JUnit report
and its own ``assert_smoke_ran`` gate so a silent skip of either is a red run.

Why opt-in: these spawn real CLIs that need authentication and spend model
credits, which bare CI does not have. They run wherever the CLIs are installed
and ``RUN_CLI_E2E=1`` is set (local dev, the nightly job with secrets); elsewhere
they SKIP with a loud reason so a skipped run never reads as a passed run. The
fast, always-on guards are the unit checks at the bottom of this file: they pin
the expected-skills set against the shipped plugin trees with no CLI, so a
renamed or deleted lifecycle skill fails in bare CI too.

Run locally:
    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_plugin_load_smoke.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from cli_exec import resolve_executable  # noqa: E402

_RUN = os.environ.get("RUN_CLI_E2E") == "1"

# The lifecycle skills PR #2735 verified by hand. They ship in BOTH plugin trees
# (src/copilot-cli/skills/<name>/ and .claude/commands/<name>.md), so the same
# set is the load contract for both CLIs. The always-on unit checks below pin
# this set against the on-disk trees so a rename fails without a real CLI.
EXPECTED_SKILLS = frozenset({"build", "plan", "ship", "test", "review", "spec", "sync"})

_COPILOT_PLUGIN_DIR = REPO_ROOT / "src" / "copilot-cli"
_CLAUDE_PLUGIN_DIR = REPO_ROOT / ".claude"
_CLAUDE_MANIFEST = _CLAUDE_PLUGIN_DIR / ".claude-plugin" / "plugin.json"

# The skill-loader warning class issue #2736 must catch before merge. Copilot
# CLI emits this on stderr when a skill's front matter has a non-string
# argument-hint; the schema check passes but the real loader rejects it.
_ARGUMENT_HINT_WARNING = "argument-hint"

_CLI_TIMEOUT_SECONDS = 240

requires_copilot = pytest.mark.skipif(
    not (_RUN and shutil.which("copilot")),
    reason="needs RUN_CLI_E2E=1 and the copilot CLI on PATH (real auth + credits)",
)
requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)


def _clean_env() -> dict[str, str]:
    """Env for the CLI subprocess with inherited plugin-root vars stripped.

    A parent Claude session or the pre-push hook may export these; strip them so
    the CLI under test resolves the plugin from ``--plugin-dir``, not from an
    inherited root that points at a different tree.
    """
    env = os.environ.copy()
    for var in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "COPILOT_PLUGIN_ROOT"):
        env.pop(var, None)
    return env


def _plugin_skill_names(payload: object) -> set[str]:
    """Extract skill names loaded from a plugin source out of `skill list --json`.

    The Copilot CLI prints a JSON array of skill records. Each record carries a
    ``name`` and a ``source``; only ``source == "plugin"`` records prove the
    skill loaded from the plugin dir under test rather than from a built-in or a
    user-level install. A record without a recognized source is ignored, not
    counted, so a built-in ``build`` cannot mask a missing plugin ``build``.
    """
    if not isinstance(payload, list):
        return set()
    names: set[str] = set()
    for record in payload:
        if not isinstance(record, dict):
            continue
        if record.get("source") != "plugin":
            continue
        name = record.get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def _read_manifest_version(manifest_path: Path) -> str:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"manifest {manifest_path} has no string version: {data!r}")
    return version


@pytest.mark.smoke
@requires_copilot
def test_copilot_plugin_loads_expected_skills(tmp_path: Path) -> None:
    """copilot --plugin-dir loads the lifecycle skills with no loader warning.

    Asserts returncode 0, that no ``argument-hint`` loader warning appears on
    stderr (the issue #2736 failure class), and that EXPECTED_SKILLS is a subset
    of the skills the CLI loaded from ``source: plugin``.
    """
    version = subprocess.run(
        [resolve_executable("copilot"), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_clean_env(),
    )
    print(f"copilot --version: {version.stdout.strip() or version.stderr.strip()}")

    try:
        run = subprocess.run(
            [
                resolve_executable("copilot"),
                "-C",
                str(tmp_path),
                "--plugin-dir",
                str(_COPILOT_PLUGIN_DIR),
                "skill",
                "list",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT_SECONDS,
            check=False,
            env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"copilot skill list exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)")

    assert run.returncode == 0, (
        f"copilot skill list failed (rc={run.returncode}). "
        f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    )
    assert _ARGUMENT_HINT_WARNING not in run.stderr.lower(), (
        "copilot reported an argument-hint loader warning (issue #2736 failure class). "
        f"stderr={run.stderr[-600:]!r}"
    )

    try:
        payload = json.loads(run.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"copilot skill list emitted non-JSON: {exc}. stdout={run.stdout[-600:]!r}")

    loaded = _plugin_skill_names(payload)
    missing = EXPECTED_SKILLS - loaded
    assert not missing, (
        f"copilot did not load expected plugin skills: missing={sorted(missing)} "
        f"loaded={sorted(loaded)}"
    )


@pytest.mark.smoke
@requires_claude
def test_claude_plugin_loads_expected_skills(tmp_path: Path) -> None:
    """claude --plugin-dir loads project-toolkit at the manifest version.

    Asserts returncode 0 on ``plugin list`` and that the version from
    ``.claude/.claude-plugin/plugin.json`` appears in ``plugin details``, proving
    the CLI loaded the shipped plugin rather than failing silently.
    """
    version = subprocess.run(
        [resolve_executable("claude"), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_clean_env(),
    )
    print(f"claude --version: {version.stdout.strip() or version.stderr.strip()}")

    manifest_version = _read_manifest_version(_CLAUDE_MANIFEST)

    try:
        listing = subprocess.run(
            [
                resolve_executable("claude"),
                "-C",
                str(tmp_path),
                "--plugin-dir",
                str(_CLAUDE_PLUGIN_DIR),
                "plugin",
                "list",
            ],
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT_SECONDS,
            check=False,
            env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"claude plugin list exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)")

    assert listing.returncode == 0, (
        f"claude plugin list failed (rc={listing.returncode}). "
        f"stdout={listing.stdout[-600:]!r} stderr={listing.stderr[-600:]!r}"
    )

    try:
        details = subprocess.run(
            [
                resolve_executable("claude"),
                "-C",
                str(tmp_path),
                "--plugin-dir",
                str(_CLAUDE_PLUGIN_DIR),
                "plugin",
                "details",
                "project-toolkit",
            ],
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT_SECONDS,
            check=False,
            env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"claude plugin details exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)")

    assert details.returncode == 0, (
        f"claude plugin details failed (rc={details.returncode}). "
        f"stdout={details.stdout[-600:]!r} stderr={details.stderr[-600:]!r}"
    )
    combined = details.stdout + details.stderr
    assert manifest_version in combined, (
        f"claude did not report manifest version {manifest_version!r}. "
        f"stdout={details.stdout[-600:]!r} stderr={details.stderr[-600:]!r}"
    )


# Always-on unit checks. They need no real CLI, so they run in bare CI and pin
# the load contract the gated smoke depends on: every expected lifecycle skill
# ships in BOTH plugin trees. A break here means the gated smoke is asserting a
# skill set that cannot load, so the contract drifted and the smoke is stale.


def test_expected_skills_ship_in_copilot_plugin_tree() -> None:
    """Each EXPECTED_SKILLS entry has a skill dir in the Copilot plugin tree.

    If a lifecycle skill is renamed or removed from src/copilot-cli/skills, the
    gated Copilot smoke would assert a name that can never load. Pin the set to
    the on-disk tree so that drift fails in bare CI, not only in the nightly job.
    """
    skills_dir = _COPILOT_PLUGIN_DIR / "skills"
    missing = {name for name in EXPECTED_SKILLS if not (skills_dir / name).is_dir()}
    assert not missing, f"expected skills missing from {skills_dir}: {sorted(missing)}"


def test_expected_skills_ship_in_claude_tree() -> None:
    """Each EXPECTED_SKILLS entry ships in the Claude tree as command or skill.

    The Claude plugin surfaces a lifecycle capability either as a slash command
    under .claude/commands/<name>.md or as a skill under .claude/skills/<name>/.
    Most lifecycle names ship as commands; `review` ships as a skill dir. Accept
    either so the contract tracks how the plugin actually exposes the capability,
    and so a rename in both places fails in bare CI before the nightly Claude
    smoke ever runs.
    """
    commands_dir = _CLAUDE_PLUGIN_DIR / "commands"
    skills_dir = _CLAUDE_PLUGIN_DIR / "skills"
    missing = {
        name
        for name in EXPECTED_SKILLS
        if not (commands_dir / f"{name}.md").is_file() and not (skills_dir / name).is_dir()
    }
    assert not missing, (
        f"expected skills missing from {commands_dir} and {skills_dir}: {sorted(missing)}"
    )


def test_claude_manifest_exposes_string_version() -> None:
    """The Claude manifest carries a non-empty string version.

    The gated Claude smoke asserts this version appears in `plugin details`. If
    the manifest loses its version or makes it non-string, the smoke assertion
    becomes meaningless; pin the precondition here so it fails in bare CI.
    """
    version = _read_manifest_version(_CLAUDE_MANIFEST)
    assert version


def test_plugin_skill_names_counts_only_plugin_source() -> None:
    """Only `source: plugin` records count toward the loaded set.

    A built-in or user-level skill with the same name must not mask a missing
    plugin skill. This pins the filter the gated Copilot assertion relies on.
    """
    payload = [
        {"name": "build", "source": "plugin"},
        {"name": "review", "source": "builtin"},
        {"name": "plan", "source": "plugin"},
        {"name": "noname-source-plugin"},
        "not-a-record",
    ]

    names = _plugin_skill_names(payload)

    assert names == {"build", "plan"}


def test_plugin_skill_names_handles_non_list_payload() -> None:
    """A non-list payload yields an empty set, not a crash.

    The Copilot CLI should print a JSON array, but a malformed run must surface
    as "no plugin skills loaded" (a failed assertion with diagnostics), not an
    unhandled exception that hides the real output.
    """
    assert _plugin_skill_names({"unexpected": "object"}) == set()
    assert _plugin_skill_names(None) == set()
