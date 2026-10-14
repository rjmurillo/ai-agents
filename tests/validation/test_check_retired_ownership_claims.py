"""Tests for scripts/validation/check_retired_ownership_claims.py.

Issue #5788: ADR-109 B1 made every agent copy generated output, and the sibling
docs, rule text, and generator docstrings kept calling them hand-maintained.
This guard is what makes that loud. Its tests drive ``main(argv)`` and assert on
the integer it returns, per .claude/rules/testing.md MUST 8: a helper that
returns a findings list proves the helper detected the problem and proves nothing
about whether the program fails.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.check_retired_ownership_claims import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_VIOLATION,
    RETIRED_CLAIMS,
    find_retired_claims,
    main,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

checks_spec = importlib.import_module("checks_spec")

# (claim name, file the claim is scoped to, a line that was true before ADR-109).
_RETIRED_LINES: tuple[tuple[str, str, str], ...] = (
    (
        "hand-maintained agent tree",
        "templates/rules/templates.md",
        "`src/claude/`, `.claude/agents/`, and `.github/agents/` are hand-maintained copies.",
    ),
    (
        "hand-maintained agent tree",
        "build/scripts/validate_agent_matrix_refs.py",
        "  .github/agents/         hand-maintained Copilot copy",
    ),
    (
        "hand-maintained agent tree",
        "build/scripts/detect_agent_drift.py",
        "Issue #2267: `.claude/agents` is one of the hand-maintained copies.",
    ),
    (
        "no generator writes the agent trees",
        "templates/README.md",
        "The install copies are hand-written: no generator writes them.",
    ),
    (
        "flat agent path",
        "docs/customization.md",
        "Create a plain markdown file at `src/claude/<agent-name>.md`.",
    ),
    (
        "flat agent path",
        ".agents/AGENT-SYSTEM.md",
        "**File**: `src/claude/orchestrator.md`",
    ),
    (
        "flat agent path",
        "docs/ideation-workflow.md",
        "- [Analyst Agent](../src/claude/analyst.md)",
    ),
    (
        "rule source is the install copy",
        ".agents/governance/GENERATOR-FILES.md",
        "| `build/scripts/generate_rules.py` | `.claude/rules/*.md` | `.github/instructions/` |",
    ),
    (
        "drift allowlist size as a count",
        "templates/rules/templates.md",
        "It scores two pairs over an 18-section allowlist.",
    ),
    (
        "PowerShell scripts README",
        "scripts/README.md",
        "PowerShell scripts for the AI Agents system.",
    ),
    (
        "PowerShell scripts README",
        "scripts/README.md",
        "Invoke-Pester -Path .\\tests",
    ),
    (
        "untracked claude-mem tooling",
        ".claude-mem/memories/README.md",
        "pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1",
    ),
    (
        "untracked claude-mem tooling",
        ".claude-mem/memories/README.md",
        'npx tsx scripts/export-memories.ts "session 229" out.json',
    ),
)


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _add(repo: Path, relative: str, body: str) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "--", relative], cwd=repo, check=True)
    return path


class TestRetiredClaimTable:
    def test_every_claim_has_a_case_below(self) -> None:
        """A claim added to the table without a positive case below is untested."""
        covered = {name for name, _, _ in _RETIRED_LINES}

        assert {claim.name for claim in RETIRED_CLAIMS} == covered

    def test_claim_names_are_unique(self) -> None:
        names = [claim.name for claim in RETIRED_CLAIMS]

        assert len(names) == len(set(names))


class TestFindRetiredClaims:
    def test_an_empty_repo_has_no_findings(self, tmp_path: Path) -> None:
        assert find_retired_claims(_git_repo(tmp_path)) == []

    @pytest.mark.parametrize(("name", "path", "line"), _RETIRED_LINES)
    def test_each_retired_line_is_found_at_its_line_number(
        self, tmp_path: Path, name: str, path: str, line: str
    ) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, path, f"# Heading\n\n{line}\n")

        findings = find_retired_claims(repo)

        assert [(f.path, f.line, f.claim.name) for f in findings] == [(path, 3, name)]

    @pytest.mark.parametrize(
        "line",
        [
            "No agent copy is hand-maintained: `.claude/agents/` is generated.",
            "`.github/agents/` is generated output, not hand-maintained.",
            "Since ADR-109 B1 no shared-agent copy is hand-maintained: `src/claude/agents/X.md`",
            "Never call `src/claude/agents/` hand-maintained.",
        ],
    )
    def test_a_correction_is_not_the_retired_claim(self, tmp_path: Path, line: str) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, "templates/rules/templates.md", f"{line}\n")

        assert find_retired_claims(repo) == []

    def test_a_hand_maintained_reference_copy_under_the_agent_dir_is_not_the_claim(
        self, tmp_path: Path
    ) -> None:
        """Security references under .github/agents/ are a real hand-maintained byte copy."""
        repo = _git_repo(tmp_path)
        _add(
            repo,
            ".agents/governance/GENERATOR-FILES.md",
            "| `security-references` | `.github/agents/security/references/*.md` | "
            "`derived` | `check_surface_parity.py` (hand-maintained byte copy) | - | - |\n",
        )

        assert find_retired_claims(repo) == []

    def test_hand_maintained_without_an_agent_tree_is_not_the_claim(self, tmp_path: Path) -> None:
        """Skill scripts and references are still hand-maintained (ADR-108)."""
        repo = _git_repo(tmp_path)
        _add(
            repo,
            "templates/rules/claude-agents.md",
            "Scripts stay hand-maintained at `.claude/skills/<name>/`.\n",
        )

        assert find_retired_claims(repo) == []

    @pytest.mark.parametrize(
        "line",
        [
            "Agents render to `src/claude/agents/orchestrator.md`.",
            "Rules render to `src/claude/rules/universal.md`.",
            "See `src/claude/AGENTS.md` for the plugin guide.",
            "Glob `src/claude/**/*.md` covers the plugin tree.",
        ],
    )
    def test_a_current_path_is_not_a_flat_agent_path(self, tmp_path: Path, line: str) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, "docs/guide.md", f"{line}\n")

        assert find_retired_claims(repo) == []

    def test_a_claim_outside_its_scope_is_ignored(self, tmp_path: Path) -> None:
        """The README rule is scoped to scripts/README.md, not every Markdown file."""
        repo = _git_repo(tmp_path)
        _add(repo, "docs/history.md", "Invoke-Pester -Path .\\tests\n")

        assert find_retired_claims(repo) == []

    def test_a_glob_star_does_not_cross_a_directory(self, tmp_path: Path) -> None:
        """``docs/*.md`` names the docs directory only; a subdirectory is history."""
        repo = _git_repo(tmp_path)
        _add(repo, "docs/archive/old.md", "Create `src/claude/<agent-name>.md`.\n")

        assert find_retired_claims(repo) == []

    def test_an_untracked_file_is_not_shipped(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path)
        scratch = repo / "docs" / "scratch.md"
        scratch.parent.mkdir(parents=True)
        scratch.write_text("Create `src/claude/<agent-name>.md`.\n", encoding="utf-8")

        assert find_retired_claims(repo) == []

    def test_a_staged_file_is_scanned(self, tmp_path: Path) -> None:
        """The next commit ships a staged file, so it must fail now."""
        repo = _git_repo(tmp_path)
        _add(repo, "docs/guide.md", "Create `src/claude/<agent-name>.md`.\n")

        assert len(find_retired_claims(repo)) == 1

    def test_a_binary_file_in_scope_is_skipped(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path)
        path = repo / "docs" / "blob.md"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
        subprocess.run(["git", "add", "--", "docs/blob.md"], cwd=repo, check=True)

        assert find_retired_claims(repo) == []

    def test_a_tracked_file_deleted_from_disk_is_skipped(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path)
        path = _add(repo, "docs/guide.md", "Create `src/claude/<agent-name>.md`.\n")
        path.unlink()

        assert find_retired_claims(repo) == []

    def test_two_claims_on_one_line_report_both(self, tmp_path: Path) -> None:
        repo = _git_repo(tmp_path)
        _add(
            repo,
            "templates/rules/templates.md",
            "`.claude/agents/` is hand-maintained, edit `src/claude/<agent>.md`.\n",
        )

        names = sorted(f.claim.name for f in find_retired_claims(repo))

        assert names == ["flat agent path", "hand-maintained agent tree"]


class TestMain:
    def test_a_clean_repo_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, "docs/guide.md", "Agents render to `src/claude/agents/analyst.md`.\n")

        assert main(["--repo-root", str(repo)]) == EXIT_OK
        assert "No retired ownership claims" in capsys.readouterr().out

    def test_a_retired_claim_exits_one_and_names_file_line_and_fix(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _git_repo(tmp_path)
        doc_path = "docs/guide.md"
        _add(repo, doc_path, "Intro\nCreate `src/claude/<agent-name>.md`.\n")

        assert main(["--repo-root", str(repo)]) == EXIT_VIOLATION

        err = capsys.readouterr().err
        assert f"{doc_path}:2: flat agent path" in err
        assert "src/claude/agents/<stem>.md" in err

    def test_a_missing_repo_root_exits_two(self, tmp_path: Path) -> None:
        assert main(["--repo-root", str(tmp_path / "absent")]) == EXIT_CONFIG

    def test_a_directory_that_is_not_a_git_repo_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--repo-root", str(tmp_path)]) == EXIT_CONFIG
        assert "git ls-files failed" in capsys.readouterr().err

    def test_the_default_repo_root_is_the_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _git_repo(tmp_path)
        _add(repo, "docs/guide.md", "Create `src/claude/<agent-name>.md`.\n")
        monkeypatch.chdir(repo)

        assert main([]) == EXIT_VIOLATION


def test_running_the_file_as_a_script_returns_the_exit_code(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    doc_path = "docs/guide.md"
    _add(repo, doc_path, "Create `src/claude/<agent-name>.md`.\n")
    script = _REPO_ROOT / "scripts" / "validation" / "check_retired_ownership_claims.py"

    result = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == EXIT_VIOLATION
    assert f"{doc_path}:1: flat agent path" in result.stderr


def test_the_live_tree_repeats_no_retired_claim() -> None:
    """The checked-in docs and docstrings agree with ADR-109 today."""
    assert main(["--repo-root", str(_REPO_ROOT)]) == EXIT_OK


class TestPrePrWrapper:
    """``validate_retired_ownership_claims`` is the pre-PR gate around the script."""

    def test_exit_one_fails_the_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            checks_spec,
            "_run_subprocess",
            lambda *_args, **_kwargs: (1, "", "1 retired ownership claim(s) found:"),
        )

        assert checks_spec.validate_retired_ownership_claims(_REPO_ROOT) is False

    def test_exit_two_fails_the_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            checks_spec, "_run_subprocess", lambda *_args, **_kwargs: (2, "", "Not a directory")
        )

        assert checks_spec.validate_retired_ownership_claims(_REPO_ROOT) is False

    def test_exit_zero_passes_the_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            checks_spec,
            "_run_subprocess",
            lambda *_args, **_kwargs: (0, "No retired ownership claims", ""),
        )

        assert checks_spec.validate_retired_ownership_claims(_REPO_ROOT) is True

    def test_a_silent_script_still_passes_on_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            checks_spec, "_run_subprocess", lambda *_args, **_kwargs: (0, None, None)
        )

        assert checks_spec.validate_retired_ownership_claims(_REPO_ROOT) is True

    def test_a_repo_without_the_script_is_skipped(self, tmp_path: Path) -> None:
        with pytest.raises(checks_spec.MissingScriptSkip):
            checks_spec.validate_retired_ownership_claims(tmp_path)
