"""Tests for scripts/validation/check_canonical_citations.py.

Covers the heuristic from PR #1890 (Evidence Standards Layer 4 of the
PR #1887 retrospective). The check exists to flag the "I recall that X
matches Y" anti-pattern by warning when a docstring or top-level comment
asserts a mirror-claim without naming the canonical source.

Tests use temporary file trees rather than the live repo, to keep the
test result independent of how clean the repository happens to be on
any given day.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_canonical_citations.py"


def _load_module():
    """Load the script as a module under a stable name."""
    spec = importlib.util.spec_from_file_location(
        "check_canonical_citations",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ccc = _load_module()


# --- Fixtures --------------------------------------------------------------


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """Create the four scan-root directories that the script inspects."""
    for sub in (
        ".claude/hooks",
        "scripts/validation",
        "build/scripts",
        ".claude/skills",
    ):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_file(repo: Path, relpath: str, content: str) -> Path:
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# --- Positive cases (should NOT flag) --------------------------------------


def test_no_mirror_claim_passes(fake_repo: Path) -> None:
    """A file with no mirror-token in its docstring should not be flagged."""
    _write_file(
        fake_repo,
        ".claude/hooks/clean.py",
        '"""Plain hook with no mirror claim.\n\nNothing to see.\n"""\n',
    )
    violations = ccc.collect_violations(fake_repo)
    assert violations == []


def test_mirror_claim_with_path_passes(fake_repo: Path) -> None:
    """A 'matches the' claim that cites a path should NOT be flagged."""
    _write_file(
        fake_repo,
        ".claude/hooks/cited.py",
        '"""Pre-push guard.\n\n'
        "Matches the regex in scripts/validate_session_json.py.\n"
        '"""\n',
    )
    violations = ccc.collect_violations(fake_repo)
    assert violations == [], f"unexpected: {violations}"


def test_mirror_claim_in_top_comments_with_path_passes(fake_repo: Path) -> None:
    """Mirror-claim in top-of-file comments with a path passes."""
    _write_file(
        fake_repo,
        "scripts/validation/cited_via_comment.py",
        "#!/usr/bin/env python3\n"
        "# This script aligns with the contract defined in\n"
        "# build/scripts/validate_marketplace_counts.py.\n"
        "import os\n",
    )
    violations = ccc.collect_violations(fake_repo)
    assert violations == []


def test_mirror_claim_outside_top_level_is_ignored(fake_repo: Path) -> None:
    """A mirror-claim deep inside a function body is intentionally not flagged.

    The heuristic only inspects the module docstring and top-of-file
    comments. False negatives at deeper nesting are accepted; the rule
    fights the surface failure mode (file-level claim with no citation).
    """
    _write_file(
        fake_repo,
        "build/scripts/deep.py",
        '"""Module docstring with no mirror claim."""\n'
        "\n"
        "def f():\n"
        '    """matches the foo without a path."""\n'
        "    return 1\n",
    )
    violations = ccc.collect_violations(fake_repo)
    assert violations == []


def test_path_outside_top_text_does_not_save_file(fake_repo: Path) -> None:
    """Paths in function-body code do not satisfy the citation requirement.

    Citations live in the docstring or top-level comments. A path that
    only appears in a function body still leaves the file flagged.
    """
    _write_file(
        fake_repo,
        ".claude/hooks/half.py",
        '"""Pre-push guard.\n\n'
        "Mirrors the validator (no path in docstring).\n"
        '"""\n'
        "\n"
        "CITATION = 'scripts/validate_session_json.py'\n",
    )
    violations = ccc.collect_violations(fake_repo)
    assert len(violations) == 1
    assert violations[0].path.name == "half.py"


# --- Negative cases (should flag) ------------------------------------------


def test_bare_matches_claim_flagged(fake_repo: Path) -> None:
    """The canonical anti-pattern: 'matches the X' with no path."""
    _write_file(
        fake_repo,
        ".claude/hooks/bare.py",
        '"""Pre-push guard.\n\n'
        "Matches the canonical validator regex.\n"
        '"""\n',
    )
    violations = ccc.collect_violations(fake_repo)
    assert len(violations) == 1
    v = violations[0]
    assert v.path.name == "bare.py"
    assert v.matched_token == "matches the"


def test_mirrors_token_flagged(fake_repo: Path) -> None:
    """'Mirrors X' with no path flagged."""
    _write_file(
        fake_repo,
        "scripts/validation/m.py",
        '"""Mirrors the upstream contract.\n\nNo citation.\n"""\n',
    )
    violations = ccc.collect_violations(fake_repo)
    assert len(violations) == 1
    assert violations[0].matched_token in {"mirrors the", "mirrors "}


def test_aligned_with_token_flagged(fake_repo: Path) -> None:
    """'Aligned with X' with no path flagged."""
    _write_file(
        fake_repo,
        "build/scripts/a.py",
        '"""Aligned with the canonical validator.\nNo path here.\n"""\n',
    )
    violations = ccc.collect_violations(fake_repo)
    assert len(violations) == 1


def test_multiple_violations_collected(fake_repo: Path) -> None:
    """Multiple offending files are all reported."""
    _write_file(
        fake_repo,
        ".claude/hooks/one.py",
        '"""Matches the regex of the validator."""\n',
    )
    _write_file(
        fake_repo,
        "scripts/validation/two.py",
        '"""Mirrors the schema."""\n',
    )
    _write_file(
        fake_repo,
        "build/scripts/three.py",
        '"""Aligned with the canonical exit codes."""\n',
    )
    violations = ccc.collect_violations(fake_repo)
    paths = sorted(v.path.name for v in violations)
    assert paths == ["one.py", "three.py", "two.py"]


# --- Edge cases ------------------------------------------------------------


def test_empty_file_does_not_crash(fake_repo: Path) -> None:
    """Empty .py files are tolerated and not flagged."""
    _write_file(fake_repo, ".claude/hooks/empty.py", "")
    violations = ccc.collect_violations(fake_repo)
    assert violations == []


def test_syntax_error_file_does_not_crash(fake_repo: Path) -> None:
    """Files with syntax errors are tolerated; the script falls back to
    top-comment scanning rather than aborting the whole run."""
    _write_file(
        fake_repo,
        ".claude/hooks/broken.py",
        "# matches the something with a syntax error\n"
        "def (((:\n",
    )
    violations = ccc.collect_violations(fake_repo)
    # The top-of-file comment contains a mirror-claim with no path; the
    # heuristic flags it even though the AST parse fails.
    assert len(violations) == 1
    assert violations[0].matched_token == "matches the"


def test_pycache_skipped(fake_repo: Path) -> None:
    """__pycache__ directories must not be scanned."""
    _write_file(
        fake_repo,
        ".claude/hooks/__pycache__/cached.py",
        '"""Mirrors the validator with no path."""\n',
    )
    violations = ccc.collect_violations(fake_repo)
    assert violations == []


def test_no_scan_roots_returns_empty(tmp_path: Path) -> None:
    """When no scan-root directories exist, the result is empty."""
    violations = ccc.collect_violations(tmp_path)
    assert violations == []


def test_unreadable_file_silent(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file that cannot be read (e.g., bad encoding) is silently skipped."""
    target = _write_file(
        fake_repo,
        ".claude/hooks/bin.py",
        '"""matches the foo bar."""\n',
    )
    target.write_bytes(b"\xff\xfe\x00\x00")
    violations = ccc.collect_violations(fake_repo)
    assert violations == []


# --- main() / CLI ----------------------------------------------------------


def test_main_no_violations_returns_zero(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_file(
        fake_repo,
        ".claude/hooks/clean.py",
        '"""Clean docstring."""\n',
    )
    rc = ccc.main(["--repo-root", str(fake_repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[PASS]" in out


def test_main_violations_default_warns_returns_zero(
    fake_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """In soft-warn mode, violations produce output but exit 0."""
    monkeypatch.delenv("STRICT_CANONICAL_CHECK", raising=False)
    _write_file(
        fake_repo,
        ".claude/hooks/v.py",
        '"""Matches the validator."""\n',
    )
    rc = ccc.main(["--repo-root", str(fake_repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "v.py" in out


def test_main_violations_strict_returns_one(
    fake_repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With --strict, violations produce a hard failure."""
    _write_file(
        fake_repo,
        ".claude/hooks/v.py",
        '"""Matches the validator."""\n',
    )
    rc = ccc.main(["--repo-root", str(fake_repo), "--strict"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "[FAIL]" in out


def test_main_violations_strict_via_env_returns_one(
    fake_repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STRICT_CANONICAL_CHECK=1 in env upgrades to hard failure."""
    _write_file(
        fake_repo,
        ".claude/hooks/v.py",
        '"""Matches the validator."""\n',
    )
    monkeypatch.setenv("STRICT_CANONICAL_CHECK", "1")
    rc = ccc.main(["--repo-root", str(fake_repo)])
    assert rc == 1


def test_main_missing_repo_root_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A nonexistent repo-root yields exit code 2 (config error)."""
    rc = ccc.main(["--repo-root", str(tmp_path / "does-not-exist")])
    assert rc == 2


def test_main_no_scan_roots_skips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo-root without any of the scan roots emits SKIP and exits 0."""
    rc = ccc.main(["--repo-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[SKIP]" in out
