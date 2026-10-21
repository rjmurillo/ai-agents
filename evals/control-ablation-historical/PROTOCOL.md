# Historical issue-to-fix control subtraction: frozen protocol

Issue #6814, under #5768 and #5456. This file was committed before any live run
of the task below. Nothing in it may change after the first live launch; a
change starts a new protocol file and a new run directory.

## Question

On one real, already-shipped issue from this repository, does Claude Code fix
the issue as well without one non-security always-loaded rule file as with the
full always-loaded control plane, at no higher model cost?

A one-task answer supports a narrow keep-or-drop decision for that file on that
task shape. It is not repository-wide non-inferiority.

## Task (frozen)

| Field | Value |
|---|---|
| Issue | #6169, "fix(eval): Codex login probe reads stdout, but the CLI prints status to stderr" (opened 2026-10-04) |
| Shipped fix | PR #6343, commit `045750319851fe56aa2000da9cadd61b8a983f91` (2026-10-12) |
| Pre-fix base | `316171ac67064874afe9965547cf5aac89f1ffc9`, the fix commit's only parent |
| Task file | `scripts/eval/examples/control-ablation-historical-tasks.json` |
| Seeded paths (from base) | `scripts/eval/`, `tests/__init__.py`, `tests/eval/`, `pyproject.toml` |
| Allowed change scope | `scripts/eval/_cli_credential_sources.py`, `tests/eval/*.py` |

The agent receives the issue title and body verbatim, as written before the
fix. It receives no PR text, no fix diff, no post-fix discussion, and no git
history: the workspace is a fresh `git init` of a `git archive` of the base
commit, so `git log` shows one seed commit. The issue's timeline (read
2026-10-21) shows no body edit after it was opened, so the body predates the fix.

Deviation from a full checkout, stated up front: the workspace holds only the
seeded paths plus the control files. Hooks, skills, agents, and path-scoped
rules are absent in every arm. Both arms differ only in the control files.

## Checks (frozen before the run)

- **Acceptance (visible):** the base commit's own
  `tests/eval/test_cli_credential_sources.py`, run with the runner's
  interpreter (`{python} -m pytest -p no:cacheprovider -q ...`). The agent can
  read and run it.
- **Withheld regression check:** the fix commit's
  `tests/eval/test_cli_credential_sources.py`, written to
  `tests/eval/test_cli_credential_sources_withheld.py` only after the agent
  exits, outside the agent's sight. Node
  `TestLoginProbes::test_codex_matches_the_line_amid_other_stderr_output` is
  deselected. The issue's "Fix direction" offers "Read stderr when stdout is
  empty" as an acceptable fix, and that node rejects that option, so it tests
  the fix author's choice rather than the issue's requirement. Every other
  shipped node runs.
- **Discrimination proof (dry run, no model):** the shipped fix
  (`known_good`, source file from the fix commit) must pass acceptance and the
  withheld check. A plausible-but-wrong fix (`known_bad`: merge stderr into
  every probe's output, which fixes Codex and breaks the Claude JSON probe)
  must pass acceptance and fail the withheld check. A dry run that does not
  discriminate aborts the experiment.

Model judgment never overrides a deterministic result. No reviewer arm runs.

## Controls (frozen)

| Arm | Control files (read from the base commit) |
|---|---|
| `full` | every file `control_plane_baseline.always_loaded` reports for `claude_code` at the base commit: `.claude/CLAUDE.md`, `.claude/rules/builder-ethos.md`, `.claude/rules/universal.md`, `.claude/rules/voice.md`, `AGENTS.md`, `CLAUDE.md` (41,354 bytes) |
| `minus:.claude/rules/voice.md` | the same set without `voice.md` (26,520 bytes) |

Removal candidate rationale: `voice.md` is the largest always-loaded rule
(14,834 bytes, 36% of the control bytes), carries no security or permission
requirement, and governs response prose rather than code. `universal.md`
carries the secrets and safety MUSTs and is not a candidate. Activation scores
were not used to pick it.

## Model, harness, budgets (frozen)

| Field | Value |
|---|---|
| Model | `claude-sonnet-5-5`, verified against the stream's resolved model |
| Harness | `claude -p`, the runner's fixed argv, `--permission-mode acceptEdits`, tools `Read,Edit,Write,Glob,Grep,Bash`, Bash allowlist `python3`, `git`, `ls`, `cat` |
| Repetitions | 4 per arm, interleaved per repeat (`full` then `minus`) |
| Retries and correction rounds | 0 for both arms (unattended) |
| Per-launch timeout | 900 s |
| Run cap | `--max-runs 8` |
| Spend cap | `--max-cost-usd 25`: no new launch starts once recorded spend reaches it |
| Auth | `--real-home` plus `--pass-env CLAUDE_CODE_REMOTE,CLAUDE_SESSION_INGRESS_TOKEN_FILE` (names recorded, values never) |

`--real-home` is a confound shared by both arms: anything under `~/.claude`
loads under both controls. The report records it.

## Per-run fields

Recorded separately for every run: withheld-check result and exit code,
acceptance exit code, scope violations (changed paths outside the allowed
scope), elapsed seconds, model cost in USD, retries (0 by construction), human
intervention (none by construction: unattended), human correction minutes
(`null`, UNKNOWN: nobody timed a correction), the Bash commands the agent ran,
which of them invoked tests, and permission denials. A field that was not
measured is `null`, never 0.

## Decision rule (frozen before any live run)

A run **passes** when acceptance exits 0, the withheld check exits 0, scope
violations are 0, and no unapproved external action was recorded.

Let `F` and `M` be the pass counts of `full` and `minus` over 4 runs each, and
`cost(X)` the summed model cost of arm X over all its runs, failed ones
included.

1. `F == 0`: **INCONCLUSIVE** (the baseline cannot solve the task, so the
   comparison carries no signal about the removed file).
2. `M < F - 1`, or `minus` has a scope violation while `full` has none:
   **KEEP_BASELINE**.
3. `M >= F`, `minus` has zero scope violations, and
   `cost(minus) <= cost(full)`: **ACCEPT_REMOVAL** for this task shape.
4. Otherwise: **INCONCLUSIVE**.

Human correction minutes are UNKNOWN in both arms, so "total effort" here is
model cost plus elapsed time, and the report says so. With 4 runs per arm the
report lists each run individually and gives the pass proportion with a 95%
Wilson interval per arm; it does not claim a difference the intervals do not
support.

## Abort conditions

Stop and report without a decision on: evidence the agent saw the withheld
test or the shipped fix (a tool call that reads a path or URL carrying them),
a dry run that fails to discriminate, an exhausted spend cap before both arms
have 4 runs, a recorded unapproved external action, or any proposal to remove
a security or permission file.

## Rollback

The removed configuration is archived by name and bytes in the run's
`report.json` (`provenance.controls`). Nothing in the repository's control
plane is changed by this experiment; a later PR that acts on an
ACCEPT_REMOVAL restores the file with `git revert`.
