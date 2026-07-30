# Phases 3 and 4: Propose and Persist Learnings (Detailed)

SKILL.md Process steps 3 and 4 point here for the proposal display format,
user-response handling, persistence strategy, memory format, and the Phase 4
auto-citation capture.

### Phase 3: Propose Learnings

Present findings using WCAG AA accessible colors (4.5:1 contrast ratio):

```text
┌─────────────────────────────────────────────────────────────┐
│ SKILL REFLECTION: {skill-name}                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [HIGH] + Add constraint: "{specific constraint}"            │
│   Source: "{quoted user correction}"                        │
│                                                             │
│ [MED]  + Add preference: "{specific preference}"            │
│   Source: "{evidence from conversation}"                    │
│                                                             │
│ [MED]  + Add edge case: "{scenario}"                        │
│   Source: "{question or workaround}"                        │
│                                                             │
│ [LOW]  ~ Note for review: "{observation}"                   │
│   Source: "{pattern observed}"                              │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Apply changes? [Y/n/edit]                                   │
└─────────────────────────────────────────────────────────────┘
```

**Color Key** (accessible):

- `[HIGH]` - Red/bold: Mandatory corrections (user explicitly said "no")
- `[MED]` - Yellow/amber: Recommended additions
- `[LOW]` - Blue/dim: Notes for later review

**User Response Handling**:

| Response | Action |
|----------|--------|
| **Y** (yes) | Proceed to Step 4 (update memory) |
| **n** (no) | Abort update, ask "What would you like to change or was this not useful?" |
| **edit** | Present each finding individually, allow user to modify/reject each one |

**On rejection (n)**:

1. Log that reflection was declined (for future pattern analysis)
2. Ask user if they want to revise the analysis or skip entirely
3. If skip, end workflow without memory update

**On edit**:

1. Present first finding with options: [keep/modify/remove]
2. If modify, accept user's revised text
3. Repeat for each finding
4. Confirm final list before applying

### Phase 4: Persist Learnings to Memory

**ALWAYS show changes before applying.**

After user approval:

1. **Read existing memory** (if exists)
2. **Append new learnings** with timestamp and session reference
3. **Preserve existing content** - never remove without explicit request
4. **Extract code citations** (Phase 4 Enhancement - see below)
5. **Write to file**: `.serena/memories/{skill-name}-observations.md`

**Storage Strategy**:

1. **Serena MCP (canonical)**:

   ```text
   mcp__serena__write_memory(memory_file_name="{name}-observations", memory_content="...")
   ```

2. **If Serena unavailable** (contingency):

   ```bash
   path=".serena/memories/{name}-observations.md"
   # Append new learnings to existing file (create if missing)
   echo "$newLearnings" >> "$path"
   git add "$path"
   git commit -m "chore(memory): update {name} skill sidecar learnings"
   ```

   Record the manual edit in the session log so Serena MCP can replay the update when the service is available again.

**Memory Format**:

```markdown
# Skill Sidecar Learnings: {Skill Name}

**Last Updated**: {ISO date}
**Sessions Analyzed**: {count}

## Constraints (HIGH confidence)

- {constraint 1} (Session {N}, {date})
- {constraint 2} (Session {N}, {date})

## Preferences (MED confidence)

- {preference 1} (Session {N}, {date})
- {preference 2} (Session {N}, {date})

## Edge Cases (MED confidence)

- {edge case 1} (Session {N}, {date})
- {edge case 2} (Session {N}, {date})

## Notes for Review (LOW confidence)

- {note 1} (Session {N}, {date})
- {note 2} (Session {N}, {date})
```

#### Phase 4 Enhancement: Auto-Citation Capture

When persisting learnings that reference specific code locations, capture
citations in the memory body. There is no command that adds a citation; the
citation is markdown you write.

1. **Detect code references** in learning text:
   - Inline code references: `` `path/to/file.ext` line N ``
   - Function references: `` `functionName()` in `file.ext` ``
   - Explicit citations: "See: file.ext:42"

2. **Extract the target**: the file path, or the issue, PR, or ADR identifier

3. **Write the citation into the memory body**, not the frontmatter:

   ```markdown
   ## Citations

   [cite:file](path/to/file.ext) - what this reference establishes
   ```

   Valid `source_type` values are `file`, `function`, `issue`, `pr`, `adr`,
   `memory`, `url`. A `citations:` list in YAML frontmatter is not parsed.

4. **Verify what you wrote**:

   ```bash
   python -m memory_enhancement verify --memory-id <memory-id>
   ```

   The memory id is the path under `.serena/memories/` without `.md`, so a
   memory at `.serena/memories/testing/foo.md` has the id `testing/foo`. Exit
   code 1 means a citation did not resolve.

**Detection Patterns**:

| Pattern | Example | Extraction |
|---------|---------|------------|
| Inline code + line | In `` `src/client/constants.ts` line 42 `` | target=src/client/constants.ts |
| Function in file | `` `handleError()` in `src/utils.ts` `` | target=src/utils.ts |
| Explicit citation | See: src/api.py:100 | target=src/api.py |

A citation target may be a bare path, `path:LINE`, or `path::function`. A bare
path must exist and `:LINE` must be within the file's length. The `::function`
check is a text search rather than a parser: it passes when the file contains
`def name` or `async def name` anywhere, including inside a comment or a
string, and it never looks at the file extension.

So prefer `::function` over `:LINE` for a Python function or method. `:LINE`
is only checked against the file's length, so an edit above it keeps passing
while pointing at different content, and it fails only once the file gets
shorter than the cited line. A name survives both. Cite
`path` or `path:LINE` for anything else. A TypeScript, C#, or Go function is
reported stale even though it exists, and so is a Python class, because none of
them is preceded by `def`. A name containing a character outside
`[A-Za-z0-9_]`, such as the hyphen in a PowerShell `Get-Thing`, fails the
target format outright and is reported broken. Both make `health` exit 1.

**Integration Point**:

After user approves learnings (step 4 above), before writing to Serena:

1. Parse learning text for code references using patterns above
2. For each reference found, append a `[cite:...]` line to the memory body
3. If no code reference is found, proceed without citations (non-blocking)
4. Proceed with normal Serena MCP write
5. Run `verify --memory-id <memory-id>` and report any `[FAIL]` line

**Example**:

Learning text: "The bug was in `scripts/health.py` line 45, where we forgot to handle None"

1. Extract: target=scripts/health.py
2. Append to the memory body:

   ```markdown
   ## Citations

   [cite:file](scripts/health.py) - line 45 missed the None case
   ```

3. Write learning to Serena, then verify it resolves
