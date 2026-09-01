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
  that file is absent. The issue attributed the session-start recommendation to
  `SESSION-PROTOCOL.md`; that file no longer exists, deleted with the session
  skill cluster by PR #5135 on 2026-08-18, two weeks before this session and
  after the issue was filed on 2026-08-09. The live publication surface is
  `.agents/governance/MEMORY-MANAGEMENT.md`, which carries the command
  unqualified by harness at lines 167, 487, and 520. The defect is unchanged by
  the correction: a Copilot CLI session reports a failure for an optional
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
- Apply: added `resolve_importer(explicit, env, home)` with precedence argument,
  then `CLAUDE_MEM_IMPORTER`, then the Claude Code plugin default. Its precedence
  is decided from its arguments alone, with no process state read; only the
  lowest tier touches the filesystem, through the one `default.exists()` call
  that decides whether the plugin is installed. So it is isolated from ambient
  state, not pure, and its result can change between calls if the plugin is
  installed or removed;
  split the exit-code contract so an unconfigured absent plugin prints `SKIP:`
  and exits 0 while a configured-but-broken importer stays exit 1; replaced the
  vacuous test with a suite that pins both directions of that contract. The
  count is deliberately not restated here. It went stale repeatedly during
  review because it lived in two documents that drift independently. The PR
  body's Testing section now carries pasted `pytest` output instead of a
  transcribed figure, and names CI as the authority for any later head.

**Execution Trace**: checked issue #4780 for a competing PR and a
`PR-AUTOFIX-LEASE` marker (neither present) -> read the script, its tests, and
`MEMORY-MANAGEMENT.md` -> created the external worktree
`/root/src/scratch/worktrees/fix-4780` off `origin/main` -> wrote the resolution
seam and the split exit-code contract -> wrote tests -> hit an `AttributeError`
at collection because the standard-library dataclasses module resolves a class's
module through `sys.modules` and the test loader never registered the module ->
fixed the loader -> ran negative controls -> `ruff check` scoped to the changed
Python files, and also ran the formatter, which `.claude/rules/python.md` forbids
(see Failures) -> committed -> `pre_pr.py` (all validations
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
contract, and the test that nominally covered it could not fail. FM-11 is the
closest mechanism match, and it is not a clean fit: its premise is a generated
artifact, and this script is hand-authored. No existing class fits, which is the
unresolved classification Phase 2 sets out below and issue #5461 raises.

**Learning Matrix**

| Category | Insight |
|---|---|
| Keep doing | Reading the existing test for the code under repair before writing the fix. `assert result in (0, 1)` reads like coverage and is worth zero; finding it first reframed the task from "add an override" to "the contract was never tested, so state it and pin it". |
| Keep doing | Designing negative controls that flip one branch each rather than reverting the whole change. A whole-change revert produces import and signature errors that look like a passing control while proving nothing about behavior. |
| Start doing | When a fix converts a failure into an intentional success, write the over-correction control too, forcing the *other* branch to succeed. Without it the suite cannot distinguish "skips when it should" from "skips always". |
| Start doing | Asking the runtime what a platform does rather than encoding a belief about it, and pinning the derivation itself so a hardcoded answer fails a test. All three platform defects in this PR (the doubled separator, the backslash overcorrection, then the drive-anchored suffix) came from writing down what I thought path handling does instead of reading `posixpath` and `ntpath`. |
| Stop doing | Treating a change as done because it is written down as done. The unpinned catch-narrowing survived nine rounds of my own review because the PR body listed it as complete, so every later pass read the record instead of the code. A checklist entry is a claim, and it decays exactly like any other claim in this file. |
| Start doing | Fixing the invariant rather than the reported instance. `expand_home` owes one narrow property: when it expands a current-user `~`, the suffix it appends cannot silently discard the injected `home`. Three mechanisms can violate that (rooted suffix, drive-anchored suffix, drive-relative suffix) and I patched them one review round at a time because each round I asked "what is broken" instead of "what does this function guarantee, and what can break that guarantee". The invariant is about the expansion, NOT general containment: `expand_home("~/../outside", home)` returns `home / "../outside"` and escapes via `..`, a plain absolute path is returned as-is by design, and `~otheruser` is deliberately left relative. This function is not a containment check and must not be cited as one. |
| Stop doing | Writing a test that asserts the behavior the code currently has, when what the code has is the thing under question. `test_backslash_tilde_resolves_against_home` locked in a defect and made it look covered for two rounds. A test earns its place by constraining a decision, not by restating one. |
| Stop doing | Assuming a harness-specific default has a counterpart on the other harness, and equally, asserting it has none. Upstream Claude-Mem does integrate with Copilot CLI, through an MCP-only installer (`MCP_IDE_INSTALLERS` in `src/services/integrations/McpIntegrations.ts`) that supplies no bulk-importer path. Inventing a Copilot importer path would have shipped an unverifiable claim as code; writing "no Copilot equivalent" shipped a different unverifiable claim as documentation, and Copilot review caught it. The checkable statement is the narrow one: no default bulk-importer path exists for that harness. |

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
`.agents/governance/MEMORY-MANAGEMENT.md` as a session-start command for every
harness, which makes Copilot CLI a target host.
The one test covering `main` asserted only that the return value was an integer
in `(0, 1)`, so no gate ever executed the script on a host where
`~/.claude/plugins/` does not exist.

**Named divergence from FM-11 as written, and the required proposal**: FM-11's
first sentence scopes the pattern to "a generator produces an artifact". This
script is hand-authored and installed by cloning the repository. The mechanism
FM-11 names (no gate runs the artifact under the target host's runtime contract)
is what produced the defect; the generator premise is not satisfied.

### Unresolved rule conflict: retros.md MUST-2 versus the Ask First boundary

This retrospective does **not** fully satisfy `.claude/rules/retros.md` MUST-2,
and says so rather than implying otherwise.

MUST-2 offers exactly two compliant outcomes: classify against an existing
FAILURE-MODES class, or "propose a new class in a linked ADR". Neither is
reachable from this session:

- **No existing class fits.** All eleven were checked, not just the neighbours.
  FM-11 matches the mechanism and fails on its generator premise. FM-9, FM-10,
  and FM-4 are excluded on the record below. FM-1 through FM-8 concern agent
  process (context reading, compaction, instruction inversion, premature merge,
  rubber-stamping, delegation, security drift) and do not describe a shipped
  code defect at all. Recording FM-11 with a divergence note is the closest
  honest answer, and it is still short of the rule.
- **The ADR cannot be authored here.** `AGENTS.md` lists new ADRs under **Ask
  First**. This was an unattended session, and `.claude/rules/voice.md` directs
  that Ask First items "get no guess: halt only that branch; continue
  elsewhere."

So the two rules conflict for an unattended run, and the conflict is not
resolvable by an agent. **Issue #5461 is the halt action, not the compliance.**
It records the analysis and puts the three-way decision (widen FM-11, add FM-12,
or reject) in front of a human. Full MUST-2 compliance is **blocked on that
human decision** and should be closed out when the ADR is written.

An earlier draft of this section recorded the divergence and moved on, which was
the "stretch the nearest class" move the rule forbids. A later draft cited #5461
as though filing it discharged MUST-2, which it does not. This is the accurate
statement of where the requirement actually stands.

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
| Verify the relayed review finding against the review's own `commit_id` | Finding 1 was reported against `d1435721d`; the fix already existed in `196dd523e`, so the action was to add the missing regression test, not to re-fix working code | 8 | 85% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Ran the Python formatter on changed files, and cited its check mode as a baseline gate, repeatedly and across many commits, review replies, and the PR body | Repo-rule violation, shipped throughout the PR | `.claude/rules/python.md` says "Never run `ruff format` or cite `ruff format --check` as a gate. No gate runs it; main does not conform," with `tests/validation/test_ruff_format_not_enforced.py` holding the evidence. I never read the Python rule file; I inferred a formatting convention from the tooling being installed | Read the language rule file before running any language tooling not named by the task, and treat "the tool exists in the venv" as no evidence that the repo sanctions it | 92% |
| Decided the exit code from `path.exists()` alone, leaving `is_configured` asserted only by tests | Latent contract defect, reached commit `176e68873` | The exit-1 behavior rested on an unstated invariant inside `resolve_importer` (a default is returned only when it exists) instead of the stated contract | Branch on the classification the resolver already computed; never re-derive a decision the caller stored | 90% |
| Narrowed `except Exception` to `except OSError` and never asked a test to confirm it | Unverified fix, shipped from commit `176e68873` and unpinned for nine rounds | Measured when review finally asked: reverting the narrowing left all 94 tests green, so the fix was indistinguishable from the bug it replaced. I wrote single-decision negative controls for every neighbouring change and never turned one on this, because it was already recorded as done in the PR body and I read my own record instead of the suite | A behavior change is not done until a control proves the old behavior fails. Run the revert before claiming the fix, not when a reviewer asks | 95% |
| Wrote four checkable claims into the retrospective from memory rather than from the artifact | False documentation, reached commit `c1ff7baf0` | A wrong interval (14 days called three weeks), citations stale after the cited file grew, a Root Cause asserting FM-11 while Phase 2 of the same file says it does not fit, and `resolve_importer` called pure when it calls `default.exists()`. Each was checkable in seconds; none was checked. Same failure as the code defects one level up | Recompute every number, re-resolve every citation, and re-read the cited body before writing a claim about it, including claims about work you did yourself | 92% |
| Loaded modules via `spec_from_file_location` without registering them in `sys.modules` | Collection error, caught before commit | Pre-existing test-loader helper; the omission is invisible until a module under test uses a dataclass | Register the module in `sys.modules` in the loader helper | 85% |
| Wrote "`dataclasses.py`" in the PR body while explaining stdlib behavior | CI red on Validate PR | The gate treats any backtick-quoted `*.py` token in `## Changes` as a claimed changed file | Name stdlib modules without the `.py` extension in PR prose | 75% |
| Used `Path.expanduser()` inside a function whose whole point was resolving against an injected `home` | Isolation defect, reached commit `0dbf3069d` | `expanduser` reads the process `HOME`, so the injected parameter was silently bypassed; the tell was that the test had to mutate global env to cover it | Treat "the test must mutate global state" as evidence the code under test is not actually isolated | 90% |
| Let `--importer ""` fall through to a lower tier via a truthiness check | Precedence defect, reached commit `0dbf3069d` | `if explicit:` conflates "flag absent" (`None`) with "flag given, value blank" (`""`); the env tier's documented blank-is-unset rule was applied to the argument tier where it does not belong | Distinguish `None` from empty for any option whose absence and blankness mean different things | 88% |
| Covered tilde expansion only with single-separator forms, so a doubled separator silently dropped home | Resolution defect, reached commit `42c8e8aed` | `Path.__truediv__` discards its left operand when the right side is rooted, so `home / "/importer.ts"` is not under home at all. My tilde cases were all the shapes that happen to work, which is what a hand-picked input set tends to be | Parametrize a path-joining test over degenerate separator forms (repeated, mixed, separator-only) rather than one canonical form | 88% |
| Fixed that by treating a backslash as a separator on every platform | Regression on the fix, reached commit `10b1fa2c1`, corrected in `2a22727c2` | A backslash is a separator only where the platform says so. `os.altsep` is `None` on POSIX and a backslash is a legal filename character there, so the fix rewrote a legitimate file name into a different path. I reasoned about POSIX behavior instead of asking the runtime, and wrote a test that asserted the wrong contract, which then held the bug in place for two rounds | Ask the standard library what the platform does (`os.sep`, `os.altsep`) instead of encoding a belief about it, and pin the derivation itself so a hardcoded answer fails | 90% |
| Then fixed THAT by stripping separators, which still left the suffix anchorable | Second regression on the same fix, reached commit `10b1fa2c1`, corrected in `d21631e3d` | Stripping separators does not make a suffix relative on Windows, where a drive anchors independently: `~/D:/x` leaves `D:/x` and joining it onto home yields `D:\x`, dropping home exactly as the rooted case did. Three consecutive rounds found a real bug in one nine-line function, each in my fix for the previous, because each fix addressed the instance in front of me rather than the invariant the function owes: an expanded `~` must not silently discard the injected `home`. That is narrower than containment, which this function does not provide and is not meant to: `..` still escapes and absolute paths pass through by design | Fix the invariant, not the instance. When a helper exists to guarantee a property, enumerate the mechanisms that can violate it (rooted, drive-anchored, drive-relative) instead of patching the one that was reported | 92% |
| Wrote an exit-code contract into the module docstring without ever invoking the CLI | False documented contract, shipped from commit `176e68873` through `2a22727c2` | The docstring claimed two exit states. `argparse` raises `SystemExit(2)` for a malformed command line and `sys.exit(main())` propagates it, so a third state existed the whole time. The prose was written from the function body I had authored, never from a run; three lines of probing would have shown it | Derive a documented CLI contract from actual invocations, including the failure argv a user will type by accident, not from reading the handler you wrote | 90% |
| Wrote default-path tests whose fixture derived its expected value from the function under test | Vacuous coverage, reached commit `aca98fa30` | Fixture and assertion shared one derivation, so the tests restated the code rather than constraining it. Proof: relocating the default to a wrong marketplace failed 0 tests before the fix and 4 after | Pin the expected value as an independent literal in the test module whenever the test guards a constant the code also computes | 92% |
| Narrowed to `except OSError`, leaving `UnicodeDecodeError` from locale-dependent pipe decoding unhandled | Latent crash, reached commit `176e68873` | Narrowing the catch was correct, but the decode was never pinned; `subprocess-encoding` only scans `scripts/`, so `.claude-mem/scripts/` is outside the gate that would have caught it | Pin `encoding="utf-8", errors="replace"` whenever narrowing a subprocess catch, per the repo convention | 85% |
| Asserted "Claude-Mem has no Copilot CLI equivalent" in four places | False external claim, reached commit `0dbf3069d` | Reasoned from the absence of a Copilot importer path to the absence of any Copilot integration; never checked upstream | Verify an external absence claim against the upstream source before writing it, per `.claude/rules/knowledge-persistence.md` MUST-NOT-4 | 92% |
| Recorded an FM-11 divergence note instead of proposing a class | Governance gap, reached commit `0dbf3069d` | `.claude/rules/retros.md` MUST-2 requires a proposal when no class matches; the divergence note was the stretch the rule forbids | When a classification needs a divergence note to fit, that is the signal to propose, not to annotate | 88% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Nearly invented a Copilot CLI default plugin path beside the Claude one | Checked upstream: Copilot's integration is MCP-only and exposes no default bulk-importer path, so there was nothing to point at. Shipped one real default plus an override seam instead | A "harness detection" that points at a path you cannot verify is a fabricated claim shipped as code |
| Nearly treated `CLAUDE_MEM_IMPORTER=""` as a configured path | `.strip()` plus a parametrized empty/whitespace test | `VAR=""` is the shell idiom for disabling an inherited value; treating it as configured turns a disable into exit 1 |
| The `is_configured` escape would have made the race unfalsifiable | Cold self-review before the bot review; Copilot independently reported the same defect against the older SHA | Tests that lean on the same invariant as the code cannot detect that invariant breaking |

## Phase 3: Decisions

### Action Classification

| Action | Type | Rationale |
|---|---|---|
| Split the exit-code contract on `is_configured` | Add | The acceptance criteria name it and it is the crux of the issue |
| Replace the vacuous test with a suite pinning both contract directions | Modify | The gate gap that let the defect ship; count lives in the PR body only |
| Narrow `except Exception` to `except OSError` | Modify | On the block being extracted; FM-10 shape |
| Register modules in `sys.modules` in the test loader | Add | Without it the test file does not collect |
| Cite and quote the canonical source in the governance doc | Add | `.agents/governance/**` is bound by `.claude/rules/canonical-source-mirror.md` |
| Split `MEMORY-MANAGEMENT.md` at the 500-line advisory | Drop | Already firing at 506 lines before this change; splitting a governance document is its own change |
| Invent a Copilot default importer path | Drop | The plugin does integrate with Copilot CLI, but only as an MCP installer, so no default bulk-importer path exists to point at |

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
- Read `.claude/rules/<language>.md` before running any language tooling the
  task did not name. I ran the Python formatter for five rounds because it was
  installed and I assumed formatting was house style. The rule file forbids it
  in one bolded line. A tool being available is not evidence the repo wants it
  run, and an unread rule file is the cheapest possible thing to have checked.

### Delta Triage

#### Actionable Items Identified

Per `.claude/rules/retros.md` MUST-4, every item below carries an owner or a
tracking reference. "Skip" is a decision with a stated reason, not a deferral
without an owner.

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| No FAILURE-MODES class covers a hand-authored cross-harness runtime-contract defect (FM-11's generator premise fails) | Governance | P3 | Issue | Issue #5461, owner: repository maintainer (ADR authoring is Ask First per `AGENTS.md`) |
| No gate detects an assertion accepting a function's full return range | Tool Gap | P2 | Issue | Issue #5461, "Notes" section, owner: repository maintainer |
| `.agents/governance/MEMORY-MANAGEMENT.md` exceeds the 500-line taste-lint advisory (506 lines before this change, larger after the mandated verbatim quotes) | Process | P3 | Skip | Owner: none required. Advisory only, pre-existing on `main`, and enlarged by `.claude/rules/canonical-source-mirror.md`, which is binding where the size lint is advisory. Splitting is out of scope for a bug fix. |
| Validate PR reads any backtick-quoted `*.py` token in `## Changes` as a changed-file claim, including stdlib references | Tool Gap | P3 | Skip | Owner: none required. Known false-positive class; worked around by rewording in this PR, and the workaround is recorded under Delta Change. |
| The `subprocess-encoding` lefthook job scans only `scripts/`, so `.claude-mem/scripts/` never gets the `errors="replace"` check that Copilot review had to catch by hand | Tool Gap | P2 | Flagged for maintainer | Raised on the PR #5459 review thread for the encoding finding, owner: repository maintainer. Not filed as an issue unilaterally, since widening a lefthook scan surfaces pre-existing debt across an unknown blast radius and that call belongs to whoever owns the ratchet. |

#### Issues Created

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| #5461 | docs(governance): FAILURE-MODES has no class for a hand-authored cross-harness runtime-contract defect | P3 | documentation, area-infrastructure, priority:P3 |

#### Backlog Items Stored

| Item | Priority | Memory File |
|------|----------|-------------|
| Vacuous-assertion detection (Learning 1) | P2 | Not stored to memory; carried on issue #5461 instead, so it has a tracked owner rather than an unindexed memory entry |

#### Skipped Items

| Item | Reason |
|------|--------|
| Splitting `MEMORY-MANAGEMENT.md` | Advisory, pre-existing on `main`, and out of scope for a bug fix |
| Formatting the other `.claude-mem/scripts/*.py` files | Not a gate and not sanctioned: `.claude/rules/python.md` forbids running the formatter or citing its check mode. The right answer was never "format them too", it was "do not run it at all", which I only learned in review |
| A Copilot CLI default importer path | Copilot's Claude-Mem integration is MCP-only and exposes no default bulk-importer path, so there is nothing to point at. The importer script does exist upstream; what is missing is an installed Copilot-side path to it |

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
