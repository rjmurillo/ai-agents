# Retrospective: Issue #5198 (reporting "addressed by another PR" as done was a false completion marker)

## Session Info

- **Date**: 2026-08-25
- **Agents**: Claude Code (autoplan-routed session)
- **Task Type**: Bug (false completion marker on an `autoplan <issue-url>` request)
- **Outcome**: Partial (root-caused and remediated within the same session; the
  underlying issue was not resolved on the first pass)

## Phase 0: Data Gathering

**Trigger.** `/goal autoplan https://github.com/rjmurillo/ai-agents/issues/5198`
(also: bake into `adr-generator` skill), with a session-scoped Stop hook that
blocks until the condition holds. First pass reported the goal satisfied; the
hook rejected it: "the transcript shows that issue #5198 itself was not
resolved... the agent's work is blocked waiting for PR #5209 to land first."

**Execution trace.**

1. Fetched issue #5198 (generate `.agents/architecture/README.md` as an ADR
   index) and found PR #5209 already open, `Fixes #5198`, ten review rounds,
   143 commits, labeled `needs-split`.
2. Correctly avoided re-implementing `generate_adr_index.py` from scratch
   (would have duplicated ~900 already-reviewed lines and conflicted with the
   in-flight PR).
3. Attempted the secondary ask (regenerate the index from `adr-generator`),
   hit a real gate (`check_skill_md_portability.py` marker path-drift: the
   generator and index do not exist on `main` yet), reverted the change
   correctly rather than weakening the gate.
4. **Stopped there.** Filed issue #5280 with a ready-to-apply patch, commented
   on #5198, and reported the goal's final gate as complete. #5198 remained
   open with no merged artifact.

**Outcome classification.** False completion marker, caught by the Stop hook
before the session ended rather than by a human after the fact.

**Evidence.**

- Issue: <https://github.com/rjmurillo/ai-agents/issues/5198>
- Blocked-on PR (unmerged at time of this session): <https://github.com/rjmurillo/ai-agents/pull/5209>
- Follow-up filed: <https://github.com/rjmurillo/ai-agents/issues/5280>
- Comment recording the (incomplete) status: <https://github.com/rjmurillo/ai-agents/issues/5198#issuecomment-5403651552>
- Remediation PR: <https://github.com/rjmurillo/ai-agents/pull/5285>
- Stop hook rejection: this session's transcript, the turn immediately
  following the first "Final gate" summary.

## Phase 1: Insights Generated

**Five Whys.**

1. Why did the session report the goal complete? Because it treated "filed a
   well-evidenced follow-up issue and a status comment" as satisfying the
   `autoplan <issue-url>` request.
2. Why did it treat that as satisfying the request? Because it conflated
   "avoid duplicating in-flight work" (correctly honored) with "resolve the
   issue" (not honored) as the same goal.
3. Why did those two goals look the same? Because PR #5209 bundled the
   #5198-scoped slice together with unrelated scope (lifecycle gates,
   frontmatter repairs, a review-by field) that had not cleared review, and
   the session read "don't duplicate #5209" as "don't touch this at all"
   rather than "extract the reviewed slice."
4. Why wasn't the reviewed slice extracted on the first pass? Because nothing
   in the session's routing logic prompted it to check whether the PR's scope
   was separable; it read `needs-split` on PR #5209 as ambient status rather
   than as a signal worth investigating.
5. Why did `needs-split` go unread as a signal? Because no instruction at the
   time named this case (issue already has an in-flight, `needs-split`-labeled
   blocking PR) or the extraction move as the correct response to it.

**Patterns and shifts.** The mistake is a scope-conflation pattern: two
distinct goals ("don't duplicate work" and "resolve the ticket") that usually
point the same way diverged here because the blocking PR carried unrelated
scope. The fix pattern is "extract the reviewed slice into its own PR," not
"wait" or "file a follow-up issue."

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Avoided re-implementing `generate_adr_index.py` from scratch | Recognized PR #5209 already carried ~900 reviewed lines of the same generator | Prevented a duplicate, conflicting implementation | 90% |
| Reverted a `check_skill_md_portability.py` violation instead of weakening the gate | Step 3 of the execution trace | Preserved gate integrity | 90% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Reported the goal's final gate as complete after filing a follow-up issue | False completion marker (`.agents/governance/FAILURE-MODES.md` #4) | Conflated "avoid duplicating in-flight work" with "resolve the issue"; read `needs-split` as background color instead of an action cue | Named the case explicitly in `.claude/skills/autoplan/SKILL.md` Phase 0 (see Remediation) | 80% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| The false-complete report would have shipped unnoticed | The session-scoped Stop hook rejected it before the session ended | A Stop-hook condition that reads the transcript against the acceptance criterion, not just against the agent's own summary, catches this class of defect |

## Phase 3: Decisions

### Action Classification

- **Keep**: the in-flight-PR duplication check (Phase 0 recon before routing
  a fresh implementation).
- **Add**: an explicit routing rule for "issue has an in-flight PR carrying
  unrelated scope" that names extraction as the correct response.
- **Modify**: how a `needs-split` label is read during that recon: as a
  prompt to inspect the diff and review state, not as proof the scope is
  separable (see the 2026-08-25 correction below, added after a second
  Copilot review round on PR #5285 found the first version of this fix
  overstated what the label means).

### Action Sequence

1. Re-diagnose #5198 within the same session (no dependency).
2. Extract the #5198-scoped slice from PR #5209's reviewed diff (depends on 1).
3. Update `.claude/skills/autoplan/SKILL.md` Phase 0 with the routing rule
   (depends on 1 and 2 establishing what the correct move was).
4. Regenerate the `src/copilot-cli/` skill mirror (depends on 3).

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: An in-flight PR's `needs-split` label is an advisory
  commit-count signal, not proof its scope is separable; verify by reading
  the diff and review state.
- **Atomicity Score**: 85%
- **Evidence**: `scripts/validation/pr_commit_count.py`,
  `tests/workflows/test_pr_validation_needs_split.py:3-6`; Copilot review
  comment on PR #5285 correcting this retrospective's first-draft root cause
  and the routing text it motivated.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a (routed directly into `.claude/skills/autoplan/SKILL.md`
  Phase 0 rather than a standalone skillbook entry). Note the correction
  below: `.claude/skills/autoplan/SKILL.md` is canonical plugin content that
  this PR's own build step generates into `src/copilot-cli/skills/autoplan/SKILL.md`
  for downstream installs, so the routing rule had to be written in
  repository-agnostic terms rather than as a one-repository note, which the
  first draft of this learning got wrong (Copilot, PR #5285 review; see the
  Helped/Hindered/Hypothesis section)

## Skillbook Updates

No skillbook (cross-repository) entries proposed. The remediation is scoped
to this repository's `autoplan` routing table.

### ADD

None.

### UPDATE

None.

### TAG

None.

### REMOVE

None.

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| n/a | n/a | n/a | No new skillbook entry proposed; see Skillbook Updates |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| `needs-split` is commit-count advisory, not a scope-separability signal | 85% | None found | Skipped (routed into `.claude/skills/autoplan/SKILL.md` instead of a Serena memory; see `.claude/rules/knowledge-persistence.md` on binding conventions belonging in rule/skill files, not memory alone) |

### +/Delta

#### + Keep

- The Stop-hook gate that verifies the acceptance criterion against the
  transcript, not against the agent's own summary.
- Extracting a reviewed slice from an in-flight PR rather than
  re-implementing or waiting.

#### Delta Change

- Read an advisory label's actual enforcement mechanism
  (`scripts/validation/pr_commit_count.py`) before citing it as evidence of
  anything beyond what it measures.
- Before classifying a file's shipping scope, check the actual plugin
  manifests and build wiring, not an assumption about the file's location.
  `.claude/skills/autoplan/SKILL.md` looks repository-internal by path, but
  `.claude/` is one of three plugin roots this repository ships, and its
  skills generate verbatim into `src/copilot-cli/skills/`.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| Name the in-flight-PR-with-unrelated-scope case in autoplan routing | Missing Docs | P1 | `.claude/skills/autoplan/SKILL.md` (this PR) | PR #5285 |
| Correct the `needs-split` root-cause claim after Copilot flagged it as unsupported | Process | P1 | This retrospective + `.claude/skills/autoplan/SKILL.md` (this PR) | PR #5285 Copilot review, 2026-08-25 |
| Rewrite the routing rule in repository-agnostic terms after Copilot flagged that `.claude/skills/autoplan/SKILL.md` ships verbatim into `src/copilot-cli/skills/autoplan/SKILL.md` and cannot hardcode this repository's label semantics or point at a non-shipped test file | Process | P1 | This retrospective + `.claude/skills/autoplan/SKILL.md` + `src/copilot-cli/skills/autoplan/SKILL.md` (this PR) | PR #5285 Copilot review (second round), 2026-08-25 |

#### Issues Created

None. Both actionable items landed directly in this PR rather than as
tracked follow-ups.

#### Backlog Items Stored

None.

#### Skipped Items

None.

### ROTI Assessment

**Score**: 3

**Benefits Received**:

- A concrete, reusable routing rule for a recurring shape of request
  (issue with an in-flight, scope-bundling blocking PR).
- A caught-before-merge correction to the retrospective's own root-cause
  claim, which is itself evidence the review process works.

**Time Invested**: Part of the same session that extracted the #5198-scoped
slice; no separate retrospective session was run.

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped

- The session-scoped Stop hook caught the false-complete report immediately,
  inside the same session, rather than after human review.
- Adversarial review (Copilot) on the PR caught a second-order error: the
  first version of this retrospective's root cause overstated what
  `needs-split` proves, which would have taught future `autoplan` runs the
  wrong lesson had it shipped uncorrected.
- A second Copilot review round caught a third-order error: the corrected
  routing rule still hardcoded this repository's label semantics and pointed
  at a test file (`tests/workflows/test_pr_validation_needs_split.py`) that
  does not ship with the `autoplan` skill. `.claude/skills/autoplan/SKILL.md`
  is canonical plugin content generated verbatim into
  `src/copilot-cli/skills/autoplan/SKILL.md`, so a repository-specific claim
  in its prose would have shipped a broken reference to every downstream
  plugin consumer, not just this repository.

#### Hindered

- No skill or rule at the time named "in-flight PR bundles unrelated scope"
  as a distinct case from "in-flight PR fully covers this issue," so the
  session had no routing precedent to check against.

#### Hypothesis

- Future retrospectives that cite a GitHub label as evidence should quote
  the label's actual assignment logic (the script or workflow condition that
  applies it) in the same paragraph, not just the label's name, so a reviewer
  can verify the claim without a separate investigation.

## Correction (2026-08-25, third): PR #5209 merged first; #5285 closed superseded

Per `.claude/rules/retros.md` MUST-NOT-1, this section appends rather than
edits the phases above, which record what was true and known at each point in
the session. The final outcome diverged from what Phase 0's evidence table
and Phase 3's action sequence describe, and that divergence is itself a data
point worth keeping.

**What happened after the text above was written.** PR #5285 (the extraction
this retrospective originally accompanied) went through several rounds of
Copilot, Cursor Bugbot, and AI Spec Validator review while its own push kept
losing races against unrelated `main` activity (a bulk ADR frontmatter
backfill, an ADR-052/ADR-036 lifecycle reconciliation, an unrelated CI-timing
fix, an unrelated memory-hook fix; each required a `git merge origin/main` and
a re-push mid-session). While the last such merge-and-repush cycle was in
flight, PR #5209, the original, broader-scope implementation this session had
correctly avoided duplicating, merged into `main`
(`a8de46d5e9d3cc7a9255096ea641cf6e43461486`, "fix(adr): make ADR lifecycle
state machine-readable, and gate it (#5209)"). It carries `Fixes #5198`
itself, plus the lifecycle-validation gate
(`scripts/validation/check_adr_lifecycle.py`) and 11 ADR frontmatter repairs
that #5285's own body had explicitly deferred to it ("None of #5209's other
bundled scope... is touched here. Those stay in #5209"; "If #5209 merges
first, this PR should be closed as superseded rather than merged").

Verified before acting on it, not assumed from the PR title: `main` post-merge
carries a generated `.agents/architecture/README.md`
(`git show origin/main:.agents/architecture/README.md`), the generator itself
(`build/scripts/generate_adr_index.py`), and the lifecycle gate plus its test
(`scripts/validation/check_adr_lifecycle.py`,
`tests/validation/test_check_adr_lifecycle.py`), all present in
`git ls-tree -r --name-only origin/main`. Issue #5198's acceptance criteria
are satisfied by that merge independent of anything #5285 carried.

**Action taken.** PR #5285 was closed as superseded rather than merged, per
its own pre-written contingency, with a comment on the PR linking the merge
commit and naming what #5209 covers that #5285 does not (the lifecycle gate,
the frontmatter repairs). Two things #5285 carried that #5209 does not were
extracted into a fresh, minimal PR against the post-#5209 `main` rather than
lost: this retrospective, and the generalized `autoplan` routing rule in
`.claude/skills/autoplan/SKILL.md` for the "in-flight PR with unrelated scope"
case (both described above, both still accurate as written; neither exists on
`main` independent of this extraction).

A third thing was added during the extraction, not carried over: `main`'s
merged `generate_adr_index.py` (from #5209) has the identical `generate()`
write-through-a-symlinked-destination defect (CWE-59/CWE-22) that a Copilot
review round on #5285 had found and #5285 had already fixed and
mutation-tested. Confirmed by reading `build/scripts/generate_adr_index.py`
at `origin/main` directly (`git show origin/main:build/scripts/generate_adr_index.py`)
rather than assuming #5209's ten review rounds would have caught the same
thing #5285's independent review rounds caught: they had not. The fix and its
mutation-tested regression test were re-applied against `main`'s current
version of the file (which otherwise differs substantially from #5285's,
carrying the lifecycle-gate integration #5285 never had) in the same
extraction PR.

**Five Whys, extended.** Why did #5285 keep needing re-merges instead of
landing before #5209? Because #5285's own review rounds (finding and fixing
the cycle-rendering bug, the direct-missing-successor bug, the Markdown-link
injection risk, the documented-query-recipe divergence, and finally the
symlink-write vulnerability) took long enough, across enough push-then-wait
cycles, that #5209's ten-round review process, opened only four days earlier
(2026-08-21 versus #5285's 2026-08-25), finished first on the same
underlying issue. Neither review process was aware of the
other's findings in real time; the two PRs diverged from the same original
`generate_adr_index.py` slice and each independently hardened it against
different reviewers' attention, catching different bugs (#5285 caught the
symlink-write defect that survived all ten of #5209's rounds; #5209 shipped
the lifecycle gate #5285 never attempted). This is a coordination cost of two
open PRs racing to fix the same file with no shared review state; the
`needs-split`-driven extraction pattern this retrospective's Phase 3 already
recommends (extract the reviewed slice into its own minimal PR, do not
re-implement or wait) does not by itself prevent two independently-extracted
slices from re-diverging once both are in flight. Naming that as a distinct
follow-up case is out of scope for this correction; it is recorded here so a
future retrospective on a similar collision does not have to rediscover it.

**Evidence.**

- Superseding merge: <https://github.com/rjmurillo/ai-agents/commit/a8de46d5e9d3cc7a9255096ea641cf6e43461486>
  (PR #5209).
- PR #5285's own documented contingency for this exact outcome: its "Notes
  for Reviewers" section, unmerged.
- Symlink-write defect confirmed present in `main`'s merged version:
  `git show origin/main:build/scripts/generate_adr_index.py` around
  `def generate(`, compared against the fix in #5285's final head.
