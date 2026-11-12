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
   `.claude`.
4. **Candidate order.** The host-rewritten token goes first because it names the
   copy the host loaded. If two copies of this plugin are installed, that copy
   wins. `COPILOT_PLUGIN_ROOT` follows. `.claude` is last.
5. **The first root that passes the probe is final.** The locator never tries a
   later root after one passes. That is how a different plugin's script would run.
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
   `bash` blocks are POSIX by existing decision.
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

Probe results for Copilot CLI and Codex join the step 2 evidence when quota
allows. A host with no result is not blocked, because the locator reaches
`.claude` and fails loud when nothing is there, which is no worse than the legacy
form. The ADR still records such a host as unproven.

Rollback: revert the migration pull requests. The resolver is inert while no site
calls it.

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
  `${..._ROOT`. The validator must read the target out of the locator, or rules 1,
  2, and 5 stop covering migrated sites.
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
