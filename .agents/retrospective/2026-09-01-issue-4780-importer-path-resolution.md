# Retrospective: Issue #4780 Claude-Mem importer path hardcoded to the Claude harness

## Session Info

- **Date**: 2026-09-01
- **Agents**: Claude (implementer, single-issue fleet worker)
- **Task Type**: Bug (cross-harness runtime contract, exit-code contract)
- **Outcome**: Success

## Phase 0: Data Gathering

**4-Step Debrief**

- Observe: Issue #4780 reported that
  `.claude-mem/scripts/import_claude_mem_memories.py` builds one fixed path
  under `~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts`
  and exits 1 when that file is absent. `SESSION-PROTOCOL` recommends the
  command at session start on every harness, so a Copilot CLI session reports a
  failure for an optional dependency that is simply not installed.
- Respond: read the script before trusting the issue's framing, then read the
  test file that covers it and the governance doc that publishes the command.
- Analyze: three separate defects sit behind one symptom.
  1. Path resolution has no override seam at all: no argument, no environment
     variable, one hardcoded harness-specific default.
  2. The exit-code contract conflates two different situations. "The optional
     plugin is not installed" and "the importer you named does not work" both
     return 1, so a caller cannot distinguish a supported configuration from a
     real failure.
  3. The only test guarding `main` was
     `assert result in (0, 1)`, an assertion that no possible implementation can
     fail. The exit-code behavior was therefore untested in both directions, and
     the defect was invisible to the suite that nominally covered the file.
- Apply: added a pure `resolve_importer(explicit, env, home)` with precedence
  argument, then `CLAUDE_MEM_IMPORTER`, then the Claude Code plugin default;
  split the exit-code contract so an unconfigured absent plugin prints `SKIP:`
  and exits 0 while a configured-but-broken importer stays exit 1; replaced the
  vacuous test with 14 tests that pin both directions of that contract.

**Execution Trace**: checked issue #4780 for a competing PR and a
`PR-AUTOFIX-LEASE` marker (neither present) -> read the script, its tests, and
`MEMORY-MANAGEMENT.md` -> created the external worktree
`/root/src/scratch/worktrees/fix-4780` off `origin/main` -> wrote the resolution
seam and the split exit-code contract -> wrote tests -> hit an
`AttributeError` at collection because `dataclasses` resolves a class's module
through `sys.modules` and the test loader never registered the module -> fixed
the loader -> 27 pass -> ran three negative controls -> `ruff check` and
`ruff format` scoped to the two changed Python files -> committed -> ran
`pre_pr.py` -> pushed under the branch push lock -> opened the PR.

**Outcome Classification**:

- Glad: the negative controls were designed to isolate each direction of the
  exit-code contract separately rather than as one revert-everything run. The
  broad revert failed 14 tests but almost all of them failed on `TypeError:
  main() got an unexpected keyword argument`, which proves the tests call a new
  API and proves nothing about behavior. The two targeted controls each flipped
  one branch and failed exactly the tests that own that branch.
- Sad: the first test run did not collect at all. The `dataclass` decorator on a
  module loaded through `spec_from_file_location` without `sys.modules`
  registration fails at class creation, which is a trap the pre-existing loader
  had never triggered because no module under test used a dataclass.
- Mad: nothing.

## Phase 1: Insights Generated

**Learning Matrix**

| Category | Insight |
|---|---|
| Keep doing | Reading the existing test for the code under repair before writing the fix. `assert result in (0, 1)` reads like coverage and is worth zero; finding it first reframed the task from "add an override" to "the contract was never tested, so state it and pin it". |
| Keep doing | Designing negative controls that flip one branch each rather than reverting the whole change. A whole-change revert produces import and signature errors that look like a passing negative control while proving nothing about behavior. |
| Start doing | When a fix converts an error into an intentional success, write the over-correction control too. Here that was patching the configured-but-missing branch to return 0 and confirming exactly the two exit-1 tests fail. Without it the suite cannot distinguish "skips when it should" from "skips always". |
| Stop doing | Assuming a harness-specific default has a counterpart on the other harness. Claude-Mem ships only as a Claude Code plugin; inventing a plausible Copilot plugin path would have been an unverifiable claim shipped as code. |

## Phase 2: Diagnosis

### Failure Mode Classification

**Primary: FM-11, Customer-Facing Generated Artifact Shipped Without Runtime
Verification** (`.agents/governance/FAILURE-MODES.md`, section 11).

The load-bearing sentence of FM-11 is: "Tests validate the artifact's structure
only. No gate ever executes the artifact under the runtime contract of its
target host (the working directory the host sets, the environment variables it
exports, the process model). The artifact ships structurally valid and
behaviorally broken."

That is this defect exactly. The script is published by
`.agents/governance/MEMORY-MANAGEMENT.md` and by `SESSION-PROTOCOL` as a
session-start command for every harness, which makes Copilot CLI a target host.
The one test covering `main` asserted only that the return value was an integer
in `(0, 1)`, so no gate ever executed the script under a host where
`~/.claude/plugins/` does not exist. It shipped structurally valid and
behaviorally broken on that host.

**Named divergence from FM-11 as written**: FM-11's first sentence scopes the
pattern to "a generator produces an artifact". This script is hand-authored, not
generator-produced, and it is installed by cloning the repository rather than by
a plugin install. The mechanism FM-11 names (no gate runs the artifact under the
target host's runtime contract) is what produced the defect; the generator
premise is not satisfied. Recording the divergence rather than silently
stretching the definition, per `.claude/rules/canonical-source-mirror.md`.

### Near Misses Ruled Out

**FM-10, Silent Defaults and Guard-Clause Suppression.** This is the closest
adjacent mode and the one this fix most risks *becoming*, because the fix
converts an exit 1 into an exit 0. Ruled out as the classification of the
original defect, and deliberately avoided in the repair, on three grounds:

1. FM-10 requires that "the call site has no way to know the operation did not
   actually do what its name claims". The new skip prints a `SKIP:` line naming
   both `$CLAUDE_MEM_IMPORTER` and `--importer`. The suppression is an artifact,
   which is FM-10's own prescribed replacement.
2. FM-10's principle is "there is no neutral default for a missing signal".
   An absent optional plugin is not a missing signal; it is a supported,
   documented configuration, and the exit 0 asserts that state rather than
   papering over an unknown one. The genuinely-missing-signal case, a path the
   caller named that is not there, still exits 1.
3. The original defect ran the other direction. It was over-reporting failure,
   not suppressing it, so FM-10 does not describe the bug being fixed.

The FM-10 risk in the repair is pinned by test
`test_exits_1_when_configured_environment_importer_does_not_exist` and by the
over-correction negative control below.

**FM-9, Confident-Incorrectness Recurrence.** Tempting, because the original
author asserted one plugin location from a single environment. Ruled out: FM-9's
shape is "partial signal, premature conclusion, confident delivery, multi-round
correction", and its trigger is a change claiming to match or mirror an existing
canonical source without quoting it. The hardcoded path was correct for the
harness it was written on and cited nothing; nothing was mirrored and no
multi-round correction occurred. FM-9 describes the author's unverified
confidence, FM-11 describes the pipeline gap, and FAILURE-MODES section 11 draws
exactly that line ("This is distinct from FM #9"). The gap is what let a
correct-on-one-host path survive review and a nominally passing test suite.

**FM-4, False Completion Markers.** Ruled out: no agent claimed this work was
done when it was not. The vacuous `assert result in (0, 1)` is adjacent, since a
test that cannot fail is a green signal that means nothing, but FM-4 lives at
the agent-narration layer and no narration was involved. The unfalsifiable
assertion is the FM-11 gate gap, not a false claim of completion.

### Evidence

- Defect: `.claude-mem/scripts/import_claude_mem_memories.py` at `origin/main`
  commit `43bbb188b`, lines 31 to 45. One `Path.home() / ".claude" / ...`
  expression, then `return 1` when it does not exist.
- Gate gap: `tests/test_claude_mem_scripts.py` at the same commit,
  `TestImportMemoriesMain.test_exits_1_when_plugin_missing`, body
  `assert result in (0, 1)`. The test name asserts exit 1 and the body accepts
  either value, so it passes on every implementation including the broken one.
- Publication surface: `.agents/governance/MEMORY-MANAGEMENT.md` lines 167, 306,
  and 339 recommend the command with no harness qualification.

### Remediation

| Change | File | Effect |
|---|---|---|
| `resolve_importer(explicit, env, home)` pure function | `.claude-mem/scripts/import_claude_mem_memories.py` | Precedence: argument, `CLAUDE_MEM_IMPORTER`, Claude plugin default. Fully unit-testable with no real HOME. |
| `ImporterResolution.is_configured` | same | Carries the configured/not-configured distinction that drives the exit code, instead of re-deriving it at the branch. |
| Split exit-code contract | same | Unconfigured absent plugin exits 0 with `SKIP:`; configured-but-missing or failing importer exits 1. |
| `except Exception` narrowed to `except OSError` | same | Adjacent FM-10 shape on the touched path: the broad catch swallowed the exception type for every failure, including bugs. |
| `sys.modules[name] = mod` in the test loader | `tests/test_claude_mem_scripts.py` | `dataclasses` resolves a class's module through `sys.modules`; without registration the module raises `AttributeError` at class creation. |
| 14 tests replacing 1 vacuous test | same | Pins both directions of the exit-code contract. |
| Resolution order and exit-code table | `.agents/governance/MEMORY-MANAGEMENT.md` | Documents the environment variable the acceptance criteria require. |

### Negative Controls

Three runs, all against the committed test suite.

| Control | Mutation | Result |
|---|---|---|
| Whole-change revert | Restore the `origin/main` script | 14 failed, 13 passed. Weak: most failures are `TypeError: main() got an unexpected keyword argument 'env'`, which proves an API change, not a behavior change. |
| Skip-branch flip | Fixed script, `return 0` changed to `return 1` in the unconfigured-absent branch only | Exactly 1 failed: `test_exits_0_and_skips_when_optional_plugin_absent`, `assert 1 == 0`. Isolates the exit-0 half of the contract. |
| Over-correction | Fixed script, `if resolution.is_configured:` forced to `if False:` so the configured branch never fires | Exactly 2 failed: `test_exits_1_when_explicit_importer_does_not_exist` and `test_exits_1_when_configured_environment_importer_does_not_exist`. Kills the discrimination itself rather than one return value, so it proves the tests read the condition and not just the outcome. |

The second and third controls together are what make the claim "the fix changes
behavior in the intended direction, and only in that direction" falsifiable. The
first control alone would not have supported it.

### Session Failures

None escaped to the PR. Two were caught in-session:

1. The `dataclasses` collection error, caught by the first test run before any
   commit.
2. A self-review escape that reached commit `176e68873`. The first
   implementation keyed the exit code on `resolution.path.exists()` alone and
   never called `is_configured` in production, so the property was asserted only
   by tests. The exit-1 behavior therefore rested on an unstated invariant
   inside `resolve_importer` (it returns a default only when that default
   exists) rather than on the contract the code claims to implement. A future
   edit relaxing that invariant would have silently converted configured
   failures into skips with no test failing, because the tests exercised the
   same invariant rather than the condition. Fixed by branching on
   `is_configured` directly, which also strengthened the over-correction control
   from "flip a return value" to "disable the discrimination".

### Successes (Tag: helpful)

- Verifying no competing PR and no `PR-AUTOFIX-LEASE` marker on the issue before
  starting, as this backlog is a shared queue across fleet sessions.
- Checking the `ruff format` baseline before formatting. The
  `.claude-mem/scripts/*.py` files all fail `ruff format --check` on `main`, so a
  blanket format would have buried the fix in unrelated churn. The formatter diff
  was inspected and touched only lines this change introduced.

### Near Misses

- Nearly invented a Copilot CLI default plugin path to sit alongside the Claude
  one. There is no Claude-Mem Copilot plugin to point at, so the "harness
  detection" the issue title implies would have been a fabricated path shipped as
  code. The honest design is: one real default, an override seam, and a clean
  skip when neither resolves.
- Nearly treated an empty `CLAUDE_MEM_IMPORTER=""` as a configured path, which
  would make the standard shell idiom for disabling an inherited variable exit 1.
  Blank values now fall through to the default, covered by a parametrized test.

## Phase 3: Decisions

### Action Classification

| Action | Type | Rationale |
|---|---|---|
| Split the exit-code contract | Fix | The acceptance criteria name it and it is the crux of the issue. |
| Replace the vacuous test | Fix | The gate gap that let the defect ship; leaving it would leave the contract unpinned. |
| Narrow `except Exception` | Boy Scout, in scope | On the line block being extracted; FM-10 shape. |
| Register modules in `sys.modules` | Fix, required | Without it the test file does not collect. |
| Split `MEMORY-MANAGEMENT.md` at 535 lines | Deferred | The taste-lint 500-line advisory already fired at 506 lines before this change. Splitting a governance document is out of scope for a bug fix and belongs in its own change. |

## Phase 4: Extracted Learnings

### Learning 1

A test whose assertion admits every possible return value is worse than no test,
because it occupies the slot where the real test would go and reports green. The
tell is an assertion built from `in (...)`, `is not None`, or a comparison
against a union of the only values the function can return. When repairing a
function, read its existing test first and ask what implementation would make it
fail; if the answer is "none", the contract is unspecified and the repair must
specify it.

### Learning 2

When a fix converts a failure into an intentional success, one negative control
is not enough. Flipping the new success back to a failure proves only that the
new test reads the new branch. The second control, forcing the *other* branch to
succeed as well, is what separates a conditional skip from a blanket skip. Both
controls are cheap and they fail different tests, which is the evidence that the
condition, not just the outcome, is under test.

## Phase 5: Persist and Close

### +/Delta

#### + Keep

- Read the target script and its tests before writing code, rather than
  implementing from the issue body alone. The issue described defect 1; defects 2
  and 3 were only visible in the source and the test file.
- Baseline the formatter before running it on a file with pre-existing drift.

#### Delta Change

- Reach for the over-correction negative control by default on any change that
  introduces an intentional-success path, instead of treating one control as
  sufficient.

### Delta Triage

#### Actionable Items Identified

- `.agents/governance/MEMORY-MANAGEMENT.md` is 535 lines against a 500-line
  taste-lint advisory, and was already at 506 before this change. Splitting it is
  a separate change and is not attempted here.
- The other three `.claude-mem/scripts/*.py` files fail `ruff format --check` on
  `main`. Not touched; formatting them is unrelated churn in a bug-fix PR.

#### Skipped Items

- Harness auto-detection beyond the Claude default. Skipped because no Claude-Mem
  Copilot plugin exists to detect. The override seam covers any future install
  location without a code change.

### Helped, Hindered, Hypothesis

#### Helped

- `FAILURE-MODES.md` sections 9, 10, and 11 are written with explicit
  "why this is X, not Y" boundaries, which made the classification a reading task
  rather than a judgment call.

#### Hindered

- The pre-existing test loader silently omitted `sys.modules` registration, which
  surfaces only when a module under test uses `dataclasses`. The failure appears
  as `AttributeError: 'NoneType' object has no attribute '__dict__'` inside
  `dataclasses.py`, which points nowhere near the loader.

#### Hypothesis

Vacuous assertions of the `assert x in (0, 1)` shape are mechanically
detectable: an assertion comparing a function's return against a set that covers
its full documented range. If a taste-lint rule flagged them, the FM-11 gate gap
this issue exposed would be visible at commit time rather than at issue-report
time. Falsifiable by scanning the test tree for the pattern and counting how many
hits are genuine contract gaps versus intentional either-or assertions.

## References

- Issue #4780
- `.agents/governance/FAILURE-MODES.md` sections 9, 10, 11
- `.claude/rules/canonical-source-mirror.md` (divergence-recording discipline)
- `.agents/governance/TESTING-RIGOR.md` (positive, negative, edge bar)
