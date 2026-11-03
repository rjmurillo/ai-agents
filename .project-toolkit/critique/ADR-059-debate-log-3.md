# ADR Debate Log: ADR-059 /pr-review Completion Gate Dispatcher and pass_when DSL (third debate)

## Summary

- **Rounds**: 4 of 10. Rounds 1 to 3 ended without consensus; round 4
  reached it. Round 3 onward and the closing summary are in part 2:
  `.project-toolkit/critique/ADR-059-debate-log-3-part-2.md`.
- **Prior debate log**: `.project-toolkit/critique/ADR-059-debate-log-2.md`
  (part 1; part 2 is `.project-toolkit/critique/ADR-059-debate-log-2-part-2.md`)
- **Outcome**: Consensus. Round 1: one Accept, five Block. Round 2: two
  Accept, two Disagree-and-Commit, two Block. Round 3: five Accept, one
  Block. Round 4: six Accept.
- **Final Status**: accepted

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-059-pr-review-completion-gate-dispatcher.md`
- **Edit**: revision of "Amendment 2026-11-01: Step 0 verify-only trust
  rules". Decision items 1 to 6 are unchanged. Frontmatter is unchanged:
  `status: accepted`, `date: 2026-11-01`.
- **PR**: #7014, branch `fix/6506-batch7-merge-pr-automation-2`.
- **Code under the rules**: `src/claude/skills/github/scripts/pr/run_completion_gate.py`
  at commit `0d89522f8` (2026-11-02), which landed D10 and the D11 template
  fix on top of the prior ADR commit `2775c0eae` (2026-11-01).
- **Owner decisions**: D10 and D11, made on 2026-11-01 in the PR #7014
  working session. No issue comment records them; the ADR says so.
- **Trigger**: any edit to the amendment opens a new debate
  (`debate-protocol.md#round-cap`). The prior log closed in its round 4
  and recommended this edit in its closing summary, item 5.

Changes under review:

1. **R3 rewritten for D10.** D10 narrows D6. An external file in another
   work tree of this repository is verified like an in-tree file, or it
   blocks. Same repository means the same `git rev-parse --git-common-dir`
   or the same normalized origin URL. A true install, or a work tree of
   another repository, keeps #5112 install trust. A named file git does not
   track in the sibling blocks. Git failures while probing exit 3. New
   Alternatives rows, Positive and Negative bullets, a rewritten
   sibling-checkout Residual risk bullet, a D10 revert path, and a D10
   revisit trigger.
2. **Owner record.** R3's "the owner should reaffirm D6" bullet now records
   the answer: D10, dated 2026-11-01. D6 holds for true installs only.
3. **IT4 fix noted.** `templates/skills/pr-review.SKILL.md.tmpl:151` now
   says installed-plugin scripts are install-trusted, not compared. It
   shipped with mirrors in `0d89522f8`. The ADR notes it under
   "Step 0 text (D11)".
4. **P2 text corrections from the prior log (R4 round).**
   - R4-CITE: the Windows `core.symlinks=false` case now cites the skip
     branch and the `return False`, not the external return.
   - R4-D6: answered by item 2.
   - R4-AN9SCOPE: the wrong-harness bullet now says its bound covers
     launcher payloads only, and names the plain-token directory case.
   - R4-UNTRACKED: the harness qualifier now covers the untracked,
     missing, and non-file cases.
   - R4-EXTERNAL: true-install files are dropped from the wrong-harness
     list; the bullet says they verify under every harness.
   - R4-RULE4: the ADR-101 rule 4 exception now says D10 removes
     sibling checkouts from it for scripts, not for the config.
   - R4-ONLY: the no-harness bullet names the third route, a plugin-root
     variable naming a true install.
   - R4-COPILOT-ENV: new Negative bullet on plugin-root variables reaching
     the agent's shell.
   - R4-REFS: ADR-101 and ADR-119 added to References.
   - R4-TESTLIST: `test_missing_script_stays_blocking` added to the R3
     test list.
   - R4-NOTEST: the directory case now says what a test pins (the gate's
     skip, through `TestWrongHarnessDropsTheMissingTarget`) and what no
     test pins (Python running the directory).
5. **Cites re-anchored.** Every `gate.py:N` cite moved from `b1baf4432` to
   `0d89522f8`, read against the code line by line. The two stale config
   cites that failed `Citation Freshness` are fixed: the Codex
   `pr-review-config.yaml:30` cite and `verify_config_only_exits` at
   `src/claude/skills/pr-review/pr-review-config.yaml:116-120`. The Hermes
   copy path is corrected to `src/hermes/project-toolkit-delivery/`.
6. **Test claims updated.** IT2/AN2 (approval asymmetry) is now pinned by
   `TestApprovalNeverUnblocksALauncher`. CR6 (wrong-harness missing
   target) is now pinned by `TestWrongHarnessDropsTheMissingTarget`. The
   ADR drops its "no test pins it" label for both.
7. **Log split (D11).** `ADR-059-debate-log-2.md` was 753 lines, over the
   500-line taste cap. It is now part 1 (372 lines: summary through round
   2) and `ADR-059-debate-log-2-part-2.md` (394 lines: rounds 3 and 4 and
   the closing summary). The split adds a link line in part 1 and a header
   in part 2; every recorded line is unchanged. The original path stays
   part 1, so this log's "Prior debate log" field names it. Names were
   checked against `scripts/validation/git_hook_policy.py`: a debate log
   is any `.md` directly under `.project-toolkit/critique/` whose name
   contains `debate`. No parser keys on a numeric suffix, and
   `detect_adr_changes.py` does not read debate logs.

Panel: full panel (architect, critic, independent-thinker, security,
analyst, high-level-advisor). The edit records rules of an executable
trust gate, which the AGENTS.md ADR review rule routes to the full panel.

## Carried Forward From Prior Log

| Item from log 2 | Priority | State at the start of this debate |
|-----------------|----------|-----------------------------------|
| R4-CITE, R4-UNTRACKED, R4-EXTERNAL, R4-RULE4, R4-ONLY, R4-COPILOT-ENV, R4-REFS, R4-TESTLIST, R4-NOTEST, R4-AN9SCOPE | P2 | Edited in this revision (item 4). Seats verify each edit. |
| R4-D6 | P2 | Answered by D10 (item 2). |
| R4-IT4 (was IT4/CR5) | P2 | Template edited in `0d89522f8` (item 3). |
| R4-AN9BODY, R4-PRSCOPE | P2 | PR #7014 body. Outside the ADR; this revision does not touch it. |
| IT2/AN2 | P2 | Test added (item 6). |
| CR6 | P2 | Test added (item 6). |
| AN1: no test pins an unpinned symlinked launcher target | P2 | Unchanged. No test added. |
| CR4: `check_citation_freshness.py` never checks `gate.py:N` cites | P2 | Unchanged. Item 5 cites were read by hand. |

## Inputs For Round 1

Found while making this edit. Each is stated in the ADR or is outside it.

- **Config install trust is not narrowed by D10.** D10 reads "an external
  plugin root that is itself a git work tree of this repository is
  verified like an in-tree path or blocks". The code applies that to
  files the commands name (`_partition_external_files`). The config
  itself still goes through `_install_trusted_root` (`gate.py:3948`), which
  has no same-repository check. So a config resolved under a sibling work
  tree is install-trusted and uncompared. Read from code; no test pins it.
  The ADR records it under R3 and Residual risk. Whether D10 extends to the
  config is an owner decision.
- **The new Step 0 sentence omits the config case.** `tmpl:151` says the
  config in this repository's work trees matches the trusted ref. By the
  item above, a config in a sibling work tree is install-trusted instead.
- **D10 misses some checkouts.** A fork clone whose origin is the fork, a
  clone whose remote is not named `origin`, and a copy with no `.git`
  keep install trust. The ADR records this under Residual risk.
- **Gate evidence for this commit.** Both log 2 files are modified by the
  split and will be staged with the ADR edit. They carry round 4 Accept
  positions that name ADR-059, so the pre-commit ADR gate in
  `git_hook_policy.py` can pass on them before this log records any
  position. The gate checks text, not which debate covered which edit.
- **Size.** The ADR is 499 of 500 lines after this edit. Any further text
  needs an equal cut.

Checks run by the editor before round 1:

- `check_citation_freshness.py` logic run on the working-tree ADR: 7
  path citations examined, 0 stale. A negative control on the committed
  ADR found the stale citations.
- `check_adr_lifecycle.py`: PASS, none outside the baseline.
- Every `gate.py:N` cite printed at `0d89522f8` and compared to its claim.
- Content check on the split: part 1 lines 1 to 367 plus part 2 from its
  line 9 equal the original 753 lines.

## Round 1 (2026-11-02)

Six seats reviewed the amendment against `run_completion_gate.py` at
`0d89522f8`. The fixes below are uncommitted in the PR #7014 work tree.

### Agent Positions

| Agent | Position | Confidence | Basis |
|-------|----------|------------|-------|
| architect | Accept | not stated | Read code; ran 36 D10 tests and 37 launcher tests, all pass |
| critic | Block | MEDIUM | Read code; ran nothing |
| independent-thinker | Block | not stated | Read code; checked plugin dirs on this host |
| security | Block | not stated | Read code; ran nothing |
| analyst | Block | HIGH on links and nesting, MEDIUM on config | Read code |
| high-level-advisor | Block | not stated | Read code; checked plugin dirs on this host |

Dissent: none recorded. No seat chose Disagree-and-Commit.

### Issues Raised

P1 (blocking):

| ID | Seats | Location | Issue |
|----|-------|----------|-------|
| R1-CONFIG | independent-thinker, security, analyst, high-level-advisor (critic as P2) | ADR R3 config bullet, Residual risk; `_install_trusted_root` | The ADR says "D10 does not reach the config" as fact. D10's words cover the plugin root, and the config is a path under it. No owner record narrows D10. A sibling config controls commands and `pass_when`. |
| R1-LINKS | security (analyst and critic as P2) | `_classify_argv_token` external branch; R3 "verified like an in-tree file" | A link in a sibling is resolved before partition, so an unpinned or retargeted link is followed (CWE-59). In-tree, it exits 2. No negative test. |
| R1-NESTED | analyst | `_same_repository_root`, `_partition_external_files` | Sameness is decided by the innermost `.git`. A named file in a nested repository under a sibling gets install trust. In-tree, it exits 2. No test. |
| R1-VERIFIER | critic | `pr-review.SKILL.md.tmpl` resolvers; ADR Positive bullet | Step 0 resolvers try plugin roots first, so a sibling root also serves the gate. That gate is PR-controlled and unchecked. The D10 tests call the gate in process, a route Step 0 does not take. |

P2:

| ID | Seat | Issue |
|----|------|-------|
| R1-APPROVAL | architect | Same-repository exit 2 omits the `--approve-untrusted-config` qualifier. |
| R1-TMPL151 | architect, critic, independent-thinker, security, analyst, high-level-advisor | `tmpl:151` says the config always matches the trusted ref; the ADR called this an omission. |
| R1-CFG117 | architect | `pr-review-config.yaml:117` exit-0 meaning has the same overclaim (predates D10). |
| R1-EXIT3 | architect, high-level-advisor | A true install below a `.git` git refuses now exits 3; unstated. |
| R1-GITINSTALL | architect, critic, independent-thinker | A git-backed install with this origin is compared and exits 2 when stale; unstated. |
| R1-GATEEVIDENCE | architect | The pre-commit ADR gate can pass on log 2's restaged Accept lines. |
| R1-INLINE | critic, security | "Files those commands name are still compared" does not bound inline code. |
| R1-TRIGGER | independent-thinker, high-level-advisor | The D10 config revisit trigger is unobservable. |
| R1-UNTRACKED-EXIT2 | independent-thinker | The exit-2 sentence omits an untracked sibling script. |
| R1-TMPL38 | high-level-advisor | `tmpl:38-45` says PR content cannot write any disjoint root. |
| R1-MEASURE | high-level-advisor | The Positive measurement predates `0d89522f8`. |
| R1-GITDIR | high-level-advisor | `_run_git` passes `GIT_DIR` through; every probe then matches. Fails closed. |
| R1-TOCTOU | security | The CWE-367 bullet omits a sibling branch change between Step 0 and dispatch. |
| R1-REMOTE | analyst | ssh URLs with a port and local-path origins do not match. |

### Consensus And Conflicts

- All six agree the D10 code for scripts matches the text for a gate run
  from this work tree, and every `gate.py` cite they checked matches
  `0d89522f8`.
- Five seats agree the config gap is real. They differ on priority (P1 in
  four seats, P2 in critic) and on the remedy (owner ruling or code).
  The architect read the gap as stated residual risk and accepted.
- No seat disputes another's facts. The conflict is over whether the
  ADR may read D10 narrowly without an owner record.

### Review Anti-Patterns

- None found. Every seat cited code lines and named missing tests.
- Four seats raised the same config finding. That is convergence on one
  defect, not Groundhog Day: each traced it by a different path.

### Revisions Made

Each fix follows the rule for this round: where the code did not match
the owner's D10 words, fix the code with a test, not the ADR text.

1. **R1-CONFIG, fixed in code.** D10 says a plugin root that is a work
   tree of this repository "is verified like an in-tree path or blocks".
   The config is a path under that root. New `_in_same_repository_tree`
   runs in `_install_trusted_root` and withholds install trust from such
   a root. Containment then refuses the config, exit 2. A git failure
   there raises `WorkTreeUnavailableError`, exit 3. The ADR R3 config
   bullet and the rule 4 bullet now say D10 covers the config. Owner
   flag: this reads D10's words as written. If the owner meant scripts
   only, the revert is one call, named in Reversibility.
2. **R1-LINKS, fixed in code.** `_collect_command_spellings` keeps each
   external file's unresolved spelling. `_partition_external_files` scans
   a spelling in a same-repository tree with `_unpinned_link_in`. An
   unpinned link is untrusted, as in-tree. A pinned one is still
   followed. A true install keeps its own links.
3. **R1-NESTED, fixed in code.** `_same_repository_root` now asks every
   enclosing `.git`, innermost first. A file in a nested repository
   under a sibling is grouped under the sibling, is untracked there, and
   blocks.
4. **R1-VERIFIER, resolved in ADR text; the residual is deferred.** A
   new R3 bullet says Step 0 cannot verify the gate it runs: a plugin
   root naming a sibling serves the gate and the skill text from that
   tree. The Positive bullet is narrowed to a gate in this work tree or
   a true install. Observed on 2026-11-02: this branch's gate, run from
   the main clone with `CLAUDE_PLUGIN_ROOT` set to this work tree,
   compared its own config with `origin/main` and exited 2 ("config ...
   is not trusted (diverged)"). The critic's inferred exit 3 was not
   reproduced; the config check halted first. See Deferred Findings.
5. **P2 text fixes.** R1-APPROVAL (R3 bullet and Positive bullet),
   R1-TMPL151 (template now says an installed plugin's config and scripts
   are install-trusted), R1-TMPL38 (template now excludes work trees of
   this repository), R1-EXIT3 and R1-GITINSTALL (one Negative bullet,
   with this host's plugin dirs as of 2026-11-02), R1-INLINE (Residual
   risk now says a config there can run inline code that names no file),
   R1-TRIGGER (config trigger deleted; the config is now in scope),
   R1-REMOTE (port and local-path URLs added to Residual risk),
   R1-MEASURE (paragraph cut to two lines, pointing at log 2; not rerun).
6. **Cuts for the 500-line cap.** The wrong-harness residual bullet, the
   owner record bullet, and the second `rev-parse` bullet were shortened.
   The ADR is 499 lines.
7. **Template line cites** moved to the edited template: `:152` (exit
   sentences), `:107-140` (resolvers), `:146` and `:150` (harness).
8. **Branch test fix.** `tests/commands/test_transport_preflight_step_zero.py`
   asserted "A non-empty list stops the run". The template at `0d89522f8`
   said "; a non-empty list", so two cases failed at the branch head.
   The template sentence is now split; no meaning changed.

### Verification

- New `tests/skills/github/test_run_completion_gate_same_repository_links.py`:
  9 tests. 9 pass with the fix. With `run_completion_gate.py` reverted to
  `0d89522f8`, 7 fail and the 2 install-trust controls pass.
- `tests/skills/github` plus `tests/build_scripts/test_copilot_launcher.py`:
  1334 passed.
- Every test file that names `pr-review`, plus `tests/skills/github` and
  `tests/build_scripts`: 6982 passed, 6 skipped, with
  `tests/test_get_unresolved_review_threads.py` run alone (15 passed). In
  one process with `tests/skills/github` it fails 7 cases; this looks like
  a module-name clash between test files, not this change (INFERRED).
- `ruff check` and `ruff format --check` on the gate and new test: pass.
- `build/scripts/build_all.py`: exit 0. Mirrors refreshed for the gate and
  `pr-review/SKILL.md` in codex, copilot-cli, cursor, and hermes.
- `check_adr_lifecycle.py`: PASS, none outside the baseline.
- `check_citation_freshness.py` scans committed lines vs `origin/main`.
  It reports the 2 stale cites in the committed ADR, which this revision
  already fixed. It was NOT RUN on the working tree.

### Deferred Findings

| Priority | Finding | Agent | Justification | Trigger to reopen |
|----------|---------|-------|---------------|-------------------|
| P1 | R1-VERIFIER residual: a PR-modified gate served from a sibling plugin root is checked by nothing | critic | No check inside the plugin can verify the plugin. With a sibling root, the skill text the agent reads comes from that tree too. An in-tree gate on a checked-out PR branch has the same limit. The ADR now states this. | adr-059 verifier selection: a resolver change that picks `$repo_root/.claude` before plugin roots, or the first report of a sibling plugin root in use |

### Residual P2 Findings

| Finding | Agent | Description |
|---------|-------|-------------|
| R1-CFG117 | architect | `pr-review-config.yaml:117` exit-0 meaning still overclaims; predates D10. |
| R1-UNTRACKED-EXIT2 | independent-thinker | The template exit-2 sentence does not name an untracked sibling script. |
| R1-GITDIR | high-level-advisor | A set `GIT_DIR` makes every probe match this repository. Fails closed. |
| R1-TOCTOU | security | A sibling branch change between Step 0 and dispatch is not named in the CWE-367 bullet. |
| R1-GATEEVIDENCE | architect | The ADR commit must wait for this log's consensus; the commit gate cannot tell log 2's Accept lines from this log's. |
| AN1, CR4 | carried | Unchanged from log 2. |

### Next Steps

Round 2: convergence check by all six seats on the revised ADR, the
gate code, the template, and the new tests. Seats verify the claims
added this round, including the 2026-11-02 sibling-gate observation.

## Round 2 (2026-11-02)

Convergence check by all six seats on the round 1 revision: the ADR, the
uncommitted gate code, the template, and the new links test file.

### Agent Positions

| Agent | Position | Basis |
|-------|----------|-------|
| architect | Block | Read code; ran 93 D10, links, and launcher tests, all pass; probed the shipped layout |
| critic | Accept | Read code; ran 45 D10 tests, all pass; diffed the log 2 split |
| independent-thinker | Disagree-and-Commit | Read code; ran 45 D10 tests, all pass; reproduced a sibling-served run, rc 2 |
| security | Accept | Read code; ran nothing (no shell) |
| analyst | Block | Read code; ran nothing; could not read `0d89522f8` |
| high-level-advisor | Disagree-and-Commit | Read code at `0d89522f8` and in the work tree; ran nothing |

Dissent (Disagree-and-Commit):

- **independent-thinker.** The round 1 R1-CONFIG fix was justified as a
  P1 exposure that was inferred from code and never reproduced. For this
  repository the premise does not hold: `_PROJECT_ROOT` follows the gate's
  own tree, so condition 3b already denied a sibling-served config install
  trust, and the config was byte-compared. The new check is sound, fails
  closed, and closes the consumer case (a plugin vendored in a sibling
  work tree). The owner should know its real beneficiaries are consumer
  repositories, not this repository's sibling worktrees.
- **high-level-advisor.** Same finding: in this repository's layout a
  sibling config was never install-trusted. A gate here or in a true
  install fails condition 3a; a sibling-served gate fails 3b. The ADR
  credited D10 with protection 3a and 3b already gave. Strategic note,
  not re-litigated: under the shipped resolvers a sibling plugin root also
  serves the gate, so D10 catches drift on a stale or honest sibling
  branch, not an adversarial PR that edits the gate (deferred R1-VERIFIER).

### Issues Raised

P1 (blocking):

| ID | Seats | Location | Issue |
|----|-------|----------|-------|
| R2-ANCHOR | architect (P1); critic, independent-thinker, security, analyst, high-level-advisor (P2) | ADR anchor paragraph; every `gate.py:N` cite | Cites are anchored to `0d89522f8`, but R3 describes round 1 code that is not at that commit. `_same_repository_root` there asks only the innermost `.git`; `_unpinned_link_in` and `_in_same_repository_tree` do not exist. |
| R2-CONFIGPATH | analyst (P1); architect, critic, independent-thinker, security, high-level-advisor (P2) | ADR R3 config bullet, Positive bullet, Reversibility | "Containment then refuses that config" is false in this repository. Condition 3a or 3b withholds install trust first, and the config is byte-compared against `_PROJECT_ROOT`, as the ADR's own 2026-11-02 observation shows. |
| R2-CONFIGTEST | analyst (P1); independent-thinker, high-level-advisor, critic (P2) | `test_run_completion_gate_same_repository_links.py` `TestConfigInSameRepositoryRoot` | The end-to-end test pairs a sibling `_DISPATCHER_PATH` with a primary `_PROJECT_ROOT`, which no work tree of this repository produces. It asserts only rc 2, with no stderr reason and no positive control. |

P2:

| ID | Seats | Issue |
|----|-------|-------|
| R2-D11QUOTE | architect, critic, independent-thinker | The D11 paragraph quotes a superseded template sentence as current. |
| R2-POSITIVE | security, high-level-advisor, critic | The Positive bullet credits D10 for config protection condition 3a gave; Reversibility says a revert install-trusts every plugin-root config. |
| R2-APPROVAL | critic | The approval parenthetical names only a diverged file; approval downgrades every same-repository `untrusted` plain-token entry. |
| R2-EXIT0-UNTRACKED | critic | `tmpl:152` exit-0 sentence says scripts in this repo's work trees match the trusted ref, but untracked plain-token scripts are skipped uncompared at exit 0. |
| R2-CWD-EXIT3 | independent-thinker | A clean sibling-served gate exits 3 on the cwd check; the template's exit-3 causes do not name it. Inferred in review; observed this round (below). |
| R2-EXIT2-NODIFF | independent-thinker | The exit-2 sentence says "surface the diff", but a containment refusal or an unpinned link has no diff, and approval cannot clear containment. |
| R2-CFGRESOLVED | security | The config D10 check tests the declared root and its ancestors, not the resolved config path; scripts get the resolved-path test. Operator layout only; risk 2/10. |
| R2-VERIFIER-TRIGGER | security | The R1-VERIFIER reopen trigger ("first report of a sibling plugin root in use") already fits the round 1 editor run. |
| R2-CFGRANGE | analyst | `pr-review-config.yaml:116-120` stops before the exit 3 entry; R1-CFG117's overclaiming text is on line 118. |
| R2-OBSERVE | analyst | The 2026-11-02 observation omits the exact plugin-root value and command. |
| R2-LINECAP | high-level-advisor | The ADR is at 499 of 500 lines; fixes must be net zero. |

### Consensus And Conflicts

- All six agree the D10 script path (links, nested repositories, probe
  failures, untracked named files) matches the text and fails closed.
- All six agree the config mechanism is misdescribed: conditions 3a and
  3b act first in this repository, and the config is compared, not
  refused. They differ only on priority (P1 analyst, P2 the rest).
- All six agree the `0d89522f8` anchor predates the code the text
  describes. Priority differs (P1 architect, P2 the rest).
- No seat disputes another's facts. The architect and analyst block on
  record accuracy; four seats accept because every outcome fails closed.

### Review Anti-Patterns

- None found. Every seat cited functions and lines. Three seats ran
  tests; two reproduced the shipped layout independently (architect
  probe, independent-thinker rc 2 run).
- Six seats raising R2-CONFIGPATH is convergence on one defect, not
  Groundhog Day: each traced it through a different condition (3a, 3b,
  or containment base).
- Security and analyst ran nothing and said so. That is a stated limit,
  not Pass Through: both cited code lines for every finding.

### Revisions Made

1. **R2-ANCHOR, resolved in the ADR.** Every `gate.py:N` cite (38) was
   mapped from `0d89522f8` to the work tree with a line diff, then
   printed and read at its new line. Unchanged regions (before line
   1724) kept their numbers. The anchor paragraph now reads: line numbers
   hold at the commit that last changed this paragraph. Commit order
   constraint for the owner: the gate code must land in the same commit
   as the ADR, or an earlier one, with no gate edit between.
2. **R2-CONFIGPATH, resolved in the ADR.** The R3 config bullet now says
   conditions 3a and 3b deny a sibling config install trust here, because
   every work tree holds `scripts/utils/path_validation.py`, and the
   config is byte-compared. `_in_same_repository_tree` is named as the
   guard for a tree without that marker, such as a consumer plugin
   vendored in a sibling work tree. The Positive bullet now credits 3a
   for the config. Reversibility now says dropping the check reopens
   install trust only for a config in a tree with no marker.
3. **R2-CONFIGTEST, resolved in tests.** The existing end-to-end test now
   names the layout it pins (consumer, cwd fallback) and asserts the
   containment reason in stderr. New `TestSiblingServedGateComparesItsConfig`
   sets `_PROJECT_ROOT` and `_DISPATCHER_PATH` both in the sibling:
   - a diverged config exits 2 with "is not trusted (diverged)" and no
     containment refusal;
   - a matching config gets no install trust, compares clean, then exits 3
     with "is outside the git work tree" (cwd check, `gate.py:3384-3393`).
     The positive control the analyst asked for (exit 0) does not occur
     in this layout; the test pins the exit 3 that does. This confirms
     R2-CWD-EXIT3. No gate code changed: both outcomes block, which is
     what D10 requires.
4. **P2 fixes in the ADR.** R2-D11QUOTE (paragraph states the current
   sentence once, IT4 history in past tense), R2-POSITIVE (Positive and
   Reversibility), R2-APPROVAL ("any of these"), R2-CFGRANGE (cite widened
   to `116-122`), R2-OBSERVE (root and command recorded; the matching
   config's exit 3 added to the same bullet), R2-LINECAP (ADR at 500 of
   500 lines; the owner record bullet and R1 revisit bullet were
   shortened).
5. **R2-VERIFIER-TRIGGER, resolved in this log.** The deferred row below
   restates the trigger to exclude editor test runs.

### Verification

- Sibling-served Step 0 run, 2026-11-02, from
  `/home/richard/src/GitHub/rjmurillo/ai-agents3` with
  `CLAUDE_PLUGIN_ROOT=<work tree>/.claude`, `COPILOT_PLUGIN_ROOT` empty:
  `run_completion_gate.py --config <work tree>/.claude/skills/pr-review/pr-review-config.yaml --pull-request 7014 --verify-config-only --harness claude_code --json`.
  Exit 2, "config ... is not trusted (diverged) against origin/main".
  The config path printed is the `src/claude/...` target of the ADR-119
  link: compared, not refused.
- `test_run_completion_gate_same_repository*.py` plus
  `tests/build_scripts/test_copilot_launcher.py`: 95 passed.
- `tests/skills/github` plus `tests/build_scripts/test_copilot_launcher.py`:
  1336 passed.
- `ruff check` and `ruff format --check` on the links test file: pass.
- `check_adr_lifecycle.py`: PASS, none outside the baseline.
- Every re-anchored cite printed at its new work-tree line and matched
  to the code it names. `check_citation_freshness.py`: NOT RUN.

### Deferred Findings

| Priority | Finding | Agent | Justification | Trigger to reopen |
|----------|---------|-------|---------------|-------------------|
| P1 | R1-VERIFIER residual (carried from round 1) | critic | Unchanged: no check inside the plugin can verify the plugin. | adr-059 verifier selection: a resolver change that picks `$repo_root/.claude` before plugin roots, or a reviewer session that uses a sibling plugin root for a real PR review. Editor test runs, such as round 1 item 4 and this round's verification run, do not count. |

### Residual P2 Findings

| Finding | Agent | Description |
|---------|-------|-------------|
| R2-EXIT0-UNTRACKED | critic | Template exit-0 sentence; untracked plain-token scripts are skipped uncompared. Template text, not edited this round. |
| R2-CWD-EXIT3 | independent-thinker | Template exit-3 causes omit the cwd check. The ADR states the behavior; the template does not. |
| R2-EXIT2-NODIFF | independent-thinker | Template exit-2 sentence assumes a diff exists. Same class as R1-UNTRACKED-EXIT2. |
| R2-CFGRESOLVED | security | Config D10 check uses root ancestors, not the resolved path. Operator layout only. |
| R1-CFG117 | architect | Carried. The overclaiming text is on `pr-review-config.yaml:118`. |
| R1-UNTRACKED-EXIT2, R1-GITDIR, R1-TOCTOU, R1-GATEEVIDENCE, AN1, CR4 | carried | Unchanged from round 1. |

### Next Steps

Round 3: convergence check by all six seats on the round 2 revision.
Seats verify the re-anchored cites against the work tree, the rewritten
config, Positive, and Reversibility text, and the new real-layout tests.

Continued in part 2:
`.project-toolkit/critique/ADR-059-debate-log-3-part-2.md` (round 3 onward).
