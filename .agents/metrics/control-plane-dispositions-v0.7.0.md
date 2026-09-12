---
# taste-lint: ignore file-size, per-candidate disposition ledger with a REQ-022 evidence obligation per row; splitting renumbers rows other artifacts cite by name and breaks the cohort's audit trail.
type: metrics
id: control-plane-dispositions-v0.7.0
title: Control-plane disposition ledger for v0.7.0
epic: EPIC-5456
baseline_sha: 53ffe92c264884904865bf437cbb3ab043e79a27
baseline_path: .agents/metrics/control-plane-baseline-v0.7.0.json
created: 2026-09-11
status: draft
---

# Control-plane disposition ledger, v0.7.0

Satisfies REQ-022. One row per epic-named candidate, plus the redundancy
this cohort's own research surfaced. Pinned baseline: commit
`53ffe92c264884904865bf437cbb3ab043e79a27`
(`.agents/metrics/control-plane-baseline-v0.7.0.json`, not yet merged to
`main` at the time this ledger was written; cited by path per the
disposition contract). Depends on PR #5725 for the baseline file paths;
merge after it.

## Rows

### #5394, Serena thinning

- Class: `EXPERIMENT`
- Owner: issue #5394
- Consumers: `.serena/memories/**`, whichever agent reads Serena at session
  start
- Evidence: `gh issue view 5394` state `OPEN`; blocked-by #5391 (`OPEN`),
  #5392 (`OPEN`), #5393 (`OPEN`). Priority label `P3`.
- Rationale: #5394 cannot start; its own body states "Blocked by #5391,
  #5392, #5393" and "Do not perform final cleanup until the placement
  contract and both extraction streams are merged." All three blockers are
  open. Value is real (baseline counts 1,037 Serena memories,
  `policy_owners.serena_memories`) but unmeasured until the blockers land,
  so `EXPERIMENT` rather than `KEEP` or `DELETE`: the mechanism has a
  defined bounded scope (#5394's cleanup algorithm) once its inputs exist.

### #5395, code-reviewer consolidation

- Class: `EXPERIMENT`
- Owner: issue #5395
- Consumers: `.claude/agents/code-reviewer.md`, `/review` (Stage-2 axes),
  reviewers who invoke the agent directly
- Evidence: `.claude/agents/code-reviewer.md:1-15`. Line 3: "Use this
  agent when you need to review code changes for correctness, discovered
  project-convention compliance, and duplicated logic." Line 4: `model:
  haiku`. Line 15: "You are a read-only code reviewer." Separately,
  `.claude/skills/review/SKILL.md:27-29`: canonical axis set is 11
  Stage-2 axes plus `spec-compliance`, auto-discovered from
  `references/*.md`. Overlap found on direct comparison.
  `.claude/skills/review/references/code-quality.md:10` reviews
  "maintainability of the code it changes: how cohesive, loosely coupled,
  encapsulated, testable, and non-redundant"; `code-reviewer.md:3` reviews
  "duplicated logic". Both surfaces check for the same redundancy defect
  under different names. `.claude/skills/review/references/analyst.md:66`
  ("Do not emit a finding that duplicates another axis") shows the
  canonical pipeline already anticipates cross-axis overlap between its
  own 11 axes, but names no rule covering the agent, which sits outside
  that set. `gh issue view 5395` state `OPEN`, blocked by #5396 (`OPEN`).
- Rationale: the two surfaces are not identical (agent: ad hoc invocation,
  read-only, Haiku-cost, correctness plus duplication; skill: the
  canonical 11-axis pipeline with `analyst`/`architect`/`security`/etc.
  roles), so this is not a clean duplicate-owner `MERGE` today. But the
  redundancy-detection overlap between `code-reviewer` and the
  `code-quality` axis is real, not merely a naming coincidence, which is
  exactly what a bounded ablation should resolve: run one review cycle
  with `code-reviewer` disabled and confirm `code-quality` still catches
  the duplication findings the agent used to report. #5395's own body
  frames the broader question as "whether `code-reviewer` should remain
  an agent at all," a design question this overlap sharpens but does not
  settle. Blocked by #5396, itself blocked. `EXPERIMENT`: the overlap is
  measured, the ablation is unrun, so this is neither `KEEP` (no
  completed justification exists) nor `DELETE` (no evidence the agent's
  distinct correctness/convention findings are covered elsewhere); `MERGE`
  is blocked on #5396's capability-ownership mechanism landing first.

### #5396, capability DAG

- Class: `EXPERIMENT`
- Owner: issue #5396
- Consumers: #5395, #5404 (via its dependency list), any future capability
  ownership tracking
- Evidence: `gh issue view 5396` state `OPEN`. Epic #5456 Execution section:
  "reduce policy owners rather than adding a second graph authority."
- Rationale: the epic's own text is a caution against this mechanism, not
  an endorsement. #5396 proposes a new dependency-graph/ownership registry;
  the epic's Abort-if clause 3 forbids "a new registry, evaluator, ratchet,
  or governance layer before deleting the mechanism it was meant to
  simplify." No evidence in this cohort's research shows #5396 has started
  or has a scoped, bounded ablation. `EXPERIMENT` records that the value is
  uncertain and the epic itself flags the risk of over-scoping it into a
  second graph authority; it does not clear to `KEEP` (nothing built and
  measured yet) and should not be `DELETE`'d outright since capability
  ownership confusion is a named epic problem.

### #5404, terminal-state contract

- Class: `KEEP`
- Owner: `.claude/rules/builder-ethos.md` (Task Completion Contract
  section), `.claude/rules/voice.md` (Completion-Tail Audit section),
  ADR-105
- Consumers: every agent template composing task-completion semantics
  (orchestrator, critic, qa, implementer); every skill lifecycle command
- Evidence: PR #5506 (`fix(rules): add terminal-state invariant to stop
  completed agent runs`, merge commit `a7c3626880decc7f3c7c7e65fc6278a481e88637`,
  state `MERGED`); PR #5537 (`docs(architecture): ADR-105 terminal-state
  completion contract, superseding PR #5433`, merge commit
  `fa0b0258eea37deb19d5cf5c50a386a01031fca1`, state `MERGED`); `gh issue
  view 5404` state `OPEN` (the issue tracks the design, the contract it
  requested has already shipped). Live guard, not provenance alone:
  `tests/test_completion_terminal_contracts.py:112-114`, function
  `test_builder_ethos_carries_the_terminal_contract`, asserts
  `TERMINAL_CONTRACT_PHRASES` are present in every `builder-ethos.md`
  path; `tests/evals/completion-terminal-runtime-fixtures.json` exists on
  this branch, its `_scope_note` field naming issue #5404 directly as a
  regression backstop for the completion-tail audit. Both files were
  opened and confirmed present this session.
- **Current outcome protected**: an agent that satisfies a request and
  then keeps working on scope nobody asked for, or appends an unsolicited
  continuation prompt ("Want me to also...") after a terminal response,
  per #5404's Problem section.
- **Evidence failure occurs**: #5404's body cites the concrete failure
  pattern (execution continuation, response reopening) and its own
  scenario matrix (14 scenarios); the mechanism ships as always-on rule
  content, counted in the baseline's `always_loaded` figures.
- **Why simpler insufficient**: a per-agent instruction would duplicate
  policy across every template; #5404's design explicitly centralizes
  ownership in two rule files rather than repeating the contract per
  consumer.
- **Owner and consumers**: as above.
- **Cost**: counted inside `always_loaded.claude_code` (16,879 tokens,
  baseline `always_loaded.claude_code.tokens`, part of the five always-on
  rules; see the always-on-rules row below for the itemized cost of the
  rule files themselves).
- Rationale: this candidate is delivered, not pending. The epic body's
  one-line description ("stop terminal runs from manufacturing more work")
  is satisfied by merged PRs and an accepted ADR, so `KEEP` records the
  already-shipped mechanism rather than treating it as open work.

### #5420 and #5421, generated-state separation

- Class: `EXPERIMENT`
- Owner: `.claude/lib/paths.py` `resolve_artifact_root` (the live write
  path #5420 targets for redirection)
- Consumers: `.claude/skills/chaos-experiment/scripts/generate_experiment.py`,
  `.claude/skills/retrospective/scripts/run_retrospective.py`, and
  `.claude/skills/retrospective/scripts/extract_evidence.py` (found by
  `grep -rl resolve_artifact_root .claude/skills/`, the callers that
  actually write, as opposed to `artifact_dir`, the read-only sibling)
- Evidence: `.claude/lib/paths.py:24` reads "artifacts to a consumer-side location, defaulting to `<cwd>/.agents/<subdir>`." `.claude/lib/paths.py:195` defines
  `resolve_artifact_root`, and its docstring at `:198` repeats "The
  default root is `<cwd>/.agents`." `git branch -r | grep 5420` returns
  six unmerged branches (`codex/5420-a-paths`, `codex/5420-b-prompts`,
  `codex/5420-c-gate`, `codex/5420-d-consumers`, `codex/5420-e-docs`,
  `codex/5420-project-toolkit-write-targets`); `git ls-tree -r origin/main
  --name-only | grep -c '^\.project-toolkit'` returns `0`; `gh issue view
  5420` and `gh issue view 5421` both state `OPEN`.
- Rationale: this is a relocation, not a deletion. #5420 redirects a live
  write target (`.agents/**`) to a new root (`.project-toolkit/**`); no
  evidence in this ledger shows any byte is dropped rather than moved, so
  `DELETE` overstates it. Six unmerged branches against zero adoption is
  evidence the current single-PR approach is not converging, but it is not
  evidence the underlying redirect has no value. `EXPERIMENT`, with the
  bounded ablation #5420's own scope already implies: land the redirect
  for one write-target subtree (for example the three consumers named
  above) rather than all of `.agents/**` at once, then report bytes
  actually removed from `.agents/**` against bytes moved to
  `.project-toolkit/**`. `DELETE` applies only to whatever that
  measurement shows dropped outright (stale generated state with no
  surviving consumer), not to the relocated majority. #5421 stays blocked
  by #5420 in either case ("Blocked by #5420... Do not begin destructive
  moves until #5420 has redirected all live project-toolkit writes").
- **Measurement posted, 2026-09-11** (`gh issue view 5420` latest comment,
  taken on `main` at `4cfd04970`, tracked files only, per-write-target
  table across `sessions/*.json`, `sessions/handoffs/`, `memory/episodes/`,
  `qa/`, `analysis/`, `metrics/`, `eval-results/`, `planning/`,
  `pr-checks/`, `scratch/`, `checkpoints/`): a move would **DELETE 1 file
  and 0 bytes** (`checkpoints/.gitkeep`, the only entry classed `DEAD`),
  **MOVE about 5.9 MB across 1,166 live files** (handoffs, episodes, qa,
  metrics, eval-results, planning, pr-checks; at least 14 reader
  `file:line` sites to re-point), and **leave about 12.7 MB of history**
  (top-level session logs, `analysis/`) that the epic's non-goals protect
  and that several validators still read. The issue's own reading: "this
  issue as written is relocation, not subtraction... it earns no
  release-gate credit. The one honest DELETE is `checkpoints/`." This
  cohort's PR independently deleted that one honest DELETE
  (`.agents/checkpoints/.gitkeep`, commit `cf4af2849`, see the Cohort 2
  deletions section below) before this measurement was read, so the
  measured DELETE line item and this cohort's item 11 are the same file.
  Classification stays `EXPERIMENT`: 1,166 files and 12.7 MB remain
  unresolved relocation/retention questions this measurement does not
  settle on its own.

### #5436, fan-out cap

- Class: `DELETE`
- Owner: N/A, both issues closed
- Consumers: N/A
- Evidence: `gh issue view 5436` state `CLOSED`. `gh issue view 5651`
  (`decision(orchestration): where does the fleet fan-out cap live, harness
  setting or repo-owned dispatcher`) state `CLOSED`, body: "Option A.
  Harness setting... Zero code in this repository... #5436 becomes a
  feature request against the CLI."
- Rationale: #5651 resolved the blocking decision for #5436 in favor of
  Option A (harness setting, not a repository-owned dispatcher), and both
  issues are closed. `DELETE` from this repository's scope: the fix routes
  to the CLI vendor, not to `ai-agents` code, so there is no repository
  mechanism left to classify `KEEP`/`MERGE`/`EXPERIMENT` against. Files
  removed in this repository: 0. The mechanism never existed here (#5651:
  "There is no dispatcher, no queue, and no worker pool in this repository
  to add a cap to"), so this row is excluded from any deletion tally the
  release report totals; `DELETE` here records "no repository mechanism to
  retain," not "a mechanism was removed."

### #5241 / ADR-100, items 1 through 6

ADR-100 names six items across five work streams (`#5241`'s Work items 1-5,
plus item 6 tracked separately per ADR-100's Decision). One row per item
per this ledger's per-candidate granularity, since the items have
different owners and states.

#### Item 1: commit-ceiling enforcement (both sites)

- Class: `DELETE` (already delivered)
- Owner: ADR-099 (`.agents/architecture/ADR-099-remove-commit-limit-bypass-gate.md`)
- Consumers: `scripts/validation/pr_commit_count.py`,
  `scripts/validation/git_hook_policy.py` `_check_commit_limit`,
  `scripts/ci/enforce_pr_validation.py`
- Evidence: PR #5234 (`fix(ci): remove the commit-limit-bypass gate`),
  merge commit `3487d2f694ce45f1aed3028c51c935ec10b552d0`, state `MERGED`,
  closes #5233.
- Separately, `scripts/validation/pr_commit_count.py:73-74` (read this
  session) reads: "Advisory only (issue #5233): neither threshold blocks
  a push or a merge." No `BLOCK_THRESHOLD` or `MAIN_MERGE_BLOCK_THRESHOLD`
  symbol remains in the file (grep for both names in that file returns
  nothing).
- Rationale: fully delivered and merged. `DELETE` records that the blocking
  mechanism itself is gone (both sites advisory-only), matching this
  ledger's convention of recording already-completed removals rather than
  reopening them.

#### Items 2-4: atomic-commit cap, scope check, `SKIP_SCOPE_CHECK`

- Class: `DELETE` (already delivered)
- Owner: PR #5723
- Consumers: `scripts/validation/git_hook_policy.py` `check_atomic_commit`,
  `scripts/detect_scope_explosion.py`, `.claude/rules/universal.md`
- Evidence: PR #5723 (`refactor(hooks): demote atomic-commit and scope
  ceilings to advisory (ADR-100 items 2 to 4)`), merge commit
  `efdfe5b3190340e363737ec92033da720fc259c0`, state `MERGED` (this is this
  branch's `main` HEAD, `git log --oneline -1` on `origin/main`).
  `.claude/rules/universal.md:30` (read this session): "5. **Atomic commits
  (advisory)**. Keep commits to five or fewer authored files... `check_atomic_commit`
  reports over the limit and does not block." `scripts/detect_scope_explosion.py:51`
  still defines `BLOCK_THRESHOLD = 50` but the symbol now only sizes a
  progress bar and an advisory message (`:411-414`, `:464-466`); `grep -n
  SKIP_SCOPE_CHECK scripts/detect_scope_explosion.py` returns only the
  file's own historical-removal comment at line 9 ("the former
  SKIP_SCOPE_CHECK bypass no longer exists").
- Rationale: delivered by the PR merged onto this branch's `main`. `DELETE`
  records the removed blocking behavior and the removed bypass flag.

#### Item 5: `post_qa_code_changes` rebind churn

- Class: `DELETE`
- Owner: `.claude/lib/qa_report.py`
- Consumers: QA rebind workflow
- Evidence: `.claude/lib/qa_report.py:294-311` (read this session)
  documents that the walk "used to pass" `-m` and was replaced by
  `--first-parent` combined with `--cc` (issue #5064), with a documented
  ancestry check and an all-parent fallback only for an off-chain QA
  commit. `grep -n "\-m \|diff-merges\|git log --format"
  .claude/lib/qa_report.py` returns no unconditional `-m` call and no
  `--diff-merges=combined`/`-c` flag, confirming the naive construct
  #5241 item 5 describes ("Replace `-m` with `-c`") is absent from the
  file.
- Rationale: `DELETE`, not a deferral. The epic's Disposition contract
  names `DELETE` for "requirement obsolete or unreachable," and that is
  exactly this row: the specific fix #5241 item 5 proposes targets code
  that no longer exists in that shape. The file already solved a related,
  more general problem (#5064's stale-rebind defect) with a different
  mechanism (`--first-parent --cc` plus an ancestry check) before this
  cohort started. There is nothing left in `qa_report.py` for #5241 item
  5's proposed `-m`-to`-c` edit to apply to.
- **Status, confirmed obsolete on #5241** (2026-09-11 comment, read this
  session): "Item 5 triage, 2026-09-11: the rebind churn no longer occurs,
  so item 5 is obsolete rather than pending." Evidence cited there:
  `.claude/lib/qa_report.py:286-336` walks `--first-parent --cc` on the
  first-parent chain and falls back to `-m` only off-chain; "Measured on
  the last 40 merged PRs: **0 commits** whose headline matches a rebind,
  QA-evidence, or session-evidence refresh pattern." One residual gap is
  named and explicitly out of this item's scope: the `-m` fallback at
  `qa_report.py:335` can still over-report if a QA commit falls off the
  first-parent chain (ADR-100 lines 278-292); nothing in the last 40
  merges shows it recurring.

#### Item 6: push-ceiling telemetry re-measure

- Class: `EXPERIMENT`
- Owner: issues #5238, #5239 (per PR #5234's body, "Refs #5238, #5239")
- Consumers: any future re-confirmation of ADR-099/ADR-100's retirement
  decision
- Evidence: PR #5234 body: "Refs #5238... 90-day re-measure follow-up
  (ADR-099/ADR-100 confirmation trigger)... Refs #5239... Push-ceiling
  telemetry follow-up (ADR-099/ADR-100 Decision item 6)."
- Rationale: `EXPERIMENT`, not a deferral. This is a bounded, time-gated
  measurement, exactly the shape the epic's Disposition contract reserves
  for `EXPERIMENT` ("value is genuinely uncertain and a bounded ablation
  can decide it"): #5238/#5239 own a 90-day telemetry window that decides
  whether the retired commit-ceiling stays retired or the data shows a
  case for reinstating some form of it. The ablation is already scoped by
  its owning issues; this row records that it has not concluded, not that
  it is out of this cohort's scope.

### Duplicate pre-push ratchet execution

- Class: `KEEP`
- Owner: `scripts/validation/pre_pr_sequence.py`
- Consumers: `lefthook.yml` pre-push hook, `pre_pr.py` (direct invocation),
  CI
- Evidence: `scripts/validation/pre_pr_sequence.py:543-554`, `fast_stage_ran =
  os.environ.get(FAST_STAGE_RAN_ENV) == "1"` through the skip block's
  `continue` (read this session, the full skip-and-record block);
  `lefthook.yml:590`, `AI_AGENTS_PRE_PR_FAST_STAGE_RAN: "1"` (read
  this session); `tests/validation/test_pre_pr_sequence_registry.py:133-141`
  defines `FAST_STAGE_DUPLICATES = frozenset({"Count Ratchets",
  "Unreachable Code Detection", "Path Normalization", "Planning Artifacts",
  "Em/en-dash Prohibition"})` and `:238-266` (`class TestFastStageDeferral`)
  exercises the skip behavior directly (read this session, confirms both
  the frozenset and the test class exist in the cited range).
- **Current outcome protected**: the five fast-stage lefthook jobs
  (`count-ratchets`, `unreachable-code-detection`, `path-normalization`,
  `planning-artifacts`, `em/en-dash-prohibition`) do not re-run a second
  time inside the same pre-push hook invocation via `pre-pr-validation`.
- **Evidence failure occurs**: the duplicate-run defect was real (see the
  corrected Serena memory,
  `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`, "The
  same work runs twice in one hook" section, measured 2026-08-19), and is
  now fixed: `TestFastStageDeferral.test_flag_defers_exactly_the_duplicate_gates`
  asserts the emitted gate set excludes exactly `FAST_STAGE_DUPLICATES`
  when the env flag is set.
- **Why simpler insufficient**: removing the fast-stage lefthook jobs
  entirely (instead of skip-on-duplicate) would lose their parallelism
  inside the pre-push hook; removing `pre-pr-validation`'s own copies
  entirely would break the standalone `uv run python
  scripts/validation/pre_pr.py` path, which does not set
  `AI_AGENTS_PRE_PR_FAST_STAGE_RAN` and must still run all gates (the
  lefthook.yml comment at line 589 states this directly: "Direct
  pre_pr.py and CI calls leave this unset and run all gates").
- **Owner and consumers**: as above.
- **Cost**: `gate_budget.seconds_by_hook.pre-push` in the baseline is
  3,450.0 seconds; this mechanism is what keeps that figure from including
  a second run of the five duplicated gates.
- Rationale: this row is REQ-022's motivating example (AC-03). It was
  already fixed by PR #5418 (`perf(hooks): consolidate pre-push ratchets`,
  merge commit `4e33c4baa0b070ef35ffe4b491fcd9ff16d49223`, state `MERGED`)
  before this ledger was written; recording it `KEEP` here, rather than
  proposing a fourth deletion PR, is exactly the failure this ledger exists
  to prevent (see REQ-022 Q2).

### Five always-on rules: `builder-ethos`, `claude-model-patches`, `search-before-building`, `universal`, `voice`

- Class: `KEEP` (one shared row; the five files are identically justified)
- Owner: `.claude/rules/{builder-ethos,claude-model-patches,search-before-building,universal,voice}.md`
- Consumers: every Claude Code session (always-loaded, per the baseline's
  `always_loaded.claude_code.files` list); mirrored to every Copilot
  session via `.github/instructions/*.instructions.md`
- Evidence: baseline JSON `dimensions.always_loaded.claude_code.files`
  lists exactly these five rule files plus `.claude/CLAUDE.md`, `AGENTS.md`,
  `CLAUDE.md`; `dimensions.policy_owners.always_on.claude_rules` lists the
  same five paths; `tests/validation/test_always_on_corpus_claims.py`
  (read this session) defines
  `test_doctrine_table_matches_measured_always_on_set`,
  `test_doctrine_always_on_figures_match_the_measured_mirror`, and
  `test_doctrine_largest_always_on_rule_matches_the_source_tree`
  (line 231, asserting `voice.md` is the largest always-on rule) as the
  guard that keeps doctrine prose and measured bytes in sync.
- **Current outcome protected**: branch discipline, PR/issue linkage,
  evidence-citation discipline, commit atomicity, dash prohibition
  (`universal.md`); task-completion termination and completion-tail
  wording (`builder-ethos.md`, `voice.md`); model-specific tool-selection
  and todo-discipline nudges (`claude-model-patches.md`); search-before-
  build discipline (`search-before-building.md`).
- **Evidence failure occurs**: `test_always_on_corpus_claims.py`'s battery
  of tests exists specifically because these files' doctrine prose has
  drifted from measured reality before; the tests are the mechanism that
  catches recurrence.
- **Why simpler insufficient**: these are prose policy, not code; there is
  no simpler mechanism than a loaded instruction file for content that must
  bind every session unconditionally (branch discipline, no-secrets,
  no-force-push).
- **Owner and consumers**: as above.
- **Cost**: `always_loaded.claude_code.tokens` is 16,879 (baseline); this
  is also the epic's own release target
  (`release_targets[1]`, "always_loaded.claude_code.tokens... strictly
  below 16879"), so this ledger's `KEEP` classification does not exempt
  these five files from the release's own token-reduction gate. They are
  retained as a class; individual line-level reduction inside them remains
  in scope for the release gate, separately from this ledger's
  candidate-level disposition.
- Rationale: these are the five files a KEEP row is easiest to write for:
  every consumer, every failure mode, and every cost figure is directly
  measured in the baseline and guarded by an existing test file, which is
  exactly DR2's bar.

### Rule mirror trees, `.github/instructions` (30 files) and `src/copilot-cli/instructions` (24 files)

- Class: `KEEP`
- Owner: `build/scripts/generate_rules.py` (generator); canonical source is
  `.claude/rules/*.md`
- Consumers: Copilot CLI sessions (`.github/instructions/`), vendored
  Copilot CLI plugin installs (`src/copilot-cli/instructions/`)
- Evidence: `find .github/instructions -name '*.md' | wc -l` returns `30`;
  `find src/copilot-cli/instructions -name '*.md' | wc -l` returns `24`
  (both counted this session, matching baseline
  `policy_owners.rule_mirrors.github_instructions: 30` and
  `policy_owners.rule_mirrors.copilot_cli_instructions: 24`).
  `.claude/rules/canonical-source-mirror.md` (read this session) is the
  rule that governs this exact pattern: a mirrored surface must cite and
  quote the canonical source verbatim, or document a stricter/looser/
  different divergence. `build/scripts/generate_rules.py:23` ("Emit to
  ``.github/instructions/<name>.instructions.md``") is the generator that
  produces the `.github/instructions` tree from `.claude/rules/`.
- **Current outcome protected**: Copilot CLI sessions and vendored Copilot
  CLI plugin installs receiving the same rule content Claude Code sessions
  get, without a human or agent hand-editing either mirror out of sync
  with `.claude/rules/*.md`.
- **Evidence failure occurs**: `.claude/rules/canonical-source-mirror.md`
  exists specifically because a mirrored surface drifting from its
  canonical source is a real, named failure mode this repository guards
  against; the generator (`build/scripts/generate_rules.py`) is the
  enforcement mechanism, not merely documentation of intent.
- **Why simpler insufficient**: without generation, each of the 54
  mirrored files (30 + 24) would need independent hand-maintenance across
  two harnesses, which is exactly the duplicate-owner failure `MERGE`
  targets elsewhere in this ledger; a single generator with one canonical
  source avoids creating that failure in the first place.
- **Owner and consumers**: as above (`generate_rules.py` owner; Copilot
  CLI sessions and vendored plugin installs consumers).
- **Cost**: 54 generated files
  (`generated_historical.generated_projections.github_instructions.count:
  30` plus `policy_owners.rule_mirrors.copilot_cli_instructions: 24`)
  is the maintenance and portability cost measured; no
  additional always-loaded token cost beyond what the five always-on
  rules row already counts, since these are per-harness projections of
  that same content, not additional content.
- Rationale: this is not a duplicate-owner problem the epic's `MERGE`
  disposition targets. `MERGE` means "duplicate owners or representations"
  where a human or an agent could independently edit either copy and
  diverge; here, one script (`generate_rules.py`) owns generation and
  `canonical-source-mirror.md` is the rule that keeps the mirrors from
  becoming independently-authored duplicates. `KEEP`: the generator is the
  canonical owner, not the mirrors themselves. The five always-on rules
  row above already carries the primary KEEP justification for the
  content; this row exists so the epic-named "redundant... generated
  mirrors" clause has an explicit disposition rather than being silently
  folded into the rules row.

### `scripts/metrics/control_plane_baseline.py`

- Class: `EXPERIMENT`
- Owner: this cohort's sibling PR (branch `feat/5456-control-plane-
  baseline`, per this task's own instructions)
- Consumers: this ledger (reads its JSON/markdown output); any future
  baseline re-run
- Evidence: `baseline-53ffe92c2.json`'s `command` field records
  `scripts/metrics/control_plane_baseline.py` invoked with `--repo`, a
  local worktree path (elided here per this repository's path-
  normalization convention), `--json`, and `--markdown` writing to
  `.agents/metrics/control-plane-baseline-v0.7.0.json` and
  `.agents/metrics/control-plane-baseline-v0.7.0.md`. This script does
  not exist on this branch's `main`
  (`ls scripts/metrics/control_plane_baseline.py` fails on this worktree,
  confirming it ships only via the unmerged sibling PR); `grep -rn
  control_plane_baseline lefthook.yml scripts/validation/pre_pr_sequence.py
  .github/workflows/*.yml` returns nothing, confirming it is wired into no
  gate.
- Rationale: measurement-only tooling that produces this ledger's own
  input data, with exactly one consumer today (this ledger). `EXPERIMENT`,
  not `KEEP`: one consumer is not yet evidence of durable value, only of
  a single completed use. Bounded ablation: re-run the script at release
  close; if no second consumer beyond this ledger has appeared by then
  (no other document, gate, or script reads its JSON/markdown output),
  delete it. It carries no blocking cost either way (wired into no gate),
  so the ablation costs nothing beyond the re-run itself.

## Cohort 2 deletions, epic #5456 (this PR)

Eleven candidates from the 2026-09-04 ponytail audit
(`.agents/audit/2026-09-04-ponytail-audit-over-engineering.md`), re-verified
zero-reader on 2026-09-11 and deleted in this PR. Each row's evidence is the
audit finding number plus the zero-reader grep run in this session, not a
re-citation of the audit alone. `git diff --stat origin/main..HEAD` totals 68 files changed; of those, 56
are the tracked-file deletions this section itemizes below, summing to
26,508,890 bytes removed (measured via `git cat-file -s
origin/main:<path>` per deleted file, this session) across the ten
file-deleting items (the eleventh, `.qualityrc.json`, removes config
keys, not a file). The remaining changed files are dangling-reference
edits (allowlists, doc rows, a test's docstring count) itemized per row
below.

### Skillforge slide-deck PNGs (audit finding 1)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: `.skillignore` line 11 already excludes `assets/images` from
  every skill install; a grep for each of the 13 basenames across
  `*.md`/`*.py`/`*.json`/`*.yml` in both trees returned zero hits this
  session. `build_all.py --check` showed no drift after the canonical
  `.claude/` tree was deleted while the `src/copilot-cli/` mirror still
  held all 13 files, confirming the skills generator does not prune a
  `.skillignore`-excluded path; the mirror was deleted directly rather
  than left to self-prune.
- Status: deleted in this PR. Files: 26 (13 per tree). Bytes: 26,389,306
  (measured via `git cat-file -s origin/main:<path>` per file, this
  session). Commits: `069d6e4a9`, `7b87c6d04`, `ca5b048f5` (canonical),
  `f89171f4a`, `8a833486c`, `70b738432` (mirror).

### `.diffray/` rules engine (audit finding 8)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: repo-wide grep found only the root-hygiene allowlist entry
  (`scripts/validation/git_hook_policy.py`), a `.markdownlint-cli2.yaml`
  ignore line, the same ignore line in `.claude/hooks/PreToolUse/
  markdownlint-safe-config.yaml`, and a `docs/project-structure.md` row;
  no workflow, hook, or script invokes a `diffray` binary. The mirror
  copy of the hook config (`src/copilot-cli/hooks/PreToolUse/
  markdownlint-safe-config.yaml`) and its `.claude/` source were left
  unedited: both are pinned by SHA-256 in
  `scripts/ci/validate_vendor_provenance.py` (`_PIN_CONFIG_SHA256`) and
  gated by `.github/workflows/vendor-provenance.yml`'s path filter, whose
  own docstring requires trust-anchor pin changes in a separate bootstrap
  PR. That one dead `.diffray/**` ignore line stays in those two files.
- Status: deleted in this PR. Files: 12 tracked files plus 3 dangling
  references removed (allowlist entry, root `.markdownlint-cli2.yaml`
  line, `docs/project-structure.md` row). Bytes: 61,317. Commits:
  `47fb03b93`, `81fa0d911`, `e03c6220c`.

### Root TypeScript island (audit finding 9)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: no root `package.json` or `tsconfig.json` covers `src/*.ts` or
  `src/transforms/`; `cli-smoke.yml`'s only `bun test` step sets
  `working-directory: packages/ai-agents-cli`, a sibling tree. Four docs
  described the files: ADR-107 (evidence sentence updated to past tense,
  with a self-review round appended to
  `.agents/critique/ADR-107-debate-log.md` to satisfy
  `adr-review-policy`), `src/AGENTS.md`, `tests/AGENTS.md`, and
  `.agents/governance/test-location-standards.md`; `docs/project-
  structure.md`'s row describing the same files was removed in the same
  pass since it was already touched this session for an unrelated row.
- Status: deleted in this PR. Files: 6 source/test files plus 5 docs
  edited. Bytes: 19,738. Commits: `031241100`, `b4875a763` (deletion),
  `c0cbfe3a1`, `c1b7788c3` (docs).

### One-shot migration scripts (audit finding 10)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: `scripts/restructure_memories.py` (Serena memory
  topic-subdirectory migration) and `scripts/mutation_test_proc_group.py`
  (process-group timeout mutation harness) are both one-shot tools for
  finished migrations; grep found zero code callers, only two historical
  Serena memory prose mentions and one synthetic PR-body test fixture
  string, none of which executes the file.
- Status: deleted in this PR. Files: 2. Bytes: 19,829. Commit:
  `a55fe7e28`.

### Disabled droid workflows (audit finding 12)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: GitHub Actions never loads a `.disabled` workflow file; grep
  found only a `.github/AGENTS.md` Skip bullet documenting them and one
  historical session log.
- Status: deleted in this PR. Files: 2 plus the `.github/AGENTS.md` Skip
  bullet and workflow count updated. Bytes: 2,890. Commit: `a7f0e17a4`.

### `.baseline/coverage-thresholds{,.schema}.json` (audit finding 13)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: schema keys on `*.Tests.ps1`; `git ls-files '*.ps1'` returns
  zero files. Grep found only historical archive session logs.
- Status: deleted in this PR. Files: 2 plus the `.baseline` root-hygiene
  allowlist entry removed (directory now holds no tracked files). Bytes:
  1,665. Commit: `053ef3233`.

### `steering-matcher.skill` (audit finding 14)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: a PowerShell-generator build artifact carrying a "GENERATED
  FILE / Do not edit" header that `universal.md` MUST NOT item 5 forbids;
  `build_all.py --check` confirmed `generate_skills.py` does not recreate
  either copy, so both are stale hand-committed artifacts, not generated
  output.
- Status: deleted in this PR. Files: 2 (canonical and mirror). Bytes:
  858. Commit: `16b7933b2`.

### CodeQL suppressions (audit finding 15)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: 12 lines, all comments; grep found zero references from any
  workflow, and no invocation of the CodeQL Action reads this file.
- Status: deleted in this PR. Files: 1 plus the `.github/AGENTS.md`
  codeql row edited. Bytes: 351. Commit: `8cc91714d`.

### `.qualityrc.json` inert `warn`/`coupling.max` keys (audit finding 17)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: `.claude/skills/code-qualities-assessment/scripts/assess.py:1522`
  reads only `thresholds["coupling"].get("min")`; grep found no `"warn"`
  read anywhere in the file. The two `templates/.qualityrc.json` copies
  already carried neither key, so only the root file needed the edit.
- Status: deleted in this PR (config keys, not a file). Files: 0. Keys
  removed: 10 (`warn` on 4 qualities x 2 scopes, plus `coupling.max` x 2
  scopes). Commit: `9e69f91c4`.

### `check_dual_priority_labels.py` (issue #2623, closed; not in the ponytail audit's 19 findings)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: issue #2623, which this validator served, is closed. It
  queries the GitHub API over the network and gates nothing in a diff,
  so `tests/ci/test_validation_scripts_are_reachable.py`'s own
  `_NO_CALLER` allowlist already recorded it as intentionally unwired.
  Removing it required correcting that test's docstring-count assertion
  from "two unreachable" to "one unreachable" (the test enforces this
  count against reality, not merely documents it).
- Status: deleted in this PR. Files: 2 (script plus its test) plus the
  reachability test's allowlist entry and docstring count. Bytes: 12,936.
  Commit: `350930e95`.

### `.agents/checkpoints/.gitkeep` (not in the ponytail audit; identified independently, corroborated by #5420's 2026-09-11 measurement)

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: `.claude/hooks/PreCompact/invoke_compact_checkpoint.py:11`
  states no on-disk checkpoint artifact is written (ADR-082, issue
  #3217), so this directory has never had a writer. #5420's measurement
  above independently classes this same path `DEAD` and names it "the one
  honest DELETE" in that issue's relocation-vs-deletion table.
- Status: deleted in this PR. Files: 1 plus the
  `docs/project-structure.md` list entry removed. Bytes: 0. Commit:
  `cf4af2849`.

### Two exclusions held back this cohort

- Class: `EXPERIMENT` (HOLD)
- Owner: not this cohort
- Consumers: `.claude-mem/scripts/import_claude_mem_memories.py` (globs
  its sibling directory for the backup blob);
  `.agents/governance/MEMORY-MANAGEMENT.md:168` reads
  "`python3 .claude-mem/scripts/import_claude_mem_memories.py`" (documents
  the manual import invocation)
- Evidence, blob: `.claude-mem/memories/direct-backup-2026-01-03-1434-
  ai-agents.json` (audit finding 3) has a real reader by directory glob,
  not by filename, and a still-documented manual import procedure names
  it. Deleting the blob without first retiring that procedure would leave
  the documented command pointing at nothing.
- Evidence, archive: `.agents/projects/v0.3.0/` and `v0.3.1/` (audit
  finding 7) are frozen history under this owner's stated convention of
  archiving rather than deleting completed project state; no reader
  requires them to stay, but no consumer of this ledger's disposition
  contract overrides an explicit owner archival convention either.
- Rationale: both are `EXPERIMENT`/HOLD, not `DELETE`, for the same
  reason different candidates get `EXPERIMENT` elsewhere in this ledger:
  the blocking fact is named and bounded (retire the import procedure
  first; confirm the archival convention with the owner) rather than
  open-ended. Neither was touched in this PR.

## Cohort 3 deletions and dispositions, epic #5456 (this PR)

### `rjmurillo-bot.yml`, disabled bot mention handler

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: `gh api repos/rjmurillo/ai-agents/actions/workflows` shows
  the workflow `disabled_manually` since 2026-05-17 (four months), with
  no re-enable plan recorded in any issue, PR, memory, or retrospective.
  Renovate bumped `anthropics/claude-code-action` in it 12 times across
  11 days with zero effect (PRs #5458 through #5732), since a disabled
  workflow never runs the bumped action.
- Status: deleted in this PR. Files: 1. Bytes: 2,736. Commit: `704e75111`.
- Note: ADR-101 line 267 lists five `pull_request_target` workflows as of
  its decision date; that list is historical, three remain after this
  cohort, and the record is left unedited on purpose.

### `auto-assign-reviewer.yml` and `assign_bot_reviewer.py`, dead trigger source

- Class: `DELETE`
- Owner: this cohort
- Consumers: none
- Evidence: `.github/scripts/assign_bot_reviewer.py`'s own module
  docstring states that routing the review request through the job's
  own `GITHUB_TOKEN` "would silence the bot review it exists to start",
  because `rjmurillo-bot.yml` triggers on `pull_request_target:
  review_requested`. The workflow's only purpose is firing that trigger.
  With `rjmurillo-bot.yml` deleted, the workflow, its script, and the
  script's test are a dead compatibility shell under the epic's gate 8.
- Status: deleted in this PR. Files: 3 (workflow, script, test). Bytes:
  18,975 (2,966 + 7,186 + 8,823, measured via `git cat-file -s` per
  file, this session). Commit: `704e75111`; dangling-reference cleanup
  in `8bf37392c` and `43136599a`.
- Note: `auto-assign-reviewer.yml` was `active` on GitHub at deletion time;
  its only consumer was the disabled handler, so the deletion stops a live
  no-op, not a live behavior.

### `pr-maintenance.yml`

- Class: `KEEP`
- Owner: `rjmurillo`
- Consumers: every contributor PR (automated conflict resolution and
  comment triage)
- Evidence: issue #4607 state `OPEN` (BOT_PAT identity mis-issuance);
  workflow disabled 2026-08-15 after five consecutive hourly runs
  exited 3 from `invoke_pr_comment_processing.py`.
- **Current outcome protected**: automated conflict resolution and
  comment triage across up to 20 PRs per hour, against a measured 294
  PRs opened or updated in the trailing 14 days per ADR-101's PR-volume
  citation.
- **Evidence failure occurs**: PR volume (294 / 14 days) exceeds what
  manual triage absorbs without a backlog; the workflow's own five
  consecutive exit-3 failures on 2026-08-15 are why it is disabled
  rather than deleted.
- **Why simpler insufficient**: manual triage does not scale to the
  measured PR volume; a scheduled or on-demand human pass would still
  need the same conflict-detection and comment-classification logic
  this workflow already carries.
- **Owner and consumers**: as above.
- **Cost**: about 98 KB of scripts and tests idle while the workflow
  stays disabled.
- Rationale: re-enable after #4607 resolves the BOT_PAT identity issue,
  or record the pause as a deliberate decision if #4607 stalls further;
  not a candidate for deletion while its protected outcome (PR triage at
  scale) has no cheaper substitute.

### Always-on rule subtraction: `claude-model-patches.md` nudge sections

- Class: `EXPERIMENT`
- Owner: not assigned
- Consumers: every Claude Code session in this repository (always-loaded
  rule content)
- Evidence: `claude-model-patches.md`'s "Todo-list Discipline", "Think
  Before Heavy Actions", and "Dedicated Tools Over Bash" sections
  (3,740 bytes, about 980 tokens per harness) overlap in intent with the
  gstack skill preamble's equivalent nudges (todo discipline, heavy-action
  preambles, tool preference), a redundancy this cohort's research
  surfaced rather than an epic-named candidate.
- Bar to clear, quoted from
  `.claude/skills/context-optimizer/references/rule-audit-procedure.md`:
  Step 0a requires "Write down the decision rule in plain text" before
  any scored run, for example "I will accept a progressive-disclosure
  recommendation if and only if `description` ties or beats `full` in
  at least 3 of 4 runs, with no run showing `full` beating"; Step 1 runs
  `eval-rule-activation.py` against `--model claude-opus-5` then "Repeat
  with `--model gpt-5.6-sol`. Run both, always. They disagree, and the
  disagreement is the point." The procedure's own calibration precedent
  (line 233) is eight runs total, followed by adversarial review, then
  `model-context-doctrine.md` and `canonical-source-mirror.md` updated
  to reflect the result.
- Blocker: no scenario file exists yet under
  `tests/evals/rule-scenarios/` for this candidate, and the eight runs
  the procedure requires are paid (Copilot CLI credits or API spend);
  neither has been run this session.
- Status: not started. `EXPERIMENT`, pending the scenario file and the
  eight-run bar above.
- Status: moved in PR (this branch): text lives in build, test, plan,
  ship, review; always-on bytes fell by 5,951 at the mirror. Epic
  #5456 M4 PR1 executed the mechanical move (ADR-108 partial into
  build/test/plan/ship; a `resources/` file for review, not
  template-owned) without running the eight-run eval bar above. That
  bar still gates cutting the text outright; it does not gate
  relocating it out of the always-on set into the skills that use it.
  `scripts/validation/instruction_budget.py` measured the `.md`
  always-on mirror at 56,863 bytes before and 50,912 bytes after
  (5 rules to 4).

### Business-strategy skill (optional pack)

- Class: `KEEP`
- Owner: rjmurillo
- Consumers: opt-in installs of the `business` pack
  (`docs/installation.md:143`, `docs/skill-reference.md:160`); users
  outside this repository's history.
- Current outcome protected: customer discovery, positioning, pricing,
  sales, and growth frameworks for the founder-facing install.
- Evidence the outcome is demanded: owner statement on issue #5456,
  2026-09-11: skills and agents are `KEEP` while they exist, because
  development also happens in environments this repository cannot observe
  and local activation counts are blind to them.
- Why a simpler mechanism is insufficient: no other skill carries this
  content; retention will be re-evaluated with telemetry or another
  cross-environment signal, not with local history.
- Cost: 8,625 bytes shipped opt-in; zero always-on cost.
- Status: `KEEP` by owner policy.

### Skill-activation proxy (measurement note, withdrawn as a basis)

- Class: note, not scored
- Owner: this cohort
- Consumers: none
- Evidence: a strict-form regex over session logs, episodes, and merged
  PR bodies on one machine found 2 skills with zero hits and 21 with one
  or two. The owner ruled on 2026-09-11 (issue #5456) that this is not a
  deletion basis: it sees one machine, and development also happens in
  environments this repository cannot observe. Skills and agents are
  `KEEP` while they exist; retention is a later, telemetry-backed
  decision.
- Status: withdrawn. No skill or agent row derives a class from it.

## Release gate status

| # | Gate | Status | Evidence / blocker |
|---|---|---|---|
| 1 | Canonical behavior owners decrease from the pinned baseline | Unchecked | This ledger classifies candidates; it performs no deletion (REQ-022 AC-05 forbids it). The baseline's own `release_targets[0]` names the figure to beat directly: `{"direction": "decrease", "metric": "canonical owner total", "target": "strictly below 412"}`. That total has not been fully re-measured after this PR. One component is: this cohort's two workflow deletions (`rjmurillo-bot.yml`, `auto-assign-reviewer.yml`) drop the canonical `workflows/*.yml` count from 58 to 56 (`.github/AGENTS.md`), which moves the 412 owner total to 410 by that definition alone; no other owner category was recounted. |
| 2 | Always-loaded instruction tokens decrease for every supported harness | Unchecked | No token-reducing change lands in this PR; this PR adds four markdown files plus two memory edits, none of which is always-loaded. |
| 3 | Required local-gate p95 does not regress | Unchecked | No p95 measurement was re-run this session; `gate_budget.seconds_by_hook.pre-push` (3,450.0s) is the baseline figure, not re-measured here. |
| 4 | No new agent/skill/rule/hook/validator/workflow/ADR/registry lands unless it removes or consolidates | Unchecked, named exception | This PR alone (four markdown files plus two memory edits) adds no agent, skill, rule, hook, validator, workflow, ADR, or registry. But its sibling PR #5725 lands `scripts/metrics/control_plane_baseline.py` and `scripts/ci/lefthook_budget_model.py` alongside three spec files and four test files, and removes nothing, so release scope is not clean against this gate. Named exception, argued against the epic's Abort-if clause 3 (forbidding "a new registry, evaluator, ratchet, or governance layer before deleting the mechanism it was meant to simplify"): `control_plane_baseline.py` is measurement-only, exits 0 for any metric value (not a pass/fail evaluator), is wired into no gate this session verified (`grep -rn control_plane_baseline lefthook.yml scripts/validation/pre_pr_sequence.py .github/workflows/*.yml` returns nothing), and the epic's own Baseline section requires exactly this script's output ("Before the first deletion cohort, capture a reproducible baseline from one pinned `main` SHA") before any classification, including this ledger's, could be trusted. It is a precondition for subtraction, not a competing governance layer. |
| 5 | At least one reduced-control configuration compared with baseline on identical downstream tasks | Unchecked | Owned by the epic's #5422-#5426 eval chain (REQ-022 Q5/Out of Scope), not started as of this session (baseline `accepted_tasks.verified: 0`). |
| 6 | Smaller configuration non-inferior on deterministic acceptance and residual defects | Unchecked | Same blocker as gate 5: no reduced configuration exists yet to compare. |
| 7 | Human correction time, total model cost, wall time reported per accepted task | Unchecked | Same blocker as gate 5; `accepted_tasks.total: 22, verified: 0` in the baseline. |
| 8 | Deleted mechanisms include exclusive scripts, tests, projections, docs, baselines, allowlists; no dead compatibility shell | Evidenced this PR | ADR-100 items 1-4 (already delivered) meet this per their own PRs' acceptance criteria (PR #5234, PR #5723 both assert no dead references remain). This PR's own Cohort 2 deletions section adds eleven candidates, each with its allowlist entry, doc row, or test assertion removed alongside the mechanism (`.baseline` root-hygiene entry, `.diffray` allowlist plus three doc/config references, four docs for the TypeScript island, `.github/AGENTS.md`'s droid bullet and codeql row, the reachability test's `_NO_CALLER` entry and docstring count, `docs/project-structure.md`'s checkpoints entry): no dead compatibility shell was left for any of the ten file deletions, with one documented exception: a `.diffray/**` ignore line stays in the two vendor-pinned markdownlint configs until the next `validate_vendor_provenance.py` bootstrap PR re-pins them (see the `.diffray` row). #5420/#5421 stays `EXPERIMENT` (relocation, now measured, see that row) and #5436 stays `DELETE` with zero files removed here (no repository mechanism ever existed to leave a shell behind). |
| 9 | Every retained candidate has a recorded KEEP justification | Checked | Six `KEEP` rows remain after this revision (#5404, duplicate pre-push ratchet, five always-on rules, rule mirror trees, `pr-maintenance.yml`, `business-strategy` by owner policy); each carries the five epic-required fields (REQ-022 AC-02). Tally by class after this revision: `KEEP` 6; `DELETE` 17 (`#5436`; ADR-100 items 1, 2-4, 5; the eleven Cohort 2 rows above; `rjmurillo-bot.yml` and `auto-assign-reviewer.yml`/`assign_bot_reviewer.py` in Cohort 3 above); `EXPERIMENT` 8 (`#5394`, `#5395`, `#5396`, `#5420`/`#5421`, ADR-100 item 6, `control_plane_baseline.py`, the two held-back exclusions row, the `claude-model-patches.md` rule-subtraction row, the `business-strategy` skill row). `control_plane_baseline.py`, the exclusions row, and the skill-activation-proxy note do not need the five-field KEEP block since none is classed `KEEP`. |
| 10 | Final release report distinguishes deletion from relocation, generation, and archival | Partially evidenced | No final release report has been written; this ledger is an input to that report, not the report itself. This revision separates the three by row: `DELETE` rows in Cohort 2 above are subtraction (files gone, byte counts given); the #5420/#5421 row is now measured as relocation (about 5.9 MB moved, 12.7 MB retained as protected history, 1 file/0 bytes actually deleted); the two-exclusions row is explicit archival/retention (owner convention, documented import procedure), not deletion. |

Gates 5, 6, and 7 cannot be met until the epic's #5422-#5426 eval chain
runs; that chain has not started as of this session (`accepted_tasks.
verified: 0` in the pinned baseline).
