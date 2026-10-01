# Review-conversation protocol

Canonical contract owned by the `pr-comment-responder` skill (capability
`review-conversation`). Every role that writes or answers a review comment
applies this file instead of stating its own copy: human and AI reviewers,
PR authors, responders, and specialist review agents. A consumer keeps a
one-line invariant only; this file is the one place the doctrine lives.

Boundaries: reviewer and author culture (goodwill, reply time, approve once
code health improves) lives in the `code-review-norms` governance file.
Whether a finding is technically valid belongs to the `review`
skill's technical-review contract. This protocol owns how a validated finding
and its answer are worded, tracked, and escalated. Prose style, banned words,
and dash rules stay in the repository voice rule; this file does not restate
them. Design input only, no runtime dependency: Google eng-practices on
review comments and pushback.

## Invariants for every participant

1. **Address code and evidence, not people.** Name the code, claim, or
   decision and its consequence. Do not speculate about competence, motive,
   diligence, or attitude. No sarcasm, humiliation, or retaliation.
2. **Read the thread first.** Answer the claim actually made, not a weaker
   version of it. If the other side is right, say so and change position.
3. **Evidence outranks role.** Reviewer status, author proximity, human
   identity, and AI confidence are not evidence. Order of weight: observable
   correctness or measurement, then explicit repository rule, then local
   convention, then general principle, then preference.
4. **Correct the record.** When evidence changes, the reviewer withdraws or
   downgrades the finding and the author accepts it. Split a partly correct
   finding into the supported and unsupported parts. Correct a materially
   wrong earlier statement visibly, never by silent pivot.
5. **One evolving record.** Resolved findings stay resolved without new
   contradicting evidence. A new agent or context reads the thread and the
   round count before acting and does not reset either.

## Publishing a finding

The publisher renders a validated finding. It never changes the finding's
technical severity.

Dispositions and their comment prefixes come from
`code-review-norms`, the repository's review-culture authority; this protocol extends it and does not restate it. In this file
`BLOCKING` means no prefix (must address before merge), `OPTIONAL` means
`Optional:`, `NIT` means `Nit:`, and `FYI` means `FYI:`. Only `BLOCKING`
gates merge.

- Render the disposition the finding carries. Do not promote a nit to
  `BLOCKING` or demote `BLOCKING` to `NIT` or `FYI`.
- A non-obvious finding states the problem, why it matters (consequence,
  invariant, or code-health cost), and evidence (caller, test, rule,
  measurement, location). A one-line nit needs no labels.
- Own the problem, not the full fix. Give a fix direction when it is clear
  and low risk. When several fixes are equivalent, state the constraint and
  let the author choose. Do not prescribe exact code because you can write it.
- Rationale that future readers also need goes into code structure, a durable
  comment, a test, a contract, or an ADR. Never leave it only in the thread.
- Praise and teaching notes are `FYI`, bounded to one line, never blocking.
- Hostile or author-directed wording is rewritten to describe the code, or
  suppressed. The finding survives; the wording does not.

## Answering a finding (author and responder)

An AI author is neither a compliance bot nor a defense lawyer. For each
finding: understand the claim, verify it against code, tests, and contracts,
then pick one outcome.

| Verdict | Response |
|---------|----------|
| Correct | Accept, fix in scope or name the concrete blocker. No defensive filler. |
| Partly correct | Accept the supported part first. Bound the rest with evidence. |
| Incorrect | Push back: show you understood the concern, cite code, test, contract, history, or measurement, state the consequence, stay concise. Do not degrade the code to appease. |
| Not enough evidence | Investigate or escalate. Do not bluff. |

Escalate only a material disagreement that survives one evidence-rich reply.

## Debt and deferral

- Debt this PR introduces is fixed before merge.
- Existing debt the PR makes unsafe or materially worse is addressed now.
- Other existing debt is tracked separately and does not widen the PR.
- A promise to "clean up later" in a thread is not tracking. A deferral
  needs a filed issue or the repository's TODO convention, referenced as
  `Refs #<issue>`.

## Mixed human and AI threads

- Keep attribution on every finding and reply. Never impersonate a human.
- Do not infer consensus from silence or from another agent's conclusion.
- Verify human comments with the same bar as AI comments.
- Reconcile conflicting conclusions with evidence. If evidence does not
  settle it, escalate to the owner.
- Stay neutral and technical when a human comment is hostile. Do not mirror
  it. Escalate interpersonal conflict instead of prolonging it.

## Exemplary AI standard

AI participants go beyond the human minimum. Do not use loaded wording.
Do not fabricate certainty, sources, test results, prior decisions, or
consensus. Mark uncertainty and investigate before asserting. Deduplicate
repeated findings and replies, and prefer one evidence-rich reply over
several argumentative ones. Never use comment volume or repetition as
pressure.

## Bounded loops and handoff

- A reply cycle with no new evidence ends in escalation to the owner, not a
  third rebuttal.
- Round counts survive handoff. Read the persisted count with
  `skills/github/scripts/pr/check_pr_round_cap.py`; a new agent or
  context continues that count and never restarts it. The `review` skill's
  self-audit cap (3 rounds per invocation) binds the same way.
- A resolved thread reopens only with new contradicting evidence cited in the
  reopening comment.

## Scenario checklist

Each scenario names the section that decides it.

1. Reviewer correct: author accepts and fixes (Answering).
2. Reviewer wrong: author pushes back with evidence, code unchanged (Answering).
3. Reviewer partly correct: reply splits supported and unsupported parts (Answering).
4. Reviewer disproven: reviewer withdraws visibly (Invariant 4).
5. Author disproven: author accepts (Invariant 4).
6. Author-directed wording: rewritten or suppressed (Publishing).
7. Non-obvious blocker: states why and evidence (Publishing).
8. Optional finding never renders as `BLOCKING` (Publishing).
9. `BLOCKING` never renders as `NIT` or `FYI` (Publishing).
10. Several valid fixes: constraint-oriented comment (Publishing).
11. Complexity explained only in the thread: simplify or encode durably (Publishing).
12. Context handoff: thread state and round count preserved (Bounded loops).
13. Human and AI disagree: attribution kept, reconcile or escalate (Mixed threads).
14. Hostile human comment: AI stays neutral and technical (Mixed threads).
15. Debt introduced by the PR: not deferred (Debt).
16. Existing adjacent debt: tracked separately (Debt).
17. Repeated replies, no new evidence: escalate (Bounded loops).
18. Duplicate AI comments: deduplicated (Exemplary AI standard).
