# Agent readiness handoff

## Current Resume (2026-11-24 UTC, after D-SDK1 and D-SDK2)

Doc accuracy now passes on this branch with zero blocking findings.
It reported 524 blocking findings before the repairs below.

The owner recorded two more decisions on 2026-11-23:

- D-SDK1 A: clear doc accuracy by repairing documents, not by building the ADR-124 bundle.
  The decision covers the class of example-heavy docs, not a fixed list.
  Twenty-five source docs carry the documented `external-sdk` marker in total.
  Twenty came first (`ffc7e470a`), and five followed the revert below.
  One template example no longer calls an undeclared helper.
  Cost: a marker silences `unresolved_symbol` for its whole file.
  It also hides future drift of this repository's own symbols in those docs.
  Exit: remove the markers when ADR-124 proof lands (issue #7501).
- D-SDK2: the owner approved the code-quality score regressions again.
  The set is 137 rows: the 136 approved at `6c809ace` plus one test coupling row.
  The approval binds a commit pair, so each new head needs a fresh comment on #7512.
  Issue #7525 tracks replacing that per-commit approval.

Commit `e7a70a4ce` reverted `0cdd2e8b6`.
That commit cleared C# types through a hand-kept `using` allowlist.
No decision covered that list, and Proposed ADR-124 rejects one.
The revert left 23 `System` findings in five docs, now marked as well.

Commit `f8eb91a96` split three files that crossed 500 lines.
The taste count ratchet then passed.

Review round 1 ran at `e9c2fdca1` and round 2 at `6c2ddab78`.
No axis returned CRITICAL_FAIL. All six security slices returned PASS in round 2.
Round 2 left a stale doc line, a test that read the shell's plugin root, and a mypy regression.
The ledgers live in the review scratch directory and are not committed.

ADR-124 stays Proposed. Round 2 inputs from review went to issue #7501.
`doc_accuracy.py` grew from 2,592 to 4,423 lines on this branch.
Review asks to move its binding lexer into a sibling module after merge.

D11's duplicate-repair worktree remains preserved until merge.
Its path is `/home/richard/worktrees/ai-agents4/fix-readiness-d11-dupli-a60624f87ff01c00`.
Its branch is `fix/readiness-d11-duplicates`.
The owner authorized removing that worktree and branch after merge.

Earlier resume snapshots are preserved in [the readiness history](2026-11-09-readiness-history.md).

## Verified Integration History

These historical receipts do not prove acceptance of the final integrated tip.
Earlier detailed prose remains in the scratch handoff copy named above.

### D11 and D15

The parent merged `0735d2bb4` as `6f4358628` on 2026-11-20 UTC.
That checkpoint includes `87a8f07d8`, `89cabae7c`, and `549025189`.
The scalar helper ships in authoring, not knowledge.
Parent regression passed 6,664 tests with one CI-only PowerShell-presence skip.
Real PowerShell parser tests used the portable runtime.
Generation parity, Ruff, whitespace, and conflict-marker checks passed.
Committed IO scanning found zero violations across 252 files.
Duplication found one new council/sol-loop block across 3,864 files.
Thirty stale baseline entries remain unchanged until no new clones remain.
Both original Opus workers stopped with provider HTTP 429 errors.
D15 option A permits alternate providers; isolated Codex workers own D13 and D14.

### Main and Four-Pack Integration

The parent integrated main `b12beeae6` as `22cf17f40` on 2026-11-20.
The instrument conflict preserves citation reverse-pass and the shared drift helper.
Generation places the scalar helper and its mirrors in authoring.
The approved pack budget remains 399 files, not main's 400.
At that integration, authoring/delivery/knowledge/quality contain 188/298/256/163 tracked files.
Each library contains 55 identical files; skill ownership remains unique.
Changed-area regression passed 8,141 tests with two skips.
A broad serial attempt timed out after collecting 20,426 tests.
That timeout is not a passing full-suite result.
Conflict markers, Ruff, instrument CLI, generation parity, and thirteen Hermes smokes passed.
Receipts use `readiness-b12-main-*` and `readiness-22cf-main-pinned-smoke.log` in scratch.

D10 tip `726bb6227` merged as `82085ac4d` on 2026-11-19.
Richard selected the fourth authoring pack in its child thread.
ADR-115 debate seven records four Accept and two Disagree-and-Commit votes.
The debate records no open P0/P1 findings; ADR status remains proposed.
Independent comparison preserved all 678 skill files without duplicate ownership.
All 552 selected integration tests passed; thirteen pinned Hermes smokes passed.
The first smoke setup failed Python discovery; no product test ran.
The passing fixture verified Hermes `63d0b94120027d487c9a5235b9ec64b696af1b26`.
The parent's global Hermes checkout was not modified.
Debate seven predates D11/D13 inventory and does not establish final pack counts.

### D12 Documentation and D14 Boundary

Corrected D12 tip `9a761dd84` merged as `621173ebb` on 2026-11-19.
Independent .NET checks first found Linux case-sibling and root-base containment defects.
The corrected immutable example passed all twenty parent checks.
Those checks cover traversal, siblings, equality, absolute paths, empty input, and NUL.
The example states its lexical-only guarantee and link-swap race limitation.
Windows behavior remains untested on a Windows runtime.
All 629 selected regression tests passed; generation and whitespace checks passed.
Markdownlint checked four shipped documents; configured exclusions skipped named history documents.
Receipts remain under `d12-parent-corrected-path-probe/` in scratch.
The integrated scan previously reported 907 high findings.
Full-corpus documentation acceptance remains unproved.

### D9 Encoding and Earlier Integration

D9 encoding tip `0f31710a2` was cherry-picked as `7cfb39b24`.
Commit `cc8798228` repaired seventeen remaining fixture writes.
All 803 selected tests passed; Ruff passed across 23 files.
The old encoding stash remains preserved; do not blindly apply it.
D9/D10 integration `1f4d972a6` preserves D9 tip `4ad3557b1`.
Its staged safety tree is `66fff7a1e021c3eab8119bbb7b8430a5dcbb171a`.
Safety ref `refs/readiness-safety/staged-20261119` and scratch patches remain preserved.
D10 history retains `07a69ff6e`, `9693b7932`, `f2373f54d`, and `c87c838dd`.
Earlier independent D9 regression passed 431 tests and eight member-resolution probes.
Combined integration regression passed 662 tests after twelve reproduced reference-test failures.
The helpers now normalize string inputs into path components.

## Resume Evidence (2026-11-18)

The D7 scanner repair is committed at `5c5e843cbc41fcd6ca1f8596337037ac17d1cab1` (2026-11-18).
Bare calls and known-method parameter checks remain visible.
Member names cannot hide unresolved constructors with identical names.
Cross-fence declarations resolve only within the same language.
On 2026-11-18, scanner regression passed all 277 tests.
On 2026-11-18, closure and surface-parity regression passed all 232 tests.
On 2026-11-18, Ruff, mypy, formatting, and committed build parity passed.
On 2026-11-18, taste examined both repair files without findings.
On 2026-11-18, command-injection scanning examined both repair files without findings.
On 2026-11-18, duplication passed across 3614 Python files.
The duplicate baseline remains unchanged during this resume.
On 2026-11-18, full scanning examined 6794 documents and extracted 30812 claims.
It reported 791 high findings and exited ten.
Those findings remain visible and lack complete triage.

On 2026-11-18, preflight passed 115 gates before the D7 commit.
Its generated-staleness failure cleared after the commit.
The merge-tree ratchet still reports conflicts against current upstream main.
Its base is `ae5acffcb3b9f9e00e4898d5bb0b0f9681a757d5` (2026-11-18).
On 2026-11-18, read-only merge analysis identified nine conflicting paths.
They comprise four authored paths and five generated copies.
Authored conflicts affect both memory-placement specifications, `close_pr.py`, and workflow-coalescing tests.
The operator authorized current-main integration and one additional conflict-resolution agent.
The fourteen final-review slots remain reserved.
No open PR exists for this branch, verified on 2026-11-18.
No push, review marker, or external write occurred during this resume.
The existing fourteen final-review slots remain unused.

## D8 Local Integration Blocker (2026-11-18)

The fresh fetch resolved main to `ae5acffcb3b9f9e00e4898d5bb0b0f9681a757d5` (2026-11-18).
The merge remains uncommitted, with all nine conflict paths resolved and staged.
Both specifications retain the repository-local mirror inventory and upstream updates.
The PR command retains shared bootstrap behavior and upstream comment deduplication.
All five PR command mirrors match their canonical source byte-for-byte.
Workflow assertions now cover ten defaults, preserving both branches' additions.
On 2026-11-18, the focused integration suite passed all 418 tests.
Ruff and formatting passed for both authored Python conflict paths.
The configured Markdown command examined zero files because these specifications are ignored.
Conflict-marker and whitespace checks passed.
Regeneration failed: Hermes delivery contains 404 files against its unchanged 399-file budget.
The runtime cap is 400 files, so raising the configured budget cannot resolve this.
The merged inventory retains five branch helper files absent from upstream.
No helper, limit, exclusion, baseline, or security contract changed to clear this blocker.
Evidence lives under `.project-toolkit/scratch/`:

- `readiness-d8-integration-build.log`: failed regeneration.
- `readiness-d8-integration-tests.log`: focused regression.
- `readiness-d8-integration-evidence.json`: inventories, helper paths, and PR parity.
- `readiness-d8-integration-markers.json`: conflict verification.
- `readiness-d8-integration-ruff.log`: Python lint.
- `readiness-d8-integration-python-lint.log`: Python formatting.
- `readiness-d8-integration-markdown-lint.log`: zero-file Markdown result.

Owner decision is required before packing or helper-layout changes.
No commit, push, PR, review marker, or additional agent was created.
Committed build verification and full acceptance remain unproved.
All fourteen final-review slots remain reserved.

## Status

The user authorized repository-side repairs, commits, PR creation, and merge.
The existing privacy contract remains unchanged.
Dependency checker repairs are committed and pass focused validation.
Final alert, setup, and duplication diagnostic repairs are committed.
Current main merged cleanly before final validation.
Integrated preflight failed on newly merged upstream duplication.
The original duplication failure is repaired without changing scanner exclusions.
The operator approved bounded upstream repairs and a fresh review budget.
The implementer returned without edits because its assignment exceeded five files.
The parent reproduced 23 stale baseline entries before source repair.
The operator approved evidence-backed, shrink-only pruning after duplication growth reaches zero.
Approved source extractions are committed with their generated projections.
The operator approved the six newly exposed consumers, and their repairs are implemented.
On 2026-11-10, their focused checks passed all 318 tests.
The operator approved the remaining bootstrap family, and its repairs are implemented.
Authorized shrink-only pruning removed stale baseline entries after zero growth.
The unchanged whole-corpus duplication gate now passes.
The initial combined suite exposed a Snap PowerShell runtime failure.
The operator authorized an isolated official portable PowerShell runtime.
Its published digest matches, and the unchanged Copilot launcher test passes.
On 2026-11-10, the combined repair suite passed all 3413 tests.
The previous push failed because required security review proof was absent.
No successful push or PR creation has been observed.
The latest main integration exposed three additional preflight failures.
The operator authorized bounded integration repairs and one replacement reviewer.
Both portability gates and whole-corpus duplication now pass focused rechecks.
Neither baseline changed during these integration repairs.
D2 fixtures and D3 test extractions pass focused validation.
The documentation scanner repairs pass their complete regression suite.
The interrupted full documentation assessment provides no current acceptance.

## State Record

- **Remote**: rjmurillo/ai-agents
- **Branch**: fix/agent-readiness-signals
- **Worktree**: ~/src/GitHub/rjmurillo/ai-agents4
- **Source checkpoint**: 5c5e843cbc41fcd6ca1f8596337037ac17d1cab1 (2026-11-18T22:30:13-08:00)
- **Timestamp**: 2026-11-19T06:30:13Z
- **Objective**: Ship repository-side readiness repairs without adding client telemetry.
- **Non-goals**: Hosted infrastructure, package releases, and security configuration changes.
- **Risk tier**: shared-repository
- **Acceptance**: New checks detect violations. Under D29, the full-corpus findings stay recorded in #7501.
- **Phase**: D7 repair committed; full scanning reports unresolved findings.
- **Next action**: Complete authorized main integration and classify full-scan residue.
- **Validation run**: On 2026-11-18, scanner regression passed all 277 tests.
- **Residual risks**: Upstream conflicts block preflight; full documentation and final reviews lack acceptance.
- **Escalation owner**: Repository owner.

## Decisions Made

- Preserve existing host CLI, model, and user-invoked outbound behavior.
  - Provenance: The user required preserving the existing README privacy contract.
- Do not add installed-client telemetry, hosted services, or remote flags.
  - Provenance: The user limited work to repository-side readiness repairs.
- Use integrity-locked jscpd without an automatic npx fallback.
  - Provenance: Security review required avoiding unlocked downloads and lifecycle execution.
- Keep duplication ceilings and narrowly evidenced dependency exemptions.
  - Provenance: Existing validator contracts prohibit baseline growth and blanket suppressions.
- Reuse existing GitHub issue alerting without ingesting workflow artifacts.
  - Provenance: Existing alert helpers support the approved repository-side failure routing.
- Preserve upstream Ruff security checks and Bandit removal.
  - Provenance: The committed main merge retained the upstream security-tooling change.
- Compare Python constraints only when declaration markers overlap.
  - Provenance: Round-three QA reproduced false conflicts from mutually exclusive Windows markers.
- Reject unsupported marker predicates explicitly rather than guessing compatibility.
  - Provenance: The repaired checker documents configuration exit two for unsupported predicates.
- Use existing locked packaging interval APIs without changing package versions.
  - Provenance: Locked packaging provides exact prerelease intervals; regenerated metadata preserves every package version.
- Admit alert publishing only after canonical eligibility classification.
  - Provenance: Independent QA reproduced ignored completions cancelling eligible alerts.
- Include locked Node tools in contributor setup without lifecycle scripts.
  - Provenance: Independent DevOps review found fresh setup omitted the required scanner.
- Preserve duplication failures when optional diagnostics contain malformed reports.
  - Provenance: QA found malformed auxiliary reports replaced controlled failures with tracebacks.
- Update coalescing tests to include the branch's three added workflows.
  - Provenance: The branch changes defaults; unchanged tests still expected six names.
- Repair the named upstream duplicate blocks and their necessary supporting code.
  - Provenance: The operator selected the recommended bounded upstream repair option.
- Prune only proven stale allowances after duplication growth reaches zero.
  - Provenance: The operator selected the recommended shrink-only pruning option.
- Preserve the existing 14-process independent review budget.
  - Provenance: The baseline approval explicitly preserved the existing review allocation.
- Repair the six newly exposed upstream consumers.
  - Provenance: The operator selected D1's recommended six-consumer repair option.
- Complete the remaining enumerated GitHub bootstrap family.
  - Provenance: The operator selected D2's recommended complete-family option.
- Use an isolated official PowerShell runtime for validation.
  - Provenance: The operator selected the isolated-runtime option after Snap failed.
- Clear doc accuracy with the documented external-sdk marker on example docs.
  - Provenance: The owner chose D-SDK1 option A on 2026-11-23.
- Drop the hand-kept C# using allowlist from the scanner.
  - Provenance: Review found no decision covering it, and ADR-124 rejects one.

## Latest Validation Evidence

- 2026-11-10: All 220 focused dependency checker tests passed.
- 2026-11-10: Ruff checks and formatting passed for repaired Python files.
- 2026-11-10: Mypy passed for the three repaired implementation modules.
- 2026-11-10: Dependency usage examined 30 declarations across three manifests without findings.
- 2026-11-10: Drift examined three Python manifests and six npm manifests without findings.
- 2026-11-10: Root lock validation passed after metadata-only regeneration.
- 2026-11-10: Validation authority passed for 14 local targets and one generated lock.
- 2026-11-10: Before main integration, final repair and coalescing tests passed all 178 cases.
- 2026-11-10: Alert admission stress passed 660 cases across 30 fresh processes.
- 2026-11-10: Stress validates local admission and wiring, not GitHub scheduler execution.
- 2026-11-10: Main integration at 39377f00ceb269b76b4330744404c8c01224e515 required no conflict edits.
- 2026-11-10: Historical preflight at 8f573a920 passed 119 gates with two accepted skips.
- 2026-11-10: Historical regression at 8f573a920 passed 5351 tests with 27 explained skips.

Historical results do not certify the repaired tip.
The operator approved repairs and a fresh review cycle after QA findings.
The renewed delegation budget allows one implementation and 14 independent review processes.
Earlier review results cannot authorize the repaired code's security marker.

## Execution Receipts

Ignored scratch contains repair risk, authority, test, and review receipts.
The authority record is `.project-toolkit/scratch/validation-authority-record.json`.
Copy its decision summary into the PR description.
The allocated PR body is `.project-toolkit/scratch/pr-body-60f5310a4fce4667288faf24824a0d63.md`.

## Historical Integrated Blocker

Command: `uv run --frozen python scripts/validation/pre_pr.py --summary-json /tmp/readiness-final-pre-pr-fe2a67b2.json`.
Result: exit one at the recorded checkpoint on 2026-11-10.
Duplication examined 3472 Python files and rejected 28 duplicate blocks.
All 31 diagnostic paths match upstream main byte-for-byte.
None appears in the PR's three-dot changed paths.
Examples include tool instrument files and GitHub skill entrypoints.
These paths exceed the approved final repair scope.
No baseline growth, exclusion, suppression, or upstream repair was applied.
The owner is `rjmurillo/ai-agents`.
The evidence record is `.project-toolkit/scratch/readiness-review-fe2a67b2/upstream-duplication-blocker.json`.

Independent Stage 1 reviewed every changed line and satisfied all ten criteria.
The complexity classifier selected Tier 3.
No Stage 2 canonical review ran after this blocker appeared.
Two historical reviewer processes preceded the current fresh review allocation.
The earlier implementation consumed its separate allocated process.
Build quality, documentation compilation, and repository-wide orphan gates exited zero.
Taste exited zero with 12 warnings and no errors.
Full coupled-document inventory timed out after 120 seconds.
Its required behavioral review remains unverified.
The integrated full regression suite was not run after preflight failed.

## Approved Upstream Repair

The approval is recorded in `.project-toolkit/scratch/readiness-upstream-duplication-decision.json`.
Scope covers the named duplicate blocks and necessary helpers, tests, and projections.
Exclusions, dependency changes, privacy changes, and baseline growth remain prohibited.
The later baseline decision permits evidence-backed, shrink-only pruning.
The fresh delegation budget allows one implementation and 14 independent review processes.
The implementation task is `1a6b131b-0d3f-47ec-8941-70fc965584f7`.
The implementer may not commit, delegate, or write externally.
It must validate provenance, authority, and risk controls before source edits.
The implementation slot was consumed without source changes.
All 14 independent review slots remain reserved.

## Historical Pre-repair Baseline Blocker

The unchanged gate failed again at the recorded head on 2026-11-10.
It examined 3472 Python files before any upstream repair edits.
It reported 28 new duplicate fingerprints and 23 stale baseline fingerprints.
Each stale fingerprint has baseline count one and current count zero.
Examples are `08426a2a8e6a8664`, `1183426f261d212d`, and `16fc2d76bb3d7364`.
At that checkpoint, the baseline contained 432 fingerprints and remained byte-identical.
The earlier blocker summary omitted this second failure condition.
The parent stopped and obtained explicit shrink-only pruning authority.
The approval is `.project-toolkit/scratch/readiness-upstream-baseline-decision.json`.
Source repair resumed after that decision.
No successful push or PR creation occurred at that checkpoint.
The raw gate receipt is `.project-toolkit/scratch/readiness-duplication-before-073.log`.
Exact fingerprints are in `.project-toolkit/scratch/readiness-upstream-stale-baseline-evidence.json`.
The owner is `rjmurillo/ai-agents`.

## Historical Source Repair Evidence

Canonical helpers now share milestone output, instrument dispatch, and skill bootstrap logic.
Other helpers share timeout parsing, comment messages, memory conversion, and scanner rule parsing.
Generated projections were rebuilt through `build_all.py`.
Consumer tests preserve differing reaction counters and dry-run behavior.
JSON serialization retains the scanners' existing field order.
On 2026-11-10, the remaining-family focused run passed 384 tests.
On 2026-11-10, the subsequent memory support extraction passed 79 tests.
On 2026-11-10, the subsequent scanner parser extraction passed 234 tests.
On 2026-11-10, six new delegation tests failed before consumer wiring.
On 2026-11-10, the repaired consumers passed all 318 focused tests.
The first combined run exposed a workspace fixture leaking an empty directory.
The fixture now runs in its temporary directory.
Only the proven empty directories created by that test were removed.
These runs do not certify the complete branch or final tip.
On 2026-11-10, Ruff and formatting passed across all 104 authored repair paths.
On 2026-11-10, all seven new helpers passed the complexity ceiling of ten.
On 2026-11-10, both runtime issue docstrings matched their original values exactly.
On 2026-11-10, six JSON comparisons matched original scanner output byte-for-byte.
On 2026-11-10, those comparisons retained arrays containing 701 violations.
On 2026-11-10, the combined focused suite passed 3277 tests and failed one.
The failure is the configured Copilot launcher, before repository Python starts.
On 2026-11-10, the additional consumer and root-path suite passed 178 tests.
On 2026-11-10, accumulated coverage reached 308 of 308 new-helper statements.
On 2026-11-10, the isolated runtime enabled all 3413 focused cases to pass.
On 2026-11-10, fresh coverage reached 308 of 308 new-helper statements.
On 2026-11-10, grouped mypy examined 104 repair paths across 21 invocations.
On 2026-11-10, its 79 remaining diagnostics were on unchanged lines.
The existing changed-line type policy passed without configuration changes.
On 2026-11-10, the subsequent type-only repairs passed 543 focused tests.
On 2026-11-10, output-contract regrouping preserved all 152 collected test identities.
On 2026-11-10, taste found zero errors and 28 inherited file-size warnings.
No warning landed on a touched line.
Full regression and final review lack current acceptance proof.
One fresh reviewer stopped without a report after the interruption.
The operator authorized one replacement, raising the reviewer cap to fifteen.
Fourteen independent review slots remain unused.

## Historical Integration Repairs

The decision is `.project-toolkit/scratch/readiness-integration-blockers-decision.json`.
The operator selected bounded repairs and one replacement reviewer.
The latest main merge introduced duplication between two reference-split test modules.
Their identical heading parser now lives in one shared test helper.
All original assertions remain, with six additional parser cases.
Workspace fallback components remain explicit in their original GitHub callers.
The shared bootstrap no longer introduces an upstream-only path reference.
The portability baseline remains byte-identical, with 164 existing references.
The duplicate baseline remains byte-identical, with 328 existing fingerprints.
On 2026-11-10, duplication passed across 3488 Python files.
On 2026-11-10, plugin-root validation passed across 12581 files.
On 2026-11-10, integration regression passed all 268 cases.
On 2026-11-10, all 378 original-source CLI comparisons matched exactly.
Those comparisons cover 63 entrypoints across six installation states.
They compare exits, stdout, and stderr against immutable original sources.
On 2026-11-10, three integration helper modules passed mypy.
On 2026-11-10, Ruff and formatting passed across 531 changed Python paths.
The authority record validates 24 targets without defects.
Full preflight and independent review do not yet certify these repairs.

## Approved Bootstrap Family and Pruning

The scope decision is `.project-toolkit/scratch/readiness-exposed-consumers-decision.json`.
D1 authorizes the completed six-consumer repair.
D2 authorizes the completed remaining family repair.
The decision record's `scope_paths` field lists its exact canonical paths.
On 2026-11-10, the shared bootstrap supports all 63 consumers and five lookup variants.
On 2026-11-10, bootstrap, legacy discovery, and coordination checks passed 231 tests.
Zero growth preceded authorized pruning.
On 2026-11-10, pruning removed 104 stale entries, reducing 432 fingerprints to 328.
No fingerprint was added, and no occurrence allowance increased.
The evidence is `.project-toolkit/scratch/readiness-source-conformance.json`.
On 2026-11-10, the unchanged gate passed across 3485 Python files.
The latest receipt is `.project-toolkit/scratch/readiness-duplication-current-tests.log`.

## Resolved Validation Runtime Blocker

Command: `pwsh --version`.
Result: exit one, with the same error as the Copilot launcher test.
The executable is `/snap/bin/pwsh`.
Snap reports that required capability `cap_dac_override` is unavailable.
The agent changed no host security settings or confinement.
The failed test remains unchanged and enabled.
The owner is the environment operator.
The decision is `.project-toolkit/scratch/readiness-powershell-runtime-decision.json`.
The focused regression receipt is `.project-toolkit/scratch/readiness-upstream-focused-combined.log`.
The operator authorized isolated installation, without host security or client changes.
On 2026-11-10, official PowerShell 7.5.13 matched its published archive digest.
Its executable is `.project-toolkit/scratch/tools/powershell-7.5.13/pwsh`.
Use its absolute directory through command-local `PATH`.
Set command-local `POWERSHELL_TELEMETRY_OPTOUT=1` and `POWERSHELL_UPDATECHECK=Off`.
The unchanged Copilot launcher test passed with this runtime.
The current suite receipt is `.project-toolkit/scratch/readiness-upstream-focused-final.log`.
Obsolete intermediate bootstrap projections were preserved outside the shipping trees.
Current projections match their canonical helper.

## Stop Conditions

Working-tree proof is not full acceptance.
On 2026-11-11, D3 preserved 313 test identities and 270 test definitions.
On 2026-11-11, duplication passed across 3504 Python files after one authorized prune.
The operator accepted only advisories in `.project-toolkit/scratch/readiness-size-warning-decision.json`.
On 2026-11-11, two of sixteen review slots were consumed; fourteen remain.

Do not push or create a review marker while preflight remains failed.
Do not repair upstream tool code without a bounded scope decision.
Prune only after growth reaches zero, within the approved shrink-only authority.
Do not claim earlier tests certify the integrated checkpoint.
Do not bypass confinement or skip the failed launcher test.

## Next Steps

1. Preserve command-local use of the authorized PowerShell runtime.
2. Complete exact-tip validation and independent review.
3. Record genuine review proof, then push normally and create the requested PR.
4. Immediately link the PR, then resolve remote gates before merging.

## Verification on Resume

Check the recorded branch, worktree, and reachable checkpoint before editing.
Inspect existing changes before changing files.
Read completed delegate reports before repeating their investigations.
Do not bypass hooks, review gates, security requirements, or branch policies.
Session log creation remains discontinued.
