# ADR Debate Log: ADR-103, Skill Output Format Standardization, Python Contract Correction

## Summary

- **Rounds**: 2 (initial 3-seat pass, then a fresh 3-seat pass closing the
  remaining seats)
- **Outcome**: Consensus (6/6 Accept)
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
