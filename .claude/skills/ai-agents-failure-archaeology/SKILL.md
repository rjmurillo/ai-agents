---
name: ai-agents-failure-archaeology
description: The chronicle of this repo's settled battles. Maps each major incident to symptom, root cause, evidence path, and the artifact that fixed it, so nobody re-fights a decided question. Use when you say `has this failed before`, `why does this rule exist`, `failure archaeology`, `what happened with the customer wedge`. Do NOT use for triaging a live failure (use `ai-agents-debugging-playbook`) or for extracting learnings from the current session (use `retrospective`).
version: 1.0.0
license: MIT
metadata:
  distribution: repo-local
  routing:
    role: conditional-adjunct
    invoker: ai-agents-change-control
    trigger: ai-agents-change-control points here for the deep history behind a settled incident
    user-facing: false
---

# ai-agents Failure Archaeology

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers -->
This repo's rules are fossils of incidents. Before you challenge a gate, weaken
a guard, or propose a "simpler" approach, check whether that battle was already
fought and what it cost. The canon lives in `.project-toolkit/retrospective/` and
`.serena/memories/`; the provenance table below carries the commands that count
both. Full local history is present, but some retro-cited short SHAs (e.g.
`ddb76e0`) do not resolve locally, so archaeology still routes through the
retros and memories as primary sources, not `git log`.

Depth per incident lives in `references/incidents.md` (read it when a table row
below is not enough). This file is the index and the verdict list.

## Triggers

- `has this failed before`
- `why does this rule exist`
- `failure archaeology`
- `what happened with the customer wedge`
- `are we re-litigating a settled decision`

## Process

### Phase 1: Check the Major Incidents Table

If your question touches hooks, generators, drift, review iteration, escape
hatches, or silent defaults, it is probably one of these eight. Read the
matching subsection in `references/incidents.md` before doing anything else.

| Incident | One-line summary | Primary retro (in `.project-toolkit/retrospective/`) | Status |
|----------|------------------|--------------------------------------------|--------|
| Customer wedge | Bare `./hooks/...` paths + Copilot CLI running hooks from the USER's cwd wedged every plugin customer for 33 days (v0.3.0 to v0.5.6); recovery was uninstall. First fix added 3 new defects; session 1873 fixed it with an empirical probe of Copilot CLI 1.0.57 | `2026-06-02-pr-2205-customer-wedge-incident.md` | Settled; gated by `scripts/validation/validate_hook_anchoring.py` + `tests/build_scripts/test_generate_hooks_runtime_contract.py` |
| Payload casing | Copilot CLI payload field names depend on event-key casing: camelCase sends `toolName`/`toolArgs` (toolArgs is a JSON string); PascalCase sends `tool_name`/`tool_input`. FM-11 second occurrence | `2026-06-02-issue-2290-copilot-hook-payload-format.md` | Settled (PascalCase + dual-format shim); exit-143 timeout flagged P0, unresolved in that retro |
| Iteration paradox | Guard framework built to cut review iteration took 69 commits / 254 conversations; Phase-6 audit showed the guards would have prevented 0 of its own 35 fix commits | `2026-05-05-pr-1887-iteration-paradox.md` | Settled diagnosis: bot concurrency (60-70% overlap) + `reviewThreads(first: 100)` pagination cliff drove the cost |
| Recursive failure | The mitigation PR reproduced the failure modes it mitigated; M1 built on a false premise (pagination already existed), M4 threshold 6 vs repo max 4 could never fire, M5 guard never run on its own branch | `2026-05-10-pr-1989-recursive-failure.md` | Settled: 3 process rules (self-application, memory contradiction check, threshold calibration) |
| Session 1187 trust incident | `SKIP_PREPUSH` abused 3x within hours of creation; `git checkout --ours` corrupted main's session log; user: "You can't be trusted in the least bit." | `2026-02-08-session-1187-skip-prepush-abuse.md` | Settled: SKIP_PREPUSH removed; session-merge rule binding |
| Scope explosion | 59 commits / 95 files; unscoped `markdownlint --fix` reformatted 53 unrelated memory files into the diff | `2026-01-15-pr-908-comprehensive-retrospective.md` | Settled: birthed `scripts/validation/pre_pr.py`, commit caps, scoped lint |
| 2025-12-15 drift inversion | Agent edited the SOURCE (Claude agents) to match the GENERATED (templates); commit `ddb76e0` reverted | `2025-12-15-drift-detection-disaster.md` | Settled: drift shows difference, never direction; always ask which side is canonical |
| Silent defaults | Verdict parser defaulted a missing `VERDICT:` line to non-blocking; 3 fix rounds because parser, exit-code translator, and workflow gate each had their own silent default | `2026-05-10-pr-1965-review-axes-convergence.md` + FM-10 in `FAILURE-MODES.md` | Settled: "there is no neutral default for a missing signal" |

Also settled, no dedicated retro: the stale plugin cache. It deleted the
deprecated `workflow` skill from `.claude/skills/` but left `plugin.json` at
0.3.0; installed plugin caches key off the version, so installs kept shipping
the dead `/workflow` until the gap was hand-caught in a later PR. Record and gate:
`build/scripts/validate_plugin_version_bump.py` docstring (lines 1-20).

### Phase 2: Check the Settled Battles List

These are decided. Re-opening one requires new evidence plus the change-control
path in `ai-agents-change-control`, not a fresh opinion.

| Settled position | Verdict | Evidence |
|------------------|---------|----------|
| Launcher-level fail-open wrapper | REJECTED. Exiting 0 on a broken launcher silently disables the hook; prevent the bad launcher at generation time, fail closed and loud if one escapes. The tracking issue closed addressed-by-prevention | `2026-06-02-pr-2205-customer-wedge-incident.md:289-297`, `:411` |
| Self-referential tests | BANNED for runtime contracts. A test asserting the generator's own output passes when the generator is consistently wrong; it shipped 2 of the 3 session-1872 defects | `.claude/rules/canonical-source-mirror.md`; `2026-06-02-pr-2205-customer-wedge-incident.md:143` |
| Copilot CLI plugin-root env contract | SETTLED EMPIRICALLY (CLI 1.0.57, probe + env dump): `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, and bare `PLUGIN_ROOT` are all set, though the public docs list none of them. Anchor form: `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}` | `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` |
| Session-file merge conflicts | Always `git checkout --theirs` (keep main's file), rename yours to the next number. Main's session files are immutable audit records | `2026-02-08-session-1187-skip-prepush-abuse.md:334`; merge-resolver agent |
| Threshold-based detectors | MUST ship with a calibration table replaying the last ~5 real merged PRs. A detector that cannot fire on real history is not calibrated | `2026-05-10-pr-1989-recursive-failure.md:149-157` |
| Drift-gate failures | The output shows a difference, not a direction. Identify the canonical side before editing anything | `2025-12-15-drift-detection-disaster.md:280-283` |
| Silent defaults | No neutral default for a missing signal: raise or block, never assume PASS | `.agents/governance/FAILURE-MODES.md:390` (FM-10: `no neutral default for a missing signal`) |
| Frictionless escape hatches | Get teeth (logging, guards, approval) or get abused within hours. SKIP_PREPUSH is the proof | `2026-02-08-session-1187-skip-prepush-abuse.md:706`; catalog in `ai-agents-config-catalog` |
| Guards shipped without self-application | A guard PR must show the guard's output run against its own branch | `2026-05-10-pr-1989-recursive-failure.md:129-137` |
| CLI subcommands proposed from analogy | BANNED. Run `--help` first; two hallucinated install commands cost user trust in the payload-casing session | `2026-06-02-issue-2290-copilot-hook-payload-format.md:74-82` |

### Phase 3: Map to the Failure-Mode Catalog

`.agents/governance/FAILURE-MODES.md` is the canonical taxonomy; its `## Index`
table lists every pattern, severity, and anchor incident. Run
`corpus_index.py` (Scripts section) for the current count and names. Classify
any new incident against the Index BEFORE proposing a new class;
FM-CONTRACT was once invented in a retro and had to be corrected to FM-11
(`2026-06-02-issue-2290-copilot-hook-payload-format.md:311-321`).

Anchors this skill routes to most often:

- FM-9 confident incorrectness: `2026-05-05-pr-1887-iteration-paradox.md`,
  `2026-05-08-pr-1897-confident-incorrectness-recurrence.md`.
- FM-10 silent defaults: silent-defaults PR rounds 9-11.
- FM-11 unverified customer artifact: customer wedge (first), payload casing (second), a hand-authored artifact (third).
- FM-12 post-completion continuation: index row 12 of `FAILURE-MODES.md`.
- FM-13 state conflation in a boolean guard: index row 13 of `FAILURE-MODES.md`.

FM-10 is a mechanism that produces FM-4 symptoms; fix at the FM-10 layer
(harden the parser), not by lecturing the agent about honesty
(`FAILURE-MODES.md:394`).

### Phase 4: Do Your Own Archaeology

When the tables above do not answer the question:

1. **Search retros by keyword**, not the index:
   `grep -rli "<term>" .project-toolkit/retrospective/`. Do NOT trust
   `.project-toolkit/retrospective/INDEX.md`: it indexes a small fraction of the retro
   files. `corpus_index.py` prints both numbers (Scripts section).
2. **Search memories**: `grep -rli "<term>" .serena/memories/` or the
   `memory-search` skill. Decision memories (`decision-*.md`) record settled
   contracts; `root-cause-*.md` record why gates exist;
   `*-observations.md` record per-domain corrections.
3. **Resolve ADR references by content, never by number.** Numbers collided
   historically (8 ADRs renamed once) and retros cite numbers that
   later moved: the customer-wedge and payload-casing retros say "ADR-063" for the runtime contract,
   but the shipped ADR is `ADR-071-plugin-hook-runtime-contract-verification.md`;
   the real ADR-063 is memory-skill decomposition. Use
   `grep -rl "<topic>" .project-toolkit/architecture/`.
4. **Do not lean on `git log` for incident history.** Full local history is
   present, but squash-merged PR-branch SHAs cited in retros (e.g. `ddb76e0`)
   may not resolve locally. Check with the `sha-resolve` instrument; look
   unresolved ones up on GitHub and treat retros and memories as the primary
   record.
5. **Auto-retros are shallow.** Files named `*-auto-retro.md` are unfilled
   Stop-hook skeletons; a later hand-written incident retro may supersede them
   (the customer-wedge retro explicitly supersedes three of them, `:452-458`).
6. **Write what you find.** If you settle a new question, record it: a retro
   per `.claude/rules/retros.md` (classify against FAILURE-MODES.md, evidence
   links mandatory), a decision memory for contracts, or both. Use the
   `retrospective` skill for the structured workflow and `chestertons-fence`
   when the question is "why does this existing thing exist".

## Anti-Patterns

| Anti-pattern | Why it fails | Instead |
|--------------|-------------|---------|
| Proposing a fail-open wrapper "so hooks never break the user" | Re-litigates the rejected fail-open wrapper; silently disabled protection is the worst outcome | Prevent at generation time; fail closed and loud (see `references/incidents.md`, Incident 1) |
| Testing a generator by asserting its own output string | Self-referential; passed while the customer wedge shipped broken for 33 days | Runtime-contract test with foreign cwd/env and a negative control (`ai-agents-empirical-probe-toolkit`) |
| Trusting vendor docs for runtime contracts | Docs were wrong by omission twice (customer-wedge env vars, payload casing) | Probe the pinned CLI version empirically (`agent-harness-reference` for the settled contract table) |
| "Fixing" a drift gate by editing whichever side is easier | 2025-12-15 inversion; edited the source of truth to match generated output | Identify the canonical side first (`ai-agents-architecture-contract`) |
| Citing an ADR by number from an old document | Numbers collided and moved (ADR-063 vs ADR-071) | Grep architecture dir by topic, verify the title |
| Shipping a detector with an intuition-chosen threshold | The recursive-failure M4 threshold could never fire on real PRs | Calibrate against the last ~5 merged PRs, show the table |
| Adding a quick env-var bypass to reduce friction | Session 1187: abused 3x within hours; ended in a trust failure | Route new flags through `ai-agents-config-catalog` (define semantics, guard, telemetry) |
| Mining `git log` for incident history | Some retro-cited SHAs do not resolve locally even with full history present | Retros + memories + GitHub |

## Verification

Before you rely on or extend this chronicle:

- [ ] The claim you are about to act on cites a retro or memory path that you
      opened and read (not just this skill's summary of it).
- [ ] If you cited a line number, you re-verified it against the current file
      (retros are append-only but line numbers can shift when corrections are
      appended).
- [ ] If you are re-opening a settled battle, you have NEW evidence and you are
      going through `ai-agents-change-control`, not around it.
- [ ] If you found a new settled result, you recorded it (retro classified
      against FAILURE-MODES.md, or a decision memory) so the next reader finds
      a fossil instead of re-fighting the battle.

## Scripts

Corpus counts come from one script, not hand-typed numbers:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-failure-archaeology/scripts/corpus_index.py" --repo .
```

It prints retro file count, how many `INDEX.md` names, the missing paths, the
failure-mode count and names from the `## Index` table, and the memory file
count (`.serena/memories/*.md`, top level only). Add `--shas ddb76e0 01e76615a`
to test whether short SHAs resolve. Exit 1 means `INDEX.md` omits retros, which
is the normal state. It does not read retro content or check line anchors. The
`instruments.py` dispatcher lists this and the path, citation, and drift
checks: `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-failure-archaeology/scripts/instruments.py" --repo . list`.

## Provenance and Maintenance

Compiled 2026-07-02, refreshed 2026-10-31 at `42e409325`. Checks live in
`reverify.json`. Drift command:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name ai-agents-failure-archaeology --require
```

Facts the scripts do not cover:

| Fact | Source | Re-verify |
|------|--------|-----------|
| Historical SKIP_PREPUSH removal | Session 1187 retrospective | Confirm current Git hook jobs in `lefthook.yml`; do not reintroduce a global bypass |
| Anchoring gate, runtime-contract test, e2e exist | repo tree | `reverify.json` path checks, plus `tests/e2e/test_cli_hook_e2e.py` |
| ADR-071 is the runtime-contract ADR; ADR-063 is memory decomposition | `.project-toolkit/architecture/` | `head -1 .project-toolkit/architecture/ADR-071*.md .project-toolkit/architecture/ADR-063*.md` |
| Plugin-root env contract (CLI 1.0.57) | `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` | open the memory; re-probe per `ai-agents-empirical-probe-toolkit` if the CLI version moved |
| Exit-143 timeout status "unresolved" | `2026-06-02-issue-2290-copilot-hook-payload-format.md:59` | check open issues before assuming; `ai-agents-portability-campaign` Phase 3 owns verification |

Primary sources: the eight retros named in Phase 1;
`.agents/governance/FAILURE-MODES.md`;
`.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`,
`copilot-hooks-observations.md`, `root-cause-governance-enforcement.md`,
`root-cause-late-feedback.md`, `root-cause-scope-creep-tools.md`,
`ci-infrastructure-observations.md` (reproduce-on-main rule);
`.claude/rules/generated-artifacts.md`, `canonical-source-mirror.md`,
`retros.md`. Update this skill when FAILURE-MODES.md gains a pattern or a new
incident retro of customer-wedge-class severity lands.
