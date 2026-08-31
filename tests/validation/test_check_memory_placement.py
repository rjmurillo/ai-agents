"""Unit tests for the memory placement signals and ratchet (issue #5391).

Pins the heuristic behind the gate that flags normative or procedural content
written into `.serena/memories/`. The CLI-level tests live in the sibling
``test_check_memory_placement_cli.py``, which imports the memory fixtures and
the process helpers from here; both files were split at the project's 500-line
ceiling (`.claude/rules/code-quality.md`), matching the split of the
production modules.

Coverage claimed here (issue acceptance criteria 5 and 6):
- positive: a memory with normative section labels plus ordered mandatory
  steps scores at or above the flag threshold;
- negative: an evidence memory does not, including one that says "must" in
  prose and one that quotes a rule inside a fenced code block;
- edge: label normalization, word boundaries, the frontmatter exception, the
  corpus filter, and the baseline range and ceiling guards.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import scripts.validation.check_memory_placement as cmod
import scripts.validation.memory_placement_baseline as bmod
import scripts.validation.memory_placement_signals as sig

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_memory_placement.py"


# ---------------------------------------------------------------------------
# Memory fixtures
# ---------------------------------------------------------------------------

NORMATIVE_MEMORY = """# Release Protocol

## Rules

The release owner MUST hold the push lock before tagging.

## Procedure

1. MUST verify the branch is even with origin/main.
2. Never tag from a dirty worktree.
3. Run the smoke suite and confirm it exits 0.
4. MUST record the tag in the release log.

## Checklist

Every release REQUIRED to carry a rollback note.
"""

EVIDENCE_MEMORY = """# Aggregate job stayed green while a leg failed

**Statement**: An aggregate job without `if: always()` reports success when a
needed job is skipped.

**Evidence**: PR #4067 merged with a red unit-test leg. The aggregate job read
`needs.tests.result == 'success'`, and a skipped leg reports `skipped`, so the
condition never ran and the job exited 0.

**Context**: We must have missed this because the summary line rendered green,
which is what a reviewer scans first. The fix must land in the workflow, not in
the reporting script.

**Impact**: 8/10. One merge with a failing leg, caught two days later.
"""

QUOTING_MEMORY = """# Why the hook policy rejects a bare python3 call

**Evidence**: The rule text below is quoted from
`.claude/rules/ci-scripts.md` MUST-18. It is reproduced so the reason survives
without a second lookup, and it must not be paraphrased.

```markdown
A step that invokes a script with bare `python3` MUST import only the standard
library. It MUST NEVER import a third-party module, and the runner ALWAYS
resolves the ambient interpreter. This is REQUIRED because a job whose only
preceding step is checkout has installed nothing. Steps MUST be converted.
1. MUST run the script with bare python3 yourself.
2. MUST change the step to uv run in the same commit.
3. Never add the import without doing one of the two.
```

**Impact**: One red required check on every PR until the import was removed.
"""

ROLE_MEMORY = """# Reviewer contract

## Role

You are a fresh-context reviewer.

## Responsibilities

1. MUST read the diff before the description.
2. Never approve a PR whose tests you did not see run.
3. MUST record every finding with a file and line.

## Handoff

Return findings to the implementer.
"""

MAXIMAL_MEMORY = (
    NORMATIVE_MEMORY
    + """
## Responsibilities

You are the release owner.
"""
)


# ---------------------------------------------------------------------------
# Process helpers, shared with the CLI test module
# ---------------------------------------------------------------------------


def scaffold(tmp_path: Path) -> Path:
    """Create the minimal repo shape: a memories directory."""
    repo = tmp_path / "repo"
    (repo / ".serena" / "memories").mkdir(parents=True)
    return repo


def write_memory(repo: Path, name: str, content: str) -> str:
    """Write a memory file and return its repo-relative path."""
    rel = f".serena/memories/{name}"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return rel


def write_baseline(repo: Path, entries: dict[str, object]) -> str:
    """Write a baseline JSON in the checked location and return its path."""
    rel = "scripts/validation/memory_placement_baseline.json"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_comment": "test", "files": entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    return rel


def run_cli(
    repo: Path,
    changed: list[str],
    *,
    pr_body: str = "",
    extra: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the checker as a process, the way CI does."""
    args = [
        sys.executable,
        str(SCRIPT),
        "--repo-root",
        str(repo),
        "--pr-body",
        pr_body,
        *(extra or []),
        "--changed-files",
        *changed,
    ]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
    )


# ---------------------------------------------------------------------------
# Scoring: positives and negatives
# ---------------------------------------------------------------------------


def test_normative_memory_is_candidate() -> None:
    score = sig.score_content("m.md", NORMATIVE_MEMORY)
    assert score.is_candidate is True
    assert score.score >= sig.FLAG_THRESHOLD
    assert score.normative_sections is True
    assert score.ordered_mandate is True


def test_evidence_memory_is_not_candidate() -> None:
    """An incident narrative using "must" in prose stays below the bar."""
    score = sig.score_content("m.md", EVIDENCE_MEMORY)
    assert score.is_candidate is False
    assert score.modal_hits == 0
    assert score.ordered_hits == 0


def test_fenced_rule_quote_is_not_scored() -> None:
    """Modals and ordered mandates inside a code fence are blanked first.

    The fence holds eight uppercase modals and three numbered mandates. The
    only hit left is the ``MUST-18`` citation in the prose above it, which is
    three short of ``MIN_MODAL_HITS`` on its own.
    """
    score = sig.score_content("m.md", QUOTING_MEMORY)
    assert score.is_candidate is False
    assert score.modal_hits == 1
    assert score.ordered_hits == 0


def test_role_contract_memory_is_candidate() -> None:
    """A role contract plus one corroborating signal reaches the threshold."""
    score = sig.score_content("m.md", ROLE_MEMORY)
    assert score.role_contract is True
    assert score.ordered_mandate is True
    assert score.score == sig.ROLE_WEIGHT + 1
    assert score.is_candidate is True


def test_role_contract_alone_is_not_a_candidate() -> None:
    """The doubled weight still leaves a bare persona line below the bar."""
    score = sig.score_content("m.md", "# Notes\n\nYou are a reviewer here.\n")
    assert score.role_contract is True
    assert score.score == sig.ROLE_WEIGHT
    assert score.is_candidate is False


def test_score_and_candidacy_are_derived_from_signals() -> None:
    """Score sums the four signals, role doubled; candidacy is the threshold."""
    below = sig.MemoryScore(
        path="m.md",
        normative_sections=True,
        ordered_mandate=True,
        modal_density=False,
        role_contract=False,
        section_hits=2,
        ordered_hits=3,
        modal_hits=0,
        exception=None,
    )
    assert below.score == 2
    assert below.is_candidate is False

    at_threshold = sig.MemoryScore(
        path="m.md",
        normative_sections=True,
        ordered_mandate=True,
        modal_density=True,
        role_contract=False,
        section_hits=2,
        ordered_hits=3,
        modal_hits=4,
        exception=None,
    )
    assert at_threshold.score == sig.FLAG_THRESHOLD
    assert at_threshold.is_candidate is True

    everything = sig.MemoryScore(
        path="m.md",
        normative_sections=True,
        ordered_mandate=True,
        modal_density=True,
        role_contract=True,
        section_hits=2,
        ordered_hits=3,
        modal_hits=4,
        exception=None,
    )
    assert everything.score == sig.MAX_SCORE


# ---------------------------------------------------------------------------
# Scoring: individual signals
# ---------------------------------------------------------------------------


def test_long_narrative_heading_is_not_a_normative_section() -> None:
    labels = sig._labels("## Why the workflow failed on the release branch\n")
    assert sig.count_normative_sections(labels) == 0


def test_short_label_and_bold_label_count_as_normative_sections() -> None:
    labels = sig._labels("## The Rules\n\n**Constraints**: none\n")
    assert sig.count_normative_sections(labels) == 2


def test_label_normalization_strips_emphasis_numbering_and_links() -> None:
    assert sig._normalize_label("2. **Entry Criteria**:") == "entry criteria"
    assert sig._normalize_label("`Checklist`") == "checklist"
    assert sig._normalize_label("[Rules](rules.md)") == "rules"


def test_ordered_mandates_need_the_ordered_shape() -> None:
    ordered = "1. MUST hold the lock.\n2. Never force push.\n3. Run the suite.\n"
    assert sig.count_ordered_mandates(ordered) == 3
    bullets = "- MUST hold the lock.\n- Never force push.\n- Run the suite.\n"
    assert sig.count_ordered_mandates(bullets) == 0
    narrative = "1. The job ran.\n2. It went green.\n"
    assert sig.count_ordered_mandates(narrative) == 0


def test_modal_count_is_case_sensitive_and_word_bounded() -> None:
    assert sig.count_modals("MUST NOT ship. NEVER retry. ALWAYS log.") == 3
    assert sig.count_modals("the branch must have been stale") == 0
    assert sig.count_modals("MUSTARD and NEVERMORE") == 0


def test_role_contract_detects_persona_and_sections() -> None:
    assert sig.has_role_contract("You are a reviewer.\n", []) is True
    assert sig.has_role_contract("Your role is to review.\n", []) is True
    assert sig.has_role_contract("", ["responsibilities"]) is True
    assert sig.has_role_contract("The agent read the diff.\n", ["evidence"]) is False


# ---------------------------------------------------------------------------
# Frontmatter exception
# ---------------------------------------------------------------------------


def test_placement_exception_returns_rationale() -> None:
    content = "---\nplacement_exception: kept as the canonical incident log\n---\n# m\n"
    assert sig.placement_exception(content) == "kept as the canonical incident log"


def test_placement_exception_rejects_false_and_empty() -> None:
    assert sig.placement_exception("---\nplacement_exception: false\n---\n# m\n") is None
    assert sig.placement_exception("---\nplacement_exception: ''\n---\n# m\n") is None


def test_placement_exception_absent_or_unparsable() -> None:
    assert sig.placement_exception("# no frontmatter\n") is None
    assert sig.placement_exception("---\nname: m\n---\n# m\n") is None
    assert sig.placement_exception("---\n- a list\n---\n# m\n") is None


# ---------------------------------------------------------------------------
# Corpus inventory
# ---------------------------------------------------------------------------


def test_memory_paths_selected_and_metadata_excluded() -> None:
    assert bmod.is_memory_path(".serena/memories/ci/observations.md") is True
    assert bmod.is_memory_path(".serena/memories/README.md") is False
    assert bmod.is_memory_path(".serena/memories/CLAUDE.md") is False
    assert bmod.is_memory_path(".serena/memories/notes.txt") is False
    assert bmod.is_memory_path(".claude/rules/testing.md") is False


def test_filter_memory_paths_normalizes_and_deduplicates() -> None:
    assert bmod.filter_memory_paths(
        [
            ".serena\\memories\\ci\\a.md",
            ".serena/memories/ci/a.md",
            "  ",
            "README.md",
        ]
    ) == [".serena/memories/ci/a.md"]


def test_resolve_repo_path_refuses_escape(tmp_path: Path) -> None:
    try:
        bmod.resolve_repo_path(tmp_path, "../outside.md")
    except ValueError as exc:
        assert "escapes repo root" in str(exc)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected ValueError")


def test_full_corpus_returns_none_when_git_cannot_answer(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(bmod, "tracked_paths_at_head", lambda _root: None)
    assert bmod.full_corpus_memory_paths(tmp_path) is None


def test_full_corpus_filters_tracked_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        bmod,
        "tracked_paths_at_head",
        lambda _root: [
            ".serena/memories/b.md",
            ".serena/memories/a.md",
            ".serena/memories/README.md",
            "AGENTS.md",
        ],
    )
    assert bmod.full_corpus_memory_paths(tmp_path) == [
        ".serena/memories/a.md",
        ".serena/memories/b.md",
    ]


def test_empty_or_unknown_corpus_is_refused(tmp_path: Path) -> None:
    assert bmod.refuse_incomplete_corpus([], tmp_path) == 2
    assert bmod.refuse_incomplete_corpus(None, tmp_path) == 2
    assert bmod.refuse_incomplete_corpus(["a.md"], tmp_path) is None


# ---------------------------------------------------------------------------
# Baseline guards
# ---------------------------------------------------------------------------


def test_baseline_scores_outside_range_are_rejected() -> None:
    bmod.validate_baseline_scores({"a.md": 0, "b.md": sig.MAX_SCORE})
    for bad in (-1, sig.MAX_SCORE + 1):
        try:
            bmod.validate_baseline_scores({"a.md": bad})
        except ValueError as exc:
            assert "outside the valid range" in str(exc)
        else:  # pragma: no cover - the call must raise
            raise AssertionError(f"expected ValueError for {bad}")


def test_ceiling_raise_and_grandfathering_are_refused() -> None:
    threshold = sig.FLAG_THRESHOLD
    assert bmod.refuse_ceiling_raise({"a.md": 4}, {"a.md": 3}, threshold) == 2
    assert bmod.refuse_ceiling_raise({"b.md": 3}, {"a.md": 3}, threshold) == 2
    assert bmod.refuse_ceiling_raise({"a.md": 3}, {"a.md": 3}, threshold) is None
    assert bmod.refuse_ceiling_raise({}, {"a.md": 3}, threshold) is None


def test_baseline_note_labels_new_recorded_and_regressed() -> None:
    assert bmod.baseline_note("a.md", 3, None) == ""
    assert bmod.baseline_note("a.md", 3, {}) == " baseline=new"
    assert bmod.baseline_note("a.md", 3, {"a.md": 3}) == " baseline=3"
    assert bmod.baseline_note("a.md", 4, {"a.md": 3}) == " baseline=3 (regression)"


def test_update_baseline_from_outside_repo_root_is_refused(
    monkeypatch, tmp_path: Path
) -> None:
    repo = scaffold(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    code = bmod.update_baseline(
        repo / "scripts" / "validation" / "b.json",
        {},
        repo_root=repo.resolve(),
        allow_shrink=False,
        flag_threshold=sig.FLAG_THRESHOLD,
    )
    assert code == 2


# ---------------------------------------------------------------------------
# Gate resolution
# ---------------------------------------------------------------------------


def test_changed_files_argument_beats_environment() -> None:
    assert cmod._split_changed_arg([], "a.md") == []
    assert cmod._split_changed_arg(None, "a.md\nb.md") == ["a.md", "b.md"]
    assert cmod._split_changed_arg(None, None) == []


def test_exception_and_baseline_suppress_the_gate() -> None:
    """fails_gate branches: exception, plain threshold, recorded, unrecorded."""
    flagged = sig.score_content("a.md", NORMATIVE_MEMORY)
    excused = replace(flagged, path="b.md", exception="deliberate")

    result = cmod.CheckResult(scores=[flagged, excused])
    assert result.fails_gate(flagged) is True
    assert result.fails_gate(excused) is False
    assert result.failing == [flagged]

    result.baseline = {flagged.path: flagged.score}
    assert result.fails_gate(flagged) is False

    result.baseline = {}
    assert result.fails_gate(flagged) is True

    result.override_rationale = "tracked in #5392"
    assert result.failing == []
