# Phase 0 Skill Triage

## Phase 0: Skill Triage (NEW in v4.0)

Before creating anything, SkillForge intelligently analyzes your input to determine the best action.

### How It Works

```
┌────────────────────────────────────────────────────────────────────┐
│                        ANY USER INPUT                               │
│  (prompt, error, code, URL, question, task request, anything)      │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 1: INPUT CLASSIFICATION                                       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │
│  │ explicit_create │ │ explicit_improve│ │ skill_question  │       │
│  │ "create skill"  │ │ "improve skill" │ │ "do I have..."  │       │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       │
│  │  task_request   │ │  error_message  │ │  code_snippet   │       │
│  │ "help me with"  │ │ "TypeError..."  │ │ [pasted code]   │       │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘       │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 2: SKILL ECOSYSTEM SCAN                                       │
│  • Load index of 250+ skills (discover_skills.py)                  │
│  • Match input against all skills with confidence scoring          │
│  • Identify top matches with reasons                               │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 3: DECISION MATRIX                                            │
│                                                                     │
│  Match ≥80%  + explicit create → CLARIFY (duplicate warning)       │
│  Match ≥60%  + skill question  → USE_EXISTING (recommend skill)    │
│  Match ≥80%  + other input     → USE_EXISTING (recommend skill)    │
│  Match 50-79%                  → IMPROVE_EXISTING (enhance match)  │
│  Match <50%  + explicit create → CREATE_NEW (proceed to Phase 1)   │
│  Multi-domain detected         → COMPOSE (suggest skill chain)     │
│  Ambiguous input               → CLARIFY (ask for more info)       │
└────────────────────────────────────────────────────────────────────┘
```

### Decision Actions

| Action | When | Result |
|--------|------|--------|
| **USE_EXISTING** | Match ≥80% (task, code, URL) or ≥60% (skill question) | Recommends existing skill(s) to invoke |
| **IMPROVE_EXISTING** | Match 50-79% | Loads skill and enters enhancement mode |
| **CREATE_NEW** | Match <50% | Proceeds to Phase 1 (Deep Analysis) |
| **COMPOSE** | Multi-domain | Suggests skill chain via SkillComposer |
| **CLARIFY** | Ambiguous or duplicate | Asks user to clarify intent |

### How Matches Are Scored

- Request scaffolding words ("create", "skill", "with", "for", and similar) are dropped before scoring. They describe the request, not its subject.
- Domain terms match on whole words with inflection. "test" matches "testing" and "tests", never "attest". A final consonant doubles before "ing" and "ed", so "debug" matches "debugging" and "ship" matches "shipped". "ci" never matches inside "social". Skill names and triggers follow the same rule, with hyphens read as spaces in both the skill text and the query, so the trigger `code-review` matches "do a code review". A skill name or trigger made only of scaffolding words (a skill named `build` or `make`) does not match any request except a name lookup, so "build a skill for X" and "build this feature" frame the request and never route to the `build` skill. It still matches an exact-name lookup such as "do I have a skill for build?" or "improve the build skill".
- A skill's score is discounted by coverage, the fraction of the remaining query terms that the skill name, keywords, triggers, description, or declared domain synonyms explain. The discount is half strength: a skill that explains none of the terms keeps half its score. A request of three or more terms that rests on one explained term is capped at 49, so one shared word cannot reach the 50% boundary, even after the domain-alignment and context boosts. Three cases are exempt: a lookup or improve request that names the skill exactly, a multi-word skill name that appears in the query, and an exact one-word skill name in any request that does not create a skill ("debug this flaky test" asks for the `test` skill). A one-word name inside a create request is a shared word and keeps the cap.
- Input that fits no other category and still carries three or more content terms routes to CREATE_NEW when no skill scores 50 or higher. Shorter unclear input, or a 50-69 match, routes to CLARIFY. So does unclear input that uses a word of three letters or fewer from an indexed skill name ("adr" for adr-generator): such a word earns no partial-name credit, so the low score is a recall gap, not an uncovered topic. Unclear input also routes to CLARIFY when a match under 50 still covers the topic: the query names the skill exactly, or the skill explains at least half the content terms ("resolve merge conflicts" and merge-resolver). The same check guards the create-skill request, the skill question, and the task request: a covered topic routes to CLARIFY with the covering skills, never to CREATE_NEW.
- CamelCase error class names split before scoring ("TypeError" reads as "type error"), so the debugging synonym "error" matches. A debugging-domain skill answering an error message is not held under the single-term cap, so "SyntaxError: unexpected token" reaches USE_EXISTING.
- `discover_skills.py` assigns domains from the skill name, description, and extracted keywords. Body prose is not scanned for domains. Only keyword tables and the text after a `Purpose` or `Description` line in the body feed the extracted keywords. Rebuild the index after upgrading so older domain assignments are replaced.

### Triage Script

```bash
# Run triage on any input
python scripts/triage_skill_request.py "help me debug this error"

# JSON output for automation
python scripts/triage_skill_request.py "create a skill for payments" --json

# Examples:
python scripts/triage_skill_request.py "TypeError: Cannot read property 'map'"
# → USE_EXISTING: Recommends ErrorExplainer (92%)

python scripts/triage_skill_request.py "create a skill for code review"
# → CLARIFY: CodeReview skill exists (85%), create anyway?

python scripts/triage_skill_request.py "help me with API and auth and testing"
# → COMPOSE: Multi-domain, suggests APIDesign + AuthSystem + TestGen chain
```

### Ecosystem Index

Phase 0 uses a pre-built index of all skills:

```bash
# Rebuild skill index (run periodically or after installing new skills)
python scripts/discover_skills.py

# Index location: ~/.cache/skillrecommender/skill_index.json
```

Sources scanned (`build_skill_sources()` in `discover_skills.py`):

| Source | Root |
|---|---|
| `custom` | `~/.claude/skills/` |
| `superpowers` | `~/.claude/plugins/cache/superpowers/skills/` |
| `anthropic-agent-skills`, `claude-code-workflows`, `claude-code-plugins` | `~/.claude/plugins/marketplaces/<name>/` |
| `plugin-claude` | `$CLAUDE_PLUGIN_ROOT/skills/` when set |
| `plugin-copilot` | `$COPILOT_PLUGIN_ROOT/skills/` when set |
| `plugin-local` | The skills folder that holds SkillForge |
| `extra-N` | Each `--extra-root PATH` (repeatable) |
| `env-extra-N` | Each entry of `SKILLFORGE_EXTRA_ROOTS`, separated like `PATH` (`:` on Linux and macOS, `;` on Windows) |

Other installed plugins under `~/.claude/plugins/cache/` are not scanned. Pass
each one with `--extra-root` or `SKILLFORGE_EXTRA_ROOTS`.

A skill reached through two roots is indexed once. A skill name found in several
roots is indexed once too: the root with the lowest priority number wins (the
table above lists roots in rank order), and the hidden copies are recorded in
the entry's `shadowed_paths`. Within one root, `SKILL.md` beats sibling
markdown files that share its skill name. A missing root adds a warning and the
scan continues. A plugin or extra root that exists but holds no `<root>/<skill>/SKILL.md` adds a
warning too; pass the directory whose subfolders hold `SKILL.md`, not a skill
folder itself. The script exits 3 only when every source is missing and no skill is
found. The folder that holds SkillForge is always a source, so the CLI does not
reach exit 3 while that folder exists.

### Integration with Phases 1-4

- **USE_EXISTING**: Exits early, no creation needed
- **IMPROVE_EXISTING**: Loads existing skill → Phase 1 analyzes gaps → Phase 2-4 enhance
- **CREATE_NEW**: Full pipeline (Phase 1 → 2 → 3 → 4)
- **COMPOSE**: Suggests using SkillComposer instead
- **CLARIFY**: Pauses for user input before proceeding

---
