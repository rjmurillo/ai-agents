# v0.3.0 Orchestrator Scripts

## orchestrate.sh

Automated orchestration harness for parallel agent execution across 6 chains.

### Quick Start

```bash
./orchestrate.sh              # Interactive mode
./orchestrate.sh start        # Begin week 1
./orchestrate.sh status       # Check progress
./orchestrate.sh resume       # Continue after interruption
```

### Commands

| Command | Description |
|---------|-------------|
| `start [week]` | Begin from week (default: 1) |
| `resume` | Continue from saved state |
| `status` | Show progress |
| `chain N` | Run chain N only |
| `setup` | Create worktrees |
| `cleanup` | Remove worktrees |
| `interactive` | Menu mode |
| `help` | Show usage |

### Environment Variables

```bash
AGENT_CMD=claude       # or copilot
PARALLEL_CHAINS=3      # concurrent chains
```

### Chains

| # | Branch | Issues |
|---|--------|--------|
| 1 | chain1/memory-enhancement | #997->#998->#999->#1001 |
| 2 | chain2/memory-optimization | #751->#734,#747->#731 |
| 3 | chain3/traceability | #724->#721->#722->#723 |
| 4 | chain4/quality-testing | #749->#778,#840 |
| 5 | chain5/skill-quality | #761->#809 |
| 6 | chain6/ci-docs | #77,#90->#71,#101 |
