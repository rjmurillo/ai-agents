# Retrospective: MCP Config Loading (2025-12-18)

## Session Info
- Date: 2025-12-18
- Agents: retrospective (this session)
- Task Type: Investigation / Configuration
- Outcome: Partial success — root causes identified and recommendations created

## Phase 0: Data Gathering

### 4-Step Debrief

#### Step 1: Observe (Facts Only)
- Tool calls: repository grep/view for mcp.json references; viewed .vscode/mcp.json; viewed Sync-McpConfig.ps1 and .agents/HANDOFF.md.
- Outputs: Located `.vscode/mcp.json` with servers entries; discovered `scripts/Sync-McpConfig.ps1` syncs `.mcp.json` -> `.vscode/mcp.json`; found CLI uses `~/.copilot/mcp-config.json`.
- Errors: No runtime errors; mismatch in expected config locations/filenames.
- Duration: Short (single-session investigative task).

#### Step 2: Respond (Reactions)
- Pivots: From checking repo files to examining sync script and HANDOFF notes.
- Retries: Single-pass reads; no retries required.
- Escalations: None — required no external dependencies.
- Blocks: None technical; only a policy/expectation gap about where the CLI loads config from.

#### Step 3: Analyze (Interpretations)
- Pattern: Multiple MCP config formats exist (Claude, VS Code, Copilot CLI), causing confusion.
- Anomaly: Sync script produces workspace `.vscode/mcp.json` but not the CLI's expected user-level file.
- Correlation: User observed CLI reported "no MCP servers configured" despite repo files because CLI reads user home config, not workspace files.

#### Step 4: Apply (Actions)
- Skills to update: Add explicit checklist step to sync MCP configs to CLI home during setup.
- Process changes: Extend Sync-McpConfig.ps1 to support an optional target `--copilot-home` to write `%USERPROFILE%\.copilot\mcp-config.json`.
- Context to preserve: Document canonical formats in `.agents/analysis/` and update HANDOFF entries.

## Execution Trace

| Time | Action | Outcome |
|------|--------|---------|
| T+0 | Searched repo for mcp configs | Found `.vscode/mcp.json` and scripts/Sync-McpConfig.ps1 |
| T+1 | Viewed `.vscode/mcp.json` | Confirmed servers defined (serena, deepwiki) |
| T+2 | Read Sync-McpConfig.ps1 | Found transform logic `.mcp.json` -> `.vscode/mcp.json` only |
| T+3 | Checked HANDOFF.md analysis | Confirmed Copilot CLI uses `~/.copilot/mcp-config.json` |

### Timeline Patterns
- Quick discovery to diagnosis; no blocking errors encountered.

## Outcome Classification

### Mad (Blocked)
- None — investigation completed.

### Sad (Suboptimal)
- The sync tooling and documentation did not cover the Copilot CLI user-level config, causing user confusion.

### Glad (Success)
- Root cause identified and concrete remediation steps produced.

## Phase 1: Generate Insights

### Five Whys (for "CLI didn't load MCP servers from repo")
- Q1: Why did CLI report no MCP servers configured? A1: CLI reads `~/.copilot/mcp-config.json`, not `.vscode/mcp.json`.
- Q2: Why is the repo config in `.vscode/mcp.json` not loaded? A2: CLI is explicitly designed to use a user-level config file for security/consistency.
- Q3: Why wasn't the user-level config populated? A3: Project tooling (Sync-McpConfig.ps1) only syncs .mcp.json -> .vscode/mcp.json and not to CLI home.
- Q4: Why does Sync-McpConfig.ps1 omit CLI home? A4: It was implemented to support Claude and VS Code formats, not Copilot CLI use-case.
- Q5: Why was Copilot CLI support excluded? A5: Likely out-of-scope for original implementer and overlooked in acceptance criteria.

Root Cause: Sync tooling and documentation omitted the Copilot CLI home config target, creating a gap between repository configs and CLI behavior.

### Fishbone (high level)
- Prompt: Ambiguous expectation that repo workspace config would be sufficient.
- Tools: Sync script supports limited targets; no option for CLI home.
- Context: Multiple MCP formats and locations (Claude, VS Code, Copilot CLI).
- Dependencies: User environment (home dir) and permissions to write user-level config.
- Sequence: User places config in workspace; CLI checks user home first; no automatic merge.
- State: Hand-off notes documented the differences, but tooling didn't act on it.

## Phase 2: Diagnosis & Actions

Priority findings:
1. Add Copilot CLI target to Sync-McpConfig.ps1 (P0).
2. Add documentation snippet to README describing where each client reads configs and how to sync (P1).
3. Add optional test(s) to scripts/tests to validate syncing to `%USERPROFILE%\.copilot\mcp-config.json` (P1).

Action plan (ordered):
1. Update `scripts/Sync-McpConfig.ps1` to accept `-CopilotHome` (or `-Target copilot`) and write user-level config when requested.
2. Add tests in `scripts/tests/` mirroring existing tests to cover CLI home sync behavior.
3. Update `.agents/HANDOFF.md` and add a short doc in `.agents/analysis/` to call out canonical formats.

## Phase 3: Learning Extraction

Learning: "Sync tooling must support all active MCP consumers (Claude, VS Code, Copilot CLI) to avoid config drift." (atomic)

## Phase 4: Close

+/Delta
- + Keep: Good analysis and existing sync script that prevents accidental overwrite of user home by default.
- Delta: Add an explicit opt-in flag to write user-level config and document the risks.

ROTI: 3 (High value for small effort)

---

## Prompt for follow-up agent session (implementer)

Task: Implement Copilot CLI sync support and tests

Context:
- Repo already contains `scripts/Sync-McpConfig.ps1` which transforms Claude `.mcp.json` -> `.vscode/mcp.json`.
- Copilot CLI expects a user-level config at `%USERPROFILE%\.copilot\mcp-config.json` with root key `mcpServers`.

Requirements:
1. Update `scripts/Sync-McpConfig.ps1` to add an optional parameter `-CopilotHome` (or `-Target "copilot"`) which writes the transformed config to the user's `%USERPROFILE%\.copilot\mcp-config.json` with correct root key.
2. Ensure the script does not overwrite an existing user config unless `-Force` is provided; if destination exists prompt or return non-destructive outcome.
3. Add tests in `scripts/tests/Sync-McpConfig.Tests.ps1` to validate the new behavior (use temp directories/mocks where needed).
4. Update README or add `.agents/analysis/001-mcp-sync-to-copilot.md` documenting the change and risks.

Deliverables:
- PR with script changes, tests, and a short documentation file.

Acceptance Criteria:
- Existing behavior (Claude -> VS Code) unchanged when new flag is not used.
- Tests pass locally.


