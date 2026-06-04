"""Tests for validate_pr_description.py validation logic."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(
    _REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "validate_pr_description.py"
)


def run_validator(*args: str) -> dict[str, object]:
    """Run the validator script and return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # JSON is on stdout, human-readable on stderr
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


class TestConventionalCommit:
    def test_valid_title(self):
        r = run_validator("--title", "feat: Add user authentication", "--body", "Closes #123")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "PASS"

    def test_title_with_scope(self):
        r = run_validator("--title", "fix(auth): Resolve login issue", "--body", "Fixes #456")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "PASS"

    def test_title_with_breaking_change(self):
        r = run_validator("--title", "feat!: Breaking change", "--body", "Closes #1")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "PASS"

    def test_invalid_title(self):
        r = run_validator("--title", "Add new feature", "--body", "Closes #123")
        assert r["Validations"]["ConventionalCommit"]["Status"] == "FAIL"
        assert r["Success"] is False


class TestIssueKeywords:
    def test_closes(self):
        r = run_validator("--title", "feat: X", "--body", "Closes #123")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_fixes(self):
        r = run_validator("--title", "feat: X", "--body", "Fixes #456")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_resolves(self):
        r = run_validator("--title", "feat: X", "--body", "Resolves #789")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_case_insensitive(self):
        r = run_validator("--title", "feat: X", "--body", "closes #100")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_past_tense(self):
        r = run_validator("--title", "feat: X", "--body", "Fixed #200")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_cross_repo(self):
        r = run_validator("--title", "feat: X", "--body", "Closes org/repo#123")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_no_keywords_warns(self):
        r = run_validator("--title", "feat: X", "--body", "No issue reference here")
        assert r["Validations"]["IssueKeywords"]["Status"] == "WARN"

    def test_multiple_keywords(self):
        r = run_validator("--title", "feat: X", "--body", "Closes #1\nFixes #2")
        kw = r["Validations"]["IssueKeywords"]
        assert kw["Status"] == "PASS"
        assert len(kw["Keywords"]) == 2


class TestTemplateCompliance:
    def test_complete_template(self):
        body = (
            "## Summary\n\nAdded auth.\n\n"
            "| Type | Reference |\n|------|--------|\n| **Issue** | Closes #1 |\n\n"
            "## Type of Change\n\n- [x] New feature\n\n"
            "## Changes\n\n- Added OAuth2\n"
        )
        r = run_validator("--title", "feat: Auth", "--body", body)
        assert r["Validations"]["TemplateCompliance"]["Status"] == "PASS"

    def test_missing_sections(self):
        r = run_validator("--title", "feat: X", "--body", "Just a description")
        assert r["Validations"]["TemplateCompliance"]["Status"] == "WARN"


class TestOverall:
    def test_success_with_warnings(self):
        r = run_validator("--title", "feat: Feature", "--body", "Minimal body")
        assert r["Success"] is True
        assert len(r["Warnings"]) > 0

    def test_fail_with_errors(self):
        r = run_validator("--title", "Bad title", "--body", "Closes #123")
        assert r["Success"] is False
        assert len(r["Errors"]) > 0

    def test_fail_on_violation_with_warnings(self):
        """--fail-on-violation promotes warnings to failures (exit code 1)."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Feature", "--body", "Minimal body",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        r = json.loads(result.stdout)
        # Warnings present (no issue keywords, incomplete template)
        assert len(r["Warnings"]) > 0
        # --fail-on-violation should cause non-zero exit even for warnings
        assert result.returncode == 1

    def test_fail_on_violation_with_errors(self):
        """--fail-on-violation returns exit code 1 when errors exist."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "Bad title", "--body", "Closes #123",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        r = json.loads(result.stdout)
        assert r["Success"] is False
        assert result.returncode == 1


class TestInlineCitationStripping:
    """Regression tests for #2252: inline citation cues must not produce false positives.

    A backtick-wrapped file path preceded by a citation cue word (see, per, e.g.,
    for example, as documented in, ...) is a reference, not a change claim, and
    must not be collected by extract_mentioned_files.
    """

    @staticmethod
    def _import_extract():
        import importlib.util
        import sys as _sys
        pr_desc_path = str(
            _REPO_ROOT / "scripts" / "validation" / "pr_description.py"
        )
        spec = importlib.util.spec_from_file_location("pr_desc_mod", pr_desc_path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        _sys.modules["pr_desc_mod"] = mod
        spec.loader.exec_module(mod)
        return mod.extract_mentioned_files

    def test_see_citation_not_collected(self):
        extract = self._import_extract()
        body = "This PR updates the scheduler. See `scripts/foo.py` for prior art."
        assert "scripts/foo.py" not in extract(body)

    def test_per_citation_not_collected(self):
        extract = self._import_extract()
        body = "Exit codes per `scripts/validate_session_json.py` contract."
        assert "scripts/validate_session_json.py" not in extract(body)

    def test_eg_citation_not_collected(self):
        extract = self._import_extract()
        body = (
            "The skill (e.g. `.claude/skills/security-scan/scripts/scan_vulnerabilities.py`)"
            " is not changed."
        )
        assert (
            ".claude/skills/security-scan/scripts/scan_vulnerabilities.py" not in extract(body)
        )

    def test_for_example_citation_not_collected(self):
        extract = self._import_extract()
        body = "For example `docs/retros/INDEX.md` shows the pattern."
        assert "docs/retros/INDEX.md" not in extract(body)

    def test_real_change_claim_list_item_still_collected(self):
        """A list-item change claim must NOT be suppressed by citation stripping."""
        extract = self._import_extract()
        body = "## Changes\n\n- `scripts/foo.py`: Updated scheduler logic\n"
        assert "scripts/foo.py" in extract(body)

    def test_reference_section_still_stripped_independently(self):
        """## References section stripping still works alongside citation cue stripping."""
        extract = self._import_extract()
        body = (
            "## Changes\n\n- `scripts/foo.py`: core change\n\n"
            "## References\n\n`docs/retros/INDEX.md` prior retro\n"
        )
        mentioned = extract(body)
        assert "scripts/foo.py" in mentioned
        assert "docs/retros/INDEX.md" not in mentioned

    def test_from_change_claim_still_collected(self):
        """The word from is a change cue, not a citation cue."""
        extract = self._import_extract()
        body = "Moved logic from `scripts/old.py` to `scripts/new.py`."
        mentioned = extract(body)
        assert "scripts/old.py" in mentioned
        assert "scripts/new.py" in mentioned

    def test_citation_cue_requires_word_boundary(self):
        """Citation cues must not match suffixes of longer words."""
        extract = self._import_extract()
        body = "The proper `scripts/config.py` file is part of this change."
        assert "scripts/config.py" in extract(body)

    def test_citation_cue_does_not_cross_line_boundary(self):
        """A cue on one line must not suppress a claim on the next line."""
        extract = self._import_extract()
        body = "See\n`scripts/next_line.py`: updated validator logic."
        assert "scripts/next_line.py" in extract(body)


def _import_extract_mentioned_files():
    """Load extract_mentioned_files from pr_description.py by path."""
    import importlib.util

    pr_desc_path = str(_REPO_ROOT / "scripts" / "validation" / "pr_description.py")
    spec = importlib.util.spec_from_file_location("pr_desc_link_mod", pr_desc_path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pr_desc_link_mod"] = mod
    spec.loader.exec_module(mod)
    return mod.extract_mentioned_files


class TestMarkdownLinkTargetExtraction:
    """Tests for #2113: markdown link targets [label](path.ext) are extracted.

    Before the fifth FILE_MENTION_PATTERNS entry, only the bracket label
    ([config.json]) was captured. The inline-link target ([text](path.ext))
    was dropped, so a PR body that cited a changed file only as a link target
    escaped the description-vs-diff drift check.
    """

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("Updated [label](config.json) for the gate.", "config.json"),
            (
                "See [the workflow](.github/workflows/ci.yml) for details.",
                ".github/workflows/ci.yml",
            ),
            (
                "Touched [parser](scripts/validation/pr_description.py) here.",
                "scripts/validation/pr_description.py",
            ),
        ],
    )
    def test_link_target_extracted(self, body: str, expected: str):
        extract = _import_extract_mentioned_files()
        assert expected in extract(body)

    def test_label_form_still_extracted(self):
        """The pre-existing [config.json] label form keeps working."""
        extract = _import_extract_mentioned_files()
        body = "The `[config.json]` reference still resolves."
        assert "config.json" in extract(body)

    def test_link_target_respects_double_extension_boundary(self):
        """_EXT_BOUNDARY rejects a backup suffix on a link target."""
        extract = _import_extract_mentioned_files()
        body = "Restored from [backup](path/to/runs.json.bak) earlier."
        mentioned = extract(body)
        assert "runs.json" not in mentioned
        assert "path/to/runs.json.bak" not in mentioned

    def test_link_target_respects_longer_extension_boundary(self):
        """A jsonl link target must not collapse to json (issue #1874 boundary)."""
        extract = _import_extract_mentioned_files()
        body = "Wrote [results](data/runs.jsonl) for analysis."
        assert "data/runs.json" not in extract(body)

    def test_link_target_last_segment_extension_matches(self):
        """A genuine multi-dotted filename whose last segment is a known ext matches."""
        extract = _import_extract_mentioned_files()
        body = "Generated [config](build/tsconfig.spec.json) output."
        assert "build/tsconfig.spec.json" in extract(body)
