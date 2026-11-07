# Capability-gain gate

Detail for the `skillify` skill. Read it before step 6 (Write) when the new or
patched skill will claim it makes the agent better at a task, and again at the
end of step 7 to settle that claim.

Loading and repeating a procedure shows the skill runs. It does not show the
agent got better at the task. Without a recorded baseline the claim is
`UNVERIFIED`. This gate builds no harness of its own.

## Record a baseline before step 6

Run this when the create or patch will claim a capability gain. If a claim is
made without a baseline, report `UNVERIFIED (no baseline)`. If there is no
claim, skip this gate and omit the capability field from the step 8 line. The
overlap check in step 4 still decides create or patch. This gate never
overrides it.

Write the baseline from what you observed this session, not from memory:

```text
Baseline task: <the task the skill must make better>
Baseline command: <the original task input: the user prompt plus the starting
  state as it was before the session's work, and how to recreate that state:
  a commit SHA, a scratch copy, or the resource's original value>
Observed result: <failure message, wrong output, or measured cost such as tool
  calls, retries, or wall time>
Success measure: <the observable that should differ when the skill is used>
```

| Baseline | Step 6 | Capability claim |
|---|---|---|
| All four fields filled with observed values | proceed | none yet; the settle step decides |
| No failure or measurable inefficiency, or a field is missing | proceed | `UNVERIFIED`; state no gain |

The Baseline command carries no solution steps, fixes, or hints learned in the
session, because the fresh-context run receives it and would inherit them. A
command you cannot reproduce, or a starting state you cannot recreate, counts
as a missing field.

Save controls now:

- Patch: copy the skill's current content to a scratch file and keep the path.
  The pre-patch version is the control.
- Create: run the control now, before the skill is written, after recreating
  the starting state. Otherwise plan to remove the new skill for the control.
- Multi-task or held-out claim: freeze an eval set before step 6, in
  `skillopt` `references/eval-set-format.md` format: the tasks, a per-task
  verifier, and a `sel` split. The author must not see `sel` tasks or
  verifiers. A separate subagent with no transcript, or the user, writes them
  to a file the authoring context never reads. A `sel` split the author wrote
  or read is training. If none was frozen, make no multi-task claim.

## Settle the claim after verify passes

A clean `verify` and a successful load prove the skill loads. Never cite them
as capability evidence. Take the first step that applies:

1. **Known failure or measured inefficiency, with a reproducible baseline
   command.** Run a control and a treatment, each in a fresh context: a new
   session, or a subagent with no transcript, no session notes, and no memory
   of this session. If you cannot block that memory, state it as a threat.
   - Reset: before every run, recreate the starting state (a clean checkout or
     scratch copy at the pre-session commit, and the original value of any
     external resource the command changes). A run that starts from another
     run's output is invalid. If you cannot recreate the state, take step 3.
   - Control: the Baseline command with the skill in its pre-write state. A
     control that can load the written skill is not a control. For a create,
     run it before the write or remove the new skill for the run and restore
     it after. For a patch, run the saved pre-patch content.
   - Treatment: the same command with the written skill loaded.
   - Sample: run each the same number of times, or state that one run each is
     the sample size.
   - Not a control: the original session run (long context, exploration noise,
     and the agent already holds the fix). An in-session rerun is
     `UNVERIFIED`. If the control does not show the baseline failure, the
     failure did not recur; take step 3.
   - Scope: this supports a claim about that one task only. State it so.
2. **Multi-task or held-out claim.** Measure with `skillopt` (`pair-gate` needs
   the frozen `sel` split and per-task verifiers). An eval set written after
   the write cannot back the claim, because its tasks were chosen with the
   skill in view. If none was frozen, take step 3.
3. **Neither is possible.** Report `UNVERIFIED` and claim no gain.

Decide the outcome from the control and treatment values:

- **Better:** the treatment beats the control by more than the run-to-run noise
  you saw. With one run each there is no noise estimate, so count it as better
  only when a pass or fail measure flips from fail to pass. A cost measure
  needs more than one run each. Report `MEASURED` with both values and the
  sample size. A tie, or a difference within the noise, is not better.
- **Not better:** patch the skill once, then rerun only the treatment (step 1)
  or the candidate tasks (step 2) and compare against the control values you
  already recorded. For step 2, base the patch on `train` results only. If
  `sel` outcomes shaped the patch, those tasks are training: replace them with
  untouched holdout tasks or report `UNVERIFIED`. If it is still not better,
  withdraw the write (delete a new skill, revert a patch). Keep the full
  content and state the rollback in the reply. Report `NO GAIN` with both
  values. Never report `MEASURED` for a result that is not better.

Do not build a new evaluation harness in this pass. Use `skillopt` or report
`UNVERIFIED`. A user adopting the skill later is a review, not a measurement.

## Report line

When this gate ran (a capability claim was made), append the capability field
to the step 8 line. A gain you did not measure is never written as `MEASURED`.
Use `Patched <name>. Trigger: "<phrase>".` in place of the first sentence after
a patch:

```text
Skillified as <name>. Trigger: "<phrase>". Capability gain: MEASURED (<before> -> <after>) | UNVERIFIED (<reason>) | NO GAIN (<before> -> <after>; <removed | patch reverted>).
```

After a `NO GAIN` withdrawal, send the line with `removed` or `patch reverted`,
followed by the withdrawn content in a fenced block and the rollback.
