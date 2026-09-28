"""Guard for acceptance criterion 1 of issue #5574, rescoped.

AC1 asked that `git grep -il forgetful` over the live scope return nothing.
That cannot hold while the decommission guards exist: an absence assertion has
to contain the substring it tests for. The 2026-09-07 comment on #5574 proposed
the rescope this module enforces. No live file names the retired backend. A
file is exempt only when the token is an assertion needle, a retired-name
registry entry, or a captured record of a past run.

Every exemption names its class and its reason. A new mention anywhere in the
scope fails `test_no_unexempted_file_names_the_retired_backend`. An exemption
whose file no longer names the token fails `test_every_exemption_is_still_needed`,
so the list cannot rot into a blanket allowance.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

TOKEN = "forgetful"

# The pathspecs in #5574 AC1, including `.project-toolkit/prompts` (widened per #5643).
AC1_SCOPE = (
    "src",
    ".claude",
    "scripts",
    "tests",
    "evals",
    "templates",
    "docs",
    ".github",
    ".mcp.json",
    "lefthook.yml",
    ".project-toolkit/prompts",
)

NEEDLE = "assertion needle"
REGISTRY = "retired-name registry"
RECORD = "captured run record"

EXEMPTION_CLASSES = frozenset({NEEDLE, REGISTRY, RECORD})

_KNOWN_RETIRED = "KNOWN_RETIRED_KEBAB_SKILLS keeps the name so stale references surface"
_FROZEN_RUN = "rewriting it would claim a run scored something it did not"

EXEMPTIONS: dict[str, tuple[str, str]] = {
    ".claude/skills/orphan-ref-validator/scripts/filters.py": (REGISTRY, _KNOWN_RETIRED),
    "src/claude/skills/orphan-ref-validator/scripts/filters.py": (REGISTRY, _KNOWN_RETIRED),
    "src/copilot-cli/skills/orphan-ref-validator/scripts/filters.py": (REGISTRY, _KNOWN_RETIRED),
    "scripts/validation/check_adr_links_baseline.txt": (
        REGISTRY,
        "baseline rows key on a historical PRD file name that contains the token",
    ),
    "evals/memory-spike/fixtures/E002.json": (
        RECORD,
        "input to the scored 20260528T061135Z run, which records its fixture_sha",
    ),
    "evals/memory-spike/runs/20260528T061135Z-94708c8e/runs.jsonl": (RECORD, _FROZEN_RUN),
    "evals/reports/adr-063-kill-gate-20260708/memory-search.json": (RECORD, _FROZEN_RUN),
    "evals/reports/skill-triage-20260509-135851/results.json": (RECORD, _FROZEN_RUN),
    "evals/reports/skill-triage-20260509-135851/run.log": (RECORD, _FROZEN_RUN),
    "tests/commands/test_research_command_contract.py": (
        NEEDLE,
        "research skill names no retired tool",
    ),
    "tests/commands/test_spec_step0_5.py": (NEEDLE, "Step 0.5 body names no retired backend"),
    "tests/skills/context-gather/test_context_gather.py": (
        NEEDLE,
        "context-gather names no retired tier",
    ),
    "tests/skills/context-gather/test_fold_context_retrieval.py": (
        NEEDLE,
        "folded reference names no retired tool",
    ),
    "tests/skills/curating-memories/test_skill_contract.py": (
        NEEDLE,
        "skill makes no retired tool call",
    ),
    "tests/skills/memory-consolidate/test_skill_structure.py": (
        NEEDLE,
        "skill names no retired backend",
    ),
    "tests/skills/test_forgetful_decommission_guards.py": (
        NEEDLE,
        "REMOVED_SPELLINGS are the check",
    ),
    "tests/test_forgetful_decommission_scope.py": (
        NEEDLE,
        "this guard's own token and exemption keys",
    ),
    "tests/test_skill_registry.py": (
        NEEDLE,
        "keyword no longer maps a skill to the memory category",
    ),
    "tests/test_validation_skill_frontmatter.py": (NEEDLE, "retired tool grant is rejected"),
}


def files_naming_token(repo: Path, scope: tuple[str, ...] = AC1_SCOPE) -> set[str]:
    """Return tracked files in *scope* that name TOKEN, case-insensitively.

    Mirrors the AC1 command exactly. `git grep` exits 1 when nothing matches,
    which is a valid empty result; any other nonzero exit is a real failure.
    """
    git = shutil.which("git")
    if git is None:
        pytest.fail("git is required to evaluate #5574 AC1")
    result = subprocess.run(
        [git, "grep", "-il", TOKEN, "--", *scope],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"git grep failed with exit {result.returncode}: {result.stderr.strip()}")
    return set(result.stdout.splitlines())


def unexempted(found: set[str], exemptions: dict[str, tuple[str, str]]) -> list[str]:
    """Files that name the token without an exemption."""
    return sorted(found - exemptions.keys())


def stale_exemptions(found: set[str], exemptions: dict[str, tuple[str, str]]) -> list[str]:
    """Exempted files that no longer name the token."""
    return sorted(exemptions.keys() - found)


@pytest.fixture(scope="module")
def found() -> set[str]:
    return files_naming_token(REPO_ROOT)


def test_no_unexempted_file_names_the_retired_backend(found: set[str]) -> None:
    offenders = unexempted(found, EXEMPTIONS)
    assert not offenders, (
        f"{offenders} name the retired memory backend. Rewrite the live text to "
        "point at Serena (ADR-106). Add an exemption only for an assertion needle, "
        "a retired-name registry, or a captured run record."
    )


def test_every_exemption_is_still_needed(found: set[str]) -> None:
    stale = stale_exemptions(found, EXEMPTIONS)
    assert not stale, f"{stale} no longer name the token; delete their exemptions."


@pytest.mark.parametrize("path", sorted(EXEMPTIONS))
def test_every_exemption_names_a_known_class_and_a_reason(path: str) -> None:
    exemption_class, reason = EXEMPTIONS[path]
    assert exemption_class in EXEMPTION_CLASSES, path
    assert reason.strip(), path


def test_scan_detects_a_mention_in_scope_and_ignores_one_outside(tmp_path: Path) -> None:
    """Negative control: without it, a scan that stopped matching would pass."""
    git = shutil.which("git")
    assert git is not None
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "live.py").write_text("# query Forgetful first\n", encoding="utf-8")
    (tmp_path / "scripts" / "clean.py").write_text("# query Serena first\n", encoding="utf-8")
    (tmp_path / "history.md").write_text("Forgetful was retired.\n", encoding="utf-8")
    subprocess.run([git, "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([git, "add", "."], cwd=tmp_path, check=True)

    hits = files_naming_token(tmp_path, ("scripts",))

    assert hits == {"scripts/live.py"}
    assert unexempted(hits, {}) == ["scripts/live.py"]
    assert unexempted(hits, {"scripts/live.py": (NEEDLE, "fixture")}) == []


def test_stale_detection_reports_an_exemption_with_no_mention() -> None:
    exemptions = {"a.py": (NEEDLE, "fixture"), "b.py": (RECORD, "fixture")}
    assert stale_exemptions({"a.py"}, exemptions) == ["b.py"]
