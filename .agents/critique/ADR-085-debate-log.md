# ADR-085 Debate Log

Multi-agent adr-review of `.agents/architecture/ADR-085-cross-harness-permission-surface-asymmetry.md`.

- Date: 2026-07-20
- ADR: ADR-085 (Cross-Harness Permission-Surface Asymmetry and Hook Survivor Disposition)
- Trigger: new ADR authored for issue #3217 (part of epic #3197)
- Rounds: 1 (consensus reached)

## Verdict Summary

| Agent | Verdict | P0 | Key contribution |
|-------|---------|----|-------------------|
| architect | ACCEPT | 0 | Confirmed frontmatter, sections, and that D-A resolves the ADR-084 rule 4 violation on both branches. Asked for a Confirmation mechanism and a D-B reversal citation. |
| critic | ACCEPT | 0 | Verified all 5 source line citations exact. Asked to lead Finding 2 with the deny-scope argument, add a staleness trigger, and cite ADR-084 rule 3. |
| security | ACCEPT | 0 | Finding 2 VERIFIED (risk 7/10). Flagged the absolute deny claim and an unstated tilde/brace residual gap. |
| analyst | ACCEPT | 0 | Verified self-neuter, `skip_if_consumer_repo` semantics, both hooks shipping to Copilot, and D-A fix feasibility (`_plugin_root` swap). Provenance and Copilot-surface flagged as could-not-verify (later verified by orchestrator). |
| high-level-advisor | ACCEPT | 0 | ASR-positive. Compressed D-A + D-B to one owner question. Tie-break: KEEP (bounded cost beats unbounded auto-approve risk). |
| independent-thinker | DISAGREE-AND-COMMIT | 0 | Accepts the evidence, disputes decision completeness: missing "delete" option (C-1) and an explicit ADR-084 rule 4 tension (C-2). |

Consensus: 5 ACCEPT + 1 Disagree-and-Commit. No P0. Consensus reached in round 1.

## Findings Verified Against Source (critic + analyst + security)

- `invoke_test_auto_approval.py:22-32` DANGEROUS_METACHARACTERS = `;`, `|`, `&`, `<`, `>`, `$`, backtick, `\n`, `\r`. Exact.
- `invoke_test_auto_approval.py:42-47` prior `python evil.py pytest` bypass comment + `-m` anchored fix. Exact.
- `invoke_skill_first_guard.py:373-374` `if skip_if_consumer_repo(...): return 0`. Exact.
- `guards.py` `skip_if_consumer_repo` returns True when origin != ai-agents or unknown+uncorroborated. Accurate.
- Both `skill_first_guard` and `observation_sync` ship to Copilot; `github` skill scripts ship to consumers. Verified via `src/copilot-cli/hooks/` and `src/copilot-cli/skills/github/scripts/`.
- Finding 2 threat model: `Bash(pytest *)` auto-approves `pytest $(...)` and `pytest > file` because Claude splits only on separators (`&&`, `||`, `;`, `|`, `|&`, `&`, newlines), not substitution or redirects. Security lens rates 7/10 (CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N). Conclusion: security regression, VERIFIED.
- Provenance (orchestrator, git log this session): `#1165` PowerShell-to-Python migration commit 4600332e dated 2026-02-14; `#1194` skip_if_consumer_repo commit 2f20b5a9 dated 2026-02-20. Both dates in the ADR are exact.

## P1 Resolutions (all resolved in the ADR, none deferred)

1. Finding 2 deny claim (security P1-1, critic P1-1): reworked to lead with the scope-mismatch argument (deny is global, blocks legitimate `$` invocations), demote expressiveness to secondary, note undocumented `$` glob escaping.
2. Finding 2 residual gap (security P1-2): added tilde/brace expansion note (risk 3/10, unchanged by migration).
3. Finding 2 severity (security P2-1): added risk score 7/10 with CVSS vector.
4. Missing "delete" option (contrarian C-1): added a delete row to the Alternatives table and a third branch to D-B (keep / migrate / delete).
5. ADR-084 rule 4 tension (contrarian C-2, architect point 5): Decision 2 now states the current shipped-dead state is a direct rule 4 violation, that the ADR grants no exception, and that D-A must resolve it on either branch.
6. Staleness trigger (critic P1-2, contrarian C-3): added a concrete re-evaluation trigger and a six-month (2027-01-20) fallback to the Neutral consequences.
7. ADR-084 rule 3 basis (critic P1-3): Decision 3 now cites rule 3's escape clause as the authorizing basis for keeping a hook where the native surface is insufficient.
8. Confirmation mechanism (architect P1-1, advisor P1): added Decision 6 (Confirmation) with the eligibility-test enforcement point and an explicit #3218 acceptance criterion.
9. D-B reversal provenance (architect P1-2): cited the #3197 autopilot working session as the recorded prior approval.
10. observation_sync (critic P2, analyst P2): added the PostToolUse-fires-after-execution justification and scoped "no consumer value" to the shipped configuration.
11. Copilot surface freshness (analyst P2): added the 2026-07-20 probe date qualifier and linked it to the re-evaluation trigger.

## Disagree-and-Commit Dissent (captured, independent-thinker)

- C-1 (resolved): the "delete" option was missing. Added to the decision space; the recommendation stays "keep" because the owner may value reduced prompt fatigue, and delete is now an explicit owner branch in D-B.
- C-2 (resolved): the rule 4 tension is now explicit in Decision 2. The dissent's stronger reading (remove `skill_first_guard` from the vendored surface now, re-add on customer-facing classification) remains a legitimate owner choice under D-A's internal-only branch; the ADR routes it there rather than pre-deciding.
- Residual dissent: the independent-thinker holds that the eligibility test's portability prong risks a permanent keep-bias tied to a third-party roadmap. The ADR mitigates with the six-month re-evaluation fallback but does not eliminate the concern. Committed for the owner's awareness.

## Outcome

- Status stays `proposed`. No self-ratification to `accepted`; the owner ratifies.
- Two open owner decisions (D-A, D-B) carried for ratification; D-B now offers keep / migrate / delete.
- No code changed by this ADR.
