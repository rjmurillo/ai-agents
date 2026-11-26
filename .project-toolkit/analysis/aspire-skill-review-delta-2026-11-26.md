# Aspire Skill Review: Delta At 91f866a

This record updates `aspire-skill-review-matrix.md` for a newer source pin. It
follows the three gates in the `skillforge` skill's
`references/external-skill-source-adaptation.md`.

## Source pin

- Repository: `microsoft/aspire`, subtree `.agents/skills`.
- Prior pin: `d1c7add665f7e6582cdaa1b328c44172f0f96339` (2026-08-12), 23 skills.
- This pin: `91f866a32580ad77b7b467581a5c2b561c402ebc` (2026-11-26), 26 skills.
- License: MIT, copyright .NET Foundation and Contributors.
- Access: anonymous shallow sparse clone. Source text was read as untrusted data.
  Nothing from the clone was run or built.
- File list: `aspire-skill-source-files-91f866a.md` holds 98 files across 26
  skills at `91f866a` (2026-11-26), each with its git blob hash.

## What changed in the question

The August review asked one question per source skill: does this deserve a new
local skill? It answered no 23 times. This pass kept that answer and asked a
second question for every skill with a local owner: does the source carry a
technique that owner lacks? A technique passed only with all three of these:

1. a named local owner file;
2. a search of that owner showing the technique is absent;
3. a present consumer in this repository.

## Outcome

| Decision | Count at 91f866a (2026-11-26) | Meaning |
|---|---|---|
| reject | 20 | Product operation, or no portable idea |
| reuse | 5 | A local owner already covers the generic idea |
| augment | 1 | One technique added to an existing owner |
| create | 0 | No new skill |

## The one augmentation

- Source: `pr-testing/ci-infra-testing.md`, a playbook for testing a pull
  request that changes CI itself.
- Local owner: the `review` skill's devops axis, `references/devops.md`.
- Gap evidence, searched 2026-11-26 at `1be533c49`: the axis asked whether a
  workflow change alters "job dependencies, ordering, or triggers" and gave no
  method. A search of `references/devops.md` and the repo-local
  `rule-ci-scripts.md` found zero matches for `continue-on-error`,
  `workflow_run`, `workflow_call`, `default branch`, `dry run`, and a base-run
  job list comparison.
- Consumer: `.github/workflows/` holds 66 workflow files at `1be533c49` (2026-11-26).
- Change: new `review/resources/ci-change-validation.md`, a short section in
  `references/devops.md`, and two WARN conditions.
- Verification: ten platform facts were checked against the GitHub Actions
  documentation on 2026-11-26. Three claims the documentation did not confirm
  were left out. The resource names each one.
- Wording: the seven questions follow the source's question list, in its order,
  restated in new words. The tables, the run list, and the reviewer scope are
  new. No product command was carried over.
- Effect check, run 2026-11-26. Fresh reviewers got the axis prompt as text and
  one real diff from this repository. Each prompt ran once per case, on one
  model. One run per case shows a difference, not a rate. The check ran on the
  first draft of the axis text. Later wording edits were not re-run.
  - Commit `af9a4d392` (2026-11-03) edits a workflow that only `schedule` and
    `workflow_dispatch` start. The old prompt returned PASS with no findings.
    The new prompt returned WARN and named the path the pull request never ran.
  - The reverse of commit `11cc3294e` (2026-09-29) adds `continue-on-error` and
    narrows a path filter. Both prompts returned WARN. The new prompt showed no added signal on this case.
  - Commit `740c858f6` (2026-11-25) bumps a pinned action in a `workflow_run`
    workflow. The new prompt returned PASS with a note. The old prompt was not
    run on this commit.
  - The first draft linked the resource by relative path only. No reviewer
    opened it. The axis now names two paths to try, and all three later
    reviewers opened it. That was tested in this checkout only. An install
    where neither path opens gets the four inline checks alone.
- Routing is unchanged. By path, `select_axes.py` picks the devops axis for
  CI and deploy files, such as workflow and action files. A script-only CI change reaches it through a diff
  effect, a pin, or a deep review.

The same pass added one bullet to Gate 2 of the skillforge guide: compare
techniques, not skill names.

## Rows

One row per source skill at `91f866a` (2026-11-26). "Carried" means the August
row stands and the source file did not change in a way that affects it.

| Source skill | Decision | Local owner | Note |
|---|---|---|---|
| api-review | reject | review, reviewer-findings | Carried. Comment dedupe lives in the `github` skill scripts. Those scripts hold no blame attribution (searched 2026-11-26). The source's blame step serves its own API review flow. |
| azdo-internal | reject | pipeline-validator | Rewritten upstream. Its reconcile-before-queue step is already in `pipeline-validator`. |
| backport-pr | reject | github | Carried. This repository has no release branches (checked 2026-11-26), so no consumer. |
| bump-aspire-version | reject | none | New upstream. Edits one product's version file. |
| ci-test-failures | reuse | github `fix-ci.md`, ai-agents-debugging-playbook | Carried. The rest parses one test-result format. |
| cli-channel-debugging | reject | ai-agents-debugging-playbook | Carried. |
| cli-e2e-testing | reject | ai-agents-validation-and-qa | Carried. |
| code-review | reuse | review, code-reviewer agent | Rewritten upstream. Checked its test-sufficiency and auto-merge rules: owned by the qa axis, `rule-testing.md`, and `auto_merge_guard.py`. |
| connection-properties | reject | none | Carried. |
| create-pr | reuse | push-pr, github | Changed upstream. Body rules are owned by `push-pr` and `validate-pr-description`. |
| create-video | reject | none | New upstream. Product branding and a recording toolchain. |
| dashboard-testing | reject | ai-agents-validation-and-qa | Carried. |
| dependency-update | reject | dependency-auditor agent | Carried. |
| deployment-e2e-testing | reject | ai-agents-validation-and-qa | Carried. |
| deprecate-integration | reject | none | Carried. |
| fix-flaky-test | reuse | test `rule-testing.md` MUST 12 and 13 | Carried. The run-count formula is the one MUST 12 already states. |
| hex1b | reject | ai-agents-validation-and-qa | Carried. |
| hosting-integration-authoring | reject | none | Carried. |
| issue-investigation | reuse | analyze, context-gather, maintainer-review | Carried. |
| pr-testing | augment | review devops axis | Was reject. `ci-infra-testing.md` supplied the CI change method above. `SKILL.md` stays product-coupled. |
| reviewing-aspire-architecture | reject | architect agent, review | Changed upstream. Its escalation limit duplicates the `review` round rules. |
| run-playground-apphosts | reject | none | New upstream. Runs one product's sample hosts. |
| startup-perf | reject | observability | Carried. |
| test-management | reject | none | Carried. No local quarantine tooling. |
| update-container-images | reject | windows-image-updater | Carried. |
| vscode-extension | reject | none | Carried. |

## Not done

The `devops` agent template was not changed. It authors workflows, and the new
resource would help it. That edit renders into every agent tree and needs its
own review.
