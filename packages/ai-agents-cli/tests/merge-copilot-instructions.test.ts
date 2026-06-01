import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, writeFile, readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { mergeCopilotInstructions } from "../src/target/merge-copilot-instructions.js";

const BEGIN_MARKER = "<!-- ai-agents:begin -->";
const END_MARKER = "<!-- ai-agents:end -->";
const REL_PATH = [".github", "copilot-instructions.md"] as const;

let testDir: string;

beforeEach(async () => {
  testDir = await mkdtemp(join(tmpdir(), "merge-copilot-"));
});

afterEach(async () => {
  await rm(testDir, { recursive: true, force: true });
});

function instructionsPath(): string {
  return join(testDir, ...REL_PATH);
}

describe("mergeCopilotInstructions", () => {
  test("creates .github/copilot-instructions.md when file does not exist", async () => {
    await mergeCopilotInstructions(testDir, false);

    const content = await readFile(instructionsPath(), "utf-8");
    expect(content).toContain(BEGIN_MARKER);
    expect(content).toContain(END_MARKER);
    expect(content).toContain("ai-agents Harness");
  });

  test("appends block to existing instructions file", async () => {
    await mkdir(join(testDir, ".github"), { recursive: true });
    const existing = "# Repo Copilot Rules\n\nExisting guidance here.\n";
    await writeFile(instructionsPath(), existing);

    await mergeCopilotInstructions(testDir, false);

    const content = await readFile(instructionsPath(), "utf-8");
    expect(content).toStartWith("# Repo Copilot Rules");
    expect(content).toContain(BEGIN_MARKER);
    expect(content).toContain(END_MARKER);
  });

  test("idempotent: does not duplicate block on re-run", async () => {
    await mergeCopilotInstructions(testDir, false);
    await mergeCopilotInstructions(testDir, false);

    const content = await readFile(instructionsPath(), "utf-8");
    const beginCount = content.split(BEGIN_MARKER).length - 1;
    expect(beginCount).toBe(1);
  });

  test("preserves CRLF line endings", async () => {
    await mkdir(join(testDir, ".github"), { recursive: true });
    const existing = "# Rules\r\n\r\nSome content.\r\n";
    await writeFile(instructionsPath(), existing);

    await mergeCopilotInstructions(testDir, false);

    const content = await readFile(instructionsPath(), "utf-8");
    expect(content).toContain("\r\n");
    // No orphaned LF (one not preceded by CR) precedes the marker block.
    for (let i = 0; i < content.length; i++) {
      if (content[i] === "\n" && content[i - 1] !== "\r") {
        const rest = content.slice(i);
        expect(rest.includes("<!-- ai-agents")).toBe(false);
      }
    }
  });

  test("handles missing trailing newline", async () => {
    await mkdir(join(testDir, ".github"), { recursive: true });
    const existing = "# Rules\n\nNo trailing newline";
    await writeFile(instructionsPath(), existing);

    await mergeCopilotInstructions(testDir, false);

    const content = await readFile(instructionsPath(), "utf-8");
    expect(content).toContain(BEGIN_MARKER);
    expect(content).toContain("No trailing newline");
  });

  test("dry run writes nothing", async () => {
    await mergeCopilotInstructions(testDir, true);

    try {
      await readFile(instructionsPath());
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err.code).toBe("ENOENT");
    }
  });
});
