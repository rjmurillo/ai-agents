"""Scope, escape hatch, and failure exits for the measurement-anchoring gate (issue #5771).

Scope is the one decision the issue left to evidence. Point-in-time records
(``stale_script_refs.HISTORICAL_ROOTS`` plus episode memory, PR comment
captures, handoffs, incident reviews) and rendered mirrors are out. Every
other tracked Markdown tree stays in, ADRs, specs, plans, metrics, and audits
included: the gate reads only lines a branch adds, so a new count in those
trees is a new claim.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import measurement_claims as claims
from tests.validation.measurement_anchoring_helpers import (
    ANCHORED,
    UNANCHORED,
    _add_doc,
    _repo,
    _run,
    checker,
    cite,
)

OUT_OF_SCOPE = [
    ".project-toolkit/retrospective/2026-01-01-x.md",
    ".project-toolkit/sessions/x.md",
    ".project-toolkit/critique/x.md",
    ".project-toolkit/analysis/x.md",
    ".project-toolkit/qa/x.md",
    ".project-toolkit/audits/x.md",
    ".project-toolkit/memory/episodes/x.md",
    ".project-toolkit/pr-comments/x.md",
    ".project-toolkit/handoffs/x.md",
    ".project-toolkit/incidents/x.md",
    ".agents/archive/x.md",
    ".serena/memories/x.md",
    "src/claude/skills/x/references/y.md",
    "src/codex/skills/x/SKILL.md",
    "src/copilot-cli/instructions/x.instructions.md",
    ".github/instructions/x.instructions.md",
    ".claude/rules/x.md",
    ".claude/agents/x.md",
    ".claude/skills/x/SKILL.md",
    "tests/validation/fixtures/x.md",
    "fixtures/x.md",
    "docs/notes.txt",
    "scripts/tool.py",
]

IN_SCOPE = [
    "README.md",
    "docs/architecture.md",
    "evals/x.md",
    ".project-toolkit/architecture/ADR-999-x.md",
    ".project-toolkit/specs/requirements/REQ-999-x.md",
    ".project-toolkit/plans/x.md",
    ".project-toolkit/metrics/x.md",
    ".project-toolkit/audit/x.md",
    "templates/rules/x.md",
    "templates/skills/x.SKILL.md.tmpl",
    ".claude/skills/x/references/y.md",
]


class TestScope:
    @pytest.mark.parametrize("path", OUT_OF_SCOPE)
    def test_out_of_scope_paths_are_never_read(self, path: str) -> None:
        assert checker.is_out_of_scope(path) is True

    @pytest.mark.parametrize("path", IN_SCOPE)
    def test_in_scope_paths_are_read(self, path: str) -> None:
        assert checker.is_out_of_scope(path) is False

    @pytest.mark.parametrize("path", OUT_OF_SCOPE)
    def test_unanchored_claim_in_an_out_of_scope_path_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], path: str
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, path, f"{UNANCHORED}\n")
        code, out = _run(root, capsys)
        assert code == 0
        assert "examined 0 line(s) across 0 file(s)" in out

    @pytest.mark.parametrize("path", IN_SCOPE)
    def test_unanchored_claim_in_an_in_scope_path_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], path: str
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, path, f"{UNANCHORED}\n")
        code, out = _run(root, capsys)
        assert code == 1
        assert cite(path, 1) in out


class TestIgnoreMarker:
    def test_reasoned_marker_on_the_same_line_exempts_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        text = f"{UNANCHORED} <!-- measurement-anchor: ignore -- worked example -->\n"
        _add_doc(root, "docs/guide.md", text)
        code, _out = _run(root, capsys)
        assert code == 0

    def test_reasoned_marker_on_the_line_above_exempts_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        marker = "<!-- measurement-anchor: ignore -- worked example -->"
        _add_doc(root, "docs/guide.md", f"{marker}\n{UNANCHORED}\n")
        code, _out = _run(root, capsys)
        assert code == 0

    def test_marker_without_a_reason_does_not_exempt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/guide.md", f"<!-- measurement-anchor: ignore -->\n{UNANCHORED}\n")
        code, _out = _run(root, capsys)
        assert code == 1

    def test_marker_two_lines_above_does_not_exempt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        marker = "<!-- measurement-anchor: ignore -- worked example -->"
        _add_doc(root, "docs/guide.md", f"{marker}\nspacer\n{UNANCHORED}\n")
        code, _out = _run(root, capsys)
        assert code == 1

    def test_marker_on_the_first_line_has_no_line_above_to_read(self) -> None:
        assert claims.has_reasoned_ignore(["only line"], 1, "only line") is False
        assert claims.has_reasoned_ignore(None, 1, "only line") is False


class TestFailureExits:
    def test_tracked_path_read_failure_exits_2(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        monkeypatch.setattr(checker, "_head_tracked_paths", lambda _root: None)
        code, _out = _run(root, capsys)
        assert code == 2

    def test_git_show_failure_is_exit_2_not_a_finding(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/guide.md", f"{UNANCHORED}\n")

        def boom(_self: object, path: str) -> list[str]:
            raise checker.HeadReadError(path)

        monkeypatch.setattr(checker._HeadFileCache, "lines", boom)
        code = checker.main(["--repo-root", str(root), "--base", "main"])
        assert code == 2
        assert "git could not read docs/guide.md at HEAD" in capsys.readouterr().err

    def test_main_skips_cleanly_when_no_base_resolves(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: None)
        code = checker.main(["--repo-root", str(root)])
        assert code == 0
        assert "[SKIP]" in capsys.readouterr().out


class TestValidateWrapper:
    def test_skip_without_a_base_ref_passes(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: None)
        assert checker.validate_measurement_anchoring(_repo(tmp_path)) is True
        assert "[SKIP]" in capsys.readouterr().out

    def test_git_failure_returns_false(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: "no-such-ref")
        assert checker.validate_measurement_anchoring(_repo(tmp_path)) is False

    def test_findings_return_false(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/guide.md", f"{UNANCHORED}\n")
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: "main")
        assert checker.validate_measurement_anchoring(root) is False

    def test_clean_branch_returns_true(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/guide.md", f"{ANCHORED}\n")
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: "main")
        assert checker.validate_measurement_anchoring(root) is True
