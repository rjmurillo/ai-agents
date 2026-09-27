"""Tests for the `path_local` discoverable-guide restriction (issue #4880).

Split out of `test_eval_runtime_parity_path_local.py` (pushed to 560 lines
by these tests, over the taste-lints 500-line ERROR threshold). Covers the
coordinator's bot-review security finding end to end: the fixture loader's
own restriction (`_runtime_parity.py`'s `_load_path_local`, backed by
`_runtime_path_local_guides.py`) and the Copilot listing preflight's
matching filter (`eval_runtime_parity.py`'s
`_path_local_discoverable_by_copilot`). General `path_local`/`cwd` loading,
install, ref resolution, and the rest of the preflight stay in the sibling
file this one was split from.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from tests.eval._runtime_parity_test_support import (
    FIXTURES,
    corpus_with_instructions,
    parity,
    runtime_parity,
)


def _corpus(tmp_path: Path, overrides: dict[str, object]) -> Path:
    """Build a one-fixture corpus from the stock "resume-phase-3" fixture.

    Mirrors the identically-named helper in the sibling test file this one
    was split from; kept local rather than shared because it writes
    `overrides` verbatim, including a value a loader test wants rejected.
    """
    source = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = dict(source["fixtures"][0])
    fixture.update(overrides)
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps({"schema_version": 1, "fixtures": [fixture]}), encoding="utf-8")
    return path


# --- Loader restriction (security, coordinator finding) --------------------


def test_path_local_rejects_an_agent_install_path(tmp_path: Path) -> None:
    """Security: a path_local entry naming an agent file would overwrite it on install.

    install_path_local writes at the exact repository-relative path,
    unprojected; a fixture-declared ".claude/agents/parity.md" would
    silently replace the agent definition under test after install.
    """
    path = _corpus(tmp_path, {"path_local": [".claude/agents/parity.md"]})

    with pytest.raises(runtime_parity.ParityConfigError, match="discoverable guide"):
        runtime_parity.load_fixtures(path)


def test_path_local_rejects_an_arbitrary_repository_file(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"path_local": ["README.md"]})

    with pytest.raises(runtime_parity.ParityConfigError, match="discoverable guide"):
        runtime_parity.load_fixtures(path)


def test_path_local_rejects_a_guide_inside_the_isolated_profile(tmp_path: Path) -> None:
    """REQ-9: a guide under `.parity-profile/` would overwrite the isolation sentinel."""
    path = _corpus(tmp_path, {"path_local": [".parity-profile/claude/CLAUDE.md"]})

    with pytest.raises(runtime_parity.ParityConfigError, match="discoverable guide"):
        runtime_parity.load_fixtures(path)


def test_path_local_accepts_a_nested_agents_md(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"path_local": [".github/AGENTS.md"]})

    fixture = runtime_parity.load_fixtures(path)[0]

    assert fixture.path_local == (".github/AGENTS.md",)


def test_path_local_accepts_a_nested_claude_md(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"path_local": ["a/b/CLAUDE.md"]})

    fixture = runtime_parity.load_fixtures(path)[0]

    assert fixture.path_local == ("a/b/CLAUDE.md",)


def test_path_local_accepts_the_copilot_repo_instructions_file(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"path_local": [".github/copilot-instructions.md"]})

    fixture = runtime_parity.load_fixtures(path)[0]

    assert fixture.path_local == (".github/copilot-instructions.md",)


def test_path_local_rejects_a_copilot_instructions_file_outside_github(tmp_path: Path) -> None:
    """Only the exact `.github/copilot-instructions.md` path is allowed."""
    path = _corpus(tmp_path, {"path_local": ["a/copilot-instructions.md"]})

    with pytest.raises(runtime_parity.ParityConfigError, match="discoverable guide"):
        runtime_parity.load_fixtures(path)


# --- Copilot preflight filter (coordinator finding) -------------------------


def test_verify_listing_passes_when_a_path_local_guide_sits_outside_the_cwd_ancestry(
    tmp_path: Path,
) -> None:
    """Coordinator finding: a sibling-directory guide installs but Copilot cannot list it here.

    Before this fix, the preflight's expected set included every
    `path_local` entry unconditionally, so a guide outside `cwd`'s
    ancestor chain (Copilot's own discovery rule) made a correct, empty
    listing look like a missing source and abort the run.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    corpus = corpus_with_instructions(
        tmp_path,
        default_instructions=False,
        path_local=["a/CLAUDE.md", "b/AGENTS.md"],
        cwd="a",
    )
    fixture = runtime_parity.load_fixtures(corpus)[0]
    # Copilot, run from cwd "a", lists only what its ancestor-chain rule
    # reaches from there: "a/CLAUDE.md" itself, not the sibling "b/AGENTS.md".
    listing = [{"sourcePath": "a/CLAUDE.md"}]
    runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(listing), ""))

    result, failure = parity._verify_copilot_instruction_listing(
        fixture,
        "copilot",
        workspace,
        workspace / "a",
        runner,
        30,
        {},
        {"a/CLAUDE.md": b"x", "b/AGENTS.md": b"y"},
    )

    assert failure is None
    assert result == listing


def test_path_local_rejects_a_non_canonical_spelling(tmp_path: Path) -> None:
    """REQ-9: `./AGENTS.md` would never match Copilot's listed `AGENTS.md`."""
    for spelling in ("./AGENTS.md", "a//CLAUDE.md", "a/./CLAUDE.md"):
        path = _corpus(tmp_path, {"path_local": [spelling]})
        with pytest.raises(runtime_parity.ParityConfigError, match="discoverable guide"):
            runtime_parity.load_fixtures(path)


def test_setup_installed_copilot_repo_instructions_are_expected_in_the_listing(
    tmp_path: Path,
) -> None:
    """REQ-9: Copilot lists `.github/copilot-instructions.md` however it was installed."""
    path = _corpus(
        tmp_path,
        {
            "path_local": ["AGENTS.md"],
            "setup_files": {".github/copilot-instructions.md": "repo rules\n"},
        },
    )
    fixture = runtime_parity.load_fixtures(path)[0]
    assert ".github/copilot-instructions.md" in parity._setup_discoverable_sources(fixture)
