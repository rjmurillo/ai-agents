# Retrospective: guard round 19, mutation analysis found what eighteen adversarial reviews did not

**Branch**: `fix/guard-class-scope`
**PR**: [#3835](https://github.com/rjmurillo/ai-agents/pull/3835)
**Issues**: [#3925](https://github.com/rjmurillo/ai-agents/issues/3925), [#3927](https://github.com/rjmurillo/ai-agents/issues/3927)
**Status**: Open, 5 unpushed commits at the time of writing, 1 file
**Outcome**: SUCCESS with a method correction. Eighteen rounds of adversarial review were producing findings but had stopped finding a whole class of defect. Switching to mutation analysis found a false positive, an unreachable branch, and a corrupted test-tool entry in one session.

---

## Failure Mode Classification

**Primary**: FM-9, Confident-Incorrectness Recurrence.

The guard flagged `partial(run, capture_output=False)` as an unpinned-codec offender. It is not one. That call decodes nothing at all, so there is no codec to pin. The guard was confidently wrong on a shape no reviewer had submitted in eighteen rounds.

Worse, a pre-existing test asserted the wrong answer was deliberate. `test_detector_over_approximates_deliberately` carried the case with the stated reason "a pre-bound capture is recorded by name, so an off value still counts". The code did the opposite: it **dropped** the off value, and the *absence* of the record is what raised the flag. The justification described a mechanism the code did not implement.

That matches the FM-9 trigger directly: a change "asserts that it matches, mirrors, or aligns with an existing source... without quoting that source verbatim. The author models the contract from memory instead of reading it." Here the "source" was the guard's own control flow, three functions away, and the test author modeled it from memory.

It also matches the FM-9 detection signal "a guard or validator is stricter or looser than its canonical counterpart with no documented divergence." The canonical counterpart was the guard's own handling of the identical direct shape, `run(cmd, capture_output=False)`, which was correctly quiet. Two spellings of one semantic, two answers, no documented reason.

**Secondary**: FM-4, False Completion Markers.

Two verification tools reported success while their underlying artifacts did not satisfy the criteria:

1. The static anchor auditor reported "0 broken" while mutation A51's anchor pointed at the wrong function. The anchor text existed in two functions; the battery applies `replace(was, now, 1)` and silently takes the first. After a refactor the mutant's name had become a lie, and the auditor could not see it because it only checks existence, not uniqueness.
2. Mutation A59 reported `SURVIVED` for four rounds. It was not a survivor. A bulk string substitution had rewritten its new arm to equal its old arm, and a no-op mutation always survives. The signal read exactly like an uncovered branch.

FM-4's trigger fits: "Success is reported in prose instead of verified against an artifact." Both tools reported a verdict without checking the property that made the verdict meaningful.

**Reference**: [`.agents/governance/FAILURE-MODES.md`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/governance/FAILURE-MODES.md)

---

## Root cause, five whys

**Why did the guard flag a call that decodes nothing?**
Because `_capture_keywords` dropped a falsy `capture_output` instead of recording it.

**Why did dropping it cause a flag rather than silence?**
Because at the call site, `inherited is None` was read as "construction supplied nothing", which falls through to "assume capturing".

**Why did one value mean two things?**
Because the record was a set of keyword *names*. A name is present or absent. It cannot express "was read, and said off". The data structure had no room for the third state.

**Why was that not caught in eighteen review rounds?**
Because no reviewer submitted the shape. Adversarial review samples the input space; it does not enumerate the code paths. A wrong answer on an unsampled input is invisible to it by construction.

**Why did the method not change sooner?**
Because eighteen rounds kept returning real findings, so the signal looked healthy. Yield masked the blind spot. A method can be productive and still be systematically blind to one class.

---

## What changed

| Commit | What it did |
|---|---|
| [`a1ef12fc8`](https://github.com/rjmurillo/ai-agents/commit/a1ef12fc8) | Killed five battery-29 survivors with distinguishing inputs |
| [`a85bfa9a6`](https://github.com/rjmurillo/ai-agents/commit/a85bfa9a6) | Read a partial that pre-bound capture off as capturing nothing |
| [`c153e4724`](https://github.com/rjmurillo/ai-agents/commit/c153e4724) | Folded the shadow check into the one caller that reaches it |

Battery 29 fell from 15 survivors to 4. All four remaining are accounted for: A10 is proven equivalent, and A17, A30 and A35 are the deliberately pinned limits tracked in [#3893](https://github.com/rjmurillo/ai-agents/issues/3893).

---

## Impact

| Area | Severity | Effect |
|---|---|---|
| Guard correctness | Medium | One false positive class removed. Repo-wide offender diff shows 0 added and 0 removed across 59451 files, because this tree contains no instance of the affected shape. The defect was real but unexercised here. |
| Test-suite trust | High | A landed test asserted a wrong behavior was intentional, with a justification that did not describe the code. Any future reader would have treated the false positive as settled. |
| Mutation tooling trust | High | Two of the tools used to certify the guard were reporting unreliable verdicts. One survivor was fabricated by a bad edit; one anchor silently retargeted. |
| Code health | Low | One unreachable branch and one double negation removed. |
| Test tree | Medium | 162 calls decode child output with the locale codec, filed as [#3925](https://github.com/rjmurillo/ai-agents/issues/3925). Outside the guard's enforced scope, so no guard change would have caught them. |

---

## What worked

**Reading which code path a surviving mutant sits on, before writing a test for it.** A surviving mutant means one of three things: a coverage gap, a wrong answer in the code under test, or dead code. Ten of twelve were the first. Assuming all twelve were would have papered over the other two: a test would have been written to *pin the false positive in place*, and a test would have been written for a branch that cannot execute.

**Proving equivalence structurally rather than by input search.** A10 resisted several candidate inputs. The decisive move was to stop guessing and enumerate: `_unpack(None, ctx)` returns `[]` across all 11 context expression shapes and never raises, so the mutant's extra call cannot change any answer. When the mutated branch has a small enumerable domain, enumerate it.

**Choosing the sound direction when two inputs both kill a mutant.** A70 had two. One killed it but pinned a false positive as the expected answer. The other killed it in the direction where the mutant misses a genuine offender. Both are green tests. Only one is a correct test.

**Proving the blocking test wrong at runtime before touching it, then moving rather than deleting it.** The over-approximation case was moved to the quiet suite with the runtime transcript as its new justification. The history of why the shape was ever considered stays readable.

---

## What did not work

**Bulk string substitution over a mutation battery file.** The substitution matched twice and rewrote a second mutant's new arm. The `2x` in the tool output was the only visible warning and it was nearly missed. Match counts must be printed and asserted on, and line-index edits with a content assertion are safer than blind `str.replace`.

**An existence-only anchor auditor.** Checking that an anchor string still appears somewhere in the file is a weak invariant. It passes while the anchor points at a different function with the same line of code.

**Treating review yield as evidence of review coverage.** Eighteen productive rounds hid one blind spot the whole time.

---

## Remediation

| Action | Status | Owner or issue |
|---|---|---|
| Fix the `capture_output=False` false positive | Done, `a85bfa9a6` | [#3927](https://github.com/rjmurillo/ai-agents/issues/3927) |
| Move the wrong over-approximation case to the quiet suite with a runtime transcript | Done, `a85bfa9a6` | [#3927](https://github.com/rjmurillo/ai-agents/issues/3927) |
| Remove the unreachable branch | Done, `c153e4724` | [#3927](https://github.com/rjmurillo/ai-agents/issues/3927) |
| Add an identity-mutation check to the anchor auditor, verified by negative control | Done | [#3927](https://github.com/rjmurillo/ai-agents/issues/3927) |
| Sweep all 46 battery files for identity mutations | Done, 1 found and repaired | [#3927](https://github.com/rjmurillo/ai-agents/issues/3927) |
| Add a uniqueness check to the anchor auditor so an anchor matching two sites fails | Open | [#3927](https://github.com/rjmurillo/ai-agents/issues/3927) |
| Pin an explicit codec at the 162 test-tree call sites | Open | [#3925](https://github.com/rjmurillo/ai-agents/issues/3925) |
| Decide whether to widen the guard's scan root beyond `scripts/` | Open, policy call | [#3925](https://github.com/rjmurillo/ai-agents/issues/3925) |

---

## Learning

Adversarial review and mutation analysis are not redundant. They fail in opposite directions.

Review samples the **input** space. It finds shapes the code reads wrong, and it is limited by what the reviewer thinks to submit.

Mutation analysis samples the **code** space. It finds lines no test constrains, which is a direct measure of what the input sampling missed.

Running one to exhaustion does not substitute for the other. Eighteen rounds of the first were still returning real findings when the second found a defect in a single session, because "the reviews are still productive" says nothing about the paths the reviews never reach.
