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
