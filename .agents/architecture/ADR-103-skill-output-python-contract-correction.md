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

`status: accepted` rests on a genuine six-seat Phase 4 convergence check
against this ADR's current text, run in Round 5 after a Copilot review
challenged an earlier self-judgment that Rounds 3-4's fixes needed no
fresh debate. Final Round 5 positions: architect Accept; critic Accept,
after two Block-then-fix cycles whose resolutions were independently
re-verified by three later seats; security Accept; independent-thinker
Accept; analyst Block-on-process (unpushed commits, resolved by pushing);
high-level-advisor Disagree-and-Commit (two non-blocking dissents, both
addressed in the same round: a documentation-accuracy fix, and this
Status paragraph plus a scope-corrected code comment for a fourth,
independently-maintained `Error.Type` contract copy the round did not
otherwise touch). Full record: `.agents/critique/ADR-103-debate-log.md`,
"Round 5." The high-level-advisor seat's explicit recommendation, given
five rounds with zero Blocks ever landing on the Decision section itself,
was to merge now and track the remaining bug-hardening scope as follow-up
work rather than run a further round; that recommendation is followed
here.

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
  previously either passed or crashed.** This is a real runtime behavior
  change on the consumer/checker side, corrected from an earlier draft of
  this section that called the change "no runtime behavior changes"
  (Copilot review on PR #5283, commit 508917d4b). An earlier version of
  this section framed every condition below as "previously returned `[]`
  (silently passed), now produces a finding," which the high-level-advisor
  seat's Round 5 convergence check found false for three of them, verified
  by loading `origin/main`'s validator directly and running the shapes:
  the top-level `null`/list cases and the non-object-`Metadata` case
  crashed with `TypeError`/`AttributeError` at `origin/main` rather than
  returning `[]`. Split accurately below.

  **Newly rejects with a finding, where it previously crashed uncaught**
  (`TypeError`/`AttributeError`, still a non-zero exit, but no parseable
  envelope): the top level is not a JSON object (`null`, a number, a
  string, an array); `Metadata` is not an object.

  **Newly rejects with a finding, where it previously silently returned
  `[]` / exit 0**: `Data` or `Error` is missing as a key (distinct from an
  explicit `null`); `Metadata.Script` or `Metadata.Timestamp` is missing,
  empty, or not a string; `Metadata.Version` is present but not a string;
  `Error` is present but is not `null` and not an object; `Error.Type` is
  missing, empty, not a string, or not one of the eight valid values;
  `Error.Message` is missing, empty, or not a string; `Error.Code` is
  missing, not an integer, or a boolean (Python's `bool` subclasses `int`,
  so a naive check would accept `Code: true`).

  Any caller that fed the validator an envelope in one of these shapes and
  relied on it passing (the second category) or on the crash's specific
  exception type (the first) would now see a different failure mode. No
  such caller is known: `validate_envelope`
  has no known caller today per the point above, and (as of this round)
  `write_skill_error` itself cannot construct most of these shapes: it
  guards `error_type` and, since the Round 5 producer-side fix below,
  `message` as well, raising `ValueError` rather than emitting a
  schema-invalid envelope. `Script` and `Timestamp` are always
  producer-supplied non-empty strings (`_detect_script_name` falls back to
  `"unknown"`, never `""`; `Timestamp` comes from
  `datetime.now(UTC).isoformat()`, never empty). The distinction that
  survives is: no *producer*-side behavior change to the envelopes any
  existing caller already constructs successfully (every value
  `write_skill_error` could already produce before Round 5 remains
  producible, byte-for-byte, after it), but a real *validator*-side
  behavior change (stricter rejection) plus one new *producer*-side
  failure mode: `write_skill_error("", ...)` now raises `ValueError`
  instead of emitting a schema-invalid envelope. This is not a
  no-known-caller case the way the validator-side changes are: the
  ADR-103 Round 5 convergence check (independent-thinker seat) found two
  real call sites, `fetch_current_body` and `update_body` in
  `.claude/skills/github/scripts/pr/edit_pr_body.py`, whose
  `raise RuntimeError(result.stderr.strip())` could stringify to `""`
  when `gh` exits non-zero with blank stderr, which their
  `write_skill_error(str(exc), ...)` handlers would have passed straight
  into the new guard, crashing uncaught with the wrong exit code (1
  instead of the intended 3) instead of emitting an error envelope. Both
  call sites were fixed in the same round to guarantee a non-empty
  message before the guard can see them; see Implementation Notes, Round
  5.

### Neutral

- No producer-side runtime behavior change **through Round 4**.
  `write_skill_error` already always set `Type` to a valid string and
  never omitted `Error` or emitted a non-dict `Error`; the schema and
  validator changes through Round 4 made that existing guarantee
  enforceable rather than merely documented. **This no longer holds
  unqualified as of Round 5**: `write_skill_error` gained a `message`
  guard that raises `ValueError` on an empty message, which is a real
  producer-side behavior change for any caller whose message could be
  empty (see the Negative consequence above for what that guard closes
  and what it required fixing at two call sites in `edit_pr_body.py`).
  An earlier draft of this section stated the "no change" claim without
  this qualification; corrected during the ADR-103 Round 5 convergence
  check (independent-thinker seat) after it was found to contradict the
  Negative consequence section in the same document.

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
- **Round 5**, first pass (self-judged mechanical, not separately
  re-debated at the time): the schema's `Error.Message` gained
  `"minLength": 1` (the validator's `if not message` truthiness check
  already rejected an empty string; the schema had not said so
  explicitly). `Metadata.Version` (typed `"string"` in the schema, listed
  in neither Metadata's `required` array nor Round 1-4's checks) gained a
  new `_validate_metadata_version_field` helper: a no-op when the key is
  absent, a finding when present and not a string. A new
  `tests/test_skill_output_schema.py` runs fixture envelopes through the
  schema directly, via the `jsonschema` library (a pre-existing
  `pyproject.toml` core dependency, not newly added), independent of
  `validate_envelope`'s hand-written checks, so a regression that narrows
  the schema without updating the validator (or the reverse) cannot go
  undetected by both at once.
- **Round 5, convergence check** (the fresh Phase 4 six-seat re-review
  this ADR's frontmatter claims to be backed by; see
  `.agents/critique/ADR-103-debate-log.md`, "Round 5"): the critic seat
  BLOCKED the first pass above on two P0s, both real and both fixed in
  this same round, not waved through:
  - The `minLength: 1` addition tightened the schema past what
    `write_skill_error` actually guaranteed: nothing on the producer side
    prevented constructing `Error.Message: ""`. Fixed by adding a
    fail-fast guard to `write_skill_error` (mirroring the existing
    `error_type` guard): `if not message: raise ValueError("message must
    be non-empty")`. Proved discriminating: reverted in a scratch copy,
    confirmed `write_skill_error("", 1, ...)` printed a schema-invalid
    envelope instead of raising, restored, confirmed byte-identical.
  - The identical gap existed in the opposite direction, one field over:
    `Metadata.Script`/`Metadata.Timestamp` were typed `"string"` in the
    schema with no `minLength`, while `validate_envelope`'s truthiness
    check already rejected an empty value for both, and both are always
    non-empty from every producer (`_detect_script_name` falls back to
    `"unknown"`, never `""`; `Timestamp` is `datetime.now(UTC).isoformat()`,
    never empty). Fixed by adding `"minLength": 1` to both schema fields,
    closing the schema-looser-than-validator gap in the reverse polarity
    from the `Error.Message` fix. Proved discriminating the same way.
  - The critic also flagged that this Round 5 section did not exist yet
    (the debate log stopped at Round 4) and that the "Concretely..."
    rejection list in the Negative consequence above had not been updated
    past Round 2's three conditions despite Rounds 3-5 adding roughly
    seven more. Both are fixed in this same edit: this Implementation
    Notes section now documents Round 5 in full, and the Negative
    consequence's rejection list above states the complete current
    surface rather than a stale subset.
  - The architect and security seats independently Accepted the
    pre-critic-fix Round 5 text; architect flagged the same
    producer/schema disagreement the critic later Blocked on, as a
    non-blocking P2, and security flagged it as Info-severity (fail-closed
    direction, no security impact) while independently measuring the
    full rejection surface against `origin/main` across 6,090 envelope
    shapes and finding zero fail-open transitions in either direction.
    Both seats' findings corroborate the critic's; none contradicts it.
  - `uv run pytest tests/test_skill_output.py tests/test_skill_output_cli.py
    tests/test_skill_output_schema.py tests/test_validate_envelope.py -q`
    -> 69 passed (up from 51). `tests/test_skill_output.py` crossed the
    500-line gate again once `test_rejects_empty_message` was added; its
    `TestValidateEnvelope` class (no dependency on the producer-side
    functions) was split into a new `tests/test_validate_envelope.py`, the
    same split pattern as the earlier CLI extraction.
  - The independent-thinker seat's re-check found the same
    producer/schema disagreement class one field further over
    (finding F1): `write_skill_error(message, True)` type-checks under
    mypy (`bool` is-a `int` under PEP 484 nominal subtyping) and passes a
    naive `isinstance(exit_code, int)` check, but the schema's
    `Error.Code: "type": "integer"` (pre-dating ADR-103) and
    `validate_skill_output.py` both reject a boolean `Code`. Fixed with
    the same `isinstance(exit_code, bool) or not isinstance(exit_code,
    int)` guard already used validator-side, added to `write_skill_error`
    next to the `message` guard. Proved discriminating: reverted in a
    scratch copy, confirmed `write_skill_error("test", True)` printed
    `{"Error":{"Code":true,...}}` instead of raising, restored, confirmed
    byte-identical. `uv run pytest tests/test_skill_output.py
    tests/test_skill_output_cli.py tests/test_skill_output_schema.py
    tests/test_validate_envelope.py tests/test_github_pr_diagnostics.py -q`
    -> 130 passed.

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
