# Stalled-investigation strategy comparison: frozen protocol

Issue #7350, a narrower successor to #6814 under #5422 and #5768. This file is
committed and pushed before any live run. Nothing in it may change after the
first live launch. A change starts a new protocol file and a new run directory.

## Question

When a repair repeatedly fails to clear a reproduction, does a bounded handoff
to the existing independent-thinker role beat continued analyst investigation?
The measure is executable acceptance: a held-out test run, plus a scope check.
Both arms get the same model, effort, harness, tools, starting state, facts,
and correction budget. Only the investigator's role text and framing differ.

Hypothesis, unmeasured before this run: the handoff raises accepted outcomes on
stalled tasks without more missed regressions or scope growth.

## Prerequisites read

#5422 to #5426, #5768, and #6814 were read, with their artifacts under
`evals/control-ablation-historical/` and `evals/routing-benchmark/`. The #6814
harness is reused: `_control_ablation_history`, `_grade`, `_claude`, `_batch`,
`_dry_run`, the outcome record, and the spend guard. The #5425 corpus (RB-01 to
RB-06) holds six synthetic or adapted scenarios, none a real issue of this
repository with a base commit, so it does not meet the issue's task rule.

## Capability gaps in the #6814 harness (documented before extending)

| Gap | Where | Extension |
|---|---|---|
| Every task must share one `base_sha`, because controls read one tree | `_control_ablation_history.load_historical_tasks` | `_handoff_strategy.load_tasks` reuses `_load_one` per task and resolves `full` at each task's own base |
| Arms are control-file sets in one launch. No investigator launch, no role text | `eval_control_ablation._grade_live_run` | `eval_handoff_strategy.run_cell`: investigator then producer launch per round |
| Retries are 0 by construction | same | `REPAIR_ROUNDS = 2` repair rounds, identical in both arms |
| No flag seam for `--append-system-prompt` or `--effort` | `_control_ablation_claude.claude_argv` | `extra_args` parameter and `invoke_launch`. Empty `extra_args` keeps the frozen argv |
| The visible tests pass on base, so no stall signal | task schema 2 | Schema 3 adds `visible_files`: a reproduction red on base |
| Held-out file is copied verbatim from the fix | schema 2 | Schema 3 adds `withheld_edits`: exact-once text edits |

No parallel harness was built. The new code is `scripts/eval/_handoff_strategy.py`
and `scripts/eval/eval_handoff_strategy.py`, with tests in
`tests/eval/test_handoff_strategy*.py`.

## Task set (frozen)

Task file: `scripts/eval/examples/handoff-strategy-tasks.json`, SHA-256
`bad0f411a3a6681037942b45c760fab949dffa3a3ee50d2a35cfde0cce8ab315`.

| Task | Role | Issue | Base (pre-fix) | Shipped fix | Allowed scope |
|---|---|---|---|---|---|
| `issue-7328-mypy-symlink-run-mypy` | stalled | #7328 | `329d3b5d452345bc8445fe6a18b939e434769873`, the parent of the second fix and the tree after the first attempt (PR #7329) | `3cf312bc14baa9757634b77e0c1c0c95334b34d1`, PR #7333 | `scripts/validation/git_hook_policy.py`, `scripts/validation/checks_mypy.py`, `tests/validation/*.py` |
| `issue-6169-codex-login-stderr` | negative control | #6169 | `316171ac67064874afe9965547cf5aac89f1ffc9` | `045750319851fe56aa2000da9cadd61b8a983f91`, PR #6343 | `scripts/eval/_cli_credential_sources.py`, `tests/eval/*.py` |

Two tasks, below the issue's ceiling of six. The search for more real repeat-fix
chains found one more that I rejected: each other chain's residual defect was
not observable from pre-fix material, or its pre-fix discussion already held
the solution. #5213 and #5738 had no pre-fix signal of the residual. #6415's
security review comment names the fix design. #5209 is an umbrella audit and
#6667 spans 51 Python files. I did not examine #5473 or #6195 past their commit
titles. The set is small by necessity, and the decision rule below accounts for
that.

The stalled task is a real second attempt. The issue's own "Suggested fix"
(change only the file-set builder, keep the refusal in `run_mypy`) shipped as
#7329. The residual symptom was reported on the CI run for PR #7330. PR #7333
was created 2026-11-12T03:16:42Z and cites that run as its cause. I did not read
the run's own timestamp, so the order rests on the PR's account.

The negative control is narrow and settled. The issue names the file, the
cause, and the fix direction. A handoff there has nothing to reframe.

## Worker-visible material (frozen)

The prompt is the issue text verbatim. The brief adds a residual symptom, the
earlier attempt as a rejected hypothesis, acceptance, and non-goals. The same
bytes go to both arms. The observed output is the base reproduction output.
Nothing from the shipped fix or the held-out file enters any prompt. The
cell directory name carries no arm (the traceback prints it).

For #7328 the earlier attempt is described as: the file-set builder was the only
place that needed to change, and the symptom shows it was not enough. The brief
does not say which callers fail or what the fix is.

## Checks (frozen)

- **Reproduction (visible, red on base).** One test file per task, written from
  the issue text and the quoted symptom. It is not lifted from the fix's tests.
  `tests/validation/test_issue_7328_repro.py` asserts `run_mypy` neither prints
  `refusing to type-check symlink` nor exits 2 for a tracked link to an in-repo
  file. `tests/eval/test_issue_6169_repro.py` asserts `codex_login_probe` accepts
  a status line printed to stderr.
- **Held-out check.** The fix commit's own test file, written into the workspace
  only after the last round. For #7328 one import line is edited so the file
  loads without a private helper name, and two nodes are deselected: the class
  that tests that helper, and `test_the_link_and_its_source_are_checked_once`,
  which pins a dedup choice the issue never states. For #6169 the same node is
  deselected as in #6814.
- **Scope check.** Changed paths outside the allowed scope are violations. A
  bytecode cache is not a change.
- A model judge never overrides a deterministic failure. No judge runs.

### Discrimination proof (dry run, no model call)

`uv run python scripts/eval/eval_handoff_strategy.py --dry-run` on the frozen
task file, run before this commit:

| Task | Base reproduction | Shipped fix | Plausible-wrong fix |
|---|---|---|---|
| #7328 | exit 1 (red) | reproduction pass, held-out 4 passed: `ACCEPTED_DURABLE` | reproduction pass, held-out 2 failed (`test_a_type_error_in_the_source_is_found_through_the_link`, `test_negative_control_a_link_that_leaves_the_repo_is_refused`): `ACCEPTED_NOT_DURABLE` |
| #6169 | exit 1 (red) | reproduction pass, held-out 53 passed: `ACCEPTED_DURABLE` | reproduction pass, held-out 1 failed (`test_claude_ignores_stderr_so_json_stays_parseable`): `ACCEPTED_NOT_DURABLE` |

The #7328 wrong fix deletes the symlink refusal in `run_mypy`. It clears the
symptom and breaks the safety boundary. A dry run that does not discriminate
aborts the experiment.

## Arms (frozen)

Each cell runs rounds of: investigator launch, producer launch, reproduction.

| Field | `continue_analyst` | `handoff_independent_thinker` |
|---|---|---|
| Role text | `src/claude/agents/analyst.md` body, frontmatter stripped, SHA-256 `d145186398d5aeb47f02c94973d1684edaf04cf070293e1f96d5532610ccda35` | `src/claude/agents/independent-thinker.md` body, frontmatter stripped, SHA-256 `0e57fd05d49f1fabd10b57ca3d49613d26db85b6aa7f27799b4bbf56f3cfd40e` |
| Delivery | `--append-system-prompt` | same |
| Instruction | continue the investigation (SHA-256 `d111b884ad8b2fe0491d72dfa3cb7f5b36180c54c3e2ebd98d535421b6e898f0`) | premise-challenging handoff (SHA-256 `b3c8a2ea1ace6fb8e5323b3d8303a71a2146248174ceb00ca7085ed39657c069`) |

Held fixed in both arms:

- Facts block: issue, residual symptom, reproduction command and observed
  output, earlier attempts and rejected hypotheses, acceptance, non-goals.
- Investigator tools: `Read,Glob,Grep,Bash`, with Bash limited to
  `python3 -m pytest`, `git log`, `git diff`, `git show`, `ls`, `cat`. No Edit or
  Write. After each investigator launch the harness hashes the changed files. Any
  difference invalidates the cell.
- Producer launch: the #6814 producer tools and Bash allowlist, no role text,
  identical prompt template (tail SHA-256
  `073a67b0a77c7122523c46e1441bf9a690b72e55534f755665570392b984e2a8`).
- Model `claude-sonnet-5-5`, checked against the stream's resolved model.
- Effort `medium` on every launch (`--effort medium`).
- Harness: Claude Code 2.1.325, `--print`, `--permission-mode acceptEdits`,
  `--real-home`. The real home loads `~/.claude` in both arms. It is a shared
  confound, recorded in `report.json`.
- Control plane: the `full` always-loaded set, read at each task's own base.
- Correction budget: 2 repair rounds after the first attempt. A repair round is
  an investigator launch with the prior findings and the failing reproduction
  output, then a producer launch. Feedback is visible output only.
- Cell order alternates per repeat. Each cell is deleted after grading.

### Deviations from the issue and the roles, stated up front

- `analyst.md` declares no shell tools and tells the analyst to read GitHub
  through MCP tools. The harness gives both investigators the same Bash
  allowlist and no MCP servers, so the tool set is held fixed across the role
  files. A role prompt that fails fast for a missing GitHub tool would show in
  the investigator reply, which `report.json` keeps.
- The independent-thinker arm is the existing role, not a different model. The
  arms share one model, so the strategy and role text are isolated from vendor.
- "Unjustified blocking findings" has no stage in this design (there is no
  review launch). It is recorded as `null`, UNKNOWN.
- Token counts are not recorded. Spend and wall time are.

## Repetitions, budgets, caps (frozen)

| Field | Value |
|---|---|
| Repetitions | 3 per arm per task, so 12 cells |
| Repair rounds | 2, identical in both arms |
| Per-launch timeout | 600 s |
| Cell cap | `--max-cells 12` |
| Spend cap | `--max-cost-usd 20`. No new cell starts once recorded spend reaches it, or once any cost is unmeasured |
| Auth | `--real-home` |

Maximum launches: 12 cells x 6 launches = 72. A harness failure in a cell is
recorded, not retried.

Run command:

```bash
uv run python scripts/eval/eval_handoff_strategy.py \
  --tasks scripts/eval/examples/handoff-strategy-tasks.json \
  --repeats 3 --model claude-sonnet-5-5 --effort medium --max-cells 12 \
  --max-cost-usd 20 --timeout 600 --real-home \
  --workspace-root "$(mktemp -d)" \
  --output-dir evals/handoff-strategy-historical/runs/2026-11-15
```

## Per-run fields

Recorded separately for each cell: base reproduction exit, final reproduction
exit, held-out exit, scope violations, accepted, regression (reproduction
passed, held-out failed), repair turns, model cost, wall seconds, tool failures,
every launch's reply and trajectory (Bash commands, other tool inputs, denials,
withheld-marker hits), and the change patch. Human correction minutes and
blocking findings are `null`, UNKNOWN. A field not measured is `null`, never 0.

A cell is **accepted** when it is valid, the reproduction exits 0, the held-out
check exits 0, scope violations are 0, and no external marker exists.

## Decision rule (frozen before any live run; `_handoff_strategy.decide`)

Default: retain the incumbent routing.

1. If any cell is missing or invalid: INCONCLUSIVE.
2. Negative control. If the treatment arm has fewer accepted cells than the
   control arm, any scope violation, or more regressions: REJECT.
3. Stalled tasks. If the treatment arm has more regressions or more scope
   violations than the control arm: REJECT.
4. If fewer than 2 stalled tasks ran: INCONCLUSIVE. This run has one, so the
   best outcome the rule allows is INCONCLUSIVE with "retain incumbent". That
   is a property of the task set, chosen before any outcome was visible.
5. Otherwise, if treatment accepts at least 2 more stalled cells than control and
   its summed wall time is at most 1.5 times control's: SUPPORTED_NARROW.
6. Otherwise: INCONCLUSIVE.

The hypothesis is accepted only under SUPPORTED_NARROW, and then only for the
task shape tested. It is rejected under REJECT. Otherwise it is not accepted and
no routing change is recommended. The report gives each arm's accepted count with
a 95% Wilson interval, lists every cell, and makes no repository-wide claim. A
sample this size cannot support one.

## Abort conditions

Stop and report without a decision on: a tool call that names withheld evidence
(the held-out path, the fix commit, the fix PR, or the runner checkout), a dry
run that fails to discriminate, an exhausted spend cap before every cell ran, a
recorded unapproved external action, an investigator that changes the workspace,
or any proposal to weaken a security or permission boundary. Existing review
caps, frozen findings, and approval safeguards are not touched.

## Limits known before the run

- One stalled task and one control. No repository-wide claim is possible.
- I wrote both reproductions after reading the fix. They come from the issue text
  and the quoted symptom, and the dry run shows they do not encode the held-out
  nodes, but an author who knows the fix can steer a test without meaning to.
- No pilot ran. Whether the first attempt stalls is unknown, so the arms may both
  pass in round 0. If so, the repair-turn and handoff effects are unobserved and
  the report says so.
- The runner checkout is readable by the `cat` and `git` allowlist under
  `--real-home`. Marker hits are recorded and invalidate a cell.
- Provider and model behavior can change between runs. One date, one model.

## Rollback

Nothing in routing templates, agent definitions, or settings changes in this
experiment. Any later routing change is the owner's decision.
