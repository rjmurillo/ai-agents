# A governance doc can name a gate that does not exist

`.agents/governance/PROJECT-CONSTRAINTS.md` has an enforcement column. Some
entries in it name a mechanism that is not wired to anything. The rule reads as
enforced, nobody spot-checks it, and violations accumulate while the document
keeps vouching for compliance.

This is worse than having no rule. With no rule, someone notices the gap. With
a phantom rule, everyone downstream relies on an enforcement that never fires.

## Confirmed instance

"MUST NOT create new bash scripts" (ADR-042, Python-first) appears in AGENTS.md,
in `PROJECT-CONSTRAINTS.md` line 39, and in `universal.instructions.md`.
`PROJECT-CONSTRAINTS.md` line 39 claims the enforcement is a "Pre-commit hook
for `.github/scripts/`; code review elsewhere."

Verified 2026-08-05:

- `git grep` on `lefthook.yml` for a bash, shell, or `.sh` policy job: NO job
  exists.
- No script under `scripts/`, `build/`, or `.claude/hooks/` enforces it.
- `scripts/validation/checks_tooling.py` runs shellcheck on workflow `run:`
  blocks. That LINTS shell; it does not PROHIBIT it.
- `git ls-files '*.sh'` returns 16 tracked files.

The rule is enforced by nothing.

## EXISTS and WIRED are different columns

Conflating them is how a dead gate survives every quality tool.

- "I found the function" is EXISTS, not WIRED.
- "A test passes" is EXISTS, not WIRED. If the tests are the only caller,
  mutation testing scores the gate PERFECT while production never invokes it.
- WIRED means traceable to a lefthook job name, a live workflow step, or a hook
  that actually fires. Only a literal `if: false` counts as disabled.

Confirmed dead-gate instance: `scripts/ci/count_ratchet.py:206 baseline_health`
with `MAX_BASELINE_SLACK = 5` at line 186 had 10+ passing assertions across two
test files and was never called by `run()`. Fixed in PR #4644 with a
remove-the-call mutant as proof.

## How to audit for more

Read the enforcement column of `PROJECT-CONSTRAINTS.md` and check each claimed
mechanism against `lefthook.yml` job names and live workflow steps. Record
EXISTS and WIRED as SEPARATE columns; a single "enforced" boolean hides the
common case where the code is present but unreachable.

Any script under `scripts/ci/` needs THREE registrations or
`tests/ci/test_ci_scripts_are_wired.py` fails: a `lefthook.yml` job, a row in
the RATCHETS table in `scripts/validation/checks_ratchet.py`, and a live
workflow step. That test is the closest thing the repository has to a
wired-ness check, and it covers only `scripts/ci/`.

## Related

Doc-claim audits over these files reported a large "unverifiable" bucket. That
bucket hides three different defects demanding opposite responses:
unfalsifiable-by-construction is a DOC defect, harness-gap is a TOOL defect,
out-of-scope is neither. Splitting them inverted the conclusion: the docs were
largely fine and the audit was the weak component.
