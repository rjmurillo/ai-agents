# Skill descriptions carry a standing token cost that saturates, and `disable-model-invocation` removes it

## Question

The wiki page `AI Productivity/Procedures vs Abilities (Skill Invocation Axis).md`
claims every auto-invocable skill's `description` is "resident in the context
window at all times", so 100 abilities means 100 descriptions always loaded, and
that `disable-model-invocation: true` buys "zero standing context cost". This
repository ships 96 skills in `.claude/skills` totalling 38,893 characters of
description. Should we roll the flag out to cut context?

## Conventional answer

Yes. Descriptions are always resident, so flagging low-value skills is a
straight context saving proportional to the description bytes removed.

## First-principles position

Measure it before acting on it. The measurement says the wiki is directionally
right about the flag and wrong about the linearity.

Two facts are instrument-verified and reproducible:

1. Description cost is real but **saturates**. Going from 25 skills to 200
   skills does not increase the standing cost at all.
2. `disable-model-invocation: true` collapses the cost to roughly the length of
   the skill name. This is the largest single lever measured, worth about
   17,000 tokens at 50 skills.

A third fact refuses to fit the obvious mechanism and is recorded unresolved
below. Do not build a rollout on top of a mechanism that is not settled.

## Evidence

Instrument: Claude Code 2.1.220, `claude -p "hi" --allowed-tools "" --output-format json`,
summing `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
Model `claude-fable-5`, `num_turns=1`, single iteration, no subagent activity
(`modelUsage` carries one entry, so the top-level total is the whole prompt).

**Isolate global skills or the measurement is worthless.** With the author's real
config (264 global skills) the effect is completely masked: 0 project skills
measured 54,128 tokens and 200 project skills with 1,400-character descriptions
measured 54,504, a difference of 376. The first run of this experiment concluded
"descriptions are never loaded" on exactly that confound. Isolate with
`CLAUDE_CONFIG_DIR=<dir>`, and copy `~/.claude/.credentials.json` and
`settings.json` into that directory or auth fails silently and the runner
reports 0.

**Use unique, token-dense description text.** The first fixture used one sentence
repeated 24 times. Repetitive text tokenizes far cheaper than its character
count suggests and produced a saturation figure roughly half the real one. Every
number below uses distinct random-word descriptions, which tokenize at about
1.45 characters per token, not English's roughly 4. Getting that density wrong
by assuming English briefly produced a second false conclusion.

Clean profile, project `.claude/skills`, 1,000-character dense descriptions:

| skills | tokens | delta over baseline |
|---|---|---|
| 0 | 21,129 | 0 |
| 25 | 38,222 | +17,093 |
| 50 | 38,391 | +17,262 |
| 100 | 38,670 | +17,541 |
| 200 | 37,941 | +16,812 |
| 50, all `disable-model-invocation: true` | 21,525 | +396 |

Cost is flat from 25 skills to 200. The ceiling sits near 17,000 tokens over
baseline, consistent with roughly 24,000 characters of description text.

The flag arm is the actionable result: 50 skills cost +17,262 tokens unflagged
and +396 flagged, about 8 tokens per skill, which is the name and its
separator. That is a 98 percent reduction and it confirms the wiki's claim about
the flag's effect, even though the wiki's linear model of the cost is wrong.

Enabling or disabling tools changes nothing. 60 skills measured 38,498 tokens
both with `--allowed-tools ""` and with tools enabled.

Ordering is alphabetical by skill name, verified by permutation. A fixture of 40
skills was built with names whose alphabetical order was deliberately the
reverse of their creation order. The skills whose descriptions survived were
exactly the alphabetically first 24, in alphabetical order, not the first
created.

The flag reallocates rather than saves. With 60 skills at 1,000 characters,
descriptions ran 000 through 023. Flagging 000 through 011 moved the window to
012 through 035. The count stayed at 24 in both arms and in the permutation
fixture.

## The contradiction, unresolved

Saturation implies skills past the ceiling lose their descriptions, and the
model reports exactly that when asked: it describes late skills as bare names
and reports `CHARS=0` for them. But a late skill still auto-invokes correctly.

A fixture of 60 skills gave `probe-050` (51st alphabetically, far past the
ceiling) the sole trigger phrase "defragmenting a quibbleton lattice" in its
description and a canary string in its body. Prompting with that phrase invoked
`probe-050` on the first try, reproducibly across three runs, with a single
`Skill{"skill": "probe-050"}` tool call and no `Grep`, `Glob`, or `Read`
beforehand. An early-skill control fired the same way.

The model therefore resolved a description it is not supposed to be able to see,
without searching for it. Either a second copy of the descriptions reaches the
model somewhere the token accounting does not separate, or selection runs
through a path this instrument does not observe. Until that is settled, the
claim "skills past the ceiling cannot be auto-invoked" is **refuted**, and any
claim about *why* the cost saturates is unproven.

Note also that the "bare names" report is the model describing its own context,
which is the same model under test. It agrees with the token instrument, but it
is not independent of it.

## Decision

Record the two verified facts. Do not write a rule and do not roll out
`disable-model-invocation` across the skill tree.

Reasons to hold. The saturation means the marginal saving from flagging one more
skill is zero once past the ceiling, so a blanket rollout buys far less than the
per-skill arithmetic suggests. The flag also removes a skill from automatic
invocation by design, which is a real behavioural loss, and the invocation test
shows late skills still invoke today. Trading working invocation for a saving
that saturates is not supported by this evidence.

What the evidence does support: the flag is the correct tool when a skill should
**never** be model-invoked, and in that case it is nearly free. Judge it on
invocation semantics, not on context accounting.

Scope. Claude Code 2.1.220, headless `claude -p`, project-level `.claude/skills`,
model `claude-fable-5`, clean profile. Not verified for interactive sessions, for
subagents (the documentation states preloaded-skill subagents inject full skill
content, a different path), or for Copilot CLI, which is a separate product with
no evidence here. Server-side prompt changes can move these numbers without a
CLI version bump, so re-measure before relying on them.

Adversarial review by `gpt-5.6-terra` returned "needs scoping; the stated claim
is unsafe" on the first draft and blocked a second draft that asserted the
invocation consequence. Both blocks were correct. The order permutation, the
flag arm, and the invocation test were all run because that review demanded
them, and the invocation test overturned the conclusion.
