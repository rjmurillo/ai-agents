---
name: sol-loop
version: 1.0.0
description: GPT Sol review after the fresh critic, at most 2 rounds, logging findings only Sol raised. Use for "sol loop". Not for pre-merge review (use review) or open-ended questions (use llm-council).
license: MIT
argument-hint: "[pr-number --author-family anthropic|openai|unknown]"
user-invocable: true
---

# sol-loop

Review a code change with OpenAI's GPT Sol after the fresh critic has reviewed
it. Sol is a second model family, so it tends to find different bugs than the
critic. Make the smallest changes that answer Sol. Fight scope creep and push
back when a finding is wrong.

## Triggers

`sol loop`, `run a Sol review`, `cross-family review after the critic`,
`second family review`

## Rules

- **After the critic.** The fresh critic reviews first and stays as it is.
  Save its output to a file outside the checkout, and never name it in the
  brief, so it stays out of the diff and `git status` Sol reads. A read-only
  sandbox can still read files outside the checkout, so this only makes the
  file harder for Sol to come across; it does not stop Sol from opening it.
  `gate` refuses a missing critic file, or one older than `HEAD`, the last
  checkout, or any uncommitted change, before Sol starts.
- **Sol only.** Never substitute a Gemini, Grok, Claude, or mixed "Fusion"
  model. `sol_loop.py` refuses any id that is not `gpt-<version>-sol`.
- **2 rounds at most.** Round 1 is full. Round 2 checks only open findings and
  code changed since round 1. There is no round 3; hand what is open to a
  human.
- **Kept findings are defects.** Each needs a file, a line, and a repro (a
  failing test, a command, or concrete inputs). Nits, including style, are
  dropped. A label other than blocker, should, or nit is dropped as
  `unknown-severity`, and a `CHANGES` verdict with no finding lines takes
  the WARN path.
- **One reviewer.** Sol must not start subagents or other reviewers.
- **Agent side only.** Never add a CI job or workflow step that calls Sol.

## Scripts

### `sol_loop.py`

This skill's `sol_loop.py` holds the steps that must not depend on judgment. Run it
from the root of the checkout under review with the plugin locator:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/sol-loop/scripts/sol_loop.py gate --route t3 --critic-findings CRITIC_FILE --model SOL_MODEL --author-family anthropic --pr PR_NUMBER; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

When no plugin root holds `lib/ptk_run.py` (for example Codex, or a plain
checkout), run the script beside this SKILL.md directly with the same
arguments. It finds its own plugin's `lib/`:

```bash
python3 "<folder that holds this SKILL.md>/scripts/sol_loop.py" gate --route cli --critic-findings CRITIC_FILE --model SOL_MODEL --author-family anthropic
```

Swap `gate` and its flags for the other steps:

| Step | When | Extra flags | Exit codes |
|------|------|-------------|------------|
| `gate` | Before each round | `--route t3\|native\|cli\|none` | `0` proceed or skip (read `verdict`), `1` round cap hit, `2` config error |
| `record` | After Sol replies | `--reply REPLY_FILE --reviewed-head SHA` | `0` logged, `1` round cap hit, `2` config error or log not written, `3` reply had no verdict (WARN) |
| `review` | CLI route: runs Sol, then records | `--brief-file BRIEF` | as `record`, plus `3` when the CLI call fails (WARN) and `2` when no CLI is installed |
| `unavailable` | Sol was started and failed | `--failure-class CLASS --detail TEXT` | `3` WARN logged (even if the critic file is unreadable), `2` refused model id |
| `outcome` | After you answer a finding | `--run LOG --id S1 --outcome fixed\|disagree\|declined --evidence TEXT` | `0` updated, `2` bad log or id |
| `summarize` | Any time | none | `0` totals printed |

`gate`, `record`, and `unavailable` share `--critic-findings`, `--model`,
`--author-family`, `--pr`, and `--repo`.

### Modules

Imported by `sol_loop.py`, never run alone:

- `sol_findings.py` parses Sol's reply, drops nits and findings without a
  file, line, or repro, and marks `sol_only` against the critic's locations.
- `sol_cli.py` runs the last-resort CLI route, read-only, and classifies a
  failed call.
- `sol_git.py` checks the critic file against `HEAD`, the last checkout, and
  uncommitted changes, including deletions and renames.
- `sol_ledger.py` reads, writes, and totals the run logs.

## Process

### Phase 1: Scope

Run `git status --short`. Do not stash, discard, or include unrelated changes.
Limit the review to the change's paths if they separate cleanly. Otherwise stop
and ask.

Find the base after `git fetch origin`:

- PR: read `baseRefName` and the head SHA with the github skill's
  `get_pr_context.py --pull-request <n>`. Check out the branch only if it is
  clean. Confirm `HEAD` is the PR head, or ahead only by this change. Base:
  `git merge-base HEAD origin/<baseRefName>`.
- Local: `git merge-base HEAD origin/<default-branch>`. With no remote, use a
  base the user names, or `HEAD` for uncommitted changes only.

The change is base to working tree in those paths, untracked files included.
Use one diff command for every round. State the intent and what is out of
scope in 1 or 2 sentences. Run the covering checks. Do not send code this
change breaks. Note missing or failing checks in the brief.

If no current critic output exists for `HEAD`, run the fresh critic agent now
and save its reply to a file.

Name the family of the model that wrote the change: `anthropic`, `openai`, or
`unknown`. When a GPT model wrote it, `gate` skips the pass: Sol would be the
same family. `unknown` runs, and the log flags it.

### Phase 2: Start Sol

Use the first route the harness supports, then run `gate` with it:

- **T3 Code**: call `orchestrator_capabilities` and pick the latest
  `gpt-<version>-sol` on the `codex` provider, unless the user named a
  version. Do not hardcode an id. Use `delegate_task` each round
  (`role: "review"`, `mode: "async"`). Save the `taskId`, and use a new
  `clientRequestId` per round. Do not use `t3_thread_send`,
  `create_threads`, or `t3_thread_launch` for review. `--route t3`.
- **The harness's own subagent**: a harness that already runs several model
  families delegates to Sol with its own tool. Copilot CLI: the `task` tool
  with a Sol `model`. Factory Droid, OpenCode: a subagent definition whose
  `model:` is Sol. Hermes: its subagent delegation on Sol. Codex:
  `spawn_agent` on Sol. In Claude Code, only a custom subagent set up to run
  Sol counts. Keep its id. `--route native`.
- **A native CLI (last resort)**: write the brief to a file and run
  `sol_loop.py review --brief-file BRIEF`. It calls
  `codex exec -m <sol> -s read-only`, or `droid exec -m <sol>` (read-only by
  default) when Codex is absent, then records the reply itself.
  `--route cli`; `gate` skips quietly when neither CLI is installed.
- **No route**: `gate --route none` prints `SKIPPED` and writes no log. Say
  "sol-loop skipped: no Sol route" in one line and stop. This is the quiet
  default for a harness that cannot reach Sol: no WARN, no run file.

`gate` prints `PROCEED` with the round number, `SKIPPED` with a reason, or
`ESCALATE` when 2 rounds are already logged for the branch. Run the round only
on `PROCEED`.

Do not edit scoped files while Sol runs. Wait for the notice. Do not poll or
start a second reviewer. A timeout, an error, or no reply is not approval: run
`unavailable` with the class (`timeout`, `5xx`, `rate-limit`,
`invalid-output`, `quota`, `model-unsupported`, `auth`, `cancelled`, or
`unknown`). It prints the WARN with reason `review-model-unavailable` and
"Review model unavailable, deferring to human." Then stop. Never fall back to
a Claude reviewer or any other model.

Round 1 brief (a T3 child gets no history):

```
Review only. Do not edit, commit, push, comment on PRs, or start subagents.
Repo: <abs path> Base: <sha> Intent: <intent> Out of scope: <scope> Checks: <results>
See: git diff <base> [-- <paths>]; git status --short (read untracked).
Read surrounding code. Find bugs, broken callers, mismatch with intent.
Skip style. Hold to the smallest change. Flag code, tests, or guards the
intent does not need. Other paths, rare cases, small perf, extra compat: nits.
Security, data loss, and trust boundaries: judge by impact, never by rarity.
blocker = intended case wrong. should = real bug callers will hit, in intent. nit = rest.
Every blocker or should needs a file, a line, and a repro. One without all three is discarded.
Reply:
VERDICT: APPROVE or CHANGES
S1 [blocker|should|nit] <file>:<line> <claim>. Repro: <test, command, or inputs>. Fix: <suggestion>
```

Save Sol's reply to a file and run `record` with `--reviewed-head` set to the
`head_sha` that `gate` printed. If HEAD moved since, the log keeps the
reviewed SHA and adds `head_at_record`. A reply with no `VERDICT:` line is
`invalid-output`: `record` takes the WARN path itself.

### Phase 3: Answer findings

Check each kept finding and its severity yourself. Another path, a rare case,
or a small cost is a nit, whatever label it came with. A security, data-loss,
or trust-boundary defect is never a nit for being rare: judge its impact and
whether a caller can reach it.

- **Agree**: make the smallest fix. Prefer deleting or narrowing over a new
  lock, cache, helper, or option. Add one focused test that fails without the
  fix, if the intent needs it.
- **Disagree**: say why, with evidence (file:line, a test, output).
- **Out of scope**: decline in one line and list it as a follow-up.

Record each answer with `outcome`. Re-run the checks and
`git diff --shortstat <base>`. If review grew the diff, cut first. Do not
agree just to end the loop.

### Phase 4: Next round

Start round 2 only if a blocker or should is open, behavior code changed, or
the approval does not cover the current behavior diff. Run the fresh critic
again on the new `HEAD`, then `gate`. Use a fresh `delegate_task` in T3, or
follow up the saved native id. Send the round 1 brief, the ledger (`fixed:`,
`disagree:`, `declined:` with evidence), the same base diff, and the change
since round 1. Tell Sol: only open ids and changed code count. Mark each old id
`resolved` or `still open: <reason>`.

### Phase 5: Stop and ship

- **Agreed**: `APPROVE` on the current behavior diff, no blocker or should
  open, and no concern of your own.
- **Stuck**: an item stays disputed after two replies, or `gate` returns
  `ESCALATE`. Show both sides in 2 or 3 lines each. The user decides. Running
  out of rounds is not approval.

Do not push during the loop. Push after agreement only if the user asked to
push, ship, or update the PR. If you push to a PR, add this line above the
model line: `Reviewed with sol-loop: <N> rounds with <model>. Sol verdict:
approved`. Add `on <effort>` only if you verified it.

Report: rounds, model, what Sol changed, diff size before and after, fixed and
declined findings with reasons, Sol-only count, usage if exposed (else say so),
and whether you pushed.

## Run log

Each `record`, `unavailable`, escalation, and logged skip writes one JSON file
to `<artifact root>/metrics/sol-loop/<timestamp>-<branch>-r<round>-<status>.json`.
The artifact root is this plugin's default artifact directory in the checkout,
or `AI_AGENTS_ARTIFACT_ROOT` when set. Commit each run file with the branch it
reviewed. A linked worktree is removed when its work ends, and an uncommitted
file goes with it; committed files also keep the round count with the branch.

Each file holds the branch, PR, head SHA, round, model, author family, verdict,
failure class, and each kept finding with its id, severity, `sol_only` flag,
and outcome. Dropped findings carry a reason. A finding is `sol_only` unless
the critic cited the same file within 3 lines of it, or inside a cited range.
Ties go to overlap. A critic citation with no `path:line` or `#L` anchor is
not matched, so a finding it covers still counts as `sol_only`. Read the count
as an estimate, not a bound.

`summarize` totals runs by status, kept and dropped findings, Sol-only and
overlap counts, and the outcome of each Sol-only finding. Sol-only findings
you marked `fixed` are the true catches that measure whether Sol earns its
place.

## Anti-Patterns

- Falling back to a Claude, Gemini, or Grok reviewer when Sol fails. Run
  `unavailable` and stop.
- Running a third round, or a second reviewer in parallel.
- Agreeing with a finding just to end the loop, or growing the diff to
  answer a nit.
- Leaving the run file uncommitted in a worktree that will be removed.

## Verification

- [ ] The fresh critic reviewed `HEAD` before `gate` ran.
- [ ] Sol ran on a `gpt-<version>-sol` model, at most 2 rounds.
- [ ] Each round's reply went through `record`, and every kept finding has an
      `outcome`.
- [ ] A failed round ran `unavailable`; no other model reviewed in its place.
- [ ] The run files are committed with the branch.

## Turning it off

Set `AI_AGENTS_SOL_PASS=off`. `gate` then prints `SKIPPED` and logs the skip.
