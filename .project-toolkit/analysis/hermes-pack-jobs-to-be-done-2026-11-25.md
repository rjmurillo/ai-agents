# Hermes Pack Layout by Jobs To Be Done

Date: 2026-11-25. Issue: #7591 (parent epic #7580). Status: proposal for the owner's decision.

Nothing here changes `templates/platforms/hermes.yaml`. The implementation is a later pull request.

## Recommendation

Group the Hermes packs by the job a user hires them for. Ship six packs:

| Pack | The user says | Status |
|---|---|---|
| `project-toolkit-delivery` | "Build, test, review, and ship my change, then see the PR through." | Existing, reshaped |
| `project-toolkit-git` | "Adopt someone else's branch, or rewrite a branch's history." | New |
| `project-toolkit-azure-devops` | "Run my Azure DevOps and OneBranch pipeline work." | New (PR #7628 shape) |
| `project-toolkit-knowledge` | "Help me decide what to build, and remember why." | Existing, reshaped |
| `project-toolkit-quality` | "Harden this system, and get a second model's opinion." | Existing, reshaped |
| `project-toolkit-authoring` | "Help me write skills, prompts, and docs." | Existing, reshaped |

The rule a user can predict: always install delivery. Add `git` or `azure-devops` for those jobs. Add `knowledge`, `quality`, or `authoring` for theirs.

Hermes opens a PR through `ship`, once the ADR-127 `ship` pilot rewires `ship` to open the PR itself. `ship`, `review`, `security-scan`, `pr-quality`, and `security-detection` return to Hermes. Two one-line rewordings in `security-scan` make that possible. `push-pr` stays on Hermes until that `ship` ships there.

## Preconditions and order

The layout depends on the pilot `ship`, not main's.

- On main at `71ab5b15b3` (2026-11-25), `ship` hands PR creation to `push-pr` (`src/claude/skills/ship/SKILL.md:4` and `:159`). It has 4 files and no `scripts/`.
- On the pilot branch at `3a619dabd6` (2026-11-25), `ship` adds `ship_pr.py`, which can open the PR through `github`'s `new_pr.py`. It has 8 files. Its `SKILL.md` still hands off to `/push-pr` (lines 31 and 159), so the pilot must also rewire the skill text.
- Every count below uses the pilot `ship`.

Required order:

1. Land the `ship` driver wiring (#7586) with `push-pr` still shipped. `ship` must call its publish driver and must not delegate to `push-pr`.
2. The implementation pull request for this layout merges.
3. Retire `push-pr` (#7587) only when step 2 has proven the replacement on Hermes.

The pilot owner confirmed that #7586 can land before #7587. Do not wait for pilot tracker #7581 to close: it is blocked by #7587. #7586 remains open and depends on #7582 through #7585 plus the pilot review and evidence gates.

If #7587 merged before step 2, Hermes would have no skill that opens a PR. If this layout shipped before step 1, Hermes `ship` would call `push-pr`, which #7587 then removes.

## Premise check

The brief said delivery holds 400 files. That count is from `d41431afe6` (2026-11-25).

- At `71ab5b15b3` (2026-11-25), main has four packs: delivery 299, knowledge 263, authoring 208, quality 166.
- PR #7542 landed the quality split after the brief's count. Delivery is not at the cap today.
- PR #7628 (head `f450839777`, 2026-11-25) predates that split. Its cap reason no longer holds. GitHub reports it `CONFLICTING`, so it needs a rebase.

The cap still matters. Restoring the PR-opening chain adds 56 files (pilot `ship`, `review`, `security-scan`, `pr-quality`, `security-detection`; 2026-11-25). ADR-127 P0 and P1 driver scripts add 31 files to today's delivery skills (299 to 330, 2026-11-25). Under the proposed table, delivery grows by 21 (351 to 372).

## Constraints the layout must obey

Each one is measured, with how it was measured.

1. **Install cap.** Hermes refuses a plugin over 400 files or 10 MB (ADR-115 Decision 6). Each pack carries `lib/` (57 files) and `plugin.json`, so every pack starts at 58 files (`git ls-files src/hermes/project-toolkit-delivery/lib`, `71ab5b15b3`, 2026-11-25).
2. **Path references cannot cross packs.** `build/scripts/hermes_pack_checks.py` fails the build when a file names another pack's `scripts`, `references`, `lib`, `templates`, `assets`, or `resources` path. A path into another pack does not resolve on Hermes.
3. **Name references can cross packs.** `Skill(skill="x")` resolves by name across every installed plugin. At the pinned hermes-agent commit `63d0b94120`, `skill_view(name, file_path)` reads a file inside another skill by name (`tools/skills_tool.py`, function at line 550, docstring at line 552). This was read, not run in a live session.
4. **Paths built in code are invisible to the check.** On the pilot branch, `ship/scripts/_ship_common.py:380` joins sibling paths at run time. `ship_pr.py:97` runs `github/scripts/pr/new_pr.py`, and `ship_preflight.py:116` runs `review`'s `validate_review_marker.py`. So `ship`, `github`, and `review` must share a pack.
5. **`github` is the hub.** It is 107 files at `71ab5b15b3` (2026-11-25). Seven shipped skills run its scripts by path: `github-url-intercept`, `validate-pr-description`, `push-pr`, `pr-autofix`, `pr-review`, `pr-comment-responder`, `research`. Through the pilot, `ship` does too. `new_pr.py` loads modules inside the `github` skill, so `lib/github_core` cannot stand in for it today.
6. **The guard blocks `dangerous` packs.** Hermes' `plugin_guard` blocks a `dangerous` verdict even with `--force`. A `caution` verdict installs with `--force` after review.

## Jobs to be done

| # | Job | Skills | Pack |
|---|---|---|---|
| J1 | Plan, build, and test a change | `plan`, `execution-plans`, `build`, `test`, `analyze`, `validation-authority`, `doc-accuracy`, `code-qualities-assessment`, `taste-lints`, `golden-principles`, `style-enforcement`, `quality-grades`, `dx-review`, `orphan-ref-validator`, `agent-harness-reference`, `sync`, `steering-matcher` | delivery |
| J2 | Review a change and open the PR | `review`, `ship`, `pr-quality`, `security-scan`, `security-detection`, `codeql-scan`, `validate-pr-description`, `push-pr` (until retired) | delivery |
| J3 | See a PR through to merge, or decide its fate | `github`, `github-url-intercept`, `pr-review`, `pr-autofix`, `pr-babysit`, `pr-comment-responder`, `reviewer-findings`, `merge-resolver`, `maintainer-review`, `research`, `ai-agents-external-claims` | delivery |
| J4 | Adopt someone else's branch, or rewrite history | `takeover`, `modernize`, `git-advanced-workflows` | git |
| J5 | Run Azure DevOps and OneBranch pipeline work | `pipeline-validator`, `windows-image-updater` | azure-devops |
| J6 | Decide what to build | `spec`, `spec-generator`, `requirements-interview`, `adr-generator`, `decision-critic`, `decision-question`, `pre-mortem`, `cynefin-classifier`, `buy-vs-build-framework`, `chestertons-fence`, `programming-advisor`, `domain-design`, `business-strategy`, `negotiation`, `work-operating-model`, `world-model-diagnostic`, `panning-for-gold`, `software-engineering-library`, `avoiding-manufactured-work`, `autoplan`, `analysis-provenance`, `evidence-provenance` | knowledge |
| J7 | Remember and recall | `memory`, `memory-consolidate`, `memory-documentary`, `memory-enhancement`, `curating-memories`, `reflect`, `retrospective`, `checkpoint`, `context-gather`, `context-hub-setup`, `using-serena-symbols`, `codebase-documenter`, `stuck-detection` | knowledge |
| J8 | Harden a system | `threat-modeling`, `security-review`, `chaos-experiment`, `slo-designer`, `observability`, `metrics`, `destructive-change-safety` | quality |
| J9 | Get a second model's opinion | `llm-council`, `sol-loop`, `benchmark-models` | quality |
| J10 | Write skills, prompts, and docs | `skillforge`, `skillify`, `skillopt`, `skill-bootstrap`, `context-optimizer`, `prose-self-check`, `prompt-engineer`, `technical-writing`, `api-doc-authoring`, `fix-markdown-fences` | authoring |

J1, J2, and J3 share one pack. Constraints 4 and 5 force that. The seam between "decide" (J6) and "build" (J1) sits between `spec` and `plan`.

Two splits a user may not predict:

- Security work spans two packs. The pre-merge gates (`security-scan`, `security-detection`, `codeql-scan`) sit in delivery with `review`. Design-time work (`security-review`, `threat-modeling`) sits in quality. For both, install both.
- `research` sits in delivery because it files its follow-up issue through `github` scripts by path.

## Proposed packs

Counts use `find_references` and `skill_files` from `build/scripts/hermes_pack_checks.py`, at `71ab5b15b3` (2026-11-25). Each count includes the 58-file `lib/` and `plugin.json` overhead, and drops `excludedFiles`.

Projection assumptions:

- "Now" includes the pilot `ship` (8 files at `3a619dabd6`, 2026-11-25).
- "After P0" and "After P0+P1" add one file per script that `.project-toolkit/analysis/skill-gap-audit-2026-11-25.md` names for that priority. `push-pr` adds none, because it retires.
- No `lib/` growth, no P2 scripts (27 audit rows), and no new skills.
- Driver tests live under `tests/skills/` (the pilot's are in `tests/skills/ship/`), not inside the skill, so they add nothing. Seven `test_*.py` tooling scripts already ship inside skills (`71ab5b15b3`, 2026-11-25); the counts include them.
- "Free of 400" counts against the Hermes cap. The build budget `packMaxFiles` is 399 (`templates/platforms/hermes.yaml:21`), one less.

| Pack | Skills | Now | After P0 | After P0+P1 | Free of 400 | Guard verdict (staged) | Jobs |
|---|---|---|---|---|---|---|---|
| delivery | 36 | 351 | 357 | 372 | 28 | `caution` | J1, J2, J3 |
| git | 3 | 64 | 70 | 70 | 330 | `safe` | J4 |
| azure-devops | 2 | 62 | 68 | 68 | 332 | `safe` | J5 |
| knowledge | 35 | 265 | 265 | 268 | 132 | `safe` | J6, J7 |
| quality | 10 | 122 | 122 | 125 | 275 | `safe` | J8, J9 |
| authoring | 10 | 252 | 252 | 253 | 147 | `caution` | J10 |

All rows measured 2026-11-25 against `71ab5b15b3` and pilot `3a619dabd6`.

The largest staged pack is delivery at 4.52 MB, under the 10 MB cap (2026-11-25). Restaged with the three-skill `git` pack, delivery still has 15 hits (13 plus the 2 discounted) and `git` rates `safe`.

Guard verdicts come from the pinned guard (`tools/plugin_guard.py` at hermes-agent `63d0b94120`) run on staged copies. They hold for that commit only.

- Delivery has no `high` finding beyond the 13 it has on main. Ten of those 13 are in `FORCE_ALLOWED_FINDINGS`. Three are not: `code-qualities-assessment/references/calibration-examples.md:228,242,249` (`python_os_environ`).
- Authoring has no `high` finding beyond its 2 on main. `skill-bootstrap/scripts/adr_reason.py:184` (`inline_shell_exec`) is not in `FORCE_ALLOWED_FINDINGS`.
- Restored `review` and pilot `ship` rate `safe` alone.
- Knowledge stays `safe` because `plan` stays in delivery. `plan/SKILL.md` carries a reviewed `context_exfil` finding, which would make knowledge `caution`.
- The staging kept `test/references/rule-testing.md`, an `excludedFiles` entry, and its 2 hits are discounted above.

### Membership

- **delivery (36):** `agent-harness-reference`, `ai-agents-external-claims`, `analyze`, `build`, `code-qualities-assessment`, `codeql-scan`, `doc-accuracy`, `dx-review`, `execution-plans`, `github`, `github-url-intercept`, `golden-principles`, `maintainer-review`, `merge-resolver`, `orphan-ref-validator`, `plan`, `pr-autofix`, `pr-babysit`, `pr-comment-responder`, `pr-quality`, `pr-review`, `push-pr`, `quality-grades`, `research`, `review`, `reviewer-findings`, `security-detection`, `security-scan`, `ship`, `steering-matcher`, `style-enforcement`, `sync`, `taste-lints`, `test`, `validate-pr-description`, `validation-authority`.
- **git (3):** `git-advanced-workflows`, `modernize`, `takeover`.
- **azure-devops (2):** `pipeline-validator`, `windows-image-updater`.
- **knowledge (35):** today's 34, minus `prompt-engineer`, plus `spec-generator` and `stuck-detection`: `adr-generator`, `analysis-provenance`, `autoplan`, `avoiding-manufactured-work`, `business-strategy`, `buy-vs-build-framework`, `checkpoint`, `chestertons-fence`, `codebase-documenter`, `context-gather`, `context-hub-setup`, `curating-memories`, `cynefin-classifier`, `decision-critic`, `decision-question`, `domain-design`, `evidence-provenance`, `memory`, `memory-consolidate`, `memory-documentary`, `memory-enhancement`, `negotiation`, `panning-for-gold`, `pre-mortem`, `programming-advisor`, `reflect`, `requirements-interview`, `retrospective`, `software-engineering-library`, `spec`, `spec-generator`, `stuck-detection`, `using-serena-symbols`, `work-operating-model`, `world-model-diagnostic`.
- **quality (10):** `benchmark-models`, `chaos-experiment`, `destructive-change-safety`, `llm-council`, `metrics`, `observability`, `security-review`, `slo-designer`, `sol-loop`, `threat-modeling`.
- **authoring (10):** `api-doc-authoring`, `context-optimizer`, `fix-markdown-fences`, `prompt-engineer`, `prose-self-check`, `skill-bootstrap`, `skillforge`, `skillify`, `skillopt`, `technical-writing`.
- **Still excluded (8):** `skill-doctor` (1 MiB file), plus `adr-review`, `cva-analysis`, `memory-search`, `memory-maintenance`, and `planner` (each `dangerous`), plus `memory-gate` and `memory-reflexion` (they refer to `memory-search` or `memory-maintenance`).

The six packs hold 96 skills. With 8 excluded, that is all 104 under `src/claude/skills/` (2026-11-25).

### Moves from today's table

| Skill | From | To | Reason |
|---|---|---|---|
| `modernize`, `takeover`, `git-advanced-workflows` | delivery | git | J4. Each works on a branch someone else started or on history. |
| `pipeline-validator`, `windows-image-updater` | delivery | azure-devops | J5. Only Azure DevOps users need them. |
| `benchmark-models` | delivery | quality | J9: it compares models. |
| `codeql-scan` | quality | delivery | J2. `review`'s `codeql_scanner_guard.py:49` names its scripts path. |
| `golden-principles`, `style-enforcement` | quality | delivery | J1 and J2: both are code gates, and `review` runs `golden-principles` as an axis. |
| `technical-writing`, `fix-markdown-fences` | quality | authoring | J10: both edit prose. |
| `api-doc-authoring` | delivery | authoring | J10: it writes docs. |
| `prompt-engineer` | knowledge | authoring | J10: it writes prompts. |

That is 13 moves. Restored to Hermes:

- `ship`, `review`, `security-scan`, `pr-quality`, `security-detection` (delivery): the `security-scan` rewording clears their exclusion closure.
- `spec-generator` (knowledge): same closure. It joins `spec` and calls 9 shipped knowledge skills by name.
- `stuck-detection` (knowledge): the pinned guard rates it `safe`, so its recorded `dangerous` reason is stale.

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

Both flagged lines are documentation, not code that runs. The rewording keeps what each line teaches:

- `vulnerability-patterns.md:23`: the example input `../../../etc/passwd` becomes a placeholder for a parent-relative path to a system file. The placeholder must not spell `../../../`, which the guard also flags.
- `SKILL.md:180`: the reader list "a shell, `ssh`, `sudo`, `psql`" stops naming `sudo`. The tested wording was "a privilege wrapper". `scan_bash_heredoc.py:62-65` names the real rule: any command outside `_INERT_READERS`, such as `su`, `sudo -i`, `runuser`, `chroot`, `at`, `source`, or a shell. The final wording should point there. The source is `templates/skills/security-scan.SKILL.md.tmpl`.

The rewording changes text on every host. Line 23 sits in the CWE-22 section, which `security-scan` says it does not scan (`SKILL.md:24`, `:34`). Moving that section out does not help Hermes, because the line flags wherever it lands, and both candidate homes (`codeql-scan`, `security-review`) are packed.

With both lines reworded, the closure clears. After the #7586 `ship` wiring lands, the PR path on Hermes is the path on every host:

1. `/build`, then `/test`, then `/review` writes the SHA-bound marker.
2. `/ship` runs its pre-flight checks. It invokes `security-scan` by name and runs `review`'s marker validator in the same pack.
3. `ship_pr.py` creates the PR through `github`'s `new_pr.py` (GitHub) or its own Azure DevOps path.

Every step lives in delivery. A Hermes user opens a PR with one pack.

Restoring these skills adds scripts that Hermes runs, not just text. `push-pr` already opens PRs on Hermes, so the capability is not new in kind. The code paths are new, and the implementation pull request reviews them (below).

### The fate of `push-pr`

- `push-pr` stays in delivery on Hermes until the pilot `ship` ships there.
- #7587 retires `push-pr` on every host only after this layout's implementation pull request merges and proves the Hermes PR path (see Preconditions). It must not share that pull request.
- Retiring `push-pr` removes 2 files and 3 reviewed `high` findings from delivery (`push-pr/SKILL.md:33-35`, measured 2026-11-25).
- `takeover` names `push-pr` twice, and `autoplan`, `validate-pr-description`, and `agent-harness-reference` name it once each (2026-11-25). #7587 already owns those callers.

## Prerequisite edits

The implementation pull request makes these edits. Each one cuts a path that would cross packs, or clears a guard block. Edit the template where one renders the file.

| File | Line | Edit | Why |
|---|---|---|---|
| `src/claude/skills/security-scan/references/vulnerability-patterns.md` | 23 | Reword the example path | Clears the `critical` finding |
| `templates/skills/security-scan.SKILL.md.tmpl` | the source of rendered line 180 | Stop naming `sudo` | Clears the last `high` finding |
| `src/claude/skills/review/references/analyst.md` | 47 | Name `decision-critic` and its file, not a path | Cross-pack read to knowledge |
| `src/claude/skills/review/references/architect.md` | 51, 54 | Same, for `decision-critic` and `observability` | Cross-pack reads |
| `src/claude/skills/review/references/code-quality.md` | 52, 53 | Same, for `chestertons-fence` and `decision-critic` | Cross-pack reads |
| `src/claude/skills/review/references/decision-rigor.md` | 53-55 | Same, for `decision-critic` | Cross-pack reads |
| `src/claude/skills/review/references/observability.md` | 52-54 | Same, for `observability` | Cross-pack reads to quality |
| `src/claude/skills/review/references/reliability.md` | 54 | Same, for `observability` | Cross-pack read |
| `src/claude/skills/spec-generator/references/spec-prior-art-schema.md` | 3, 158, 275-280 | Name `analyze` and `review` files without a path | Edges to delivery |
| `templates/skills/api-doc-authoring.SKILL.md.tmpl` | 127 | Name `test`'s file without a path | Edge to delivery |
| `src/claude/skills/api-doc-authoring/references/example-verification.md` | 79 | Same | Edge to delivery |

The rewording pattern for a cross-pack read: "read `references/<file>.md` in the `<skill>` skill". On Hermes that is `skill_view("<skill>", "references/<file>.md")`.

No `review` axis loses content. Without `knowledge` and `quality` installed, `review` cannot open its `decision-critic`, `chestertons-fence`, and `observability` reading lists. It runs its axes without them.

## Cross-pack references and install sets

After the edits above, no path crosses a pack. These name-level calls cross packs and work when both packs are installed (measured 2026-11-25 by `Skill(skill=...)` lines):

- `build` (delivery) calls `pre-mortem` and `analysis-provenance` (knowledge).
- `spec-generator` (knowledge) calls `doc-accuracy` and `golden-principles` (delivery), and `slo-designer` and `threat-modeling` (quality).
- `adr-generator` (knowledge) calls `doc-accuracy` (delivery).
- `spec-generator` (knowledge) also calls `adr-review` and `cva-analysis`, which stay excluded. On Hermes those two steps have no skill, as today on every host without them.
- `takeover` and `modernize` (git) hand off to `github`, `pr-autofix`, `pr-comment-responder`, and `push-pr` (delivery) by name.
- `retrospective` (knowledge) runs `context-optimizer`'s `distill_artifact.py` (authoring), as today.

| Job | Install |
|---|---|
| J1, J2, J3 (build, review, ship, see a PR through) | delivery |
| J4 (adopt a branch, rewrite history) | delivery, git |
| J5 (Azure DevOps pipelines) | delivery, azure-devops |
| J6, J7 (decide, remember) | knowledge for basic work; see the spec tier limits below |
| J8, J9 (harden, second opinion) | quality |
| J10 (write skills and docs) | authoring |
| The full toolkit | all six |

Spec generation on Hermes has two limits. First, `spec-generator` calls excluded `cva-analysis` for every Tier 3 to 5 spec and for a Tier 1 or 2 spec with several use cases (`spec-prior-art-schema.md`, Step 5). No proposed pack ships it, so those specs cannot finish on Hermes. Second, Tier 4 and 5 also need blocking `adr-review`, which no proposed pack ships. A Tier 1 or 2 spec with one use case needs knowledge, plus delivery for validation. Finish the other specs on a host that ships `cva-analysis` and `adr-review`.

## Install order and reinstalls

One implementation pull request makes every move at once. Each existing Hermes user then reinstalls each pack they have one time.

1. Remove each pack you have with `hermes plugins remove project-toolkit-<name>`.
2. Install the packs you want without `--force`. Hermes then prints any finding for a `caution` pack (delivery, authoring).
3. Compare those findings with the reviewed list in the install guide before you pass `--force`.

Removing first avoids two problems. Hermes needs `--force` to replace an installed pack, even a `safe` one, and `--force` also accepts every new `caution` finding without a prompt. And on 2026-11-24, an old pack left installed beside a new one listed moved skills twice (`docs/training/install-on-every-host.md`).

Reinstall count: one per existing pack, in one release. The owner's earlier option C (2026-11-25) cost two reinstalls of delivery. Landing PR #7628 alone first, then this layout, would also cost two.

## Implementation pull request: acceptance criteria

The build check cannot see paths joined in code, and the smoke is the only runtime check. So the implementation pull request must show:

1. A `RUN_CLI_E2E=1` smoke run that installs all six packs at the pinned commit, with its output in the PR body. No workflow runs that smoke today.
2. Each `high` finding reviewed by hand, and `FORCE_ALLOWED_FINDINGS` updated for the six packs, including the 4 unreviewed findings above.
3. One live cross-pack `skill_view(skill, file)` call between two installed packs.
4. A negative-control test that `security-scan`'s detection results on its fixtures do not change after the rewording.
5. A list of each script restored to Hermes, with its subprocess, network, and credential use.
6. Updates to `docs/training/install-on-every-host.md` (pack table, skill count, remove-then-install steps) and `src/hermes/README.md`.
7. A build check for paths assembled in code. Allow same-pack targets. Reject targets in another pack or excluded from Hermes. Keep the existing exception: `skillforge/scripts/_packs.py` may look up a sibling pack and must report not evaluated when it is absent. Test same-pack, cross-pack, excluded, and `_packs.py` cases. The check proves only the path forms it parses. If it does not land, record that gap as an accepted risk in ADR-115.
8. A build check that requires `push-pr` or an independently wired `ship`. Exercise the installed `ship` publish handoff with a fake PR transport and no `push-pr`. A negative control must fail if `ship` delegates to the missing skill. Require that proof before #7587.
9. Commits that each pass the build check alone, in this order: (1) the name-only references and the `security-scan` rewording, which change no pack table; (2) restore the chain and move `codeql-scan` and `golden-principles` into delivery in one commit, because `review` names their paths; (3) the remaining pack moves. Run the smoke after step 2 and at the last commit.
10. A check that each line reworded to clear the guard is prose that does not run.

## Reversibility

- Before #7587, the previous four-pack table can still use `push-pr`. #7587 must not merge until one of two things is recorded. Either a four-pack rollback table that keeps the `ship` chain fits the cap and its smoke opens a PR without `push-pr`, or the owner accepts roll-forward-only recovery. Users reinstall the affected packs on any rollback.
- The prerequisite edits can stay after a revert. Name-only references work on every host, and the reworded `security-scan` lines keep their meaning.
- The claim that users predict packs by job is a hypothesis from this job table, not user data. After rollout, check install-guide questions and reports of missing skills per pack. The by-choice moves (`benchmark-models`, `prompt-engineer`, `technical-writing`, `fix-markdown-fences`, `api-doc-authoring`) are the cheapest to reverse.

## Growth policy

- Delivery keeps 28 files free after P0 and P1.
- Split again when delivery has fewer than 20 files free. The next seam is J1's gate skills. That needs the `review` axes to reach `code-qualities-assessment`, `doc-accuracy`, `golden-principles`, and `taste-lints` by name only.
- A shared `lib/` file adds one file to every pack. Against the cap, that is one file per pack.
- An ADR-127 driver in `git` or `azure-devops` calls `lib/github_core`, never `skills/github/scripts`. A path into `github` would fail the build there. If a driver needs a `lib/` module that does not exist yet, that module adds one file to each pack.
- The Semgrep `nosemgrep` comment on `lib/ptk_run.py` lives at the `src/claude/lib` source (owner ruling, 2026-11-25). Every pack copy, new packs included, inherits it.

## Rejected alternatives

1. **Fold `git` into delivery.** Delivery lands at 384 of 400 after P0 and P1, 16 free (2026-11-25). That is under the 20-free split trigger on day one. It saves one pack and one install. It is a real owner option (open question 1).
2. **Option C: an `azure-devops` pack plus a pack for five P0 skills.** The second pack cannot build. `pr-review` and `pr-autofix` run `github` scripts by path, so they cannot leave `github`'s pack.
3. **A build pack split from a review-and-ship pack.** Most jobs then need both packs, and `review` reaches its axes only when both are installed. It also leaves eight path edges to cut.
4. **A five-skill `git` pack.** The first draft put `merge-resolver` and `maintainer-review` in `git`. Both serve J3 (a PR's conflicts, a PR's fate), so a user looks for them beside `pr-review`. Keeping them in delivery costs 10 files of room.
5. **Today's table, plus `azure-devops`, plus the chain restored.** It also needs `codeql-scan` and `golden-principles` moved into delivery. Delivery lands at 390 of 400 after growth, 10 free (2026-11-25). It is the least-change fallback, priced in the open questions.
6. **Keep today's table and leave `ship` excluded.** Delivery has room (330 after growth), but Hermes keeps no PR path once #7587 retires `push-pr`.
7. **Drop `vulnerability-patterns.md` from the Hermes pack instead of rewording it.** `security-scan` stays `caution`, and Hermes users lose its remediation reference.
8. **Move the CWE-22 section out of `security-scan`.** The flagged line rates `dangerous` in any packed skill, so it needs rewording wherever it lands.
9. **Delete the CWE-22 section.** `security-scan` delegates CWE-22 detection to CodeQL (`SKILL.md:24`), but the section still guides remediation and false-positive triage on every host. Rewording one line keeps that guidance; deleting about 148 lines removes it everywhere to fix one Hermes verdict.

## Findings outside this task

Recorded for the owner. None is fixed here.

- **Guard drift.** At `71ab5b15b3` (2026-11-25), 4 `high` findings are missing from `FORCE_ALLOWED_FINDINGS`: 3 in delivery, 1 in authoring (listed above). The install guide says delivery has 10 and authoring 1. The smoke was NOT RUN, so whether it fails today is unknown.
- **Stale exclusion reason.** `stuck-detection` rates `safe` with the pinned guard, but its `excluded` reason says `dangerous`. ADR-115 already notes this.
- **Pilot description.** The pilot `ship` description still says "hand PR creation to push-pr" (`3a619dabd6`, 2026-11-25).
- **Excluded skills are close to restorable.** Each `dangerous` skill traces to 1 to 4 `critical` lines in reference prose: `adr-review/references/deletion-workflow.md:86`, `cva-analysis/references/SKILL_SPEC.md:110`, `memory-maintenance/references/benchmarking.md:352`, `memory-search/references/memory-router.md:293` and `skill-reference.md:209,276,292`, `planner/resources/plan-format.md:170`. Restoring them is out of scope.
- **doc-accuracy on the whole repo is slow.** `doc_accuracy.py --target . --phases 1,2,3` did not finish Phase 1 in 300 s. The diff-scoped run (`--diff-base origin/main`) passed with 0 findings.

## Open questions for the owner

1. Approve the six-pack layout. Or fold `git` into delivery (five packs, delivery at 384 of 400). Or take the least-change fallback (alternative 5: today's table plus `azure-devops`, delivery at 390 of 400).
2. Approve rewording two `security-scan` lines on every host, or keep `ship` off Hermes.
3. Lift the no-shipped-edit constraint for this change. You set it for D10 and D11, and ADR-115 says a later change may reword. This layout edits about a dozen shipped files (the prerequisite table). The same lift would allow rewording `skillforge`'s finding, which could rate authoring `safe`.
4. Close PR #7628 into the implementation pull request (one reinstall), or land it first (two).

## Method

- Pack counts: `skill_files` and `excludedFiles` from `build/scripts/hermes_pack_checks.py`, run over `src/claude/skills/` at `71ab5b15b3`. The method reproduces main's four committed pack counts exactly.
- Path edges: `find_references` from the same module, then every hit per edge read by hand. `find_references` keeps the first hit per skill pair only.
- Name edges: every `Skill(skill="...")` line in shipped `SKILL.md` and reference files.
- Guard: `tools/plugin_guard.py`, `plugin_guard_context.py`, and `skills_guard.py` read from hermes-agent `63d0b94120`, run on staged pack copies with `scan_plugin(..., source="local")`.
