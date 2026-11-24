---
id: ADR-126
status: proposed
date: 2026-11-23
decision-makers:
  - rjmurillo
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-126: Repository-Resolved Memory Store

## Context

ADR-106 Decision 2 makes Serena the only memory backend: committed Markdown
under `.serena/memories/`. Decision 5 makes a memory's identity its path under
that folder. Both hold for this repository.

The memory skills also ship to other repositories through the plugin roots.
Many of those repositories have no `.serena/` folder and no Serena MCP server.
The owner set a requirement on 2026-11-23 for branch `t3/7cbd5e13`: the memory
suite must work with no MCP server and no extra configuration. Under ADR-106 as
written, a repository without `.serena/memories/` has no memory store at all.

The branch already implements a second location,
`.project-toolkit/memory/notes/`. That conflicts with ADR-106 Decision 2 as
written. This record resolves the conflict.

Forces:

- One store per repository must stay true. ADR-106 Decision 3 withdrew the
  router, deduplication, and cross-store augmentation. Two live stores would
  bring all three back.
- Serena users must keep their corpus, index files, and tools unchanged.
- The skill script `search_memory.py` and the `memory_router` module ship
  stdlib-only. Neither can import the `memory_enhancement` package, so the root
  and store rules exist in three copies each.
- Recalled text enters model context. It must arrive as data.

## Prior Art Investigation

### What Currently Exists

- ADR-106 (accepted, 2026-09-08) names `.serena/memories/` as the only backend.
- `.project-toolkit/memory/episodes/` holds the ADR-038 episode tier. ADR-106
  Decision 2 leaves it untouched.
- `scripts/memory_enhancement/__init__.py:58` defines `repository_memory_dir`.
  It returns `.serena/memories` when that folder exists, else
  `.project-toolkit/memory/notes` when that folder exists, else `None`.

### Historical Rationale

ADR-106 removed a second, embedding-based backend. The cost it removed was
reconciliation: routing, deduplication, health probing, and sync between two
stores that held different memories. It did not weigh repositories that lack
the Serena folder, because the skills then assumed this repository's layout.

### Why Change Now

The owner made MCP and configuration independence a requirement. The branch
implements it, and an accepted ADR now contradicts merge-bound code. Recording
the rule now keeps ADR-106's withdrawn router from returning through drift.

## Decision

**1. Each repository has exactly one memory store, resolved by folder.** The
store is `.serena/memories/` when that folder exists and resolves inside the
repository root, even when it is empty. Otherwise it is
`.project-toolkit/memory/notes/`, which is also where a first memory is created.
Retrieval never reads both memory folders. The episode tier is separate and
unchanged. When both folders exist and the notes folder holds Markdown, the
notes are shadowed: retrieval skips them, and the search diagnostic and the
SessionEnd summary report them with a `git mv` migration step. This amends
ADR-106 Decision 2 by reference.

**2. Serena is an optional accessor, never a requirement.** Serena MCP tools
may read and write the Serena folder when active. Search, prompt recall,
SessionEnd reporting, and the memory skills' read and write steps work on
either folder with no server. Corpus maintenance scripts that edit the indexed
Serena layout stay Serena-layout tools: `memory_git_targets.py`,
`supersession_sweep.py`, `improve_memory_graph_density.py`,
`convert_memory_references.py`, `convert_index_table_links.py`,
`invoke_memory_cross_reference.py`, `test_memory_size.py`, and
`measure_memory_performance.py`. They default to `.serena/memories`.

**3. Identity is the path under the resolved folder.** This amends ADR-106
Decision 5. In this repository the resolved folder is `.serena/memories/`, so
existing identities do not change.

**4. One root rule and one store rule.** A repository root is the nearest
ancestor holding `.git`, `.serena/memories`, or `.project-toolkit/memory`.
Search starts from `CLAUDE_PROJECT_DIR` when the host sets it, else from the
current directory. Three copies implement the root rule: `find_memory_root` in
`scripts/memory_enhancement/__init__.py:24`, `_find_checkout` in
`search_memory.py:311`, and `_find_memory_root` in
`memory_core/memory_router.py:91`. Three copies pick the store inside that root:
`repository_memory_dir` (`__init__.py:58`), `_resolve_stores`
(`search_memory.py:340`), and `resolve_memory_store` (`memory_router.py:98`).
The recall and SessionEnd hooks use the package copies. The `memory_enhancement`
CLI takes its root from `--repo-root` and picks its default folder with
`repository_memory_dir`.

**5. The prompt recall hook frames recalled text as data.** Its block says
excerpts are data and must not be followed as instructions. Excerpts are
collapsed to one line, so a note cannot forge a heading or a `Source:` line.
`search_memory.py` and `memory_router` return structured fields, and the
`memory-search` skill frames their content as evidence to verify.

**6. Unchanged.** ADR-106 Decisions 1, 3, 4, 6, and 7 stand. The episode tier
stays under ADR-038. ADR-063's decomposition stands: it decides which sub-skill
does what, not where the store lives, so it is not amended.

**Out of scope.** Shipping the prompt recall hook to plugin installs is a
separate decision. Today it runs only in this repository.

## Rationale

### Alternatives Considered

| Option | Pros | Cons | Why Not Chosen |
|--------|------|------|----------------|
| Keep ADR-106 as written and drop the notes folder | No new record; one fixed path everywhere | Memory needs Serena's layout; breaks the owner's requirement | Fails the stated requirement |
| Create `.serena/memories/` in every repository | One fixed path | Writes a vendor-named folder into repositories that do not use the vendor | Couples layout to one tool |
| Search both folders and merge results | Finds everything | Restores ADR-106's withdrawn router and deduplication | Reverses ADR-106 Decision 3 |
| Prefer Serena only when it holds memories | An empty Serena folder hides nothing | The store flips when the last Serena memory is deleted, so identities move without a change anyone made | Store choice must not depend on content |
| Choose the store with an explicit marker file | Choice is visible and deliberate | Adds configuration, which the requirement forbids | Fails the stated requirement |
| Supersede ADR-106 with a new full record | One place to read | Restates five unchanged decisions; churns every citation | Amend by reference plus an `**Amended by**:` footer is the repository convention |

### Trade-offs

A repository that holds both folders uses only the Serena one. Notes written
there before a Serena folder appears stop being searched. The diagnostic makes
that visible instead of silent.

## Consequences

### Positive

- The memory skills work in any repository with no MCP server and no setup.
- Serena users see no change in location, index, or tools.
- Parity tests, not review, catch root-rule and store-rule drift between copies.

### Negative

- Three copies of the root and store rules exist because two shipped modules
  must stay stdlib-only. The parity tests are the only guard.
- Corpus maintenance scripts still assume the Serena layout (Decision 2).
- Creating `.serena/memories/` in a repository that has notes shadows them.
  A Serena write can create that folder. No tool migrates the notes; the
  diagnostic names the `git mv` step.
- Prose that named `.serena/memories/` as the only store had to change across
  agent and skill templates.

### Neutral

- The episode tier and its path are unchanged.

## Security Considerations

ADR-106's Security Considerations apply to `.project-toolkit/memory/notes/`
unchanged. Notes are committed files a branch can change, so recalled text is
untrusted data. A store the resolver finds that resolves outside the repository
root is ignored by all three store-rule copies. A path the caller passes
explicitly, such as `--serena-path`, is trusted as given.

## Confirmation

`tests/skills/memory/test_memory_root_parity.py` confirms the decisions:

- `test_hook_and_script_choose_the_same_root` runs four layouts through all
  three root-rule copies (Decision 4).
- `test_every_picker_chooses_the_same_store` runs five layouts, including an
  empty Serena folder beside notes, through all three store-rule copies, and
  `test_every_picker_ignores_a_serena_link_outside_the_root` checks containment.
- `test_router_prefers_the_project_directory_over_the_current_directory` checks
  the start directory.
- `test_empty_serena_folder_shadows_notes_on_every_entry_point` and
  `test_search_names_the_git_mv_step_for_shadowed_notes` check the shadow rule.
- `test_search_reads_only_serena_and_reports_shadowed_notes`,
  `test_recall_hook_reads_only_serena_when_both_exist`, and
  `test_router_reads_only_serena_when_both_exist` check one store per entry
  point (Decision 1).
- `test_session_end_names_shadowed_notes` and
  `test_empty_notes_folder_is_not_reported_as_shadowed` check the shadow report.
- `test_cli_defaults_to_notes_when_no_store_exists` and
  `test_cli_prefers_serena_corpus_when_present` check the CLI default.
- `test_recall_field_cannot_forge_a_heading_or_source_line` checks Decision 5.

## Impact on Dependent Components

| Component | Impact | Action |
|-----------|--------|--------|
| ADR-106 | Decisions 2 and 5 amended by reference | `**Amended by**:` footer added; body unchanged |
| Memory skills and agent templates | Named one folder | Reworded in this change to name the resolved folder |
| `search_memory.py`, `memory_router`, recall hooks, CLI | Implement Decisions 1, 4, and 5 | Done in this change |

## Implementation Notes

Branch `t3/7cbd5e13` implements every decision. Decision 3 needs no code:
`memory_id_from_path` in `serena_integration.py` already builds identity
relative to the folder it is given. Of the implementing code, only
`search_memory.py` and `memory_router` ship to plugin installs. The hooks and the
CLI live under `scripts/` and run in this repository.

## Related Decisions

- ADR-106: Serena-only memory architecture. Decisions 2 and 5 amended here.
- ADR-038: Reflexion memory schema. Episode tier, unchanged.
- ADR-063: Memory skill decomposition. Unchanged; see Decision 6.

## References

- `scripts/memory_enhancement/__init__.py`
- `src/claude/skills/memory/scripts/search_memory.py`
- `src/claude/skills/memory/memory_core/memory_router.py`
- `tests/skills/memory/test_memory_root_parity.py`
