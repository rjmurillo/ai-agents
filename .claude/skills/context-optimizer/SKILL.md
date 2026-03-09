---
name: context-optimizer
version: 1.1.0
model: claude-sonnet-4-5
description: |
  Analyze skill content for optimal placement (Skill vs Passive Context vs Hybrid).
  Compress markdown to pipe-delimited format (60-80% token reduction).
  Validate content placement compliance against decision framework.
  Based on Vercel research showing passive context achieves 100% pass rates vs 53-79% for skills.
license: MIT
user-invocable: true
---

# Context Optimizer

Tooling suite for optimizing Claude Code context placement. Passive context (AGENTS.md, @imports) achieves 100% pass rates versus 53-79% for skills by eliminating decision points.

## Triggers

- `analyze skill placement` - classify content as Skill vs Passive Context
- `compress markdown` - reduce token count for context files
- `validate compliance` - check skill/passive context placement decisions
- `optimize context` - lower API costs and improve agent performance
- `extract and index` - split markdown into detail files with compact index

## Process

1. **Analyze**: Run `analyze_skill_placement.py` to classify content
2. **Compress**: Run `compress_markdown_content.py` to reduce token counts
3. **Validate**: Run `test_skill_passive_compliance.py` to check compliance
4. **Verify**: Confirm output JSON contains expected classification and metrics

## Verification

- [ ] Classification matches expected type (Skill/PassiveContext/Hybrid)
- [ ] Compression achieves target reduction (40-80% depending on level)
- [ ] Compliance validator returns exit code 0
- [ ] Output JSON is valid and contains all required fields

## Scripts

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `analyze_skill_placement.py` | Classify content as Skill/PassiveContext/Hybrid | 0=success, 1=error |
| `compress_markdown_content.py` | Compress markdown with token reduction metrics | 0=success, 1=error, 2=config, 3=external |
| `test_skill_passive_compliance.py` | Validate compliance with decision framework | 0=pass, 1=violations |
| `extract_and_index.py` | Extract sections into detail files with pipe-delimited index | 0=success, 1=error, 2=config, 3=external |
| `path_validation.py` | Shared CWE-22 repo-root-anchored path validation | N/A (library module) |

## Prerequisites

Python 3.12+ with `tiktoken` for local token counting:

```bash
uv pip install -e ".[dev]"   # includes tiktoken
pip install tiktoken           # or install directly
```

`tiktoken` is an offline tokenizer (cl100k_base encoding). No API key required. For exact Claude token counts, set `ANTHROPIC_API_KEY`.

## Decision Framework

### Use Passive Context For

- Framework knowledge (APIs, patterns, conventions)
- Always-needed information (constraints, protocols, gates)
- Domain concepts (terminology, relationships)
- Routing rules (comment classification, agent selection)
- Reference data (memory indexes, skill catalogs)

### Use Skills For

- Tool-based actions (file modification, API calls, git operations)
- User-triggered workflows (PR creation, issue management)
- Multi-step procedures (conflict resolution, session completion)
- Actions requiring validation (security scans, linting)
- Versioned, team-reviewed instructions across projects

### Hybrid Pattern

- Knowledge in passive context (routing, classification)
- Actions in skill (script execution, state changes)
- Example: pr-comment-responder has routing in SKILL-QUICK-REF.md, scripts in skill

## Why This Matters

| Configuration | Pass Rate |
|---------------|-----------|
| Baseline (no docs) | 53% |
| Skill (default) | 53% |
| Skill + explicit instructions | 79% |
| **AGENTS.md passive context** | **100%** |

Skills create decision points where agents must choose whether to retrieve documentation. These introduce 4 failure modes: late retrieval, partial retrieval, integration failure, and instruction fragility. Passive context eliminates all four by being always-available.

## References

- [Vercel: AGENTS.md outperforms skills](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)
- Analysis: `.agents/analysis/vercel-passive-context-vs-skills-research.md`
- Memory: `passive-context-vs-skills-vercel-research`
- Decision framework: `SKILL-QUICK-REF.md` (see the "Decision Framework" section)

## Related

- Issue #1108: Build passive context tooling suite

<details>
<summary><strong>Tool Details: Skill/Passive Content Analyzer</strong></summary>

**Script**: `scripts/analyze_skill_placement.py`

Analyzes skill content and recommends Skill, Passive Context, or Hybrid placement.

**Classification Logic**:

- **Tool Calls**: Bash, Read, Write, Edit, gh, git, pwsh commands -> Skill
- **Action Verbs**: create, update, delete, execute, run -> Skill
- **Reference Content**: Tables, lists, code blocks -> Passive
- **User Triggers**: "when user", slash commands, explicit requests -> Skill
- **Always-Needed**: "always", "mandatory", "framework knowledge" -> Passive

**Usage**:

```bash
# Analyze a skill directory (from repo root)
python3 .claude/skills/context-optimizer/scripts/analyze_skill_placement.py -p .claude/skills/github

# Analyze a specific SKILL.md
python3 .claude/skills/context-optimizer/scripts/analyze_skill_placement.py -p .claude/skills/github/SKILL.md

# Get detailed metrics
python3 .claude/skills/context-optimizer/scripts/analyze_skill_placement.py -p .claude/skills/github -d
```

**Output**:

```json
{
  "classification": "Hybrid",
  "confidence": 85,
  "reasoning": "High tool execution (12 calls); High reference content ratio (0.75)",
  "recommendations": {
    "Passive": ["Routing Rules", "Classification Framework"],
    "Skill": ["Get-UnaddressedComments.ps1", "Post-PRCommentReply.ps1"]
  }
}
```

**Classification Thresholds**:

| Classification | Criteria | Confidence |
|----------------|----------|------------|
| **Skill** | skillScore > passiveScore + 3 | 70-90% |
| **PassiveContext** | passiveScore > skillScore + 3 | 70-90% |
| **Hybrid** | abs(skillScore - passiveScore) <= 3 | 50-70% |

</details>

<details>
<summary><strong>Tool Details: Content Compression Utility</strong></summary>

**Script**: `scripts/compress_markdown_content.py`

Compress markdown to pipe-delimited format achieving 60-80% token reduction while maintaining 100% information density.

**Compression Techniques**:

- Convert tables to pipe-delimited: `|key: value|key2: value2|`
- Extract headings to index: `[Section] |item1 |item2`
- Strip redundant words (the, a, an, is, are)
- Collapse whitespace and abbreviate common terms
- Preserve code blocks

**Usage**:

```bash
# Basic compression (JSON output to stdout)
python3 scripts/compress_markdown_content.py -i README.md -l medium

# Save to file with aggressive compression
python3 scripts/compress_markdown_content.py -i CRITICAL-CONTEXT.md -l aggressive -o compressed.txt

# With verbose metrics
python3 scripts/compress_markdown_content.py -i input.md -l medium -v
```

**Compression Levels**:

| Level | Reduction | Techniques |
|-------|-----------|------------|
| Light | 40-50% | Headers, tables, whitespace |
| Medium | 50-60% | + redundant words, tighter whitespace |
| Aggressive | 60-80% | + H3 compression, lists, abbreviations |

**Example** (26 tokens -> 18 tokens, 31% reduction):

Before:

```text
## Session Protocol

The session protocol has multiple phases:

1. Serena Activation - You must activate Serena
```

After:

```text
[Session Protocol]
session protocol has multiple phases:
1. Serena Activation - activate Serena
```

</details>

<details>
<summary><strong>Tool Details: Extract-and-Index Utility</strong></summary>

**Script**: `scripts/extract_and_index.py`

Implements the Vercel extract-and-index pattern for 60-80% token reduction. Splits markdown by headings into detail files, generates a compact pipe-delimited index.

**Usage**:

```bash
# Extract sections and output JSON to stdout
python3 scripts/extract_and_index.py -i AGENTS.md -d .agents-details

# Write index to a file
python3 scripts/extract_and_index.py -i AGENTS.md -d .agents-details -o AGENTS-INDEX.md

# Custom reference path in index
python3 scripts/extract_and_index.py -i AGENTS.md -d .agents-details -r .agents-docs -o AGENTS-INDEX.md
```

**Output Index Format** (Vercel pattern):

```text
[Architecture]
|Layered design with separation of concerns (see: .agents-details/architecture.md)
[Testing]
|80% coverage required for business logic (see: .agents-details/testing.md)
```

Works with CLAUDE.md @import mechanism. Reference via `@AGENTS-INDEX.md`.

</details>

<details>
<summary><strong>Tool Details: Compliance Validator</strong></summary>

**Script**: `scripts/test_skill_passive_compliance.py`

Validates content placement against the skill vs passive context decision framework.

**6 Compliance Checks**:

1. Skills contain actions (verbs, tool execution, scripts)
2. Passive context is knowledge-only (no action patterns)
3. CLAUDE.md under 200 lines (Anthropic recommendation)
4. @imported files exist and are readable
5. Skills have frontmatter (`name` and `description`)
6. No duplicate content between skills and passive context

**Usage**:

```bash
# Scan .claude directory (JSON output)
python3 scripts/test_skill_passive_compliance.py

# Scan specific directory with table output
python3 scripts/test_skill_passive_compliance.py --path .claude/skills/github --format table
```

**Exit Codes**: 0 = all passed, 1 = violations detected

**Common Violations**:

| Violation | Fix |
|-----------|-----|
| CLAUDE.md too long | Split into separate files, add @imports |
| Missing @import file | Create file or remove @import directive |
| Skill missing frontmatter | Add `---` block with `name:` and `description:` |
| Skill has no actions | Add scripts or move to passive context |
| Passive has actions | Extract executable content to a skill |
| Duplicate content | Remove redundant content from skill or passive |

</details>

<details>
<summary><strong>Classification Examples</strong></summary>

### Clear Skill Classification

**Input**: GitHub skill with gh pr create, gh issue close commands

{"classification": "Skill", "confidence": 85, "reasoning": "High tool execution (8 calls); Many action verbs (12)"}

```

### Clear Passive Classification

**Input**: Memory hierarchy reference with tables and always-needed patterns

```json

{"classification": "PassiveContext", "confidence": 90, "reasoning": "High reference content ratio (0.85); Always-needed information (5 indicators)"}
```

### Hybrid Classification

**Input**: PR comment responder with routing rules + script execution

```json
{
  "classification": "Hybrid",
  "confidence": 65,
  "reasoning": "High reference content ratio (0.72); Some tool execution (4 calls)",
  "recommendations": {
    "Passive": ["Routing Rules", "Classification Framework"],
    "Skill": ["Get-UnaddressedComments.ps1", "Post-PRCommentReply.ps1"]
  }
}
```

</details>

<details>
<summary><strong>Testing</strong></summary>

```bash
python3 -m pytest tests/                                          # all tests
python3 -m pytest tests/test_skill_passive_compliance_test.py -v  # specific
python3 -m pytest tests/ --cov=scripts --cov-report=term-missing  # coverage
```

**Coverage Summary**:

| Component | Tests | Key Areas |
|-----------|-------|-----------|
| Compliance Validator | 19/20 (95%) | Line count, @imports, frontmatter, duplicates, exit codes |
| Analyzer | Full | Tool calls, action verbs, classification logic, confidence scoring |
| Extract-and-Index | 36 | Slug generation, parsing, index format, 60%+ reduction targets |
| Compressor | Full | All levels, code block preservation, 40-80% reduction targets |

</details>

<details>
<summary><strong>Implementation Notes</strong></summary>

- **Language**: Python 3.12+ per ADR-042 (PowerShell deprecated)
- **Testing**: pytest with comprehensive coverage
- **Exit codes**: ADR-035 standardization (0 = success, non-zero = failure)
- **Type safety**: Full type hints using dataclasses and typing module
- **Cross-platform**: pathlib for platform-independent path handling

### Marketplace Value

- **Automated optimization**: Compress context without manual editing
- **Quality gates**: Enforce best practices in CI/CD
- **Token savings**: 60-80% reduction = lower API costs

</details>
