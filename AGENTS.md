# AGENTS.md

Cross-platform agent instructions for Claude Code, Copilot CLI, Cortex, and Factory Droid.

## Serena Initialization (BLOCKING)

Initialize Serena BEFORE any work when MCP tools are available:

1. `mcp__serena__activate_project` (or `serena/activate_project`)
2. `mcp__serena__initial_instructions` (or `serena/initial_instructions`)

If unavailable, proceed without Serena. Read `.serena/memories/<name>.md` as fallback.

## Retrieval-Led Reasoning (MANDATORY)

Agents retrieve current information. They do not rely on pre-training for project-specific decisions.

| Decision Type | Retrieve From |
|---------------|---------------|
| Framework APIs | Official docs (Context7, DeepWiki, WebSearch) |
| Project constraints | `.agents/governance/PROJECT-CONSTRAINTS.md` |
| Learned patterns | Serena `memory-index` via `mcp__serena__read_memory` |
| Architecture decisions | `.agents/architecture/ADR-*.md` |
| Session protocol | `.agents/SESSION-PROTOCOL.md` |
| Skills | `.claude/skills/{name}/SKILL.md` |

Rule: Read first, reason second. Pre-training is the last resort, never the default.

## Session Protocol Gates

> Canonical source: [.agents/SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md)

### Session Start (BLOCKING)

| Level | Step | Verification |
|-------|------|--------------|
| MUST | Initialize Serena (two-call sequence above) | Tool output in transcript |
| MUST | Read `.agents/HANDOFF.md` (read-only) | Content in context |
| MUST | Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.json` | File exists |
| SHOULD | Search relevant Serena memories | Memory results present |
| SHOULD | Verify git status and starting commit | Output documented |

### Session End (BLOCKING)

| Level | Step | Verification |
|-------|------|--------------|
| MUST | Complete session log (all MUST items `[x]`) | All MUST items marked complete |
| MUST NOT | Update `.agents/HANDOFF.md` | File unchanged |
| MUST | Update Serena memory (cross-session context) | Memory write confirmed |
| MUST | Run scoped markdownlint on changed `.md` files (ADR-043) | Lint passes |
| MUST | Commit all changes including `.agents/` | Commit SHA recorded |
| MUST | Run `python3 scripts/validate_session_json.py [log]` | Exit code 0 |
| SHOULD | Update PROJECT-PLAN.md task checkboxes | Tasks marked |
| SHOULD | Invoke retrospective (significant sessions) | Doc created |

Exit code 0 required before claiming completion. If validation fails, use `/session-log-fixer`.

## Boundaries and Constraints

> Full details: [.agents/governance/PROJECT-CONSTRAINTS.md](.agents/governance/PROJECT-CONSTRAINTS.md)

### Always

- **Python (.py)** for new scripts (ADR-042). PowerShell for existing scripts.
- **Verify branch** before any git/gh operation: `git branch --show-current`
- **Update Serena memory** at session end with cross-session context
- **Check for existing skills** before writing inline GitHub operations
- **Assign issues** before starting work: `gh issue edit <number> --add-assignee @me`
- **Use PR template** with all sections from `.github/PULL_REQUEST_TEMPLATE.md`
- **Commit atomically** (max 5 files or single logical change)
- **Run scoped linting** before commits (ADR-043)
- **Pin GitHub Actions to SHA** with version comment
- **Run `gh act` locally** before pushing workflow changes

### Ask First

- Architecture changes affecting multiple agents or core patterns
- New ADRs or additions to PROJECT-CONSTRAINTS.md
- Breaking changes to workflows, APIs, or handoff protocols
- Security-sensitive changes (auth, credentials, data handling)

### Never

- Commit secrets or credentials
- Update HANDOFF.md (read-only reference)
- Use bash for scripts (Python or PowerShell only, ADR-042)
- Skip session validation (`validate_session_json.py` must pass)
- Put logic in workflow YAML (ADR-006: logic goes in modules)
- Use raw `gh` commands when skills exist
- Force push to main/master
- Skip hooks (`--no-verify`, `--no-gpg-sign`)
- Reference internal PR/issue numbers in user-facing files (`src/`, `templates/`)

## Skill-First Checkpoint

Before EVERY git/gh/script operation, ask: "Is there a skill for this?"

| Operation | Skill | NOT raw command |
|-----------|-------|-----------------|
| Create/manage PRs | github | `gh pr create` |
| Respond to reviews | pr-comment-responder | `gh pr comment` |
| Resolve conflicts | merge-resolver | manual git merge |
| Create session log | /session-init | manual JSON creation |
| Fix CI failures | session-log-fixer | manual debugging |
| Complete session log | session-end | manual JSON editing |
| Commit and push | /push-pr | `git commit && git push` |
| Run security scan | security-detection | manual scanning |
| Analyze code quality | analyze | manual review |
| Learn from session | reflect | manual capture |

If no skill exists, proceed with raw command. If capability is missing, add to skill first.

### PR Comment Routing

| Comment Pattern | Skill | Route |
|-----------------|-------|-------|
| CWE-* security | security-scan | Process FIRST |
| Style/linting | style-enforcement | After security |
| Documentation gaps | doc-coverage | After style |
| Bot summaries | skip | Informational only |

### ADR Review (BLOCKING)

Any file matching `.agents/architecture/ADR-*.md` created or edited triggers mandatory adr-review skill before workflow continues.

## Agent Catalog

| Agent | Purpose | Model |
|-------|---------|-------|
| orchestrator | Task coordination, routing, synthesis | opus |
| analyst | Research, root cause analysis, investigation | sonnet |
| architect | ADRs, design governance, pattern enforcement | sonnet |
| milestone-planner | Epic breakdown, milestones, impact analysis | sonnet |
| implementer | Production code, tests, approved plans | sonnet |
| critic | Plan validation, gap detection, quality gate | sonnet |
| qa | Test strategy, coverage, verification | sonnet |
| security | Threat modeling, OWASP, vulnerability analysis | sonnet |
| devops | CI/CD pipelines, infrastructure, deployment | sonnet |
| roadmap | Product strategy, prioritization (RICE/KANO) | sonnet |
| explainer | PRDs, specs, documentation | sonnet |
| task-decomposer | Atomic task breakdown, backlog grooming | sonnet |
| independent-thinker | Challenge assumptions, alternative viewpoints | sonnet |
| high-level-advisor | Strategic decisions, unblocking, P0 priority | opus |
| retrospective | Learning extraction, Five Whys, skill extraction | haiku |
| skillbook | Learned strategies, deduplication, atomicity scoring | haiku |
| memory | Cross-session context, knowledge retrieval | haiku |
| pr-comment-responder | PR review triage, comment tracking, resolution | sonnet |
| backlog-generator | Proactive task discovery when idle | sonnet |

## Workflow Patterns

| Workflow | Agent Sequence |
|----------|----------------|
| Feature (standard) | orchestrator, analyst, architect, milestone-planner, critic, implementer, qa |
| Quick fix | implementer, qa |
| Strategic decision | independent-thinker, high-level-advisor, task-decomposer |
| Ideation pipeline | analyst, high-level-advisor, independent-thinker, critic, roadmap, explainer, task-decomposer |

For multi-domain features (3+ domains), add impact analysis during planning. See [.agents/governance/IMPACT-ANALYSIS.md](.agents/governance/IMPACT-ANALYSIS.md).

For specialist disagreements, use consensus mechanisms. See [.agents/governance/CONSENSUS.md](.agents/governance/CONSENSUS.md).

## Coding Standards

> Full reference: [.gemini/styleguide.md](.gemini/styleguide.md)

| Topic | Standard |
|-------|----------|
| Commit format | `<type>(<scope>): <desc>` with `Co-Authored-By:` trailer |
| AI attribution | Claude `noreply@anthropic.com`, Copilot `copilot@github.com` |
| Exit codes | 0=success, 1=logic, 2=config, 3=external, 4=auth (ADR-035) |
| Actions | SHA-pin all, no `${{ }}` in run blocks |
| Coverage | 100% security, 80% business, 60% docs |

### Test Exit Codes (BLOCKING)

ANY non-zero exit code from test frameworks blocks commits.

| Output | Exit Code | Verdict |
|--------|-----------|---------|
| `66 passed` | 0 | PASS, safe to commit |
| `66 passed, 1 failed` | 1 | FAIL, fix before commit |
| `66 passed, 1 error` | 1 | FAIL, fix before commit |

Both "failed" and "error" are failures. Run full test suite before every commit.

## Tech Stack

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.12.x | Primary scripting (ADR-042) |
| UV | Latest | Package manager, hash-pinned deps |
| PowerShell | 7.5.4+ | Cross-platform, existing scripts |
| Node.js | LTS (20+) | markdownlint-cli2 |
| Pester | 5.7.1 | PowerShell tests, supply chain pinned |
| pytest | 8.0+ | Python tests |
| GitHub CLI | 2.60+ | gh operations |

## Key References

| Document | Purpose |
|----------|---------|
| `.agents/SESSION-PROTOCOL.md` | Full session requirements |
| `.agents/HANDOFF.md` | Project dashboard (read-only) |
| `.agents/governance/PROJECT-CONSTRAINTS.md` | Hard constraints |
| `.agents/AGENT-SYSTEM.md` | Full agent details |
| `.gemini/styleguide.md` | Code style, security patterns |
| `.agents/governance/IMPACT-ANALYSIS.md` | Impact analysis framework |
| `.agents/governance/CONSENSUS.md` | Consensus and disagree-and-commit |
| `.config/wt.toml` | Worktrunk configuration |
| `docs/installation.md` | Installation guide |
