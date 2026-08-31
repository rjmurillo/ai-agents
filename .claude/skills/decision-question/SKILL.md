---
name: decision-question
version: 1.0.0
description: >-
  Ask the user to choose only when work is genuinely blocked on their
  preference or authority, and present the smallest complete decision brief.
  Do NOT use to review a decision already made (use decision-rigor) or to
  surface project risks (use pre-mortem).
license: MIT
---

# Decision Question

Governing principle: **Ask only when a real user decision is required. When
asking, present the smallest complete decision brief that lets the user choose
deliberately.** Questions spend user attention. Spend it only on decisions the
user actually owns, and make each question decision-complete.

This skill is the canonical owner of user decision elicitation. `voice.md`
routes here; it does not embed the protocol. Load the reference and script only
when a genuine decision brief is needed.

## Triggers

Activate when agent work stalls on a choice the user owns and the routing gate
below returns "ask":

- `Ask the user to choose between these paths`
- `Do I need a user decision here`
- `Present a bounded decision brief`
- `Which option should the user pick`

## Routing gate: when NOT to ask

Do not invoke this capability merely because several implementation choices
exist. No user question is warranted when any of these holds:

- the user explicitly delegated the choice;
- one option is mandated by repository or safety policy;
- existing acceptance criteria already determine the choice;
- the distinction is an implementation detail within authorized scope;
- the agent can resolve the uncertainty by reading available evidence or tools;
- the task is already terminal (#5404 STOP TOKEN wins) and the question would
  only solicit optional follow-up.

Composition with #5407: #5407 owns whether a mutation is authorized. This skill
owns how to ask when authorization or preference is genuinely unresolved.

```text
no unresolved user decision   -> act within existing authorization
material unresolved decision  -> invoke this bounded capability
```

## Process

1. **Route.** Run the gate above. If no user question is warranted, act within
   authorization and stop.
2. **Draft the brief.** Fill the decision-brief fields for the earliest
   load-bearing decision.
3. **Check completeness.** Run the script or the checklist. Enrich until no
   field is missing.
4. **Bound and split.** Keep options within the harness limit; paginate
   deterministically when they exceed it.
5. **Ask, then prune.** Present the earliest decision. Use the answer to prune
   or recompute dependent decisions, preserving their IDs.

## Decision brief contract

Each decision carries: a stable ID (`D1`, `D2`, ...), a one-sentence statement
of what must be decided now, why it matters now (the blocking consequence or
tradeoff), bounded materially distinct options within the harness limit, a
recommendation with its load-bearing reason when evidence supports one (say so
plainly when it does not), and explicit `Hold`/`Defer` with a reopen condition
when deferring is legitimate. Render using the `AskUserQuestion` structure in
`voice.md`; do not invent a new UI contract. See
[decision-brief-protocol.md](references/decision-brief-protocol.md) for field
rules, option construction, split-chain behavior, and the completeness check.

## Harness option bound

`scripts/decision_question.py` pins `MAX_PRESENTED_OPTIONS = 4` and
`HARNESS_LIMIT_OBSERVED = False`. This environment exposes no
`AskUserQuestion`/`ask_user` tool in the agent tool schema, so the per-prompt
option cap could not be observed here. The bound is configurable: pass
`--max-options` with the value observed in a harness that does expose the tool.
When options exceed the bound, the engine splits deterministically into ordered
pages rather than overflowing one prompt.

## Scripts

### decision_question.py

```bash
python3 .claude/skills/decision-question/scripts/decision_question.py \
  --brief <brief.json> [--max-options N]
```

Reads one decision or `{decisions, context, answers}`. Routes, then validates
and plans the next actionable decision.

**Exit codes**:

- `0`: routing resolved. Either no question is warranted (`skip`/`resolved`), or
  a complete bounded brief was produced (`ask`).
- `1`: invalid arguments or unreadable/malformed brief JSON.
- `2`: a question is warranted but the brief is not decision-complete.

## Relationship to existing decision capabilities

- `decision-rigor` (`.claude/skills/review/references/decision-rigor.md`) stays a
  PR review axis. This skill reuses its concepts (explicit assumptions, distinct
  alternatives, reversibility, failure modes) but not its verdict schema,
  `CONTEXT_MODE`, or JSON output.
- `decision-critic` and `pre-mortem` are optional dependencies for irreversible,
  high-cost decisions with weak evidence, not mandatory steps for every question.

## Deferred (out of scope for this skill)

- #5396 capability-DAG wiring: consumers reference this owner manually until
  the DAG lands.
- #5391 placement conformance: artifact placement follows current conventions;
  formal conformance is #5391.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Asking when the user delegated the choice | Spends attention the user already gave away | Act within authorization |
| Presenting more options than the harness allows | Overflows the prompt so the user cannot choose | Split into a deterministic chain |
| Omitting a recommendation when evidence supports one | Pushes the decision cost back to the user | Recommend and give the load-bearing reason |
| Using `Hold` as a generic escape hatch | Leaves a required decision unresolved | Offer `Hold` only with a reopen condition |

## Verification

```bash
python3 .claude/skills/decision-question/scripts/decision_question.py \
  --brief <brief.json>; echo "exit=$?"
```

- [ ] Routing gate ran; a delegated, policy-mandated, criteria-determined,
      implementation-detail, evidence-resolvable, or terminal case emits no
      question (`status: skip`, exit 0).
- [ ] The presented decision is complete (exit 0, `status: ask`); an incomplete
      brief exits 2 and lists the missing fields.
- [ ] No prompt page exceeds the harness bound; over-limit briefs report
      `split: true`.
- [ ] Dependent decisions are pruned or recomputed after earlier answers.
