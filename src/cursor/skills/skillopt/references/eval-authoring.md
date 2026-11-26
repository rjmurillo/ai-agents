# Eval authoring practices

How to write SkillOpt tasks and verifiers that measure the skill, how to lay
out each step's artifacts, and what to do with report signals. The schemas
live in `references/eval-set-format.md`. Source:
<https://agentskills.io/skill-creation/evaluating-skills>.

## Mapping from agentskills.io `evals.json`

Upstream test cases (<https://agentskills.io/skill-creation/evaluating-skills>)
map onto `eval.json` like this:

- `prompt` becomes `tasks[].prompt`.
- `expected_output` and `assertions` become the frozen `verifier`, or a
  `command` with `expect_exit` and `expect_stdout`.
- `files` become fixtures inside the bundle.

The schema differs on purpose. Upstream adds assertions after it sees the first
outputs and compares against a previous version or no skill. SkillOpt freezes
each verifier before any candidate exists, and `splits` keeps the held-out
tasks away from the author. The baseline is the incumbent.

## Writing tasks

- Vary phrasing, formality, and detail. Mix a casual prompt with a precise one.
- Include at least one edge or boundary case: malformed input, an unusual
  request, or a spot where the skill's instructions are ambiguous.
- Use realistic context: file paths, column names, personal context.
- Avoid vague prompts such as "process this data". They test nothing.
- Score the run the skill is written for. When the skill names a checker (a
  test suite, a validator, a screenshot), give the eval run that tool and let
  it iterate. A single-shot score misses the self-check loop.
- For a skill that explores a repository, codebase Q&A is a cheap family that
  tells versions apart: questions with one known answer in the files or git
  history, such as "which commit first added this rule". Derive the gold
  yourself with git before any run, and plant a trap answer, such as a
  rename or mirror commit that a shallow probe returns.

## Verifier quality

- Make each check specific and verifiable: countable ("at least 3
  recommendations") or observable ("both axes are labeled").
- Avoid vague checks ("the output is good"). A grader cannot decide them.
- Avoid brittle exact-phrase checks unless exact output is the requirement.
  `expect_stdout` is exact text, so correct output with different wording
  fails it.
- Quality with no deterministic check, such as style or tone, belongs to human
  review (see Acting on report signals below). It does not belong in the gate.

## Step directory layout (convention)

Keep each step's artifacts together so a reviewer can replay it. The scripts
do not require this layout, and the result file names stay as they are.

```text
skillopt-work/
  eval.json
  rejected.jsonl
  step-0/
    incumbent/            (or incumbent.md)
    candidate/            (or candidate.md)
    patches.json
    results/              incumbent_results.json, candidate_results.json, null_results.json
    measurements.json
    pair-gate.json        (pair-gate stdout)
    report.json           (skillopt.py report stdout)
    feedback.json
  step-1/
```

`run --out-dir` must not sit inside the bundle, so keep `results/` beside
`incumbent/` and `candidate/`, not under them.

## Acting on report signals

What to do per signal:

- `unstable` (flaky): the instruction is ambiguous. Add an example or more
  specific guidance.
- `always_passes` in both arms: the task does not measure the skill. Replace
  it.
- `never_passes`: the task or verifier is broken, or the skill lacks the
  capability. Check the verifier first.
- A time or token outlier: read that run's execution transcript.
- A gain: identify which instruction caused it.

Optional human review: a reviewer reads each output and records feedback per
task in `feedback.json`, where an empty string means the output was fine.

```json
{ "t1": "cites no source for the stdlib module", "t2": "" }
```

Only train-split feedback may reach the author or the reflection prompt. Feedback
on `sel` tasks stays with the `sel` runner, or held-out integrity is lost.
Feedback is diagnostic. The gate still decides.

Blind comparison (an LLM judge sees two outputs without knowing which is
which) may serve as a train-side diagnostic for holistic quality. Never gate
on it.
