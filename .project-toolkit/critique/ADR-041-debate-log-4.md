# ADR-041 Debate Log 4: widen the /review scanner-input guard

**ADR**: `.project-toolkit/architecture/ADR-041-codeql-integration.md`
**Amendment**: "Amendment 2026-11-09: Let /review read CodeQL results as an explicit caller"
**Rules file**: `.project-toolkit/analysis/adr-041-review-caller-rules.md`
**Prior debate log**: `.project-toolkit/critique/ADR-041-debate-log-3.md` (closed by consensus in round 1)
**Review date**: 2026-11-10
**Protocol**: adr-review, reduced panel plus security. The change edits a
security rule in the amendment, so security joined architect and critic.
**Participants**: architect, critic, security

## Summary

An automated security review of the wiring branch flagged the scanner-input
guard. It covered only `.github/workflows/codeql-analysis.yml` among workflows.
A same-repo branch could add or edit another workflow that uploads SARIF and
plant or shadow Tier 1 alerts. The `.yaml` spelling was also uncovered.

## Round 1 Summary

### Positions

- **architect (Accept):** guard all of `.github/workflows/`. Do not filter by
  tool name, since SARIF content sets it. ADR summary item 1 and the rules file
  must change in one commit. 67 of the last 200 commits on `origin/main` touch
  `.github/workflows/` (2438d8def, 2026-11-09), so about a third of reviews will
  report `SKIPPED`. The skip is loud and Tier 1 still blocks.
- **critic (Disagree-and-Commit):** widening is testable. A text match on
  `upload-sarif` misses reusable workflows, local actions, and direct API calls.
  Raised two gaps: `.github/actions/**`, and the `pytest.yml` SARIF upload.
- **security (Disagree-and-Commit):** widen, do not narrow. P1: the `pytest.yml`
  job `security` holds `security-events: write` (line 1108), runs branch
  controlled code through `uv run --frozen`, and uploads at line 1171. No
  workflow file change is needed to plant results.

### Key Issues Addressed

- **P1 (widen guard):** resolved. The guard covers any file under
  `.github/workflows/`. A changed directory entry or symlink under a guarded
  path counts as touching it.
- **P1 (`pytest.yml` upload):** resolved by an origin filter. Only alerts whose
  analysis `analysis_key` names `codeql-analysis.yml`, under a `/language:`
  category, count. `codeql-analysis.yml:169` sets that category;
  `pytest.yml:1174` uploads under `ruff-security`.
- **Critic gap `.github/actions/**`:** withdrawn. That path was already guarded.

## Round 2 Summary

### Positions

- **architect (Accept):** checked the claims against the workflow files. Only
  `codeql-analysis.yml` and `pytest.yml` upload SARIF or grant
  `security-events: write` today.
- **critic (Accept):** the forged-SARIF case is marked unverified, and its harm
  is bounded because results stay input only.
- **security (Disagree-and-Commit):** the filter fixes the `ruff-security` path.
  Condition: record the residual risk in the rules file before merge. Applied.

### Dissent (security)

Branch code in the `pytest.yml` job could read the token that
`actions/checkout` persists in `.git/config` and post SARIF with a forged
`analysis_key`. Whether GitHub validates that field is INFERRED, not verified.
The rules file now records this. Setting `persist-credentials: false` on that
job's checkout would narrow the path. That workflow change is outside this
decision and is flagged for the owner.

## Outcome

Consensus: 2 Accept, 1 Disagree-and-Commit. ADR summary items 1 and 2 and the
rules file change together in one commit. The ADR is 481 lines, under the
500-line cap.

## Post-consensus correction

PR #7196 thread `PRRT_kwDOQoWRls61kD6I` (Cursor Bugbot, low) found that the
ADR frontmatter `date` stayed `2026-11-09`. ADR-073 treats `date` as last
updated. The date and the architecture index row now read `2026-11-10`. No
rule text changed, so no new vote was taken.
