---
name: skillopt
version: 1.0.0
description: Improve a skill, agent file, or prompt through bounded patches and a held-out, per-task acceptance gate. Use when you say `optimize this skill`, `make this skill better`, `compress these skills safely`, `tune this prompt against an eval`, or a skill keeps failing the same way. Refuses unscored improvement claims. Do NOT use to create or route skills (use skillforge) or to decide skill placement or compress markdown without an eval (use context-optimizer).
license: MIT
user-invocable: true
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - validation-gated-skill-evolution
    depends-on: []
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan's long-tail resolver matches a measured skill, agent, or prompt optimization request
    user-facing: true
    intents:
      - optimize this skill
      - make this skill better
      - compress these skills safely
      - tune this prompt against an eval
      - skill keeps failing
      - skill optimization
---

# SkillOpt

> A candidate lands only when it adds at least one held-out pass and loses
> none. No scored eval set means no gate, and no gate means no edit.

SkillOpt treats a skill document as the trainable state of a frozen model.
You run rollouts and reflect on failures. The bundled scripts decide whether
an edit may exist: the edit budget, the patch applier, the protected-section
guard, the rejected-edit buffer, and the acceptance gate are deterministic.
Do not edit the target by hand. Route every edit through the scripts so the
gate is real. Method: Yang et al., arXiv:2605.23904. The paper's reported
gains are its claims; this skill does not reproduce them.

## Triggers

| Phrase | Action |
|--------|--------|
| `optimize this skill` | Run the Process below against a scored eval set |
| `make this skill better` | Same, after the Preconditions pass |
| `compress these skills safely` | Declare a resource task up front, then gate |
| `tune this prompt against an eval` | Same loop with a prompt as the target |
| A skill keeps failing the same way | Mine sessions, confirm the defect, then gate |

## Boundaries

| Need | Owner |
|------|-------|
| Create a skill, find one, or route a request to one | `skillforge` |
| Decide skill vs passive context, or compress markdown with no eval | `context-optimizer` |
| Measured improvement of an existing skill, agent file, or prompt | this skill |
| Held-out optimization of agents, rules, and hooks inside the `rjmurillo/ai-agents` checkout | `optimize-artifact.py` in that repository's eval tooling (not shipped) |

## Preconditions (hard stop if unmet)

1. **Target artifact.** A `SKILL.md`, agent file, or prompt.
2. **Scored eval set.** A nonempty held-out `sel` split with per-task pass or
   fail verifiers (`references/eval-set-format.md`). Without one, stop and say
   so. `score` and `pair-gate` exit 2 on a missing or empty split.
3. **Canonical owner.** Name the versioned source, its generated mirrors, and
   the live install path before any candidate runs. A file in an eval
   workspace is not deployed behavior.
4. **Two isolated runners.** The candidate author and the `sel` runner must
   be separate: a fresh subagent or another session. If the harness cannot
   provide both, do not run skillopt. Report that the gate cannot be
   independent. Replacement holdouts written by the same agent are still
   exposed.

Freeze the `train` and `sel` task lists before authoring any candidate. Keep
`sel` prompts, verifiers, and outcomes away from the candidate author until
the candidate is frozen. If they were exposed, list them under `exposed` in
the manifest, move them to `train`, and add untouched holdout tasks.
`pair-gate` exits 2 while an exposed or invalid task sits in the `sel` split.

## Scripts

Every subcommand takes explicit file paths, so it runs from any working
directory and needs no clone of the source repository. Pure standard library.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skillopt/scripts/skillopt.py" --help
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skillopt/scripts/mine_sessions.py" --help
SKILLOPT_DIR="${SKILLOPT_DIR:-${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skillopt/scripts}"
```

If neither `COPILOT_PLUGIN_ROOT` nor `CLAUDE_PLUGIN_ROOT` is set (for example
Codex, or a plain checkout under PowerShell), use the directory that holds
this SKILL.md. Set `SKILLOPT_DIR` to the `scripts` folder beside it:

```bash
SKILLOPT_DIR="<folder that holds this SKILL.md>/scripts"
python3 "$SKILLOPT_DIR/skillopt.py" --help
```

On Windows PowerShell, no Bash required:

```powershell
if (-not $SkillOptDir) {
    $Root = if ($env:COPILOT_PLUGIN_ROOT) { $env:COPILOT_PLUGIN_ROOT } else { $env:CLAUDE_PLUGIN_ROOT }
    if (-not $Root) { throw 'Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT, or set $SkillOptDir to the scripts folder beside this SKILL.md' }
    $SkillOptDir = Join-Path $Root 'skills\skillopt\scripts'
}
$SkillOpt = Join-Path $SkillOptDir 'skillopt.py'
py -3 $SkillOpt --help
```

Below, `skillopt.py` means that resolved path. References use `$SKILLOPT_DIR`
(`$SkillOptDir` in PowerShell) for the same folder.

| Command | Exit codes |
|---------|------------|
| `skillopt.py budget`, `apply`, `score`, `buffer-add` | 0 success, 2 usage or validation error |
| `skillopt.py gate`, `pair-gate` | 0 accept, 1 reject, 2 usage or validation error |
| `skillopt.py hash FILE...` | 0 digests printed |
| `skillopt.py hash FILE --expect SHA` | 0 match, 1 `MISMATCH`, 2 usage or validation error |
| `skillopt.py buffer-check` | 0 `KNOWN-BAD` (discard), 1 `NOVEL` (proceed), 2 usage or validation error |
| `mine_sessions.py sources`, `rank`, `tasks`, `collect`, `merge` | 0 success, 2 usage or validation error |

`buffer-check` is inverted on purpose: exit 0 means the edit was already
rejected. Branch on the printed word or the exact code, never on `&&`.

Modules named `_skillopt_*.py` and `_mine_*.py` are internal helpers the
two entry scripts import. Do not call them directly.

## Process

One optimization step:

1. **Baseline.** Split the roles first. The candidate author sees only
   `train` tasks and their results. A separate runner, such as a fresh
   subagent or another session (Precondition 4), holds the `sel` prompts,
   verifiers, and results until the candidate is frozen, and reports only
   the verdict back.
   Each runner preflights its own tasks: prompt, verifier, inputs, fixtures,
   and permitted scope. Run the rollout under exactly the scope the task grants.
   A rollout with the wrong artifact or a scope change is invalid, not a pass
   or a fail; mark the task `"status": "invalid"` and replace it. Grade the
   complete persisted output against every clause of the verifier. A runner's
   self-check or summary is not proof. A clipped or missing answer is
   `"UNVERIFIED"` in the results file, which the gate refuses to count.
   Record `{"task_id": true|false}` to `incumbent_results.json` and hash the
   incumbent: `skillopt.py hash target.md`. When the manifest sets
   `"scorer": "nondeterministic"`, the `sel` runner also reruns the
   byte-identical incumbent into `null_results.json` now (see Before
   promotion, step 2).
2. **Budget.** `skillopt.py budget --step T --total N` prints L_t, the
   cosine-decayed cap on atomic patches this step.
3. **Reflect.** Failures become corrective rules; successes become behaviors
   to preserve. Write at most L_t patches to `patches.json`. Use only `train`
   evidence.
4. **Buffer check.** `skillopt.py buffer-check --buffer rejected.jsonl
   --patches patches.json`. Exit 0 prints `KNOWN-BAD`: discard and reflect
   again. Exit 1 prints `NOVEL`: proceed.
5. **Apply to a candidate.** `skillopt.py apply --skill target.md --eval
   eval.json --patches patches.json --budget L_t --out candidate.md`. The
   incumbent is never written; an `--out` that resolves to the incumbent exits
   2. Exit 2 is a usage or validation error, not a gate loss: an empty `sel`
   split, an incumbent `--out`, budget overflow, a bad anchor, a protected
   fence, or marker text inside a patch.
6. **Re-roll** every task on `candidate.md` into `candidate_results.json`.
   The `sel` runner does the `sel` half.
7. **Gate.** `skillopt.py pair-gate --eval eval.json --incumbent-results
   incumbent_results.json --candidate-results candidate_results.json`. For a
   nondeterministic scorer, add `--null-results null_results.json
   --incumbent-sha256 <sha> --null-sha256 <sha>`; without them the gate exits
   2.
   - Exit 0, `ACCEPT_PARETO`: at least one held-out gain, zero held-out
     regressions, every held-out result a literal boolean.
   - Verdict precedence: `REJECT_UNVERIFIED` first (a missing or non-boolean
     result), then `REJECT_NULL_CONTROL` (the null run moved and no genuine
     gain remains), then `ACCEPT_PARETO` or `REJECT`.
   - Exit 1, `REJECT`, `REJECT_UNVERIFIED`, or `REJECT_NULL_CONTROL`: record
     it with `skillopt.py buffer-add --buffer rejected.jsonl --patches
     patches.json --score <cand> --incumbent <best> --note "..." --step T`.
8. **Repeat** until the budget reaches its floor and several steps reject, or
   the step budget runs out.

Use `pair-gate` as the acceptance decision. Scalar `gate --candidate X
--incumbent Y` (exit 0 `ACCEPT`, exit 1 `REJECT`, ties reject) is only for a
single-objective experiment declared before the candidate existed. A resource
objective such as context reduction may be one `sel` task with
`"kind": "resource"`, declared before candidate creation. It cannot offset a
semantic regression, because `pair-gate` rejects any regression.

## Before promotion

`ACCEPT_PARETO` is necessary, not sufficient:

1. **Training review.** Run `pair-gate --split train` and read its
   `regressions`. A lost training pass on a load-bearing verifier blocks
   promotion. If fixing it changes the candidate, freeze a fresh `sel` set.
2. **Null control** for nondeterministic scorers. It runs at baseline and
   feeds the step 7 gate. Set `"scorer": "nondeterministic"` in the manifest;
   `pair-gate` on `sel` then exits 2 without `--null-results`. Rerun the
   byte-identical incumbent (confirm with
   `skillopt.py hash target.md --expect <sha256>`, exit 1 on `MISMATCH`) into
   `null_results.json`, then pass `--null-results null_results.json
   --incumbent-sha256 <sha> --null-sha256 <sha>` to `pair-gate`, using the
   digests `hash` printed for the incumbent and for the file the null run
   used. Both are required, and a mismatch exits 2. A gain the no-op also
   produced is noise; if no genuine gain remains the verdict is
   `REJECT_NULL_CONTROL`.
3. **Evidence.** Keep incumbent, candidate, patches, every results file, the
   pair report, hashes, `rejected.jsonl`, and one line of evidence per task.

## Promotion

1. Confirm the canonical source still hashes to the evaluated incumbent.
2. Apply the accepted candidate to the canonical source, not to an eval copy
   or a generated mirror.
3. Hash the canonical source after applying it
   (`skillopt.py hash canonical.md --expect <candidate sha256>`). It must
   equal the accepted candidate's hash before you check the live copy.
4. Regenerate mirrors, run the owner's tests, and load the skill once.
5. Commit and push through the owner's repository workflow.
6. Reload the live skill and confirm its hash matches the canonical file.

If any step stops short, report `ACCEPTED_NOT_DEPLOYED`. Never call an
eval-workspace candidate installed.

## Protected sections

Fence guidance that step edits must never touch:

```text
<!-- SLOW_UPDATE_START -->
Durable guidance changed only by hand, at epoch boundaries.
<!-- SLOW_UPDATE_END -->
```

Contract: `references/slow-section-convention.md`.

## Finding targets from sessions

`mine_sessions.py` ranks skills by usage and a weak correction signal from
local transcripts, and pulls the prompts that triggered a skill:

- `sources` lists each supported source and whether it is available.
- `rank`, `tasks --skill X`, `collect --out PATH`, `merge`.
- `--patterns patterns.json` reads a `session-patterns/1` handoff instead of
  transcripts.

Supported sources: Claude Code transcripts (`~/.claude/projects/**/*.jsonl`)
and the GitHub Copilot CLI session store (`~/.copilot/session-store.db`),
both resolved from the user's home directory on Linux, macOS, and Windows.
Any other harness is unsupported; supply a `session-patterns/1` file
instead. A missing source is skipped, never an error; `sources` shows which
ones were found, and a run with no source at all prints a note to stderr. Session
data stays local; keep extracted prompts out of git unless the user names
another destination.

A correction nominates a candidate. It is not a gold label. Confirm the
defect in the target and in two distinct sessions before funding rollouts.
Workflow: `references/cross-machine-mining.md`.

## Limits

The gate needs tasks with checkable pass or fail outcomes. A style guide or
taste document with no measurable success signal has no `sel` split, so the
gate cannot run. Say that you are flagging, not gating, and do not invent a
score to make the gate pass.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Editing the target by hand | The gate never sees the edit | Route every edit through `apply` |
| Promoting on a higher aggregate score | It can hide a lost behavior | Use `pair-gate` |
| Reflecting on `sel` tasks | That trains on the test set | Reflect on `train` only |
| Treating a correction as a defect | Corrections are weak signals | Confirm in the target and two sessions |
| Calling an accepted candidate installed | Acceptance is not deployment | Report `ACCEPTED_NOT_DEPLOYED` until promoted |

## Verification

- [ ] `eval.json` has a nonempty `sel` split frozen before the candidate.
- [ ] No `sel` task is exposed or invalid.
- [ ] The incumbent hash is recorded and unchanged after `apply`.
- [ ] `pair-gate` returned `ACCEPT_PARETO` with no unverified task.
- [ ] Training regressions were reviewed.
- [ ] A null control ran when the scorer is nondeterministic.
- [ ] The live copy hashes to the canonical source, or the report says
      `ACCEPTED_NOT_DEPLOYED`.

## Extension Points

- A new acceptance rule belongs in `pair-gate`, with a test, not in prose.
- A new session source belongs in `mine_sessions.py sources` and its table
  in `references/cross-machine-mining.md`.

## Close-out

After each run, check this skill and its references for a reusable lesson
from a user correction, failed verifier, or tool discovery. Patch the
class-level guidance; do not add an incident-named reference.

## References

- `references/eval-set-format.md`: eval manifest, patch, and results schemas.
- `references/slow-section-convention.md`: protected-fence contract.
- `references/mechanism.md`: the training analogy and paper citation.
- `references/cross-machine-mining.md`: session sources and the handoff.
- `references/example-eval.json` with `example-incumbent-results.json` and
  `example-candidate-results.json`: a runnable `pair-gate` example.
