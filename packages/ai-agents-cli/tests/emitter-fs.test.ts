import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { FsTargetEmitter } from "../src/target/emitter-fs.js";

let testDir: string;
let emitter: FsTargetEmitter;

beforeEach(async () => {
  testDir = await mkdtemp(join(tmpdir(), "emitter-fs-"));
  emitter = new FsTargetEmitter();
});

afterEach(async () => {
  await rm(testDir, { recursive: true, force: true });
});

describe("FsTargetEmitter", () => {
  test("canEmit returns true", () => {
    expect(emitter.canEmit({ targetDir: testDir, force: false, dryRun: false })).toBe(true);
  });

  test("writes file with nested directories", async () => {
    const entry = { relativePath: "commands/build.md", size: 5 };
    const content = Buffer.from("hello");

    await emitter.emit(entry, content, { targetDir: testDir, force: false, dryRun: false });

    const written = await readFile(join(testDir, ".claude", "commands", "build.md"), "utf-8");
    expect(written).toBe("hello");
  });

  test("dry run writes nothing", async () => {
    const entry = { relativePath: "agents/test.md", size: 4 };
    const content = Buffer.from("test");

    await emitter.emit(entry, content, { targetDir: testDir, force: false, dryRun: true });

    try {
      await readFile(join(testDir, ".claude", "agents", "test.md"));
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err.code).toBe("ENOENT");
    }
  });
});
