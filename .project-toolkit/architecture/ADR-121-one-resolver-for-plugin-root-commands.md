---
id: ADR-121
status: proposed
date: 2026-11-11
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-02-11
---

# ADR-121: One Resolver Launches Every Shipped Plugin-Root Shell Command

## Context

Issue #7281 reports that a shipped command can run another plugin's files. The
command form is:

```text
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts/<file>.py"
```

POSIX `${VAR:-default}` tests only whether a variable is set. It cannot test for
a file. The context-mode plugin exports its own `CLAUDE_PLUGIN_ROOT` inside its
`ctx_execute` sandbox. The command then resolves into context-mode and exits 2
with "No such file". PR #7318 fixed the same flaw in the completion gate, in
Python, where a probe is possible. The shell form has no such fix.

The form is authored in 489 places at 48b4ea4c2 (2026-11-11).
- 287 sit in `templates/skills` (74 files) at 48b4ea4c2.
- 50 sit in `templates/agents` (33 files) at 48b4ea4c2.
- 2 sit in `templates/rules` at 48b4ea4c2.
- 150 sit in 43 files under `src/claude` at 48b4ea4c2, not counting `SKILL.md` or
  `agents/`. Of those, 123 are Markdown, 19 are YAML, and 8 are `.py` files.

The build copies the form into every other host tree.

### Evidence

Measured on 2026-11-11 with Claude Code 2.1.322. Each row is one sample on the
Haiku model, run with `-p` and `--plugin-dir` from a neutral directory with
`CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` unset. Two review-panel seats ran
extra probes for rows 4, 5, and 7. The author re-ran rows 3 to 7.

| # | Question | Result |
|---|---|---|
| 1 | Does a shell command a skill issues see `*PLUGIN_ROOT`? | No. `env` listed no such variable. |
| 2 | Is bare `${CLAUDE_PLUGIN_ROOT}` rewritten in `SKILL.md` text? | Yes, to the absolute plugin directory. |
| 3 | Is it rewritten inside a fenced code block in `SKILL.md`? | Yes. |
| 4 | Is it rewritten in an agent file body? | Yes. |
| 5 | Is it rewritten in a skill `references/` file? | No. The text stays literal. |
| 6 | Are `${CLAUDE_PLUGIN_ROOT:-.claude}` and the shipped nested form rewritten anywhere? | No. The shell sees them literally. |
| 7 | Is `${CLAUDE_SKILL_DIR}` rewritten? | Yes in `SKILL.md` text. No in agent bodies and `references/`. |

Rules files and YAML were not probed. Copilot CLI 1.0.109 is UNAVAILABLE: the
probe stopped on a monthly quota error. Codex 0.167.0 is NOT RUN. The official
Copilot changelog says plugin hooks receive `PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`,
and `CLAUDE_PLUGIN_ROOT`. It does not say a model-issued shell command receives
them (`official-hook-contracts.md`, "Plugin-root variables"). This ADR claims
nothing about those hosts.

Three facts follow.

1. Under Claude Code the shipped form is never rewritten and the variable is not
   exported, so it resolves to `.claude` under the working directory. The foreign
   export in issue #7281 is one trigger. INFERRED: every consumer outside this
   repo meets the `.claude` resolution too. No end-to-end consumer test exists.
2. The host rewrites the bare token on the 337 template sites for `SKILL.md` and
   agents (287 plus 50). The rendered Claude files hold fewer, 238 by one
   panel count (INFERRED), because the template count also feeds other hosts. The
   rewritten value is an absolute path that no environment can change. The other
   152 sites get no rewrite.
3. On a surface with no rewrite, the shell expands the token from the live
   environment, which is the value a foreign plugin controls.

### Constraints from existing rules

- `generated-artifacts.md` (blast radius section, SHOULD 1) says a launcher
  failure must fail loud, never become a silent exit 0, and that a launcher-shape
  change goes through architect review. This ADR carries its panel debate log.
- The 2026-06-02 PR #2205 incident shipped a launcher nobody ran in its target
  runtime. The broken form shipped for 33 days. Structure tests did not catch it.
- `plugin-self-containment.md` MUST 2 and 4 fix the launcher form. The validator
  `check_plugin_root_interpreter.py` enforces it.
- Hook commands are out of scope. Hosts export the variable to hooks, and
  `hooks.json` handles an unset variable in its own command text.

## Decision

1. **Three classes of site.**
   - **Class S** is a shell command that a model runs: `SKILL.md`, agent bodies,
     rules, `references/`. It gets the locator below.
   - **Class G** is a command the completion gate runs, such as
     `pr-review-config.yaml`, and Python scripts that bootstrap themselves. It is
     out of scope. The gate splits commands with `shlex` and runs no shell, so a
     locator would stay literal and break the rule that the file verified is the
     file executed. Class G resolves in Python: the probe from PR #7318 and the
     bootstrap from issue #3897. The validator's YAML allowance list stays.
   - **Class P** is the Copilot `pwsh` recipe in `build/scripts/copilot_launcher.py`.
     It also takes the first set variable. A follow-up moves it onto the same
     resolver. It is out of scope here.
2. **One resolver file.** `lib/ptk_run.py` ships in every plugin tree that
   receives locator text. It is a real file with byte copies. The multi-tree
   mechanism is `PLUGIN_LIB_FILES` in `lib_hand_files.py`; a parity row pins the
   Copilot hand copy. A tree with no `lib/` keeps the legacy form until it ships
   the resolver. The validator tracks that per tree.
3. **The locator keys on the resolver, not the target.** It tries candidate roots
   in order and runs the first root that holds `lib/ptk_run.py`:

   ```sh
   ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/NAME/scripts/FILE.py ARGS; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
   ```

   Lengths below use `skills/NAME/scripts/FILE.py` and no arguments. The subshell
   keeps `exit 2` from ending a persistent shell. The text holds no
   `|`, so it survives a Markdown table cell. It names both variables, which the
   validator's single-root rule requires. A foreign root lacks the resolver and is
   skipped. Where the host rewrites the bare token (rows 2 to 4) and the resolver
   is present at that path, the first candidate is an absolute path no
   environment can change. Elsewhere, or when the loaded root lacks the resolver,
   the probe is
   the only protection. A foreign root is skipped, and the search reaches
   `.claude`. Amended on 2026-11-14 by decision 11: when the chosen root lacks
   the target, the resolver tries the later candidates.
4. **Candidate order.** The host-rewritten token goes first because it names the
   copy the host loaded. If two copies of this plugin are installed, that copy
   wins. `COPILOT_PLUGIN_ROOT` follows. `.claude` is last.
5. **The first root that passes the probe is final.** The locator never tries a
   later root after one passes. That is how a different plugin's script would run.
   Replaced on 2026-11-14 by decision 11: the resolver itself may fall through
   to a later root that holds both the resolver and the target.
6. **The resolver validates before it runs.** The target must match
   `skills/[A-Za-z0-9_./-]+\.py`, the same pattern `copilot_launcher.py` uses.
   It must hold no `..` part, no absolute path, no backslash, and no NUL. The
   joined path must be a regular file. The check is lexical. It does not resolve
   symlinks, because ADR-119 links `.claude/skills/*` into `src/claude`, and
   whoever controls a root controls everything under it. That pattern admits the
   shipped targets that sit outside `scripts/`, such as `skills/metrics/collect_metrics.py`.
7. **Run semantics.** On POSIX the resolver calls `os.execv`, so the exit code and
   `sys.path[0]` match a direct `python3 <file>`. Off POSIX it calls
   `subprocess.run` and exits with the child's code, because `os.execv` returns
   to the shell at once on Windows. The locator itself is POSIX shell. Markdown
   `bash` blocks are POSIX by existing decision. Amended on 2026-11-14 by
   decision 12, which adds `python3 -I` and `uv run python` forms.
8. **Failure is loud and uses exit 2.** Exit 2 is the config-error code from
   ADR-035. It covers: no root holds the resolver, the target is missing, the
   target fails validation, and the arguments are malformed. A target's own exit 2
   or Python's "can't open file" exit 2 look the same by code. Callers and tests
   tell them apart by the fixed stderr prefix `ptk_run:`. A resolution failure
   never exits 0. A missing `python3` ends in the shell's 127. Target exits 0 to 4
   pass through unchanged.
9. **One recipe owns the launcher text.** A build module
   (`build/scripts/plugin_run_launcher.py`) renders the locator, as
   `copilot_launcher.py` renders its form. Authored sites hold the expanded text,
   because skill templates reject `{{var}}` and `references/` files are byte
   copies. A `--fix` mode rewrites sites. The validator derives the expected shape
   from the recipe, so one recipe change updates every site.
10. **The resolver is not an authentication boundary.** Any root that holds
    `lib/ptk_run.py` passes, including a second install of this plugin. The
    `.claude` candidate runs repo-controlled code, as the legacy form does today.
    A hostile repo that ships `.claude/lib/ptk_run.py` is no worse than one that
    ships `.claude/skills/...`. The gate keeps its own authority:
    `_install_trusted_root` decides what a root may hold, and Class G never sees
    the locator. The resolver and the gate share no state.

## Rollout

Each step is its own pull request. A step starts when the one before it merged.

1. This ADR, with its debate log.
2. The resolver, the recipe, and the tests. No call sites. Tests in the list
   below. The real-CLI smoke covers Claude Code, including a fenced block.
3. The validator learns the locator and gains `--fix`. It extracts the target and
   applies rules 1 and 2 to it, and keeps rule 4 satisfied. Rule 5 stays a
   per-module import-time scan. The validator rejects the locator in
   gate-dispatched YAML (`scripts:` maps), so Class G cannot gain one by accident.
   Both forms pass through a counted allowance. This step edits
   `plugin-self-containment.md` MUST 2 and 4 and the form named in
   `generated-artifacts.md`. It audits every `allowed-tools` pattern of the form
   `Bash(python3 ...)` in skill templates (five templates at 48b4ea4c2 on one
   panel count: `push-pr`, `research`, `pr-review`, `checkpoint`, `sync`). A
   command that starts with `( for` may not match a prefix pattern, and a
   headless run would deny it. A real-CLI permission test settles that before any
   site migrates. It measures the
   instruction-budget headroom (`FIXTURE_HEADROOM_FLOOR_BYTES` is 100) and stops if a
   fixture would exceed its cap.
4. Migrate `templates/agents`, then `templates/skills` in batches the budget
   allows. These are the 337 sites the host can rewrite. Each batch names its
   verifier. A tree migrates only when it ships the resolver.
5. Decide the 152 sites by class, in a separate pull request with the same owner,
   starting when step 4 merges, with its own evidence. These are the sites where
   the probe is the only protection, so this step carries the part of issue #7281
   that the host rewrite cannot fix: `references/` (no rewrite), rules, and Python and YAML mentions. Class
   G sites stay on the legacy form.
6. Remove legacy acceptance for migrated classes. The allowance reaches zero.

Assignment sites need their own rule. At 48b4ea4c2, 97 lines in `templates` and
`src/claude` assign a variable from the nested form, such as `SCRIPTS_DIR=...`,
and later commands run `python3 "$SCRIPTS_DIR/..."`. The count comes from
`git grep -nE '^\s*[A-Za-z_][A-Za-z0-9_]*=.*COPILOT_PLUGIN_ROOT:-\$\{CLAUDE_PLUGIN_ROOT:-' 48b4ea4c2 -- templates src/claude`.
The validator uses this pattern. The shorter `[A-Za-z_]+=` also gives 97 at 48b4ea4c2 (checked 2026-11-12).
It covers Markdown, YAML, and `.py` lines alike. Step 3 states the scope of the
inventory it builds. A narrower pattern counts 84 to 92, so the inventory fixes
the real number. The locator takes the target
in one command, so it cannot replace the assignment line, and a foreign root still
reaches `$SCRIPTS_DIR`. Step 3 inventories these sites by file. Step 4 rewrites
each follow-on call to the locator and deletes the assignment, one skill at a
time. `--fix` reports an assignment it cannot rewrite, and the legacy allowance
keeps that file until a person rewrites it. A skill counts as migrated only when
no line in it assigns from the nested form. Assignment sites in `references/`
files wait for step 5.

Probe results for Copilot CLI and Codex join the step 2 evidence when quota
allows. A host with no result is not blocked, because the locator reaches
`.claude` and fails loud when nothing is there, which is no worse than the legacy
form. The ADR still records such a host as unproven.

Rollback: revert the migration pull requests. The resolver is inert while no site
calls it.

## Status at 2026-11-12

The record stays `proposed` and `implemented: false`, because a `proposed` record
cannot carry `implemented: true` (`check_adr_lifecycle.py`). Steps 1 to 3 have
merged. Steps 4 and 5 are partial. 22 skill sites outside Class G remain.

| Step | Pull request | Result |
|---|---|---|
| 1 | #7326 | This ADR, with two debate logs. |
| 2 | #7330 | The resolver, the recipe, and the tests. The real-CLI smoke covers Claude Code. #7333 made the mypy gate follow the resolver symlink. |
| 3 | #7336 | The validator reads the locator and gains `--fix`. |
| 4 | #7337, #7339, #7340, #7341 | Agents, then three skill batches. Partial: seven skills remain. |
| 5 | #7342 | Invocations and assignments in the `src/claude` support files. Prose mentions of the nested form remain in `src/claude` and `templates/rules`. |
| 6 | #7337, #7342 | Partial. The `templates/agents` and `src/claude` allowances are zero. The `templates/skills` allowance is not. |

At 4aff49bb0 (2026-11-12), `LEGACY_SITE_BASELINE` holds `templates/skills` at 15
invocations and 7 assignments. It holds `src/claude yaml` at 17 invocations, which
is Class G and stays by design. The Copilot CLI probe returned UNAVAILABLE for
quota. The Codex probe was not run.

Seven skills keep the legacy form. Each needs a decision, because the tool cannot
move it. "Rule 1" and "rule 2" below are rules of
`check_plugin_root_interpreter.py`. On 2026-11-12, for the `autoplan`,
`memory-maintenance`, and `skillforge` rows, the blocker was reproduced by
rewriting the sites by hand and running that validator. The `repository-completion-proof` row
was read from the validator's rule text and the script's import. The other rows
are facts about the commands or the byte cap.

| Skill | Sites | What stops the migration |
|---|---|---|
| `skill-bootstrap` | 11 invocations | `--fix` rewrites all 11. SKILL.md grows from 24,552 to 26,400 bytes (24,552 plus 11 times 168, computed), over the 24,576-byte cap. |
| `push-pr` | 4 invocations | The commands run `python3 -I`. `--fix` leaves them, because the locator has no interpreter option. |
| `autoplan` | 2 assignments | Rule 2 rejects `resolve_route.py`, which imports `yaml` (issue #5949). A byte-budget effect was not measured. |
| `memory-maintenance` | 1 assignment | Rule 2 rejects `count_memory_tokens.py`, which imports `tiktoken` (issue #5949). |
| `skillforge` | 1 assignment | Rule 2 rejects `quick_validate.py`, which imports `yaml`, and `package_skill.py`, which imports it through `quick_validate` (issue #5949). |
| `repository-completion-proof` | 2 assignments | Both set `GITHUB_SCRIPTS`. The commands run `uv run python`, and rule 1 allows only `python3`. `run_completion_gate.py` imports `yaml`. |
| `skillopt` | 1 assignment | `SKILLOPT_DIR` lets Codex and PowerShell run with no plugin root. Shipped references read it. |

`--fix` leaves every assignment for a person, as the Rollout section says. Until
these sites move, issue #7281 stays open for the seven skills.

## Amendment 2026-11-14: the last seven skills

On 2026-11-14 the owner chose option A in issue #7281. This amendment replaces
decision 5 and amends decisions 3 and 7. It adds decisions 11 to 14. It also
settles five reviewer asks from PRs #7340 and #7341. Decisions 1, 2, 4, 6, and
8 to 10 stand as written.

### Measurements

All counts are at b5e05e9c6 (2026-11-14). `skill_size.py` caps a whole
`SKILL.md` file at 24,576 bytes (`SKILL_BYTE_LIMIT`, `len(raw)`).

- 482 authored lines and fences hold the locator head (`_HEAD` in
  `plugin_run_launcher.py`), 298 of them under `templates`. Count:
  `git grep -F -o` of the head over `templates` and the hand-kept
  `src/claude` files.
- `github/SKILL.md` is 24,557 bytes with 5 copies of the head.
- `orphan-ref-validator/SKILL.md` is 24,535 bytes with 8 copies of the head.
  A ninth line names `ptk_run.py` in prose.
- A target probe in the shell text adds 26 bytes to every site. That draft
  sets `t=TARGET;` once and adds `&& [ -f "$d/$t" ]`. The 271-byte locator for
  `new_pr.py --x` grows to 297. `github/SKILL.md` would reach 24,687 bytes and
  `orphan-ref-validator/SKILL.md` 24,743. Both exceed the cap.

### Amended and added decisions

11. **The resolver may fall through to a later root that holds the target. This
    replaces decision 5 and amends decision 3.** The shell text does not change.
    - **Own root first.** When the target is a file under the resolver's own
      root, that copy runs. Nothing else is tried.
    - **Fallthrough.** Otherwise the resolver tries, in locator order, the
      values of `CLAUDE_PLUGIN_ROOT` and `COPILOT_PLUGIN_ROOT` from its own
      environment, then `.claude` under the working directory. It drops an
      empty value. It drops a candidate whose `os.path.realpath` equals the own
      root's or an earlier candidate's, so one tree is never probed twice. A
      candidate passes only when `os.path.isfile` is true for its
      `lib/ptk_run.py` and for the target, the same lexical test as decision 6.
    - The target is validated once, by decision 6, before any lookup.
    - The first candidate that passes runs, with decision 7 semantics. Before it
      runs, the resolver writes one stderr line:
      `ptk_run: <target> is not under <own root>; running it from <root>`.
    - When none passes, the resolver exits 2 with
      `ptk_run: target is not a file under any plugin root: <target>`.
    - **Why Python and not the shell.** The shell form breaks two byte caps (see
      Measurements). `--fix` could rewrite the 482 sites, so the caps are the
      deciding cost. The shell form would keep decisions 3 to 5 exact; the
      Python form does not, and the next bullets say how.
    - **What it fixes.** A plugin root that holds the resolver but not a
      repo-local skill's script (PR #7341, `repository-pr-recovery`), and a
      plugin root that holds the resolver but not the skill (PR #7340,
      `fix-markdown-fences` under `project-toolkit-knowledge`). A root whose
      older resolver predates this decision cannot fall through; it still
      exits 2.
    - **What it widens.** Decision 5 stopped at the first root with the
      resolver. Now a later root runs when it holds both files. Two cases
      follow, and decision 10 accepts both:
      - When our root lacks the target, the `.claude` copy runs. That is
        repo-controlled code, as decision 10 already says.
      - Where the host rewrote the bare token, the shell never read the
        environment. The resolver now does. A foreign root that ships its own
        `lib/ptk_run.py` and a same-named target runs. A root that ships both
        files controls them, so decision 10's limit is unchanged. A runtime
        test pins this case.
      The stderr line makes every fallthrough visible.
    - Row 1 says no `*PLUGIN_ROOT` reached a skill's shell on Claude Code
      2.1.322. There, `.claude` is the only fallthrough candidate.
12. **The locator carries one interpreter from a closed set. This amends
    decision 7.** The recipe renders one of three forms in front of
    `"$d/lib/ptk_run.py"`. Nothing else in the text changes, so every existing
    site stays valid.

    | Form | Who may use it | Rule 2 at that site | How the target starts |
    |---|---|---|---|
    | `python3` | every site (the default) | tracked target, import scan | `sys.executable <target>` |
    | `python3 -I` | every site | tracked target, import scan | `sys.executable -I <target>`, because the resolver reads `sys.flags.isolated` |
    | `uv run --frozen python` | a skill whose template sets `metadata.distribution: repo-local` | tracked target, no import scan | `sys.executable <target>`, the project interpreter |

    - The POSIX path (`os.execv`) and the Windows path (`subprocess.run`) build
      the same argument list, so `-I` reaches the target on both.
    - A consumer has no `uv` (MUST 4). The validator reads the skill name from
      the site's path and asks `build/scripts/skill_distribution.py`. A missing
      or unknown value counts as shipped, and a shipped site with the `uv` form
      is an offense. `--frozen` matches the repository's `uv` convention and
      keeps `uv run` from rewriting the lock.
    - A legacy-form site keeps its current interpreter until it migrates. The
      legacy count (rule 6) treats `python3 -I` like `python3`.
    - `push-pr` uses `python3 -I`. `repository-completion-proof` uses the `uv`
      form.
13. **Rule 2 takes a named allowance list for guarded imports.** Rule 2 walks a
    target's import closure and counts a guarded import as a dependency.
    - The list is `GUARDED_IMPORT_ALLOWANCES` in
      `plugin_root_interpreter_allowances.py`. Each entry names one target, one
      module, the site it unblocks, and the fallback in one sentence.
    - Four entries, one per blocked target:

      | Target | Module | Unblocks | Fallback |
      |---|---|---|---|
      | `autoplan/scripts/resolve_route.py` | `yaml` | `autoplan`, 2 assignments | exits 2, naming PyYAML |
      | `memory/scripts/count_memory_tokens.py` | `tiktoken` | `memory-maintenance`, 1 assignment | exits 1, naming tiktoken |
      | `skillforge/scripts/quick_validate.py` | `yaml` | `skillforge`, 1 assignment | parses with a stdlib reader |
      | `skillforge/scripts/package_skill.py` | `yaml` | `skillforge`, 1 assignment | through `quick_validate.py` |

    - The validator keeps an entry only while every import of that module in
      the closure is guarded by the rule 5 test (`unguarded_third_party_imports`).
      An entry covers its one module; a second unguarded module still fails.
    - A test runs each listed target with the module blocked and asserts the
      fallback in the table. It runs in the pytest suite, which runs before push
      and in CI.
    - An entry that matches no site, or whose import loses its guard, fails the
      run.
    - Why a list and not a guard-aware rule 2: rule 5 checks that a guard
      exists, not what the fallback does. A list makes a reviewer read each
      fallback once, and the test keeps it true. The owner chose the list.
14. **A directory variable comes from the locator.** `SKILLOPT_DIR` is read by
    shipped `references/` files, so it stays a variable.
    - The POSIX block assigns it from a locator that runs `skillopt.py where`.
      That subcommand prints the directory that holds `skillopt.py`. The probe
      that picks the root for the other commands picks this one, which is the
      #7341 ask. `where` is a target, so decision 6 applies unchanged.
    - The locator wins. A preset `SKILLOPT_DIR` is used only when the locator
      fails, which covers Codex and plain checkouts. When both fail, the
      assignment aborts with `${SKILLOPT_DIR:?...}` and a message, so the
      variable is never empty.
    - `references/` commands write `${SKILLOPT_DIR:?}`, so a skipped
      assignment fails loud and never runs `/skillopt.py`.
    - The PowerShell block is hand-written. It tries the same candidates in the
      same order and requires `lib/ptk_run.py` and `skillopt.py` under each,
      with `Test-Path -LiteralPath`. A structure test pins the order and the two
      checks.
    - Every other assignment site becomes one locator per call, and its
      assignment line is deleted, as the Rollout section already requires.

### Reviewer asks decided

| Ask | Source | Decision |
|---|---|---|
| Select the root by its target too | #7340 (`fix-markdown-fences`), #7341 (`repository-completion-proof`) | Adopted as decision 11, in Python. |
| Put `.claude` first for repo-local skills | #7341 (`repository-pr-recovery`) | Rejected. A repo's `.claude` would then shadow the installed, host-rewritten copy for every skill, against decisions 4 and 10. Decision 11 already reaches `.claude` when no plugin root holds a repo-local script. |
| Add a `PLUGIN_ROOT` candidate for Hermes | #7341 (`research`) | Rejected. ADR-115 records that Hermes `PLUGIN_ROOT` reaches MCP stdio servers only, not a skill's shell. ADR-071 records the Copilot `PLUGIN_ROOT` for plugin hooks only. A probe that finds it in a skill shell reopens this. |
| Resolve `SKILLOPT_DIR` from the same root | #7341 (`skillopt`) | Adopted as decision 14. |
| Write `${CLAUDE_PLUGIN_ROOT:-}` for `set -u` | #7340 (`memory-gate`) | Rejected. Row 6 shows the host leaves `${CLAUDE_PLUGIN_ROOT:-.claude}` literal, and decision 4's absolute path depends on the rewrite. Under `set -u` the locator aborts with an unbound-variable error, which is loud. `set +u;` inside the subshell would fix it at 8 bytes a site, which the two capped files cannot take. |
| Check a plugin manifest name on env roots | debate 4, security seat | Rejected. Alternatives already rejects the manifest as a marker: `.claude/` has none, and the Hermes packs use other names. Decision 10 says the resolver is not an authentication boundary. |

### Costs and limits

- `skill-bootstrap` moves its phase command blocks into a `references/` file so
  `SKILL.md` stays under 24,576 bytes. Row 5 says the host does not rewrite
  `references/`, so those commands rely on the probe alone. This is accepted
  for the largest skill.
- `autoplan` loses its `git rev-parse --show-toplevel` anchor. From a
  subdirectory of a checkout, its locator exits 2 with the `ptk_run:` prefix
  instead of finding the repo copy. Wrapping it in
  `cd "$(git rev-parse --show-toplevel)"` was weighed and rejected: it breaks
  the installed, no-checkout case that the locator serves.
- `skillforge` drops its `cd "$HOME/.claude"` line. The validators still need
  the skill under the working directory, and the locator's `.claude`
  candidate is relative to it.
- Hermes and Codex shells stay unproven, as the Rollout section says.

### Rollout, continued

Each step is its own pull request, in order.

7. This amendment, with debate log 4.
8. Decisions 11 to 13 in the resolver, the recipe, and the validator. Tests
   cover fallthrough order, realpath dedupe, the stderr line, the own-root-wins
   case, a foreign root with its own resolver, `-I` passthrough on both launch
   paths, the `uv` form and its repo-local gate, each allowance entry with its
   module blocked, and every committed locator target resolving under its own
   root with no fallthrough. No site moves.
9. Migrate the 22 sites (15 invocations and 7 assignments under
   `templates/skills`), split `skill-bootstrap`, and add decision 14. The
   `templates/skills` entry in `LEGACY_SITE_BASELINE` goes from (15, 7) to
   (0, 0). The `src/claude yaml` count of 17 stays, because it is Class G. This
   step closes issue #7281, whose 2026-11-12 status comment names these 22
   sites as the open scope.

Rollback: revert step 9, then step 8. A step 8 revert is safe for every site,
because decision 11 changes nothing when the target is under the resolver's own
root.

## Alternatives considered

| Option | Why not |
|---|---|
| Document `env -u CLAUDE_PLUGIN_ROOT` | The owner rejected it. The failure stays and depends on every agent reading a note. |
| Per-plugin variable name | Hosts export fixed names. The plugin cannot set its own. |
| Render the bare token per host, no resolver | It fixes the 337 rewritable sites on Claude Code at no cost per site. It leaves `references/` and every other host on the first-set-wins form. The locator's first candidate is that same token, so the resolver contains this option and adds the probe for the rest. |
| Inline `python3 -c` probe at each site | About 450 characters per site. It repeats validation 489 times. |
| Shell loop that probes the target | It repeats validation at every site and accepts a foreign file with the same name. |
| Template token only | Skill templates reject `{{var}}`, and `references/` files are byte copies. |
| Manifest name as the marker | `.claude/` has no manifest, and the Hermes packs use other names. |
| `${CLAUDE_SKILL_DIR}` alone | Only `SKILL.md` text is rewritten. Other hosts leave it literal. |

## Consequences

- **Good.** One place enforces the contract. Where the host rewrites the token, no
  foreign environment can displace our script. A bad root fails loud.
- **Cost, measured 2026-11-11.** The locator is 260 characters against 92 for the
  legacy form, so each site grows by 168 plus its arguments. A command starts a
  second `python3`, about 12 ms on the author's host. A model must copy a
  260-character command exactly. The validator checks committed bytes, not what a
  model types. A bad copy fails loud.
- **Version skew.** A root whose resolver exists but whose target does not exits 2.
- **Review date.** Review this record by 2027-02-11, or when a Copilot CLI or
  Codex probe returns.
- **Riskiest assumption.** Hosts other than Claude Code may export no variable to
  a model-issued shell and may not rewrite the token. The locator then falls to
  `.claude`, which is today's behavior and fixes nothing for an installed consumer
  on that host. The first Copilot or Codex probe result may change step 4 for that
  host.

## Enforcement and tests

- A runtime-contract test runs the committed locator through `sh -c` from a
  directory that is not the plugin root. Cases:
  - A foreign root that holds a same-named script runs our script.
  - A foreign root that also holds a `lib/ptk_run.py` is the accepted limit of
    decision 10, and the test documents it.
  - Both variables unset falls to `.claude`.
  - No root holds the resolver, and the exit is 2 with the `ptk_run:` prefix.
  - A root path with spaces, and arguments with spaces, a leading `-`, `;`, `$()`,
    and a newline, arrive intact.
  - Target exits 1, 3, and 4 pass through.
  - A target that fails validation exits 2.
- The negative control runs the legacy form through the same harness. It fails.
- `check_plugin_root_interpreter.py` matches only an interpreter followed by
  `${..._ROOT`. The validator must read the target out of the locator, or rules 1
  and 2 stop covering migrated sites. Rule 5 is a per-module import-time scan, so
  migrating a site does not change its coverage.
- A host-inlined root is a path the host writes into the double quotes. The
  matrix adds a root that holds `$`, a backtick, and a double quote, and records
  which of them the form survives.
- A real-CLI smoke runs the committed text under Claude Code. It needs model
  quota, so it joins `plugin-cli-smoke.yml` as a blocking job only after the job
  proves it can run there. Step 2 checks whether the workflow's
  `continue-on-error` setting applies to that job.
- Per `generated-artifacts.md`, the committed artifacts are gated, and the build
  output is compared with the recipe.

## Related

- Issue #7281, PR #7318 (the gate probe), issue #3897 (the Python bootstrap).
- ADR-035 (exit codes), ADR-071 (hook runtime contract), ADR-109 (template-first
  distribution), ADR-119 (symlinked dogfood trees).
- `2026-06-02-pr-2205-customer-wedge-incident.md`.
