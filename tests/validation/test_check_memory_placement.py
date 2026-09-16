"""Tests for check_memory_placement.py, the issue #5391 placement validator.

Coverage:

- ``classify()`` (pure, no I/O): each signal in isolation, each classification
  branch (evidence / suspect via one signal / normative via a heading, a
  role-contract, or a term-density-plus-ordered-procedure combination), both
  route branches, valid and invalid suppression, and the edge cases that keep
  the signals from over-firing (lowercase "must", a list broken by prose or by
  two blank lines, empty text).
- CLI (``main()``, real ``git`` in a ``tmp_path`` repo): new-vs-existing via
  ``--base HEAD``, the exit-code contract (0 clean/warning, 1 new-normative
  under ``--ci``, 2 usage/environment error), the README/``*-index.md``/
  non-``.md`` skip, ``--path`` directory-walk mode, and ``--json`` output.

Isolation: every CLI test drives a real git repository under ``tmp_path``;
nothing here touches this repository's own ``.serena/memories/`` tree.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_memory_placement as checker

# --- content fixtures used by both classify() and CLI tests -----------------

NORMATIVE_HEADING = """# Some Memory

## Constraints

1. First
2. Second
"""

EVIDENCE_INCIDENT = """# Incident Record

We noted that we must document this. We also must remember the impact.
This will never again happen the same way, we hope.
"""

SUSPECT_TERM_DENSITY = """# Suspect Memory

This must not be repeated. This should always be reviewed. This is
required for context.
"""

SUSPECT_ORDERED_ONLY = """# Suspect Ordered

1. Step one
2. Step two
3. Step three
4. Step four
5. Step five
"""

NORMATIVE_TERM_AND_ORDER = """# Combo

This MUST happen. This MUST NOT be skipped. This SHALL be documented.
This is required. This must not be forgotten.

1. One
2. Two
3. Three
4. Four
5. Five
"""

VALID_SUPPRESSION = (
    NORMATIVE_HEADING
    + "\n<!-- placement: evidence; reason: kept as rationale for ADR-0000 -->\n"
)

INVALID_SUPPRESSION = NORMATIVE_HEADING + "\n<!-- placement: evidence; reason: -->\n"

ROLE_CONTRACT = """# Some Agent

## Role

Does the thing.

## Authority

Decides the thing.
"""


# --- classify(): unit tests --------------------------------------------------


def test_classify_evidence_plain_prose_has_no_signals():
    result = checker.classify("# Notes\n\nJust some observations about the build.\n")
    assert result.label == "evidence"
    assert result.signals == ()


def test_classify_evidence_incident_record_with_lowercase_must_and_never_again():
    result = checker.classify(EVIDENCE_INCIDENT)
    assert result.label == "evidence"
    assert result.raw_label == "evidence"


def test_classify_lowercase_must_is_not_counted_as_a_normative_term():
    # Two lowercase "must" occurrences: signal (a) counts only exact-case
    # MUST/MUST NOT/SHALL or case-insensitive "must not"/never/always/required.
    result = checker.classify("must go here. must also go there.")
    assert result.signals == ()


def test_classify_normative_via_heading_signal():
    result = checker.classify(NORMATIVE_HEADING)
    assert result.label == "normative"
    assert any(s.startswith("heading:") for s in result.signals)
    assert result.route == "rule"


def test_classify_ignores_headings_and_lists_inside_fenced_code():
    # A memory that quotes a rule's shape inside a code fence is evidence
    # about that rule, not a rule. Headings and numbered steps inside the
    # fence must not fire signals (b), (c), or (d).
    text = (
        "# Observation about the review skill\n\n"
        "The skill file looked like this when it broke:\n\n"
        "```markdown\n"
        "## Constraints\n"
        "## Role\n"
        "## Handoff\n"
        "1. step\n2. step\n3. step\n4. step\n5. step\n6. step\n"
        "```\n\n"
        "It failed because the fence was unterminated in the original.\n"
    )
    result = checker.classify(text)
    assert result.label == "evidence", result.signals


def test_classify_normative_via_role_contract_signal():
    result = checker.classify(ROLE_CONTRACT)
    assert result.label == "normative"
    assert any(s.startswith("role-contract:") for s in result.signals)
    assert result.route == "agent"


def test_classify_normative_via_term_density_and_ordered_procedure_combo():
    result = checker.classify(NORMATIVE_TERM_AND_ORDER)
    assert result.label == "normative"
    assert any(s.startswith("normative-terms=") for s in result.signals)
    assert any(s.startswith("ordered-procedure=") for s in result.signals)
    # No heading or role signal fired; this file is normative purely on the
    # (a >= 5 AND c) combination, not on b or d.
    assert not any(s.startswith("heading:") for s in result.signals)
    assert not any(s.startswith("role-contract:") for s in result.signals)


def test_classify_suspect_via_term_density_alone():
    result = checker.classify(SUSPECT_TERM_DENSITY)
    assert result.label == "suspect"
    assert result.route == "rule"


def test_classify_suspect_via_ordered_procedure_alone():
    result = checker.classify(SUSPECT_ORDERED_ONLY)
    assert result.label == "suspect"
    # Signal (c) fired with normative-term count below the density threshold,
    # so this routes to a skill rather than a rule.
    assert result.route == "skill"


def test_classify_route_rule_is_the_default_for_a_plain_normative_heading():
    result = checker.classify(NORMATIVE_HEADING)
    assert result.route == "rule"


def test_classify_valid_suppression_downgrades_to_evidence():
    result = checker.classify(VALID_SUPPRESSION)
    assert result.raw_label == "normative"
    assert result.label == "evidence"
    assert result.suppressed is True
    assert result.invalid_suppression is False


def test_classify_invalid_suppression_does_not_downgrade():
    result = checker.classify(INVALID_SUPPRESSION)
    assert result.raw_label == "normative"
    assert result.label == "normative"
    assert result.suppressed is False
    assert result.invalid_suppression is True
    assert "invalid-suppression" in result.signals


def test_classify_empty_text_is_evidence():
    result = checker.classify("")
    assert result.label == "evidence"
    assert result.signals == ()


def test_classify_ordered_list_tolerates_one_blank_line_between_items():
    text = "1. one\n\n2. two\n3. three\n\n4. four\n5. five\n"
    fires, longest = checker._has_ordered_procedure(text)
    assert fires is True
    assert longest == 5


def test_classify_ordered_list_breaks_on_two_blank_lines():
    text = "1. one\n2. two\n3. three\n\n\n4. four\n5. five\n"
    fires, longest = checker._has_ordered_procedure(text)
    assert fires is False
    assert longest < 5


def test_classify_ordered_list_breaks_on_an_interrupting_prose_line():
    text = "1. one\n2. two\nsome prose here\n3. three\n4. four\n5. five\n"
    fires, _ = checker._has_ordered_procedure(text)
    assert fires is False


# --- git test-repo fixture ---------------------------------------------------


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
    )
    return env


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_git_env(),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repository with one commit, holding an empty memories dir."""
    _run_git(tmp_path, "init", "-q")
    (tmp_path / ".serena" / "memories").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# repo\n")
    _run_git(tmp_path, "add", "README.md")
    _run_git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
    return tmp_path


def _write(repo: Path, relpath: str, content: str) -> Path:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _commit_all(repo: Path, message: str) -> None:
    _run_git(repo, "add", "-A")
    _run_git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message)


# --- CLI tests ----------------------------------------------------------------


def test_new_normative_memory_fails_under_ci(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/new.md"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert ".serena/memories/new.md: normative:" in out


def test_existing_normative_file_warns_and_exits_zero(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/old.md", NORMATIVE_HEADING)
    _commit_all(repo, "add old normative memory")
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", "--base", "HEAD", ".serena/memories/old.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert ".serena/memories/old.md: normative:" in out


def test_evidence_memory_exits_zero_with_no_finding(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/incident.md", EVIDENCE_INCIDENT)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/incident.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "incident.md" not in out


def test_suspect_new_file_is_a_warning_only(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/suspect.md", SUSPECT_TERM_DENSITY)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/suspect.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert ".serena/memories/suspect.md: suspect:" in out


def test_valid_suppression_downgrades_and_reports_suppressed(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/kept.md", VALID_SUPPRESSION)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/kept.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert ".serena/memories/kept.md: suppressed:" in out


def test_invalid_suppression_is_reported_and_still_fails(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/bad-marker.md", INVALID_SUPPRESSION)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/bad-marker.md"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "invalid-suppression" in out
    assert ".serena/memories/bad-marker.md: normative:" in out


def test_readme_and_index_files_are_skipped(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/README.md", NORMATIVE_HEADING)
    _write(repo, ".serena/memories/foo-index.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", "--path", ".serena/memories"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "README.md" not in out
    assert "foo-index.md" not in out
    assert "0 file(s) examined" in out


def test_non_markdown_files_are_ignored(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/notes.txt", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", ".serena/memories/notes.txt"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "0 file(s) examined" in out


def test_path_outside_repo_exits_two(repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--path", str(repo.parent)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "outside the repository" in err


def test_bad_base_ref_exits_two(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/x.md", EVIDENCE_INCIDENT)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--base", "not-a-real-ref-xyz", ".serena/memories/x.md"])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "base ref" in err


def test_not_a_git_repository_exits_two(tmp_path: Path, monkeypatch, capsys):
    plain_dir = tmp_path / "not-a-repo"
    plain_dir.mkdir()
    monkeypatch.chdir(plain_dir)

    exit_code = checker.main([])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "not a git repository" in err


def test_json_output_parses_and_has_counts(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/normative.md", NORMATIVE_HEADING)
    _write(repo, ".serena/memories/suspect.md", SUSPECT_TERM_DENSITY)
    _write(repo, ".serena/memories/suppressed.md", VALID_SUPPRESSION)
    monkeypatch.chdir(repo)

    exit_code = checker.main(
        [
            "--ci",
            "--json",
            ".serena/memories/normative.md",
            ".serena/memories/suspect.md",
            ".serena/memories/suppressed.md",
        ]
    )

    out = capsys.readouterr().out
    report = json.loads(out)
    assert exit_code == 1
    assert report["examined"] == 3
    assert report["counts"] == {"normative": 1, "suspect": 1, "suppressed": 1}
    assert report["failing"] == 1
    assert len(report["findings"]) == 3


def test_path_directory_mode_walks_recursively(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/sub/dir/nested.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main(["--ci", "--path", ".serena/memories"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert ".serena/memories/sub/dir/nested.md: normative:" in out


def test_without_ci_flag_never_fails_even_on_a_new_normative_file(repo: Path, monkeypatch, capsys):
    _write(repo, ".serena/memories/new.md", NORMATIVE_HEADING)
    monkeypatch.chdir(repo)

    exit_code = checker.main([".serena/memories/new.md"])

    assert exit_code == 0
