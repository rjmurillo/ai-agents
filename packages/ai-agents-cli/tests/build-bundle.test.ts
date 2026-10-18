import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, writeFile, mkdir, symlink, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { copyTree } from "../scripts/build-bundle.js";

let root: string;
let src: string;
let plugin: string;
let dest: string;

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "build-bundle-"));
  src = join(root, ".claude");
  plugin = join(root, "src", "claude");
  dest = join(root, "out");
  await mkdir(join(plugin, "skills", "alpha"), { recursive: true });
  await mkdir(src, { recursive: true });
  await writeFile(join(plugin, "skills", "alpha", "SKILL.md"), "alpha\n");
});

afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

const run = () => copyTree(src, dest, 0, { allowedRoot: plugin, ancestors: [] });

describe("copyTree link handling", () => {
  test("copies a skill linked into the plugin tree as real bytes", async () => {
    await mkdir(join(src, "skills"), { recursive: true });
    await symlink(join(plugin, "skills", "alpha"), join(src, "skills", "alpha"), "dir");

    expect(await run()).toBe(1);
    expect(await readFile(join(dest, "skills", "alpha", "SKILL.md"), "utf8")).toBe("alpha\n");
  });

  test("refuses a link to an ancestor instead of recursing until ELOOP", async () => {
    await mkdir(join(src, "skills"), { recursive: true });
    await symlink(join(plugin, "skills", "alpha"), join(src, "skills", "alpha"), "dir");
    await symlink(join(plugin, "skills"), join(plugin, "skills", "alpha", "loop"), "dir");

    await expect(run()).rejects.toThrow(/link cycle/);
  });

  test("refuses a link to the directory being copied", async () => {
    await mkdir(join(src, "sub"), { recursive: true });
    await writeFile(join(src, "sub", "f.txt"), "x");
    await symlink(join(src, "sub"), join(src, "sub", "self"), "dir");
    const ctx = { allowedRoot: root, ancestors: [] };

    await expect(copyTree(src, dest, 0, ctx)).rejects.toThrow(/link cycle/);
  });

  test("refuses a link inside the repo but outside the plugin tree", async () => {
    await mkdir(join(root, "docs"), { recursive: true });
    await writeFile(join(root, "docs", "secret.md"), "s");
    await symlink(join(root, "docs"), join(src, "docs"), "dir");

    await expect(run()).rejects.toThrow(/outside the plugin tree/);
  });

  test("refuses a file link outside the plugin tree", async () => {
    await writeFile(join(root, "outside.md"), "o");
    await symlink(join(root, "outside.md"), join(src, "outside.md"));

    await expect(run()).rejects.toThrow(/outside the plugin tree/);
  });
});
