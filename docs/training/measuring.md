# Measure agent quality with evals and benchmarks

## Goal

You will run the repo's evals and read what they say. You will also learn what a result does not say.

By the end you will have:

- Checked a benchmark corpus and planned a live run without spending money.
- Scored an existing benchmark result and read its verdict.
- Rebuilt the v0.7.0 gate 6 non-inferiority interval from raw counts.
- Computed cost and wall time per accepted task from a metrics file.

Every command in Steps 1 to 8 makes zero model calls. Paid runs are named as paid.

This page is for contributors who change prompts, skills, or model pins.

## Before you start

- A clean checkout of `main`. See [Installation](../installation.md) and [CONTRIBUTING](../../CONTRIBUTING.md) for setup.
- `uv` and Python 3.14, as `uv run python` is the repo's runner.
- Nothing else. No API key, no login, no credits.

## Pick the right tool

| Question | Tool | Reference |
|---|---|---|
| Did my prompt edit help or hurt? | `scripts/eval/eval-prompt-change.py` | [`scripts/eval/README.md`](../../scripts/eval/README.md) |
| Does an agent beat a generic baseline? | `scripts/eval/eval-agent-vs-baseline.py` | [`evals/README.md`](../../evals/README.md) |
| Which model or harness routes work best? | `scripts/eval/eval_routing_benchmark.py` | [`evals/routing-benchmark/README.md`](../../evals/routing-benchmark/README.md) |
| Can I remove a control file and lose nothing? | `scripts/eval/eval_control_ablation.py` | [`evals/control-ablation-historical/README.md`](../../evals/control-ablation-historical/README.md) |
| Is this skill edit a real gain? | `skillopt.py pair-gate` | [`skillopt` skill](../../.claude/skills/skillopt/SKILL.md) |
| Which provider is faster or cheaper on one prompt? | `benchmark-models` skill | [`benchmark-models` skill](../../.claude/skills/benchmark-models/SKILL.md) |
| Is setup and tooling easy to use? | `dx-review` skill | [`dx-review` skill](../../.claude/skills/dx-review/SKILL.md) |

## Steps

### 1. Check the routing corpus

The routing benchmark gives six scenarios to every strategy arm. Each scenario ships a known-good fix and a known-bad fix. The corpus check proves the grader tells them apart.

```bash
uv run python scripts/eval/eval_routing_corpus.py
```

It prints one JSON report. Read the two counts that matter:

```bash
uv run python scripts/eval/eval_routing_corpus.py | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['examined'], d['failed'])"
```

Expected output:

```text
6 0
```

Six scenarios examined, none failed. A grader that cannot reject the known-bad fix measures nothing, so run this check first.

### 2. Plan a live benchmark without spending

The same script plans the run when you leave out `--live`.

```bash
uv run python scripts/eval/eval_routing_benchmark.py | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['mode'], d['planned'], d['rejected'], d['model_calls'])"
```

Expected output:

```text
dry-run 60 48 0
```

It planned 60 rows, rejected 48, and made 0 model calls. The rejected rows are Copilot (unsupported) and the Claude arms whose effort setting was never verified.

A live run spends real credits. It needs four flags: `--live`, `--output`, `--max-invocations`, and `--real-home` (Claude requires it). Claude Code was added as a harness in #6880. The Codex live path came from #6161. Results are per harness and are never pooled.

Before any paid run, ask what your machine can reach:

```bash
uv run python scripts/eval/eval_billing_matrix.py
```

It prints `READY`, `NOT_READY`, or `UNKNOWN` for each harness and billing cell. It reads variables and PATH only, so `UNKNOWN` means a login on disk may still work. See the [billing matrix](../../scripts/eval/README.md#providers-the-harness-x-billing-matrix).

### 3. Score an existing benchmark result

The repo keeps the Claude run from 2026-10-23. Score it with the pre-registered rules:

```bash
uv run python scripts/eval/eval_routing_verdicts.py \
  --results evals/routing-benchmark/results-2026-10-23-claude-v2/arms-AE.jsonl \
            evals/routing-benchmark/results-2026-10-23-claude-v2/arms-BF.jsonl \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['harnesses']['claude']; print(d['rows_scored'], d['decision']); [print(h, v['status']) for h, v in d['hypotheses'].items()]"
```

Expected output:

```text
72 INSUFFICIENT_EVIDENCE
H1 INSUFFICIENT_EVIDENCE
H2 INSUFFICIENT_EVIDENCE
H3 INSUFFICIENT_EVIDENCE
H4 INSUFFICIENT_EVIDENCE
```

Read this as a result, not a failure. The run had 72 scored rows, 60 accepted and 12 failed. Arms C and D never ran because their effort setting was not verified. The rules in [`PREDICTIONS.md`](../../evals/routing-benchmark/PREDICTIONS.md) say what evidence would move each hypothesis. The honest decision is: no routing change.

The README records one observation that is not a verdict. On the fallback scenarios, arm E matched arm A's acceptance at 29.7 percent of the wall-clock. The scorer does not read it, and neither should you.

### 4. Dry-run a control ablation

A control ablation runs the same tasks twice. One arm loads the control files (`full`). The other loads none (`reduced`). The dry run proves each task's grader can tell a good fix from a bad one before any paid launch.

```bash
uv run python scripts/eval/eval_control_ablation.py --dry-run | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d['known_good_accepted_durable'], '/', d['known_good_total'], d['known_bad_accepted_durable'], '/', d['known_bad_total'])"
```

Expected output:

```text
Report: <repo>/artifacts/control-ablation/<run id>/report.json
PASS 5 / 5 0 / 5
```

The `Report:` line goes to stderr and the path changes on every run. All five known-good fixes pass and none of the five known-bad fixes do. The `artifacts/` folder is not tracked by git.

### 5. Compare two configurations

The v0.7.0 batch of 2026-09-28 has committed records for both arms. Compare them:

```bash
D=.project-toolkit/metrics/control-ablation-v0.7.0
uv run python scripts/eval/eval_durable_outcome.py \
  --records $D/records-reduced.jsonl --baseline $D/records-full.jsonl \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['result']); [print(k, d[k]['config']['control'], d[k]['headline']['cost_per_accepted_durable_task_usd']) for k in ('baseline','candidate')]"
```

Expected output:

```text
MIXED
baseline full 0.2444
candidate reduced 0.1292
```

`MIXED` means the candidate is not worse and not better. It accepted 9 of 15 durable tasks against 10 of 15, at about half the cost. That gap is one run. Do not call it a win.

### 6. Rebuild the gate 6 non-inferiority interval

A tie in pass counts is not proof of equal quality. Non-inferiority asks a sharper question: can we rule out a loss bigger than a margin you fixed in advance?

Release v0.7.0 gate 6 asked whether the smaller configuration (`reduced`) is non-inferior to `full`. The rule was written down before the first paid launch. The ledger section is "Gate 6 pre-registration, 2026-11-10" in [`control-plane-dispositions-v0.7.0.md`](../../.project-toolkit/metrics/control-plane-dispositions-v0.7.0.md).

| Part of the rule | Value |
|---|---|
| Margin | 0.10 (10 percentage points) |
| Interval | Newcombe hybrid-score, 95 percent |
| Minimum runs | 50 per arm |
| Task guard | Verdict is NOT SHOWN if `reduced` trails `full` by 4 or more runs on any one task |
| Success test | Lower bound of the difference is above -0.10 |
| Defect test | Upper bound of the difference is below +0.10 |

Save this as a scratch file outside the repo, for example `newcombe.py`:

```python
from math import sqrt

Z = 1.959964


def wilson(x, n):
    p = x / n
    c = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    h = Z * sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return c - h, c + h


def newcombe(x_new, x_old, n):
    p1, p2 = x_new / n, x_old / n
    l1, u1 = wilson(x_new, n)
    l2, u2 = wilson(x_old, n)
    d = p1 - p2
    low = d - sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    high = d + sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, low, high


print("success %+.4f %+.4f %+.4f" % newcombe(69, 70, 70))
print("defects %+.4f %+.4f %+.4f" % newcombe(0, 0, 70))
print("tie     %+.4f %+.4f %+.4f" % newcombe(50, 50, 50))
```

```bash
python3 newcombe.py
```

Expected output:

```text
success -0.0143 -0.0766 +0.0390
defects +0.0000 -0.0520 +0.0520
tie     +0.0000 -0.0713 +0.0713
```

The first line is the real gate 6 result: `full` passed 70 of 70 and `reduced` passed 69 of 70. The difference is -0.0143. The interval is -0.0766 to +0.0390. The lower bound clears -0.10, so the success test holds. The [release report](../../.project-toolkit/metrics/release-report-v0.7.0.md) lists the same numbers.

The third line shows why the minimum is 50 runs. A perfect tie at 50 of 50 gives a lower bound of -0.0713. Fewer runs and a clean tie cannot clear a 0.10 margin.

Read the verdict with its limits. The release report says "Shown" for gate 6 only on this corpus:

- Five tasks, one model (`claude-sonnet-5`), one harness version.
- The ambient `~/.claude` load applies to both arms, so `reduced` is not free of instructions.
- The arms differ by one run in 70. The tasks may not exercise the controls at all.
- Codex was not rerun. Human correction time was not measured.

The same question on 2026-11-06, at 15 runs per arm, was reported as not shown. Three runs per cell cannot bound anything.

### 7. Hold out data before you claim an improvement

A loop that edits a prompt and re-reads its own score will find a gain by chance. [ADR-087](../../.project-toolkit/architecture/ADR-087-held-out-validated-improvement.md) sets the rules:

- Split the tasks into optimize, selection, and optional test groups before the first edit.
- Fingerprint the split. A decision against a different fingerprint is refused.
- Count every read of the selection group. Do not re-draw the split after a loss.
- Refuse any pass-to-fail change, whatever the average did. There is no override.
- Refuse a comparison whose corpora disagree.

ADR-087 is `proposed`. It describes the mechanism and its limits. Read its Open Requirements before you cite it as policy.

`skillopt` carries the working gates. List them:

```bash
uv run python .claude/skills/skillopt/scripts/skillopt.py --help | grep -E "^    (gate|pair-gate|efficiency-gate|hash)"
```

Expected output:

```text
    gate                accept iff candidate strictly beats incumbent
    pair-gate           accept iff candidate adds a held-out pass with zero
    efficiency-gate     accept a pre-declared efficiency gain with correctness
    hash                sha256 of file bytes or a whole bundle directory;
```

Use `pair-gate` for a skill edit. It accepts only when the candidate adds a held-out pass and loses none. Use `hash` to pin the incumbent bundle, so a null rerun provably used the same bytes. For how the skill loop maps to the agentskills.io guide, see [`evals/README.md`](../../evals/README.md).

### 8. Check that model pins carry eval evidence

A versioned model pin needs evidence. [ADR-080](../../.project-toolkit/architecture/ADR-080-model-pin-justification-policy.md) set that rule. [ADR-111](../../.project-toolkit/architecture/ADR-111-skill-model-pins-project-per-harness.md) superseded it on 2026-09-27 and keeps the evidence bar:

- Skills and commands carry no versioned model id. They may use a bare alias such as `haiku`, with a `model-rationale:` field.
- An agent may carry a versioned pin only with a cited KEEP_PIN sweep. The bar is a mean recall delta of at least 0.05, a paired bootstrap interval whose lower bound is above 0, and at least 8 shared fixtures.
- The evidence lives in `.agents/governance/model-pin-evidence.json`, not in frontmatter.

Run the gate:

```bash
uv run python scripts/validation/check_model_pins.py --mode enforce
```

Expected output:

```text
[model-pins] scanned 7 pinned units
[model-pins] OK: no new or changed pin violations
```

If you add a pin, the gate fails until the manifest cites a sweep. For the cost side of form-factor choices, see [ADR-075](../../.project-toolkit/architecture/ADR-075-form-factor-eval-methodology.md). It compares `baseline`, `agent`, and `skill` forms on the same fixtures.

### 9. Audit developer experience

Evals measure agent output. `dx-review` measures what a person meets when they set up and use a tool. It came from #5009.

Ask your agent: `run a DX audit` on the target. The skill runs inside your agent session, so it has no command to copy. It scores eight dimensions out of 10: getting started, API and CLI, error messages, documentation, upgrade path, dev environment, community, and DX measurement. It also records time to hello world when the target has a runnable example.

Every score must cite an evidence label:

| Label | Meaning |
|---|---|
| TESTED | The auditor ran it and saw the result. |
| PARTIAL | Some parts ran. Others came from reading files. |
| INFERRED | Read from files or docs only. |

Fetched docs alone are never TESTED. The audit stops at an evidence gate until each high-impact conclusion has two independent sources, then a read-only reviewer must pass it. Treat an all-INFERRED scorecard as a reading list, not a measurement. See the [`dx-review` skill](../../.claude/skills/dx-review/SKILL.md).

## Check your result

You are done when you can state each of these from your own terminal output:

1. The routing corpus examined 6 scenarios and failed 0.
2. The dry-run plan made 0 model calls.
3. The Claude benchmark decision is `INSUFFICIENT_EVIDENCE`, and you can say why.
4. The control-ablation dry run printed `PASS 5 / 5 0 / 5`.
5. `newcombe.py` printed `-0.0143 -0.0766 +0.0390` for success.
6. `check_model_pins.py` printed `OK`.

## Read cost and wall time per accepted task

Price accepted work, not tokens. A cheap arm that fails more often can cost more per good result.

Each record in a `records-*.jsonl` file holds `economics.model_cost_usd` and `economics.wall_seconds`. Divide the totals by the number of accepted runs. An accepted run passes deterministic acceptance, the hidden follow-up, and the objective check. The `durable_outcome` comparison from Step 5 already prints cost per accepted durable task.

To get wall time as well, save this as `per_accepted.py`:

```python
import json
import sys

for path in sys.argv[1:]:
    rows = [json.loads(line) for line in open(path)]
    ok = [
        r
        for r in rows
        if r["execution"]["deterministic_acceptance"] == "PASS"
        and r["durable"]["followup_validation"] == "PASS"
        and r["durable"]["objective_satisfied"] == "PASS"
    ]
    cost = sum(r["economics"]["model_cost_usd"] for r in rows)
    wall = sum(r["economics"]["wall_seconds"] for r in rows)
    print(
        f"{path.split('/')[-1]}: runs={len(rows)} accepted={len(ok)} "
        f"usd/accepted={cost / len(ok):.3f} wall_s/accepted={wall / len(ok):.1f}"
    )
```

```bash
D=.project-toolkit/metrics/control-ablation-v0.7.0
python3 per_accepted.py $D/records-full.jsonl $D/records-reduced.jsonl
```

Expected output:

```text
records-full.jsonl: runs=15 accepted=10 usd/accepted=0.244 wall_s/accepted=39.4
records-reduced.jsonl: runs=15 accepted=9 usd/accepted=0.129 wall_s/accepted=29.1
```

These match [`control-ablation-v0.7.0.md`](../../.project-toolkit/metrics/control-ablation-v0.7.0.md). The 2026-11-10 batch priced accepted deterministic tasks at USD 0.165 for `full` and 0.078 for `reduced`, at list price. Both arms carried the same ambient `~/.claude` load, so the gap is not a clean measure of one control file. Subscription cells report request counts, not dollars, on purpose.

Do not confuse this with [`docs/agent-metrics.md`](../agent-metrics.md). That page covers how often agents are invoked and how fast reviews return. It does not price accepted tasks.

## Avoid overclaiming

Before you write "better", "equal", or "safe to remove", check each item:

- **Sample size.** Three runs per cell cannot bound anything. A task that succeeds half the time passes 3 of 3 runs 12.5 percent of the time.
- **Margin.** Name the margin before the run. Do not pick it after you see the data.
- **Scope.** State the corpus, model, and harness version. "Shown on this corpus" is a smaller claim than "shown".
- **Pooling.** Never pool across harnesses, or across runs under different prompts or graders.
- **Unverified fields.** A null or `UNVERIFIED` field is not a zero. Human correction time was null for v0.7.0, so formal `ACCEPTED_DURABLE` was 0.
- **Confounds.** Name what both arms share. An ambient config load shrinks any difference you can see.
- **Judges.** A blind LLM judge is advisory only. Graders must be deterministic and frozen before a scored run.
- **Insufficient evidence.** It is a valid result. Report it as one.

## If it fails

| Symptom | Likely cause | What to do |
|---|---|---|
| `uv: command not found` | `uv` is not installed | Follow [CONTRIBUTING](../../CONTRIBUTING.md) setup, then rerun. |
| Corpus check prints `failed` above 0 | A fixture or grader changed | Read the failing check name in the JSON. Do not loosen the grader to make it pass. |
| Verdict script refuses to run | You mixed `results-2026-10-03/` with later runs | Score each attempt alone. The scorer refuses to pool them. |
| Billing matrix shows `UNKNOWN` | The CLI may log in from disk | Run one live call with a low `--max-invocations` cap to find out. That call is paid. |
| `eval_durable_outcome.py` exits 2 | The two files disagree on config or task set | Compare `config` and `task_id` in both files. |
| `check_model_pins.py` fails | A pin has no cited sweep | Add the sweep to `.agents/governance/model-pin-evidence.json`, or drop the pin. |
| A live run stops at a credit error | The workspace hit its cap | Stop. Score what exists and report `INSUFFICIENT_EVIDENCE` unless it clears the floor. Rerun only on a funded workspace, into a new results folder. |

## Next

- Back to the [training index](README.md).
- Reference: [`evals/README.md`](../../evals/README.md), [`scripts/eval/README.md`](../../scripts/eval/README.md), and the [v0.7.0 release report](../../.project-toolkit/metrics/release-report-v0.7.0.md).
