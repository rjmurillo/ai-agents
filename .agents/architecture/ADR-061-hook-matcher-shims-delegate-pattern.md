# ADR-061: Hook Matcher Shims Delegate to Canonical Body

## Status

Withdrawn (2026-05-27, before acceptance, based on 6-agent debate verdict)

## Date

2026-05-27 (drafted); 2026-05-27 (withdrawn)

## Withdrawal Rationale

This ADR was withdrawn before acceptance after a 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) revealed that the urgency framing was unsupported by evidence on `main`:

1. **Zero drift on `main` today.** Direct `diff` between multi-matcher shims of the same canonical hook produces no output. The drift evidence cited in the Context section is entirely from the unmerged PR 1763 branch, where partial regeneration during PR development produced divergent matcher shims. That is a workflow failure, not a structural defect of the inline-body design.
2. **Alternative B is a 2-hour fix.** Deterministic full-tree regeneration (`generate_hooks.py` always regenerates every matcher shim from canonical on every run) plus a CI step (`git diff --exit-code src/copilot-cli/hooks/` after generation) eliminates the drift root cause at one-tenth the cost. No spec amendment. No `_impl/` import surface. No additional attack surface.
3. **Delegate-shim reintroduces drift one layer deeper.** The analyst surfaced that after the refactor, a direct edit to `_impl/invoke_X.py` would pass all three parity rules proposed in this ADR while drifting from the canonical `.claude/hooks/<Event>/<hook>.py`. A fourth rule would be required, which is itself the same shape of drift the ADR claims to eliminate, just one layer down.
4. **Premature abstraction.** On `main`, only three hooks have two matchers each. The ADR projected toward "all hooks multi-matcher" without growth evidence. Per `.claude/rules/philosophy-of-software-design.md`, this is a speculative-generality smell.
5. **Opportunity cost.** Holding PR 1763 for a multi-day structural refactor while alternative B unblocks it in 2 hours has negative ROI against the projected (not observed) failure rate.

This ADR is preserved (not deleted) as institutional knowledge. The debate log at `.agents/critique/ADR-061-debate-log.md` records the full positions. The follow-up issue (TBD link) tracks when the structural refactor should be revisited: when multi-matcher hook count exceeds 8, OR when the alternative B CI drift gate fires three or more times in a quarter (signal that the procedural fix is failing).

The two valid criticisms that survive into the alternative-B implementation:

- The drift class of bug is real, even if not currently observable on `main`. The CI gate must catch it the next time partial regeneration is attempted.
- The generator must be made deterministic on regeneration (regenerate all shims from canonical, never reuse existing shim contents).

---

*Original "Proposed" content below is retained verbatim for institutional record.*

---

## Original Status (superseded)

Proposed (amends REQ-003-007 step 5; not a successor to a prior ADR)

## Original Date

2026-05-27

## Context

REQ-003-007 step 5 (`.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:281-305`) mandates that each `(hook_event, matcher_pattern)` pair in `.claude/settings.json` produce a per-matcher shim file under `src/copilot-cli/hooks/<event>/`. The current generator (`build/scripts/generate_hooks.py::inject_shim`, line 474) implements this by wrapping the canonical hook body in `def _original_main(stdin_bytes)`, prepending a ~140-line dispatch header (`_shim_classify`, `_shim_normalize_args`, `_shim_glob_match`, `_shim_should_fire`, `_shim_dispatch`), and writing one self-contained file per matcher, named `<hook>__<MatcherTokens>_<hash>.py`.

The design produces correct shims on first generation. It does not stay correct across edits.

### Drift evidence (PR 1763, observed 2026-05-26)

PR 1763 (`feature/1703-lifecycle-hook-infrastructure`) registers `invoke_false_completion_gate` against four matchers: `Bash`, `Bash(gh pr create*)`, `Bash(gh pr merge*)`, `Bash(git commit*)(git ci*)`. The generator produced four shim files. `diff` between them shows divergent wrapped-body content:

| File pair | Divergence |
|-----------|------------|
| `__Bash_f620ca.py` vs `__Bash_gh_pr_create_be117f.py` | Different regex set for test-result detection (one excludes `FAILED`/`failed` signals; the other includes them) |
| Same pair | One has midnight-spanning session-log fallback; the other does not |
| Same pair | One imports `from datetime import UTC, datetime`; the other adds `timedelta` |

Same hook, four files, divergent gate logic. Runtime behavior depends on which matcher fires. The canonical `.claude/hooks/PreToolUse/invoke_false_completion_gate.py` was edited; some shims got regenerated, some did not.

### Cost evidence (current main, multi-matcher hooks)

| Hook | Canonical size | Shim count | Total bytes | Amplification |
|------|----------------|------------|-------------|---------------|
| `invoke_false_completion_gate` (PR 1763) | 27 KB | 4 | 133 KB | 4.9x |
| `invoke_branch_protection_guard` | 3 KB | 3 | 26 KB | 7.9x |
| `invoke_session_log_guard` | 7 KB | 3 | 38 KB | 5.5x |

On main, only multi-matcher hooks (4 today) carry the amplification. PR 1763 and future lifecycle-hook PRs increase it.

### Rule violations

The inline-body design violates:

- `.claude/rules/pragmatic-programmer.md` DRY at the knowledge level: business rules duplicated, not text alone.
- `.claude/rules/canonical-source-mirror.md`: shims claim to mirror the canonical hook but the mirror is hand-regenerated per file and drifts.
- `.claude/rules/philosophy-of-software-design.md` deep modules: each shim is shallow; it exposes the whole wrapped body to the install tree.

## Decision

Amend REQ-003-007 step 5 so the generator emits **delegate shims**, not inline-body shims.

A delegate shim file contains only:

- Idempotency sentinels (`# AUTO-GENERATED MATCHER SHIM (REQ-003-007)` at top; `# END MATCHER SHIM` at end).
- Per-matcher metadata: `_MATCHER` literal and a comment naming the matcher.
- A stdin cap (`_SHIM_MAX_STDIN_BYTES`), applied before delegate.
- An `import` of `shim_dispatch` from a shared runtime module.
- An `import` of `main` (or `_original_main`) from a sibling canonical-body module.
- One call: `sys.exit(shim_dispatch(_MATCHER, _original_main, stdin_bytes))`.

Target output layout per event directory `src/copilot-cli/hooks/<event>/`:

```text
_impl/
  __init__.py
  _shim_runtime.py           # shared classify/normalize/glob_match/should_fire/dispatch (one per event dir)
  invoke_<hook>.py           # canonical body (one per source hook)
invoke_<hook>__<MatcherTokens>_<hash>.py   # thin delegate shim (one per matcher)
```

Single source of truth per concern: hook body in `_impl/invoke_<hook>.py`, dispatch logic in `_impl/_shim_runtime.py`, matcher metadata in the thin shim.

A source edit to `.claude/hooks/<Event>/invoke_X.py` regenerates exactly one file (`_impl/invoke_X.py`). All matcher shims for that hook continue to delegate to it. Drift between matchers of the same hook becomes structurally impossible.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: per-matcher inline-body shim, written by `build/scripts/generate_hooks.py::inject_shim` (line 474). Each shim is a self-contained Python module.
- **When introduced**: REQ-003 M5-T2 (matcher shim injector), captured in `.agents/plans/active/req-003-multi-tool-artifact-build.md:79`. The plan explicitly anticipates this alternative at M7-T3.
- **Original author and context**: REQ-003-007 author chose inline-body to keep shim files self-contained, removing any runtime import dependency in the install tree. Per the plan, the alternative was captured as a fallback.

### Historical Rationale

- **Why was it built this way?** Shim must run before any other code in the wrapped script, and Copilot CLI launches hooks as standalone files. Inline-body made the shim a single file with no import surface.
- **What alternatives were considered?** "One-body-many-matchers" listed in `req-003-multi-tool-artifact-build.md:114` (M7-T3) as the fallback. Captured but not implemented.
- **What constraints drove the design?** (a) shim must own stdin-buffering before user code reads it; (b) any cross-file import must work at Copilot CLI's runtime cwd.

### Why Change Now

- **Has the original problem changed?** Constraint (a) still holds (delegate shim still buffers stdin first). Constraint (b) is testable.
- **Is there a better solution now?** Install-parity (PR 2095, merged 2026-05-26) demonstrates that the project now accepts and enforces "canonical + thin install copies" as the design idiom. Delegate-shim aligns hook generation with that pattern.
- **What are the risks of change?** See Impact and Implementation Phasing below; runtime import resolution is the binary blocker.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **A. Delegate shim** (this ADR) | Eliminates body duplication structurally. Edits propagate atomically. Aligns with install-parity idiom. Per-shim drops to ~12 lines. | Requires `_impl/` subdir + import resolution. Spec text change. Multi-day refactor. | **Chosen.** Structural fix, not procedural. |
| **B. Regenerate-all-on-any-edit + drift CI gate** | Keeps existing layout. No spec change. Hours of work. | Duplication remains. Future drift still possible on partial regeneration. Wastes ~25 KB per multi-matcher hook. | Rejected: addresses symptom, not cause. |
| **C. One-body-many-matchers** | Single shim file per hook with internal matcher dispatch. No `_impl/` subdir. | Couples matcher dispatch to a runtime env-passing contract (`$CLAUDE_MATCHER` or argv) that Copilot CLI does not currently guarantee. Settings.json schema implications. | Rejected: relies on a contract not currently guaranteed by Copilot CLI; delegate-shim keeps file-per-matcher registration intact. |
| **D. Accept drift, document only** | Zero implementation cost. | Production behavior diverges per matcher. Security gate logic inconsistent. Violates DRY, canonical-source-mirror, deep-modules rules. | Rejected: silent gate-bypass class of bug. |

### Trade-offs

The delegate shim trades a single self-contained file for a three-file layout (matcher shim + canonical body + shared runtime). The trade buys: (1) elimination of body duplication across matchers, (2) atomic propagation of source edits, (3) ~88% byte reduction across the shim tree once all hooks are multi-matcher.

The cost is a runtime import surface. The shim cannot work without `_impl/` siblings present. The generator emits both together; users do not hand-edit shims. Hot-reload, lazy import, and runtime matcher addition are explicitly out of scope (YAGNI). Revisit if matcher count exceeds 20 per event.

## Consequences

### Positive

- Drift between matchers of the same hook becomes structurally impossible.
- Per-shim file shrinks from ~30 KB to ~700 bytes.
- Source edits to `.claude/hooks/<Event>/<hook>.py` regenerate exactly one `_impl/<hook>.py`, not N matcher copies.
- Aligns hook generation with install-parity pattern (canonical + thin copies).

### Negative

- Spec amendment to REQ-003-007 step 5 required. Governance load: ADR + maintainer review.
- Generator refactor (`build/scripts/generate_hooks.py`) is non-trivial: shim builder, body wrapper, audit log entries, idempotency strip/inject all change shape.
- Tests in `tests/build_scripts/test_generate_hooks.py` need rewrite for new shim format. Snapshot fixtures change.
- Adds `_impl/` subdir to each event directory. Anyone inspecting the install tree sees a new layout.
- **Debuggability**: tracebacks gain two frames (`shim.py` → `_shim_runtime.py:dispatch` → `_impl/invoke_X.py:main`). `_shim_runtime` becomes a hot path for every hook failure investigation. **Mitigation**: keep `_shim_runtime.py` under 100 lines and exception-transparent (no `except` blocks that swallow or rewrap).

### Neutral

- Total install-tree size shrinks for multi-matcher hooks, unchanged for single-matcher hooks.
- Idempotency sentinels (`# AUTO-GENERATED MATCHER SHIM (REQ-003-007)`, `# END MATCHER SHIM`) preserved unchanged.
- Crash policy (exit 2 on shim error, exit 0 on no-match, propagate wrapped exit on match) preserved unchanged.

## Reversibility

- **Rollback path**: generator retains a `--legacy-inline-body` flag for one release window. Install-parity validator detects drift in either direction (inline vs delegate), so a rollback is mechanically safe.
- **Lock-in**: none. Generator code, shim format, and runtime module are all owned by this repo.
- **Data migration**: not applicable; install-tree files are regenerated artifacts.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md` step 5 | Direct | Replace inline-body language with delegate-shim language; preserve sentinel and crash-policy clauses verbatim | Low |
| `build/scripts/generate_hooks.py::inject_shim` | Direct | Emit thin shim + canonical body file + shared runtime module instead of inline-body shim | High (load-bearing) |
| `build/scripts/generate_hooks.py::strip_shim` | Direct | Adjust idempotency stripping to new shim shape | Medium |
| `tests/build_scripts/test_generate_hooks.py` | Direct | Update snapshot fixtures, parametrized tests, property tests | High (broad rewrite) |
| `src/copilot-cli/hooks/<event>/` install trees | Direct | Regenerate all shims; old `__matcher_hash.py` files with inline bodies removed; new `_impl/` subdirs added | High (visible diff) |
| `build/scripts/build_all.py --check` | Indirect | Drift detection must understand new layout (one body file + many thin shims) | Medium |
| Copilot CLI hook runtime (dev, user-install, system-install modes) | Indirect | Must launch shim with `sys.path` allowing `from _impl import ...` under all three install modes | High (BLOCKER if any mode fails) |
| `pytest.ini` / pytest discovery configuration | Direct | Add `_impl/` to `norecursedirs` or rely on leading-underscore convention to prevent test collection from invoking canonical bodies as tests | Medium |
| `build/scripts/validate_install_parity.py` | Direct | Extend parity rules: (a) every thin shim has sibling `_impl/invoke_X.py`; (b) no two thin shims contain divergent body bytes; (c) `_shim_runtime.py` exists exactly once per event dir | Medium |

## Implementation Phasing

1. **Spike Copilot CLI runtime (BLOCKER)**: install a delegate-shim test hook into a clean Copilot CLI repo under all three install modes (dev, user-install, system-install). Trigger the hook. Confirm `from _impl._shim_runtime import shim_dispatch` and `from _impl.invoke_X import _original_main` resolve under every mode. Validate: working directory at hook launch, hook invocation form (`python shim.py` vs `python -m`), install copy fidelity (does the installer preserve subdirectories or flatten them). If any mode fails, this ADR is blocked; reopen alternative-design discussion.
2. **Amend REQ-003-007 spec text** to mandate delegate-shim layout. Preserve sentinel and crash-policy clauses verbatim.
3. **Rewrite generator** (`_build_shim`, `inject_shim`, `strip_shim`, `_wrap_body_in_function` retired in favor of new `_emit_canonical_body`, `_emit_delegate_shim`, `_emit_shim_runtime`).
4. **Rewrite tests**. Snapshot fixtures regenerated. Property tests target the new format. Add: drift detection test that mutates `_impl/invoke_X.py` and confirms all shim files still execute the new body via delegation.
5. **Regenerate** `src/copilot-cli/hooks/` install trees. Delete pre-refactor shim files. Add `_impl/` subdirs.
6. **Extend** `build/scripts/validate_install_parity.py` with the three rules listed in Impact above.
7. **Configure pytest** to exclude `_impl/` from collection.
8. **Open PR** with title `refactor(REQ-003-007): delegate-shim hook generator`. Link this ADR.

Exit codes per ADR-035: 0 success, 1 logic, 2 config.

## Confirmation Mechanism

Compliance verified by the extended `validate_install_parity.py`:

- **Rule 1**: every thin shim (`invoke_X__*.py` at the event-dir root) has a sibling `_impl/invoke_X.py`.
- **Rule 2**: no two thin shims for the same source hook contain divergent body bytes (the body lives in `_impl/`; thin shims only differ in matcher metadata).
- **Rule 3**: `_shim_runtime.py` exists exactly once per event directory under `_impl/`.

Pre-push hook and CI gate both invoke the validator. Pre-PR script (`scripts/validation/pre_pr.py`) includes it as a non-quick step.

## Security Considerations

The `_impl/` subdirectory is an additional import surface inside the install tree. A maliciously-crafted `_shim_runtime.py` placed in the install tree by a third party would be loaded by every shim in that event directory. The threat model is unchanged from today's inline-body shims: the install tree is write-protected post-install (filesystem permissions, package signing where available). The same trust boundary that protects the existing inline shims protects the `_impl/` modules. No new attack surface; the existing one is now organized differently.

## Related Decisions

- [ADR-035: Exit Code Standardization](ADR-035-exit-code-standardization.md). Preserves crash-policy exit codes.
- [ADR-042: Python Migration Strategy](ADR-042-python-migration-strategy.md). Generator and shim runtime remain Python.
- [ADR-006: Thin Workflows, Testable Modules](ADR-006-thin-workflows-testable-modules.md). Delegate shim is the thin-workflow analog at the hook layer.
- [ADR-053: ADR Exception Criteria](ADR-053-adr-exception-criteria.md). This ADR follows standard (non-exception) workflow.

## References

- `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md` step 5 (REQ-003-007). Source of the inline-body mandate.
- `.agents/plans/active/req-003-multi-tool-artifact-build.md:79,114`. M5-T2 implementation task; M7-T3 captures one-body-many-matchers as the alternative.
- `build/scripts/generate_hooks.py`. Current generator implementation.
- `.claude/rules/pragmatic-programmer.md`. DRY at the knowledge level.
- `.claude/rules/canonical-source-mirror.md`. Mirror claims must match canonical.
- `.claude/rules/philosophy-of-software-design.md`. Deep modules.
- `build/scripts/validate_install_parity.py`. Existing canonical/install parity validator (PR 2095).
- PR 1763 (`feature/1703-lifecycle-hook-infrastructure`). Drift evidence source.
- PR 2095 (install-parity validator). Demonstrates canonical-plus-thin pattern.

---

*ADR Version: 1.0*
*Created: 2026-05-27*
*Author: Richard Murillo (drafted via session 1837)*
*Architect review: session 1837 (REVISE_BEFORE_SAVE → R1-R7 applied)*
*GitHub Issue: (to be linked when filed)*
