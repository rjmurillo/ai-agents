#!/usr/bin/env python3
"""End-to-end plugin-load smoke for the shipped CLI plugins (issue #2736).

PR #2735 was green on unit tests, schema checks, and generated-file checks, yet a
broken skill front-matter field (``argument-hint must be a string``) could still
reach a customer because nothing loaded the plugin in the real CLI and asserted
the skills loaded. These tests close that gap: they launch the REAL CLIs, load
the shipped plugin directory, list the plugin's skills, and assert the lifecycle
skills load.

  - Copilot: ``copilot --plugin-dir <repo>/src/copilot-cli skill list --json``
    with ``cwd`` set to a neutral directory. Assert returncode 0, no
    ``argument-hint`` loader warning in stderr, and the expected lifecycle skills
    load from ``source: plugin``.
  - Claude: ``claude --plugin-dir <repo>/.claude plugin list`` and
    ``plugin details project-toolkit`` with ``cwd`` set to a neutral directory.
    Assert returncode 0, the manifest version appears, and the expected lifecycle
    skills are present in the details output.

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
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cli_exec import resolve_executable  # noqa: E402
finally:
    sys.path[:] = _original_sys_path

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
_PLUGIN_ROOT_ENV_KEYS = {"CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "COPILOT_PLUGIN_ROOT"}

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
    for key in list(env):
        if key.upper() in _PLUGIN_ROOT_ENV_KEYS:
            env.pop(key, None)
    return env


def _run_cli(
    args: list[str],
    *,
    timeout: int,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=_clean_env(),
    )


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


def _has_plugin_source_record(payload: object) -> bool:
    """True if `payload` is a list with at least one `source: plugin` record.

    Unlike `_plugin_skill_names`, this ignores the ``name`` field: a plugin
    record with a missing or non-string name still proves the enumeration
    surface carried plugin loads. The strict ``name`` filter is applied later by
    `_plugin_skill_names`, so a nameless plugin record makes the smoke fail loud
    on the missing skill rather than skip.
    """
    if not isinstance(payload, list):
        return False
    return any(
        isinstance(record, dict) and record.get("source") == "plugin"
        for record in payload
    )


def _plugin_enumeration_available(payload: object) -> bool:
    """True when the caller must keep the strict assertion instead of skipping.

    The smoke skips ONLY for the known-benign shape: a well-formed JSON array
    that carries zero ``source: plugin`` records. On Copilot CLI 1.0.69
    (verified 2026-07-08 on this repo's shipped ``src/copilot-cli`` tree),
    ``copilot --plugin-dir <dir> skill list --json`` run from a neutral cwd
    surfaces ZERO ``source: plugin`` records: the output carries only
    ``builtin`` and ``personal-copilot``. The ``source: project`` group that
    does list the lifecycle skills is cwd-based (the repo you stand in), not
    ``--plugin-dir`` based, so it is not a valid load signal for a neutral-cwd
    smoke. See issue #2990.

    The caller validates list-ness first:
    ``test_copilot_plugin_loads_expected_skills`` fails loud on a non-list
    payload before this helper is consulted. This helper still returns True for
    every non-benign shape as defense in depth, so any caller (present or
    future) that omits its own guard fails loud rather than skips:

    - a non-list payload (unexpected schema, or a CLI error object) returns True,
      so a caller without its own list guard still fails loud instead of
      skipping silently; and
    - a list that DOES carry ``source: plugin`` records keeps the strict subset
      assertion, so a plugin record with a missing name fails on the absent
      skill instead of masking a regression.
    """
    if not isinstance(payload, list):
        return True
    return _has_plugin_source_record(payload)


_COPILOT_BENIGN_NO_ENUM_VERSIONS = frozenset({"1.0.69", "1.0.70"})


def _copilot_version_omits_plugin_enumeration(version_output: str) -> bool:
    """True when the Copilot CLI version is known to omit ``--plugin-dir`` skills.

    Only the versions in ``_COPILOT_BENIGN_NO_ENUM_VERSIONS`` are allowed to skip
    the strict subset assertion when ``skill list --json`` surfaces zero
    ``source: plugin`` records (issue #2990). Any other version that fails to
    enumerate the plugin is a real plugin-load regression and must fail loud, so
    the smoke keeps its negative control instead of masking a broken load on a
    CLI that DOES enumerate ``--plugin-dir`` skills.

    The version token is the first ``MAJOR.MINOR.PATCH`` in the CLI's
    ``--version`` output; a ``-<suffix>`` build tag (for example ``1.0.69-3``) is
    ignored because the enumeration behavior tracks the release, not the build.
    A version string with no parseable token returns False (fail loud).
    """
    match = re.search(r"\d+\.\d+\.\d+", version_output)
    if match is None:
        return False
    return match.group(0) in _COPILOT_BENIGN_NO_ENUM_VERSIONS


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
    version = _run_cli(
        [resolve_executable("copilot"), "--version"],
        timeout=60,
    )
    print(f"copilot --version: {version.stdout.strip() or version.stderr.strip()}")

    try:
        run = _run_cli(
            [
                resolve_executable("copilot"),
                "--plugin-dir",
                str(_COPILOT_PLUGIN_DIR),
                "skill",
                "list",
                "--json",
            ],
            cwd=tmp_path,
            timeout=_CLI_TIMEOUT_SECONDS,
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

    if not isinstance(payload, list):
        pytest.fail(
            "copilot skill list --json did not return a JSON array "
            f"(got {type(payload).__name__}); the enumeration schema changed. "
            f"stdout={run.stdout[-600:]!r}"
        )

    if not _plugin_enumeration_available(payload):
        version_text = version.stdout.strip() or version.stderr.strip()
        sources = sorted(
            {
                str(record.get("source"))
                for record in (payload if isinstance(payload, list) else [])
                if isinstance(record, dict)
            }
        )
        if not _copilot_version_omits_plugin_enumeration(version_text):
            pytest.fail(
                "copilot skill list --json surfaced no source:plugin records for a "
                f"known-good --plugin-dir on CLI version {version_text!r}, which is "
                "NOT a known plugin-enumeration-omitting version (issues #2990, "
                "#3014). A version that enumerates --plugin-dir skills but returns "
                "none is a real plugin-load regression, not the benign 1.0.69/1.0.70 "
                "shape. "
                f"sources seen: {sources}"
            )
        pytest.skip(
            "copilot skill list --json surfaced no source:plugin records for a "
            "known-good --plugin-dir. On CLI 1.0.69 and 1.0.70 the plugin-dir load "
            "is not enumerated through this surface (issues #2990, #3014); the load "
            "itself is unaffected (the plugin's hooks still load and fire). Skipping "
            "loud rather than false-failing. "
            f"copilot --version: {version_text!r}; "
            f"sources seen: {sources}"
        )

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
    version = _run_cli(
        [resolve_executable("claude"), "--version"],
        timeout=60,
    )
    print(f"claude --version: {version.stdout.strip() or version.stderr.strip()}")

    manifest_version = _read_manifest_version(_CLAUDE_MANIFEST)

    try:
        listing = _run_cli(
            [
                resolve_executable("claude"),
                "--plugin-dir",
                str(_CLAUDE_PLUGIN_DIR),
                "plugin",
                "list",
            ],
            cwd=tmp_path,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"claude plugin list exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)")

    assert listing.returncode == 0, (
        f"claude plugin list failed (rc={listing.returncode}). "
        f"stdout={listing.stdout[-600:]!r} stderr={listing.stderr[-600:]!r}"
    )

    try:
        details = _run_cli(
            [
                resolve_executable("claude"),
                "--plugin-dir",
                str(_CLAUDE_PLUGIN_DIR),
                "plugin",
                "details",
                "project-toolkit",
            ],
            cwd=tmp_path,
            timeout=_CLI_TIMEOUT_SECONDS,
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
    missing = {name for name in EXPECTED_SKILLS if name not in combined}
    assert not missing, (
        f"claude did not report expected plugin skills: missing={sorted(missing)}. "
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


def test_plugin_enumeration_available_true_when_plugin_records_present() -> None:
    """A payload with at least one `source: plugin` record enables the assertion.

    This is the branch where the CLI does enumerate `--plugin-dir` loads, so the
    caller keeps the strict subset check rather than skipping.
    """
    payload = [
        {"name": "build", "source": "plugin"},
        {"name": "review", "source": "builtin"},
    ]

    assert _plugin_enumeration_available(payload) is True


def test_plugin_enumeration_available_false_when_no_plugin_records() -> None:
    """No `source: plugin` record means the CLI did not enumerate the plugin dir.

    On CLI 1.0.69 a neutral-cwd run surfaces only `builtin` and
    `personal-copilot`; the smoke must SKIP rather than false-fail (issue #2990).
    Only a well-formed list with zero plugin records collapses to this
    not-available verdict; malformed shapes are handled separately below.
    """
    only_builtin = [
        {"name": "review", "source": "builtin"},
        {"name": "explain", "source": "personal-copilot"},
    ]

    assert _plugin_enumeration_available(only_builtin) is False
    assert _plugin_enumeration_available([]) is False


def test_plugin_enumeration_available_true_on_non_list_payload() -> None:
    """A non-list payload proceeds (True) so the smoke fails loud, not skips.

    A CLI error object or any unexpected schema must surface as a failed
    assertion with diagnostics, never a silent skip that masks a regression
    (gemini/copilot review on PR #3001).
    """
    assert _plugin_enumeration_available({"unexpected": "object"}) is True
    assert _plugin_enumeration_available(None) is True
    assert _plugin_enumeration_available("not-a-list") is True


def test_plugin_enumeration_available_true_when_plugin_record_missing_name() -> None:
    """A `source: plugin` record counts even without a string `name`.

    Detection is name-independent so a schema change that drops or mangles the
    name field keeps the strict assertion (True), where `_plugin_skill_names`
    then fails on the absent skill instead of skipping.
    """
    payload = [
        {"source": "plugin"},
        {"name": 123, "source": "plugin"},
    ]

    assert _plugin_enumeration_available(payload) is True
    assert _plugin_skill_names(payload) == set()


def test_has_plugin_source_record() -> None:
    """`_has_plugin_source_record` detects plugin records independent of name."""
    assert _has_plugin_source_record([{"source": "plugin"}]) is True
    assert _has_plugin_source_record([{"name": "build", "source": "plugin"}]) is True
    assert _has_plugin_source_record([{"name": "review", "source": "builtin"}]) is False
    assert _has_plugin_source_record([]) is False
    assert _has_plugin_source_record({"unexpected": "object"}) is False
    assert _has_plugin_source_record(None) is False


def test_copilot_version_omits_enumeration_true_for_benign_version() -> None:
    """CLI 1.0.69 and 1.0.70 are the known plugin-enumeration-omitting releases.

    Both surface zero ``source: plugin`` records for a known-good ``--plugin-dir``
    while the plugin still loads (issues #2990, #3014). A build-tag suffix
    (``1.0.69-3``) tracks the same release, so it still matches; extra surrounding
    text from ``--version`` is tolerated.
    """
    assert _copilot_version_omits_plugin_enumeration("1.0.69") is True
    assert _copilot_version_omits_plugin_enumeration("1.0.69-3") is True
    assert _copilot_version_omits_plugin_enumeration("1.0.70") is True
    assert _copilot_version_omits_plugin_enumeration("1.0.70-0") is True
    assert _copilot_version_omits_plugin_enumeration("copilot 1.0.69 (build 42)") is True


def test_copilot_version_omits_enumeration_false_for_other_versions() -> None:
    """Any version not in the benign set must fail loud, not skip (issues #2990, #3014).

    A CLI that enumerates ``--plugin-dir`` skills but returns none is a real
    plugin-load regression; the negative control depends on this returning False.
    """
    assert _copilot_version_omits_plugin_enumeration("1.0.68") is False
    assert _copilot_version_omits_plugin_enumeration("1.0.71") is False
    assert _copilot_version_omits_plugin_enumeration("1.1.0") is False
    assert _copilot_version_omits_plugin_enumeration("2.0.0") is False


def test_copilot_version_omits_enumeration_false_when_unparseable() -> None:
    """No parseable version token means fail loud (return False), never skip."""
    assert _copilot_version_omits_plugin_enumeration("") is False
    assert _copilot_version_omits_plugin_enumeration("unknown") is False
    assert _copilot_version_omits_plugin_enumeration("v1.0") is False


def test_clean_env_strips_plugin_root_keys_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plugin-root env cleanup handles Windows-style case-insensitive names."""
    monkeypatch.setenv("claude_plugin_root", "/wrong/claude")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/wrong/project")
    monkeypatch.setenv("Copilot_Plugin_Root", "/wrong/copilot")
    monkeypatch.setenv("KEEP_ME", "1")

    env = _clean_env()

    assert "KEEP_ME" in env
    assert not any(key.upper() in _PLUGIN_ROOT_ENV_KEYS for key in env)


def test_run_cli_uses_cwd_and_decodes_utf8(tmp_path: Path) -> None:
    """The subprocess helper uses neutral cwd and UTF-8 decoding."""
    run = _run_cli(
        [
            sys.executable,
            "-c",
            "import os; print(os.getcwd()); print(chr(0x2713))",
        ],
        cwd=tmp_path,
        timeout=60,
    )

    assert run.returncode == 0
    lines = run.stdout.splitlines()
    assert lines == [str(tmp_path), chr(0x2713)]
