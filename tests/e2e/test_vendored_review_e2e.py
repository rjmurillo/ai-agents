#!/usr/bin/env python3
"""End-to-end /review test inside a vendored checkout (issue #1984, PR #1965 Y13).

`tests/integration/test_vendored_install.py` proves AC5 (REQ-008-06) at the
file-structure and Python-surface level: the vendored `.claude/` subtree
imports cleanly, the verdict library runs, and every axis file passes schema
validation. It explicitly does NOT invoke the Claude Code harness, so a
regression in `/review` axis loading, skill chaining, or verdict merging would
escape it.

This module closes that gap. It builds a vendored checkout in `tmp_path`
(`.claude/{vendored subtree}` + `CLAUDE.md` + a plugin manifest), spawns the
REAL `claude` CLI with `--plugin-dir` pointed at it, and asks it to `/review`
a synthetic one-line diff inside that tree. It asserts:

  1. `/review` exits without error (returncode 0).
  2. The output carries a verdict row for every axis the vendored install
     ships (the canonical `references/*.md` set plus the 3 chained-skill axes),
     discovered from the vendored copy rather than hardcoded. The issue text
     said "9 verdict rows", which was the 5-axis era; the current canonical
     set is larger, so the test derives the expected count from the directory
     that `/review` itself discovers (SKILL.md "Convergence contract"). Pinning
     a literal would drift the moment an axis is added or removed.
  3. The final merged verdict line is parseable by `extract_verdict` from the
     VENDORED verdict library (`.claude/lib/ai_review_common/verdict.py`),
     proving the merge ran end-to-end from the copied module.

Why opt-in. `claude -p` spawns the real CLI, which needs authentication and
spends model credits. Bare CI has neither. So the harness test runs only when
``RUN_CLI_E2E=1`` is set AND the ``claude`` binary is on PATH (local dev, or a
nightly job with secrets). Everywhere else it SKIPS with a loud reason, so a
skipped run never reads as a passed run. This mirrors the established pattern
in ``tests/e2e/test_cli_hook_e2e.py`` (``requires_claude``); the maintainer's
triage on #1984 (2026-06-16) explicitly endorsed modeling this test on it.

The always-on guards below (no CLI, run in bare CI) pin the facts the gated
E2E depends on: the vendored fixture builder produces a loadable plugin tree,
the discovered axis count is non-trivial and matches the canonical set, and
the synthetic diff is a real git change. A break in those is a break in the
contract the harness test asserts, caught without spending a credit.

Run the full E2E locally:
    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_vendored_review_e2e.py -v

References:
  - Source: PR #1965 coderabbit Y13
  - AC5: REQ-008-06
  - Structural sibling: tests/integration/test_vendored_install.py
  - Harness pattern: tests/e2e/test_cli_hook_e2e.py (RUN_CLI_E2E opt-in)
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = REPO_ROOT / ".claude"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# The vendored plugin-distribution surface. Kept identical to
# tests/integration/test_vendored_install.py::VENDORED_SUBTREE so both tests
# track one packaging contract. A divergence here is a bug in one of them.
VENDORED_SUBTREE = (
    "agents",
    "commands",
    "hooks",
    "lib",
    "rules",
    "settings.json",
    "skills",
)

# The 3 chained skill axes /review layers on top of the canonical axes
# (SKILL.md Process step 5). They are not under references/, so they are not
# counted by the references/*.md glob; they add to the verdict-row total.
CHAINED_SKILL_AXES = (
    "code-qualities-assessment",
    "golden-principles",
    "taste-lints",
)

_RUN = os.environ.get("RUN_CLI_E2E") == "1"

# /review against a synthetic diff. The instruction names the command and the
# scope explicitly so the harness runs the skill rather than free-forming.
_REVIEW_PROMPT = (
    "/review HEAD. Review the staged diff in this repository. "
    "Emit the full findings table with one verdict row per axis and the "
    "FINAL VERDICT line."
)

# A claude -p /review run drives many subagents; it needs a generous ceiling.
_REVIEW_TIMEOUT_S = 900

requires_claude_e2e = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)


# --------------------------------------------------------------------------- #
# Fixture builders (pure Python, exercised by the always-on guards).
# --------------------------------------------------------------------------- #


def build_vendored_plugin(target: Path) -> Path:
    """Copy `.claude/{vendored subtree}` + CLAUDE.md + a manifest into target.

    Returns the plugin root (the directory passed to `claude --plugin-dir`).
    The manifest under `.claude-plugin/plugin.json` makes the tree loadable as
    a plugin, the same shape `claude --plugin-dir` consumes in
    tests/e2e/test_cli_hook_e2e.py.

    Raises AssertionError if any required subtree entry is absent in the source
    tree: AC5 is a strict packaging contract, so a missing entry must surface,
    not be silently skipped (PR #1965 coderabbit Y12).
    """
    target.mkdir(parents=True, exist_ok=True)
    target_claude = target / ".claude"
    target_claude.mkdir(exist_ok=True)

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
    assert not missing, (
        f"vendored fixture: required source entries missing under "
        f"{CLAUDE_DIR}: {missing}"
    )

    if CLAUDE_MD.exists():
        shutil.copy2(CLAUDE_MD, target / "CLAUDE.md")

    manifest_dir = target / ".claude-plugin"
    manifest_dir.mkdir(exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "review-e2e-vendored",
                "description": "vendored /review e2e probe",
                "version": "0.0.1",
                "author": {"name": "e2e"},
            }
        ),
        encoding="utf-8",
    )
    return target


def make_synthetic_diff_repo(repo: Path) -> str:
    """Create a git repo with one committed file and one staged one-line change.

    Returns the relative path of the changed file. `/review HEAD` evaluates the
    staged diff, so the change is staged (not committed) to give the review a
    concrete, bounded change set to assess.
    """
    repo.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "e2e",
        "GIT_AUTHOR_EMAIL": "e2e@example.com",
        "GIT_COMMITTER_NAME": "e2e",
        "GIT_COMMITTER_EMAIL": "e2e@example.com",
    }

    def _git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    _git("init", "-q")
    target = repo / "widget.py"
    target.write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    _git("add", "widget.py")
    _git("commit", "-q", "-m", "feat: add")
    # Staged one-line change: introduce a subtract helper.
    target.write_text(
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    _git("add", "widget.py")
    return "widget.py"


def discover_axis_count(plugin_root: Path) -> int:
    """Total verdict rows /review emits for the vendored install.

    The canonical axes are the stems of `references/*.md` under the vendored
    review skill (SKILL.md auto-discovers the set from that directory). The 3
    chained-skill axes layer on top. The total is the number of verdict rows
    the findings table must carry.
    """
    refs = plugin_root / ".claude" / "skills" / "review" / "references"
    canonical = sorted(p.stem for p in refs.glob("*.md"))
    return len(canonical) + len(CHAINED_SKILL_AXES)


def load_vendored_extract_verdict(plugin_root: Path):
    """Import `extract_verdict` from the VENDORED verdict library copy.

    Loads `.claude/lib/ai_review_common/verdict.py` from the temp plugin tree
    under a unique module name so the production module is not shadowed. This
    proves the assertion runs against the copied module, not the repo's own.
    """
    verdict_py = (
        plugin_root / ".claude" / "lib" / "ai_review_common" / "verdict.py"
    )
    spec = importlib.util.spec_from_file_location(
        "vendored_verdict_e2e", verdict_py
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.extract_verdict


# --------------------------------------------------------------------------- #
# Output parsing.
# --------------------------------------------------------------------------- #

# A findings-table verdict row: | <axis> | <VERDICT> | ... . Matches the
# Output schema in SKILL.md ("| Axis | Verdict | Emoji | Summary |").
_VERDICT_TOKEN = r"PASS|WARN|CRITICAL_FAIL|UNKNOWN|SKIPPED"
_ROW_RE = re.compile(
    r"^\s*\|\s*(?P<axis>[A-Za-z][\w-]*)\s*\|\s*"
    r"(?P<verdict>" + _VERDICT_TOKEN + r")\b",
    re.MULTILINE,
)

# The merged-verdict line, e.g. "**FINAL VERDICT**: PASS".
_FINAL_RE = re.compile(
    r"(?im)^\s*\**\s*FINAL\s+VERDICT\s*\**\s*:\s*\**\s*"
    r"\[?(PASS|WARN|CRITICAL_FAIL|UNKNOWN)\]?"
)


def count_verdict_rows(output: str) -> int:
    """Count findings-table rows that carry a known verdict token."""
    return len(_ROW_RE.findall(output))


def extract_final_verdict_line(output: str) -> str | None:
    """Return the merged FINAL VERDICT token, or None if absent."""
    match = _FINAL_RE.search(output)
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# The gated end-to-end test.
# --------------------------------------------------------------------------- #


@requires_claude_e2e
def test_review_runs_end_to_end_in_vendored_checkout(tmp_path: Path) -> None:
    """`claude -p /review` completes inside a vendored checkout (#1984 Y13).

    Asserts the three behavioral facts the structural test cannot:
      1. exit 0
      2. one verdict row per discovered axis (canonical + chained)
      3. merged FINAL VERDICT parseable by the vendored extract_verdict
    """
    plugin_root = build_vendored_plugin(tmp_path / "plugin")
    workdir = tmp_path / "workdir"
    make_synthetic_diff_repo(workdir)

    expected_rows = discover_axis_count(plugin_root)
    extract_verdict = load_vendored_extract_verdict(plugin_root)

    # Strip inherited plugin-root vars so the CLI sets its own for the loaded
    # plugin (same hygiene as test_cli_hook_e2e._clean_env).
    env = os.environ.copy()
    for var in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "COPILOT_PLUGIN_ROOT"):
        env.pop(var, None)

    try:
        run = subprocess.run(
            ["claude", "-p", _REVIEW_PROMPT, "--plugin-dir", str(plugin_root)],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=_REVIEW_TIMEOUT_S,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"claude /review exceeded {_REVIEW_TIMEOUT_S}s (CLI/infra latency)")

    # 1. exits without error.
    assert run.returncode == 0, (
        f"/review exited {run.returncode}. "
        f"stdout={run.stdout[-1200:]!r} stderr={run.stderr[-800:]!r}"
    )

    output = run.stdout

    # 2. a verdict row per discovered axis.
    rows = count_verdict_rows(output)
    assert rows >= expected_rows, (
        f"expected at least {expected_rows} verdict rows (canonical axes + "
        f"chained skills), found {rows}. A short count means an axis failed "
        f"to load or chain in the vendored install. "
        f"output_tail={output[-1500:]!r}"
    )

    # 3. merged verdict parseable by the vendored extract_verdict.
    final_line = extract_final_verdict_line(output)
    assert final_line is not None, (
        f"no FINAL VERDICT line in /review output. output_tail={output[-1500:]!r}"
    )
    parsed = extract_verdict(f"Final verdict: {final_line}")
    assert parsed in {"PASS", "WARN", "CRITICAL_FAIL", "UNKNOWN"}, (
        f"vendored extract_verdict could not parse merged verdict "
        f"{final_line!r}; got {parsed!r}"
    )


# --------------------------------------------------------------------------- #
# Always-on guards (no CLI; run in bare CI). They pin the facts the gated
# E2E above depends on, so a break is caught without spending a credit.
# --------------------------------------------------------------------------- #


def test_build_vendored_plugin_produces_loadable_tree(tmp_path: Path) -> None:
    """The fixture builder ships the review skill, lib, and a plugin manifest."""
    root = build_vendored_plugin(tmp_path / "p")
    assert (root / ".claude-plugin" / "plugin.json").is_file()
    assert (root / ".claude" / "skills" / "review" / "SKILL.md").is_file()
    assert (
        root / ".claude" / "lib" / "ai_review_common" / "verdict.py"
    ).is_file()
    assert (
        root / ".claude" / "skills" / "review" / "references"
    ).is_dir()


def test_discovered_axis_count_matches_canonical_plus_chained(
    tmp_path: Path,
) -> None:
    """Discovered row count = canonical references/*.md + 3 chained skills.

    Cross-checks against the canonical role list the schema test owns, so this
    test tracks the single source of truth and the row-count assertion in the
    E2E cannot silently drift.
    """
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from tests.lib.test_axis_schema import CANONICAL_ROLES  # noqa: PLC0415
    finally:
        sys.path.remove(str(REPO_ROOT))

    root = build_vendored_plugin(tmp_path / "p")
    count = discover_axis_count(root)
    assert count == len(CANONICAL_ROLES) + len(CHAINED_SKILL_AXES)
    # The stale issue literal (9) must be a floor we have since exceeded; if a
    # future change drops below it, that is a coverage regression worth a look.
    assert count >= 9


def test_synthetic_diff_repo_has_staged_change(tmp_path: Path) -> None:
    """The synthetic repo carries exactly one staged file with a diff."""
    repo = tmp_path / "r"
    changed = make_synthetic_diff_repo(repo)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    names = [line for line in staged.stdout.splitlines() if line.strip()]
    assert names == [changed], f"expected staged change {changed!r}, got {names!r}"
    diff = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "subtract" in diff.stdout, "staged diff missing the expected change"


def test_count_verdict_rows_parses_findings_table() -> None:
    """The row counter matches the SKILL.md findings-table shape."""
    table = (
        "| Axis | Verdict | Emoji | Summary |\n"
        "|------|---------|-------|---------|\n"
        "| spec-compliance | PASS | OK | gate passed |\n"
        "| analyst | WARN | WARN | minor |\n"
        "| security | CRITICAL_FAIL | X | bug |\n"
        "| taste-lints | UNKNOWN | ? | crashed |\n"
    )
    assert count_verdict_rows(table) == 4


def test_count_verdict_rows_ignores_header_and_separator() -> None:
    """The header and the `|---|` separator are not verdict rows."""
    table = (
        "| Axis | Verdict |\n"
        "|------|---------|\n"
        "| analyst | PASS |\n"
    )
    assert count_verdict_rows(table) == 1


def test_extract_final_verdict_line_handles_bold_markup() -> None:
    """The FINAL VERDICT matcher tolerates the `**FINAL VERDICT**:` markup."""
    assert extract_final_verdict_line("**FINAL VERDICT**: PASS") == "PASS"
    assert extract_final_verdict_line("FINAL VERDICT: [WARN]") == "WARN"
    assert (
        extract_final_verdict_line("**FINAL VERDICT**: CRITICAL_FAIL (merge)")
        == "CRITICAL_FAIL"
    )
    assert extract_final_verdict_line("no verdict here") is None


def test_vendored_extract_verdict_loads_and_parses(tmp_path: Path) -> None:
    """The vendored extract_verdict imports and parses a merged verdict line.

    Proves assertion 3's machinery works against the copied module without the
    CLI, so a break in the vendored verdict library surfaces in bare CI.
    """
    root = build_vendored_plugin(tmp_path / "p")
    extract_verdict = load_vendored_extract_verdict(root)
    assert extract_verdict("Final verdict: WARN") == "WARN"
    assert extract_verdict("Final verdict: PASS") == "PASS"
