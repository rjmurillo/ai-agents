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
made three decisions on issue #6506 on 2026-11-01: D3, D5, and D6. The
review of PR #7014 found them recorded only in issue comments 6563759761
and 6564151380. This amendment records them where the gate's design lives.
The Decision items 1 to 6 above are unchanged.

Line numbers below are for branch `fix/6506-batch7-merge-pr-automation-2`
at commit `b1baf4432` (2026-11-01). The gate source is
`src/claude/skills/github/scripts/pr/run_completion_gate.py`, served at
`.claude/skills/github/scripts/pr/run_completion_gate.py` (ADR-119). It is
cited below as `gate.py`. Function names are the durable key. Line
numbers are a convenience: this repository squash-merges, so the branch
commit may not stay reachable. Resolve a cite by its function name on
`main` when the commit is gone.

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
  `_scripts_map_criteria` (`gate.py:3925-3946`) feeds every map to
  `_enforce_command_trust`. A diverged tracked script in any map exits 2,
  whatever harness runs.
- `_unverifiable_by_harness` (`gate.py:4016-4061`) pairs each unverifiable
  token with the map that names it. A token in two maps appears once per
  map.
- `_blocking_tokens` (`gate.py:4064-4081`) keeps only the tokens of the
  harness named by `--harness`. They go in
  `blocking_unverifiable_command_tokens` (`gate.py:4108-4122`). Tokens from
  other maps stay in `unverifiable_command_tokens` and do not stop the run.
- With no `--harness`, every unverifiable token blocks (`gate.py:4077-4078`).
  This is the fail closed reading for Codex, Cursor, and Hermes, which
  have no map. They are not known to set either plugin-root variable; no
  source for that is cited here. Without one, every launcher target falls back to `.claude/skills/...` in the work tree. No-harness
  passes only when those fallback files are tracked, reached through real
  directories or ADR-119 pinned links, and match the trusted ref. In this
  repository that holds: `.claude/skills/github` is a pinned link into
  `src/claude`. A consumer repository with no tracked `.claude/skills`
  copy fails it: the target is missing, so every Copilot payload blocks.
  Codex, Cursor, and Hermes are supported there only with no Copilot map,
  or with that copy committed. Their shipped configs carry a Copilot map
  (`src/codex/skills/pr-review/pr-review-config.yaml:30`, same line in the
  `src/cursor` and `src/hermes` copies). So the first condition never
  holds as shipped (Consequences, Negative).
- An `--harness` value with no `scripts` map exits 2 before any verdict
  prints (`gate.py:4241-4251`).
- `--harness` without `--verify-config-only` exits 2 (`gate.py:4177-4181`).
  A caller cannot believe it narrowed a full gate run.
- The stop is in the skill text. Step 0 proceeds only on exit 0 with an
  empty `blocking_unverifiable_command_tokens` list
  (`templates/skills/pr-review.SKILL.md.tmpl:149-153`). The config mirrors
  this in `transport_preflight.verify_config_only_exits`
  (`src/claude/skills/pr-review/pr-review-config.yaml:118-120`).
- So R1 has two strengths. Exit 2 is enforced by the gate. A blocking
  token is not: the gate still exits 0 (`gate.py:4261-4270`) and lists the
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

- `_launcher_script` (`gate.py:1674-1700`) reads the script path from the
  payload. It accepts only a path that matches `skills/<path>.py` with no
  `..` segment.
- It re-renders the launcher for that path (`gate.py:1648-1671`). The
  command must equal the rendering byte for byte. One added statement, a
  changed root chain, or a changed prefix returns `None`.
- Words after the launcher must match `_LAUNCHER_TAIL_RE`
  (`gate.py:1645`): letters, digits, `_ . - { } =`, and spaces. A quote,
  `$`, shell operator, or newline there returns `None`. As stored in the
  config, before placeholder substitution, the tail cannot run code or
  reach another script. This is not a dispatch-time guarantee: the agent
  fills `{body}`, `{thread_id}`, and `{head_sha}` at dispatch, and `{body}`
  is comment text an outside author writes. Quoting it is the agent's job
  in every map, not only Copilot's (CWE-78). It can still change argv: the class
  admits `{`, `}`, and `.`, so a bash brace expansion such as `{1..9}`
  expands.
- The tail rule and `_LAUNCHER_PREFIX_ARGV` exist only in the gate. The
  renderer accepts any `args` string, so the gate is stricter than its
  source on purpose. The port test reaches the tail rule only indirectly:
  every shipped entry must still be recognized.
- A recognized launcher adds the plain token
  `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/<path>`
  (`gate.py:1703-1712`) to the argv the trust check classifies
  (`gate.py:1833-1838`). The script is then compared like a plain token,
  with two differences R3 names: an untracked work-tree script, and a
  diverged script a human approved.
- The payload token is dropped from the unverifiable list only when the
  launched script verified and the argv starts with the exact prefix words
  (`gate.py:4043-4054`). Otherwise the payload blocks.
- The renderer in the gate is a port of `build/scripts/copilot_launcher.py`,
  because `build/` does not ship with the skill. `TestGatePortMatchesTheRenderer`
  (`tests/build_scripts/test_copilot_launcher.py:210-242`) pins the port's
  constants and patterns to that module. It also checks that every shipped
  `scripts.copilot` entry renders the same in both.
- Tests: `TestCopilotLauncherVerification`, including
  `test_tampered_launcher_stays_blocking`
  (`tests/skills/github/test_run_completion_gate.py:2291-2652`).

**R3 (D6): where the launched script lives decides how it is verified.**

- `_launcher_target_verified` (`gate.py:3980-3997`) classifies the plain
  token with `_classify_argv_token`, the same rule a plain token gets.
- Inside the work tree, the script must be in `checked_files` and not in
  `untrusted_files`. So it must be tracked and match the trusted ref.
  A diverged tracked script exits 2 through R1's union check before any
  payload is classified (`gate.py:4239-4240`). So does a script reached
  through a symlink the trusted ref does not pin: `_classify_argv_token`
  returns escapes (`gate.py:1764-1765`), escaping paths join `untrusted`
  (`gate.py:3078`), and the check halts. These two exits hold unless a
  human passes `--approve-untrusted-config`. An untracked script outside
  a nested repository, or a missing script, leaves the payload blocking at
  exit 0. An untracked script inside a nested repository joins `untrusted`
  and exits 2 (`gate.py:3071-3078`). A PR can produce a missing target by
  deleting the tracked script. A non-file path, such as a directory,
  classifies as skip like a missing one (`gate.py:1796-1797`). Under the
  right `--harness` both still block the payload.
- A link the trusted ref pins (ADR-119) is followed, and its target is
  byte-compared (`gate.py:1534-1555`). `main` loads the pinned-link
  manifest before any path is classified (`gate.py:4185-4187`). In-tree
  R3 depends on it here: every `.claude/skills/github/...` launcher target
  crosses such a link. Without the manifest the target classifies as
  escapes; with it, as the `src/claude/...` file.
- Untracked files are stricter than the plain-token rule. A plain token
  naming an untracked file outside a nested repository is recorded in `skipped_untracked_files` and
  does not block (`gate.py:3068-3076`). A launcher naming the same file stays
  blocking (`test_untracked_script_stays_blocking`). The launcher's file
  is reached through a payload the gate cannot read as argv, so the gate
  wants a compared file before it drops the payload. Do not loosen this
  to match plain tokens without a new decision.
- Human approval is stricter for launchers too. With
  `--approve-untrusted-config`, `_enforce_command_trust` returns no halt
  for a diverged script (`gate.py:3211-3217`), so a plain token for it
  proceeds. The file stays in `untrusted_files`, and
  `_launcher_target_verified` requires it not to be there
  (`gate.py:3993-3994`). So approval cannot unblock a Copilot payload.
  This fails closed. It is read from code; no test pins it.
- Outside the work tree, the plugin-root variable names an installed
  plugin. A file there is classified external (`gate.py:1787-1794`) and
  recorded in `skipped_external_files`. The launcher counts as verified
  when its script is in that list. This matches the plain-token rule from
  issue #5112: a PR cannot rewrite that file through this work tree.
  The launcher string itself is bounded by config trust: compared with
  the trusted ref, install-trusted with no comparison (#5112,
  `gate.py:871-892`), or human-approved.
  The rule assumes the plugin root is a real install. If it names another
  checkout of the same repository, a PR branch checked out there is
  accepted uncompared (Residual risk).
- R3's external branch is a scoped exception to ADR-101 rule 4
  (`ADR-101-enforcement-planes.md:145`): a gate must checksum everything it
  dispatches. The installed file sits outside the plane the PR author
  writes, and install trust is the #5112 rule. The path back to rule 4 is
  the R3 revisit trigger: signed or hashed plugin installs.
- D6 as recorded rests on a wider premise than this review found. Comment
  6564151380 says "A PR cannot rewrite it, and the launcher string is
  compared with the config." Both hold only in part. The config may be
  install-trusted or human-approved, so the launcher string is not always
  compared. A plugin root that names a sibling checkout lets a PR branch
  run uncompared. The owner chose Option A in ledger comment 6564031218
  before these cases were named. The owner should reaffirm D6 with them
  in view.
- If the work tree cannot be located, `_launcher_verifier`
  (`gate.py:4000-4013`) returns `None` and every payload stays
  unverifiable.
- Tests: `test_untracked_script_stays_blocking`,
  `test_installed_plugin_launcher_passes`,
  `test_installed_plugin_launcher_with_tampered_payload_blocks`,
  `test_installed_plugin_without_the_script_blocks`, and
  `test_launcher_verifier_returns_none_when_git_fails`
  (`tests/skills/github/test_run_completion_gate.py:2448-2645`).

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

### Consequences

Positive:

- Copilot runs with `--harness copilot` no longer stop on every launcher.
  Measured on the shipped `pr-review-config.yaml` at `b1baf4432`
  (2026-11-01), plugin-root variables unset, with the real
  `_launcher_verifier` and `origin/main` (`8dd4f43d5`, 2026-11-01) as the
  trusted ref. With the pinned-link manifest loaded, as `main` does: the
  command check is trusted, 31 files compared, 0 unverifiable tokens, and
  0 blocking for no harness, `claude_code`, and `copilot`. The run was on
  Linux with symlinks enabled. A Windows checkout with
  `core.symlinks=false` writes the pinned link as a text file, so the
  target is missing and every Copilot payload blocks. That case is
  inferred from `gate.py:3996`, not run. Without the
  manifest: 11 untrusted files, so Step 0 would exit 2. With no verifier:
  11 unverifiable tokens, all in the `copilot` map. This bypassed the
  config check, since the branch's config differs from `origin/main`. No
  measurement covers an installed plugin.
- A token from another harness's map no longer stops the running harness.
  With the shipped config this changes nothing today, since the
  `claude_code` map has no unverifiable token. R1 is preventive, for
  consumer configs and for a Copilot payload whose target fails to verify.
- Gate-enforced, by exit 2: an unknown harness, and `--harness` without
  `--verify-config-only`.
- Agent-enforced, by a non-empty blocking list at exit 0: no harness, an
  unrecognized launcher, a missing verifier, and a git failure. These
  stop only if the agent reads the list (R1).
- One branch fails open: a wrong but valid `--harness` (Residual risk).

Negative:

- The gate carries a second copy of the launcher recipe. A test keeps the
  two equal, and it reads two private names in `copilot_launcher.py`
  (`_PAYLOAD_RE`, `_SCRIPT_REL_RE`). Renaming them breaks the test with no
  real drift.
- Launcher recognition runs in two places, `_collect_command_paths` and
  `_unverifiable_by_harness`. Both call `_launcher_script_token`, but they
  must stay in step.
- `_launcher_verifier` runs `git rev-parse --show-toplevel` a second time.
  Both calls run from `_PROJECT_ROOT` (`gate.py:3022`, `gate.py:4007`).
  If they ever disagreed, the script path would classify under another
  root. It would then sit in neither `checked_files` nor
  `skipped_external_files`, so the payload stays blocking. This outcome
  is read from `_launcher_target_verified`; no test pins it.
- Only the Copilot skill copy gets `--harness` filled in at build time.
  The other copies rely on the agent to substitute `{harness}` or drop the
  line. Both mistakes fail closed: a literal `{harness}` exits 2, and a
  dropped line blocks every token.
- With the shipped config, Codex, Cursor, and Hermes stop at Step 0 in a
  consumer install with no tracked `.claude/skills` copy. Their configs
  carry a Copilot map, and its launcher targets are missing there. This
  PR did not cause it: before it, every unverifiable token blocked every
  harness.

### Residual risk

- An installed plugin's script is trusted with no byte comparison. If the
  installed copy is stale or was changed on the host, the gate cannot see
  it. This is the same trust #5112 gives a plain token.
- The external location comes from `COPILOT_PLUGIN_ROOT` or
  `CLAUDE_PLUGIN_ROOT` in the host environment. Any existing file outside
  the work tree at that path is accepted. Whoever sets those variables is
  trusted to name the real install.
- The external-or-in-tree verdict holds only for the environment and
  files present at Step 0. The gate expands the plugin-root variables in
  its own process (`gate.py:1582-1598`). PowerShell reads
  `$env:COPILOT_PLUGIN_ROOT` again at dispatch, and the `.claude` fallback
  resolves from the dispatch working directory. If either changes between
  Step 0 and dispatch, an unchecked file runs (CWE-367). Plain tokens under
  #5112 share this window.
- A plugin root that names another checkout of the same repository is
  treated as an install. This repository works in sibling worktrees and a
  main clone, so the setup is realistic. A PR branch checked out there runs
  uncompared on the reviewer's host (CWE-829).
- R1 scopes only the stop. The running harness is named by the agent, not
  proven. A wrong but valid `--harness` fails open: `_blocking_tokens`
  drops every token owned by the map that actually runs, and Step 0
  proceeds. The bound has two parts. First, the union check still runs on
  every map and appends each launcher's target (`gate.py:1833-1838`), so a
  PR-modified tracked target still exits 2 (`gate.py:4239-4240`). The
  fail-open reaches targets that check left uncompared: untracked files
  outside a nested repository, which checkout does not produce; external
  install files; and missing or non-file paths, which a PR can produce.
  A PR that deletes a tracked target makes it missing. Dispatch then
  finds no file, unless one is created at that path before dispatch
  (the CWE-367 window above). A PR that replaces a tracked target with a
  directory of the same name holding `__main__.py` is worse: the gate
  classifies it as skip (`gate.py:1796-1797`), and Python runs a
  directory that holds `__main__.py`. So under a wrong `--harness`, PR
  code reaches dispatch uncompared. Under the right `--harness` the
  payload blocks. Second, the command strings are bounded by config trust:
  compared with the trusted ref, install-trusted, or human-approved. The
  Copilot copy gets `--harness copilot` at build time
  (`build/scripts/copilot_body_translation.py:395`). Other copies rely on
  the agent to fill `{harness}`
  (`templates/skills/pr-review.SKILL.md.tmpl:145`, guidance at `:149`).
  With the shipped config, the `claude_code` map has no unverifiable token,
  so the exposure today is the Copilot map under a wrong
  `--harness claude_code`.
- An agent that ignores a non-empty blocking list proceeds on exit 0, and
  the gate cannot detect it. A prompt-injected agent (ASI01) is the actor.

### Reversibility and revisit

- Reverting is code only. Drop `--harness` scoping in `_blocking_tokens`
  and launcher recognition in `_launcher_script_token`, and every Copilot
  run blocks again. No data or external state is orphaned.
- Revisit R1 the first time an agent is seen proceeding on a non-empty
  blocking list. Then take the deferred option: a distinct nonzero exit
  for a non-empty list. Nothing records that event, so this trigger
  depends on a human seeing it. The channels are a retrospective or a
  transcript review that finds a dispatch after a non-empty Step 0 list.
  An eval scenario that feeds a non-empty list and checks that the agent
  stops would make the trigger observable. The contradiction check in
  Alternatives is a second option at that revisit.
- Revisit R2 if `build/` ships with the skill: delete the port and import
  the renderer.
- Revisit R3 on the first report of a stale or host-modified installed
  plugin script, or when plugin installs gain a signature or hash to check.

### References

- Issue #6506, comment 6563759761 (D3 and D5) and comment 6564151380 (D6)
- Issue #5112 (install-trusted plugin files), #5520 (`--verify-config-only`),
  #5521 (Copilot launcher)
- PR #7014
- `.project-toolkit/critique/ADR-059-debate-log-2.md`
