import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, writeFile, readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { mergeClaudeMd } from "../src/target/merge-claude-md.js";

const BEGIN_MARKER = "<!-- ai-agents:begin -->";
const END_MARKER = "<!-- ai-agents:end -->";

let testDir: string;

beforeEach(async () => {
  testDir = await mkdtemp(join(tmpdir(), "merge-claude-md-"));
});

afterEach(async () => {
  await rm(testDir, { recursive: true, force: true });
});

describe("mergeClaudeMd", () => {
  test("creates CLAUDE.md when file does not exist", async () => {
    await mergeClaudeMd(testDir, false);

    const content = await readFile(join(testDir, "CLAUDE.md"), "utf-8");
    expect(content).toContain(BEGIN_MARKER);
    expect(content).toContain(END_MARKER);
    expect(content).toContain("ai-agents Harness");
  });

  test("appends block to existing CLAUDE.md", async () => {
    const existing = "# My Project\n\nExisting instructions here.\n";
    await writeFile(join(testDir, "CLAUDE.md"), existing);

    await mergeClaudeMd(testDir, false);

    const content = await readFile(join(testDir, "CLAUDE.md"), "utf-8");
    expect(content).toStartWith("# My Project");
    expect(content).toContain(BEGIN_MARKER);
    expect(content).toContain(END_MARKER);
  });

  test("idempotent: does not duplicate block on re-run", async () => {
    await mergeClaudeMd(testDir, false);
    await mergeClaudeMd(testDir, false);

    const content = await readFile(join(testDir, "CLAUDE.md"), "utf-8");
    const beginCount = content.split(BEGIN_MARKER).length - 1;
    expect(beginCount).toBe(1);
  });

  test("preserves CRLF line endings", async () => {
    const existing = "# Project\r\n\r\nSome content.\r\n";
    await writeFile(join(testDir, "CLAUDE.md"), existing);

    await mergeClaudeMd(testDir, false);

    const content = await readFile(join(testDir, "CLAUDE.md"), "utf-8");
    expect(content).toContain("\r\n");
    expect(content).not.toMatch(/(?<!\r)\n.*<!-- ai-agents/);
  });

  test("handles missing trailing newline", async () => {
    const existing = "# Project\n\nNo trailing newline";
    await writeFile(join(testDir, "CLAUDE.md"), existing);

    await mergeClaudeMd(testDir, false);

    const content = await readFile(join(testDir, "CLAUDE.md"), "utf-8");
    expect(content).toContain(BEGIN_MARKER);
    expect(content).toContain("No trailing newline");
  });

  test("dry run writes nothing", async () => {
    await mergeClaudeMd(testDir, true);

    try {
      await readFile(join(testDir, "CLAUDE.md"));
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err.code).toBe("ENOENT");
    }
  });
});
