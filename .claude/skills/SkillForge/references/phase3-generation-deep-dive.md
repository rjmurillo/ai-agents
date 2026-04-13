
**Context:** Fresh, clean (no analysis artifacts polluting)
**Standard:** Zero errors—every section verified before proceeding

### Generation Order

```
1. Create directory structure
   mkdir -p ~/.claude/skills/{skill-name}/references
   mkdir -p ~/.claude/skills/{skill-name}/assets/templates
   mkdir -p ~/.claude/skills/{skill-name}/scripts  # if scripts needed

2. Write SKILL.md
   • Frontmatter (YAML - allowed properties only)
   • Title and brief intro
   • Quick Start section
   • Triggers (3-5 varied phrases)
   • Quick Reference table
   • How It Works overview
   • Commands
   • Scripts section (if applicable)
   • Validation section
   • Anti-Patterns
   • Verification criteria
   • Deep Dive sections (in <details> tags)

3. Generate reference documents (if needed)
   • Deep documentation for complex topics
   • Templates for generated artifacts
   • Checklists for validation

4. Create assets (if needed)
   • Templates for skill outputs

5. Create scripts (if needed)
   • Use script-template.py as base
   • Include Result dataclass pattern
   • Add self-verification
   • Document exit codes
   • Test before finalizing
```

### Quality Checks During Generation

| Check | Requirement |
|-------|-------------|
| Frontmatter | Only allowed properties (name, description, license, allowed-tools, metadata) |
| Name | Hyphen-case, ≤64 chars |
| Description | ≤1024 chars, no angle brackets |
| Triggers | 3-5 distinct, natural language |
| Phases | 1-3 max, not over-engineered |
| Verification | Concrete, measurable |
| Tables over prose | Structured information in tables |
| No placeholder text | Every section fully written |
| Scripts (if present) | Shebang, docstring, argparse, exit codes, Result pattern |
| Script docs | Scripts section in SKILL.md with usage examples |
