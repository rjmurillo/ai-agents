---
name: decision-question
description: Ask the user to choose only when blocked on a decision they own, with the smallest complete decision brief. Use when you say `ask the user to choose`, `do I need a user decision here`, or `present a decision brief`. Do NOT use to review a decision already made (use decision-critic) or to surface project risks (use pre-mortem).
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - user-decision-elicitation
    status: active
  routing:
    role: conditional-adjunct
    invoker: autoplan
    trigger: autoplan's confusion protocol finds a material decision only the user can make
    user-facing: false
---

# Decision Question

> Ask only when a real user decision is required. When asking, present the
> smallest complete decision brief that lets the user choose deliberately.

Questions spend user attention. Spend it only on decisions the user owns, and
make each question decision-complete. This skill owns how to ask. It does not
own whether a mutation is authorized (#5407) or whether a task is finished
(#5404).

`voice.md` routes here and does not carry the protocol. Load the reference and
script only when the routing gate says ask.

## Triggers

`ask the user to choose between these paths`, `do I need a user decision here`,
`present a decision brief`, `which option should the user pick`

## Routing gate: when NOT to ask

Multiple implementation choices do not make a user decision. Do not ask when any
of these holds:

- the user delegated the choice (`choose the best option and implement it`);
- repository or safety policy mandates one option;
- existing acceptance criteria already determine the choice;
- the distinction is an implementation detail within authorized scope, and
  reversible;
- reading available evidence or tools resolves the uncertainty;
- the task is terminal under #5404 and the question would only solicit optional
  follow-up. The STOP TOKEN wins.

```text
no unresolved user decision      -> act within existing authorization
material unresolved user decision -> build the brief below
```

## Process

All commands run `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/decision-question/scripts/decision_question.py`
with `python3`. Output is one JSON object.

1. **Route.** Apply the gate. If no question is warranted, act and stop.
2. **Draft the brief** for the earliest load-bearing decision (fields below).
3. **Check and plan.** Write the brief as JSON and run:

   ```bash
   python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/decision-question/scripts/decision_question.py" --brief <brief.json>
   ```

   `status: incomplete` (exit 2) lists the missing fields. Enrich the brief and
   rerun. `status: revise_recommendation` (exit 2) means an earlier answer
   filtered out the recommended option: pick a remaining option or set
   `no_recommendation`, then rerun. `status: ask` lists the prompt `pages` and
   the `page` to present now.
4. **Ask, then prune.** Present the decision with `AskUserQuestion`. Record the
   answer under `answers` and rerun. When the user picks `_more`, add one to
   that decision's count under `paging` and rerun; the same decision returns
   its next page. Decisions that depend on an answer are pruned or filtered from
   that answer, and unresolved IDs are never renumbered.
5. **Weak evidence on an irreversible choice.** `pre_ask_review` in the output
   names `decision-critic` and `pre-mortem`. Run one before asking.

## Scripts

### decision_question.py

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/decision-question/scripts/decision_question.py" --brief <brief.json> [--max-options N]
```

Reads one decision, or `{context, decisions, answers, paging}`. Routes, then validates
and plans the next actionable decision. `--max-options` overrides the pinned
per-prompt bound for a harness that reports a different cap (minimum 3).

**Exit codes**:

- `0`: routing resolved. No question warranted (`skip`), a complete bounded
  brief (`ask`), every open decision held (`held`), or nothing left (`resolved`).
- `1`: unreadable or malformed brief JSON, an answer that is not one of the
  decision's options, a duplicate decision ID, an out-of-range `paging` count, or a cap below 3.
- `2`: a question is warranted but the brief is not decision-complete
  (`incomplete`, with the missing fields listed), or an earlier answer removed
  the recommended option (`revise_recommendation`).

## Decision brief contract

Each decision carries a stable ID (`D1`, `D2`), a one-sentence statement of what
must be decided now, why it matters now, at least two materially distinct options
(presented 2 to 4 per page; overflow becomes a split chain) with their consequences, a recommendation with its load-bearing reason (or an
explicit statement that evidence supports none), and `Hold` only when deferring
is legitimate and a reopen condition exists. Render with the harness
`AskUserQuestion` tool (`voice.md` defines the term); do not invent a new UI
contract.

Field rules, option construction, split chains, Hold, and the completeness
check: [decision-brief-protocol.md](references/decision-brief-protocol.md).

## Harness bound

`decision_question.py` pins what the Claude Code `AskUserQuestion` schema accepts:
1 to 4 questions per call, 2 to 4 options per question, and a free-text `Other`
the tool adds itself. `Hold` and the continuation entry each take a presented
slot. Options beyond the bound split into ordered pages. Another harness with a
different cap: pass the observed value as `--max-options`.

## Relationship to existing capabilities

- `decision-rigor` (a `review` reference) stays a PR review axis. This skill
  reuses its concepts (assumptions, distinct alternatives, reversibility,
  failure modes) and none of its verdict schema, `CONTEXT_MODE`, or JSON output.
- `decision-critic` and `pre-mortem` are optional steps for high-impact
  decisions, not steps for every question.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Asking when the user delegated the choice | Spends attention the user already gave away | Act within authorization |
| More options than the harness shows | The user cannot see or pick the overflow | Split into a deterministic chain |
| Asking D2 before D1 is answered | D1's answer may make D2 moot | Ask D1, then prune D2 |
| `Hold` with no reopen condition | The decision silently disappears | State the event that reopens it |
| Omitting a recommendation the evidence supports | Pushes the cost back to the user | Recommend and give the reason |
| Fabricating a recommendation | Invents confidence the evidence lacks | Say evidence supports no preference |

## Verification

- [ ] The routing gate ran. A delegated, policy-mandated, criteria-determined,
      detail-level, evidence-resolvable, or terminal case emitted no question
      (`status: skip`, exit 0).
- [ ] The presented decision is complete (`status: ask`, exit 0).
- [ ] No page exceeds the bound; over-bound briefs report `split: true`.
- [ ] Dependent decisions were pruned or filtered from the recorded answers.
- [ ] A held decision keeps its ID and states its reopen condition.
