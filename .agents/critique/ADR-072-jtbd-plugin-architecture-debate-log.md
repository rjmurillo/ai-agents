# ADR-072 debate log

Record: `.agents/architecture/ADR-072-jtbd-plugin-architecture.md`, `status:
proposed`, `implemented: false`, dated 2026-06-09.

## Round 1, 2026-09-09

Six seats. Five returned Block recommending `rejected`. The sixth returned Block
against that consensus and refuted the premise the other five shared.

| Seat | Verdict | Recommended status | Core position |
|---|---|---|---|
| architect | Block | rejected | Decisions 2 and 3 rest on manifest capabilities this repo's validator forbids |
| independent-thinker | Block | rejected | Second-system markers; mechanisms assumed rather than verified |
| security | Block | rejected | No `dev-lifecycle -> quality-gates` edge declared; emitter review bar too weak |
| high-level-advisor | Block | rejected | Chesterton's fence holds; the slicing is discovery-shaped, not storage-shaped |
| analyst | Block | rejected | Premises falsified against HEAD; buildability not discharged for any decision |
| critic | Block | **none, stay proposed** | Ran a probe; the mechanism objection is refuted |

### What the five agreed on, and why it did not hold

All five read `build/scripts/validate_plugin_manifests.py:86`, which pins its
rationale to "Claude Code 2.1.122", and concluded that a `dependencies` field and
explicit content keys are capabilities the platform does not offer. The comment
records a measurement taken in commit `a4ed5850c` on 2026-05-01. It was read as a
standing platform law.

The critic seat ran `claude plugin validate` instead of reading about it. That
probe was reproduced independently by the orchestrator on Claude Code 2.1.266
before any of it was written into the record:

| Probe | Result |
|---|---|
| `dependencies: ["cap-b@mkt"]` plus explicit `skills` and `commands` keys | PASSES, only routine missing-`version` and missing-`author` warnings |
| An unrecognized key `zzzUnknownKey` | `Unknown field ... Claude Code ignores it at load time`, validation PASSES |
| `dependencies: "nope"` | `dependencies: Invalid input`, validation FAILS |

The second and third are the controls that make the first mean something. A field
the host merely tolerated could not be type-checked, so the hard failure on a
wrong type establishes that `dependencies` is first-class. The critic also
installed a two-plugin local marketplace end to end and observed the resolver
report `+ 1 dependency: cap-b` on install and a no-longer-needed notice on
uninstall.

`_is_repo_marketplace_manifest` also turned out to gate the forbidden-key check
on three hardcoded paths, so a capability-plugin root anywhere else is unaffected
by it today. Five seats read the constant and none read the function under it.

**This is the round's most useful output, and it is a finding about the review
method rather than about the ADR.** Five independent seats converged on a wrong
answer because they all read the same stale comment, and unanimity across seats
that share a source is one observation, not five. Only the seat that executed
something moved the result. That matches ADR-101's own recorded experience across
eleven rounds, that every substantive defect came from executing something or
reading a primary source and none from re-reading text.

### What survived the probe

The five seats' non-mechanism findings are real, and the amendment carries all of
them:

| Finding | Disposition |
|---|---|
| The "~400 engineers" installed base is ADR-045's future-tense distribution target restated as fact, for an extraction that never happened | Corrected in Distribution context; the number is withdrawn, not repaired |
| Decision 1 names five plugins, zero of which exist; two contents cells partition hook assets that do not exist (ADR-097 emptied both `hooks.json`) | Noted in place |
| `dependencies` is absent from `ALLOWED_KEYS`, and ADR-092 deleted `version`, so a dependency can only be a bare name | Recorded in Decision 3 as local work with the ADR-092 citation |
| M5's alias has no dedicated schema field | Recorded in Reversibility, with the two constructible routes and the obligation to name one and pin a client version |
| Issue #1774 closed `not_planned` ten days after authoring; epic #1072 closed | Recorded; ADR-052's successor precedent named as the remedy |
| ADR-064 conflict never cited | Cited. ADR-064 settled first, `accepted` and `implemented: true` on 2026-09-08, deleting `generate_commands.py`, so M1 to M3's commands leg is dead as written |

### One charge withdrawn

The high-level-advisor seat reported ADR-072's `#1773 decision D3` citation as a
probable number collision with the PR that broke plugin install. The analyst seat
checked and found the opposite: PR #1773 does not exist (the API returns 404),
issue #1773 does and its decisions table row D3 says what ADR-072 attributes to
it, and the change that broke plugin install was PR #1776. The miscitation is in
`build/scripts/validate_plugin_manifests.py` lines 4 and 233 and in
`.agents/incidents/2026-04-27-pir-plugin-manifest-schema-1773.md` lines 13 and
30, all of which call the issue number a PR. That is a defect in shipped
artifacts, one of them a runtime error message, and it needs its own change.

### Why the record is amended rather than rejected

In this repository `rejected` means declined and not returning; ADR-031 and
ADR-095 both open "Recorded so the proposal is findable and does not return".
Every seat endorsed the JTBD direction. Stamping `rejected` would record the
opposite of the panel's position, on a mechanism objection the probe refuted.
ADR-073 line 58 names this record by name as the case the prose Status section
exists to carry.

The owner ruled: amend now, settle later.

### Outcome

No consensus. The record stays `proposed` and is amended against every surviving
finding. The blockers are now enumerated in its Status section, and all five are
this record's own defects rather than platform limits.

### Before a second round

1. Answer the three Definition-of-Ready questions.
2. Rewrite Decision 1 against the three plugin roots that exist.
3. File successors for the milestones and name them in Status, per ADR-052.
4. Re-run the panel against the amended text, with the mechanism question closed
   by the probe rather than reopened by each seat.

### Tracker, filed 2026-09-09

Unlike ADR-101, which turned out to have three open trackers nobody had named,
ADR-072 genuinely had none: issue #1774 closed `not_planned` on 2026-06-19, ten
days after the record was authored, and parent epic #1072 is closed.

Successor **#5669** is filed and named in the Status section, per ADR-052.

It tracks **settling** this record, not implementing it, and says so in its own
body. An implementation tracker would have been manufactured work: this round
established that the record names five plugins of which zero exist, leaves three
Definition-of-Ready questions open, and points M1 to M3 at an emitter ADR-064
deleted. Its checklist is the blocker list from the Status section, so closing it
means the record is ready for a second round, not that any milestone shipped.

### A note on Status prose, for whoever writes round 2

`.agents/architecture/README.md` is generated by
`build/scripts/generate_adr_index.py`, and its blurb column is the ADR's `##
Status` section with the leading status word stripped. So a Status opening
"Proposed, and amended ..." renders in the index as ", and amended ...". Write
the first sentence so the remainder stands alone: "Proposed. Amended ..." works,
a trailing clause does not. The staleness gate catches the drift but not the
awkwardness.

## Two corrections the round 1 amendment did not carry through, 2026-09-09

Round 1's amendment withdrew two premises and repaired the statement of each
without repairing its restatement elsewhere in the same file. Both were found by
reading the record straight through after the amendment merged, which is the same
way round 1's surviving findings were found.

**The installed-base figure.** "Distribution context" withdraws the ~400 figure
as ADR-045's future-tense target restated as a measurement, quoting ADR-045 lines
24, 38 and 56, all three of which verify verbatim. The Negative consequences list
kept "Cross-cutting change to the install contract for ~400 consumers" as a
statement of fact, so the record withdrew the number in one place and spent it in
another.

**The tracked follow-up pointed at a closed epic.** The Status section records
epic #1072 and issue #1774 as closed and names successor **#5669**. The tracked
follow-ups list still read "M1 to M5 issues opened under #1072 before
implementation", which instructs an implementer to file against a closed epic and
bypasses the successor filed precisely so the work has somewhere to live.

Both are corrected in place with the correction visible rather than deleted, per
this record's own treatment of the premises round 1 refuted. The shape is worth
naming because it recurred on ADR-101 in the same session: a correction reaches
the sentence that carries the argument and not the paraphrase two hundred lines
away, and no gate in this repository looks for the second one.

## Round 3, 2026-09-11: six seats against the amended text

Run to clear issue #5669 blocker 6. The mechanism question was held closed by the
2026-09-09 probe and no seat reopened it; two seats re-ran an equivalent probe on
Claude Code 2.1.268 and got the same result, making three independent
confirmations. The three Definition-of-Ready questions were held as owner
decisions and no seat decided one.

| Seat | Verdict |
|---|---|
| architect | BLOCK |
| critic | BLOCK |
| analyst | ACCEPT |
| independent-thinker | DISAGREE-AND-COMMIT |
| security | DISAGREE-AND-COMMIT |
| high-level-advisor | ACCEPT |

Not consensus. Both BLOCKs carried a P0; one is fixed below and the other is an
owner decision the round cannot take.

### P0: the record quoted a sentence that does not exist

Decision 4 attributed reasoning to "ADR-064's own Related Decisions section" and
quoted it as saying the two records "cannot both stand as written". Verified
independently before acting: `grep -rn "cannot both stand as written" .
--include=*.md` returns only ADR-072 itself, and `grep -n '072'
.agents/architecture/ADR-064-commands-to-skills-migration.md` exits 1. ADR-064's
Related Decisions section names ADR-030, ADR-094, ADR-012, ADR-040 and a design
review. It does not mention ADR-072 anywhere in the file.

The References section restated the same unsupported attribution in different
words ("It named the conflict with this record first"). Both are corrected, and
the underlying point, that ADR-064 settled first by shipping, needs no citation
and now carries none.

This is the fifth instance in this file of the pattern round 2 named: a
correction reaches the sentence carrying the argument and not its restatement
elsewhere. Round 2 found the restatement two hundred lines away. Round 3 found
one a hundred and twenty lines away, in a section whose job is to list sources.

### P0 held open: M5's alias route is still undecided

The critic seat is right that naming two routes is not deciding between them, and
that this is the only stated mitigation for the only irreversible milestone.
Choosing the route and pinning the client version is issue #5669 checklist item
4, an owner decision. What round 3 could do, it did: it measured route 1.

### The unprobed mitigation, now probed

The Reversibility section asserted that "two marketplace entries with different
`name` values pointing at one `source` validate clean" in the same confident
register as Decision 3's probed finding, in the section immediately after it, and
nobody had ever run it. The independent-thinker seat caught this and named it as
the round 1 failure shape reproduced inside the amendment written to diagnose
that shape.

Run on 2026-09-11 against Claude Code 2.1.268, with two negative controls:

| Case | Result |
|---|---|
| two entries, different `name`, one `source` | PASS, exit 0, routine missing-`version` and missing-`author` warnings only |
| `plugins: "nope"` | FAIL, `plugins: Invalid input`, exit 1 |
| two entries, SAME `name`, one `source` | FAIL, exit 1 |

The third control is the discriminating one. Name uniqueness is enforced, so the
passing case is a genuine alias rather than a duplicate the validator ignores.
Route 1 now has a measured floor of 2.1.268. Route 2, the `strict: false` catalog
metadata path, remains unprobed and the record now says so.

### A defect this round introduced and this round corrected

The Cursor and Codex asymmetry paragraph added earlier on 2026-09-11 said a Codex
emitter would mean "reversing a requirement", citing REQ-003-010 through
`generate_skills.py`'s docstring. The analyst and advisor seats independently
read the requirement itself.
`.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:358` to `:359`
reads "`.claude/` is read-only to the build. The build shall never write to
`.claude/<artifact>/` or `.claude/settings.json`". That is a no-write invariant.
It says nothing about excluding `AGENTS.md` and `CLAUDE.md` from generated
output.

So the exclusion at `generate_skills.py:39` is real in code and its stated
requirement backing is one hop short. The record now says exactly that, and the
docstring citation is flagged as a separable defect in `generate_skills.py`
rather than in this record. The paragraph that overstated it was written in the
same session that wrote this log, which is worth recording plainly: a citation
chain was followed one link and not two.

### Other findings applied

| Priority | Finding | Disposition |
|---|---|---|
| P1 | Context's "Current generation model" still listed `generate_commands.py` as existing and `.claude/commands/*.md` as a canonical source, both deleted by ADR-064; the 2026-09-09 amendment corrected this in Decision 4 only | Rewritten. Rules and hooks split from the commands leg, which is now recorded as gone |
| P1 | References listed `generate_commands.py` among governing source files | Removed, with a note that ADR-064 deleted it |
| P1 | ADR-107 governs provenance for generated harness projections, the surface M1 to M3 would write into, and was cited nowhere | Added, recording the asymmetry ADR-107 itself declares |
| P1 | Decision 3 required fail-loud only for a missing dependency, and was silent on a declared dependency widening a consumer's install | Two M4 requirements added: validate the dependency value and constrain its marketplace; justify each edge in the PR that adds it |
| P1 | The job-shaped install premise is an unmeasured hypothesis; a repository-wide search found no user research, install friction report, or complaint about the current split | Recorded in Negative consequences. Raised independently by two seats |
| P2 | "ADR-073 line 58" is line 57 | Corrected |
| P2 | "lines 86 and 120" pin the 2.1.122 rationale; line 120 is blank and the real occurrences are 86, 99 and 133 | Corrected |

### Left open, deliberately

- The three Definition-of-Ready questions. Owner decisions. The advisor seat
  produced a grounded options brief for each; it is attached to issue #5669
  rather than written into the record, because the record must not pre-empt the
  decision.
- A fourth question the round surfaced and the record now names: whether a Codex
  emitter writes a new generated surface or converts some of the eleven
  hand-authored `AGENTS.md` files. Different costs, different risks, and the
  third Definition-of-Ready question is incomplete without it.
- M5's alias route choice, per the P0 above.
- ADR-045's `implemented: true` flag, which this record has flagged as wrong
  since round 1 with no tracker named. Still untracked.
- A path-traversal asymmetry the security seat found in
  `validate_plugin_manifests.py`: `_validate_hooks_string_ref` does a
  `resolve()` plus `is_relative_to(plugin_root)` containment check that the
  `agents`, `skills` and `commands` path fields never get. Pre-existing, unrelated
  to this record, and cheapest to close in the same PR as M4 since that PR opens
  the file anyway.

### Round 3 addendum, same day: the third line citation drifted while the round ran

Four commits landed on `main` between this round's commit and its first check-in,
one of them ADR-108, which amended REQ-003 in the same file this round had just
started citing. Two things moved at once:

- **The line number.** REQ-003-010 sat at line 358 when the Cursor and Codex
  paragraph was written and at 359 about an hour later.
- **The quoted sentence.** ADR-108 added an "except the template-owned skill
  files" carve-out, so the verbatim quote in this record stopped one clause
  early and presented an amended requirement as unamended.

The substance was unaffected: REQ-003-010 still constrains where the build may
write rather than which filenames it may emit, the carve-out adds no filename
exclusion, and `generate_skills.py` is unchanged (`_DEFAULT_EXCLUDES` at line 39,
the docstring attribution at line 7). ADR-107 also still names this record and
still declares it "**not** a dependency", so the reference added this round
holds.

The paragraph now cites REQ-003-010 by requirement id and names the
ADR-108 amendment. Counting the two this round already corrected (an ADR-073
reference off by one, and a validator line pair where one of the two cited lines
was blank), that is three line citations wrong out of three checked in a single
round. The generalization worth keeping: in this repository, cite a stable
identifier (a requirement id, a symbol name, a heading) and quote the contract
verbatim. Reserve a line number for a file the citation-freshness gate actually
covers, and expect it to rot everywhere else.

## Round 4, 2026-09-12: six seats against the accepted text

Run because the owner directed this record to `accepted` and round 3 had not
reached consensus. The four Definition-of-Ready answers, the M5 route pick and the
`dependencies` code were all new since round 3, so the round was reviewing text no
seat had seen.

| Seat | Verdict |
|---|---|
| architect | ACCEPT |
| critic | BLOCK |
| analyst | BLOCK |
| independent-thinker | DISAGREE-AND-COMMIT |
| security | DISAGREE-AND-COMMIT |
| high-level-advisor | ACCEPT |

Both BLOCKs carried defects in the new text, both are fixed below, and neither
challenged the direction.

### The P0 worth reading: an authority claim that evidenced itself

The record said the Definition-of-Ready answers were taken "under delegated
authority" and cited nothing. The critic and independent-thinker seats
independently ran the same check and got the same result: `grep -rn "delegated
authority" --include=*.md .` returns only ADR-072, issue #5669 carries zero
comments, and `universal.md` MUST NOT 9 already says git identity cannot prove a
human acted. AGENTS.md lists "New ADRs" under **Ask First** and this record's
frontmatter names `decision-makers: [rjmurillo]`; an agent asserting it was
authorized satisfies neither.

The instruction was real, and it was given in a working session, which is not a
repository artifact and cannot be cited as one. So the record no longer claims it.
It now says what is checkable: the owner's merge of the pull request carrying the
status flip is the ratification, and until that merge the `accepted` enum is a
proposal. That is the honest shape, and it has the useful property that the
evidence and the act are the same event.

The independent-thinker seat added the closing half: a future record may cite
ADR-072 for the settled mechanism questions but may not cite its acceptance as
evidence the job-shaped install premise is validated. That is the exact path by
which ADR-045's unexecuted `implemented: true` became citable authority for this
record, and it is now barred in text.

### The seventh restatement drift, and the first one inside a single section

The architect seat found the Status section's Blockers list still reading "1. The
Definition-of-Ready questions below are unanswered" about thirty lines below a
paragraph saying all four were answered, with item 4 similarly stale. The previous
six instances were far enough apart that distance explained them. This one was not.
All five blockers are now struck with their closing dates rather than deleted, so
the path from `proposed` to `accepted` stays auditable.

### The same line citation drifted twice in one session

The analyst seat found "lines 86, 99 and 133" for the 2.1.122 rationale had become
140, 153 and 187. By the time the fix was applied it had moved again, to 146, 159
and 193, because the `dependencies` validator this very change adds sits above it.
Three drifts of one citation, the last two caused by edits in the change that was
documenting the problem. It is now cited by symbol: the comment above
`_is_repo_marketplace_manifest`, the comment above
`_MARKETPLACE_RUNTIME_FORBIDDEN_KEYS`, and the error string inside
`_check_marketplace_runtime_forbidden_keys`.

### A real code defect the security seat found in the new validator

`_DEPENDENCY_VERSION_SPECIFIER_RE` was `@\d|==|>=|~|\^\d`, which let
`cap-b<2.0.0` through as a bare name and so contradicted the stated intent that
any version specifier is rejected. Extended to cover `<`, `<=` and `!=`, with
three regression cases added to the parametrization. The suite is 58 passing, 16
of them dependency cases.

### Other findings applied

| Priority | Finding | Disposition |
|---|---|---|
| P0 | "Shipped 2026-09-12" described code sitting uncommitted in the working tree, not on `main` | Reworded to "Staged in this same change", with the distinction stated |
| P1 | ADR-107 called ADR-072 `proposed` in two places and would contradict it on merge | Both updated, the same treatment condition 3 required for ADR-045 |
| P1 | The test count read "Ten tests"; neither 10 nor the seat's 12 was right | Measured: nine functions, sixteen collected cases after the regression additions |
| P2 | The Context commands bullet said the correction had not reached it, inside the bullet that is the correction | Rephrased |
| P2 | `.agents/architecture/README.md` was not regenerated after the status flip | Regenerated; both ADR-072 and ADR-101 moved to the Accepted table |

### Left open, recorded rather than fixed

- **M4 owes four supply-chain items**, not two. The security seat added
  traversal defense for dependency entries (they get none today, not even the
  `..` check the path fields have), unicode homoglyph rejection, and a
  self-reference and length bound, alongside the marketplace-membership
  constraint already named. It ranked homoglyph rejection ahead of the
  marketplace constraint, because a confusable name defeats the human PR review
  that is the only control until M4 ships.
- **The `keywords` carrier is the weakest of the four answers.** The
  independent-thinker seat noted the 2026-09-09 probe measured a novel `jobs`
  key being ignored, which is evidence about schema tolerance and not about
  `keywords`. Nobody has probed whether any host surface displays or indexes
  `keywords`. Probe before M4 locks the mechanism.
- **"Exactly one `jtbd:` keyword" needs a producer, not just a checker.** The
  nearest precedent, `check_dual_priority_labels.py`, enforces at most one and
  leans on a single canonical writer. `plugin.json` is hand-edited and has no
  such writer.
- **ADR-045's `implemented: true` is still wrong and still untracked**, flagged
  in round 3 and again here. It should not keep riding as a footnote in this
  record.
- **Issue #5669 was closed before its own checklist item 6**, the panel re-run,
  had concluded. This round is that re-run.
