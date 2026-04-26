import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";

const BEGIN_MARKER = "<!-- ai-agents:begin -->";
const END_MARKER = "<!-- ai-agents:end -->";

const GENERIC_BLOCK = `${BEGIN_MARKER}
# ai-agents Harness

Vendored by [@rjmurillo/ai-agents](https://github.com/rjmurillo/ai-agents).

## Skill Routing

When your request matches an available skill, invoke it using the Skill tool
as your FIRST action. Skills provide specialized workflows.

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

Use the Task tool with specialized agents:
- orchestrator: multi-step coordination
- analyst: research and investigation
- architect: design and ADRs
- implementer: code and tests
- critic: plan validation
- qa: testing and verification
${END_MARKER}`;

export async function mergeClaudeMd(
  targetDir: string,
  dryRun: boolean,
): Promise<void> {
  if (dryRun) return;

  const filePath = join(targetDir, "CLAUDE.md");
  const dir = dirname(filePath);
  await mkdir(dir, { recursive: true });

  let existing = "";
  let detectedCrlf = false;
  try {
    const raw = await readFile(filePath);
    existing = raw.toString("utf-8");
    detectedCrlf = existing.includes("\r\n");
  } catch {
    // File does not exist yet
  }

  if (existing.includes(BEGIN_MARKER) && existing.includes(END_MARKER)) {
    return;
  }

  let block = GENERIC_BLOCK;
  if (detectedCrlf) {
    block = block.replace(/\n/g, "\r\n");
  }

  let result: string;
  if (existing.length === 0) {
    result = block + "\n";
  } else {
    const lineEnding = detectedCrlf ? "\r\n" : "\n";
    const trimmed = existing.endsWith(lineEnding) ? existing : existing + lineEnding;
    result = trimmed + lineEnding + block + lineEnding;
  }

  if (detectedCrlf) {
    result = result.replace(/(?<!\r)\n/g, "\r\n");
  }

  await writeFile(filePath, result, "utf-8");
}
