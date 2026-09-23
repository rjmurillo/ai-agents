# Ideation Research: Agent Templating System

**Date**: 2025-12-15
**Analyst**: analyst
**Status**: Research Complete

## Package/Technology Overview

### What It Is

A templating system to define agents once in a canonical format and generate platform-specific outputs for:
- **Claude Code** (`src/claude/*.md`)
- **VS Code Copilot** (`src/vs-code-agents/*.agent.md`)
- **GitHub Copilot CLI** (`src/copilot-cli/*.agent.md`)

### What Problem It Solves

Currently, 18 agents are maintained as 54 separate files (18 x 3 platforms) with significant content duplication. Changes require manual synchronization across all three platforms, risking:
- Inconsistencies between platforms
- Increased maintenance burden
- Drift in agent behavior across platforms
- Error-prone manual updates

## Commonality & Variability Analysis (CVA)

### Methodology

Analyzed 5 representative agents across all 3 platforms:
- `analyst` - Research-focused agent
- `implementer` - Code execution agent (largest)
- `orchestrator` - Coordination agent (most complex)
- `memory` - Simpler, focused agent

### Commonalities (Shared Content ~80-90%)

| Component | Shared Across All Platforms |
|-----------|----------------------------|
| Core Identity | Identical |
| Core Mission | Identical |
| Key Responsibilities | Identical |
| Analysis Types / Templates | Identical |
| Handoff Options Table | Identical (content, not syntax) |
| Execution Mindset | Identical |
| Constraints | Identical |
| Output Location | Identical |
| Markdown Templates | Identical |
| Code Examples (bash, csharp, etc.) | Identical |

### Variabilities (Platform-Specific)

| Component | Claude Code | VS Code | Copilot CLI |
|-----------|-------------|---------|-------------|
| **File Extension** | `.md` | `.agent.md` | `.agent.md` |
| **YAML: name field** | `name: analyst` | (absent) | `name: analyst` |
| **YAML: description** | Present | Present | Present |
| **YAML: model** | `model: opus` | `model: Claude Opus 4.5 (anthropic)` | (absent in some) |
| **YAML: tools** | (absent - inline in body) | `tools: ['vscode', 'read', ...]` array | `tools: ['shell', 'read', ...]` array |
| **Tools Section Header** | `## Claude Code Tools` | (tools in YAML, no section) | (tools in YAML, no section) |
| **Tool Syntax (MCP)** | `mcp__cloudmcp-manager__memory-search_nodes` | `cloudmcp-manager/memory-search_nodes` | `cloudmcp-manager/memory-search_nodes` |
| **Tool Invocation Examples** | Full MCP syntax in code blocks | Shortened path syntax | Shortened path syntax |
| **Memory Protocol Header** | `## Memory Protocol` | `## Memory Protocol (cloudmcp-manager)` | `## Memory Protocol (cloudmcp-manager)` |
| **Handoff Invocation** | `Task(subagent_type="[agent]", prompt="[task]")` | `#runSubagent with subagentType={agent_name}` | `/agent [agent_name]` |
| **Platform-Specific Tools** | WebSearch, WebFetch, Task | vscode, github.vscode-*, ms-vscode.* | shell, agent |

### Variation Point Summary

```
Variation Points Identified: 11
- Front matter schema: 4 variations
- Tool declaration location: 2 variations (YAML vs body)
- Tool syntax format: 2 variations (MCP prefix vs path)
- Handoff syntax: 3 variations
- Platform-specific sections: 2 variations (present/absent)
```

## Templating Options Evaluation

### Option 1: Handlebars

**Repository**: github.com/handlebars-lang/handlebars.js
**npm Downloads**: 40M+/month
**License**: MIT

| Criterion | Score | Notes |
|-----------|-------|-------|
| Community Signal | High | 17k+ stars, mature, widely adopted |
| Learning Curve | Low | Mustache-compatible, simple syntax |
| Logic Support | Medium | Helpers, partials, block expressions |
| Performance | Low | 390ms (slowest in benchmarks) |
| IDE Support | High | Plugins for VS Code, JetBrains |
| .NET Compatibility | Yes | Handlebars.NET available |

**Pros**:
- Familiar syntax (`{{variable}}`, `{{#if}}`, `{{#each}}`)
- Strong ecosystem with custom helpers
- Partials for reusable content blocks
- Good IDE support for syntax highlighting

**Cons**:
- Slowest performance in benchmarks
- Logic-less by design (complex logic needs helpers)
- Verbose for conditional platform targeting

**Example**:
```handlebars
---
{{#if platform.claude}}
name: {{agent.name}}
model: opus
{{else}}
{{#if platform.vscode}}
description: {{agent.description}}
tools: {{{json tools.vscode}}}
model: Claude Opus 4.5 (anthropic)
{{/if}}
{{/if}}
---
# {{agent.title}} Agent

## Core Identity

{{agent.coreIdentity}}

{{#if platform.claude}}
## Claude Code Tools

You have direct access to:
{{#each tools.claude}}
- **{{this.name}}**: {{this.description}}
{{/each}}
{{/if}}
```

### Option 2: LiquidJS

**Repository**: github.com/harttle/liquidjs
**npm Downloads**: 1.7M+/month
**License**: MIT

| Criterion | Score | Notes |
|-----------|-------|-------|
| Community Signal | High | 1.7k stars, active maintenance |
| Learning Curve | Low | Shopify/Jekyll compatible |
| Logic Support | Medium | Filters, tags, control flow |
| Performance | Medium | 153ms in benchmarks |
| IDE Support | High | Jekyll/Shopify editor support |
| .NET Compatibility | Yes | DotLiquid, Fluid available |

**Pros**:
- GitHub Pages compatible (Jekyll uses Liquid)
- Excellent filter system for text transformation
- Well-documented with Shopify backing
- Safer than JS-based engines (sandboxed)

**Cons**:
- Ruby-style naming conventions by default
- Less flexible than full JS logic
- Requires more verbose conditionals

**Example**:
```liquid
---
{% if platform == 'claude' %}
name: {{ agent.name }}
model: opus
{% elsif platform == 'vscode' %}
description: {{ agent.description }}
tools: {{ tools.vscode | json }}
model: Claude Opus 4.5 (anthropic)
{% endif %}
---
# {{ agent.title }} Agent

## Core Identity

{{ agent.coreIdentity }}

{% if platform == 'claude' %}
## Claude Code Tools

You have direct access to:
{% for tool in tools.claude %}
- **{{ tool.name }}**: {{ tool.description }}
{% endfor %}
{% endif %}
```

### Option 3: EJS (Embedded JavaScript)

**Repository**: github.com/mde/ejs
**npm Downloads**: 30M+/month
**License**: Apache-2.0

| Criterion | Score | Notes |
|-----------|-------|-------|
| Community Signal | High | 7k+ stars, very widely used |
| Learning Curve | Low | Plain JavaScript |
| Logic Support | High | Full JavaScript available |
| Performance | High | 68ms (second fastest) |
| IDE Support | Medium | Basic highlighting |
| .NET Compatibility | No | JavaScript only |

**Pros**:
- Full JavaScript power in templates
- Very fast performance
- Native partials and includes
- No new syntax to learn

**Cons**:
- Less safe (arbitrary JS execution)
- No .NET equivalent for cross-platform builds
- Tags (`<% %>`) can be noisy in markdown

**Example**:
```ejs
---
<% if (platform === 'claude') { %>
name: <%= agent.name %>
model: opus
<% } else if (platform === 'vscode') { %>
description: <%= agent.description %>
tools: <%= JSON.stringify(tools.vscode) %>
model: Claude Opus 4.5 (anthropic)
<% } %>
---
# <%= agent.title %> Agent

## Core Identity

<%= agent.coreIdentity %>

<% if (platform === 'claude') { %>
## Claude Code Tools

You have direct access to:
<% tools.claude.forEach(tool => { %>
- **<%= tool.name %>**: <%= tool.description %>
<% }); %>
<% } %>
```

### Option 4: Eta.js

**Repository**: github.com/eta-dev/eta
**npm Downloads**: 1.6M+/month
**License**: MIT

| Criterion | Score | Notes |
|-----------|-------|-------|
| Community Signal | Medium | 1.6k stars, active |
| Learning Curve | Low | EJS-like but improved |
| Logic Support | High | Full JavaScript |
| Performance | Highest | 20ms (fastest in benchmarks) |
| IDE Support | Low | Limited tooling |
| .NET Compatibility | No | JavaScript only |

**Pros**:
- Fastest templating engine
- Modern EJS alternative
- Cleaner syntax than EJS
- TypeScript support

**Cons**:
- Smaller community
- No .NET equivalent
- Less ecosystem support

### Option 5: Custom PowerShell/Node.js Solution

| Criterion | Score | Notes |
|-----------|-------|-------|
| Community Signal | N/A | Custom implementation |
| Learning Curve | Medium | Team must maintain |
| Logic Support | High | Full language power |
| Performance | Variable | Depends on implementation |
| IDE Support | N/A | No special support |
| .NET Compatibility | Yes | PowerShell is .NET native |

**Pros**:
- Exact fit for requirements
- No external dependencies
- Full control over output
- Native to existing build scripts

**Cons**:
- Maintenance burden
- No template syntax highlighting
- Reinventing the wheel
- Documentation overhead

### Option 6: Scriban (for .NET builds)

**Repository**: github.com/scriban/scriban
**NuGet Downloads**: 86k+/version
**License**: BSD-2-Clause

| Criterion | Score | Notes |
|-----------|-------|-------|
| Community Signal | High | 3k+ stars, very active |
| Learning Curve | Low | Liquid-compatible mode |
| Logic Support | High | Full scripting language |
| Performance | Highest | Fastest .NET templating |
| IDE Support | Medium | JetBrains Liquid plugin |
| .NET Compatibility | Native | Built for .NET |

**Pros**:
- Native .NET integration
- Can parse Liquid templates
- Extremely fast (3-6x faster than DotLiquid)
- Can be used in C# source generators

**Cons**:
- Less common in JavaScript ecosystems
- Requires .NET tooling for builds

## Technical Fit Assessment

### Current Codebase Patterns

The repository uses:
- **PowerShell** for installation scripts (`scripts/`)
- **Pester** for testing (`scripts/tests/`)
- **Node.js** ecosystem implied by typical AI agent tooling
- **Markdown** as the primary output format

### Recommended Approach

**Primary Recommendation: LiquidJS (Node.js) + Scriban (optional .NET)**

Rationale:
1. **Jekyll/GitHub Pages compatibility** - Liquid is widely understood
2. **Good performance** - Middle tier, but acceptable for build-time generation
3. **Cross-platform options** - DotLiquid/Scriban if PowerShell builds preferred
4. **Strong filter system** - Perfect for text transformations needed
5. **Safe templating** - No arbitrary code execution risks

### Proposed Architecture

```
templates/
  agents/
    _shared/                    # Shared partials
      core-identity.liquid
      memory-protocol.liquid
      handoff-options.liquid
    analyst.liquid              # Canonical agent definition
    implementer.liquid
    orchestrator.liquid
    ...
  platforms/
    claude.liquid               # Platform-specific wrappers
    vscode.liquid
    copilot-cli.liquid
  data/
    tools.yaml                  # Platform-specific tool mappings
    platforms.yaml              # Platform configuration

build/
  generate-agents.js            # Node.js build script
  generate-agents.ps1           # PowerShell alternative

src/                            # Generated output (gitignored or checked in)
  claude/
  vs-code-agents/
  copilot-cli/
```

### Template Data Model

```yaml
# data/agent-analyst.yaml
name: analyst
title: Analyst
description: Pre-implementation research, root cause analysis, feature request review
model:
  claude: opus
  vscode: Claude Opus 4.5 (anthropic)
  copilot: null  # Uses default

coreIdentity: |
  **Research and Analysis Specialist** for pre-implementation investigation.
  Conduct strategic research into root causes, systemic patterns, requirements,
  and feature requests. Read-only access to production code - never modify.

coreMission: |
  Investigate before implementation. Surface unknowns, risks, and dependencies.
  Provide research that enables informed design decisions.

responsibilities:
  - Research technical approaches before implementation
  - Analyze existing code to understand patterns
  - Investigate bugs and issues to find root causes
  - Evaluate feature requests for necessity and impact
  - Surface risks, dependencies, and unknowns
  - Document findings for architect/planner

# Platform-specific tool configurations in data/tools.yaml
```

## Integration Complexity

### Estimated Effort

| Task | Effort | Notes |
|------|--------|-------|
| Template structure design | 2-4 hours | Define canonical format |
| Data model definition | 2-3 hours | YAML schema for agents |
| Build script (Node.js) | 4-6 hours | LiquidJS integration |
| Migrate 18 agents to templates | 8-12 hours | Extract commonalities |
| CI/CD integration | 2-3 hours | GitHub Actions workflow |
| Documentation | 2-3 hours | README for template system |
| **Total** | **20-31 hours** | ~3-4 days of focused work |

### Breaking Changes

- **None for consumers** - Output files remain identical
- **Development workflow change** - Edit templates, not output files
- **Build step required** - Adds generation to release process

### Migration Path

1. **Phase 1**: Create templates for 2-3 agents as proof of concept
2. **Phase 2**: Validate generated output matches existing files exactly
3. **Phase 3**: Migrate remaining agents
4. **Phase 4**: Remove source files from version control (or keep as generated artifacts)
5. **Phase 5**: Document contribution workflow

## Alternatives Considered

| Alternative | Pros | Cons | Why Not Preferred |
|-------------|------|------|-------------------|
| Manual sync | No tooling | Error-prone, tedious | Current pain point |
| Git submodules | Single source | Complex, merge conflicts | Doesn't solve variation |
| Single platform only | Simple | Limits adoption | Reduces value proposition |
| AI-assisted sync | Low effort | Inconsistent, unreliable | Not deterministic |

## Risks and Concerns

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Template complexity grows | Medium | Medium | Strict partial discipline |
| Build step forgotten | Low | High | CI validation, pre-commit hook |
| Output drift from manual edits | Medium | Medium | Generated file headers, CI checks |
| Templating engine deprecated | Low | Medium | Well-established choices |

### Process Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Contributors edit output files | Medium | Medium | Clear docs, CI rejection |
| Template syntax learning curve | Low | Low | Liquid is simple |
| Lost context in abstraction | Low | Medium | Good partial naming |

### Security Implications

- **Low risk** - Build-time only, no runtime templating
- **No user input** - All data is developer-controlled
- **Sandboxed execution** - LiquidJS is safe by design

### Licensing

- **LiquidJS**: MIT (permissive)
- **Handlebars**: MIT (permissive)
- **EJS**: Apache-2.0 (permissive)
- **Scriban**: BSD-2-Clause (permissive)

All options are compatible with open-source and commercial use.

## Recommendation

**Decision**: Proceed

**Rationale**:
- **Evidence Strength**: Strong - CVA confirms 80-90% content overlap
- **Risk Level**: Low - Build-time only, reversible
- **Strategic Fit**: High - Reduces maintenance, enables scaling

### Recommended Implementation

1. **Templating Engine**: LiquidJS (Node.js) with optional Scriban for PowerShell
2. **Template Format**: Canonical YAML data + Liquid templates
3. **Build Integration**: npm script + GitHub Actions
4. **Validation**: Diff-based CI check against expected output

### Success Metrics

- [ ] 100% of agents generated from templates
- [ ] Zero manual edits to output files
- [ ] < 5 second generation time for all agents
- [ ] Contributor docs updated
- [ ] CI validation passing

## Next Steps

1. **Route to high-level-advisor** for strategic validation
2. **If approved**: Route to architect for template structure design
3. **Then**: Route to planner for work breakdown
4. **Finally**: Route to implementer for build script creation

---

**Tools for Ideation Research Used**:
- Perplexity Search - Templating engine comparisons and benchmarks
- Context7 - Library documentation (Handlebars, LiquidJS)
- Read - CVA of existing agent files
- Memory Search - Prior context (none found)

**Data Transparency**:
- **Found**: Performance benchmarks, feature comparisons, .NET options, community metrics
- **Not Found**: Prior team decisions on templating, existing POC attempts
