# ADR Debate Log: ADR-059 /pr-review Completion Gate Dispatcher and pass_when DSL

## Summary

- **Rounds**: 4 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-059-debate-log.md`
- **Outcome**: Consensus. Round 1 had no consensus (analyst Block, P1).
  Round 2 had no consensus (analyst Block, high-level-advisor Block, one
  P1 each). Round 3 had no consensus (analyst Block, one P1). Round 4:
  all six seats Accept, no P0 or P1. The debate is closed.
- **Final Status**: accepted (frontmatter status before this debate)

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-059-pr-review-completion-gate-dispatcher.md`
- **Edit**: new section "Amendment 2026-11-01: Step 0 verify-only trust rules".
  Decision items 1 to 6 are unchanged. Round 1 set the frontmatter
  `date` to 2026-11-01 (architect P2).
- **PR**: #7014, branch `fix/6506-batch7-merge-pr-automation-2`.
- **Code under the rules**: `src/claude/skills/github/scripts/pr/run_completion_gate.py`
  at commit `b1baf4432` (2026-11-01).
- **Owner decisions recorded**: D3, D5, and D6 on issue #6506, comments
  6563759761 and 6564151380 (2026-11-01).
- **Trigger**: the architect review of PR #7014 returned WARN. It found
  that D5 and D6 widen what the trust gate accepts with no ADR behind them.
  Owner decision D8 (2026-11-01) directs this amendment and a full debate
  inside PR #7014 before merge.

Rules under review:

- **R1 (D3)**: the Step 0 stop blocks only on unverifiable tokens from the
  running harness's `scripts` map. Tokens from other maps are reported and
  do not stop. No `--harness` blocks on every token. An unknown harness
  exits 2.
- **R2 (D5)**: a Copilot launcher counts as the plain token for its script
  only when it re-renders byte for byte with the shipped recipe. The port in
  the gate is pinned to `build/scripts/copilot_launcher.py` by a test. Words
  after the launcher must be inert.
- **R3 (D6)**: a launched script inside the work tree must be tracked and
  match the trusted ref. A script under an installed plugin root outside the
  work tree is accepted with no byte comparison, matching the plain-token
  rule from issue #5112.

Panel: full panel (architect, critic, independent-thinker, security,
analyst, high-level-advisor). The amendment records rules of an executable
trust gate, which the AGENTS.md ADR review rule routes to the full panel.

## Carried Forward From Prior Log

The prior log closed with Accept on 2026-05-08. Its one P2 item, AND/OR
evaluation order, was added to the ADR text in that debate. No unresolved
issue carries forward.

Input for round 1 from outside the prior log: the architect WARN findings
on PR #7014 (launcher port reads private names, two launcher recognition
sites, second `git rev-parse`, build-time `--harness` only for Copilot).
The amendment lists them under Consequences, Negative.

## Round 1

**Date**: 2026-11-01. **Text reviewed**: the amendment as first drafted,
against `run_completion_gate.py` at `b1baf4432` (2026-11-01).

### Agent Positions

| Agent | Position | P0 | P1 | P2 | Dissent |
|-------|----------|----|----|----|---------|
| architect | Accept | 0 | 0 | 4 | none |
| critic | Accept | 0 | 0 | 3 | none |
| independent-thinker | Accept | 0 | 0 | 4 | none |
| security | Accept | 0 | 0 | 4 | none |
| analyst | Block | 0 | 1 | 3 | none |
| high-level-advisor | Accept | 0 | 0 | 3 | none |

### Issues Raised

P1:

- **A1 (analyst)**, Residual risk bullet 3; `gate.py:4064-4081`. The wrong
  `--harness` risk was stated only as over-blocking. A wrong but valid
  value drops the running map's tokens, so they reach evaluation with
  their files uncompared. Same finding at P2 from independent-thinker
  (IT1).

P2, grouped by theme:

- **Enforcement strength** (architect AR1, security S2, high-level-advisor
  H1). "Every new branch fails closed: block or exit 2" mixes a gate exit 2
  with an agent-read list at exit 0 (`gate.py:4261-4270`). Cite ADR-101,
  split the bullet, name the agent-ignores-the-list risk (ASI01).
- **Missing alternatives** (architect AR2, independent-thinker IT2). No
  rejected option per rule R1 to R3.
- **Stale frontmatter date** (architect AR3). `date` stayed 2026-05-08.
- **No reversibility or revisit trigger** (architect AR4, high-level-advisor
  H3).
- **Launcher stricter than plain token for untracked files** (critic C1).
  `gate.py:182-187` skips an untracked plain token; the launcher blocks.
- **Environment binding between Step 0 and dispatch** (critic C2,
  independent-thinker IT4, security S3). CWE-367.
- **"Inert" tail overstated** (critic C3). `_LAUNCHER_TAIL_RE` admits
  `{`, `}`, `.`, so brace expansion can change argv.
- **Second rev-parse outcome unstated** (independent-thinker IT3, security
  S4). Disagreement fails closed.
- **"Cannot rewrite that file" too flat** (security S1). False when the
  plugin root names another checkout of this repository. CWE-829.
- **No-harness path may mean unsupported** (analyst A2). Needs a run on the
  shipped config.
- **Tail rule is gate-only** (analyst A3). Stricter than the renderer, not
  pinned by the port test.
- **Diverged script path not observable** (analyst A4). A diverged tracked
  script exits 2 through R1 before any payload is classified.
- **Measured effect** (high-level-advisor H2). Replace "no longer stop on
  every launcher" with token counts.

### Consensus Points

- All six seats found the code matches R1, R2, and R3. Every cited
  `gate.py` range, test name, and test range checked out.
- No seat challenged the owner decisions D3, D5, or D6.
- Every finding is about the text, not the code. No code change was needed.

### Conflicts

- One position conflict: the analyst rated the wrong-harness gap P1
  (Block); independent-thinker rated the same gap P2 (Accept). No ruling
  was needed. The fix both asked for is the same one or two sentences, and
  it landed this round.

### Review Anti-patterns

- None flagged. Each seat checked code against text and cited lines.
- Five seats converged on overlapping text gaps (enforcement strength,
  environment binding, rev-parse outcome). That is independent agreement,
  not Groundhog Day: no prior-log item was re-raised.
- Evidence limits stated by the seats: security had no shell and could not
  confirm the worktree commit. Critic, analyst, and high-level-advisor made
  no GitHub call. Issue #6506 comments 6563759761 and 6564151380, and
  issues #5112, #5520, #5521, stay UNVERIFIED for round 2.

### Revisions Made

Consolidator checks before editing (2026-11-01, `b1baf4432`):

- VERIFIED by reading: `_blocking_tokens` skips `owner != harness`
  (`gate.py:4077`); verify-only returns 0 after `_report_verify_only`
  (`gate.py:4261-4270`); diverged script halts at `gate.py:4239-4240`;
  both rev-parse calls use `_PROJECT_ROOT` (`gate.py:3022`, `4007`);
  build-time `--harness copilot` at `copilot_body_translation.py:395`.
- VERIFIED by run: imported the gate on the shipped
  `pr-review-config.yaml`. `_unverifiable_by_harness` with no verifier: 11
  tokens, all `copilot`. With every launcher target verified: 0. With no
  harness and targets verified, `_blocking_tokens` returns 0. This resolves
  A2: no-harness passes on the shipped config, so it is not "unsupported".

ADR edits, by issue:

| Issue | Edit |
|-------|------|
| A1, IT1 | Residual risk bullet rewritten: a wrong but valid `--harness` fails open for the running map's tokens. Bound named: command strings still config-compared; Copilot gets the value at build time; shipped `claude_code` map has no unverifiable token. Positive bullets now name this one fail-open branch. |
| AR1, S2, H1 | New R1 bullet: two strengths, exit 2 gate-enforced, blocking list agent-enforced at exit 0, advisory per ADR-101 rule 1. Positive bullet split into gate-enforced and agent-enforced. New Residual risk: agent ignores the list (ASI01). |
| AR2, IT2 | New "Alternatives considered" table, five rows across R1 to R3, including gate-derived harness and shipping the launcher module. |
| AR3 | Frontmatter `date: 2026-11-01`; Date section reads "2026-05-08, amended 2026-11-01". |
| AR4, H3 | New "Reversibility and revisit" section: code-only revert, R2 revisit if `build/` ships, R3 revisit trigger. |
| C1 | New R3 bullet: launcher stricter than plain token for untracked files, with reason and a do-not-loosen note. R2 bullet points to it. |
| C2, IT4, S3 | New Residual risk bullet: verdict holds only for Step 0 environment, files, and working directory (CWE-367). |
| C3 | R2 tail bullet narrowed to "cannot run code or reach another script", names brace expansion. |
| IT3, S4 | Negative bullet now states disagreement fails closed, marked as read from code with no test. |
| S1 | R3 text qualified to "through this work tree"; new Residual risk bullet for another checkout of the same repository (CWE-829). |
| A2 | R1 no-harness bullet: not unsupported, backed by the measured run. |
| A3 | New R2 bullet: tail rule and prefix argv are gate-only and stricter than the renderer. |
| A4 | R3 bullet split: diverged tracked script exits 2 via R1; untracked, missing, symlinked block. |
| H2 | Positive bullet carries the 11-to-0 measurement and says R1 is preventive today. |

Deferred: none. No P1 deferral.

Not changed: the D3, D5, and D6 rules. No code changed, so no test run
was needed for this round's edits.

### Round 1 Result

- **Consensus**: No. Analyst blocked on A1.
- **Revised**: Yes. Every P1 and P2 above has an edit.
- **Next**: round 2 convergence check by all six seats on the revised
  amendment. Seats must verify claims added this round, including the
  11-to-0 measurement and the new line cites (`gate.py:182-187`,
  `1582-1598`, `3022`, `4007`, `4239-4240`, `4261-4270`).

## Round 2

**Date**: 2026-11-01. **Text reviewed**: the amendment after the round 1
revisions, against `run_completion_gate.py` at `b1baf4432` (2026-11-01).

### Agent Positions

| Agent | Position | P0 | P1 | P2 | Dissent |
|-------|----------|----|----|----|---------|
| architect | Accept | 0 | 0 | 2 | none |
| critic | Accept | 0 | 0 | 3 | none |
| independent-thinker | Accept | 0 | 0 | 4 | none |
| security | Accept | 0 | 0 | 4 | none |
| analyst | Block | 0 | 1 | 4 | none |
| high-level-advisor | Block | 0 | 1 | 3 | none |

### Issues Raised

P1:

- **AN1 (analyst)**, R3 bullet 2; `gate.py:1764-1765`, `3078`,
  `3135-3143`, `4239-4240`. REFUTED claim from the round 1 A4 edit: "an
  untracked, missing, or symlinked script leaves the payload blocking". An
  unpinned in-tree symlink classifies as escapes, joins `untrusted`, and
  halts with exit 2 before any payload is classified. Same finding at P2
  from critic (CR1, adds the ADR-119 pinned-link exception,
  `gate.py:1534-1541`), independent-thinker (IT3), security (SE1), and
  high-level-advisor (HL2).
- **HL1 (high-level-advisor)**, R1 no-harness bullet, Positive 11-to-0
  bullet, round 1 "This resolves A2". The 11-to-0 run stubbed the
  verifier. For Codex, Cursor, and Hermes the launcher target falls back
  to `.claude/skills/github/...`. The seat inferred that this halts with
  exit 2 in this repository (ADR-119 symlink) and blocks in a plugin
  install with no `.claude` copy. Same measurement gap at P2 from analyst
  (AN4).

P2:

- **AR1 (architect)**, R3 untracked bullet. Cite `gate.py:3068-3076`, the
  code, not `182-187`, the docstring.
- **AR2 (architect)**, Alternatives R1 row 1 and Reversibility. The
  "changes the exit contract" reason is thin: the blocking list is empty
  on the shipped config. Name the real cost or defer. Add an R1 revisit
  trigger.
- **CR2 (critic)**, R1 advisory bullet. The "advisory" rating comes from
  the ADR-101 plane table (`ADR-101-enforcement-planes.md:128`), not only
  rule 1 (`:142`).
- **CR3 (critic), SE4 (security), HL4 (high-level-advisor)**, Residual
  risk bullet 5. `{harness}` placeholder is at `tmpl:145`, not `:149`.
- **IT1 (independent-thinker)**, R3 external bullet and Residual risk.
  "Compared as part of the config" is false under install trust
  (`gate.py:871-892`) and under `--approve-untrusted-config`.
- **IT2 (independent-thinker), AN2 (analyst)**. Approval lets a diverged
  plain token through, but a launcher for the same file stays blocked
  (`gate.py:3993-3994`). Second launcher asymmetry, undocumented and
  untested.
- **IT4 (independent-thinker)**, `templates/skills/pr-review.SKILL.md.tmpl:151`.
  The exit-0 sentence overstates coverage for install-trusted and external
  files.
- **SE2 (security)**, R2 tail bullet; `pr-review-config.yaml:62-63`.
  "Tail cannot run code" holds only for the stored template. `{body}` is
  attacker-written comment text filled at dispatch (CWE-78). Predates the
  amendment and applies to every map.
- **SE3 (security), AN3 (analyst)**, Residual risk bullet 5. The
  wrong-harness bound omits that the union check still exits 2 on a
  PR-modified tracked target (`gate.py:1833-1838`, `4239-4240`).
- **AN5 (analyst)**, R1 bullet 5. `gate.py:4241-4250` misses the
  `return 2` at 4251.
- **HL3 (high-level-advisor)**. Name the pre-existing dogfood halt under
  `claude_code` with `CLAUDE_PLUGIN_ROOT` unset.

### Consensus Points

- All six seats again found the code matches R1, R2, and R3. No seat
  challenged D3, D5, or D6.
- Every round 1 edit landed and was confirmed in text and code.
- Five seats independently found the symlink misfiling. Four seats found
  the wrong-harness or config-trust bound worded wrong. All findings are
  text accuracy; no seat asked for a code change.

### Conflicts

- **Severity of the symlink finding**: analyst P1 (REFUTED claim blocks
  per the verification block); critic, independent-thinker, security, and
  high-level-advisor P2 (the error understates a control that fails
  closed). No ruling needed: one fix serves both.
- **Dogfood path (HL1, HL3 vs IT3)**: high-level-advisor inferred that
  this repository halts with exit 2 because `.claude/skills/github` is a
  symlink. Independent-thinker observed that `main` loads the ADR-119
  pinned-link manifest (`gate.py:4185-4187`) and the token then classifies
  as `verify`. Settled by a consolidator run (below): independent-thinker
  is right. HL3 is refuted and gets no ADR edit. HL1's measurement and
  consumer-install points stand and are fixed.

### Review Anti-patterns

- None flagged. Each seat cited code lines and separated read, run, and
  unverified evidence.
- HL1 and HL3 rested on a run with the pinned-link manifest unset, while
  `main` always sets it. That is a reproduction gap, not an anti-pattern:
  the seat marked the halt INFERRED and named why it could not run end to
  end.
- No prior-round item was re-raised (no Groundhog Day). The symlink
  finding is new: it targets text the round 1 A4 edit introduced.
- Evidence limits: no seat made a GitHub call. Issue #6506 comments
  6563759761 and 6564151380, and issues #5112, #5520, #5521, stay
  UNVERIFIED. Security and analyst had no shell.

### Revisions Made

Consolidator checks before editing (2026-11-01, worktree at `b1baf4432`,
`origin/main` at `8dd4f43d5`, plugin-root variables unset):

- VERIFIED by reading: `gate.py:1764-1765` (symlink returns escapes),
  `3068-3076` (untracked split), `3078` (escaping joins `untrusted`),
  `3135-3143` (untrusted status), `3195-3217` (halt, or return with no
  halt under approval), `871-892` (install trust, no byte comparison),
  `1534-1555` (pinned link followed), `3993-3994`, `4185-4187` (manifest
  loaded in `main`), `4251` (`return 2`), `tmpl:145` and `:149`,
  `ADR-101-enforcement-planes.md:128` and `:142`.
- VERIFIED by run: `_classify_argv_token` on
  `.claude/skills/github/scripts/pr/add_pr_review_thread_reply.py`
  returns `escapes` with no manifest and `verify` (as the `src/claude`
  path) with the `origin/main` manifest loaded.
- VERIFIED by run, real `_launcher_verifier`, shipped config, trusted ref
  `origin/main`: with the manifest, command trust `trusted`, 31 checked,
  0 untrusted, 0 unverifiable, `_blocking_tokens` 0 for no harness,
  `claude_code`, and `copilot`. Without the manifest: `untrusted`, 11
  untrusted files, 11 unverifiable (all `copilot`). This run bypassed the
  config check: the branch config differs from `origin/main` by 4 lines.
  An installed plugin was not measured.
- VERIFIED by run: a missing in-tree target classifies as skip, and
  `_launcher_target_verified` returns False, so its payload blocks.
- `HEAD` as the trusted ref loads no pinned links, so the HEAD run is not
  used as evidence.

ADR edits, by issue:

| Issue | Edit |
|-------|------|
| AN1, CR1, IT3, SE1, HL2 | R3 bullet 2: unpinned symlink moves to the exit-2 sentence with the diverged case, cited `1764-1765`, `3078`. Both exits hold unless approval is given. Only untracked and missing block at exit 0. New bullet: pinned links are followed and byte-compared (`1534-1555`), `main` loads the manifest (`4185-4187`), and in-tree R3 depends on it in this repository. |
| HL1, AN4 | R1 no-harness bullet rewritten: no-harness passes only when the `.claude` fallback files are tracked, reached through real directories or pinned links, and match the trusted ref. True here; false in a consumer repository with no tracked `.claude/skills` copy, where every Copilot payload blocks. Positive bullet 1 replaced with the real-verifier measurement, its config-check bypass, and no installed-plugin measurement. |
| AR1 | Untracked cite changed to `gate.py:3068-3076`. |
| AR2 | R1 row 1 now "Deferred, not refuted", with the real costs. New R1 revisit trigger: first agent seen proceeding on a non-empty list. |
| CR2 | Advisory rating cites the plane table `:128` and rule 1 `:142`. |
| CR3, SE4, HL4 | Cite is now `tmpl:145`, guidance at `:149`. |
| IT1 | R3 external bullet and Residual risk: launcher string bounded by config trust, which is compared, install-trusted (`871-892`), or human-approved. |
| IT2, AN2 | New R3 bullet: approval unblocks a plain token but not a launcher payload (`3211-3217`, `3993-3994`), fails closed, no test. R2 bullet now names two differences. |
| SE2 | R2 tail bullet scoped to the stored config, before substitution. Names `{body}` as attacker text and quoting as the agent's job in every map (CWE-78). |
| SE3, AN3 | Residual risk wrong-harness bullet: the union check still exits 2 on a PR-modified tracked target; the fail-open reaches only untracked, missing, or external targets. |
| AN5 | Cite changed to `gate.py:4241-4251`. |
| HL3 | No edit. Refuted by run: `main` loads the manifest, and the dogfood tree gives 0 blocking for every harness. |

### Deferred Findings

| Issue | Priority | Reason | Reopen trigger |
|-------|----------|--------|----------------|
| IT4: `pr-review.SKILL.md.tmpl:151` exit-0 sentence overstates coverage | P2 | A skill-template change needs a build and mirror commit, outside this ADR edit. | Next edit to the Step 0 text in the pr-review template. |
| IT2, AN2: no test pins the approval asymmetry | P2 | Text records it as read from code. A test is code work outside the ADR. | Any change to `_launcher_target_verified` or approval handling. |
| AN1: no test pins an unpinned symlinked launcher target | P2 | Same as above. | Any change to `_classify_argv_token` or launcher recognition. |

No P1 deferred. No code changed, so no test run was needed.

Validators run on the edited ADR: `check_adr_links.py` 0 violations;
`check_adr_lifecycle.py` PASS (none outside baseline). A dash and
banned-word scan of the ADR diff found none.
`check_citation_freshness.py --base origin/main` examined 0 citations: it
reads committed lines, and the edit is uncommitted. The cites were
checked by reading instead.

### Round 2 Result

- **Consensus**: No. Analyst (AN1) and high-level-advisor (HL1) blocked.
- **Revised**: Yes. Both P1s and every P2 except the three deferred above
  have an edit.
- **Next**: round 3 convergence check by all six seats. Seats should
  verify the new cites (`1534-1555`, `3068-3076`, `3211-3217`,
  `4185-4187`, `4241-4251`, `tmpl:145`) and the real-verifier
  measurement.

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
