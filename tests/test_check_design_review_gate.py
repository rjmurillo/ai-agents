"""Tests for check_design_review_gate.py."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("check_design_review_gate")
extract_verdict = _mod.extract_verdict
check_review_file = _mod.check_review_file
run_gate = _mod.run_gate
parse_yaml_frontmatter = _mod.parse_yaml_frontmatter
BLOCKING_VERDICTS = _mod.BLOCKING_VERDICTS
PASSING_VERDICTS = _mod.PASSING_VERDICTS


# ---------------------------------------------------------------------------
# parse_yaml_frontmatter
# ---------------------------------------------------------------------------


class TestParseYamlFrontmatter:
    def test_valid_frontmatter(self):
        content = "---\nstatus: complete\nreviewer: architect\n---\n# Title"
        result = parse_yaml_frontmatter(content)
        assert result["status"] == "complete"
        assert result["reviewer"] == "architect"

    def test_no_frontmatter(self):
        content = "# Title\n\nSome content"
        assert parse_yaml_frontmatter(content) == {}

    def test_frontmatter_not_at_start(self):
        content = "\n---\nstatus: complete\n---"
        assert parse_yaml_frontmatter(content) == {}


# ---------------------------------------------------------------------------
# extract_verdict
# ---------------------------------------------------------------------------


class TestExtractVerdict:
    def test_yaml_frontmatter_status(self):
        content = "---\nstatus: complete\n---\n# Review"
        assert extract_verdict(content) == "COMPLETE"

    def test_markdown_verdict_with_brackets(self):
        content = "# Review\n\n**Verdict**: [PASS] - Good work"
        assert extract_verdict(content) == "PASS"

    def test_markdown_verdict_without_brackets(self):
        content = "# Review\n\n**Verdict**: NEEDS_CHANGES"
        assert extract_verdict(content) == "NEEDS_CHANGES"

    def test_markdown_status_field(self):
        content = "# Review\n\n**Status**: APPROVED with recommendations"
        assert extract_verdict(content) == "APPROVED"

    def test_uppercase_verdict(self):
        content = "# Review\n\n**VERDICT**: PASS"
        assert extract_verdict(content) == "PASS"

    def test_verdict_concerns(self):
        content = "**Verdict**: CONCERNS (P0: 1, P1: 8)"
        assert extract_verdict(content) == "CONCERNS"

    def test_verdict_needs_adr(self):
        content = "**Verdict**: NEEDS_ADR (with conditional APPROVE)"
        assert extract_verdict(content) == "NEEDS_ADR"

    def test_no_verdict_found(self):
        content = "# Review\n\nNo verdict here."
        assert extract_verdict(content) == ""

    def test_status_with_bracket_format(self):
        content = "**Status**: [PASS]"
        assert extract_verdict(content) == "PASS"

    def test_status_warning_bracket(self):
        content = "**Status**: [WARNING] - Conditional approval"
        assert extract_verdict(content) == "WARNING"


# ---------------------------------------------------------------------------
# check_review_file
# ---------------------------------------------------------------------------


class TestCheckReviewFile:
    def test_blocking_verdict(self, tmp_path):
        review = tmp_path / "DESIGN-REVIEW-test.md"
        review.write_text("# Review\n\n**Verdict**: NEEDS_CHANGES\n")
        result = check_review_file(str(review))
        assert result.is_blocking is True
        assert result.verdict == "NEEDS_CHANGES"

    def test_passing_verdict(self, tmp_path):
        review = tmp_path / "DESIGN-REVIEW-test.md"
        review.write_text("# Review\n\n**Verdict**: [PASS]\n")
        result = check_review_file(str(review))
        assert result.is_blocking is False
        assert result.verdict == "PASS"

    def test_fail_verdict_blocks(self, tmp_path):
        review = tmp_path / "DESIGN-REVIEW-test.md"
        review.write_text("# Review\n\n**Status**: [FAIL]\n")
        result = check_review_file(str(review))
        assert result.is_blocking is True
        assert result.verdict == "FAIL"

    def test_rejected_verdict_blocks(self, tmp_path):
        review = tmp_path / "DESIGN-REVIEW-test.md"
        review.write_text("# Review\n\n**Verdict**: REJECTED\n")
        result = check_review_file(str(review))
        assert result.is_blocking is True
        assert result.verdict == "REJECTED"


# ---------------------------------------------------------------------------
# run_gate
# ---------------------------------------------------------------------------


class TestRunGate:
    def _setup_reviews(self, tmp_path, reviews: dict[str, str]) -> str:
        """Create design review files in a temp directory structure."""
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        for name, content in reviews.items():
            (arch_dir / f"DESIGN-REVIEW-{name}.md").write_text(content)
        return str(tmp_path)

    def test_no_review_files_passes(self, tmp_path):
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        output = io.StringIO()
        rc = run_gate(str(tmp_path), output=output)
        assert rc == 0
        assert "No design review files found" in output.getvalue()

    def test_all_passing_reviews(self, tmp_path):
        base = self._setup_reviews(tmp_path, {
            "alpha": "**Verdict**: [PASS]\n",
            "beta": "**Status**: APPROVED\n",
        })
        output = io.StringIO()
        rc = run_gate(base, output=output)
        assert rc == 0
        assert "All design reviews pass" in output.getvalue()

    def test_one_blocking_review_fails(self, tmp_path):
        base = self._setup_reviews(tmp_path, {
            "alpha": "**Verdict**: [PASS]\n",
            "beta": "**Verdict**: NEEDS_CHANGES\n",
        })
        output = io.StringIO()
        rc = run_gate(base, output=output)
        assert rc == 1
        assert "1 blocking review(s) found" in output.getvalue()

    def test_multiple_blocking_reviews(self, tmp_path):
        base = self._setup_reviews(tmp_path, {
            "alpha": "**Verdict**: NEEDS_CHANGES\n",
            "beta": "**Verdict**: REJECTED\n",
            "gamma": "**Verdict**: [PASS]\n",
        })
        output = io.StringIO()
        rc = run_gate(base, output=output)
        assert rc == 1
        assert "2 blocking review(s) found" in output.getvalue()

    def test_concerns_verdict_passes(self, tmp_path):
        base = self._setup_reviews(tmp_path, {
            "alpha": "**Verdict**: CONCERNS\n",
        })
        output = io.StringIO()
        rc = run_gate(base, output=output)
        assert rc == 0

    def test_yaml_frontmatter_blocking(self, tmp_path):
        base = self._setup_reviews(tmp_path, {
            "alpha": "---\nstatus: NEEDS_CHANGES\n---\n# Review\n",
        })
        output = io.StringIO()
        rc = run_gate(base, output=output)
        assert rc == 1

    def test_yaml_frontmatter_passing(self, tmp_path):
        base = self._setup_reviews(tmp_path, {
            "alpha": "---\nstatus: complete\n---\n# Review\n",
        })
        output = io.StringIO()
        rc = run_gate(base, output=output)
        assert rc == 0

    def test_github_output_written(self, tmp_path, monkeypatch):
        output_file = tmp_path / "github_output"
        output_file.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        base = self._setup_reviews(tmp_path, {
            "alpha": "**Verdict**: NEEDS_CHANGES\n",
        })
        run_gate(base, output=io.StringIO())

        outputs = output_file.read_text()
        assert "gate_result=FAIL" in outputs
        assert "blocking_count=1" in outputs


# ---------------------------------------------------------------------------
# Blocking verdict set completeness
# ---------------------------------------------------------------------------


class TestVerdictSets:
    def test_blocking_verdicts_are_disjoint_from_passing(self):
        assert BLOCKING_VERDICTS.isdisjoint(PASSING_VERDICTS)

    @pytest.mark.parametrize("verdict", sorted(BLOCKING_VERDICTS))
    def test_each_blocking_verdict_detected(self, verdict, tmp_path):
        review = tmp_path / "review.md"
        review.write_text(f"**Verdict**: {verdict}\n")
        result = check_review_file(str(review))
        assert result.is_blocking is True
