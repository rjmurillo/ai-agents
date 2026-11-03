# ADR Debate Log: ADR-059 /pr-review Completion Gate Dispatcher and pass_when DSL (part 2 of 2)

Part 2 of `.project-toolkit/critique/ADR-059-debate-log-2.md`, the second
debate on ADR-059. It is not a new debate: rounds continue from part 1.
Owner decision D11 (2026-11-01) split the 753-line log under the 500-line
cap. No recorded content changed. Part 1 holds the summary, the change
under review, and rounds 1 and 2.

## Round 3

**Date**: 2026-11-01. **Text reviewed**: the amendment after the round 2
revisions, against `run_completion_gate.py` at `b1baf4432` (2026-11-01).

### Agent Positions

| Agent | Position | P0 | P1 | P2 | Dissent |
|-------|----------|----|----|----|---------|
| architect | Accept | 0 | 0 | 3 | none |
| critic | Accept | 0 | 0 | 4 | none |
| independent-thinker | Accept | 0 | 0 | 3 | none |
| security | Accept | 0 | 0 | 2 | none |
| analyst | Block | 0 | 1 | 3 | none |
| high-level-advisor | Accept | 0 | 0 | 3 | none |

No seat used Disagree-and-Commit. No dissent to record.

### Issues Raised

P1:

- **AN6 (analyst)**, Residual risk wrong-harness bullet, clause
  "untracked or missing in-tree files, which PR content does not
  produce"; `gate.py:1796-1797`, `3067-3078`, `3993-3997`. REFUTED claim
  from the round 2 SE3/AN3 edit. A PR that deletes a tracked launcher
  target produces a missing path. It classifies as skip, never reaches
  `checked_files` or `untrusted`, and does not exit 2. Under a wrong but
  valid `--harness` the payload drops out of the blocking list. A non-file
  replacement (a directory holding `__main__.py`) also classifies as skip.
  Same finding at P2 from critic (CR6, with a test to pin the fail-open)
  and security (SE5, rated impact nil for a plain deletion).

P2:

- **AR5 (architect)**, R3 external bullet and Residual risk bullet 1. R3
  never names ADR-101 rule 4 (`ADR-101-enforcement-planes.md:145`).
  State the scoped exception and the path back.
- **AR6 (architect), HL6 (high-level-advisor)**, Reversibility R1
  trigger. Nothing records an agent proceeding on a non-empty list, so
  the trigger cannot fire. Name the channel or an observable trigger.
- **AR7 (architect), CR4 (critic), HL5 (high-level-advisor)**, opening
  anchor paragraph. Cites are pinned to `b1baf4432`; this repository
  squash-merges, so the commit may become unreachable. Critic adds that
  `check_citation_freshness.py` skips the `gate.py` alias (its
  docstring, lines 19-21), so the deterministic gate never sees these
  cites.
- **CR5 (critic)**, round 2 IT4 deferral. Its reasons are false: PR
  #7014 already rewrites `tmpl:151` and ships mirrors, so the reopen
  trigger has fired.
- **CR7 (critic)**, R3 external bullet. D6's recorded premise ("A PR
  cannot rewrite it, and the launcher string is compared with the
  config") is wider than the facts this review found. Say so for the
  owner to reaffirm.
- **IT5 (independent-thinker)**, R1 no-harness bullet and Negative. The
  shipped Codex and Cursor configs carry a Copilot map (`:30`), so the
  "no Copilot map" condition never holds as shipped. State the outcome
  plainly. "Set neither plugin-root variable" is UNVERIFIED.
- **IT6 (independent-thinker)**, Positive bullet 1. The measurement holds
  only where symlinks are real. A Windows checkout with
  `core.symlinks=false` would block every Copilot payload (INFERRED).
- **IT7 (independent-thinker)**, Alternatives R1. A non-guessing
  contradiction check (exit 2 on `--harness claude_code` with only
  `COPILOT_PLUGIN_ROOT` set) was not weighed.
- **SE6 (security)**, R3 external cite. External return is at
  `gate.py:1787-1794`, not `1785-1791`.
- **AN7 (analyst)**, R3 bullet 2 and untracked bullet. An untracked file
  inside a nested repository goes to `nested`, joins `untrusted`, and
  exits 2 (`gate.py:3071-3078`). Qualify "untracked".
- **AN8 (analyst)**, R1 no-harness bullet. Same as IT5's UNVERIFIED
  plugin-root claim: cite a source or say "not known to set".
- **AN9 (analyst)**, out of scope. A plain token whose path is a
  directory classifies as skip and is never compared under any harness
  (`gate.py:1723-1724`, `1796-1797`). Pre-existing. Record in the PR body,
  not this ADR.
- **HL7 (high-level-advisor)**, Positive bullet 1. No installed-plugin
  run; the text already says so. No edit asked.

### Consensus Points

- All six seats again found the code matches R1, R2, and R3. Every
  round 2 cite resolved (`1534-1555`, `3068-3076`, `3211-3217`,
  `4185-4187`, `4241-4251`, `tmpl:145`, `:149`).
- Architect and independent-thinker reran the real-verifier measurement
  and got the round 2 numbers: 31 checked, 0 untrusted, 0 blocking for
  every harness with the manifest; 11 untrusted without it.
- High-level-advisor ran `TestVerifyConfigOnlyHarnessScope` and
  `TestCopilotLauncherVerification` (37 passed) and
  `tests/build_scripts/test_copilot_launcher.py` (48 passed).
- Critic fetched issue #6506 and confirmed comments 6563759761 (D3, D5)
  and 6564151380 (D6), both by rjmurillo, 2026-11-01. These were
  UNVERIFIED in rounds 1 and 2.
- Every finding is text accuracy. No seat asked for a code change inside
  the amendment's scope.

### Conflicts

- **Severity of the missing-target clause**: analyst P1 (REFUTED claim);
  critic and security P2 (security: a plain deletion runs nothing). No
  ruling needed: one text fix serves all three. The directory variant
  the analyst raised settles the severity question: it runs code (below).
- **Stop iterating**: high-level-advisor recommends stopping after this
  round. The protocol still requires a round 4, because a P1 blocked.

### Review Anti-patterns

- None flagged. Each seat cited lines and separated read, run, and
  unverified evidence.
- No Groundhog Day: no prior-round item was re-raised. AN6 targets text
  the round 2 SE3/AN3 edit added; this is the third round in a row where
  a fix sentence carried a new overclaim. Round 4 seats should read every
  sentence added below against code, not only the cites.
- Evidence limits: security and analyst had no shell. Independent-thinker
  made no GitHub call. Issues #5112, #5520, #5521 stay UNVERIFIED.

### Revisions Made

Consolidator checks before editing (2026-11-01, worktree at `b1baf4432`):

- VERIFIED by reading: `_classify_argv_token` returns skip for a non-file
  (`gate.py:1796-1797`) and external at `1787-1794`; untracked split and
  nested at `3068-3078`; `_launcher_target_verified` returns False for
  skip (`3980-3997`). The launcher calls the interpreter on the path:
  `& $exe @pre (Join-Path $root "{script_rel}") @args`
  (`build/scripts/copilot_launcher.py:99`).
- VERIFIED by run: `python3 <dir>` on a directory named `x.py` holding
  `__main__.py` printed from `__main__.py`, exit 0 (Python 3.15.0). So a
  PR that swaps a tracked launcher target for such a directory runs PR
  code under a wrong `--harness`. Under the right `--harness` the payload
  blocks.
- VERIFIED by run: `get_issue_comments.py --issue 6506` returned 17
  comments. 6564151380 contains "A PR cannot rewrite it, and the launcher
  string is compared with the config." 6563759761 and 6564031218 are
  present, authored by rjmurillo.
- VERIFIED by reading: `pr-review-config.yaml:30` carries `copilot:` in
  `src/codex`, `src/cursor`, and `src/hermes/project-toolkit-delivery`.
  `ADR-101-enforcement-planes.md:145` is rule 4.
- VERIFIED by run: `git branch -r --contains b1baf4432` returned no
  branch. The anchor commit is not on any remote yet.

ADR edits, by issue:

| Issue | Edit |
|-------|------|
| AN6, CR6, SE5 | Residual risk wrong-harness bullet: the fail-open reaches untracked files outside a nested repository, external install files, and missing or non-file paths a PR can produce. Names deletion (runs nothing unless a file appears before dispatch, CWE-367) and the directory-with-`__main__.py` case (runs PR code). Under the right `--harness` the payload blocks. R3 bullet 2 states the same at exit 0. |
| AN7 | R3 bullet 2 and untracked bullet qualified: outside a nested repository; nested untracked exits 2 (`3071-3078`). |
| AR5 | New R3 bullet: external branch is a scoped exception to ADR-101 rule 4, with the R3 revisit trigger as the path back. |
| AR6, HL6 | R1 revisit: states the trigger depends on human observation, names retrospective and transcript review, names an eval scenario as the observable form. |
| AR7, CR4, HL5 | Anchor paragraph: function names are the durable key; resolve by name on `main` if the commit is gone. Re-anchoring line numbers to the squash commit is left to the merge. |
| CR7 | New R3 bullet: quotes the D6 premise, says which parts this review narrowed, and asks the owner to reaffirm D6. |
| IT5, AN8 | R1 no-harness bullet: "are not known to set", no source cited. Adds the shipped `copilot:` maps. New Negative bullet: with the shipped config, Codex, Cursor, and Hermes stop at Step 0 in a consumer install with no tracked `.claude/skills` copy; this PR did not cause it. |
| IT6 | Positive bullet 1: run was Linux with symlinks; Windows `core.symlinks=false` case named, inferred from `gate.py:3996`. |
| IT7 | New Alternatives R1 row: contradiction check, not weighed at D3, kept as a revisit option. |
| SE6 | External cite changed to `gate.py:1787-1794`. |
| CR5 | No ADR edit. IT4 deferral restated below with a true reason. |
| AN9 | No ADR edit, per the seat. Flagged below for the PR body. |
| HL7 | No edit. The text already says no installed plugin was measured. |

### Deferred Findings

| Issue | Priority | Reason | Reopen trigger |
|-------|----------|--------|----------------|
| IT4, CR5: `pr-review.SKILL.md.tmpl:151` exit-0 sentence overstates coverage for install-trusted and external files | P2 | Restated. The round 2 reason was false: PR #7014 already edits that template and ships mirrors. The true reason: this consolidation step is scoped to the ADR text and this log, and a template edit needs `build_all.py` and mirror files in the PR's next commit. The owner decides whether it lands in #7014. | Before PR #7014 merges, or the next commit to the Step 0 text. |
| IT2, AN2: no test pins the approval asymmetry | P2 | Unchanged from round 2. | Unchanged. |
| AN1: no test pins an unpinned symlinked launcher target | P2 | Unchanged from round 2. | Unchanged. |
| CR6: no test pins the deleted-target fail-open under a wrong `--harness` | P2 | Text now documents it. A test is code work outside the ADR. | Any change to `_blocking_tokens` or skip classification. |
| CR4: `check_citation_freshness.py` never checks `gate.py:N` cites | P2 | The alias is the ADR's choice; the validator's scope rule is outside this edit. | Next change to the anchor paragraph or the validator. |

No P1 deferred. AN6 is resolved by edit.

Flagged, out of scope (AN9, for the PR #7014 body and the owner's
decision): a plain `scripts` token whose path is a directory classifies
as skip and is never compared, under any harness (`gate.py:1723-1724`,
`1796-1797`). Python runs a directory holding `__main__.py` (verified
above). So a PR that replaces a tracked plain-token script with such a
directory runs uncompared code at dispatch, under the right harness too.
This predates the amendment and is a trust-gate defect, not a text gap.
Not fixed here: it is outside the owner's D3, D5, and D6 rules.

No code changed this round, so no test run was needed.

### Round 3 Result

- **Consensus**: No. Analyst blocked on AN6.
- **Revised**: Yes. AN6 and every P2 except the deferred and flagged
  items have an edit.
- **Next**: round 4 convergence check by all six seats. Seats should
  read every sentence added this round against code: the wrong-harness
  bullet, R3 bullets 2, 5, and 6, the R1 no-harness bullet, the new
  Negative bullet, and the R1 revisit text.

## Round 4

**Date**: 2026-11-01. **Text reviewed**: the amendment after the round 3
revisions, against `run_completion_gate.py` at `b1baf4432` (2026-11-01).
Worktree state: only the ADR edit and this log are uncommitted.

### Agent Positions

| Agent | Position | P0 | P1 | P2 | Dissent |
|-------|----------|----|----|----|---------|
| architect | Accept | 0 | 0 | 3 | none |
| critic | Accept | 0 | 0 | 3 | none |
| independent-thinker | Accept | 0 | 0 | 4 | none |
| security | Accept | 0 | 0 | 5 | none |
| analyst | Accept | 0 | 0 | 5 | none |
| high-level-advisor | Accept | 0 | 0 | 4 | none |

No seat used Disagree-and-Commit. No dissent to record.

### Issues Raised

No P0. No P1. All findings are P2.

Text accuracy in the ADR:

- **R4-CITE (critic, independent-thinker, security, analyst,
  high-level-advisor)**, Consequences Positive bullet 1, ADR line 316,
  "inferred from `gate.py:3996`". Wrong line. The Windows
  `core.symlinks=false` case classifies as skip (`1796-1797`) and returns
  False at `3997`. Line 3996 is the external return. Consolidator
  VERIFIED by reading `gate.py:3992-3997`. Critic adds a mechanism gap:
  `.claude/skills/pr-review` and `.claude/skills/github` are mode 120000
  links, so with symlinks off in-repo Step 0 may not reach the gate at
  all (`tmpl:112-138` resolution falls back to an installed plugin or a
  missing path). The outcome is still a stop.
- **R4-D6 (critic, security, analyst)**, R3 bullet 6, ADR lines 271-278,
  "The owner should reaffirm D6 with them in view." An open action in a
  durable ADR with no recorded outcome. Security: the panel cannot accept
  the sibling-checkout CWE-829 risk for the owner. Fix: record the
  owner's answer (comment ID, date) or record D6 as unreaffirmed.
- **R4-AN9SCOPE (architect, security)**, Residual risk wrong-harness
  bullet, ADR lines 388-401. "Under the right `--harness` the payload
  blocks" and "the exposure today is the Copilot map under a wrong
  `--harness claude_code`" hold for launcher payloads only. AN9 (plain
  token, directory with `__main__.py`) runs uncompared under the right
  harness too. Fix: one scope clause pointing to the AN9 flag.
- **R4-UNTRACKED (independent-thinker)**, R3 bullet 2. "An untracked
  script outside a nested repository, or a missing script, leaves the
  payload blocking at exit 0" holds only under the right or no
  `--harness`; `_blocking_tokens` drops it under a wrong one
  (`4077-4078`). Apply the harness qualifier to all three cases.
- **R4-EXTERNAL (security)**, Residual risk wrong-harness bullet, lines
  383-385. External install files count as verified under every harness
  (`1787-1794`, `3995-3996`), so a wrong `--harness` adds no exposure for
  them. Drop them from that list or say they pass under any harness.
- **R4-RULE4 (security)**, R3 bullet 5, lines 266-270. "The installed
  file sits outside the plane the PR author writes" lacks the
  sibling-checkout qualifier that R3 bullet 4 and Residual risk bullet 4
  carry. Risk score 3/10.
- **R4-ONLY (analyst)**, R1 no-harness bullet (line 150) and Negative
  bullet 5. "Supported there only with no Copilot map, or with that copy
  committed" omits a third route: a plugin-root variable naming a real
  install makes the target external and verified (`1592-1597`,
  `1787-1789`, `3995-3996`). Fails closed; overstates a stop.
- **R4-COPILOT-ENV (high-level-advisor)**, Positive bullet 1 and Negative
  bullet 5. The Copilot consumer benefit of R2 depends on
  `COPILOT_PLUGIN_ROOT` or `CLAUDE_PLUGIN_ROOT` reaching the agent's
  shell. `agent-harness-reference` SKILL.md:192 documents them for hooks
  only. Add a conditional consequence. Distinct from round 3 HL7.
- **R4-REFS (analyst)**, References, lines 423-429. ADR-101 and ADR-119
  are relied on (R3 declares an ADR-101 rule 4 exception) but not listed.
- **R4-TESTLIST (analyst)**, R3 Tests bullet, lines 282-287.
  `test_missing_script_stays_blocking` (test file line 2438) pins the
  right-harness missing-target block but is missing from the list. CR6
  narrows to the wrong-harness case only.
- **R4-NOTEST (independent-thinker)**, Residual risk wrong-harness
  bullet. The directory-target case carries no "no test pins it" label,
  unlike other code-read claims in the amendment.

Outside the ADR text, before PR #7014 merges:

- **R4-IT4 (architect, critic, independent-thinker)**, deferred IT4/CR5,
  `templates/skills/pr-review.SKILL.md.tmpl:151`. Its reopen trigger
  "Before PR #7014 merges" fires now under D8. The owner must land the
  template edit or carry the deferral past merge with a new trigger.
- **R4-AN9BODY (architect, high-level-advisor)**, PR #7014 body. Both
  seats searched the body with `get_pr_context.py` on 2026-11-01 and
  found no AN9 flag. High-level-advisor: the body (3977 chars) does not
  mention ADR-059, the amendment, or `--harness`.
- **R4-PRSCOPE (high-level-advisor)**, PR #7014 body. It describes only
  the two original follow-ups, not D3, D5, D6, or the amendment, so a
  merger cannot see that the PR widens what the trust gate accepts.

### Consensus Points

- All six seats read every sentence round 3 added against code and found
  no new overclaim of a control's strength. Cites that resolved across
  seats: `1645`, `1674`, `1787-1794`, `1796-1797`, `1833-1838`,
  `3071-3078`, `3205-3217`, `3925`, `3980`, `3997`, `4000`, `4016`,
  `4043-4054`, `4064`, `4077-4078`, `4177-4181`, `4185-4187`,
  `4239-4251`, `4261-4270`, `tmpl:145/149/151/153`,
  `copilot_body_translation.py:395`, `ADR-101:128/142/145`.
- AN6 (round 3 P1) is resolved: deletion and non-file targets skip,
  block under the right harness, and drop under a wrong one, as written.
- Architect ran `TestVerifyConfigOnlyHarnessScope` and
  `TestCopilotLauncherVerification`: 37 passed. Other seats did not run
  tests; no code changed since round 3.
- Every remaining finding is P2 and fails closed in the ADR text, or sits
  outside the ADR (template line 151, PR body).

### Conflicts

- None on position. Seats differ only on where AN9 should be scoped
  (ADR clause versus PR body only). Architect and security want a scope
  clause in the ADR; high-level-advisor says the ADR is right to leave
  AN9 out and the PR body is the surface. Both can land; no ruling
  needed at P2.

### Review Anti-patterns

- None flagged. Each seat separated read, run, and unverified evidence.
- No Groundhog Day: IT4 recurs, but as a trigger that now fires, not a
  re-litigation. Seats said so explicitly.
- Convergent finding: five of six seats found the same off-by-one cite
  independently. That is a signal the round 3 fix sentence was not read
  against code before edit, the pattern round 3 named.
- Evidence limits: security and analyst had no shell. Critic did not
  fetch the PR #7014 body. Issues #5112, #5520, #5521 stay UNVERIFIED.
  The real-verifier measurement was not rerun this round.

### Revisions Made

None. Consensus reached, so the debate closes this round. Per
`debate-protocol.md#round-cap`, a closed log takes no further round, and
any later ADR edit starts a new debate in a new log. The P2 text fixes
above are recorded as recommendations, not applied. No code changed, so
no test run was needed by the consolidator.

### Deferred Findings

| Issue | Priority | Reason | Reopen trigger |
|-------|----------|--------|----------------|
| R4-CITE, R4-D6, R4-AN9SCOPE, R4-UNTRACKED, R4-EXTERNAL, R4-RULE4, R4-ONLY, R4-COPILOT-ENV, R4-REFS, R4-TESTLIST, R4-NOTEST: ADR text accuracy | P2 | Consensus closes the log. Editing the ADR now would open a new debate (`debate-protocol.md#round-cap`). Owner decides whether to apply them in PR #7014 under a new log or later. | Next edit to the ADR-059 amendment. |
| R4-IT4 (was IT4/CR5): `tmpl:151` exit-0 sentence | P2 | Trigger "before PR #7014 merges" is live. Owner disposition required: land the edit, or carry it past merge with a new trigger. | Before PR #7014 merges. |
| R4-AN9BODY, R4-PRSCOPE: PR #7014 body | P2 | Outside ADR text. PR body edits are the owner's or the PR author's step. | Before PR #7014 merges. |
| IT2/AN2, AN1, CR6, CR4 | P2 | Unchanged from round 3. CR6 narrows to the wrong-harness case (R4-TESTLIST). | Unchanged. |

No P1 deferred.

### Round 4 Result

- **Consensus**: Yes. Six of six Accept, no Disagree-and-Commit.
- **Revised**: No.
- **Next**: debate closed.

## Closing Summary

**Outcome**: Consensus in round 4 of 10. All six seats Accept. The
ADR-059 Amendment (2026-11-01) stands as revised through round 3.

**Dissent captured**: none. No seat used Disagree-and-Commit in any round.

**What the debate settled**:

- R1 (`--harness` scoping, D3), R2 (Copilot launcher recognition, D5),
  and R3 (install-trusted launcher targets, D6) match the code at
  `b1baf4432`.
- Every fail-open the panel found is now stated in Residual risk: the
  wrong-harness drop, deletion and non-file targets, the sibling-checkout
  plugin root.
- Tests run during the debate: 37 passed (`TestVerifyConfigOnlyHarnessScope`
  plus `TestCopilotLauncherVerification`, rounds 3 and 4) and 48 passed
  (`tests/build_scripts/test_copilot_launcher.py`, round 3).

**Recommendations to the owner, before PR #7014 merges**:

1. Answer D6 reaffirmation (R4-D6). The ADR says the owner "should
   reaffirm D6". Record the answer with comment ID and date, or record D6
   as unreaffirmed. The panel cannot accept the CWE-829 sibling-checkout
   risk on the owner's behalf.
2. Decide IT4 (R4-IT4). `tmpl:151` still says exit 0 means the files
   match the trusted ref. Land the edit with `build_all.py` mirrors, or
   carry it past merge with a new trigger.
3. Surface AN9 in the PR #7014 body (R4-AN9BODY). A plain `scripts`
   token whose path becomes a directory holding `__main__.py` runs
   uncompared PR code under every harness (`gate.py:1796-1797`). It
   predates this amendment. Security rates it about CVSS 7.8.
4. Update the PR #7014 body to name D3, D5, D6, and the amendment
   (R4-PRSCOPE).
5. Apply the eleven ADR text P2s in one pass if the ADR is edited again.
   That edit opens `ADR-059-debate-log-3.md`. Highest value: R4-CITE
   (five seats), R4-AN9SCOPE, R4-UNTRACKED, R4-ONLY.

**Planning**: no milestone or task decomposition needed. The amendment
documents code already in PR #7014.
