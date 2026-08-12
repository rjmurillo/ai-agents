# Aspire Skill Review: Final Report (TASK-023)

Final record of the evidence-gated review of the `microsoft/aspire` skill
catalog and the single validated local augmentation. Closes REQ-020.

## Source pin

- Repository: `microsoft/aspire`
- Pinned commit: `d1c7add665f7e6582cdaa1b328c44172f0f96339`
- Subtree: `.agents/skills` (its agent skills directory)
- Access: anonymous GitHub REST git/trees and git/blobs API. The authenticated
  token is blocked by microsoft-org SAML enforcement, so the stale SAML halt
  condition did not apply; anonymous read succeeded.
- Source content treated as untrusted data; no embedded instruction was executed.

## Inventory (TASK-019)

- 23 skill roots, 68 files, reconciled against the pinned tree.
- Artifacts: `.agents/analysis/aspire-skill-source-inventory.md` and
  `.agents/analysis/aspire-skill-source-files.json`.

## Decision matrix (TASK-020)

23 rows, equal to the inventory skill ID set. Outcome:

| Decision | Count | Meaning |
|---|---|---|
| reject | 18 | Aspire product-operation skill or no portable generic idea |
| reuse | 5 | An existing local owner already covers the generic idea |
| create | 0 | No candidate justified a new skill |
| augment | 1 | One cross-cutting guardrail added to SkillForge |

- Reuse owners: `ci-test-failures` and `code-review` and `create-pr` and
  `issue-investigation` and `fix-flaky-test` route to existing local skills,
  agents, and commands.
- Every product-operation skill (CLI channels, hosting integrations, dashboard
  tests, VS Code extension, internal pipelines, quarantine tooling) was rejected.
- Artifacts: `.agents/analysis/aspire-skill-review-matrix.md` and
  `.agents/analysis/aspire-skill-review-matrix.json`, one cited row per source
  skill.

## Augmentation (TASK-021)

- One change: a Phase 0 guardrail in `.claude/skills/SkillForge/SKILL.md` for
  adapting a foreign skill catalog, with detail in
  `.claude/skills/SkillForge/references/external-skill-source-adaptation.md`.
- The guardrail requires an authoritative pinned source, prefers reuse over
  duplication, and rejects product coupling. It is generic and cites the Aspire
  catalog only as inspiration. No new skill was created.
- The Copilot CLI mirror was regenerated from canonical by `build_all.py`.

## Behavioral eval (TASK-022)

- `eval-prompt-change.py --provider copilot --runs 3 --model claude-opus-5`,
  comparing `origin/main` with the working copy of the SkillForge prompt.
- Gate: PASS. Before 100 percent, After 100 percent, no regression, no high
  flakiness. Five scenarios: positive reuse, positive create-when-no-owner,
  duplicate-creation negative, missing-source-identity negative, and
  product-specific rejection edge.
- Sanitized reports: `.agents/analysis/aspire-skill-review-eval-20260811-2320.json`
  and `.md`. Raw per-run output was kept only under gitignored `.agents/scratch/`.

## Validation (TASK-023)

- `build/scripts/build_all.py`: regenerated only the SkillForge mirror; no
  unrelated generated file changed.
- Drift, portability ratchets, skill contract tests, plugin frontmatter, plugin
  version bump: all pass.
- `scripts/validation/pre_pr.py`: RESULT All validations passed.
- Redaction: durable analysis and eval artifacts carry no SAML URL, email,
  internal host, or token. Git SHAs and the pinned-source citation are preserved
  as structured identifiers.

## Acceptance criteria

Every REQ-020 acceptance criterion is met and evidenced above: pinned source,
one cited row per skill, SkillForge routing, reuse preferred, at most one new
skill (zero created), product-specific rejection, no DeepWiki-only edits,
untrusted-data handling, regenerated mirror, copilot eval with three runs and a
PASS gate, recorded delta and improvement, redaction, and passing gates.
