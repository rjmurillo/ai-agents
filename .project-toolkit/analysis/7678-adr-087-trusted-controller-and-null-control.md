# ADR-087: the trusted controller and the first agent-path null control

Detail for the ADR-087 amendment of 2026-11-25. Issues #7642 and #7678.
The ADR keeps the decision and its condition. This file keeps the mechanism and the numbers.

## Tracking

Each Open Requirement now has a sub-issue of #7642:

| Open Requirement | Issue | State on 2026-11-25 |
| --- | --- | --- |
| 1, trusted controller | #7678 | Built, see below; closes with this change |
| 2, provenance binding | #7679 | Closed, discharged by #3436 |
| 3, boolean seam decision | #7680 | Open |
| 4, governance document | #7681 | Open |
| 5, live rule-path run | #7682 | Closed, done 2026-07-27 |
| 6, rule run-count floor | #7683 | Open |
| 7, test-group reveal | #7684 | Open; `optimize-artifact.py report` may already discharge it |
| 8, Thresholdout study | #7685 | Open |
| 9, initial-cap policy | #7686 | Open; the controller path takes the cap from launcher config |
| 10, fixed ledger root | #7687 | Open; the controller path takes the root from launcher config |
| 11, expiring lock | #7688 | Open |
| 12, corpus namespace | #7689 | Open |

## The controller

`scripts/eval/eval_controller.py` inverts the loop. The launcher runs the controller.
The controller runs the scorer, `extract`, `split`, and `gate` itself.
It runs the optimizing agent as a child proposer, once per step.
`scripts/eval/_controller_config.py` holds config loading, layout checks, and
the access rule. `scripts/eval/_controller_io.py` holds digests, child
processes, and artifact I/O.

### What the proposer sees

The controller empties the proposer workspace each step, then writes two things:

- `feedback.json`, with the step number, the artifact path, the optimize-group
  results of the current incumbent and their pass fraction, the consultations
  left, and `last_decision`;
- copies of the optimize-group task files, when the config names them. A
  missing file stops the run rather than giving the proposer a partial set.

`last_decision` is `ACCEPT` or `REJECT` after a gated step. It is `NO_CHANGE`
when the proposer left the artifact alone, which spends no consultation. So a
gated candidate teaches the proposer one bit.

Emptying the workspace closes a channel. Candidate code run by the scorer could
otherwise leave held-out data there for the next proposer step.

### What stays with the controller

Scorer output, every results file, the split, the ledger, the full gate
payloads, and child stderr stay in the state directory. A failed call's output
goes to the controller log, not to the launcher's stderr. The log records a
timestamp, a session id, each call's duration, and an `abort` event when a run
stops early.

### Guards on the artifact

- Every exit from a step restores the incumbent before the gate. That covers a
  failed proposer, a failed scorer, a timeout, and SIGTERM, which the
  controller turns into an exception so the restore still runs. A SIGTERM that
  arrives during the restore waits until the incumbent is written. A failed
  baseline scoring run restores the incumbent too.
- The gate log records each candidate's SHA-256.
- Only an ACCEPT writes the candidate back.
- The controller re-reads the artifact after scoring and refuses to gate if it
  changed.
- It refuses an artifact the proposer replaced with a symlink, a hard link, or
  a directory.
- It writes the artifact by swapping the directory entry, with the original
  mode, so the write never follows a link.
- The final digest it reports is read from disk.

### Guards on the controller's own inputs

- The config must name the task-definition paths (`deny_paths`). A deny path
  may not overlap the state directory, the config, the workspace, or the
  artifact.
- The controller digests `deny_paths`, every entry under `scripts/eval/`
  (its own code and the gate's, directories included, so a planted package is
  caught), and any `trusted_paths` the config names, such as the scorer's own
  files. It checks those digests before and after each scoring run and after
  each step, and stops on any change. The optimizer runs with
  `PYTHONPYCACHEPREFIX` under the state directory, and each scorer run with it
  inside that run's own directory, so a planted cache beside trusted code is
  never read.
- After each scoring run, including the baseline, the artifact must still be
  the bytes that were scored.
- The state directory and the workspace may not sit inside trusted code, where
  the controller's own writes would read as tampering.
- `inputs` must sit under the run directory, a report already at a `collect`
  path stops the run, and a task-file path through a linked directory is
  refused. An unreadable protected root is refused, not read as missing.
  Bytecode caches are skipped only under `scripts/eval/`.
- SIGINT is handled like SIGTERM, so Ctrl+C cannot unwind a restore.
- Task ids come from scorer output. An id with a path separator, or `.` or
  `..`, is refused before it fills `opt_task_files`. A task file that is a
  link, or two task files with the same name, stop the run.
- A launcher may name a tracked symlink as the artifact. The controller
  resolves it once, at config load, and works on the target file. It resolves
  `state_dir`, `workspace_dir`, `deny_paths`, and `trusted_paths` the same
  way, so a symlinked directory is digested by its contents.
- Around each scoring run, it digests the whole state directory except the new
  run's output directory, and stops if anything else changed.
- The gate cap is `max_consultations` from the config. The ledger root is
  `state_dir/ledger`, set through `EVAL_LEDGER_DIR` for the gate only. The
  proposer gets `PATH` plus the variables the required `proposer_env` names,
  so scorer credentials never reach it by default. `EVAL_LEDGER_DIR` never
  passes.
- A gate exit of 1 counts as a decision only when the gate actually compared.
  The gate also exits 1 to refuse without comparing (split drift, corpus
  mismatch, a guard). A refusal spends no consultation and stops the run.

### Child processes

A scorer call succeeds on the exit codes `scorer_exit_codes` names (default
`[0]`). pytest exits 1 when any test fails, and the rule scorer exits 1 on a
negative verdict, so those launchers name `[0, 1]`. A failed scorer's
`collect` outputs are still moved into state, since they may hold held-out
outcomes.

Scorer, proposer, and optimizer calls each have a timeout (`timeout_seconds`,
default 3600). Child output goes to files, not pipes, so a lingering
descendant cannot stretch the timeout. On POSIX the controller kills each
call's process group when the call ends. A descendant that leaves the group
with `setsid` survives that, and on Windows only the direct child is killed.
The post-score byte check and the integrity checks are what remain then.

### The access rule

`eval_controller.py policy` prints the rule the launcher must apply:

- `deny_read_write`: the state directory, the config file, and every
  `deny_paths` entry;
- `deny_write`: the `scripts/eval/` directory and every `trusted_paths` entry;
- `deny_read_write_collect`: the `collect` templates, whose reports wait there
  until the controller moves them;
- `proposer_may_write`: the artifact. `proposer_workspace` names the workspace,
  which must be absent or empty at start and must not contain the artifact.

The config is on the read list because it names the seed and the task
inventory. `deny_paths` must cover the whole task directory: if the proposer
can list it, the held-out group is the complement of the optimize ids. It must
also cover earlier results for the same tasks, such as committed report
directories, because those hold per-task outcomes for the held-out group.

### Residual risk

- The controller cannot check that the launcher applied the rule.
- For the `hook` kind the scorer runs the candidate's code with the scorer's
  access. The controller detects that code tampering with earlier state. It
  cannot stop that code forging its own results.
- A scorer failure on a candidate stops the whole run rather than counting as
  a REJECT. That fails closed, and it costs the run.
- `killpg` after a normal exit could reach an unrelated group only if the
  group emptied and its id was reused.
- `os.replace` keeps the mode bits but not extended attributes, ACLs, or
  ownership.
- Two controller runs on one artifact are not locked against each other; the
  launcher must run one at a time per artifact.
- Child output files are not size-capped while the child runs; only what the
  controller reads back is bounded.

## The first valid agent-path null control

Two architect-spike runs ran on 2026-11-25 (local time; the run ids are UTC and
read 2026-11-26). They ran from one checkout, with no edit between them. Both
reports agree on `fixture_set_sha` (`f6310eb016cb`) and on `agent_prompt_sha`
(`dfcb7790a0e8`). Both used `claude-sonnet-5-5`, three runs per fixture, with
zero errors. The hub no longer serves `claude-sonnet-4-6`, so these runs are
not comparable to the 2026-05-28 reports.

| Measure | Run A (`20261126T051545Z-9db16cc0`) | Run B (`20261126T051950Z-bffd8a14`) |
| --- | --- | --- |
| Agent recall | 0.583 | 0.625 |
| Baseline recall | 0.729 | 0.708 |
| Flaky fixtures | 5 of 8 | 4 of 8 |
| `recommendation` | `halt-due-to-flakiness` | `halt-due-to-flakiness` |

B was gated against A with seed `7642`, holding out three tasks (A004, A006,
A008):

- At the default `--pass-threshold 1.0`, both runs pass the same 2 of 8 tasks
  (A003, A005). The gate returned REJECT on a tie at 0/3, with 0 gains,
  0 losses, p = 1.0, `corpus_verified: true`, and `corpus_pinned: true`.
- Three agent-variant means moved with no input change: A001 from 0.33 to
  0.50, A004 from 0.83 to 0.67, and A007 from 0.50 to 0.83. None crossed 1.0.
- At `--pass-threshold 0.5`, one task flipped: A001 went from fail to pass. It
  was in the optimize group, so the held-out group tied again.

### What it does and does not show

Both reports set `flaky_halt_threshold_crossed: true`. By the eval's own
methodology, neither run is fit to judge the architect agent. That does not
spoil the control. A null control asks what the gate does with noise, and these
runs are noisy. It does mean the pair measures a noise floor, not agent
quality.

The pair had little power to produce an accept. Three held-out tasks that all
fail at threshold 1.0 tie almost by construction. So the result is "no false
accept on this pair", not "the gate resists noise". It is not a false-accept
rate. At a lower threshold the same noise flips tasks, and a flip inside the
held-out group would read as a gain.
