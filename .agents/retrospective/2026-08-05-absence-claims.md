# Retrospective: Absence claims in durable knowledge

## Session Info

- **Date**: 2026-08-05
- **Agents**: Copilot CLI (Opus 5) as author; Sol, Gemini, and Grok as adversarial reviewers
- **Task Type**: Bug
- **Outcome**: Partial
- **Failure Mode**: #9 Confident-incorrectness recurrence (per `.agents/governance/FAILURE-MODES.md`)

Scope: the memory-subdirectory work, commits `78e808238` through `74459685d`. One
Critical false claim shipped into a durable artifact and was caught by review. A second
error of the same shape occurred later in the same session and was caught by a gate.

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe.** Commit `78e808238` added a memory asserting: "No script regenerates these,
and no validator checks them, so a hand-written guess persists silently." Three clauses,
all false. `scripts/update_memory_index_tokens.py` regenerates them.
`scripts/ci/memory_index_token_ratchet.py` validates them. `lefthook.yml` runs the first
as a pre-commit autofix and the second as a pre-push gate.

**Respond.** An adversarial review on a third model family flagged it. I verified the
claim by execution rather than accepting the reviewer's wording, found the reviewer was
right, and corrected the memory in `9cd7097f1`.

**Analyze.** The memory was teaching the exact anti-pattern that
`.claude/rules/knowledge-persistence.md` MUST-6 forbids in as many words: repair a stale
count "by running `uv run --frozen python scripts/update_memory_index_tokens.py`, not by
editing the number by hand." The artifact whose purpose is to instruct future agents was
instructing them to violate a binding rule.

**Apply.** The corrective is an evidence bar for absence claims in the rule that already
governs what may be written to a rule or a memory.

### Execution Trace

| # | Event | Evidence |
|---|-------|----------|
| 1 | Working in `scripts/memory/`, formed the hypothesis that no regenerator existed | Session context |
| 2 | Ran one path probe: `scripts/memory/update_memory_index_tokens.py` | Returned "No such file" |
| 3 | Treated the single negative as proof of repo-wide absence | No follow-up search run |
| 4 | Wrote the absence claim into a durable memory | `78e808238` |
| 5 | Hand-computed a token count of 2522 to fill the gap the false claim implied | Same commit |
| 6 | Adversarial review on a third model family flagged the claim | Review output |
| 7 | Verified by execution; regenerator exists one directory up at `scripts/update_memory_index_tokens.py` | File present |
| 8 | Ran the real regenerator; it produced 2538, not my 2522 | Sibling branch |
| 9 | Corrected the memory, the corpus counts, and the "Fixed in #4655" claim | `9cd7097f1` |
| 10 | Later, same session: stashed a change, re-ran ruff, confirmed an E402 predated my branch, concluded "not mine" | Correct measurement |
| 11 | Pre-push `python-lint-ratchet` blocked the push anyway | `pre_pr.py` red |
| 12 | Read `scripts/ci/ruff_ratchet.py`: it gates *changed files* with zero tolerance and reads no baseline | Zero `baseline` references |
| 13 | Fixed the import; verified no circular import before moving it | `bc9cb0d62` |

### Outcome Classification

**Mad.** A false claim reached a durable artifact and would have taught future agents to
hand-edit token counts, which a binding rule forbids and which drifts silently.

**Sad.** The hand-computed 2522 was already stale when I wrote it. A later edit changed
the file. That is precisely the drift MUST-6 exists to prevent, so the error demonstrated
the rule it contradicted.

**Glad.** Adversarial review on a different model family caught it. Verifying every
reviewer claim by execution caught wrong line numbers from all three reviewers and caught
one reviewer's root cause being shallower than the truth.

## Phase 1: Insights Generated

### Five Whys

1. **Why did a durable memory contain a false claim?** Because I asserted an absence
   without a repo-wide search.
2. **Why did I assert it without a repo-wide search?** Because one path probe returned
   "No such file" and I treated that single negative as sufficient.
3. **Why did one negative feel sufficient?** Because I had guessed the path from the
   directory I was already working in. The probe confirmed a hypothesis I had already
   formed rather than testing it.
4. **Why did nothing catch it before it became durable?** Because absence claims are
   self-sealing. A presence claim ("file X line N says Y") is checked the next time
   someone opens X. An absence claim ("nothing does Z") is never revisited, because
   nothing later in the workflow searches for the evidence that would contradict it.
5. **Why did the workflow encourage writing it?** Because the standing instruction to log
   eureka moments rewards logging discoveries, and "there is no regenerator" registered as
   a discovery. The instruction carries no evidence bar keyed to claim type, so a
   single guessed-path negative was enough to produce a durable artifact.

**Root cause**: the persistence rule sets an evidence bar for presence claims about rules
(MUST NOT 3: grep the rule tree and cite file and item number) but sets none for absence
claims about the repository. The two failure modes are mirror images and only one was
covered.

### Fishbone Analysis

| Category | Contributing factor |
|----------|--------------------|
| Method | One path probe substituted for a repo-wide search |
| Method | Hypothesis formed before the probe, so the probe confirmed rather than tested |
| Tooling | No validator can check an absence claim in prose; only a human or a reviewer can |
| Process | The eureka-logging instruction rewards volume of logged discoveries, not their verification |
| Process | Absence claims receive no later scrutiny, unlike cited presence claims |
| Environment | I was working inside `scripts/memory/`, which made the wrong path the plausible one |

### Patterns and Shifts

Two incidents in one session share one shape: **I ran a real experiment, got a true
result, and drew a conclusion the experiment did not license.**

| | Incident 1 (token counts) | Incident 2 (E402 ratchet) |
|---|---|---|
| Experiment run | Probe one guessed path | Stash the change, re-run ruff |
| Result | True: that path has no file | True: the violation predates my branch |
| Conclusion drawn | No regenerator exists anywhere | The gate will not hold this against me |
| Why it failed | Too narrow for a repo-wide claim | Measured age; the gate keys on membership in the changed set |
| Caught by | Adversarial review | Pre-push gate |

Incident 2 is the milder case: the gate caught it in seventeen minutes at no lasting cost.
Incident 1 had no gate, which is why it shipped.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Adversarial review on a model family other than the author's | Caught a Critical that three of my own passes missed | 9 | 75% |
| Verify every reviewer claim by execution before acting | Grok, Gemini, and Sol each gave at least one wrong line number; all three caught | 8 | 75% |
| Negative control on a new test | Reverting the fix fails `test_directory_only_match_scores_below_stem_match` with `assert 100.0 == 50.0`, proving the test guards | 8 | 80% |
| Bound the fix to the boundary I disturbed | Directory distortion was mine and was fixed; the pre-existing tie-breaker absence was flagged, not built | 7 | 75% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Single path probe as proof of repo-wide absence | False negative | Hypothesis formed before probe; no repo-wide search | Evidence bar for absence claims in `knowledge-persistence.md` | 75% |
| Hand-computed a token count | Rule violation | Followed from the false absence claim | Already covered by MUST-6; the fix is upstream at the absence claim | 70% |
| Concluded a lint gate did not apply because the violation was pre-existing | Wrong question | Never read what the gate keys on | Read the gate's own criterion before concluding exemption | 75% |
| Read a branch's absence from `git ls-remote` as push failure while the push was still running, then launched a second push of the same ref | False negative, same class as row 1 | An in-flight push is absent from the remote, so the probe cannot separate "failed" from "not finished"; I had a memory saying exactly this and did not consult it | State the precondition: `ls-remote` answers what landed only after the shell's exit status is known | 80% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Gemini returned DO NOT SHIP on a ranking regression. Accepting it verbatim would have reverted a change that measured a large net win across four queries; dismissing it would have shipped a real regression | Reproduced the finding, then ran a before/after probe across four queries, then fixed the narrow defect and kept the win | A reviewer's finding and a reviewer's root cause are separate claims; verify each |
| Two commits reached the remote without gate coverage because I committed while a push was in flight | `conftest.py` emitted a `#3109` warning naming the exact SHA drift; re-ran `ruff_ratchet.py` and full `pre_pr.py` against current HEAD, both green | Do not commit while a push is running; the hook validates the ref it was handed, not the ref that transfers |
| The adversarial reviewer of this retrospective returned two findings (`H1`, `M1`) asserting that a lefthook autofix and a hook named `memory-token-update` do not exist. Accepting them would have replaced two true statements with two false ones | Read `lefthook.yml` directly: line 260 defines `memory-token-update` with exactly the `skip` array claimed, and `git_hook_policy.py:5658` runs `update_memory_index_tokens.py` with no `--check`, which is the autofix. The reviewer had grepped only the sibling hook `memory-token-counts`, found its `--check` invocation, and concluded the other did not exist | The reviewer committed the precise error this retrospective documents, on the artifact documenting it. Verify a reviewer's absence findings by the same standard the rule sets for your own |
| Spent several minutes reconciling why `memory_index.py` reported `Files: 321 indexed` both before and after I added an index row, and ran a negative control to prove my entry was validated | `memory-index-validator-checks-one-direction-only.md` already answers it: the counter parses the 33 `skills-*-index.md` domain indices, not `memory-index.md`, so "a stable count across an edit is expected and says nothing about whether your entry landed" | Third retrieval failure of the same shape in one session, after the two that produced the primary finding. The knowledge was written, indexed, and unread. The probe was not wasted (it surfaced the `0 missing` reporting defect, now added to that memory), but the reconciliation preceding it was |

## Phase 3: Decisions

### Action Classification

| Action | Item | Rationale |
|--------|------|-----------|
| Keep | Adversarial review on a different model family for every implemented change | Caught the only Critical of the session |
| Keep | Verify reviewer claims by execution before acting on them | Caught wrong line numbers from all three reviewers |
| Keep | Negative control on every new regression test | Proved the guard actually guards |
| Add | An evidence bar for absence claims in `.claude/rules/knowledge-persistence.md` | The rule covers unverified presence claims and not their mirror image |
| Modify | Nothing. MUST-6 already forbids hand-edited counts and was correct | The defect was upstream of it |
| Drop | Nothing | No practice used this session should stop |

### SMART Validation

The single new convention, stated as a MUST NOT item:

- **Specific**: names the claim shape (an assertion that no file, script, validator, or
  rule exists) and the required evidence (a repo-wide search, cited).
- **Measurable**: a reviewer can check whether the search is cited. An uncited absence
  claim is a review defect.
- **Achievable**: one `grep -r` or `glob` at the repository root.
- **Relevant**: the incident is cited inline, per `knowledge-persistence.md` SHOULD-2.
- **Time-bound**: applies at write time, before the artifact is committed.

### Action Sequence

1. Add MUST NOT 4 to `.claude/rules/knowledge-persistence.md` (relocated to `universal.md` MUST NOT 9 by issue #5492). No dependencies.
2. Regenerate both instruction mirrors with `build/scripts/generate_rules.py`, per MUST-2.
   Depends on 1.
3. Re-run `scripts/validation/instruction_budget.py`. The rule applies to `**`, so the
   addition consumes always-on headroom in all four language baselines, and `.py` sits at
   97.8% with 2216 bytes free. Depends on 2.
4. Adversarial review on a model family other than the author's. Depends on 3.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: An absence claim requires a repo-wide search, not a single path probe.
- **Atomicity Score**: 75%
- **Evidence**: `78e808238` asserted no regenerator existed after one probe of
  `scripts/memory/update_memory_index_tokens.py`. The file is at
  `scripts/update_memory_index_tokens.py`, one directory up. Corrected in `9cd7097f1`.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 2

- **Statement**: Before concluding a gate does not apply, read the gate's own criterion.
- **Atomicity Score**: 75%
- **Evidence**: Proving an E402 predated the branch is a correct measurement of the wrong
  quantity. `scripts/ci/ruff_ratchet.py` gates changed files with zero tolerance and
  contains zero references to any baseline, so age was never the criterion.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 3

- **Statement**: Verify a reviewer's finding by execution before accepting or dismissing it.
- **Atomicity Score**: 75%
- **Evidence**: Gemini's High on ranking was real, but its root cause was shallower than
  the truth. A before/after probe across four queries showed the change was a large net
  win with one degenerate regression, which is what made the narrow fix in `4835bdb59`
  correct rather than a revert.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

## Skillbook Updates

### ADD

```json
{
  "skill_id": "knowledge-absence-claim-evidence-bar",
  "statement": "An absence claim requires a repo-wide search, not a single path probe.",
  "context": "Writing any rule, memory, ADR, or review comment that asserts no file, script, validator, or rule exists.",
  "evidence": "78e808238 asserted no token regenerator existed after probing one guessed path; scripts/update_memory_index_tokens.py exists one directory up. Corrected in 9cd7097f1.",
  "atomicity": 75
}
```

```json
{
  "skill_id": "ci-read-the-gate-criterion-before-claiming-exemption",
  "statement": "Before concluding a gate does not apply, read the gate's own criterion.",
  "context": "Any time a pre-push or CI gate might be argued away as pre-existing, inherited, or out of scope.",
  "evidence": "scripts/ci/ruff_ratchet.py gates changed files with zero tolerance and holds zero baseline references, so proving a violation was pre-existing measured the wrong quantity.",
  "atomicity": 75
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| `retrospective` | `SKILL.md` Phase 5 mandates the closing activities (Plus/Delta, ROTI, Helped/Hindered/Hypothesis), but `references/learning-template.md` ends at `## Deduplication Check` and the Success Criteria says the artifact must match that template | Give the template a `## Closing` section, or move the closing activities out of Phase 5 | The two instructions cannot both be satisfied. A reviewer read the Success Criteria and called the section non-conformant; 4 of the 145 retros in `.agents/retrospective/` carry `## Closing`, so the ambiguity is already producing divergent artifacts. No validator enforces either reading. Kept the section here, because dropping it would discard content Phase 5 requires |
| `memory` | `scripts/test_memory_size.py` prints "Recommendation: Decompose into N focused files" on any overflow | Qualify it: decomposition is wrong when the memories' mutual contradiction is the knowledge | Conventional wisdom, and the tool's own printed advice, said split the oversized push memory into a new atomic file. First principles said the opposite. The failure being recorded was a retrieval failure across two memories that were each half right and never read together; a third file recreates it. Co-locating them and cutting the duplicated narrative took the file from 9,979 to 8,940 characters, so the size objection dissolved once the redundancy was removed rather than relocated |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| n/a | n/a | n/a | n/a |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| n/a | n/a | n/a |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| knowledge-absence-claim-evidence-bar | `.serena/memories/git/git-absence-and-case-in-plumbing.md` | Low | Keep both. That memory covers two specific git plumbing commands that cannot prove absence. This learning covers the reasoning step, in any tool, and belongs in a rule rather than a memory because it binds every harness. |
| knowledge-absence-claim-evidence-bar | `.claude/rules/universal.md` MUST NOT 8 (`knowledge-persistence.md` MUST NOT 3 when written) | High | Add as a sibling item in the same rule rather than a new file, per SHOULD-1. That item bars unverified presence claims about rules; this bars unverified absence claims about the repository. |
| ci-read-the-gate-criterion-before-claiming-exemption | `.serena/memories/python/python-lint-ratchet-is-not-a-ratchet.md` | High | Already committed in `65ccf3b20`. No duplicate written. |
| push-ls-remote-ordering | `.serena/memories/git/git-empty-hook-run-means-an-empty-push.md` | High | Augmented that memory rather than writing a new one, per SHOULD-1. It already warned that in-flight absence proves nothing; what it lacked was the sequencing against the competing "verify with `ls-remote`" rule, plus the `cannot lock ref` tell. |
| push-ls-remote-ordering | `.serena/memories/git/git-hooks-observations.md` line 78 | High | Corrected in place. That line was a contributing cause: it correctly says the log tail lies, then recommends `git ls-remote` with no precondition, which is the probe that misled me. |
| Verify a reviewer's finding by execution | `.serena/memories/decision-agent-self-assessment-does-not-survive-review.md` | Medium | Not written. The session applied it consistently and it produced no defect, so it is recorded here as a Keep rather than persisted as new knowledge. |

## Closing

### Plus / Delta

**Plus.** Adversarial review on a different model family was the only control that caught
the Critical. Verification by execution caught defects in all three reviewers' output.

**Delta.** The eureka-logging instruction amplified this error instead of catching it: it
rewards logging discoveries and sets no evidence bar keyed to claim type. Adding that bar
to the rule that governs persistence is the fix, and it is P1 because the instruction is
standing and will fire again.

### ROTI

3 of 5. The retrospective produced one durable rule change and confirmed that the second
incident's knowledge was already captured, avoiding a duplicate memory.

### Helped, Hindered, Hypothesis

**Helped**: running the reviewer's claim rather than reading it. **Hindered**: forming the
path hypothesis before probing it, which turned a test into a confirmation. **Hypothesis**:
an evidence bar stated as a MUST NOT beside the existing presence-claim bar will be applied,
because the two read as a pair and the existing one has held.
