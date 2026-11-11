import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, readFile, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { FsTargetEmitter } from "../src/target/emitter-fs.js";
import { hashContent } from "../src/target/version-pin.js";

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
  test("writes file with nested directories", async () => {
    const entry = { relativePath: "commands/build.md", size: 5 };
    const content = Buffer.from("hello");

    await emitter.emit(entry, content, { targetDir: testDir, force: false, dryRun: false });

    const written = await readFile(join(testDir, ".claude", "commands", "build.md"), "utf-8");
    expect(written).toBe("hello");
  });

  test("rejects path traversal in relativePath (CWE-22)", async () => {
    const entry = { relativePath: "../../outside.md", size: 4 };
    const content = Buffer.from("evil");
    await expect(
      emitter.emit(entry, content, { targetDir: testDir, force: false, dryRun: false }),
    ).rejects.toThrow(/Path traversal detected/);
  });

  test("rejects absolute relativePath (CWE-22)", async () => {
    const entry = { relativePath: "/etc/passwd", size: 0 };
    const content = Buffer.from("");
    await expect(
      emitter.emit(entry, content, { targetDir: testDir, force: false, dryRun: false }),
    ).rejects.toThrow(/Path traversal detected/);
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

describe("FsTargetEmitter.diverges", () => {
  const ctx = () => ({ targetDir: testDir, force: false, dryRun: false });
  const entry = { relativePath: "skills/spec/SKILL.md", size: 1 };

  async function seed(content: string): Promise<void> {
    const dest = join(testDir, ".claude", "skills", "spec");
    await mkdir(dest, { recursive: true });
    await writeFile(join(dest, "SKILL.md"), content);
  }

  test("is false when the file does not exist", async () => {
    expect(await emitter.diverges(entry, Buffer.from("new"), ctx())).toBe(false);
  });

  test("is false when the file already holds the incoming content", async () => {
    await seed("new");
    expect(await emitter.diverges(entry, Buffer.from("new"), ctx())).toBe(false);
  });

  test("is true for an existing file with no recorded hash", async () => {
    await seed("mine");
    expect(await emitter.diverges(entry, Buffer.from("new"), ctx())).toBe(true);
  });

  test("is false when the file still matches the recorded hash", async () => {
    await seed("old");
    const recorded = { [entry.relativePath]: hashContent(Buffer.from("old")) };
    const aware = new FsTargetEmitter(recorded);
    expect(await aware.diverges(entry, Buffer.from("new"), ctx())).toBe(false);
  });

  test("is true when the file differs from the recorded hash", async () => {
    await seed("mine");
    const recorded = { [entry.relativePath]: hashContent(Buffer.from("old")) };
    const aware = new FsTargetEmitter(recorded);
    expect(await aware.diverges(entry, Buffer.from("new"), ctx())).toBe(true);
  });

  test("rejects path traversal (CWE-22)", async () => {
    await expect(
      emitter.diverges({ relativePath: "../../x", size: 1 }, Buffer.from("x"), ctx()),
    ).rejects.toThrow(/Path traversal detected/);
  });

  test("installedHashes reports each emitted entry, dry run included", async () => {
    await emitter.emit(entry, Buffer.from("new"), { ...ctx(), dryRun: true });
    expect(emitter.installedHashes()).toEqual({
      [entry.relativePath]: hashContent(Buffer.from("new")),
    });
  });
});
