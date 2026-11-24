# Agent readiness history

Moved verbatim from [the active readiness handoff](2026-11-09-readiness.md).

## Earlier Resume (2026-11-20 UTC, after D24 to D27)

The parent tip is `2b788dd53` on `fix/agent-readiness-signals`.
The checkout still contains only this handoff's uncommitted changes.
D19 citation repairs landed as `b121c912d`, `e6519b136`, and `dad59b117`.
D22 severity inheritance landed as `1f081a44a`.
D22 diagnostic redaction landed as `2b788dd53`.
Earlier validation receipts below remain historical, not final-tip certification.

The resumed conversation records ADR-123 round one as six Block votes.
Its draft and debate log remain in the preserved design checkout.
That checkout is `/home/richard/worktrees/ai-agents4/t3-53b866da-4515ae9b3ac36f3f`.
The ADR remains unaccepted.
The conversation records these owner decisions:

- D24 A requires documentation repairs before replay and narrowed ADR review.
- D25 A retains existing local and standard-library shortcuts.
- D26 A makes Phase 3 blocking in build, test, and CI only.
- D26 A keeps pre-PR Phase 3 advisory.
- D27 A authorizes test-first repairs for the reproduced scanner false passes.

D27 covers mixed receivers, shadowed imports, and unrelated repository symbols.
It also covers invented members hidden by real imports.
Unknown symbols and unproven receivers must still fail.
No ignore markers, exclusions, baseline growth, or threshold weakening are authorized.
The README privacy contract still binds repository-side changes.

Both delegated workers remained running when this resume checked their threads.
D27's thread suffix is `d24d27-D27-scanner-false-pass-fixes`.
D24's thread suffix is `d24d27-D24-doc-example-repairs`.
Both use Codex `gpt-6.2-sol` in isolated checkouts.
Integrate their verified commits before the full-corpus replay.
Use replay evidence to narrow ADR-123 before its second review round.
All fourteen final independent review slots remain unused.
No push, pull request creation, or merge occurred during this resume.
Goal tools remain unavailable; no automated goal is armed.

D11's duplicate-repair worktree remains preserved until merge.
Its path is `/home/richard/worktrees/ai-agents4/fix-readiness-d11-dupli-a60624f87ff01c00`.
Its branch is `fix/readiness-d11-duplicates`.
The owner authorized removing that worktree and branch after merge.

## Earlier Resume (2026-11-20 UTC, after D20 approval)

The parent tip is `8f889d682` on `fix/agent-readiness-signals`.
D14 landed as `f915118ec`; portability fixtures landed as `8f889d682`.
D19b's approved governance citations landed as `49ebeee9e`.
The normal-buffering full suite exited zero at `8f889d682`.
It recorded 73,800 passed, 129 skipped, and 38 passing subtests.
Its reported pytest duration was 213.26 seconds.
Receipt: `.project-toolkit/scratch/readiness-8f889d682-full-suite.log`.
The post-suite build check exited zero without deleting caches.
It reported zero Hermes drift and zero stale files.
Receipt: `.project-toolkit/scratch/readiness-8f889d682-postsuite-build-check.log`.
These results do not certify later implementation commits.

D19a's citation-only patch remains isolated and uncommitted.
Its checkout is `/home/richard/worktrees/ai-agents4/t3-d59117c2-fec7c25fbcec1a40`.
Historical Git objects support ADR-100's removed enforcement references.
Fresh architect and critic delegates reviewed all three ADR patches.
Their task suffixes are `f4b12e0f-9990-4014-b075-4c3ec9b9f183`
and `81b4d669-f1de-435a-b78e-3d802a6dc02c`.
Both accepted ADR-101; ADR-100 received Accept and Disagree-and-Commit votes.
Both blocked ADR-102's current-tense claim about its deleted CI caller.
Richard approved D21 A to correct only the necessary historical framing.
No decision, policy, or enforcement change is authorized by D21.
The citation worker now owns that correction and the missing HEAD-resolution anchor.
Fresh round-two reviewers reported zero P0 and P1 findings.
Both voted Disagree-and-Commit for ADR-100 and Accept for ADR-101 and ADR-102.
The worker owns separate debate logs and three atomic ADR-plus-log commits.
No ADR repair has been integrated into the parent yet.
The D21 decision brief is `.project-toolkit/scratch/readiness-d21-adr102-scope.json`.

Richard approved D20 option A during this resume.
It authorizes positive-evidence external API resolution and genuine example repairs.
Unknown symbols and unproven receivers must still fail.
Ignore markers, symbol allowlists, exclusions, and weaker thresholds remain prohibited.
Blanket illustrative acceptance and advisory downgrades remain prohibited.
The validated decision brief is `.project-toolkit/scratch/readiness-d20-scanner-policy.json`.
Memory search ran before delegation and returned ten results.
Relevant episodes cover doc-accuracy false findings and immutable PR snapshots.
The fresh Codex GPT-6.2 Sol implementation uses high reasoning effort.
Its isolated task suffix is `fce67c46-0bad-42a0-a83c-2212606a8274`.
The worker stopped at a Tier 4 design milestone with zero commits.
Baseline scanner regression passed all 593 tests in its isolated checkout.
The worker drafted proposed ADR-123 and its claims ledger without executable changes.
Its checkout is `/home/richard/worktrees/ai-agents4/t3-53b866da-4515ae9b3ac36f3f`.
The parent launched the full six-role ADR debate at round one.
The review examines default integration, evidence trust, portability, and scope fit.
GitHub related-work search found the merged external-SDK-marker change, PR 7423.
That search did not establish the proposed bundle design's acceptance.
The design must specify default-entry integration and offline dependency provenance.
Proof receipts, symbol catalogs, and grandfathered unproven members cannot replace evidence.
The proposed architecture requires the full ADR debate before implementation.
Implementation must pass provenance, authority, test-first, and normal exit gates.

D14's recorded replay still failed with 801 high findings.
Mirror normalization produced 283 findings across 59 canonical documents.
The parent integrated full-corpus scan exited ten at `8f889d682`.
It assessed 7,301 documents and extracted 32,156 claims.
It recorded 18,591 code blocks and 801 high findings.
Receipt: `.project-toolkit/scratch/readiness-8f889d682-corpus.log`.
CodeQL 2.23.9 completed a full scan at `8f889d682` and exited one.
Actions recorded zero findings; Python recorded three sensitive-logging findings.
All three source files were unchanged by this branch.
The result-level severity field was absent; the rule default was error.
The severity gate counted zero high findings despite that default.
The quick configuration also failed real database initialization with exit two.
CodeQL requires a `uses` property in each query entry.
CodeQL-focused regression passed all 322 tests.
Full configuration validation and SARIF structure checks passed.
Tracked-entry parity checked all 17,850 entries; six scanner wrappers matched.
The scan artifacts reside under `.project-toolkit/scratch/codeql-8f889d682.MjvaIVPV/`.
Read-only triage classified the three exact CodeQL traces as false positives.
The export traces carry counts and line numbers; the workflow trace carries a boolean.
A separate workflow subprocess-diagnostic path reproduced unmasked synthetic output.
Synthetic SARIF also proved inherited CVSS ten bypasses the critical gate.
Richard approved D22 A: repair those two bounded implementation defects.
The approval adjudicates only the three exact reviewed false-positive flows.
It authorizes no suppression, alert dismissal, threshold change, or security-setting change.
The broken quick configuration remains unchanged and is not certified for use.
Full configuration remains the required scan path.
The fresh isolated implementation task suffix is `0bf09946-07e4-467d-86b6-72b920f4ed51`.
The D22 brief is `.project-toolkit/scratch/readiness-d22-security-repairs.json`.
All fourteen final independent review slots remain unused.
The authenticated branch query returned zero open pull requests during this resume.
No push, pull request, or merge has occurred.

## Earlier Resume (2026-11-20 UTC)

HEAD `586619654` integrates D13 tip `756bf3997` on 2026-11-20.
D13's six ADR votes closed with no P0 or P1 findings.
The exact-file bootstrap rejects cached modules and supports isolated entry-file symlinks.
Parent entry-point regression passed all 52 tests.
Combined bootstrap, hook-health, and validation-skill regression passed all 167 tests.
The worker's broader 673-test receipt remains historical integration evidence.
All fourteen final independent review slots remain unused.

Commit `e19924ac5` contains D17's six approved numeric governance citation repairs.
Richard approved D18's three redundant command-label removals on 2026-11-20.
Those removals preserve function names, ranges, behavior, and policy fields.
Commit `f87460eb0` landed D18, but the three rows still fail reverse citation.
Their prose names typed tokens defined in shared helpers at lines 7539-7541 and 9241.
Each function name also hits its dispatch line, so it casts no inside vote.
Any further row edit needs a new governance decision.
Richard canceled D16; ADR-100, ADR-101, and ADR-102 remain untouched.
Their six reverse-citation failures still block merge and require owner action.

Duplication examined 3865 Python files after D13 integration on 2026-11-20.
It found zero growth and exactly 30 stale entries.
The authorized shrink-only updater removed those entries; 305 allowances remain.
A fresh unchanged gate passed against origin/main.
Portability removed one redundant upstream reference and its stale declaration.
The updater reduced only existing allowances; no entry grew.
Fresh skill-page checking found zero stale pages across 29 changed skills.
Forward citation checking passed across 248 changed files.
Hook-health wording preserves its quoted signature at 500 lines.
Ruff checks, formatting, and whitespace checks passed.
The full pre-condensation handoff remains in scratch:
`readiness-handoff-before-20261120-condensation.md`.

Preflight at `1e5f0f7ee` completed in 612.5231 seconds on 2026-11-20.
It recorded 120 passes, seven failures, and two skips.
Five failures blocked: count ratchets, duplication, reverse citations, portability, and doc accuracy.
The documentation-accuracy subprocess timed out at its internal 300-second cap.
Other failures were advisory temporary-worktree and active-plan findings.
Receipt: `.project-toolkit/scratch/readiness-1e5f0f7ee-preflight.json`.
This historical run does not certify the integrated tip.

D13's first Codex worker exhausted credits; its old worktree remains preserved.
Duplicate recovery task `0853489c-1903-4c49-b9c4-6b2b764ba0c6` was canceled.
The Factory recovery worker completed the integrated D13 commit.
D14 still owns only L1-L6 and L10-L12 scanner repairs.
L7-L9, illustrative-example acceptance, suppressions, and threshold changes remain unauthorized.
Full-corpus documentation acceptance remains unproved.
No push, PR creation, or merge occurred during this resume.

## Resume Snapshot (2026-11-20 UTC, after D28 and D29)

The branch tip is the handoff commit after `b6f4f9e56`.
D24 document repairs landed as `a9d7fa2ec`, `6b69843a3`, and `be029fa05`.
D27 scanner fixes landed as `6a8c7e8c8`.
`f56b96104` merged `origin/main` through `a5e0847ff`.
`b6f4f9e56` added ADR-124 as proposed.

Main merged an unrelated ADR-123 while the draft was open.
The SDK symbols draft is now ADR-124, with its debate log and claims ledger.
Round 1 is preserved. Round 2 has not run.
Issue [#7501](https://github.com/rjmurillo/ai-agents/issues/7501) tracks the residual work.

The owner recorded two more decisions:

- D28 A narrowly amends D25 to allow occurrence binding and positive member checks.
- D29 A ships this branch with the residual tracked.

The full-corpus replay at `6a8c7e8c8` exited 10 with 1,137 high findings.
All are `unresolved_symbol`: 817 C#, 287 TypeScript, and 33 Python.
The run took 12 minutes 56 seconds and 328,940 KiB peak RSS.
Under D29 the branch ships with that exit 10 recorded.
No CI workflow or lefthook job runs the full-corpus scan.

Post-merge checks passed: marker verify, `build_all.py --check`, citations, and portability.
Focused tests reported 5,453 passed and 5 skipped.
Final gates and the fourteen independent reviews come next.
No push, pull request, or merge has happened yet.

D11's duplicate-repair worktree remains preserved until merge.
Its path is `/home/richard/worktrees/ai-agents4/fix-readiness-d11-dupli-a60624f87ff01c00`.
Its branch is `fix/readiness-d11-duplicates`.
The owner authorized removing that worktree and branch after merge.
