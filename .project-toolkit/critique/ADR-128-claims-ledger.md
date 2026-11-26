# ADR-128 claims ledger

Checked on 2026-11-25 against the working tree of branch `feat/receipts-phase1`.

Rows marked "local logs" come from a full count of all 11,160 `~/.copilot/session-state/*/events.jsonl` files on the author's machine on 2026-11-25. Those logs are not in the repository. A reviewer can check only that the ADR matches REQ-050's probe section. Method: for each file, track the last `session.start` `copilotVersion`, count `hook.start` and `hook.end` records whose `data.hookType` is `agentStop`, and after a `decision: block` output read `stop_hook_active` from the next `hook.start` input in the same file. The first draft of rows 5, 7, 8, and 9 used a scan capped at the 3,000 most recently modified files (2,115 runs, 49 blocks, 25 false). The full count replaced them on 2026-11-25. ADR-084 line numbers were re-read after the rule 2b amendment shifted them.

| # | Claim | Kind | Command or source | Result |
|---|-------|------|-------------------|--------|
| 1 | `src/copilot-cli/hooks/hooks.json` has an empty `hooks` object | behavior | Read the file | VERIFIED. Content is `{"hooks": {}, "version": 1}`. |
| 2 | ADR-084 rule 2a says the nudge "MUST stay out of the Copilot tree" | quote | Read `ADR-084-vendored-hook-roi-bar.md` line 164 | VERIFIED. Line reads "The hook MUST stay out of the Copilot tree." |
| 3 | Rule 2a's reason: Copilot documents neither an advisory field nor `transcript_path` | quote | Read ADR-084 lines 169 to 171 | VERIFIED. |
| 4 | Rule 2a condition b puts state in per-user storage outside every detectable repository | behavior | Read ADR-084 lines 122 to 126 | VERIFIED. |
| 5 | 3,897 logged blocks; next stop had `stop_hook_active` true 3,510 times, false 378, absent 1; 8 had no next stop; 279 false of 1,586 blocks on 1.0.79 builds | count | local logs; REQ-050 line 145 records 378 of 3,889 and 279 of 1,586 | UNAVAILABLE to a reviewer. Measured by the author on 2026-11-25. The next-stop pairing is INFERRED. |
| 6 | Zero contradicted stamps in 678 spike runs | count | `git show spike/nocap-checker-core:.project-toolkit/prototypes/nocap-spike/REPORT.md`, lines 20 and 57 | VERIFIED by the author with `git show`. "678 runs scanned. No CAP stamp appeared in any of them." CAP is the spike's label for a contradicted stamp. The refuting seat had no git tool and could not check this row. |
| 7 | 19,518 `agentStop` runs in 11,160 files, Copilot 1.0.37 to 1.0.105; 1.0.116 installed; `stop_hook_active` present in 17,632 | count | local logs; REQ-050 lines 75 and 77 | UNAVAILABLE to a reviewer. ADR matches REQ-050. |
| 8 | `transcriptPath` set in 10,977, empty in 8,541; before 1.0.79: 5,711 set, 5,424 empty; 1.0.79 builds: 4,830 set, 3,117 empty; 436 runs on 1.0.87 and later all set; none on 1.0.80 to 1.0.86 | count | local logs; REQ-050 line 78 | UNAVAILABLE to a reviewer. ADR matches REQ-050. The sums check: 5,711 + 4,830 + 436 = 10,977 and 5,424 + 3,117 = 8,541. |
| 9 | Logged outputs: 13,922 empty, 3,897 `decision` plus `reason` (all `block`), 1,699 `reason` alone, no other field; no block on 1.0.87 or later | count | local logs; REQ-050 line 80 | UNAVAILABLE to a reviewer. ADR matches REQ-050. The sum is 19,518. |
| 10 | Copilot documents `decision` for `agentStop` and `subagentStop` only | behavior | `official-hook-contracts.md` line 215 in the `agent-harness-reference` skill | VERIFIED. |
| 11 | The reflect nudge shim carries `copilotExclude: true` with decision `ADR-084` | behavior | Read `src/claude/hooks/dispatch_groups.json` lines 40 to 52 | VERIFIED. The group has `"event": "Stop"` and `"surface": "plugin"`. |
| 12 | The shared Claude Stop timeout is 15 s | count | `grep -n '"Stop"' -A12 src/claude/hooks/hooks.json` | VERIFIED. `"timeout": 15`. |
| 13 | Two decision objects from one Copilot Stop dispatcher concatenate into invalid JSON | behavior | `.serena/memories/decision-claude-hook-group-dispatch.md` line 14 | VERIFIED as a recorded decision. Not re-probed. |
| 14 | PR #3372 deleted a hook that blocked a turn until a retro existed | behavior | ADR-084 lines 152 to 155 | VERIFIED as ADR-084's own statement. The PR was not opened. |
| 15 | ADR-097 is titled "Zero Tool-Use Hooks" | quote | Read the ADR-097 heading | VERIFIED. |
| 16 | Zero false in 30 gives an upper 95% Wilson bound of 0.114 | count | Wilson score interval, z = 1.96, k = 0, n = 30 | VERIFIED. Computed 0.1135. |
| 17 | The reflect nudge carries a `Customer value:` line | behavior | `grep -n 'Customer value' src/claude/hooks/Stop/invoke_reflect_nudge.py` | VERIFIED. Line 37. |
| 18 | No live probe ran on 1.0.116 | absence | REQ-050 line 75 | VERIFIED against REQ-050. The probe fired `sessionEnd` only. |
| 19 | ADR-084 sets six rules | count | ADR-084 lines 103, 106, 229, 241, 247, and 293 | VERIFIED by the refuting seat; line numbers re-read 2026-11-25. |
| 20 | ADR-097 retired the tool-use hooks | behavior | ADR-097 lines 23 to 24, "retire all 5 hooks" | VERIFIED by the refuting seat. |
| 21 | The reflect nudge prints a `systemMessage` | behavior | `invoke_reflect_nudge.py` line 481 | VERIFIED by the refuting seat. |
| 22 | ADR-084 rule 6 treats session-boundary events apart from per-call events | behavior | ADR-084 lines 293 to 298 | VERIFIED. "Their cost scales with how hard the agent is working, which the session-boundary events do not." |
| 23 | The owner chose on 2026-11-25 to ship to both harnesses and to block on Copilot | behavior | REQ-050 user stories 1 and 2, Open questions, and ADR cross-reference | VERIFIED against REQ-050. The decision itself was made in the authoring session. |
| 24 | ADR-071 and ADR-085 titles in Related Decisions | quote | Read both headings | VERIFIED. |
| 25 | Rule 2a covers one hook only, and any other advisory hook needs its own amendment | quote | Read ADR-084 lines 115 to 117 | VERIFIED. "Rule 2a covers one hook only: the REQ-048 friction nudge" and "Any other advisory hook needs its own amendment." |
| 26 | Rule 2a calls a hook that fails any of a to g enforcement | quote | Read ADR-084 lines 155 to 156 | VERIFIED. |
| 27 | Two tests pin one advisory group and an empty Copilot Stop list | behavior | Read `tests/hooks/test_plugin_stop_registration.py` lines 111 to 115 and 244 to 248 | VERIFIED. `test_copilot_plugin_has_no_entry_for_the_hook` and `test_the_advisory_set_is_exactly_the_reflect_nudge_group`. |
| 28 | Zero in 678 gives an upper 95% Wilson bound of 0.0056, so 30 contradictions need at least 5,300 runs | count | Wilson score interval, z = 1.96, k = 0, n = 678; 30 / 0.00563 | VERIFIED. Computed 0.00563 and 5,325. |
| 29 | The flag was false after 9.7% of blocks | count | 378 / 3,889 | VERIFIED. Computed 0.0972. Rests on row 5. |
| 30 | ADR-084 gains rule 2b in the same change | behavior | Read ADR-084 lines 177 to 228 | VERIFIED. Rule 2b is marked proposed and not yet binding. |
| 31 | The Claude message repeats at most 80 characters of claim text | quote | REQ-050 line 167 | VERIFIED against REQ-050. |
| 32 | Each receipt names the tool, on both harnesses | behavior | REQ-050 lines 129, 166, 178, and 180 | VERIFIED against REQ-050. Line 129 defines a receipt "by index, tool name, and a short reason". Line 178 (AC-1) puts each receipt in the Claude message. Lines 166 and 180 put the tool name in the Copilot reason. |
| 33 | 10,977 of the 19,518 runs carry a `transcriptPath`, and the hook is silent on the other 8,541 | count | Row 8; 10,977 + 8,541 | VERIFIED as arithmetic. Computed 19,518. Rests on row 8. |
| 34 | Receipts stops at a 5 s internal deadline | behavior | REQ-050 line 184, AC-7 | VERIFIED against REQ-050. No code exists yet. |
| 35 | The ADR-084 rule 5 tests live in `tests/hooks/test_dispatch_groups_parity.py` | path | Read the file, lines 264 and 289 | VERIFIED. `test_every_vendored_hook_states_its_customer_value` and `test_the_customer_value_check_examines_a_nonempty_surface`. |
| 36 | Issue #7633 tracks the work and PR #7631 is the draft spike record | behavior | `get_issue_context.py --issue 7633` and `get_pr_context.py --pull-request 7631` on 2026-11-25 | VERIFIED. The issue is open. The PR is open and a draft. |
| 37 | No ADR-128 exists on `origin/main` | absence | `git fetch origin main`, then `git ls-tree --name-only origin/main .project-toolkit/architecture/` on 2026-11-25 | VERIFIED. The highest number there is ADR-127. |

## Gate results

| Gate | Result |
|------|--------|
| 1. Claims ledger | VERIFIED for 33 rows. UNAVAILABLE for rows 5, 7, 8, and 9, which rest on local logs. Rows 32 to 37 were added during review rounds 2 and 3. |
| 2. Documentation accuracy | NOT RUN as the `doc-accuracy` skill. The refuting seat covered the same path, count, and quote checks. |
| 3. Self-consistency | VERIFIED. Decision items 3 and 5 agree: no marker means no block. Item 9 agrees with the Negative consequence on builds 1.0.79 and earlier. Item 7's date matches frontmatter `review-by`. |
| 4. Refuting seat | Ran once on 2026-11-25 (`analyst`, haiku, 23 tool calls, 170 s). It found row 14 overstated and five claims with no row. The ADR was corrected and rows 19 to 24 were added. No factual finding remains open from that run. It could not see the local logs, so it did not catch the capped scan behind rows 5, 7, 8, and 9. The author found that on 2026-11-25 while answering review round 1. |
