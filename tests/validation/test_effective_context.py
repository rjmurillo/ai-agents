"""Tests for the CLI in scripts/validation/effective_context.py (issue #4880).

Covers argument validation, dispatch, and output formats. Split out of one
1196-line file (taste-lints 500-line ERROR): Claude- and Copilot-specific
resolution live in ``test_effective_context_claude.py`` and
``test_effective_context_copilot.py``; shared source-reading in
``test_effective_context_sources.py``; the ratchet and ``--observe`` in
``test_effective_context_ratchet.py``. This file keeps ``--target``/
``--harness`` validation, error-to-exit-code mapping, and the table/JSON
report formats.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context as ec
import scripts.validation.effective_context_resolvers as ecr
from tests.validation._effective_context_helpers import FakeCompletedProcess, _write


class TestOrchestratorDispatch:
    def test_unknown_harness_raises_value_error(self, tmp_path: Path) -> None:
        _write(tmp_path, "target.py", "x = 1\n")
        with pytest.raises(ValueError, match="unknown harness"):
            ecr.resolve_effective_context(tmp_path, "target.py", "bogus")


class TestCliInjectedRepoRoot:
    """CLI paths only reachable by injecting `repo_root` (a synthetic tree)."""

    def test_malformed_rule_frontmatter_exits_two_via_main(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/bad.md", "---\npaths: [unclosed\n---\nbody\n")
        _write(tmp_path, "target.py", "x = 1\n")
        code = ec.main(["--target", "target.py", "--harness", "claude"], repo_root=tmp_path)
        assert code == 2
        assert "not valid YAML" in capsys.readouterr().err

    def test_ci_reports_a_malformed_rule_as_exit_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/bad.md", "---\npaths: [unclosed\n---\nbody\n")
        _write(tmp_path, "target.py", "x = 1\n")
        monkeypatch.setattr(ec, "CEILINGS_BYTES", {("target.py", "claude"): 10})
        code = ec.main(["--ci"], repo_root=tmp_path)
        assert code == 2
        assert "not valid YAML" in capsys.readouterr().err

    def test_ci_prints_fail_and_exits_one_on_a_real_breach(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "a/CLAUDE.md", "a" * 100 + "\n")
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "target.py").write_text("x\n", encoding="utf-8")
        monkeypatch.setattr(ec, "CEILINGS_BYTES", {("a/b/target.py", "claude"): 1})
        code = ec.main(["--ci"], repo_root=tmp_path)
        assert code == 1
        out = capsys.readouterr().out
        assert "FAIL: path-local effective-context ratchet breached." in out

    def test_problems_are_printed_in_the_table(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "@nonexistent.md\n")
        _write(tmp_path, "target.py", "x = 1\n")
        code = ec.main(["--target", "target.py", "--harness", "claude"], repo_root=tmp_path)
        assert code == 0
        assert "PROBLEM  missing" in capsys.readouterr().out

    def test_observe_mismatch_via_main_prints_missing_and_extra_and_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(tmp_path, "target.py", "x = 1\n")
        entries = [{"location": "repository", "sourcePath": "bogus.instructions.md"}]

        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(0, stdout=json.dumps(entries))

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        code = ec.main(
            ["--target", "target.py", "--harness", "copilot", "--observe"], repo_root=tmp_path
        )
        assert code == 1
        out = capsys.readouterr().out
        assert "MISMATCH" in out
        assert "missing (static but not observed)" in out
        assert "extra (observed but not static)" in out

    def test_observe_mismatch_via_main_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(tmp_path, "target.py", "x = 1\n")
        entries: list[dict[str, str]] = []

        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(0, stdout=json.dumps(entries))

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        code = ec.main(
            [
                "--target",
                "target.py",
                "--harness",
                "copilot",
                "--observe",
                "--json",
            ],
            repo_root=tmp_path,
        )
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["observe"]["match"] is False
        assert ".github/copilot-instructions.md" in payload["observe"]["missing"]

    def test_normalize_source_path_folds_an_absolute_path_under_repo_root(
        self, tmp_path: Path
    ) -> None:
        absolute = str(tmp_path / "a" / "b.md")
        assert ec._normalize_source_path(tmp_path, absolute) == "a/b.md"

    def test_observe_copilot_unavailable_via_main_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(tmp_path, "target.py", "x = 1\n")

        def _fake_run(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        code = ec.main(
            ["--target", "target.py", "--harness", "copilot", "--observe"], repo_root=tmp_path
        )
        assert code == 3
        assert "not on PATH" in capsys.readouterr().err

    def test_normalize_source_path_falls_back_for_a_path_outside_repo_root(
        self, tmp_path: Path
    ) -> None:
        outside = str(tmp_path.parent / "elsewhere" / "b.md")
        result = ec._normalize_source_path(tmp_path, outside)
        assert result == Path(outside).as_posix()


class TestCli:
    def test_missing_target_and_harness_without_ci_exits_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            ec.main([])
        assert exc_info.value.code == 2

    def test_observe_with_rev_exits_two(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            ec.main(
                [
                    "--target",
                    "scripts/validation/pre_pr.py",
                    "--harness",
                    "copilot",
                    "--observe",
                    "--rev",
                    "HEAD",
                ]
            )
        assert exc_info.value.code == 2

    def test_observe_with_claude_only_exits_two(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            ec.main(
                ["--target", "scripts/validation/pre_pr.py", "--harness", "claude", "--observe"]
            )
        assert exc_info.value.code == 2

    def test_target_outside_repo_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = ec.main(["--target", "../outside.py", "--harness", "claude"])
        assert code == 2
        assert "escapes the repository" in capsys.readouterr().err

    def test_invalid_rev_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = ec.main(
            [
                "--target",
                "scripts/validation/pre_pr.py",
                "--harness",
                "claude",
                "--rev",
                "not-a-rev",
            ]
        )
        assert code == 2
        assert "does not resolve to a commit" in capsys.readouterr().err

    def test_json_output_is_valid_json_with_expected_keys(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = ec.main(
            ["--target", "scripts/validation/pre_pr.py", "--harness", "claude", "--json"]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["target"] == "scripts/validation/pre_pr.py"
        assert payload[0]["harness"] == "claude"
        assert "path_local_bytes" in payload[0]["totals"]

    def test_table_output_runs_for_both_harnesses(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = ec.main(["--target", "scripts/validation/pre_pr.py", "--harness", "both"])
        assert code == 0
        out = capsys.readouterr().out
        assert "== claude ::" in out
        assert "== copilot ::" in out
