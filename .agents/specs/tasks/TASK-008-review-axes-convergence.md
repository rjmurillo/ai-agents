---
type: task
id: TASK-008
title: review-axes-convergence
status: draft
priority: high
complexity: Tier-2
related:
  - DESIGN-008
  - REQ-008
blocked_by: []
blocks: []
assignee: ~
date: 2026-05-09
---

# TASK-008: review-axes-convergence

All tasks reference DESIGN-008 for interface contracts and REQ-008 for acceptance criteria. Tasks are ordered by dependency. Each task is atomic (5 files or fewer changed per commit, per AGENTS.md).

---

## TASK-008-01: Create Canonical Axis Files

**Complexity:** S (2-4 h)

**Objective:** Seed `.claude/review-axes/` with 6 canonical axis files by migrating content verbatim from existing CI prompt files. This establishes the SoR (REQ-008-01).

**In scope:**
- Create directory `.claude/review-axes/`.
- Create 6 files: `analyst.md`, `architect.md`, `devops.md`, `qa.md`, `roadmap.md`, `security.md`.
- Seed each from the corresponding `.github/prompts/pr-quality-gate-{role}.md`.
- Add required YAML frontmatter (`name`, `role`, `version: "1.0"`, `description`).
- Ensure body sections `Grounding Rules`, `Analysis Focus Areas`, `Output Schema` are present.
- Ensure `Output Schema` documents verdict tokens: `PASS`, `WARN`, `CRITICAL_FAIL`, `UNKNOWN`.

**Out of scope:** Generator, drift check, `/review` rewrite. Those are later tasks.

**Acceptance Criteria:**
- [ ] `.claude/review-axes/` directory exists and contains exactly 6 `.md` files.
- [ ] Each file passes filename regex `^[a-z][a-z0-9_-]*\.md$`.
- [ ] Each file has frontmatter with keys `name`, `role`, `version`, `description`.
- [ ] Each file has body sections `Grounding Rules`, `Analysis Focus Areas`, `Output Schema`.
- [ ] `Output Schema` in each file explicitly lists verdict tokens.
- [ ] Content is functionally equivalent to source `.github/prompts/pr-quality-gate-{role}.md` (not a summary).

**Files affected:**

| File | Action | Description |
|------|--------|-------------|
| `.claude/review-axes/analyst.md` | Create | Seeded from `.github/prompts/pr-quality-gate-analyst.md` + frontmatter |
| `.claude/review-axes/architect.md` | Create | Seeded from corresponding CI prompt |
| `.claude/review-axes/devops.md` | Create | Seeded from corresponding CI prompt |
| `.claude/review-axes/qa.md` | Create | Seeded from corresponding CI prompt |
| `.claude/review-axes/roadmap.md` | Create | Seeded from corresponding CI prompt |
| `.claude/review-axes/security.md` | Create | Seeded from corresponding CI prompt |

**Implementation notes:**
- Read each `.github/prompts/pr-quality-gate-{role}.md` first. Insert YAML frontmatter block at top. Do not paraphrase; copy the body verbatim.
- `version: "1.0"` for all initial files.
- `role` frontmatter value must match the filename stem (e.g., `role: analyst` for `analyst.md`).
- `description` frontmatter: 1-sentence summary of the role's focus (extract from existing file header if present).
- Changes to `.github/prompts/` are NOT part of this task; those files become derived after TASK-008-03 ships.

**Testing requirements:** Manual inspection only at this stage. TASK-008-05 adds schema validation tests.

---

## TASK-008-02: Implement Verdict Merge Module

**Complexity:** S (2-4 h)

**Objective:** Create `.claude/lib/ai_review_common.py` with `merge_verdicts` and `get_verdict_emoji` (REQ-008-05). This has no dependencies and can start in parallel with TASK-008-01.

**In scope:**
- Create `.claude/lib/` directory if absent.
- Implement `merge_verdicts(verdicts: Sequence[str]) -> str`.
- Implement `get_verdict_emoji(verdict: str) -> str`.
- Docstring must quote the canonical source per `.claude/rules/canonical-source-mirror.md`: cite `.claude/review-axes/{role}.md Output Schema` section as the source of verdict tokens.

**Out of scope:** File I/O, subprocess, any external calls.

**Acceptance Criteria:**
- [ ] Module exists at `.claude/lib/ai_review_common.py`.
- [ ] `merge_verdicts([])` returns `"UNKNOWN"`.
- [ ] `merge_verdicts(["UNKNOWN"])` returns `"UNKNOWN"`.
- [ ] `merge_verdicts(["PASS"])` returns `"PASS"`.
- [ ] `merge_verdicts(["PASS", "WARN"])` returns `"WARN"`.
- [ ] `merge_verdicts(["PASS", "WARN", "CRITICAL_FAIL"])` returns `"CRITICAL_FAIL"`.
- [ ] `merge_verdicts(["PASS", "FAIL"])` returns `"CRITICAL_FAIL"`.
- [ ] `merge_verdicts(["PASS", "REJECTED"])` returns `"CRITICAL_FAIL"`.
- [ ] `get_verdict_emoji("PASS")` returns non-empty string.
- [ ] `get_verdict_emoji("WARN")` returns non-empty string distinct from PASS result.
- [ ] `get_verdict_emoji("CRITICAL_FAIL")` returns non-empty string distinct from PASS and WARN results.
- [ ] `get_verdict_emoji("unknown_token_xyz")` returns non-empty fallback.
- [ ] Module passes `flake8` and `mypy --strict` (or project-equivalent linter).
- [ ] No `eval`, `exec`, subprocess calls in module.

**Files affected:**

| File | Action | Description |
|------|--------|-------------|
| `.claude/lib/__init__.py` | Create | Empty init to make `lib` a package |
| `.claude/lib/ai_review_common.py` | Create | merge_verdicts + get_verdict_emoji |

**Implementation notes:**
- Emoji choices: prefer ASCII-safe fallbacks that render in CI log viewers. Suggested: `[+]`/`[-]`/`[!]`/`[?]` or Unicode checkmark/cross/warning (test in GitHub Actions log before committing).
- Unknown verdict token in `merge_verdicts`: log a warning (use `logging.warning`), treat as `UNKNOWN`.
- `CRITICAL_TOKENS = frozenset({"CRITICAL_FAIL", "REJECTED", "FAIL"})` as a module-level constant.
- Type hints required: `from __future__ import annotations` + `Sequence[str]` from `collections.abc`.

**Testing requirements:** TASK-008-05 writes the test file. At this task, implementer writes the module and manually verifies the truth table above with a quick `python3 -c` invocation.

---

## TASK-008-03: Implement Generator Script

**Complexity:** M (4-8 h)

**Objective:** Create `build/scripts/generate_pr_quality_prompts.py` that derives `.github/prompts/` from `.claude/review-axes/` atomically (REQ-008-02).

**Blocked by:** TASK-008-01 (canonical files must exist to validate generator output).

**In scope:**
- Generator CLI with `--dry-run` and `--no-regen` flags.
- Atomic write (tmp + fsync + rename).
- Schema validation (required frontmatter keys, filename regex).
- Structured stdout (`key=value`).
- ADR-035 exit codes (0/1/2).
- Generated file header: `# GENERATED - do not hand-edit. Source: .claude/review-axes/{role}.md`.

**Out of scope:** Updating orchestrator prose (TASK-008-07), modifying `.githooks/` (TASK-008-04).

**Acceptance Criteria:**
- [ ] `python3 build/scripts/generate_pr_quality_prompts.py` exits 0 and writes 6 files to `.github/prompts/`.
- [ ] Re-running with no canonical changes exits 0 and produces zero git diff.
- [ ] `--dry-run` mode exits 1 if any file would change; exits 0 if all match; writes no files.
- [ ] `--no-regen` skips canonical files containing `<!-- NO-REGEN -->` comment.
- [ ] Invalid filename (not matching `^[a-z][a-z0-9_-]*\.md$`) is skipped with logged warning; other files processed.
- [ ] Missing required frontmatter key causes exit 1 with descriptive message naming the missing key and file.
- [ ] Partial crash (simulate by patching `os.rename` to raise): no corrupt output file exists; `.tmp` file may exist but is not the target path.
- [ ] Stdout contains one `role={role} status=ok output={path}` line per processed role.
- [ ] Stdout contains `summary=generated:{n} skipped:{n} errors:{n}` as final line.
- [ ] No `eval`, `exec`, `shell=True`, subprocess in script.

**Files affected:**

| File | Action | Description |
|------|--------|-------------|
| `build/scripts/generate_pr_quality_prompts.py` | Create | Generator implementation |
| `build/scripts/__init__.py` | Create (if absent) | Package marker |

**Implementation notes:**
- Follow `build/generate_commands.py` as a reference for the regen_guard pattern. Read it before writing.
- `os.rename` is atomic on POSIX when src and dest are on same filesystem (they are: both under repo root).
- Generated file content: prepend the `# GENERATED` banner, then output the canonical file body unchanged (frontmatter preserved as-is). Do not transform the markdown body.
- Use `pathlib.Path` throughout for path operations.
- Regen guard: compute SHA-256 of canonical content and compare against SHA-256 of existing generated file body (strip the `# GENERATED` banner line before hashing). If equal, skip write.

**Testing requirements:** TASK-008-05 writes formal tests. At this task, run manually: `python3 build/scripts/generate_pr_quality_prompts.py && git diff --exit-code .github/prompts/` must exit 0 after first run (assuming files already match canonical seeded content).

---

## TASK-008-04: Add Drift Detection Gates

**Complexity:** S (2-4 h)

**Objective:** Add drift-detection step to `.githooks/pre-push` and add `drift-check` job to `ai-pr-quality-gate.yml` (REQ-008-03).

**Blocked by:** TASK-008-03 (generator's `--dry-run` mode must exist).

**In scope:**
- Append drift-check step to `.githooks/pre-push`.
- Add `drift-check` job to `.github/workflows/ai-pr-quality-gate.yml`.
- Pin any new Action references to SHA.

**Out of scope:** Changes to the generator itself.

**Acceptance Criteria:**
- [ ] `.githooks/pre-push` runs `python3 build/scripts/generate_pr_quality_prompts.py --dry-run` after existing checks.
- [ ] On divergence, pre-push emits message to stderr and exits 1 (does NOT commit or modify files).
- [ ] On no divergence, pre-push continues normally (exits 0 from drift step; overall hook result unchanged).
- [ ] `ai-pr-quality-gate.yml` contains a `drift-check` job that runs `--dry-run` and fails the job on non-zero exit.
- [ ] `drift-check` job emits a GitHub Actions error annotation (`core.error(...)`) on failure.
- [ ] All new Action `uses:` lines pin to commit SHA (not floating tag).
- [ ] Drift check does not execute prompt file content.

**Files affected:**

| File | Action | Description |
|------|--------|-------------|
| `.githooks/pre-push` | Modify | Append drift-check step |
| `.github/workflows/ai-pr-quality-gate.yml` | Modify | Add drift-check job |

**Implementation notes:**
- Pre-push step guards with `if command -v python3 >/dev/null 2>&1; then ... fi` so environments without Python3 fail open (warning, not block). CI has Python3; local dev should too.
- `ai-pr-quality-gate.yml` drift-check job: `needs: []` (runs in parallel with other jobs); `if: always()` is NOT set (drift-check failing should block merge regardless of other job results).
- The `actions/github-script` SHA can be sourced from the existing workflow file where it is already used. Match the existing pinned SHA.

**Testing requirements:** TASK-008-05 covers the hook via `tests/hooks/test_drift_check.py`. At this task, manual test: (1) introduce a one-character diff in a `.github/prompts/` file; run `git push --no-verify` (bypass) to confirm CI catches it; (2) restore the file; confirm hook passes.

---

## TASK-008-05: Write Test Suite

**Complexity:** M (4-8 h)

**Objective:** Write all automated tests for the generator, verdict module, drift hook, and vendored install (REQ-008-06, REQ-008-07).

**Blocked by:** TASK-008-02 (module), TASK-008-03 (generator), TASK-008-04 (hook step).

**In scope:**
- `tests/lib/test_ai_review_common.py`: full truth table for `merge_verdicts`, all `get_verdict_emoji` tokens, 100% coverage.
- `tests/build_scripts/test_generate_pr_quality_prompts.py`: idempotency, partial-write recovery, schema validation, NO-REGEN sentinel, exit codes.
- `tests/hooks/test_drift_check.py`: positive (no drift, exit 0) and negative (drift, unified diff, exit 1).
- `tests/integration/test_vendored_install.py`: fresh-checkout with only `.claude/` subtree.

**Out of scope:** Tests for `/review` command prose (manual verification only; commands are markdown, not Python).

**Acceptance Criteria:**
- [ ] `pytest tests/lib/test_ai_review_common.py --cov=.claude/lib/ai_review_common.py --cov-fail-under=100` passes.
- [ ] `pytest tests/build_scripts/test_generate_pr_quality_prompts.py` passes; includes idempotency, partial-write, schema validation, exit-code assertions.
- [ ] `pytest tests/hooks/test_drift_check.py` passes positive and negative paths.
- [ ] `pytest tests/integration/test_vendored_install.py` passes in temp directory with only `.claude/` subtree.
- [ ] No test uses `pytest.mark.skip` without a linked issue number in the reason string.
- [ ] All tests follow AAA (Arrange/Act/Assert) structure with one blank line between sections.
- [ ] Tests do not modify baseline fixtures to force a pass.

**Files affected:**

| File | Action | Description |
|------|--------|-------------|
| `tests/lib/__init__.py` | Create (if absent) | Package marker |
| `tests/lib/test_ai_review_common.py` | Create | Verdict module tests |
| `tests/build_scripts/__init__.py` | Create (if absent) | Package marker |
| `tests/build_scripts/test_generate_pr_quality_prompts.py` | Create | Generator tests |
| `tests/hooks/test_drift_check.py` | Create | Hook drift tests |
| `tests/integration/test_vendored_install.py` | Create | Vendored install test |

**Implementation notes:**

Partial-write recovery test pattern:
```python
import unittest.mock as mock
import os

def test_partial_write_leaves_no_corrupt_output(tmp_path, canonical_dir):
    # Arrange: set up canonical file and output dir
    ...
    # Patch os.rename to raise after fsync
    with mock.patch("os.rename", side_effect=OSError("simulated crash")):
        # Act: run generator; expect it to raise or exit non-zero
        ...
    # Assert: output path does not exist (or still has old content); .tmp file may exist
    assert not output_path.exists() or output_path.read_text() == old_content
```

Vendored install test pattern:
```python
import shutil, subprocess, tempfile

def test_vendored_install(tmp_path):
    # Arrange: copy .claude/ subtree + CLAUDE.md to tmp_path
    shutil.copytree(repo_root / ".claude", tmp_path / ".claude")
    shutil.copy(repo_root / "CLAUDE.md", tmp_path / "CLAUDE.md")
    # Act + Assert: import ai_review_common from tmp_path and call merge_verdicts
    # (Full /review invocation requires Claude; test the Python components only)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ai_review_common", tmp_path / ".claude/lib/ai_review_common.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.merge_verdicts(["PASS"]) == "PASS"
```

Note: full end-to-end `/review` invocation (which requires Claude Code) is out of scope for automated tests. The vendored install test validates that the Python components load and function correctly from the vendored path.

---

## TASK-008-06: Rewrite `/review` Command

**Complexity:** M (4-8 h)

**Objective:** Rewrite `.claude/commands/review.md` to load 6 canonical axis files, chain 3 skill invocations, merge 9 verdicts, and output a findings table (REQ-008-04).

**Blocked by:** TASK-008-01 (canonical files), TASK-008-02 (merge module).

**In scope:**
- Rewrite `.claude/commands/review.md` prose per DESIGN-008 `/review` component spec.
- Read `scripts/validate_plugin_manifests.py` to determine if `.claude/review-axes/` needs explicit enumeration. Resolve OQ1.
- Document the 6/3 split (canonical vs skill) explicitly in command prose.
- Implement `UNKNOWN` handling per REQ-008-04.

**Out of scope:** Generator, drift check, test suite.

**Acceptance Criteria:**
- [ ] `.claude/commands/review.md` references `.claude/review-axes/` as the source for axis definitions.
- [ ] Command prose names all 6 canonical roles explicitly: analyst, architect, devops, qa, roadmap, security.
- [ ] Command prose specifies the 3 skill invocations: `code-qualities-assessment`, `golden-principles`, `taste-lints`.
- [ ] Command prose specifies `merge_verdicts` from `.claude/lib/ai_review_common.py` for verdict aggregation.
- [ ] Command prose specifies `UNKNOWN` handling: mark axis UNKNOWN, continue, surface in table.
- [ ] Command prose specifies the findings table format (axis, verdict with emoji, key findings).
- [ ] OQ1 resolved and documented in a comment or note in the command file.
- [ ] Command contains no reference to `AIReviewCommon.psm1`.
- [ ] Command does not hard-code any axis evaluation logic (evaluation logic lives in canonical axis files).

**Files affected:**

| File | Action | Description |
|------|--------|-------------|
| `.claude/commands/review.md` | Modify (full rewrite) | Converged /review command |

**Implementation notes:**
- Read the current `.claude/commands/review.md` before rewriting to preserve any non-axis sections (e.g., diff preparation instructions, output formatting header).
- Read `scripts/validate_plugin_manifests.py` to check if it enumerates `.claude/review-axes/` or similar patterns. If it does, update the manifest to include the new directory. Document the finding in the command file as a comment.
- The command file is markdown prose (instructions to the Claude agent), not Python. There are no executable tests for it. Manual verification: run `/review` on a PR with known findings and confirm all 9 axes appear in output.

---

## TASK-008-07: Update Stale Citation in `pr-quality/all.md`

**Complexity:** XS (1-2 h)

**Objective:** Replace stale `AIReviewCommon.psm1` citation with `ai_review_common.py` in `.claude/commands/pr-quality/all.md` (REQ-008-08).

**Blocked by:** TASK-008-02 (module must exist before it can be cited correctly).

**In scope:**
- Read `.claude/commands/pr-quality/all.md`.
- Replace all occurrences of `AIReviewCommon.psm1` with `.claude/lib/ai_review_common.py`.
- Replace any reference to `AIReviewCommon` (without `.py`) with `ai_review_common.py`.
- Verify no other files under `.claude/commands/` cite the deleted PowerShell module.

**Out of scope:** Logic changes to the `all.md` command behavior.

**Acceptance Criteria:**
- [ ] `.claude/commands/pr-quality/all.md` contains `ai_review_common.py` and does not contain `AIReviewCommon.psm1`.
- [ ] `grep -r "AIReviewCommon.psm1" .claude/` exits non-zero (no remaining references).
- [ ] `grep -r "AIReviewCommon[^.]" .claude/` exits non-zero (no remaining unqualified references).

**Files affected:**

| File | Action | Description |
|------|--------|-------------|
| `.claude/commands/pr-quality/all.md` | Modify | Replace stale PowerShell citation |

**Implementation notes:**
- Run `grep -r "AIReviewCommon" .claude/` first to find all occurrences before editing.
- Commit message: `fix(commands): replace stale AIReviewCommon.psm1 citation with ai_review_common.py`.

---

## TASK-008-08: Update GitHub Issues #1933 and #1934

**Complexity:** XS (1-2 h)

**Objective:** Update issue bodies for #1934 and epic #1933 to reflect the correct design: 6 canonical axes, `ai_review_common.py`, chained-skills extras approach (REQ-008-08).

**Blocked by:** TASK-008-02 (module must exist to cite correctly), TASK-008-06 (design finalized in command rewrite).

**In scope:**
- `gh issue edit 1934 --body "..."`: remove "7 axes", add "6 canonical axes + 3 chained skills = 9 total", cite `ai_review_common.py`.
- `gh issue edit 1933 --body "..."`: same corrections.
- Preserve all existing content not related to axis count or module citation.

**Out of scope:** Closing the issues, adding labels, or any other issue management.

**Acceptance Criteria:**
- [ ] `gh issue view 1934 --json body` does not contain "7 axes".
- [ ] `gh issue view 1934 --json body` contains "ai_review_common.py".
- [ ] `gh issue view 1934 --json body` contains "6 canonical" or "6 axes".
- [ ] `gh issue view 1933 --json body` does not contain "7 axes".
- [ ] `gh issue view 1933 --json body` contains the chained-skills approach description.

**Files affected:**

| Resource | Action | Description |
|----------|--------|-------------|
| GitHub issue #1934 | Update via gh CLI | Fix axis count and module citation |
| GitHub issue #1933 | Update via gh CLI | Fix axis count and module citation |

**Implementation notes:**
- Use `gh issue view {n} --json body --jq .body` to read current body before editing. Preserve the existing content; do a targeted string replacement, not a full rewrite.
- OQ4 resolution: perform this update after TASK-008-02 and TASK-008-06 are merged so the citations are accurate at time of update.

---

## Dependency Order

```
TASK-008-01 (canonical files)
TASK-008-02 (merge module)          <- parallel with 01
    |
    +-> TASK-008-03 (generator)
            |
            +-> TASK-008-04 (drift gates)
                        |
                        +-> TASK-008-05 (test suite)   <- also needs 01, 02
    |
    +-> TASK-008-06 (/review rewrite)  <- also needs 01
    |
    +-> TASK-008-07 (stale citation)
    |
    +-> TASK-008-08 (issue updates)   <- also needs 06
```

## Effort Estimate

| Task | Complexity | Hours |
|------|-----------|-------|
| TASK-008-01 | S | 2-4 |
| TASK-008-02 | S | 2-4 |
| TASK-008-03 | M | 4-8 |
| TASK-008-04 | S | 2-4 |
| TASK-008-05 | M | 4-8 |
| TASK-008-06 | M | 4-8 |
| TASK-008-07 | XS | 1-2 |
| TASK-008-08 | XS | 1-2 |
| **Total** | | **20-40 h** |

Parallelism: TASK-008-01 and TASK-008-02 can run simultaneously. TASK-008-03 starts after 01 completes. TASK-008-06, 07, 08 can run after 02 completes independent of 03/04.
