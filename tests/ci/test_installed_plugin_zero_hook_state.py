"""The installed-plugin guard must certify the ADR-097 zero-hook state.

Before ADR-097 the guard returned 1 unconditionally on an empty manifest, by
design: "an empty run is a failure, never a skip" (#4672). ADR-097 makes zero
registered hooks the deliberately shipped state, so that assertion is inverted
rather than deleted. What the guard asserts now is AGREEMENT between what the
manifest registers and what the tree ships.

These tests drive `main(argv)` and assert on the integer it returns, not on a
helper's return value, per `.claude/rules/testing.md` MUST 8. The empty-passes
case is paired with two controls, because a gate that cannot fail is not a gate:
an orphaned dispatcher and an unreadable manifest must both still exit nonzero.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "test_installed_plugin_hooks.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("installed_plugin_hooks_zero", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load()


def _plugin_source(tmp_path: Path, manifest: str) -> Path:
    """Build a minimal plugin source tree carrying the given hooks.json text."""
    source = tmp_path / "plugin-source"
    (source / "hooks").mkdir(parents=True)
    (source / "hooks" / "hooks.json").write_text(manifest, encoding="utf-8")
    return source


def _run(tmp_path: Path, source: Path, negative_env: str = "false") -> int:
    argv = [
        "--plugin-source",
        str(source),
        "--install-root",
        str(tmp_path / "install"),
        "--consumer-cwd",
        str(tmp_path / "consumer"),
        "--negative-env",
        negative_env,
    ]
    original = sys.argv
    sys.argv = [str(_SCRIPT), *argv]
    try:
        return _MODULE.main()
    finally:
        sys.argv = original


@pytest.mark.parametrize("negative_env", ["false", "true"])
def test_zero_registered_hooks_passes(tmp_path: Path, negative_env: str) -> None:
    """The shipped ADR-097 state exits 0 in both the positive and degraded run."""
    source = _plugin_source(tmp_path, json.dumps({"hooks": {}, "version": 1}))

    assert _run(tmp_path, source, negative_env) == 0


def test_a_dispatcher_shipped_with_zero_events_fails(tmp_path: Path) -> None:
    """Control: orphaned machinery a consumer installs and never runs."""
    source = _plugin_source(tmp_path, json.dumps({"hooks": {}, "version": 1}))
    orphan = source / "hooks" / "PreToolUse" / "_dispatch.py"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    assert _run(tmp_path, source) == 1


def test_an_unparseable_manifest_still_fails(tmp_path: Path) -> None:
    """Control: generation-broke is not the same verdict as deliberately-empty.

    Without this, permitting the empty case would also silently permit a
    manifest that failed to generate at all.
    """
    source = _plugin_source(tmp_path, "not json at all")

    assert _run(tmp_path, source) == 1


def test_a_manifest_without_a_hooks_mapping_still_fails(tmp_path: Path) -> None:
    """Control: a structurally wrong manifest must not read as empty."""
    source = _plugin_source(tmp_path, json.dumps({"version": 1}))

    assert _run(tmp_path, source) == 1


def test_a_missing_plugin_source_is_a_config_error(tmp_path: Path) -> None:
    """Exit 2 stays reserved for configuration errors (ADR-035)."""
    assert _run(tmp_path, tmp_path / "does-not-exist") == 2


def _registering_source(tmp_path: Path) -> Path:
    """A plugin source that DOES register an event, for the non-empty path."""
    return _plugin_source(
        tmp_path,
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {"type": "command", "bash": "true", "powershell": "exit 0", "cwd": "."}
                    ]
                },
                "version": 1,
            }
        ),
    )


def test_a_registered_event_with_no_dispatcher_still_fails(tmp_path: Path) -> None:
    """The #4672 invariant survives ADR-097 for any event that IS registered.

    This is the load-bearing control for the whole redesign. ADR-097 makes an
    EMPTY manifest pass, and the docstring claims the non-empty path stays
    fully armed. If that claim were false, re-adding a tool-use hook would land
    against a guard that had quietly become a no-op, which is precisely the
    "passes after executing nothing" failure #4672 was filed for.

    Inherited from the retired
    `test_partial_upgrade_degrades.py::test_absent_dispatcher_fails_the_guard`,
    which asserted the same property against the shipped Copilot tree that
    ADR-097 deleted. The subject moves to a synthetic tree; the invariant does
    not change.

    Driven as a real subprocess rather than through `main()` in-process, so the
    assertion is on the process exit status a CI step actually reads
    (`.claude/rules/testing.md` MUST 8, `.claude/rules/ci-scripts.md` MUST 10).
    """
    source = _registering_source(tmp_path)
    assert not (source / "hooks" / "PreToolUse" / "_dispatch.py").exists()

    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--plugin-source",
            str(source),
            "--install-root",
            str(tmp_path / "install"),
            "--consumer-cwd",
            str(tmp_path / "consumer"),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )

    assert proc.returncode != 0, (
        "the guard passed a plugin that registers PreToolUse but ships no "
        f"dispatcher, so it certified a run it could not perform.\n{proc.stdout}"
    )
    assert "FAIL: no dispatcher" in proc.stdout, proc.stdout


def test_registered_events_and_readability_are_separable(tmp_path: Path) -> None:
    """`_registered_events` returns [] for two opposite situations.

    The caller distinguishes them via `_manifest_is_readable`. Pinning that
    split here keeps a future refactor from collapsing the two back together,
    which is what would let a broken manifest pass as the empty state.
    """
    empty = _plugin_source(tmp_path / "a", json.dumps({"hooks": {}}))
    broken = _plugin_source(tmp_path / "b", "{{{")

    assert _MODULE._registered_events(empty) == []
    assert _MODULE._registered_events(broken) == []
    assert _MODULE._manifest_is_readable(empty) is True
    assert _MODULE._manifest_is_readable(broken) is False
