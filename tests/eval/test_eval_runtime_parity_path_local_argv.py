"""CLI argv for `path_local` and `cwd` fixtures (SPEC-4880 REQ-9).

A live run on 2026-09-27 showed two argv defects. Claude denied reads
outside a nested `cwd`, so a fixture could not reach a sibling tree. Copilot
received `--no-custom-instructions` for a fixture that declared only
`path_local`, which disables the very files the fixture installs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.eval._runtime_parity_test_support import parity, runtime_parity

PATH_LOCAL_FIXTURES = (
    runtime_parity.REPO_ROOT / "scripts" / "eval" / "examples" / "path-local-parity-fixtures.json"
)


def _path_local_fixture() -> Any:
    return runtime_parity.load_fixtures(PATH_LOCAL_FIXTURES)[0]


def _root_cwd_fixture() -> Any:
    return runtime_parity.load_fixtures(parity.DEFAULT_FIXTURES)[0]


def test_copilot_keeps_custom_instructions_for_path_local_fixture(tmp_path: Path) -> None:
    """REQ-9: a `path_local`-only fixture must not disable custom instructions."""
    fixture = _path_local_fixture()
    assert fixture.path_local and not fixture.instructions
    argv = parity.build_argv("copilot", "copilot", parity.DEFAULT_MODEL, fixture, tmp_path)
    assert "--no-custom-instructions" not in argv


def test_nested_cwd_grants_workspace_root_to_both_clis(tmp_path: Path) -> None:
    """REQ-9: a nested `cwd` adds `--add-dir <workspace>` for each CLI."""
    fixture = _path_local_fixture()
    assert fixture.cwd != "."
    for harness in ("claude", "copilot"):
        argv = parity.build_argv(harness, harness, parity.DEFAULT_MODEL, fixture, tmp_path)
        index = argv.index("--add-dir")
        assert argv[index + 1] == str(tmp_path)


def test_root_cwd_adds_no_directory_grant(tmp_path: Path) -> None:
    """REQ-9: a fixture run from the workspace root keeps its argv unchanged."""
    fixture = _root_cwd_fixture()
    assert fixture.cwd == "."
    for harness in ("claude", "copilot"):
        argv = parity.build_argv(harness, harness, parity.DEFAULT_MODEL, fixture, tmp_path)
        assert "--add-dir" not in argv


def test_workspace_is_optional_for_existing_callers() -> None:
    """REQ-9: callers that pass no workspace get no directory grant."""
    argv = parity.build_argv("claude", "claude", parity.DEFAULT_MODEL, _path_local_fixture())
    assert "--add-dir" not in argv
