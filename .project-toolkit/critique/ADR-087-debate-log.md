# ADR Debate Log: ADR-087 amendment 2026-11-25, trusted controller and first agent-path null control

## Summary

- ADR: `.project-toolkit/architecture/ADR-087-held-out-validated-improvement.md`, the "Amendment 2026-11-25" section, plus short pointers at the Open Requirement 1 paragraph, the "What the mechanism protects against" section, and Validation Status.
- Driver: issue #7642. The owner kept the ADR (decision D1) and chose the controller boundary (decision D2, option A: controller process plus a launcher deny rule).
- Panel: reduced, architect and critic. The amendment adds no executable enforcement that another gate reads. `scripts/eval/eval_controller.py` is opt-in tooling that no hook or CI job calls.
- Claims ledger: `.project-toolkit/critique/ADR-087-claims-ledger.md`. This is the first ADR-087 debate log; no prior log exists.
- Outcome: consensus after four rounds. The architect voted Accept in rounds 2 and 3. The critic voted Block in rounds 1 to 3 and Accept in round 4.
- Status: stays `proposed`. Ten Open Requirements remain open.

## How this panel was run

Each seat ran as a separate subagent with a fresh context and the same brief. The brief held the ADR diff, the controller code, the tests, and the ledger. It did not hold the author's reasoning. One model family ran both seats. Seats read files and ran tests and probes; they did not edit the repository. The author made every fix.

## Pre-panel gates (adr-generator exit gates)

| Gate | Result |
| --- | --- |
| Claims ledger | VERIFIED. One row per factual claim, updated after each round. |
| Documentation accuracy (`doc-accuracy` Phase 4) | NOT RUN. The ledger and both panel seats checked each claim against source instead. |
| Self-consistency | VERIFIED after round 1. Round 1 found the stale "No committed pair does" bullet and the stale "needs a controller" sentence; both now point to the amendment. |
| Refuting seat (analyst) | One factual finding: the amendment said the proposer gets "three things, and nothing else" and "one bit". `feedback.json` carries six keys, and `NO_CHANGE` is a third value. Fixed in round 1. All null-control numbers matched the reports. |

## Round 1

### Architect

Vote: Block.

| Id | Pri | Finding | Disposition |
| --- | --- | --- | --- |
| A1 | P1 | A proposer that edits the artifact and exits non-zero left the edit on disk; the proposer call sat outside the restore block. | Fixed. Proposer, scoring, and the byte check now sit inside one `try`; `finally` restores. Test `test_proposer_that_edits_then_fails_leaves_the_incumbent`. |
| A2 | P1 | `policy` omitted the config file, which names the seed and the task inventory. | Fixed. `policy` lists the config; a config inside the workspace is refused. |
| A3 | P1 | `deny_paths` was optional, so an empty list protected nothing. | Fixed. Required and non-empty. |
| A4 | P1 | Validation Status still said no committed pair agreed on both digests. | Fixed. The bullet now says "at the time" and points to the amendment. |
| A5 | P2 | "Three things, and nothing else" was wrong. | Fixed. The amendment lists every `feedback.json` field. |
| A6 | P2 | The "needs a controller" sentence needed a pointer. | Fixed. |
| A7 | P2 | `max_p` stays optional; the noise threat stays open. | Fixed. Stated in the amendment. |

### Critic

Vote: Block.

| Id | Pri | Finding | Disposition |
| --- | --- | --- | --- |
| C1 | P1 | Same as A1. | Fixed with A1. |
| C2 | P1 | The accepted bytes could differ from the scored bytes. No timeout and no process-group kill. | Fixed. The artifact is re-read after scoring and the step is refused on a change. Calls run in a new session with `timeout_seconds`, and the group is killed when the call ends. |
| C3 | P1 | A symlink planted in the workspace redirected controller writes. | Fixed. Workspace files are deleted and recreated each step; `feedback.json` opens with `x`. Test `test_planted_feedback_symlink_is_not_followed`. |
| C4 | P1 | Held-out membership is the complement of the optimize ids if the fixtures directory is listable. | Fixed. `deny_paths` is required, and the ADR says it must cover the whole task directory. |
| C5 | P1 | Both reports flag `halt-due-to-flakiness`; the amendment omitted it. | Fixed. The amendment states the flag and calls the pair a noise-floor observation. |
| C6 | P2 | The run ids are UTC and read 2026-11-26. | Fixed. Stated. |
| C7 | P2 | The OR9 and OR10 rows read as blocked while the controller path already pins both. | Fixed. Rows reworded. |
| C8 | P2 | Missing tests for `collect`, missing output, and `NO_CHANGE` followed by a change. | Fixed. Three tests added. |

## Round 2

### Architect

Vote: Accept. All round 1 items verified fixed; 33 of 33 tests passed.

| Id | Pri | Finding | Disposition |
| --- | --- | --- | --- |
| N1 | P2 | The process-group kill is POSIX only, and a `setsid` child leaves the group. The caveat was only in a docstring. | Fixed. ADR and README state it. |
| N2 | P2 | Open Requirement 6 covers the rule adapter, not the agent adapter. | Fixed. The amendment says no open requirement covers agent-path noise. |
| N3 | P2 | No ledger rows for the timeout and the kill. | Fixed. Rows added. |

### Critic

Vote: Block. The critic re-ran the gate with a fresh ledger: REJECT on a 0.0 tie, p = 1.0, `corpus_verified` and `corpus_pinned` true, matching the amendment.

| Id | Pri | Finding | Disposition |
| --- | --- | --- | --- |
| N1 | P0 | A proposer swapped the artifact for a symlink to a denied fixture. The controller's restore wrote through it and overwrote `fixtures/T01.json`. Reproduced by probe. | Fixed. `_read_artifact` refuses a symlinked artifact; `_write_artifact` writes a temp file and calls `os.replace`, which replaces the link instead of following it. An integrity check now runs after every step. Test `test_artifact_swapped_for_symlink_cannot_redirect_the_restore`. |
| N2 | P1 | A `setsid` grandchild held the stdout pipe, so a 2 s timeout took 25 s. Reproduced by probe. | Fixed. Output goes to temporary files, not pipes. Test `test_escaped_grandchild_cannot_stretch_the_timeout`. |
| N3 | P2 | Windows kills only the direct child; unqualified in README and ADR. | Fixed. Stated in both. |
| N4 | P2 | Earlier report directories hold held-out outcomes and were not named. | Fixed. ADR and README require them in `deny_paths`. |

## Round 3

### Architect

Vote: Accept. All round 2 P2 items verified.

| Id | Pri | Finding | Disposition |
| --- | --- | --- | --- |
| R3-1 | P2 | The ADR said the controller kills the proposer's process group; `_run` serves scorer and proposer alike. | Fixed. The ADR now names both. |
| R3-2 | P2 | `killpg` after a normal exit could reach an unrelated group if the pid were reused. | Accepted as residual risk. A process group id stays reserved while the group has a live member, so reuse needs the group to be empty first. |
| R3-3 | P2 | `mkstemp` resets the artifact mode. | Fixed with the critic's R3-1. |

### Critic

Vote: Block. Round 2 N1 to N3 verified fixed by probe; N4 judged partial (documented, not enforced).

| Id | Pri | Finding | Disposition |
| --- | --- | --- | --- |
| R3-1 | P1 | Every restore installed mode 0600. A probe showed 0o755 become 0o600 with a no-op proposer. | Fixed. The mode is recorded before the loop and set on the temp file before `os.replace`. `test_artifact_mode_survives_restore_and_accept` fails with the fix removed and passes with it. |
| R3-2 | P2 | A hard-linked artifact was accepted. | Fixed. `_read_artifact` refuses `st_nlink > 1`. |
| R3-3 | P2 | The summary digest came from memory. | Fixed. The final digest is read from disk and compared to the incumbent. |
| N4 | P2 | `deny_paths` coverage of report directories is documented, not enforced. | Accepted as residual risk. The controller cannot know which paths hold held-out data. |

## Round 4

### Critic

Vote: Accept. 39 of 39 tests passed. Probes for mode and hard link re-run: mode kept at 0o755, hard link refused with exit 2. No new blocking concern. Two P3 notes, not acted on: a failing restore inside `finally` masks the original error, and `os.replace` keeps mode bits but drops xattrs, ACLs, and ownership.

The architect did not re-vote in round 4. The round 3 code changes add refusals and keep the mode; the ADR text changed in two sentences the architect had asked for.

## After consensus: `/review` and pre-PR fixes

The `/review` skill ran on commit `bfe33e69b` after round 4: spec-compliance, a
correctness pass, and the 11 canonical axes in four batched seats. Spec-compliance
and roadmap returned PASS; the rest returned WARN. `pre_pr.py` failed on the
file-size, naming, and complexity taste ratchet, the ADR size cap, and test file
encodings. The fixes below changed code and condensed ADR text. The round 4
votes covered the text as it stood then; a round 5 critic pass and a round 2
code review covered the condensed text and the restructured code.

| Source | Finding | Disposition |
| --- | --- | --- |
| correctness | A gate exit 1 that refused without comparing was counted as a REJECT and spent budget. | Fixed. Only `compared: true` counts; a refusal stops the run with exit 3. |
| correctness, qa | `OSError`, `KeyError`, `ValueError`, and a directory at the artifact path escaped as exit 1. | Fixed. `main` maps them to exit 3; `write_artifact` removes a planted directory and raises `ControllerError`. |
| security, agent-safety | The gate and controller code were writable and undigested. | Fixed. `scripts/eval/*.py` and `trusted_paths` are digested and printed as `deny_write`. |
| security, plugin review | For `hook`, candidate code runs inside the scorer. | Partly fixed. State outside the new run's directory is digested around scoring, and the workspace is emptied each step. Forged results remain a stated residual risk. |
| security | The proposer inherited the full environment; child stderr went to the launcher. | Fixed. `EVAL_LEDGER_DIR` is dropped, `proposer_env` allowlists, and stderr goes to the log. |
| reliability | `optimize-artifact.py` calls had no timeout. | Fixed. |
| devops | SIGTERM skipped the restore. | Fixed. A handler raises, so `finally` runs. |
| architect | A deny path could contain `state_dir`; a missing opt task file was skipped. | Fixed. Both refused. |
| architect | A candidate that breaks the scorer stops the run instead of counting as REJECT. | Kept. It fails closed; recorded as residual risk. |
| observability | No timestamps, no abort event. | Fixed. Every event carries `ts` and `session`; calls carry `duration_s`; an early exit logs `abort`. |
| decision-rigor | "Did not produce a false accept" overstated a pair with little power. | Fixed. The ADR now says three all-failing tasks tie almost by construction. |
| analyst | The ledger root is `state_dir/ledger`, not the state directory. | Fixed in the analysis file. |
| pre-PR | Taste ratchet (+3), ADR size cap, test encodings. | Fixed. The controller is split into `eval_controller.py` (snake_case) and `_controller_io.py`. The ADR is back to 1000 lines, with detail moved to `.project-toolkit/analysis/7678-adr-087-trusted-controller-and-null-control.md`. |

## Round 5 and code review round 2

### Critic (ADR condensation)

Vote: Disagree-and-Commit.

| Id | Finding | Disposition |
| --- | --- | --- |
| R5-1 | The condensed ADR dropped the condition that `deny_paths` must cover the whole task directory and earlier report directories; "the three surfaces are closed" overclaimed without it. | Fixed. The sentence is restored in the ADR. |
| R5-2 | "Sees only" omitted the step, artifact path, score, and budget fields. | Fixed. |
| R5-3 | The analysis file said `proposer_may_write` includes the workspace; the code prints it separately. | Fixed. |
| R5-4 | README said `state_dir` "Must be fresh"; the code refuses only an earlier `split.json`. | Fixed. |
| R5-5 | README still said closing selection pressure "needs the trusted controller" with no pointer. | Fixed. Pointer added. |
| R5-6 | This log claimed the round 4 vote covered the condensed text. | Fixed. Reworded above. |

Dissent recorded: the per-requirement state table and the POSIX `setsid` limit now live in the analysis file, not the ADR.

### Code review round 2 (frozen)

Verdict: WARN. Eleven of twelve round 1 items verified fixed. The proposer allowlist is opt-in, so the default still passes the environment minus `EVAL_LEDGER_DIR`; kept as documented.

| Id | Finding | Disposition |
| --- | --- | --- |
| D1 | A workspace containing the artifact would delete it each step, and an unrelated directory named as the workspace would be wiped. | Fixed. Both refused at start; tests `test_artifact_inside_the_workspace_is_refused` and `test_non_empty_workspace_is_refused_and_left_alone`. |
| D2 | A refused existing `state_dir` got an `abort` line appended. | Fixed. Abort is logged only after the session starts. |
| Note 1 | The docstring claimed the state directory is digested at all times. | Fixed. It now names the scoring window. |
| Note 5 | `TypeError` and `AttributeError` escaped as exit 1. | Fixed. Mapped to exit 3. |
| Plugin review | Only top-level `.py` files were digested, so a planted package or bytecode cache could shadow a module. | Fixed. Every entry under `scripts/eval/` is digested, `deny_write` names the directory, and the optimizer runs with `PYTHONPYCACHEPREFIX` under state. |

### Security axis on `b00f6f838`

Verdict: WARN, two Low findings, both reachable only after the launcher rule fails.

| Id | Finding | Disposition |
| --- | --- | --- |
| S1 | `tree_digest` skips `__pycache__`, and the scorer ran with no cache prefix, so a planted cache beside the scorer's code could run. | Fixed. Each scorer run gets `PYTHONPYCACHEPREFIX` inside its own run directory. |
| S2 | Scorer-derived task ids filled `opt_task_files` unchecked, so `../../x` could copy an arbitrary file to the proposer. | Fixed. `task_file` refuses a separator, `.`, or `..` in any placeholder the template uses. |

The spec-compliance axis on `b00f6f838` returned WARN because the owner decisions were not on #7642. They are now recorded there in a comment.

### Merge of main, 2026-11-26

Main's #7692 accepted ADR-022 and edited two ADR-087 sentences to say so, which took the record to 1001 lines. One paragraph is reflowed to bring it back to 1000. No wording changed, so no new panel round.

## PR #7699 review threads

Seventeen inline threads on `efba0ce6e`. Code fixes landed in one commit; each thread carries its own reply.

| Source | Finding | Disposition |
| --- | --- | --- |
| rjmurillo | The digest sentence sat in the task-id bullet of the analysis file. | Fixed. Moved. |
| Devin | A scorer that exits 1 on failing tests (pytest, rule scorer) aborted the run. | Fixed. `scorer_exit_codes` (default `[0]`). |
| Devin | SIGTERM during the restore could leave the candidate. | Fixed. Deferred until the write lands. |
| Devin | A launcher artifact that is a tracked symlink was refused. | Fixed. Resolved once at config load. |
| Devin | Same-named task files overwrote each other. | Fixed. Refused. |
| Devin | State or workspace under trusted code tripped the digest. | Fixed. Refused at load. |
| Devin | Gate events lacked the candidate digest. | Fixed. `candidate_sha256` recorded. |
| Devin | The proposer inherited scorer credentials by default. | Fixed. `proposer_env` is required. |
| Devin | A failed scorer left its report in the checkout. | Fixed. Collected before stopping. |
| Devin | Hook scoring runs candidate code with scorer access. | Kept as stated residual risk (decision D2). |
| Devin | The split inventory comes from the baseline results. | Deferred to Open Requirement 12 (#7689). |
| Cursor | Baseline scoring skipped the integrity and artifact checks. | Fixed. Every score checks both. |
| Cursor | Task copies followed symlinks. | Fixed. Links refused; `copyfile` used. |
| Cursor | Symlink tests lacked a Windows skip. | Fixed. |
| Semgrep | `0o700` called too permissive. | False positive: owner-only is stricter than the `0o644` it suggests. |
| CodeQL | `chmod` with a world-readable mode. | By design: restores the artifact's original mode (round 3 fix R3-1). |
| CodeQL | Clear-text logging of a secret in `cmd_policy`. | False positive: `policy` prints paths only. |

Second Cursor pass on `f3f27f824`:

| Finding | Disposition |
| --- | --- |
| A failed baseline scoring run left a scorer-rewritten artifact on disk. | Fixed. The baseline restores the incumbent on failure. |
| `state_dir`, `workspace_dir`, `deny_paths`, and `trusted_paths` were not canonical, so a symlinked directory skipped the content digest. | Fixed. All resolve at config load. |

Third Cursor pass on `3d6635d79`:

| Finding | Disposition |
| --- | --- |
| An artifact under `scripts/eval/` passed the layout check, then tripped the integrity digest after an ACCEPT. | Fixed. The artifact is checked against all trusted code. |
| Optimizer calls used `subprocess.run`, which kills only the child on timeout. | Fixed. Optimizer, scorer, and proposer share one spawn path: new session, file output, group kill. |

CodeRabbit and fourth Cursor pass on `c65d91240`:

| Finding | Disposition |
| --- | --- |
| Windows proposer env dropped startup variables and matched `PATH` case-sensitively. | Fixed. |
| The artifact could be the config. | Fixed. Refused. |
| `rglob` skips unreadable directories, so a digest could attest to an incomplete scan. | Fixed. `os.walk` with an error handler refuses. |
| Child output was read back unbounded. | Partly fixed. Reads are bounded; disk use while a child runs is not, since a pipe would bring back the round 2 timeout bypass. |
| `_collect` stopped at the first missing or failed report. | Fixed. Each is attempted. |
| A state-change refusal ran before collection. | Fixed. Collection runs first. |
| `results.json` could be written through a planted link. | Fixed. Exclusive create. |
| A baseline `OSError` skipped the restore. | Fixed. Any exception restores. |
| A SIGTERM before `_restore` set its guard could skip the restore. | Fixed. Callers set the guard first. |
| A new `state_dir` resets the budget; README did not say so. | Fixed in README. |
| `collect` paths were not in the printed policy. | Fixed. `deny_read_write_collect`. |
| README overstated logged child output. | Fixed. |
| Timeout tests did not prove the proposer timed out. | Fixed. |

CodeRabbit pass on `71555828f` (12 threads):

| Finding | Disposition |
| --- | --- |
| The ADR condition omitted `collect` paths and `trusted_paths`. | Fixed. Reworded at the same length. |
| `max_p` out of range was found only at the gate. | Fixed. Checked at load. |
| `__pycache__` was skipped in every protected tree. | Fixed. Only under `scripts/eval/`. |
| A protected root that cannot be inspected read as missing. | Fixed. `lstat` classifies it, and inspection errors refuse. |
| `inputs` outside the run directory were not in the policy. | Fixed. `inputs` must start with `{run_dir}`. |
| A stale report at a fixed `collect` path could be gated. | Fixed. Refused before scoring. |
| A task path through a linked directory passed the leaf check. | Fixed. `realpath` must equal `abspath`. |
| Ctrl+C could unwind a restore. | Fixed. SIGINT is deferred like SIGTERM. |
| The detached test grandchild was left running. | Fixed. Killed in `finally`. |
| The split comes from baseline results, not a launcher inventory. | Deferred to Open Requirement 12, #7689, as before. |
| Two runs on one artifact can restore over each other. | Not fixed. Documented: one controller per artifact; a cross-process lock is new scope. |

CodeRabbit follow-ups on resolved threads, after the round cap: twelve asks for deeper hardening of fixes already landed. Each got a `[WONTFIX]` reply with its reason, and none started a new round. Recorded here as residual risk:

- A failed report move on the scorer-failure path is reported only through the scorer error.
- Child output files are not capped while the child runs; readback is.
- A signal in the one instruction before `restoring = True` can still skip a restore.
- An unreadable directory inside the scorer's own run directory stops the digest (fails closed).
- A `trusted_paths` entry containing `scripts/eval/` digests its caches (fails closed).
- Baseline coverage against a launcher-owned inventory: noted on #7689.
- A failed baseline scoring run restores the artifact but does not re-check protected paths, so a crash after tampering reports as a scorer error (Cursor, after the cap).

## Dissent and residual risk

- The boundary holds only under a launcher deny rule the controller cannot verify. The owner chose this in decision D2 over an OS user or a CI job.
- A `setsid` descendant survives the group kill on POSIX, and Windows kills only the direct child. The byte check and the per-step integrity check are the remaining guards.
- The null control is one pair on one benchmark, and both runs flag their own methodology as unstable. It is not a false-accept rate.
- `deny_paths` must cover earlier report directories for the same tasks. The controller documents this and cannot enforce it.
- `killpg` after a normal exit carries a pid-reuse risk that needs an empty group first.
- For the `hook` kind, candidate code run by the scorer can forge its own results.
- A candidate that breaks the scorer stops the run rather than counting as a REJECT.
- Two controller runs on one artifact are not locked against each other.
