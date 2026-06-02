"""Tests for scripts/validation/check_vendor_portability.py.

Issue #2050. The check fails CI when a vendor-shipped skill script
hard-codes an upstream-only path (.agents/ or .claude/lib/) without
routing through the portability helper, unless the offender is recorded
in the baseline. Tests use temporary file trees rather than the live
repo so the result is independent of how clean the repo happens to be.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_vendor_portability.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_vendor_portability", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cvp = _load_module()


def _write(repo: Path, relpath: str, content: str) -> Path:
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Create the scan root the script inspects."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    return tmp_path


# --- collect_offenders: positive (clean) -----------------------------------


def test_clean_script_is_not_an_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/clean.py",
        "from pathlib import Path\n\nx = Path('output.json')\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_script_routing_through_helper_is_exempt(fake_repo: Path) -> None:
    # References .agents/ but imports the helper, so it is presumed portable.
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/portable.py",
        "from paths import resolve_artifact_root\n\n"
        "root = resolve_artifact_root('analysis')  # default <cwd>/.agents/\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_comments_with_upstream_paths_are_not_offenders(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/comment.py",
        "# writes to .agents/analysis when running upstream\nvalue = 'safe'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_docstrings_with_upstream_paths_are_not_offenders(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/docstring.py",
        '"""Mentions .claude/lib/paths.py in prose."""\n\nvalue = "safe"\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


# --- collect_offenders: negative (offending) -------------------------------


def test_hardcoded_agents_path_is_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/bad.py",
        "from pathlib import Path\n\nout = Path('.agents/analysis/x.md')\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/bar/scripts/bad.py"
    assert ".agents/" in offenders[0].excerpt


def test_hardcoded_claude_lib_path_is_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/baz/scripts/bad.py",
        "spec = '.claude/lib/ai_review_common/verdict.py'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/baz/scripts/bad.py"


def test_offender_line_number_points_at_first_hit(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/bad.py",
        "import os\n\n\nout = '.agents/sessions/log.json'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders[0].line == 4


# --- baseline ratchet ------------------------------------------------------


def test_baselined_offender_does_not_fail(fake_repo: Path) -> None:
    rel = ".claude/skills/bar/scripts/bad.py"
    _write(fake_repo, rel, "out = '.agents/analysis/x.md'\n")
    offenders = cvp.collect_offenders(fake_repo)

    new, known = cvp.split_offenders(offenders, {rel})

    assert new == []
    assert len(known) == 1


def test_new_offender_outside_baseline_fails(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/new_bad.py",
        "out = '.agents/analysis/x.md'\n",
    )
    offenders = cvp.collect_offenders(fake_repo)

    new, known = cvp.split_offenders(offenders, {".claude/skills/old/x.py"})

    assert len(new) == 1
    assert known == []


def test_load_baseline_ignores_comments_and_blanks(tmp_path: Path) -> None:
    bpath = tmp_path / "baseline.txt"
    bpath.write_text(
        "# header comment\n\n.claude/skills/a/x.py\n  # indented comment\n.claude/skills/b/y.py\n",
        encoding="utf-8",
    )

    entries = cvp.load_baseline(bpath)

    assert entries == {".claude/skills/a/x.py", ".claude/skills/b/y.py"}


def test_load_baseline_missing_file_returns_empty(tmp_path: Path) -> None:
    assert cvp.load_baseline(tmp_path / "nope.txt") == set()


# --- main / CLI exit codes -------------------------------------------------


def test_main_passes_when_no_offenders(fake_repo: Path) -> None:
    _write(fake_repo, ".claude/skills/foo/scripts/clean.py", "x = 1\n")

    rc = cvp.main(["--repo-root", str(fake_repo)])

    assert rc == 0


def test_main_fails_on_new_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/bad.py",
        "out = '.agents/analysis/x.md'\n",
    )

    rc = cvp.main(["--repo-root", str(fake_repo)])

    assert rc == 1


def test_main_passes_when_offender_in_baseline(fake_repo: Path) -> None:
    rel = ".claude/skills/bar/scripts/bad.py"
    _write(fake_repo, rel, "out = '.agents/analysis/x.md'\n")
    bpath = cvp.baseline_path(fake_repo)
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(rel + "\n", encoding="utf-8")

    rc = cvp.main(["--repo-root", str(fake_repo)])

    assert rc == 0


def test_main_update_baseline_writes_offenders(fake_repo: Path) -> None:
    rel = ".claude/skills/bar/scripts/bad.py"
    _write(fake_repo, rel, "out = '.agents/analysis/x.md'\n")

    rc = cvp.main(["--repo-root", str(fake_repo), "--update-baseline"])

    assert rc == 0
    written = cvp.load_baseline(cvp.baseline_path(fake_repo))
    assert written == {rel}


def test_main_skips_when_no_scan_root(tmp_path: Path) -> None:
    # No .claude/skills directory present.
    rc = cvp.main(["--repo-root", str(tmp_path)])

    assert rc == 0


def test_main_config_error_on_missing_repo_root(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    rc = cvp.main(["--repo-root", str(missing)])

    assert rc == 2


# --- edge: pycache excluded, baselined-then-removed --------------------------


def test_pycache_files_are_skipped(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/__pycache__/bad.py",
        "out = '.agents/analysis/x.md'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []
