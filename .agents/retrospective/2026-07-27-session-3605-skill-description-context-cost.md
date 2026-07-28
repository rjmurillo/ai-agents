# Three conclusions, two of them wrong: measuring what skill descriptions cost

Session 3605. Branch `docs/skill-description-context-cost`. One decision memory
shipped, no code.

- Issue: #3605
- PR: #3606
- Starting commit: `a65181a264` (branch point from main)
- Final code commit: `56f4f861aa` (`docs(memory): measure what skill descriptions actually cost in context`)
- Artifact under review: `.serena/memories/decision-skill-description-context-cost.md`

## Failure mode classification

Primary: Failure Mode #9, Confident-Incorrectness Recurrence (`.agents/governance/FAILURE-MODES.md`). The documented shape is partial signal, premature conclusion, confident delivery, multi-round correction. This session ran that loop twice before the third conclusion held. Both times the conclusion was drafted as settled and both times an adversarial reviewer on a second model family returned it.

Secondary: Failure Mode #4, False Completion Markers. The first run shipped a positive control and a negative control that both passed while the instrument was measuring nothing: 264 pre-existing global skills had already saturated the budget the experiment was trying to move. A passing control reported verification that had not occurred.

Neither instance reached `main`. Both were caught in review, which is the outcome the second-family requirement exists to produce.

## What this was

A wiki page claims every auto-invocable skill's `description` sits in the
context window at all times, and that setting `disable-model-invocation: true`
buys "zero standing context cost". This repository ships 96 skills in
`.claude/skills`. If the claim held, that is a standing cost worth acting on.

The task was to test it. The test produced three conclusions in sequence. The
first two were wrong. Both were caught, and the mechanism that caught each one
is the useful part of this write-up.

## The first wrong conclusion: a confound in the environment

The first run compared 0 project skills against 200 project skills with
1,400-character descriptions. It measured 54,128 tokens against 54,504. A
233-fold difference in description length moved the total by 376 tokens.

That looked like a clean negative result, and it had a positive control that
passed: the model listed all 50 probe skill names when asked. A behavioural
check agreed, with the model reporting it could not see the descriptions.

The conclusion drafted from it was "skill descriptions are never loaded into
context". It went out to an adversarial reviewer on a different model family.

The reviewer's sixth attack was that the author's own global skill directory
could be saturating whatever budget exists, masking any project-level effect.
That was exactly right. Re-running with `CLAUDE_CONFIG_DIR` pointed at an empty
config inverted the result: 0 skills measured 21,144 tokens and 50 skills with
1,400-character descriptions measured 29,500. The effect had been there all
along, hidden behind 264 pre-existing global skills.

The measurement was not wrong. The environment was. A control that holds the
treatment fixed and varies the environment would have caught it; every control
in the first run varied the treatment inside one environment.

## The second wrong conclusion: arithmetic on an assumed constant

The corrected fixtures used unique random-word descriptions, because the
reviewer had also flagged that the original filler was a single sentence
repeated 24 times and could not support a character-to-token conversion.

Measuring 60 skills at 1,000 characters gave 38,498 tokens against a 21,129
baseline, a delta of 17,369. Dividing that by an assumed English density of
roughly 4 characters per token gave about 290 tokens per description, which
multiplied out to all 60 descriptions being present. That refuted the
saturation the earlier cells had shown, and it refuted the model's own report
that late skills appeared as bare names.

The refutation was written up. It was wrong. Random lowercase word salad does
not tokenize like English; it tokenizes at roughly 1.45 characters per token.
At the real density, 17,369 tokens is 24 or 25 descriptions, not 60. The token
instrument and the model's report had agreed the whole time.

The tell was available and ignored: 25 skills, 50 skills, 100 skills, and 200
skills all measured within 800 tokens of each other. A flat line across an
eight-fold change in N is not consistent with "all descriptions present". The
arithmetic error survived because it produced a dramatic result, and a dramatic
result invites writing rather than checking.

## The third conclusion, and the claim that did not survive

The surviving facts are narrow. Description cost is real and saturates near
17,000 tokens above baseline. Setting `disable-model-invocation: true` on 50
skills drops the cost from +17,262 tokens to +396, about 8 tokens per skill.
Listing order is alphabetical by skill name, confirmed by building 40 skills
whose alphabetical order reversed their creation order and finding the
survivors were exactly the alphabetically first 24.

The draft went back to the reviewer, which blocked it again. Among its attacks
was that the artifact asserted description-based auto-invocation could not fire
for skills past the ceiling, and that no invocation test had been run.

So one was run. A skill 51st alphabetically, well past the ceiling, was given
the sole trigger phrase in its description and a canary in its body. It was
invoked correctly on the first try, three times, with a single `Skill` tool call
and no `Grep`, `Glob`, or `Read` beforehand.

The consequence claim was false. It was the most quotable sentence in the draft
and the reason the investigation had seemed worth doing. It is now recorded as
refuted, and the mechanism behind the saturation is recorded as unresolved
rather than guessed at.

## Learnings

1. **A control that varies only the treatment cannot detect a confounded
   environment.** The first run had a passing positive control and a passing
   negative control and was still measuring nothing, because both controls lived
   inside the same saturated environment. Vary the environment too.

2. **Name the density before dividing by it.** The second wrong conclusion was
   one assumed constant applied to text that did not obey it. Any conversion
   between characters and tokens on synthetic text needs the density measured on
   that text, not inherited from prose.

3. **A flat line across an eight-fold change in N is a finding, not noise.**
   The saturation was visible in the data before either wrong conclusion was
   written. It was skipped past twice.

4. **The most quotable sentence in a draft deserves the most hostile test.**
   "Late skills cannot auto-invoke" was the claim that would have made this
   investigation matter. It was the one claim never tested until a reviewer
   demanded it, and it was false.

5. **Adversarial review on a different model family earned its cost three
   times here.** It found the environment confound, it flagged the compressible
   filler that caused the density error, and it demanded the invocation test
   that overturned the headline. None of the three came from the author.

6. **Asking a model what it can see is not an independent instrument.** The
   model's report about bare names agreed with the token accounting, which is
   worth something, but it is the same model under test describing its own
   context. That limitation is recorded in the memory rather than resolved,
   because resolving it needs an instrument that inspects the serialized
   request.

7. **Measuring a claim is not the same as acting on it.** The measurement
   confirms the flag is nearly free. It does not follow that the flag should be
   rolled out, because the saving saturates and the flag costs automatic
   invocation. The memory records the numbers and declines the rollout.

## Remediation

1. Any context-measurement experiment MUST run at least one control that holds the treatment fixed and varies the environment, not only controls that vary the treatment inside one environment. Concretely: point `CLAUDE_CONFIG_DIR` at an empty config and re-measure the baseline before trusting any delta. Owner: this session, applied; recorded in the decision memory so the next measurement inherits it.
2. Any character-to-token conversion on synthetic text MUST measure the density on that text. Do not inherit the roughly four-characters-per-token figure from English prose; the random-word fixtures here tokenized at about 1.45. Owner: this session, applied.
3. The saturation mechanism is recorded as unresolved, not guessed. Closing it needs an instrument that inspects the serialized request rather than the reported token total. Left open rather than claimed.
4. The refuted consequence claim ("skills past the ceiling cannot auto-invoke") is recorded as refuted in the decision memory with the invocation test that killed it, so a future session cannot re-derive it from the surviving saturation numbers.
