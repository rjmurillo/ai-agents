# taste-lint: ignore file-size, validator regression suite keeps shared fixtures.
"""Tests for validate_session_json module.

These tests verify the session log validation functionality used for
protocol compliance. This is a pilot migration from Validate-SessionJson.ps1
per ADR-042.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any
from unittest import mock
from urllib.parse import urlparse

import pytest

from scripts.validate_session_json import (
    _INCOMPLETE_MUST_PREFIX,
    _LEGACY_HANDOFF_FIELD,
    _MISSING_LEVEL_PREFIX,
    _MISSING_REQUIRED_PREFIX,
    _MUST_FAILURE_PREFIXES,
    _MUST_NOT_VIOLATED_PREFIX,
    _RELAXED_FOR_EXISTING_LOGS,
    _UNJUSTIFIED_DEMOTION_PREFIX,
    BRANCH_PATTERN,
    COMMIT_SHA_PATTERN,
    CONTRADICTION_PATTERNS,
    SESSION_END_REQUIRED_ITEMS,
    SESSION_START_REQUIRED_ITEMS,
    ValidationResult,
    _session_identity,
    _validate_session_path,
    build_summary,
    count_must_failures,
    filename_session_number,
    get_case_insensitive,
    has_case_insensitive,
    load_session_file,
    validate_checklist_section,
    validate_filename_number,
    validate_must_item,
    validate_protocol_compliance,
    validate_qa_report_evidence,
    validate_qa_skip_scope,
    validate_session_end,
    validate_session_log,
    validate_session_section,
    validate_session_start,
)
from scripts.validation.session_scope import commit_reachability_problem

_qa_report = sys.modules["qa_report"]
QaBinding = _qa_report.QaBinding
load_qa_report = _qa_report.load_qa_report
non_evidence_paths = _qa_report.non_evidence_paths
post_qa_code_changes = _qa_report.post_qa_code_changes
resolve_session_log_path = _qa_report.resolve_session_log_path
session_log_identity = _qa_report.session_log_identity
session_qa_binding = _qa_report.session_qa_binding
validate_qa_report = _qa_report.validate_qa_report

QA_COMMIT = "a" * 40
QA_SESSION_LOG = (
    ".agents/sessions/2026-08-06-session-10004-memory-index-duplicate.json"
)


def _write_qa_report(
    path: Path,
    *,
    verdict: str = "PASS",
    session_log: str = QA_SESSION_LOG,
    commit: str = QA_COMMIT,
    extra_frontmatter: str = "",
) -> None:
    path.write_text(
        "---\n"
        f"qaVerdict: {verdict}\n"
        f"qaSessionLog: {session_log}\n"
        f"qaCommit: {commit}\n"
        f"{extra_frontmatter}"
        "---\n"
        "# QA Report\n",
        encoding="utf-8",
    )


def test_loads_passing_report_with_machine_readable_binding(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_qa_report(report_path, extra_frontmatter="title: QA evidence\n")

    report = load_qa_report(report_path)

    assert report.verdict == "PASS"
    assert report.session_log == QA_SESSION_LOG
    assert report.commit == QA_COMMIT


def test_rejects_unreadable_report(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="QA report cannot be read"):
        load_qa_report(tmp_path / "missing.md")


@pytest.mark.parametrize("verdict", ["DEFERRED", "FAIL", "WARN", "UNKNOWN", "pass"])
def test_rejects_every_non_passing_verdict(tmp_path: Path, verdict: str) -> None:
    report_path = tmp_path / "report.md"
    _write_qa_report(report_path, verdict=verdict)

    with pytest.raises(ValueError, match="verdict must be PASS"):
        load_qa_report(report_path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("# QA\n", "missing leading YAML frontmatter"),
        ("---\nqaVerdict: PASS\n", "frontmatter is not closed"),
        (
            "---\nqaVerdict: PASS\nqaSession: 10004\n---\n",
            "frontmatter is missing: qaCommit, qaSessionLog",
        ),
        (
            "---\nqaVerdict: PASS\nqaVerdict: PASS\n"
            f"qaSessionLog: {QA_SESSION_LOG}\nqaCommit: {QA_COMMIT}\n---\n",
            "frontmatter repeats qaVerdict",
        ),
    ],
)
def test_rejects_missing_or_malformed_qa_frontmatter(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_qa_report(report_path)


@pytest.mark.parametrize(
    "session_log",
    [
        "/absolute/session.json",
        ".agents/sessions/../qa/report.json",
        ".agents\\sessions\\session.json",
        ".agents/sessions/session.md",
        "sessions/session.json",
        "",
    ],
)
def test_rejects_noncanonical_qa_session_identity(
    tmp_path: Path,
    session_log: str,
) -> None:
    report_path = tmp_path / "report.md"
    _write_qa_report(report_path, session_log=session_log)

    with pytest.raises(ValueError, match="canonical .agents/sessions"):
        load_qa_report(report_path)


@pytest.mark.parametrize("commit", ["a" * 39, "a" * 41, "A" * 40, "abcdef1234"])
def test_rejects_non_full_qa_commit(tmp_path: Path, commit: str) -> None:
    report_path = tmp_path / "report.md"
    _write_qa_report(report_path, commit=commit)

    with pytest.raises(ValueError, match="full lowercase 40-character SHA"):
        load_qa_report(report_path)


def test_rejects_qa_report_for_unrelated_session(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_qa_report(report_path, session_log=".agents/sessions/unrelated.json")

    with pytest.raises(ValueError, match="unrelated.json"):
        validate_qa_report(
            report_path,
            QaBinding(session_log=QA_SESSION_LOG, commit=QA_COMMIT),
        )


def test_accepts_qa_report_with_matching_session_and_commit(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_qa_report(report_path)

    report = validate_qa_report(
        report_path,
        QaBinding(session_log=QA_SESSION_LOG, commit=QA_COMMIT),
    )

    assert report.verdict == "PASS"


def test_rejects_qa_report_for_stale_commit(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    _write_qa_report(report_path, commit="b" * 40)

    with pytest.raises(ValueError, match=f"{'b' * 40} != {QA_COMMIT}"):
        validate_qa_report(
            report_path,
            QaBinding(session_log=QA_SESSION_LOG, commit=QA_COMMIT),
        )


def test_extracts_qa_binding_from_episode_comparison_head() -> None:
    binding = session_qa_binding(
        {
            "episodeMetrics": {"comparison": {"head": QA_COMMIT}},
            "endingCommit": "a" * 10,
        },
        session_log=QA_SESSION_LOG,
        resolve_commit=lambda _commit: QA_COMMIT,
    )

    assert binding == QaBinding(session_log=QA_SESSION_LOG, commit=QA_COMMIT)


def test_extracts_qa_binding_from_full_ending_commit() -> None:
    binding = session_qa_binding(
        {"endingCommit": QA_COMMIT},
        session_log=QA_SESSION_LOG,
    )

    assert binding == QaBinding(session_log=QA_SESSION_LOG, commit=QA_COMMIT)


def test_rejects_qa_commit_disagreement() -> None:
    with pytest.raises(ValueError, match="different commits"):
        session_qa_binding(
            {
                "episodeMetrics": {"comparison": {"head": QA_COMMIT}},
                "endingCommit": "b" * 40,
            },
            session_log=QA_SESSION_LOG,
        )


def test_resolves_abbreviated_qa_ending_commit() -> None:
    seen: list[str] = []

    def resolve(commit: str) -> str:
        seen.append(commit)
        return QA_COMMIT

    binding = session_qa_binding(
        {"endingCommit": "a" * 10},
        session_log=QA_SESSION_LOG,
        resolve_commit=resolve,
    )

    assert binding == QaBinding(session_log=QA_SESSION_LOG, commit=QA_COMMIT)
    assert seen == ["a" * 10]


def test_rejects_session_without_resolvable_full_qa_commit() -> None:
    with pytest.raises(ValueError, match="full 40-character QA commit"):
        session_qa_binding(
            {"endingCommit": "a" * 10},
            session_log=QA_SESSION_LOG,
            resolve_commit=lambda _commit: None,
        )


def test_rejects_abbreviated_qa_commit_without_resolver() -> None:
    with pytest.raises(ValueError, match="full 40-character QA commit"):
        session_qa_binding(
            {"endingCommit": "a" * 10},
            session_log=QA_SESSION_LOG,
        )


def test_rejects_invalid_qa_commit_resolver_output() -> None:
    with pytest.raises(ValueError, match="full 40-character QA commit"):
        session_qa_binding(
            {"endingCommit": "a" * 10},
            session_log=QA_SESSION_LOG,
            resolve_commit=lambda _commit: "still-short",
        )


def test_filters_session_evidence_from_post_qa_changes() -> None:
    assert non_evidence_paths(
        [
            "",
            ".agents/qa/report.md",
            ".agents/sessions/session.json",
            ".agents/memory/episodes/episode.json",
            "scripts/changed.py",
        ]
    ) == ["scripts/changed.py"]


def test_maps_external_session_file_to_canonical_identity(
    tmp_path: Path,
) -> None:
    sessions_root = tmp_path / "artifacts" / "sessions"
    session_path = sessions_root / "nested" / "session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text("{}", encoding="utf-8")

    identity = session_log_identity(
        session_path,
        sessions_root=sessions_root,
    )

    assert identity == ".agents/sessions/nested/session.json"
    assert resolve_session_log_path(
        identity,
        sessions_root=sessions_root,
    ) == session_path


def test_rejects_session_file_outside_configured_root(tmp_path: Path) -> None:
    sessions_root = tmp_path / "artifacts" / "sessions"
    sessions_root.mkdir(parents=True)
    session_path = tmp_path / "session.json"

    with pytest.raises(ValueError, match="outside the configured sessions root"):
        session_log_identity(
            session_path,
            sessions_root=sessions_root,
        )


def test_rejects_non_json_session_identity(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    session_path = sessions_root / "session.md"
    session_path.parent.mkdir()

    with pytest.raises(ValueError, match="canonical .agents/sessions"):
        session_log_identity(
            session_path,
            sessions_root=sessions_root,
        )


def test_rejects_session_identity_that_resolves_outside_root(
    tmp_path: Path,
) -> None:
    sessions_root = tmp_path / "sessions"
    outside = tmp_path / "outside"
    sessions_root.mkdir()
    outside.mkdir()
    try:
        (sessions_root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(ValueError, match="escapes the sessions root"):
        resolve_session_log_path(
            ".agents/sessions/linked/session.json",
            sessions_root=sessions_root,
        )


def test_validator_accepts_configured_external_session_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "artifacts"
    session_path = artifact_root / "sessions" / "session.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(artifact_root))

    validated = _validate_session_path(session_path)

    assert validated == session_path
    assert _session_identity(validated) == ".agents/sessions/session.json"


def test_detects_code_touched_then_reverted_after_qa(tmp_path: Path) -> None:
    completed = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess(
            [],
            0,
            (
                "scripts/changed.py\0"
                ".agents/qa/report.md\0"
                "scripts/changed.py\0"
            ),
            "",
        ),
    ]

    with mock.patch.object(
        _qa_report.subprocess,
        "run",
        side_effect=completed,
    ) as run:
        changed = post_qa_code_changes(
            "a" * 40,
            "b" * 40,
            repo_root=tmp_path,
        )

    assert changed == ["scripts/changed.py"]
    assert [call.args[0] for call in run.call_args_list] == [
        ["git", "merge-base", "--is-ancestor", "a" * 40, "b" * 40],
        [
            "git",
            "log",
            "--format=",
            "--name-only",
            "--no-renames",
            "-m",
            "-z",
            f"{'a' * 40}..{'b' * 40}",
        ],
    ]


def test_accepts_evidence_only_commits_after_qa(tmp_path: Path) -> None:
    completed = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess(
            [],
            0,
            (
                ".agents/sessions/session.json\0"
                ".agents/qa/report.md\0"
                ".agents/memory/episodes/episode.json\0"
            ),
            "",
        ),
    ]

    with mock.patch.object(
        _qa_report.subprocess,
        "run",
        side_effect=completed,
    ):
        changed = post_qa_code_changes(
            "a" * 40,
            "b" * 40,
            repo_root=tmp_path,
        )

    assert changed == []


def test_rejects_qa_commit_outside_validation_history(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess([], 1, "", "")

    with (
        mock.patch.object(
            _qa_report.subprocess,
            "run",
            return_value=completed,
        ) as run,
        pytest.raises(ValueError, match="not an ancestor"),
    ):
        post_qa_code_changes(
            "a" * 40,
            "b" * 40,
            repo_root=tmp_path,
        )

    run.assert_called_once()


def test_fails_closed_when_qa_ancestry_cannot_be_checked(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess([], 2, "", "")

    with (
        mock.patch.object(
            _qa_report.subprocess,
            "run",
            return_value=completed,
        ),
        pytest.raises(ValueError, match="Could not verify QA commit ancestry"),
    ):
        post_qa_code_changes(
            "a" * 40,
            "b" * 40,
            repo_root=tmp_path,
        )


def test_fails_closed_when_post_qa_commits_cannot_be_read(tmp_path: Path) -> None:
    completed = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 1, "", ""),
    ]

    with (
        mock.patch.object(
            _qa_report.subprocess,
            "run",
            side_effect=completed,
        ),
        pytest.raises(ValueError, match="Could not inspect commits after QA"),
    ):
        post_qa_code_changes(
            "a" * 40,
            "b" * 40,
            repo_root=tmp_path,
        )


def _make_complete_start_section(**overrides: dict) -> dict:
    """Build a sessionStart section with all required items complete."""
    section = {
        name: {"complete": True, "evidence": "Evidence", "level": "MUST"}
        for name in SESSION_START_REQUIRED_ITEMS
    }
    section.update(overrides)
    return section


def _make_complete_end_section(**overrides: dict) -> dict:
    """Build a sessionEnd section with all required items complete."""
    section = {
        name: {"complete": True, "evidence": "Evidence", "level": "MUST"}
        for name in SESSION_END_REQUIRED_ITEMS
    }
    # handoffPreserved is MUST: complete=True means HANDOFF.md was not modified
    section["handoffPreserved"] = {
        "complete": True,
        "evidence": "HANDOFF.md not modified",
        "level": "MUST",
    }
    section["qaValidation"] = {
        "complete": True,
        "evidence": "SKIPPED: investigation-only",
        "level": "MUST",
    }
    section.update(overrides)
    return section


if TYPE_CHECKING:
    from collections.abc import Iterator

    from _pytest.capture import CaptureFixture


_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scratch() -> Iterator[Path]:
    """A throwaway directory inside the repo.

    `validate_safe_path` rejects any path outside the project root, so a
    `tmp_path` fixture would make every CLI case exit 1 for a path reason and
    prove nothing about the load or the schema.
    """
    with tempfile.TemporaryDirectory(dir=_REPO_ROOT) as name:
        yield Path(name)


def _run_cli(
    path: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Drive the validator as the hooks and the workflow drive it."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "scripts/validate_session_json.py", str(path)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class TestConstants:
    """Tests for module constants."""

    def test_the_schema_requires_the_session_fields_the_protocol_names(self) -> None:
        """The schema is the only enforcer of session shape, so pin what it requires.

        This replaces an assertion on a Python constant that duplicated the
        schema's own ``required`` list. The constant was deleted once the
        duplicate presence check went with it; a test that echoes a literal back
        at itself catches nothing.
        """
        import scripts.validate_session_json as vsj

        schema = json.loads(vsj.SCHEMA_PATH.read_text(encoding="utf-8"))

        assert set(schema["properties"]["session"]["required"]) == {
            "number",
            "date",
            "branch",
            "startingCommit",
            "objective",
        }

    def test_branch_pattern_matches_conventional(self) -> None:
        """BRANCH_PATTERN matches conventional branch names."""
        valid_branches = [
            "feat/new-feature",
            "fix/bug-123",
            "docs/update-readme",
            "chore/cleanup",
            "refactor/code-cleanup",
            "test/add-tests",
            "ci/update-workflow",
        ]
        for branch in valid_branches:
            assert BRANCH_PATTERN.match(branch), f"Expected to match: {branch}"

    def test_branch_pattern_rejects_invalid(self) -> None:
        """BRANCH_PATTERN rejects invalid branch names."""
        invalid_branches = [
            "main",
            "feature/something",
            "bugfix/something",
            "my-branch",
        ]
        for branch in invalid_branches:
            assert not BRANCH_PATTERN.match(branch), f"Expected to not match: {branch}"

    def test_commit_sha_pattern_matches_valid(self) -> None:
        """COMMIT_SHA_PATTERN matches valid SHA formats."""
        valid_shas = [
            "abcdef1",  # 7 chars
            "1234567890abcdef1234567890abcdef12345678",  # 40 chars
            "abc1234",
        ]
        for sha in valid_shas:
            assert COMMIT_SHA_PATTERN.match(sha), f"Expected to match: {sha}"

    def test_commit_sha_pattern_rejects_invalid(self) -> None:
        """COMMIT_SHA_PATTERN rejects invalid formats."""
        invalid_shas = [
            "abc",  # Too short
            "xyz123",  # Invalid chars
            "1234567890abcdef1234567890abcdef1234567890",  # 41 chars
        ]
        for sha in invalid_shas:
            assert not COMMIT_SHA_PATTERN.match(sha), f"Expected to not match: {sha}"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_is_valid(self) -> None:
        """Empty result is valid."""
        result = ValidationResult()

        assert result.is_valid
        assert result.errors == []
        assert result.warnings == []

    def test_with_errors_is_invalid(self) -> None:
        """Result with errors is invalid."""
        result = ValidationResult(errors=["Error 1"])

        assert not result.is_valid

    def test_with_warnings_only_is_valid(self) -> None:
        """Result with only warnings is still valid."""
        result = ValidationResult(warnings=["Warning 1"])

        assert result.is_valid


class TestCaseInsensitiveHelpers:
    """Tests for case-insensitive dictionary helpers."""

    def test_get_case_insensitive_exact_match(self) -> None:
        """get_case_insensitive finds exact match."""
        data = {"Key": "value"}

        assert get_case_insensitive(data, "Key") == "value"

    def test_get_case_insensitive_different_case(self) -> None:
        """get_case_insensitive finds different case match."""
        data = {"KEY": "value"}

        assert get_case_insensitive(data, "key") == "value"

    def test_get_case_insensitive_not_found(self) -> None:
        """get_case_insensitive returns None when not found."""
        data = {"other": "value"}

        assert get_case_insensitive(data, "key") is None

    def test_has_case_insensitive_found(self) -> None:
        """has_case_insensitive returns True when found."""
        data = {"Key": "value"}

        assert has_case_insensitive(data, "KEY")

    def test_has_case_insensitive_not_found(self) -> None:
        """has_case_insensitive returns False when not found."""
        data = {"other": "value"}

        assert not has_case_insensitive(data, "key")


class TestValidateSessionSection:
    """Tests for validate_session_section function."""

    def test_valid_session(self) -> None:
        """Valid session passes validation."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            "branch": "feat/test",
            "startingCommit": "abcdef1",
            "objective": "Test objective",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert result.is_valid
        assert len(result.warnings) == 0

    def test_missing_required_field_defers_to_schema(self) -> None:
        """Missing required fields are NOT reported here; schema owns shape."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            # Missing branch, startingCommit, objective
        }
        result = ValidationResult()

        validate_session_section(session, result)

        # No errors from validate_session_section; schema validation catches these
        assert result.is_valid
        assert not any("Missing: session." in e for e in result.errors)

    def test_invalid_branch_name_warning(self) -> None:
        """Invalid branch name causes warning."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            "branch": "my-feature",  # Invalid
            "startingCommit": "abcdef1",
            "objective": "Test",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        # Still valid, but has warning
        assert result.is_valid
        assert any("conventional naming" in w for w in result.warnings)

    def test_invalid_commit_sha(self) -> None:
        """Invalid commit SHA causes error."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            "branch": "feat/test",
            "startingCommit": "invalid!",  # Invalid
            "objective": "Test",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert not result.is_valid
        assert any("Invalid commit SHA" in e for e in result.errors)

    def test_future_date_emits_error(self) -> None:
        """A session date in the future is an error (not a warning) (#3717)."""
        session = {
            "number": 1,
            "date": "2099-12-31",
            "branch": "fix/test",
            "startingCommit": "abcdef1",
            "objective": "Test",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert any("future" in e for e in result.errors)
        assert any("2099-12-31" in e for e in result.errors)
        assert not any("future" in w for w in result.warnings)

    def test_today_date_is_accepted(self) -> None:
        """A session date matching today does not produce a future-date error (#3717)."""
        from datetime import datetime, timezone

        today = datetime.now(tz=timezone.utc).date().isoformat()
        session = {
            "number": 1,
            "date": today,
            "branch": "fix/test",
            "startingCommit": "abcdef1",
            "objective": "Test",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert not any("future" in e for e in result.errors)

    def test_past_date_is_accepted(self) -> None:
        """A past session date does not trigger the future-date error (#3717)."""
        session = {
            "number": 1,
            "date": "2024-01-01",
            "branch": "fix/test",
            "startingCommit": "abcdef1",
            "objective": "Test",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert not any("future" in e for e in result.errors)

    @pytest.mark.parametrize(
        ("hour", "minute", "expected_future_errors"),
        [(9, 59, 1), (10, 0, 0)],
        ids=["before-utc-10", "at-utc-10"],
    )
    def test_host_local_tomorrow_at_utc_10_boundary(
        self, hour: int, minute: int, expected_future_errors: int
    ) -> None:
        """UTC+14 reaches tomorrow precisely at 10:00 UTC (#4779)."""
        from datetime import datetime, timedelta, timezone

        fixed_now = datetime(2026, 8, 14, hour, minute, tzinfo=timezone.utc)
        tomorrow = (fixed_now.date() + timedelta(days=1)).isoformat()
        session = {
            "number": 1,
            "date": tomorrow,
            "branch": "fix/test",
            "startingCommit": "abcdef1",
            "objective": "Test",
        }
        result = ValidationResult()

        with mock.patch("scripts.validate_session_json.datetime") as clock:
            clock.now.return_value = fixed_now
            validate_session_section(session, result)

        future_errors = [error for error in result.errors if "future" in error]
        assert len(future_errors) == expected_future_errors
        assert all(tomorrow in error for error in future_errors)

    def test_date_two_days_ahead_of_utc_emits_error(self) -> None:
        """Two days ahead exceeds the max timezone offset, so it is flagged (#4779).

        No real timezone puts the host-local date two calendar days ahead of
        UTC, so a +2 date is a placeholder or a wrong date, not a timezone
        artifact.
        """
        from datetime import datetime, timedelta, timezone

        fixed_now = datetime(2026, 8, 14, 23, 59, tzinfo=timezone.utc)
        two_days = (fixed_now.date() + timedelta(days=2)).isoformat()
        session = {
            "number": 1,
            "date": two_days,
            "branch": "fix/test",
            "startingCommit": "abcdef1",
            "objective": "Test",
        }
        result = ValidationResult()

        with mock.patch("scripts.validate_session_json.datetime") as clock:
            clock.now.return_value = fixed_now
            validate_session_section(session, result)

        assert any("future" in e for e in result.errors)
        assert any(two_days in e for e in result.errors)


class TestValidateSessionStart:
    """Tests for validate_session_start function."""

    def test_complete_must_items(self) -> None:
        """Complete MUST items pass validation."""
        session_start = _make_complete_start_section()
        result = ValidationResult()

        validate_session_start(session_start, result)

        assert result.is_valid

    def test_incomplete_must_item(self) -> None:
        """Incomplete MUST item causes error."""
        session_start = _make_complete_start_section(
            serenaActivated={"complete": False, "evidence": "", "level": "MUST"},
        )
        result = ValidationResult()

        validate_session_start(session_start, result)

        assert not result.is_valid
        assert any("Incomplete MUST" in e for e in result.errors)

    def test_missing_evidence_warning(self) -> None:
        """Missing evidence on complete MUST causes warning."""
        session_start = _make_complete_start_section(
            serenaActivated={"complete": True, "evidence": "", "level": "MUST"},
        )
        result = ValidationResult()

        validate_session_start(session_start, result)

        # Still valid, but has warning
        assert result.is_valid
        assert any("Missing evidence" in w for w in result.warnings)


class TestValidateSessionEnd:
    """Tests for validate_session_end function."""

    def test_valid_session_end(self) -> None:
        """Valid session end passes validation."""
        session_end = _make_complete_end_section()
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert result.is_valid

    def test_handoff_preserved_satisfied(self) -> None:
        """handoffPreserved with Complete=true passes (issue #868)."""
        session_end = _make_complete_end_section()
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert result.is_valid

    def test_handoff_preserved_violated(self) -> None:
        """handoffPreserved with Complete=false fails (issue #868)."""
        session_end = _make_complete_end_section(
            handoffPreserved={
                "complete": False,
                "evidence": "HANDOFF.md was modified",
                "level": "MUST",
            },
        )
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert not result.is_valid
        assert any("Incomplete MUST" in e for e in result.errors)

    def test_legacy_handoff_not_updated_satisfied(self) -> None:
        """Legacy handoffNotUpdated with Complete=false passes (backward compat)."""
        session_end = _make_complete_end_section()
        # Replace handoffPreserved with legacy field
        del session_end["handoffPreserved"]
        session_end["handoffNotUpdated"] = {"complete": False, "level": "MUST NOT"}
        result = ValidationResult()

        validate_session_end(session_end, result)

        # handoffNotUpdated is not in SESSION_END_REQUIRED_ITEMS but is
        # picked up by validate_checklist_section as MUST NOT level item.
        # Complete=false for MUST NOT is the satisfied state, and the legacy
        # backward-compat check should not flag it as a violation.
        assert result.is_valid

    def test_legacy_handoff_not_updated_violated(self) -> None:
        """Legacy handoffNotUpdated with Complete=true fails (backward compat)."""
        session_end = _make_complete_end_section()
        # Replace handoffPreserved with violated legacy field
        del session_end["handoffPreserved"]
        session_end["handoffNotUpdated"] = {"complete": True, "level": "MUST NOT"}
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert not result.is_valid
        assert any("MUST NOT violated" in e for e in result.errors)

    def test_session_end_must_items_uses_handoff_preserved(self) -> None:
        """SESSION_END_REQUIRED_ITEMS uses handoffPreserved (not legacy name)."""
        assert "handoffPreserved" in SESSION_END_REQUIRED_ITEMS
        assert _LEGACY_HANDOFF_FIELD not in SESSION_END_REQUIRED_ITEMS


class TestChecklistSectionValidation:
    """Tests for validate_checklist_section - the core fix for issue #1028."""

    def test_unknown_must_item_incomplete_causes_error(self) -> None:
        """MUST items NOT in the required set are still validated."""
        section_data = {
            "usageMandatoryRead": {"complete": False, "evidence": "", "level": "MUST"},
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert not result.is_valid
        assert any("usageMandatoryRead" in e for e in result.errors)

    def test_unknown_must_item_complete_passes(self) -> None:
        """Complete MUST items NOT in the required set pass validation."""
        section_data = {
            "customMustItem": {"complete": True, "evidence": "Done", "level": "MUST"},
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert result.is_valid

    def test_should_items_not_checked_as_must(self) -> None:
        """SHOULD items that are incomplete do not cause errors."""
        section_data = {
            "optionalItem": {"complete": False, "evidence": "", "level": "SHOULD"},
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert result.is_valid

    def test_missing_required_item_causes_error(self) -> None:
        """Required item absent from section_data causes an error."""
        section_data = {
            "someOtherItem": {"complete": True, "evidence": "Done", "level": "MUST"},
        }
        result = ValidationResult()

        validate_checklist_section(
            section_data, frozenset({"requiredButMissing"}), "sessionStart", result
        )

        assert not result.is_valid
        assert any(
            "Missing required item: sessionStart.requiredButMissing" in e for e in result.errors
        )

    def test_non_dict_items_ignored(self) -> None:
        """Non-dict values in section data are ignored."""
        section_data = {
            "someString": "not a dict",
            "someNumber": 42,
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert result.is_valid


class TestEvidenceContradiction:
    """Tests for evidence-contradiction detection."""

    @pytest.mark.parametrize(
        "evidence",
        [
            "not available",
            "SKIPPED",
            "N/A",
            "Deferred to next session",
            "will validate later",
            "will run after merge",
            "TODO",
            "pending review",
            "TBD",
        ],
    )
    def test_contradiction_detected(self, evidence: str) -> None:
        """Evidence containing skip/waiver patterns triggers warning."""
        section_data = {
            "serenaActivated": {
                "complete": True,
                "evidence": evidence,
                "level": "MUST",
            },
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert any("Evidence contradiction" in w for w in result.warnings)

    def test_legitimate_evidence_no_contradiction(self) -> None:
        """Legitimate evidence does not trigger contradiction warning."""
        section_data = {
            "serenaActivated": {
                "complete": True,
                "evidence": "mcp__serena__activate_project output confirmed",
                "level": "MUST",
            },
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert not any("Evidence contradiction" in w for w in result.warnings)

    def test_contradiction_pattern_matches_expected(self) -> None:
        """CONTRADICTION_PATTERNS matches known skip indicators."""
        assert CONTRADICTION_PATTERNS.search("not available")
        assert CONTRADICTION_PATTERNS.search("SKIPPED due to CI")
        assert CONTRADICTION_PATTERNS.search("N/A for this session")
        assert not CONTRADICTION_PATTERNS.search("Tool output confirmed")

    @staticmethod
    def _warn(section_data: dict) -> list[str]:
        """Validate a sessionStart section and return contradiction warnings."""
        result = ValidationResult()
        validate_checklist_section(section_data, frozenset(), "sessionStart", result)
        return [w for w in result.warnings if "Evidence contradiction" in w]

    @staticmethod
    def _item(evidence: str) -> dict:
        """Build a complete MUST item with the given evidence."""
        return {
            "serenaActivated": {
                "complete": True,
                "evidence": evidence,
                "level": "MUST",
            },
        }

    @pytest.mark.parametrize(
        "evidence",
        [
            # Item ITSELF deferred is a genuine contradiction (issue #2007).
            "Deferred to next session",
            "Deferred to pre-commit hook validation",
            "Planning artifacts staged; commit deferred to session-824",
            "Serena init deferred per ADR-007 fast-path",
            "deferred",
            "pending",
            # A genuine token alongside a scope-qualified one still flags.
            "Tests skipped. Perf deferred to follow-up.",
            # Adversative conjunction ties the deferral to the completion, so
            # it contradicts rather than noting separate work (gemini).
            "Tests passed. But we deferred the deploy to next session",
            # Clause boundary must sit AFTER the affirmative word, not before:
            # the ';' precedes 'passed', so it is not a trailing-note separator.
            "Status; passed but pending review",
            # Adverb-separated negation: "not yet validated" negates the
            # affirmative, so the deferral is not suppressed (bug 07f14170).
            "Not yet validated; pending final review",
            # A dot inside a version/decimal is not a clause boundary, so the
            # deferral is not suppressed (bug 0a163adc).
            "Created item v1.5 pending review",
            # Contraction negation: "haven't passed" negates the affirmative, so
            # the trailing deferral is a genuine contradiction (bug 0ea9d246).
            "Tests haven't passed; pending review",
        ],
    )
    def test_genuine_contradiction_still_flags(self, evidence: str) -> None:
        """An item-itself deferral or any genuine token must still warn."""
        assert self._warn(self._item(evidence)), f"expected warning for {evidence!r}"

    @pytest.mark.parametrize(
        "evidence",
        [
            # Deferred/pending in a parenthetical aside about other work.
            "Tests pass (perf benchmark deferred to follow-up)",
            "Schema validated (migration pending review)",
            "Two commits created: P0 (commit 5639b23f) and P1 (pending)",
            "CI checks passing (CodeRabbit pending)",
            # Trailing note after affirmative completion across a clause boundary.
            "Markdown lint passed (0 errors after fix); pending pre-commit final run",
            # Mid-clause adversative ("but" meaning "except") does not introduce
            # the deferral clause, so suppression still applies (bug ref1_dda37e6b).
            "Tests passed. All scenarios but the edge case handled; deferred edge case",
            # Exact strings from issue #2007.
            "Used: spec skill (Step 0 + Step 0.5 gates), plan skill (decomposition). "
            "Bash: grep, awk, wc, gh CLI. No Python scorer (deferred per PRD 11).",
            "Spec scope validation: Step 0 First Principles Gate PASS (after H3 halt "
            "+ revision); Step 0.5 Memory-First Gate PASS (after H11 halt + "
            "reclassification); Step 9 critic checks 9a/9b/9c/9d all PASS. "
            "Audit-execution validation per TASK-011 Step 10 deferred to audit commit.",
        ],
    )
    def test_scope_qualified_deferral_not_flagged(self, evidence: str) -> None:
        """Deferred/pending pointing at a different scope must not warn (#2007)."""
        assert not self._warn(self._item(evidence)), f"false positive on {evidence!r}"

    @pytest.mark.parametrize(
        "evidence",
        [
            # Exact string from issue #3141: full pytest summary line.
            "uv run pytest tests/ -q: 14434 passed, 21 skipped, 45 xfailed",
            # Minimal numeric count.
            "21 skipped",
            # Zero is still a numeric count, not a skipped step.
            "0 skipped",
            # Thousands separator keeps the digit immediately before the token.
            "1,234 skipped",
            # Whitespace between digit and token (multiple spaces / tab).
            "12   skipped",
            # Pytest summary with non-delimiter word between count and "skipped" (#3939).
            "94 passed plus 1 skipped",
            # Multi-word summary with errors keyword.
            "103 passed, 2 errors, 5 skipped",
        ],
    )
    def test_numeric_skipped_count_not_flagged(self, evidence: str) -> None:
        """A pytest numeric 'N skipped' count is not a contradiction (#3141, #3939)."""
        assert not self._warn(self._item(evidence)), f"false positive on {evidence!r}"

    @pytest.mark.parametrize(
        "evidence",
        [
            # Bare status word: the item itself was skipped.
            "Tests skipped.",
            # A word (not a digit) immediately precedes the token, so it is a
            # skipped step, not a numeric count.
            "step skipped",
            # The digit is not immediately before the token ("step" is), so this
            # describes a skipped validation step and must still flag.
            "1 step skipped",
            # A numeric skipped count alongside a genuine incomplete token still
            # flags on the genuine token (TODO).
            "14434 passed, 21 skipped, 45 xfailed; TODO wire up remaining check",
            # Numeric identifier immediately before "skipped" where the number is
            # part of an identifier phrase, not a pytest count. These must flag.
            "step 21 skipped",
            "PR #3141 skipped review",
            "v2.1 skipped tests",
            # A numbered prose step sits after a word, not a delimiter, so it is
            # not a pytest count and must still flag (#3141 review).
            "Phase 2 skipped",
            "check 5 skipped",
            "test 3 skipped",
            "phase3 skipped",
        ],
    )
    def test_skipped_step_still_flags(self, evidence: str) -> None:
        """A skipped validation step (not a numeric count) must still warn (#3141)."""
        assert self._warn(self._item(evidence)), f"expected warning for {evidence!r}"


class TestValidateProtocolCompliance:
    """Tests for validate_protocol_compliance function."""

    def test_missing_session_start_is_left_to_the_schema(self) -> None:
        """The schema's protocolCompliance.required already names it (issue #3346).

        This layer only walks the section it was given; it must not restate the
        absence under a second spelling. The one-message guarantee is pinned in
        TestSectionAbsenceIsReportedOnce, which drives the full validator.
        """
        result = ValidationResult()

        validate_protocol_compliance({"sessionEnd": {}}, result)

        assert not any("protocolCompliance.sessionStart" in error for error in result.errors)
        assert any(
            error.startswith("Missing required item: sessionEnd.") for error in result.errors
        )

    def test_missing_session_end_is_left_to_the_schema(self) -> None:
        """Mirror of the sessionStart case."""
        result = ValidationResult()

        validate_protocol_compliance({"sessionStart": {}}, result)

        assert not any("protocolCompliance.sessionEnd" in error for error in result.errors)
        assert any(
            error.startswith("Missing required item: sessionStart.") for error in result.errors
        )

    def test_both_sections_present(self) -> None:
        """Both sections present passes section validation."""
        protocol: dict[str, Any] = {
            "sessionStart": {},
            "sessionEnd": {},
        }
        result = ValidationResult()

        validate_protocol_compliance(protocol, result)

        # No section-level errors
        assert "Missing: protocolCompliance.sessionStart" not in result.errors
        assert "Missing: protocolCompliance.sessionEnd" not in result.errors


class TestValidateQaReportEvidence:
    """Tests for owned QA report evidence."""

    COMMIT = "a" * 40
    SESSION_LOG = ".agents/sessions/current.json"

    @staticmethod
    def _session_end(evidence: str) -> dict[str, Any]:
        return {
            "qaValidation": {
                "complete": True,
                "evidence": evidence,
                "level": "MUST",
            }
        }

    @classmethod
    def _data(cls, *, commit: str | None = None) -> dict[str, Any]:
        return {
            "episodeMetrics": {
                "comparison": {"head": commit if commit is not None else cls.COMMIT}
            },
        }

    @classmethod
    def _write_report(
        cls,
        path: Path,
        *,
        verdict: str = "PASS",
        session_log: str | None = None,
        commit: str | None = None,
    ) -> None:
        path.write_text(
            "---\n"
            f"qaVerdict: {verdict}\n"
            f"qaSessionLog: {session_log or cls.SESSION_LOG}\n"
            f"qaCommit: {commit if commit is not None else cls.COMMIT}\n"
            "---\n"
            "# QA\n",
            encoding="utf-8",
        )

    def test_existing_report_under_qa_root_passes(
        self, tmp_path: Path
    ) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(report)
        result = ValidationResult()

        with mock.patch(
            "scripts.validate_session_json.artifact_dir",
            return_value=qa_root,
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(report)),
                result,
                session_log=self.SESSION_LOG,
            )

        assert result.errors == []

    def test_missing_report_fails_closed(self, tmp_path: Path) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        result = ValidationResult()

        with mock.patch(
            "scripts.validate_session_json.artifact_dir",
            return_value=qa_root,
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(qa_root / "missing.md")),
                result,
                session_log=self.SESSION_LOG,
            )

        assert result.errors == [
            f"QA report not found: {(qa_root / 'missing.md').resolve()}"
        ]

    def test_report_outside_qa_root_fails_closed(
        self, tmp_path: Path
    ) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("# Not QA\n", encoding="utf-8")
        result = ValidationResult()

        with mock.patch(
            "scripts.validate_session_json.artifact_dir",
            return_value=qa_root,
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(outside)),
                result,
                session_log=self.SESSION_LOG,
            )

        assert result.errors == [
            "QA evidence must name a report under the configured QA "
            f"artifact root: {str(outside)!r}"
        ]

    def test_verified_skip_does_not_require_report(
        self, tmp_path: Path
    ) -> None:
        result = ValidationResult()

        with mock.patch(
            "scripts.validate_session_json.artifact_dir"
        ) as artifact_dir_mock:
            validate_qa_report_evidence(
                self._data(),
                self._session_end("SKIPPED: investigation-only"),
                result,
                session_log=self.SESSION_LOG,
            )

        assert result.errors == []
        artifact_dir_mock.assert_not_called()

    @pytest.mark.parametrize("verdict", ["DEFERRED", "FAIL"])
    def test_non_passing_report_fails_closed(
        self,
        tmp_path: Path,
        verdict: str,
    ) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(report, verdict=verdict)
        result = ValidationResult()

        with mock.patch(
            "scripts.validate_session_json.artifact_dir",
            return_value=qa_root,
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(report)),
                result,
                session_log=self.SESSION_LOG,
            )

        assert result.errors == [
            f"QA report verdict must be PASS, got {verdict!r}"
        ]

    def test_unrelated_session_report_fails_closed(self, tmp_path: Path) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(
            report,
            session_log=".agents/sessions/unrelated.json",
        )
        result = ValidationResult()

        with mock.patch(
            "scripts.validate_session_json.artifact_dir",
            return_value=qa_root,
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(report)),
                result,
                session_log=self.SESSION_LOG,
            )

        assert result.errors == [
            "QA report session log does not match current session: "
            ".agents/sessions/unrelated.json != .agents/sessions/current.json"
        ]

    def test_stale_commit_report_fails_closed(self, tmp_path: Path) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(report, commit="b" * 40)
        result = ValidationResult()

        with mock.patch(
            "scripts.validate_session_json.artifact_dir",
            return_value=qa_root,
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(report)),
                result,
                session_log=self.SESSION_LOG,
            )

        assert result.errors == [
            "QA report commit does not match current session commit: "
            f"{'b' * 40} != {self.COMMIT}"
        ]

    def test_code_changed_after_qa_fails_closed(self, tmp_path: Path) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(report)
        result = ValidationResult()

        with (
            mock.patch(
                "scripts.validate_session_json.artifact_dir",
                return_value=qa_root,
            ),
            mock.patch(
                "scripts.validate_session_json.post_qa_code_changes",
                return_value=["scripts/new_code.py"],
            ),
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(report)),
                result,
                session_log=self.SESSION_LOG,
                validation_head="b" * 40,
            )

        assert result.errors == [
            "QA report is stale; code changed after its commit: scripts/new_code.py"
        ]

    def test_evidence_only_changes_after_qa_pass(self, tmp_path: Path) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(report)
        result = ValidationResult()

        with (
            mock.patch(
                "scripts.validate_session_json.artifact_dir",
                return_value=qa_root,
            ),
            mock.patch(
                "scripts.validate_session_json.post_qa_code_changes",
                return_value=[],
            ),
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(report)),
                result,
                session_log=self.SESSION_LOG,
                validation_head="b" * 40,
            )

        assert result.errors == []

    def test_unverifiable_validation_head_fails_closed(self, tmp_path: Path) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(report)
        result = ValidationResult()

        with (
            mock.patch(
                "scripts.validate_session_json.artifact_dir",
                return_value=qa_root,
            ),
            mock.patch(
                "scripts.validate_session_json.post_qa_code_changes",
                side_effect=ValueError("Could not inspect commits after QA"),
            ),
        ):
            validate_qa_report_evidence(
                self._data(),
                self._session_end(str(report)),
                result,
                session_log=self.SESSION_LOG,
                validation_head="b" * 40,
            )

        assert result.errors == ["Could not inspect commits after QA"]

    def test_existing_log_defers_qa_report_validation(
        self, tmp_path: Path
    ) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        missing_report = qa_root / "missing.md"
        data = {
            **self._data(),
            "protocolCompliance": {
                "sessionEnd": self._session_end(str(missing_report))
            }
        }

        with mock.patch(
            "scripts.validate_session_json.artifact_dir"
        ) as artifact_dir_mock:
            result = validate_session_log(data, existing_log=True)

        assert not any("QA report" in error for error in result.errors)
        artifact_dir_mock.assert_not_called()

    def test_existing_log_ignores_explicit_validation_head(
        self,
        tmp_path: Path,
    ) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        report = qa_root / "report.md"
        self._write_report(report)
        data = {
            **self._data(),
            "protocolCompliance": {
                "sessionEnd": self._session_end(str(report))
            },
        }

        with (
            mock.patch("scripts.validate_session_json.artifact_dir") as artifact_dir_mock,
            mock.patch(
                "scripts.validate_session_json.post_qa_code_changes",
                return_value=["scripts/new_code.py"],
            ) as post_qa_code_changes,
        ):
            result = validate_session_log(
                data,
                existing_log=True,
                session_log=self.SESSION_LOG,
                validation_head="b" * 40,
            )

        assert not any("QA report" in error for error in result.errors)
        artifact_dir_mock.assert_not_called()
        post_qa_code_changes.assert_not_called()

    def test_creation_mode_defers_qa_report_validation(
        self, tmp_path: Path
    ) -> None:
        qa_root = tmp_path / "qa"
        qa_root.mkdir()
        missing_report = qa_root / "missing.md"
        data = {
            **self._data(),
            "protocolCompliance": {
                "sessionEnd": self._session_end(str(missing_report))
            }
        }

        with mock.patch(
            "scripts.validate_session_json.artifact_dir"
        ) as artifact_dir_mock:
            result = validate_session_log(data, creation_mode=True)

        assert not any("QA report" in error for error in result.errors)
        artifact_dir_mock.assert_not_called()


class TestValidateSessionLog:
    """Tests for validate_session_log function."""

    def test_valid_minimal_log(self) -> None:
        """Valid minimal log passes validation.

        "Minimal" means the six root fields SESSION-PROTOCOL.md requires, not
        the two the schema used to name (issue #3763).
        """
        data = {
            "schemaVersion": "1.0",
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test",
            },
            "protocolCompliance": {
                "sessionStart": _make_complete_start_section(),
                "sessionEnd": _make_complete_end_section(),
            },
            "workLog": [],
            "endingCommit": "",
            "nextSteps": [],
        }

        result = validate_session_log(data)

        assert result.is_valid

    def test_missing_session_section(self) -> None:
        """Missing session section causes error."""
        data: dict[str, Any] = {
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
        }

        result = validate_session_log(data)

        assert not result.is_valid
        # The schema owns presence reporting since #3346; the
        # hand-rolled "Missing: session" duplicate was removed.
        assert any("'session' is a required property" in e for e in result.errors)

    def test_missing_protocol_section(self) -> None:
        """Missing protocolCompliance section causes error."""
        data = {
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test",
            },
        }

        result = validate_session_log(data)

        assert not result.is_valid
        # The schema owns presence reporting since #3346; the
        # hand-rolled "Missing: protocolCompliance" duplicate was removed.
        assert any("'protocolCompliance' is a required property" in e for e in result.errors)


class TestValidateQaSkipScope:
    """Tests for blocking docs-only and investigation-only claim verification."""

    @staticmethod
    def _log(evidence: str = "SKIPPED: investigation-only") -> dict[str, Any]:
        return {
            "session": {"startingCommit": "a" * 40},
            "endingCommit": "b" * 40,
            "protocolCompliance": {
                "sessionEnd": {
                    "qaValidation": {
                        "Complete": True,
                        "Evidence": evidence,
                        "level": "MUST",
                    }
                }
            },
        }

    def test_eligible_range_passes(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps({"Eligible": True, "Violations": []}),
            stderr="",
        )
        result = ValidationResult()

        with mock.patch("subprocess.run", return_value=completed) as run:
            validate_qa_skip_scope(self._log(), result)

        assert result.errors == []
        assert run.call_args.args[0][-4:] == [
            "--base-ref",
            "a" * 40,
            "--head-ref",
            "b" * 40,
        ]

    def test_validation_head_extends_beyond_stale_ending_commit(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps({"Eligible": True, "Violations": []}),
            stderr="",
        )
        result = ValidationResult()

        with mock.patch("subprocess.run", return_value=completed) as run:
            validate_qa_skip_scope(
                self._log(),
                result,
                validation_head="c" * 40,
            )

        assert result.errors == []
        assert run.call_args.args[0][-4:] == [
            "--base-ref",
            "a" * 40,
            "--head-ref",
            "c" * 40,
        ]

    def test_ineligible_range_fails(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {"Eligible": False, "Violations": ["scripts/main.py"]}
            ),
            stderr="",
        )
        result = ValidationResult()

        with mock.patch("subprocess.run", return_value=completed):
            validate_qa_skip_scope(self._log(), result)

        assert result.errors == [
            "QA investigation-only scope includes disqualifying changes: "
            "scripts/main.py"
        ]

    def test_checker_error_fails_closed(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {"Eligible": False, "Violations": [], "Error": "bad ref"}
            ),
            stderr="",
        )
        result = ValidationResult()

        with mock.patch("subprocess.run", return_value=completed):
            validate_qa_skip_scope(self._log(), result)

        assert result.errors == [
            "QA investigation-only scope cannot be verified: bad ref"
        ]

    def test_docs_only_eligible_range_passes(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps({"Eligible": True, "Violations": []}),
            stderr="",
        )
        result = ValidationResult()

        with mock.patch("subprocess.run", return_value=completed) as run:
            validate_qa_skip_scope(self._log("SKIPPED: docs-only"), result)

        assert result.errors == []
        assert run.call_args.args[0][-4:] == [
            "--base-ref",
            "a" * 40,
            "--head-ref",
            "b" * 40,
        ]
        assert "test_docs_only_eligibility.py" in run.call_args.args[0][1]

    def test_docs_only_ineligible_range_fails(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {
                    "Eligible": False,
                    "Violations": ["scripts/main.py: not a documentation file"],
                }
            ),
            stderr="",
        )
        result = ValidationResult()

        with mock.patch("subprocess.run", return_value=completed):
            validate_qa_skip_scope(self._log("SKIPPED: docs-only"), result)

        assert result.errors == [
            "QA docs-only scope includes disqualifying changes: "
            "scripts/main.py: not a documentation file"
        ]

    def test_docs_only_checker_error_fails_closed(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {"Eligible": False, "Violations": [], "Error": "bad ref"}
            ),
            stderr="",
        )
        result = ValidationResult()

        with mock.patch("subprocess.run", return_value=completed):
            validate_qa_skip_scope(self._log("SKIPPED: docs-only"), result)

        assert result.errors == ["QA docs-only scope cannot be verified: bad ref"]


class TestLoadSessionFile:
    """Tests for load_session_file function."""

    def test_loads_valid_json(self, tmp_path: Path) -> None:
        """Loads valid JSON file successfully."""
        session_file = tmp_path / "session.json"
        session_file.write_text('{"test": "value"}')

        data, error = load_session_file(session_file)

        assert error is None
        assert data == {"test": "value"}

    def test_error_for_missing_file(self, tmp_path: Path) -> None:
        """Returns error for missing file."""
        session_file = tmp_path / "nonexistent.json"

        data, error = load_session_file(session_file)

        assert data is None
        assert error is not None
        assert "not found" in error

    def test_error_for_invalid_json(self, tmp_path: Path) -> None:
        """Returns error for invalid JSON."""
        session_file = tmp_path / "invalid.json"
        session_file.write_text('{"invalid": }')

        data, error = load_session_file(session_file)

        assert data is None
        assert error is not None
        assert "Invalid JSON" in error
        assert "line" in error
        assert "Common fixes" in error


class TestMainFunction:
    """Tests for main() function via monkeypatching."""

    @pytest.fixture
    def valid_session_file(self, tmp_path: Path) -> Path:
        """Create a valid session log file."""
        qa_report = tmp_path / ".agents" / "qa" / "report.md"
        qa_report.parent.mkdir(parents=True)
        qa_report.write_text(
            "---\n"
            "qaVerdict: PASS\n"
            "qaSessionLog: .agents/sessions/valid-session.json\n"
            f"qaCommit: {'a' * 40}\n"
            "---\n"
            "# QA\n",
            encoding="utf-8",
        )
        data = {
            "schemaVersion": "1.0",
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test objective",
            },
            "protocolCompliance": {
                "sessionStart": _make_complete_start_section(),
                "sessionEnd": _make_complete_end_section(
                    qaValidation={
                        "complete": True,
                        "evidence": ".agents/qa/report.md",
                        "level": "MUST",
                    }
                ),
            },
            "workLog": [],
            "endingCommit": "a" * 40,
            "nextSteps": [],
        }
        session_file = tmp_path / ".agents" / "sessions" / "valid-session.json"
        session_file.parent.mkdir(parents=True)
        session_file.write_text(json.dumps(data))
        return session_file

    @pytest.fixture
    def invalid_session_file(self, tmp_path: Path) -> Path:
        """Create an invalid session log file."""
        data: dict[str, Any] = {
            # Missing session section
            "protocolCompliance": {},
        }
        session_file = tmp_path / "invalid-session.json"
        session_file.write_text(json.dumps(data))
        return session_file

    def test_main_valid_session(
        self,
        valid_session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 0 for valid session."""
        from scripts import validate_session_json

        # Allow temp directory paths for testing
        monkeypatch.setattr(
            validate_session_json,
            "_PROJECT_ROOT",
            valid_session_file.parents[2],
        )
        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(valid_session_file)],
        )

        result = validate_session_json.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out

    def test_main_invalid_session(
        self,
        invalid_session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 1 for invalid session."""
        from scripts import validate_session_json

        # Allow temp directory paths for testing
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", invalid_session_file.parent)
        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(invalid_session_file)],
        )

        result = validate_session_json.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out

    def test_main_pre_commit_mode(
        self,
        invalid_session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with --pre-commit uses compact output."""
        from scripts import validate_session_json

        # Allow temp directory paths for testing
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", invalid_session_file.parent)
        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(invalid_session_file), "--pre-commit"],
        )

        result = validate_session_json.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        # Pre-commit mode should not show the full header
        assert "===" not in captured.out

    def test_main_missing_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 1 for missing file."""
        from scripts import validate_session_json

        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(tmp_path / "nonexistent.json")],
        )

        result = validate_session_json.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err


class TestScriptIntegration:
    """Integration tests for the script as a CLI tool."""

    @pytest.fixture
    def script_path(self, project_root: Path) -> Path:
        """Return path to the script."""
        return project_root / "scripts" / "validate_session_json.py"

    def test_help_flag(self, script_path: Path) -> None:
        """--help flag shows usage information."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "session_path" in result.stdout
        assert "--pre-commit" in result.stdout

    def test_validates_real_session(self, script_path: Path, project_root: Path) -> None:
        """Script validates real session files."""
        # Find a real session file
        sessions_dir = project_root / ".agents" / "sessions"
        session_files = list(sessions_dir.glob("*.json"))

        if not session_files:
            pytest.skip("No session files found")

        result = subprocess.run(
            [sys.executable, str(script_path), str(session_files[0])],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        # Should complete (pass or fail, but not crash)
        assert result.returncode in (0, 1)


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_session_object(self) -> None:
        """Empty session object fails validation."""
        data: dict[str, Any] = {
            "session": {},
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
        }

        result = validate_session_log(data)

        assert not result.is_valid
        # Should have multiple missing field errors
        assert len(result.errors) >= 5

    def test_null_values_in_session(self) -> None:
        """Null values treated as missing."""
        data = {
            "session": {
                "number": None,
                "date": None,
                "branch": None,
                "startingCommit": None,
                "objective": None,
            },
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
        }

        result = validate_session_log(data)

        assert not result.is_valid

    def test_extra_fields_allowed(self) -> None:
        """Extra fields in session do not cause errors."""
        data = {
            "schema": "session-protocol-v1.4",
            "schemaVersion": "1.0",
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test",
                "extraField": "allowed",
            },
            "protocolCompliance": {
                "sessionStart": _make_complete_start_section(),
                "sessionEnd": _make_complete_end_section(),
            },
            "workLog": [],
            "endingCommit": "",
            "nextSteps": [],
            "decisions": [],
            "outcome": {},
        }

        result = validate_session_log(data)

        assert result.is_valid


def _make_valid_log(**session_overrides: object) -> dict:
    """Build a session log that satisfies both the schema and the protocol checks."""
    session: dict[str, object] = {
        "number": 3346,
        "date": "2026-07-25",
        "branch": "fix/3346-session-schema-enforcement",
        "startingCommit": "1ffee3834e910608ed6c03c374fb71ff7c39bdc3",
        "objective": "Enforce the committed schema in the session log validator.",
    }
    session.update(session_overrides)
    return {
        # The four fields below are required by SESSION-PROTOCOL.md and emitted
        # by session_structure.build_session_log, but the schema did not name
        # them until issue #3763. A fixture that omitted them was only "valid"
        # against the weaker schema, so it is corrected here alongside the fix.
        "schemaVersion": "1.0",
        "session": session,
        "protocolCompliance": {
            "sessionStart": _make_complete_start_section(),
            "sessionEnd": _make_complete_end_section(),
        },
        "workLog": [],
        "endingCommit": "",
        "nextSteps": [],
    }


class TestSchemaIsActuallyEnforced:
    """The docstring promises schema validation; these prove the schema runs.

    Issue #3346: the validator advertised schema validation and never loaded the
    schema, so a bot reviewer caught by hand a `session.number` the gate passed.
    """

    def test_valid_log_passes(self) -> None:
        result = validate_session_log(_make_valid_log())
        assert result.errors == []

    def test_string_session_number_is_rejected(self) -> None:
        """The exact shape a bot reviewer caught by hand on PR #3344."""
        result = validate_session_log(_make_valid_log(number="3343-branch-context-merge"))
        assert any("number" in e and e.startswith("Schema:") for e in result.errors)

    def test_null_session_number_is_rejected(self) -> None:
        """The shape sitting in 2026-01-09-session-389.json."""
        result = validate_session_log(_make_valid_log(number=None))
        assert any("number" in e and e.startswith("Schema:") for e in result.errors)

    def test_session_number_below_minimum_is_rejected(self) -> None:
        """`minimum: 1` is a schema-only rule; no hand-rolled check covers it."""
        result = validate_session_log(_make_valid_log(number=0))
        assert any("number" in e and e.startswith("Schema:") for e in result.errors)

    def test_malformed_date_is_rejected(self) -> None:
        result = validate_session_log(_make_valid_log(date="July 25, 2026"))
        assert any("date" in e and e.startswith("Schema:") for e in result.errors)

    def test_wrong_type_for_a_declared_object_is_rejected(self) -> None:
        log = _make_valid_log()
        log["protocolCompliance"] = ["sessionStart", "sessionEnd"]
        result = validate_session_log(log)
        assert any(e.startswith("Schema:") for e in result.errors)

    def test_every_violation_is_reported_not_just_the_first(self) -> None:
        """One commit round should fix the log, not one field per round."""
        result = validate_session_log(_make_valid_log(number="x", date="nope"))
        schema_errors = [e for e in result.errors if e.startswith("Schema:")]
        assert len(schema_errors) >= 2

    def test_violation_names_the_field_path(self) -> None:
        result = validate_session_log(_make_valid_log(number="x"))
        assert any("session.number" in e for e in result.errors)

    def test_missing_section_is_reported_once_not_twice(self) -> None:
        """The schema owns presence; the hand-rolled check must not restate it."""
        log = _make_valid_log()
        del log["session"]
        result = validate_session_log(log)
        assert sum("'session' is a required property" in e for e in result.errors) == 1
        assert "Missing: session" not in result.errors

    def test_unloadable_schema_is_an_error_not_a_silent_pass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A gate that cannot load its contract has checked nothing; say so."""
        import scripts.validate_session_json as vsj

        monkeypatch.setattr(vsj, "SCHEMA_PATH", Path("/nonexistent/session-log.schema.json"))
        result = ValidationResult()
        vsj.validate_against_schema(_make_valid_log(), result)
        assert any("schema layer skipped" in e for e in result.errors)

    def test_unloadable_schema_does_not_claim_the_whole_gate_checked_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """validate_session_log still runs protocol checks; the message must not
        claim total silence when only the schema layer was skipped."""
        import scripts.validate_session_json as vsj

        monkeypatch.setattr(vsj, "SCHEMA_PATH", Path("/nonexistent/session-log.schema.json"))
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"]["handoffRead"] = {
            "complete": False,
            "evidence": "",
            "level": "MUST",
        }
        result = vsj.validate_session_log(log)
        assert not any("nothing was checked" in e for e in result.errors)
        assert any("handoffRead" in e for e in result.errors)

    @pytest.mark.parametrize(
        ("schema", "reason"),
        [
            ({"type": "nope"}, "unknown type name raises UnknownType"),
            (
                {"$schema": "http://json-schema.org/draft-07/schema#", "properties": "notadict"},
                "non-object properties raises AttributeError",
            ),
            ({"required": "notalist"}, "non-array required raises nothing until use"),
        ],
    )
    def test_an_invalid_schema_is_an_error_not_a_crash(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        schema: dict[str, object],
        reason: str,
    ) -> None:
        """Driven with real malformed schemas, not a mock of ``validator_for``.

        Mocking the constructor to raise ``SchemaError`` proves only that the
        handler is reachable. It does not prove the handler catches what
        jsonschema actually raises, and for two of these three it does not:
        ``UnknownType`` and ``AttributeError`` are not ``SchemaError``.
        """
        import scripts.validate_session_json as vsj

        schema_path = tmp_path / "broken.schema.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        monkeypatch.setattr(vsj, "SCHEMA_PATH", schema_path)

        result = ValidationResult()
        vsj.validate_against_schema(_make_valid_log(), result)

        assert any("not a valid schema" in e for e in result.errors), reason

    def test_a_valid_schema_is_not_reported_as_malformed(self) -> None:
        """Negative control: the guard must not fire on the committed schema."""
        import scripts.validate_session_json as vsj

        result = ValidationResult()
        vsj.validate_against_schema(_make_valid_log(), result)

        assert not any("not a valid schema" in e for e in result.errors)

    def test_array_indices_are_ordered_numerically_not_lexically(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pins why the sort key stays raw.

        Stringifying every path element to dodge a mixed str/int comparison
        would order index 10 ahead of index 2. Session logs carry workLog arrays
        well past ten entries, so the reordering is reachable on real data.

        The mixed comparison the stringify guards against is not: two paths are
        only compared past a shared prefix, and a shared prefix names one
        container, whose child keys are all strings or all integers.
        """
        import scripts.validate_session_json as vsj

        schema_path = tmp_path / "array.schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "type": "array",
                    "items": {"type": "string"},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(vsj, "SCHEMA_PATH", schema_path)

        document: list[object] = ["ok"] * 12
        document[2] = 2
        document[10] = 10

        result = ValidationResult()
        vsj.validate_against_schema(document, result)

        assert [e.split(":")[1].strip() for e in result.errors] == ["2", "10"]

    def test_committed_schema_is_readable(self) -> None:
        """Guards against a schema edit that leaves the file unparseable."""
        import scripts.validate_session_json as vsj

        assert vsj.SCHEMA_PATH.is_file()
        assert isinstance(vsj._load_schema(), dict)

    def test_malformed_history_timestamp_is_rejected(self) -> None:
        """The schema declares `format: "date-time"` on
        developmentPhase.history[].timestamp. jsonschema treats "format" as
        annotation-only unless a FormatChecker covering it is supplied, so
        this was previously accepted silently."""
        log = _make_valid_log()
        log["developmentPhase"] = {
            "current": "refinement",
            "history": [{"phase": "refinement", "timestamp": "not-a-date"}],
        }
        result = validate_session_log(log)
        assert any(
            "developmentPhase.history" in e and "not a" in e and e.startswith("Schema:")
            for e in result.errors
        )

    def test_valid_history_timestamp_passes(self) -> None:
        """A real RFC 3339 date-time must not be rejected by the new check."""
        log = _make_valid_log()
        log["developmentPhase"] = {
            "current": "refinement",
            "history": [{"phase": "refinement", "timestamp": "2026-07-26T01:12:11Z"}],
        }
        result = validate_session_log(log)
        assert result.errors == []

    def test_offset_naive_history_timestamp_is_rejected(self) -> None:
        """`datetime.fromisoformat` accepts a timestamp with no UTC offset,
        but RFC 3339 section 5.6 (what the schema's `format: "date-time"`
        means) requires one. A naive parse must not pass as RFC 3339."""
        log = _make_valid_log()
        log["developmentPhase"] = {
            "current": "refinement",
            "history": [{"phase": "refinement", "timestamp": "2026-07-26T01:12:11"}],
        }
        result = validate_session_log(log)
        assert any(
            "developmentPhase.history" in e and e.startswith("Schema:") for e in result.errors
        )


class TestProtocolChecksSurviveSchemaEnforcement:
    """The schema cannot express these; adding it must not displace them."""

    def test_incomplete_must_item_still_fails(self) -> None:
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"]["handoffRead"] = {
            "complete": False,
            "evidence": "",
            "level": "MUST",
        }
        result = validate_session_log(log)
        assert any("handoffRead" in e for e in result.errors)

    def test_both_checklist_casings_still_accepted(self) -> None:
        """`definitions.checklistItem` is an anyOf over Complete/complete.

        Note the asymmetry: the anyOf varies the casing of Complete and
        Evidence but declares `level` lowercase in both branches, and all
        16675 checklist items in .agents/sessions/ agree. A log spelling it
        `Level` passes the Python check (which is case-insensitive) and fails
        the schema; that is the schema's call to make, so this test pins the
        casing the corpus actually uses.
        """
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"] = {
            name: {"Complete": True, "Evidence": "Evidence", "level": "MUST"}
            for name in SESSION_START_REQUIRED_ITEMS
        }
        result = validate_session_log(log)
        assert result.errors == []


class TestHistoricalLogsAreExemptByConstruction:
    """Issue #3346 accepted exemption-by-changed-files over backfilling 131 logs.

    The exemption is not a flag anyone can forget to set: it holds because both
    call sites hand the validator one changed path at a time. These tests fail
    if a future change points the validator at the whole directory, which would
    turn every historical log into a blocking failure.
    """

    @staticmethod
    def _invoked_paths(paths: list[str]) -> list[str]:
        """Return the session paths validate_branch_sessions actually shelled out for."""
        from scripts.validation import git_hook_policy, session_scope

        seen: list[str] = []

        def _no_base(
            args: list[str], _repo_root: Path, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if args[0] == "merge-base":
                return subprocess.CompletedProcess(args, 1, "", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def _record(command: list[str], _repo_root: Path) -> subprocess.CompletedProcess[str]:
            if "scripts/validate_session_json.py" in command:
                seen.append(command[1 + command.index("scripts/validate_session_json.py")])
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(
                git_hook_policy,
                "_path_exists_at_head",
                return_value=True,
            ),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                return_value=False,
            ),
            mock.patch.object(session_scope, "_git", _no_base),
        ):
            git_hook_policy.validate_branch_sessions(paths, Path.cwd())
        return seen

    def test_git_hook_policy_validates_only_the_paths_it_is_given(self) -> None:
        given = [
            ".agents/sessions/2026-01-01-session-1.json",
            ".agents/sessions/2026-01-02-session-2.json",
        ]
        assert self._invoked_paths(given) == given

    def test_git_hook_policy_skips_non_session_paths(self) -> None:
        """Non-session files (e.g. GOTCHAS.md) passed by lefthook are ignored.

        lefthook passes all staged .agents/** files to the session-policy
        hook. Without the SESSION_PATH_RE filter, validate_branch_sessions
        would try to parse governance docs as JSON and fail every commit that
        touches both a session log and any other .agents/ file.
        """
        mixed = [
            ".agents/sessions/2026-01-01-session-1.json",
            ".agents/governance/GOTCHAS.md",
            ".agents/architecture/ADR-001.md",
        ]
        assert self._invoked_paths(mixed) == [".agents/sessions/2026-01-01-session-1.json"]

    def test_git_hook_policy_validates_nothing_when_given_nothing(self) -> None:
        """No path list means no work. A directory fallback would fail 131 logs."""
        assert self._invoked_paths([]) == []

    def test_git_hook_policy_skips_logs_already_on_main(self) -> None:
        from scripts.validation import git_hook_policy

        seen: list[str] = []
        old_path = ".agents/sessions/2026-01-01-session-1.json"
        new_path = ".agents/sessions/2026-01-02-session-2.json"

        def _record(command: list[str], _repo_root: Path) -> subprocess.CompletedProcess[str]:
            seen.append(command[1 + command.index("scripts/validate_session_json.py")])
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                side_effect=lambda _root, path: path == old_path,
            ),
            mock.patch.object(
                git_hook_policy,
                "_path_exists_at_head",
                return_value=True,
            ),
        ):
            result = git_hook_policy.validate_branch_sessions(
                [old_path, new_path],
                Path.cwd(),
            )

        assert result == 0
        assert seen == [new_path]


class TestMainNarrowsOnThePayload:
    """`main` branches on `error is not None`, not on `data is None` (issue #3346).

    The old form left `data` optional and carried a type suppression. These
    pin the observable behavior so the narrowing cannot be reverted silently.

    Fixtures live inside the repo on purpose: `validate_safe_path` rejects any
    path outside the project root, so a `tmp_path` fixture would make every
    case exit 1 for a path reason and prove nothing about the load or the
    schema.
    """

    def test_missing_file_exits_one_with_the_load_error(self, scratch: Path) -> None:
        proc = _run_cli(scratch / "absent.json")
        assert proc.returncode == 1
        assert "not found" in (proc.stdout + proc.stderr)

    def test_unparseable_file_exits_one(self, scratch: Path) -> None:
        bad = scratch / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        proc = _run_cli(bad)
        assert proc.returncode == 1
        assert "Invalid JSON" in (proc.stdout + proc.stderr)

    def test_schema_violation_exits_one(self, scratch: Path) -> None:
        """The headline acceptance criterion, driven through the CLI."""
        log = scratch / "log.json"
        log.write_text(json.dumps(_make_valid_log(number="not-an-integer")), encoding="utf-8")
        proc = _run_cli(log)
        assert proc.returncode == 1
        assert "Schema:" in (proc.stdout + proc.stderr)

    def test_valid_file_exits_zero(self, scratch: Path) -> None:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        artifact_root = scratch / ".agents"
        report = artifact_root / "qa" / "report.md"
        report.parent.mkdir(parents=True)
        sessions_root = _REPO_ROOT / ".agents" / "sessions"
        with tempfile.TemporaryDirectory(dir=sessions_root) as session_dir:
            log = Path(session_dir) / "log.json"
            session_log = log.relative_to(_REPO_ROOT).as_posix()
            report.write_text(
                "---\n"
                "qaVerdict: PASS\n"
                f"qaSessionLog: {session_log}\n"
                f"qaCommit: {commit}\n"
                "---\n"
                "# QA\n",
                encoding="utf-8",
            )
            data = _make_valid_log()
            data["endingCommit"] = commit
            data["protocolCompliance"]["sessionEnd"]["qaValidation"]["evidence"] = str(
                report
            )
            log.write_text(json.dumps(data), encoding="utf-8")
            proc = _run_cli(
                log,
                env_overrides={"AI_AGENTS_ARTIFACT_ROOT": str(artifact_root)},
            )
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestNonObjectPayloadsAreReportedNotCrashed:
    """A session log is an object, but any JSON value can reach the validator.

    Before issue #3346's review, a top-level array reached ``data.get`` and
    exited 2 with ``'list' object has no attribute 'get'``: a crash, reported as
    an internal error, for input the schema already describes.
    """

    @pytest.mark.parametrize("payload", [[1, 2, 3], "a string", 7, True])
    def test_the_schema_reports_the_type_instead_of_crashing(self, payload: object) -> None:
        result = validate_session_log(payload)
        assert not result.is_valid
        assert any("is not of type 'object'" in error for error in result.errors)

    def test_protocol_checks_do_not_run_on_a_non_object(self) -> None:
        """Only the schema speaks. A protocol message here means a mapping was assumed."""
        result = validate_session_log([1, 2, 3])
        assert all(error.startswith("Schema:") for error in result.errors)

    def test_a_non_object_file_exits_one_not_two(self, scratch: Path) -> None:
        path = scratch / "array.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert _run_cli(path).returncode == 1

    def test_json_null_reaches_the_schema_rather_than_looking_like_a_load_error(
        self, scratch: Path
    ) -> None:
        """`json.loads('null')` succeeds, so the loader reports no error for it.

        `main` therefore branches on `error`, not on the payload. Branching on
        the payload would print `ERROR: None` for a file that parsed fine.
        """
        path = scratch / "null.json"
        path.write_text("null", encoding="utf-8")

        data, error = load_session_file(path)
        assert data is None
        assert error is None

        proc = _run_cli(path)
        assert proc.returncode == 1
        assert "ERROR: None" not in (proc.stdout + proc.stderr)
        assert "is not of type 'object'" in (proc.stdout + proc.stderr)


class TestValidatorFollowsTheSchemaDeclaration:
    """The committed schema declares draft-07; pinning another draft changes meaning.

    Asserting `validator_for` returns Draft7Validator would only test jsonschema.
    These drive `validate_against_schema` against a schema whose result differs
    between the two drafts, so a hard-coded validator fails them.
    """

    # Array-form `items` is tuple validation in draft-07. Draft 2020-12 replaced
    # it with `prefixItems` and ignores this spelling, so the two drafts disagree
    # on whether [1] is valid here.
    _DIVERGENT = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "array",
        "items": [{"type": "string"}],
    }

    def test_draft_seven_semantics_are_applied(
        self, scratch: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.validate_session_json as module

        schema_path = scratch / "divergent.schema.json"
        schema_path.write_text(json.dumps(self._DIVERGENT), encoding="utf-8")
        monkeypatch.setattr(module, "SCHEMA_PATH", schema_path)

        result = ValidationResult()
        module.validate_against_schema([1], result)

        assert result.errors, "draft-07 tuple validation was not applied"
        assert any("is not of type 'string'" in error for error in result.errors)

    def test_the_committed_schema_declares_draft_seven(self) -> None:
        """Pins the premise. If the schema is upgraded, the test above must be revisited."""
        import scripts.validate_session_json as module

        schema = json.loads(module.SCHEMA_PATH.read_text(encoding="utf-8"))
        assert schema["$schema"].startswith("http://json-schema.org/draft-07/")

    def test_the_committed_schema_is_itself_valid(self) -> None:
        """A malformed schema would silently accept everything."""
        from jsonschema.validators import validator_for

        import scripts.validate_session_json as module

        schema = json.loads(module.SCHEMA_PATH.read_text(encoding="utf-8"))
        validator_for(schema).check_schema(schema)


class TestSectionAbsenceIsReportedOnce:
    """protocolCompliance.required names both sections, so Python must not restate it."""

    def test_a_missing_session_start_is_named_once(self) -> None:
        log = _make_valid_log()
        del log["protocolCompliance"]["sessionStart"]
        result = validate_session_log(log)
        naming = [error for error in result.errors if "sessionStart" in error]
        assert len(naming) == 1
        assert naming[0].startswith("Schema:")

    def test_a_missing_session_end_is_named_once(self) -> None:
        log = _make_valid_log()
        del log["protocolCompliance"]["sessionEnd"]
        result = validate_session_log(log)
        naming = [error for error in result.errors if "sessionEnd" in error]
        assert len(naming) == 1
        assert naming[0].startswith("Schema:")

    def test_a_non_mapping_section_does_not_reach_the_protocol_checks(self) -> None:
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"] = "not a mapping"
        result = validate_session_log(log)
        assert any(
            "sessionStart" in error and error.startswith("Schema:") for error in result.errors
        )


class TestCountMustFailures:
    """Issue #3365: the CI MUST counter must be able to reach a nonzero value.

    The workflow previously counted MUST failures with a regex for markdown
    table rows this validator has never emitted, so the count was pinned at 0
    and the "Enforce MUST Requirements" step could not fire on its own terms.
    """

    def test_no_errors_counts_zero(self) -> None:
        assert count_must_failures(ValidationResult()) == 0

    @pytest.mark.parametrize(
        "prefix",
        [_INCOMPLETE_MUST_PREFIX, _MISSING_REQUIRED_PREFIX, _MUST_NOT_VIOLATED_PREFIX],
        ids=["incomplete-must", "missing-required", "must-not-violated"],
    )
    def test_every_must_prefix_is_counted(self, prefix: str) -> None:
        """Each MUST-level error shape the validator emits must be countable."""
        result = ValidationResult(errors=[f"{prefix}sessionStart.handoffRead"])
        assert count_must_failures(result) == 1

    def test_non_must_errors_are_not_counted(self) -> None:
        """Schema and format errors are real failures but not MUST-level."""
        result = ValidationResult(
            errors=[
                "Invalid commit SHA format: zzz",
                "Schema: cannot load session-log.schema.json, schema layer skipped: boom",
            ]
        )
        assert count_must_failures(result) == 0

    def test_must_and_non_must_errors_are_separated(self) -> None:
        result = ValidationResult(
            errors=[
                f"{_INCOMPLETE_MUST_PREFIX}sessionStart.handoffRead",
                f"{_INCOMPLETE_MUST_PREFIX}sessionStart.serenaActivated",
                "Invalid commit SHA format: zzz",
            ]
        )
        assert count_must_failures(result) == 2
        assert len(result.errors) == 3

    def test_an_incomplete_must_item_reaches_the_counter_end_to_end(self) -> None:
        """The prefix constants must match what the validators actually emit.

        A test that only feeds hand-written strings to the counter would stay
        green if the emit sites drifted. This one runs a real validation.
        """
        start = _make_complete_start_section()
        start["handoffRead"]["complete"] = False
        result = ValidationResult()
        validate_session_start(start, result)
        assert count_must_failures(result) >= 1


class TestBuildSummary:
    """The --json-output summary is the workflow's machine-readable contract."""

    def test_a_clean_result_reports_compliant(self, tmp_path: Path) -> None:
        summary = build_summary(tmp_path / "s.json", ValidationResult())
        assert summary["verdict"] == "COMPLIANT"
        assert summary["exit_code"] == 0
        assert summary["must_failures"] == 0
        assert summary["error_count"] == 0

    def test_a_failing_result_reports_non_compliant(self, tmp_path: Path) -> None:
        result = ValidationResult(
            errors=[f"{_INCOMPLETE_MUST_PREFIX}sessionStart.handoffRead"],
            warnings=["Missing evidence: sessionEnd.changesCommitted"],
        )
        summary = build_summary(tmp_path / "s.json", result)
        assert summary["verdict"] == "NON_COMPLIANT"
        assert summary["exit_code"] == 1
        assert summary["must_failures"] == 1
        assert summary["error_count"] == 1
        assert summary["warnings"] == ["Missing evidence: sessionEnd.changesCommitted"]

    def test_non_must_errors_leave_must_failures_at_zero(self, tmp_path: Path) -> None:
        """A NON_COMPLIANT verdict with 0 MUST failures is legitimate."""
        result = ValidationResult(errors=["Invalid commit SHA format: zzz"])
        summary = build_summary(tmp_path / "s.json", result)
        assert summary["verdict"] == "NON_COMPLIANT"
        assert summary["must_failures"] == 0
        assert summary["error_count"] == 1

    def test_the_summary_is_json_serialisable(self, tmp_path: Path) -> None:
        summary = build_summary(tmp_path / "s.json", ValidationResult(errors=["boom"]))
        assert json.loads(json.dumps(summary)) == summary


class TestFilenameSessionNumber:
    """The number encoded in a session log filename."""

    def test_reads_the_number_from_a_conventional_stem(self, tmp_path: Path) -> None:
        assert filename_session_number(tmp_path / "2026-07-26-session-3355.json") == 3355

    def test_reads_the_number_when_a_slug_follows(self, tmp_path: Path) -> None:
        path = tmp_path / "2026-07-26-session-3355-validate-session-number.json"
        assert filename_session_number(path) == 3355

    def test_leading_zeros_read_as_the_integer(self, tmp_path: Path) -> None:
        """`session-09` and `session-9` name the same session."""
        assert filename_session_number(tmp_path / "2026-01-18-session-09-slug.json") == 9

    def test_a_non_numeric_discriminator_returns_none(self, tmp_path: Path) -> None:
        """Six committed logs predate the convention; they are skipped, not failed."""
        for stem in (
            "2026-03-01-session-64a-slug",
            "2026-03-01-session-critic-468-slug",
            "2026-03-01-session-pr513-slug",
            "2026-03-01-session-qa-issue-500-slug",
            "2026-03-01-session-chain1-slug",
            "2026-03-01-session-2993b-slug",
        ):
            assert filename_session_number(tmp_path / f"{stem}.json") is None, stem

    def test_a_stem_without_the_date_prefix_returns_none(self, tmp_path: Path) -> None:
        assert filename_session_number(tmp_path / "session-3355.json") is None

    def test_a_number_elsewhere_in_the_stem_is_not_read(self, tmp_path: Path) -> None:
        """The pattern anchors at the start; a slug number must not be mistaken."""
        assert filename_session_number(tmp_path / "2026-07-26-session-12-fix-3355.json") == 12


class TestValidateFilenameNumber:
    """session.number must agree with the number in the filename (issue #3355)."""

    @staticmethod
    def _check(path: Path, number: object) -> ValidationResult:
        result = ValidationResult()
        validate_filename_number(path, {"session": {"number": number}}, result)
        return result

    def test_agreement_passes(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-07-26-session-3355-slug.json", 3355)
        assert result.errors == []

    def test_disagreement_is_an_error(self, tmp_path: Path) -> None:
        """The reported bite: filename 3342 carrying number 3343."""
        result = self._check(tmp_path / "2026-07-26-session-3342-slug.json", 3343)
        assert len(result.errors) == 1
        assert "3343" in result.errors[0]
        assert "3342" in result.errors[0]

    def test_the_error_names_both_repairs(self, tmp_path: Path) -> None:
        """Either side can be the wrong one, so the message must not assume."""
        result = self._check(tmp_path / "2026-07-26-session-3342-slug.json", 3343)
        assert "Set session.number" in result.errors[0]
        assert "rename the file" in result.errors[0]

    def test_the_error_names_the_file(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-07-26-session-3342-slug.json", 3343)
        assert "2026-07-26-session-3342-slug.json" in result.errors[0]

    def test_leading_zeros_still_agree(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-01-18-session-09-slug.json", 9)
        assert result.errors == []

    def test_an_unparseable_stem_is_skipped(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-03-01-session-64a-slug.json", 999)
        assert result.errors == []

    def test_a_missing_number_is_left_to_the_schema(self, tmp_path: Path) -> None:
        """Reporting it here would print the same defect under two spellings."""
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", {"session": {}}, result)
        assert result.errors == []

    def test_a_string_number_is_left_to_the_schema(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-07-26-session-3355.json", "3355")
        assert result.errors == []

    def test_a_bool_number_is_left_to_the_schema(self, tmp_path: Path) -> None:
        """bool is an int subclass, so the type check has to exclude it explicitly.

        The filename number is deliberately not 1: ``True == 1`` in Python, so a
        ``session-1`` filename would agree by coercion and pass either way.
        """
        result = self._check(tmp_path / "2026-07-26-session-3355.json", True)
        assert result.errors == []

    def test_a_missing_session_object_is_skipped(self, tmp_path: Path) -> None:
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", {}, result)
        assert result.errors == []

    def test_a_non_mapping_session_is_skipped(self, tmp_path: Path) -> None:
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", {"session": []}, result)
        assert result.errors == []

    def test_a_non_mapping_root_is_skipped(self, tmp_path: Path) -> None:
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", [1, 2], result)
        assert result.errors == []

    def test_the_legacy_snake_case_shape_is_skipped(self, tmp_path: Path) -> None:
        """Pre-convention logs carry `session_number` at the root and no `session`."""
        result = ValidationResult()
        validate_filename_number(
            tmp_path / "2026-01-09-session-389.json", {"session_number": 389}, result
        )
        assert result.errors == []

    def test_the_violation_is_not_counted_as_a_must_failure(self, tmp_path: Path) -> None:
        """It is a naming defect, not a protocol MUST the session skipped."""
        result = self._check(tmp_path / "2026-07-26-session-3342.json", 3343)
        assert count_must_failures(result) == 0


class TestEveryCommittedLogSatisfiesTheFilenameInvariant:
    """The guard is only trustworthy if the corpus it governs already passes."""

    def test_no_committed_session_log_violates_it(self) -> None:
        sessions = Path(__file__).resolve().parents[1] / ".agents" / "sessions"
        violations = []
        checked = 0
        for path in sorted(sessions.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                # The validator treats an unreadable log as a failure, so
                # skipping one here would let a corrupt log land while this
                # guard stayed green on the strength of its sibling count.
                violations.append(f"{path.name}: cannot be read as JSON: {exc}")
                continue
            result = ValidationResult()
            validate_filename_number(path, data, result)
            if filename_session_number(path) is not None:
                checked += 1
            violations.extend(result.errors)

        assert violations == [], "\n".join(violations)
        assert checked > 900, f"expected the whole corpus, only reached {checked}"


class TestTheCorpusGuardDoesNotSkipUnreadableLogs:
    """The guard above walks every committed log. It used to `continue` past any
    log that failed to decode or parse, which meant a corrupt log could land
    while the test stayed green on the strength of its sibling count. The
    validator itself treats an unreadable log as a failure, so this one has to
    as well, and it has to name the file.
    """

    @staticmethod
    def _walk(sessions: Path) -> list[str]:
        """The loop under test, lifted so a temporary corpus can drive it."""
        violations: list[str] = []
        for path in sorted(sessions.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                violations.append(f"{path.name}: cannot be read as JSON: {exc}")
                continue
            result = ValidationResult()
            validate_filename_number(path, data, result)
            violations.extend(result.errors)
        return violations

    def test_a_log_that_is_not_json_is_reported_not_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "2026-07-26-session-1-x.json").write_text("{ not json", encoding="utf-8")
        violations = self._walk(tmp_path)
        assert len(violations) == 1
        assert "2026-07-26-session-1-x.json" in violations[0]

    def test_a_log_that_is_not_utf8_is_reported_not_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "2026-07-26-session-2-x.json").write_bytes(b'{"a": "\xff\xfe"}')
        violations = self._walk(tmp_path)
        assert len(violations) == 1
        assert "2026-07-26-session-2-x.json" in violations[0]

    def test_a_readable_log_produces_no_read_violation(self, tmp_path: Path) -> None:
        """Negative control: the new branch must not fire on a healthy log."""
        (tmp_path / "2026-07-26-session-7-x.json").write_text(
            json.dumps({"session": {"number": 7}}), encoding="utf-8"
        )
        assert self._walk(tmp_path) == []

    def test_the_shipped_guard_shares_this_loop(self) -> None:
        """Ties the lifted copy to the real one: if the guard stops reporting
        read failures, this catches the divergence.

        Reads the guard through inspect rather than slicing this file's text,
        so renaming a neighbouring test or reindenting cannot break it.
        """
        guard = TestEveryCommittedLogSatisfiesTheFilenameInvariant
        body = inspect.getsource(guard.test_no_committed_session_log_violates_it)
        assert "cannot be read as JSON" in body


class TestAnExistingLogIsValidatedAsARecord:
    """Issue #3385: an edit cannot make a finished session compliant.

    Two questions live in this validator. "Is this record well formed" is the
    log's own property and always binds. "Did the session run markdownlint" is
    a property of a session that already ended; demanding it on an edit is a
    demand to invent evidence, and it is what made a historical log
    uncorrectable.
    """

    @staticmethod
    def _log() -> dict:
        """A log whose shape is fine and whose checklist is honestly incomplete."""
        return {
            "session": {
                "number": 1,
                "date": "2026-02-11",
                "branch": "fix/x",
                "startingCommit": "abc1234",
            },
            "protocolCompliance": {
                "sessionStart": {
                    name: {"complete": False, "level": "MUST", "evidence": "not run"}
                    for name in SESSION_START_REQUIRED_ITEMS
                },
                "sessionEnd": {
                    name: {"complete": False, "level": "MUST", "evidence": "not run"}
                    for name in SESSION_END_REQUIRED_ITEMS
                },
            },
        }

    def test_a_new_log_still_fails_its_incomplete_musts(self) -> None:
        """The looser mode must be opt-in, or it is a bypass rather than a fix."""
        errors = validate_session_log(self._log()).errors
        assert [e for e in errors if "Incomplete MUST" in e]

    def test_an_existing_log_does_not_fail_them(self) -> None:
        errors = validate_session_log(self._log(), existing_log=True).errors
        assert [e for e in errors if "Incomplete MUST" in e] == []

    def test_an_existing_log_is_still_held_to_its_shape(self) -> None:
        """Record-only is not no-op. A malformed log is malformed either way."""
        log = self._log()
        log["session"]["number"] = "not a number"
        assert validate_session_log(log, existing_log=True).errors

    def test_the_blocked_historical_log_now_passes_as_a_record(self) -> None:
        """The concrete case from #3385, by path.

        2026-02-11-session-1198 was renamed in this change. Before it, the
        rename turned a green PR red on sessionEnd.validationPassed and
        sessionEnd.markdownLintRun, neither of which a rename can supply.
        """
        path = (
            Path(__file__).resolve().parents[1]
            / ".agents/sessions/2026-02-11-session-1198-pr-review-1146-security-fixes.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert validate_session_log(data).errors, "the log really was non-compliant"
        assert validate_session_log(data, existing_log=True).errors == []


class TestAMalformedChecklistItemIsReportedNotFatal:
    """Six committed logs store a bare boolean where the object belongs.

    Reading .items() off a bool raised AttributeError, which main() turned into
    exit 2. Exit 2 means the validator broke, so the operator went looking at
    the wrong file.
    """

    @staticmethod
    def _log(item: object) -> dict:
        start: dict[str, object] = {
            name: {"complete": True, "level": "MUST", "evidence": "done"}
            for name in SESSION_START_REQUIRED_ITEMS
        }
        start["branchVerified"] = item
        return {"protocolCompliance": {"sessionStart": start}}

    def test_a_boolean_item_is_an_error_not_an_exception(self) -> None:
        errors = validate_session_log(self._log(True)).errors
        assert any("Malformed item" in e and "branchVerified" in e for e in errors)

    def test_the_message_names_the_type_found(self) -> None:
        errors = validate_session_log(self._log(["a"])).errors
        assert any("list" in e for e in errors if "Malformed item" in e)

    def test_a_well_formed_item_is_not_reported(self) -> None:
        """Vacuity control: a rule that flags everything proves nothing."""
        errors = validate_session_log(
            self._log({"complete": True, "level": "MUST", "evidence": "done"})
        ).errors
        assert not [e for e in errors if "Malformed item" in e]

    @pytest.mark.timeout(300)
    def test_every_committed_log_can_be_validated_without_crashing(self) -> None:
        """The corpus is the reason this guard exists."""
        sessions = Path(__file__).resolve().parents[1] / ".agents" / "sessions"
        checked = 0
        for path in sorted(sessions.glob("*.json")):
            validate_session_log(json.loads(path.read_text(encoding="utf-8")))
            checked += 1
        assert checked > 900, f"expected the whole corpus, only reached {checked}"


class TestSessionScopeIsDecidedOnceForBothCallSites:
    """ADR-006: one owner for the rule, so hook and workflow cannot disagree."""

    @staticmethod
    def _stub(
        base: str = "deadbee",
        added: tuple[str, ...] = (),
        deleted: tuple[str, ...] = (),
        tracked: tuple[str, ...] = (),
    ) -> tuple[Callable[..., subprocess.CompletedProcess[str]], list[list[str]]]:
        seen: list[list[str]] = []

        def _git(
            args: list[str], _repo_root: Path, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            seen.append(args)
            if args[0] == "merge-base":
                code = 0 if base else 1
                return subprocess.CompletedProcess([], code, f"{base}\n" if base else "", "")
            if args[0] == "diff":
                body = "".join(f"A\0{name}\0" for name in added)
                body += "".join(f"D\0{name}\0" for name in deleted)
                return subprocess.CompletedProcess([], 0, body, "")
            return subprocess.CompletedProcess([], 0, "\0".join(tracked), "")

        return _git, seen

    @staticmethod
    def _added_paths_stub(
        *,
        staged_added: tuple[str, ...] = (),
        head_added: tuple[str, ...] = (),
        parents: tuple[str, ...] = (),
        head_added_by_parent: dict[str, tuple[str, ...]] | None = None,
        staged_returncode: int = 0,
        head_returncode: int = 0,
        staged_stderr: str = "",
        head_stderr: str = "",
    ) -> tuple[Callable[..., subprocess.CompletedProcess[str]], list[list[str]]]:
        seen: list[list[str]] = []

        def _git(
            args: list[str], _repo_root: Path, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            seen.append(args)
            if args == ["diff", "--cached", "--name-status", "-M", "--diff-filter=A"]:
                if staged_returncode != 0:
                    return subprocess.CompletedProcess([], staged_returncode, "", staged_stderr)
                body = "".join(f"A\t{name}\n" for name in staged_added)
                return subprocess.CompletedProcess([], 0, body, "")
            if args == ["rev-list", "--parents", "-n", "1", "HEAD"]:
                line = "HEAD"
                if parents:
                    line += f" {' '.join(parents)}"
                return subprocess.CompletedProcess([], 0, f"{line}\n", "")
            if args == ["cat-file", "-p", "HEAD"]:
                body = "".join(f"parent {parent}\n" for parent in parents)
                return subprocess.CompletedProcess([], 0, body, "")
            if args == [
                "diff-tree",
                "--root",
                "--name-status",
                "-M",
                "--diff-filter=A",
                "-r",
                "HEAD",
            ]:
                if head_returncode != 0:
                    return subprocess.CompletedProcess([], head_returncode, "", head_stderr)
                body = "".join(f"A\t{name}\n" for name in head_added)
                return subprocess.CompletedProcess([], 0, body, "")
            if len(args) == 7 and args[:5] == [
                "diff-tree",
                "--name-status",
                "-M",
                "--diff-filter=A",
                "-r",
            ]:
                if head_returncode != 0:
                    return subprocess.CompletedProcess([], head_returncode, "", head_stderr)
                parent = args[5]
                added: tuple[str, ...] = ()
                if head_added_by_parent is None:
                    if parents == (parent,):
                        added = head_added
                else:
                    added = head_added_by_parent.get(parent, ())
                body = "".join(f"A\t{name}\n" for name in added)
                return subprocess.CompletedProcess([], 0, body, "")
            return subprocess.CompletedProcess([], 0, "", "")

        return _git, seen

    def test_the_shared_module_imports_no_third_party_package(self) -> None:
        """It runs under the workflow's bare python3, which has no PyYAML."""
        source = (
            Path(__file__).resolve().parents[1] / "scripts/validation/session_scope.py"
        ).read_text(encoding="utf-8")
        imports = [
            line.strip()
            for line in source.splitlines()
            if line.startswith(("import ", "from ")) and "__future__" not in line
        ]
        assert imports == [
            "import json",
            "import os",
            "import re",
            "import subprocess",
            "import sys",
            "from collections.abc import Iterable",
            "from pathlib import Path",
        ]

    def test_an_unresolvable_merge_base_validates_strictly(self) -> None:
        """Fail toward the stricter mode.

        A shallow CI checkout with no origin/main would otherwise downgrade
        every log to record-only, turning a fetch failure into a silent bypass.
        """
        from scripts.validation import session_scope

        stub, _ = self._stub(base="")
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.session_log_is_new("a.json", Path.cwd()) is True

    def test_a_git_failure_validates_strictly(self) -> None:
        from scripts.validation import session_scope

        def _boom(_args: list[str], _repo_root: Path) -> subprocess.CompletedProcess[str]:
            raise OSError("git missing")

        with mock.patch.object(session_scope, "_git", _boom):
            assert session_scope.session_merge_base(Path.cwd()) == ""
            assert session_scope.session_log_is_new("a.json", Path.cwd()) is True

    def test_a_failed_diff_validates_strictly(self) -> None:
        from scripts.validation import session_scope

        def _fail(args: list[str], _repo_root: Path) -> subprocess.CompletedProcess[str]:
            if args[0] == "merge-base":
                return subprocess.CompletedProcess([], 0, "deadbee\n", "")
            return subprocess.CompletedProcess([], 128, "", "fatal")

        with mock.patch.object(session_scope, "_git", _fail):
            assert session_scope.new_session_logs(["a.json"], Path.cwd()) == {"a.json"}

    def test_a_tracked_log_absent_from_the_added_set_is_existing(self) -> None:
        from scripts.validation import session_scope

        stub, _ = self._stub(tracked=("a.json",))
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.session_log_is_new("a.json", Path.cwd()) is False

    def test_a_log_git_reports_as_added_is_new(self) -> None:
        from scripts.validation import session_scope

        stub, _ = self._stub(added=("a.json",), tracked=("a.json",))
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.session_log_is_new("a.json", Path.cwd()) is True

    def test_a_session_replacement_still_gets_full_validation(self) -> None:
        from scripts.validation import session_scope

        new_path = ".agents/sessions/2026-08-10-session-2-new.json"
        old_path = ".agents/sessions/2026-08-10-session-1-old.json"
        stub, _ = self._stub(
            added=(new_path,),
            deleted=(old_path,),
            tracked=(new_path,),
        )
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.new_session_logs([new_path], Path.cwd()) == {new_path}

    def test_a_tab_in_a_new_session_path_is_preserved(self) -> None:
        from scripts.validation import session_scope

        path = ".agents/sessions/2026-08-10-session-1-tab\tname.json"
        stub, _ = self._stub(added=(path,), tracked=(path,))
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.new_session_logs([path], Path.cwd()) == {path}

    def test_an_untracked_log_is_new_even_though_no_diff_shows_it(self) -> None:
        """git diff never lists an untracked file; without the ls-files check
        a brand-new unstaged log would skip the whole checklist."""
        from scripts.validation import session_scope

        stub, _ = self._stub(added=(), tracked=())
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.session_log_is_new("a.json", Path.cwd()) is True

    def test_the_diff_carries_no_pathspec_so_renames_stay_paired(self) -> None:
        """Measured: the same rename reports A under a pathspec, R100 without."""
        from scripts.validation import session_scope

        stub, seen = self._stub(tracked=("a.json",))
        with mock.patch.object(session_scope, "_git", stub):
            session_scope.new_session_logs(["a.json"], Path.cwd())
        diff = next(args for args in seen if args[0] == "diff")
        assert "--" not in diff
        assert "-M" in diff
        assert diff[-1] == "deadbee"

    def test_named_ref_scope_ignores_the_working_tree(self) -> None:
        """Pre-push validates committed HEAD paths, not ambient local edits."""
        from scripts.validation import session_scope

        stub, seen = self._stub(added=("a.json",), tracked=("a.json",))
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.new_session_logs(
                ["a.json"],
                Path.cwd(),
                compare_ref="HEAD",
            ) == {"a.json"}
        diff = next(args for args in seen if args[0] == "diff")
        assert diff[-2:] == ["deadbee", "HEAD"]

    def test_the_probe_reads_the_merge_base_not_the_tip_of_main(self) -> None:
        """A log added to main after this branch started is still new here."""
        from scripts.validation import session_scope

        stub, seen = self._stub(tracked=("a.json",))
        with mock.patch.object(session_scope, "_git", stub):
            session_scope.session_log_is_new("a.json", Path.cwd())
        assert seen[0] == ["merge-base", "origin/main", "HEAD"]

    def test_a_whole_batch_costs_one_diff_and_one_listing(self) -> None:
        """A 50-log branch must not pay 50 redundant git forks."""
        from scripts.validation import session_scope

        names = ("a.json", "b.json", "c.json")
        stub, seen = self._stub(tracked=names)
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.new_session_logs(list(names), Path.cwd()) == set()
        assert [args[0] for args in seen] == ["merge-base", "diff", "ls-files"]

    def test_the_shared_helper_reads_head_adds_without_a_pathspec(self) -> None:
        """Rename detection needs the whole diff, not a path-limited half."""
        from scripts.validation import session_scope

        stub, seen = self._added_paths_stub(parents=("parent",), head_added=("a.json",))
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.added_session_paths_in_head(["a.json"], Path.cwd()) == {"a.json"}
        assert seen == [
            ["rev-list", "--parents", "-n", "1", "HEAD"],
            ["diff-tree", "--name-status", "-M", "--diff-filter=A", "-r", "parent", "HEAD"],
        ]

    def test_the_shared_helper_returns_none_on_git_failure(self) -> None:
        from scripts.validation import session_scope

        stub, _ = self._added_paths_stub(
            parents=("parent",),
            head_returncode=128,
            head_stderr="fatal: bad HEAD",
        )
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.added_session_paths_in_head(["a.json"], Path.cwd()) is None

    def test_the_shared_helper_marks_merge_commit_adds_only_when_all_parents_add(self) -> None:
        from scripts.validation import session_scope

        stub, _ = self._added_paths_stub(
            parents=("left", "right"),
            head_added_by_parent={"left": ("a.json",), "right": ("a.json",)},
        )
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.added_session_paths_in_head(["a.json"], Path.cwd()) == {"a.json"}

    def test_the_shared_helper_rejects_merge_commit_adds_missing_from_one_parent(self) -> None:
        from scripts.validation import session_scope

        stub, _ = self._added_paths_stub(
            parents=("left", "right"),
            head_added_by_parent={"left": ("a.json",), "right": ()},
        )
        with mock.patch.object(session_scope, "_git", stub):
            assert session_scope.added_session_paths_in_head(["a.json"], Path.cwd()) == set()

    @pytest.mark.parametrize(
        ("event_head", "update_after_add", "shallow_head", "expected"),
        [
            ("feature", False, False, {"session.json"}),
            ("", False, False, set()),
            ("feature", True, False, set()),
            ("feature", True, True, set()),
            ("main-parent", False, False, set()),
        ],
    )
    def test_synthetic_pull_request_merge_classifies_only_pr_head_additions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        event_head: str,
        update_after_add: bool,
        shallow_head: bool,
        expected: set[str],
    ) -> None:
        from scripts.validation import session_scope

        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            ).stdout.strip()

        git("init", "-b", "main")
        git("config", "user.name", "Test User")
        git("config", "user.email", "test@example.com")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-m", "test: base")

        git("switch", "-c", "feature")
        session_file = repo / "session.json"
        session_file.write_text("{}\n", encoding="utf-8")
        git("add", "session.json")
        git("commit", "-m", "test: add session")
        if update_after_add:
            session_file.write_text('{"updated": true}\n', encoding="utf-8")
            git("add", "session.json")
            git("commit", "-m", "test: update session")
        feature_head = git("rev-parse", "HEAD")
        feature_parent = git("rev-parse", "HEAD^")

        git("switch", "main")
        main_parent = git("rev-parse", "HEAD")
        git("merge", "--no-ff", "feature", "-m", "test: synthetic pull request merge")
        if shallow_head:
            (repo / ".git" / "shallow").write_text(f"{feature_head}\n", encoding="utf-8")
        event_path = repo / "event.json"
        head_sha = {
            "feature": feature_head,
            "main-parent": main_parent,
        }.get(event_head, feature_parent)
        if event_head:
            event_path.write_text(
                json.dumps({"pull_request": {"head": {"sha": head_sha}}}),
                encoding="utf-8",
            )
            monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        else:
            monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

        assert session_scope.added_session_paths_in_head(["session.json"], repo) == expected

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            None,
            {"pull_request": None},
            {"pull_request": {"head": None}},
        ],
    )
    def test_malformed_event_shapes_do_not_select_a_synthetic_pr_head(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        payload: object,
    ) -> None:
        from scripts.validation import session_scope

        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

        assert session_scope._pull_request_head_sha() == ""

    def test_the_index_add_probe_uses_the_active_alternate_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.validation import session_scope

        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *args],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        git("init")
        git("config", "user.name", "Test User")
        git("config", "user.email", "test@example.com")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-m", "test: base")

        relative = ".agents/sessions/2026-01-01-session-1.json"
        session_file = repo / relative
        session_file.parent.mkdir(parents=True)
        session_file.write_text("{}\n", encoding="utf-8")

        alternate_index = repo / ".git/alternate-index"
        alternate_index.write_bytes((repo / ".git/index").read_bytes())
        monkeypatch.setenv("GIT_INDEX_FILE", str(alternate_index))
        git("add", relative)

        assert session_scope.added_session_paths_in_index([relative], repo) == {relative}

        monkeypatch.delenv("GIT_INDEX_FILE")
        assert git("diff", "--cached", "--name-only").stdout.splitlines() == []

    def test_the_hook_runs_full_validation_for_a_branch_owned_log(self) -> None:
        from scripts.validation import git_hook_policy, session_scope

        commands: list[list[str]] = []
        branch_owned = ".agents/sessions/2026-01-01-session-1.json"

        def _record(command: list[str], _root: Path) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        stub, _ = self._stub(added=(), tracked=(branch_owned,))
        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                return_value=False,
            ),
            mock.patch.object(session_scope, "_git", stub),
            mock.patch.object(git_hook_policy, "_path_exists_at_head", return_value=True),
        ):
            git_hook_policy.validate_branch_sessions([branch_owned], Path.cwd())
        assert commands
        assert "--existing-log" in commands[0]
        assert "--creation-mode" not in commands[0]

    def test_the_hook_passes_the_flag_only_for_a_historical_log(self) -> None:
        from scripts.validation import git_hook_policy, session_scope

        commands: list[list[str]] = []
        historical = ".agents/sessions/2026-01-01-session-1.json"

        def _record(command: list[str], _root: Path) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        stub, _ = self._stub(added=(), tracked=(historical,))
        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(git_hook_policy, "_path_exists_at_head", return_value=True),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                return_value=False,
            ),
            mock.patch.object(session_scope, "_git", stub),
        ):
            git_hook_policy.validate_branch_sessions([historical], Path.cwd())
        assert commands and "--existing-log" in commands[0]

    def test_the_hook_passes_creation_mode_for_a_new_log(self) -> None:
        """A validate pass uses creation-mode only when HEAD adds the log path.

        A later commit that merely edits the same path must not keep skipping
        protocol-compliance checks forever.
        """
        from scripts.validation import git_hook_policy, session_scope

        commands: list[list[str]] = []
        new = ".agents/sessions/2026-01-02-session-2.json"

        def _record(command: list[str], _root: Path) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        stub, _ = self._stub(added=(new,), tracked=(new,))
        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                return_value=False,
            ),
            mock.patch.object(session_scope, "_git", stub),
            mock.patch.object(git_hook_policy, "_path_exists_at_head", return_value=True),
        ):
            git_hook_policy.validate_branch_sessions([new], Path.cwd())
        assert commands
        assert "--creation-mode" in commands[0], "new log must get --creation-mode"
        assert "--existing-log" not in commands[0], "new log must not get --existing-log"

    def test_the_hook_fully_validates_an_ambiguous_session_replacement(self) -> None:
        from scripts.validation import git_hook_policy, session_scope

        commands: list[list[str]] = []
        new_path = ".agents/sessions/2026-08-10-session-2-new.json"
        old_path = ".agents/sessions/2026-08-10-session-1-old.json"

        def _record(command: list[str], _root: Path) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        stub, _ = self._stub(
            added=(new_path,),
            deleted=(old_path,),
            tracked=(new_path,),
        )
        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                return_value=False,
            ),
            mock.patch.object(session_scope, "_git", stub),
            mock.patch.object(git_hook_policy, "_path_exists_at_head", return_value=False),
        ):
            git_hook_policy.validate_branch_sessions([new_path], Path.cwd())
        assert commands
        assert "--creation-mode" not in commands[0]
        assert "--existing-log" not in commands[0]

    def test_an_empty_batch_forks_no_git_at_all(self) -> None:
        from scripts.validation import git_hook_policy, session_scope

        stub, seen = self._stub()
        with mock.patch.object(session_scope, "_git", stub):
            assert git_hook_policy.validate_branch_sessions([], Path.cwd()) == 0
        assert seen == []

    def test_scope_from_git_addresses_the_blob_by_a_repo_relative_path(self) -> None:
        """git addresses paths inside the tree; an absolute path never matches."""
        import scripts.validate_session_json as vsj

        root = Path(__file__).resolve().parents[1]
        assert vsj._repo_relative(root / ".agents/sessions/x.json") == ".agents/sessions/x.json"

    def test_a_path_outside_the_repository_stays_absolute(self) -> None:
        import scripts.validate_session_json as vsj

        assert vsj._repo_relative(Path("/tmp/elsewhere.json")) == "/tmp/elsewhere.json"

    def test_session_identity_override_preserves_the_logical_sessions_path(self) -> None:
        import scripts.validate_session_json as vsj

        identity = ".agents/sessions/2026-08-10-session-42-example.json"
        assert vsj._session_identity_override(identity) == identity

    def test_session_identity_override_rejects_a_scratch_path(self) -> None:
        import scripts.validate_session_json as vsj

        with pytest.raises(ValueError):
            vsj._session_identity_override(
                ".agents/scratch/session-log-validation/example.json"
            )

    def test_an_explicit_existing_log_flag_skips_the_git_probe(self) -> None:
        """--existing-log is the caller's own answer; do not re-derive it."""
        import scripts.validate_session_json as vsj

        source = inspect.getsource(vsj.main)
        assert "args.scope_from_git and not existing_log" in source

class TestCheckSessionsCreationMode:
    """check_sessions uses staged adds, not branch ancestry, for creation-mode.

    The session-policy hook calls git_hook_policy session (singular), which
    routes to check_sessions. Only the staged add that creates the session log
    should get --creation-mode. A later commit that edits the same file gets
    --pre-commit --existing-log instead, which validates record shape and
    structure for an already-committed log but skips the protocol-compliance,
    evidence-agreement, and QA-evidence checks that --pre-commit alone runs,
    since those items cannot be made true retroactively for a session that
    already happened (e.g. a tool unavailable in the original session).
    """

    _stub = staticmethod(TestSessionScopeIsDecidedOnceForBothCallSites._stub)

    def test_check_sessions_passes_creation_mode_for_new_log(self) -> None:
        """A staged add must get --creation-mode at commit time.

        This preserves the #4425 fix for the first commit that creates the log.
        """
        from scripts.validation import git_hook_policy

        new = ".agents/sessions/2026-01-01-session-1.json"
        validate_commands: list[list[str]] = []

        def _record(command, _root):
            import subprocess

            if any("validate_session_json.py" in part for part in command):
                validate_commands.append(command)
            return subprocess.CompletedProcess(command, 0, "[PASS] Session log is valid", "")

        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(git_hook_policy, "_merge_in_progress", return_value=False),
            mock.patch.object(git_hook_policy, "added_session_paths_in_index", return_value={new}),
        ):
            rc = git_hook_policy.check_sessions([new], Path.cwd())
        assert rc == 0
        assert validate_commands, "expected exactly one validator call"
        assert "--creation-mode" in validate_commands[0], "new log must get --creation-mode"
        assert "--pre-commit" not in validate_commands[0], (
            "new log must not run pre-commit validation"
        )

    def test_check_sessions_no_creation_mode_for_existing_log(self) -> None:
        """A staged edit must NOT keep getting creation-mode forever, and must
        get --existing-log so a refinement of an already-committed log is not
        held to protocol-compliance items that cannot be made true
        retroactively (e.g. a tool unavailable in the original session).
        """
        from scripts.validation import git_hook_policy

        existing = ".agents/sessions/2026-01-01-session-1.json"
        validate_commands: list[list[str]] = []

        def _record(command, _root):
            import subprocess

            if any("validate_session_json.py" in part for part in command):
                validate_commands.append(command)
            return subprocess.CompletedProcess(command, 0, "[PASS] Session log is valid", "")

        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(git_hook_policy, "_merge_in_progress", return_value=False),
            mock.patch.object(git_hook_policy, "added_session_paths_in_index", return_value=set()),
        ):
            rc = git_hook_policy.check_sessions([existing], Path.cwd())
        assert rc == 0
        assert validate_commands
        assert "--creation-mode" not in validate_commands[0], (
            "existing log must not get --creation-mode"
        )
        assert "--existing-log" in validate_commands[0], (
            "existing log must get --existing-log so protocol-compliance is not "
            "re-enforced on every edit to an already-committed log"
        )

    def test_the_hook_passes_creation_mode_for_a_new_log(self) -> None:
        """A validate pass uses creation-mode only when HEAD adds the log path.

        A later commit that merely edits the same path must not keep skipping
        protocol-compliance checks forever.
        """
        from scripts.validation import git_hook_policy, session_scope

        commands: list[list[str]] = []
        new = ".agents/sessions/2026-01-02-session-2.json"

        def _record(command: list[str], _root: Path) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        stub, _ = self._stub(added=(new,), tracked=(new,))
        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                return_value=False,
            ),
            mock.patch.object(session_scope, "_git", stub),
            mock.patch.object(git_hook_policy, "_path_exists_at_head", return_value=True),
        ):
            git_hook_policy.validate_branch_sessions([new], Path.cwd())
        assert commands
        assert "--creation-mode" in commands[0], "new log must get --creation-mode"
        assert "--existing-log" not in commands[0], "new log must not get --existing-log"

    def test_the_hook_fully_validates_an_ambiguous_session_replacement(self) -> None:
        from scripts.validation import git_hook_policy, session_scope

        commands: list[list[str]] = []
        new_path = ".agents/sessions/2026-08-10-session-2-new.json"
        old_path = ".agents/sessions/2026-08-10-session-1-old.json"

        def _record(command: list[str], _root: Path) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        stub, _ = self._stub(
            added=(new_path,),
            deleted=(old_path,),
            tracked=(new_path,),
        )
        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(
                git_hook_policy,
                "_is_session_on_upstream_default",
                return_value=False,
            ),
            mock.patch.object(session_scope, "_git", stub),
            mock.patch.object(git_hook_policy, "_path_exists_at_head", return_value=False),
        ):
            git_hook_policy.validate_branch_sessions([new_path], Path.cwd())
        assert commands
        assert "--creation-mode" not in commands[0]
        assert "--existing-log" not in commands[0]

    def test_check_sessions_blocks_when_the_index_add_probe_fails(self) -> None:
        from scripts.validation import git_hook_policy

        path = ".agents/sessions/2026-01-01-session-1.json"
        validate_commands: list[list[str]] = []

        def _record(command, _root):
            import subprocess

            if any("validate_session_json.py" in part for part in command):
                validate_commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(git_hook_policy, "_merge_in_progress", return_value=False),
            mock.patch.object(git_hook_policy, "added_session_paths_in_index", return_value=None),
        ):
            rc = git_hook_policy.check_sessions([path], Path.cwd())
        assert rc == 1
        assert validate_commands == []

    def test_check_sessions_allows_commit_without_session_log(self) -> None:
        """The committed session-log gate is retired: no staged log is fine.

        Staging a .agents change with no session JSON must pass. check_sessions
        is validate-if-present, so an absent log returns 0 and emits no mandate.
        """
        from scripts.validation import git_hook_policy

        with mock.patch.object(git_hook_policy, "_merge_in_progress", return_value=False):
            rc = git_hook_policy.check_sessions([".agents/governance/GOTCHAS.md"], Path.cwd())
        assert rc == 0

    def test_the_hook_fully_validates_when_head_presence_is_unknown(self) -> None:
        from scripts.validation import git_hook_policy, session_scope

        commands: list[list[str]] = []

        def _record(command: list[str], _root: Path) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        new_path = ".agents/sessions/2026-08-10-session-2-new.json"
        stub, _ = self._stub(added=(new_path,), tracked=(new_path,))
        with (
            mock.patch.object(git_hook_policy, "_run_command", _record),
            mock.patch.object(session_scope, "_git", stub),
            mock.patch.object(
                git_hook_policy,
                "_path_exists_at_head",
                return_value=None,
            ),
        ):
            git_hook_policy.validate_branch_sessions([new_path], Path.cwd())
        assert commands
        assert "--creation-mode" not in commands[0]
        assert "--existing-log" not in commands[0]

def _log_with_evidence(**items: str) -> dict:
    """A valid log whose named checklist items carry the given evidence.

    Args:
        items: Checklist item name to evidence text. Items are placed in
            sessionStart for convenience, even when the protocol locates them
            in sessionEnd (e.g. changesCommitted). The cross-field check reads
            both sections, so placement does not affect test outcomes.

    Returns:
        A log that passes schema and protocol checks apart from whatever the
        supplied evidence contradicts.
    """
    log = _make_valid_log()
    start = log["protocolCompliance"]["sessionStart"]
    for name, evidence in items.items():
        start[name] = {"complete": True, "evidence": evidence, "level": "MUST"}
    return log


class TestEvidenceAgreesWithSession:
    """Evidence that describes a different session than the record does.

    Issue #3383. Logs are seeded by copying a recent log, so the previous
    session's evidence survives whenever the edit was incomplete. Every field
    is present and correctly typed, so the schema sees nothing; the document is
    simply not true.
    """

    @pytest.mark.parametrize("item", ["branchVerified", "notOnMain", "verifyBranch"])
    def test_branch_not_matching_declared_is_an_error(self, item: str) -> None:
        log = _log_with_evidence(**{item: "Verified feat/999-some-other-thing"})
        errors = validate_session_log(log).errors
        assert any("names a different branch" in e for e in errors), errors
        named = next(e for e in errors if "names a different branch" in e)
        assert "feat/999-some-other-thing" in named
        assert "fix/3346-session-schema-enforcement" in named

    def test_the_declared_branch_in_its_own_evidence_is_not_an_error(self) -> None:
        log = _log_with_evidence(
            branchVerified="git branch --show-current returned fix/3346-session-schema-enforcement"
        )
        assert not any("names a different branch" in e for e in validate_session_log(log).errors)

    @pytest.mark.parametrize(
        "evidence",
        [
            "On a feature branch, not main",
            "Compared against origin/main",
            "merge-base with main resolved",
            "",
        ],
        ids=["no-branch-named", "origin-main", "bare-main", "empty"],
    )
    def test_evidence_naming_no_feature_branch_is_not_an_error(self, evidence: str) -> None:
        """main and origin/main appear legitimately; the error fires only when evidence
        names a feature branch and none of them is the declared branch."""
        log = _log_with_evidence(branchVerified=evidence)
        assert not any("names a different branch" in e for e in validate_session_log(log).errors)

    def test_a_different_starting_commit_in_evidence_is_an_error(self) -> None:
        log = _log_with_evidence(startingCommitNoted="Starting commit: 50b05eb9")
        errors = validate_session_log(log).errors
        assert any("names a different starting commit" in e for e in errors), errors

    def test_an_abbreviation_of_the_declared_commit_is_not_an_error(self) -> None:
        """git abbreviates to whatever is unambiguous, so a prefix is the same commit."""
        log = _log_with_evidence(startingCommitNoted="Starting commit: 1ffee38")
        assert not any(
            "names a different starting commit" in e for e in validate_session_log(log).errors
        )

    def test_evidence_citing_several_commits_passes_when_one_is_the_declared_one(self) -> None:
        log = _log_with_evidence(
            startingCommitNoted="base 1ffee3834e910608ed6c03c374fb71ff7c39bdc3, head deadbeef1"
        )
        assert not any(
            "names a different starting commit" in e for e in validate_session_log(log).errors
        )

    def test_evidence_citing_no_commit_is_not_an_error(self) -> None:
        log = _log_with_evidence(startingCommitNoted="Recorded at session start")
        assert not any(
            "names a different starting commit" in e for e in validate_session_log(log).errors
        )

    def test_a_committed_claim_without_an_ending_commit_warns(self) -> None:
        log = _make_valid_log()
        log["endingCommit"] = ""
        assert any("endingCommit is empty" in w for w in validate_session_log(log).warnings)

    def test_a_committed_claim_with_an_ending_commit_does_not_warn(self) -> None:
        log = _make_valid_log()
        log["endingCommit"] = "1ffee3834e910608ed6c03c374fb71ff7c39bdc3"
        assert not any("endingCommit is empty" in w for w in validate_session_log(log).warnings)

    def test_a_log_with_no_next_steps_field_warns(self) -> None:
        """`SESSION-PROTOCOL.md` lists `nextSteps` as a required top-level field."""
        log = _make_valid_log()
        log.pop("nextSteps", None)
        assert any("nextSteps" in w for w in validate_session_log(log).warnings)

    def test_an_empty_next_steps_array_is_an_answer_and_does_not_warn(self) -> None:
        """`[]` says there is nothing to follow up. Absence says nothing at all."""
        log = _make_valid_log()
        log["nextSteps"] = []
        assert not any("nextSteps" in w for w in validate_session_log(log).warnings)

    def test_a_populated_next_steps_array_does_not_warn(self) -> None:
        log = _make_valid_log()
        log["nextSteps"] = ["Land the follow-up PR"]
        assert not any("nextSteps" in w for w in validate_session_log(log).warnings)

    def test_the_next_steps_warning_does_not_block_an_existing_log(self) -> None:
        """Negative control: 71 committed logs predate the field.

        Issue #3763 promoted nextSteps to schema-required, so a *new* log that
        omits it is now an error. The 71 records keep their old protection
        through record mode, which is the whole point of the split: the field
        is demanded of the author who can still supply it, and excused for the
        record that cannot.
        """
        log = _make_valid_log()
        log.pop("nextSteps", None)
        assert validate_session_log(log, existing_log=True).errors == []

    def test_a_new_log_without_next_steps_is_now_an_error(self) -> None:
        log = _make_valid_log()
        log.pop("nextSteps", None)
        assert any(
            "nextSteps" in e and e.startswith("Schema:") for e in validate_session_log(log).errors
        )

    def test_an_existing_log_is_not_blocked_by_a_contradiction_it_cannot_repair(self) -> None:
        """Four committed logs contradict themselves and git cannot adjudicate which
        side is true. On the record side they would be a permanent block that no
        honest edit could clear, so the check sits on the claim side. Issue #3385.
        """
        log = _log_with_evidence(branchVerified="Verified feat/999-some-other-thing")
        assert not any(
            "names a different branch" in e
            for e in validate_session_log(log, existing_log=True).errors
        )

    def test_a_malformed_log_does_not_crash_the_cross_field_checks(self) -> None:
        for broken in (
            {"session": "not a mapping", "protocolCompliance": {}},
            {"session": {"branch": 7}, "protocolCompliance": "not a mapping"},
            {"session": {"startingCommit": None}, "protocolCompliance": {"sessionStart": None}},
            {"session": {}, "protocolCompliance": {"sessionStart": {"branchVerified": "flat"}}},
        ):
            validate_session_log(broken)


class TestBranchEvidenceMayDescribeARelationship:
    """Honest evidence names a second branch whenever it explains a relationship.

    Measured on all 946 committed logs: flagging any second feature branch
    caught seven, and six were a rename, a stack, or a branched-from note. The
    rule that survives is narrower. Contamination describes the *other* session
    and never mentions this branch at all. Issue #3383.
    """

    @pytest.mark.parametrize(
        "evidence",
        [
            "fix/3346-session-schema-enforcement, stacked on fix/3385-historical-logs",
            "fix/3346-session-schema-enforcement (renamed from the initial chore/adr006 branch)",
            "Branched fix/3346-session-schema-enforcement from feat/1769-autonomous",
            "On branch chore/old-thing, then created fix/3346-session-schema-enforcement",
        ],
        ids=["stacked-on", "renamed-from", "branched-from", "switched-to"],
    )
    def test_evidence_naming_its_own_branch_and_another_is_not_an_error(
        self, evidence: str
    ) -> None:
        log = _log_with_evidence(branchVerified=evidence)
        assert not any("names a different branch" in e for e in validate_session_log(log).errors)

    def test_evidence_naming_only_another_branch_is_still_an_error(self) -> None:
        """The narrowing must not swallow the case it exists to catch."""
        log = _log_with_evidence(branchVerified="Verified feat/merge-velocity-analysis")
        assert any("names a different branch" in e for e in validate_session_log(log).errors)

    def test_a_prefix_of_the_declared_branch_counts_as_naming_it(self) -> None:
        """Logs abbreviate their own branch; that is not a second session."""
        log = _log_with_evidence(notOnMain="On fix/3346-session-schema, not main")
        assert not any("names a different branch" in e for e in validate_session_log(log).errors)


class TestEndingCommitReachability:
    """`endingCommit` was written once and never revalidated (issue #3618).

    Of 1003 committed logs, 542 leave the field empty, 332 name a SHA that is
    not an object in this repository at all, and 95 name a real commit that is
    off the current history. 34 are sound. Nothing ever looked, so a value
    orphaned by a later amend or rebase stayed in the record and seeded a
    causal-graph node pointing at a commit that does not exist.
    """

    @staticmethod
    def _make_repo(tmp_path: Path) -> tuple[Path, str, str]:
        """Build a repo and return (root, reachable_sha, existing_offbranch_sha)."""
        repo = tmp_path / "r"
        repo.mkdir()

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args],
                cwd=repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            ).stdout.strip()

        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "T")
        (repo / "a.txt").write_text("a", encoding="utf-8")
        git("add", "a.txt")
        git("commit", "-qm", "a")
        reachable = git("rev-parse", "HEAD")
        git("checkout", "-qb", "side")
        (repo / "b.txt").write_text("b", encoding="utf-8")
        git("add", "b.txt")
        git("commit", "-qm", "b")
        offbranch = git("rev-parse", "HEAD")
        git("checkout", "-q", "main")
        return repo, reachable, offbranch

    def test_a_reachable_commit_raises_no_complaint(self, tmp_path: Path) -> None:
        repo, reachable, _ = self._make_repo(tmp_path)
        assert commit_reachability_problem(reachable, repo) is None

    def test_a_sha_that_is_no_object_is_named(self, tmp_path: Path) -> None:
        repo, _, _ = self._make_repo(tmp_path)
        assert commit_reachability_problem("0" * 40, repo) == "names no commit in this repository"

    def test_a_real_commit_off_the_history_is_named(self, tmp_path: Path) -> None:
        """The amend case: the commit still exists, but nothing reaches it."""
        repo, _, offbranch = self._make_repo(tmp_path)
        assert (
            commit_reachability_problem(offbranch, repo)
            == "names a commit that is not an ancestor of HEAD"
        )

    def test_a_dash_leading_value_never_reaches_git(self, tmp_path: Path) -> None:
        """The value lands in argv, where a leading dash reads as an option (CWE-88)."""
        repo, _, _ = self._make_repo(tmp_path)
        assert commit_reachability_problem("--upload-pack=touch", repo) == "is not a commit SHA"

    def test_a_shallow_clone_stays_silent(self, tmp_path: Path) -> None:
        """Older commits are genuinely absent, so any complaint describes the clone."""
        repo, _, _ = self._make_repo(tmp_path)
        shallow = tmp_path / "shallow"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", repo.as_uri(), str(shallow)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        assert (
            subprocess.run(
                ["git", "rev-parse", "--is-shallow-repository"],
                cwd=shallow,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            ).stdout.strip()
            == "true"
        )
        assert commit_reachability_problem("0" * 40, shallow) is None

    def test_a_directory_that_is_no_repository_stays_silent(self, tmp_path: Path) -> None:
        bare = tmp_path / "plain"
        bare.mkdir()
        assert commit_reachability_problem("0" * 40, bare) is None

    def test_a_clone_source_is_built_as_a_uri_not_a_concatenation(self, tmp_path: Path) -> None:
        """`"file://" + path` is a URL only where the separator is already `/`.

        On Windows the drive path carries no leading slash, so everything after
        `file://` parses as the URL host and the path comes back empty. `git
        clone` then looks for a host named `C:\\Users\\...` and the shallow-clone
        test fails on the Windows job for a reason that has nothing to do with
        reachability. `Path.as_uri()` emits the third slash and forward
        separators, so the host stays empty on both platforms.
        """
        windows = PureWindowsPath(r"C:\Users\runner\Temp\repo")
        naive = urlparse(f"file://{windows}")
        assert naive.netloc == "C:\\Users\\runner\\Temp\\repo"
        assert naive.path == ""

        built = urlparse(tmp_path.as_uri())
        assert built.netloc == ""
        assert "\\" not in built.path
        assert built.path.startswith("/")

    def test_an_orphaned_ending_commit_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pinned to a purpose-built repo, not the ambient checkout.

        Reading the ambient repository made this test depend on how CI clones.
        The pytest job checks out at the actions/checkout default depth of 1, and
        the helper stays deliberately silent in a shallow clone because older
        commits are genuinely absent there. The assertion therefore passed
        locally against a full clone and failed in CI against a shallow one, on
        identical code. The sibling test below had the mirror-image defect: it
        passed in CI for the wrong reason, because a silent helper satisfies a
        no-warning assertion vacuously.
        """
        from scripts import validate_session_json

        repo, _, _ = self._make_repo(tmp_path)
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", repo)
        log = _make_valid_log()
        log["endingCommit"] = "0" * 40
        assert any("issue #3618" in e for e in validate_session_log(log).errors), (
            "an unresolvable endingCommit must be reported as an error (#3883)"
        )

    def test_orphan_message_mentions_squash_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Error message must mention squash merge as a cause (#4312).

        The repo uses squash-only merges, so squash is the most common reason an
        endingCommit becomes unreachable. An error message that only lists amend
        and rebase misleads contributors into looking in the wrong place.
        """
        from scripts import validate_session_json

        repo, _, _ = self._make_repo(tmp_path)
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", repo)
        log = _make_valid_log()
        log["endingCommit"] = "0" * 40
        errors = validate_session_log(log).errors
        assert any("squash" in e for e in errors), (
            "error must mention squash merge as a possible cause (#4312)"
        )

    def test_a_sound_ending_commit_does_not_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards against a check that simply always complains."""
        from scripts import validate_session_json

        repo, reachable, _ = self._make_repo(tmp_path)
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", repo)
        log = _make_valid_log()
        log["endingCommit"] = reachable
        assert not any("issue #3618" in e for e in validate_session_log(log).errors)

    def test_an_existing_log_is_never_rechecked(self) -> None:
        """427 committed logs carry a broken SHA. They are records, not claims,
        and no honest edit could repair them, so the check sits on the claim
        side of the issue #3385 line with the other cross-field checks."""
        log = _make_valid_log()
        log["endingCommit"] = "0" * 40
        result = validate_session_log(log, existing_log=True)
        assert not any("issue #3618" in e for e in result.errors)

    def test_a_malformed_value_is_left_to_the_schema(self) -> None:
        """Reporting it here too would print one fact under two spellings."""
        log = _make_valid_log()
        log["endingCommit"] = "not-a-sha"
        assert not any("issue #3618" in e for e in validate_session_log(log).errors)

    def test_an_empty_value_keeps_its_own_warning(self) -> None:
        log = _make_valid_log()
        log["endingCommit"] = ""
        warnings = validate_session_log(log).warnings
        assert any("endingCommit is empty" in w for w in warnings)
        assert not any("issue #3618" in w for w in warnings)

    def test_orphaned_ending_commit_message_names_squash_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The error message names squash merge as a cause (issue #4312).

        The most common cause in this repo is a squash merge: the branch is
        merged and the branch commits disappear from the history, leaving the
        logged endingCommit unreachable. The old message only mentioned amend
        and rebase, sending users down a dead end.
        """
        from scripts import validate_session_json

        repo, _, _ = self._make_repo(tmp_path)
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", repo)
        log = _make_valid_log()
        log["endingCommit"] = "0" * 40
        errors = validate_session_log(log).errors
        matching = [e for e in errors if "issue #3618" in e]
        assert matching, "expected at least one error referencing issue #3618"
        message = matching[0]
        assert "squash" in message.lower(), (
            f"error message should name squash merge as a cause (#4312); got: {message!r}"
        )


class TestARequiredItemCannotChooseItsOwnEnforcement:
    """Issue #3747: every check in validate_must_item reads the item's own
    `level`, so the document being checked decided how hard it was checked.

    Two exits followed. Demotion to SHOULD silences an incomplete MUST, which
    is the one the issue names. An absent `level` skips every branch, so the
    item is not merely lenient, it is unread. Measured over the 1,027 committed
    logs, the unnamed hole is the larger one: 138 required items carry no level
    and *zero* demotions lack justification.
    """

    @staticmethod
    def _check(item: object, *, required: bool = True) -> ValidationResult:
        result = ValidationResult()
        validate_must_item(item, "branchVerified", "sessionStart", result, is_required=required)
        return result

    def test_a_required_item_with_no_level_is_an_error(self) -> None:
        """The 138-instance hole. `branchVerified` and `notOnMain` are 23 of them,
        and they are the two items that answer "did this run on main"."""
        errors = self._check({"complete": False, "evidence": ""}).errors
        assert any(e.startswith(_MISSING_LEVEL_PREFIX) for e in errors)

    def test_a_required_item_with_no_level_is_an_error_even_when_complete(self) -> None:
        """Completeness is the item's own claim. An unread item's claim is unread."""
        errors = self._check({"complete": True, "evidence": "on feat/x"}).errors
        assert any(e.startswith(_MISSING_LEVEL_PREFIX) for e in errors)

    def test_an_optional_item_with_no_level_is_left_alone(self) -> None:
        """Isolating negative control for the is_required flag.

        Without the flag the rule would fire on every optional item in every
        log. This is the assertion that proves the flag itself is load-bearing
        rather than decoration.
        """
        errors = self._check({"complete": False, "evidence": ""}, required=False).errors
        assert not any(e.startswith(_MISSING_LEVEL_PREFIX) for e in errors)

    def test_a_demoted_incomplete_item_without_evidence_is_an_error(self) -> None:
        """The bypass #3747 names. SESSION-PROTOCOL.md line 20 already requires
        documented justification to deviate from a MUST, so this enforces the
        rule as written rather than inventing policy."""
        errors = self._check({"complete": False, "level": "SHOULD", "evidence": ""}).errors
        assert any(e.startswith(_UNJUSTIFIED_DEMOTION_PREFIX) for e in errors)

    def test_a_demoted_incomplete_item_with_evidence_passes(self) -> None:
        """Isolating negative control for the demotion rule.

        Demotion has to stay legal: Copilot CLI exposes no Serena tools at all,
        so pinning serenaActivated to MUST unconditionally would make every
        Copilot session permanently invalid. All 257 demotions in the committed
        corpus already carry justification, so the rule ratifies practice.
        """
        errors = self._check(
            {
                "complete": False,
                "level": "SHOULD",
                "evidence": "Serena MCP not exposed by this harness",
            }
        ).errors
        assert not any(e.startswith(_UNJUSTIFIED_DEMOTION_PREFIX) for e in errors)

    def test_whitespace_is_not_justification(self) -> None:
        errors = self._check({"complete": False, "level": "SHOULD", "evidence": "   "}).errors
        assert any(e.startswith(_UNJUSTIFIED_DEMOTION_PREFIX) for e in errors)

    def test_a_demoted_but_complete_item_passes(self) -> None:
        """Nothing was skipped, so there is no deviation to justify."""
        errors = self._check({"complete": True, "level": "SHOULD", "evidence": ""}).errors
        assert not any(e.startswith(_UNJUSTIFIED_DEMOTION_PREFIX) for e in errors)

    def test_a_must_item_is_not_reported_as_a_demotion(self) -> None:
        """Isolating negative control: the incomplete-MUST error already covers
        this, and reporting both would print one fact under two spellings."""
        errors = self._check({"complete": False, "level": "MUST", "evidence": ""}).errors
        assert any(e.startswith(_INCOMPLETE_MUST_PREFIX) for e in errors)
        assert not any(e.startswith(_UNJUSTIFIED_DEMOTION_PREFIX) for e in errors)

    def test_a_must_not_item_is_not_reported_as_a_demotion(self) -> None:
        """`notOnMain` is MUST NOT, where complete=false is the *passing* state."""
        errors = self._check({"complete": False, "level": "MUST NOT", "evidence": ""}).errors
        assert not any(e.startswith(_UNJUSTIFIED_DEMOTION_PREFIX) for e in errors)

    def test_a_malformed_item_is_not_double_reported(self) -> None:
        """A bare boolean returns early with its own message; the new rules must
        not run on it and add a second, less accurate one."""
        errors = self._check(True).errors
        assert any(e.startswith("Malformed item:") for e in errors)
        assert not any(e.startswith(_MISSING_LEVEL_PREFIX) for e in errors)

    def test_both_new_messages_are_counted_as_must_failures(self) -> None:
        """count_must_failures matches on exact prefixes, so a new MUST-level
        message that is not registered is a message CI silently never counts.
        Issue #3365 was exactly this drift."""
        assert _MISSING_LEVEL_PREFIX in _MUST_FAILURE_PREFIXES
        assert _UNJUSTIFIED_DEMOTION_PREFIX in _MUST_FAILURE_PREFIXES
        missing = self._check({"complete": False, "evidence": ""})
        demoted = self._check({"complete": False, "level": "SHOULD", "evidence": ""})
        assert count_must_failures(missing) >= 1
        assert count_must_failures(demoted) >= 1

    def test_the_checklist_walker_passes_the_flag_through(self) -> None:
        """End-to-end: the flag is computed in validate_checklist_section, so a
        unit test on validate_must_item alone would pass with the wiring cut."""
        section = _make_complete_start_section()
        del section["branchVerified"]["level"]
        result = ValidationResult()
        validate_checklist_section(section, SESSION_START_REQUIRED_ITEMS, "sessionStart", result)
        assert any(
            e.startswith(_MISSING_LEVEL_PREFIX) and "branchVerified" in e for e in result.errors
        )

    def test_the_generator_output_trips_neither_rule(self) -> None:
        """A rule that fires on the repo's own session-init template is a rule
        that blocks every new session. build_session_log emits `level` on all
        twelve required items, so both rules are pure ratchets on practice."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude/skills/session-init"))
        from session_init.session_structure import build_session_log

        log = build_session_log(
            branch="feat/probe",
            commit="a" * 40,
            session_number=1,
            objective="probe",
            current_date="2026-07-29",
        )
        errors = validate_session_log(log).errors
        assert not any(e.startswith(_MISSING_LEVEL_PREFIX) for e in errors)
        assert not any(e.startswith(_UNJUSTIFIED_DEMOTION_PREFIX) for e in errors)
        assert not any(e.startswith("Schema:") for e in errors)


class TestTheSchemaNamesEveryRequiredRootField:
    """Issue #3763: SESSION-PROTOCOL.md lists six required root fields and
    build_session_log emits all six, but the schema named two. The schema was
    the single document disagreeing with both the prose and the generator.
    """

    def test_each_promoted_field_is_individually_required(self) -> None:
        """Isolating negative control, one per field: a single `required` list
        entry could be dropped without any other assertion in this file
        noticing, because _make_valid_log supplies all four."""
        for field in ("schemaVersion", "workLog", "endingCommit", "nextSteps"):
            log = _make_valid_log()
            log.pop(field)
            errors = validate_session_log(log).errors
            assert any(field in e and e.startswith("Schema:") for e in errors), field

    def test_the_two_original_fields_still_bind(self) -> None:
        for field in ("session", "protocolCompliance"):
            log = _make_valid_log()
            log.pop(field)
            assert any(
                field in e and e.startswith("Schema:") for e in validate_session_log(log).errors
            )

    def test_an_existing_log_is_excused_from_the_four_new_fields(self) -> None:
        """544 committed logs predate schemaVersion. Renaming one must not
        demand that the renamer invent a workLog the session never wrote.
        This is the #3385 rule, applied to the fields #3763 adds."""
        log = _make_valid_log()
        for field in _RELAXED_FOR_EXISTING_LOGS:
            log.pop(field, None)
        assert validate_session_log(log, existing_log=True).errors == []

    def test_an_existing_log_is_not_excused_from_the_two_original_fields(self) -> None:
        """Isolating negative control for the relaxation: it must subtract
        exactly four names, not disable root `required` wholesale."""
        log = _make_valid_log()
        log.pop("session")
        assert any(
            "session" in e and e.startswith("Schema:")
            for e in validate_session_log(log, existing_log=True).errors
        )

    def test_the_relaxation_does_not_reach_nested_required(self) -> None:
        """`session.required` names five fields of its own. Editing the root
        list must not touch them."""
        log = _make_valid_log()
        del log["session"]["objective"]
        assert any(
            "objective" in e and e.startswith("Schema:")
            for e in validate_session_log(log, existing_log=True).errors
        )

    def test_an_empty_ending_commit_still_satisfies_required(self) -> None:
        """`required` means the key is present, not that it is filled. A log
        written at session start cannot know the SHA of the commit that will
        contain it, so demanding a value would be unsatisfiable."""
        log = _make_valid_log()
        log["endingCommit"] = ""
        assert not any(e.startswith("Schema:") for e in validate_session_log(log).errors)

    def test_the_schema_file_and_the_relaxation_list_agree(self) -> None:
        """If a future edit promotes a fifth field without adding it to the
        relaxation set, renames of old logs start failing again."""
        schema = json.loads(
            (
                Path(__file__).resolve().parents[1] / ".agents/schemas/session-log.schema.json"
            ).read_text(encoding="utf-8")
        )
        assert _RELAXED_FOR_EXISTING_LOGS < set(schema["required"])
        assert set(schema["required"]) - _RELAXED_FOR_EXISTING_LOGS == {
            "session",
            "protocolCompliance",
        }


class TestPytestSummaryContextAnchoredToClause:
    """CRITICAL 1: pytest-summary escape must only excuse the 'skipped' in its own clause.

    Post-#4001 adversarial review: _has_contradiction("354 passed; markdownlint step skipped")
    returned False because _PYTEST_SUMMARY_CONTEXT searched the entire evidence string.
    The escape hatch must only apply to 'skipped' tokens that appear in the same
    clause (bounded by ';' and newline) as the pytest summary pattern.
    """

    @staticmethod
    def _item(evidence: str) -> dict:
        return {"complete": True, "evidence": evidence, "level": "MUST"}

    @staticmethod
    def _warn(item: dict) -> bool:
        result = ValidationResult()
        validate_checklist_section({"x": item}, frozenset(), "sessionStart", result)
        return any("Evidence contradiction" in w for w in result.warnings)

    def test_cross_clause_skipped_still_flags(self) -> None:
        """354 passed in one clause must not excuse 'skipped' in a different clause."""
        evidence = "354 passed; markdownlint step skipped"
        assert self._warn(self._item(evidence)), (
            f"Expected contradiction for {evidence!r} -- 'skipped' is in a different clause"
        )

    def test_cross_clause_newline_still_flags(self) -> None:
        """Same bug via newline separator: pytest summary on one line, skip on the next."""
        evidence = "Tests: 17 passed 3 skipped\nmarkdownlint: skipped"
        # The second 'skipped' is in a different clause from "17 passed"
        assert self._warn(self._item(evidence)), (
            f"Expected contradiction for second 'skipped' in {evidence!r}"
        )

    def test_same_clause_numeric_still_passes(self) -> None:
        """17 passed 3 skipped in a single clause must remain a false-positive exclusion."""
        evidence = "17 passed 3 skipped"
        assert not self._warn(self._item(evidence)), f"False positive for {evidence!r}"

    def test_comma_separated_summary_still_passes(self) -> None:
        """14434 passed, 21 skipped, 45 xfailed must still be excused (existing test parity)."""
        evidence = "uv run pytest tests/ -q: 14434 passed, 21 skipped, 45 xfailed"
        assert not self._warn(self._item(evidence)), f"False positive for {evidence!r}"

    def test_legitimate_pytest_tallies_still_pass(self) -> None:
        """The 27 real evidence fields with pytest tallies must not become false contradictions."""
        tallies = [
            "94 passed plus 1 skipped",
            "103 passed, 2 errors, 5 skipped",
            "uv run pytest tests/ -q: 14434 passed, 21 skipped, 45 xfailed",
            "21 skipped",
            "0 skipped",
        ]
        for evidence in tallies:
            assert not self._warn(self._item(evidence)), (
                f"False positive regression for {evidence!r}"
            )

    def test_isolating_negative_control(self) -> None:
        """Bare 'skipped' with no preceding digit and no pytest context still flags."""
        evidence = "markdownlint step skipped"
        assert self._warn(self._item(evidence)), f"Expected contradiction for {evidence!r}"


class TestCreationMode:
    """CRITICAL 2: --creation-mode skips protocol-compliance but keeps full schema.

    A fresh log cannot satisfy 'Incomplete MUST' checks for items that only exist
    after the session ends. But the schema (required fields, types, date, branch)
    still fully binds at creation time.  post-#4001 adversarial review.
    """

    def test_fresh_log_passes_creation_mode(self) -> None:
        """A freshly created log with all items complete=False passes creation-mode."""
        log = _make_valid_log()
        # Set all items to incomplete (as new_session_log.py creates them)
        for section in ("sessionStart", "sessionEnd"):
            for item in log["protocolCompliance"][section].values():
                item["complete"] = False
                item["evidence"] = ""
        result = validate_session_log(log, creation_mode=True)
        assert result.errors == [], result.errors

    def test_fresh_log_fails_normal_mode(self) -> None:
        """The same log fails normal (non-creation) mode due to Incomplete MUSTs."""
        log = _make_valid_log()
        for section in ("sessionStart", "sessionEnd"):
            for item in log["protocolCompliance"][section].values():
                item["complete"] = False
                item["evidence"] = ""
        result = validate_session_log(log, creation_mode=False)
        incomplete = [e for e in result.errors if "Incomplete MUST" in e]
        assert incomplete, "Expected Incomplete MUST errors in normal mode"

    def test_schema_still_enforced_in_creation_mode(self) -> None:
        """Required schema fields (session.number, branch, etc.) still bind in creation-mode."""
        log = _make_valid_log()
        del log["session"]["number"]
        result = validate_session_log(log, creation_mode=True)
        assert any("number" in e and e.startswith("Schema:") for e in result.errors), (
            "Schema check for session.number must still run in creation-mode"
        )

    def test_creation_mode_skips_evidence_agreement(self) -> None:
        """creation_mode also skips evidence-agreement checks (nothing to agree yet)."""
        log = _make_valid_log()
        # Insert a branch mismatch: evidence names a different feature branch
        log["protocolCompliance"]["sessionStart"]["branchVerified"] = {
            "complete": True,
            "evidence": "verified on fix/old-session-branch",
            "level": "MUST",
        }
        # Session is on a different branch entirely
        log["session"]["branch"] = "fix/other-branch"
        result_normal = validate_session_log(log, creation_mode=False)
        branch_errors = [e for e in result_normal.errors if "different branch" in e]
        assert branch_errors, "Normal mode should flag branch mismatch"
        result_creation = validate_session_log(log, creation_mode=True)
        creation_branch_errors = [e for e in result_creation.errors if "different branch" in e]
        assert not creation_branch_errors, "creation_mode must skip evidence-agreement checks"

    def test_existing_log_wins_when_both_set(self) -> None:
        """existing_log=True wins when creation_mode is also True (documented precedence)."""
        log = _make_valid_log()
        for field in _RELAXED_FOR_EXISTING_LOGS:
            log.pop(field, None)
        # With existing_log=True, the four relaxed fields are not required
        result = validate_session_log(log, existing_log=True, creation_mode=True)
        assert not any(e.startswith("Schema:") for e in result.errors), result.errors

    def test_cli_creation_mode_flag(self, scratch: Path) -> None:
        """--creation-mode flag accepted by the CLI and produces PASS for a fresh log."""
        log = _make_valid_log(number=9001)
        for section in ("sessionStart", "sessionEnd"):
            for item in log["protocolCompliance"][section].values():
                item["complete"] = False
                item["evidence"] = ""
        path = scratch / "2026-07-31-session-9001-test.json"
        path.write_text(json.dumps(log))

        r = subprocess.run(
            [sys.executable, "scripts/validate_session_json.py", "--creation-mode", str(path)],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 0, f"Expected PASS, got:\n{r.stdout}"
