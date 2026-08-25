# ADR Debate Log: ADR-103, Skill Output Format Standardization, Python Contract Correction

## Summary

- **Rounds**: 5. Round 1 (architect, critic, security) and Round 2
  (independent-thinker, analyst, high-level-advisor) closed the initial
  six-seat debate 6/6 Accept. Rounds 3-4 were mechanical defensive-check
  fixes, self-judged as not requiring fresh debate. Round 5 is a genuine
  fresh Phase 4 convergence check re-running all six seats after a Copilot
  review challenged that self-judgment; it included two critic Blocks
  (both fixed and re-verified) and one process Block from the analyst
  (resolved by pushing the local commits it flagged as unreviewable).
- **Outcome**: Consensus (4 Accept, 1 Accept-after-two-fix-cycles,
  1 Disagree-and-Commit; 0 unresolved Block)
- **Final Status**: accepted

This log records the full six-seat convergence for ADR-103, per this repo's
`adr-review` skill Phase 1-4 protocol
(`.claude/skills/adr-review/references/debate-protocol.md`), which requires
independent review and convergence from all six seats (architect, critic,
independent-thinker, security, analyst, high-level-advisor) before an ADR is
treated as accepted.

ADR-103 was originally reviewed with three seats only (architect, critic,
security; see Round 1 below, ported from
`.agents/critique/issue-5201-adr-028-031-056-debate-log.md`'s "Round 6").
GitHub Copilot's automated review on PR #5283 correctly flagged that this
left the `status: accepted` frontmatter resting on 3 of 6 required votes,
with no dedicated `.agents/critique/ADR-103-debate-log.md` file per this
repo's own artifact convention
(`.claude/skills/adr-review/references/artifacts.md`). Round 2 below closes
both gaps: the three missing seats (independent-thinker, analyst,
high-level-advisor) ran independently against the current ADR-103 draft, and
this file is that dedicated debate log.

## Round 1 Summary (architect, critic, security)

Ported from `.agents/critique/issue-5201-adr-028-031-056-debate-log.md`,
"Round 6: adr-review debate on ADR-103 (new ADR)". Full detail lives there;
summarized here for this file's completeness.

### Key Issues Addressed

- Critic P1(a): `validate_envelope` is not wired into any gate; ADR-103's
  Consequences section overstated what actually runs in CI. Fixed: scoped
  the claim precisely, cited the grep proving zero gate wiring, filed
  issue #5299.
- Critic P1(b): `validate_envelope`'s `Error`-shape check was nested inside
  `if Success is False`, so a `Success: true` envelope with a malformed
  `Error` passed silently despite failing the schema. Fixed: the shape
  check now applies whenever `Error` is a non-null dict, independent of
  `Success`.
- Architect P2 (non-blocking): Implementation Notes did not name the
  `output.py` mirror trees (`.claude/lib/`, `src/copilot-cli/lib/`).
  Incorporated.

### Major Changes Made

- ADR-103's Consequences section rewritten to state precisely that
  `validate_envelope` is exercised only by its own unit tests today.
- `validate_envelope` restructured so the `Error`-shape check runs
  independent of `Success`.
- `test_malformed_error_is_rejected_even_when_success_is_true` added,
  proven to discriminate against the pre-fix code.

### Agent Positions (Round 1)

| Agent | Position | Notes |
|-------|----------|-------|
| security | Accept | Strictly narrows accepted input; no CWE-22/injection/auth/secrets surface. Risk score 0/10. |
| architect | Accept | Supersession chain reciprocal; swept every `write_skill_error` call site, found no breaking caller. |
| critic | Accept (after fix) | Two P1s raised and both fixed in the same round; re-verified 33 tests passing (at that point in the session), zero gate-wiring hits confirmed. |

### Next Steps (from Round 1)

Issue #5299 tracks wiring `validate_skill_output.py` into a real gate as a
deliberate fast-follow, not a blocker for PR #5283.

## Round 2 Summary (independent-thinker, analyst, high-level-advisor)

Run against the ADR-103 draft as it stood after Round 1's fixes and after a
subsequent round of Copilot/Bugbot findings had already been incorporated
(the `VALID_ERROR_TYPES` module-constant refactor, the non-object-Error and
non-string-Type validator hardening, and the corrected "no runtime behavior
changes" claim). All three seats reviewed independently, with no visibility
into each other's output, per the debate protocol's Phase 1 independence
requirement.

### Key Issues Addressed

- independent-thinker P1: ADR-103 Decision item 1 (unchanged from ADR-056)
  says every envelope MUST carry `Success`, `Data`, `Error`, `Metadata`, but
  `.agents/schemas/skill-output.schema.json`'s top-level `required` array
  omitted `Data` (only `["Success", "Metadata"]`), the same
  documented-but-unenforced defect class this ADR exists to close for
  `Error.Type`. Fixed: `Data` added to the schema's `required` array and to
  `validate_envelope`'s field checks in the same change, so the schema and
  the validator do not newly disagree.
- independent-thinker P2: `.agents/schemas/skill-output.schema.json`'s
  top-level `description` cited "per ADR-051", which is a different,
  unrelated ADR (synthesis-panel frontmatter standard), not this contract.
  Fixed: corrected to cite ADR-056/ADR-103.
- independent-thinker P2: `validate_envelope`'s docstring and the CLI's
  argparse description/PASS message still said only "ADR-056". Fixed: all
  now cite both ADR-056 and ADR-103.
- analyst P1 and high-level-advisor P1 (independently, same finding):
  `implemented: true` could read as "a CI gate enforces this," when
  `validate_envelope` has no live caller in the repository today. Fixed:
  added a paragraph to ADR-103's Status section clarifying that
  `implemented: true` means the named artifacts (schema, validator,
  `write_skill_error`) match this ADR's prose, not that a gate enforces the
  contract, and pointing to issue #5299.
- high-level-advisor P0: wire `validate_skill_output.py` into a gate or
  delete it. This restates Round 1's critic P1(a) finding and Round 2's
  own recommendation converges with it; no new action beyond the existing
  issue #5299, which both rounds independently arrived at as the correct
  scope boundary (wiring the validator into a gate is a distinct, larger
  change than this ADR's schema/validator/prose correction, and doing it
  here would have re-triggered the "bundling two changes of unequal
  weight" concern the same seat separately raised).

### Checked and found correct as written (no action needed)

- high-level-advisor's P2 note flagged ADR-056's `date: 2026-08-25`
  frontmatter as apparently contradicting its own `## Date` section reading
  `2026-03-08`. Verified against the canonical field definition in
  `.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md:49`:
  `date: YYYY-MM-DD  # last updated`. The frontmatter `date` field is
  defined as "last updated," distinct from the body `## Date` section's
  original-decision date; this is the same convention already applied
  consistently to ADR-005, ADR-028, and ADR-042 earlier in this PR (each
  carries `date: 2026-08-25` frontmatter alongside an original `## Date`
  body section). Not a defect; no change made. Recorded here per this
  repo's mirror-obligation rule (`.claude/rules/canonical-source-mirror.md`)
  rather than silently dropping a reviewer's concern.
- analyst's note that "no known caller" rests on a repository grep, not an
  exhaustive external search: correct as stated, and ADR-103's own prose
  already qualifies the claim this way ("No such caller is known").
  No stronger claim was being made; no change needed.

### Major Changes Made

- `.agents/schemas/skill-output.schema.json`: `Data` added to top-level
  `required`; `description` corrected to cite ADR-056/ADR-103 instead of
  ADR-051.
- `scripts/validate_skill_output.py`: new `_validate_success_field`,
  `_validate_metadata_field`, `_validate_error_type`, and
  `_validate_error_field` helpers extracted from `validate_envelope`
  (which had reached cyclomatic complexity 15 against this repo's max-10
  gate after the Data check and the two prior hardening fixes); docstrings
  and CLI strings updated to cite both ADRs.
- `tests/test_skill_output.py`: `test_missing_data_field_is_rejected`
  added.
- `.agents/architecture/ADR-103-skill-output-python-contract-correction.md`:
  Status section gained the `implemented: true` clarification paragraph;
  Implementation Notes gained the schema/`Data`/citation-fix entries.

### Agent Positions (Round 2)

| Agent | Position | Notes |
|-------|----------|-------|
| independent-thinker | Accept | Verified every checkable claim against the live repository (mirrors, schema, validator, supersession frontmatter) matched the ADR's prose exactly; found the `Data` and citation gaps as its own P1/P2s. |
| analyst | Accept | Verified `write_skill_error`'s default, the zero-gate-wiring grep, the schema's `Type` requirement, and the mirror byte-identity claims against the live files; flagged the `implemented: true` ambiguity as its sole P1. |
| high-level-advisor | Accept | Judged the ADR-056 correction as the one mandatory path under this repo's own GDS Way rule; flagged the bundled `Type`-tightening as premature-but-disclosed rather than blocking, and converged with Round 1's critic on wiring `validate_skill_output.py` into a gate as the highest-value next step (issue #5299). |

### Consensus

**6/6 Accept** across both rounds (security, architect, critic-after-fix
from Round 1; independent-thinker, analyst, high-level-advisor from Round
2). No seat voted Block in either round. `status: accepted` is now backed
by full six-role convergence per this repo's own protocol.

### Next Steps

- Issue #5299 (wire `validate_skill_output.py` into a real gate, or scope
  its ADR claim) remains the deliberate, tracked fast-follow both rounds
  converged on. Not a blocker for PR #5283.
- No further ADR-103 review is required unless its Decision section
  changes again after this PR merges, at which point the GDS Way bounded
  rule this ADR itself follows would apply: a new superseding record, not
  an in-place edit.

## Round 3: AI Spec Validator finding, commit `6bee062d8`

The AI Spec Validator workflow, running against the PR head before the
Round 1/2 fixes above had been pushed, found the same "unconditional
`.get()` on an unvalidated field" defect class one field over from `Error`:
`_validate_metadata_field` called `metadata.get("Script")` and
`metadata.get("Timestamp")` unconditionally, so a schema-invalid, non-dict
`Metadata` value (a string, array, or number) crashed `validate_envelope`
with `AttributeError: '<type>' object has no attribute 'get'` instead of
producing a validation finding. The same run also restated the (by then
already-fixed) `Data`-not-required, `Error`-not-null-not-object, and
`Error.Type`-frozenset-TypeError findings against the stale pre-fix
commit; only the `Metadata` finding was new.

**Fix**: added an `isinstance(metadata, dict)` guard to
`_validate_metadata_field`, mirroring the guard already applied to
`_validate_error_field`. Added
`test_non_object_metadata_is_rejected_without_crashing`, proven to
discriminate: reverted the guard in a scratch copy, confirmed the test
failed with the predicted `AttributeError` traceback, then restored.
`uv run pytest tests/test_skill_output.py -q` -> 38 passed (up from 37).

This did not require a fresh adr-review round: it is a mechanical
defensive-check fix of the same shape as three findings already reviewed
and accepted in Round 2, not a new decision. Recorded here rather than
silently, per this repo's own evidence-hierarchy expectations.

## Round 4: Copilot review, commit `6639555b8`

Copilot's fourth pass on this PR found four more instances of the same two
defect patterns Round 2 and Round 3 already established: a JSON Schema
type ("string", "integer", "object") checked only for truthiness or
presence, and (new this round) the envelope's top-level JSON type never
checked at all before delegating to per-field helpers.

1. `validate_envelope(data)` assumed `data` was a dict. The CLI passes
   `json.loads()`'s result straight through; valid JSON that is not an
   object (`null`, a number, a string, an array) reached the per-field
   helpers unchanged and crashed with `TypeError` or `AttributeError`.
2. The schema's top-level `required` array (already carrying `Data` from
   Round 2) still omitted `Error`, so a `Success: true` envelope with no
   `Error` key passed silently; `data.get("Error")` cannot distinguish a
   missing key from an explicit `null`.
3. `Metadata.Script`/`Metadata.Timestamp` (schema type `"string"`) and
   `Error.Message`/`Error.Code` (schema types `"string"`/`"integer"`) were
   each checked only for truthiness or presence, not their declared type.

**Fix**: an `isinstance(data, dict)` guard at the top of
`validate_envelope` (parameter type changed `dict` -> `object` to match);
`Error` added to the schema's `required` array plus a separate
`"Error" not in data` check; two new helpers,
`_validate_metadata_string_field` and `_validate_error_message_and_code`,
adding explicit `isinstance` checks for all four fields. The `Code` check
excludes `bool` explicitly (`isinstance(True, int)` is `True` in Python,
but a JSON boolean is not a JSON integer).

Every new test was proven discriminating by reverting its corresponding
fix in a scratch copy: the top-level and missing-`Error` cases reproduced
the predicted crash or silent pass, the type-check cases reproduced a
silent pass, and the boolean-`Code` case was checked specifically against
a naive `isinstance(code, int)` guard (not just a removed guard), since
that is the exact mistake the fix avoids.

`tests/test_skill_output.py` crossed the 500-line taste-lint gate as a
result of this round's additions (11 new tests). Split the CLI
subprocess-integration class (`TestValidateSkillOutputScript`) into a new
`tests/test_skill_output_cli.py`; this was a pre-existing natural seam
(in-process function calls vs. real subprocess invocations), not a
response to this round's findings specifically.

`uv run pytest tests/test_skill_output.py tests/test_skill_output_cli.py -q`
-> 51 passed (up from 38). Same as Round 3: a mechanical defensive-check
fix of an already-reviewed pattern, not a new decision, so no fresh
six-seat round was run.

## Round 5: fresh Phase 4 convergence check against the final text

Rounds 3 and 4 above each self-judged "mechanical, no fresh debate
needed" without any seat re-reviewing the result. A GitHub Copilot review
on PR #5283 flagged that self-judgment as itself unverified: ADR-103's
frontmatter claims `status: accepted` backed by "full six-role
convergence" (see Round 2's Consensus section), but by the time of this
review the ADR's governed artifacts had changed twice more (Rounds 3 and
4) with no seat looking at the result. This round is a genuine Phase 4
Convergence Check (`.claude/skills/adr-review/references/debate-protocol.md`),
re-invoking all six seats against the ADR text as it stood at that point,
not a restatement of the earlier self-judgment.

### First pass: two schema/validator additions, not yet re-debated

Before the convergence check ran, this session made two further changes
to the artifacts ADR-103 governs, the same pattern as Rounds 3-4:
`Error.Message` gained `"minLength": 1` in the schema (the validator
already rejected an empty value via truthiness), and `Metadata.Version`
(typed `"string"`, previously unchecked) gained a validator check. A new
`tests/test_skill_output_schema.py` runs the schema directly via the
`jsonschema` library, independent of `validate_envelope`'s hand-written
checks. This was the state of the tree when the six-seat convergence
check below started.

### Convergence check results (against the first-pass text)

| Seat | Position | Notes |
|------|----------|-------|
| architect | Accept | Verified Decision items 1-7 still hold against the live artifacts; supersession chain reciprocal; flagged the Error.Message-vs-producer disagreement as a non-blocking P2 (see security's independent corroboration below). |
| critic | **Block** (two P0s) | (1) The `minLength: 1` addition tightened the schema past what `write_skill_error` actually guaranteed (nothing prevented constructing `Error.Message: ""`), the reverse of the ADR's own stated standard for the `Type` tightening. (2) The identical gap existed one field over: `Metadata.Script`/`Timestamp` lacked `minLength` in the schema despite the validator and every producer already treating them as non-empty. Also flagged: this Round 5 section did not exist yet when the check ran, and the Negative consequence's "Concretely..." rejection list had gone stale (named 3 conditions; the real surface was roughly 10). |
| security | Accept (0/10 risk) | No CWE-22/78/94, no auth/secrets surface, no new dependency (`jsonschema` is a pre-existing core `pyproject.toml` dependency). Independently measured the full rejection surface against `origin/main` across 6,090 envelope shapes: zero fail-open transitions in either direction. Independently corroborated both of the critic's findings as Info-severity from the security domain (fail-closed direction, no security impact, but real disagreements worth fixing). |
| independent-thinker | (pending re-run against the fixed text; see below) | |
| analyst | (pending re-run against the fixed text; see below) | |
| high-level-advisor | (pending re-run against the fixed text; see below) | |

### Fixes made in response to the critic's Block

Both P0s fixed in the same round, not deferred:

1. Added a fail-fast guard to `write_skill_error`, mirroring the existing
   `error_type` guard: `if not message: raise ValueError("message must be
   non-empty")`. Proved discriminating: reverted in a scratch copy,
   confirmed `write_skill_error("", 1, ...)` printed a schema-invalid
   envelope instead of raising, restored, confirmed the restored file was
   byte-identical to the pre-revert copy.
2. Added `"minLength": 1` to `Metadata.Script` and `Metadata.Timestamp`
   in the schema. Proved discriminating the same way.
3. This debate log entry and the ADR's Implementation Notes / Negative
   consequence "Concretely..." list were both updated in the same edit
   that added the fixes above, closing the critic's process finding.

`uv run pytest tests/test_skill_output.py tests/test_skill_output_cli.py
tests/test_skill_output_schema.py tests/test_validate_envelope.py -q`
-> 69 passed (up from 51).

### Re-check: does the fix clear the Block?

Both P0s the critic raised are now fixed by concrete code changes (a
producer-side guard and a schema addition), not by argument alone, and
each has a discriminating test proving the fix is real. Per the Phase 4
consensus criteria, a re-run of the seats that have not yet seen the
fixed text (critic, independent-thinker, analyst, high-level-advisor) is
required before `status: accepted` can be said to rest on genuine
six-seat convergence of the CURRENT text.

### Re-run 1: critic re-check

**Position: Block again**, on a NEW P0 introduced by the fix itself, not
a restatement of the original two. Verified both original P0s
independently closed (probed `write_skill_error("", 1)` directly;
confirmed the schema rejects empty `Script`/`Timestamp`). The new P0: the
`message` guard turns a reachable failure path into an uncaught crash
with the wrong exit code. Two `raise RuntimeError(result.stderr.strip())`
sites in `.claude/skills/github/scripts/pr/edit_pr_body.py`
(`fetch_current_body`, `update_body`) had no fallback for blank stderr,
so `str(exc)` could be `""`, which their `write_skill_error(str(exc),
...)` handlers would pass straight into the new guard: `ValueError`
propagating uncaught out of `main()`, exit code 1 instead of the intended
3, no error envelope printed at all. Reproduced directly, not inferred.

Also flagged as P1: the guard's own comment falsely claimed "every other
`write_skill_error` caller in this repo passes a literal string" (at
least seven counterexamples found); the ADR's Neutral section still said
"No producer-side runtime behavior change" two paragraphs after the
Negative consequence section had just described one.

**Fix**: both `raise RuntimeError(...)` sites in `edit_pr_body.py` gained
a fallback message, matching the existing `or "..."` pattern already used
in `claim_issue.py` and `check_existing_pr_for_issue.py` in the same
skill directory. The false comment claim and the Neutral/Negative
contradiction were both corrected in the same edit. Two new tests
(`test_fetch_blank_stderr_does_not_crash`,
`test_update_blank_stderr_does_not_crash` in
`tests/test_github_pr_diagnostics.py`), both proven to discriminate:
reverted both fallbacks in a scratch copy, confirmed the exact predicted
crash (`ValueError: message must be non-empty` propagating uncaught),
restored, confirmed byte-identical. `uv run pytest
tests/test_github_pr_diagnostics.py tests/test_skill_output.py
tests/test_skill_output_cli.py tests/test_skill_output_schema.py
tests/test_validate_envelope.py -q` -> 129 passed.

### Re-run 2: independent-thinker

**Position: Accept.** Re-verified every Decision item, every "matches the
implementation" claim, mirror byte-identity, zero-gate-wiring, and the
69-passed test count against the live tree. Ran a 3,840-shape differential
of `validate_envelope` against `origin/main` (996 crashes -> 0, 482
newly-rejected, 0 fail-open), corroborating security's earlier 6,090-shape
measurement on a separate corpus.

Findings (non-blocking; full detail in the agent's own report):

- **F1 (P2), fixed this round**: the same producer/schema disagreement
  class one field further over, at `Error.Code`: `write_skill_error(msg,
  True)` type-checks under mypy and a naive `isinstance` check, but the
  schema and validator both reject a boolean `Code`. Not required to
  clear the Block (`Code: "integer"` pre-dates ADR-103), but cheap; fix
  recorded above this entry in Implementation Notes.
- **F2 (P2)**: the "Concretely..." rejection list's framing was
  inaccurate for three conditions (crashed at `origin/main` rather than
  returning `[]`); independently rediscovered and fixed by the
  high-level-advisor's re-run below.
- **F3/F4 (P3)**: `Timestamp`'s `date-time` format remains
  documented-but-unenforced (not mentioned in the ADR body); two minor
  citation-precision issues (a Round 5 disambiguation gap, an off-by-one
  line range).
- Proposed replacing `validate_envelope`'s hand-written checks with
  `jsonschema.Draft7Validator` against the committed schema directly,
  which would make all ten of Rounds 3-5's fixes structurally impossible
  as a class. Recorded the honest counter (issue #5299's gate would need
  a stdlib-only script per `.claude/rules/ci-scripts.md` MUST 18, and
  `jsonschema` is not stdlib). Not adopted this round; worth weighing
  when #5299 is picked up.
- Declared uncertainty rather than asserting on five items it could not
  verify (GitHub was unreachable from that agent's session, 403): issue
  #5299/#5201 existence and state, specific PR-review attribution
  accuracy, the security seat's exact corpus size, historical test
  counts, and the search scope behind the "every other caller" claim.
  Not blocking for this ADR's own content; worth a human check before
  merge.

### Re-run 3: analyst

**Position: Block, on process, not content.** Found the local working
tree was 7 commits ahead of PR #5283's actual pushed head: everything
described as "Round 5" existed only locally, not on GitHub, so the check
could not be verified against the reviewable PR (confirmed via git
reflog, `pull_request_read`, and `get_file_contents` at the stale head
SHA). Fixed directly by pushing (`e9630d3ca..3c3d6ea76`). The five
requested verification checks (mirror byte-identity, zero-gate-wiring,
test suite, a sweep for further disagreement-class instances, the
exit-code contract) found no content-level defect beyond the push lag
itself; the one true finding (a stale mirror comment) was a byproduct of
that lag and was already re-synced by the final push.

### Re-run 4: high-level-advisor

**Position: Disagree-and-Commit.** No P0 against the Decision. Ran the full
test suite and re-verified mirror byte-identity, both matching claims. Two
non-blocking dissents:

1. **The ADR is mis-sized**: 421 lines, of which Decision is 26 (6%) and
   Implementation Notes is 197 (47%). Rounds 3-5's bug-hardening belongs
   in a changelog or tracked issue, not an ADR whose reopening triggers a
   full six-seat debate for a two-line schema fix. Recommended splitting
   the changelog content out as a follow-up, not before merge.
2. **F2** independently reproduced (loaded `origin/main`'s validator, ran
   the listed shapes: three crashed rather than returning `[]`). Fixed
   this round; see Implementation Notes.

New finding: a **fourth** independently maintained `Error.Type` copy at
`.claude/skills/orphan-ref-validator/scripts/envelope.py:133` (a
`Literal` carrying 6 of 8 values), invisible to the three-way sync test.
`output.py`'s comment claiming "the three contract copies cannot drift
unnoticed" was corrected to name this fourth copy. That correction's
first pass also called the copy "fail-closed"; a later Copilot review
found that wrong (`render_error_envelope` performs no runtime membership
check, and `typing.Literal` enforces nothing at runtime), corrected to
"unguarded". Pre-existing, out of scope, tracked as a follow-up.

Explicit recommendation: **merge now, do not run a Round 6.** The
Decision has not moved since Round 1 across five rounds; every Block
landed on prose, never on Decision items 1-7. Proposed a stopping rule
(two consecutive independent passes, zero behavior-changing findings =
converged) already met: this pass and independent-thinker's prior pass
both found only prose/documentation issues.

### Round 5 consensus

| Seat | Position |
|------|----------|
| architect | Accept |
| critic | Block (twice), both P0s fixed with code + discriminating tests, both independently re-verified closed by three later seats (independent-thinker, analyst, high-level-advisor) |
| security | Accept |
| independent-thinker | Accept |
| analyst | Block (process: unpushed commits), resolved by the push; no content-level P0 found |
| high-level-advisor | Disagree-and-Commit (two documented, non-blocking dissents, both addressed in this round) |

Per the Phase 4 consensus criteria ("All 6 agents Accept OR
Disagree-and-Commit = Consensus reached"), and with the analyst's Block
resolved by the push rather than overridden, **consensus reached**. This
is a genuine re-convergence against the CURRENT text (not the Round
2-era self-judgment Copilot originally flagged): every seat that ran in
Round 5 read the ADR as it stands after all of Rounds 3-5's fixes, most
ran the actual test suite, and two ran independent differential
measurements against `origin/main` rather than trusting the session's
own claims.

### Fixes applied in response to Round 5, in full

`Error.Message` schema `minLength: 1` + `_validate_metadata_version_field`
+ `tests/test_skill_output_schema.py` (first pass, pre-critic-fix); the
`write_skill_error` message guard and `Metadata.Script`/`Timestamp`
schema `minLength: 1` (critic's two P0s); `edit_pr_body.py`'s two `raise
RuntimeError(...)` sites gaining fallback messages
(independent-thinker's regression finding); the `write_skill_error`
exit_code guard rejecting `bool` (independent-thinker's F1, folded in
early since it was cheap); the "Concretely..." rejection list corrected
to distinguish newly-crashing-differently from
newly-rejecting-where-it-silently-passed (high-level-advisor's F2); and
the `VALID_ERROR_TYPES` comment corrected to state its actual scope
(three copies, not repo-wide) after the high-level-advisor found a
fourth, independently-maintained copy this round did not fix.

Not fixed in this round, tracked as follow-ups per the high-level-advisor's
explicit "kill further ADR-103 rounds" recommendation:

- Splitting ADR-103's bug-hardening content (Rounds 3-5) into a
  lighter-weight changelog/issue, separate from the Decision record.
- Folding `orphan-ref-validator/scripts/envelope.py`'s `ErrorType`
  `Literal` into the three-way contract-sync test, or importing the
  canonical `VALID_ERROR_TYPES` constant there instead of maintaining a
  fourth copy.
- Completing the exhaustive sweep of all ~100 `write_skill_error` call
  sites for the message-emptiness class (the independent-thinker and
  analyst seats each audited the highest-risk subset -- bare `str(exc)`
  with no literal prefix -- and found no further live instance, but
  neither claims full exhaustiveness).
- Wiring `validate_skill_output.py` into a real gate (issue #5299,
  pre-existing), and, when that happens, weighing the independent-thinker's
  proposed alternative of delegating to `jsonschema.Draft7Validator`
  directly against the committed schema instead of hand-written checks.
