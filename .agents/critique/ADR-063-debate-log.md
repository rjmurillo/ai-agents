# ADR-063 Review Debate Log

**ADR**: `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` (renumbered from ADR-063 per #2228)
**Date**: 2026-06-02
**Protocol**: 6-agent adr-review (architect, critic, independent-thinker, security, analyst, high-level-advisor)
**Outcome**: Consensus reached. 2 Accept, 4 Disagree-and-Commit, 0 Block. P0/P1 dissents resolved in revision.

## Verdicts

| Agent | Verdict | Headline finding |
|-------|---------|------------------|
| architect | Accept | Format coherent with ADR-062; FM #11 placement correct; missing Reversibility/Vendor-lock-in section (P1). |
| critic | Disagree-and-Commit | P0: anchoring gate + e2e run only in pre-push (bypassable); no server-side CI gate. P1: validator hardcodes two artifact paths. P1: deferred launcher fix unowned. |
| independent-thinker | Disagree-and-Commit | P0: anchoring rides undocumented vendor vars; deferring launcher graceful-degradation leaves blast radius open. P1: contract test injects the var it checks (self-referential). |
| security | Accept | CWE-78 not reachable (double-quoted expansion not re-tokenized, proven empirically); CWE-426 needs same-user (no new trust boundary); deferrals OK. All P2. |
| analyst | Disagree-and-Commit | All technical claims verified at file:line. P1: quote the contract verbatim (canonical-source-mirror); distinguish the two test files in Consequences. |
| high-level-advisor | CONCERNS / D&C | P0: convert launcher graceful-degradation from open-ended deferral to a committed, issue-tracked follow-up with the fail-open-at-launcher principle. P1: no-auth cross-platform (Windows pwsh) contract sim in CI. |

## P0/P1 issues and resolutions

| # | Pri | Finding | Resolution |
|---|-----|---------|-----------|
| 1 | P0 | No server-side (CI) enforcement of the anchoring gate; pre-push is bypassable (`--no-verify`, fork PR, release from un-pre-pushed branch). | Added a `Run hook anchoring gate` step to `.github/workflows/validate-plugin-manifests.yml`, which triggers on any `**/hooks/hooks.json` or manifest change. The no-auth runtime-contract test and the validator unit test already run in `pytest.yml`. |
| 2 | P0 | Launcher graceful-degradation (proposed as the control to bound the wedge blast radius) was an open-ended deferral with no owner. | Resolved by rejecting launcher fail-open in favor of prevention plus loud failure: anchoring + the runtime-contract gate catch a broken launcher before release, and an escaped failure fails loud rather than silently exiting 0. ADR Decision item 5 records the fail-closed position; issue #2230 closed addressed-by-prevention. |
| 3 | P1 | Contract test injects the plugin-root var it then checks (self-referential); could pass while production breaks on vendor drift. | Added `test_anchor_is_load_bearing_when_no_plugin_root_var_set`: with no var set, the anchored path must NOT resolve. Documented that the contract sim verifies path resolution, not vendor behavior (the real-CLI e2e does that). |
| 4 | P1 | ADR doc gaps: no Reversibility/Vendor-lock-in section; contract not quoted verbatim; two test files conflated; undocumented-var fragility unstated. | Added Reversibility and Vendor Lock-in section; added a verbatim measurement block and an explicit "not a vendor contract" caveat; distinguished the three verification layers (validator, runtime-contract test, real-CLI e2e) in Consequences. |
| 5 | P1 | Validator hardcodes two artifact paths; a new hook-bearing platform ships ungated. | Tracked in issue #2231 (glob/registry-based discovery). |
| 6 | P1 | Windows PowerShell path-resolution has no always-on CI gate (incident was reported on Windows). | Tracked in issue #2231 (no-auth Windows pwsh contract sim in CI). |
| 7 | P2 | Security: keep the command double-quoted (an unquoted future variant would be CWE-78); restrict the e2e probe env dump; nightly smoke needs secrets governance; run the nightly from a trusted ref only. | Recorded in the rule and issue #2231; the e2e probe dumps only the two named path vars. |

## Anti-pattern self-check (Zimmermann)

No Pass-Through (all agents produced substantive, cited findings). No Groundhog Day (each round distinct). No rubber-stamping: the security and architect Accepts cite specific evidence; the four D&C votes each carry concrete, file-cited dissent that was resolved in revision rather than waved through.

## Disposition

ADR-063 status set to Accepted. All P0 issues resolved in code/ADR; all P1 issues resolved or tracked with an issue (#2230, #2231). Dissent preserved here.
