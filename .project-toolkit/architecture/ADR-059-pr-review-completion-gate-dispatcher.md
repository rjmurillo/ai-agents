---
id: ADR-059
status: accepted
date: 2026-11-01
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-059: /pr-review Completion Gate Dispatcher and pass_when DSL

## Date

2026-05-08, amended 2026-11-01

## Context

PR #1887 introduced a /pr-review completion gate as a narrative checklist:
the agent reviewed the PR, then claimed verdicts like "0 unresolved threads"
inline. The retrospective at
`.project-toolkit/retrospective/2026-05-05-pr-1887-iteration-paradox.md` records four
times the gate was satisfied while review threads were unresolved. The
failure mode is named "Reporting-Without-Acting Anti-Pattern" (Layer 6 in
the retrospective): an audit output that asserts state instead of measuring
it produces the same wrong answer on retry.

## Decision

1. Replace the narrative completion gate with a dispatcher.
   `.claude/skills/github/scripts/pr/run_completion_gate.py` reads
   `pr-review-config.yaml`, runs each criterion's command, parses its
   stdout as JSON, evaluates `pass_when`, and prints a per-criterion table.
   Exit 0 if all pass, 1 if any fail, 2 on usage.

2. Define a small `pass_when` DSL: dotted-path resolution, literals
   (integers, `true`, `false`, `null`, double-quoted strings), `==`/`!=`
   comparisons, `AND`/`OR` composition (left-to-right, no parentheses).
   AND/OR evaluate left-to-right with equal precedence; atoms are pure
   lookups with no side effects, so the evaluation order does not affect
   correctness.

3. Provide `pass_when_python` as an escape hatch. Evaluated with `eval`
   against an empty `__builtins__` dict. NOT a sandbox (Python class
   hierarchy remains reachable). Acceptable because the config file is
   repo-controlled and `--config` is locked to the repo root.

4. Fail closed by default. `fail_open` defaults to false.

5. Lock `--config` to the repo root via `validate_safe_path` (CWE-22).

6. Make `fetched_pages_complete` a Published Language across verifiers.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep narrative gate | No new code | Same failure mode | Root cause unaddressed |
| Policy engine (OPA) | Mature | Heavy dependency | Overkill for 3 criteria |
| Python-only (no DSL) | One mechanism | Every criterion is eval | DSL keeps common case safe |
| DSL-only (no eval) | No eval surface | Limits future logic | Escape hatch is rare |

## Consequences

### Positive

- Verdicts are functions of verifier output, not agent narration
- Pagination cliffs surface via `fetched_pages_complete`
- New criteria are config-only changes

### Negative

- DSL is not parens-aware
- `pass_when_python` is an eval surface
- Adding operators requires parser changes
- **PR-branch trust boundary**: when `/pr-review` runs after
  `gh pr checkout`, the config it reads is the PR branch's copy. A
  malicious PR can change `completion_criteria.command` or
  `pass_when_python` and the dispatcher will execute it. This is the
  same trust a reviewer extends by running tests/linters on a PR
  branch, but more direct. Mitigations documented in the dispatcher
  docstring and the `/pr-review` workflow; structural hardening
  (loading config from `main` or refusing to run on divergence) is
  deferred as follow-up. Surfaced by CodeRabbit review on PR #1898.

## References

- `.project-toolkit/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- `.claude/skills/github/scripts/pr/run_completion_gate.py`
- PR #1898

## Amendment 2026-11-01: Step 0 verify-only trust rules

PR #7014 widens what the `--verify-config-only` path accepts. The owner
made three decisions on issue #6506 on 2026-11-01: D3, D5, and D6. Issue
comments 6563759761 and 6564151380 record them. Later that day the owner
made D10, which narrows D6, and D11, which orders the text fixes in this
revision. D10 and D11 were made in the PR #7014 working session; no issue
comment records them. This amendment records all five where the gate's
design lives. The Decision items 1 to 6 above are unchanged.

Line numbers below hold at commit `8d8c3b01d` (2026-11-02) on branch
`fix/6506-batch7-merge-pr-automation-2`, and at any later commit that leaves
the cited file unchanged, unless a bullet names another commit. The gate
source is `src/claude/skills/github/scripts/pr/run_completion_gate.py`, served
at `.claude/skills/github/scripts/pr/run_completion_gate.py` (ADR-119). It is
cited below as `gate.py`. Function names are the durable key: this repository
squash-merges, so the commit may not stay reachable. Resolve a cite by its function name on `main` when it is gone.

### Context

Step 0 of `/pr-review` runs the gate with `--verify-config-only` before any
`scripts` command (issue #5520). That path compares the config and every
work-tree file the `scripts` commands name with the trusted ref. It runs
nothing. Some tokens reach their file only through shell or PowerShell
evaluation, so no file comparison covers them. The gate lists those as
`unverifiable_command_tokens`.

Two gaps followed. First, every unverifiable token stopped every harness,
even a token from a map the running harness never dispatches. Second, every
Copilot `scripts` entry is a PowerShell launcher (issue #5521). Its script
path sits inside a quoted payload, so every Copilot run stopped.

### Rules

**R1 (D3): the Step 0 stop is scoped to the running harness.**

- The trust check still covers the union of all `scripts` maps.
  `_scripts_map_criteria` (`gate.py:4424-4445`) feeds every map to
  `_enforce_command_trust`. A diverged tracked script in any map exits 2,
  whatever harness runs.
- `_unverifiable_by_harness` (`gate.py:4533-4578`) pairs each unverifiable
  token with the map that names it. A token in two maps appears once per
  map.
- `_blocking_tokens` (`gate.py:4581-4598`) keeps only the tokens of the
  harness named by `--harness`. They go in
  `blocking_unverifiable_command_tokens` (`gate.py:4625-4639`). Tokens from
  other maps stay in `unverifiable_command_tokens` and do not stop the run.
- With no `--harness`, every unverifiable token blocks (`gate.py:4594-4595`).
  This is the fail closed reading for Codex, Cursor, and Hermes, which
  have no map. They are not known to set either plugin-root variable; no
  source for that is cited here. Unset, every launcher target falls back
  to `.claude/skills/...` in the work tree. No-harness then passes only
  when those files are tracked, reached through real directories or
  ADR-119 pinned links, and match the trusted ref. In this repository that
  holds: `.claude/skills/github` is a pinned link into `src/claude`. A
  consumer repository with no tracked `.claude/skills` copy fails it: the
  target is missing, so every Copilot payload blocks. Two other routes
  pass there: a config with no Copilot map, or a plugin-root variable that
  names a true install, which makes the target external and verified
  (`gate.py:1624-1629`, `1845-1852`, `4495-4496`). The shipped Codex,
  Cursor, and Hermes configs all carry a Copilot map at line 30, so the
  first route never holds as shipped (`src/codex/skills/pr-review/pr-review-config.yaml:30`).
- An `--harness` value with no `scripts` map exits 2 before any verdict
  prints (`gate.py:4758-4768`).
- `--harness` without `--verify-config-only` exits 2 (`gate.py:4694-4698`).
  A caller cannot believe it narrowed a full gate run.
- The stop is in the skill text. Step 0 proceeds only on exit 0 with an
  empty `blocking_unverifiable_command_tokens` list
  (`templates/skills/pr-review.SKILL.md.tmpl:152-154`). The config table
  `verify_config_only_exits` summarizes it; the template governs
  (`src/claude/skills/pr-review/pr-review-config.yaml:116-122`).
- So R1 has two strengths. Exit 2 is enforced by the gate. A blocking
  token is not: the gate still exits 0 (`gate.py:4778-4787`) and lists the
  token for the agent to stop on. The ADR-101 plane table rates files
  under version control as advisory (`ADR-101-enforcement-planes.md:128`),
  and rule 1 bars such a stop from being the only gate (`:142`). This stop
  lives in tree text the actor reads, so it is advisory.
- Tests: `TestVerifyConfigOnlyHarnessScope`, including
  `test_other_harness_token_is_reported_but_does_not_block`,
  `test_unnamed_harness_fails_closed_on_every_token`, and
  `test_unknown_harness_exits_2`
  (`tests/skills/github/test_run_completion_gate.py:2080-2290`).

**R2 (D5): a canonical Copilot launcher counts as the plain token for its
script.**

- `_launcher_script` (`gate.py:1706-1732`) reads the script path from the
  payload. It accepts only a path that matches `skills/<path>.py` with no
  `..` segment.
- It re-renders the launcher for that path (`gate.py:1680-1703`). The
  command must equal the rendering byte for byte. One added statement, a
  changed root chain, or a changed prefix returns `None`.
- Words after the launcher must match `_LAUNCHER_TAIL_RE`
  (`gate.py:1677`): letters, digits, `_ . - { } =`, and spaces. A quote,
  `$`, shell operator, or newline there returns `None`. As stored in the
  config, before placeholder substitution, the tail cannot run code or
  reach another script. This is not a dispatch-time guarantee: the agent
  fills `{body}`, `{thread_id}`, and `{head_sha}` at dispatch, and `{body}`
  is comment text an outside author writes. Quoting it is the agent's job
  in every map, not only Copilot's (CWE-78). It can still change argv: the
  class admits `{`, `}`, and `.`, so a bash brace expansion such as
  `{1..9}` expands.
- The tail rule and `_LAUNCHER_PREFIX_ARGV` exist only in the gate, which
  is stricter than the renderer on purpose. The port test reaches the tail
  rule only indirectly: every shipped entry must still be recognized.
- A recognized launcher adds the plain token
  `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/<path>`
  (`gate.py:1735-1744`) to the argv the trust check classifies
  (`gate.py:1910-1915`). The script is then compared like a plain token,
  with the differences R3 names.
- The payload token is dropped from the unverifiable list only when the
  launched script verified and the argv starts with the exact prefix words
  (`gate.py:4560-4571`). Otherwise the payload blocks.
- The renderer in the gate is a port of `build/scripts/copilot_launcher.py`,
  because `build/` does not ship with the skill. `TestGatePortMatchesTheRenderer`
  (`tests/build_scripts/test_copilot_launcher.py:210-242`) pins the port's
  constants and patterns to that module. It also checks that every shipped
  `scripts.copilot` entry renders the same in both.
- Tests: `TestCopilotLauncherVerification`, including
  `test_tampered_launcher_stays_blocking`
  (`tests/skills/github/test_run_completion_gate.py:2291-2666`).

**R3 (D6, narrowed by D10): where the launched script lives decides how it
is verified.**

- `_launcher_target_verified` (`gate.py:4479-4499`) classifies the plain
  token with `_classify_argv_token`, the same rule a plain token gets.
- Inside the work tree, the script must be in `checked_files` and not in
  `untrusted_files` (`gate.py:4497-4498`). So it must be tracked and match
  the trusted ref. A diverged tracked script exits 2 through R1's union
  check before any payload is classified (`gate.py:4756-4757`). So does a
  script reached through a symlink the trusted ref does not pin:
  `_classify_argv_token` returns escapes (`gate.py:1822-1823`), escaping
  paths join `untrusted` (`gate.py:3602`), and the check halts. These two
  exits hold unless a human passes `--approve-untrusted-config`. An
  untracked script outside a nested repository, or a missing script,
  leaves the payload blocking at exit 0 under the right or no `--harness`.
  An untracked script inside a nested repository joins `untrusted` and
  exits 2 (`gate.py:3321-3327`). A PR can produce a missing target by
  deleting the tracked script. A non-file path, such as a directory,
  classifies as skip like a missing one (`gate.py:1854-1855`). Under a
  wrong `--harness`, all three exit-0 cases drop out of the blocking list
  (Residual risk).
- A link the trusted ref pins (ADR-119) is followed, and its target is
  byte-compared (`gate.py:1552-1587`). `main` binds the pinned-link
  source, loaded on first use, before any path is classified (`gate.py:4702-4704`). In-tree
  R3 depends on it here: every `.claude/skills/github/...` launcher target
  crosses such a link. Without the manifest the target classifies as
  escapes; with it, as the `src/claude/...` file.
- Untracked files are stricter than the plain-token rule. A plain token
  naming an untracked file outside a nested repository is recorded in
  `skipped_untracked_files` and does not block (`gate.py:3321-3327`). A
  launcher naming the same file stays blocking
  (`test_untracked_script_stays_blocking`). The launcher's file is reached
  through a payload the gate cannot read as argv, so the gate wants a
  compared file before it drops the payload. Do not loosen this to match
  plain tokens without a new decision.
- Human approval is stricter for launchers too. With
  `--approve-untrusted-config`, `_enforce_command_trust` returns no halt
  for a diverged script (`gate.py:3672-3678`), so a plain token for it
  proceeds. The file stays in `untrusted_files`, so the launcher stays
  blocking. Approval cannot unblock a Copilot payload. This fails closed.
  `TestApprovalNeverUnblocksALauncher` pins it for in-tree and
  same-repository targets.
- Outside the work tree, D10 splits the external files in two
  (`_partition_external_files`, `gate.py:3468-3510`). A file with no
  `.git` entry above it is a true install (`_inside_git_work_tree`,
  `gate.py:3158-3173`). So is a file in a work tree of another repository.
  Either is recorded in `skipped_external_files` uncompared, and a
  launcher on it counts as verified (`gate.py:4495-4496`). This is the
  #5112 plain-token rule: a PR cannot rewrite that file through this work
  tree.
- A file in another work tree of this repository is verified like an
  in-tree file (`_verify_same_repository_files`, `gate.py:3359-3393`). Same
  repository means the same `git rev-parse --git-common-dir`, which every
  linked worktree of a clone shares, or the same normalized origin URL, as
  for a separate clone (`_same_repository_root`, `gate.py:3176-3208`).
  URLs compare as lowercase `host/path`, so HTTPS, scp, and ssh spellings
  match (`_normalized_remote`, `gate.py:3111-3129`). Two work trees that
  both lack an origin do not match by URL. The file must be tracked there
  and match the trusted ref read from this work tree's git. A diverged
  file joins `untrusted`, so Step 0 exits 2 unless a human passes
  `--approve-untrusted-config`. One rule is stricter than in-tree: a named
  file git does not track there blocks too (`gate.py:3322-3326`). A
  launcher on such a file counts as verified only when the file is
  compared and not flagged. Every enclosing `.git` is asked, innermost
  first (`_same_repository_root`), so a file in a nested repository under
  such a tree is untracked there and blocks, as in-tree. The command's
  spelling, as written, blocks if it holds `..` anywhere. Otherwise it is
  scanned for links under that tree (`_unpinned_link_in`): an unpinned link
  is untrusted, as in-tree; a pinned one is followed and its target compared. A spelling
  that enters such a tree only through a host link, such as an aliased
  plugin root, is found by resolving its ancestors
  (`_aliased_same_repository_root`) and blocks: no ref pins the alias. Any git
  failure while deciding or comparing halts with exit 3
  (`gate.py:3571`, `3634-3649`). Plain tokens and launchers share this
  rule: both reach `_verify_command_trust` as one external-file list.
- The launcher string itself is bounded by config trust: compared with
  the trusted ref, install-trusted with no comparison (#5112,
  `gate.py:874-895`), or human-approved. D10 covers a sibling root's
  config. Here conditions 3a and 3b of `_install_trusted_root` deny it
  install trust: every work tree holds `scripts/utils/path_validation.py`,
  so a sibling-served gate takes that tree as `_PROJECT_ROOT` and
  byte-compares the config. `_in_same_repository_tree` guards a tree with
  no such marker, such as a consumer plugin vendored in a sibling work
  tree: containment refuses the config (exit 2; a git failure exits 3).
- Step 0 cannot verify the gate it runs. Its resolvers try plugin-root
  variables before `$repo_root/.claude`
  (`templates/skills/pr-review.SKILL.md.tmpl:107-140`), so a root naming a
  sibling serves the gate and the skill text from that tree. On
  2026-11-02, from the main clone with `CLAUDE_PLUGIN_ROOT=<this work
  tree>/.claude` and the Step 0 command, this branch's gate compared its
  own config with `origin/main` and exited 2 (diverged). A matching config
  exits 3 instead: the cwd is outside the gate's work tree
  (`gate.py:3546-3555`). A PR-modified gate there is checked by
  nothing, like an in-tree gate on a checked-out PR branch. A host that
  names a PR-writable plugin root hands it the plugin, past any check.
- R3's true-install branch is a scoped exception to ADR-101 rule 4
  (`ADR-101-enforcement-planes.md:145`): a gate must checksum everything
  it dispatches. A true install sits outside the plane the PR author
  writes, and install trust is the #5112 rule. D10 takes sibling checkouts
  of this repository out of the exception, for scripts and the config.
  The path back to rule 4 is the R3 revisit trigger: signed or hashed
  plugin installs.
- Owner record. D6 (comment 6564151380) assumed "A PR cannot rewrite it".
  A sibling-checkout plugin root broke that. Asked by log 2 to reaffirm D6,
  the owner made D10 on 2026-11-01: D6 holds for true installs only.
- If the work tree cannot be located, `_launcher_verifier`
  (`gate.py:4502-4521`) returns `None`; every payload stays unverifiable.
- Tests: `test_missing_script_stays_blocking`,
  `test_untracked_script_stays_blocking`,
  `test_installed_plugin_launcher_passes`,
  `test_installed_plugin_launcher_with_tampered_payload_blocks`,
  `test_installed_plugin_without_the_script_blocks`, and
  `test_launcher_verifier_returns_none_and_names_the_cause`
  (`tests/skills/github/test_run_completion_gate.py:2438-2649`). D10 adds
  `test_run_completion_gate_same_repository.py` (linked worktree, sibling
  clone, kept install trust) and
  `test_run_completion_gate_same_repository_contracts.py` (probe failures,
  approval, wrong-harness drop), `..._same_repository_links.py` (links,
  `..` spellings, nested repository, config in both layouts), and
  `..._same_repository_failures.py` (git and resolve failures), all under `tests/skills/github/`.

**Step 0 text (D11).** Exit 0 says tracked scripts match; an untracked
in-tree script is skipped and an installed plugin install-trusted, not
compared. Exit 3 names the cwd check and git failure (`templates/skills/pr-review.SKILL.md.tmpl:152`),
and the config table carries both. `0d89522f8` (2026-11-02) did IT4; log 3 the rest.

### Alternatives considered

The owner chose each rule. These are the options each one beat.

| Rule | Rejected option | Why not chosen |
|------|-----------------|----------------|
| R1 | Exit nonzero when the blocking list is non-empty | Deferred, not refuted. On the shipped config it changes no outcome today: the blocking list is empty for every harness when targets verify. Its cost is a new exit code in a space callers already branch on, and a hard stop for consumer configs that run today with unverifiable tokens. It would make the advisory stop gate-enforced. See the R1 revisit trigger. |
| R1 | Derive the harness from evidence the gate reads, such as which plugin-root variable is set | Both variables can be set at once, and Codex, Cursor, and Hermes are not known to set either. The guess could name the wrong map. |
| R1 | Refuse a contradiction without guessing, such as exit 2 for `--harness claude_code` when only `COPILOT_PLUGIN_ROOT` is set | Not weighed when the owner chose D3. It never picks a map, and it would narrow the wrong-harness fail-open. Kept as a revisit option for R1. |
| R2 | Ship `build/scripts/copilot_launcher.py` with the skill | `build/` is a build-time tree, not a served path (ADR-119). Shipping it would add a served module for one recipe. A pinned port with a test was cheaper. |
| R2 | Leave Copilot launchers unverifiable | Every Copilot run stops at Step 0, which was the defect. |
| R3 | Byte-compare installed-plugin scripts against a manifest or hash | No signed or hashed plugin install exists to compare against. #5112 already accepts install trust for plain tokens. |
| R3 | Keep install trust for every external root (D6 as first recorded) | Replaced by D10. This repository works in sibling worktrees and a main clone, so a plugin root naming one is realistic, and a PR branch there ran uncompared. |
| R3 | Recognize this repository by common dir alone, or by origin alone | Common dir misses a separate clone. Origin misses a linked worktree whose clone has no origin. D10 accepts either signal. |

### Consequences

Positive:

- Copilot runs with `--harness copilot` no longer stop on every launcher.
  Measured at `b1baf4432` (2026-11-01) on Linux, plugin-root variables
  unset: 0 blocking tokens for every harness (log 2 has the run). Not
  rerun since; D10 does not touch in-tree files. A Windows checkout with
  `core.symlinks=false` blocks every Copilot payload (inferred, not run).
- A token from another harness's map no longer stops the running harness.
  With the shipped config this changes nothing today, since the
  `claude_code` map has no unverifiable token. R1 is preventive, for
  consumer configs and for a Copilot payload whose target fails to verify.
- A gate here or in a true install no longer runs a PR branch's sibling
  scripts uncompared (D10); condition 3a already denied a sibling config
  install trust. A gate served from that sibling is outside this (R3).
- Gate-enforced, by exit 2: an unknown harness, `--harness` without
  `--verify-config-only`, a diverged or untracked named script, or an
  unpinned link, in a same-repository work tree (approval downgrades any
  of these to exit 0 for a plain token), and a config there that diverges
  or fails containment. By exit 3: a git failure while probing one.
- Agent-enforced, by a non-empty blocking list at exit 0: no harness, an
  unrecognized launcher, a missing verifier, and a git failure in
  `_launcher_verifier`. These stop only if the agent reads the list (R1).
- One branch fails open: a wrong but valid `--harness` (Residual risk).

Negative:

- The gate carries a second copy of the launcher recipe. A test keeps the
  two equal, and it reads two private names in `copilot_launcher.py`
  (`_PAYLOAD_RE`, `_SCRIPT_REL_RE`). Renaming them breaks the test with no
  real drift.
- Launcher recognition runs in two places, `_collect_command_paths` and
  `_unverifiable_by_harness`. Both call `_launcher_script_token`, but they
  must stay in step.
- `_launcher_verifier` runs `git rev-parse --show-toplevel` a second time,
  from `_PROJECT_ROOT` as the first (`gate.py:3528`, `4511`). If they
  disagreed, the payload stays blocking (read from code; no test).
- Only the Copilot skill copy gets `--harness` filled in at build time.
  The other copies rely on the agent to substitute `{harness}` or drop the
  line. Both mistakes fail closed: a literal `{harness}` exits 2, and a
  dropped line blocks every token.
- With the shipped config, Codex, Cursor, and Hermes stop at Step 0 in a
  consumer install with no tracked `.claude/skills` copy and no plugin-root
  variable naming a true install. Their configs carry a Copilot map, and
  its launcher targets are missing there. This PR did not cause it:
  before it, every unverifiable token blocked every harness.
- The Copilot consumer benefit of R2 depends on `COPILOT_PLUGIN_ROOT` or
  `CLAUDE_PLUGIN_ROOT` reaching the agent's shell. The
  `agent-harness-reference` skill documents them for plugin hooks only.
  Without them a consumer with no tracked `.claude/skills` copy still
  blocks every Copilot payload.
- D10 adds a `rev-parse` and an origin lookup per enclosing `.git`, then
  a tracked probe and byte compare for this repository. A true install
  below a `.git` git refuses (`safe.directory`) now exits 3. An install
  keeping a `.git` with this origin exits 2 when it lags the trusted ref:
  on this host on 2026-11-02, `~/.claude/plugins/marketplaces/ai-agents`
  is one; the project-toolkit cache entries have no `.git`.

### Residual risk

- An installed plugin's script is trusted with no byte comparison. If the
  installed copy is stale or was changed on the host, the gate cannot see
  it. This is the same trust #5112 gives a plain token.
- The external location comes from `COPILOT_PLUGIN_ROOT` or
  `CLAUDE_PLUGIN_ROOT` in the host environment. Any existing file outside
  the work tree at that path, and outside every work tree of this
  repository, is accepted. Whoever sets those variables is trusted to name
  the real install.
- The verdict holds only for the environment and files present at Step 0.
  The gate expands the plugin-root variables in its own process
  (`gate.py:1614-1630`). PowerShell reads `$env:COPILOT_PLUGIN_ROOT` again
  at dispatch, and the `.claude` fallback resolves from the dispatch
  working directory. If either changes between Step 0 and dispatch, an
  unchecked file runs (CWE-367). Plain tokens under #5112 share this
  window.
- D10 recognizes this repository only by a shared common dir or a matching
  origin URL. A checkout that matches neither keeps install trust: a clone
  of a fork whose origin is the fork, a clone whose remote has another
  name or a port or local-path URL, or a copy with no `.git`. A PR branch
  checked out there runs uncompared on the reviewer's host (CWE-829), and
  so does its config, whose commands can run inline code that names no
  file. Over-matching costs availability (exit 2 or 3), not safety.
- R1 scopes only the stop. The running harness is named by the agent, not
  proven. A wrong but valid `--harness` fails open: `_blocking_tokens`
  drops every token owned by the map that actually runs, and Step 0
  proceeds. The bound has two parts. First, the union check still runs on
  every map and appends each launcher's target (`gate.py:1910-1915`), so a
  PR-modified tracked target still exits 2 (`gate.py:4756-4757`), in this
  work tree or a same-repository one. The fail-open reaches targets that
  check left uncompared: untracked files outside a nested repository,
  which checkout does not produce, and missing or non-file paths, which a
  PR can produce. True-install files count as verified, uncompared,
  under every harness (`gate.py:4495-4496`), so no exposure is added. A
  deleted target finds no file at dispatch unless one appears in the
  CWE-367 window above. A directory of the same name holding
  `__main__.py` is worse: the gate skips it (`gate.py:1854-1855`) and
  Python runs it, so PR code reaches dispatch uncompared.
  `TestWrongHarnessDropsTheMissingTarget` pins both blocking under
  `copilot` and dropping under `claude_code`; no test pins Python running
  the directory. Under the right `--harness` a launcher payload blocks. A
  plain token naming such a directory runs uncompared under every
  harness; that predates this amendment and is flagged for the PR #7014
  body. Second, the command strings are bounded by config
  trust: compared with the trusted ref, install-trusted, or
  human-approved. The Copilot copy gets `--harness copilot` at build time
  (`build/scripts/copilot_body_translation.py:395`). Other copies rely on
  the agent to fill `{harness}`
  (`templates/skills/pr-review.SKILL.md.tmpl:146`, guidance at `:150`).
  The `claude_code` map has no unverifiable token, so the launcher exposure
  today is the Copilot map under a wrong `--harness claude_code`.
- An agent that ignores a non-empty blocking list proceeds on exit 0, and
  the gate cannot detect it. A prompt-injected agent (ASI01) is the actor.

### Reversibility and revisit

- Reverting is code only. Drop `--harness` scoping in `_blocking_tokens`
  and launcher recognition in `_launcher_script_token`, and every Copilot
  run blocks again. Drop the `_partition_external_files` call in
  `_verify_command_trust`, and every external file is install-trusted
  again, as D6 first read. Drop the `_in_same_repository_tree` check in
  `_install_trusted_root`, and only a config in a tree with no
  `scripts/utils` marker regains it; conditions 3a and 3b stay. No data
  or external state is orphaned.
- Revisit R1 the first time an agent is seen proceeding on a non-empty
  blocking list. Then take the deferred option: a distinct nonzero exit
  for a non-empty list. No telemetry records that event; a transcript
  review, or an eval that feeds a non-empty list, must find it. The contradiction check in
  Alternatives is a second option at that revisit.
- Revisit R2 if `build/` ships with the skill: delete the port and import
  the renderer.
- Revisit R3 on the first report of a stale or host-modified installed
  plugin script, or when plugin installs gain a signature or hash to check.
  Revisit D10 on the first checkout of this repository it fails to
  recognize, such as a fork clone used as a plugin root.

### References

- Issue #6506, comment 6563759761 (D3 and D5) and comment 6564151380 (D6)
- Issues #5112 (install trust), #5520 (`--verify-config-only`), #5521
  (Copilot launcher); PR #7014; ADR-101 (rule 4); ADR-119 (pinned links)
- `.project-toolkit/critique/ADR-059-debate-log-2.md` (and its part 2)
- `.project-toolkit/critique/ADR-059-debate-log-3.md` (and its part 2)
