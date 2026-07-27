# Debate Log: Planning Archive Path Repoints (Issue #3431)

**Date**: 2026-07-27
**Trigger**: `adr-review-policy` pre-commit gate. The change edits eight files under
`.agents/architecture/` plus `.agents/SESSION-PROTOCOL.md`, both of which fire the
mandatory adr-review protocol.
**Skill**: `adr-review`
**Rounds**: 1
**Outcome**: Consensus reached. Four ACCEPT, two DISAGREE-AND-COMMIT.

## What was under review

110 stale planning artifacts moved from `.agents/planning/` to
`.agents/archive/planning/` by `git mv`. Nothing deleted. The change also rewrites
`.agents/planning/INDEX.md`, adds an archive index, and repoints inbound links.

The reviewed surface was not the archive decision alone. It was whether the link
repoints into ADR files and the session protocol were correct, complete, and
consistent with this repository's own governance on historical records.

## Agents and verdicts

| Agent | Role | Vote |
|-------|------|------|
| architect | Structure, governance, coherence | ACCEPT |
| security | Threat model, evidence integrity | ACCEPT |
| high-level-advisor | Priority, tie-breaking | ACCEPT with required amendment |
| analyst | Evidence quality, feasibility | ACCEPT with advisory notes |
| critic | Gaps, risks, completeness | DISAGREE-AND-COMMIT |
| independent-thinker | Challenge assumptions | DISAGREE-AND-COMMIT |

## Findings and disposition

| ID | Severity | Agent | Finding | Disposition |
|----|----------|-------|---------|-------------|
| F1 | P0 | critic | ADR-026 line 314: display text repointed to the archive, markdown link target left at `../planning/`. A broken link inside a file the change claimed to fix | Fixed. Target now `../archive/planning/` |
| F2 | P0 | advisor | `.agents/SESSION-PROTOCOL.md` carried a SHOULD-read of a finished project plan inside a BLOCKING phase. Repointing keeps a dead instruction alive and costs context every session | Fixed. Line deleted, list renumbered |
| F3 | P1 | critic | ADR-006 line 7 and ADR-017 line 367 had identical breakage and were never touched | Fixed. Both repointed |
| F4 | P1 | critic | 15 Serena memory files carried 21 references to moved paths. Memories are loaded as live guidance under session protocol Phase 2, unlike the dated records under `analysis/` and `critique/` | Fixed. Repointed |
| F5 | P1 | independent-thinker | 30 references between archived documents still pointed at pre-move sibling paths, so the archive was not internally navigable | Fixed. Repointed, verified zero remaining |
| F6 | P1 | independent-thinker | The archive index labeled clusters Complete on closed-issue evidence alone. The three named MCP packages do not exist and the numbered command scheme never shipped | Fixed. Three-MCP relabeled Superseded, root documents relabeled Retired, and a section added stating what a closed issue does and does not prove |
| F7 | P1 | independent-thinker | The 33 eval JSONs were misfiled from the start, so they cannot be retired, only re-homed. The eval directory is their documented system of record | Deferred to #3435. Re-homing sends them to a destination other than the one specified for this pass, so it is a separate decision |
| F8 | P1 | analyst | Cluster table: `session-evidence-verification/` claimed 4 files, the directory holds 2 | Fixed. Corrected to 2, and the root document count corrected from 41 to 43. Table still sums to 110 |
| F9 | P1 | advisor | `.agents/SESSION-PROTOCOL.md` gets no non-semantic carve-out, unlike ADR files under `_is_frontmatter_only_metadata_change`, so any byte change forces a full six-agent debate | Open. Recorded as a candidate follow-up, not filed |
| F10 | P2 | advisor | Issue #3426 is scoped to `.agents/plans/`, so citing it as tracking this directory overclaims | Fixed. Scope note added to #3426, claims softened in both indexes |
| F11 | P2 | analyst | The gate note said the validator returns 0 because it finds no documents. Post-move the directory still holds `INDEX.md`, so that branch never fires. Conclusion correct, stated mechanism wrong | Fixed in both indexes |
| F12 | P2 | critic | `.agents/README.md` bootstrap recipe copied the archived enhancement plan into new repositories | Fixed. Line deleted |
| F13 | P2 | architect | ADR-037 paths appear as inline code rather than links, against the documentation link requirements | Not fixed. Pre-existing, outside this change |

## Contested points and how they resolved

**Delete or repoint the session protocol line.** The architect argued for
repointing now and tracking a follow-up, on the grounds that changing protocol
semantics deserves its own review cycle. The advisor and the critic argued for
deleting it now: the enhancement project is finished, so the instruction is dead
weight that every session pays for, and it contradicts the retrieval-led reasoning
principle stated four lines below it. Deleted. Two reviewers to one, and the
deletion is three lines against an issue plus a future pull request.

**Whether closed issues prove completion.** The independent-thinker produced three
counterexamples and was correct on the evidence. Issues #51 and #739 are closed as
completed, yet the user-level Visual Studio install path is still marked BLOCKED in
its own document, the numbered command scheme in the workflow orchestration PRD
never appeared, and `packages/` holds none of the three MCP packages the plan
specified. This does not change where the files belong. It changes what the index
is allowed to claim about them, which is why the labels moved from Complete to
Retired and Superseded.

**Whether Serena memories are records or guidance.** The stated policy left dated
point-in-time records under `analysis/`, `critique/`, `qa/`, `retrospective/`,
`security/`, and `roadmap/` untouched, because rewriting a historical record to
match a later move falsifies it. The critic showed that policy was applied too
broadly. Memories are read every session under Phase 2 as current guidance, so a
stale path there is a functional failure, not a preserved fact. Repointed.

**Proportionality of the review itself.** Six agents debated what began as eleven
lines of path repointing. The advisor ruled the review correct anyway: the gate has
no exemption for non-semantic edits to the session protocol, and the alternatives
were to fabricate the evidence string, bypass the hook, or leave links broken. All
three are worse. The gate design gap is recorded as F9. The review also earned its
cost, finding two P0 defects that would otherwise have shipped.

**Mechanism versus backlog.** The independent-thinker and the advisor both raised
whether draining the backlog without automating retirement merely defers a
recurrence. Both concluded ship the cleanup: the recurrence operates on a six month
timescale, the directory is actively misleading agents today, and the gap is
disclosed in the live index rather than hidden.

## Verification performed during the debate

Findings were not accepted on assertion. Each checkable claim was re-derived:

- A link scanner over 977 files across `.agents/architecture/`, the protocol and
  instruction documents, and `.serena/memories/` confirmed F1, F3, and F4, and
  disproved the critic's guess that ADR-017 was orphaned before the move. That file
  moved, so the break was introduced here.
- A second scanner over the 79 archived markdown files confirmed F5 at 30
  references across 19 files.
- `packages/` was listed directly, confirming F6.
- Close reasons for #51 and #739 were queried, showing both closed as completed,
  which is what makes the closed-issue signal insufficient on its own.
- Per-cluster file counts were recounted from the filesystem, confirming F8 and
  disproving the analyst's related claim that the total was 111. Git reports
  exactly 110 staged renames.

Both scanners report zero remaining broken references. 74 references across 37
files were repointed as a result of this debate.

## Dissent carried forward

The independent-thinker commits to the change while maintaining that the eval JSONs
belong in the eval system of record rather than a planning archive, and that
document by document verification of the 43 root documents was never performed. The
first is tracked as #3435. The second is disclosed in the archive index rather than
resolved, because the disposition is identical either way and nothing here is
deleted.

The critic commits while maintaining that the Serena memory question is a scope call
that deserved its own issue. It was fixed in place instead, since the fix was the
same mechanical transform already being applied.

## References

- Issue #3431, this cleanup
- Issue #3435, eval JSON re-homing, filed from F7
- Issue #3426, plan retirement automation, scope note added from F10
- `.agents/archive/planning/README.md`, the archive index and per-cluster verdicts
- `.agents/planning/INDEX.md`, the rewritten live index
