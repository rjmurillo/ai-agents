"""The staleness gate names its stale files and says when to commit (issue #6427).

Before the fix the gate returned a bool, so the pre-PR summary read
``reason=legacy.boolean_contract`` and "Validation failed", and the failure echo
kept the last 40 lines of a list that can pass 300 paths. These tests pin the
replacement: a typed outcome that carries the count, the first paths, and a
reason code that tells stale output from uncommitted output.

Coverage:

- positive: a clean child passes with an examined count; a drift child yields
  a FAIL outcome naming the first paths and the hidden remainder.
- negative: a child that fails without a drift block is ``script.failed``, not
  a path list; an absent script is BLOCKED; a killed child is UNKNOWN.
- edge: generator progress indented like a path is not read as a path; a
  partial commit hint is not "uncommitted only"; a 306-path list keeps its head.
- conformance: the marker spelling and the real ``build_all`` output parse
  through the gate's own parser.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.validation import generated_staleness_report
from scripts.validation.evidence import EvidenceState
from tests.validation.staleness_gate_helpers import (
    REPO_ROOT,
    check_generated_staleness,
    fake_repo,
    no_ambient_outer_cap,  # noqa: F401  (autouse fixture)
    stub,
)

sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
import build_all

_HEADER = "STALENESS DETECTED: uncommitted regen drift:"
_MARKER_ALL = (
    f"{build_all.UNCOMMITTED_UNCHANGED_PREFIX} 3 of 3 drifted path(s) match the generators' "
    "output. Commit the regenerated files, then rerun --check."
)
_MARKER_SOME = (
    f"{build_all.UNCOMMITTED_UNCHANGED_PREFIX} 1 of 3 drifted path(s) match the generators' "
    "output; commit those. The other 2 are stale: run uv run python build/scripts/build_all.py."
)


def _drift_output(paths: list[str], marker: str = "") -> str:
    lines = ["generating agents...", "  wrote progress line", _HEADER]
    lines += [f"  {path}" for path in paths]
    if marker:
        lines.append(marker)
    return "\n".join(lines)


def _failing_child(root: Path, stderr_text: str, exit_code: int = 2) -> None:
    body = f"sys.stderr.write({stderr_text!r} + '\\n')\nsys.exit({exit_code})"
    stub(root / "build" / "scripts" / "build_all.py", body)


class TestParseStaleReport:
    def test_the_drift_block_becomes_paths_in_order(self) -> None:
        report = check_generated_staleness.parse_stale_report(_drift_output(["a.md", "b/c.py"]))

        assert report.paths == ("a.md", "b/c.py")

    def test_progress_lines_before_the_header_are_not_paths(self) -> None:
        report = check_generated_staleness.parse_stale_report(_drift_output(["a.md"]))

        assert "  wrote progress line" in report.other
        assert "wrote progress line" not in report.paths

    def test_the_block_ends_at_the_first_unindented_line(self) -> None:
        text = _drift_output(["a.md"]) + "\nSURFACE PARITY VIOLATION:\n  finding one"

        report = check_generated_staleness.parse_stale_report(text)

        assert report.paths == ("a.md",)
        assert "  finding one" in report.other

    def test_single_line_staleness_kinds_are_paths(self) -> None:
        text = (
            "STALENESS DETECTED: install tree differs from plugin tree: .claude/x.md\n"
            "STALENESS DETECTED: lib mirror differs from scripts/: src/lib/y.py"
        )

        report = check_generated_staleness.parse_stale_report(text)

        assert report.paths == (".claude/x.md", "src/lib/y.py")

    def test_output_without_staleness_has_no_paths_and_keeps_every_line(self) -> None:
        report = check_generated_staleness.parse_stale_report("Error: boom\n  indented detail")

        assert report.paths == ()
        assert report.other == ("Error: boom", "  indented detail")

    def test_a_marker_covering_every_path_is_uncommitted_only(self) -> None:
        report = check_generated_staleness.parse_stale_report(
            _drift_output(["a", "b", "c"], _MARKER_ALL)
        )

        assert report.uncommitted_only is True
        assert report.hint == _MARKER_ALL

    def test_a_marker_covering_some_paths_is_not_uncommitted_only(self) -> None:
        report = check_generated_staleness.parse_stale_report(
            _drift_output(["a", "b", "c"], _MARKER_SOME)
        )

        assert report.uncommitted_only is False
        assert report.hint == _MARKER_SOME

    def test_no_marker_means_no_hint(self) -> None:
        report = check_generated_staleness.parse_stale_report(_drift_output(["a"]))

        assert report.hint == ""
        assert report.uncommitted_only is False


class TestTypedOutcome:
    def test_a_clean_child_passes_with_an_examined_count(self, tmp_path: Path) -> None:
        root = fake_repo(tmp_path, build_exit=0)

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.state is EvidenceState.PASS
        assert outcome.examined == 1

    def test_drift_fails_with_the_stale_reason_and_names_the_first_paths(
        self, tmp_path: Path
    ) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, _drift_output(["one.md", "two.md"]))

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "generated.stale"
        assert outcome.findings == 2
        assert "one.md, two.md" in outcome.detail
        assert "legacy" not in outcome.reason

    def test_a_long_list_names_ten_paths_and_counts_the_rest(self, tmp_path: Path) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        paths = [f"gen/file{i:03d}.md" for i in range(306)]
        _failing_child(root, _drift_output(paths))

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.findings == 306
        assert "gen/file000.md" in outcome.detail
        assert "gen/file009.md" in outcome.detail
        assert "gen/file010.md" not in outcome.detail
        assert "and 296 more" in outcome.detail

    def test_uncommitted_only_drift_gets_its_own_reason_and_the_hint(self, tmp_path: Path) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, _drift_output(["a", "b", "c"], _MARKER_ALL))

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.reason == "generated.uncommitted"
        assert "Commit the regenerated files" in outcome.detail

    def test_partly_uncommitted_drift_stays_stale(self, tmp_path: Path) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, _drift_output(["a", "b", "c"], _MARKER_SOME))

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.reason == "generated.stale"
        assert "The other 2 are stale" in outcome.detail

    def test_a_failure_without_a_drift_block_is_script_failed(self, tmp_path: Path) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, "Error: no platform configs")

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "script.failed"
        assert outcome.findings == 1

    def test_an_absent_script_is_blocked_not_failed(self, tmp_path: Path) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        (root / "build" / "scripts" / "build_all.py").unlink()

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == "script.absent"

    def test_a_killed_child_is_unknown_with_the_timeout_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        stub(root / "build" / "scripts" / "build_all.py", "import time\ntime.sleep(30)")
        monkeypatch.setattr(check_generated_staleness, "_GATE_BUDGET_SECONDS", 1.0)

        outcome = check_generated_staleness.validate_generated_staleness(root)

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == "timeout"


class TestFailureEcho:
    def test_a_long_list_prints_the_head_and_drops_the_tail_paths(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        paths = [f"gen/file{i:03d}.md" for i in range(306)]
        _failing_child(root, _drift_output(paths))

        check_generated_staleness.main([str(root)])

        out = capsys.readouterr().out
        assert "[STALE] 306 generated path(s) differ from HEAD; first 10:" in out
        assert "  gen/file000.md" in out
        assert "  ... and 296 more" in out
        assert "gen/file305.md" not in out

    def test_the_tail_keeps_a_non_path_diagnosis(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        text = _drift_output(["a.md"]) + "\nSURFACE PARITY VIOLATION:\n  src is stale"
        _failing_child(root, text)

        check_generated_staleness.main([str(root)])

        assert "SURFACE PARITY VIOLATION:" in capsys.readouterr().out

    def test_uncommitted_only_drift_prints_the_commit_remedy_not_the_regenerate_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, _drift_output(["a", "b", "c"], _MARKER_ALL))

        check_generated_staleness.main([str(root)])

        err = capsys.readouterr().err
        assert "Commit the regenerated files, then rerun this gate." in err
        assert "regenerate and commit" not in err

    def test_stale_drift_keeps_the_regenerate_remedy(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, _drift_output(["a"]))

        check_generated_staleness.main([str(root)])

        assert "uv run python build/scripts/build_all.py" in capsys.readouterr().err

    def test_the_cli_exit_code_is_still_one_for_drift(self, tmp_path: Path) -> None:
        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, _drift_output(["a"]))

        assert check_generated_staleness.main([str(root)]) == 1


class TestPreprSummary:
    def test_run_validation_prints_the_stale_path_not_the_legacy_reason(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
        import pre_pr

        root = fake_repo(tmp_path, build_exit=0)
        _failing_child(root, _drift_output(["gen/only.md"]))
        state = pre_pr.ValidationState()

        passed = pre_pr.run_validation(
            check_generated_staleness.GATE_NAME,
            state,
            lambda: check_generated_staleness.validate_generated_staleness(root),
        )

        out = capsys.readouterr().out
        assert passed is False
        assert "reason=generated.stale" in out
        assert "legacy.boolean_contract" not in out
        assert "Error: 1 generated path(s) differ from HEAD: gen/only.md." in out


class TestBuildAllConformance:
    def test_the_marker_prefix_is_spelled_the_same_in_both_files(self) -> None:
        assert generated_staleness_report.UNCHANGED_PREFIX == build_all.UNCOMMITTED_UNCHANGED_PREFIX

    def test_the_real_all_unchanged_message_parses_as_uncommitted_only(self) -> None:
        text = _drift_output(["a", "b"], build_all._unchanged_regeneration_message(2, 2))

        report = check_generated_staleness.parse_stale_report(text)

        assert report.uncommitted_only is True

    def test_the_real_partial_message_does_not_parse_as_uncommitted_only(self) -> None:
        text = _drift_output(["a", "b"], build_all._unchanged_regeneration_message(1, 2))

        report = check_generated_staleness.parse_stale_report(text)

        assert report.uncommitted_only is False
        assert report.hint.startswith(build_all.UNCOMMITTED_UNCHANGED_PREFIX)

    def test_the_real_drift_printer_output_round_trips(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "a.md").write_text("same", encoding="utf-8")
        (tmp_path / "b.md").write_text("changed", encoding="utf-8")
        snapshot = {tmp_path / "a.md": b"same", tmp_path / "b.md": b"before"}

        build_all._print_stale_paths(tmp_path, ["a.md", "b.md"], snapshot)

        report = check_generated_staleness.parse_stale_report(capsys.readouterr().err)
        assert report.paths == ("a.md", "b.md")
        assert report.uncommitted_only is False
        assert "1 of 2" in report.hint
