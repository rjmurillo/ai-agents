# Plan: ai-agents init — Stage 1 Claude Kit Vendor

**Issue:** https://github.com/rjmurillo/ai-agents/issues/1574
**Related PR (merged, to be deprecated):** https://github.com/rjmurillo/ai-agents/pull/1575
**Branch:** `feat/1574-stage1-claude-kit-vendor`
**Milestone:** v1.1
**Priority:** P1
**Stage:** 1 of 4 (Claude-only, ship this week)

---

## Problem

ai-agents has 26MB of structured institutional memory, governance, session protocols, 25+ agents, 62 skills, and 57+ ADRs. It works. It compounds. But the onramp is a cliff: read SESSION-PROTOCOL, configure Serena, understand skill routing, learn the agent roster, then finally do something useful. Squad ships in 3 commands. We need the same onramp, reusing everything we already have.

The strategic reframe (per Richard, 2026-04-12): the "working team" already exists in `.claude/commands/*.md` + `.claude/agents/*` + `.claude/skills/*`. We do not build a new team. We package the existing one into `npx ai-agents init`.

Four-stage ladder:

1. **Stage 1 (this plan):** Claude version. `npx @rjmurillo/ai-agents init` vendors a curated `.claude/` kit into a target repo. Works with Claude Code immediately. Days.
2. Stage 2: Copilot infrastructure. Translator `.claude/*` → Copilot format. Weeks.
3. Stage 3: Squad-compete Copilot version. Includes `--from squad` importer. Weeks.
4. Stage 4: Evangelize. Blog, HN, Squad community outreach, benchmarks. Ongoing.

Stage 1 is the only one specified here. Stages 2-4 are named to lock sequencing. Each gets its own spec when its time comes.

---

## Premises (these must be true for this plan to make sense)

1. **P1:** Developers have Node installed. `npx` is a one-step command.
2. **P2:** The existing `.claude/` kit works for users of this repo. It will also work for users of fresh repos after curation + generic top-level files.
3. **P3 (revised 2026-04-12):** Claude Code is the dogfood runtime. Richard uses it daily; shipping there first means every bug hits him before it hits a user. Tightest feedback loop. Copilot follows in Stage 2. The CLI's job is the same for both targets: a "lazy wrapper" that updates `CLAUDE.md` and/or `.github/copilot-instructions.md` and vendors the portable assets. Low-stakes convenience tool, not platform magic.
4. **P4:** ADR-042 (Python first) can be amended to scope "Python first" to internal automation. User-facing distribution surfaces may use TypeScript when the target audience demands it.
5. **P5 (revised 2026-04-12 post-Q9):** The full `.claude/` vendor (minus github skill) is sufficient for a first-session experience. Strong opinions are a feature — users who want neutral start should use alternatives. We accept the tradeoff: higher friction for tourists, faster value for believers.
6. **P6:** npm publication as `@rjmurillo/ai-agents` is acceptable. Unscoped name reservation is not blocking.

---

## Acceptance criteria (testable)

### REQ-1 — `npx ai-agents init [path]` vendors the full Claude kit

- **REQ-1.1:** Creates target dir if missing. Vendors the entire `.claude/` tree (see REQ-2 for exclusions). **Pass/fail:** tree comparison against canonical snapshot.
- **REQ-1.2 (revised per Q10):** Appends a generic inline context block to the target's `CLAUDE.md`. If `CLAUDE.md` does not exist, creates it with only the generic block. Block contains: harness overview, skill routing rules, lifecycle commands reference, memory interface decision matrix. No `@import` syntax — fully inline. **Pass/fail:** grep for block markers `<!-- ai-agents:begin -->` and `<!-- ai-agents:end -->`; idempotent re-runs do not duplicate the block.
- **REQ-1.3:** Writes `AGENTS.md` at target root if missing. Generic 10-line harness overview + pointer to `.claude/commands/`. Frames `.claude/` as harness spec, not defaults. Frames content as "harness spec" not "defaults". **Pass/fail:** file exists, contains "harness" + "spec" + "interop" keywords; does not overwrite existing `AGENTS.md`.
- **REQ-1.4:** Idempotent. If target `.claude/` tree already exists AND diverges from vendor snapshot, refuse with exit 2. `--force` overrides (warns + overwrites). **Pass/fail:** exit code tests; re-run with no changes = exit 0 no-op.
- **REQ-1.5:** Prints one next-step line: `Open this folder in Claude Code and run /spec to start.` Plus one-line bundle summary: `Vendored N commands, M agents, K skills.` **Pass/fail:** stdout line count ≤ 3.
- **REQ-1.6:** Bundle is **full scope** of `.claude/` per Q9 decision (2026-04-12). Curated-subset approach from prior spec draft is rejected.

### REQ-2 — Vendor bundle scope (full minus exclusions)

**Included (user-facing content):**
- `.claude/commands/` — all 15 commands + subdirs + yaml configs. **Claude-specific syntax; Stage 2 needs Copilot translator for these.**
- `.claude/agents/` — all 24 agent files + index
- `.claude/skills/` — all skills EXCEPT `github/` (Q11)

**Excluded (Eng review finding 2026-04-12 — dev-private runtime infra, not portable):**
- `.claude/hooks/` — Python hooks, depend on Python 3.14 + UV + `.claude/lib/hook_utilities/`. Fail-closed in fresh repos (no Python interpreter, no imports resolve). NOT user-facing content; ai-agents3 internal dev infra.
- `.claude/lib/` — Shared libs imported only by `.claude/hooks/`. Worthless without hooks.
- `.claude/settings.json` — Registers hook paths; wires session-init, lint hooks, scheduled tasks. Every entry is repo-specific. Emit `settings.json.sample` in Stage 1.1+ after preflight design.
- `.claude/*/__pycache__/`, `*.pyc`, `.skill_pattern_cache.json` — binary artifacts, absolute paths embedded.
- `.claude/scheduled_tasks.lock` — runtime state.
- `.claude/settings.local.json` — user-local overrides.
- `.claude/worktrees/` — transient agent scratch.
- `.claude/skills/github/` — framework-opinionated (Q11).

**Rationale for exclusion (reconciliation with Q9):** Q9 resolved "full scope" for user-facing content. Eng voices independently identified that hooks/lib/settings.json are NOT user-facing — they are this repo's private CI + dev-loop infrastructure with hard dependencies on Python, UV, Serena, Forgetful, and `.agents/` governance. Including them ships a known-broken first run regardless of target runtime (Claude or Copilot). Excluding them is the technical implementation of Q9, not a reversal.

**Top-level additions (new stubs):**
- `AGENTS.md` — generic harness overview (REQ-1.3)
- Generic inline block appended to `CLAUDE.md` (REQ-1.2)

**Requirements:**
- **REQ-2.1:** Manifest auto-generated at build time by walking `.claude/` with exclusions applied. Not hand-edited. Lives at `packages/ai-agents-cli/bundle/manifest.json`. **Pass/fail:** manifest content matches `.claude/` tree modulo exclusions.
- **REQ-2.2:** CI job regenerates manifest on every push and fails if committed manifest is stale. **Pass/fail:** CI diff check.
- **REQ-2.3 (revised per Eng phase, both voices CRITICAL):** Pre-publish lint is **BLOCKING**, not warning-only. Exit 1 blocks publish on any match of:
  - `(^|[^A-Za-z0-9_])\.agents/` — broken governance path
  - `(^|[^A-Za-z0-9_])\.serena/memories/` — broken memory path
  - `rjmurillo/ai-agents` or `ai-agents3` (allowed only in README top 30 lines + bundle provenance metadata)
  - `(?:^|[\s"'`])(?:/home/|/Users/|[A-Za-z]:\\)` — absolute paths
  - `ADR-0\d{2,3}` when used as a normative dependency, not historical prose (heuristic: presence of "see ADR-NNN" or "per ADR-NNN")
  - `HANDOFF\.md|SESSION-PROTOCOL\.md|pr-quality-gate-output\.schema\.json` — references to files that won't exist in target
  - `Validate-PRReadiness\.ps1`, `Test-InvestigationEligibility\.ps1` — `.agents/`-relative scripts
  - `__pycache__|\.pyc$|\.lock$|\.local\.json$` in manifest paths — binary/state artifacts
  - `settings\.json` referencing files outside the vendored tree

  **Pass/fail:** lint exits 0 on clean bundle, exit 1 on any match. CI publish workflow runs lint as a required gate. Offending files must be rewritten or excluded before publish. The plan's Stage 1 work includes cleaning or excluding every currently-flagged file in commands/, agents/, and skills/ (likely dozens — see REQ-2.5).
- **REQ-2.4 (new):** Bundle size is not a blocker (Q12). Verify `npm pack` output size and log it. If >50MB, emit warning but proceed. **Pass/fail:** size logged in publish workflow. Measured baseline (Eng phase, 2026-04-12): `.claude/` minus exclusions ≈ 14MB, well under npm practical threshold.
- **REQ-2.5 (new, Eng phase finding):** Stage 1 includes a "cleanup pass" sub-task that walks vendored content and replaces or removes every reference matched by REQ-2.3 lint rules. Rewrites produce generic placeholders (`.agents/governance/PROJECT-CONSTRAINTS.md` → removed or replaced with `<your-governance-doc>`). ADR citations in historical prose are allowed (non-normative); ADR citations in imperative instructions must be rewritten or removed. **Pass/fail:** lint exits 0 on final bundle. This is the bulk of Stage 1 engineering effort.

### REQ-1 extension: architecture interfaces (Eng phase finding, both voices CRITICAL)

- **REQ-1.7 (new):** The TS package declares two interfaces before any copy logic runs:
  ```typescript
  interface BundleSource {
    list(): AsyncIterable<BundleEntry>;
    read(entry: BundleEntry): Promise<Buffer>;
  }
  interface TargetEmitter {
    canEmit(target: TargetContext): boolean;
    emit(entry: BundleEntry, target: TargetContext): Promise<void>;
  }
  type Transform = (entry: BundleEntry, target: TargetContext) => BundleEntry | null;
  ```
  Pipeline: `BundleSource → Transform[] → TargetEmitter`. Stage 1 ships one `BundleSource` (local assets), no transforms, one `TargetEmitter` (Claude filesystem layout). Stage 2 adds a second `TargetEmitter` (Copilot layout) and transforms for command-syntax translation without touching `init.ts`. **Pass/fail:** interfaces exist in `src/types.ts`, `init.ts` depends only on the interfaces, not on concrete classes. Cost: ~20 LOC. Payoff: Stage 2 becomes additive, not a rewrite.

### REQ-3 — Published to npm as `@rjmurillo/ai-agents`

- **REQ-3.1:** `npx @rjmurillo/ai-agents init /tmp/demo` works on fresh container with only Node installed. **Pass/fail:** CI fresh-container test.
- **REQ-3.2:** Built with bun, published as plain JS + bundled assets. No bun runtime required for consumers. **Pass/fail:** test under `node` without bun.
- **REQ-3.3:** README top 30 lines contain 3-step quickstart: install (or skip, using npx), init, open Claude Code. **Pass/fail:** README grep.
- **REQ-3.4 (Eng phase finding — npm mechanics):**
  - `package.json`: `name: "@rjmurillo/ai-agents"`, `bin: { "ai-agents": "dist/cli.js" }`, `files: ["dist/", "bundle/assets/", "README.md", "LICENSE"]` allowlist
  - Publish command: `npm publish --provenance --access public`
  - CI publish job runs from GitHub Actions with OIDC auth (not PAT)
  - `tsconfig.json` targets ES2022, module Node16
  - `bunfig.toml` used for build only; bun is dev dependency
  - CI validates consumer install via `npm pack` then `npx --yes ./rjmurillo-ai-agents-*.tgz init /tmp/demo`, NOT from source checkout
  - Release docs enumerate: npm auth setup, 2FA/provenance permissions, rollback procedure, yanking a bad version
  - **Pass/fail:** all of the above present + CI pack-install smoke green

### REQ-4 — CI smoke test (multi-OS + first-turn verification)

- **REQ-4.1:** GH Action matrix (ubuntu-latest, macos-latest, windows-latest) runs `npx @rjmurillo/ai-agents init /tmp/demo` and verifies expected file tree. **Pass/fail:** 3 green jobs.
- **REQ-4.2:** Smoke test uses `npm pack` tarball, installed via `npx --yes ./tarball init`, not source checkout. **Pass/fail:** job references tarball.
- **REQ-4.3 (Eng phase finding):** Smoke test matrix covers Node 20 AND Node 22 on each OS. Bun is used only in the build job; consumers use Node. **Pass/fail:** 6 green jobs (3 OS × 2 Node).
- **REQ-4.4 (Eng phase finding — first-turn verification):** After `init` completes, smoke test runs `claude --non-interactive "/spec hello world"` in the target dir and asserts zero unresolved-path errors in output. This catches bundled content that references `.agents/` or other missing dependencies at agent runtime. **Pass/fail:** zero errors matching `(file not found|no such file|cannot resolve|ENOENT).*\.agents` in claude stdout. This is the decisive test: does the bundle actually work in a fresh repo?
- **REQ-4.5 (Eng phase finding):** Test fixtures for edge cases:
  - Existing `CLAUDE.md` with: missing trailing newline, CRLF line endings, duplicate markers, user content before/after block markers
  - Existing `.claude/` with local user edits + `--force`
  - Fresh empty dir with no git repo
  - Dir with Unicode filenames
  - Symlinks in source bundle (reject at manifest-build time per Eng finding)
  - `--dry-run` mode: list all files that WOULD be created without touching disk
  - Partial failure: copy to `.claude.tmp`, verify, atomic rename on success
  - **Pass/fail:** unit tests for each; CI job runs them

### REQ-5 — Deprecate Python `scripts/init_project.py`

- **REQ-5.1:** Delete `scripts/init_project.py`, `tests/test_init_project.py`, `[project.scripts]` entry in `pyproject.toml`. **Pass/fail:** files absent, toml entry gone.
- **REQ-5.2:** Commit message cites user-preference memory `no-bash-python` + references this plan. **Pass/fail:** commit grep.
- **REQ-5.3:** No callers remain (verified in discovery phase — only pyproject + its own test).

### REQ-6 — Docs positioning

- **REQ-6.1:** `README.md` adds "Fastest Start (Zero Config)" as the first section after the header. **Pass/fail:** section order check.
- **REQ-6.2:** Existing install-plugin + skill-installer docs preserved unchanged, demoted to "Alternative: Full Installation" beneath Fastest Start. **Pass/fail:** section order + unchanged content hash.
- **REQ-6.3:** `AGENTS.md` generic stub (bundled in kit) frames `.claude/` as a harness spec other tools can read/write. **Pass/fail:** grep for "harness" + "spec" + "interop" in the stub.

### REQ-7 — Review gates

- **REQ-7.1:** Security agent reviews bundled content for embedded secrets, credentials, unsafe commands, shell injection risk. Verdict: PROCEED required. **Pass/fail:** security agent verdict.
- **REQ-7.2:** DevOps agent reviews npm publish flow (auth, provenance), CI matrix, bun build reproducibility. Verdict: PROCEED required. **Pass/fail:** devops agent verdict.
- **REQ-7.3:** ADR-042 amendment drafted + adr-review cleared before S1 merges. **Pass/fail:** ADR exists, adr-review PROCEED recorded.

---

## NOT in scope

- Copilot support (Stage 2)
- `.github/copilot-instructions.md` generation (Stage 2)
- Codex adapter (bundled `AGENTS.md` will work incidentally; no explicit adapter)
- `--from squad` importer (Stage 3)
- `chat`, `status`, `doctor`, `nap`, `upgrade`, `export`, `import` commands (all out, revisit post-S3)
- Template tiers (minimal/standard/full) — full vendor is the only tier in S1 (Q9)
- `.serena/` scaffolding (separate skill, parallel PR, not bundled with `init`)
- Telemetry (defer to v0.2)
- Blog / HN / marketing (Stage 4)
- Breaking changes to existing `/install-plugin` and `skill-installer` paths

---

## What already exists (leverage map)

| Sub-problem | Existing code/asset | Leverage |
|---|---|---|
| Working agent team | `.claude/agents/` (24 agents) | Vendor all 24 (Q9: full scope) |
| Working command set | `.claude/commands/` (15 commands + subdirs) | Vendor all |
| Working skill catalog | `.claude/skills/` (62 skills) | Vendor 61 (exclude `github/` per Q11) |
| Event hooks | `.claude/hooks/` | **EXCLUDED** (Eng finding — Python deps) |
| Shared libs | `.claude/lib/` | **EXCLUDED** (imported only by hooks) |
| Project settings | `.claude/settings.json` | **EXCLUDED** (wires hook paths; emit `.sample` in v0.2+) |
| ADR for language choice | `.agents/architecture/ADR-042-python-first-enforcement.md` | Amend to scope Python-first to internal automation |
| npm publish pattern | None in repo today | Greenfield — scoped `@rjmurillo/ai-agents` + `bin` entry |
| CI matrix pattern | Existing GH Actions workflows under `.github/workflows/` | Reuse matrix idiom |
| Bundle lint pattern | None yet | Write small TS script that walks vendored tree + reports repo-specific refs |
| Generic CLAUDE.md pattern | Q10 answer: inline block append, HTML-comment delimited | Emit fixed template string |

---

## CVA summary

- **Common:** Vendoring a file tree from a manifest into a target directory.
- **Varies (in Stage 1):** Nothing. Single target = Claude Code. One emitter.
- **Varies (in Stages 2-3):** Target runtime (Copilot format, Squad source format). These unlock real variability — the emitter/adapter pattern becomes right at that moment.
- **Relationship:** Stage 1 is the smallest useful abstraction: copy files from manifest. Introducing a strategy/adapter layer now is premature generalization. YAGNI.

---

## Open questions (all resolved 2026-04-12)

| # | Question | Answer |
|---|---|---|
| Q9 | Curated kit list? | **RESOLVED:** Full scope of `.claude/`, no curation. Everything ships. |
| Q10 | `CLAUDE.md` import syntax? | **RESOLVED:** Append inline block to user's `CLAUDE.md`. No `@import`. Block is delimited by HTML comments for idempotency. |
| Q11 | Bundled `github` skill Python conflict? | **RESOLVED:** Skip `.claude/skills/github/` in S1 bundle. "Strong opinions in some frameworks — make call later." Defer framework-opinion review to Stage 2. |
| Q12 | Bundle size budget? | **RESOLVED:** 18M is fine. Skills are effective, slimming deferred. Size warning logged but not blocking. |

---

## Risks + pre-mortem

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Curated kit has hidden repo-specific references | High | Medium | REQ-2.3 lint + manual spot check |
| `CLAUDE.md @import` paths fail to resolve in fresh repo | Medium | High | CI smoke test runs in truly empty dir |
| npm name `@rjmurillo/ai-agents` taken | Low | Low | Scoped; user owns scope |
| Bundle exceeds npm 10MB practical threshold | Medium | Medium | Q12 measures early; drop files if over |
| `github` skill Python scripts trigger user-pref complaint | Medium | Low | Q11 resolves before REQ-2 lands |
| PR 1575 deletion breaks an unseen caller | Low | Medium | grep verified only pyproject + self-test; REQ-5.3 locks verification |
| Squad releases Claude mode mid-sprint | Low | Medium | Keep moving; S1 is days, not weeks |
| ADR-042 amendment gets stuck in adr-review | Medium | High | Land as separate PR first, ADR clears, then CLI merges |
| Windows path handling breaks scaffolder | Medium | Medium | Windows CI row is mandatory |
| Users run `init` in existing non-empty repos and clobber | Medium | High | REQ-1.4 idempotency + `--force` gate |

---

## Sequencing (proposed)

1. ADR-042 amendment PR (architect + adr-review) — parallel
2. Create `packages/ai-agents-cli/` scaffold + TS+bun setup — day 1
3. Write manifest + bundle lint — day 1
4. Implement `init` command + generic CLAUDE.md/AGENTS.md stubs — day 1-2
5. CI smoke matrix — day 2
6. Security + DevOps agent review gates — day 2
7. Delete Python init_project.py — day 2 (after TS ships)
8. README "Fastest Start" section — day 2
9. npm publish dry-run — day 2
10. Final PR + merge — day 3

---

## Discourse notes (from issue #1574 comments)

- **Comment 2 (PRD bot):** Milestone v1.1, P1, complexity 10/12, escalated to PRD. Aligned to "Master Product Objective: minimal friction adoption."
- **Comment 3 (analyst bot) — gap analysis table is load-bearing:** Time-to-value gap, cognitive-load gap, no-pre-built-team gap, chat-entry gap. Stage 1 closes first three; chat-entry gap is closed differently (users open Claude Code natively, agents load automatically, no wrapper).
- **Comment 4 (Richard):** "The init issue above is tactical. This comment captures the strategic reframe." → platform framing. The `.claude/` kit IS the working team.
- **Comments 0, 5 (traycer):** Python-path plans, now obsolete. Caught real docs positioning needs ("harness not product", "Fastest Start" section). Both fed into REQ-6.

---

## /autoplan Phase 1: CEO Dual Voices (2026-04-12)

### CLAUDE SUBAGENT (CEO — strategic independence)

**Severity: HIGH — wrong framing.** Plan solves "how do we ship a CLI" when the user's actual job is "get a working AI team running in a repo in 60 seconds." A GitHub template repo ships today in hours. Plan never considered it.

**Severity: CRITICAL — P2 is a trapdoor.** REQ-2.3 lint is warning-only and explicitly "accepts strong opinions inherited." Shipping a bundle known to contain repo-specific references (`.agents/governance/*`, `ai-agents3` paths, ADR citations). Cost if wrong: users install, hit broken references, abandon on first run. Onramp becomes offramp. **Fix:** make the lint blocking.

**Severity: HIGH — P3 is founder-local reasoning.** "Claude Code users are ai-agents' existing audience → lose zero users" is retention logic, not acquisition logic. Squad's growth audience is Copilot devs. Shipping Stage 1 to people who already have us is optimizing the wrong metric.

**Severity: MEDIUM — P5 contradicted.** Q9 resolved to "full scope, no curation," invalidating P5's "curated kit is sufficient" phrasing. Signals the plan was rewritten without re-examining its foundation. [NOTE: fixed in plan file.]

**Severity: HIGH — right-size wrong.** Too much AND too little. Full-scope vendoring of 24 agents + 62 skills + hooks + lib is NOT an MVP; it is a complete platform dump. Meanwhile it cuts the entire Copilot audience. Maximalist bundle + minimalist market.

**Severity: HIGH — alternatives dismissed silently.** GitHub template repo, `curl | bash`, `degit`. `gh repo create --template` is 30 seconds vs 3-day npm yak shave. The plan builds infrastructure before validating demand.

**Severity: HIGH — October 2026 regret.** The bundle lint being warning-only. Predicts a GitHub issue titled "nothing works after `npx init`" closed as wontfix because fixing means un-shipping.

**Severity: MEDIUM — competitive risk.** Squad shipping Claude mode before Stage 2 is plausible. Bigger risk: Squad doesn't need to. They stay the 3-step Copilot answer while Stage 1 serves people we already have.

**4-hour MVP:** Cut npm, bun, CI matrix, security gate, DevOps gate, ADR amendment, Python deletion, README restructure, idempotency, `--force`. Keep: `gh repo create rjmurillo/ai-agents-starter --template`, push cleaned `.claude/` + generic `CLAUDE.md` + `AGENTS.md`. Tweet it. Measure stars.

**Verdict:** Plan ships infrastructure before validating demand. Template repo first; CLI only if template adoption proves the thesis.

---

### CODEX SAYS (CEO — strategy challenge)

**Severity: CRITICAL — plan is internally inconsistent.** REQ-1.6 says full scope, "NOT in scope" says no full skills bundle / no hooks, leverage map talks about curated subset. Nobody has made the core product decision: full transplant vs opinionated starter. Shipping from that ambiguity is how you create a support nightmare week one. [NOTE: fixed in plan file.]

**Severity: CRITICAL — wrong problem.** Plan is solving distribution friction, not adoption proof. `npx init` is a packaging answer to an unvalidated go-to-market question: do teams actually want your operating system, or do they just want 2-3 high-value workflows that work in their existing toolchain? **The 10x reframe is "portable team operating layer for any repo/runtime," not "vendor our Claude kit."** If that is the real product, Stage 1 should test portability and first-session value, not file copying.

**Severity: CRITICAL — competitive moat wrong.** If Squad ships a Claude mode before Stage 2, differentiation collapses unless the advantage is the team operating model itself. The plan treats runtime compatibility as the moat; it probably is not.

**Severity: HIGH — P2/P3/P5 weakest.** P2 assumes repo-specific institutional memory becomes broadly useful after light curation; usually false, cost is users importing alien governance that feels broken day one. P3 is founder-local reasoning (same as Claude subagent finding). P5 assumes "Squad-simple first session" while shipping a large inherited system with strong opinions; cost is false positive on install, false negative on retention.

**Severity: HIGH — Claude-only is a speed bet, not a market bet.** If target is "compete with Squad," Stage 1 is aimed at the wrong beachhead unless explicitly redefined as "serve existing Claude Code believers first."

**Severity: HIGH — alternatives dismissed too fast.** GitHub template repo would test demand in hours, not days. `curl` installer is uglier but closer to the actual problem than building npm packaging and publish machinery. **npm adds brand polish, not validated value.**

**Severity: MEDIUM — October 2026 regret.** Shipping 26MB vendored opinion stack with "warnings but not blocking" for repo-specific references; betting on `npx` as moat; amending ADRs to justify a distribution choice instead of choosing the smallest experiment.

**Severity: HIGH — 4-hour MVP.** Cut npm, CI matrix, manifest generation, ADR amendment, Python deprecation first. Ship one proof: a minimal portable starter via template/copy script with one killer workflow and a retention test.

---

### CEO DUAL VOICES — CONSENSUS TABLE

```
═══════════════════════════════════════════════════════════════════════════════
  Dimension                           Claude          Codex           Consensus
  ──────────────────────────────────── ─────────────── ─────────────── ─────────
  1. Premises valid?                   NO (P2/P3/P5)   NO (P2/P3/P5)   CONFIRMED
  2. Right problem to solve?           NO (framing)    NO (10x reframe)CONFIRMED
  3. Scope calibration correct?        NO (too much+too little)        CONFIRMED
  4. Alternatives sufficiently explored? NO (template) NO (template)   CONFIRMED
  5. Competitive/market risks covered? NO (Claude-only) NO (moat wrong) CONFIRMED
  6. 6-month trajectory sound?         NO (lint warn)   NO (lint warn) CONFIRMED
═══════════════════════════════════════════════════════════════════════════════
CONFIRMED = both agree. 6 of 6 dimensions agree. Zero disagreements.
```

**This is an unusually strong consensus.** Independent models converged on the same thesis: the plan is infrastructure-first when it should be demand-validation-first. Both recommend shipping a GitHub template repo as Stage 0 before (or instead of) the npm CLI.

---

### USER CHALLENGE (requires human decision — never auto-decided)

**What you said:**
- Stage 1 = Claude version via `npx @rjmurillo/ai-agents init`
- TS + bun + npm publish
- Full `.claude/` vendor
- 3-day sprint
- Stages 2-4 follow in sequence

**What both models independently recommend:**
- **Stage 0 (new): GitHub template repo first.** `rjmurillo/ai-agents-starter`. Push a cleaned `.claude/` tree + generic `CLAUDE.md` + `AGENTS.md`. `gh repo create --template` or "Use this template" button is the onramp. Ships in hours, zero install, zero npm complexity.
- **Defer npm CLI until template adoption proves demand.** Measure stars, forks, issues. If >50 uses in 2 weeks, build the CLI. If <10, the CLI was the wrong problem.
- **Collapse Stage 1 + 2.** Ship Claude + Copilot instruction files in the SAME template repo simultaneously. Copilot's `.github/copilot-instructions.md` is a generated duplicate of `AGENTS.md`, cheap. Don't make runtime compatibility an axis.
- **Make bundle lint blocking, not warning.** Fix every repo-specific reference before publish. No known-broken shipping.

**Why (the models' reasoning):**
1. A CLI is packaging. Template repo is distribution. Distribution without packaging is cheaper and teaches you the same lesson.
2. Claude-only Stage 1 serves retention, not acquisition. Squad's audience is not Claude-native.
3. The real moat is the operating model (25 agents, 62 skills, session protocol, governance), not `npx`. Prove the moat before building the packaging.
4. Warning-only lint ships known bugs into users' first session. Onramp becomes offramp.

**What we might be missing:**
- Strategic timing. You may have reasons to prefer a CLI for brand/trust/legitimacy signal (npm install = "real tool").
- You may already have a rollout-to-team plan that depends on a CLI (teammates installing globally), which template repos don't serve.
- Your team may not use `gh repo create --template` (internal policy, different platform, enterprise constraints).
- The 3-day budget may be non-negotiable for a reason we do not see (internal deadline, external announcement, parallel work).
- Template repos do not show up in `npx` search results — npm presence matters for SEO.

**If we (the models) are wrong, the cost is:**
- You spend 3 days shipping a template repo that doesn't move the needle because the audience actually wanted `npx install`. Sunk cost: ~3 days + brand confusion.
- You ship a template repo that succeeds, then still need to build the CLI later. Sunk cost: duplicated onramp work. But you at least validated demand before building.

**Your original direction stands unless you explicitly change it.** The models must make the case for change, not the other way around.

---

### Premise confirmation gate

Per /autoplan Phase 1, premises require human judgment and are NEVER auto-decided. The 6 premises in this plan plus the CEO findings:

| # | Premise | Status after CEO review |
|---|---|---|
| P1 | Devs have Node installed; `npx` is one-step | Valid (uncontested) |
| P2 | Existing `.claude/` kit will work in fresh repos after light curation | **CHALLENGED — both models say this premise is shaky; lint must be blocking, not warning** |
| P3 | Claude Code is a valid first-target runtime; lose zero users | **CHALLENGED — both models say this is retention logic, not acquisition logic** |
| P4 | ADR-042 amendable to scope Python-first to internal automation | Valid (mechanical) |
| P5 | Full vendor is sufficient for first-session Squad-simple experience | **CHALLENGED — both models say full inherited opinion stack will feel alien, not simple** |
| P6 | `@rjmurillo/ai-agents` scope is acceptable | Valid (uncontested) |

---

**Phase 1 complete.** Phases 3 + 3.5 (Eng + DX) paused pending premise gate + user challenge resolution. Running Eng/DX now would review a plan whose strategic foundation is under fire. Wasted work.

---

### User challenge resolution (2026-04-12, Richard)

**Decision: A — stand firm.** Original direction holds.

**Sovereign context the models lacked:**

1. **Demand is already validated.** The `.claude/` kit has active adoption. Stars are low because of zero marketing, not low value. Star-counting as a demand signal is wrong here — acquisition is a Stage 4 marketing function, not a Stage 1 product function.
2. **Separate repo is a maintenance liability.** A `rjmurillo/ai-agents-starter` fork creates a sync problem: either the starter rots or every `.claude/` change triggers double work. Worse than shipping a CLI that vendors from the live source on each release.
3. **Single source of truth.** The CLI model lets `.claude/` stay the canonical live definition. Template repo splits truth across two repos. Harness-as-spec philosophy requires one source.
4. **"Something I KNOW works."** The repo itself is the proof. A template would be a stale snapshot of that proof.
5. **Claude-first = dogfood loop.** Richard uses Claude daily. Shipping to his own runtime gives the fastest feedback loop and the cheapest bug surface. Any regression hits him before it hits a user.
6. **Full vendor IS the value.** A curated starter would be a regression versus the existing `/install-plugin` path. If users want a slim start, that path already exists and stays preserved. The CLI's reason-to-exist is the full experience in one command.
7. **The "magic" is the product.** `npx ai-agents init` sells the same emotion that drew users to Squad: one command, working team, no thinking. Template repos and curated starters lose that emotion. The magic is non-negotiable because it's what converts.

**Implication for premises:**

| # | Before | After user challenge |
|---|---|---|
| P1 | Valid | Valid |
| **P2** | CHALLENGED | **Still shaky. User's evidence is "works in THIS repo, not a fresh one."** REQ-2.3 lint must be strengthened — see Phase 3 Eng review for specific fix. |
| **P3** | CHALLENGED | **RESOLVED.** User has in-house adoption proof. Claude-first is retention + expansion, not a pivot. Acquisition via marketing is Stage 4. |
| P4 | Valid | Valid |
| **P5** | CHALLENGED | **ACCEPTED BY DESIGN.** Full vendor is opinionated on purpose. Tourists can use alternatives. Believers get value fast. Tradeoff named explicitly. |
| P6 | Valid | Valid |

**Remaining technical risks from CEO phase (to address in Eng + DX):**
- REQ-2.3 lint is warning-only. Both models called this a ship-blocker. P2 depends on the lint being blocking OR on repo-specific references being fixed pre-publish. Eng phase must resolve.
- First-session experience with full vendor is untested in a truly-empty target repo. DX phase must define a smoke test that exercises the actual first-run from zero.

**Phase 1 → Phase 3 transition summary:**
> Phase 1 complete. Codex + Claude subagent both HIGH/CRITICAL on the CLI vs template-repo question. User challenge resolved in favor of original direction with explicit sovereign context. P3 resolved, P5 accepted by design, P2 carries forward to Eng review as a blocking technical risk. Proceeding to Phase 3.

---

## /autoplan Phase 3: Eng Dual Voices (2026-04-12)

### CLAUDE SUBAGENT (eng — independent technical review)

**R1 [CRITICAL] — Bundle deny-list missing.** Full `.claude/` tree is 71,248 files / 1.1GB. After excluding `worktrees/` and `skills/github/`: 18MB, 491 files. But the plan never lists `hooks/__pycache__`, `*.pyc`, `.skill_pattern_cache.json`, `scheduled_tasks.lock`, `settings.local.json`, `lib/**/__pycache__`, `.DS_Store` as explicit exclusions. These ship by accident through a naive walker. **Fix:** manifest builder uses deny-list regex enforced in tests.

**R2 [CRITICAL] — Hooks fail-closed in fresh repos.** `.claude/hooks/` is 404KB of Python. Imports `.claude/lib/hook_utilities/` and `.claude/lib/github_core/`. `.claude/settings.json` wires hooks by path. Fresh repos have no Python 3.14, no UV, no Serena MCP, no Forgetful. Every hook fails on first turn. Plan was silent on this. **Fix:** exclude `hooks/`, `lib/`, and `settings.json` from Stage 1 bundle. Ship `settings.json.sample` in Stage 1.1+ after preflight design.

**R3 [HIGH] — 32,922 files reference `.agents/`; 21,712 reference specific ADR numbers.** Virtually every command, agent, and skill cites `.agents/governance/*`, `.agents/SESSION-PROTOCOL.md`, `.agents/HANDOFF.md`, or specific ADR filenames. None exist in a fresh repo. First `/spec`, `/build`, `/review`, or agent invocation reads a broken path. Warning-only lint ships this knowingly. **Fix:** REQ-2.3 becomes blocking; REQ-2.5 cleanup pass rewrites or removes every flagged ref.

**Architecture [MEDIUM → CRITICAL if deferred]:** Define `BundleSource`, `TargetEmitter`, `Transform` interfaces in Stage 1 even with single implementations. Cost ~20 LOC. Without them, Stage 2 becomes a rewrite of `init.ts`.

**Test gaps [HIGH]:** Rollback on partial failure, symlinks, Windows path separators + CRLF in `CLAUDE.md` merge, Unicode filenames, `--dry-run`, idempotency with local user edits + `--force`, first-turn agent smoke.

**Bundle size:** 18MB, feasible for `npm pack`. Do not embed via `bun build --compile`. Ship assets as a directory referenced from `__dirname`.

**Security [CRITICAL]:** Hooks are an A06 supply chain vector. Every consumer executes vendored Python on every turn. Excluding hooks removes this surface. Enable `npm publish --provenance`. Publish from CI only.

### CODEX SAYS (eng — architecture challenge)

**[CRITICAL] Blocking bundle-lint rules** (8 regex rules; listed in REQ-2.3 above).

**[CRITICAL] Stage 1 needs one extension point now or Stage 2 rewrites the CLI.** Lock in `BundleSource → Transform[] → Emitter`. Do not bake "copy manifest to disk" into the command. Stage 2 Copilot is not another flag; it is a different emitter plus target-specific transforms. If Stage 1 writes files directly from manifest entries, you rip it apart in two weeks.

**[CRITICAL] What breaks in the first 100 installs:**
- Hooks firing against missing `.agents/` and `.serena/`
- Commands instructing users to write files into nonexistent governance trees
- Session-end and merge tools failing on absent session/memory scaffolding
- Windows users hitting path and Python assumptions
- Users rerunning `init` into non-empty repos and tripping false divergence
- Consumers assuming "Node-only" while the vendored runtime requires Python

**[HIGH] Test plan gaps:** (same list as Claude subagent, independently derived)

**[HIGH] npm publish mechanics the plan under-specifies:**
- Scoped package name `@rjmurillo/ai-agents` with bin alias `ai-agents`
- `npm publish --provenance --access public`
- Bun-built JS must target Node LTS, not Bun runtime APIs
- `files` allowlist in `package.json` or tarball is wrong
- No `package.json`, `tsconfig.json`, or `bunfig.toml` exists yet — this is greenfield
- CI validates install via `npm pack` + `npx --yes ./tarball init`, not source checkout
- Auth failure path + 2FA/provenance permissions need explicit release docs

---

### ENG DUAL VOICES — CONSENSUS TABLE

```
═══════════════════════════════════════════════════════════════════════════════
  Dimension                           Claude          Codex           Consensus
  ──────────────────────────────────── ─────────────── ─────────────── ─────────
  1. Architecture sound?               NO (need ifaces) NO (Src→Xform→Em) CONFIRMED
  2. Test coverage sufficient?         NO (gaps listed) NO (gaps listed)  CONFIRMED
  3. Performance risks addressed?      N/A (size OK)    N/A (size OK)     N/A
  4. Security threats covered?         NO (hooks A06)   NO (hooks fire)   CONFIRMED
  5. Error paths handled?              NO (rollback)    NO (rollback)     CONFIRMED
  6. Deployment risk manageable?       NO (np under-spec) NO (np under-spec) CONFIRMED
═══════════════════════════════════════════════════════════════════════════════
CONFIRMED = both agree. 5 of 5 actionable dimensions agree. Zero disagreements.
```

**Consensus: agree with Phase 1 finding on blocking lint; additionally identify hook/lib/settings exclusion as independent critical fix that neither Phase 1 nor the original plan caught.**

### Eng phase resolution (applied to plan 2026-04-12)

1. **Excluded hooks/lib/settings.json** from Stage 1 bundle (REQ-2 revised)
2. **Made REQ-2.3 lint blocking** with 8 specific regex rules
3. **Added REQ-2.5 cleanup pass** — rewrites or removes flagged `.agents/` and ADR references in vendored content
4. **Added REQ-1.7 interfaces** — `BundleSource`, `TargetEmitter`, `Transform` declared now even with single implementations
5. **Added REQ-4.3–4.5 test matrix** — Node 20/22 × 3 OS, first-turn smoke via `claude --non-interactive`, edge-case fixtures
6. **npm publish specs folded into REQ-3** (provenance, allowlist, pack+npx validation) — see REQ-3.4 below

### Day estimate — REVISED after Eng phase

The cleanup pass (REQ-2.5) is the dominant cost. Every command, agent, and most skills need lint-clean rewrites. Estimate:

| Task | Days |
|---|---|
| ADR-042 amendment | 0.5 |
| TS+bun scaffold + interfaces | 0.5 |
| Bundle manifest builder + deny-list + lint | 0.5 |
| **REQ-2.5 cleanup pass (commands + agents + skills)** | **1.5–2** |
| `init` command + `CLAUDE.md` merge + `AGENTS.md` stub | 0.5 |
| Edge-case tests (REQ-4.5) | 0.5 |
| CI smoke matrix + first-turn verification | 0.5 |
| npm publish flow + provenance | 0.5 |
| Security + DevOps review gates | 0.5 |
| **Total wall-clock** | **~5 days** |

Original 3-day estimate was optimistic. Cleanup pass scope was unknown until Eng review grepped the tree and found 32k+ files with `.agents/` refs. 5 days is still compressed vs 4-week ENG-REVIEW-ai-agents-platform.md estimate for the full 8-command CLI.

**PHASE 3 COMPLETE.** Emit phase-transition summary:
> Phase 3 complete. 5 critical/high consensus findings, all agreed by both voices. All 5 applied to plan file as REQ updates. Day estimate revised 3→5 due to discovered cleanup-pass scope. Proceeding to Phase 3.5 (DX).

---

## /autoplan Phase 3.5: DX Dual Voices (2026-04-12)

### CLAUDE SUBAGENT (DX — independent review)

**[CRITICAL] "First value" moment missing.** REQ-1.5's `/spec hello world` next-step is an abstraction cliff. Devs don't know what `/spec` does. The cliff is step 6 of the journey — ran init, see hundreds of files, no clear next action. This is where 40% close the tab. **Fix:** Add `ai-agents list` subcommand (40 LOC, second verb) that prints colored agent roster + command catalog. Add post-init printout of "first 5 things to try" with real examples (`/review`, `/analyze <file>`, `/session-init`), not harness vocabulary.

**[CRITICAL] Error messages are a wish, not a spec.** "Exit 2 with clear message" is not testable. Every error must satisfy: **what** happened + **why** (cause) + **fix** (exact command) + **docs** (stable URL). Enforce via `errfmt.ts` + test suite. Example:
```
error: .claude/ exists and diverges from ai-agents snapshot
  cause: 3 files modified locally (.claude/skills/analyze/SKILL.md, ...)
  fix:   re-run with --force to overwrite, or --dry-run to preview
  docs:  https://github.com/rjmurillo/ai-agents#idempotency
```

**[HIGH] Missing flags.** Plan ships `init [path] --force --dry-run`. Devs also expect: `--help`, `--version`, `--list`, `--yes`, `--no-claude-md`, `--only <commands|agents|skills>`. `--dry-run` currently lives in REQ-4.5 (tests only); promote to REQ-1 as a user-facing flag.

**[HIGH] No interactive confirm.** Writing 14MB into a user's repo without `[Y/n]` confirmation is hostile. Add confirmation unless `--yes` passed.

**[CRITICAL] Upgrade path is absent.** Vendored tree + refuse-on-divergence + no `upgrade`/`status`/`doctor` = stasis. Every upgrade trips `--force`. Users fork + never update. **Fix:** write version + manifest hash to `.claude/.ai-agents-version.json` at init time. State deprecation policy in README. Defer actual `upgrade` subcommand to v0.2 but LOCK the version-pin now.

**[HIGH] No escape hatches.** P5 says "strong opinions are a feature." That's a choice. But zero subsetting for a "lazy wrapper" is user-hostile. **Fix (minimum viable):** `--only <commands|agents|skills>` flag. Ship in Stage 1. Cost trivial — manifest already exists.

**[HIGH] vs Squad:** Worse on discoverability of value, single-verb payoff, "show me it work" moment. Squad has `init` + `chat`. ai-agents has only `init`. **Fix:** `ai-agents list` is the second verb. No chat needed (per user).

**[HIGH] README incomplete.** REQ-6 moves "Fastest Start" to top but the copy-paste path is not fully spelled out. Need literal 3-line block + 30-second gif/screencast + "what you get" table (commands, agents, skills with 1-line each) + troubleshooting + uninstall.

**DX SCORECARD:**
| Dimension | Score |
|---|---|
| Getting started (<5 min) | 6 |
| CLI naming | 6 |
| Error messages | 3 |
| Docs findability | 5 |
| Upgrade path | 2 |
| Dev environment friction | 8 |
| Escape hatches | 3 |
| Competitive DX vs Squad | 5 |

**Weighted overall: 4.8/10.** "Engineering-solid, DX-thin. Ships a file copier and calls it a product."

**TTHW:** Floor ~60s (Claude Code already running, dev knows /spec). Ceiling ~15min (Go engineer, fresh install), 40% bounce at step 6.

**3-fix delta to 7+/10 without scope creep:**
1. Add `ai-agents list` + `ai-agents demo` (two verbs, not one)
2. Specify error format + `--dry-run` promoted + `--yes` + post-init "first 5 things" printout
3. Version pin file + deprecation policy in README

---

### CODEX SAYS (DX — developer experience challenge)

**[HIGH] Zero to working session.** Best case is 3 steps, not 1: `npx`, open Claude Code, run `/spec`. Plausibly under 5 minutes if Node + Claude Code already exist. Worst case worse than pitch — plan assumes both without a preflight. No `doctor`, no runtime check for Claude Code presence, no guardrail for "scaffolded files but tool won't use them."

**[HIGH] Failure handling.** Better than average for file safety (divergence detection, exit 2, `--force`, atomic rename, idempotent `CLAUDE.md` markers). Weak for user recovery. No error taxonomy, no human-first remediation output, `doctor`/`status` explicitly out of scope. Trial user hitting bundle lint or merge edge case gets a correct failure and still bounces.

**[MEDIUM] API/CLI design.** `init [path]` + `--force` guessable. Defaults sensible. Missing flags matter more than included: `--dry-run`, `--minimal`, `--commands-only`, `--yes`. `--dry-run` is currently a test gap, not a user flag. Risky for "lazy wrapper" positioning because the product behaves like a framework install.

**[HIGH] README quickstart.** Moving "Fastest Start" to top is right but incomplete. Needs literal 3-line block:
```
npx @rjmurillo/ai-agents init
cd <repo>
Open in Claude Code, run /spec
```
Without this, drops users into harness vocabulary and misses the 30-min trial.

**[CRITICAL] Upgrade path.** Not good enough. Plan explicitly punts `upgrade`, `status`, `doctor`, `export`, `import`. For a vendored tree, **upgrade fear is the core product problem.** "Refuse on divergence unless `--force`" protects files but creates stasis. Devs will fork the vendored tree and never upgrade. Silent death. **Fix:** at minimum, write version + manifest hash to disk at init so future `upgrade` commands have an anchor.

**[HIGH] vs Squad.** Keep iterating before shipping as the main bet.
- Better than Squad: stronger safety around overwrite/idempotency, clearer Claude-first focus, more opinionated "working team" out of the box.
- Worse than Squad: heavier conceptual payload, weaker escape hatches, no trust-building maintenance commands. Squad feels npm-native; this still feels like repo internals being copied into your project with a lot of faith required.

**[CRITICAL] Escape hatches.** Bad. Plan explicitly rejects tiers and ships full bundle only. For a competitive trial, wrong trade. Need at least one thin mode: commands only, or commands + orchestrator, or no skills/hooks. Right now the answer to "I just want commands" is effectively "use something else."

**Verdict:** Strong internal implementation plan, weak product onramp. Ship only if framed as alpha for believers. If goal is beating `squad init` in a 30-min evaluation, keep iterating until upgrade and minimal-mode exist.

---

### DX DUAL VOICES — CONSENSUS TABLE

```
═══════════════════════════════════════════════════════════════════════════════
  Dimension                           Claude          Codex           Consensus
  ──────────────────────────────────── ─────────────── ─────────────── ─────────
  1. Getting started < 5 min?          PARTIAL (6/10)  PARTIAL (3 step) CONFIRMED
  2. API/CLI naming guessable?         PARTIAL (missing flags) PARTIAL  CONFIRMED
  3. Error messages actionable?        NO (3/10)       NO (no taxonomy) CONFIRMED
  4. Docs findable & complete?         NO (5/10)       NO (quickstart)  CONFIRMED
  5. Upgrade path safe?                NO (2/10)       NO (stasis)      CONFIRMED
  6. Dev environment friction-free?    OK (8/10)       N/A             N/A
  7. Escape hatches?                   NO (3/10)       NO (bad)        CONFIRMED
  8. Competitive DX vs Squad?          LOSING (5/10)   LOSING (iterate) CONFIRMED
═══════════════════════════════════════════════════════════════════════════════
CONFIRMED = both agree. 7 of 7 actionable dimensions agree. Zero disagreements.
```

**Weighted DX overall: 4.8/10 (Claude) — Codex concurs with "weak product onramp, strong internals."**

### DX phase resolution — TASTE DECISIONS + USER CHALLENGES

Unlike CEO and Eng phases where fixes were mechanical, DX phase surfaces **real product-shape questions** that the user must decide:

**USER CHALLENGE DX-1: Add `ai-agents list` subcommand (second verb).**
- **What you said:** Single command `init`.
- **Both models recommend:** Add `list` (or `demo`). Second verb, 40 LOC, gives devs a zero-risk exploration path + a "show me it work" moment that matches Squad's `chat` without requiring chat.
- **Why:** Without a second verb, the first-value moment lives in Claude Code, which devs may not have open. `list` keeps the moment in the CLI.
- **Cost if models are wrong:** 40 LOC of dead code. Trivial.
- **Cost if you're right to reject:** DX stays at 4.8/10, 30-min trials bounce at step 6.
- **Default stands:** Your single-verb direction holds unless you explicitly accept.

**USER CHALLENGE DX-2: Add `--only <commands|agents|skills>` escape hatch.**
- **What you said:** Q9 = "full scope, full stop." No curation.
- **Both models recommend:** Add `--only` flag. Default stays "full scope" (your Q9 stance preserved). Flag is opt-in for devs who want commands-only or similar thin modes.
- **Why:** "Lazy wrapper" framing conflicts with framework-install behavior. For devs who already have their own agents and just want commands, zero subsetting = tool is unusable for them. Cost is low; manifest already exists.
- **Cost if models are wrong:** Flag exists, nobody uses it. Negligible.
- **Cost if you're right to reject:** Tool competes for an audience that wants ALL of it, loses the audience that wants a slice.
- **Default stands:** Full-scope-only direction holds unless you explicitly accept.

**USER CHALLENGE DX-3: Lock version pin at init time.**
- **What you said:** Defer `upgrade`/`doctor`/`status` to v0.2.
- **Both models recommend:** Even without an `upgrade` subcommand, write `.claude/.ai-agents-version.json` at init time. Records package version + manifest hash. Gives future `upgrade` a safe anchor, lets `init --force` compute a diff on upgrade.
- **Why:** Without version pin, upgrade becomes stasis. Devs fork and never update. This is an architectural seam — once you ship without it, adding it later means all existing users have no anchor.
- **Cost if models are wrong:** One JSON file per install. Trivial.
- **Cost if you're right to reject:** Silent user death on upgrade; forking instead of upgrading.
- **Default stands:** Defer stance holds unless you explicitly accept.

**MECHANICAL (auto-decided by /autoplan 6 principles):**
- Error format specification (REQ-1.8 new): errfmt.ts + test-enforced. P1 completeness.
- `--help`, `--version`, `--dry-run` (promoted), interactive `[Y/n]` confirm unless `--yes`: all standard CLI affordances. P1 + P3.
- README literal 3-line block + "what you get" table + troubleshooting: P5 explicit over clever.
- Post-init "first 5 things to try" printout replacing vague `/spec hello world`: P1.

**PHASE 3.5 COMPLETE.**
> Phase 3.5 complete. DX overall 4.8/10 (Claude) / "weak onramp" (Codex). 3 USER CHALLENGES surfaced (list subcommand, --only flag, version pin). Mechanical DX fixes auto-applied via new REQs below. Proceeding to Phase 4 (Final Gate).

---

### REQs added by Phase 3.5 (mechanical auto-decisions)

- **REQ-1.8 (NEW):** Error format `errfmt.ts` emits every error as: `error:` line + `cause:` + `fix:` + `docs:`. Test-enforced on all error paths. **Pass/fail:** unit tests assert format on every thrown error.
- **REQ-1.9 (NEW):** Promote `--dry-run` from test-only (REQ-4.5) to user-facing flag in REQ-1. Lists files that would be written/modified, exits 0 without touching disk.
- **REQ-1.10 (NEW):** `--help` and `--version` flags. Standard Unix conventions. `--help` shows command + flags + 3-line example + docs URL.
- **REQ-1.11 (NEW):** Interactive `[Y/n]` confirmation before writing to a non-empty target dir. `--yes` skips. TTY detection: non-TTY invocations assume `--yes`.
- **REQ-1.12 (NEW):** Post-init output replaces the current one-line next-step. New format:
  ```
  ✓ Vendored N commands, M agents, K skills into <target>
  
  Try one of these:
    /review <file>        # Code review
    /analyze <pattern>    # Investigation
    /spec <feature>       # New feature spec
    /build                # Implementation
    /ship                 # PR + deploy

  Docs: https://github.com/rjmurillo/ai-agents#getting-started
  ```
- **REQ-6.4 (NEW):** README "Fastest Start" block is exactly 3 lines of copy-paste code + 1 line pre + 1 line post. Plus a "What you get" table listing vendored counts + top 5 commands + top 5 agents + top 5 skills with 1-line descriptions each. Plus a Troubleshooting section with 3 known issues (Claude Code not installed, path conflicts, existing `.claude/`).
- **REQ-6.5 (NEW):** README top includes a 30-second gif or screencast URL (placeholder OK for v0.1; record before v0.2).

---

## /autoplan Phase 3.5b: Squad Competitive Analysis (2026-04-12)

Data pulled from github.com/bradygaster/squad + npm/@bradygaster/squad-cli v0.9.1 via analyst subagent.

### Squad momentum (2026-04-13)
- 1,968 stars, 269 forks, 45 open issues
- Created 2026-02-06 (2 months old) → ~1,000 stars/month
- 100+ commits in 90 days, actively developed
- Brady Gaster, MSFT Principal Program Manager → built-in DevRel reach
- npm: `@bradygaster/squad-cli` v0.9.1, Node >=22.5.0

### Squad CLI command count: **17** (not 3-4)

`squad init`, `upgrade`, `upgrade --self`, `status`, `triage`, `copilot`, `doctor`, `link`, `externalize`, `internalize`, `shell` (deprecated), `export`, `import`, `plugin marketplace`, `upstream`, `nap`, `aspire`, `scrub-emails`. All visible in the README with documented flags and behaviors.

### Squad quickstart (verbatim, 4 steps with checkpoints)
1. `mkdir my-project && cd my-project && git init` → validate `git status` shows "No commits yet"
2. `npm install -g @bradygaster/squad-cli && squad init` → validate `.squad/team.md` created
3. `gh auth login`
4. `copilot --agent squad --yolo` OR VS Code Copilot Chat → select Squad agent

### Squad's moat-candidate features we lack
- **Committed per-agent memory.** `.squad/agents/{name}/history.md` is in the repo. Clone it, get the team's knowledge. Ours lives in Serena (local graph, not vendored by init).
- **Copilot-native.** Native GitHub Copilot CLI extension. 21 `.copilot/skills/` shipped. We are Claude-only in Stage 1.
- **Dynamic casting model.** Agents are drawn from themed universes (Futurama.json casting found). User-defined count per repo. We ship 24 fixed roles.
- **Context hygiene (`squad nap`).** Compress/prune/archive old context. No equivalent in Stage 1.
- **Upgrade commands.** `squad upgrade` (files) and `squad upgrade --self` (CLI). Clean separation, preserves state. We defer upgrade to v0.2.
- **Observable runtime (`squad aspire`).** Dashboard integration. Stage 2+ or ignore.

### Competitive matrix (top findings)

| Dimension | Squad | us (Stage 1) | Winner | Gap |
|---|---|---|---|---|
| Install | `npm i -g && squad init` (2) | `npx ...init` (1) | us | LOW |
| Runtime | Copilot CLI + VS Code native | Claude Code only | **Squad** | **CRITICAL** |
| Agent memory portability | Committed history.md per agent | Serena local graph, not vendored | **Squad** | **HIGH** |
| CLI command count | 17 | 1 | Squad | HIGH |
| Upgrade command | `squad upgrade` + `--self` | None (deferred) | Squad | HIGH |
| CI/CD workflows on init | Creates `.github/` workflows | None | Squad | HIGH |
| Onboarding narrative | 4-step with validate checkpoints | 1 cold next-step line | Squad | HIGH |
| Skill catalog | 21 Copilot-native skills | 62 Claude skills (many repo-coupled) | Depends | MEDIUM |
| **Session protocol rigor** | **None** | SESSION-PROTOCOL.md, gates, validation | **us** | **HIGH** |
| **Governance (ADRs, constraints, reviews)** | **None** | **57 ADRs + review gates** | **us** | **HIGH — PR-grade moat** |
| Visibility / stars | 1,968 | 0 public | Squad | CRITICAL (marketing) |
| Security audit | PII scrub + hook guards | Lint + security-detection skill | Tie | LOW |

### Strategic positioning (from competitive data)

**Squad's audience:** Individual devs + small teams who want a fast, fun, opinionated AI team. Copilot-native, Microsoft brand, casting-character UX. "Get going in 4 steps."

**Our audience (differentiated):** Platform teams, engineering managers, organizations with compliance/audit/governance requirements. 57 ADRs, session protocol, review gates, security scans. Squad cannot copy this without building years of accumulated decisions. **This is a different buyer, not the same one we're losing on Copilot.**

**The moat is governance depth, not runtime.** Brady Gaster is optimizing for "get a team fast." We can own "run your AI team like a real engineering org." Different buyer = not a zero-sum competition. Stage 1 still ships to the Claude-Code-native slice; Stage 2 adds Copilot; Stage 4 marketing pitches governance-first to platform teams.

### Where Squad beats us in Stage 1 (closeable vs not)

| Gap | Severity | Closeable in Stage 1? |
|---|---|---|
| Copilot runtime | CRITICAL | NO — Stage 2 |
| Visibility / stars | CRITICAL | NO — Stage 4 marketing |
| Committed per-agent memory | HIGH | PARTIAL — ship `MEMORY.md` stub + `.agents/knowledge/` placeholder in bundle |
| Upgrade command | HIGH | YES — 1 day to add `update` subcommand (thin wrapper around re-init + `--force`) |
| CI workflow generation | HIGH | DEFER — v0.2 |
| Onboarding narrative | HIGH | YES — 0.5 day to write `GETTING-STARTED.md` stub + rewrite post-init output |
| Context hygiene (`nap`) | MEDIUM | DEFER — v0.2 |

### Analyst's recommendation (adopted into plan)

**Ship Stage 1 as planned PLUS 2 additions:**

1. **`ai-agents update` subcommand.** Thin wrapper: recomputes manifest hash vs current `.claude/`, diffs, prompts, re-runs init with `--force` on accept. Closes the upgrade gap in 1 day. This matches Squad's `upgrade` semantics.
2. **`GETTING-STARTED.md` bundled in init + printed post-init guide.** Stops the "cold next-step" problem flagged by DX voices + confirmed by Squad comparison. 0.5 day.

**Do not pivot.** Beachhead is correct (Claude Code users with no kit). Core mechanics sound. Gap is real but closeable at the margin.

### Plan REQ additions from competitive analysis

- **REQ-1.13 (NEW):** `ai-agents update` subcommand. Reads `.claude/.ai-agents-version.json`, computes manifest diff, prompts user with diff summary, runs `init --force` on accept. Rejects if no version file exists (user must run `init` first). **Pass/fail:** unit + e2e tests.
- **REQ-1.14 (NEW):** Writes `.claude/.ai-agents-version.json` at init time containing: `version` (package semver), `manifestHash` (sha256 of bundle manifest), `installedAt` (ISO timestamp), `source` (`"npx"` | `"global"`). **Pass/fail:** file exists post-init, schema valid.
- **REQ-1.15 (NEW):** Bundle includes `GETTING-STARTED.md` at the root of the vendored tree. Content: 1-page guide with "What you just got", "First 5 things to try", "If something looks broken", "Where to ask for help". **Pass/fail:** file copied to target; content ≤ 1 page.

### Positioning update to REQ-6.1

- **REQ-6.6 (NEW):** README Fastest Start section includes positioning 1-liner: *"For platform teams, engineering managers, and orgs that want AI-assisted development with real governance. 57 ADRs, session protocol, review gates built in."* **Pass/fail:** README grep.

---

## /autoplan Phase 4: Final Gate — APPROVED (2026-04-12)

**Status:** APPROVED by Richard Murillo, all 3 taste decisions accepted.

### Taste decisions resolved

| # | Decision | User's call | REQ |
|---|---|---|---|
| DX-1 | `ai-agents list` subcommand (second verb) | **ACCEPTED** | REQ-1.16 below |
| DX-2 | `--only <commands\|agents\|skills>` escape hatch | **ACCEPTED** | REQ-1.17 below |
| DX-3 | `ai-agents update` subcommand | **ACCEPTED** | REQ-1.13 (already in plan) |

### REQs added by final gate approval

- **REQ-1.16 (NEW):** `ai-agents list` subcommand. Prints colored catalog: vendored commands (name + 1-line), agents (name + role), skills (name + trigger). Optional filters: `list commands`, `list agents`, `list skills`. Read from manifest; no network. **Pass/fail:** unit tests; snapshot output.
- **REQ-1.17 (NEW):** `--only <commands|agents|skills>` flag on `init`. Default behavior unchanged (full scope per Q9). Flag is opt-in subset. Accepts comma-separated values: `--only commands,agents`. Manifest walker filters by top-level directory. **Pass/fail:** unit tests for each combination; full-scope default unaffected.

### Final REQ count

| Section | Count | Range |
|---|---|---|
| REQ-1 (init + adapters + DX affordances) | 17 | REQ-1.1 through REQ-1.17 |
| REQ-2 (bundle manifest + lint + cleanup) | 5 | REQ-2.1 through REQ-2.5 |
| REQ-3 (npm publish) | 4 | REQ-3.1 through REQ-3.4 |
| REQ-4 (CI smoke tests) | 5 | REQ-4.1 through REQ-4.5 |
| REQ-5 (Python deprecation) | 3 | REQ-5.1 through REQ-5.3 |
| REQ-6 (docs positioning) | 6 | REQ-6.1 through REQ-6.6 |
| REQ-7 (review gates) | 3 | REQ-7.1 through REQ-7.3 |
| **Total** | **43** | |

### Day estimate — final

Previous: 5 days (post-Eng phase).
Plus taste decisions:
- REQ-1.16 `list` subcommand: +0.5 day
- REQ-1.17 `--only` flag: +0.25 day
- Integration tests for both: +0.25 day

**Final wall-clock: ~6 days.** Still 4x compressed vs 4-week ENG-REVIEW-ai-agents-platform.md estimate.

### Review logs to write on approval

- plan-ceo-review: clean (user challenge resolved)
- plan-eng-review: clean (all findings applied)
- plan-devex-review: clean (mechanical + taste fixes applied)
- autoplan-voices-ceo: codex+subagent, 6/6 confirmed
- autoplan-voices-eng: codex+subagent, 5/5 confirmed
- autoplan-voices-dx: codex+subagent, 7/7 confirmed

### Next action

`/plan` or `/build`. Given the 6-day budget and approved spec, recommend going directly to `/build` and decomposing the 43 REQs into atomic commits. The `/plan` skill would add decomposition and sequencing structure if you want a build order before implementation starts.

**Plan status: APPROVED — ready to implement.**
