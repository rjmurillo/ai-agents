---
name: context-optimizer
version: 1.2.0
description: Analyze skill content for optimal placement (Skill vs Passive Context vs Hybrid), compress markdown to pipe-delimited format (60-80% token reduction), and validate compliance against the decision framework. Passive context wins for what the model cannot know (post-cutoff APIs, repo gotchas); pre-trained knowledge belongs in progressive disclosure. Use when you ask "compress this skill", "Skill vs Passive Context placement", "reduce tokens". Do NOT use for gathering knowledge before a task (use context-gather).
license: MIT
user-invocable: true
allowed-tools:
  - view
  - bash
  - glob
---

# Context Optimizer

Tooling suite for optimizing Claude Code context placement. Passive context (AGENTS.md, @imports) achieves 100% pass rates versus 53-79% for skills by eliminating decision points.

## Triggers

- `analyze skill placement` - classify and validate content as Skill vs Passive Context
- `compress markdown` - reduce token count for context files
- `optimize context` - lower API costs and improve agent performance
- `extract and index` - split markdown into detail files with compact index
- `audit always-on rules` - eval-gated procedure for whether a rule earns its slot, and the doctrine behind it, in [rule-audit-procedure.md](references/rule-audit-procedure.md) and [model-context-doctrine.md](references/model-context-doctrine.md). Also the entry point when a new model ships. **Requires a full rjmurillo/ai-agents checkout**: the procedure runs this repo's eval harness and rule generator, neither of which ships in a plugin install. The doctrine and the instrument write-ups are readable anywhere; only the commands need the checkout

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

`tiktoken` is an offline tokenizer (cl100k_base encoding) that approximates Claude tokenization. No API key is required for these scripts.

## Decision Framework

The first question is not "skill or passive context." It is: **does the model already know this?**

### Passive Context Earns Its Slot Only For What The Model Cannot Know

- Repo-specific gotchas (a gate that rejects one exact string, a hook that must not be bypassed)
- Local conventions that contradict the common default
- APIs newer than the training cutoff, which is exactly what the Vercel eval measured
- Routing tables, catalogs, and protocols specific to this repository

### Keep Out Of Passive Context

- Generic engineering knowledge the model already has: SOLID, Clean Code, refactoring catalogs, testing pyramids. It does not earn an always-on slot without task-specific evidence that it changes behavior. It bills tokens on every edit, in every language, forever. The burden is on the content to prove it helps, not on the reader to prove it does not.
- Anything already stated in another always-on file. Duplicates drift apart, and then the agent spends reasoning reconciling them instead of doing the work.

### Use Skills For

- Tool-based actions (file modification, API calls, git operations)
- User-triggered workflows (PR creation, issue management)
- Multi-step procedures (conflict resolution, session completion)
- Actions requiring validation (security scans, linting)
- Depth on knowledge the model partly has, loaded on demand

### Hybrid Pattern

- Knowledge in passive context (routing, classification)
- Actions in skill (script execution, state changes)
- Example: pr-comment-responder is routed from the always-on AGENTS.md skill table, and its scripts stay in the skill

## Why This Matters

| Configuration | Pass Rate |
|---------------|-----------|
| Baseline (no docs) | 53% |
| Skill (default) | 53% |
| Skill + explicit instructions | 79% |
| **AGENTS.md passive context** | **100%** |

Skills create decision points where agents must choose whether to retrieve documentation. These introduce 4 failure modes: late retrieval, partial retrieval, integration failure, and instruction fragility. Passive context eliminates all four by being always-available.

### Read That Table Honestly

The 53 to 100 percent result is real and it is narrow. Vercel's suite targeted Next.js 16 APIs chosen because they were **absent from model training data**. That is a knowledge-injection problem: an agent cannot retrieve what it does not know it is missing, so putting the docs in front of it wins.

It is not evidence that pre-trained knowledge belongs in passive context. Anthropic's Claude 5 context-engineering guidance points the other way for behavioral instruction, naming overconstraint as the failure mode after cutting more than 80 percent of a system prompt with no measurable coding-eval loss. Both results hold, because they answer different questions:

| Content | Model already knows it | Where it goes |
|---------|------------------------|---------------|
| A post-cutoff framework API | No | Passive context |
| This repo's dash ban, its gates | No | Passive context |
| SOLID, Clean Code, refactoring | Yes | Progressive disclosure, or nowhere |
| Deep book material | Partly | Progressive disclosure |

The pass-rate table has no cost column. Passive context is paid on every request, forever, whether or not the task needs it. This repository adopted the strategy in #1022 with a stated budget of Vercel's own 8KB figure; the always-on corpus later reached about 95KB on a `.py` edit. The enforced ceilings ratchet to measured size, so a passing budget gate is not evidence the corpus is small. Measure with `scripts/validation/instruction_budget.py` before adding always-on text, and prefer deleting a duplicate over compressing one.

## References

- [model-context-doctrine.md](references/model-context-doctrine.md) - What the current doctrine is, why Vercel and Shihipar do not conflict, per-model levers, and how to update when a new model ships. **Read this before arguing about always-on content.**
- [rule-audit-procedure.md](references/rule-audit-procedure.md) - Repeatable procedure for deciding whether an always-on rule earns its slot, including the eval commands and the decision table. Contributor-only: its commands invoke this repo's eval harness and rule generator
- [rule-audit-instrument.md](references/rule-audit-instrument.md) - What the eval can and cannot resolve, the noise floor, and the known instrument gotchas. Read before believing any number the eval prints
- [rule-audit-evidence.md](references/rule-audit-evidence.md) - Forensics behind the published table: which judge samples were lost, what recovering them changed, and what the loss does to the headline claim. Read before citing a cell
- [rule-audit-parser-forensics.md](references/rule-audit-parser-forensics.md) - Repair history of the parser that produced the table: what more than twenty rounds of adversarial review found, and which fixes were themselves wrong. Read before writing a new instrument that parses judge output
- [rule-audit-measurement-discipline.md](references/rule-audit-measurement-discipline.md) - How the checks themselves went wrong: false negative controls, numbers read off the wrong population, and edits that silently deleted what they anchored on. Read before quoting a figure from a one-off command
- [Vercel: AGENTS.md outperforms skills](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)
- Analysis: `.agents/analysis/vercel-passive-context-vs-skills-research.md`
- Memory: `passive-context-vs-skills-vercel-research`
- [vibe-engineering.md](references/vibe-engineering.md) - 7-step agent interaction protocol for structured context optimization
- [claude-code-productivity-patterns.md](references/claude-code-productivity-patterns.md) - Cost control, context management, and quality gates

## Related

- Issue #1108: Build passive context tooling suite

<details>
<summary><strong>Tool Details: Skill/Passive Content Analyzer</strong></summary>

**Script**: `scripts/analyze_skill_placement.py`

Analyzes skill content and recommends Skill, Passive Context, or Hybrid placement.

> The script reports shape, not admission. It cannot tell whether the model
> already knows the content, and that is the question the Decision Framework
> above turns on. Use it for size and duplication; the Decision Framework
> decides what earns an always-on slot.

**Classification Logic**:

- **Tool Calls**: Bash, Read, Write, Edit, gh, git, pwsh commands -> Skill
- **Action Verbs**: create, update, delete, execute, run -> Skill
- **Reference Content**: Tables, lists, code blocks -> Passive
- **User Triggers**: "when user", slash commands, explicit requests -> Skill

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

**Evaluated Checks**:

1. Skills contain actions (verbs, tool execution, scripts)
2. Passive context is knowledge-only (no action patterns)
3. @imported files exist and are readable
4. Skills have frontmatter (`name` and `description`)
5. No duplicate content between skills and passive context
6. Declared size exceptions include rationale and safeguard evidence

The report also measures the selected `CLAUDE.md` file. That number is not a
compliance verdict. It excludes imported content, hierarchical
`CLAUDE.md` and `AGENTS.md` files, generated instruction layers, and plugin
context.

Claude Code loads `CLAUDE.md` files in full. The vendor's first 200 lines or
25 KB limit applies to auto-memory `MEMORY.md`, not `CLAUDE.md`. This
repository's 200-line command ratchet is separate local policy in
`command_size.py`.

Source:
<https://docs.anthropic.com/en/docs/claude-code/memory>

Skill size is also separate. In a full `rjmurillo/ai-agents` checkout, run the
repository's `skill_size.py` validator against both the canonical and generated
skill trees.

The report states what it does not evaluate. Content value still needs
evidence-based review. Classify each passive rule as one of:

1. Non-inferable gotcha with cited evidence
2. Local arbitration between otherwise reasonable rules
3. Costly-failure safeguard
4. Task procedure that belongs in a skill
5. Inferable restatement that should be removed

Lexical matches do not prove those categories. Cite the incident, source, or
test that supports each keep or remove decision.

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
| Missing @import file | Create file or remove @import directive |
| Skill missing frontmatter | Add `---` block with `name:` and `description:` |
| Skill has no actions | Add scripts or move to passive context |
| Passive has actions | Extract executable content to a skill |
| Duplicate content | Remove redundant content from skill or passive |
| Unaudited size exception | Add invariant, behavior tests, and review trigger |

</details>

<details>
<summary><strong>Classification Examples</strong></summary>

### Clear Skill Classification

**Input**: GitHub skill with gh pr create, gh issue close commands

```json
{"classification": "Skill", "confidence": 85, "reasoning": "High tool execution (8 calls); Many action verbs (12)"}
```

### Clear Passive Classification

**Input**: Memory hierarchy reference, tables and lists, no commands

```json
{"classification": "PassiveContext", "confidence": 80, "reasoning": "High reference content ratio (0.85)"}
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

<!-- vendor-portability: declared. This skill cites .agents/analysis/vercel-passive-context-vs-skills-research.md as background reading. It is a documentation citation; the optimizer runs without reading the file, and a vendored install loses only the link target. Issue #2050. -->
