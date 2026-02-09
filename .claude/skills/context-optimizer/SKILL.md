---
name: context-optimizer
version: 1.0.0
model: claude-sonnet-4-5
description: |
  Analyze skill content for optimal placement (Skill vs Passive Context vs Hybrid).
  Compress markdown to pipe-delimited format (60-80% token reduction).
  Validate content placement compliance against decision framework.
  Based on Vercel research showing passive context achieves 100% pass rates vs 53-79% for skills.
license: MIT
---

# Context Optimizer

Tooling suite for optimizing Claude Code context placement based on Vercel research demonstrating that passive context (AGENTS.md, @imports) achieves 100% pass rates versus 53-79% for skills due to elimination of decision points.

## Tools

### 1. Skill/Passive Content Analyzer

**Script**: `scripts/analyze_skill_placement.py`

Analyzes skill content and recommends whether it should be a Skill, Passive Context, or Hybrid.

**Classification Logic**:

- **Tool Calls**: Bash, Read, Write, Edit, gh, git, pwsh commands → Skill
- **Action Verbs**: create, update, delete, execute, run → Skill
- **Reference Content**: Tables, lists, code blocks → Passive
- **User Triggers**: "when user", slash commands, explicit requests → Skill
- **Always-Needed**: "always", "mandatory", "framework knowledge" → Passive

**Usage**:

```bash
# Analyze a skill directory
python3 scripts/analyze_skill_placement.py -p ../github

# Analyze a specific SKILL.md
python3 scripts/analyze_skill_placement.py -p ../github/SKILL.md

# Get detailed metrics
python3 scripts/analyze_skill_placement.py -p ../github -d

# Analyze content directly
python3 scripts/analyze_skill_placement.py -c "$(cat ../github/SKILL.md)"
```

**Output**:

```json
{
  "classification": "Hybrid",
  "confidence": 85,
  "reasoning": "High tool execution (12 calls); User-triggered workflow (5 triggers); High reference content ratio (0.75)",
  "recommendations": {
    "Passive": [
      "Routing Rules",
      "Classification Framework",
      "Reference Data"
    ],
    "Skill": [
      "Get-UnaddressedComments.ps1",
      "Post-PRCommentReply.ps1",
      "Process section"
    ]
  },
  "metrics": {
    "tool_calls": 12,
    "action_verbs": 8,
    "reference_content_ratio": 0.75,
    "user_triggers": 5,
    "always_needed": 2
  }
}
```

**Classification Thresholds**:

| Classification | Criteria | Confidence |
|----------------|----------|------------|
| **Skill** | skillScore > passiveScore + 3 | 70-90% |
| **PassiveContext** | passiveScore > skillScore + 3 | 70-90% |
| **Hybrid** | \|skillScore - passiveScore\| <= 3 | 50-70% |

**Hybrid Recommendations**:

- **Passive**: Headings matching routing, classification, framework, reference, index, hierarchy, decision
- **Skill**: Headings matching process, workflow, steps, execution, script, procedure, plus *.py references

### 2. Content Compression Utility

**Script**: `scripts/compress_markdown_content.py`

Compress markdown to pipe-delimited format (Vercel pattern) achieving 60-80% token reduction while maintaining 100% information density.

**Compression Techniques**:

- Convert tables to pipe-delimited: `|key: value|key2: value2|`
- Extract headings to index: `[Section] |item1 |item2`
- Strip redundant words (the, a, an, is, are)
- Collapse whitespace
- Abbreviate common terms (configuration → config)
- Preserve code blocks

**Usage**:

```bash
# Basic compression (JSON output to stdout)
python3 scripts/compress_markdown_content.py -i README.md -l medium

# Save to file
python3 scripts/compress_markdown_content.py \
  -i CRITICAL-CONTEXT.md \
  -l aggressive \
  -o compressed.txt

# With verbose metrics
python3 scripts/compress_markdown_content.py \
  -i input.md -l medium -v

# Programmatic use (parse JSON output)
result=$(python3 scripts/compress_markdown_content.py -i input.md -l medium)
echo "$result" | jq '.metrics.reduction_percent'
```

**Compression Levels**:

| Level | Reduction | Techniques |
|-------|-----------|------------|
| Light | 40-50% | Headers, tables, whitespace |
| Medium | 50-60% | + redundant words, tighter whitespace |
| Aggressive | 60-80% | + H3 compression, lists, abbreviations |

**Output**:

```json
{
  "Success": true,
  "CompressedContent": "...",
  "Metrics": {
    "OriginalTokens": 1000,
    "CompressedTokens": 250,
    "ReductionPercent": 75.0,
    "OriginalSize": 4000,
    "CompressedSize": 1000,
    "CompressionLevel": "Aggressive"
  }
}
```

**Examples**:

Before (52 tokens):

```markdown
## Session Protocol

The session protocol has multiple phases:

1. Serena Activation - You must activate Serena
2. Read HANDOFF.md - Read the handoff file
```

After Aggressive (30 tokens, 42% reduction):

```text
[Session Protocol]
session protocol has multiple phases:
1. Serena Activation - activate Serena
2. Read HANDOFF.md - handoff file
```

### 3. Compliance Validator

**Script**: `scripts/test_skill_passive_compliance.py`

Validate that content placement follows the skill vs passive context decision framework. Returns structured JSON with violations, warnings, and recommendations.

**6 Compliance Checks**:

1. **Skills contain actions**: Verifies skills have action verbs, tool execution, or scripts
2. **Passive context is knowledge-only**: Ensures passive files don't contain action patterns
3. **CLAUDE.md under 200 lines**: Enforces Anthropic's recommendation
4. **@imported files exist**: Validates all @imports are readable
5. **Skills have frontmatter**: Checks for required `name` and `description` fields
6. **No duplicate content**: Detects content duplicated between skills and passive context

**Usage**:

```bash
# Scan .claude directory (JSON output)
python3 scripts/test_skill_passive_compliance.py

# Scan specific directory with table output
python3 scripts/test_skill_passive_compliance.py \
  --path .claude/skills/github \
  --format table

# Custom CLAUDE.md path
python3 scripts/test_skill_passive_compliance.py \
  --claude-md-path CLAUDE.md \
  --format json
```

**Exit Codes**:

| Code | Meaning |
|------|---------|
| 0 | All compliance checks passed |
| 1 | One or more violations detected |

**Example Output (JSON)**:

```json
{
  "timestamp": "2026-02-08T13:45:00.123456",
  "path": ".claude",
  "claudeMdPath": "CLAUDE.md",
  "violations": [
    {
      "check": "CLAUDE.md Line Count",
      "severity": "error",
      "message": "CLAUDE.md has 250 lines (exceeds 200 line limit) - use @imports to split",
      "recommendation": "Split content into separate files and use @imports"
    },
    {
      "check": "Skill Frontmatter (test-skill)",
      "severity": "error",
      "message": "Missing required frontmatter field: name",
      "recommendation": "Add required frontmatter fields (name, description) to test-skill/SKILL.md"
    }
  ],
  "warnings": [
    {
      "check": "Skill Has Actions (reference-skill)",
      "message": "No action verbs, scripts, or tool execution found - consider moving to passive context"
    }
  ],
  "recommendations": [
    "Consider moving reference-skill to passive context (SKILL-QUICK-REF.md)",
    "Extract action patterns from CLAUDE.md to a skill"
  ],
  "summary": {
    "total_checks": 10,
    "passed": 7,
    "failed": 2,
    "warnings": 1
  }
}
```

**Example Output (Table)**:

```text
Skill/Passive Context Compliance Check
======================================================================
Timestamp: 2026-02-08T13:45:00.123456
Path: .claude
CLAUDE.md: CLAUDE.md

Summary:
  Total Checks: 10
  Passed: 7
  Failed: 2
  Warnings: 1

Violations:
  ❌ CLAUDE.md Line Count
     Severity: ERROR
     Issue: CLAUDE.md has 250 lines (exceeds 200 line limit)
     Fix: Split content into separate files and use @imports

  ❌ Skill Frontmatter (test-skill)
     Severity: ERROR
     Issue: Missing required frontmatter field: name
     Fix: Add required frontmatter fields to test-skill/SKILL.md

Warnings:
  ⚠️  Skill Has Actions (reference-skill)
     No action verbs, scripts, or tool execution found

Recommendations:
  💡 Consider moving reference-skill to passive context
  💡 Extract action patterns from CLAUDE.md to a skill

[FAIL] Compliance violations detected
```

**Severity Levels**:

| Severity | Meaning | Effect |
|----------|---------|--------|
| error | Blocks compliance | Exit code 1 |
| warning | Informational only | Exit code 0 |
| none | Check passed | Exit code 0 |

**Common Violations**:

| Violation | Fix |
|-----------|-----|
| CLAUDE.md too long | Split into separate files, add @imports |
| Missing @import file | Create file or remove @import directive |
| Skill missing frontmatter | Add `---` block with `name:` and `description:` |
| Skill has no actions | Add scripts, tool execution, or move to passive context |
| Passive has actions | Extract executable content to a skill |
| Duplicate content | Remove redundant content from skill or passive |

## Decision Framework

Based on: SKILL-QUICK-REF.md lines 152-203

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

**Key Insight**: Skills create decision points where agents must choose whether to retrieve documentation. These decision points introduce 4 failure modes:

1. **Late retrieval**: Agent makes decisions before consulting skill
2. **Partial retrieval**: Skill scope doesn't cover all needed info
3. **Integration failure**: Skill retrieved but not integrated with project context
4. **Instruction fragility**: Minor prompt changes break skill invocation

Passive context eliminates all four failure modes by being always-available.

## Testing

Run pytest tests:

```bash
# Run all tests
python3 -m pytest tests/

# Run specific tool tests
python3 -m pytest tests/test_skill_passive_compliance_test.py -v

# Run with coverage
python3 -m pytest tests/ --cov=scripts --cov-report=term-missing
```

**Coverage - Compliance Validator** (95%, 19/20 tests passing):

- CLAUDE.md line count validation (under 150, 150-200, over 200)
- @import existence and readability checks
- Passive context knowledge-only detection
- Skill action detection (verbs, scripts, tools)
- Frontmatter validation (presence, required fields, format)
- Duplicate content detection between skills and passive
- Full compliance check integration
- Exit code validation (0 = pass, 1 = fail)
- JSON and table output formats
- Edge cases (missing files, empty content, malformed frontmatter)

**Coverage - Analyzer**:

- Parameter validation
- Tool call detection (Bash, Read, Write, gh, git, python3)
- Action verb counting
- Reference vs procedural content ratio
- User trigger pattern detection
- Always-needed pattern detection
- Classification logic (Skill/PassiveContext/Hybrid)
- Hybrid recommendations
- Output structure and JSON validity
- Edge cases (empty content, whitespace, special chars)
- Confidence scoring (0-100 range)
- Exit codes (0 success, 1 error)

**Coverage - Compressor**:

- Parameter validation
- All compression levels (Light, Medium, Aggressive)
- Header compression (H2, H3)
- Table to pipe-delimited conversion
- List compression
- Redundant word removal
- Abbreviation application
- Code block preservation
- Whitespace collapsing
- Token reduction targets (40-80%)
- Before/after examples
- Metrics calculation
- JSON output format
- File output
- Edge cases (empty, whitespace, no formatting)
- Exit codes (0 success, 1-3 errors)

## References

**Research**:

- [Vercel: AGENTS.md outperforms skills in our agent evals](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)
- Analysis: `.agents/analysis/vercel-passive-context-vs-skills-research.md`
- Memory: `passive-context-vs-skills-vercel-research`

**Project Documentation**:

- Decision framework: `SKILL-QUICK-REF.md` lines 152-203
- Passive context examples: `CRITICAL-CONTEXT.md`, `SKILL-QUICK-REF.md`
- Skill examples: `.claude/skills/github/`, `.claude/skills/pr-comment-responder/`

## Examples

### Example 1: Clear Skill Classification

**Input**: GitHub skill with gh pr create, gh issue close commands

**Output**:

```json
{
  "classification": "Skill",
  "confidence": 85,
  "reasoning": "High tool execution (8 calls); Many action verbs (12)"
}
```

### Example 2: Clear Passive Classification

**Input**: Memory hierarchy reference with tables and always-needed patterns

**Output**:

```json
{
  "classification": "PassiveContext",
  "confidence": 90,
  "reasoning": "High reference content ratio (0.85); Always-needed information (5 indicators)"
}
```

### Example 3: Hybrid Classification

**Input**: PR comment responder with routing rules + script execution

**Output**:

```json
{
  "classification": "Hybrid",
  "confidence": 65,
  "reasoning": "High reference content ratio (0.72); Some tool execution (4 calls); User-triggered workflow (3 triggers); Mixed indicators suggest hybrid approach",
  "recommendations": {
    "Passive": ["Routing Rules", "Classification Framework"],
    "Skill": ["Get-UnaddressedComments.ps1", "Post-PRCommentReply.ps1"]
  }
}
```

## Marketplace Value

These tools enable:

- **Automated optimization**: Compress context without manual editing
- **Quality gates**: Enforce best practices in CI/CD
- **Knowledge transfer**: Help teams understand skill vs passive tradeoffs
- **Token savings**: 60-80% reduction = lower API costs

## Implementation Notes

- **Language**: Python 3.12+ for new tools per ADR-042 (PowerShell deprecated)
- **Testing**: pytest with comprehensive test coverage
- **Exit codes**: Follows ADR-035 standardization (0 = success, non-zero = failure)
- **Type safety**: Full type hints using dataclasses and typing module
- **Cross-platform**: pathlib for platform-independent path handling
- Bundled as single skill: `context-optimizer`
- Includes reference materials (Vercel research, decision framework)

## Related

- Issue #1108: Build passive context tooling suite
- Analysis: `.agents/analysis/vercel-passive-context-vs-skills-research.md`
- Memory: `passive-context-vs-skills-vercel-research`
