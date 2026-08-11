# Aspire Skill Review CVA

## Use cases

- Aspire `issue-investigation`
- Aspire `pr-testing`
- Aspire `cli-e2e-testing`
- Aspire `ci-test-failures`
- Aspire `test-management`

## Matrix

| Commonality | issue-investigation | pr-testing | cli-e2e-testing | ci-test-failures | test-management |
|---|---|---|---|---|---|
| Local ownership check | `github`, `analyze`, debugging agent | QA agent, PR test analyzer, `github` | `ai-agents-validation-and-qa` | `github`, `ai-agents-debugging-playbook` | No current quarantine owner |
| Reusable policy | Build context before reproducing | Verify PR artifact provenance before testing | Capture deterministic terminal and workspace evidence | Check main, then inspect exact logs | Distinguish flaky quarantine from deterministic disable |
| Likely change type | Compose or augment | Augment, or one new skill if no owner remains | Augment QA reference | Augment debugging playbook | Reject until local mechanism exists |
| Evidence type | Reproduction dossier and cited issue context | Scenario results and artifact identity | Terminal recording, prompt sequence, workspace capture | Failed tests, logs, artifacts, linked issue | Test attribute, issue link, separate scheduled run |
| Product coupling removed | Aspire CLI commands | Dogfood installer and Aspire packages | Hex1b and Aspire helper classes | Aspire workflow names | QuarantineTools and Aspire attributes |

## Commonalities

1. Every retained idea needs commit-pinned source evidence.
2. Every candidate needs a local ownership and overlap check.
3. Product commands and repository policy do not transfer.
4. Evidence must match the behavior under review.
5. Existing skills receive the change before a new skill is considered.

## Variabilities

1. Local owner differs by source workflow.
2. Evidence shape differs by workflow.
3. The correct decision varies across compose, augment, create, and reject.
4. Some source skills contain reusable policy, while others depend on missing
   local infrastructure.

## Pattern recommendation

Do not build a generic external-skill review framework. The matrix shows one
review procedure with source-specific judgment, not a stable product family or
runtime strategy hierarchy. Use SkillForge and a decision matrix directly.

## Reassessment triggers

- A second independent external skill repository needs the same review.
- Two reviews repeat the same source normalization and overlap steps.
- Review work requires a deterministic script rather than human judgment.
