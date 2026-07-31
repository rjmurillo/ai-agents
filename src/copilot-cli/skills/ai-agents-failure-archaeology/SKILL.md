---
name: ai-agents-failure-archaeology
description: The chronicle of this repo's settled battles. Maps each major incident to symptom, root cause, evidence path, and the artifact that fixed it, so nobody re-fights a decided question. Use when you say `has this failed before`, `why does this rule exist`, `failure archaeology`, `what happened with issue 2205`. Do NOT use for triaging a live failure (use `ai-agents-debugging-playbook`) or for extracting learnings from the current session (use `retrospective`).
version: 1.0.0
license: MIT
---

# ai-agents Failure Archaeology

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This repo's rules are fossils of incidents. Before you challenge a gate, weaken
a guard, or propose a "simpler" approach, check whether that battle was already
fought and what it cost. The canon lives in `.agents/retrospective/`
and `.serena/memories/`. Retro-cited short
SHAs (e.g. `ddb76e0`, `01e76615a`) are not reachable from `main`. GitHub permits
squash merge only on this repo, so a PR lands as one new commit and its branch
SHAs stay off `main`. One merge commit predates that setting (`0f13c85ab`,
PR #1, 2025-12-13) and its branch side is on `main`, so verify rather than
assume. Archaeology still routes through the retros and memories as primary
sources, not `git log`.

Depth per incident lives in `references/incidents.md` (read it when a table row
below is not enough). This file is the index and the verdict list.

## Triggers

- `has this failed before`
- `why does this rule exist`
- `failure archaeology`
- `what happened with issue 2205`
- `are we re-litigating a settled decision`

## Process

### Phase 1: Check the Major Incidents Table

If your question touches hooks, generators, drift, review iteration, escape
hatches, or silent defaults, it is probably one of these eight. Read the
matching subsection in `references/incidents.md` before doing anything else.

| Incident | One-line summary | Primary retro (in `.agents/retrospective/`) | Status |
|----------|------------------|--------------------------------------------|--------|
| #2205 customer wedge | Bare `./hooks/...` paths + Copilot CLI running hooks from the USER's cwd wedged every plugin customer for 33 days (v0.3.0 to v0.5.6); recovery was uninstall. First fix added 3 new defects; session 1873 fixed it with an empirical probe of Copilot CLI 1.0.57 | `2026-06-02-pr-2205-customer-wedge-incident.md` | Settled; gated by `scripts/validation/validate_hook_anchoring.py` + `tests/build_scripts/test_generate_hooks_runtime_contract.py` |
| #2290 payload casing | Copilot CLI payload field names depend on event-key casing: camelCase sends `toolName`/`toolArgs` (toolArgs is a JSON string); PascalCase sends `tool_name`/`tool_input`. FM-11 second occurrence | `2026-06-02-issue-2290-copilot-hook-payload-format.md` | Settled (PascalCase + dual-format shim); exit-143 timeout flagged P0, unresolved in that retro |
| #1887 iteration paradox | Guard framework built to cut review iteration took 69 commits / 254 conversations; Phase-6 audit showed the guards would have prevented 0 of its own 35 fix commits | `2026-05-05-pr-1887-iteration-paradox.md` | Settled diagnosis: bot concurrency (60-70% overlap) + `reviewThreads(first: 100)` pagination cliff drove the cost |
| #1989 recursive failure | The mitigation PR reproduced the failure modes it mitigated; M1 built on a false premise (pagination already existed), M4 threshold 6 vs repo max 4 could never fire, M5 guard never run on its own branch | `2026-05-10-pr-1989-recursive-failure.md` | Settled: 3 process rules (self-application, memory contradiction check, threshold calibration) |
| Session 1187 trust incident | `SKIP_PREPUSH` abused 3x within hours of creation; `git checkout --ours` corrupted main's session log; user: "You can't be trusted in the least bit." | `2026-02-08-session-1187-skip-prepush-abuse.md` | Settled: SKIP_PREPUSH removed; session-merge rule binding |
| PR #908 scope explosion | 59 commits / 95 files; unscoped `markdownlint --fix` reformatted 53 unrelated memory files into the diff | `2026-01-15-pr-908-comprehensive-retrospective.md` | Settled: birthed `scripts/validation/pre_pr.py`, commit caps, scoped lint |
| 2025-12-15 drift inversion | Agent edited the SOURCE (Claude agents) to match the GENERATED (templates); commit `ddb76e0` reverted | `2025-12-15-drift-detection-disaster.md` | Settled: drift shows difference, never direction; always ask which side is canonical |
| PR #1965 silent defaults | Verdict parser defaulted a missing `VERDICT:` line to non-blocking; 3 fix rounds because parser, exit-code translator, and workflow gate each had their own silent default | `2026-05-10-pr-1965-review-axes-convergence.md` + FM-10 in `FAILURE-MODES.md` | Settled: "there is no neutral default for a missing signal" |

Also settled, no dedicated retro: PR #1942 stale plugin cache. It deleted the
deprecated `workflow` skill from `.claude/skills/` but left `plugin.json` at
0.3.0; installed plugin caches key off the version, so installs kept shipping
the dead `/workflow` until the gap was hand-caught in PR #2114. Record and gate:
`build/scripts/validate_plugin_version_bump.py` docstring (lines 1-20).

### Phase 2: Check the Settled Battles List

These are decided. Re-opening one requires new evidence plus the change-control
path in `ai-agents-change-control`, not a fresh opinion.

| Settled position | Verdict | Evidence |
|------------------|---------|----------|
| Launcher-level fail-open wrapper | REJECTED. Exiting 0 on a broken launcher silently disables the hook; prevent the bad launcher at generation time, fail closed and loud if one escapes. Issue #2230 closed addressed-by-prevention | `2026-06-02-pr-2205-customer-wedge-incident.md:289-297`, `:411` |
| Self-referential tests | BANNED for runtime contracts. A test asserting the generator's own output passes when the generator is consistently wrong; it shipped 2 of the 3 session-1872 defects | `.claude/rules/canonical-source-mirror.md`; `2026-06-02-pr-2205-customer-wedge-incident.md:143` |
| Copilot CLI plugin-root env contract | SETTLED EMPIRICALLY (CLI 1.0.57, probe + env dump): `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, and bare `PLUGIN_ROOT` are all set, though the public docs list none of them. Anchor form: `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}` | `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` |
| Session-file merge conflicts | Always `git checkout --theirs` (keep main's file), rename yours to the next number. Main's session files are immutable audit records | `2026-02-08-session-1187-skip-prepush-abuse.md:334`; merge-resolver agent |
| Threshold-based detectors | MUST ship with a calibration table replaying the last ~5 real merged PRs. A detector that cannot fire on real history is not calibrated | `2026-05-10-pr-1989-recursive-failure.md:149-157` |
| Drift-gate failures | The output shows a difference, not a direction. Identify the canonical side before editing anything | `2025-12-15-drift-detection-disaster.md:283-286` |
| Silent defaults | No neutral default for a missing signal: raise or block, never assume PASS | `.agents/governance/FAILURE-MODES.md:387` (FM-10) |
| Frictionless escape hatches | Get teeth (logging, guards, approval) or get abused within hours. SKIP_PREPUSH is the proof | `2026-02-08-session-1187-skip-prepush-abuse.md:706`; catalog in `ai-agents-config-catalog` |
| Guards shipped without self-application | A guard PR must show the guard's output run against its own branch | `2026-05-10-pr-1989-recursive-failure.md:129-137` |
| CLI subcommands proposed from analogy | BANNED. Run `--help` first; two hallucinated install commands cost user trust in the #2290 session | `2026-06-02-issue-2290-copilot-hook-payload-format.md:74-82` |

### Phase 3: Map to the Failure-Mode Catalog

`.agents/governance/FAILURE-MODES.md` is the canonical taxonomy (11 patterns as
of 2026-07-02). Classify any new incident against it BEFORE proposing a new
class; FM-CONTRACT was once invented in a retro and had to be corrected to
FM-11 (`2026-06-02-issue-2290-copilot-hook-payload-format.md:311-321`).

| FM | Name | Anchor incident |
|----|------|-----------------|
| FM-1 | Context reading failure (95.8% session-start non-compliance in the anchor sample) | `2025-12-20-session-protocol-mass-failure.md` |
| FM-2 | Continuation reset after compaction | `2026-01-09-session-protocol-violation-analysis.md` |
| FM-3 | Ambiguous instruction inversion | `2025-12-17-protocol-compliance-failure.md` |
| FM-4 | False completion markers | `2026-01-13-pr894-test-coverage-failure.md` |
| FM-5 | Premature merge and deploy | `2025-12-22-pr-226-premature-merge-failure.md` |
| FM-6 | Multi-agent rubber-stamping | `2025-12-24-parallel-pr-review-session.md` |
| FM-7 | Self-contained agent delegation failure | `2025-12-19-self-contained-agents.md` |
| FM-8 | Security drift | `2026-01-04-pr760-security-suppression-failure.md` |
| FM-9 | Confident-incorrectness recurrence (claims of "matches/mirrors" without quoting the canonical source) | `2026-05-05-pr-1887-iteration-paradox.md`, `2026-05-08-pr-1897-confident-incorrectness-recurrence.md` |
| FM-10 | Silent defaults and guard-clause suppression | PR #1965 rounds 9-11; FM-10 section of `FAILURE-MODES.md` |
| FM-11 | Customer-facing generated artifact shipped without runtime verification | #2205 (first), #2290 (second) |

FM-10 is a mechanism that produces FM-4 symptoms; fix at the FM-10 layer
(harden the parser), not by lecturing the agent about honesty
(`FAILURE-MODES.md:391`).

### Phase 4: Do Your Own Archaeology

When the tables above do not answer the question:

1. **Search retros by keyword**, not the index:
   `grep -rli "<term>" .agents/retrospective/`. Do NOT trust
   `.agents/retrospective/INDEX.md`: it indexes a small fraction of the corpus.
   Measure the gap instead of quoting a snapshot:
   `grep -c "^. 20" .agents/retrospective/INDEX.md; set -- .agents/retrospective/*.md; echo $#`
   (9 indexed against 121 files on 2026-07-30).
2. **Search memories**: `grep -rli "<term>" .serena/memories/` or the
   `memory-search` skill. Decision memories (`decision-*.md`) record settled
   contracts; `root-cause-*.md` record why gates exist;
   `*-observations.md` record per-domain corrections.
3. **Resolve ADR references by content, never by number.** Numbers collided
   historically (8 ADRs renamed in issue #474) and retros cite numbers that
   later moved: the #2205/#2290 retros say "ADR-063" for the runtime contract,
   but the shipped ADR is `ADR-071-plugin-hook-runtime-contract-verification.md`;
   the real ADR-063 is memory-skill decomposition. Use
   `grep -rl "<topic>" .agents/architecture/`.
4. **Do not lean on `git log` for incident history.** Current squash-only merge
   policy leaves PR-branch SHAs such as `01e76615a` and `ddb76e0` off `main`.
   Verify ancestry, then use GitHub when the object is absent from your clone.
   Treat retros and memories as the primary record.
5. **Auto-retros are shallow.** Files named `*-auto-retro.md` are unfilled
   Stop-hook skeletons; a later hand-written incident retro may supersede them
   (the #2205 retro explicitly supersedes three of them, `:452-458`).
6. **Write what you find.** If you settle a new question, record it: a retro
   per `.claude/rules/retros.md` (classify against FAILURE-MODES.md, evidence
   links mandatory), a decision memory for contracts, or both. Use the
   `retrospective` skill for the structured workflow and `chestertons-fence`
   when the question is "why does this existing thing exist".

## Anti-Patterns

| Anti-pattern | Why it fails | Instead |
|--------------|-------------|---------|
| Proposing a fail-open wrapper "so hooks never break the user" | Re-litigates #2230; silently disabled protection is the worst outcome | Prevent at generation time; fail closed and loud (see `references/incidents.md`, Incident 1) |
| Testing a generator by asserting its own output string | Self-referential; passed while #2205 shipped broken for 33 days | Runtime-contract test with foreign cwd/env and a negative control (`ai-agents-empirical-probe-toolkit`) |
| Trusting vendor docs for runtime contracts | Docs were wrong by omission twice (#2205 env vars, #2290 payload) | Probe the pinned CLI version empirically (`agent-harness-reference` for the settled contract table) |
| "Fixing" a drift gate by editing whichever side is easier | 2025-12-15 inversion; edited the source of truth to match generated output | Identify the canonical side first (`ai-agents-architecture-contract`) |
| Citing an ADR by number from an old document | Numbers collided and moved (ADR-063 vs ADR-071) | Grep architecture dir by topic, verify the title |
| Shipping a detector with an intuition-chosen threshold | #1989 M4 threshold could never fire on real PRs | Calibrate against the last ~5 merged PRs, show the table |
| Adding a quick env-var bypass to reduce friction | Session 1187: abused 3x within hours; ended in a trust failure | Route new flags through `ai-agents-config-catalog` (define semantics, guard, telemetry) |
| Mining `git log` for incident history | Current squash-only policy leaves PR-branch SHAs off `main`; clone refs vary | Retros + memories + GitHub |

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

## Provenance and Maintenance

Compiled 2026-07-02 from primary sources. Volatile facts were re-verified
against the working tree on 2026-07-30. Re-verification commands:

| Fact | Source | Re-verify |
|------|--------|-----------|
| Retro corpus far exceeds INDEX.md coverage (121 files, 9 indexed rows as of 2026-07-30) | `.agents/retrospective/` | `set -- .agents/retrospective/*.md; echo $#; grep -c "^. 20" .agents/retrospective/INDEX.md` |
| Markdown memory corpus size | `.serena/memories/` | `python3 -c "from pathlib import Path; print(sum(1 for p in Path('.serena/memories').rglob('*.md') if p.is_file()))"` |
| Retro-cited SHAs unreachable from `main` under the current squash-only policy | repository merge settings | `gh api repos/rjmurillo/ai-agents -q '.allow_squash_merge, .allow_merge_commit, .allow_rebase_merge'` (expect `true`, `false`, `false`); locally, `for sha in ddb76e0 01e76615a; do git merge-base --is-ancestor "$sha" origin/main; printf "%s %s\n" "$sha" "$?"; done` (expect status `1` when an object is present, or a `fatal:` line and status `128` when absent) |
| 11 failure modes | `.agents/governance/FAILURE-MODES.md:16-28` | `grep -c "^. [0-9]" .agents/governance/FAILURE-MODES.md` |
| Historical SKIP_PREPUSH removal | Session 1187 retrospective | Confirm current Git hook jobs in `lefthook.yml`; do not reintroduce a global bypass |
| Anchoring gate + runtime-contract test + e2e exist | repo tree | `ls scripts/validation/validate_hook_anchoring.py tests/build_scripts/test_generate_hooks_runtime_contract.py tests/e2e/test_cli_hook_e2e.py` |
| ADR-071 is the runtime-contract ADR; ADR-063 is memory decomposition | `.agents/architecture/` | `head -1 .agents/architecture/ADR-071*.md .agents/architecture/ADR-063*.md` |
| Plugin-root env contract (CLI 1.0.57) | `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` | open the memory; re-probe per `ai-agents-empirical-probe-toolkit` if the CLI version moved |
| Exit-143 timeout status "unresolved" | `2026-06-02-issue-2290-copilot-hook-payload-format.md:59` | check open issues before assuming; `ai-agents-portability-campaign` Phase 3 owns verification |

Primary sources: the eight retros named in Phase 1;
`.agents/governance/FAILURE-MODES.md`;
`.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`,
`copilot-hooks-observations.md`, `root-cause-governance-enforcement.md`,
`root-cause-late-feedback.md`, `root-cause-scope-creep-tools.md`,
`ci-infrastructure-observations.md` (PR #1361 reproduce-on-main rule);
`.claude/rules/generated-artifacts.md`, `canonical-source-mirror.md`,
`retros.md`. Update this skill when FAILURE-MODES.md gains a pattern or a new
incident retro of #2205-class severity lands.
