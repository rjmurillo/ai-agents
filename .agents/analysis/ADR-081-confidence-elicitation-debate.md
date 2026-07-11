# ADR-081 Debate Log: Confidence Elicitation as a Calibration-Gated Experiment

Multi-agent adversarial review of the proposed metacognitive confidence-elicitation
feature (issue #3016), run 2026-07-11 before the ADR was written. This log
satisfies the ADR-033 routing-level architect-review gate and records the findings
that shaped the ADR.

## Participants

| Reviewer | Model | Role |
|----------|-------|------|
| architect | Claude | Mechanism feasibility, harness capability |
| independent-thinker | GPT-5.5 | Adversarial: circularity, ceremony, cost, corpus power |
| author grounding | Claude | Scorer/schema fact-finding |

## Consensus verdict

Do NOT ship confidence-elicitation as a blocking PreToolUse hook. Both reviewers
independently reached this. The architect found the mechanism unbuildable as
specified; the GPT-5.5 adversary's honest read was "close the hook portion
WONTFIX, allow only an offline shadow study." The feature's own justification (the
calibration gate) is not runnable with current tooling, and its ground truth is
circular. There is a simpler, higher-value adjacent intervention.

## Decisive findings

### BLOCKER 1 (architect): a PreToolUse hook cannot elicit, only check

`.claude/hooks/PreToolUse/invoke_false_completion_gate.py` reads the tool-call
stdin, scans session logs for verification patterns, and exits 0 or 2. A hook
cannot prompt the agent, inject a question, or pause and wait for an answer. The
issue's "wire confidence-elicitation into the false-completion gate" is
mechanically impossible inside the hook: the hook can only be a consumer of a
confidence list that some OTHER mechanism (a system-prompt instruction, a skill,
a Stop-boundary prompt) produced and persisted first. The draft never named the
producer, the storage format, or the location.

### BLOCKER 2 (architect + author grounding): the kill criterion is not measurable with the existing harness

`scripts/eval/_scoring_engine.py` dispatches `Assertion` objects whose
`AssertionKind` is a closed enum of `REGEX` and `VERDICT` only
(`scripts/eval/_eval_agent_types.py`), scoring one fixture's assertions against
one response. It has no concept of session-level aggregation, cross-signal
correlation, or precision/recall over a population. The session-log schema
(`.agents/schemas/session-log.schema.json`) has no confidence or reflection
field. So the issue's claim "this repo has the harness to measure it" is false:
the repo has a fixture-assertion scorer, not a metacognitive-calibration
analyzer. The kill criterion requires a new analysis script plus new data.

### CRITICAL 1 (GPT-5.5): the calibration gate is not runnable, and the corpus does not exist

`evals/` holds agent-spike fixtures (`input`, `provenance`, `assertions`, `tags`),
not session-level confidence/defect labels. A power analysis (Fisher z, alpha
.05, power .80) puts the needed labeled corpus at about 85 sessions to detect a
moderate correlation (r=.30), 194 for r=.20, and 783 for r=.10; a precision/recall
estimate within +/-10 points needs about 320 labeled sessions if a quarter carry
real defects. That is a hand-labeled research corpus, not a gate that runs in a
short window. The gate as written is an unbounded research project in gate
clothing.

### CRITICAL 2 (GPT-5.5): the ground truth is circular

The draft correctly names generator self-report as a closed-loop risk, then
proposes measuring it against "defects the critic caught." The critic is another
LLM. Correlating one LLM's self-report against another LLM's judgment measures
LLM-to-LLM agreement, not defect prediction, and is the same anti-pattern the
draft claims to avoid
(`.serena/memories/feedback-self-referential-test-anti-pattern.md`). The existing
gate uses EXTERNAL evidence (test/build/PR-check patterns,
`invoke_false_completion_gate.py`). Critic findings may nominate candidate labels
but cannot be the labels; calibration must use failing tests, CI failures, or
human adjudication.

### HIGH 3 (GPT-5.5): likely ceremony even if calibration passes

The existing gate already blocks completion claims without external evidence.
Adding a self-report list at the same boundary can degrade to theater: the agent
lists vague unknowns, marks them accepted-risk (which the draft permits), and the
test/build gate still does the real work. The only defensible metric is
INCREMENTAL: defects the confidence list catches that the existing gate, tests,
and PR checks missed. If shadow mode shows no incremental catches, close WONTFIX.

### HIGH 4 (GPT-5.5): LLM-in-hook violates the local budget

The false-completion gate is local Python with a 5-second timeout
(`.claude/settings.json`) and an internal 4-second git deadline. Eliciting a
confidence list at completion time implies model calls inside the blocking path
(an estimated 4 to 8 extra LLM calls and 20k to 120k extra tokens per session).
Never call an LLM inside a PreToolUse blocking path. Any elicitation must run at
the Stop or PR boundary, not in the gate.

### WARNING (architect): "routing, never a verdict" contradicts blocking

If the hook blocks (exit 2) when unresolved items exist, the list IS a de-facto
verdict. The claim only holds if the hook warns (exit 0 plus routes to the
silent-failure-hunter) or if "logged as accepted-risk" trivially clears it (which
invites the ceremony failure mode). The ADR must own block-vs-warn semantics.

### MEDIUM (GPT-5.5): a simpler intervention has better evidence alignment

The current gate accepts verification found anywhere in today's logs; it does not
prove verification happened AFTER the last code-changing edit. A stronger, simpler
change hardens that: require test/build evidence after the last code edit, block
if a failure appears after the last passing evidence, and surface recent failed
commands in the block message. This uses external evidence already present, with
no LLM self-report, no critic-as-truth, and no hand-labeled corpus.

## Outcome adopted in the ADR

The ADR rejects shipping a blocking confidence-elicitation hook. It reframes the
requester's intent (measure whether the technique earns its place) into a
buildable form and presents the simpler alternative for the owner to choose,
under User Sovereignty (the owner filed #3016; the ADR recommends, the owner
decides):

1. If confidence elicitation is pursued, run it as an OFFLINE SHADOW STUDY at the
   Stop or PR boundary (never in the blocking gate), logging confidence lists to a
   study corpus, measuring INCREMENTAL defect prediction against EXTERNAL labels
   only (failing tests, CI, human adjudication; critic findings nominate, never
   label), over a power-justified corpus (100 to 320 labeled sessions) with a
   fixed effect threshold and a 30-day hard stop. Ship a mechanism only on a
   passing incremental-value result.
2. The recommended alternative is to harden the existing false-completion gate
   (evidence-after-last-edit, block-on-post-evidence-failure), which delivers
   external-evidence value now without any of the above risks.
3. Do not close #3016 unilaterally; the owner chooses between the shadow study,
   the gate hardening, or WONTFIX.
