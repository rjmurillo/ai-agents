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
3. Every canonical axis file is present and passes schema validation.
4. No path under .claude/lib/ai_review_common/ or .claude/skills/review/references/
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
    missing: list[str] = []
    for entry in VENDORED_SUBTREE:
        src = CLAUDE_DIR / entry
        if not src.exists():
            missing.append(entry)
            continue
        dst = target_claude / entry
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    # PR #1965 coderabbit Y12: do not silently skip missing required
    # subtrees. AC5 is a strict packaging contract; if any of the listed
    # entries is absent in the source tree, the vendored install would
    # break in the wild and the test must surface it.
    assert not missing, (
        f"vendored fixture: required source entries missing under "
        f"{CLAUDE_DIR}: {missing}"
    )
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
    """Every canonical axis ships under .claude/skills/review/references/.

    Reuses CANONICAL_ROLES so the vendored-install contract tracks the
    single authoritative axis list. Adding a new axis to that list (and a
    `references/{role}.md` file) extends this assertion with no edit here.
    """
    from tests.lib.test_axis_schema import CANONICAL_ROLES

    axes = vendored_root / ".claude" / "skills" / "review" / "references"
    assert axes.is_dir()
    for role in CANONICAL_ROLES:
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

    axes = vendored_root / ".claude" / "skills" / "review" / "references"
    for role in ("analyst", "architect", "qa", "security", "devops", "roadmap"):
        validate_axis_schema(axes / f"{role}.md")


def test_no_runtime_dependency_on_agents_or_scripts_in_lib(
    vendored_root: Path,
) -> None:
    """Vendored ai_review_common has no executable dependency on .agents/ or scripts/.

    Walks the AST of every .py file in the vendored lib and asserts:
    - no Import or ImportFrom node references `scripts.*` or `.agents.*`
    - no string literal in a Call argument references `.agents/`, `scripts/`,
      or `.github/` as a filesystem path

    Docstrings citing ``Canonical: scripts/...`` (the sync_plugin_lib.py
    marker) are acceptable: AST walk skips Expr(Constant) at module top
    level (docstrings) by inspecting only Import/ImportFrom and Call args.
    """
    import ast

    lib = vendored_root / ".claude" / "lib" / "ai_review_common"
    forbidden_path_prefixes = (".agents/", "scripts/", ".github/")
    failures: list[str] = []

    for py in lib.glob("**/*.py"):
        text = py.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as exc:
            failures.append(f"{py.name}: parse error: {exc}")
            continue
        rel = py.relative_to(vendored_root)

        for node in ast.walk(tree):
            # Reject `from scripts.X import ...` (absolute) and relative
            # imports like `from ..scripts import ...` or `from ..agents import`.
            # ast.ImportFrom: node.module never starts with `.`; relative
            # imports are signaled by node.level > 0. PR #1965 cluster V.
            if isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                # Absolute imports.
                if (
                    module_name == "scripts"
                    or module_name.startswith("scripts.")
                ):
                    failures.append(
                        f"{rel}:{node.lineno}: import from {module_name!r} "
                        f"(forbidden in vendored install)"
                    )
                # Relative imports targeting a forbidden namespace.
                if node.level > 0 and module_name in {"scripts", "agents"}:
                    failures.append(
                        f"{rel}:{node.lineno}: relative import "
                        f"(level={node.level}) of {module_name!r} "
                        f"(forbidden in vendored install)"
                    )
                if node.level > 0 and (
                    module_name.startswith("scripts.")
                    or module_name.startswith("agents.")
                ):
                    failures.append(
                        f"{rel}:{node.lineno}: relative import "
                        f"(level={node.level}) of {module_name!r} "
                        f"(forbidden in vendored install)"
                    )
            # Reject `import scripts.X`.
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "scripts" or alias.name.startswith("scripts."):
                        failures.append(
                            f"{rel}:{node.lineno}: import {alias.name!r} "
                            f"(forbidden in vendored install)"
                        )
            # Reject string-literal arguments to Call nodes that start with
            # forbidden path prefixes (e.g. open(".agents/X")).
            if isinstance(node, ast.Call):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(
                        arg.value, str
                    ):
                        for prefix in forbidden_path_prefixes:
                            if arg.value.startswith(prefix):
                                failures.append(
                                    f"{rel}:{node.lineno}: call arg "
                                    f"{arg.value!r} starts with {prefix!r} "
                                    f"(would fail in vendored install)"
                                )

    assert not failures, "vendored lib has runtime path leaks:\n" + "\n".join(
        failures
    )


def test_review_skill_loads_from_canonical_dir(vendored_root: Path) -> None:
    """/review prose names .claude/skills/review/references/ as the source.

    Structural check (grep): the skill file must reference the canonical
    directory and the verdict-merge module.
    """
    review = vendored_root / ".claude" / "skills" / "review" / "SKILL.md"
    text = review.read_text(encoding="utf-8")
    assert ".claude/skills/review/references/" in text, (
        "/review must reference canonical .claude/skills/review/references/ as source"
    )
    assert "merge_verdicts" in text, (
        "/review must invoke merge_verdicts from ai_review_common"
    )
    assert "ai_review_common" in text, (
        "/review must reference the verdict module"
    )


def test_review_skill_chains_skill_extras(vendored_root: Path) -> None:
    """/review chains the 3 local-only skill axes after the canonical axes."""
    review = vendored_root / ".claude" / "skills" / "review" / "SKILL.md"
    text = review.read_text(encoding="utf-8")
    for skill in ("code-qualities-assessment", "golden-principles", "taste-lints"):
        assert skill in text, f"/review missing skill chain: {skill}"


def test_review_skill_names_every_canonical_axis(vendored_root: Path) -> None:
    """/review prose names every canonical axis, including the 4 new ones (#2196).

    The dead-file bug: the four axes added by PR #2179 (reliability,
    observability, agent-safety, decision-rigor) shipped under references/
    but were never named in the dispatcher, so /review never ran them.
    This asserts the dispatcher enumerates the full canonical set.
    """
    from tests.lib.test_axis_schema import CANONICAL_ROLES

    review = vendored_root / ".claude" / "skills" / "review" / "SKILL.md"
    text = review.read_text(encoding="utf-8")
    for role in CANONICAL_ROLES:
        assert role in text, f"/review dispatcher does not name canonical axis: {role}"


def test_review_skill_dispatches_by_discovery_not_fixed_count(
    vendored_root: Path,
) -> None:
    """/review discovers axes from references/ rather than asserting a fixed count.

    Negative guard: the stale "Run 6 canonical axes" header and the
    "exactly 9 rows" contract both predate the four new axes. Their
    return would resurrect the dead-file bug, so they must be absent.
    Edge: the body must point at the discovery directory glob.
    """
    review = vendored_root / ".claude" / "skills" / "review" / "SKILL.md"
    text = review.read_text(encoding="utf-8")
    assert "Run 6 canonical axes" not in text, (
        "/review still hardcodes the 6-axis dispatch header"
    )
    assert "exactly 9 rows" not in text, (
        "/review output contract still asserts the stale 9-row count"
    )
    assert "references/*.md" in text, (
        "/review must document axis discovery from references/*.md"
    )
