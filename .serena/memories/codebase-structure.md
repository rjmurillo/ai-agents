# Codebase Structure

## Root Directory

```text
ai-agents/
├── .agents/                    # Agent artifacts and outputs
├── .claude/                    # Claude Code configuration
├── .githooks/                  # Git hooks (pre-commit)
├── .github/                    # GitHub configuration
├── .serena/                    # Serena MCP configuration
├── claude/                     # Claude Code CLI agent definitions
├── copilot-cli/                # GitHub Copilot CLI agent definitions
├── docs/                       # Documentation
├── scripts/                    # Installation scripts
├── vs-code-agents/             # VS Code / GitHub Copilot agent definitions
├── .markdownlint-cli2.yaml     # Markdown linting configuration
├── CLAUDE.md                   # Claude Code instructions
├── copilot-instructions.md     # GitHub Copilot instructions
├── README.md                   # Project overview
└── USING-AGENTS.md             # Comprehensive usage guide
```

## Agent Directories

### claude/

Claude Code CLI agent definitions (18 agents):

- analyst.md, architect.md, critic.md, devops.md, explainer.md
- high-level-advisor.md, implementer.md, independent-thinker.md
- memory.md, orchestrator.md, planner.md, pr-comment-responder.md
- qa.md, retrospective.md, roadmap.md, security.md, skillbook.md
- task-generator.md

### copilot-cli/

GitHub Copilot CLI agents (same 18 agents with `.agent.md` suffix)

### vs-code-agents/

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

Installation scripts (PowerShell):

- install-vscode-global.ps1
- install-vscode-repo.ps1
- install-copilot-cli-global.ps1
- install-copilot-cli-repo.ps1
- install-claude-global.ps1
- install-claude-repo.ps1

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
