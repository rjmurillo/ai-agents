# ADR-116 Debate Log 2: Acceptance and FM-14

## Summary

- **Prior debate log**: `.project-toolkit/critique/ADR-116-debate-log.md`. It closed with status `proposed` and left acceptance to the owner.
- **Rounds**: 2
- **Outcome**: Consensus. Both seats voted Accept in round 2.
- **Final Status**: accepted.
- **Panel**: reduced (architect and critic). The change is a status edit plus one taxonomy entry. No gate reads the FM class list. One skill helper, `.claude/skills/ai-agents-failure-archaeology/scripts/corpus_index.py`, parses the index table to list classes. It is not a gate. AGENTS.md reserves the full panel for executable enforcement or a rule other gates read.
- **Method note**: each seat ran as a fresh subagent. Each received the diff and the files, not the author's reasoning. The seats share a model family with the author, so the panel is not fully independent. The outside check is the owner's merge review under `governance.md` MUST 1.

## Owner decision

The owner accepted the class on 2026-11-25, through a decision brief in the issue #7643 session. The brief named the weak points: two instances of one rule, one local catch, and no enforcement owner. FM #14 was the next free number. The index ended at FM #13 on main at `ffc759356` (2026-11-25), and no open PR touched `FAILURE-MODES.md`.

## Round 1

Both seats voted Disagree-and-Commit. No P0.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Critic | P1 | The new index row shifts inbound line citations to `FAILURE-MODES.md` by one. | Fixed. `citation_reverse_pass.py` named 14 citations. A later `/review` found 3 more with no checkable anchor: `ai-agents-validation-and-qa` (template and generated copy) and `incidents.md:251`. All 17 now point at their content. Templates and generated copies changed together. |
| Critic | P1 | "Across nine files" overstated the hook catch. The retro says the hook named three files and a sweep found six more. | Fixed in the FM-14 Evidence section. |
| Critic | P1 | The Enforcement table prescribed a practice no gate backs. ADR Decision item 6 says "None new". | Fixed. The section now says none new and records the absence with a date. |
| Critic | P1 | ADR body still said the taxonomy was unchanged until acceptance. | Fixed in Decision, Impact, and Reversibility. |
| Architect | P1 | Generated ADR index still listed ADR-116 under Proposed. | Fixed. `generate_adr_index.py` was rerun. |
| Architect | P1 | The prior debate log ends at `proposed`. | Fixed. This log records the acceptance and leaves the closed log unchanged. |
| Architect | P2 | Frontmatter `date` was stale. | Fixed. Set to 2026-11-25. |
| Architect | P2 | The "no pre-stage check" absence claim had no date. | Fixed. It cites the ADR-116 search of 2026-10-13. |
| Critic | P2 | Detection table differed from ADR item 5. | Fixed. The row cites item 5 with its gate list. |
| Critic | P2 | The `voice.md` claim cited the retro, not the ADR. | Fixed. It cites ADR Decision item 6. |

## Round 2

Both seats voted Accept. No P0 or P1.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Both | P2 | Rationale still said nothing changes until acceptance. | Fixed. Past tense with the acceptance date. |
| Critic | P2 | Consequences still said the owner can decline. | Fixed. It records the acceptance. |
| Architect | P2 | "No open issue owns it" had no date. | Fixed. An open-issue search on 2026-11-25 found no owner. |
| Critic | P2 | The title still reads "Propose a Failure Mode". | Not adopted. The title names the record as filed, and the index keys on it. The Status section carries the decision. |

## Gates

Run on the final branch content, 2026-11-25.

| Gate | Command | Result |
| --- | --- | --- |
| adr-review policy | `scripts/validation/git_hook_policy.py adr-review` on the staged branch diff | exit 0 |
| Staged dash policy | `scripts/validation/git_hook_policy.py staged-dashes` on the staged branch diff | exit 0 |
| Citation reverse pass | `scripts/validation/citation_reverse_pass.py` | 0 blocking. Citations already stale at the merge base do not block. |
| Pre-PR | `scripts/validation/pre_pr.py` | exit 0. 126 PASS, 0 FAIL, 2 BLOCKED. |

The two BLOCKED gates are `actionlint` and `yamllint`, which are not installed locally. This change edits no workflow or YAML file. CI runs both.

## Outcome

Consensus Accept. ADR-116 moves to `accepted` with `implemented: true`, because FM-14 lands in the same change. Issue #7643 closes on merge.
