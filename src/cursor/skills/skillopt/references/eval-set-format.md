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
- `tasks[id].kind`: optional `semantic` or `resource`. A resource task may
  encode a threshold declared up front, such as total bytes reduced by at
  least 15%. Adding a resource objective after seeing the candidate is
  test-set editing.

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

`score` prints the held-out pass rate. Scalar `gate` compares two numbers and
rejects ties. Neither is the default promotion decision.
