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

    # Issue #2489 — `.claude/rules/universal.md` MUST-2 permits `Refs #<n>` as a
    # valid issue link for partial-fix PRs. The PR-description gate must accept
    # it as PASS, not WARN, so authors are not pressured to falsely upgrade to
    # `Closes` (the #2481 false-complete-close anti-pattern).
    def test_refs_singular_passes(self):
        r = run_validator("--title", "feat: X", "--body", "Refs #123")
        kw = r["Validations"]["IssueKeywords"]
        assert kw["Status"] == "PASS"
        assert any("Refs #123" in k or "refs #123" in k.lower() for k in kw["Keywords"])

    def test_ref_singular_passes(self):
        r = run_validator("--title", "feat: X", "--body", "Ref #789")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_refs_plural_multiple_passes(self):
        r = run_validator("--title", "feat: X", "--body", "Refs #456 and Refs #457")
        kw = r["Validations"]["IssueKeywords"]
        assert kw["Status"] == "PASS"
        assert len(kw["Keywords"]) == 2

    def test_refs_case_insensitive(self):
        r = run_validator("--title", "feat: X", "--body", "refs #100")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_refs_cross_repo(self):
        r = run_validator("--title", "feat: X", "--body", "Refs org/repo#42")
        assert r["Validations"]["IssueKeywords"]["Status"] == "PASS"

    def test_warn_message_mentions_refs(self):
        # When NO keywords are found the WARN message must list `Refs` alongside
        # `Closes/Fixes/Resolves` so authors of partial-fix PRs see the
        # universal.md MUST-2 option, not just the closing keywords.
        r = run_validator("--title", "feat: X", "--body", "No issue reference here")
        kw = r["Validations"]["IssueKeywords"]
        assert kw["Status"] == "WARN"
        assert "Refs" in kw["Message"]


class TestValidatorMirror:
    """The vendored mirror under ``src/copilot-cli/skills/`` is generated by
    ``build/scripts/generate_skills.py`` from ``.claude/skills/`` and must stay
    byte-identical. If anyone hand-edits one copy without re-running the
    generator (or hand-mirroring) we want to catch the drift here, not in CI."""

    def test_validator_source_and_mirror_are_identical(self):
        src = (
            _REPO_ROOT
            / ".claude"
            / "skills"
            / "github"
            / "scripts"
            / "pr"
            / "validate_pr_description.py"
        ).read_bytes()
        mirror = (
            _REPO_ROOT
            / "src"
            / "copilot-cli"
            / "skills"
            / "github"
            / "scripts"
            / "pr"
            / "validate_pr_description.py"
        ).read_bytes()
        assert src == mirror, (
            "validate_pr_description.py drifted between .claude/skills/ source "
            "and src/copilot-cli/skills/ mirror. Re-run "
            "`python3 build/scripts/generate_skills.py` or mirror the edit by hand."
        )


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

    def test_fail_on_violation_warnings_no_unconditional_pass_message(self):
        """Regression for #2369: must not print 'Validation passed' while exiting 1.

        Under --fail-on-violation with warnings (and no errors), the validator
        previously printed '✓ Validation passed' on stderr while exiting 1,
        producing a contradictory signal. The fix:
          - Suppresses the success message when warnings are fatal.
          - Surfaces an explicit failure summary.
          - Exposes EffectiveSuccess/WarningsAreFatal/FailOnViolation in JSON.
        """
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Feature", "--body", "Minimal body",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        r = json.loads(result.stdout)
        assert result.returncode == 1
        assert len(r["Warnings"]) > 0
        # Hard-fail invariant: never print the unconditional pass banner when
        # the process exits nonzero.
        assert "Validation passed" not in result.stderr, (
            "Validator must not claim 'Validation passed' while exiting nonzero "
            f"(stderr was:\n{result.stderr})"
        )
        # New JSON fields make fatality policy visible to automation.
        assert r["FailOnViolation"] is True
        assert r["WarningsAreFatal"] is True
        assert r["EffectiveSuccess"] is False
        assert r["Success"] is True  # no hard errors
        assert r["WarningCount"] == len(r["Warnings"])
        # Human output must explain WHY this failed.
        assert "warnings are fatal" in result.stderr.lower()

    def test_default_mode_warnings_still_pass(self):
        """Without --fail-on-violation, warnings remain advisory and exit is 0."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Feature", "--body", "Minimal body"],
            capture_output=True, text=True, timeout=30,
        )
        r = json.loads(result.stdout)
        assert result.returncode == 0
        assert r["FailOnViolation"] is False
        assert r["WarningsAreFatal"] is False
        assert r["EffectiveSuccess"] is True
        assert "Validation passed" in result.stderr
        assert "warnings are advisory" in result.stderr.lower()

    def test_fail_on_violation_no_warnings_passes(self):
        """--fail-on-violation with a fully clean body still exits 0 and reports pass."""
        body = (
            "## Summary\n\nAdded auth.\n\n"
            "| Type | Reference |\n|------|--------|\n| **Issue** | Closes #1 |\n\n"
            "## Type of Change\n\n- [x] New feature\n\n"
            "## Changes\n\n- Added OAuth2\n"
        )
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Auth", "--body", body,
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        r = json.loads(result.stdout)
        assert result.returncode == 0
        assert r["EffectiveSuccess"] is True
        assert r["WarningsAreFatal"] is False
        assert "Validation passed" in result.stderr

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


class TestExitMessageMatchesExitCode:
    """Regression tests for #2369: the printed summary must agree with the exit code.

    The validator printed 'Validation passed' to stderr whenever no errors
    existed, even when --fail-on-violation promoted warnings to violations and
    the process exited 1. The summary and the exit code must never disagree.
    """

    def test_passed_not_printed_when_warnings_are_fatal(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Feature", "--body", "Minimal body",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 1
        assert "Validation passed" not in result.stderr

    def test_warning_fatal_message_present_when_warnings_are_fatal(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Feature", "--body", "Minimal body",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 1
        assert "Validation failed" in result.stderr
        assert "treated as violations" in result.stderr

    def test_passed_printed_in_default_mode_with_warnings(self):
        """Without --fail-on-violation, warnings are non-fatal: exit 0, pass message."""
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "feat: Feature", "--body", "Minimal body"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "Validation passed" in result.stderr

    def test_passed_not_printed_when_errors_are_fatal(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "Bad title", "--body", "Closes #123",
             "--fail-on-violation"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 1
        assert "Validation passed" not in result.stderr


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

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/org/repo/blob/main/scripts/validator.py",
            "http://example.com/config.json",
            "ftp://example.com/files/workflow.yml",
            "//example.com/static/app.js",
            "www.example.com/docs/readme.md",
        ],
    )
    def test_link_target_ignores_external_urls(self, url: str):
        """External URLs ending in known extensions are not repo file mentions."""
        extract = _import_extract_mentioned_files()
        body = f"Check [the linked file]({url}) for details."
        assert url not in extract(body)
        assert Path(url).name not in extract(body)
