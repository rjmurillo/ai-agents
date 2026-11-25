# Hermes Pack Layout by Jobs To Be Done

Date: 2026-11-25. Issue: #7591 (parent epic #7580). Status: proposal for the owner's decision.

Nothing here changes `templates/platforms/hermes.yaml`. The implementation is a later pull request.

## Recommendation

Group the Hermes packs by the job a user hires them for. Ship six packs:

| Pack | The user says | Status |
|---|---|---|
| `project-toolkit-delivery` | "Build, test, review, and ship my change, then see the PR through." | Existing, reshaped |
| `project-toolkit-git` | "Rescue, adopt, or rewrite a branch or a stale PR." | New |
| `project-toolkit-azure-devops` | "Run my Azure DevOps and OneBranch pipeline work." | New (PR #7628 shape) |
| `project-toolkit-knowledge` | "Help me decide what to build, and remember why." | Existing, reshaped |
| `project-toolkit-quality` | "Harden this system, and get a second model's opinion." | Existing, reshaped |
| `project-toolkit-authoring` | "Help me write skills, prompts, and docs." | Existing, reshaped |

`delivery` is the base pack. `git` and `azure-devops` are add-ons that hand off to it.

Hermes opens a PR through `ship`, the same path every other host uses. `ship`, `review`, `security-scan`, `pr-quality`, and `security-detection` return to Hermes. Two one-line rewordings in `security-scan` make that possible. `push-pr` stays on Hermes until that `ship` ships there, then retires on every host together.

## Premise check

The brief said delivery holds 400 files. That count is from `d41431afe6` (2026-11-25).

- At `71ab5b15b3` (2026-11-25), main has four packs: delivery 299, knowledge 263, authoring 208, quality 166.
- PR #7542 landed the quality split after the brief's count. Delivery is not at the cap today.
- PR #7628 (head `f450839777`, 2026-11-25) predates that split. Its cap reason no longer holds. GitHub reports it `CONFLICTING`, so it needs a rebase.

The cap still matters for two reasons. Restoring the PR-opening chain adds 60 files. ADR-127 driver scripts add 31 more to delivery's skills.

## Constraints the layout must obey

Each one is measured, with how it was measured.

1. **Install cap.** Hermes refuses a plugin over 400 files or 10 MB (ADR-115 Decision 6). Each pack carries `lib/` (57 files) and `plugin.json`, so every pack starts at 58 files (`git ls-files src/hermes/project-toolkit-delivery/lib`, `71ab5b15b3`, 2026-11-25).
2. **Path references cannot cross packs.** `build/scripts/hermes_pack_checks.py` fails the build when a file names another pack's `scripts`, `references`, `lib`, `templates`, `assets`, or `resources` path. A path into another pack does not resolve on Hermes.
3. **Name references can cross packs.** `Skill(skill="x")` resolves by name across every installed plugin. At the pinned hermes-agent commit `63d0b94120`, `skill_view(name, file_path)` also reads a file inside another skill by name (`tools/skills_tool.py:550`). A cross-pack reading list can name the skill and file instead of a path.
4. **Paths built in code are invisible to the check.** On the pilot branch (`3a619dabd6`, 2026-11-25), `ship/scripts/_ship_common.py:380` joins sibling paths at run time. `ship_pr.py:97` runs `github/scripts/pr/new_pr.py`, and `ship_preflight.py:116` runs `review`'s `validate_review_marker.py`. So `ship`, `github`, and `review` must share a pack.
5. **`github` is the hub.** It is 107 files at `71ab5b15b3` (2026-11-25). Nine shipped skills run its scripts by path: `github-url-intercept`, `validate-pr-description`, `push-pr`, `pr-autofix`, `pr-review`, `pr-comment-responder`, `research`, and, through the pilot, `ship`. `new_pr.py` loads modules inside the `github` skill, so `lib/github_core` cannot stand in for it today.
6. **The guard blocks `dangerous` packs.** Hermes' `plugin_guard` blocks a `dangerous` verdict even with `--force`. A `caution` verdict installs with `--force` after review.

## Jobs to be done

A Hermes user installs a pack to finish a job. Each job lists the skills that serve it.

| # | Job | Skills | Pack |
|---|---|---|---|
| J1 | Plan, build, and test a change | `plan`, `execution-plans`, `build`, `test`, `analyze`, `validation-authority`, `doc-accuracy`, `code-qualities-assessment`, `taste-lints`, `golden-principles`, `style-enforcement`, `quality-grades`, `dx-review`, `orphan-ref-validator`, `agent-harness-reference`, `sync`, `steering-matcher` | delivery |
| J2 | Review a change and open the PR | `review`, `ship`, `pr-quality`, `security-scan`, `security-detection`, `codeql-scan`, `validate-pr-description`, `push-pr` (until retired) | delivery |
| J3 | See a PR through to merge | `github`, `github-url-intercept`, `pr-review`, `pr-autofix`, `pr-babysit`, `pr-comment-responder`, `reviewer-findings`, `research`, `ai-agents-external-claims` | delivery |
| J4 | Rescue, adopt, or rewrite a branch or stale PR | `modernize`, `takeover`, `merge-resolver`, `git-advanced-workflows`, `maintainer-review` | git |
| J5 | Run Azure DevOps and OneBranch pipeline work | `pipeline-validator`, `windows-image-updater` | azure-devops |
| J6 | Decide what to build | `spec`, `spec-generator`, `requirements-interview`, `adr-generator`, `decision-critic`, `decision-question`, `pre-mortem`, `cynefin-classifier`, `buy-vs-build-framework`, `chestertons-fence`, `programming-advisor`, `domain-design`, `business-strategy`, `negotiation`, `work-operating-model`, `world-model-diagnostic`, `panning-for-gold`, `software-engineering-library`, `avoiding-manufactured-work`, `autoplan`, `analysis-provenance`, `evidence-provenance` | knowledge |
| J7 | Remember and recall | `memory`, `memory-consolidate`, `memory-documentary`, `memory-enhancement`, `curating-memories`, `reflect`, `retrospective`, `checkpoint`, `context-gather`, `context-hub-setup`, `using-serena-symbols`, `codebase-documenter`, `stuck-detection` | knowledge |
| J8 | Harden a system | `threat-modeling`, `security-review`, `chaos-experiment`, `slo-designer`, `observability`, `metrics`, `destructive-change-safety` | quality |
| J9 | Get a second model's opinion | `llm-council`, `sol-loop`, `benchmark-models` | quality |
| J10 | Write skills, prompts, and docs | `skillforge`, `skillify`, `skillopt`, `skill-bootstrap`, `context-optimizer`, `prose-self-check`, `prompt-engineer`, `technical-writing`, `api-doc-authoring`, `fix-markdown-fences` | authoring |

J1, J2, and J3 share one pack. Constraints 4 and 5 force that: `ship` needs `github` and `review`, and the PR skills need `github`. The seam between "decide" (J6) and "build" (J1) sits between `spec` and `plan`.

## Proposed packs

Counts use `find_references` and `skill_files` from `build/scripts/hermes_pack_checks.py`, at `71ab5b15b3` (2026-11-25). Each count includes the 58-file `lib/` and `plugin.json` overhead, and drops `excludedFiles`.

- "Now" includes the pilot `ship` (8 files at `3a619dabd6`, 2026-11-25).
- "After P0" and "After P0+P1" add one file per script that `.project-toolkit/analysis/skill-gap-audit-2026-11-25.md` names. `push-pr` adds none, because it retires.
- No test files live under `src/claude/skills/` (0 at `71ab5b15b3`, 2026-11-25), so driver tests add nothing.

| Pack | Skills | Now | After P0 | After P0+P1 | Free of 400 | Guard verdict (staged) | Jobs |
|---|---|---|---|---|---|---|---|
| delivery | 34 | 343 | 349 | 362 | 38 | `caution` | J1, J2, J3 |
| git | 5 | 72 | 78 | 80 | 320 | `safe` | J4 |
| azure-devops | 2 | 62 | 68 | 68 | 332 | `safe` | J5 |
| knowledge | 35 | 265 | 265 | 268 | 132 | `safe` | J6, J7 |
| quality | 10 | 122 | 122 | 125 | 275 | `safe` | J8, J9 |
| authoring | 10 | 252 | 252 | 253 | 147 | `caution` | J10 |

All rows measured 2026-11-25 against `71ab5b15b3` and pilot `3a619dabd6`.

The largest staged pack is delivery at 4.38 MB, under the 10 MB cap (2026-11-25).

Guard verdicts come from the pinned guard (`tools/plugin_guard.py` at hermes-agent `63d0b94120`) run on staged copies. Delivery's `high` findings are the 13 it has on main today, with none added. Restored `review` and pilot `ship` rate `safe` alone. Knowledge stays `safe` because `plan` stays in delivery. Moving `plan` into knowledge would add `plan/SKILL.md`'s `context_exfil` finding there and force `--force` on knowledge.

### Membership

- **delivery (34):** `agent-harness-reference`, `ai-agents-external-claims`, `analyze`, `build`, `code-qualities-assessment`, `codeql-scan`, `doc-accuracy`, `dx-review`, `execution-plans`, `github`, `github-url-intercept`, `golden-principles`, `orphan-ref-validator`, `plan`, `pr-autofix`, `pr-babysit`, `pr-comment-responder`, `pr-quality`, `pr-review`, `push-pr`, `quality-grades`, `research`, `review`, `reviewer-findings`, `security-detection`, `security-scan`, `ship`, `steering-matcher`, `style-enforcement`, `sync`, `taste-lints`, `test`, `validate-pr-description`, `validation-authority`.
- **git (5):** `git-advanced-workflows`, `maintainer-review`, `merge-resolver`, `modernize`, `takeover`.
- **azure-devops (2):** `pipeline-validator`, `windows-image-updater`.
- **knowledge (35):** today's 34, minus `prompt-engineer`, plus `spec-generator` and `stuck-detection`: `adr-generator`, `analysis-provenance`, `autoplan`, `avoiding-manufactured-work`, `business-strategy`, `buy-vs-build-framework`, `checkpoint`, `chestertons-fence`, `codebase-documenter`, `context-gather`, `context-hub-setup`, `curating-memories`, `cynefin-classifier`, `decision-critic`, `decision-question`, `domain-design`, `evidence-provenance`, `memory`, `memory-consolidate`, `memory-documentary`, `memory-enhancement`, `negotiation`, `panning-for-gold`, `pre-mortem`, `programming-advisor`, `reflect`, `requirements-interview`, `retrospective`, `software-engineering-library`, `spec`, `spec-generator`, `stuck-detection`, `using-serena-symbols`, `work-operating-model`, `world-model-diagnostic`.
- **quality (10):** `benchmark-models`, `chaos-experiment`, `destructive-change-safety`, `llm-council`, `metrics`, `observability`, `security-review`, `slo-designer`, `sol-loop`, `threat-modeling`.
- **authoring (10):** `api-doc-authoring`, `context-optimizer`, `fix-markdown-fences`, `prompt-engineer`, `prose-self-check`, `skill-bootstrap`, `skillforge`, `skillify`, `skillopt`, `technical-writing`.
- **Still excluded (8):** `skill-doctor` (1 MiB file), plus `adr-review`, `cva-analysis`, `memory-search`, `memory-maintenance`, and `planner` (each `dangerous`), plus `memory-gate` and `memory-reflexion` (they refer to `memory-search` or `memory-maintenance`).

### Moves from today's table

| Skill | From | To | Reason |
|---|---|---|---|
| `modernize`, `takeover`, `git-advanced-workflows`, `merge-resolver`, `maintainer-review` | delivery | git | J4, and 22 files of room in delivery. |
| `pipeline-validator`, `windows-image-updater` | delivery | azure-devops | J5. Only Azure DevOps users need them. |
| `benchmark-models` | delivery | quality | J9: it compares models. |
| `codeql-scan` | quality | delivery | J2. `review`'s `codeql_scanner_guard.py:49` names its scripts path. |
| `golden-principles`, `style-enforcement` | quality | delivery | J1 and J2: both are code gates, and `review` runs `golden-principles` as an axis. |
| `technical-writing`, `fix-markdown-fences` | quality | authoring | J10: both edit prose. |
| `api-doc-authoring` | delivery | authoring | J10: it writes docs. |
| `prompt-engineer` | knowledge | authoring | J10: it writes prompts. |

Restored to Hermes: `ship`, `review`, `security-scan`, `pr-quality`, `security-detection` (delivery); `spec-generator`, `stuck-detection` (knowledge). `spec-generator` joins `spec`, which is already in knowledge, and it calls 9 shipped knowledge skills by name.

## How Hermes opens a PR

Today `ship` is excluded on Hermes, because the closure runs `ship` to `review` to `security-scan`. The guard rates `security-scan` `dangerous`. `push-pr` is Hermes' only PR-opening skill.

Measured with the pinned guard on 2026-11-25:

| Skill (alone) | Verdict | `critical` or `high` lines |
|---|---|---|
| `security-scan` (main) | `dangerous` | `references/vulnerability-patterns.md:23` (`system_passwd_access`, critical; `path_traversal_deep`, high), `SKILL.md:180` (`sudo_usage`, high) |
| `security-scan`, line 23 reworded | `caution` | `SKILL.md:180` |
| `security-scan`, both lines reworded | `safe` | none |
| `security-scan`, reference file dropped by `excludedFiles` | `caution` | `SKILL.md:180` |
| `review` (main) | `safe` | none |
| `ship` (main and pilot `3a619dabd6`) | `safe` | none |

The two rewordings keep each line's meaning:

- `vulnerability-patterns.md:23`: the example input `../../../etc/passwd` becomes "a parent-relative path that escapes `base`".
- `SKILL.md:180`: the reader list "a shell, `ssh`, `sudo`, `psql`" names `sudo` as "a privilege wrapper". The source is `templates/skills/security-scan.SKILL.md.tmpl`.

The rewording changes text on every host. The `excludedFiles` route is Hermes-only, but it leaves `security-scan` at `caution` and drops a reference Hermes users need.

With both lines reworded, the closure clears. The PR path on Hermes becomes the path on every host:

1. `/build`, then `/test`, then `/review` writes the SHA-bound marker.
2. `/ship` runs its pre-flight checks. It invokes `security-scan` by name and runs `review`'s marker validator in the same pack.
3. `ship_pr.py` creates the PR through `github`'s `new_pr.py` (GitHub) or its own Azure DevOps path.

Every step lives in delivery. A Hermes user opens a PR with one pack.

### The fate of `push-pr`

- `push-pr` stays in delivery on Hermes until `ship` ships there.
- #7587 retires `push-pr` on every host. It must merge with or after the pull request that restores `ship` on Hermes. Merging it first leaves Hermes with no PR-opening skill.
- Retiring `push-pr` removes 2 files and 3 reviewed `high` findings from delivery (`push-pr/SKILL.md:33-35`, measured 2026-11-25).
- `takeover` names `push-pr` twice, and `autoplan`, `validate-pr-description`, and `agent-harness-reference` name it once each (2026-11-25). #7587 already owns those callers.

## Prerequisite edits

The implementation pull request makes these edits. Each one cuts a path that would cross packs, or clears a guard block.

| File | Line | Edit | Why |
|---|---|---|---|
| `src/claude/skills/security-scan/references/vulnerability-patterns.md` | 23 | Reword the example path | Clears the `critical` finding |
| `templates/skills/security-scan.SKILL.md.tmpl` | the source of rendered line 180 | Reword `sudo` | Clears the last `high` finding |
| `src/claude/skills/review/references/analyst.md` | 47 | Name `decision-critic` and its file, not a path | Cross-pack read to knowledge |
| `src/claude/skills/review/references/architect.md` | 51, 54 | Same, for `decision-critic` and `observability` | Cross-pack reads |
| `src/claude/skills/review/references/code-quality.md` | 52, 53 | Same, for `chestertons-fence` and `decision-critic` | Cross-pack reads |
| `src/claude/skills/review/references/decision-rigor.md` | 53-55 | Same, for `decision-critic` | Cross-pack reads |
| `src/claude/skills/review/references/observability.md` | 52-54 | Same, for `observability` | Cross-pack reads to quality |
| `src/claude/skills/review/references/reliability.md` | 54 | Same, for `observability` | Cross-pack read |
| `src/claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py` | 160, 202, 213 | Reword "Stricter than" docstrings to name the script, not its path | Comment-only edges to `github` and `pr-comment-responder` |
| `src/claude/skills/spec-generator/references/spec-prior-art-schema.md` | 158, 275-280 | Name `analyze` and `review` files without a path | Edges to delivery |
| `src/claude/skills/api-doc-authoring/SKILL.md`, `references/example-verification.md` | the `skills/test/references` lines | Name `test`'s file without a path | Edge to delivery |

The rewording pattern for a cross-pack read: "read `references/<file>.md` in the `<skill>` skill". On Hermes that is `skill_view("<skill>", "references/<file>.md")`. On Claude Code and Copilot CLI the agent finds the file the same way it finds the skill.

No `review` axis loses content. The reading lists still name the same files.

## Cross-pack references and install sets

After the edits above, no path crosses a pack. These name-level calls cross packs and work when both packs are installed (measured 2026-11-25 by `Skill(skill=...)` lines):

- `build` (delivery) calls `pre-mortem` and `analysis-provenance` (knowledge).
- `spec-generator` (knowledge) calls `doc-accuracy` and `golden-principles` (delivery), and `slo-designer` and `threat-modeling` (quality).
- `adr-generator` (knowledge) calls `doc-accuracy` (delivery).
- `takeover` and `modernize` (git) hand off to `github`, `pr-autofix`, `pr-comment-responder`, and `push-pr` (delivery) by name.
- `retrospective` (knowledge) runs `context-optimizer`'s `distill_artifact.py` (authoring), as today.

Packs to install per job:

| Job | Install |
|---|---|
| J1, J2, J3 (build, review, ship, see a PR through) | delivery |
| J4 (rescue a branch) | delivery, git |
| J5 (Azure DevOps pipelines) | delivery, azure-devops |
| J6, J7 (decide, remember) | knowledge |
| J8, J9 (harden, second opinion) | quality |
| J10 (write skills and docs) | authoring |
| The full toolkit | all six |

## Install order and reinstalls

One implementation pull request makes every move at once. Then each existing Hermes user reinstalls each pack they have one time.

1. Reinstall the packs you already have: delivery, knowledge, quality, authoring. Hermes needs `--force` to replace any installed pack. On 2026-11-24, an old pack left installed beside a new one listed moved skills twice until the old pack was reinstalled (`docs/training/install-on-every-host.md`).
2. Install the new packs you need: git, azure-devops.
3. Read the findings for `caution` packs (delivery, authoring) before you pass `--force`.

Reinstall count: one per existing pack, in one release. Richard's earlier option C (2026-11-25) cost two reinstalls of delivery, one per new pack. Landing PR #7628 alone first, then this layout, would also cost two.

The smoke's `FORCE_ALLOWED_FINDINGS` (`tests/e2e/hermes_runtime.py`) is keyed by pack. The moves keep every reviewed delivery finding in delivery, except `push-pr`'s three, which go away when it retires.

## Growth policy

- Delivery keeps 38 files free after P0 and P1. One shared `lib/` file now costs six slots, one per pack.
- An ADR-127 driver in `git` or `azure-devops` calls `lib/github_core`, never `skills/github/scripts`. A path into `github` would fail the build there.
- The Semgrep `nosemgrep` comment on `lib/ptk_run.py` lives at the `src/claude/lib` source (owner ruling, 2026-11-25). Every pack copy, new packs included, inherits it.
- The next seam, if delivery fills, is J1's gate skills. That needs the `review` axes to reach `code-qualities-assessment`, `doc-accuracy`, `golden-principles`, and `taste-lints` by name only.

## Rejected alternatives

1. **One delivery pack for every GitHub job.** It lands at 398 of 400 after P0 and P1 (2026-11-25). The next driver script breaks it.
2. **Option C: an `azure-devops` pack plus a pack for five P0 skills.** The second pack cannot build. `pr-review` and `pr-autofix` run `github` scripts by path, so they cannot leave `github`'s pack.
3. **A build pack split from a review-and-ship pack.** Build and test, plus their gates, go in one pack. Review, ship, and the PR skills go in the other. Most jobs then need both packs, and `review` loses its axes unless both are installed. It also leaves eight path edges to cut.
4. **Keep today's table and restore the chain into delivery.** Delivery lands at 389 of 400 after growth (2026-11-25). Five `review` paths still cross into knowledge and quality.
5. **Keep today's table and leave `ship` excluded.** Delivery has room (330 after growth), but Hermes keeps no PR path once #7587 retires `push-pr`.
6. **Drop `vulnerability-patterns.md` from the Hermes pack instead of rewording it.** `security-scan` stays `caution`, and Hermes users lose its remediation reference.

## Findings outside this task

Recorded for the owner. None is fixed here.

- **Guard drift.** The pinned guard reports 13 `high` findings in delivery and 2 in authoring at `71ab5b15b3` (2026-11-25). The install guide says 10 and 1. New ones: `github/scripts/issue/check_existing_pr_for_issue.py:122,124`, `code-qualities-assessment/references/calibration-examples.md:228,242,249`, `skill-bootstrap/scripts/adr_reason.py:184`. The smoke was NOT RUN, so whether it fails is unknown.
- **Stale exclusion reason.** `stuck-detection` rates `safe` with the pinned guard. Its `excluded` reason still says `dangerous`. ADR-115 already notes this.
- **Pilot description.** The pilot `ship` description still says "hand PR creation to push-pr" (`3a619dabd6`, 2026-11-25).
- **Excluded skills are close to restorable.** Each `dangerous` skill traces to 1 to 4 `critical` lines in reference prose: `adr-review/references/deletion-workflow.md:86`, `cva-analysis/references/SKILL_SPEC.md:110`, `memory-maintenance/references/benchmarking.md:352`, `memory-search/references/memory-router.md:293` and `skill-reference.md:209,276,292`, `planner/resources/plan-format.md:170`. Restoring them is out of scope.

## Open questions for the owner

1. Approve the six-pack layout, or name the job split you want instead.
2. Approve rewording two `security-scan` lines on every host, or keep `ship` off Hermes.
3. Close PR #7628 into the implementation pull request (one reinstall), or land it first (two).

## Method

- Pack counts: `skill_files` and `excludedFiles` from `build/scripts/hermes_pack_checks.py`, run over `src/claude/skills/` at `71ab5b15b3`. The method reproduces main's four committed pack counts exactly.
- Path edges: `find_references` from the same module, then every hit per edge read by hand. `find_references` keeps the first hit per skill pair only.
- Name edges: every `Skill(skill="...")` line in shipped `SKILL.md` and reference files.
- Guard: `tools/plugin_guard.py`, `plugin_guard_context.py`, and `skills_guard.py` read from hermes-agent `63d0b94120`, run on staged pack copies with `scan_plugin(..., source="local")`.
