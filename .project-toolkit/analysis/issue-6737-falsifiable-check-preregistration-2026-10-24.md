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

- Scenario: `tests/evals/skill-scenarios/spec.json`, id `S8`. The scenario hash (first 16 hex characters) must equal `44ded3f54b83fdb5`. If it differs, the run does not start.
- Runner: `scripts/eval/eval-rule-activation.py`, arms `harness-baseline` and `skill-routed`, as defined in the second run's record.
- Transport `claude-cli`, model `claude-sonnet-5`, judge repeats 1, judge reducer median, seed 0.
- The Claude CLI version may differ from 2.1.309. The record states the version used.
- The run starts from `origin/main` as merged after this file. No runner or scenario edit lands between the merge of this file and the end of the run.

## Primary measure

**Falsifiable success check named (FSC).** One binary value per response. The
unit is the cell, which is one response from one arm in one repeat.

A response has FSC = 1 when it states, for the proposed weekly process, at
least one condition that a person can observe to be true or false, where a
false result would show that the process failed or that its list is wrong.
Three kinds count:

- **(a) Correctness check.** Compares the automated output with an independent reference: the dashboard, the CSV export, or the manual list. The comparison is by rows, names, or counts.
- **(b) Health or completeness check.** A stated test on the output or the job, such as a row count, a non-empty list, an HTTP status, or a failure alert, where a failed test is stated to stop or flag the report.
- **(c) Outcome check.** A stated measurable pass condition for the whole change, such as "zero manual steps for 4 consecutive weeks".

These do not count:

- Restating the goal, such as "the report arrives every Monday".
- A risk or open question to confirm before building, such as "confirm the API exists".
- "Test it", "verify it works", or "validate the output" with no condition.
- A delivery or scheduling step.
- The words "falsifiable" or "success check" with no condition after them.

Each response also gets a flag for kind (a) alone, called **FSC-A**. FSC-A is
a secondary measure.

## Scoring rule

Two independent scorers apply the rubric. Neither sees the arm.

1. After all valid pairs exist, extract the response text of every valid cell. Sort the cells by (repeat, arm name). Shuffle them with `random.Random(0).shuffle`. Assign ids `R01`, `R02`, and so on in shuffled order. Write the blind file (id and response text only) and a key file (id, arm, repeat). Record the SHA-256 of both files in the results record.
2. Scorer A is `claude --print --model claude-sonnet-5 --output-format json --tools "" --setting-sources project --no-session-persistence`, run in an empty temporary directory. Scorer B is `codex exec -m gpt-5.6-sol --sandbox read-only`. Each gets the same prompt, the rubric above, and the blind file. Each runs once. No rerun on a bad answer, except when the output is not parseable JSON, which allows one rerun of the same prompt.
3. Each scorer returns a JSON object that maps each id to an object with the keys `a`, `b`, and `c`, each 0 or 1. No other text is read.
4. A cell's FSC is 1 only when both scorers give at least one of `a`, `b`, `c` as 1 for it. A cell's FSC-A is 1 only when both scorers give `a` as 1.
5. Agreement is the count of cells where both scorers give the same FSC value. If agreement is below 85% of the valid cells (for example fewer than 34 of 40), the verdict is INCONCLUSIVE whatever the counts say. The measure is then too unreliable to decide.
6. The key file is applied only after both scorer outputs are saved.

The author of this file reads the responses after unblinding. That read is
reported as description only. It never changes a count.

The scoring prompt is the rubric text above (from "A response has FSC = 1" to
the end of the "do not count" list), followed by this instruction: "For each
response id in the JSON below, return one JSON object mapping the id to
{\"a\": 0 or 1, \"b\": 0 or 1, \"c\": 0 or 1}. Return only the JSON object."

## Sample size

n = 20 valid pairs, so 20 cells per arm and 40 cells in all.

A valid pair is a repeat where both arms returned a non-empty response. The
runner is invoked with `--repeats 20`. If fewer than 20 valid pairs result,
one top-up invocation runs exactly the missing number of repeats. Cells from a
failed attempt are listed in the record and excluded from every statistic. A
judge failure alone does not make a pair invalid, because the primary measure
reads the response only.

Planned paid calls: 20 repeats x 2 arms x 2 calls (one response, one judge) =
80. Scoring adds one Claude call and one Codex call.

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
- **Minimum effect**: 0.25. It is half the 0.5 seen in the second run's post hoc read, which shrinks that estimate for selection. It is also the smallest lift that justifies the extra input of at least 4,555 tokens per call that the skill adds (median 4,880 on a 9,246 token baseline).

Verdict, applied in this order:

1. If agreement is below 85%, or fewer than 20 valid pairs exist, the verdict is INCONCLUSIVE.
2. **CLEAR YES** when d is at least 0.25 and the Fisher p is below 0.05.
3. **CLEAR NO** when the upper bound U is below 0.25. This rules out a lift of the minimum effect or more.
4. Otherwise **INCONCLUSIVE**.

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

- The run stops when 20 valid pairs exist. Nothing is added because a result looks close.
- The run stops early, with verdict INCONCLUSIVE and no analysis of counts, if any of these holds: the capture wrapper reaches 120 harness calls (response plus judge); 5 harness calls in a row fail; or the CLI reports a quota, credit, or rate limit that does not clear after one retry 10 minutes later.
- A quota or credit stop is a blocker for a person. The issue gets the label `blocked:human` and one comment that names the exact action.
- A scorer that returns unparseable output twice is a stop. The verdict is INCONCLUSIVE.

## Cost recording

The runner does not save cost. The run therefore sets `CLAUDE_CLI_BIN` to a
small wrapper kept outside the repository, in `~/src/scratch`. The wrapper
runs the real `claude` with the same arguments and standard input, passes
standard output through unchanged, and appends each `total_cost_usd` and
`usage` block it sees to a log. It also counts calls for the stop rule. The
record reports:

- Calls by kind (response, judge, scorer) and the sum of `total_cost_usd` for each, in USD at list price. The account is a subscription, so this is the metered equivalent, not a charge.
- Input and output tokens per arm.
- The Codex scorer call, which has no cost field. It is counted and marked not metered.
- Any call the wrapper could not read, listed by id.

A check that the wrapper changed nothing: before the run, one `claude --version` and one dry run of the runner (`--dry-run`) go through it, and their outputs match a run without it.

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


def verdict(r, b, n=20, minimum_effect=0.25):
    d, _, upper = newcombe(r, b, n)
    if d >= minimum_effect and fisher_two_sided(r, n, b, n) < 0.05:
        return "CLEAR YES"
    if upper < minimum_effect:
        return "CLEAR NO"
    return "INCONCLUSIVE"
```
