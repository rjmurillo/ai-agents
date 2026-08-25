---
id: ADR-103
status: accepted
date: 2026-08-25
decision-makers: [rjmurillo]
supersedes: [ADR-056]
superseded-by: null
explainer: null
implemented: true
---

# ADR-103: Skill Output Format Standardization, Python Contract Correction

## Status

Accepted (2026-08-25, issue #5201). Supersedes ADR-056: corrects two Decision
items that still specified ADR-056's original PowerShell-era wording after
the skill-output surface migrated to Python, and settles a related
enforcement gap Copilot's PR review found while checking the correction.

`implemented: true` means the artifacts named in the Decision section (the
schema, the standalone validator, `write_skill_error`'s behavior) now match
this ADR's prose, not that a CI gate enforces the contract: two independent
adr-review seats (analyst, high-level-advisor) flagged that the flag could
otherwise read as "enforced." `validate_envelope` has no live caller in this
repository today; see the Negative consequence below and issue #5299.

## Date

2026-08-25

## Context

ADR-056 ("Skill Output Format Standardization", accepted 2026-03-08,
`implemented: true`) standardizes a JSON envelope for skill script output.
Its Decision section was written when skill scripts were PowerShell and
named a `-OutputFormat` parameter and a flat `ErrorCode` field. The skill
output surface has since migrated to Python (ADR-042); the shipped
implementation, `scripts/github_core/output.py`, uses a `--output-format`
argparse flag (`add_output_format_arg`) and nests the error code and type
inside the envelope's `Error` object (`write_skill_error`), never a
top-level `ErrorCode`.

During issue #5201 (reconciling contradicting ADR statuses), a PR draft
edited ADR-056's Decision section in place to match the Python contract.
GitHub Copilot's review on PR #5283 correctly rejected that approach: ADR-056
already carries `implemented: true`, and this repository's own documented
policy (`.claude/skills/adr-generator/references/adr-best-practices.md`,
"ADR Mutability and Superseding", the GDS Way bounded rule) states plainly:
"Decision change after any implementation: create a new superseding ADR.
Never delete the old one." This ADR is that superseding record. ADR-056's
Decision section is restored to its original wording; this ADR carries the
correction.

Copilot's same review pass found a second, independent gap while checking
the correction: the JSON schema (`.agents/schemas/skill-output.schema.json`)
and the standalone validator (`scripts/validate_skill_output.py`) both treat
the envelope's `Error.Type` field as optional (present in neither's
`required` list; the validator's `validate_envelope` checks `Type` against
the valid-values set only when the field is truthy), while ADR-056's prose
(and this ADR's corrected item 6 below) states every error object carries a
`Type`. `write_skill_error`'s `error_type` parameter defaults to `"General"`
and is never omitted by any of its call sites, so `Type` is de facto always
present, but the schema and validator did not enforce that. This ADR settles
the question by making `Type` required, matching what the implementation
already guarantees.

## Decision

Supersede ADR-056 items 2 and 6, and its enforcement scope, as follows.
Items 1, 3, 4, 5, and 7 are unchanged from ADR-056.

1. (unchanged) All skill scripts MUST wrap output in a standard envelope
   with `Success`, `Data`, `Error`, and `Metadata` fields.
2. **Scripts MUST accept `--output-format`** argument with values `json`,
   `human`, `auto` (default: `auto`). Corrects ADR-056 item 2's
   `-OutputFormat`/`JSON`/`Human`/`Auto` PowerShell-parameter wording.
3. (unchanged) `auto` resolves to `json` when stdout is redirected or in CI;
   `human` when interactive.
4. (unchanged) JSON mode emits only valid JSON to the success output
   stream: no interleaved human text.
5. (unchanged) Human mode writes a compact summary to the host with
   color-coded status.
6. **Error responses use the standard envelope's `Error` field**: a nested
   object with `Message`, `Code` (the ADR-035 exit code), and a **required**
   `Type` (one of `NotFound`, `ApiError`, `AuthError`, `InvalidParams`,
   `RateLimitError`, `Timeout`, `General`, `VerificationFailed`). Corrects
   ADR-056 item 6's flat `ErrorCode` wording, and closes the schema/validator
   gap: `Type` moves from documented-but-unenforced to a required field in
   both `.agents/schemas/skill-output.schema.json` and
   `scripts/validate_skill_output.py`, matching what `write_skill_error`
   already guarantees at the implementation layer.
7. (unchanged) Exit codes continue to follow ADR-035.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Edit ADR-056's Decision section in place | Single source of truth, no new file | Violates this repo's own GDS Way bounded rule once `implemented: true`; the exact mistake Copilot's review caught | Rejected: process violation, not a wording preference |
| Leave `Type` optional in the schema/validator, note it as optional in prose | No enforcement-code change | Understates the real contract: every current producer always sets `Type`, so "optional" would document a permissiveness nothing exercises and a future caller could exploit | Rejected: the implementation already guarantees `Type`; the schema should say so |
| Make `Type` required (chosen) | Schema, validator, and prose now agree with the implementation; `validate_envelope` (when called) fails loud on a missing `Type` instead of passing silently | Existing callers that omit `Type` (none found; `write_skill_error`'s default is always applied) would start failing if the validator is ever wired into a gate | Chosen: closes the schema/validator/prose disagreement with no known breaking caller; see the Negative consequence below on what this does and does not enforce today |

### Trade-offs

Making `Type` required is a stricter validator than ADR-056 originally
documented. The trade-off is accepted because the stricter rule matches
reality (`write_skill_error` cannot construct an envelope without a `Type`)
and because a permissive schema that diverges from the implementation is
exactly the contradiction class issue #5201 exists to eliminate.

## Consequences

### Positive

- ADR-056's supersession chain (ADR-028 -> ADR-056 -> ADR-103) is
  reciprocal and machine-readable; the corpus resolves to exactly one
  accepted record for the skill-output-format contract.
- `Type` moves from documented-required-but-unenforced to actually checked
  by `validate_envelope` whenever that function is called, including on a
  `Success: true` envelope carrying a malformed `Error` object (a case the
  prior nesting under `if Success is False` missed entirely; see
  Implementation Notes).
- The GDS Way bounded rule this repository already documents is followed,
  not just cited.

### Negative

- A third file (`ADR-103` alongside `ADR-056`) is now the canonical
  reference for this contract; a reader who opens only `ADR-056` sees the
  historical, PowerShell-era wording and must follow `superseded-by` to
  reach the current contract. Mitigated by ADR-056's `## Status` section
  stating the supersession explicitly at the top of the file.
- **`validate_envelope` is not wired into any gate.** Verified: no hit for
  `validate_skill_output` in `lefthook.yml`, `.github/workflows/`, or
  `scripts/validation/pre_pr_sequence.py`/`pre_pr.py`. The function is
  exercised only by its own unit tests (`tests/test_skill_output.py`). This
  ADR closes the disagreement between the schema, the validator, and this
  ADR's prose; it does not, by itself, put a live check in front of any real
  skill-script output. Tracked as a fast follow-up: issue #5299.
- **`validate_envelope` and the standalone CLI now reject envelopes that
  previously passed.** This is a real runtime behavior change on the
  consumer/checker side, corrected from an earlier draft of this section
  that called the change "no runtime behavior changes" (Copilot review on
  PR #5283, commit 508917d4b). Concretely, an envelope that previously
  returned `[]` from `validate_envelope` (or exit 0 from the CLI) now
  produces a finding (or exit 1) when: `Error.Type` is missing or empty;
  `Error` is present but is not `null` and not an object (an array,
  string, or number); or `Error.Type` is present but is not a string
  (unhashable values such as a list previously crashed the validator with
  `TypeError` instead of failing closed, also fixed in this round). Any
  caller that fed the validator an envelope in one of these shapes and
  relied on it passing would now see a rejection. No such caller is known:
  `validate_envelope` has no known caller today per the point above, and
  `write_skill_error` cannot construct any of these three shapes, so the
  change has no effect on any envelope this repository's own code
  produces. The distinction that survives is: no *producer*-side behavior
  change (`write_skill_error`'s output is byte-for-byte unchanged), but a
  real *validator*-side behavior change (stricter rejection).

### Neutral

- No producer-side runtime behavior change. `write_skill_error` already
  always sets `Type` to a valid string and never omits `Error` or emits a
  non-dict `Error`; this ADR and its accompanying schema/validator/test
  changes make that existing guarantee enforceable by the validator rather
  than merely documented in prose.

## Implementation Notes

- Output helpers: `scripts/github_core/output.py`. `write_skill_error`'s
  `error_type` allow-list, previously a tuple literal local to the function
  body, is now the module-level `VALID_ERROR_TYPES` constant, so it is
  directly importable and comparable rather than a copy a reader has to
  re-transcribe. Mirrored byte-identically at `.claude/lib/` and
  `src/copilot-cli/lib/` via `scripts/sync_plugin_lib.py` then
  `build/scripts/build_all.py --platform copilot-cli` (per
  `.claude/rules/generated-artifacts.md`'s sync-before-build chain).
- Schema: `.agents/schemas/skill-output.schema.json`:
  - `Error.Type` moved into the object's `required` array.
  - Top-level `required` gained `Data`, alongside the pre-existing
    `Success`/`Metadata`: Decision item 1 (unchanged from ADR-056) already
    said every envelope MUST carry `Data`, but the schema never required
    it. Found by the independent-thinker seat during this ADR's adr-review
    debate; `validate_envelope` gained a matching check in the same
    change so the two contract copies do not newly disagree.
  - `description` corrected from "per ADR-051" (a different, unrelated
    ADR: synthesis-panel frontmatter standard) to cite ADR-056/ADR-103.
- Validator: `scripts/validate_skill_output.py`, `validate_envelope`:
  - Reports a missing or empty `Error.Type` as an error rather than
    skipping the check.
  - The `Error` object's shape (`Message`/`Code`/`Type`) is now validated
    whenever `Error` is a non-null dict, independent of `Success`, matching
    the schema's `oneOf(null, object)` (schema lines 16-39). The original
    fix in this ADR nested that check inside `if Success is False`, which
    let a `Success: true` envelope with a malformed `Error` pass silently;
    caught by the `critic` seat during this ADR's adr-review debate and
    fixed in the same change.
- Tests: `tests/test_skill_output.py` gains:
  - A negative test asserting a missing/empty `Type` fails validation.
  - A negative test asserting a malformed `Error` fails validation even
    when `Success: true` (the case above).
  - The parametrized `test_validates_error_types` now derives its case list
    from `output.py`'s own `VALID_ERROR_TYPES` (not a second hardcoded
    copy), round-trips each produced envelope through `validate_envelope`,
    and checks the type against the schema's own enum, read live from the
    JSON file.
  - `test_error_type_contracts_stay_in_sync` asserts three-way set equality
    across `output.py`'s `VALID_ERROR_TYPES`, `validate_skill_output.py`'s
    `VALID_ERROR_TYPES`, and the schema's enum. This closes the direction
    `test_validates_error_types` cannot: a value added only to the schema
    or the validator never appears in `output.py`'s allow-list, so it would
    never be parametrized into `test_validates_error_types` at all, and
    that test would stay green while the two artifacts silently disagreed.
    Caught by Cursor Bugbot on PR #5283, commit `508917d4b`: "A type added
    to the schema, or to write_skill_error's valid_types without updating
    the parametrize list, leaves the test green, so the three contract
    copies can drift again." Proved discriminating by hand-inserting an
    extra value into a scratch copy of `validate_skill_output.py`'s
    `VALID_ERROR_TYPES` and confirming `test_error_type_contracts_stay_in_sync`
    fails while the rest of the parametrized suite stays green, then
    reverting.
  - `test_non_object_error_is_rejected` and
    `test_non_string_error_type_is_rejected_without_crashing`: Copilot
    review on PR #5283, commit `508917d4b`, found `validate_envelope`'s
    `isinstance(error_field, dict)` gate had no companion branch for a
    non-null value that is also not a dict (an array, string, or number),
    so such a value silently passed; and that `error_type not in
    VALID_ERROR_TYPES` (a frozenset membership test) raises `TypeError`
    for an unhashable `Type` (a list or dict) instead of returning a
    finding. `validate_envelope` now reports both as validation errors.
    Both new tests were proven to discriminate: reverted to the pre-fix
    code in a scratch copy, confirmed the first assertion fails silently
    (the old code appends nothing) and the second raises `TypeError`
    exactly as predicted, then restored the fix.
  - `test_non_object_metadata_is_rejected_without_crashing`: the AI Spec
    Validator workflow (running against PR #5283, commit `6bee062d8`,
    before the fixes above landed) found the same defect class one field
    over: `_validate_metadata_field` called `metadata.get(...)`
    unconditionally, so a schema-invalid non-dict `Metadata` (a string,
    array, or number) crashed with `AttributeError` instead of producing a
    finding. Fixed with the same `isinstance` guard already applied to
    `Error`. Proved discriminating: reverted the guard in a scratch copy,
    confirmed the test failed with the predicted
    `'str' object has no attribute 'get'` traceback, then restored.
  - A fourth Copilot review pass (PR #5283, commit `6639555b8`) found four
    more schema-vs-validator disagreements, all the same "checked
    truthiness/presence, not the declared JSON type" pattern, and one
    "top-level input never type-checked" pattern:
    - `validate_envelope`'s top level assumed `data` was already a dict.
      The CLI passes `json.loads()`'s result straight through, and valid
      JSON such as `null`, a number, a string, or an array reaches it
      unchanged; each of those crashed with `TypeError` or
      `AttributeError` instead of producing a finding. Fixed with an
      `isinstance(data, dict)` guard at the top of `validate_envelope`,
      and the parameter's type annotation changed from `dict` to `object`
      to state honestly that any JSON value can arrive there.
    - The schema's top-level `required` array added `Data` in an earlier
      round but still omitted `Error`, so a `Success: true` envelope with
      no `Error` key at all passed both the schema and the validator
      (`data.get("Error")` cannot distinguish a missing key from an
      explicit `null`). Fixed: `Error` added to the schema's `required`
      array; `validate_envelope` now checks `"Error" not in data`
      separately from `data.get("Error") is None`.
    - `Metadata.Script` and `Metadata.Timestamp` are typed `"string"` in
      the schema; the validator checked only truthiness, so
      `{"Script": 1, "Timestamp": 1}` passed. Fixed with explicit
      `isinstance(..., str)` checks (extracted into
      `_validate_metadata_string_field`, shared by both fields).
    - `Error.Message` (typed `"string"`) and `Error.Code` (typed
      `"integer"`) had the same truthiness/presence-only gap. Fixed with
      explicit type checks (extracted into
      `_validate_error_message_and_code`). The `Code` check excludes
      `bool` explicitly: Python's `bool` subclasses `int`, so
      `isinstance(True, int)` is `True`, but a JSON boolean is not a JSON
      integer; a naive `isinstance(code, int)` check would have accepted
      `Code: true`.
    All four fixes proved discriminating the same way as the earlier
    rounds: each corresponding new test was run against a scratch copy
    with that specific fix reverted and confirmed to fail (crash for the
    top-level and missing-Error cases, silent pass for the type-check
    cases; the bool-vs-int case specifically confirmed against a
    deliberately naive `isinstance(code, int)` check, not just a removed
    check). `tests/test_skill_output.py` grew past the 500-line taste-lint
    gate as a result; the CLI subprocess-integration tests
    (`TestValidateSkillOutputScript`) were split into a new
    `tests/test_skill_output_cli.py`, a natural seam (in-process
    `validate_envelope` calls vs. real subprocess invocations) that
    predated this round's growth. `uv run pytest tests/test_skill_output.py
    tests/test_skill_output_cli.py -q` -> 51 passed (up from 38).

## Related Decisions

- ADR-056: Skill Output Format Standardization (superseded by this ADR)
- ADR-028: PowerShell Output Schema Consistency (superseded by ADR-056)
- ADR-035: Exit Code Standardization
- ADR-042: Python Migration Strategy
- ADR-073: ADR Lifecycle Frontmatter
- Issue #5201
- Issue #5299 (fast follow-up: wire `validate_skill_output.py` into a gate)

## References

- `.claude/skills/adr-generator/references/adr-best-practices.md`, "ADR
  Mutability and Superseding" (GDS Way bounded rule)
- `.agents/critique/issue-5201-adr-028-031-056-debate-log.md`, Round 3 and
  Round 5
