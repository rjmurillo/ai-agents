---
type: design
id: DESIGN-026
title: Placement taxonomy doc extension and the narrow memory placement validator
status: draft
priority: P1
related:
  - REQ-028
  - TASK-037
created: 2026-09-16
updated: 2026-10-12
author: spec
tags:
  - governance
  - memory
  - knowledge-persistence
  - lefthook
---

# DESIGN-026: Placement taxonomy doc extension and the narrow memory placement validator

## Requirements Addressed

REQ-028-001 through REQ-028-007, per the numbering in
`.project-toolkit/specs/requirements/REQ-028-knowledge-placement-contract.md`.

## Design Overview

Two deliverables on separate branches off `main`, with an explicit merge
order: PR B (the validator) merges first, because PR A's rule text names
the `memory-placement` job. PR A extends the two existing persistence-surface documents
(`templates/rules/knowledge-persistence.md`, `.serena/memories/README.md`)
with the placement taxonomy REQ-028 defines; no code changes. PR B adds one
new, narrow validator script that flags newly added Serena memories carrying
normative or procedural content, wires it into the existing parallel memory
job group in `lefthook.yml`, and ships its tests. Issue #5828 adds a server-side
step in `.github/workflows/pr-validation.yml`, rename-aware base reads, and a
rule that fails an existing memory whose classification rises to normative. Neither PR touches the
always-on `templates/rules/universal.md`, the memory-index integrity
validators (issues #4313, #4776, #4705), or any capability registry.

## Component Architecture

```text
PR A (doc only)
templates/rules/knowledge-persistence.md   canonical (edit: new "Placement
                                            taxonomy" section, five
                                            destinations)
        |
        |  uv run python build/scripts/build_all.py
        v
src/claude/rules/knowledge-persistence.md          plugin tree
.claude/rules/knowledge-persistence.md             install tree
.github/instructions/knowledge-persistence.instructions.md   Copilot mirror
src/copilot-cli/instructions/knowledge-persistence.instructions.md   plugin mirror

.serena/memories/README.md   canonical, hand-maintained (edit: new "What
                              belongs here" section, points at the taxonomy
                              and documents the suppression marker)

PR B (validator)
scripts/validation/check_memory_placement.py   new
tests/validation/test_check_memory_placement.py   new
lefthook.yml   edit: one new job in the existing memory-size/memory-index/
               memory-token-counts/memory-tier parallel group
```

## Technology Decisions

| Decision | Choice | O5 source | Rationale |
|---|---|---|---|
| Where the taxonomy lives | Extend `templates/rules/knowledge-persistence.md`, not `universal.md` | REQ-028 Out of scope | Epic #5456's 2026-09-11 direction: any byte change to `universal.md` needs figures refreshed in four downstream documents; `knowledge-persistence.md` is already path-scoped to the exact trees this contract governs and already carries the sibling rule and memory guidance |
| Validator language | Python, matching existing `scripts/validation/` siblings | ADR-042 | Every validator this job group already runs (`memory_index.py`, `update_memory_index_tokens.py`, `validate_memory_tier.py`) is Python; a new script in the same language keeps one runtime for the whole group |
| New-vs-existing policy | Presence in `git ls-tree -r --name-only <base>` decides new; for an existing file, a rename-aware read of its base content decides whether the classification rose (issue #5828) | REQ-028 Out of scope (no corpus migration) | Existing memories keep warning, so the corpus needs no migration; only a file entering the tree, or one that gets worse, fails. The base ref is the baseline, so no debt-register file exists to raise |
| Classification model | Two-signal threshold (normative-heading OR role-contract, else keyword-count-plus-procedure-shape), not a single keyword count | REQ-028 Q5 evidence | Corpus measurement (993 validator-eligible files): 162 contain `MUST`, 185 carry a governance-style heading; a single-keyword rule would flag roughly one file in six with no discrimination. Two independent signals catch the shape the rules actually care about (a memory that reads like a rule or an agent contract) instead of penalizing incidental use of `never` or `always` in prose |
| Suppression mechanism | One HTML comment with a non-empty reason, `<!-- placement: evidence; reason: ... -->`, matching the existing `vendor-portability` and `citation-freshness: ignore` marker convention already used elsewhere in this repository | `canonical-source-mirror.md` precedent | Reuses a pattern every contributor already knows instead of inventing a new escape-hatch syntax |
| Server-side leg | A `Run memory-placement check` step in `validate-pr` of `.github/workflows/pr-validation.yml`, after the memory-index token ratchet, running `check_memory_placement.py --ci --changed-since FETCH_HEAD` after one base-ref fetch (issue #5828) | ADR-006 | Every route that skips local hooks (`--no-verify`, a clone without `lefthook install`, a bot push, a cloud agent, the web editor) reaches `main` unchecked; the sibling memory ratchets carry the same server-side step for the same reason. The script owns the diff, the rename detection, and the merge-base lookup, so the `run:` block holds the fetch and one command |
| Lefthook placement | Stays as the fast local leg. Joins the existing `parallel: true` group (`memory-size`, `memory-index`, `memory-token-counts`, `memory-tier`), all globbed `.serena/memories/**/*.md` | `lefthook.yml:328-350` | Same trigger glob, same group, no new group needed; the four existing jobs in that group establish the pattern for a fifth |

## Placement taxonomy (doc content, PR A)

New section in `templates/rules/knowledge-persistence.md`, placed after the
existing "Net-new information decision checklist" and before "MUST NOT". Five
destinations, each with a one-paragraph decision rule, matching the shape of
REQ-028's Ontology section:

1. **Rule** (`templates/rules/<name>.md`). A cross-cutting normative
   invariant (must, never, always, a required recovery step, a scope
   discipline, a safety or quality gate) that applies whenever its `paths:`
   scope matches, and that must not depend on Serena retrieval to be honored.
   Always-on only when it binds every task; otherwise path-scoped. If the
   behavior binds only one skill's own workflow, it belongs in that skill,
   not in a rule.
2. **Skill** (`.claude/skills/<name>/SKILL.md`). A repeatable task, workflow,
   procedure, or tool-using capability invoked by task intent. May carry its
   own scripts, references, deterministic checks, and workflow-specific
   normative text that binds only when that skill runs.
3. **Agent** (`templates/agents/<stem>.claude.md.tmpl` and its Copilot
   variant). Role-specific specialization: authority, responsibilities, entry
   criteria, outputs, or a handoff contract for a distinct persona.
4. **Memory** (`.serena/memories/<topic>/<name>.md`). An empirical
   observation, project state, measurement, incident record, learned lesson,
   piece of rationale, or contextual fact whose applicability still requires
   judgment. May explain why a rule, skill, or agent exists. Must never be the
   only place a required behavior is defined.
5. **Delete/merge**. Duplicate explanatory text, an obsolete index, a stale
   copy, or content fully represented by an authoritative artifact with no
   remaining evidentiary value. The disposition, not a sixth storage location.

Overlap rule, stated once at the end of the section: when a rule, skill, or
agent overlaps a memory on the same fact, the rule, skill, or agent is
authoritative and the memory is evidence that yields to it.

`.serena/memories/README.md` gets a short new "What belongs here" section
(after "Directory Structure", before "Size Constraints") that points at the
taxonomy in `knowledge-persistence.md` by path, and documents the suppression
marker: a memory that reads as normative or procedural but is deliberately
kept as evidence carries `<!-- placement: evidence; reason: ... -->` with a
non-empty reason.

## Validator design (PR B)

`scripts/validation/check_memory_placement.py`.

### CLI

```text
check_memory_placement.py [FILE ...] [--path .serena/memories]
                           [--base <git-ref>] [--staged] [--ci] [--json]
check_memory_placement.py --changed-since <git-ref> [--ci] [--json]
```

- Positional `FILE` arguments: explicit paths, the shape lefthook's
  `{staged_files}` substitution produces.
- `--path DIR`: scan every `.md` file under `DIR` recursively (full-corpus
  mode; used for the committed PR-body warning count, not by the lefthook
  job).
- `--base REF` (default `HEAD`): the git ref whose tree defines "existing."
  Resolved once via `git ls-tree -r --name-only <REF>`; any scanned path
  present in that listing is existing, everything else is new. An existing
  file's base content is read with `git cat-file blob <REF>:<path>`.
- `--staged`: read each file from the git index, and take rename sources from
  `git diff --cached --name-status --find-renames --diff-filter=ACMR -z <REF>`.
- `--changed-since REF`: the server-side mode. Lists the memories that
  `git diff --name-status --find-renames --diff-filter=ACMR -z REF...HEAD`
  reports under `.serena/memories`, and uses `git merge-base REF HEAD` as the
  base. It replaces `--base`, `--staged`, `--path`, and positional paths;
  combining them is a usage error (exit 2).
- `--ci`: exit 1 when a file fails (see New-vs-existing policy below);
  without `--ci`, always exit 0 and print findings only.
- `--json`: emit a machine-readable report instead of the human-readable
  table.

### Skip list

- `README.md` (any directory).
- Any file matching `*-index.md`.
- Any non-`.md` file.

### Signals

Four independent signals computed per file:

- **(a) Normative terms.** Word-boundary count of case-sensitive `MUST`,
  `MUST NOT`, `SHALL`, plus case-insensitive `must not`, `never`, `always`,
  `required`. Counted, not just detected, because the classification
  threshold below reads the count.
- **(b) Governance heading.** Any Markdown heading (any level) whose text
  matches `Constraints|Guardrails|Workflow|Procedure|Protocol|Responsibilities|Entry Criteria|Acceptance Criteria|Handoff`.
- **(c) Ordered procedure.** A numbered list with 5 or more consecutive
  items (a Markdown ordered-list block, `1.` through `5.` or further, with no
  non-list line breaking the run).
- **(d) Role contract.** Two or more headings (any level) drawn from
  `Role|Authority|Entry Criteria|Outputs|Handoff|Responsibilities`.

### Classification

- `normative`: signal (b) fires, OR signal (d) fires, OR (signal (a) count
  >= 5 AND signal (c) fires).
- `suspect`: signal (a) count >= 3, or signal (c) fires, or both, when no
  `normative` condition above is met (two weak signals stay `suspect`; they
  never fall through to `evidence`).
- `evidence`: none of the above.

### Suppression

A file carrying an HTML comment on its own line matching
`<!-- placement: evidence; reason: <reason> -->`, where the reason starts
with a non-whitespace character (so an empty or whitespace-only reason is
rejected and reported as an invalid suppression), is forced to `evidence` regardless of its computed signals, and is reported as
`suppressed` (not silently downgraded) so a reviewer can see the marker was
used.

### New-vs-existing policy

A file's base content is its content at the base ref. For a renamed file the
base path is the old path, so an unchanged file that survives a move keeps its
base class. Classification ranks `evidence` below `suspect` below `normative`,
after suppression.

- File absent from the base tree: new. A `normative` classification fails
  under `--ci`. A `suspect` classification is a warning, never a finding,
  because the two-signal design (Technology Decisions, above) reserves failure
  for the stronger of the two classes.
- File present at the base: existing. It fails under `--ci` only when its
  classification rose to `normative` from `suspect` or `evidence`. A file that
  stays `normative`, falls, or stays below `normative` is a warning at most.
  Removing a valid suppression marker from a file that reads as `normative`
  counts as a rise, because the marker had held the label at `evidence`.
- A copy is not tracked: git reports it as an add, so it is new.
- A rename that also edits the file is judged on the edited content against
  the old path's content. Renames below git's 50 percent similarity threshold
  appear as a delete plus an add and are judged as new.

The base content is read only for a file that classifies `normative`, since
only that file can fail by rising.

### Routing hint

Every `normative` or `suspect` finding names where the content should move,
per the taxonomy in `templates/rules/knowledge-persistence.md`:

- Signal (b) or (a)-dominant match without a role-contract shape: route to
  `templates/rules/`.
- Signal (d) (role-contract shape): route to `templates/agents/<stem>.claude.md.tmpl`.
- Signal (c) (ordered procedure) without a role-contract shape: route to
  `.claude/skills/<name>/SKILL.md`.

### Exit codes

Per `AGENTS.md` Standards (0 ok, 1 logic, 2 config, 3 external, 4 auth):

| Code | Meaning |
|---|---|
| 0 | Clean, or findings exist but none is a failing file, or `--ci` not passed |
| 1 | `--ci` passed and at least one file is `normative` and either new or risen |
| 2 | Bad arguments, not a git repository, `--base` or `--changed-since` does not resolve, or no merge base exists |

### Lefthook wiring

New job in the existing `parallel: true` group at `lefthook.yml:328-350`,
alongside `memory-size`, `memory-index`, `memory-token-counts`, and
`memory-tier`:

```yaml
- name: memory-placement
  timeout: 1m
  run: uv run --frozen python scripts/validation/check_memory_placement.py --ci --base HEAD --staged {staged_files}
  glob: ".serena/memories/**/*.md"
```

`{staged_files}` supplies exactly the files lefthook is already gating in
this group, so the job costs no additional filesystem walk beyond what its
four siblings already do.

### Server-side wiring

The local hook is skipped by `--no-verify`, a clone without `lefthook install`,
a bot push, a cloud agent, and the web editor. A step in the `validate-pr` job
of `.github/workflows/pr-validation.yml` closes that gap (issue #5828):

```yaml
- name: Run memory-placement check
  env:
    BASE_REF: ${{ github.base_ref || github.event.repository.default_branch }}
  run: |
    git fetch origin "$BASE_REF"
    uv run --frozen python3 scripts/validation/check_memory_placement.py --ci --changed-since FETCH_HEAD
```

The step sits after "Run memory-index token ratchet", takes no `if:`, and keeps
the fetch full-depth so `git merge-base` finds the branch point. The PR-body
override token some designs add is not part of this check; the in-file
`<!-- placement: evidence; reason: ... -->` marker is the only suppression, so
the same rule applies on `merge_group`, where the PR body is empty.

## Decision-rule Traceability

| Decision rule | Source | Where enforced |
|---|---|---|
| Existing memories warn unless an edit raises them to normative | REQ-028 Out of scope | New-vs-existing policy, `--base` comparison and rise rule |
| No second parallel taxonomy | REQ-028 Out of scope | Placement taxonomy content extends `knowledge-persistence.md` and `README.md` in place; no new document created |
| No capability registry, ownership graph, duplication framework, token ratchet, or copied-contract policy | REQ-028 Out of scope | Validator scope limited to the four signals above; no cross-file graph, no token counting, no duplicate-detection logic |
| `universal.md` untouched | REQ-028 Out of scope | Design Overview; taxonomy lives in `knowledge-persistence.md` only |

## Failure modes

| Scenario | Mode | Detection | Handling |
|---|---|---|---|
| `git ls-tree` fails (not a git repo, bad `--base`) | Cannot determine new-vs-existing | Non-zero exit from the subprocess call | Exit 2, error names the ref and the command tried |
| A file is renamed with no content change | Would read as new at the new path | `--find-renames` in the name-status diff supplies the old path | The base class is read from the old path, so the unchanged file passes. Content that gets worse in the same commit fails as a rise |
| A rename scores below git's 50 percent similarity | Reads as a delete plus an add | None; git's threshold | Judged as new. Split the move and the rewrite into two commits |
| `--changed-since REF` cannot find a merge base (shallow clone, unrelated history) | Cannot decide the baseline | Non-zero exit from `git merge-base` | Exit 2, error says to fetch full history for the base ref |
| A heading regex false-matches inside a fenced code block | Miscounts signal (b) or (d) | None automatic | Test suite includes a fixture with a fenced block containing a matching heading string, asserting it is excluded from signal counting |
| Suppression marker present but reason is empty or whitespace-only | Marker does not downgrade | The regex requires `.+` after `reason:` | File keeps its computed classification; reported as `suppression-rejected: empty reason` |
| A memory file has no headings and no numbered lists but a high normative-term count (for example, a wall of `MUST` in prose) | Neither `normative` condition is met (needs (b), (d), or (a)&(c) together) | Classified `suspect`, warning only | Documented as an accepted false-negative for `--ci` purposes; the two-signal threshold trades this case away deliberately, per REQ-028 Q5's evidence that a single-keyword rule over-fires |
| Full-corpus run (`--path .serena/memories`, no `--ci`) is used to justify a claim in a PR body | Warning count could be misquoted as a pass/fail signal | N/A, this is a process risk not a code risk | TASK-037 records the exact full-corpus warning count as PR-body evidence, and this design's Observability line names the three counts a caller must report together |

## Security

Input: a list of file paths (from lefthook's `{staged_files}` or `--path`)
and a git ref string (`--base`). No network access. No secrets are read or
written; memory files carry no credentials by repository convention
(`universal.md` MUST 6). Path handling: every scanned path is resolved and
checked for containment inside the repository root before being opened,
mirroring the CWE-22 defense pattern `skill_templates._name_validation_error`
already uses elsewhere in this repository; a path resolving outside the
repository root is rejected with exit 2 rather than opened. The `--base`
argument is passed to `git ls-tree` as a single argv element via
`subprocess.run` with a list (`shell=False`), never interpolated into a
shell string, so it cannot inject additional git arguments or shell
metacharacters.

## Observability

The CI output for a run reports three counts together, always in the same
line: number of files classified `normative`, number classified `suspect`,
and number of `suppressed` (marker-downgraded) files, for the scope
scanned. A full-corpus run's line is the number TASK-037 commits into the PR
B body as the baseline warning count, so a future full-corpus run can be
diffed against it to see whether the corpus is drifting toward more
normative content over time, without that comparison becoming a second
enforced ratchet.

## Testing Strategy

`tests/validation/test_check_memory_placement.py`, positive, negative, and
edge cases, mirroring the shape of the existing memory-validator tests in
the same directory (`test_validate_memory_tier.py` and siblings):

| Case | Assertion |
|---|---|
| New file, signal (b) heading present | Classified `normative`; `--ci` exit 1 |
| New file, signal (d) two role headings present | Classified `normative`; routed to `templates/agents/` |
| New file, (a) count >= 5 and (c) 5-item list present | Classified `normative` |
| New file, (a) count == 3, no other signal | Classified `suspect`; `--ci` exit 0 |
| New file, plain incident record with "never again" once and no headings/lists | Classified `evidence`; exit 0 |
| New file, evidence memory with two incidental "must" words in prose | Classified `evidence`; exit 0 |
| Existing file (present in `--base` tree), `normative` shape | Reported as warning; exit 0 even under `--ci` |
| Suppression marker with non-empty reason on an otherwise-`normative` new file | Classified `evidence`, reported `suppressed`; exit 0 |
| Suppression marker with empty reason | Marker rejected; original classification stands |
| `README.md` under any directory | Skipped, absent from the report |
| Any `*-index.md` file | Skipped, absent from the report |
| Non-`.md` file passed on the CLI | Skipped, absent from the report |
| `--base` pointing at a temp git repo's initial commit, file added since | New-vs-existing correctly split via a real temp git repo, not a mock |
| Bad `--base` ref | Exit 2, error names the ref |
| Not a git repository (`--path` run outside any `.git`) | Exit 2 |
| Full-corpus run against a fixture tree | Warning/normative/suppressed counts sum to the fixture's known totals |
| `git mv` of a normative memory, staged and via `--changed-since` | Passes under `--ci`; the same move with a rise in signals fails |
| Existing memory moving evidence to normative, suspect to normative, normative to normative, normative to suspect or evidence | The first two fail; the rest pass |
| `--changed-since` after main moved on | Judged against the merge base, not the tip |
| `--changed-since` combined with `--staged`, `--base`, `--path`, or a path | Exit 2 |
| Live `.serena/memories/` corpus (`test_check_memory_placement_corpus.py`) | Zero failing files, and normative, suspect, and suppressed counts stay under pinned ceilings |
| `pr-validation.yml` wiring (`tests/ci/test_pr_validation_memory_placement_wiring.py`) | One unconditional step in `validate-pr`, a fetch plus one `--ci --changed-since FETCH_HEAD` command |

`tests/validation/` already hosts every sibling memory validator's tests;
this file joins that directory rather than creating a new test location.

## Open Questions

None blocking. REQ-028 records no open questions either.
