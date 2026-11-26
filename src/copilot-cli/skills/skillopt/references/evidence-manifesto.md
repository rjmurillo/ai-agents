# Evidence-driven edits

Read this before you write `weakness.json` or `manifesto.json`, and before
you pin the read-only surfaces. These checks make each edit a falsifiable
claim tied to train evidence. They come from Lilian Weng's survey "Harness
Engineering for Self-Improvement" (Lil'Log, 2026,
<https://lilianweng.github.io/posts/2026-07-04-harness/>) and the papers it
cites. The survey's reported gains are its claims; this skill does not
reproduce them.

Every file here names train task ids only. A `sel` id in a task list or a
free-text field exits 2, because the candidate author must not see `sel`
tasks (Precondition 4). Patch text in `patches.json` is not scanned.

Only a literal `false` counts as a failure. An `"UNVERIFIED"` result is not
a failure: it cannot sit in a weakness pattern or be a predicted fix.

Sections 2 to 4 cover accuracy edits, judged by `pair-gate`. An
efficiency-only edit, made when every task already passes, skips them. Its
prediction is the metric and threshold it declares for `efficiency-gate`.
Pins (section 5) still apply.

## 1. Proposer tier

Run `skillopt.py proposer-check --model <proposer>` before Reflect.

| Exit | Word | Meaning |
|---|---|---|
| 0 | `CAPABLE` | sonnet tier or stronger |
| 1 | `LIGHTWEIGHT` or `UNKNOWN` | warning; continue only with a recorded reason |
| 2 | none | blank model name |

Why: STOP (Zelikman et al., "Self-Taught Optimizer (STOP)", COLM 2024)
"improved mean downstream performance across iterations with GPT-4 but
degraded with weaker models like GPT-3.5 and Mixtral." A loop run on a weak
proposer can make the target worse.

The check warns and does not refuse. Lin et al. ("Harness Updating Is Not
Harness Benefit", arXiv:2605.30621) measured harness-updating ability as flat
from Qwen3.5-9B to Claude Opus 4.6, so tier is a risk signal, not proof. The
gate still decides.

## 2. Weakness mining (`weakness.json`)

Cluster failing train tasks before you propose any patch. Self-Harness (Zhang
et al., arXiv:2606.09498) mines "verifier-grounded failure patterns", because
two runs can share a verifier outcome, such as a timeout, while having
different causes.

```json
{
  "schema": "skillopt-weakness/1",
  "patterns": [
    {
      "id": "missing-output-path",
      "tasks": ["t1", "t2"],
      "verifier_cause": "verifier found no report file",
      "agent_behavior": "the runner printed the report to chat",
      "mechanism": "no rule names where the report goes",
      "addressable": true
    }
  ]
}
```

- `tasks`: failing train tasks. A task that passed at baseline exits 2. A
  task sits in one pattern at most.
- `verifier_cause`, `agent_behavior`, `mechanism`: the terminal verifier
  cause, the causal agent behavior, and the mechanism the trace exposed.
- `addressable`: `false` for task-specific difficulty that no narrow edit
  fixes. A manifesto entry that targets it exits 2.

`skillopt.py weakness-check --eval eval.json --incumbent-results
incumbent_results.json --weakness weakness.json` exits 0 with a report, or 2.
The report lists `recurrent_addressable` patterns (two or more tasks) and
`unclustered_failures`. Prefer recurrent, addressable patterns. Keep each
step's patches few (the budget L_t) and aimed at distinct patterns.

## 3. Manifesto (`manifesto.json`)

One entry per patch, in the form AHE uses (Lin et al., "Agentic Harness
Engineering", arXiv:2604.25850): the failure evidence, the inferred root
cause, the targeted fix, and a predicted impact with expected fixes and
at-risk regressions.

```json
{
  "schema": "skillopt-manifesto/1",
  "proposer_model": "claude-opus-5-5",
  "entries": [
    {
      "patch": 0,
      "pattern": "missing-output-path",
      "evidence": ["t1", "t2"],
      "root_cause": "the skill never says where the report goes",
      "component": "skill",
      "fix": "name the report path in step 4",
      "predicted_fixes": ["t1", "t2"],
      "at_risk": ["t5"]
    }
  ]
}
```

- `patch`: index into `patches.json`. Every patch needs exactly one entry.
- `evidence`: tasks from the named pattern.
- `component`: one of AHE's seven editable components: `system-prompt`,
  `tool-description`, `tool-implementation`, `middleware`, `skill`,
  `sub-agent-configuration`, `long-term-memory`.
- `predicted_fixes`: train tasks that fail now and you expect to flip to
  pass. At least one. A task that passes at baseline exits 2.
- `at_risk`: train tasks that pass now and might break. May be empty. A task
  that fails at baseline exits 2.

`skillopt.py manifesto-check --eval eval.json --incumbent-results
incumbent_results.json --weakness weakness.json --manifesto manifesto.json
--patches patches.json` exits 0 or 2. It prints a warning for a lightweight
proposer and for a single-task pattern chosen over a recurrent one.

## 4. Verify the predictions

After the candidate re-roll, run `skillopt.py manifesto-verify --eval eval.json
--manifesto manifesto.json --incumbent-results incumbent_results.json
--candidate-results candidate_results.json`. It reads train results only.

| Exit | Verdict | Meaning |
|---|---|---|
| 0 | `PREDICTIONS_HELD` | every predicted fix passed, no unlisted train regression |
| 1 | `PREDICTION_FALSIFIED` | a predicted fix still fails, or a train task regressed that no entry listed as at risk |
| 1 | `PREDICTION_UNVERIFIED` | a train task has no boolean result |
| 2 | none | invalid input, or a `sel` id in an entry's task lists |

A listed at-risk regression is reported in `at_risk_regressed`, not
falsified. A falsified prediction means the root cause was wrong; mine
again. When `pair-gate` rejects, put the verdict in the `buffer-add` note.
When it accepts, keep the report with the run's evidence and do not call
`buffer-add`, because the buffer marks a patch set as known bad.
`manifesto-verify` never replaces `pair-gate`; the `sel` runner still
returns only the gate verdict.

## 5. Read-only surfaces (`pins.json`)

AHE keeps "the runs directory, tracer, verifier, and LLM configuration"
read-only, which blocks reward hacking such as "disabling the verifier,
swapping the model, or raising the reasoning budget." In skillopt the
read-only surfaces are the eval set (`eval.json`), each verifier script, any
tracer or grading script, and the model configuration. Pass an effort or
budget config file as a surface to pin it. The optimizing run may edit only
the target.

At baseline, add `"pins": "pins.json"` to `eval.json` (a path relative to
it) and finish every other edit to it. Then pin once:

```bash
python3 "${SKILLOPT_DIR:?}/skillopt.py" pin --eval eval.json --surface verifier=check.py --surface tracer=grade.py --model claude-sonnet-5-5 --out pins.json
```

With that field set, `pair-gate`
and `efficiency-gate` exit 2 when any pinned file changed, the pins file is
gone, or the pins file pins a different eval set. `--out` may not overwrite
or sit inside a pinned surface, and each `--surface` name may appear once.

`skillopt.py pin-check --pins pins.json --model <model in use>` exits 0
`MATCH`, 1 `MISMATCH` (a changed surface or a different model), or 2.

What is enforced and what is only named:

- Files are enforced by digest at `pair-gate` and `efficiency-gate` when
  `eval.json` declares `pins`, and by `pin-check` at any time.
- Pins store absolute paths. Moving the checkout, or gating from another
  worktree, exits 2 until you pin again.
- A pinned symlink records both the link and its target. A link that now
  points elsewhere is a mismatch, even when the new target has the same
  bytes.
- `pin` hashes the path you name. When an eval command runs a grader by a
  path relative to the bundle, each bundle has its own copy. Keep graders
  outside the bundle, or pin the incumbent's and the candidate's copies as
  two surfaces.
- The model is enforced only when you pass `--model` to `pin-check`. Nothing
  reads the model your harness actually used.
- A manifest without `pins` gates as before. Deleting the `pins` field alone
  defeats the check, and so does running `pin` again after an edit. It
  defends against an honest mistake, not an adversary.
