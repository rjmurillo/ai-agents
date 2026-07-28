# Retrospective: the test was enforcing the bug

Session 3607. Issue #3607. Branch `fix/agent-context-self-report`.

## Failure mode classification

Primary: Failure Mode #9, Confident-Incorrectness Recurrence (`.agents/governance/FAILURE-MODES.md`). The listed "most damaging variant" is shipping a guard meant to prevent a failure mode while exhibiting that same failure mode in the act of shipping it. `tests/test_context_budget_management.py` was written to hold the context-budget guidance in place across twelve agent copies. It held the defect in place instead: `REQUIRED_PHRASES` asserted that `"pressure signals"` must appear in every copy.

Secondary: Failure Mode #4, False Completion Markers. The suite was green for the entire life of the defect. Green reported "this text is verified" when what it verified was the bug's presence.

## What the work was

Two agent prompts told the model to watch its own output for "pressure signals," conclude from them that it was "near the limit," and checkpoint or hand the remaining work to a fresh session. The model cannot observe its context window. Every one of those triggers fires on a premise the model invents.

## What went right

**Two families, not two runs of one.** The standing requirement is adversarial review on a different model family, escalating for riskier changes. This change edits the prompt of the agent that writes code and the agent that routes work, so it went to two reviewers on two families. They converged, independently, on the same three defects in my first draft. Convergence across families is worth more than the same reviewer twice: a single family shares my blind spots.

All three of their blocking findings were the same failure, wearing different clothes. I removed a self-assessment trigger from the top of the section and reintroduced it three paragraphs later in "larger than one session should carry," in "the synthesis you can stand behind," and in "if you cannot complete the full task." I had been editing the sentence I was angry at rather than the property I wanted gone.

**The predicate already existed.** My first instinct was to invent an objective replacement for "the budget is nearly spent." Grepping `[NEEDS_DECOMPOSITION]` across the agent templates showed three sibling agents already gate it on countable thresholds, and the implementer itself already carried "XL complexity, touches more than 5 files" with the context clause merely appended to it. The fix was a deletion, not an invention. That grep also surfaced a third contaminated site I would otherwise have shipped past.

**Checking for a wiki-internal conflict before shipping.** The whole change rests on one wiki note forbidding self-report. A second wiki note is titled `Context Budget Management for AI Agents` and is the source the section was built from. If it had prescribed self-detection, I would have been shipping one note's position over another's without saying so. It does not: it puts enforcement in hooks and the session log. Reading it converted an assumption into a checked fact and made the finding stronger, because the agent text had drifted from its own cited source.

## What went wrong, and the learning

**1. I nearly shipped a change that its own regression test forbade.**

`tests/test_context_budget_management.py` asserted `"pressure signals"` must appear in all twelve agent copies. The test existed to stop someone silently dropping the guidance. It also, therefore, pinned the defect in place. I found it by grepping for the section heading before editing, not by running the suite after. Had I edited only the templates and pushed, CI would have failed on twelve parametrized cases and I would have learned it from a red build.

**Learning: before changing prompt text, grep for a test that asserts on that text.** Prompt content is usually unpinned, which trains you not to look. Where the repository has bothered to pin it, that test encodes an earlier decision, and changing the text without changing the test is changing half of a contract.

**2. The corollary is worse: a passing test suite is not evidence the text is right.**

This suite was green the entire time the defect shipped. It was green because it was asserting the defect's presence. A test can only defend the contract someone wrote into it.

**Learning: when a test pins prose, read what it is pinning before you trust that it is protecting anything.**

**3. I wrote a negative test and almost trusted it unverified.**

The new `FORBIDDEN_PHRASES` guard is the part of this change that matters most, because it is the only thing preventing the framing from returning. A negative assertion passes trivially when it is looking for the wrong string. Reinserting "Any of these means you are near the limit" into the template failed exactly that test and nothing else; restoring the file returned all 49 green.

This is the third time this session that verifying an instrument changed the conclusion, after a negative control that did not match the treatment's form and a token-density constant that was assumed rather than measured.

**Learning: a guard you have not seen fail is a guard you have not tested. Mutate the input, watch it go red, restore.**

## The generalizable finding

A rule keyed to model self-report is not weak enforcement. It is anti-enforcement, because it hands the agent both the trigger and the authority the trigger unlocks.

The tell is a rule whose precondition only the agent can evaluate. "Checkpoint when you sense pressure" is that shape. "Return `[NEEDS_DECOMPOSITION]` when the task touches more than five files" is not: a reader can count the files and check the claim.

The repair is not to delete the rule. The durable half here (commit as you go, record progress, degrade with evidence) was worth keeping. The repair is to re-key the trigger to something an orchestrator or a human can check, and to require the agent to produce the evidence rather than assert the conclusion.

One detail is easy to lose in that repair. The pressure-signal list carried a real protection: do not re-delegate a task already routed. That protection was sound; only its stated cause (memory pressure) was fabricated. Deleting the list wholesale would have dropped a duplicate-work guard along with the bad reasoning, and one reviewer caught exactly that. **When removing a rule for a bad premise, check what the rule was incidentally protecting, and re-anchor it.**

## Remediation

1. Before editing prompt text, grep the test tree for a suite that asserts on that text. Prompt content is usually unpinned, which trains the habit of not looking; `tests/test_context_budget_management.py` was the counterexample and it was invisible until searched for. Owner: this session, applied.
2. Every negative assertion added to a prompt-pinning suite MUST be mutation-verified before it is trusted: reinsert the phrase it forbids, watch exactly that case go red, restore. A `FORBIDDEN_PHRASES` tuple that searches for the wrong string passes silently forever. Owner: `tests/test_context_budget_management.py`, applied via `test_section_rejects_self_reported_context_triggers`.
3. The sweep this change did not run: other rules across `templates/agents/` and `.claude/skills/` may still key a trigger to model state the model cannot observe. The tell is a precondition only the agent can evaluate. Recorded in the session log `nextSteps` and left open rather than claimed.
