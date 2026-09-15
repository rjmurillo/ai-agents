---
source: wiki/concepts/AI Productivity/Claude Code Productivity Patterns.md
created: 2026-04-11
review-by: 2026-07-11
---

# Claude Code Productivity Patterns

Battle-tested workflows for cost control, context management, and quality gates in Claude Code development.

## Context Growth = Quadratic Cost

Context usage grows linearly. Cost grows quadratically because every message re-sends entire chat history.

**Multi-instance orchestration**: Separate CC instances per domain (frontend, backend, DB). All log to central memory bank. Cross-instance reads fetch only relevant logs, not full history.

**Proactive handover at ~80% context**: Outgoing agent writes all undocumented context, decisions, working memory to dedicated file. New agent reads that file. No chat history re-reading.

## MCP Context Optimization

MCP servers wrapping CRUD JSON APIs dump 50KB+ per tool call.

**Code Mode pattern**: LLM writes small extraction script. Server runs it in sandbox against raw data. Only stdout enters context. Saves 65-99% context.

| Language | Sandbox |
|----------|---------|
| TypeScript/JS | `quickjs-emscripten` |
| Python | `RestrictedPython` |
| Go | `goja` |
| Rust | `boa_engine` |

**mcpkit alternative**: Converts MCP server into CLI-based skills. Generates SKILL.md. Agent calls via `mcpkit call <server> <tool> '{params}'`. Skill puts 2 lines in system prompt vs flooding context with tool descriptions.

## Selective MCP Exposure

- **Global (always-on)**: Context7, Chrome DevTools only
- **Local (project-specific)**: Per CC instance
- **On-demand (mcpkit)**: Install as skills when needed

If Claude already knows the CLI from training data, skip the MCP entirely.

## Drift Detection via Static Analysis

Purpose-built CLI tools (1-2 second runtime each) detect divergence between intended and actual state.

| Tool | Detects |
|------|---------|
| `api-contract-drift` | Go API response vs TypeScript interface mismatches |
| `schema-drift-detector` | DB schema vs struct alignment |
| `code-audit` | 30+ checks: SQL injection, CSRF, N+1, credential leaks |
| `query-complexity-analyzer` | SQL performance risk, N+1, injection vectors |
| `implementation-test-coverage` | Per-implementation test tracking |

Design principles: multiple output formats, CI mode with exit codes, focused scope, fast execution.

## Planning Patterns

**SDD (Spec-Driven Development)**: Treat Claude like a junior dev needing a spec, not a magic box.

- GitHub Spec-kit, OpenSpec, APM, CC SDD

**Auto-triggered agents**: Agents fire based on context, not manual invocation.

| Agent | Auto-Trigger |
|-------|-------------|
| `test-writer-fixer` | After code changes |
| `experiment-tracker` | Feature flags introduced |
| `project-shipper` | Launch milestones |

## Task Management

Validated pattern regardless of tooling: break work into max ~10 min tasks, let agents claim and complete them, parallelize with swarms.

GitHub Issues format that works: `# CONTEXT # TODO # SUCCESS CRITERIA`
