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


Continued in part 2:
`.project-toolkit/critique/ADR-059-debate-log-2-part-2.md` (rounds 3 and 4,
closing summary). The split is D11 (2026-11-01): one debate, one log, two
files under the 500-line cap. No recorded content changed.
