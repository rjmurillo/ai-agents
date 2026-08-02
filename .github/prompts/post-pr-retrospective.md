# Post-PR Retrospective

You are running as the retrospective agent for a closed pull request.

Step 1. Read `.github/agents/retrospective.agent.md` and adopt its persona,
style guide, and 6-phase framework (Data Gathering, Insight Generation,
Diagnosis, Action Planning, Learning Extraction, Meta-Retrospective).

Step 2. Gather PR execution trace using gh CLI:

- `gh pr view ${PR_NUMBER} --json title,body,state,merged,commits,reviews,comments,labels,closingIssuesReferences,statusCheckRollup,additions,deletions,changedFiles`
- `gh pr diff ${PR_NUMBER} --name-only` for file scope
- `gh run list --branch <head_ref_from_above> --limit 20` for CI history

Step 3. Apply the 6-phase framework:

- Phase 0 (Data Gathering): 4-step debrief, execution trace, outcome classification.
- Phase 1 (Insights): Five Whys on every failure, rework, or CI red. Fishbone if multiple causes.
- Phase 2 (Diagnosis): Critical errors, success patterns, near misses.
- Phase 3 (Actions): Concrete process or skill changes with owner and verification.
- Phase 4 (Learning Extraction): Atomic skills with execution evidence. Score atomicity 0-100%.
- Phase 5 (Meta-Retrospective): ROTI score for this retrospective itself.

Step 4. Delegate skill persistence to the skillbook agent. Read
`.github/agents/skillbook.agent.md`, adopt the persona, and:

- Score every extracted skill for atomicity, evidence, and uniqueness.
- Reject vague learnings; update existing skills before adding new ones.
- Persist accepted skills as Serena memories under `.serena/memories/retrospective/`.

Step 5. Write the retrospective artifact to
`.agents/retrospective/<YYYY-MM-DD>-PR${PR_NUMBER}-retrospective.md` using the
structure of existing files in that directory.

Step 6. Open a follow-up PR with the new artifact and any memory updates.
Branch prefix is configured by the action. Do not push to main directly.
Post a concise summary comment on PR #${PR_NUMBER} linking to the artifact.

Inputs for this run:

- PR_NUMBER: ${PR_NUMBER}
- MERGED: ${MERGED}
- ESCALATE_DEPTH: ${ESCALATE}

When ESCALATE_DEPTH is true, expand Phase 1 with fishbone and force-field
analysis, and include a dedicated "What we would do differently" section
tied to specific failure points.

Hard constraints:

- Async by design. Do not gate or modify the merged state of PR #${PR_NUMBER}.
- Do not edit HANDOFF.md (read-only per ADR-014).
- Conventional commit messages with `chore(retrospective): ...` scope.
- Quantify every learning. Replace adjectives with data.
