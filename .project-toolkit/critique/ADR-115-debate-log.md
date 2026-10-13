# ADR Debate Log: ADR-115 Native Plugin Support for Cursor, Codex, Grok Build, Hermes, Devin, Pi, and Muse

## Summary

- **Rounds**: 5
- **Outcome**: Consensus
- **Final Status**: proposed (owner decides acceptance)
- **Numbering**: decision numbers in rounds 1 to 3 predate the round 4 renumbering. Smoke was Decision 9 (now 10), the resolver rule was Decision 8 (now 9), and Hermes was Decision 5 (now 6).
- **Panel**: reduced, architect and critic. The record is new prose and changes neither executable enforcement nor a rule other gates read.

## Round 1 Summary

### Key Issues Addressed

- Critic P0: Codex reads one of two marketplace files, and the record did not say which.
- Critic P0: Hermes blocks a `dangerous` install scan, and the record did not run the scan.
- Critic P0: a `NOT RUN` smoke conflicts with `generated-artifacts.md` MUST 4 and MUST NOT 2.
- Architect P1: packing Hermes skills by name splits `pr-review` and `pr-autofix` from the `github` scripts they call.
- Architect P1: the record named no new generator modes or schema keys.
- Architect P1: the Codex and Grok reasons used opposite logic; ADR-111 was not cited.
- P2s: `OWNED_PREFIXES` wording, the source tree for skills, no Decision Drivers, Cursor skill keys, Muse citations.

### Major Changes Made

- Measured Codex 0.162.1 marketplace precedence in a scratch `CODEX_HOME`, with a negative control and a same-name install. Codex reads only `.agents/plugins/marketplace.json` when both exist. The record now keeps the `ai-agents` name and the `project-toolkit` id.
- Ran Hermes `plugin_guard` at the pinned commit. The full tree is `dangerous`; per skill, 85 safe, 5 caution, 7 dangerous. The 7 are excluded.
- Replaced `NOT RUN` with Decision 9: no marketplace entry before a real-runtime smoke passes.
- Replaced name-order packing with a hand-maintained `packs` table and a build failure on cross-pack references.
- Named `rules.outputFormat`, `agents.frontmatterDrop`, `agents.sourceDir`, and `skills.mode: hermes-packs`.
- Added Decision Drivers and the Muse citations.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit, four P1s conditional |
| critic | Block, three P0s |

## Round 2 Summary

### Key Issues Addressed

- Critic P0: 166 skill files import `lib/`, and no new tree shipped it. Moving Codex installs to `src/codex` would break scripts that work today.
- Architect P1: 33 skills find scripts only through Claude and Copilot locations, and the smoke bar did not run a script.
- Critic P2: Cursor skill keys `license`, `user-invocable`, and `size-exception` were neither kept nor dropped; Hermes exclusion was not transitive.

### Major Changes Made

- Measured `src/claude/lib/`: 40 files, 376 KB, `plugin_guard` verdict `safe`.
- Every tree and every Hermes pack gets `lib/`. The Hermes skill budget per pack is 340 files.
- New Decision 8: resolvers gain only measured host locations, recorded by amendment.
- Decision 9 smoke now runs a `lib`-importing script through the skill's own resolver.
- Cursor skills use an allow list. Hermes exclusion is a computed closure.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit, one new P1 |
| critic | Block, one new P0 |

## Round 3 Summary

### Key Issues Addressed

- Critic P2: the Neutral consequence was wrong once resolvers change; `lib_mirror.py` `PLUGIN_ROOTS` and the `surface-parity.yaml` rows were not named; Decision 8 had no fallback.
- Architect P2: the file-count estimate was stale.

### Major Changes Made

- Neutral line now says behavior does not change while `SKILL.md` text does.
- Decision 1 names the `PLUGIN_ROOTS` extension and the `lib` parity rows.
- Decision 8 falls back to the measured install path, else no marketplace entry.
- The count now separates skill files from `lib/` copies.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |

### Post-consensus evidence

On 2026-10-13 the owner pointed to the Hermes plugin developer guide. Its text at the pinned commit adds two facts to Decision 5. Native `register_skill` skills stay out of `<available_skills>`. Portable packages get `PLUGIN_ROOT`. Both support the portable form the panel accepted, so no decision changed and no new round ran.

## Round 4 Summary

### Key Issues Addressed

- Scope change by the owner on 2026-10-13: add Devin and Pi, and reopen Muse, citing `obra/superpowers` as a working example.
- Architect P1 and critic P1: Devin loads a root `AGENTS.md` as an always-on rule, and `src/claude/AGENTS.md` is a repository-only guide.
- Critic P1: the Muse field set and the ADR-092 `version` rule were left open.
- P2s: the Muse generator and gate were unnamed, "observed working file" overstated the evidence, Muse may need the ADR-111 drop, Devin has no marketplace file to withhold, and two counts were stale.

### Major Changes Made

- Devin gets a generated `src/devin/` tree without `AGENTS.md` or `CLAUDE.md`.
- Pi reads a private root `package.json` whose `pi.skills` points at `src/claude/skills`.
- Muse emits six named fields with no `version`, through an `artifacts.muse` stanza and a drift gate. A recorded `muse plugins validate` and `install` run is its schema check.
- Grok Bot stays unsupported.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit, one P1 |
| critic | Block, two P1s |

## Round 5 Summary

### Key Issues Addressed

- Confirmation of every round 4 item.
- Architect P2: Devin's rule copy did not say whether internal-only globs are filtered.
- Critic P2: the Status line still named round 4 as the last round.

### Major Changes Made

- Devin filters internal-only rule globs the way Cursor does.
- Status records rounds 4 and 5.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |

## Owner Review and Measurement Amendments, 2026-10-13

No panel round ran for these changes. Their authority is the owner's 12 review threads on PR #6437, the host measurements recorded in the ADR, and the Cursor branch security review.

### Key Issues Addressed

- Owner threads: stale research date, missing Grok Build evidence, Hermes exclusions contradicting "same 97 skills", rules keys left open, Hermes enable and subdirectory install steps, the 380 versus 400 gap, the MUST 3 citation, Devin's missing marketplace file, the reversibility wording, and debate-log grammar and numbering.
- Measurement: Hermes `PLUGIN_ROOT` reaches MCP servers only, not a skill's shell, which falsified the Decision 6 claim that resolvers can use it.
- Security review of the Cursor branch (BLOCK): Cursor has no `tools` allow list, so a `security` agent copy lost its no-shell restriction.

### Major Changes Made

- Decision 3: Cursor rules keep only `description`, `alwaysApply`, and `globs`. An agent whose `tools` restriction `readonly` cannot express does not ship to Cursor.
- Decision 6: Hermes resolvers use the install path, the stanza also drops `allowed-tools`, and each pack needs an enable step.
- Host facts and measurements now record the Grok Build, Cursor, Hermes, and Codex runs of 2026-10-13.
- Decision 11 and the Reversibility Assessment wording, per the owner threads.

### Agent Positions

| Agent | Position |
|-------|----------|
| owner (reviewer) | Raised the 12 threads these edits answer |
| security | Block on the Cursor branch; the Decision 3 agent rule answers it |

### Next Steps

The owner decides acceptance. Implementation follows Decision 12, one pull request per host, Grok Build first.
