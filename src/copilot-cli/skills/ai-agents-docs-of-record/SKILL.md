---
name: ai-agents-docs-of-record
version: 1.0.0
license: MIT
description: Runbook for this repo's documents of record. Session logs, ADRs, retrospectives, Serena memories, per-issue handoffs, plus the templates, validators, naming rules, and house prose style that bind them. Use when you say `write the session log`, `create an ADR`, `fill the retro`, `save this to memory`, `which document of record`. Do NOT use for authoring skills (use `SkillForge`) or research write-ups (use `ai-agents-research-methodology`).
---

# ai-agents-docs-of-record

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This repo runs on verification-based governance. Continuity lives in per-issue
handoffs and Serena memory. Session logs are optional records, while transcript
and pull request evidence remain valid.

## Triggers

- `write the session log`
- `create an ADR`
- `fill the retro`
- `save this to memory`
- `which document of record does this go in`

## The Record System Map

| Record | Location | Create with | Validated by |
|--------|----------|-------------|--------------|
| Session log | `.agents/sessions/YYYY-MM-DD-session-NN[-slug].json` | hand-written against the schema | `scripts/validate_session_json.py`, validate-if-present via the `session-policy` pre-commit hook or on demand (a session log is optional) |
| Per-issue handoff | `.agents/sessions/handoffs/{YYYY-MM-DD}-{ISSUE}-handoff.md` | copy `.agents/templates/HANDOFF.md` | resume-verification checklist at next session start |
| ADR | `.agents/architecture/ADR-NNN-slug.md` | `adr-generator` skill | `scripts/validation/check_adr_uniqueness.py`; `adr-review` debate gate |
| Retrospective | `.agents/retrospective/` | auto-retro skeleton + `/retro fill`, or `retrospective` skill | `INDEX.md` row (auto-appended, incomplete; see Phase 4) |
| Serena memory | `.serena/memories/[domain]-[name].md` | `memory` skill write conventions | `curating-memories` skill; `memory-index` routing |
| Project dashboard | `.agents/HANDOFF.md` | nobody. READ-ONLY per ADR-014, 5K hard cap | push guard; protocol MUST NOT |

## Process

### Phase 1: Pick the right record

| Situation | Record | Why |
|-----------|--------|-----|
| Operator requests a committed session record | Optional session log | Retained schema and validator |
| Issue spans multiple sessions | Per-issue handoff | Cold-start continuity (Issue #1725: 95.8% protocol failure without file-based gates) |
| Architectural or irreversible decision | ADR | Fires `adr-review` multi-agent debate |
| Incident, failure, or "what went wrong" | Retrospective | Feeds the failure canon; see `ai-agents-failure-archaeology` |
| Reusable pattern, correction, gotcha | Serena memory | Only memories are read by future sessions at start |
| User corrected you mid-session | `reflect` skill, then memory | Corrections not persisted are lost |
| A doc you touched is stale | Fix on contact (Phase 7) | Broken-windows rule |

One fact can need two records: an incident gets a retrospective AND a memory
distilling the rule. The retro is the evidence; the memory is the searchable
lesson.

### Phase 2: Session logs

Session logs are JSON, schema at `.agents/schemas/session-log.schema.json`
(top-level required: `session`, `protocolCompliance` with `sessionStart` and
`sessionEnd` subsections).

Create a log only when the operator opts in. No start, end, commit, push, or
pull request gate requires one.

```bash
uv run python3 scripts/validate_session_json.py .agents/sessions/<file>.json
```

Write the JSON by hand against `.agents/schemas/session-log.schema.json`, name
it `YYYY-MM-DD-session-NN[-slug].json` (host-local date, per Issue #4779; see
`scripts/hook_utilities/utilities.py::host_session_date`), and validate it
with the command above.

Hard requirements enforced by `scripts/validate_session_json.py`:

- Required `session` fields: `number`, `date`, `branch`, `startingCommit`, `objective`.
- Branch must match `^(feat|fix|docs|chore|refactor|test|ci)/`.
- `startingCommit` must be a 7-40 char lowercase hex SHA.

Naming in current practice may append a slug:
`2026-06-30-session-2600-skill-tooling-hygiene-taste-lints-naming.json`. Never
resolve a session-log merge conflict with `git checkout --ours`; the settled
rule from the session 1187 incident is take `--theirs` and rename your own log
to the next free number (see `ai-agents-failure-archaeology`).

### Phase 3: ADRs

Numbering collides here; treat numbers as claims, not identity. History:
concurrent ADR PRs each picked the same "next" number (Issue #2253), and
ADR-058/062/063 each existed twice until the duplicates were renumbered to
069/070/071 (Issue #2228, per the docstring of
`scripts/validation/check_adr_uniqueness.py`). ADR-055 and ADR-024 share the
slug `github-actions-runner-selection` (055 supersedes 024). Rule: when citing
an ADR, verify the file content says what you claim, not just the number.

```bash
python3 scripts/validation/check_adr_uniqueness.py --print-next
```

Workflow:

1. Search first: `memory-search` for prior decisions, then read neighbors in
   `.agents/architecture/` (ADR-007 memory-first: retrieval precedes reasoning).
2. Generate with `adr-generator` against `.agents/architecture/ADR-TEMPLATE.md`.
3. Claim the number from `--print-next` at the last moment before commit.
4. Expect the gate: any `ADR-*.md` create or edit fires the `adr-review`
   multi-agent debate (AGENTS.md, "ADR Review").
   Governance-level changes additionally need human approval (AGENTS.md
   Boundaries: "Ask First: Architecture|New ADRs|Breaking|Security").
5. Lifecycle frontmatter per ADR-073 (accepted 2026-06-19): optional,
   unenforced Phase-1 fields `id`, `status`, `date`, `decision-makers`,
   `supersedes`, `superseded-by`, `explainer`, `implemented`. Use them on new
   ADRs; do not backfill mechanically.

### Phase 4: Retrospectives

Two skills, different jobs. `reflect` captures corrections and praise
mid-conversation while context is hot. `retrospective` produces the full
artifact (timeline, Five Whys, learning matrix) in `.agents/retrospective/`.

Retrospectives are written on demand: `/retro` here, plus the Post-PR
Retrospective workflow in CI. Until #3349 a Stop hook also wrote a skeleton
at session end stamped `<!-- RETRO-STATE: skeleton-pending-fill -->` (Issue #2079); that hook is deleted, but skeletons it already wrote are still
placeholders rather than records, so fill them with `/retro fill YYYY-MM-DD`.

`INDEX.md` was auto-appended by that hook (Issue #1703) and is incomplete: 5
rows against 95 retro files as of 2026-07-03. Nothing appends to it now.
Never treat INDEX.md as the catalog; list the directory. Also note retro-cited short SHAs do not resolve
locally even with full history present (~1471 commits as of 2026-07-03), so
retros and memories, not git archaeology, are the durable history (depth in
`ai-agents-failure-archaeology`).

Retro learnings MUST be persisted to Serena in the same session, not left as
prose in the artifact (`.serena/memories/retrospective-accuracy.md`: "learnings
were proposed in the retrospective but then not persisted to Serena, so they
will be lost").

### Phase 5: Serena memories

Write conventions (canonical text: `.claude/skills/memory/SKILL.md`, "Serena
Write Conventions"):

- File name: `[domain]-[descriptive-name].md`, lowercase, hyphens. Example:
  `pr-review-security.md`.
- Entity ID inside the file: `{domain}-{description}`, kebab-case, no prefix.
  File name and entity ID are separate things; do not conflate them.
- Domain index files (`skills-*-index.md`) are a two-column table ONLY. Insert
  new rows AFTER the last existing data row, never after the header or
  delimiter row.
- Register new memories where `memory-index` (the keyword-to-memory routing
  map read at session start) will find them.

Curation (marking obsolete, dedupe, bidirectional links) is the
`curating-memories` skill. Search is `memory-search` (Tier 1); the four-tier
model is ADR-063.

Separate-PR rule: `.claude/rules/claude-agents.md` MUST NOT item 2: "MUST NOT
bundle skill code changes with memory changes in the same PR (separate
concerns)." Memory edits ride their own PR. The cautionary tale is PR #908,
where 53 memory files changed in a PR that started as one CI fix
(`.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md`).

### Phase 6: Handoffs

Tier model per ADR-014 and `.agents/sessions/handoffs/README.md`:

| Tier | Location | Scope |
|------|----------|-------|
| Session log | `.agents/sessions/*.json` | Optional single-session record |
| Per-issue handoff | `.agents/sessions/handoffs/{date}-{issue}-handoff.md` | One issue across sessions; rewritten each session |
| Per-branch handoff | `.agents/handoffs/{branch}/{session}.md` | Multi-session branch coordination |
| Dashboard | `.agents/HANDOFF.md` | Project-wide, READ-ONLY, 5K hard cap |

Start from the template `.agents/templates/HANDOFF.md`. A handoff must carry a
"Verification on Resume" checklist; the next session executes it before any
Edit or Write (`templates/agents/implementer.shared.md`, "Session Start", a
blocking gate). Never edit
`.agents/HANDOFF.md` itself: it had grown to 122KB with an 80%+ per-PR merge
conflict rate before ADR-014 froze it
(`.agents/architecture/ADR-014-distributed-handoff-architecture.md:13-16`;
AGENTS.md "Never" list).

### Phase 7: House style and stale docs

Prose rules (canonical: `.claude/rules/voice.md`, `.claude/rules/universal.md`):

- Lead with the point. Name file, line, command, number, or say you do not know.
- No em-dashes or en-dashes anywhere in authored text (universal.md MUST NOT
  item 5; only `tests/hooks/fixtures/` is exempt). Every dash costs a bot
  review thread.
- No banned vocabulary (voice.md "Banned Vocabulary" section).
- No auto-generated headers or timestamps-as-headers in any authored or
  generated file (universal.md MUST NOT item 6; rejected by the user three
  times as of 2025-12-17).
- Block-style YAML arrays only in frontmatter
  (`.agents/governance/PROJECT-CONSTRAINTS.md`, Frontmatter constraints table;
  ADR-040 Amendment). Inline `['a', 'b']` breaks Copilot CLI parsing.
- Run `prose-self-check` before emitting any session-log narrative, ADR
  context section, retro, or PR description.

Markdown lint is SCOPED to files you changed. The PR #908 Five Whys traced 53
unrelated memory-file changes to `markdownlint --fix **/*.md` run repo-wide
(retro, Q1-Q4). Lefthook filters staged Markdown and runs the named validator
declared in `lefthook.yml`. Config is `.markdownlint-cli2.yaml`. Never widen
the glob.

Mirror claims (FM-9): any statement that a file "matches", "mirrors", or
"aligns with" another source MUST cite the canonical path and quote the
load-bearing fragment character-for-character; intentional divergence gets a
named divergence section (`.agents/governance/FAILURE-MODES.md`, failure mode
9; rule text in `.claude/rules/canonical-source-mirror.md`; heuristic gate
`scripts/validation/check_canonical_citations.py`, warn-only unless
`STRICT_CANONICAL_CHECK=1`). Cost of ignoring it: PR #1887 took 7 fix commits
on confident-incorrectness claims.

Fix stale docs on contact. Worked example from before PR #2871:
`CONTRIBUTING.md` line 155 said `build/Generate-Agents.ps1` PowerShell invocation until PR #2871
repointed it to `build/generate_agents.py`. Zero `.ps1` build scripts
exist (ADR-042 Python migration). When you touch a stale doc: fix the lines on
your path, quote the canonical source per FM-9, and flag (do not silently expand
into) the rest. Behavioral claims in docs are verified with `doc-accuracy`.

## Anti-Patterns

| Anti-pattern | Why it burns you | Evidence |
|--------------|------------------|----------|
| Editing `.agents/HANDOFF.md` | Read-only per ADR-014; push guards and reviewers reject it | AGENTS.md "Never" list |
| Creating a log only to satisfy a gate | Reintroduces the retired workflow | `.claude/rules/session-logs.md` MUST 1 |
| Trusting an ADR number without reading the file | Numbers collided (058/062/063 dupes; 024 vs 055 same slug) | `check_adr_uniqueness.py` docstring |
| Repo-wide `markdownlint --fix` | Reformatted 53 unrelated memory files in PR #908 | PR #908 retro Five Whys |
| Bundling memory changes with skill code in one PR | Violates `claude-agents.md` MUST NOT 2; scope explosion | PR #908 retro |
| "Matches X" without a verbatim quote | FM-9 confident-incorrectness; 7 fix commits on PR #1887 | FAILURE-MODES.md section 9 |
| Leaving learnings only in the retro artifact | Never read by future sessions | `retrospective-accuracy` memory |
| Treating INDEX.md or `git log` as complete history | 5 index rows vs 95 retro files; retro-cited SHAs do not resolve locally | Phase 4 |
| `git checkout --ours` on session-log conflicts | Corrupted the main session log once | session 1187 incident |
| Em/en dashes, banned vocab, generated headers | One bot thread per dash, every PR | universal.md MUST NOT 5 and 6 |

## Verification

Before ending any session that produced records:

- [ ] Any staged or supplied session log passes `uv run python scripts/validate_session_json.py <log>`.
- [ ] Any new ADR number came from `check_adr_uniqueness.py --print-next` and the `adr-review` gate ran.
- [ ] Retro learnings are persisted as Serena memories, not just prose in the retro file.
- [ ] New memories follow `[domain]-[name].md` naming and their index row sits after the last data row.
- [ ] Open-issue work has a per-issue handoff with a Verification on Resume checklist.
- [ ] `grep -rPn '[\x{2013}\x{2014}]' <changed .md files>` returns nothing; lint ran scoped to changed files only.
- [ ] Every "matches/mirrors" claim quotes its canonical source verbatim.

## Provenance and Maintenance

Verified 2026-07-03 against the working tree. Re-verify volatile facts before
relying on them:

| Fact | Source | Re-verify |
|------|--------|-----------|
| Optional session-log contract | `.claude/rules/session-logs.md` MUST 1 | `grep -n "validate-if-present" .claude/rules/session-logs.md` |
| Branch naming pattern | `scripts/validate_session_json.py` (`BRANCH_PATTERN`) | `grep -n "^BRANCH_PATTERN = re.compile" scripts/validate_session_json.py` |
| Schema required keys, top level and nested session | `.agents/schemas/session-log.schema.json` | `python3 -c "import json;s=json.load(open('.agents/schemas/session-log.schema.json'));print(s['required'], s['properties']['session']['required'])"` |
| ADR collision history, next-number helper | `scripts/validation/check_adr_uniqueness.py` docstring | `python3 scripts/validation/check_adr_uniqueness.py --print-next` |
| ADR-073 lifecycle fields | `.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md:1-9` | `head -10 .agents/architecture/ADR-073-adr-lifecycle-frontmatter.md` |
| adr-review fires on ADR edits | `AGENTS.md` "ADR Review" | `grep -n "adr-review" AGENTS.md` |
| Auto-retro skeleton + marker + /retro fill | `.claude/commands/retro.md:1-15` | `grep -n "RETRO-STATE" .claude/commands/retro.md` |
| Retro corpus size vs INDEX.md coverage | `.agents/retrospective/` | `python3 -c "import pathlib;d=pathlib.Path('.agents/retrospective');f={p.name for p in d.glob('*.md')}-{'INDEX.md'};t=(d/'INDEX.md').read_text();print(len(f),'retro files,',sum(n in t for n in f),'indexed')"` |
| Memory naming + index-row hazard | `.claude/skills/memory/SKILL.md` "Serena Write Conventions" | `grep -n "Serena Write Conventions" .claude/skills/memory/SKILL.md` |
| Memory/skill separate-PR rule | `.claude/rules/claude-agents.md` MUST NOT item 2 | `grep -n "same PR" .claude/rules/claude-agents.md` |
| Handoff tiers, HANDOFF.md 5K cap | `.agents/sessions/handoffs/README.md` tier table; ADR-014 | `grep -n "5K hard cap" .agents/sessions/handoffs/README.md` |
| FM-9 verbatim-quote rule | `.agents/governance/FAILURE-MODES.md:284-307` | `grep -n "character-for-character" .agents/governance/FAILURE-MODES.md` |
| PR #908 lint scope story | `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md:281-296` | `grep -n "markdownlint" .agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` |
| CONTRIBUTING.md pre-PR #2871 staleness example | PR #2871 repointed `CONTRIBUTING.md` to `build/generate_agents.py` | `git show b320f4ac1 -- CONTRIBUTING.md` |
| Serena canonical, Forgetful supplementary | `.agents/architecture/ADR-007-memory-first-architecture.md:83-102` | `grep -n "Canonical" .agents/architecture/ADR-007-memory-first-architecture.md` |

Maintenance: when a validator, template path, or protocol phase changes, update
the matching row here in the same PR. This file is itself a document of record;
it obeys everything it prescribes.
