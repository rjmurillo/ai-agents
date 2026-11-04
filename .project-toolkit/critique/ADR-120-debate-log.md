# ADR Debate Log: ADR-120 The Completion Gate Reports a Refused Session as Unknown

## Summary

- **Rounds**: 2 of 10. Round 2 reached consensus.
- **Prior debate log**: none for ADR-120. ADR-059 closed at `.project-toolkit/critique/ADR-059-debate-log-5.md`.
- **Outcome**: Consensus. Round 2: six Accept.
- **Final Status**: accepted

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-120-completion-gate-unknown-verdict.md`
- **Related edit**: ADR-059 Decision 1 gains the words "(exit 3: ADR-120)" on its existing line. ADR-059 stays at 500 lines.
- **Issue**: #5232. Branch `fix/5232-gh-refused-session`.

Panel: full panel, because the decision changes the completion gate's exit contract. Round 1 reviewed the text as an ADR-059 amendment. The `size-cap` check refused that, because ADR-059 was already at 500 lines. The text moved to ADR-120, and round 2 reviewed it there.

Method: each seat ran as its own subagent with read-only tools. Seats read the ADR, the gate, and the tests. They did not see the author's reasoning.

## Round 1 (2026-11-04)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Disagree-and-Commit | Rules match the code. Status cited a missing log, and a decision was misquoted. |
| critic | Block | Status claimed acceptance before the panel closed. Rules overstated the evidence. |
| independent-thinker | Disagree-and-Commit | Direction is sound. The refusal applies by exit code, not by verifier. |
| security | Disagree-and-Commit | No path to a pass. The hand check had no limits. |
| analyst | Disagree-and-Commit | Code matches. Citations and caller claims were weak. |
| high-level-advisor | Disagree-and-Commit | With the App declined, the gate gives no verdict in cloud sessions. The ADR must say so. |

### Issues Raised

| Priority | Issue | Resolution |
|----------|-------|------------|
| P0 | Status said accepted before the panel closed | Status stayed proposed until this log closed |
| P0 | "Decision 4" misquoted ADR-059 | Context now names `_evaluate_criterion` |
| P0 | Strategic fit: no verdict in cloud sessions | Rationale states it is deliberate. Deferred MCP evidence names the owner |
| P0 | Refusal is session-wide, so a non-`gh` fault reads unknown | Decision 8 and a test pin the preflight. Consequences name the trade-off |
| P1 | Hand check had no limits | Decision 9: never sets `all_passed`, never arms a merge, reported as derived |
| P1 | Exit 3 overload not justified | Decision 7 cites ADR-035. Alternatives weigh exit 1, exit 2, and a code above 100 |
| P1 | Caller claims lacked evidence | Consequences list the callers |
| P1 | Probe trust assumptions unstated | Decision 3 and Residual risk state them |
| P1 | Reversibility overstated | Reversibility says no code parses the new fields |

### Claims Checked

| Claim | Agent | Result |
|-------|-------|--------|
| `pr-autofix` line 92 says to retry the gate's exit 3 | critic, independent-thinker | WITHDRAWN in round 2. That table describes `check_github_transport.py` |
| All five verifiers call `assert_gh_authenticated` | analyst, security | VERIFIED |
| `assert_gh_authenticated` exits 2 on a refusal | analyst | VERIFIED |
| `get_unresolved_review_threads.py` exits 0 on API failure | analyst | VERIFIED |

## Round 2 (2026-11-04)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Accept | All round-1 issues resolved. One P2 on the loose GraphQL pattern. |
| critic | Accept | No open P0 or P1. Withdrew the line 92 finding. |
| independent-thinker | Accept | Ran the suite. Two P2 notes. |
| security | Accept | No open P0 or P1. Two P2 notes. |
| analyst | Accept | No open P0 or P1. Two P2 notes. |
| high-level-advisor | Accept | No open P0 or P1. Two P2 notes. |

### Dissent and P2 Items

| Item | Agent | Disposition |
|------|-------|-------------|
| Decision 8 test checked presence, not order | independent-thinker, security | Fixed after the vote. An AST test now allows only argument parsing before the preflight |
| GraphQL pattern matched the REST body | architect | Fixed after the vote. The pattern quotes the GraphQL body |
| ADR said `pr-autofix` halts on exit 3 | analyst | Fixed after the vote. It now says the text forbids a retry |
| Resolve `gh` to an absolute path | critic | Dissent recorded. Verifiers trust the same binary, so it adds no safety |
| No run in a real refused session | independent-thinker | Dissent recorded. Stated in Residual risk |
| `pr-review` line 236 omits the data-handling text | security | Dissent recorded. The skill is 13 bytes under its size limit, and `transport-routing.md` carries the full rule |
| File an issue for deferred MCP evidence | high-level-advisor | Flagged in the PR. Filing is the owner's decision |

## Closing Summary

Consensus in round 2 with six Accept. The three post-vote fixes tighten a test, a pattern, and one sentence. They change no decision.
