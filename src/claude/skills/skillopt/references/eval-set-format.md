# Eval set, patch, and results schemas

Three small JSON files drive one optimization step. The bundled
`skillopt.py` reads all of them. The eval set is the contract that makes
the gate real, so build it first.

## 1. Eval manifest (`eval.json`)

Names the tasks and which task ids are held out for the gate. The JSON below
is an excerpt; `example-eval.json` is a full, runnable manifest.

```json
{
  "skill": "programming-advisor",
  "splits": {
    "train": ["t1", "t2", "t3", "t4", "t5", "t6"],
    "sel": ["t7", "t8", "t9", "t10"]
  },
  "exposed": [],
  "scorer": "deterministic",
  "tasks": {
    "t1": {
      "prompt": "Is there a stdlib way to do X in Python?",
      "verifier": "answer names a real stdlib module and cites docs",
      "kind": "semantic"
    }
  }
}
```

- `splits.train`: tasks the optimizer reflects on.
- `splits.sel`: the held-out split. The gate scores only this split. Never
  reflect on `sel` tasks; that is training on the test set.
- `exposed`: optional list of task ids whose prompt, verifier, or outcome the
  candidate author saw at any point in the run. `pair-gate` exits 2
  while any of them is in the `sel` split. The check covers `sel` only, so
  `train` may hold exposed tasks and a `--split train` review still works.
  Move exposed tasks to `train` and add untouched holdout tasks.
  Deterministic tasks taken from a written spec before any candidate exists
  are frozen once their list and verifiers stop changing, but freezing is not
  isolation. When one agent writes those tasks and the candidate, list them
  here and keep them in `train`. They count as `sel` only when a different
  author or session wrote them and kept them from the candidate author.
  Replacement holdouts must come from an author who has not seen the
  candidate. If the candidate author also writes them, they are exposed too.
- `tasks[id].status`: optional. `"invalid"` or `"exposed"` marks a task that
  cannot count. `pair-gate` exits 2 while such a task is in the `sel` split.
  A `status` that is present but not a string exits 2, and so does a `tasks`
  value that is not an object.
  Use `"invalid"` for missing inputs, a verifier that demands unsupported
  work, a scope violation, or a rollout run against the wrong artifact.
- `scorer`: optional, `"deterministic"` or `"nondeterministic"`. Absent
  means no extra requirement. With `"nondeterministic"`, `pair-gate` on `sel`
  exits 2 ("nondeterministic scorer requires --null-results") until you pass a
  null control. Any other non-null value exits 2.
- `tasks[id].verifier`: how pass or fail is decided. Prefer a deterministic
  check (exit code, exact match, a script) over a judgment. For a task with
  no `command`, the scripts do not run the verifier; you do, and you write the
  result into the results file. A task with a `command` can be run by
  `skillopt.py run` (see Command tasks below).
- `tasks[id].kind`: optional `semantic`, `resource`, or `safety`. A resource
  task may encode a threshold declared up front, such as total bytes reduced by
  at least 15%. Adding a resource objective after seeing the candidate is
  test-set editing. A `safety` task must pass in the candidate whether or not
  the incumbent passed it; `efficiency-gate` enforces this for every safety
  task in the gated split. On the default `sel` split, a safety task that is
  not listed in `splits.sel` exits 2, because the gate would never check it.
- `efficiency`: optional object, required only by `efficiency-gate`. It names
  the cost, latency, or token gain you are claiming. Write it into the
  manifest before you author the candidate. All five fields are required:

```json
{
  "efficiency": {
    "metric": "total_tokens",
    "direction": "lower",
    "min_relative_gain": 0.10,
    "null_tolerance": 0.03,
    "min_repeats": 3
  }
}
```

- `metric`: a label for the report, such as `total_tokens` or `wall_ms`.
- `direction`: `lower` when smaller is better (cost, latency, tokens), or
  `higher` when larger is better (throughput).
- `min_relative_gain`: number above 0 and below 1. The candidate must beat
  the incumbent by at least this fraction. `0.10` means 10 percent.
- `null_tolerance`: number above 0 and below `min_relative_gain`. The largest
  relative change the null control may show. A null control that moves more
  than this means the measurement is too noisy to trust. It is also the
  largest cost increase any single task may show. A value at or above
  `min_relative_gain` exits 2, because the null control could not rule out
  noise at the claimed gain.
- `min_repeats`: whole number, at least 3. Every task needs at least this
  many measurements in every arm. With 2 repeats the median equals the
  mean, so one lucky repeat would move it. A smaller value exits 2.

  The gate cannot see when you wrote this object. Commit `eval.json` before
  you author the candidate, and never edit these numbers after you see results.
  If the candidate already exists and the object does not, the claim was not
  declared in advance. Do not run the gate. Tell the user.

A manifest with no `sel` split, an empty one, a duplicate id, or a non-string
id makes `score` and `pair-gate` exit 2. No held-out split, no gate.

### Command tasks (`skillopt.py run`)

A task with a `command` is a deterministic verifier that `run` executes
against a bundle directory and records as `true`, `false`, or `"UNVERIFIED"`.

```json
"t7": {
  "prompt": "audit-draft flags the banned phrase",
  "verifier": "exit 1 and prints one finding",
  "command": ["python3", "scripts/audit-draft.py", "--check", "fixtures/draft.md"],
  "timeout": 30,
  "expect_exit": 1,
  "expect_stdout": "1 finding"
}
```

- `command`: an argv list. A string is refused: there is no shell, so no
  pipes, redirects, globbing, or `$VAR` expansion. Wrap shell syntax in a
  script inside the bundle and run that script.
- `timeout`: required, in seconds, greater than 0 and at most 600. A task
  that exceeds it is killed with its process group and recorded as
  `"UNVERIFIED"`, so a hung candidate cannot be scored as a pass.
- `expect_exit`: integer exit status. Defaults to 0 when only
  `expect_stdout` is set. At least one of `expect_exit` and `expect_stdout`
  is required, so a verifier is never implicit.
- `expect_stdout`: exact stdout text. `\r\n` counts as `\n`, and trailing
  newlines are ignored on both sides. When both expectations are set, both
  must hold. A task that writes more than 1 MiB to stdout is killed and
  fails, whether or not `expect_stdout` is set.
- Working directory is the bundle root. Stdin is closed and stderr is
  discarded. The environment keeps only `PATH`, `PATHEXT`, `SYSTEMROOT`,
  `LANG`, `LC_ALL`, `LC_CTYPE`, `TMPDIR`, `TEMP`, and `TMP`, plus
  `PYTHONIOENCODING=utf-8` and a `PYTHONPYCACHEPREFIX` outside the bundle.
  Tokens in the caller's environment do not reach the task, and Python
  neither writes bytecode into the bundle nor loads a stale `.pyc` from it.
- A task that could not start (the binary is missing) is `"UNVERIFIED"`.
- On POSIX the task runs in its own process group. A timeout kills the whole
  group, and the group is also killed after the task exits, so no background
  process in that group outlives its task. A process that starts its own
  session escapes it. On Windows only the direct child is killed.
- `PATH` keeps only its absolute entries, so a bare command name cannot
  resolve to a file inside the bundle through a `.` or empty entry.
- A task with no `command` is skipped and left out of the results file, which
  `pair-gate` reports as `REJECT_UNVERIFIED`. Run `run` first, then grade
  those tasks yourself and add them: each `run` replaces its results file.
- A task id named by a split but absent from `tasks` exits 2, so a typo cannot
  pass as a semantic task. A copy that drops the `sel` task bodies must run
  with `--split train`.

**Security.** `eval.json` is executable input. Every `command` runs as you
and may start any binary on `PATH`, so only run an `eval.json` you wrote or
reviewed. `run` refuses these before any task starts, with exit 2:
a non-list `command`, an empty command, a non-string or NUL-containing
argv entry, a missing or out-of-range `timeout`, a missing expectation, any
argv entry (or the value after any `=`, or after a short option such as
`-I`) that is an absolute path or has a `..` segment, and an `argv[0]` containing a path separator that resolves
outside the bundle after symlinks. These are string checks on the literal
argv. They are not a sandbox: a program you name can still read or write
anywhere your account can. Use a container or a throwaway account for an
`eval.json` you did not write.

Use `python3` or another bare name for the interpreter; an absolute path is
refused. Run the incumbent and the candidate bundle with the same `eval.json`:

```bash
python3 "$SKILLOPT_DIR/skillopt.py" run --eval eval.json --bundle incumbent/ --role incumbent --out-dir results/
python3 "$SKILLOPT_DIR/skillopt.py" run --eval eval.json --bundle candidate/ --role candidate --out-dir results/
```

`--role` is `incumbent`, `candidate`, or `null` and names the file
(`incumbent_results.json`, `candidate_results.json`, `null_results.json`).
`--split NAME` runs one split; the default runs every split. `--out-dir`
defaults to the current directory and must not sit inside the bundle. Stdout
is a JSON summary with `bundle_sha256`, counts, and a short reason per task;
it never echoes task output. Exit 0: results written. Exit 1: results
written, at least one task `"UNVERIFIED"`. Exit 2: refused or invalid; no
results written.

`run` hashes the bundle before the tasks and again after each task. A task
that edits the bundle fails the run with exit 2 and no results file, and the
error names the task. The bundle is not restored, so keep it under version
control. An exit 2 leaves any earlier results file untouched, so
check the exit code before passing a results file to `pair-gate`.

### Bundle directories

A bundle is a skill directory: `SKILL.md` plus its script folders, reference
files, and fixtures. A candidate that changes a bundled script is a different
artifact even when `SKILL.md` is identical, so identity covers the whole tree.

- `skillopt.py hash DIR` prints one sha256 for the directory. The digest
  covers each regular file by relative POSIX path and content, in sorted
  order. It skips `__pycache__` and ignores empty directories, file modes, and
  timestamps. A symlink anywhere in the tree exits 2.
- `skillopt.py apply --skill DIR --out NEWDIR ...` copies the bundle to a new
  directory and applies the patches to its `SKILL.md`. `--out` must not exist
  and must not sit inside, or contain, the incumbent. It prints the candidate
  bundle digest. If the candidate also changes a script, edit it in `NEWDIR`
  after `apply`, then `hash NEWDIR` again: the new digest is the candidate's
  identity, and `run --bundle NEWDIR` records that digest in its summary.
- `hash DIR --expect SHA` checks a directory the same way as a file.

## 2. Patches (`patches.json`)

A list of atomic edits, capped at the step's budget L_t. An anchor matches a
whole line by its exact, unique content. A missing or ambiguous anchor rejects
the whole batch.

```json
[
  { "op": "append", "text": "## New rule\n\nAlways cite the source." },
  { "op": "insert_after", "anchor": "## When to use", "text": "- case Y" },
  { "op": "replace", "anchor": "old line text", "text": "new line text" },
  { "op": "delete", "anchor": "line to remove" }
]
```

- `append` ignores `anchor` and adds `text` as trailing lines.
- `insert_after`, `replace`, and `delete` require a unique `anchor`.
- `text` may contain `\n` for multi-line insertions.
- Any patch that would change a protected slow section is rejected.
- A patch whose `text` contains `SLOW_UPDATE_START` or `SLOW_UPDATE_END` is
  rejected for `append`, `insert_after`, and `replace`, so a patch cannot open,
  close, or forge a fence. After the last patch the document's fences must
  still be well formed.
- CRLF documents keep their line endings.

## 3. Results (`*_results.json`)

Per-task outcomes recorded after one rollout. The incumbent, the candidate,
and any null control each get their own file. `skillopt.py run` writes these
for command tasks.

```json
{ "t7": true, "t8": false, "t9": true, "t10": "UNVERIFIED" }
```

- Only literal `true` is a pass. `1`, `"yes"`, and other truthy values are
  not passes, so a sloppy verifier cannot inflate the score.
- `score` counts a missing or non-boolean held-out entry as a fail.
- `pair-gate` is stricter. A missing or non-boolean held-out entry in any
  compared file makes the verdict `REJECT_UNVERIFIED`. Write `"UNVERIFIED"`
  for a clipped, missing, or contradictory answer until a full artifact or a
  rerun settles it.
- Keep evidence notes in the pair report or scoring notes, not here.

## 4. Efficiency measurements (`measurements.json`)

Used only by `efficiency-gate`. Three arms, each a map from `sel` task id to a
list of numbers. Measure all three arms the same way, on the same machine.

```json
{
  "incumbent": { "t7": [1200, 1180, 1215], "t8": [900, 910, 905] },
  "candidate": { "t7": [980, 1000, 990], "t8": [700, 705, 698] },
  "null":      { "t7": [1190, 1210, 1200], "t8": [902, 899, 908] }
}
```

- `incumbent`: the current skill, measured now.
- `candidate`: the edited skill.
- `null`: a second run of the byte-identical incumbent. It shows how far the
  metric moves when nothing changed. If it moves, the candidate gain is noise.
- Every value must be a number that is 0 or more. Strings, booleans, `null`,
  `NaN`, negative numbers, and integers too large for a float are rejected as
  `measurements_invalid`.
- Every task needs the same number of values in all three arms. A task with 50
  incumbent values and 3 candidate values is `measurements_unmatched`. Run the
  same plan in every arm.
- The gate takes the median of each task's repeats and sums the medians over
  the `sel` split for each arm. With `direction: lower`, gain is
  `(incumbent total - candidate total) / incumbent total`. With
  `direction: higher`, gain is `(candidate total - incumbent total) / incumbent
  total`. `null_gain` uses the same formula with the null arm in place of the
  candidate. One lucky repeat cannot move a median.
- A median hides a heavy upper tail, such as `[80, 80, 1000]` against a
  baseline of 100. So the gate also computes `mean_gain` with the same formula
  on the summed per-task means. Both gains must clear `min_relative_gain`. A
  candidate that is cheaper at the median but costs more on average is
  rejected as `mean_gain_below_threshold`. If `mean_gain` is not larger than
  the absolute `null_mean_gain`, the gate adds `mean_gain_within_null`.
- A saving smaller than the spread between repeats is noise even when one null
  run looks quiet. So the gate also compares the candidate's worst repeats with
  the incumbent's best repeats. With `direction: lower`, `worst_case_gain` is
  `(sum of incumbent per-task minimums - sum of candidate per-task maximums) /
  sum of incumbent per-task minimums`. With `direction: higher`, it is
  `(sum of candidate per-task minimums - sum of incumbent per-task maximums) /
  sum of incumbent per-task maximums`. A value of 0 or less means the two ranges overlap, and the
  gate reports `gain_within_spread`. The report shows `null` when the
  incumbent's best total is 0, and that also rejects.
- The null arm gets the same two checks. `null_gain` uses the medians and
  `null_mean_gain` uses the means. If either moves more than
  `null_tolerance`, the gate reports `null_too_wide`. A 100x outlier in a
  rerun of the byte-identical incumbent is direct evidence of a noisy metric,
  even when the null median sits still.
- The null arm also gets a per-task check, because offsetting outliers on
  different tasks can cancel in the summed gains. If any one task's null
  median or mean differs from the incumbent's by more than `null_tolerance`,
  the gate reports `null_too_wide` even when `null_gain` and `null_mean_gain`
  are both 0. When the incumbent's value for that task is 0, any nonzero null
  value counts. `null_wide_tasks` names those tasks.
- The measurement method is yours: count tokens, time the run, or read the
  cost from the harness. Use the identical method in all three arms.

## Scoring and gating

Run with `$SKILLOPT_DIR` from SKILL.md, from any directory:

```bash
python3 "$SKILLOPT_DIR/skillopt.py" pair-gate --eval eval.json --incumbent-results incumbent_results.json --candidate-results candidate_results.json
```

On Windows:

```powershell
py -3 (Join-Path $SkillOptDir 'skillopt.py') pair-gate --eval eval.json --incumbent-results incumbent_results.json --candidate-results candidate_results.json
```

Optional flags: `--split NAME` (default `sel`) and `--null-results FILE`. A
null control also needs `--incumbent-sha256` and `--null-sha256`, the digests
`skillopt.py hash` printed for the incumbent and for the file the null
run used. A missing digest, or two that differ, exits 2 ("null control did not
run on the byte-identical incumbent").

The report is JSON on stdout:

| Key | Meaning |
|-----|---------|
| `verdict` | `ACCEPT_PARETO`, `REJECT`, `REJECT_UNVERIFIED`, `REJECT_NULL_CONTROL`, or `REJECT_CEILING` |
| `gains` | Tasks the candidate passes and the incumbent does not |
| `regressions` | Tasks the incumbent passes and the candidate does not |
| `unverified` | Tasks with a missing or non-boolean result in any file |
| `null_gains`, `null_regressions` | Flips a byte-identical rerun of the incumbent produced |
| `genuine_gains` | `gains` minus `null_gains` |
| `hint` | Present only with `REJECT_CEILING`: the next step |

Exit 0 only for `ACCEPT_PARETO`. It needs a gain, zero regressions, no
unverified task, and, with a null control, at least one genuine gain. Exit 1
for every reject. Exit 2 for an invalid manifest or input file.

`REJECT_CEILING` means the incumbent passes every task in the `sel` split and
the candidate regresses none. No gain is possible, so the gate cannot accept
any candidate, even one with real training gains. It outranks `REJECT` and
ranks below `REJECT_UNVERIFIED` and `REJECT_NULL_CONTROL`. It applies to the
`sel` split only. Freeze a new `sel` set of harder tasks that sample the
failure mode, re-score the incumbent on it, then author a fresh candidate.
Never re-gate this candidate on tasks written after it: its author already
knew the failure mode, so those tasks are not held out. For a first draft
whose `sel` tasks came from its own requirements, hand back to `skillforge`.

When the only claim is a pre-declared cost, latency, or token gain at the
ceiling, use `efficiency-gate` (below) instead of authoring harder tasks.

`score` prints the held-out pass rate. Scalar `gate` compares two numbers and
rejects ties. Neither is the default promotion decision.

### Efficiency gate

Use the efficiency gate only when the claim is a cheaper or faster candidate
that has no new held-out pass, such as a skill already at the accuracy ceiling:

```bash
python3 "$SKILLOPT_DIR/skillopt.py" efficiency-gate \
  --eval eval.json \
  --incumbent-results incumbent_results.json \
  --candidate-results candidate_results.json \
  --measurements measurements.json
```

It prints one JSON report. Exit 0 means `ACCEPT_EFFICIENCY`. Exit 1 means
`REJECT`, and `reasons` lists why; every code in the table below exits 1.
Exit 2 means the gate could not run: an eval manifest with no `efficiency`
object or a malformed one, a `tasks` value that is not an object, a missing `sel` split (or the split you pass with
`--split`), a `kind: safety` task that is not in the `sel` split, an exposed or invalid task in the `sel` split (the same refusal as `pair-gate`), or an input
file that is missing, unreadable, not valid JSON, or not a JSON object. The same file errors exit 2 for every subcommand that reads
JSON. Exit 2 is not a
verdict on the edit. Fix the input and rerun. `--split` defaults to `sel`.
Safety tasks and the other checks apply only to the tasks in that split. The
safety-task membership check runs only for `sel`. Only a `sel` run can support
promotion. Run `--split train` for diagnosis only.

| Reason code | Meaning | Fix |
|---|---|---|
| `unverified_correctness` | A `sel` task has no real `true` or `false` in the incumbent or candidate results. | Run the verifier for every `sel` task in both arms. |
| `incumbent_below_ceiling` | The incumbent failed a `sel` task. Efficiency is the claim for an incumbent that already passes every `sel` task. | Use `pair-gate`. Do not claim efficiency on a failing skill. |
| `correctness_regression` | The incumbent passed a `sel` task and the candidate did not. | Reject the edit. Do not retune the threshold. |
| `safety_failure` | A task with `kind: safety` failed in the candidate. | Reject the edit. |
| `measurements_missing` | An arm, a task, or a repeat list is absent. | Measure every task in all three arms. |
| `measurements_short` | A task has fewer than `min_repeats` values in some arm. | Add repeats. |
| `measurements_unmatched` | A task has a different number of values in different arms. | Run the same number of repeats for every task in every arm. |
| `measurements_invalid` | A value is not a number of 0 or more (this includes an integer too large for a float), a sum or mean overflows, or the incumbent total is 0. | Fix the measurement run. |
| `null_too_wide` | The null control's summed median gain or mean gain moved more than `null_tolerance`, or one task's null median or mean strayed from the incumbent by more than `null_tolerance` (a nonzero value when the incumbent is 0). The summed gains can both read 0 in the per-task case. | The metric is too noisy. `null_wide_tasks` names the tasks that strayed. Reduce noise and remeasure. |
| `gain_below_threshold` | The gain is under `min_relative_gain`. | Reject the edit. |
| `gain_within_null` | The gain is not larger than the null control's own change. | Reject the edit. |
| `mean_gain_within_null` | The mean gain is not larger than the null control's own mean change. | Reject the edit. |
| `gain_within_spread` | The candidate's worst repeats do not beat the incumbent's best repeats on the summed total. The saving is inside the run-to-run spread. | Reject the edit. Reduce noise or add repeats and remeasure. |
| `task_cost_regression` | One task got worse by more than `null_tolerance`, or went from a cost of 0 to more than 0. The summed gain can hide it. | Reject the edit. `task_cost_regressions` names the tasks. |
| `mean_gain_below_threshold` | The median gain clears the threshold but the mean gain does not. A heavy upper tail makes the candidate cost more on average. | Reject the edit. Look at the slow repeats before you retry. |

The report also holds `gain`, `mean_gain`, `null_gain`, `null_mean_gain`,
`worst_case_gain`, `per_task_gain`, `task_cost_regressions`, and
`null_wide_tasks`. `per_task_gain`
is the same gain formula applied to one task, or `null` when that task's
incumbent median is 0. A negative value means that task got worse. The gate
rejects a task that got worse by more than `null_tolerance` as
`task_cost_regression`, so a large task cannot hide a regression on a small
one. A smaller worsening passes, so still read `per_task_gain` before you
promote. If one task got worse and you are unsure it is noise, do not promote.
Tell the user which task and by how much. Do not edit the manifest to make it
pass.
