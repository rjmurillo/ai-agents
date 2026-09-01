# Retrospective: Issue #4780 Claude-Mem importer path hardcoded to the Claude harness

## Session Info

- **Date**: 2026-09-01
- **Agents**: Claude (implementer, single-issue fleet worker)
- **Task Type**: Bug
- **Outcome**: Success

## Phase 0: Data Gathering

**4-Step Debrief**

- Observe: Issue #4780 reported that
  `.claude-mem/scripts/import_claude_mem_memories.py` builds one fixed path
  under `~/.claude/plugins/marketplaces/thedotmack/scripts/` and exits 1 when
  that file is absent. `SESSION-PROTOCOL` recommends the command at session start
  on every harness, so a Copilot CLI session reports a failure for an optional
  dependency that is simply not installed.
- Respond: read the script before trusting the issue's framing, then read the
  test file that covers it and the governance doc that publishes the command.
- Analyze: three separate defects sit behind one symptom.
  1. Path resolution has no override seam at all: no argument, no environment
     variable, one hardcoded harness-specific default.
  2. The exit-code contract conflates two situations. "The optional plugin is not
     installed" and "the importer you named does not work" both return 1, so a
     caller cannot distinguish a supported configuration from a real failure.
  3. The only test guarding `main` was `assert result in (0, 1)`, an assertion
     that no possible implementation can fail. The exit-code behavior was
     untested in both directions, and the defect was invisible to the suite that
     nominally covered the file.
- Apply: added a pure `resolve_importer(explicit, env, home)` with precedence
  argument, then `CLAUDE_MEM_IMPORTER`, then the Claude Code plugin default;
  split the exit-code contract so an unconfigured absent plugin prints `SKIP:`
  and exits 0 while a configured-but-broken importer stays exit 1; replaced the
  vacuous test with 17 tests that pin both directions of that contract.

**Execution Trace**: checked issue #4780 for a competing PR and a
`PR-AUTOFIX-LEASE` marker (neither present) -> read the script, its tests, and
`MEMORY-MANAGEMENT.md` -> created the external worktree
`/root/src/scratch/worktrees/fix-4780` off `origin/main` -> wrote the resolution
seam and the split exit-code contract -> wrote tests -> hit an `AttributeError`
at collection because the standard-library dataclasses module resolves a class's
module through `sys.modules` and the test loader never registered the module ->
fixed the loader -> ran negative controls -> `ruff check` and `ruff format`
scoped to the changed Python files -> committed -> `pre_pr.py` (all validations
passed) -> pushed under the branch push lock -> opened PR #5459 -> cold
self-review found the `is_configured` escape and fixed it -> Validate PR flagged
a false-positive file claim in the PR body, reworded -> Copilot review returned
three findings, all addressed.

**Outcome Classification**:

- Glad: the negative controls were designed to isolate each direction of the
  exit-code contract separately rather than as one revert-everything run.
- Sad: the first test run did not collect at all, and the first implementation
  shipped an `is_configured` escape that reached a commit.
- Mad: nothing.

## Phase 1: Insights Generated

**Five Whys** (on the shipped defect, not the session)

1. Why did the importer fail under Copilot CLI? Because it exited 1 when
   `~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts` was
   absent.
2. Why did an absent file produce exit 1? Because the code treated "plugin file
   not present" as an error rather than as an optional dependency that is not
   installed.
3. Why was absence modeled as an error? Because the script was written against a
   single host where the plugin is always present, so "absent" was never a state
   the author had to represent.
4. Why did that single-host assumption survive review and the test suite?
   Because the only test on `main` asserted `assert result in (0, 1)`, which
   passes for every possible implementation, so no gate ever executed the script
   on a host without the plugin.
5. Why was an unfalsifiable assertion accepted? Because it reads like coverage.
   Nothing in the repo flags an assertion whose accepted set spans the function's
   entire documented return range, so the gap was invisible at review time and at
   commit time.

**Root cause**: no gate executes this script under a target host's runtime
contract, and the test that nominally covered it could not fail. This is FM-11
(see Phase 2).

**Learning Matrix**

| Category | Insight |
|---|---|
| Keep doing | Reading the existing test for the code under repair before writing the fix. `assert result in (0, 1)` reads like coverage and is worth zero; finding it first reframed the task from "add an override" to "the contract was never tested, so state it and pin it". |
| Keep doing | Designing negative controls that flip one branch each rather than reverting the whole change. A whole-change revert produces import and signature errors that look like a passing control while proving nothing about behavior. |
| Start doing | When a fix converts a failure into an intentional success, write the over-correction control too, forcing the *other* branch to succeed. Without it the suite cannot distinguish "skips when it should" from "skips always". |
| Stop doing | Assuming a harness-specific default has a counterpart on the other harness. Claude-Mem ships only as a Claude Code plugin; inventing a plausible Copilot path would have been an unverifiable claim shipped as code. |

## Phase 2: Diagnosis

### Failure Mode Classification

**Primary: FM-11, Customer-Facing Generated Artifact Shipped Without Runtime
Verification** (`.agents/governance/FAILURE-MODES.md`, section 11).

The load-bearing sentence of FM-11 is: "Tests validate the artifact's structure
only. No gate ever executes the artifact under the runtime contract of its
target host (the working directory the host sets, the environment variables it
exports, the process model). The artifact ships structurally valid and
behaviorally broken."

That is this defect. The script is published by
`.agents/governance/MEMORY-MANAGEMENT.md` and by `SESSION-PROTOCOL` as a
session-start command for every harness, which makes Copilot CLI a target host.
The one test covering `main` asserted only that the return value was an integer
in `(0, 1)`, so no gate ever executed the script on a host where
`~/.claude/plugins/` does not exist.

**Named divergence from FM-11 as written**: FM-11's first sentence scopes the
pattern to "a generator produces an artifact". This script is hand-authored, not
generator-produced, and it is installed by cloning the repository. The mechanism
FM-11 names (no gate runs the artifact under the target host's runtime contract)
is what produced the defect; the generator premise is not satisfied. Recording
the divergence rather than silently stretching the definition, per
`.claude/rules/canonical-source-mirror.md`.

### Near Misses Ruled Out (adjacent failure modes)

**FM-10, Silent Defaults and Guard-Clause Suppression.** The closest adjacent
mode, and the one this fix most risks *becoming*, because it converts an exit 1
into an exit 0. Ruled out on three grounds:

1. FM-10 requires that "the call site has no way to know the operation did not
   actually do what its name claims". The new skip prints a `SKIP:` line naming
   both `$CLAUDE_MEM_IMPORTER` and `--importer`. The suppression is an artifact,
   which is FM-10's own prescribed replacement.
2. FM-10's principle is "there is no neutral default for a missing signal". An
   absent optional plugin is not a missing signal; it is a supported, documented
   configuration. The genuinely-missing-signal case, a path the caller named that
   is not there, still exits 1.
3. The original defect ran the other direction. It over-reported failure rather
   than suppressing it, so FM-10 does not describe the bug being fixed.

**FM-9, Confident-Incorrectness Recurrence.** Ruled out: FM-9's trigger is a
change claiming to match or mirror a canonical source without quoting it. The
hardcoded path cited nothing and was correct for the harness it was written on.
FAILURE-MODES section 11 draws exactly this line ("This is distinct from FM #9"):
FM-9 is the author's unverified confidence, FM-11 is the pipeline gap.

**FM-4, False Completion Markers.** Ruled out: no agent claimed this work was
done when it was not. The vacuous assertion is adjacent, since a test that cannot
fail is a green signal that means nothing, but FM-4 lives at the agent-narration
layer.

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Read the target script and its existing test before implementing from the issue body | Issue described defect 1 only; defects 2 and 3 (exit-code conflation, `assert result in (0, 1)`) were visible only in the source | 9 | 90% |
| Isolate each contract direction with its own single-branch negative control | Control A failed exactly 1 test, control B exactly 2; the whole-change revert failed 14 but mostly on `TypeError`, proving nothing | 9 | 85% |
| Baseline `ruff format --check` before running the formatter | All four `.claude-mem/scripts/*.py` fail it on `main`; a blanket format would have buried the fix in unrelated churn | 7 | 80% |
| Verify the relayed review finding against the review's own `commit_id` | Finding 1 was reported against `d1435721d`; the fix already existed in `196dd523e`, so the action was to add the missing regression test, not to re-fix working code | 8 | 85% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Decided the exit code from `path.exists()` alone, leaving `is_configured` asserted only by tests | Latent contract defect, reached commit `176e68873` | The exit-1 behavior rested on an unstated invariant inside `resolve_importer` (a default is returned only when it exists) instead of the stated contract | Branch on the classification the resolver already computed; never re-derive a decision the caller stored | 90% |
| Loaded modules via `spec_from_file_location` without registering them in `sys.modules` | Collection error, caught before commit | Pre-existing test-loader helper; the omission is invisible until a module under test uses a dataclass | Register the module in `sys.modules` in the loader helper | 85% |
| Wrote "`dataclasses.py`" in the PR body while explaining stdlib behavior | CI red on Validate PR | The gate treats any backtick-quoted `*.py` token in `## Changes` as a claimed changed file | Name stdlib modules without the `.py` extension in PR prose | 75% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Nearly invented a Copilot CLI default plugin path beside the Claude one | Checked that no Claude-Mem Copilot plugin exists; shipped one real default plus an override seam instead | A "harness detection" that points at a path you cannot verify is a fabricated claim shipped as code |
| Nearly treated `CLAUDE_MEM_IMPORTER=""` as a configured path | `.strip()` plus a parametrized empty/whitespace test | `VAR=""` is the shell idiom for disabling an inherited value; treating it as configured turns a disable into exit 1 |
| The `is_configured` escape would have made the race unfalsifiable | Cold self-review before the bot review; Copilot independently reported the same defect against the older SHA | Tests that lean on the same invariant as the code cannot detect that invariant breaking |

## Phase 3: Decisions

### Action Classification

| Action | Type | Rationale |
|---|---|---|
| Split the exit-code contract on `is_configured` | Add | The acceptance criteria name it and it is the crux of the issue |
| Replace the vacuous test with 17 pinning tests | Modify | The gate gap that let the defect ship |
| Narrow `except Exception` to `except OSError` | Modify | On the block being extracted; FM-10 shape |
| Register modules in `sys.modules` in the test loader | Add | Without it the test file does not collect |
| Cite and quote the canonical source in the governance doc | Add | `.agents/governance/**` is bound by `.claude/rules/canonical-source-mirror.md` |
| Split `MEMORY-MANAGEMENT.md` at the 500-line advisory | Drop | Already firing at 506 lines before this change; splitting a governance document is its own change |
| Invent a Copilot default importer path | Drop | No such plugin exists to point at |

### SMART Validation

| Learning | Specific | Measurable | Achievable | Relevant | Time-bound | Verdict |
|---|---|---|---|---|---|---|
| L1: an assertion accepting a function's full return range is not a test | Names the exact shape (`in (0, 1)`, `is not None`) | Countable by scanning the test tree | A lint rule or a review question | Produced this defect and hid it | Applies at every test write | Pass |
| L2: a fix that creates an intentional success needs an over-correction control | Names both controls and what each must fail | Each control names the exact tests it must fail | Two extra test runs, seconds each | Separates a conditional skip from a blanket skip | Applies whenever an error path becomes a success | Pass |
| L3: decide from the stored classification, never re-derive it | Names the anti-pattern (second existence check) | The negative control fails when violated | One boolean branch | Caused the escape in `176e68873` | Applies at every guard that consumes a resolver result | Pass |

### Action Sequence

1. Resolution seam and exit-code split (no dependencies).
2. Tests pinning both directions (depends on 1).
3. Negative controls (depends on 2).
4. `is_configured` refactor plus race regression tests (depends on 3, since the
   controls are what exposed the weakness of the first shape).
5. Governance doc citation and verbatim quotes (depends on 1 and 4, because the
   quoted fragments must be final).
6. Retrospective (depends on all of the above).

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: An assertion accepting a function's entire return range tests nothing.
- **Atomicity Score**: 92%
- **Evidence**: `tests/test_claude_mem_scripts.py` on `main` asserted `result in (0, 1)` for a function documented to return only 0 or 1; the Copilot-path defect in issue #4780 passed it.
- **Skill Operation**: ADD
- **Target Skill ID**: N/A

### Learning 2

- **Statement**: A fix creating an intentional success needs an over-correction control.
- **Atomicity Score**: 88%
- **Evidence**: Control A (`return 0` to `return 1`) failed 1 test; control B (`if resolution.is_configured:` to `if False:`) failed exactly the 2 configured-but-missing tests. Only B distinguishes a conditional skip from a blanket one.
- **Skill Operation**: ADD
- **Target Skill ID**: N/A

### Learning 3

- **Statement**: Decide from the resolver's stored classification, never re-derive it downstream.
- **Atomicity Score**: 90%
- **Evidence**: Commit `176e68873` decided the exit code from `path.exists()` alone, so a default removed between resolution and use would exit 1 for an unconfigured optional plugin. Fixed in `196dd523e`; the regression test fails when the existence-only shape is restored.
- **Skill Operation**: ADD
- **Target Skill ID**: N/A

## Skillbook Updates

### ADD

```json
{
  "skill_id": "testing-full-range-assertion-is-vacuous",
  "statement": "An assertion accepting a function's entire return range tests nothing.",
  "context": "When reading or writing a test for a function with a small documented return set, ask which implementation would make it fail; if none, the contract is unspecified.",
  "evidence": "tests/test_claude_mem_scripts.py asserted result in (0, 1) and passed on the issue #4780 defect",
  "atomicity": 92
}
```

```json
{
  "skill_id": "testing-over-correction-negative-control",
  "statement": "A fix creating an intentional success needs an over-correction control.",
  "context": "Whenever a change converts an error path into a deliberate success (a skip, a default, a no-op), run a second control forcing the other branch to succeed.",
  "evidence": "PR #5459 controls A and B failed 1 and 2 tests respectively; only B proved the skip was conditional",
  "atomicity": 88
}
```

```json
{
  "skill_id": "design-consume-stored-classification",
  "statement": "Decide from the resolver's stored classification, never re-derive it downstream.",
  "context": "When a resolver returns a value plus a classification, branch on the classification; a second check of the underlying state can disagree with it.",
  "evidence": "Commit 176e68873 re-checked path existence and would have flipped the exit-code contract for a vanished default",
  "atomicity": 90
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| N/A | N/A | N/A | No existing entry needed revision |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| N/A | N/A | N/A | N/A |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| N/A | N/A | N/A |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| testing-full-range-assertion-is-vacuous | `.agents/governance/TESTING-RIGOR.md` pos+neg+edge bar | Partial. TESTING-RIGOR requires that negative tests exist; it does not say an existing assertion can be unfalsifiable | Keep as distinct |
| testing-over-correction-negative-control | `.claude/skills/ai-agents-empirical-probe-toolkit` negative-control recipe | Partial. The toolkit covers negative-control design; the over-correction direction for intentional-success changes is not called out | Keep as distinct |
| design-consume-stored-classification | `.claude/rules/code-quality.md` defensive-programming section | Low. That section covers validating at boundaries, not consuming a classification a caller already computed | Keep as distinct |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| testing-full-range-assertion-is-vacuous | 92% | none | Skipped |
| testing-over-correction-negative-control | 88% | none | Skipped |
| design-consume-stored-classification | 90% | none | Skipped |

All three clear the 70 percent bar and would normally be persisted. They are
recorded as Skipped, not written, and the reason is stated rather than hidden:
`.claude/rules/knowledge-persistence.md` MUST-5 requires a hand-written keyword
row in `.serena/memories/memory-index.md` for every new memory, and roughly 20
fleet worktrees are active against this repository concurrently. Adding rows to
that shared index from a single-issue bug-fix branch invites merge conflicts for
every other in-flight branch. The learnings are captured here and in PR #5459;
persisting them belongs in a campaign-level change that owns the index.

### +/Delta

#### + Keep

- Read the target script and its tests before writing code, rather than
  implementing from the issue body alone. The issue described defect 1; defects 2
  and 3 were only visible in the source and the test file.
- Verify a relayed review finding against the review's own `commit_id` before
  acting. Finding 1 was real at `d1435721d` and already fixed at `196dd523e`;
  the correct response was the missing regression test, not re-fixing code that
  was already correct.

#### Delta Change

- Reach for the over-correction negative control by default on any change that
  introduces an intentional-success path, instead of treating one control as
  sufficient.
- Write stdlib module names without a file extension in PR prose, since the
  Validate PR gate reads any backtick-quoted `*.py` token in `## Changes` as a
  claimed changed file.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| `.agents/governance/MEMORY-MANAGEMENT.md` exceeds the 500-line taste-lint advisory (506 before this change, larger after the mandated verbatim quotes) | Process | P3 | Skip | Advisory only; pre-existing and enlarged by a competing rule |
| Validate PR flags any backtick-quoted `*.py` token as a changed-file claim, including stdlib references | Tool Gap | P3 | Skip | Known false-positive class; worked around by rewording |
| No gate detects an assertion accepting a function's full return range | Tool Gap | P2 | Memory | Learning 1 above; recorded here pending a campaign-level owner |

#### Issues Created

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| none | No P0 or P1 delta items surfaced | N/A | N/A |

#### Backlog Items Stored

| Item | Priority | Memory File |
|------|----------|-------------|
| Vacuous-assertion detection (Learning 1) | P2 | Not stored; see Memory Persistence note on shared-index contention |

#### Skipped Items

| Item | Reason |
|------|--------|
| Splitting `MEMORY-MANAGEMENT.md` | Advisory, pre-existing on `main`, and out of scope for a bug fix |
| Formatting the other three `.claude-mem/scripts/*.py` files | Unrelated churn; they fail `ruff format --check` on `main` |
| A Copilot CLI default importer path | No Claude-Mem Copilot plugin exists to point at |

### ROTI Assessment

**Score**: 3

**Benefits Received**:

- Named the mechanism (FM-11) that let a single-host assumption pass a green
  suite, which is reusable beyond this script.
- Produced a concrete, checkable heuristic for spotting unfalsifiable assertions.
- Established the over-correction control as the discriminator for any
  intentional-success change.

**Time Invested**: One session, roughly 25 percent of it on the retrospective.

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped

- `FAILURE-MODES.md` sections 9, 10, and 11 are written with explicit "why this
  is X, not Y" boundaries, which made classification a reading task rather than a
  judgment call.
- The review tooling exposes `commit_id` on each review, which is what separated
  "already fixed" from "still broken" on finding 1 without guessing.

#### Hindered

- The pre-existing test loader silently omitted `sys.modules` registration, which
  surfaces only when a module under test uses a dataclass. The failure appears as
  `AttributeError: 'NoneType' object has no attribute '__dict__'` raised inside
  the standard library, pointing nowhere near the loader.
- `.claude/rules/canonical-source-mirror.md` mandates verbatim quotes in
  `.agents/governance/**`, while the taste-lint file-size advisory pushes the
  other way on an already-oversized document. The two rules pull against each
  other and neither yields.

#### Hypothesis

Vacuous assertions of the `assert x in (0, 1)` shape are mechanically detectable:
an assertion comparing a call's return against a set covering its full documented
range. If a taste-lint rule flagged them, the FM-11 gate gap this issue exposed
would be visible at commit time rather than at issue-report time. Falsifiable by
scanning the test tree for the pattern and counting how many hits are genuine
contract gaps versus intentional either-or assertions.

## References

- Issue #4780, PR #5459
- `.agents/governance/FAILURE-MODES.md` sections 9, 10, 11
- `.claude/rules/canonical-source-mirror.md`
- `.agents/governance/TESTING-RIGOR.md`
- `.claude/rules/knowledge-persistence.md`
