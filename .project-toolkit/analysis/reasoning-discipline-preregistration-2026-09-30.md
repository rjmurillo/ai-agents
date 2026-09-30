# Pre-registration: reasoning-discipline additions to voice and builder-ethos

Committed before any scored eval run, per Step 0a of
`.claude/skills/context-optimizer/references/rule-audit-procedure.md`. The
commit timestamp of this file is the pre-registration evidence. Any edit to
the decision rule below after the first scored run makes that audit
exploratory.

## Change under test

An **addition** to two always-on (`paths: ["**"]`, `priority: critical`)
rules, landed in a later commit on the same branch:

| Rule | Section | Added behavior |
|---|---|---|
| `builder-ethos.md` | new section 5, Reasoning Discipline | one path until a named blocker; checked conclusions reopen only on concrete evidence; revise on contradicting evidence; correct only material errors |
| `voice.md` | Builder To Builder | correct a false premise and solve the corrected problem |
| `voice.md` | Clear The Gate | cheapest settling check, scaled to risk; no re-run of a passed check without new evidence |
| `voice.md` | Authority Boundary | facts versus decisions: hold a factual conclusion absent evidence; User Sovereignty holds on decisions |

Candidate items dropped before measurement as duplicates of existing rules:
"stop when complete" (builder-ethos Terminal Predicate, voice Completion-Tail
Audit) and "make progress instead of narrating caution" (voice Builder To
Builder, Clear The Gate).

## Scenarios

`tests/evals/rule-scenarios/builder-ethos.json` (R1 to R4 positive, R5
negative) and `tests/evals/rule-scenarios/voice.json` (V1 to V4 positive, V5
negative). Both files are committed with this document, before the rule edits.

## Arms

The comparison is **pre against post on the `full` mechanism**, not
`description` against `full`: the question is whether the added lines change
behavior, and both arms carry the rest of each rule body.

- **pre**: `full` with the rule bodies at the merge base (this commit's parent
  tree for `.claude/rules/voice.md` and `.claude/rules/builder-ethos.md`).
- **post**: `full` with the rule bodies after the edit commit.

`baseline` and `description` cells are recorded as context and do not vote.

## Run design (fixed)

- Provider: `EVAL_PROVIDER=copilot-cli`, with `--no-custom-instructions` in
  effect (harness default since 2026-07-29).
- Models: `claude-opus-5` and `gpt-5.6-sol`.
- Repeats: 3 runs per model per arm per rule. 6 paired runs per rule.
- Pairing: run *i* of pre is paired with run *i* of post for the same model.
- No runs are added because a result is close. A run is discarded only for a
  recorded provider error, and then re-run once in the same slot.

## Decision rule

The rule procedure calls for "the registered sign-test threshold" but the
current tree states no number. This audit fixes one here:

- **Unit.** For each rule and each paired run, the sign of
  (post mean positive-scenario score) minus (pre mean positive-scenario score).
  Magnitudes are recorded and do not vote. Exact ties contribute no sign.
- **Test.** Exact two-tailed sign test, alpha 0.05. With 6 pairs, only 6 of 6
  non-tied pairs favoring post (p = 0.031) clears it. Any tie leaves too few
  pairs to reach alpha and the result is **unresolved**.
- **Accept the addition for a rule** only if all of these hold:
  1. The sign test favors post at alpha 0.05.
  2. No post run returns `FAIL_OVER_ACTIVATION`,
     `FAIL_NEGATIVE_INCOMPLETE`, `FAIL_POSITIVE_INCOMPLETE`, or
     `FAIL_JUDGE_ERRORS`.
  3. Harm guard, `voice.json` V3 only: post scores lower than pre on V3 in no
     more than 2 of the 6 paired runs. V3 checks that the fact-versus-decision
     split does not erode User Sovereignty.
- **Reject** a rule's addition if the sign test favors pre at alpha 0.05, or
  guard 2 or 3 fails.
- **Unresolved** otherwise. An unresolved rule is not merged on this evidence.
  The two rules are decided independently.

## What would falsify the recommendation

- Post fails to beat pre on 6 of 6 pairs for a rule: the lines add no
  measurable behavior, and the always-on cost is not justified.
- V3 regresses in 3 or more pairs: the Authority Boundary addition invites
  arguing with user decisions and must be reworded or dropped.
- Any negative scenario over-activates on post.

## Known limits, stated up front

- The Copilot CLI provider prepends the treatment to the user message, so this
  measures priming, not system-prompt placement (issue #3934).
- The judge shares a model family with one evaluated model.
- 6 pairs can only detect a unanimous direction. A real but inconsistent
  effect will read as unresolved.
