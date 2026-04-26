import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, writeFile, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { writeAgentsMd } from "../src/target/write-agents-md.js";

let testDir: string;

beforeEach(async () => {
  testDir = await mkdtemp(join(tmpdir(), "write-agents-md-"));
});

afterEach(async () => {
  await rm(testDir, { recursive: true, force: true });
});

describe("writeAgentsMd", () => {
  test("creates AGENTS.md when missing", async () => {
    const created = await writeAgentsMd(testDir, false);
    expect(created).toBe(true);

    const content = await readFile(join(testDir, "AGENTS.md"), "utf-8");
    expect(content).toContain("harness");
    expect(content).toContain("spec");
    expect(content).toContain("interop");
  });

  test("preserves existing AGENTS.md", async () => {
    await writeFile(join(testDir, "AGENTS.md"), "# Custom agents\n");

    const created = await writeAgentsMd(testDir, false);
    expect(created).toBe(false);

    const content = await readFile(join(testDir, "AGENTS.md"), "utf-8");
    expect(content).toBe("# Custom agents\n");
  });

  test("dry run writes nothing", async () => {
    const created = await writeAgentsMd(testDir, true);
    expect(created).toBe(false);

    try {
      await readFile(join(testDir, "AGENTS.md"));
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err.code).toBe("ENOENT");
    }
  });
});
