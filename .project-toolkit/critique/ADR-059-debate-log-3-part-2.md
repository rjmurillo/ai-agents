# ADR Debate Log: ADR-059 /pr-review Completion Gate Dispatcher and pass_when DSL (third debate, part 2)

Part 2 of `.project-toolkit/critique/ADR-059-debate-log-3.md`, the third
debate on ADR-059. It is not a new debate: rounds continue from part 1.
Owner decision D11 (2026-11-01) caps a debate log at 500 lines, and part 1
held 462 lines before round 3. Part 1 holds the summary, the change under
review, and rounds 1 and 2.

## Round 3 (2026-11-02)

Convergence check by all six seats on the round 2 revision: the
re-anchored cites, the rewritten config, Positive, and Reversibility text,
and the real-layout tests.

### Agent Positions

| Agent | Position | Basis |
|-------|----------|-------|
| architect | Accept | Read all 38 `gate.py` cites against the work tree; ran 95 D10 and launcher tests and 42 gate tests, all pass |
| critic | Accept | Read every cited function; ran 132 tests, all pass; checked the log 2 split |
| independent-thinker | Block | Read cites; ran 95 tests, all pass; reproduced an aliased plugin root bypass, rc 0 |
| security | Accept | Read code and ADR; ran nothing (no shell) |
| analyst | Accept | Read about 30 cites; ran nothing (no shell) |
| high-level-advisor | Accept | Read cites; ran 95 tests, all pass |

No seat chose Disagree-and-Commit, so no dissent is recorded.

### Issues Raised

P1 (blocking):

| ID | Seats | Location | Issue |
|----|-------|----------|-------|
| R3-ALIAS | independent-thinker | `_partition_external_files` spelling loop; ADR R3 link-scan sentence and Positive bullet | A plugin root that is a host link to a sibling's `.claude` skips the link scan. No lexical ancestor of the spelling holds the sibling's `.git`, so `_unpinned_link_in` never runs. An unpinned PR link to a tracked identical file exits 0. A link to a file outside every work tree gets install trust and exits 0. Without the alias, both exit 2. CWE-59, the R1-LINKS class. |

P2:

| ID | Seats | Issue |
|----|-------|-------|
| R3-EXIT0 | critic, independent-thinker, analyst, high-level-advisor | D11 ordered the exit-0 sentence fixed. It still says scripts match, but an untracked in-tree script is skipped uncompared (carried R2-EXIT0-UNTRACKED). |
| R3-MIRROR | architect, critic, independent-thinker | `tmpl:152` says the config table mirrors Step 0, but the table's exit-0 meaning lacks the install-trust clause (carried R1-CFG117). |
| R3-LOGSPLIT | all six | Round 3 pushes log 3 past the 500-line cap; D11 requires a part 2. |
| R3-ORDER | architect, critic | The cite anchor needs the gate and template to land with or before the ADR commit. Only this log states that; no check enforces it. |
| R3-CITE154 | independent-thinker | The ADR cites `tmpl:152` for the proceed rule, which is on line 154. |
| R3-LOADS | security | "`main` loads the pinned-link manifest": `main` binds the source; the load is lazy. |
| R3-VERIFIED | high-level-advisor | Residual risk calls true-install files "verified"; R3 calls them uncompared. |
| R3-GITCONFIG | security | D10 runs git in external repositories without `-c core.fsmonitor=`, so their `.git/config` is honored. Needs host write access; risk 2/10. Whether `ls-files` starts fsmonitor is INFERRED. |
| R3-EXIT3 | analyst | Exit-3 causes omit the cwd check and a git failure (carried R2-CWD-EXIT3). |
| R3-CONTAIN3A | analyst | The config bullet gives only the 3b outcome; under 3a, containment refuses the config. |
| R3-MARKER | analyst | A sibling PR branch that deletes `scripts/utils/path_validation.py` loses the marker, so `_in_same_repository_tree` guards this repository's own branches too. Reversibility understates the revert. INFERRED from code; bounded by R1-VERIFIER. |
| R3-APPROVED-EXIT0 | critic | With human approval, exit 0 holds with a diverged script. Human-only path. |

### Consensus And Conflicts

- All six agree the round 2 P1s (R2-ANCHOR, R2-CONFIGPATH, R2-CONFIGTEST)
  are resolved. Every seat that printed cites found them matching.
- All six agree the D10 rule as written matches the code for spellings
  that lie lexically under a work tree.
- Conflict: one seat blocks on R3-ALIAS; five did not test that layout.
  No seat disputes the reproduction. The conflict is coverage, not fact.
- All six flag the log split; four flag the exit-0 sentence.

### Review Anti-Patterns

- None found. Every seat cited functions and lines.
- Security and analyst ran nothing and said so. Each cited code for every
  finding, so this is a stated limit, not Pass Through.
- The independent-thinker placed two probe files under `tests/` for one
  run each and moved them out after. It disclosed this, and git status
  matched before and after. Noted, not an anti-pattern.
- The high-level-advisor urged closing the debate. That is a cost view,
  not a Power Game: it cited evidence for each P2.

### Revisions Made

1. **R3-ALIAS, fixed in code with tests.** The ADR text was right; the code
   missed a layout. New `_aliased_same_repository_root` resolves each
   ancestor of an unresolved spelling, innermost first. A resolved
   ancestor in a work tree of this repository names that root.
   `_partition_external_files` now calls it for every spelling that
   differs from the resolved path when the lexical walk finds no root, then
   runs `_unpinned_link_in`. That refuses the alias, since no ref pins it.
   A resolve or probe failure exits 3. New `TestAliasedSiblingPluginRoot`
   holds five tests: both reproduced cases now exit 2; a clean aliased
   sibling exits 2 (availability cost, fail closed); an alias to the
   sibling root exits 2, as it did before; an alias to a true install keeps
   install trust and exits 0. Negative control: with the new helper patched
   to return `(None, "")`, three of the five fail with rc 0.
2. **R3-ANCHOR follow-up.** The gate edit added 39 lines before most
   cites. Every `run_completion_gate.py` cite in the ADR was remapped with
   a line diff, and the function anchors were printed at their new lines.
   Cites before line 3199 did not move. The commit order rule (R3-ORDER)
   still holds: the gate, template, and ADR must land together.
3. **R3-EXIT0, R3-MIRROR, R3-EXIT3, fixed in text with a test.** Template
   exit 0 now says tracked scripts match, an untracked in-tree script is
   listed in `skipped_untracked_files`, and an installed plugin is
   install-trusted. Exit 3 names the cwd check and git failure. "Mirrors"
   became "summarizes". `pr-review-config.yaml` exit 0 and exit 3 carry
   the same clauses. New `test_exit_0_text_names_what_is_not_compared`
   asserts both clauses in both files. The ADR D11 paragraph states this.
4. **ADR P2 fixes.** R3-CITE154 (`:152-154`), R3-LOADS ("binds the
   pinned-link source, loaded on first use"), R3-VERIFIED ("count as
   verified, uncompared"), a link-scan sentence for the alias case, and
   "(and its part 2)" on the log 3 reference. The ADR stays at 500 lines:
   the R1 Codex cite and the R1 revisit bullet were shortened.
5. **R3-LOGSPLIT.** This file is part 2. Part 1 gained a link line and an
   updated summary.

### Verification

- `test_run_completion_gate_same_repository*.py` plus
  `tests/build_scripts/test_copilot_launcher.py`: 100 passed.
- `tests/commands`, `tests/skills/github`, `tests/build_scripts`, and
  `tests/test_run_completion_gate_install.py`: 5755 passed, 2 skipped.
- `ruff check` and `ruff format --check` on the gate, the links test, and
  the wiring test: pass.
- `build/scripts/build_all.py` regenerated the gate, SKILL.md, and config
  mirrors under `.claude/` and `src/{codex,copilot-cli,cursor,hermes}`.
- `check_adr_lifecycle.py`: PASS, none outside the baseline.
- `check_citation_freshness.py`: NOT RUN.

### Deferred Findings

| Priority | Finding | Agent | Justification | Trigger to reopen |
|----------|---------|-------|---------------|-------------------|
| P1 | R1-VERIFIER residual (carried) | critic | Unchanged: no check inside the plugin can verify the plugin. | Unchanged from round 2. |

### Residual P2 Findings

| Finding | Agent | Description |
|---------|-------|-------------|
| R3-ORDER | architect, critic | Commit order is a human step. Before the ADR commit, `git diff --stat` on the gate and template from that commit to HEAD must be empty. |
| R3-GITCONFIG | security | External repositories' git config is honored. Not edited this round. |
| R3-CONTAIN3A | analyst | 3a containment outcome not in the config bullet. ADR at line cap. |
| R3-MARKER | analyst | Marker-deleted sibling branch. INFERRED, no test. |
| R3-APPROVED-EXIT0 | critic | Approval path, human-only. |
| R2-EXIT2-NODIFF, R2-CFGRESOLVED, R1-UNTRACKED-EXIT2, R1-GITDIR, R1-TOCTOU, R1-GATEEVIDENCE, AN1, CR4 | carried | Unchanged. |

R2-EXIT0-UNTRACKED, R2-CWD-EXIT3, and R1-CFG117 closed this round
(revision 3).

### Next Steps

Round 4: convergence check by all six seats. Seats verify the
`_aliased_same_repository_root` fix and its tests, the remapped cites,
and the exit-0 and exit-3 text in the template and config table.

## Round 4 (2026-11-02)

Convergence check by all six seats on the round 3 revision: the
`_aliased_same_repository_root` fix and its tests, the remapped cites,
and the exit-0 and exit-3 text in the template and config table.

### Agent Positions

| Agent | Position | Basis |
|-------|----------|-------|
| architect | Accept | Read 28 cite ranges and 22 function anchors; ran 145 D10, launcher, and wiring tests and 43 gate tests, all pass |
| critic | Accept | Read 23 cite ranges and anchors; ran 145 and 42 tests, all pass; reproduced the negative control (3 of 5 alias tests fail with the helper neutered) |
| independent-thinker | Accept | Read about 30 cites; ran 145 tests, all pass; R3-ALIAS block resolved |
| security | Accept | Read code and ADR; ran nothing (no shell) |
| analyst | Accept | Read about 30 cites; ran nothing (no shell) |
| high-level-advisor | Accept | Read about 20 cites; ran 100 and 42 tests, all pass; reproduced the negative control |

No seat chose Disagree-and-Commit, so no dissent is recorded.

### Issues Raised

No P0 or P1. All findings are P2.

| ID | Seats | Location | Issue |
|----|-------|----------|-------|
| R4-ALIAS-COST | architect, independent-thinker, security, analyst | ADR Negative, D10 bullet (lines 410-415); R3 link-scan sentence | A plugin root that is a host link into a clean sibling work tree now always exits 2. Approval cannot unblock a Copilot launcher. Negative lists only the `.git` lag case. The ADR at 500 lines needs an offsetting cut. |
| R4-ALIAS-ERRTEST | critic, security | `gate.py:3199-3228`, `3359-3362` | The resolve and probe failure branch of `_aliased_same_repository_root` has no test. A grep of `tests/` finds no reference to the helper (rechecked by the consolidator, 2026-11-02). Fails closed. |
| R4-EXIT3-PARITY | critic | `test_transport_preflight_wiring.py:316-337` | Only exit-0 text parity is tested. The exit-3 clauses can drift between template and config. |
| R4-IT4 | critic | ADR line 341 | "did IT4" is undefined in the ADR; only log 3 part 1 defines it (rechecked, line 341). |
| R4-TESTNAME | critic, analyst | ADR R3 Tests bullet (lines 330-336) | `TestAliasedSiblingPluginRoot` is not named. |
| R4-CMDPATHS | independent-thinker, analyst | ADR Negative (line 390) | Names `_collect_command_paths` (1824), a wrapper; the launcher call is in `_collect_command_spellings` (1877). Rechecked. |
| R4-THISREPO | independent-thinker | ADR R3 bullets; Residual risk D10 bullet | "This repository" means the work tree Step 0 runs in. An ai-agents checkout used as plugin root while reviewing a consumer PR keeps install trust. |
| R4-SIBLING-UNTRACKED | independent-thinker | `tmpl:152`; `pr-review-config.yaml:118` | Exit-0 says untracked scripts "in this work tree"; sibling untracked closure files also land in `skipped_untracked_files` (3533, 3542, 3551). |
| R4-EXIT3-RESOLVE | security | ADR R3 (lines 288-290) | Exit-3 causes name only git failure; path-resolution failure in the alias helper also exits 3. Log revision 1 says so; the ADR does not. |
| R4-GITCONFIG-REACH | security | `gate.py:3225` | The alias walk probes the enclosing repository of any link target. Extends carried R3-GITCONFIG; same host-write bound. Risk 2/10. |
| R4-NODIFF-ALIAS | analyst | `tmpl:152`; config `:120`; `gate.py:3598-3602` | New trigger for carried R2-EXIT2-NODIFF: an alias refusal exits 2 with byte-identical files, and HALT text says files differ or are absent. |
| R4-FOREIGN-ALIAS | analyst | `gate.py:3354-3361`; links test `97-187` | No test places the alias inside a foreign git repository. Code reads correctly. INFERRED. |
| R4-EXIT0-SKIP | high-level-advisor | `tmpl:152`; config `:116`; ADR D11 | Exit 0 omits a third uncompared class: a named path that is missing or not a file (`gate.py:1819-1820`). Predates this amendment; Residual risk discloses it. |
| R4-LINECAP | independent-thinker, high-level-advisor | ADR file length (500) | The 500-line cap is shaping content (R3-CONTAIN3A deferred for it). D11 caps logs, not ADRs. Split the Step 0 trust rules out before the next amendment. |
| R4-D10-RECORD | high-level-advisor | ADR lines 99-102; References line 496 | D10 and D11 have no comment on #6506, unlike D3, D5, D6. Squash merge leaves the ADR and log as the only record. |

### Consensus And Conflicts

- All six Accept. Consensus is reached in round 4.
- All six agree R3-ALIAS is resolved: the alias walk runs before
  `_unpinned_link_in`, and config install trust uses resolved roots.
- Four seats independently flag R4-ALIAS-COST. Two flag the missing
  error-branch test. No seat disputes another's finding.
- No conflict on fact. The only tension is cost: the high-level-advisor
  urges closing now; no seat argues for another round.

### Review Anti-Patterns

- None found. Every seat cited lines for each finding.
- Security and analyst ran nothing and said so. Their findings cite code.
  This is a stated limit, not Pass Through.
- Two seats reproduced the round 3 negative control instead of trusting
  the log. That is the opposite of Rubber Stamp.
- The high-level-advisor's push to close is backed by evidence for each
  P2, so it is a cost view, not a Power Game.

### Revisions Made

None. Consensus closes the debate. Under `debate-protocol.md`, any later
ADR edit starts a new debate in a new log. The P2s go to the owner as
recommendations below.

### Verification

Consolidator checks, 2026-11-02, worktree at uncommitted state:

- ADR length: 500 lines (`wc -l`).
- `grep -rln _aliased_same_repository_root tests`: no hits.
- `gate.py:1824` defines `_collect_command_paths`; `gate.py:1877` holds
  the `_launcher_script_token` call in `_collect_command_spellings`.
- ADR line 341 holds the undefined "IT4"; line 390 names
  `_collect_command_paths`.
- Seat test runs are as reported in Agent Positions. The consolidator
  ran no tests this round.

### Residual P2 Findings

| Finding | Agent | Description |
|---------|-------|-------------|
| R4-* (15 rows above) | all six | Text, coverage, and record gaps. None blocks. |
| R3-ORDER | architect, critic | Commit order is a human step. Gate, template, and ADR must land in one commit. |
| R3-GITCONFIG, R3-CONTAIN3A, R3-MARKER, R3-APPROVED-EXIT0 | carried | Unchanged. |
| R2-EXIT2-NODIFF | carried | Unchanged; R4-NODIFF-ALIAS adds a trigger. |
| R2-CFGRESOLVED, R1-UNTRACKED-EXIT2, R1-GITDIR, R1-TOCTOU, R1-GATEEVIDENCE, AN1, CR4 | carried | Unchanged. |

| Priority | Finding | Agent | Justification | Trigger to reopen |
|----------|---------|-------|---------------|-------------------|
| P1 | R1-VERIFIER residual (carried) | critic | No check inside the plugin can verify the plugin. | Unchanged from round 2. |

## Closing Summary

- **Outcome**: Consensus in round 4 of 10. All six seats Accept.
- **Final Status**: accepted.
- **Dissent captured**: none. No seat chose Disagree-and-Commit.
- **What changed across this debate**: D10 same-repository trust rules
  (R1 to R3), launcher recognition and harness scope, the aliased plugin
  root fix with five tests, re-anchored cites, and the D11 exit text in
  the template and config table.

### Recommendations

1. **Commit order (R3-ORDER).** Land the gate, template, mirrors, tests,
   and ADR in one commit. Before it, `git diff --stat` on the gate and
   template must show nothing outside that commit.
2. **Tests to add in this PR** (code coverage, no ADR edit needed):
   R4-ALIAS-ERRTEST (make `Path.resolve` raise for the alias, assert rc 3
   and empty stdout) and R4-EXIT3-PARITY (assert both exit-3 clauses in
   template and config). Security code targets 100% coverage.
3. **Owner record (R4-D10-RECORD).** Post one comment on #6506 that
   records D10 and D11.
4. **Next ADR text pass** (starts a new debate): R4-ALIAS-COST,
   R4-EXIT3-RESOLVE, R4-IT4, R4-TESTNAME, R4-CMDPATHS, R4-THISREPO,
   R4-SIBLING-UNTRACKED, R4-EXIT0-SKIP. Do it with R4-LINECAP: split the
   Step 0 trust rules into their own ADR first, so the line cap stops
   deciding content.
5. **Planning route**: none. The implementation exists in this worktree.
