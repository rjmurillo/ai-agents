---
type: requirement
id: REQ-049
title: skill-bootstrap cross-source friction sweep with evidence files and independent judges
status: draft
priority: P1
category: functional
created: 2026-11-11
related:
  - "#7155"
  - "#7160"
  - "#6642"
---

# REQ-049: skill-bootstrap cross-source friction sweep with evidence files and independent judges

This file is durable. It holds design and counts only, no message text from any connected source.

## Step 0 First Principles

### Q1

Richard Murillo (repository owner) requested it on 2026-11-11 in this session: friction points must combine tool-call evidence (skill-doctor) with friction gathered through every MCP server (PR discussions, GitHub, Jira, and Azure DevOps work items, Gmail and Microsoft 365 mail, Slack and Teams chat, memory systems such as mem0, hindsight, and Serena, and work-intelligence platforms such as WorkIQ), with institutional knowledge gaps as the priority. He named the friction directions (between humans, agents, tools, and processes, including agent to agent, agent to tool, and agent to process, as skill-doctor shows) and the patterns to detect: context is fragmented, linking conventions are inconsistent, evidence is incomplete or delayed, tools require switching surfaces, human review gates slow automated flows, and work items and PRs drift out of sync. He asked that the model use all tools and skills to gather information, dump it in files, and run judges over the files for suggestions, following the deterministic contract skill-doctor adopted. Single requester, so Q1 passes on the evidence path: specific Q3 plus evidenced Q5.

### Q2

Today a bootstrap run mines git (`bootstrap_mine.py candidates`), imports a skill-doctor inventory (`--sessions-json`), and imports normalized GitHub or Azure DevOps exports (`--hosted-json`, four count signals). Everything else is a hand read: the agent opens PR threads and issues by itself, guided by prose. Chat, mail, documents, meetings, memory systems, and work-intelligence platforms are never named, so a run does not look at them. Nothing records which sources were read, and no second reader checks the agent's conclusions.

Reframing: capability invention, check: a sweep on a repository with at least one connected non-code source reports a knowledge-gap incident that no git or session signal produced.

### Q3

The skill-bootstrap user who wants skills that close institutional knowledge gaps. They are blocked because the skill reads only code-adjacent signals, so the knowledge that lives in chat, mail, meetings, and memory never becomes a skill or a documentation finding, and agents keep getting corrected for context the repository does not hold.

### Q4

About 16 hours: one stdlib script (`bootstrap_sweep.py`, four subcommands), three judge rubrics, one reference, a `--sweep-json` import in `bootstrap_mine.py`, template and reference edits, tests.

### Q5

Repository evidence at commit `9a4c6e416` (2026-11-11): `references/discovery.md` and the SKILL.md template contain no mention of MCP, chat, mail, documents, meetings, or memory servers outside agent sessions; `bootstrap_friction.py` `HOSTED_SIGNALS` accepts exactly four kinds, all GitHub or Azure DevOps. Issue #7155 (open) records the same blind spot for review outcomes: "a bootstrap run will not see it, because round counts carry no content and the manual discovery read does not scale or repeat."

### Q6

At 10x connected sources the sweep still fits: classification is a keyword table plus overrides, collection is bounded by window and page completion, and judges run per batch. The liability is volume, handled by batch size and the coverage report naming what was not read.

## Prior Art / Constraints

- Issue #7155 (open): repeated review failures and missed items from PR exports. Complementary: it computes review signals from code-host data. This spec covers every other source class and judge-based suggestion. Neither blocks the other; both feed `candidates`.
- PR #7160: skill-doctor and bootstrap improvement loop; the `--sessions-json` seed contract this spec mirrors for imports.
- skill-doctor `audit_batches.py`: immutable batch assignment bound to a source digest, all-or-nothing row import, atomic replace. This spec adopts that shape for judges.
- skill-bootstrap anti-pattern table rejects "a friction ledger, registry, or per-fact database". The sweep writes only to a run directory outside the repository and is never persisted as a library artifact.
- Memory search: no prior spec on cross-source friction (searched `.serena/memories`, `.project-toolkit/specs`, `.project-toolkit/architecture` for "institutional knowledge" and "friction" with "mcp"; hits were memory-first pattern notes only).

## Problem statement

skill-bootstrap discovers friction only from git, agent sessions, and four GitHub or Azure DevOps counters, so friction between people, tools, and processes recorded in trackers, chat, mail, documents, meetings, memory systems, and work-intelligence platforms never reaches skill selection. The hand-read discovery it relies on is not recorded, not repeatable, and not checked by a second reader.

## User stories

1. As a bootstrap user, I run one plan command over the connected tool inventory and get the source classes, the read-only tools to use, the tools that are forbidden, and the classes that are not connected.
2. As a bootstrap user, I get evidence files from every connected class in a run directory outside the repository, with a coverage row per class.
3. As a bootstrap user, independent judges read those files and return suggestions (create or update a skill, write a document, add an instrument, fix a process, ask an owner) tied to evidence ids.
4. As a bootstrap user, a deterministic tally ranks incidents, lists institutional knowledge gaps, and feeds the top incidents into `candidates` as seeds.

## Ontology

| O2 name | Meaning |
| --- | --- |
| ToolInventory | The servers, tools, and skills the harness exposes, written by the agent |
| SourceClass | One of `code_review`, `work_tracking`, `chat`, `email`, `documents`, `meetings`, `build_ops`, `memory`, `work_intelligence`, `agent_sessions`, `other` |
| SweepPlan | Classified inventory, window, seeds, judges; identified by `plan_id` |
| EvidenceItem | One sanitized file of collected source content with its locator, date, class, and digest |
| Coverage | Per class: `read`, `partial`, `declined`, `not_connected`, or `unavailable`, with counts and reasons |
| EvidenceIndex | Validated evidence items plus immutable batches; identified by `index_id` |
| Judge | A rubric file that turns a batch into findings |
| Finding | One judge row: incident key, friction type, evidence ids, suggestion, optional knowledge gap |
| Incident | Findings merged by incident key across judges and batches |
| Sweep | The tally output: ranked incidents, knowledge gaps, suggestions, coverage, incomplete work |

Decision rules:

- No source list is prescribed: every server, tool, resource, prompt, and skill the harness exposes enters the inventory, discovered through `tools/list`, `resources/list`, `prompts/list`, and a skill listing where supported.
- A tool is usable only if classified `read`; a write verb always excludes it. Resources are read routes. Prompts are informational.
- Each rubric runs at least twice, by independent readers that see only the rubric and the batch and have no tools. A finding forms an incident only when another run of the same rubric on the same batch reports the same type on overlapping evidence; other findings are `single_reader`.
- An incident is `corroborated` only with evidence from two source classes, or two distinct threads, or a tracked repository path that appears in the text of a cited evidence file.
- Judge output enters `candidates` only as `candidate_unverified` seeds with keys, counts, and enums, never summary or rationale text. This amends the template rule against importing qualitative grades: judged incidents are imported, but as unverified hints, and Phase 2 still confirms each against current code and authoritative evidence.
- The run directory is outside the repository, starts empty, and is deleted when the bootstrap run ends. It is never reused, so it never becomes a friction ledger.

## Data model

- ToolInventory v1: `{"schema_version": 1, "servers": [...], "skills": [...]}`. The agent lists every server and skill the harness exposes, not a known set. A server is a string or `{name, description?, classes?, tools: [str or {name, description?, access?: "read"}]}`; a skill is a string or `{name, description?, classes?}`. Class resolution: `--class-override`, then declared `classes`, then the keyword table as a fallback hint, else `other`. `other` is swept like every class.
- SweepPlan v1: `plan_id` (SHA-256 of the canonical body), `repo`, `window` (`start`, `end`, ISO dates), `classes` (per class: `servers`, `read_tools`, `skills`), `not_connected`, `excluded_tools` (`server`, `tool`, `reason`: `write` or `unknown`), `declared_read_tools`, `resources`, `prompts`, `connected_without_read`, `discovery` (status of each listing call), `judge_runs` (at least 2), `needs_classification` (informational), per-entry `class_source` (`override`, `declared`, `keyword`, `default`), `query_seeds`, `judges` (name and SHA-256 of each rubric).
- Evidence manifest v1, written by the agent at `<run-dir>/evidence.json`: `plan_id`, `coverage` rows, `items` (`id`, `class`, `server` (a server or a skill routing that class), `locator`, `thread`, `visibility` (`public` or `private`), `date`, `path` under `<run-dir>/evidence/`, optional `metrics` (change metrics such as commits, revisions, review rounds, hours to first review, days open, idle days, lines and files changed, CI runs and failures, and booleans for linked issue, test changes, description context, stacked; work-item metrics such as days open, days unassigned, days since activity, comments, reopen count, and booleans for assigned, prioritized, linked change)). Coverage rows carry `consent: granted` for any class with private items.
- EvidenceIndex v1: `index_id`, `plan_id`, items with `sha256`, `bytes`, and `metrics`, `batches` (`batch_id`, ordered item ids, their metrics), `coverage`, `metric_thresholds` (nearest-rank 90th percentile per numeric metric reported by at least five items).
- Rows file v1: `index_id`, `judge`, `run`, `batch_id`, `findings` (possibly empty). Finding: `batch_id`, `finding_id`, `incident` (kebab key), `type` (`human-human`, `human-tool`, `human-process`, `human-agent`, `agent-agent`, `agent-tool`, `agent-process`, `knowledge-gap`), `pattern` (`fragmented-context`, `inconsistent-linking`, `incomplete-evidence`, `surface-switching`, `review-gate-latency`, `work-item-drift`, `shadow-work`, `lagging-indicator`, `access-barrier`, `oversized-change`, `unclear-ownership`, `missing-context`, `unstable-checks`, `other`), `evidence` (item ids in the batch), `summary` (one line, at most 240 characters), `people` (positive int), optional `repo_paths`, `suggestion` (`action`, `target`, `rationale`), and for `knowledge-gap` a `gap` object (`question`, `answer_location`: `repo`, `maintained_doc`, `chat`, `email`, `meeting`, `memory`, `person`, `unknown`; `documented`: bool).
- Aliases v1 (optional): `index_id`, `aliases` (incident key to canonical key), written by a reconciliation reader over the accepted keys.
- Sweep v1: `index_id`, `incidents` ranked, `knowledge_gaps`, `coverage`, `pattern_counts`, `friction_map` (one row per system, with outlier items), `outliers` (items above each threshold, and items missing each boolean signal), `outliers_not_computed`, `single_reader`, `incomplete` (judge, run, and batch triples never imported), `examined` counts. `friction-map.md` renders the map, gaps, missing conventions, and counts as deterministic Markdown with no free text.

Invariants: every id resolves; every path stays inside the run directory; the run directory is outside the repository; digests bind plan to index to accepted rows.

## Integrations

- MCP servers: read through harness tools by the agent only. The script never touches the network.
- Skills: the plan lists installed skills that route collection for a class (for example `memory-search`, `github`).
- skill-doctor: unchanged; its inventory still enters through `--sessions-json`.
- `bootstrap_mine.py candidates --sweep-json <sweep.json>`: adds seeds of kind `cross_source_incident`.

## Failure modes

| Mode | Behavior |
| --- | --- |
| Malformed JSON, duplicate keys, wrong schema version, path in repository | Exit 2, nothing written |
| Plan digest mismatch between plan, manifest, index, or rows | Exit 2 |
| Evidence file missing, outside run dir, over 64 KiB, not UTF-8, or date outside window | Exit 1 with every violation listed |
| Evidence file holds an email address, token-shaped secret, or private key header | Exit 1 naming the file and pattern class, never the match |
| Connected class without a coverage row, `partial` without `unread` | Exit 1 |
| Judge row cites an evidence id outside its batch, unknown judge, bad enum | Whole batch rejected, accepted file unchanged |
| Contradictory duplicate finding ids | Batch rejected |
| A judge, run, and batch triple never imported at tally | Listed under `incomplete`, exit 1 |
| A judge rubric changed after `plan` | `import` and `tally` exit 2 |
| Run directory exists and is not empty at `plan` | Exit 2 |
| Private item without granted consent | `index` exits 1 |
| A connected class with no read tool, resource, or skill | Listed under `connected_without_read`; its coverage must be `unavailable` with a reason |
| Source auth failure or rate limit during collection | Coverage `unavailable` with reason; never silent |

## Security

- Read-only authority on every source: the plan excludes tools whose names carry a write verb, and excludes unknown verbs (fail closed).
- Collected content is untrusted data. Judges receive rubric and batch files only, never authority to act.
- PII: evidence files may not hold email addresses, phone numbers, or chat user mentions; people appear as roles; HR, legal, medical, compensation, and personal threads are skipped; private channels, direct messages, and shared mailboxes need explicit user consent, recorded as `consent: granted`, or `declined` when refused.
- Judges and the reconciliation reader run with no tools beyond reading their assigned files.
- Secrets: token shapes for GitHub, Slack, AWS, and PEM headers are rejected at index time.
- Paths: run directory must resolve outside the repository; symlinks inside `evidence/` that resolve outside the run directory are rejected.

## Observability

Every subcommand prints JSON with an `examined` object. The sweep reports per-class coverage, incidents by type, corroborated count, and incomplete pairs. Metric that proves it works: count of corroborated `knowledge-gap` incidents per run, reported in the bootstrap report.

## Acceptance criteria

1. When `plan` reads a valid ToolInventory, the script shall assign every server and skill to at least one SourceClass (override, declared, keyword, else `other`), list `other` entries with no declaration and no keyword match under `needs_classification`, exclude none of them, and emit a `plan_id` that is identical across runs with identical inputs and `--today`.
2. When a tool name contains a write verb, the script shall list it under `excluded_tools` with reason `write`, and when it contains no known read or write verb, with reason `unknown` unless the inventory declares `access: "read"` with a nonempty description, in which case it shall list the tool under `declared_read_tools`; a declared read never overrides a write verb.
3. When `--class-override SERVER=CLASS` names a server, the script shall use that class for that server.
4. When the run directory resolves inside the repository, every subcommand shall exit 2 and write nothing.
5. When `index` reads a manifest whose `plan_id` differs from the plan, the script shall exit 2.
6. When an evidence item violates path, size, encoding, date window, or sensitive-pattern rules, `index` shall exit 1 and list every violation.
7. When a connected class lacks a coverage row, `index` shall exit 1.
8. When `index` succeeds, the script shall write batches whose order and ids are identical across runs with identical inputs.
9. When `import` reads rows for one batch that all validate, the script shall replace the accepted file atomically; when any row fails, it shall exit 1 and leave the accepted file byte-identical.
10. When `tally` merges agreed findings, it shall mark an incident `corroborated` only under the decision rule in the Ontology section, and rank incidents by corroborated, then knowledge-gap type first, then distinct threads, then distinct evidence count, then incident key; two items in one thread, an untracked path, or a tracked path absent from cited evidence text shall not corroborate.
11. When a judge, run, and batch triple was never imported, `tally` shall list it under `incomplete` and exit 1.
12. When `tally` sees a `knowledge-gap` incident, it shall list the gap with its disposition: `unresolved` when any `answer_location` is `person` or `unknown`, `covered` only when every location is `repo` or `maintained_doc` and every finding has `documented: true`, else `document`.
13. When `candidates` receives `--sweep-json`, it shall add one `cross_source_incident` seed per agreed incident with `disposition: candidate_unverified`, carrying no summary, target, or rationale text, and leave output unchanged without the flag.
14. The SKILL.md template shall direct Phase 2 to run the sweep across every connected class, with judges in independent agents, and the rendered SKILL.md shall stay under 500 lines and 24576 bytes.
15. The discovery lens table, the plan-file lens enum, and `bootstrap_forms.py` shall include an `institutional-knowledge` lens.
16. The bootstrap report shall carry one coverage row per source class and the knowledge gaps with dispositions.
17. When `import` reads a finding with a missing or unknown `pattern`, the script shall reject the batch; when `tally` succeeds, it shall report per-incident `patterns` and a top-level `pattern_counts` holding every pattern value, zero included.
18. When two runs of a judge on a batch do not reach the same type on overlapping evidence, `tally` shall list the finding under `single_reader` and exclude it from incidents and seeds.
19. When `plan` reads inventory resources, it shall list them as read routes and not report their class as `connected_without_read`.
20. When `tally` succeeds, it shall write a `friction_map` row per system with every pattern counted and a `friction-map.md` that is byte-identical across runs with identical inputs.
21. The SKILL.md template's Authority paragraph and the discovery Privacy section shall name the run directory, its empty start, and its deletion at run end.
22. When an evidence item carries a metric key outside the allowed set or a value of the wrong type, `index` shall exit 1.
23. When at least five items report a numeric metric, `index` shall store its nearest-rank 90th-percentile threshold, and `tally` shall list the items strictly above it; with fewer than five, `tally` shall list the metric under `outliers_not_computed`. No threshold shall be a hard-coded external value.
24. The judges directory shall hold a change-review rubric covering size and scope, ownership, context, tests and checks, responsiveness, and work items, judged against the project's stated practice.

## Out of scope

- Calling any MCP server from a script.
- Writing to any source (posting, labeling, reacting, marking read).
- Free-text similarity clustering computed by the script; incident keys come from judges.
- Review-outcome clustering from PR exports (issue #7155).

## Deferred

- A judge calibration set with gold findings (owner: repository owner, after first real runs).
- Provider-specific normalizers that turn raw MCP responses into evidence files (owner: repository owner, if hand collection proves noisy).

## Open questions

- None blocking. Default window 180 days and batch size 20 are tunable flags.

## CVA summary

Common: every source yields items with a locator, date, and text; every judge maps a batch to findings; every finding cites evidence. Variable: source class, read tools, judge rubric, gap fields. Relationship: plan constrains manifest, manifest feeds index, index constrains rows, rows feed tally, tally feeds `candidates`.

## Buy-vs-build decision

Core-vs-context: context (discovery plumbing). Alternatives: reuse skill-doctor `audit_batches.py` directly (rejected: its rows are session scorer rows bound to an inventory schema, and skill scripts do not import across skills); extend `bootstrap_friction.py` hosted kinds (rejected: kinds are count signals, not judged content). Recommendation: build a sibling script that copies the batch pattern. Rationale: the contract is small and stdlib-only.

## Complexity classification

Tier 3. Domain: Complicated (known pattern from skill-doctor, new sources). Methodology: spec, plan, test-first build, independent review.

## Tasks (sequenced)

See `.project-toolkit/plans/active/REQ-049-skill-bootstrap-cross-source-friction.md`.
