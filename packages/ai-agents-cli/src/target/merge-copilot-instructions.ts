import { join } from "node:path";
import {
  BEGIN_MARKER,
  END_MARKER,
  appendMarkerBlock,
} from "./append-marker-block.js";

const COPILOT_BLOCK = `${BEGIN_MARKER}
# ai-agents Harness

Vendored by [@rjmurillo/ai-agents](https://github.com/rjmurillo/ai-agents).

## Skill Routing

When your request matches an available skill, invoke it as your FIRST action.
Skills provide specialized workflows.

Key routing:
- Bugs, errors -> /analyze
- PRs, issues -> /github
- Define requirements -> /spec
- Plan work -> /plan
- Implement -> /build
- Test -> /test
- Review code -> /review
- Ship, deploy -> /ship

## Memory Interface

| Scenario | Tool |
|----------|------|
| Quick search | /memory-search |
| Deep exploration | context-retrieval agent |
| Direct MCP | mcp__serena__read_memory |

## Agents

Delegate to specialized agents:
- orchestrator: multi-step coordination
- analyst: research and investigation
- architect: design and ADRs
- implementer: code and tests
- critic: plan validation
- qa: testing and verification
${END_MARKER}`;

export async function mergeCopilotInstructions(
  targetDir: string,
  dryRun: boolean,
): Promise<void> {
  const filePath = join(targetDir, ".github", "copilot-instructions.md");
  await appendMarkerBlock(filePath, COPILOT_BLOCK, dryRun);
}
