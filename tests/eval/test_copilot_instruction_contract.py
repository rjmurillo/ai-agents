"""Tests for the Copilot instruction projection contract (REQ-034 AC1-AC7).

Covers what `test_eval_runtime_parity_semantic.py` and
`test_eval_runtime_parity_semantic_cli.py` do not: the `copilot_instruction_path`
mapping itself, the missing-projection config error (AC2), and every branch
of the `copilot instruction list --json` preflight
(`_verify_copilot_instruction_listing`, AC4-AC6) in isolation from a full
`run_evaluation` call.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.eval._runtime_parity_test_support import (
    FIXTURES,
    FixedResponseRunner,
    corpus_with_instructions,
    parity,
    runtime_harness,
    runtime_parity,
)

REPO_ROOT = parity.REPO_ROOT


# --- copilot_instruction_path mapping (pure function) ------------------------


def test_copilot_instruction_path_maps_the_stem() -> None:
    assert (
        runtime_harness.copilot_instruction_path(".claude/rules/voice.md")
        == ".github/instructions/voice.instructions.md"
    )


def test_copilot_instruction_path_uses_the_basename_stem_not_the_directory() -> None:
    """A fixture instruction need not live under `.claude/rules/`; only the stem matters."""
    assert (
        runtime_harness.copilot_instruction_path("a/b/c/builder-ethos.md")
        == ".github/instructions/builder-ethos.instructions.md"
    )


def test_copilot_instruction_path_strips_only_the_final_suffix() -> None:
    assert (
        runtime_harness.copilot_instruction_path("voice.instructions.md")
        == ".github/instructions/voice.instructions.instructions.md"
    )


# --- AC2: missing projection is a config error before any model call --------


def test_missing_copilot_projection_is_a_config_error_before_any_call(
    tmp_path: Path,
) -> None:
    """`AGENTS.md` exists at the repo root but has no Copilot projection."""
    corpus = corpus_with_instructions(tmp_path, instructions=["AGENTS.md"])
    runner = FixedResponseRunner("CONTINUE_PHASE_3")

    with pytest.raises(parity.ParityConfigError, match="AGENTS.instructions.md"):
        parity.run_evaluation(
            fixtures_path=corpus,
            model=parity.DEFAULT_MODEL,
            output=tmp_path / "run" / "report.json",
            claude_bin="claude",
            copilot_bin="copilot",
            timeout=30,
            dry_run=False,
            runner=runner,
        )
    assert runner.calls == []


def test_missing_copilot_projection_is_skipped_for_a_claude_only_run(
    tmp_path: Path,
) -> None:
    """A Claude-only run never resolves a Copilot projection it will not use."""
    corpus = corpus_with_instructions(tmp_path, instructions=["AGENTS.md"])

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
    )

    assert code == parity.EXIT_OK
    assert report["fixtures"][0]["copilot_instructions"] == []


# --- AC3: argv omits --no-custom-instructions only for an instruction fixture


def test_build_argv_omits_no_custom_instructions_for_an_instruction_fixture(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path)
    fixture = runtime_parity.load_fixtures(corpus)[0]

    argv = parity.build_argv("copilot", "copilot", parity.DEFAULT_MODEL, fixture)

    assert "--no-custom-instructions" not in argv


def test_build_argv_keeps_no_custom_instructions_without_instructions() -> None:
    fixture = runtime_parity.load_fixtures(FIXTURES)[0]
    assert fixture.instructions == ()

    argv = parity.build_argv("copilot", "copilot", parity.DEFAULT_MODEL, fixture)

    assert "--no-custom-instructions" in argv


# --- AC4-AC6: the instruction listing preflight ------------------------------


def _fixture() -> Any:
    fixture = runtime_parity.load_fixtures(FIXTURES)[0]
    return dataclasses.replace(fixture, instructions=(".claude/rules/voice.md",))


class _ListingRunner:
    """Answer the listing call and record the `cwd` and `env` it ran with."""

    def __init__(self, *, returncode: int = 0, stdout: str = "", timeout: bool = False) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.timeout = timeout
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        self.kwargs.append(kwargs)
        if self.timeout:
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout") or 1)
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


def _listing_runner(
    response: None, *, returncode: int = 0, stdout: str = "", timeout: bool = False
) -> _ListingRunner:
    return _ListingRunner(returncode=returncode, stdout=stdout, timeout=timeout)


def test_listing_matching_the_installed_set_returns_it_with_no_failure(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    stdout = json.dumps([{"sourcePath": ".github/instructions/voice.instructions.md"}])
    runner = _listing_runner(None, stdout=stdout)

    listing, failure = parity._verify_copilot_instruction_listing(
        fixture, "copilot", workspace, runner, 30, installed
    )

    assert failure is None
    assert listing == [{"sourcePath": ".github/instructions/voice.instructions.md"}]
    # The listing must see the same workspace and environment as the model run.
    assert runner.kwargs[0]["cwd"] == workspace
    assert runner.kwargs[0]["env"] == runtime_harness.runtime_env(workspace, "copilot")


@pytest.mark.parametrize(
    "entry",
    [{"path": "AGENTS.md"}, {"sourcePath": 7}, "AGENTS.md"],
    ids=["other-key", "non-string", "non-dict"],
)
def test_listing_with_an_unreadable_entry_is_a_config_error(
    tmp_path: Path, entry: object
) -> None:
    """An entry the parser cannot read could hide a leaked source."""
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    stdout = json.dumps([{"sourcePath": ".github/instructions/voice.instructions.md"}, entry])
    runner = _listing_runner(None, stdout=stdout)

    with pytest.raises(parity.ParityConfigError, match="without a string sourcePath"):
        parity._verify_copilot_instruction_listing(
            fixture, "copilot", workspace, runner, 30, installed
        )


def test_listing_with_an_extra_source_is_a_config_error(tmp_path: Path) -> None:
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    stdout = json.dumps(
        [
            {"sourcePath": ".github/instructions/voice.instructions.md"},
            {"sourcePath": ".github/copilot-instructions.md"},
        ]
    )
    runner = _listing_runner(None, stdout=stdout)

    with pytest.raises(parity.ParityConfigError, match="extra="):
        parity._verify_copilot_instruction_listing(
            fixture, "copilot", workspace, runner, 30, installed
        )


def test_listing_with_a_missing_source_is_a_config_error(tmp_path: Path) -> None:
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    runner = _listing_runner(None, stdout=json.dumps([]))

    with pytest.raises(parity.ParityConfigError, match="missing="):
        parity._verify_copilot_instruction_listing(
            fixture, "copilot", workspace, runner, 30, installed
        )


def test_listing_command_nonzero_exit_is_unavailable(tmp_path: Path) -> None:
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    runner = _listing_runner(None, returncode=1, stdout="")

    listing, failure = parity._verify_copilot_instruction_listing(
        fixture, "copilot", workspace, runner, 30, installed
    )

    assert listing is None
    assert failure is not None
    assert "unavailable" in failure["error"]
    assert failure["passed"] is False


def test_listing_command_bad_json_is_unavailable(tmp_path: Path) -> None:
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    runner = _listing_runner(None, stdout="not json")

    listing, failure = parity._verify_copilot_instruction_listing(
        fixture, "copilot", workspace, runner, 30, installed
    )

    assert listing is None
    assert failure is not None
    assert "unparsable JSON" in failure["error"]


def test_listing_command_non_array_json_is_unavailable(tmp_path: Path) -> None:
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    runner = _listing_runner(None, stdout=json.dumps({"sourcePath": "x"}))

    listing, failure = parity._verify_copilot_instruction_listing(
        fixture, "copilot", workspace, runner, 30, installed
    )

    assert listing is None
    assert failure is not None
    assert "not an array" in failure["error"]


def test_listing_command_timeout_is_unavailable(tmp_path: Path) -> None:
    fixture = _fixture()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    installed = {".github/instructions/voice.instructions.md": b"x"}
    runner = _listing_runner(None, timeout=True)

    listing, failure = parity._verify_copilot_instruction_listing(
        fixture, "copilot", workspace, runner, 30, installed
    )

    assert listing is None
    assert failure is not None
    assert "timed out" in failure["error"]


# --- AC5, AC6 end to end: an unavailable listing exits 3 and is recorded ----


def test_end_to_end_listing_failure_exits_external_and_is_recorded(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path)

    def runner(argv, **kwargs):
        args = [str(value) for value in argv]
        if args[1:4] == ["instruction", "list", "--json"]:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        if "--version" in args:
            executable = Path(args[0]).name.lower()
            return subprocess.CompletedProcess(args, 0, f"{executable} test-version\n", "")
        return FixedResponseRunner("CONTINUE_PHASE_3")(argv, **kwargs)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=runner,
    )

    assert code == parity.EXIT_EXTERNAL
    assert report["verdict"] == "ERROR"
    copilot_record = report["fixtures"][0]["copilot"]
    assert copilot_record["passed"] is False
    assert "unavailable" in copilot_record["error"]
    assert "instruction_listing" not in copilot_record
