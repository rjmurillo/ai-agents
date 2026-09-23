"""Tests for the Copilot instruction projection contract (REQ-034 AC1-AC6).

Covers the `copilot_instruction_path` mapping, the missing-projection config
error, the `--no-custom-instructions` argv rule, and an unavailable listing
end to end. The listing preflight's own branches live in
`test_copilot_instruction_listing.py`.
"""

from __future__ import annotations

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


@pytest.mark.parametrize(
    ("rule_path", "projection"),
    [
        (".claude/rules/voice.md", ".github/instructions/voice.instructions.md"),
        # Only the stem matters, not the directory.
        ("a/b/c/builder-ethos.md", ".github/instructions/builder-ethos.instructions.md"),
        # Only the final suffix is stripped.
        ("voice.instructions.md", ".github/instructions/voice.instructions.instructions.md"),
    ],
)
def test_copilot_instruction_path_maps_the_stem(rule_path: str, projection: str) -> None:
    assert runtime_harness.copilot_instruction_path(rule_path) == projection


@pytest.mark.parametrize("harnesses", ["both", "claude"])
def test_missing_copilot_projection_fails_only_a_copilot_run(
    tmp_path: Path, harnesses: str
) -> None:
    """`AGENTS.md` exists at the repo root but has no Copilot projection."""
    corpus = corpus_with_instructions(tmp_path, instructions=["AGENTS.md"])
    runner = FixedResponseRunner("CONTINUE_PHASE_3")

    def run() -> Any:
        return parity.run_evaluation(
            fixtures_path=corpus,
            model=parity.DEFAULT_MODEL,
            output=tmp_path / "run" / "report.json",
            claude_bin="claude",
            copilot_bin="copilot",
            timeout=30,
            dry_run=False,
            runner=runner,
            harnesses=harnesses,
        )

    if harnesses == "both":
        with pytest.raises(parity.ParityConfigError, match="AGENTS.instructions.md"):
            run()
        assert runner.calls == []
        return
    # A Claude-only run never resolves a Copilot projection it will not use.
    report, code = run()
    assert code == parity.EXIT_OK
    assert report["fixtures"][0]["copilot_instructions"] == []


@pytest.mark.parametrize("with_instructions", [True, False])
def test_build_argv_drops_no_custom_instructions_only_for_instruction_fixtures(
    tmp_path: Path, with_instructions: bool
) -> None:
    corpus = corpus_with_instructions(tmp_path) if with_instructions else FIXTURES
    fixture = runtime_parity.load_fixtures(corpus)[0]
    assert bool(fixture.instructions) is with_instructions

    argv = parity.build_argv("copilot", "copilot", parity.DEFAULT_MODEL, fixture)

    assert ("--no-custom-instructions" in argv) is not with_instructions


@pytest.mark.parametrize("listing_works", [True, False])
def test_end_to_end_listing_result_is_recorded(tmp_path: Path, listing_works: bool) -> None:
    corpus = corpus_with_instructions(tmp_path)
    fixed = FixedResponseRunner("CONTINUE_PHASE_3")

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        if args[1:4] == ["instruction", "list", "--json"] and not listing_works:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        return fixed(argv, **kwargs)

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

    copilot_record = report["fixtures"][0]["copilot"]
    if listing_works:
        installed = {entry["path"] for entry in report["fixtures"][0]["copilot_instructions"]}
        listed = {entry["sourcePath"] for entry in copilot_record["instruction_listing"]}
        assert listed == installed != set()
        return
    assert code == parity.EXIT_EXTERNAL
    assert report["verdict"] == "ERROR"
    assert copilot_record["passed"] is False
    assert "unavailable" in copilot_record["error"]
    assert "instruction_listing" not in copilot_record
