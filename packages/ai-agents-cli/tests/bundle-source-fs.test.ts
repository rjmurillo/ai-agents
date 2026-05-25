import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { FsBundleSource } from "../src/io/bundle-source-fs.js";

let assetsDir: string;

beforeEach(async () => {
  assetsDir = await mkdtemp(join(tmpdir(), "bundle-source-"));
});

afterEach(async () => {
  await rm(assetsDir, { recursive: true, force: true });
});

describe("FsBundleSource", () => {
  test("list yields nothing for empty directory", async () => {
    const source = new FsBundleSource(assetsDir);
    const entries = [];
    for await (const e of source.list()) entries.push(e);
    expect(entries).toHaveLength(0);
  });

  test("list yields files with relative paths and sizes", async () => {
    await writeFile(join(assetsDir, "a.md"), "hi");
    await writeFile(join(assetsDir, "b.md"), "world!");
    const source = new FsBundleSource(assetsDir);

    const entries = [];
    for await (const e of source.list()) entries.push(e);
    entries.sort((x, y) => x.relativePath.localeCompare(y.relativePath));

    expect(entries).toHaveLength(2);
    expect(entries[0].relativePath).toBe("a.md");
    expect(entries[0].size).toBe(2);
    expect(entries[1].relativePath).toBe("b.md");
    expect(entries[1].size).toBe(6);
  });

  test("list recurses into subdirectories", async () => {
    await mkdir(join(assetsDir, "commands"), { recursive: true });
    await writeFile(join(assetsDir, "commands", "build.md"), "x");
    const source = new FsBundleSource(assetsDir);

    const entries = [];
    for await (const e of source.list()) entries.push(e);

    expect(entries).toHaveLength(1);
    expect(entries[0].relativePath).toBe(join("commands", "build.md"));
  });

  test("read returns file contents as Buffer", async () => {
    await writeFile(join(assetsDir, "a.md"), "payload");
    const source = new FsBundleSource(assetsDir);

    const buf = await source.read({ relativePath: "a.md", size: 7 });
    expect(buf.toString("utf-8")).toBe("payload");
  });
});
