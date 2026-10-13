"""Review-finding tests for build/scripts/check_agent_source_parity.py (issue #5688)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.build_scripts.test_check_agent_source_parity import (
    CLAUDE,
    SHARED,
    build_repo,
    gate,
    mutate,
    run_gate,
)


class TestReviewFindings:
    def test_reordered_sections_fail(self, tmp_path: Path) -> None:
        claude = mutate(
            CLAUDE,
            "## Completion Criteria\n\n- Every test passes.\n\n## Evidence Requirements\n\n"
            "- Cite the command output.\n",
            "## Evidence Requirements\n\n- Cite the command output.\n\n"
            "## Completion Criteria\n\n- Every test passes.\n",
        )
        build_repo(tmp_path, claude=claude)
        found, _ = gate.collect_divergence(tmp_path)
        assert list(found) == [("widget", gate.PAIR_CLAUDE, "order")]

    def test_deleted_claude_preamble_fails(self, tmp_path: Path) -> None:
        claude = mutate(CLAUDE, "Intro paragraph for the widget agent.\n\n", "")
        build_repo(tmp_path, claude=claude)
        found, _ = gate.collect_divergence(tmp_path)
        assert ("widget", gate.PAIR_CLAUDE, "preamble") in found

    def test_orphan_template_without_shared_is_reported(self, tmp_path: Path) -> None:
        build_repo(tmp_path, shared="", copilot="")
        _, missing = gate.collect_divergence(tmp_path)
        assert [f.agent for f in missing] == ["widget"]
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED

    def test_write_baseline_refuses_incomplete_agents(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_repo(tmp_path, copilot="")
        assert run_gate(tmp_path, "--write-baseline") == gate.EXIT_DIVERGED
        assert "refusing to write the baseline" in capsys.readouterr().err
        assert not (tmp_path / gate.BASELINE_RELATIVE_PATH).exists()

    def test_repeated_h2_name_is_a_config_error(self, tmp_path: Path) -> None:
        shared = SHARED + "\n## Steps\n\n1. Again.\n"
        build_repo(tmp_path, shared=shared)
        assert run_gate(tmp_path) == gate.EXIT_CONFIG
