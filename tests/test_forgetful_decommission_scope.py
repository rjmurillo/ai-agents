"""Guard for acceptance criterion 1 of issue #5574, rescoped by the repository owner.

AC1 asked that `git grep -il forgetful` over the live scope return nothing.
That cannot hold while the decommission guards exist: an absence assertion has
to contain the substring it tests for. The 2026-09-07 comment on #5574 proposed
a rescope, and the owner accepted it. The token may remain only in decommission
guard tests, ADRs and other architecture records, and history (git history,
changelog, retrospectives, session logs, and recorded eval data). Every other
tracked file is a live reference and must not name the retired backend.

This module scans every tracked file, not a fixed list of directories, so a
new mention in a new location fails. Exemptions come in two forms:

- HISTORY_PREFIXES: whole record trees, allowed by path prefix.
- EXEMPTIONS: single files, each with a class, a reason, and the count of
  matching lines it allows.

A new mention anywhere else, including one more line inside a pinned file,
fails `test_no_unexempted_file_names_the_retired_backend`. A pinned file that
names the token less often than pinned fails `test_every_exemption_is_still_needed`,
so the list cannot rot into a blanket allowance. A history prefix that matches
no tracked file fails `test_every_history_prefix_is_still_needed`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

TOKEN = "forgetful"

# Scan every tracked file. A fixed directory list let new locations escape.
SCAN_SCOPE = (".",)

# Record trees: what happened, kept as written. Path prefixes, matched on the
# repo-relative POSIX path.
HISTORY_PREFIXES = (
    "CHANGELOG.md",
    ".agents/archive/",
    ".claude-mem/memories/",
    ".serena/memories/",
    ".project-toolkit/architecture/",
    ".project-toolkit/sessions/",
    ".project-toolkit/analysis/",
    ".project-toolkit/critique/",
    ".project-toolkit/qa/",
    ".project-toolkit/specs/design/",
    ".project-toolkit/specs/interviews/",
    ".project-toolkit/specs/requirements/REQ-",
    ".project-toolkit/specs/tasks/",
    ".project-toolkit/security/",
    ".project-toolkit/memory/episodes/",
    ".project-toolkit/retrospective/",
    ".project-toolkit/audit/",
    ".project-toolkit/audits/",
    ".project-toolkit/planning/",
    ".project-toolkit/roadmap/",
)

NEEDLE = "assertion needle"
REGISTRY = "retired-name registry"
RECORD = "captured run record"

EXEMPTION_CLASSES = frozenset({NEEDLE, REGISTRY, RECORD})

_KNOWN_RETIRED = "KNOWN_RETIRED_KEBAB_SKILLS keeps the name so stale references surface"
_FROZEN_RUN = "rewriting it would claim a run scored something it did not"

# Path to (class, matching-line count pinned from `git grep -ic`, reason).
EXEMPTIONS: dict[str, tuple[str, int, str]] = {
    ".claude/skills/orphan-ref-validator/scripts/filters.py": (REGISTRY, 1, _KNOWN_RETIRED),
    "src/claude/skills/orphan-ref-validator/scripts/filters.py": (REGISTRY, 1, _KNOWN_RETIRED),
    "src/copilot-cli/skills/orphan-ref-validator/scripts/filters.py": (REGISTRY, 1, _KNOWN_RETIRED),
    "scripts/validation/check_adr_links_baseline.txt": (
        REGISTRY, 2, "rows key on a historical PRD file name"
    ),
    "evals/memory-spike/runs/20260528T061135Z-94708c8e/runs.jsonl": (RECORD, 3, _FROZEN_RUN),
    "evals/reports/adr-063-kill-gate-20260708/memory-search.json": (RECORD, 4, _FROZEN_RUN),
    "evals/reports/skill-triage-20260509-135851/results.json": (RECORD, 1, _FROZEN_RUN),
    "evals/reports/skill-triage-20260509-135851/run.log": (RECORD, 9, _FROZEN_RUN),
    "tests/.test_durations": (RECORD, 92, "pytest-split timing map keyed by recorded node IDs"),
    "tests/commands/test_research_command_contract.py": (NEEDLE, 19, "names no retired tool"),
    "tests/commands/test_spec_step0_5.py": (NEEDLE, 3, "Step 0.5 names no retired backend"),
    "tests/skills/context-gather/test_context_gather.py": (NEEDLE, 20, "names no retired tier"),
    "tests/skills/context-gather/test_fold_context_retrieval.py": (
        NEEDLE, 6, "reference names no retired tool"
    ),
    "tests/skills/curating-memories/test_skill_contract.py": (NEEDLE, 21, "no retired tool call"),
    "tests/skills/memory-consolidate/test_skill_structure.py": (
        NEEDLE, 2, "names no retired backend"
    ),
    "tests/skills/test_forgetful_decommission_guards.py": (
        NEEDLE, 28, "REMOVED_SPELLINGS are the check"
    ),
    "tests/test_forgetful_decommission_scope.py": (NEEDLE, 7, "this guard's own needle"),
    "tests/test_skill_registry.py": (NEEDLE, 3, "keyword left the memory category"),
    "tests/test_validation_skill_frontmatter.py": (NEEDLE, 8, "retired tool grant is rejected"),
    ".project-toolkit/specs/PRD-memory-enhancement-layer-for-serena-forgetful.md": (
        RECORD, 11, "spec of the retired feature, kept as written and marked superseded"
    ),
    ".project-toolkit/specs/STATUS.md": (
        REGISTRY, 2, "index rows key on the retired PRD file name and mark it superseded"
    ),
    "scripts/consolidate_skills.py": (REGISTRY, 2, "archived actions stay memory work"),
    "tests/test_consolidate_skills.py": (NEEDLE, 1, "archived action stays memory"),
}


def mention_counts(repo: Path, scope: tuple[str, ...] = SCAN_SCOPE) -> dict[str, int]:
    """Map tracked files in *scope* to their count of lines naming TOKEN, any case.

    `git grep` exit 1 means no match, a valid empty result; any other is a failure.
    """
    git = shutil.which("git")
    if git is None:
        pytest.fail("git is required to evaluate #5574 AC1")
    result = subprocess.run(
        [git, "grep", "-ic", TOKEN, "--", *scope],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"git grep failed with exit {result.returncode}: {result.stderr.strip()}")
    pairs = (line.rsplit(":", 1) for line in result.stdout.splitlines())
    return {path: int(count) for path, count in pairs}


Audit = tuple[list[str], list[str]]


def is_history(path: str, prefixes: tuple[str, ...] = HISTORY_PREFIXES) -> bool:
    """Return True when *path* sits in a record tree allowed to name the token."""
    return any(_matches(path, prefix) for prefix in prefixes)


def _matches(path: str, prefix: str) -> bool:
    """A prefix ending in `.md` names one file; any other prefix matches by start."""
    if prefix.endswith(".md"):
        return path == prefix
    return path.startswith(prefix)


def audit(
    counts: dict[str, int],
    exemptions: dict[str, tuple[str, int, str]],
    prefixes: tuple[str, ...] = HISTORY_PREFIXES,
) -> Audit:
    """Return (files over their pinned count, exemptions now under their pin)."""
    pinned = {path: entry[1] for path, entry in exemptions.items()}
    over = [
        p for p, n in sorted(counts.items())
        if n > pinned.get(p, 0) and not is_history(p, prefixes)
    ]
    under = [p for p, n in sorted(pinned.items()) if counts.get(p, 0) < n]
    return over, under


@pytest.fixture(scope="module")
def ac1_audit() -> Audit:
    return audit(mention_counts(REPO_ROOT), EXEMPTIONS)


def test_no_unexempted_file_names_the_retired_backend(ac1_audit: Audit) -> None:
    offenders, _ = ac1_audit
    assert not offenders, (
        f"{offenders} name the retired memory backend beyond their pinned count. Rewrite "
        "the live text to "
        "point at Serena (ADR-106). Add an exemption only for an assertion needle, "
        "a retired-name registry, or a captured run record."
    )


def test_every_exemption_is_still_needed(ac1_audit: Audit) -> None:
    _, stale = ac1_audit
    assert not stale, f"{stale} name the token less than pinned; lower or delete the pin."


@pytest.mark.parametrize("path", sorted(EXEMPTIONS))
def test_every_exemption_names_a_known_class_and_a_reason(path: str) -> None:
    exemption_class, _, reason = EXEMPTIONS[path]
    assert exemption_class in EXEMPTION_CLASSES, path
    assert reason.strip(), path


def test_audit_flags_an_unexempted_mention_and_a_stale_exemption(tmp_path: Path) -> None:
    """Negative control: without it, a scan that stopped matching would pass."""
    git = shutil.which("git")
    assert git is not None
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "live.py").write_text("# query Forgetful first\n", encoding="utf-8")
    (tmp_path / "scripts" / "clean.py").write_text("# query Serena first\n", encoding="utf-8")
    (tmp_path / "history.md").write_text("Forgetful was retired.\n", encoding="utf-8")
    subprocess.run([git, "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([git, "add", "."], cwd=tmp_path, check=True)

    hits = mention_counts(tmp_path, ("scripts",))

    assert hits == {"scripts/live.py": 1}
    assert audit(hits, {}) == (["scripts/live.py"], [])
    assert audit(hits, {"scripts/live.py": (NEEDLE, 1, "x")}) == ([], [])
    one_allowed = {"scripts/live.py": (NEEDLE, 1, "x")}
    assert audit({"scripts/live.py": 2}, one_allowed) == (["scripts/live.py"], [])
    assert audit(hits, {"gone.py": (RECORD, 1, "x")}) == (["scripts/live.py"], ["gone.py"])


def test_history_prefix_exempts_records_but_not_live_files() -> None:
    """Negative control: a prefix must not swallow a live sibling path."""
    assert is_history(".project-toolkit/sessions/2026-01-09-session-386.json")
    assert is_history(".serena/memories/memory-index.md")
    assert not is_history(".agents/governance/MEMORY-MANAGEMENT.md")
    assert not is_history(".project-toolkit/testing/prompt-eval-methodology.md")
    assert not is_history("README.md")
    assert not is_history(".project-toolkit/specs/STATUS.md")
    assert not is_history(".project-toolkit/specs/PRD-new-memory-flow.md")
    assert not is_history("CHANGELOG.md.bak")
    assert not is_history(".project-toolkit/specs/requirements/EARS-TEMPLATE.md")
    assert audit({"README.md": 1}, {}) == (["README.md"], [])
    assert audit({".agents/archive/x.md": 4}, {}) == ([], [])


def test_every_history_prefix_is_still_needed() -> None:
    """A prefix with no tracked match is dead allowance; delete it."""
    counts = mention_counts(REPO_ROOT)
    unused = [
        prefix for prefix in HISTORY_PREFIXES
        if prefix != "CHANGELOG.md" and not any(is_history(p, (prefix,)) for p in counts)
    ]
    assert not unused, f"{unused} match no tracked file naming the token; remove them."
