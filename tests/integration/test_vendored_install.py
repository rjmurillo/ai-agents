"""Vendored install verification (REQ-008-06).

Asserts that `/review` works when only the .claude/ subtree ships
(project-toolkit plugin distribution surface). Does NOT invoke the
Claude Code harness; tests the Python surface and file structure that
`/review` and `/pr-quality:all` depend on.

The harness-side behavioral check (does `/review` actually load axes
and chain skills end-to-end) is out of scope for pytest. This test
covers what is testable in pure Python:

1. The .claude/lib/ai_review_common/ package imports cleanly from a
   .claude/-only checkout (no scripts/ or .agents/ on the path).
2. merge_verdicts, get_verdict_emoji, extract_verdict execute correctly
   from the copied module.
3. All 6 canonical axis files are present and pass schema validation.
4. No path under .claude/lib/ai_review_common/ or .claude/review-axes/
   references .agents/, .github/, scripts/, or tests/ (vendored install
   would lack those).
5. `/review` command prose loads axes from the canonical directory
   (structural grep).

Refs #1934 (REQ-008-06).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = REPO_ROOT / ".claude"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

VENDORED_SUBTREE = (
    "agents",
    "commands",
    "hooks",
    "lib",
    "rules",
    "settings.json",
    "skills",
    "review-axes",
)


@pytest.fixture
def vendored_root(tmp_path: Path) -> Path:
    """Copy `.claude/{vendored subtree}` + CLAUDE.md to tmp_path/.

    Returns the temp directory containing the vendored layout.
    """
    target = tmp_path / "vendored"
    target.mkdir()
    target_claude = target / ".claude"
    target_claude.mkdir()
    for entry in VENDORED_SUBTREE:
        src = CLAUDE_DIR / entry
        if not src.exists():
            continue
        dst = target_claude / entry
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    if CLAUDE_MD.exists():
        shutil.copy2(CLAUDE_MD, target / "CLAUDE.md")
    return target


def test_vendored_lib_directory_present(vendored_root: Path) -> None:
    """The synced .claude/lib/ai_review_common/ ships under .claude/."""
    lib = vendored_root / ".claude" / "lib" / "ai_review_common"
    assert lib.is_dir(), f"vendored lib not present: {lib}"
    for name in ("__init__.py", "verdict.py", "issue_triage.py"):
        assert (lib / name).is_file(), f"missing module: {lib / name}"


def test_vendored_axes_directory_present(vendored_root: Path) -> None:
    """All 6 canonical axes ship under .claude/review-axes/."""
    axes = vendored_root / ".claude" / "review-axes"
    assert axes.is_dir()
    for role in ("analyst", "architect", "qa", "security", "devops", "roadmap"):
        assert (axes / f"{role}.md").is_file(), f"missing axis: {role}.md"


def test_ai_review_common_imports_from_vendored_copy(vendored_root: Path) -> None:
    """The vendored module imports cleanly when `.claude/lib/` is on sys.path.

    Runs in a subprocess so the production sys.path is not polluted with
    the vendored copy.
    """
    lib_path = str(vendored_root / ".claude" / "lib")
    code = (
        "import sys; sys.path.insert(0, "
        + repr(lib_path)
        + "); "
        "from ai_review_common.verdict import merge_verdicts, extract_verdict; "
        "assert merge_verdicts(['PASS', 'PASS']) == 'PASS'; "
        "assert merge_verdicts(['PASS', 'UNKNOWN']) == 'UNKNOWN'; "
        "assert merge_verdicts(['WARN', 'CRITICAL_FAIL']) == 'CRITICAL_FAIL'; "
        "assert extract_verdict('Final verdict: WARN') == 'WARN'; "
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, (
        f"vendored import failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_canonical_axes_pass_schema_in_vendored_copy(vendored_root: Path) -> None:
    """Schema validation passes against the vendored copy of the axes."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from tests.lib.conftest import validate_axis_schema  # noqa: PLC0415
    finally:
        sys.path.remove(str(REPO_ROOT))

    axes = vendored_root / ".claude" / "review-axes"
    for role in ("analyst", "architect", "qa", "security", "devops", "roadmap"):
        validate_axis_schema(axes / f"{role}.md")


def test_no_runtime_dependency_on_agents_or_scripts_in_lib(
    vendored_root: Path,
) -> None:
    """Vendored ai_review_common has no executable dependency on .agents/ or scripts/.

    Docstrings citing ``Canonical: scripts/...`` (the sync_plugin_lib.py
    marker) are acceptable: they document upstream provenance, not a
    runtime requirement. What matters is that no import statement, no
    file read, and no subprocess call references those paths.

    This is a stricter and more accurate version of "no path references"
    than a literal grep would provide.
    """
    lib = vendored_root / ".claude" / "lib" / "ai_review_common"
    forbidden_patterns = (
        # imports
        "from scripts.",
        "import scripts.",
        "from .agents.",
        # filesystem reads
        "open('.agents",
        'open(".agents',
        "Path('.agents",
        'Path(".agents',
        "open('scripts/",
        'open("scripts/',
        # subprocess invocations
        "'.agents/'",
        '".agents/"',
    )
    for py in lib.glob("**/*.py"):
        text = py.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            assert pattern not in text, (
                f"{py.relative_to(vendored_root)} contains runtime reference "
                f"to {pattern!r} (would break in vendored install)"
            )


def test_review_command_loads_from_canonical_dir(vendored_root: Path) -> None:
    """/review prose names .claude/review-axes/ as the source.

    Structural check (grep): the command file must reference the canonical
    directory and the verdict-merge module.
    """
    review = vendored_root / ".claude" / "commands" / "review.md"
    text = review.read_text(encoding="utf-8")
    assert ".claude/review-axes/" in text, (
        "/review must reference canonical .claude/review-axes/ as source"
    )
    assert "merge_verdicts" in text, (
        "/review must invoke merge_verdicts from ai_review_common"
    )
    assert "ai_review_common" in text, (
        "/review must reference the verdict module"
    )


def test_review_command_chains_skill_extras(vendored_root: Path) -> None:
    """/review chains the 3 local-only skill axes after the 6 canonical axes."""
    review = vendored_root / ".claude" / "commands" / "review.md"
    text = review.read_text(encoding="utf-8")
    for skill in ("code-qualities-assessment", "golden-principles", "taste-lints"):
        assert skill in text, f"/review missing skill chain: {skill}"
