# Pre-registration: falsifiable success check, S8, third paid run for issue 6737

Owner decision D20 (2026-10-24) funded a third paid run for issue 6737 with the
falsifiable success check as the primary measure. This file fixes the measure,
the scoring rule, the sample size, the decision threshold, and the stop rule
before any response from that run exists. The merge commit of the pull request
that adds this file is the pre-registration evidence. Any edit to the rules
below after the first response of the run makes the run exploratory, and the
record must say so.

## Why this run exists

- The first run (`2026-10-23-issue-6737-spec-option-free-claude-cli.json`) used S7, which names the endpoint. Both arms made the right call 12 of 12 times. The call cannot show uplift.
- The second run (`2026-10-23-issue-6737-spec-s8-skill-routed-claude-cli.json`) used S8, which withholds the endpoint, and a skill-routed arm. Both arms chose a machine interface first, 12 of 12. The judge cell score gap was 0.139, with a 95% bootstrap interval of -0.5 to 0.722.
- A hand read of the 24 responses from the second run, done after the run and with arm labels visible, found a falsifiable success check in 6 of 12 skill-routed responses and 0 of 12 baseline responses. That read was not pre-registered, so it is a hypothesis, not a result.
- This run tests that hypothesis on new data, with the measure fixed first.

Disclosure: the rubric below was written after reading the 24 responses from the
second run. It is fitted to that data. The new responses are the test of it.
The first estimate is also likely too high, because the hand read picked the
measure after seeing which arm had it.

## What is held fixed

Same harness and scenario as the second run.

- Scenario: `tests/evals/skill-scenarios/spec.json`, id `S8`. The `input`, `expected_signals`, `expected_gate`, and `proof_points` fields must equal the `scenario` object in the second run's record. The runner hashes the whole file, and the file changed after the second run (only the `_scope_note` text), so the whole-file hash is recorded, not gated. It was `b52f14d88ce7ed99` at `origin/main` 97ea576195 on 2026-10-24 (the second run recorded `44ded3f54b83fdb5` at 735ff7ed41).
- Treatment: the `skill-routed` arm installs `src/claude/skills/spec`. Its git tree id must equal `5f94c26166fe5e4cfdab2daef34f58bdf11d08b7`, the id at both 735ff7ed41 and 97ea576195. If it differs, the run does not start.
- Runner: every file under `scripts/eval/`. The four files that decide what runs (`eval-rule-activation.py`, `_claude_skill_harness.py`, `_claude_cli.py`, `_claude_stream.py`) are unchanged between 735ff7ed41 and 97ea576195.
- Transport `claude-cli`, model `claude-sonnet-5`, judge repeats 1, judge reducer median, seed 0.
- The Claude CLI version may differ from 2.1.309 (2.1.310 on 2026-10-24). The record states the version used.
- The run starts only at a commit where `git diff --stat <merge commit of this file> HEAD -- scripts/eval src/claude/skills/spec tests/evals/skill-scenarios` is empty. The record names that commit. No such edit lands before the run ends.

Command, run from a worktree at `origin/main` after this file merges:

```bash
EVAL_PROVIDER=claude-cli CLAUDE_CLI_BIN=<capture wrapper> \
  uv run python scripts/eval/eval-rule-activation.py \
  --scenarios tests/evals/skill-scenarios/spec.json --scenario-id S8 \
  --repeats 20 --arms harness-baseline skill-routed --judge-repeats 1 \
  --model claude-sonnet-5 --seed 0 --output <results json>
```

## Primary measure

**Falsifiable success check named (FSC).** One binary value per response. The
unit is the cell, which is one response from one arm in one repeat.

A response has FSC = 1 when it states, for the proposed weekly process, at
least one condition that a person can observe to be true or false, where a
false result would show that the process failed or that its list is wrong.
Three kinds count:

- **(a) Correctness check.** Compares the automated output with an independent reference: the dashboard, the CSV export, or the manual list. The comparison is by rows, names, or counts.
- **(b) Health or completeness check.** A stated test on the output or the job, such as a row count, a non-empty list, an HTTP status, or a failure alert, where a failed test is stated to stop or flag the report.
- **(c) Outcome check.** A stated measurable pass condition for the whole change, with a number or a time window, such as "zero manual steps for 4 consecutive weeks". The goal restated with no number or window is not kind (c).

These do not count:

- Restating the goal, such as "the report arrives every Monday".
- A question of whether something exists or works, to settle before building, such as "confirm the API exists". A stated test of the output counts even when the response says to run it once before cutover. An alert on zero rows counts as kind (b).
- "Test it", "verify it works", or "validate the output" with no condition.
- A delivery or scheduling step.
- The words "falsifiable" or "success check" with no condition after them.

Each response also gets a flag for kind (a) alone, called **FSC-A**. FSC-A is
a secondary measure.

## Scoring rule

Two independent scorers apply the rubric. Neither is told the arm. The response text can still reveal it, for example through the skill's wording, and that limit is accepted.

1. After the stop condition is met, take the first 20 valid pairs in order of (invocation number, repeat, arm name). Extra valid pairs are dropped before scoring. Only cells of valid pairs are scored. A response from a half-failed pair is excluded. Shuffle the 40 cells, in that order, with `random.Random(0).shuffle`. Assign ids `R01` to `R40` in shuffled order. Write two files with `json.dumps(obj, indent=2, sort_keys=True)` plus a trailing newline. The blind file is a list of objects with the keys `id` and `response`. The key file is a list of objects with the keys `id`, `arm`, `invocation`, and `repeat`. Record the SHA-256 of each file in the results record.
2. Scorer A calls `_ClaudeCLIProvider(executable=<capture wrapper>, timeout=900.0).complete(messages=[{"role": "user", "content": <prompt>}], model="claude-sonnet-5")` from `scripts/eval/_claude_cli.py`. That is the runner's own judge path, with its isolation: no settings sources, no MCP servers, no tools, no slash commands, no session persistence. Scorer B is the same call with `model="claude-opus-5"`. The scorer script is kept with the results record. A Codex scorer was the first plan. The Codex workspace returned "out of credits" on 2026-10-24, so both scorers are Claude models of different sizes. Each gets the same prompt. Each runs once, plus one rerun only when its output is unparseable (rule 3).
3. The scorer output is read from the `result` field of the CLI's JSON envelope. One optional Markdown code fence around the JSON is removed. The output is valid only if it is a JSON object whose keys are exactly the 40 ids, and each value is an object with exactly the keys `a`, `b`, and `c`, each 0 or 1. Anything else, including an `is_error` envelope, is unparseable. A scorer with unparseable output is rerun once with the same prompt. A valid output is never rerun.
4. A cell's FSC is 1 only when both scorers give at least one of `a`, `b`, `c` as 1 for it (the AND rule). A cell's FSC-OR is 1 when either scorer does. A cell's FSC-A is 1 only when both scorers give `a` as 1. The three are computed separately from the raw scorer outputs.
5. Agreement is the count of cells where both scorers give the same FSC value. If agreement is below 85% of the cells (fewer than 34 of 40), the verdict is INCONCLUSIVE whatever the counts say.
6. The key file is applied only after both scorer outputs are saved.

The author of this file reads the responses after unblinding. That read is
reported as description only. It never changes a count.

The scoring prompt is these parts, joined by blank lines, in this order: the
rubric text above (from "A response has FSC = 1" to the end of the "do not
count" list); "Request given to the model under test:" and the S8 `input`
string; "Responses (JSON):" and the blind file contents; and this instruction:
"For each response id above, return one JSON object mapping the id to
{\"a\": 0 or 1, \"b\": 0 or 1, \"c\": 0 or 1}. Return only the JSON object."

## Sample size

n = 20 valid pairs, so 20 cells per arm and 40 cells in all.

A valid pair is a repeat where both arms returned a non-empty response. The
runner is invoked with `--repeats 20`. If fewer than 20 valid pairs result,
top-up invocations of the same command run, each with `--repeats` set to the
missing number, until 20 valid pairs exist or a stop condition holds. Repeat
numbers restart at 1 in each invocation, so cells are identified by (invocation
number, repeat). Cells from a failed attempt are listed in the record and
excluded from every statistic. A judge failure alone does not make a pair
invalid, because the primary measure reads the response only.

Planned paid calls: 20 repeats x 2 arms x 2 calls (one response, one judge) =
80. Scoring adds two Claude calls, one per scorer.

Why 20: with the rule below, if the true rates are 0.5 for skill-routed and
0.05 for baseline, the chance of a clear yes is 0.89. If both true rates are
0.05, the chance of a clear no is 0.79. At n = 12 those chances are 0.59 and
0.58.

## Comparison and decision threshold

Let r be the count of FSC = 1 cells in the skill-routed arm and b the count in
the harness-baseline arm, each out of 20. The rate difference is
d = r/20 - b/20.

- **Fisher p**: the two-sided Fisher exact p value for the 2 by 2 table (r, 20 - r, b, 20 - b). It sums the probability of every table with the same margins whose probability is at or below the observed one.
- **Interval**: the Newcombe hybrid score 95% interval for d. It uses the Wilson score interval for each arm with z = 1.959964. Lower bound L = d - sqrt((pr - lr)^2 + (ub - pb)^2). Upper bound U = d + sqrt((ur - pr)^2 + (pb - lb)^2). Here pr = r/20, pb = b/20, (lr, ur) is the Wilson interval for r, and (lb, ub) is the Wilson interval for b.
- **Minimum effect**: 0.25. It is half the 0.5 seen in the second run's post hoc read, which shrinks that estimate for selection. The skill also adds at least 4,555 input tokens per call (median 4,880 on a 9,246 token baseline). That cost is context for the choice. It does not derive the number.

Verdict, applied in this order. Rule 3 and rule 4 use `verdict` from the reference implementation below.

1. If agreement is below 85%, or fewer than 20 valid pairs exist, or a stop fired before the 20th valid pair, or the count of failed response attempts differs between the two arms by more than 4, the verdict is INCONCLUSIVE.
2. Compute `verdict(r, b)` twice: once with the counts under the AND rule, once with the counts under the OR rule. If the two differ, the verdict is INCONCLUSIVE, because scorer strictness would decide it.
3. **CLEAR YES** when d is at least 0.25 and the Fisher p is below 0.05.
4. **CLEAR NO** when the upper bound U is below 0.25. This rules out a lift of the minimum effect or more. It includes the case where the skill-routed arm is lower than baseline. A reversed result is reported as "CLEAR NO (reversed)" when, on the AND-rule counts, the Fisher p is below 0.05 with skill-routed lower. It closes the issue the same way.
5. Otherwise **INCONCLUSIVE**.

The rules are checked once, on the complete data. No look at any count, score,
or response happens before the stop condition below is met.

Boundary table for n = 20 per arm (the rule above governs if they disagree).
For each baseline count b, CLEAR NO holds when r is at or below the first
number, and CLEAR YES holds when r is at or above the second.

| b | CLEAR NO when r is at most | CLEAR YES when r is at least |
|---|---|---|
| 0 | 1 | 5 |
| 1 | 1 | 7 |
| 2 | 2 | 9 |
| 3 | 3 | 10 |
| 4 | 4 | 11 |
| 5 | 4 | 13 |
| 6 | 5 | 14 |

The second run's post hoc counts, 6 of 12 against 0 of 12, would be CLEAR YES
at n = 12 (Fisher p 0.0137, d 0.5). At n = 20 the same rates give r = 10 and
b = 0, which is CLEAR YES.

## Stop rule

The runner has no stop of its own. It catches a failed call, records the cell
as failed, and moves on, and it writes `--output` once, when the invocation
ends. The capture wrapper therefore enforces the stops by refusing calls.

- The run ends when 20 valid pairs exist. Nothing is added because a result looks close.
- The wrapper refuses every `claude --print` call after the 120th call of the run (response plus judge, all invocations). Failed attempts count. The runner then finishes its remaining cells as failures and writes its output.
- The wrapper also refuses every call after 5 `claude --print` calls in a row exit non-zero. It writes a trip file. A trip is not retried.
- A stop counts only if it fires before the 20th valid pair exists. Then fewer than 20 valid pairs result, the verdict is INCONCLUSIVE, and no count is analyzed beyond the number of valid pairs and the failure causes. A stop that fires after 20 valid pairs exist (for example on judge calls) does not change the data, and the analysis proceeds.
- No run resumes after a stop, even if a person restores credits. A new attempt needs a new pre-registration.
- A stop caused by a quota, credit, or rate-limit message in the CLI's error output is a blocker for a person. The issue gets the label `blocked:human` and one comment that names the exact action.
- A scorer with unparseable output twice stops the scoring. The verdict is INCONCLUSIVE. The other scorer's saved output is reported, and the key file is never applied.

## Cost recording

The runner does not save cost. The run therefore sets `CLAUDE_CLI_BIN` to a
small wrapper kept outside the repository, in `~/src/scratch`. The wrapper
runs the real `claude` with the same arguments and standard input and passes
standard output through unchanged. For each `claude --print` call it appends
the `result` event's `total_cost_usd`, `usage`, `subtype`, and exit code to a
log, from either the stream-json output (responses) or the json envelope
(judge and scorers). It counts only `claude --print` calls. Other
invocations, such as `claude auth status`, pass through uncounted. It also
enforces the stops above. Its log, call counter, and trip file sit at fixed paths under `~/src/scratch/eval-6737/` written into the wrapper, because the runner passes a minimal environment. The failure streak counts `claude --print` calls in the order they finish, whatever their kind. When the runner kills the wrapper on a timeout, the wrapper forwards the signal to the real CLI, and the call is logged as unread. The scorers run through the same wrapper with their
own log and a cap of 4 calls. The record reports:

- Calls by kind (response, judge, scorer), the count of failed calls, and the sum of `total_cost_usd` for each kind, in USD at list price. The account is a subscription, so this is the metered equivalent, not a charge.
- Input and output tokens per arm.
- Any call whose cost the wrapper could not read, listed by position.
- A reconciliation: the wrapper's call count against the runner's cell count. The runner makes 1 response call and 1 judge call per cell, so a run with no failures logs 80 calls.

## Secondary measures

Reported, never used for the verdict.

- FSC-A counts and the same Fisher p and interval.
- The runner's `row_equality_check` proof point, count per arm.
- Judge cell score per arm, paired difference (skill-routed minus baseline), and a percentile bootstrap 95% interval over pairs (10000 resamples, `random.Random(0)`).
- Whether each arm chose a machine interface first, and whether any plan scripts the UI.
- Input token delta of the skill-routed arm against the baseline median.
- Scorer agreement, and the cells where the two scorers differ.
- Responses where the model says the skill text is an injection or skips the skill process.

## What the verdict covers

The verdict answers one question: on S8, does routing through `/spec` make the
model state a falsifiable success check more often than the bare request? It
does not show that the check is a good one, that the call changes, that an
amnesiac agent finds the principle from entry points, or that the novel-tool
requirements (demand, owner, authority boundary, cost) hold. Those acceptance
criteria of issue 6737 stay as the second run's comment left them.

Both scorers are Claude models, as is the model under test. A bias they share is not controlled by this design.

Skill-routed responses may use the skill's words ("falsifiable check") because
the skill asks for a proof point. A response that uses the words with a stated
condition counts. This measures whether the skill makes the model state the
check. That is what the skill's first step asks for.

## After the run

- Per owner decision D20 (2026-10-24), a CLEAR YES or CLEAR NO closes issue 6737. The closing comment names the acceptance criteria that the three runs did not measure.
- An INCONCLUSIVE verdict leaves the issue open with the result posted.
- The results record goes to `.project-toolkit/eval-results/` in its own pull request. It holds the command, commit, CLI version, scenario hash, blind and key file hashes, both scorer outputs, every count, the verdict, and the cost table.

## Reference implementation of the verdict

```python
from fractions import Fraction
from math import comb, sqrt


def fisher_two_sided(a, n1, b, n2):
    k, n = a + b, n1 + n2

    def p(x):
        return comb(n1, x) * comb(n2, k - x) / comb(n, k)

    observed = p(a)
    return sum(p(x) for x in range(max(0, k - n2), min(n1, k) + 1) if p(x) <= observed * (1 + 1e-9))


def wilson(x, n, z=1.959964):
    ph, d = x / n, 1 + z * z / n
    centre = (ph + z * z / (2 * n)) / d
    half = z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def newcombe(r, b, n):
    pr, pb = r / n, b / n
    lr, ur = wilson(r, n)
    lb, ub = wilson(b, n)
    d = pr - pb
    return (d, d - sqrt((pr - lr) ** 2 + (ub - pb) ** 2), d + sqrt((ur - pr) ** 2 + (pb - lb) ** 2))


def verdict(r, b, n=20, minimum_effect=Fraction(1, 4)):
    _, _, upper = newcombe(r, b, n)
    if Fraction(r - b, n) >= minimum_effect and fisher_two_sided(r, n, b, n) < 0.05:
        return "CLEAR YES"
    if upper < minimum_effect:
        return "CLEAR NO"
    return "INCONCLUSIVE"


def final_verdict(r_and, b_and, r_or, b_or, agreement, valid_pairs, stopped):
    # `stopped` is True only when a stop fired before the 20th valid pair.
    if stopped or valid_pairs < 20 or agreement < 0.85:
        return "INCONCLUSIVE"
    v = verdict(r_and, b_and)
    return v if v == verdict(r_or, b_or) else "INCONCLUSIVE"
```
