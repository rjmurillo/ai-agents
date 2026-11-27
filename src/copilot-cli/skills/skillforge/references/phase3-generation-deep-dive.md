# Phase 3: Generation Deep Dive

**Context:** Fresh, clean (no analysis artifacts polluting)
**Standard:** Zero errors, every section verified before proceeding

## Generation Order

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

3. Run the Placement Check in SKILL.md before moving detail to references.
   Follow its result before continuing. Skip it for mechanics-only edits.

4. Generate reference documents (if needed)
   • Deep documentation for complex topics
   • Templates for generated artifacts
   • Checklists for validation

5. Create assets (if needed)
   • Templates for skill outputs

6. Create scripts (if needed)
   • Use script-template.py as base
   • Include Result dataclass pattern
   • Add a fast-fail check, and plan an independent postcondition check
   • Follow references/script-design-rules.md: shared exit codes
     (0 ok, 1 logic, 2 usage or config, 3 external, 4 auth), main(argv)
     returns the code, stdlib only
   • Write tests in the repository's test tree from the test template in
     script-design-rules.md, one per exit code, and run them before finalizing
   • In SKILL.md, invoke scripts through the plugin-root locator, never a bare
     .claude/skills path (see ADR-121)

7. Write the reference page (only when the repository has docs/skills/README.md
   and --path is a folder named skills)
   • init_skill.py writes docs/skills/{skill-name}.md with the seven sibling
     sections: When to use it, When not to use it, Quick start, What you get,
     Advanced use, Where it runs, Related
   • Pass --docs-section "<README heading>" to add the README table row, or
     paste the row it prints into the right table
   • Fill in every TODO on the page and in the row
```

## Quality Checks During Generation

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
| Scripts (if present) | Shebang, docstring with an `Exit codes:` block, argparse, `main(argv)` returning the code, Result pattern |
| Script tests | One test per exit code, in the repository's test tree, never in the skill directory |
| Script docs | Scripts section in SKILL.md with usage examples |
| Docs page (if `docs/skills/README.md` exists) | Page with the seven sibling sections in order, TODOs filled in, and a README table row that links it |
| Portable exec paths | Script invocations use the plugin-root locator, never a bare `.claude/skills/...` path (issue #2838) |
