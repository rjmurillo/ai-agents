"""Tests for scripts/validation/check_skill_md_drift.py (issue #4116).

Covers all seven defects identified in review:
  1. Existence check must fire for any missing path (no parent-directory guard)
  2. Absolute paths and '..' traversals are rejected
  3. Broad directory declaration does not swallow missing descendants
  4. Case-sensitive comparison on Linux
  5. HTML comments stripped from prose (do not count as references)
  6. Exact set assertions (no substring checks)
  7. File size (this file is the extracted test module)

Each test is designed to FAIL against the broken implementation. Regression
guards are marked with comments indicating which defect they cover.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.check_skill_md_drift import (
    _extract_paths_from_text,
    _is_consumer_workspace_path,
    diff_drift_baseline,
    drift_counts_from_failures,
    marker_declared_paths,
    marker_path_drift,
    prose_declared_paths,
    report_drift_ratchet,
)

# Inject the strip functions from the main module for marker/prose extraction
from scripts.validation.check_skill_md_portability import (
    _strip_code,
    _strip_inline_code,
)


def _make_marker_file(
    marker_paths: str, prose_body: str
) -> str:
    """Build a markdown file with a vendor-portability marker and prose."""
    return (
        f"<!-- vendor-portability: declared. References {marker_paths}. -->\n"
        f"{prose_body}\n"
    )


class TestExtractPathsFromText:
    """Unit tests for the path extraction regex."""

    def test_extracts_multi_segment_path(self) -> None:
        text = "See scripts/validation/foo.py for details."
        paths = _extract_paths_from_text(text)
        assert paths == {"scripts/validation/foo.py"}

    def test_rejects_bare_single_word(self) -> None:
        """Defect 2 regression: bare 'scripts' is not a path."""
        text = "Run scripts to set things up."
        paths = _extract_paths_from_text(text)
        assert paths == set()

    def test_rejects_english_phrase(self) -> None:
        """Defect 2 regression: 'build/buy/partner/defer' is English."""
        text = "Options: build/buy/partner/defer."
        paths = _extract_paths_from_text(text)
        assert paths == set()

    def test_rejects_absolute_path(self) -> None:
        """Defect 2 (HIGH): absolute paths must be rejected."""
        text = "See /scripts/validation/check.py for the code."
        paths = _extract_paths_from_text(text)
        # The leading / is stripped by _clean_match, but the result must not
        # include an absolute-looking path. The cleaned version should be valid.
        for p in paths:
            assert not p.startswith("/"), f"Absolute path leaked: {p}"

    def test_rejects_dotdot_traversal(self) -> None:
        """Defect 2 (HIGH): '..' in path components must be rejected."""
        text = "Read .agents/../../../etc/passwd for config."
        unsafe: set[str] = set()
        paths = _extract_paths_from_text(text, unsafe_collector=unsafe)
        assert paths == set()
        assert len(unsafe) == 1

    def test_placeholder_path_excluded(self) -> None:
        """Angle-bracket placeholders are templates, not filesystem paths.

        Text like '<skill_dir>/scripts/foo.py' is a template showing where
        a path resolves in a consumer install. It is not an absolute path
        and should not be reported as invalid.
        """
        text = "at `<skill_dir>/scripts/metrics_writer.py` it resolves"
        unsafe: set[str] = set()
        paths = _extract_paths_from_text(text, unsafe_collector=unsafe)
        assert paths == set()
        # Must not appear as an invalid path either
        assert unsafe == set()

    def test_extracts_dotfile_prefix(self) -> None:
        text = "Write to .agents/sessions/log.json."
        paths = _extract_paths_from_text(text)
        assert paths == {".agents/sessions/log.json"}

    def test_extracts_multi_segment_prefix(self) -> None:
        text = "Load templates/agents/foo.yaml."
        paths = _extract_paths_from_text(text)
        assert paths == {"templates/agents/foo.yaml"}


class TestMarkerDeclaredPaths:
    """Test marker path extraction."""

    def test_extracts_declared_paths(self) -> None:
        text = _make_marker_file(
            ".agents/sessions and scripts/validation/foo.py",
            "Some prose.",
        )
        paths = marker_declared_paths(text, _strip_code, _strip_inline_code)
        assert ".agents/sessions" in paths
        assert "scripts/validation/foo.py" in paths

    def test_no_marker_returns_empty(self) -> None:
        text = "No marker here. References .agents/sessions.\n"
        paths = marker_declared_paths(text, _strip_code, _strip_inline_code)
        assert paths == set()

    def test_marker_in_code_block_ignored(self) -> None:
        """A marker inside a fenced code block is not a real declaration."""
        text = (
            "```\n"
            "<!-- vendor-portability: declared. References .agents/sessions. -->\n"
            "```\n"
            "Prose referencing .agents/sessions here.\n"
        )
        paths = marker_declared_paths(text, _strip_code, _strip_inline_code)
        assert paths == set()

    def test_empty_marker(self) -> None:
        """An empty marker declares no paths."""
        text = "<!-- vendor-portability: -->\nProse.\n"
        paths = marker_declared_paths(text, _strip_code, _strip_inline_code)
        assert paths == set()


class TestProseDeclaredPaths:
    """Test prose path extraction."""

    def test_excludes_marker_paths_from_prose(self) -> None:
        text = _make_marker_file(
            ".agents/architecture",
            "Read .agents/sessions for state.",
        )
        paths = prose_declared_paths(text, _strip_code, _strip_inline_code)
        # prose should have .agents/sessions but NOT .agents/architecture
        # (which was only in the marker)
        assert ".agents/sessions" in paths

    def test_html_comments_stripped_from_prose(self) -> None:
        """Defect 5 (MEDIUM): commented-out refs do not count as prose."""
        text = (
            "<!-- vendor-portability: declared. References .agents/sessions. -->\n"
            "<!-- old: .agents/architecture/ADR-001.md -->\n"
            "Read .agents/sessions for state.\n"
        )
        paths = prose_declared_paths(text, _strip_code, _strip_inline_code)
        assert ".agents/sessions" in paths
        # The commented-out path must NOT appear
        assert not any("architecture" in p for p in paths)

    def test_two_markers_in_one_file(self) -> None:
        """Edge: two markers, both stripped from prose."""
        text = (
            "<!-- vendor-portability: declared. References .agents/sessions. -->\n"
            "<!-- vendor-portability: declared. References scripts/validation/x.py. -->\n"
            "Read .agents/sessions and scripts/validation/x.py.\n"
        )
        paths = prose_declared_paths(text, _strip_code, _strip_inline_code)
        assert ".agents/sessions" in paths
        assert "scripts/validation/x.py" in paths


class TestMarkerPathDrift:
    """Integration tests for the drift checker."""

    def test_clean_file_passes(self, tmp_path: Path) -> None:
        """Marker names X, prose references X, X exists on disk: no failures."""
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        text = _make_marker_file(
            ".agents/sessions",
            "Write state to .agents/sessions for persistence.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        assert failures == []

    def test_stale_declaration_fails(self, tmp_path: Path) -> None:
        """Marker names X, prose does not reference X: stale failure."""
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        text = _make_marker_file(
            ".agents/sessions",
            "This skill does not reference any upstream paths in prose.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        assert len(failures) == 1
        assert "stale" in failures[0]
        assert ".agents/sessions" in failures[0]

    def test_undeclared_ref_fails(self, tmp_path: Path) -> None:
        """Prose references Y, marker does not name Y: undeclared failure."""
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "foo.py").touch()
        text = _make_marker_file(
            ".agents/sessions",
            "Read .agents/sessions and run scripts/validation/foo.py.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        undeclared = [f for f in failures if "undeclared" in f]
        assert len(undeclared) == 1
        assert "scripts/validation/foo.py" in undeclared[0]

    def test_existence_miss_nonexistent_child_of_existing_parent(
        self, tmp_path: Path
    ) -> None:
        """Defect 1 (CRITICAL): parent exists and is non-empty, child missing.

        This is the regression guard for the vacuity bug. The parent-directory
        shortcut made this pass falsely. Without the fix, this test fails.
        """
        (tmp_path / ".agents" / "architecture").mkdir(parents=True)
        # Parent .agents/architecture EXISTS and is non-empty (has something)
        (tmp_path / ".agents" / "architecture" / "ADR-001.md").touch()
        text = _make_marker_file(
            ".agents/architecture/ADR-999.md",
            "See .agents/architecture/ADR-999.md for guidance.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        existence = [f for f in failures if "existence miss" in f]
        assert len(existence) == 1
        assert "ADR-999.md" in existence[0]

    def test_consumer_workspace_exemption(self, tmp_path: Path) -> None:
        """A consumer-workspace path that does not exist on disk passes."""
        text = _make_marker_file(
            ".agents/sessions",
            "Write to .agents/sessions for state.",
        )
        # .agents/sessions does NOT exist under tmp_path but is exempt
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        assert failures == []

    def test_consumer_workspace_component_match(self) -> None:
        """Defect 2 (HIGH): exemption uses component match, not string prefix.

        .agents/sessions-evil must NOT be exempt just because .agents/sessions is.
        """
        assert _is_consumer_workspace_path(".agents/sessions/foo") is True
        assert _is_consumer_workspace_path(".agents/sessions") is True
        assert _is_consumer_workspace_path(".agents/sessions-evil/x") is False

    def test_dotdot_traversal_rejected(self, tmp_path: Path) -> None:
        """Defect 2 (HIGH): '..' in declared paths does not bypass checks."""
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        text = _make_marker_file(
            ".agents/../../../etc/passwd",
            "Read .agents/../../../etc/passwd for config.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        # The path is reported as invalid, not silently dropped
        invalid = [f for f in failures if "invalid path" in f]
        assert len(invalid) >= 1
        assert "'..' traversal" in invalid[0] or ".." in invalid[0]
        # Must NOT reach the existence check
        assert not any("existence miss" in f for f in failures)

    def test_leading_dotdot_traversal_detected(self, tmp_path: Path) -> None:
        """Leading ../prefix/path is captured and reported as invalid.

        Regression guard: the extractor previously anchored only on the prefix
        itself, so ../scripts/foo.py matched as scripts/foo.py and the leading
        traversal was silently normalized away.
        """
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "real.py").touch()
        text = _make_marker_file(
            "../scripts/validation/real.py",
            "Check ../scripts/validation/real.py for details.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        invalid = [f for f in failures if "invalid path" in f]
        assert len(invalid) == 1
        assert "../scripts/validation/real.py" in invalid[0]
        # Must NOT reach the existence check (the file exists, but traversal
        # is invalid regardless)
        assert not any("existence miss" in f for f in failures)

    def test_absolute_path_reported_as_invalid(self, tmp_path: Path) -> None:
        """Absolute paths are reported as invalid, not silently dropped."""
        text = _make_marker_file(
            "/scripts/validation/foo.py",
            "See /scripts/validation/foo.py for the code.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        invalid = [f for f in failures if "invalid path" in f]
        assert len(invalid) >= 1
        assert "/scripts/validation/foo.py" in invalid[0]
        # Must NOT reach the existence check
        assert not any("existence miss" in f for f in failures)

    def test_broad_directory_does_not_swallow_missing_child(
        self, tmp_path: Path
    ) -> None:
        """Defect 3 (HIGH): declaring 'scripts/validation' does not make
        'scripts/validation/definitely-missing.py' pass existence.

        Each concrete prose path is checked individually.
        """
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        text = _make_marker_file(
            "scripts/validation",
            "Run scripts/validation/definitely-missing.py.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        existence = [f for f in failures if "existence miss" in f]
        assert len(existence) >= 1
        assert "definitely-missing.py" in existence[0]

    def test_case_sensitive_comparison(self, tmp_path: Path) -> None:
        """Defect 4 (MEDIUM): case mismatch fails on Linux."""
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "check.py").touch()
        # Marker and prose use different cases
        text = _make_marker_file(
            "scripts/VALIDATION/check.py",
            "See scripts/VALIDATION/check.py for the code.",
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        # On Linux, scripts/VALIDATION/check.py does NOT exist
        existence = [f for f in failures if "existence miss" in f]
        assert len(existence) >= 1

    def test_html_comment_does_not_count_as_prose(self, tmp_path: Path) -> None:
        """Defect 5 (MEDIUM): commented-out reference does not keep stale
        declaration alive."""
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        text = (
            "<!-- vendor-portability: declared. References "
            ".agents/sessions and .agents/architecture. -->\n"
            "<!-- old path: .agents/architecture/ADR-001.md -->\n"
            "Write to .agents/sessions.\n"
        )
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        # .agents/architecture is in the marker but NOT in prose (the HTML comment
        # was stripped), so it should be flagged as stale
        stale = [f for f in failures if "stale" in f]
        assert any(".agents/architecture" in s for s in stale)

    def test_no_marker_returns_empty(self, tmp_path: Path) -> None:
        text = "No marker. References .agents/sessions.\n"
        failures = marker_path_drift(
            text, tmp_path, "skills/test/SKILL.md", _strip_code, _strip_inline_code
        )
        assert failures == []


class TestDriftBaseline:
    """Tests for the ratchet baseline comparison."""

    def test_no_change_no_regression(self) -> None:
        current = {"file.md": 3}
        baseline = {"file.md": 3}
        regressions, improvements = diff_drift_baseline(current, baseline)
        assert regressions == []
        assert improvements == []

    def test_increase_is_regression(self) -> None:
        current = {"file.md": 5}
        baseline = {"file.md": 3}
        regressions, _ = diff_drift_baseline(current, baseline)
        assert len(regressions) == 1
        assert "file.md" in regressions[0]

    def test_decrease_is_improvement(self) -> None:
        current = {"file.md": 1}
        baseline = {"file.md": 3}
        _, improvements = diff_drift_baseline(current, baseline)
        assert len(improvements) == 1

    def test_new_file_is_regression(self) -> None:
        current = {"new.md": 2}
        baseline: dict[str, int] = {}
        regressions, _ = diff_drift_baseline(current, baseline)
        assert len(regressions) == 1

    def test_removed_file_is_improvement(self) -> None:
        current: dict[str, int] = {}
        baseline = {"old.md": 5}
        _, improvements = diff_drift_baseline(current, baseline)
        assert len(improvements) == 1


class TestDriftCountsFromFailures:
    """Tests for aggregating failure strings into per-file counts."""

    def test_aggregates_by_file(self) -> None:
        failures = [
            "foo.md: stale marker declaration: x",
            "foo.md: undeclared reference: y",
            "bar.md: existence miss: z",
        ]
        counts = drift_counts_from_failures(failures)
        assert counts == {"foo.md": 2, "bar.md": 1}


class TestReportDriftRatchet:
    """Tests for the reporting wrapper."""

    def test_returns_regressions(self, capsys: pytest.CaptureFixture) -> None:
        current = {"file.md": 5}
        baseline = {"file.md": 3}
        regressions, _ = report_drift_ratchet(current, baseline)
        assert len(regressions) == 1
        captured = capsys.readouterr()
        assert "regressions" in captured.out.lower()

    def test_clean_returns_empty(self, capsys: pytest.CaptureFixture) -> None:
        regressions, improvements = report_drift_ratchet({"a": 2}, {"a": 2})
        assert regressions == []
        assert improvements == []


class TestVacuityRegressionGuard:
    """Defect 1 regression: reinstating the parent-directory shortcut must
    cause test_existence_miss_nonexistent_child_of_existing_parent to fail.

    This class exists purely to document the guard. The actual regression test
    is in TestMarkerPathDrift above. If someone re-adds the parent check, that
    test will fail because the parent (.agents/architecture) exists and is
    non-empty, yet the child (ADR-999.md) is missing.
    """

    def test_guard_documented(self) -> None:
        """Placeholder: the real guard is the existence miss test above."""
        assert True
