# Retrospective: Knowledge Audit Fleet Session

## Session Info

- **Date**: 2026-08-02
- **Agents**: Copilot CLI orchestrator (Opus 5); code-review sub-agents on gpt-5.6-terra and gemini-3.1-pro-preview
- **Task Type**: Research
- **Outcome**: Partial

## Failure Mode Classification

Classified against `.agents/governance/FAILURE-MODES.md`. No new class is proposed; both
observed failures land inside the existing taxonomy.

| # | Class | Severity | How it presented here |
|---|-------|----------|-----------------------|
| 4 | False completion markers | High | Three separate success signals were false in one session: `pre_pr.py:330` printed "Ready to create pull request!" without pushing; a real `git push` printed `error: failed to push some refs` while the wrapping pipeline reported exit 0; a markdownlint run reported `Summary: 0 issues` while linting 0 files |
| 9 | Confident-incorrectness recurrence | High | One vivid self-generated measurement was allowed to underwrite an adjacent claim that had no evidence, and the resulting memory contradicted the repo's own `push_guard_base.py` |

Class 4 is the primary. Its cross-cutting theme in the taxonomy, that a soft requirement to
"verify" degrades without an observable artifact, is exactly what happened: I did verify, but
I verified the message rather than the state. The remedy in each case was to name the
artifact (`git ls-remote` output, the before and after SHA, the linted-file count) rather than
to try harder at checking.

The lint case is worth separating because the wrapper already handles it and I bypassed the
wrapper. `.markdownlint-cli2.yaml:118` excludes `.agents/**`, so a lint run against a
retrospective examines nothing. The repo's `markdown-check` hook prints exactly the right
warning for this: "Markdown linting selected 0 of 1 target(s) ... This PASS means 'not
linted', not 'clean'." My direct `npx markdownlint-cli2` invocation had no such warning and
reported `Summary: 0 issues in 0 files`. The lesson is not that the tooling is missing a
guard. It is that calling the underlying tool directly discards a guard the wrapper adds, and
that `Linting: N files` is the artifact while `Summary` is the message.

## Evidence

| Artifact | Reference |
|----------|-----------|
| Router eval arms pinned to the same ref | [#4304](https://github.com/rjmurillo/ai-agents/issues/4304) |
| Atomicity scorer returns 75 for keyboard mash | [#4306](https://github.com/rjmurillo/ai-agents/issues/4306) |
| Memory index reports 305 indexed against 896 files | [#4313](https://github.com/rjmurillo/ai-agents/issues/4313) |
| Scope inversion in plugin rule generation | [#4317](https://github.com/rjmurillo/ai-agents/issues/4317) |
| Stale `__pycache__` defeats mutation control | [#4314](https://github.com/rjmurillo/ai-agents/pull/4314) |
| False success message source | `scripts/validation/pre_pr.py:330` |
| Universal-scope fallback | `build/scripts/generate_rules.py:321-337` |
| Budget gate reads one mirror tree only | `scripts/validation/instruction_budget_constants.py:5` |
| Two-dot diff is deliberate | `scripts/validation/push_guard_base.py` |
| Lint excludes the retrospective tree | `.markdownlint-cli2.yaml:118` |
| Selection disclaimer in the tooling itself | `scripts/validation/checks_tooling.py::_report_selection` |

## Impact

| Area | Severity | Effect |
|------|----------|--------|
| Mutation testing | High | Both directions of the stale-cache trap can silently corrupt a measurement; a mutant reads as surviving a test that would have killed it |
| Plugin consumers | High | Three of 26 rules ship with `applyTo: '**'` and reference an `.agents/` tree that plugin consumers do not have; two are already on `main` |
| Memory tooling | Medium | The index gate cannot detect the orphan class it exists to catch, and the atomicity scorer's only discriminator is whether the text contains a digit |
| Router evaluation | Medium | An eval comparing two arms pinned to the same ref cannot measure a change |
| This session's own output | Medium | Four claims required correction before merge; one memory was rewritten entirely |

## Remediation

| Action | Owner | Tracking |
|--------|-------|----------|
| Omit internal-only rules from the plugin instead of universalizing them | unassigned | [#4317](https://github.com/rjmurillo/ai-agents/issues/4317) |
| Pin router eval arms to distinct refs, or fail loudly when they match | unassigned | [#4304](https://github.com/rjmurillo/ai-agents/issues/4304) |
| Replace or retire the atomicity scorer's digit-presence discriminator | unassigned | [#4306](https://github.com/rjmurillo/ai-agents/issues/4306) |
| Make the memory index gate fail closed when no domain index exists | unassigned | [#4313](https://github.com/rjmurillo/ai-agents/issues/4313) |
| Land the mutation-control rule covering both cache directions | in flight | [#4314](https://github.com/rjmurillo/ai-agents/pull/4314) |
| Persist the push-verification and worktree-mutation traps as memories | done | `docs/push-success-message` |
| Correct the budget memory's "scoping is free" claim | done | `docs/budget-headroom-refresh` |

## Phase 0: Data Gathering

**4-Step Debrief**

1. *Intended result*: audit `.claude/` and `.serena/memories/` against the wiki, make atomic
   adjustments, run evals where possible, open atomic PRs.
2. *Actual result*: five defects filed with reproductions (#4304, #4306, #4313, #4317, plus
   the mutation-control finding shipped as a rule). Nine branches produced. Four of the
   claims I intended to ship were falsified before merge, three of them by adversarial
   review and one by my own control.
3. *What caused the difference*: the audit method changed mid-session from reading and
   comparing text to running commands with paired controls. Everything durable came from the
   second method. Nothing durable came from the first.
4. *What to do differently*: apply the control discipline to my own probes, not only to the
   artifacts under audit. Three of the four falsified claims were mine, and two of those were
   supported by evidence I had generated and not examined.

**Execution Trace**

Audit by citation produced zero verified findings. Audit by executable command produced
five. The turn where I stopped quoting `memory_index.py` and ran it is the pivot: the
citation said it validates the memory tree; the run reported `Files: 305 indexed` against a
tree of 896 files.

**Outcome Classification**

Partial. The defects are real and reproducible. The knowledge artifacts I wrote to
accompany them required three rounds of correction, and one shipped memory had to be
rewritten entirely after review.

## Phase 1: Insights Generated

**Five Whys** (on the shipped-then-rewritten diff-base memory)

1. Why was the memory wrong? It asserted "three dots, never two" and "compare against
   `origin/main`", both of which the repo's own code contradicts.
2. Why did I assert them? I had just measured a two-dot diff reporting 5205 deletions for a
   three-file branch, which is a real and severe failure mode.
3. Why did one true observation become a false general rule? I generalized from the failure
   to its inverse without checking whether the codebase had already reasoned about it.
   `push_guard_base.py` deliberately uses two dots for "committed but not pushed" and
   documents a four-step base ladder specifically because `origin/main` is wrong.
4. Why did I not check? The measurement was vivid and self-generated. Strong evidence for the
   narrow claim created confidence in the adjacent general claim, which had no evidence at all.
5. Why did that go unnoticed until review? I had no step that separates "what I measured"
   from "what I concluded". The memory presented both in one voice.

**Root cause**: strong evidence for a narrow claim was allowed to underwrite an adjacent
broad claim that was never tested. The verification method was applied to the observation
and not to the generalization drawn from it.

**Patterns and Shifts**

The recurring shape across all four falsified claims is the same: a control that cannot
distinguish the hypothesis from its negation. The stale-cache probe returned the mutant
string under both branches of the test. The router eval compared two arms pinned to the same
ref (#4304). The atomicity scorer's discriminator is `re.search(r"\d", text)`, so it cannot
separate a real statement from keyboard mash (#4306). The memory-index gate's orphan check
requires a `skills-<domain>-index.md` that does not exist for the population it is meant to
catch, so absence looks identical to compliance (#4313).

Four independent artifacts, one defect. That is a pattern, not four coincidences.

**Learning Matrix**

| | Worked | Did not work |
|---|---|---|
| **Method** | Run the command, capture both controls | Read the code and reason about what it does |
| **Evidence** | Before and after SHAs, pinned bases | Success messages, exit codes after a pipeline |
| **Review** | Different model family, given the artifact | Self-review of my own generalization |

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Audit by executable command, not citation | `memory_index.py` reports 305 indexed against 896 files; five defects filed | 9 | 90% |
| Paired positive and negative controls | Stale-cache claim confirmed only once fresh and stale answers differed | 9 | 90% |
| Capture before and after SHAs around state changes | Caught a silent `commit-file-count` rejection and a failed push reporting exit 0 | 8 | 95% |
| Falsify my own causal hypothesis before filing | Two hypotheses for #4313 killed on dates and file evidence; filed on measurement alone | 8 | 85% |
| Read the source a reviewer cites before accepting | All three BLOCKING findings on the diff-base memory confirmed against repo code | 8 | 90% |
| Review on a different model family | gpt-5.6-terra and gemini-3.1-pro found seven defects across four artifacts I had verified | 9 | 85% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Generalizing from one vivid measurement | Overreach | Strong evidence for a narrow claim underwrote an adjacent untested one | Search the repo and tracker for the thesis before writing it | 90% |
| Suppressing command output with `>/dev/null 2>&1` | Blindness | Optimized for terse transcript over verifiable state | Never suppress output from a state-changing command | 95% |
| Reading `$?` after a pipeline | Wrong instrument | `git push \| tail` reports `tail`'s status | Capture the artifact, not the exit code | 95% |
| Attributing a background shell's output by its label | Misattribution | Long-running parallel shells; I trusted my own description over the command | Verify the effect, not the report | 90% |
| Building a non-discriminating control | Method | Both branches of the test produced the same observable | Require the two branches to differ before running | 90% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Retracting a correct claim about `python -B` | Noticed stale and fresh both returned the same string, so the row proved nothing | A failing control is not a falsification until the control can discriminate |
| Reporting a branch as pushed when it was not | `git ls-remote` returned empty after a success message | Verify the state, never the message |
| Committing a reviewer's scratch onto `main` | Re-read `git status` and found a branch switch I did not make | A sub-agent given a live worktree will change it |
| A budget overflow at 100.6% of the `.md` ceiling | Measured, then scoped the rule instead of compressing it | Ask whether the rule was ever universal before compressing |

## Phase 3: Decisions

### Action Classification

| Action | Item |
|---|---|
| **Keep** | Executable audit with paired controls; before and after SHA capture; cross-family adversarial review |
| **Drop** | Output suppression on state-changing commands; exit codes read after a pipeline |
| **Add** | Discriminating-control precondition; search-before-writing for memories; post-agent worktree check |
| **Modify** | Treat scoping as free at the gate only, not free downstream (#4317) |

### SMART Validation

Each new learning is specific to a named command or artifact, measurable by a command that
returns a different answer when the learning is violated, achievable in the current session,
relevant to work already in flight, and time-bound to the next state-changing operation.

### Action Sequence

1. File the mechanism defects with reproductions. Done: #4304, #4306, #4313, #4317.
2. Correct the artifacts review falsified. Done: diff-base memory rewritten, budget memory
   corrected, session-log rule qualified, pycache rule extended to both directions.
3. Persist the traps as memories. Done: push-verification, worktree mutation.
4. Land the branches.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: A control whose branches share one observable proves nothing.
- **Atomicity Score**: 90%
- **Evidence**: The `python -B` probe row returned the mutant string whether the interpreter
  read the stale cache or the fresh source, because both held `BBBB`. Rebuilt so the cache
  held `AAAA` and the source `BBBB`; all four invocations then returned `AAAA`.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 2

- **Statement**: Verify a push by remote ref, never by the last message.
- **Atomicity Score**: 95%
- **Evidence**: `pre_pr.py:330` prints "Ready to create pull request!" without pushing. A
  later real push printed `error: failed to push some refs` while the wrapping pipeline
  reported exit 0. `git ls-remote` returned empty in both cases.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 3

- **Statement**: Search the tracker and repo before writing a memory's thesis.
- **Atomicity Score**: 90%
- **Evidence**: The diff-base memory duplicated four existing sources and contradicted two,
  including `push_guard_base.py`'s documented four-step base ladder.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 4

- **Statement**: Scoping a rule is free at the gate, not free downstream.
- **Atomicity Score**: 85%
- **Evidence**: `instruction_budget.py` reads only `.github/instructions`, so a scoped rule
  costs 0 bytes there. `generate_rules.py:321-337` backfills `applyTo: '**'` into the plugin
  when every glob is internal-only. Three of 26 rules are in that state, two on `main`.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 5

- **Statement**: A sub-agent handed a live worktree will change its branch.
- **Atomicity Score**: 95%
- **Evidence**: A review agent left `wt-pushmsg` checked out on `main` with two staged files
  it created. The reflog shows the checkout; the agent's report did not mention it.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

## Skillbook Updates

### ADD

```json
{
  "skill_id": "verification-discriminating-control",
  "statement": "A control whose branches share one observable proves nothing.",
  "context": "Before running any probe intended to confirm or falsify a claim",
  "evidence": "2026-08-02 pycache probe; both branches returned BBBB",
  "atomicity": 90
}
```

```json
{
  "skill_id": "git-verify-push-by-remote-ref",
  "statement": "Verify a push by remote ref, never by the last message.",
  "context": "After any push, especially from a parallel background shell",
  "evidence": "pre_pr.py:330; failed push reporting exit 0 through a pipeline",
  "atomicity": 95
}
```

```json
{
  "skill_id": "memory-search-before-writing",
  "statement": "Search the tracker and repo before writing a memory's thesis.",
  "context": "Before persisting any durable knowledge artifact",
  "evidence": "diff-base memory duplicated four sources and contradicted two",
  "atomicity": 90
}
```

```json
{
  "skill_id": "agents-worktree-is-mutable",
  "statement": "A sub-agent handed a live worktree will change its branch.",
  "context": "After any agent given a filesystem path, before committing there",
  "evidence": "wt-pushmsg left on main with two staged files; reflog confirms",
  "atomicity": 95
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| `decision-the-instruction-budget-gate-already-exists` | "Scoping is free" | "Free at the gate, not downstream" | The gate reads only one of two mirror trees (#4317) |
| `github-skill/pr-creation-rules` | "Three dots, never two" | Diagnostic note pointing at the existing base ladder | Two dots are deliberate in `push_guard_base.py` |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| `score_atomicity` | unreliable | Returns 75 for keyboard mash; discriminator is `re.search(r"\d", text)` (#4306) | Scores in this document are author judgment, not tool output |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| n/a | No skill was retired this session | |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| `verification-discriminating-control` | `testing.md` SHOULD 5 (subprocess isolation) | Medium | Keep separate; SHOULD 5 is about state leakage, this is about control design |
| `git-verify-push-by-remote-ref` | `git/git-lock-pushes-per-branch-not-globally` | Low | Keep separate; that memory is about contention, this about false success |
| `memory-search-before-writing` | `knowledge-persistence.md` "prefer an existing rule file" | Medium | Keep separate; the rule governs placement, this governs whether to write at all |
| `agents-worktree-is-mutable` | none found | None | Add |

## Note On Atomicity Scores

Every percentage in this document is author judgment. `score_atomicity` was not used, because
it returns 75 for keyboard mash and its only discriminator is whether the text contains a
digit (#4306). Naming the tool and filing its output would give these numbers a precision
they do not have.
