# Skill gap audit against ADR-127

Decision: `.project-toolkit/architecture/ADR-127-workflow-skills-are-script-drivers.md`.
Scope: all 121 templates under `templates/skills/` at `a7b036aba3` (2026-11-25).
Each row below is a gap-audit row in ADR-127's terms. Its id is stable.

## Method

1. A scan script read every template. It counted lines, shell blocks, script files, grants, and eval files.
   It also matched commands that push, merge, delete a branch, rewrite history, or write to a PR or issue.
2. Four Sonnet readers then opened each template and judged shape, prose steps, and missing scripts.
3. A second pass re-opened one deciding line for each driver, each disputed skill, and each P0 row.
   It corrected the `push-pr` line numbers. Every other citation is the reader's, as given.

Limits:

- Line numbers are template lines. A cell that was not re-opened may be off by a few lines.
- "Missing scripts" are proposals. A rewrite thread decides the real split.
- No eval ran for this audit. The eval column says only whether a scenario file exists.
- The all-rows table scores decisions 1 and 3. A separate table scores decisions 2, 4, 6, and 8 for the drivers.
- The readers judged `allowed-tools` from the template frontmatter.
- Two `reference` rows rest on a reader's unverified read: `ai-agents-generation-and-release` and `repository-completion-proof`.

## How shape and priority were set

Shape follows ADR-127 decision 1. One test covers conditional writers:
a skill is a `driver` when its own instructions run the push or the external write, even behind a user yes.
A skill is `disputed` when it shows such a command as knowledge, or hands the push to another workflow.

| Priority | Meaning |
|---|---|
| P0 | A driver that pushes, merges, or writes to a PR, with the mutating step in prose and a wide grant or no script. |
| P1 | A driver with scripts behind most steps, a driver whose only external write waits on a user yes, or a non-driver whose fixed steps or wide grant are clear script work. |
| P2 | A small gap. Fix it when the skill is next edited. |
| P3 | No gap worth a rewrite. |

## Summary

| Measure | Count |
|---|---|
| Templates scored at `a7b036aba3` (2026-11-25) | 121 |
| Shape `driver` at `a7b036aba3` (2026-11-25) | 15 |
| Shape `disputed`, for the owner at `a7b036aba3` (2026-11-25) | 2 |
| Shape `reference` at `a7b036aba3` (2026-11-25) | 104 |
| Priority P0 at `a7b036aba3` (2026-11-25) | 9 |
| Priority P1 at `a7b036aba3` (2026-11-25) | 19 |
| Priority P2 at `a7b036aba3` (2026-11-25) | 27 |
| Priority P3 at `a7b036aba3` (2026-11-25) | 66 |
| Templates with no verdict scenario file at `a7b036aba3` (2026-11-25) | 116 |
| Rendered skills over the 12 KiB driver budget at `a7b036aba3` (2026-11-25) | 69 |
| Driver skills with no scripts directory at `a7b036aba3` (2026-11-25) | 10 |

Drivers: `git-advanced-workflows`, `github`, `merge-resolver`, `modernize`, `pipeline-validator`, `pr-autofix`, `pr-babysit`, `pr-comment-responder`, `pr-review`, `push-pr`, `research`, `ship`, `sol-loop`, `takeover`, `windows-image-updater`.

Driver skills with no scripts: `git-advanced-workflows`, `modernize`, `pipeline-validator`, `pr-autofix`, `pr-review`, `push-pr`, `research`, `ship`, `takeover`, `windows-image-updater`.

## Ship and push-pr first

These two are the pilot. Both are drivers. `ship` has no script. `push-pr` scripts PR creation but not the push.

| | `ship` | `push-pr` |
|---|---|---|
| Row id | G-096 | G-082 |
| Template lines at `a7b036aba3` (2026-11-25) | 241 | 215 |
| Rendered bytes at `a7b036aba3` (2026-11-25) | 24401 | 14890 |
| Scripts in the skill's own directory at `a7b036aba3` (2026-11-25) | 0 | 0. It calls `new_pr.py` in the `github` skill. |
| Grant | `Bash(*)` | `Bash(git push:*)` and seven more git grants |
| Verdict scenarios at `a7b036aba3` (2026-11-25) | 8 in `tests/evals/ship-scenarios.json`, 6 in `ship-review-coverage-scenarios.json` | none |
| Activation scenarios at `a7b036aba3` (2026-11-25) | 4 | 3 |
| Deterministic tests | `tests/skills/ship/test_skill_md_contract.py` | two files under `tests/skills/push-pr/` |

Prose doing a script's job in `ship`:

- lines 52-64: host detection shell
- lines 76-78: PR lookup that tells "no PR" from a failed query by stderr text
- lines 82-85: owner or contributor mode
- lines 100-131: Azure DevOps policy loop with TSV parsing
- lines 96, 163: checks rerun on exit 7
- lines 137-145: marker validator resolution and exit codes
- line 161: PR creation arguments by hand
- line 165: a 30 minute wait loop

Prose doing a script's job in `push-pr`:

- line 47: branch name chosen from the change type
- lines 54-62: body file allocated, path copied by hand
- lines 77-90: preflight call and its rejections
- line 91: description check with exit 1 against exit 2 handling
- line 109: push with no script

What the pilot must settle before its rewrite:

- All 8 `ship` verdict scenarios at `a7b036aba3` (2026-11-25) test host detection, mode detection, or the marker check. Those steps move into scripts.
  ADR-127 decision 7 needs at least 8 scenarios on kept judgment, with 6 passing on `origin/main`. They do not exist yet.
- `push-pr` has no verdict scenario file. It is retired into `ship`, so its judgment scenarios belong in the `ship` file.
- `ship` grants `Bash(*)`. Decision 3 item 7 requires a grant that names each script.
- Retiring `push-pr` leaves callers that name it. Moving its trigger phrases does not migrate them.
  `autoplan` line 161 routes push-only requests to `/push-pr`. `takeover` line 65 uses `push-pr` to file a replacement PR.
  `ship` line 158 and `validate-pr-description` also name it, as do six pages under `docs/skills/`.
  The pilot must update each caller in the same change, or the retirement breaks them.

## Decisions recorded for the pilot

The unmerged ship driver draft left three decisions open.
They were decided on 2026-11-25 by the coordinator under Richard's delegation. Richard can reverse each one.
The delegation is a coordinator thread the owner opened on 2026-11-25. It is not a repository record, so treat these as provisional until the owner confirms them.
The draft is not on `main` yet, so the rulings are recorded here.

| # | Decision | Ruling | Reason given |
|---|---|---|---|
| 1 | Draft PRs before review | `ship --draft` skips the marker check and opens a draft PR | Spikes and early CI feedback need a PR before `/review`. Draft state already blocks a merge. |
| 2 | Branch | Build on a fresh branch from `origin/main` | The earlier branch was open as PR #7572 on 2026-11-25. Its commits become history on `main`. |
| 3 | Stub | Delete `/push-pr` outright | Its trigger phrases move into the `ship` description. A stub would compete with `ship` on routing. |

Sequencing, from the same rulings:

- The pilot starts after PR #7572 merges. Both edit the same templates.
- At most two fix threads run at once.

## Driver contract, decisions 2, 4, 6, and 8

The rows below score each driver on the rest of the contract. The numbers are measured, not judged.

| Skill | Rendered bytes at `a7b036aba3` (2026-11-25) | Within the 12 KiB budget | States a call budget | Scripts that end on `NEXT:` or `STOP:` | STOP table | Test files under `tests/skills/<name>/` |
|---|---|---|---|---|---|---|
| `git-advanced-workflows` | 15145 | no | no | 0 of 0 | no | 1 |
| `github` | 25548 | no | no | 0 of 1 | no | 68 |
| `merge-resolver` | 18317 | no | no | 0 of 2 | no | 14 |
| `modernize` | 10726 | yes | no | 0 of 0 | no | 1 |
| `pipeline-validator` | 19660 | no | no | 0 of 0 | no | 1 |
| `pr-autofix` | 84393 | no | no | 0 of 0 | no | 14 |
| `pr-babysit` | 11184 | yes | no | 0 of 3 | no | 7 |
| `pr-comment-responder` | 22518 | no | no | 0 of 2 | no | 5 |
| `pr-review` | 24449 | no | no | 0 of 0 | no | 1 |
| `push-pr` | 14890 | no | no | 0 of 0 | no | 2 |
| `research` | 15590 | no | no | 0 of 0 | no | 1 |
| `ship` | 24401 | no | no | 0 of 0 | no | 1 |
| `sol-loop` | 13624 | no | no | 0 of 5 | no | 10 |
| `takeover` | 4418 | yes | no | 0 of 0 | no | 2 |
| `windows-image-updater` | 14367 | no | no | 0 of 0 | no | 1 |

Reading the table at `a7b036aba3` (2026-11-25):

- 3 of 15 drivers fit the 12 KiB budget at `a7b036aba3` (2026-11-25): `modernize`, `pr-babysit`, `takeover`.
- No driver states a call budget, has a STOP table, or has a script that ends on `NEXT:` or `STOP:` at `a7b036aba3` (2026-11-25). The protocol is new, so every driver starts at zero.
- The test file counts say only that tests exist. None is a decision 8 contract test, because no driver has a STOP table or result lines to test yet.
- The two disputed skills are not scored here. They get this table when the owner rules on their shape.

## Disputed shapes, for the owner

| Row | Skill | Why it is unclear |
|---|---|---|
| G-008 | `ai-agents-debugging-playbook` | line 78: a table cell says `git fetch origin main && git merge origin/main` |
| G-101 | `skillopt` | line 283: "Commit and push through the owner's repository workflow" |

Two more calls for the owner:

- `sol-loop`, `takeover`, `research`, and `pr-babysit` push or write only on a condition. The readers scored them as drivers because the instruction exists.
- `review` writes a local marker commit. That is not a push, so it is a `reference` skill here. It still gates `ship`.

## Findings that cross skills

1. **Force push against decision 3 item 8.** `modernize` (lines 61-62) and `pr-autofix` (lines 925-926) tell the model to force push with a lease.
   `git-advanced-workflows` (line 50) gives the same command. Decision 3 item 8 bars a script from a force push.
   So these steps cannot move into a script as written. A rewrite keeps them with the human, or the ADR changes through `adr-review`.
2. **`Bash(*)` on four skills.** `build`, `review`, `ship`, and `test` grant `Bash(*)`. Only `ship` is a driver.
   `analyze`, `benchmark-models`, `context-optimizer`, `pr-autofix`, and `requirements-interview` grant bare `Bash`.
3. **Scripts outside `scripts/`.** `metrics`, `security-detection`, and `stuck-detection` keep scripts at the skill root. `sync` uses a repository path.
   Decision 3 item 2 puts a driver's scripts in `skills/<name>/scripts/`. These four are not drivers, so this is a note, not a breach.
4. **Calls that skip the locator.** `planner`, `doc-accuracy`, `memory-enhancement`, and `memory` (line 318) run scripts by bare path.
5. **The locator one-liner is pasted everywhere.** It is the ADR-121 form and is not a gap by itself. It does inflate many templates.
6. **Exit code 2 with two meanings.** `cynefin-classifier` and `decision-question` make the model tell a launcher failure from a script result by reading stderr.
   The result-line protocol in decision 4 removes that.

## Proposed rewrite groups

Each group is one fix thread and one small PR series. Groups run two at a time.

| Order | Group | Skills | Why together |
|---|---|---|---|
| 1 | Pilot: ship and push-pr | `ship`, `push-pr` | The consolidation. `push-pr` folds into `ship`. |
| 2 | Evidence check | none (decision 9 check and the ADR-057 amendment) | No second gated change merges before it. |
| 3 | PR write surface | `github`, `pr-comment-responder`, `pr-review` | They share the PR and thread scripts. |
| 4 | PR automation | `pr-autofix`, `pr-babysit`, `merge-resolver` | They share branch update and push steps. |
| 5 | Branch rewrite | `modernize`, `takeover`, `git-advanced-workflows` | All three meet the force-push question in finding 1. |
| 6 | Azure DevOps | `pipeline-validator`, `windows-image-updater` | Both drive Azure DevOps and git with no scripts. |
| 7 | Grants on lifecycle skills | `build`, `review`, `test`, `validate-pr-description`, `pr-quality` | Narrow `Bash(*)` and move the fixed gate steps into scripts. |
| 8 | Conditional writers | `sol-loop`, `research`, `skillopt` | Each pushes or files only after a user yes. |
| 9 | Reference skills at P1 | `analyze`, `benchmark-models`, `checkpoint`, `github-url-intercept`, `memory-consolidate`, `reviewer-findings`, `ai-agents-build-and-env`, `ai-agents-portability-campaign` | Clear script candidates with no remote write. |

Sizing, by ADR-127 decision 7: each gated skill needs at least 8 verdict scenarios before its rewrite.
Groups 1 and 3 to 9 cover 29 skills at `a7b036aba3` (2026-11-25): 21 in groups 1 and 3 to 8, and 8 reference skills in group 9. Only `ship` has a verdict file today.
Decision 7 gates a reference skill too when a rewrite implements its audit row. So the floor is 28 new scenario files of at least 8 scenarios each, 224 scenarios or more.
The P2 and P3 rows need no rewrite thread. A P2 row is a candidate when its skill is next edited.
One exception: `pr-babysit` is P2 but rides in group 4, because it shares that group's branch update and push steps.
`git-advanced-workflows` is a driver, so it stays in group 5.

## All rows

| Id | Skill | Shape | Deciding evidence | Prose doing a script's job | Missing scripts | Grant | Eval files | Priority | Reason |
|---|---|---|---|---|---|---|---|---|---|
| G-001 | `adr-generator` | reference | no push, merge, or PR write; lines 311-315 run a local index generator | line 311: repo-identity shell check before the index refresh | check_adr_repo.py (verify origin before index refresh) | none | verdict: yes; activation: yes | P2 | Writes ADR files only. One host-check block is a script candidate. |
| G-002 | `adr-review` | reference | no external write; line 196 runs read-only `detect_adr_changes.py` | lines 196-218: six path variants of one script call | none | none | verdict: no; activation: yes | P3 | The script exists. The variants are usage notes. |
| G-003 | `agent-harness-reference` | reference | contract field reference; no mutating command | none | none | none | verdict: no; activation: yes | P3 | Knowledge only. |
| G-004 | `ai-agents-architecture-contract` | reference | lines 165, 184 call read-only `contract_probe.py` | lines 165, 184: locator one-liner pasted per call | none | none | verdict: no; activation: no | P3 | Scripts exist. |
| G-005 | `ai-agents-build-and-env` | reference | lines 191-197: "Each is read-only" | lines 191-197: four pasted locator calls; line 195: Phase 3 setup done by hand | run_setup_phase.py (uv sync, hooks install, verify) | none | verdict: no; activation: no | P1 | Setup phases are fixed steps left as prose. |
| G-006 | `ai-agents-change-control` | reference | lines 40-42, 64 run `classify_change.py` | lines 40-42: three pasted locator calls | none | none | verdict: no; activation: no | P3 | The classifier script exists. |
| G-007 | `ai-agents-config-catalog` | reference | lines 182, 188, 204 are read-only | lines 182, 188, 204: pasted locator calls | none | none | verdict: no; activation: no | P3 | Catalog plus an existing locator script. |
| G-008 | `ai-agents-debugging-playbook` | disputed | line 78: a table cell says `git fetch origin main && git merge origin/main` | lines 90-98: pasted locator calls; lines 78-79: fetch, merge, and rev-list text in table cells | none | none | verdict: no; activation: no | P2 | The merge is a remedy cell, not a driven step. Owner rules on shape. |
| G-009 | `ai-agents-diagnostics-toolkit` | reference | lines 35, 36, 45, 82 are read-only baselines | lines 35-36: pasted locator calls | none | none | verdict: no; activation: no | P3 | A script sits behind each call. |
| G-010 | `ai-agents-docs-of-record` | reference | writes docs in the tree only | lines 97, 267, 268: pasted locator calls | none | none | verdict: no; activation: no | P2 | Its "never" lines guard doc rules. No doc writer script exists. |
| G-011 | `ai-agents-empirical-probe-toolkit` | reference | line 95: eval `--dry-run` | lines 95-99: eval dry-run block the model assembles | run_eval_dry_run.py (assemble eval-prompt-change args) | none | verdict: no; activation: no | P2 | The same argument assembly repeats in two skills. |
| G-012 | `ai-agents-external-claims` | reference | `claim_ledger.py` is local | line 180: one locator call | none | none | verdict: no; activation: no | P3 | One-script skill. |
| G-013 | `ai-agents-failure-archaeology` | reference | lines 166, 176, 184 run `corpus_index.py` | lines 166, 176, 184: pasted locator calls | none | none | verdict: no; activation: no | P3 | History reference with an index script. |
| G-014 | `ai-agents-generation-and-release` | reference | publish is described, not instructed (UNVERIFIED for every line) | lines 56-58, 94: four pasted locator calls | none | none | verdict: no; activation: no | P2 | High-blast domain, but only read-only inventory is driven. |
| G-015 | `ai-agents-portability-campaign` | reference | ten shell blocks are tests and probes | lines 164-170: a fixed `uv run pytest` list the model pastes | run_portability_tests.py (run fixed hook test set) | none | verdict: no; activation: no | P1 | A fixed test set pasted by the model. |
| G-016 | `ai-agents-research-frontier` | reference | lines 234, 287 are read-only | lines 234, 287: pasted locator calls | none | none | verdict: no; activation: no | P3 | Research list. |
| G-017 | `ai-agents-research-methodology` | reference | line 79: eval `--dry-run` | lines 79-84: eval dry-run block, same as the probe toolkit | run_eval_dry_run.py (assemble eval-prompt-change args) | none | verdict: no; activation: no | P2 | Duplicate block. One shared script serves both. |
| G-018 | `ai-agents-validation-and-qa` | reference | lines 80-87 are pytest invocations | lines 80-87: five pytest variants | none | none | verdict: no; activation: no | P3 | An invocation menu, not a fixed sequence. |
| G-019 | `analysis-provenance` | reference | every block runs read-only `check_provenance.py` | lines 31-39, 105, 192-230: nine identical locator calls | none | none | verdict: no; activation: no | P2 | Wrapper copies fill the file. The script is complete. |
| G-020 | `analyze` | reference | line 101 runs the `analyze.py` step counter | lines 101-105: step and file argument assembly; lines 49-60: quoting MUST list | none | bare `Bash` | verdict: no; activation: yes | P1 | Broad grant plus quoting rules that guard arguments. |
| G-021 | `api-doc-authoring` | reference | lines 116, 134 run local example scripts | lines 116, 134: locator calls | none | none | verdict: no; activation: yes | P3 | Scripts exist for both fixed steps. |
| G-022 | `autoplan` | reference | line 203 runs `resolve_route.py` | lines 202-203: request text spliced into `--request` in a shell string | none | none | verdict: no; activation: yes | P2 | Request text in a shell string is an injection-shaped gap. |
| G-023 | `avoiding-manufactured-work` | reference | rule content, no shell | none | none | none | verdict: no; activation: no | P3 | No gap. |
| G-024 | `benchmark-models` | reference | runs model CLIs; line 87 is a dry run | lines 87-89, 118-121, 139-141: path resolution and env setup as prose | resolve_benchmark.py (locate driver, set allowed roots) | bare `Bash` | verdict: no; activation: no | P1 | Broad grant. Driver path detection is prose. |
| G-025 | `build` | reference | commits locally; no push, merge, or PR write | lines 108-128: long locator calls with per-path arguments; lines 76-79: exit-code handling | run_validation_gate.py (trigger, classify, record check) | `Bash(*)` | verdict: no; activation: yes | P1 | `Bash(*)` on a high-traffic skill that is not a driver. The model assembles a four-step gate. |
| G-026 | `business-strategy` | reference | router, no shell | none | none | none | verdict: no; activation: no | P3 | Routing prose only. |
| G-027 | `buy-vs-build-framework` | reference | four local scoring scripts | lines 139-150: nine-flag `calculate_tco.py` call | none | none | verdict: no; activation: no | P2 | Scripts exist. The blocks are usage examples. |
| G-028 | `chaos-experiment` | reference | `generate_experiment.py` writes files | lines 311-318: argument block | none | none | verdict: no; activation: no | P3 | One usage example. |
| G-029 | `checkpoint` | reference | line 114: "does not push or commit" | lines 55-62: eight ordered steps deferred to a reference; path and slug assembly | write_checkpoint.py (path, redact, write, link log) | four narrow `Bash(...)` entries | verdict: no; activation: yes | P1 | Eight fixed steps with one right order and no script. |
| G-030 | `chestertons-fence` | reference | line 87: `gh pr list --search` is a read | line 87: hand-run PR search | search_originating_pr.py (find PR or ADR for a file) | none | verdict: no; activation: no | P2 | `investigate.py` exists. The PR search is still prose. |
| G-031 | `code-qualities-assessment` | reference | lines 35-44: `assess.py` quick start, local report | line 382: CI recipe whose exit codes the model reads; lines 413, 426, 439: repeat calls | none | none | verdict: no; activation: yes | P2 | One script exists. The exit-code prose is minor. |
| G-032 | `codebase-documenter` | reference | frontmatter grants Read, Write, Edit only | none | none | none | verdict: no; activation: no | P3 | No shell. |
| G-033 | `codeql-scan` | reference | lines 20-33: runs `invoke_codeql_scan.py`, local SARIF | lines 295-303: a diagnostics call outside the locator | none | none | verdict: no; activation: no | P3 | The script owns the scan. |
| G-034 | `context-gather` | reference | reads memory, docs, and web; no remote write | none | none | none | verdict: no; activation: no | P3 | No shell. |
| G-035 | `context-hub-setup` | reference | lines 41, 90: read-only checks | lines 41-48: the model reads `claude plugins list` output by hand | check_plugin_prereqs.py (report missing plugins) | none | verdict: no; activation: yes | P3 | One hand parse of CLI output. |
| G-036 | `context-optimizer` | reference | line 407: a PR command appears only as example input text | lines 313-314: capture recipe with `echo exit=$?` | none | bare `Bash` | verdict: no; activation: no | P2 | Scripts exist. The bare grant is the gap. |
| G-037 | `curating-memories` | reference | line 71: read-only sweep; edits are file edits | lines 111-122: six-step manual edit and verify procedure | none | none | verdict: no; activation: no | P3 | Judgment edits are model work. |
| G-038 | `cva-analysis` | reference | lines 278-290: validator plus routing | lines 360, 433: exit codes read in prose | none | none | verdict: no; activation: no | P2 | The validator exists. |
| G-039 | `cynefin-classifier` | reference | lines 263, 376: `classify.py`, local | lines 376-382: the model tells a launcher failure from a domain by reading stderr and exit 2 | none | none | verdict: no; activation: no | P2 | Exit 2 has two meanings the model parses by hand. |
| G-040 | `decision-critic` | reference | line 47: one local script | none | none | none | verdict: no; activation: yes | P3 | No gap. |
| G-041 | `decision-question` | reference | lines 64, 91: one local script | lines 66-72: the model parses exit 2 plus a stderr line | none | none | verdict: no; activation: yes | P2 | Launcher failure against incomplete input is parsed in prose. |
| G-042 | `destructive-change-safety` | reference | lines 55, 153: gate scripts return verdicts; the skill writes nothing | none | none | none | verdict: no; activation: yes | P3 | Scripts own the work. |
| G-043 | `doc-accuracy` | reference | lines 93-114: local runs and reports | lines 93-114: 21 lines of raw `python3 scripts/doc_accuracy.py` variants outside the locator | none | none | verdict: no; activation: yes | P3 | A flag catalog, not a fixed step. |
| G-044 | `domain-design` | reference | line 102: one local script | none | none | none | verdict: no; activation: yes | P3 | No gap. |
| G-045 | `dx-review` | reference | no shell tools granted | none | none | none | verdict: no; activation: yes | P3 | No shell. |
| G-046 | `evidence-provenance` | reference | line 62: one local script | none | none | none | verdict: no; activation: yes | P3 | The script owns classification. |
| G-047 | `execution-plans` | reference | plan writing guidance; no shell | none | none | none | verdict: no; activation: no | P3 | No shell. |
| G-048 | `fix-markdown-fences` | reference | lines 312-316: a quick check; the fixer writes working-tree files | line 312: a one-line grep fallback | none | none | verdict: no; activation: no | P3 | The fixer and write guard exist. |
| G-049 | `git-advanced-workflows` | driver | lines 139-146: the publish procedure says to commit, rebase, and "Push the topic branch"; lines 42-52: `rebase -i` then a lease-pinned force push | lines 42-52: nine-line fetch, rebase, and push block; lines 65-70: split-commit sequence; lines 249-254: abort block | rewrite_branch_history.py (rebase and lease-pinned push); abort_git_operation.py (abort an in-progress operation) | none | verdict: no; activation: no | P0 | Pushes and rewrites history with no script. A reviewer on PR #7579 showed the publish procedure is an instruction, not an example. |
| G-050 | `github` | driver | line 130: create PR; line 134: comment; line 149: close PR; line 150: merge | lines 126-150: routing tree to about 20 mutating scripts; lines 166-170: three multi-line locator blocks | route_github_operation.py (map intent to script and args) | none | verdict: no; activation: yes | P1 | Mutating and high traffic, with a script behind each write. Over the 12 KiB driver budget. |
| G-051 | `github-url-intercept` | reference | lines 47-56: read-only `gh api` calls | lines 47-56: the model fills owner, repo, and path; lines 139-146: URL parse in prose; lines 110-130: routing tree | route_github_url.py (parse URL and fetch JSON) | none | verdict: no; activation: no | P1 | A blocking intercept on every GitHub URL. Parsing is a fixed step. |
| G-052 | `golden-principles` | reference | lines 64-83: read-only scan | lines 64-83: six variants of one scan command | none | none | verdict: no; activation: no | P3 | The script owns the scan. |
| G-053 | `llm-council` | reference | lines 192-199: local run that calls model APIs | lines 190-199: the model picks locator or direct call | none | none | verdict: no; activation: yes | P3 | Small host-detection fallback. |
| G-054 | `maintainer-review` | reference | lines 45-46: "No remote writes" | none | none | none | verdict: no; activation: yes | P3 | Read-only by its own text. |
| G-055 | `memory` | reference | lines 86-109: writes local memory files | line 318: runs a script by bare path, not the locator | none | none | verdict: yes; activation: yes | P3 | Scripts exist. |
| G-056 | `memory-consolidate` | reference | lines 118-160: memory edits and deletes; no push | lines 114-118: git state block; lines 70-76: file count and size caps enforced by prose; lines 123-126: hand-written manifest JSON | check_memory_tree_clean.py (verify tracked, clean tree); audit_memory_inventory.py (enforce count and size caps) | none | verdict: no; activation: yes | P1 | Deletes memory files with three rules enforced only by prose. |
| G-057 | `memory-documentary` | reference | lines 104-109: slash invocations | none | none | none | verdict: no; activation: no | P3 | No gap. |
| G-058 | `memory-enhancement` | reference | lines 122-130, 271-282: read-only module calls | lines 122-130, 271-282: `python -m` calls outside the locator | none | none | verdict: no; activation: no | P3 | Calls a module outside the locator. |
| G-059 | `memory-gate` | reference | line 53: read-only search | none | none | none | verdict: no; activation: no | P3 | One locator call. |
| G-060 | `memory-maintenance` | reference | lines 51-63, 125-130: local memory scripts | lines 51-63: four locator calls | none | none | verdict: no; activation: no | P3 | Lists scripts that live in the `memory` skill. |
| G-061 | `memory-reflexion` | reference | lines 68-70: `--force` overwrites a local episode file | lines 70, 134, 141: `--force` against `--preserve` explained in prose | none | none | verdict: no; activation: no | P3 | Local write only. The scan's history-rewrite hit is false. |
| G-062 | `memory-search` | reference | lines 25-40: search and read only | lines 33-39: tool choice is a prose decision tree | none | none | verdict: no; activation: yes | P3 | Read-only lookup. |
| G-063 | `merge-resolver` | driver | lines 51, 55: `git merge`, commit, `git push` | lines 66-69: PR view, checkout, merge as a prose table; phases 3.2-3.5: validate, commit, and push for conflicts the model resolves by hand | push_branch.py (push a hand-resolved merge, no force); gather_pr_context.py (fetch PR, checkout, start merge) | none | verdict: no; activation: no | P1 | `resolve_pr_conflicts.py` already commits and pushes automatic resolutions. Only the hand-resolved path commits and pushes in prose. |
| G-064 | `metrics` | reference | lines 234-235: local add and commit | line 110: fetch before recheck; lines 93-117: ten pasted locator blocks | none | none | verdict: no; activation: yes | P3 | Read-only reports. Scripts sit at the skill root, not in `scripts/`. |
| G-065 | `modernize` | driver | lines 153-155: push after the user says yes; lines 61-62: pinned force-with-lease | lines 61-62: lease string built by hand; lines 56-60: fork-head against base-repo compare; line 147: range-diff | rebase_pr_branch.py (rebase, abort on conflict); check_pr_head_repo.py (reject a fork head) | none | verdict: no; activation: yes | P0 | History rewrite plus a force push with zero scripts. Decision 3 item 8 bars a script from the force push. |
| G-066 | `negotiation` | reference | analysis only | none | none | none | verdict: no; activation: no | P3 | Knowledge skill. |
| G-067 | `observability` | reference | lines 110-145: read-only log queries | none | none | none | verdict: no; activation: no | P3 | Scripts exist. |
| G-068 | `orphan-ref-validator` | reference | lines 43-60: read-only scan; writes a baseline file | line 47: argument placement rule in prose | none | none | verdict: no; activation: no | P3 | The scan script exists. |
| G-069 | `panning-for-gold` | reference | lines 49-56: writes under scratch; line 53 `--force` overwrites a file | none | none | none | verdict: no; activation: no | P3 | The scan's history-rewrite hit is false. |
| G-070 | `pipeline-validator` | driver | line 318: `git push`; line 231: `az pipelines run`; lines 355-361, 440: `az repos pr update` | lines 92-124: repo, branch, and PR detection; lines 132-138: MUST NOT flag list; lines 236-248: poll loop; lines 272-279: timeline parse | detect_pipeline_context.py (repo, branch, PR lookup); run_pipeline.py (trigger and poll to a result); update_pr_description.py (edit the PR body) | none | verdict: no; activation: no | P0 | Azure DevOps and git writes with no scripts. Polling and a flag guard live in prose. |
| G-071 | `plan` | reference | lines 60-135: spec to plan file | none | none | no Bash | verdict: no; activation: yes | P3 | Judgment skill. |
| G-072 | `planner` | reference | lines 22-24, 152-158: local script calls; no push | lines 152, 201, 267: bare `python3 scripts/planner.py` calls with no locator | none | none | verdict: no; activation: no | P2 | Script-stepped already, but the calls skip the locator. |
| G-073 | `pr-autofix` | driver | lines 895-896: merge and push; lines 925-926: force push with lease; line 906: thread reply; line 694: merge script | lines 161-690: one 529-line annotated bash program; lines 80-150: transport preflight; lines 916-936: force-push lease rules | preflight_transport.py (pick the transport); run_pr_pass.py (live gate, tier, disarm, round cap); update_branch_from_base.py (fetch, merge, push base) | bare `Bash` | verdict: no; activation: yes | P0 | It mutates PRs and pushes. The safety order lives in prose. |
| G-074 | `pr-babysit` | driver | line 146: update, push, wait again; lines 143-144: merge when the user asked | lines 135-136: branch update by script or local merge; lines 178-181: exit code to action table | none | none | verdict: no; activation: yes | P2 | Already a script-driven watcher. Push and merge stay prose but are rare. |
| G-075 | `pr-comment-responder` | driver | lines 76-77: push fix, post reply, resolve thread | lines 96-110: PR number and repo taken from the prompt; lines 126-152: processing order tables; lines 168-177: domain-first loop | order_threads.py (domain then reviewer priority); infer_pr_context.py (PR and repo from prompt or git) | none | verdict: no; activation: yes | P1 | Scripts exist. Ordering and context inference are prose. |
| G-076 | `pr-quality` | reference | lines 71-90: git read commands; a local gate | lines 71-82: base ref check by regex, then two git calls, then a SHA carried by hand | resolve_base_sha.py (validate base, print the merge-base SHA) | five scoped read-only `Bash(git ...)` entries | verdict: no; activation: yes | P1 | A regex check and a two-step git call are prose. |
| G-077 | `pr-review` | driver | line 220: push per worktree; line 234: thread reply and resolve; lines 194-195: worktree add | lines 109-143 and 243-277: two 17-line bash resolver functions pasted twice; line 183: settle rerun | resolve_pr_paths.py (scripts dir and config); create_pr_worktree.py (add a PR worktree); push_pr_worktrees.py (push each worktree) | `Bash(git:*)`, `Bash(gh:*)`, `Bash(python3:*)`, `Bash(pwsh:*)` | verdict: no; activation: yes | P0 | Broad grants, mutating, duplicated shell resolvers, trust gate in prose. |
| G-078 | `pre-mortem` | reference | lines 250-281: validates a file | line 291: the model re-checks a triad the script passes too easily | none | none | verdict: no; activation: no | P2 | Prose patches a weak script gate. |
| G-079 | `programming-advisor` | reference | lines 194-208: commands are shown to the user, not run | lines 182-186: package manager detected by file presence | detect_project_context.py (package manager and framework) | none | verdict: no; activation: no | P2 | Manifest detection has one right answer. |
| G-080 | `prompt-engineer` | reference | no commands | none | none | none | verdict: no; activation: no | P3 | Judgment content. |
| G-081 | `prose-self-check` | reference | lines 177-258: local lint scripts | none | none | none | verdict: no; activation: yes | P3 | Scripts own the checks. |
| G-082 | `push-pr` | driver | line 109: "Push the branch to origin"; lines 110-121: create the PR with `new_pr.py` | line 47: branch name chosen from the change type; lines 54-62: body file allocated, path copied by hand; lines 77-90: preflight call and its rejections; line 91: description check with exit 1 against exit 2 handling; line 109: push with no script | publish_pr.py (check, push, create in one call); create_branch.py (name and create the branch) | `Bash(git push:*)` plus seven more git grants and scoped script paths | verdict: no; activation: yes | P0 | High traffic. The push at step 6 has no script, and `Bash(git push:*)` also allows force flags. |
| G-083 | `quality-grades` | reference | lines 36-52: writes a report file | lines 129-131: exit code check in prose | none | none | verdict: no; activation: no | P3 | Scripts exist. |
| G-084 | `reflect` | reference | lines 67-94: local memory write | none | none | none | verdict: no; activation: no | P3 | Judgment skill. |
| G-085 | `repository-completion-proof` | reference | lines 52-56, 108-112: runs a completion gate; thread work is delegated | lines 52-56, 108-112: env binding blocks; lines 100-104: three consecutive zero readings | run_completion_proof.py (verify config, merged check, gate, settle) | none | verdict: no; activation: yes | P2 | Gate side effects UNVERIFIED. Two pasted blocks and a settle rule are script candidates. |
| G-086 | `repository-consumer-proof` | reference | lines 61-63, 82-85: read and test commands | lines 82-85: two pytest commands chosen by hand | none | none | verdict: no; activation: yes | P3 | Read and test only. |
| G-087 | `repository-pr-recovery` | reference | lines 50-52, 66-68: diagnosis scripts | lines 46-52: three variables set by hand across blocks | none | none | verdict: no; activation: yes | P2 | Diagnosis only. |
| G-088 | `requirements-interview` | reference | lines 87-89, 114-117: local audit script | none | none | bare `Bash` | verdict: no; activation: yes | P2 | The grant is wider than its two script calls need. |
| G-089 | `research` | driver | lines 156-161: files an issue after the user confirms | lines 112-127: claim ledger run twice with flag sets; lines 160-162: issue arguments assembled by hand; line 224: no-retry rule | run_claim_gate.py (check draft, copy, recheck); file_issue.py (confirm, create, parse the issue number) | two directory-wildcard script grants | verdict: no; activation: yes | P1 | The external write is conditional. Script wildcards and a retry rule live in prose. |
| G-090 | `retrospective` | reference | lines 198, 220: says it does not file issues | none | none | none | verdict: no; activation: yes | P3 | Scripts own the work. |
| G-091 | `review` | reference | lines 172-192: writes a local empty marker commit; no push or external write | line 32: base branch detection; lines 66-80: candidate-path lookup for scripts; lines 174-192: marker commit built from prose | write_review_marker.py (build the SHA-bound marker commit); resolve_review_paths.py (locate chained skill scripts) | `Bash(*)` | verdict: no; activation: yes | P1 | `Bash(*)` on a reference skill. Marker assembly is a fixed step that gates `ship`. |
| G-092 | `reviewer-findings` | reference | lines 82-140: git grep and log only verify claims | lines 82-100: needle and path files keep untrusted text out of the shell; lines 123-130: flag guard on `git grep` | verify_finding_claim.py (check a finding claim at a commit) | none | verdict: no; activation: yes | P1 | Injection guards live as prose around command flags. |
| G-093 | `security-detection` | reference | lines 55-61: read-only usage | none | none | none | verdict: no; activation: yes | P3 | Already scripted. |
| G-094 | `security-review` | reference | no shell; knowledge only | none | none | none | verdict: no; activation: no | P3 | Analysis guidance. |
| G-095 | `security-scan` | reference | lines 92-119: read-only scanner calls | none | none | none | verdict: no; activation: yes | P3 | Variants of one call. |
| G-096 | `ship` | driver | line 158: runs `push-pr` to push and open a PR; line 161: `az repos pr create` after a push | lines 52-64: host detection shell; lines 76-78: PR lookup that tells "no PR" from a failed query by stderr text; lines 82-85: owner or contributor mode; lines 100-131: Azure DevOps policy loop with TSV parsing; lines 96, 163: checks rerun on exit 7; lines 137-145: marker validator resolution and exit codes; line 161: PR creation arguments by hand; line 165: a 30 minute wait loop | detect_ship_context.py (host, mode, PR state); check_pipeline_gate.py (CI gate with deferral); evaluate_ado_policies.py (build policy verdict); wait_ado_policies.py (poll until policies settle); create_ado_pr.py (open the Azure DevOps PR); verify_review_marker.py (validate marker, report axes) | `Bash(*)` | verdict: yes; activation: yes | P0 | The front door for every release. No scripts directory, and `Bash(*)`. |
| G-097 | `skill-bootstrap` | reference | lines 176-229: writes files in the tree only | lines 176-190: hand-built arguments; lines 227-229: flags appended by hand | none | none | verdict: no; activation: yes | P2 | Scripts exist. Argument assembly across phases is the gap. |
| G-098 | `skill-doctor` | reference | line 136: writes only to a scratch directory | lines 47-50: root check; lines 105-107: repo detection; lines 141-155: collector arguments; line 213: a mean computed by hand | resolve_run_context.py (set root, repo, scratch dir) | none | verdict: no; activation: yes | P2 | Setup and aggregate steps are hand work. |
| G-099 | `skillforge` | reference | lines 295-312: validators and packager write local files | lines 295-312: six validators and a packager pasted as one block | run_skill_checks.py (run all skill validators once) | none | verdict: no; activation: yes | P2 | Scripts exist. The run order is prose. |
| G-100 | `skillify` | reference | no shell blocks | none | none | none | verdict: no; activation: yes | P3 | Already gated by a script. |
| G-101 | `skillopt` | disputed | line 283: "Commit and push through the owner's repository workflow" | lines 102-107: locator discovery shell; lines 114-117: directory fallback; lines 276-284: deploy steps by hand | deploy_candidate.py (apply and hash-verify an accepted candidate) | none | verdict: no; activation: yes | P1 | Deploy ends in a push it defers to another workflow. Owner rules on shape. |
| G-102 | `slo-designer` | reference | lines 158-162: writes a local doc | none | none | none | verdict: no; activation: no | P3 | Usage blocks only. |
| G-103 | `software-engineering-library` | reference | no shell | none | none | none | verdict: no; activation: yes | P3 | Knowledge index. |
| G-104 | `sol-loop` | driver | lines 228-231: "Push after agreement only if the user asked to push" and a PR body line | lines 116-120: PR or local base detection; lines 228-231: attribution line added by hand; lines 240-244: run-file path and commit | push_reviewed_branch.py (push and append attribution); commit_run_file.py (commit the metrics run file) | none | verdict: no; activation: yes | P1 | A conditional push and a PR body edit are prose. |
| G-105 | `spec` | reference | no Bash grant | lines 61-66: six answers checked by hand; line 70: hedge-phrase table applied by the model | validate_step0_gates.py (check Step 0 hedge phrases) | none | verdict: yes; activation: yes | P2 | The hedge-phrase check has one right answer. |
| G-106 | `spec-generator` | reference | lines 91-95: writes spec files in the tree | lines 93-95: id and file name picked by hand (UNVERIFIED that no script allocates ids) | allocate_spec_id.py (pick the next spec id) | none | verdict: no; activation: no | P2 | Id and path assembly is prose. |
| G-107 | `steering-matcher` | reference | line 55: read-only matcher | none | none | none | verdict: no; activation: no | P3 | Scripted. |
| G-108 | `stuck-detection` | reference | lines 207-221: local history only | none | none | none | verdict: no; activation: no | P3 | Scripted. The script sits at the skill root, not in `scripts/`. |
| G-109 | `style-enforcement` | reference | lines 34-43: read-only checker | none | none | none | verdict: no; activation: no | P3 | Scripted. |
| G-110 | `sync` | reference | lines 64, 71: read-only drift detector | none | none | one script grant ending in `*` | verdict: no; activation: yes | P3 | The grant's trailing wildcard would conflict with decision 3 item 7 if the skill became a driver. |
| G-111 | `takeover` | driver | lines 65-71: push to the branch, file a replacement PR, merge or close the original when authorized | lines 45-47: import commits; lines 49-56: credit trailers from git log; line 60: update against base; line 69: follow checks and answer threads | import_commits.py (copy contributor commits to a branch); build_credit_trailers.py (derive verified co-author trailers) | none | verdict: no; activation: yes | P0 | Push, merge, and close authority. The whole lifecycle is prose with no scripts. |
| G-112 | `taste-lints` | reference | lines 93-112: read-only scanner | line 98: uses a base variable this skill never sets | none | none | verdict: no; activation: no | P3 | Scripted. |
| G-113 | `technical-writing` | reference | no shell | none | none | none | verdict: no; activation: yes | P3 | Guidance. |
| G-114 | `test` | reference | lines 71, 142, 157: no push, merge, or external write | lines 71-78: base branch, changed files, then a file-type table by hand; line 142: hand arguments | classify_changed_files.py (map a diff to test gates) | `Bash(*)` | verdict: no; activation: yes | P1 | `Bash(*)` on a reference skill. The classification table has one right answer. |
| G-115 | `threat-modeling` | reference | lines 191-193: local report | none | none | none | verdict: no; activation: yes | P3 | Scripted. |
| G-116 | `using-serena-symbols` | reference | Python blocks are call examples | none | none | none | verdict: no; activation: no | P3 | Knowledge. |
| G-117 | `validate-pr-description` | reference | lines 107-124: validates only | lines 102-105: discard one warning, ignore an exit code; lines 107-124: two validators merged by hand | validate_pr_body.py (run both validators, one verdict) | `Bash(python3:*)`, `Bash(git:*)` | verdict: no; activation: yes | P1 | Broad grants. The model parses validator output by hand. |
| G-118 | `validation-authority` | reference | lines 93-95: local decision record | lines 108-110: record path resolved in prose | none | none | verdict: no; activation: no | P3 | One path rule. |
| G-119 | `windows-image-updater` | driver | line 299: `git push -u origin`; line 383: `git branch -D`; line 384: `git reset --hard`; a draft PR near line 303 | lines 80-96: clone and branch by hand; lines 288-299: add, commit, push block; lines 303-325: pasted PR body; lines 383-384: rollback commands | prepare_branch.py (clone and branch); commit_and_push.py (commit then push); create_draft_pr.py (open a draft PR from a template) | none | verdict: no; activation: no | P0 | Pushes, deletes a branch, rewrites history, and creates a PR with no scripts. |
| G-120 | `work-operating-model` | reference | writes local JSON | none | none | none | verdict: no; activation: no | P3 | The validator exists. |
| G-121 | `world-model-diagnostic` | reference | no shell | none | none | none | verdict: yes; activation: no | P3 | Interview guidance. |
