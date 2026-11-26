# Judge grading discipline

How a model must grade an output or a transcript when no deterministic
verifier can. It covers the burden of proof, the evidence a verdict needs, and
how to critique the eval itself. The schemas live in
`references/eval-set-format.md`.

## Scope

This applies whenever a model, not a deterministic verifier, judges an output
or a transcript. Examples are a blind comparison and a reviewer pass over
train-split outputs.

It never changes the SkillOpt rule. A judge is a train-side diagnostic. It is
never a gate. The gate still decides (see `references/eval-authoring.md`).

## Burden of proof

The burden of proof sits on the assertion. When you are uncertain, the
assertion fails. Give no partial credit. Apply one standard to every assertion
in a run.

## Pass and fail criteria

Pass only with cited evidence that the task was really done. A file that
exists and holds the right content passes. A file that merely exists does not.

Fail the assertion in each of these cases:

- No evidence for it exists.
- The evidence contradicts it.
- The available outputs cannot show it either way.
- The output complies on the surface only, such as the right filename with
  wrong or empty content.
- The output meets it by coincidence, not because the skill did the work.

An unverifiable assertion is a fail, not a skip. This matches the
`"UNVERIFIED"` handling in `references/rollout-validity.md`.

## Inspect the outputs

Open the persisted outputs and read them. Do not stop at the transcript. A
transcript line that claims a result is a claim, not evidence.

Say a runner writes "filled all 12 fields". Count the filled fields in the
output file. If the output is not plain text, use a tool that can read it.

## Cite evidence for every verdict

Every verdict carries its evidence, in one of two forms: a quote of the exact
text, or a precise description of what you found and where. For a fail, say
what was missing or wrong.

## Extract implicit claims

Listed assertions miss things. Read the outputs for claims nobody listed, and
verify each one. Sort them into three kinds:

- **Factual:** a statement you can check against the outputs, such as "the
  form has 12 fields".
- **Process:** a statement about how the work was done, such as "used the
  bundled script". Check it against the transcript.
- **Quality:** a judgment, such as "all fields were filled correctly". Decide
  whether the output justifies it.

Flag every claim you cannot verify from what is available.

## Critique the eval

After grading, ask whether the eval is weak. Name a gap only in these cases:

- An assertion that a clearly wrong output would also pass.
- An important outcome you observed that no assertion covers.
- An assertion that cannot be verified from the available outputs.

Keep the bar high. Raise a point only if the eval author would call it a good
catch. Do not nitpick. Say "no gaps found" when that is true.

## Act on the findings

Judge findings feed the eval, not the gate. Map each one to an existing
mechanism:

- A weak assertion becomes a rewritten deterministic verifier. Follow
  `references/eval-authoring.md` for what a specific check looks like.
- An uncovered outcome becomes a new task or verifier on the train split.
- Per-task judge feedback follows the train-only feedback rule. Only
  train-split feedback may reach the author or the reflection prompt. Feedback
  on `sel` tasks stays with the `sel` runner.

## Source

This reference is adapted from the Anthropic `claude-plugins-official`
`skill-creator` plugin, file
`plugins/skill-creator/skills/skill-creator/agents/grader.md`, at commit
0fbfda5a91f4adc311daca25acc99132f40f0b6e (2026-11-25), under Apache-2.0. It is
a distillation in this repository's own words, not a copy.
