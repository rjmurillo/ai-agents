# Retrospective: pr-5359-merge-state-tier-triage

## Session Info

- **Date**: 2026-09-01
- **Agents**: Orchestrator (GitHub Copilot / Claude session), lease `53590000-0000-4000-8000-000000000006`
- **Task Type**: PR triage, CI-failure remediation, review-thread resolution
- **Outcome**: Success (PR #5359 driven toward merge; see PR for final disposition)

## Phase 0: Data Gathering

Observe: PR #5359 (`fix(github): allowlist executable merge states so Tier T1
stays merge-ready`, closing issue #4899) showed a red `mergeStateStatus` of
`BLOCKED` with two failed required checks (`Validate Spec Coverage`,
`Run Python Tests`), one failed non-required check (`pytest (bulk-nested)`),
and one unresolved Copilot review thread.

Respond: Ran `triage_red_check.py` against every failing check name before
reading any log, per the pr-autofix CI-failure triage step. `Run Python Tests`
and `pytest (bulk-nested)` both returned `RED_ON_MAIN` with an `EvidenceUrl`
pinned to the base commit (`8926061a1`), confirming both were inherited from
`main`, not introduced by the PR. `Validate Spec Coverage` returned `UNKNOWN`
(the workflow is path-filtered and had no prior run on `main` to compare
against), so it could not be dismissed as inherited and needed direct log
reading.

Analyze: The `Validate Spec Coverage` failure's first occurrence was
`HTTP 401: Bad credentials` calling `gh issue view` for #4899 - a transient
GitHub token/API window, corroborated by four other unrelated PRs failing the
same workflow in the same ~65-minute window and all later PRs passing.
Rerunning the failed job cleared the transient failure, but the completeness
critic then returned a real `PARTIAL` verdict: the missing/null
`mergeStateStatus` negative test asserted `CanMerge is False` and that the
reason names itself, but never asserted the resulting `Tier`, leaving half of
acceptance criterion 2 (`UNKNOWN`, missing, and future values cannot reach
`T1`) demonstrated only by inference. The one Copilot review thread was a
correctness finding, not a style nit: the PR body's Security Review section
said "No security-critical changes" while the diff it was attached to
controls whether an armed auto-merge is revoked for the new `UNSUPPORTED`
tier - a merge-authorization-relevant change by the command's own CWE-829
framing.

Apply: Added a direct `Tier == "UNSUPPORTED"` assertion to the existing
missing-`mergeStateStatus` test, closing the criterion without touching
production logic (the classifier already routed it there). Rewrote the PR's
Security Review section to state the merge-authorization impact accurately
alongside the fail-closed direction, and replied to and resolved the Copilot
thread citing the updated section. Verified via the PR's own branch-owned
`test_pr_merge_ready.py` (not a shared checkout copy) that the resulting
tier read is `BLOCKED` (branch-protection/CI/thread state), matching the
merge-path table's `BLOCKED` row rather than a work tier.

Execution trace:

1. `178dda2fd` / `d2f7fc93f` (same content, two worktrees) added the missing
   `Tier == "UNSUPPORTED"` assertion to
   `tests/test_test_pr_merge_ready.py::test_null_merge_state_status_normalizes_to_empty_string`.
2. `edit_pr_body.py` rewrote the Security Review section with a stale-write
   guard (`--expected-hash`) so a concurrent PR-body edit could not be
   silently clobbered.
3. `add_pr_review_thread_reply.py --resolve` replied to and resolved thread
   `PRRT_kwDOQoWRls6duTf0`.
4. `gh run rerun --failed` ccleared the transient `Validate Spec Coverage`
   401 without touching PR content.

Outcome classification: Glad that `triage_red_check.py` immediately separated
two genuinely inherited failures from one that needed real investigation,
preventing wasted debugging effort on `main`'s pre-existing
`test_check_repo_health_scope_precedence.py` /
`test_recovery_manifest_boundaries.py` / `test_gc_worktrees_real_git.py`
flakes. Sad that the local Windows sandbox could not validate the fix
honestly on the first attempt: the pre-push `review-axis-drift` hook reported
false drift on two unrelated generated files because
`build/scripts/generate_pr_quality_prompts.py` reads files without an
explicit UTF-8 encoding, so Windows' default codepage double-mojibake'd a
`→`/`≤` byte sequence that is provably identical between source and generated
file at the byte level. No lasting failure: the same push, run natively from
a WSL worktree, reported `status=ok` for all twelve roles, confirming the
repo content was never actually drifted.

## Phase 1: Insights Generated

Five Whys (the pre-push false positive):

1. `git push` failed pre-push validation on the first attempt.
2. `review-axis-drift` reported `role=devops status=drift` and
   `role=qa status=drift`.
3. The script's own diff output showed the "actual" side using mojibake
   (`â†’`) against a "expected" side using the correct arrow (`→`).
4. Reading the same on-disk file's raw bytes directly showed the correct
   single-encoded UTF-8 sequence (`e2 86 92`) in both cases - the corruption
   was not in the file, it appeared only inside the script's own read path.
5. `build/scripts/generate_pr_quality_prompts.py` opens these files without
   pinning `encoding="utf-8"`, so on a host whose default text encoding is a
   Windows code page, decoding produces the double-mojibake pattern this
   session observed; on a UTF-8-locale host (WSL, and every GitHub Actions
   Linux runner) the same script reports `status=ok`.

Root cause: A missing explicit `encoding="utf-8"` in a file-reading path lets
a comparison hook's correctness depend on the host's default text encoding.
This is a portability defect in `generate_pr_quality_prompts.py` itself, not
in this PR's content, and it would silently and wrongly block any push made
from a non-UTF-8-locale host until noticed.

Patterns and shifts: `triage_red_check.py` before any log read continues to
pay for itself - it converts "which of four red checks are real" from a log-
reading exercise into a single per-check classification call. Verifying a
hook failure against the actual bytes on disk, rather than trusting the
hook's rendered diff, caught a tooling bug instead of accepting a false block.

Learning matrix: Keep triaging every red check against `main` before reading
logs. Keep verifying a review-authenticity finding against the code diff
before conceding or contesting it - the Copilot thread here was correct on
inspection. Add: when a local hook's diff output itself looks encoding-
corrupted, compare raw bytes directly before treating the hook's verdict as
ground truth, and prefer a UTF-8-locale environment for hooks whose scripts
have not pinned an explicit encoding.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Triage every red check against `main` before reading logs | `triage_red_check.py` returned `RED_ON_MAIN` for 2 of 4 checks in one call each | 9 | 90% |
| Verify a bot review-thread finding against the actual diff before disposing it | Confirmed the `UNSUPPORTED` arm does gate auto-merge disarm before conceding the point | 8 | 85% |
| Re-run the branch-owned readiness helper from the PR's own worktree, not a shared checkout | Confirmed `Tier=BLOCKED` and the exact `Reasons` set post-fix | 8 | 85% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Trusted the first pre-push hook failure at face value | Environment-encoding false positive | `generate_pr_quality_prompts.py` reads files without pinning `encoding="utf-8"` | Compare raw bytes directly before accepting a hook diff as real; prefer a UTF-8-locale host for this repo's hooks | 85% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| A Windows worktree git-worktree pointer used an absolute `C:/...` path unreadable from WSL | Created a fresh worktree with WSL's own `git worktree add`, which writes an `/mnt/c/...`-relative pointer | Worktrees are not portably shared between a host git and WSL git; create the worktree from whichever side will run the push |
| Assuming the network TLS handshake failures blocking `uv sync` also blocked the drift check itself | Ran the script directly via the already-built `.venv` interpreter, skipping `uv run`'s sync step | A blocked package download does not mean the already-cached tool is unusable; isolate the failing step before treating a whole gate as broken |

## Phase 3: Decisions

### Action Classification

| Class | Action | Owner | Reference |
|-------|--------|-------|-----------|
| Keep | Triage every red check via `triage_red_check.py` before reading logs | pr-autofix protocol | `.claude/commands/pr-autofix.md` |
| Add | Direct `Tier == "UNSUPPORTED"` assertion for the missing-`mergeStateStatus` case | This session | `d2f7fc93f` |
| Modify | Security Review section must name merge-authorization impact when a change gates auto-merge disarm | This session | `edit_pr_body.py` invocation |
| Add | Pin `encoding="utf-8"` in `build/scripts/generate_pr_quality_prompts.py`'s file reads | Follow-up (out of scope for PR #5359) | This retrospective |

### SMART Validation

The `Tier` assertion addition is specific to one test case, measurable by the
Validate Spec Coverage re-run and by `pytest` locally (130 passed), achievable
without touching classifier production code, relevant to closing acceptance
criterion 2 completely, and applied before requesting re-merge review.

### Action Sequence

1. Run `triage_red_check.py` for every red check before reading any log.
2. When a bot review thread makes a factual claim about the diff, verify it
   against the diff directly before disposing it either way.
3. When a local hook fails, verify the hook's own evidence (bytes, not just
   its rendered diff) before treating the failure as real; prefer a
   UTF-8-locale environment for this repo's hooks when one is available.
4. File the encoding-portability defect as follow-up scope rather than
   folding an unrelated fix into a PR already narrowly scoped to tier logic.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: Before trusting a local hook's failure, compare the file's
  raw on-disk bytes directly; a hook that reads files without an explicit
  encoding can report a diff that does not exist.
- **Atomicity Score**: 85%
- **Evidence**: `generate_pr_quality_prompts.py --dry-run` reported
  `role=devops status=drift` on Windows and `status=ok` for the same commit
  from a UTF-8-locale WSL worktree.
- **Skill Operation**: TAG
- **Target Skill ID**: hook-verification

### Learning 2

- **Statement**: A missing-value/negative-control test should assert the
  full classification result (e.g. `Tier`), not only the boolean gate
  (`CanMerge`), when the acceptance criterion is about classification.
- **Atomicity Score**: 85%
- **Evidence**: `test_null_merge_state_status_normalizes_to_empty_string`
  asserted `CanMerge is False` alone; the AI completeness critic on PR #5359
  correctly flagged this as leaving criterion 2 partially unverified.
- **Skill Operation**: TAG
- **Target Skill ID**: test-completeness

## Skillbook Updates

### ADD

```json
{}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| None | None | None | Existing skills already cover triage-before-logs and diff-first verification |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| hook-verification | raw-bytes-before-trust | This session's WSL vs. Windows comparison | Prevents a tooling encoding bug from blocking a legitimate push |
| test-completeness | assert-full-classification | PR #5359 completeness critic finding | Prevents a negative control from under-proving its acceptance criterion |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| None | No obsolete skill identified | PR #5359 |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| None | Existing pr-autofix triage-before-logs skill | 80% | Tag existing skill rather than add a new one |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| Compare raw bytes before trusting a hook diff | 85% | None found | Recorded here; candidate for skillbook promotion |
| Assert full classification in negative-control tests | 85% | None found | Recorded here; candidate for skillbook promotion |

### +/Delta

#### + Keep

- Triage every red check against `main` before reading any log.
- Verify a bot review-thread's factual claim against the diff before
  disposing it.
- Re-run the branch-owned readiness helper from the PR's own worktree when
  the PR touches that helper.

#### Δ Change

- File `build/scripts/generate_pr_quality_prompts.py`'s missing
  `encoding="utf-8"` as its own follow-up issue rather than scope-creeping it
  into PR #5359.
