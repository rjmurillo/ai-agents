---
id: ADR-126
status: accepted
date: 2026-11-25
decision-makers:
  - rjmurillo
supersedes: []
superseded-by: null
explainer: null
implemented: true
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
- The `memory_enhancement` package ships only in the Claude plugin's `lib/`
  (ADR-109 amendment 2026-11-20); the memory skill ships to five more trees.
  A shipped script may import only the standard library, a declared dependency,
  its tree's `lib/`, or a module beside it (import-closure gate, issue #7221).
  The package ships only in `lib/`, so the skill keeps its own copy.
  The gate also accepts a folder a script puts on `sys.path` through the
  `dirname(__file__)` idiom, so `store_resolution.py` shares that copy.
  Two source copies of the root and store rules exist.
  (Amended 2026-11-25; this record first said three.)
- Recalled text enters model context. It must arrive as data.

## Prior Art Investigation

### What Currently Exists

- ADR-106 (accepted, 2026-09-08) names `.serena/memories/` as the only backend.
- `.project-toolkit/memory/episodes/` holds the ADR-038 episode tier. ADR-106
  Decision 2 leaves it untouched.
- `repository_memory_dir` in `scripts/memory_enhancement/stores.py` picks the store.
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
the memory skill's cross-reference script, `test_memory_size.py`, and
`measure_memory_performance.py`. They default to `.serena/memories`.
`memory-consolidate` drives `memory_git_targets.py` and `curating-memories`
drives `supersession_sweep.py`, so both are Serena-layout skills too.

**3. Identity is the path under the resolved folder.** This amends ADR-106
Decision 5. In this repository the resolved folder is `.serena/memories/`, so
existing identities do not change.

**4. One root rule and one store rule.** A repository root is the nearest
ancestor holding `.git`, `.serena/memories`, or `.project-toolkit/memory`.
Search starts from `CLAUDE_PROJECT_DIR` when the host sets it, else from the
current directory. Each rule exists in two source copies, one per import
boundary. The build mirrors the skill copy into each harness tree.

- `scripts/memory_enhancement/stores.py`: `find_memory_root`,
  `repository_memory_dir`, and `shadowed_notes_dir`. The prompt recall hook
  (both entry points), SessionEnd, and the CLI use it; the hook adds Decision 7.
- `src/claude/skills/memory/memory_core/memory_store.py`: `find_memory_root`
  and `resolve_memory_store`. The shipped router uses it.

`src/claude/skills/memory/scripts/store_resolution.py` holds no copy. It sits
beside `search_memory.py` and adds `resolve_stores`, which also reports
shadowed notes. It imports `STORE_DIRS`, `contained_stores`,
`find_memory_root`, and `project_start` from `memory_core.memory_store`. It
reaches `memory_core` by putting its skill folder on `sys.path` through the
`dirname(__file__)` idiom, which the import-closure gate accepts.

The skill copy does not live in `lib/`. The memory skill ships to five trees
with no `memory_enhancement`. The lib bootstrap also fails when
`CLAUDE_PLUGIN_ROOT` points at another plugin. The CLI takes its root from
`--repo-root` and picks its default folder with `repository_memory_dir`.

**5. The prompt recall hook frames recalled text as data.** Its block says
excerpts are data and must not be followed as instructions. Excerpts are
collapsed to one line, so a note cannot forge a heading or a `Source:` line.
`search_memory.py` and `memory_router` return structured fields, and the
`memory-search` skill frames their content as evidence to verify.

**6. Unchanged.** ADR-106 Decisions 1, 3, 4, 6, and 7 stand. The episode tier
stays under ADR-038. ADR-063's decomposition stands: it decides which sub-skill
does what, not where the store lives, so it is not amended.

**7. The prompt recall hook keeps ADR-109's trust boundary.** The hook ships to
Claude plugin installs under ADR-109's 2026-11-20 amendment, which treats memory
as untrusted repository content. It finds its root with Decision 4's rule, then
recalls only when that root itself holds `.git`. The nearest marker wins first,
so an untracked memory folder nested inside a work tree shadows the checkout
above it, and recall then prints a `recall skipped` note and returns nothing. A
`.git` file, as in a linked worktree or a submodule, counts. A tree with no
`.git`, such as an unpacked tarball, gets no recall, while search, the router,
and the CLI still read its store. The hook refuses, with a note, a Serena folder
that resolves outside the repository, and then recalls nothing, even when a
notes folder exists. A linked memory file that leaves its store is skipped
without a note, on every entry point. Otherwise its store follows Decision
1, so a consumer with only the notes folder gets recall from it. This amends by
reference ADR-109's statement that a repository without `.serena/memories/` gets
no output.

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

- Two source copies of the root and store rules exist because the package
  ships only in the Claude lib while the skill ships to five more trees (see Decision 4). The
  parity tests are the only guard.
- Corpus maintenance scripts still assume the Serena layout (Decision 2). In a
  notes-only repository, `supersession_sweep.py` stops with
  `root not found: .serena/memories`, so `curating-memories` cannot run there.
- Creating `.serena/memories/` in a repository that has notes shadows them.
  A Serena write can create that folder. No tool migrates the notes; the
  diagnostic names the `git mv` step.
- Prose that named `.serena/memories/` as the only store had to change across
  agent and skill templates.
- Rollback to Serena only means removing the notes branch from the two
  store-rule copies, `store_resolution.resolve_stores`, and the hook.
  `resolve_stores` reads notes and computes the shadow on its own. Serena identities do not move, so nothing in
  `.serena/memories/` changes; notes written meanwhile need a `git mv`. The
  hook keeps Decision 7's `.git` rule either way.

### Neutral

- The episode tier and its path are unchanged.

## Security Considerations

ADR-106's Security Considerations apply to `.project-toolkit/memory/notes/`
unchanged. Notes are committed files a branch can change, so recalled text is
untrusted data. A store the resolver finds that resolves outside the repository
root is ignored by both store-rule copies. `resolve_stores` also skips a
default episode store that resolves outside the root. A linked memory file (a file
symlink) counts only when it resolves inside its own store, in the search script, the router, and the
loader the hook uses, so a committed link cannot surface another repository file
such as `.env`. The corpus walk does not enter a linked folder: `rglob` returned
no files under one on Python 3.14.8 and 3.15.0. The data framing is advisory: the model may still follow text
in a note. `MAX_BLOCK_CHARS` (8000), at most 3 results, and one-line snippets
bound what one prompt can carry. The recall hook is stricter still: an escaping Serena folder
stops recall entirely (Decision 7). A path the caller passes explicitly, such as
`--serena-path`, is trusted as given.

## Confirmation

`tests/skills/memory/test_memory_root_parity.py` confirms the decisions:

- `test_hook_and_skill_choose_the_same_root` runs four layouts through both
  root-rule copies and the recall hook's root (Decisions 4 and 7).
  `store_resolution` re-exports the skill copy, so its assert adds no leg.
- `test_hook_recalls_notes_only_inside_a_checkout`, and in
  `tests/test_memory_recall_limits.py`
  `test_a_project_dir_with_no_git_ancestor_recalls_nothing` and
  `test_a_symlinked_memories_dir_notes_the_directory_and_reason`, check the
  recall hook's trust boundary (Decision 7).
- `test_every_picker_chooses_the_same_store` runs five layouts, including an
  empty Serena folder beside notes, through both store-rule copies and the
  search script, and
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
- `test_recall_snippet_cannot_forge_a_heading_or_source_line` checks Decision 5.
- In `tests/skills/memory/test_memory_store_containment.py`,
  `test_search_script_refuses_a_link_to_a_repository_file`,
  `test_router_refuses_a_link_to_a_repository_file`,
  `test_loader_bounds_links_to_the_store`, and
  `test_search_script_skips_the_env_link_end_to_end` check linked-file
  containment, and `test_recall_fails_open_when_store_resolution_raises` checks
  that a resolve error never fails a prompt.
- `test_recall_accepts_a_git_file_as_in_a_linked_worktree` checks that a `.git`
  file counts, and the `notes-nested-in-outer-git` layout in
  `test_hook_and_skill_choose_the_same_root` checks that the nearest marker wins.

## Amendment 2026-11-25

Branch `fix/agent-readiness-signals` commit `3ed94c402` (2026-11-24) changed
`store_resolution.py`. It now imports the store rule from
`memory_core.memory_store` instead of keeping a third copy. It reaches
`memory_core` through a skill-root `sys.path` insert. The import-closure gate
(`build/scripts/import_closure.py:25-31`, enforced by `sys_path_inserts` at
`build/scripts/import_closure_paths.py:59`) accepts that idiom. Forces, Decision
4, Consequences, Security, and Confirmation now say two copies. No decision
changed. The lib bootstrap is still avoided for the reason Decision 4 gives.

## Impact on Dependent Components

| Component | Impact | Action |
|-----------|--------|--------|
| ADR-106 | Decisions 2 and 5 amended by reference | `**Amended by**:` footer added; body unchanged |
| ADR-109 | 2026-11-20 amendment's no-output statement amended by reference | `**Amended by**:` footer added; body unchanged |
| Memory skills and agent templates | Named one folder | Reworded in this change to name the resolved folder |
| `search_memory.py`, `memory_router`, recall hooks, CLI | Implement Decisions 1, 4, and 5 | Done in this change |

## Implementation Notes

Branch `t3/7cbd5e13` implements every decision. Decision 3 needs no code:
`memory_id_from_path` in `serena_integration.py` already builds identity
relative to the folder it is given. Of the implementing code, `search_memory.py`
with `store_resolution.py`, and `memory_router.py` with `memory_store.py`, ship
to plugin installs. The package, with the recall hook and `stores.py`, ships in the
Claude plugin's `lib/`; SessionEnd and the CLI run only in this repository.

## Related Decisions

- ADR-109: Template-first plugin distribution. Its 2026-11-20 amendment ships the
  recall hook and sets its trust boundary; this record amends its no-output
  statement by reference.
- ADR-106: Serena-only memory architecture. Decisions 2 and 5 amended here.
- ADR-038: Reflexion memory schema. Episode tier, unchanged.
- ADR-063: Memory skill decomposition. Unchanged; see Decision 6.

## References

- `scripts/memory_enhancement/stores.py`
- `src/claude/skills/memory/scripts/store_resolution.py`
- `src/claude/skills/memory/memory_core/memory_store.py`
- `src/claude/skills/memory/scripts/search_memory.py`
- `src/claude/skills/memory/memory_core/memory_router.py`
- `tests/skills/memory/test_memory_root_parity.py`
