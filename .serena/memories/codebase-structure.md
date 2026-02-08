# Codebase Structure

## Root Directory

```text
ai-agents/
├── .agents/                    # Agent artifacts and outputs
├── .claude/                    # Claude Code configuration
├── .githooks/                  # Git hooks (pre-commit)
├── .github/                    # GitHub configuration
├── .serena/                    # Serena MCP configuration
├── src/                        # Agent source files
│   ├── claude/                 # Claude Code CLI agent definitions
│   ├── copilot-cli/            # GitHub Copilot CLI agent definitions
│   └── vs-code-agents/         # VS Code / GitHub Copilot agent definitions
├── docs/                       # Documentation
├── scripts/                    # Installation scripts
├── .markdownlint-cli2.yaml     # Markdown linting configuration
├── CLAUDE.md                   # Claude Code instructions
├── copilot-instructions.md     # GitHub Copilot instructions
├── README.md                   # Project overview
└── USING-AGENTS.md             # Comprehensive usage guide
```

## Agent Directories

All agent source files are located under `src/`:

### src/claude/

Claude Code CLI agent definitions (18 agents):

- analyst.md, architect.md, critic.md, devops.md, explainer.md
- high-level-advisor.md, implementer.md, independent-thinker.md
- memory.md, orchestrator.md, milestone-planner.md, pr-comment-responder.md
- qa.md, retrospective.md, roadmap.md, security.md, skillbook.md
- task-decomposer.md

### src/copilot-cli/

GitHub Copilot CLI agents (same 18 agents with `.agent.md` suffix)

### src/vs-code-agents/

VS Code / GitHub Copilot agents (same 18 agents with `.agent.md` suffix)

## .agents/ Directory (Artifacts)

```text
.agents/
├── architecture/              # ADRs and design decisions
│   ├── ADR-001-markdown-linting.md
│   └── ADR-TEMPLATE.md
├── critique/                  # Plan reviews
├── governance/                # Agent governance docs
│   ├── agent-interview-protocol.md
│   └── interviews/
├── planning/                  # Plans and PRDs
├── qa/                        # Test reports
├── retrospective/             # Learning extractions
├── security/                  # Security templates and checklists
├── skills/                    # Learned skills
└── utilities/                 # Utility scripts
    └── fix-markdown-fences/
```

## scripts/ Directory

Validation and utility scripts (PowerShell):

- Validate-SessionJson.ps1 - Session protocol validation
- Validate-PRDescription.ps1 - PR description validation
- Detect-SkillViolation.ps1 - Skill usage detection
- Sync-McpConfig.ps1 - MCP configuration sync

> **Note**: Agent installation is handled by [skill-installer](https://github.com/rjmurillo/skill-installer).
> See [docs/installation.md](../docs/installation.md) for installation instructions.

## docs/ Directory

- markdown-linting.md - Markdown standards
- orchestrator-routing-algorithm.md - Routing logic
- task-classification-guide.md - Task classification
- diagrams/ - Flowcharts and diagrams

## Key Configuration Files

| File | Purpose |
|------|---------|
| `.markdownlint-cli2.yaml` | Markdown linting rules |
| `CLAUDE.md` | Claude Code instructions |
| `copilot-instructions.md` | GitHub Copilot instructions |
| `.githooks/pre-commit` | Auto-fix markdown on commit |
