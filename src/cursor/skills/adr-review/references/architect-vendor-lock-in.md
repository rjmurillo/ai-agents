# Vendor Lock-in Assessment

Loaded by the Claude `architect` body when an ADR introduces an external dependency. The Copilot and VS Code bodies carry no reversibility section and do not load this file.

## Vendor Lock-in Section (Required in ADRs)

Add this section to all ADRs that introduce external dependencies:

```markdown
## Vendor Lock-in Assessment

**Dependency**: [Name of external service, library, or platform]
**Lock-in Level**: [None / Low / Medium / High / Critical]

### Lock-in Indicators
- [ ] Proprietary APIs without standards-based alternatives
- [ ] Data formats that require conversion to export
- [ ] Licensing terms that restrict migration
- [ ] Integration depth that increases switching cost
- [ ] Team training investment

### Exit Strategy
**Trigger conditions**: [When would we consider switching?]
**Migration path**: [How would we extract ourselves?]
**Estimated effort**: [Time/cost to switch to alternative]
**Data export**: [How to extract our data in portable format]

### Accepted Trade-offs
[Why we accept this lock-in despite the risks]
```

## Lock-in Levels Defined

| Level | Definition | Examples |
|-------|------------|----------|
| **None** | Standard protocols, easily replaceable | REST APIs, SQL databases |
| **Low** | Minor adaptation needed | NuGet packages with alternatives |
| **Medium** | Significant but manageable effort | Cloud provider SDKs |
| **High** | Major project to migrate | Proprietary data formats |
| **Critical** | Effectively permanent | Deep platform integration |
