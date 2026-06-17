"""Tests for scripts/ci/classify_semantic_title_result.py.

Covers issue #2616: the "Validate PR title" job failed because
amannn/action-semantic-pull-request received GitHub's Unicorn HTML error page
instead of an API response, on PR #2611 whose title was valid. Rerunning
recovered without changing the title.

The classifier separates a real semantic-title failure (the action sets its
`error_message` output before failing) from a transient GitHub infrastructure
flake (the action crashes fetching PR data, so `error_message` is empty and the
log carries the Unicorn HTML marker). A real failure must block (exit 1) and
echo the PR title plus the reason; a transient flake must not block (exit 0).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts/ci to path for import.
_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
sys.path.insert(0, str(_SCRIPTS_CI))

from classify_semantic_title_result import (  # noqa: E402
    Classification,
    classify,
    main,
)

UNICORN_LOG = (
    "<!DOCTYPE html>\n<title>Unicorn! · GitHub</title>\n"
    "Something went wrong, but worry not."
)
SEMANTIC_REASON = (
    'No release type found in pull request title "broken title". '
    "Add a prefix to indicate what kind of release this pull request "
    "corresponds to."
)


# --- Positive: a real semantic-title failure must block ---------------------


def test_real_semantic_failure_blocks_with_reason():
    result = classify(outcome="failure", error_message=SEMANTIC_REASON, log="")
    assert result.exit_code == 1
    assert result.is_semantic_failure is True
    assert SEMANTIC_REASON in result.message


def test_real_semantic_failure_blocks_even_when_log_has_unicorn():
    # error_message present is authoritative: a real reason blocks regardless of
    # incidental Unicorn text elsewhere in the log.
    result = classify(
        outcome="failure", error_message=SEMANTIC_REASON, log=UNICORN_LOG
    )
    assert result.exit_code == 1
    assert result.is_semantic_failure is True


# --- Negative: a transient Unicorn flake must not block ---------------------


def test_unicorn_flake_does_not_block():
    result = classify(outcome="failure", error_message="", log=UNICORN_LOG)
    assert result.exit_code == 0
    assert result.is_semantic_failure is False
    assert result.is_transient is True


def test_empty_error_without_unicorn_treated_as_transient():
    # Action failed but set no semantic reason and no Unicorn marker: still an
    # infra/unknown failure, not a title problem. Do not block the required job
    # on something that is not a title defect.
    result = classify(outcome="failure", error_message="", log="connection reset")
    assert result.exit_code == 0
    assert result.is_semantic_failure is False
    assert result.is_transient is True


# --- Success path -----------------------------------------------------------


def test_success_passes():
    result = classify(outcome="success", error_message="", log="")
    assert result.exit_code == 0
    assert result.is_semantic_failure is False


def test_skipped_passes():
    # Bot-actor skip path: the action step did not run.
    result = classify(outcome="skipped", error_message="", log="")
    assert result.exit_code == 0
    assert result.is_semantic_failure is False


# --- Edge: whitespace-only error_message is not a real reason ---------------


def test_whitespace_only_error_message_is_transient():
    result = classify(outcome="failure", error_message="   \n  ", log=UNICORN_LOG)
    assert result.exit_code == 0
    assert result.is_semantic_failure is False


# --- CLI: main echoes title + reason on a real failure and exits 1 ----------


def test_main_real_failure_echoes_title_and_reason(capsys, tmp_path):
    log_file = tmp_path / "action.log"
    log_file.write_text("", encoding="utf-8")
    exit_code = main(
        [
            "--outcome",
            "failure",
            "--error-message",
            SEMANTIC_REASON,
            "--pr-title",
            "broken title",
            "--log-file",
            str(log_file),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "broken title" in captured.out
    assert SEMANTIC_REASON in captured.out


def test_main_unicorn_flake_exits_zero(capsys, tmp_path):
    log_file = tmp_path / "action.log"
    log_file.write_text(UNICORN_LOG, encoding="utf-8")
    exit_code = main(
        [
            "--outcome",
            "failure",
            "--error-message",
            "",
            "--pr-title",
            "fix(x): valid title",
            "--log-file",
            str(log_file),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "transient" in captured.out.lower() or "unicorn" in captured.out.lower()


def test_main_success_exits_zero(capsys):
    exit_code = main(["--outcome", "success", "--error-message", "", "--pr-title", "x"])
    captured = capsys.readouterr()
    assert exit_code == 0


def test_main_missing_log_file_is_tolerated(capsys, tmp_path):
    # A missing log file should not crash; treat as no log content.
    exit_code = main(
        [
            "--outcome",
            "failure",
            "--error-message",
            "",
            "--pr-title",
            "x",
            "--log-file",
            str(tmp_path / "does-not-exist.log"),
        ]
    )
    assert exit_code == 0


def test_classification_is_a_dataclass_instance():
    result = classify(outcome="success", error_message="", log="")
    assert isinstance(result, Classification)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
