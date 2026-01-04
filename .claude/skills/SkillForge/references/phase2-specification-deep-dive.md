
### Specification Structure

The specification captures all analysis insights in XML format:

```xml
<skill_specification>
  <metadata>
    <name>skill-name</name>
    <analysis_iterations>N</analysis_iterations>
    <timelessness_score>X/10</timelessness_score>
  </metadata>

  <context>
    <problem_statement>What + Why + Who</problem_statement>
    <existing_landscape>Related skills, distinctiveness</existing_landscape>
  </context>

  <requirements>
    <explicit>What user asked for</explicit>
    <implicit>Expected but unstated</implicit>
    <discovered>Found through analysis</discovered>
  </requirements>

  <architecture>
    <pattern>Selected pattern with WHY</pattern>
    <phases>Ordered phases with verification</phases>
    <decision_points>Branches and defaults</decision_points>
  </architecture>

  <scripts>
    <decision_summary>needs_scripts + rationale</decision_summary>
    <script_inventory>name, category, purpose, patterns</script_inventory>
    <agentic_capabilities>autonomous, self-verify, recovery</agentic_capabilities>
  </scripts>

  <evolution_analysis>
    <timelessness_score>X/10</timelessness_score>
    <extension_points>Where skill can grow</extension_points>
    <obsolescence_triggers>What would break it</obsolescence_triggers>
  </evolution_analysis>

  <anti_patterns>
    <pattern>What to avoid + WHY + alternative</pattern>
  </anti_patterns>

  <success_criteria>
    <criterion>Measurable + verification method</criterion>
  </success_criteria>
</skill_specification>
```

See: [references/specification-template.md](references/specification-template.md)

### Specification Validation

Before proceeding to Phase 3:

- [ ] All sections present with no placeholders
- [ ] Every decision includes WHY
- [ ] Timelessness score ≥ 7 with justification
- [ ] At least 2 extension points documented
- [ ] All requirements traceable to source
- [ ] Scripts section complete (if applicable)
- [ ] Agentic capabilities documented (if scripts present)
