# Archived Planning Artifacts

110 files moved here from `.agents/planning/` on 2026-07-27 under issue #3431.
77 markdown documents and 33 JSON eval outputs. The superseded index came with
them as `INDEX-2026-01-23.md`, so the state it claimed is still readable.

Nothing was deleted. Every file kept its name and its position inside the
original subdirectory tree, so `git log --follow` still reaches the full history.

`.agents/planning/` itself stays live. `.github/PULL_REQUEST_TEMPLATE.md` tells
feature authors to create a spec there, and `ai-spec-validation.yml` accepts that
path. This pass retired the contents, not the directory.

## Why these moved

`.agents/planning/INDEX.md` was dated 2026-01-23 and declared
`**Current Milestone**: v0.3.0`. That milestone closed with 139 issues completed.
An agent reading the index was told that finished work was in flight.

## How each document was verified

A closed tracking issue on its own is not proof that a plan finished. The bar was
two independent signals: the referenced work is closed, and the deliverable the
document names is present on disk.

**Signal one, applied mechanically to all 78 markdown files.** Every issue and PR
reference was extracted, producing 235 distinct numbers, and each was queried
through the GitHub GraphQL API:

```text
resolved: 235 of 235
OPEN items: 0
```

Not one referenced issue or PR is open. Milestone state agrees independently:

| Milestone | Open | Closed | State |
|-----------|------|--------|-------|
| 0.2.0 | 0 | 344 | closed |
| 0.3.0 | 0 | 139 | closed |
| v0.3.1 | 0 | 54 | open |
| v0.4.0 | 0 | 14 | open |
| v0.5.0 | 0 | 16 | open |
| Future | 0 | 71 | open |

**Signal two, applied to the claims that would be most expensive to get wrong.**

| Claim under test | Check | Result |
|------------------|-------|--------|
| v0.3.1 retired PowerShell | `find` for `*.ps1`, `*.psm1`, `*.psd1` in repo code | Zero. The only hit is `.venv/bin/activate.ps1`, a vendored virtualenv script |
| Knowledge integration shipped `references/` | Count `references/` directories under `.claude/skills/` | 54 present |
| PR remediation plans landed | Query PR state for 60, 147, 43, 830, 760, 365 | All six merged |

## Inventory by cluster

| Cluster | Files | Verdict | Evidence |
|---------|-------|---------|----------|
| `v0.2.0/`, `v0.3.0/`, `v0.3.1/` | 5 | Complete | Milestones closed with 344, 139, and 54 issues. Zero PowerShell files remain, which was the v0.3.1 target |
| `PR-60/` | 8 | Complete | PR #60 merged. Distinct from the six `pr-60-*` documents already in `.agents/archive/`, so both sets are kept |
| `PR-147/` | 1 | Complete | PR #147 merged |
| `ADR-042-IMPLEMENTATION/` | 1 | Complete | Python-first migration landed. Zero PowerShell files remain |
| `CodeQL/` | 1 | Complete | Referenced issues closed |
| `claude-compat/` | 1 | Complete | Referenced issues closed. `DESIGN-REVIEW-vscode-copilot-parity-plan.md` in `.agents/architecture/` keeps the review record |
| `codex-context-optimization/` | 2 | Complete | Referenced issues closed |
| `session-evidence-verification/` | 2 | Complete | Referenced issues closed |
| Agent consolidation set | 5 | Complete | Epic #907 and #972 closed. 32 agents on disk |
| Knowledge integration set | 5 | Superseded, residual tracked | See the note below |
| Three-MCP set | 3 | Superseded, not shipped as specified | Tracking issues closed, but `packages/` holds only `ai-agents-cli` and `semantic-hooks`. None of the three named MCP packages exist. The repository took a different approach |
| Remaining root PRDs, plans, and task lists | 43 | Retired | Every referenced issue closed. See the verification limits note below before treating any single document here as shipped-as-written |
| Eval JSON output | 33 | Misfiled, not planning documents | See the note below |

## What this verification does not prove

A closed tracking issue proves the issue was closed. It does not prove the
document's design shipped as written. GitHub reports #51 and #739 as closed and
completed, yet the user-level Visual Studio install path in
`prd-visual-studio-install-support.md` is still marked BLOCKED in the document
itself, and the numbered command scheme in
`prd-workflow-orchestration-enhancement.md` (`/0-init`, `/1-plan`, `/2-impl`)
never appeared. The repository ships `/spec`, `/plan`, `/build`, `/test`,
`/review`, and `/ship` instead.

The second signal, a named deliverable present on disk, was applied to the
clusters where a deliverable was named: PowerShell removal, `references/`
directories, specific merged PRs, agent counts, and the MCP packages. It was not
applied document by document to the 41 root PRDs and task lists, because most of
them name no single checkable artifact.

So read the verdicts in that table as retired, not as delivered. Every document
here describes work nobody is tracking any longer. Some of it shipped as
designed, some shipped differently, and some was dropped. If you need to know
which happened for one specific document, read the document and check its
tracking issue. That distinction does not change where the file belongs, and it
is the reason nothing here was deleted.

## Two clusters that need a word

**Knowledge integration.** Five documents cover this: `004-knowledge-integration-plan.md`,
`SPEC-knowledge-integration.md`, `TASKS-004-knowledge-integration.md`,
`2026-04-11-wiki-knowledge-integration-plan.md`, and `TASKS-wiki-knowledge-integration.md`.
The work shipped, and 54 skills now carry a `references/` directory. Residual work
is already tracked under #3421.

These documents disagree with each other, which is the concrete reason they should
not stay in a live directory. `SPEC-knowledge-integration.md` mandates a per-skill
`resources/` directory. The later `004-knowledge-integration-plan.md` overrides it
and calls `resources/` a planner-only anomaly. On disk `references/` won 54 to 2.
The two survivors are exactly what the newer plan predicted: `planner/resources/`
is the named anomaly, and `memory/resources/schemas` holds JSON schemas rather
than reference documents. An agent following the older spec would adopt a
convention the repository abandoned. No open defect, so no issue was filed.

**Eval JSON output.** The 33 JSON files are agent-slimming experiment results, not
planning artifacts. Names follow `*-slim-results.json`, `spot-check-*.json`,
`agent-baseline-*.json`, `*-verify.json`, and `quality-results-*.json`. All date to
2026-04-11 and 2026-04-12. `build/scripts/validate_planning_artifacts.py` never
scanned them; it counts 57 documents and ignores JSON. Nothing outside
`.agents/planning/` referenced any of them. Two are cited by
`quality-results.md`, which moved here with them, so that link still resolves.

They moved here with the rest of the directory because the standing rule for this
pass was that retired material goes to the archive. That preserves them but does
not fix the filing: the repository's eval directory is the documented system of
record for this class of artifact. Re-homing is a separate decision with a
different destination, so it is tracked under #3435 rather than assumed here.

The repository has a top-level `evals/` directory that is the natural subject-matter
home for this output. They were sent here instead because the standing instruction
for this cleanup is that retired material goes to `.agents/archive/`. Relocating
them to `evals/` is a follow-up decision, not a correctness problem.

## What did not move

Dated records that describe a moment in time keep their original paths. Rewriting
a session log, a handoff, or an audit to match a later file move would falsify the
record. That covers `.agents/sessions/`, `.agents/archive/` entries that predate
this pass, `.claude-mem/`, and `.forgetful/`.

## Gate behavior after the move

Both consumers of `.agents/planning/` tolerate an empty directory, which was
checked before anything moved. Note that the empty case is the fallback, not the
state this change produced: `INDEX.md` stays behind, so the validator parses one
document and passes on content rather than short-circuiting on an empty set.

- `build/scripts/validate_planning_artifacts.py` line 383 returns 0 when it finds
  no documents. Post-move it finds `INDEX.md` instead, parses it, and still
  exits 0.
- `.github/workflows/artifact-insight-scanner.yml` line 77 guards its `find` with
  `2>/dev/null || true` and handles a zero artifact count with a notice.

One side effect is worth naming. The insight scanner selects files by `mtime`, so
this move resets the modification time on all 110 files and they will look new to
the next weekly scan. The scan is advisory and produces a report, so the cost is
one noisy run.

## Follow-ups

| Issue | Subject |
|-------|---------|
| #3421 | 15 skills over 12KB have no `references/` to defer content into |
| #3426 | Nothing invokes the plan closeout triggers, which is why the sibling `.agents/plans/active/` filled up. That issue is written against `.agents/plans/`, so a scope note was added asking whether the fix covers this directory too |
| #3431 | This cleanup |
| #3435 | The 33 eval JSONs belong in the eval system of record, not in a planning archive |
