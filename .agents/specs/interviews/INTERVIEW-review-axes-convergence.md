# Interview: review-axes convergence (issue #1934, child of epic #1933)

Date: 2026-05-10
Driver: requirements-interview skill (auto-invoked from `/spec`)
Author: rjmurillo

## Restated problem (one sentence)

Establish `.claude/review-axes/{role}.md` as the single canonical source for PR-quality review prompts so `/review` (local, primary, strict superset) and CI (backstop) evaluate byte-identical criteria, with drift detection at pre-push and CI; verdict-merge logic moves to a Python module per ADR-042.

CONFIRMED by author (Step 1 clarifications, 2026-05-10).

## Step 0 First Principles (carried verbatim)

- Q1 Demand Reality: Richard (author), observations, AI agent Hermes
- Q2 Status Quo: burn tokens, frustrated looping (2 fix-loops + 5 commits on PR feat/skill-eval-triage)
- Q3 Desperate Specificity: sludge slowing all PRs; Richard babysits, can't delegate
- Q4 Narrowest Wedge: pre-decomposed from epic #1933; M (1-2 days) per issue body
- Q5 Observation: `~/.claude` past sessions; PR feat/skill-eval-triage; retro `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- Q6 Future-fit: yes (system grows -> divergence grows -> convergence still wins)

## Codebase facts established by grep (no user time spent)

| Fact | Evidence | Status |
|------|----------|--------|
| `AIReviewCommon.psm1` removed | `git log` commit `3f3326f9` (PR #1066/#1169, Pester retirement) | CONFIRMED missing |
| Verdict merge prose lives in `/pr-quality:all` | `.claude/commands/pr-quality/all.md` cites `Merge-Verdicts`, `Get-VerdictEmoji` | CONFIRMED stale citation |
| CI workflow runs **6** axes | `.github/workflows/ai-pr-quality-gate.yml` lists `pr-quality-gate-{security,qa,analyst,architect,devops,roadmap}.md` | CONFIRMED, NOT 7 |
| `session-protocol-check.md` is orphaned | `.github/prompts/session-protocol-check.md` referenced only in archived/worktree files | CONFIRMED out-of-band |
| `/review` runs 5 axes (architecture, security, code-quality, qa, standards) | `.claude/commands/review.md` (84 lines) | CONFIRMED |
| `/review`-only extras are skills, not prompts | `.claude/skills/{code-qualities-assessment,golden-principles,taste-lints}/` exist | CONFIRMED |
| `pr-quality.{role}.prompt.md` are template wrappers | Use `{{file ".github/prompts/pr-quality-gate-X.md"}}` include syntax | CONFIRMED, not separate criteria |
| Pre-push hook is bash (grandfathered) | `.githooks/pre-push` 36KB, comment cites ADR-005 exception | CONFIRMED, drift check fits here |
| Build-script generator pattern | `build/scripts/generate_{commands,hooks,rules,skills}.py` | CONFIRMED, follow this pattern |
| `plugin.json` has no file enumeration | `.claude/.claude-plugin/plugin.json` 4 fields (name, description, version, author) | CONFIRMED, ship-by-convention |

## Decisions resolved with author (Step 1 + interview)

| # | Question | Recommended | Author verdict |
|---|----------|-------------|----------------|
| D1 | Verdict merge precedence with extras | Equal weight; any CRITICAL_FAIL blocks (across 9 axes total: 6 canonical + 3 skill extras) | CONFIRMED |
| D2 | Drift hook location | Pre-push + CI workflow (belt-and-suspenders) | CONFIRMED |
| D3 | Vendored discovery path | Hardcoded relative `.claude/review-axes/` | CONFIRMED |
| D4 | /review-only axes treatment | Move to `.claude/review-axes/` directory? Refined to: keep skills as skills, /review chains them after canonical axes | OVERRIDDEN (author chose chained skills) |
| D5 | Verdict-merge module home | `.claude/lib/ai_review_common.py` (Python per ADR-042) with `merge_verdicts(verdicts) -> str`, `get_verdict_emoji(verdict) -> str` | CONFIRMED |
| D6 | Axis count | 6 axes matching current CI (analyst, architect, qa, security, devops, roadmap). Drop session-protocol from issue's 7-claim. Update issue body and epic to match. | CONFIRMED |
| D7 | Extras invocation in /review | Keep as skills; /review chains `Skill(skill="...")` after canonical 6 axes. Verdict merge unifies all 9 results. | CONFIRMED |
| D8 | Plugin manifest | `.claude/review-axes/` ships under existing `.claude/` convention. Verify in design. | CONFIRMED |

## Open questions (deferred to design step)

| OQ | Question | Owner | Trigger |
|----|----------|-------|---------|
| OQ1 | Does plugin.json need explicit `files:` enumeration to ship `.claude/review-axes/`? | architect agent in /plan | Read full plugin.json; check `build/scripts/validate_plugin_manifests.py`. If implicit ship works, no change. |
| OQ2 | Should the build script also update `.claude/commands/pr-quality/all.md` (the orchestrator that cites stale `AIReviewCommon.psm1`)? | implementer | After D5 lands, the prose in all.md must cite `ai_review_common.py`. Either build script regenerates orchestrator prose or manual update is part of this PR. |
| OQ3 | What schema fields are MUST vs SHOULD for canonical axis files? | spec-generator | Frontmatter: `name`, `role`, `version`, `description`. Body: Grounding rules, Focus areas, Output schema. AC1 says "structured-finding output schema (severity, category, location, recommendation, verdict)". |
| OQ4 | Is the issue body itself updated as part of this PR? Issue says 7 axes, .github/prompts/, AIReviewCommon. | implementer + PR author | Spec-coverage gate compares PR description / linked issue text. Per memory `feedback_pr_description_is_spec_input`, drift causes CI fail. Update issue body via gh CLI as part of PR. |

---

## Structured PRD (handed to /spec downstream steps)

### Problem

PR review prompts exist in two parallel families that drift independently. CI runs `.github/prompts/pr-quality-gate-{role}.md` (6 axes); `/review` runs inline 5-axis prose in `.claude/commands/review.md`. On PR `feat/skill-eval-triage` (M1 skill prune), `/review` returned PASS while `/pr-quality:all` returned BLOCKED. Two recursive fix-loops + 5 commits + 4 Round-2 regressions to reconcile (iteration paradox per `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`). Without a single canonical source, every CI prompt evolution drifts from `/review` and every `/review` improvement bypasses CI.

### User stories

- US1. As Richard (PR author), when I run `/review` locally, I see the same findings CI will surface, so I do not push, wait for CI, and round-trip on issues `/review` could have caught.
- US2. As Hermes (delegated agent finishing a PR), when I run `/review`, I get the strict-superset of CI's evaluation, so my output is reliable enough that Richard does not need to babysit.
- US3. As a downstream installer of the `project-toolkit` plugin (vendored install, no `.agents/` or `.github/`), when I run `/review`, the command works because all canonical inputs ship under `.claude/`.
- US4. As a maintainer editing review criteria, when I update `.claude/review-axes/{role}.md`, the build script regenerates `.github/prompts/pr-quality-gate-{role}.md`, the pre-push hook + CI drift check enforce parity, and `/review` picks up the change automatically.

### Data model

- **Canonical axis file**: `.claude/review-axes/{role}.md` for `role in {analyst, architect, qa, security, devops, roadmap}`. Frontmatter: `name`, `role`, `version`, `description`. Body sections: Title, Grounding Rules, Analysis Focus Areas, Output Schema. Identity: `role`. Lifecycle: edited by maintainers; build script reads on every regen.
- **Generated CI prompt**: `.github/prompts/pr-quality-gate-{role}.md`. Identity: `role`. Lifecycle: regenerated from canonical; never hand-edited; drift hook + CI check enforce.
- **Verdict merge module**: `.claude/lib/ai_review_common.py`. Functions: `merge_verdicts(verdicts: Sequence[str]) -> str`, `get_verdict_emoji(verdict: str) -> str`. Verdict tokens: `PASS`, `WARN`, `CRITICAL_FAIL`, `REJECTED`, `FAIL`, `UNKNOWN`. Merge rules: any CRITICAL_FAIL/REJECTED/FAIL -> CRITICAL_FAIL; any WARN (no critical) -> WARN; all PASS -> PASS.
- **Drift state**: ephemeral comparison between `.claude/review-axes/{role}.md` (after generator transform) and `.github/prompts/pr-quality-gate-{role}.md`. No persistent state; computed on demand.
- **/review extras**: 3 skills under `.claude/skills/{code-qualities-assessment,golden-principles,taste-lints}/`. Identity: skill name. Lifecycle: independent of this PR. Invoked via `Skill(skill="...")` in `/review` after canonical axes.

### Integrations

- **GitHub Actions** (`ai-pr-quality-gate.yml`): consumes `.github/prompts/pr-quality-gate-{role}.md` via `prompt-file:` parameter to GitHub Copilot CLI. Failure mode: stale prompt -> CI evaluates wrong criteria. Idempotency: workflow re-runs deterministically on each push.
- **`.githooks/pre-push`**: bash hook, grandfathered exception per ADR-005. Add a drift-detection step that invokes the build script in dry-run mode and diffs against `.github/prompts/`. Failure mode: hook bypassed (`git push --no-verify`); CI catches in backstop. Idempotency: pure read; no state mutation.
- **`/review` command** (`.claude/commands/review.md`): rewritten to read `.claude/review-axes/{role}.md` for the 6 canonical axes, then invoke `Skill(skill=...)` for the 3 extras. Calls `merge_verdicts` from `.claude/lib/ai_review_common.py`. Failure mode: missing canonical file -> verdict UNKNOWN, command fails fast with explicit error. Idempotency: pure analysis; safe to re-run.
- **`/pr-quality:all`** (`.claude/commands/pr-quality/all.md`): existing orchestrator. Stale prose cites `AIReviewCommon.psm1`. Update to cite `ai_review_common.py` as part of this PR (resolves OQ2).
- **`build/scripts/generate_pr_quality_prompts.py`**: new script. Reads `.claude/review-axes/*.md`, transforms (strips `.claude/` frontmatter, adds CI-specific header), writes `.github/prompts/pr-quality-gate-{role}.md`. Pattern follows `generate_commands.py` (ADR-035 exit codes, NO-REGEN sentinel, regen_guard).
- **Plugin manifest** (`.claude/.claude-plugin/plugin.json`): `.claude/review-axes/` ships by virtue of `.claude/` convention. Verify with `build/scripts/validate_plugin_manifests.py` (resolves OQ1).

### Failure modes

| FM | Failure | Detection | Mitigation |
|----|---------|-----------|------------|
| FM1 | Canonical and generated diverge (hand edit to `.github/prompts/`) | Drift hook (pre-push) + drift CI check | Hook blocks push; CI blocks merge. Build script idempotent. |
| FM2 | Build script partial generation (5 of 6 files written, then crash) | pytest case: simulate write failure mid-generation | Atomic write: generate to `.tmp`, fsync, rename. Reject partial state. |
| FM3 | Vendored install missing `.claude/review-axes/` | AC5 verification: fresh checkout of `.claude/` only | Plugin manifest ships the directory. Pre-merge check confirms `.claude/review-axes/*.md` are tracked. |
| FM4 | Schema evolution: new axis added | Build script + drift hook discover `.claude/review-axes/X.md` not in `.github/prompts/` | Generator scans canonical dir; emits all matching files. Drift hook flags missing CI prompt. CI workflow needs manual update for new axis (matrix job). Documented in axis-add runbook. |
| FM5 | Schema evolution: axis renamed | Generator detects only by filename | Renaming requires deleting old `.github/prompts/pr-quality-gate-OLD.md` AND updating CI workflow. Blocking failure mode; needs manual cleanup. Documented. |
| FM6 | `merge_verdicts` receives unknown token | Function returns `UNKNOWN` and logs at WARN | Caller (/review, /pr-quality:all) reports verdict UNKNOWN to user; does not silently downgrade. |
| FM7 | Skill invocation fails (taste-lints crashes) | `/review` catches exception, marks that axis UNKNOWN | Verdict merge: UNKNOWN does not block but is surfaced. /review continues remaining axes. |
| FM8 | Stale `pr-quality.all.md` orchestrator prose | OQ2: orchestrator cites `AIReviewCommon.psm1` (vanished module) | Update orchestrator prose to cite `ai_review_common.py` as part of this PR. Add lint check (canonical-source-mirror rule per `.claude/rules/canonical-source-mirror.md`) for future regressions. |

### Security

- **Prompt injection via canonical axis content**: review-axes files are markdown, consumed verbatim by Copilot CLI / Claude. A malicious PR could modify `.claude/review-axes/X.md` to include instructions that bypass evaluation. Mitigation: file mode 0644, codeowners pin `.claude/review-axes/` to maintainers (per `.claude/rules/security.md`). Drift check itself does not execute axis content; only diffs.
- **Code execution in build script**: `generate_pr_quality_prompts.py` reads markdown, transforms via Python string ops. No `eval`, no shell, no subprocess. Input validation: filenames must match `^[a-z][a-z0-9_-]*\.md$`. Cite `.claude/rules/security.md` AC: input validation at boundary.
- **Authorization for canonical edits**: changes to `.claude/review-axes/` MUST trigger security agent review per `.claude/skills/security-detection/`. Add path to security-detection allowlist if not already covered.
- **Secrets**: none. No API keys, no tokens.

### Observability

- **Build script output**: structured stdout per `AGENTS.md` exit-code contract: `0` success (with summary "regenerated N files"), `1` logic error (collision, source missing), `2` config error. Lines of form `key=value` for parseability.
- **Drift hook output**: when divergence detected, prints `DRIFT: .claude/review-axes/X.md != .github/prompts/pr-quality-gate-X.md` with unified diff. Exit code `1` blocks push.
- **CI drift job**: emits GitHub Actions error annotation with file paths and diff. Job summary lists divergent files.
- **/review output**: per-axis verdict + final merged verdict via `get_verdict_emoji`. Findings in markdown table with severity/category/location/recommendation.
- **Metrics**: count of canonical axes regenerated (logged), count of drift detections per week (manual review against `.agents/sessions/`).

### Acceptance criteria (EARS syntax)

- AC1. WHEN a maintainer commits to `.claude/review-axes/{role}.md` for `role in {analyst, architect, qa, security, devops, roadmap}` THE SYSTEM SHALL preserve frontmatter (`name`, `role`, `version`, `description`) AND a body containing sections `Grounding Rules`, `Analysis Focus Areas`, `Output Schema` SO THAT the canonical file is self-contained and parseable by both `/review` and the build script. **Initial content seeded verbatim from `.github/prompts/pr-quality-gate-{role}.md` (current rigorous source).**
- AC2. WHEN `python3 build/scripts/generate_pr_quality_prompts.py` runs THE SYSTEM SHALL read `.claude/review-axes/*.md`, transform each (strip `.claude/`-only frontmatter, prepend CI header, write atomically), AND emit `.github/prompts/pr-quality-gate-{role}.md` SO THAT the CI prompts are regenerated deterministically. Running the script twice in succession SHALL produce zero diff (idempotent).
- AC3. WHEN `git push` is invoked with divergence between `.claude/review-axes/*.md` and `.github/prompts/pr-quality-gate-*.md` THE SYSTEM SHALL block the push via `.githooks/pre-push` AND emit a unified diff identifying every divergent file SO THAT drift cannot land in main. WHEN the same divergence exists at PR-merge time THE SYSTEM SHALL block the merge via the `ai-pr-quality-gate.yml` drift-check job (backstop).
- AC4. WHEN `/review` is invoked THE SYSTEM SHALL load 6 canonical axes from `.claude/review-axes/{analyst,architect,qa,security,devops,roadmap}.md` AND chain `Skill(skill="code-qualities-assessment")`, `Skill(skill="golden-principles")`, `Skill(skill="taste-lints")` SO THAT 9 verdicts are produced. THE SYSTEM SHALL merge verdicts via `merge_verdicts` from `.claude/lib/ai_review_common.py` (any CRITICAL_FAIL/REJECTED/FAIL -> CRITICAL_FAIL; any WARN -> WARN; all PASS -> PASS).
- AC5. WHEN `/review` runs in a vendored install (only `.claude/` checked out, no `.agents/` or `.github/`) THE SYSTEM SHALL succeed AND produce verdicts from the 6 canonical axes + 3 skill extras SO THAT downstream consumers of `project-toolkit` get full review capability. Verified by a fresh-checkout test that copies only `.claude/{agents,commands,hooks,lib,rules,settings.json,skills,review-axes}` + `CLAUDE.md` and runs `/review` via the Claude Code harness.
- AC6. WHEN tests run via `python3 -m pytest tests/build_scripts/test_generate_pr_quality_prompts.py tests/lib/test_ai_review_common.py tests/hooks/test_drift_check.py` THE SYSTEM SHALL exercise: (a) build script idempotency, (b) build script partial-write recovery (FM2), (c) build script schema validation (filename regex, required frontmatter), (d) `merge_verdicts` for every verdict-token combination including UNKNOWN, (e) `get_verdict_emoji` mapping, (f) drift hook detects divergence, (g) drift hook passes when synced. Coverage: 100% for `ai_review_common.py` (per security/business floor in AGENTS.md).
- AC7. WHEN `.claude/commands/pr-quality/all.md` orchestrator prose cites verdict-merge logic THE SYSTEM SHALL cite `.claude/lib/ai_review_common.py` (the live module) AND NOT `AIReviewCommon.psm1` (the removed module from PR #1066/#1169). Resolves stale citation per `.claude/rules/canonical-source-mirror.md`.
- AC8. WHEN issue #1934 body and epic #1933 body claim "7 axes" or cite `.claude/lib/AIReviewCommon` (no `.py`) THE SYSTEM SHALL update both bodies via `gh issue edit` to reflect: 6 canonical axes (matching current CI), `ai_review_common.py` Python module location, and the chained-skills approach for /review extras. Resolves spec-coverage drift per memory `feedback_pr_description_is_spec_input`.

### Out of scope

- Wiring existing skills (analyze, threat-modeling, etc.) into /review axes (Child 2 #1935).
- Promoting borderline concepts (Conway, Brandolini, Falsifiability) to vendor-safe paths (Child 3 #1936).
- Importing wiki concepts to vendor-safe paths (Child 4 #1937).
- `/ship` collapse to "did /review pass" (Child 5 #1938).
- `orphan-ref-validator` skill (Child 6 #1939).
- Retrospective doc creation (Child 7 #1940; project-only artifact, vendor-survival N/A).
- Adding session-protocol-check.md as a 7th canonical axis (deferred; CI does not currently run it; can be added in a follow-up if value proven).

### Deferred

- DEF1. Generator updating orchestrator prose automatically. Owner: implementer. Trigger: if drift between `ai_review_common.py` API and `pr-quality/all.md` prose recurs after this PR.
- DEF2. Codeowners pin on `.claude/review-axes/`. Owner: security agent. Trigger: first observed prompt-injection attempt or PR review from non-maintainer touching review-axes.
- DEF3. Telemetry on drift-detection frequency (weekly count). Owner: devops. Trigger: 4 weeks post-merge, evaluate whether drift is recurring (signal for tooling gap) or one-off (signal that drift hook works as intended).

### Open questions (carry to design step)

- OQ1. Plugin manifest enumeration: read full plugin.json + `validate_plugin_manifests.py`. Decision in design step.
- OQ2. Orchestrator prose update mechanism: manual edit in this PR vs generator-driven. Decision in design step.
- OQ3. Axis schema MUSTs vs SHOULDs. Decision in spec-generator step.
- OQ4. Issue body update timing (before merge or as part of merge). Decision in implementer step.

### CVA summary

To be filled by step 5 of `/spec` (cva-analysis skill).

Commonalities anticipated: all 6 canonical axes share frontmatter schema, body section structure (Grounding Rules, Focus Areas, Output Schema), and verdict token vocabulary. Variabilities anticipated: per-axis focus content differs (architect vs security vs qa). Relationships anticipated: canonical -> generated CI prompt is one-to-one transform; canonical + skill extras -> /review verdict is many-to-one merge.
