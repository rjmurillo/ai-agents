import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";

const AGENTS_STUB = `# AGENTS.md

Cross-platform harness spec for AI coding agents.

This file describes the agent team vendored into \`.claude/\`.
Compatible with Claude Code, GitHub Copilot CLI, and other harness-aware tools.

## What is here

- \`.claude/commands/\` — slash commands for lifecycle phases
- \`.claude/agents/\` — specialized agent definitions
- \`.claude/skills/\` — domain knowledge and workflows

## Interop

This is a harness spec with interop across multiple AI coding tools.
Any tool that reads \`.claude/\` or \`AGENTS.md\` can consume it.
The content is portable across Claude Code, Copilot, and Codex runtimes.

## Getting started

Open this folder in Claude Code and run \`/spec\` to start.
`;

export async function writeAgentsMd(
  targetDir: string,
  dryRun: boolean,
): Promise<boolean> {
  if (dryRun) return false;

  const filePath = join(targetDir, "AGENTS.md");
  const dir = dirname(filePath);
  await mkdir(dir, { recursive: true });

  try {
    await readFile(filePath);
    return false;
  } catch {
    // File does not exist, create it
  }

  await writeFile(filePath, AGENTS_STUB, "utf-8");
  return true;
}
