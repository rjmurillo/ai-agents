# Diffray Configuration

This directory contains diffray configuration for AI-assisted code review tailored to the ai-agents project.

## Overview

Diffray provides intelligent, context-aware code review using AI agents. This configuration focuses on areas where AI adds the most value, while excluding concerns already handled by existing tools (PSScriptAnalyzer, markdownlint).

## Configuration Structure

```text
.diffray/
├── config.yaml                    # Main configuration
├── README.md                      # This file
└── rules/
    ├── powershell-patterns.yaml   # PowerShell-specific rules (6 rules)
    ├── workflow-constraints.yaml  # GitHub Actions rules (5 rules)
    ├── agent-templates.yaml       # Agent template rules (4 rules)
    └── session-protocol.yaml      # Governance/protocol rules (7 rules)
```

## Key Features

### 1. ADR Enforcement

Rules directly enforce architectural decisions:

- **ADR-005**: No bash/Python scripts (PowerShell only)
- **ADR-006**: Thin workflows, testable modules
- **ADR-014**: HANDOFF.md is read-only

### 2. Security Focus

- Secret exposure detection in workflows
- Path normalization (no absolute paths)
- Error handling validation

### 3. Quality Gates

- PowerShell best practices (CmdletBinding, validation)
- Skill usage enforcement (no raw gh commands)
- Atomic commits and proper git history

### 4. Template Protection

- Prevents direct edits to generated agent files
- Validates agent frontmatter
- Ensures required sections exist

## Configuration Tuning

### Thresholds

Current settings:

```yaml
review:
  model: sonnet               # Balanced cost/quality
  minConfidence: 70           # Higher due to strong existing linting
  minImportance: 5            # Focus on medium+ issues
```

**Adjustment guidance**:

- Increase `minConfidence` (to 80) if too many false positives
- Decrease `minImportance` (to 3) to catch more minor issues
- Switch to `opus` model for critical PRs (security, architecture)

### Filters

Excluded paths:

- `.agents/sessions/**` - Historical session logs
- `.agents/retrospective/**` - Historical retrospectives
- `.serena/memories/**` - AI memory (managed separately)

**When to adjust**:

- Add new artifact directories to exclusions
- Re-include specific files if review needed

## Rule Categories

### PowerShell Patterns (6 rules)

| Rule ID | Importance | Focus |
|---------|------------|-------|
| `ps_no_bash_python_scripts` | 9 | ADR-005 enforcement |
| `ps_cmdletbinding_required` | 7 | Parameter handling |
| `ps_error_handling_required` | 8 | Try-catch in external calls |
| `ps_avoid_write_host_in_modules` | 6 | Testability |
| `ps_proper_parameter_validation` | 7 | Input validation |

### Workflow Constraints (5 rules)

| Rule ID | Importance | Focus |
|---------|------------|-------|
| `wf_no_inline_logic` | 8 | ADR-006 enforcement |
| `wf_should_call_modules` | 7 | Delegation to modules |
| `wf_max_line_limit` | 5 | Complexity warning |
| `wf_error_handling` | 7 | Exit code checking |
| `wf_secrets_exposure` | 9 | Secret safety |

### Agent Templates (4 rules)

| Rule ID | Importance | Focus |
|---------|------------|-------|
| `agent_no_direct_edit` | 9 | Template-first workflow |
| `agent_handoff_syntax` | 7 | Platform consistency |
| `agent_required_sections` | 6 | Complete definitions |
| `agent_frontmatter_validation` | 7 | Generation metadata |

### Session Protocol (7 rules)

| Rule ID | Importance | Focus |
|---------|------------|-------|
| `session_handoff_readonly` | 9 | ADR-014 enforcement |
| `session_skill_usage_enforcement` | 8 | Skill-first pattern |
| `session_pr_template_required` | 7 | PR documentation |
| `session_adr_changes_trigger_review` | 9 | ADR review process |
| `session_commit_atomicity` | 6 | Git history quality |
| `session_spec_reference_required` | 7 | Traceability |
| `session_path_normalization` | 7 | Security/portability |

## Testing the Configuration

### Validate Syntax

```bash
# Check YAML syntax
yamllint .diffray/config.yaml .diffray/rules/*.yaml
```

### Test on Sample PR

1. Create test branch with intentional violations
2. Run diffray review
3. Verify expected rules trigger
4. Adjust thresholds if needed

### Common Validation Scenarios

**Test bash script detection**:

```bash
# Should trigger ps_no_bash_python_scripts
git checkout -b test-bash-detection
echo '#!/bin/bash' > test.sh
git add test.sh && git commit -m "test: bash detection"
```

**Test workflow logic detection**:

```bash
# Should trigger wf_no_inline_logic
# Edit .github/workflows/test.yml to add inline conditionals
```

**Test generated file edit**:

```bash
# Should trigger agent_no_direct_edit
# Edit src/vs-code-agents/analyst.agent.md
```

## Integration with Existing Tools

Diffray complements existing tooling:

| Tool | Focus | Diffray Focus |
|------|-------|---------------|
| PSScriptAnalyzer | Syntax, style | Semantic patterns, architecture |
| markdownlint | Markdown formatting | Documentation completeness |
| Pester | Unit test execution | Test coverage gaps |
| Git hooks | Pre-commit validation | PR-level review |

## Customization

### Adding New Rules

1. Choose appropriate rules file (or create new)
2. Follow rule structure (see examples)
3. Set importance (1-10) and agent assignment
4. Add to relevant tags for filtering

**Rule template**:

```yaml
rules:
  - id: unique_rule_id
    agent: security|bugs|quality|architecture
    title: "Brief rule description"
    description: |
      Detailed explanation
    importance: 1-10
    
    match:
      file_glob:
        - "**/*.ext"
      content_regex:
        - "pattern"
    
    checklist:
      - "Step 1"
      - "Step 2"
    
    examples:
      bad: |
        # Anti-pattern
      good: |
        # Correct pattern
    
    tags:
      - tag1
      - tag2
```

### Disabling Rules

**Temporarily disable a rule**:

```yaml
# In config.yaml
rules:
  exclude:
    - rule_id_to_disable
```

**Disable for specific PR** (comment on PR):

```text
@diffray ignore rule_id
```

## Monitoring and Improvement

### Review Metrics

Track these metrics to tune configuration:

- False positive rate per rule
- Most frequently triggered rules
- Rules that catch real issues vs noise
- Review completion time

### Iteration Cycle

1. **Week 1**: Collect data on all rules
2. **Week 2**: Adjust thresholds based on false positives
3. **Week 3**: Add new rules for missed patterns
4. **Week 4**: Review rule effectiveness, retire low-value rules

## Resources

- [Diffray Documentation](https://docs.diffray.ai/)
- [Writing Effective Rules](https://docs.diffray.ai/configuration/writing-effective-rules)
- [Project ADRs](.agents/architecture/)
- [Project Constraints](.agents/governance/PROJECT-CONSTRAINTS.md)

## Support

For questions or issues with diffray configuration:

1. Check rule output for suggestions
2. Review [Project Constraints](.agents/governance/PROJECT-CONSTRAINTS.md)
3. Consult relevant ADRs in `.agents/architecture/`
4. Open issue with `diffray` label
