# v0.3.0 Project: Memory Enhancement and Quality

Self-contained project directory for the v0.3.0 milestone execution.

## Directory Structure

```
.agents/projects/v0.3.0/
├── README.md           # This file
├── scripts/
│   └── orchestrate.sh  # Main orchestration harness
├── state/
│   └── orchestrator.json  # Persistent state for resume
├── logs/
│   └── chain{N}-issue{XXX}-{timestamp}.log
├── messages/
│   ├── inbox/          # Messages to chains
│   └── outbox/         # Sent message archive
└── worktrees/
    ├── chain1/         # Memory Enhancement
    ├── chain2/         # Memory Optimization
    ├── chain3/         # Traceability
    ├── chain4/         # Quality Testing
    ├── chain5/         # Skill Quality
    └── chain6/         # CI/Docs
```

## Quick Start

```bash
# Navigate to project
cd .agents/projects/v0.3.0

# Make executable (first time only)
chmod +x scripts/orchestrate.sh

# Interactive mode (recommended)
./scripts/orchestrate.sh

# Or start directly
./scripts/orchestrate.sh start
```

## Commands

| Command | Description |
|---------|-------------|
| `start [week]` | Begin orchestration from week (default: 1) |
| `resume` | Continue from saved state |
| `status` | Show current progress |
| `chain N` | Run only chain N |
| `setup` | Create all worktrees |
| `cleanup` | Remove worktrees (keeps state) |
| `interactive` | Menu-driven mode |
| `help` | Show usage |

## Configuration

```bash
# Use Copilot instead of Claude (see limitations below)
AGENT_CMD=copilot ./scripts/orchestrate.sh start

# Run 6 chains simultaneously
PARALLEL_CHAINS=6 ./scripts/orchestrate.sh start
```

### Agent Mode Limitations

| Mode | Status | Notes |
|------|--------|-------|
| `claude` | Stable | Default. Uses `claude --print` for non-interactive execution. |
| `copilot` | Experimental | Uses `gh copilot suggest`. May require interactive terminal input. Not recommended for automated/background execution. |

**Copilot Mode Caveats**:

- Requires `gh copilot` extension installed (`gh extension install github/gh-copilot`)
- May prompt for interactive input, breaking automated workflows
- Not tested for long-running background execution
- Consider using Claude mode for production orchestration

## Chain Structure

| Chain | Branch | Issues | Starts |
|-------|--------|--------|--------|
| 1 | `chain1/memory-enhancement` | #997 -> #998 -> #999 -> #1001 | Week 1 |
| 2 | `chain2/memory-optimization` | #751 -> #734, #747 -> #731 | Week 1 |
| 3 | `chain3/traceability` | #724 -> #721 -> #722 -> #723 | Week 1 |
| 4 | `chain4/quality-testing` | #749 -> #778, #840 | Week 3 |
| 5 | `chain5/skill-quality` | #761 -> #809 | Week 3 |
| 6 | `chain6/ci-docs` | #77, #90 -> #71, #101 | Week 5 |

## Message Passing

Chains communicate via JSON files in `messages/`:

```bash
# View inbox
ls messages/inbox/

# Read a message
cat messages/inbox/chain2-*.json | jq '.'
```

Messages are sent automatically when blocking issues complete.

## Resume After Interruption

```bash
# Check where you left off
./scripts/orchestrate.sh status

# Continue
./scripts/orchestrate.sh resume
```

## Manual Intervention

If an issue needs human work:

```bash
# 1. Navigate to chain worktree
cd worktrees/chain1

# 2. Do manual work with Claude
claude

# 3. Update state (mark issue complete)
cd ../..
jq '.issues."997".status = "completed" | .chains."1".completed_issues += [997]' \
  state/orchestrator.json > tmp && mv tmp state/orchestrator.json

# 4. Resume
./scripts/orchestrate.sh resume
```

## Cleanup After Completion

When v0.3.0 ships:

```bash
# Remove worktrees
./scripts/orchestrate.sh cleanup

# Archive or delete entire project
rm -rf .agents/projects/v0.3.0
```

## Merge Order

After all chains complete:

1. Chain 2 (fragmentation) - Unblocks router
2. Chain 1 (enhancement) - Core feature
3. Chain 3 (traceability) - Independent
4. Chain 4 (quality) - Independent
5. Chain 5 (skills) - Independent
6. Chain 6 (CI/docs) - Polish

## Testing

Automated tests for orchestrate.sh are in `tests/test_orchestrate_sh.py`:

```bash
# Run orchestrator tests
pytest tests/test_orchestrate_sh.py -v

# Run specific test class
pytest tests/test_orchestrate_sh.py::TestOrchestrateShHelp -v
```

**Test Coverage**:

- Script syntax validation (bash -n)
- Help command output
- Status command execution
- Chain configuration validation
- State file structure
- Directory structure
- Input validation (chain numbers 1-6)
- Error handling patterns (file locking, temp cleanup)

## Chain Definitions

Chain definitions in `orchestrate.sh` are synchronized with `.agents/planning/v0.3.0/PLAN.md`.

**Source of Truth**: PLAN.md is authoritative. If the schedule or chain structure changes:

1. Update PLAN.md first
2. Sync orchestrate.sh arrays: `CHAINS`, `CHAIN_BRANCHES`, `CHAIN_START_WEEK`, `ISSUE_BLOCKED_BY`

## Platform Notes

**macOS Compatibility**:

- Script uses GNU `date -Iseconds` format
- On macOS, install coreutils: `brew install coreutils`
- Or modify date commands to use BSD-compatible format
