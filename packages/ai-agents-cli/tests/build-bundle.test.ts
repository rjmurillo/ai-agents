import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, writeFile, mkdir, symlink, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
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

describe("copyTree maintainer files and lib", () => {
  test("omits the root CLAUDE.md and AGENTS.md but keeps the same names inside a skill", async () => {
    await writeFile(join(src, "CLAUDE.md"), "maintainer\n");
    await writeFile(join(src, "AGENTS.md"), "maintainer\n");
    await mkdir(join(src, "skills", "alpha"), { recursive: true });
    await writeFile(join(src, "skills", "alpha", "CLAUDE.md"), "skill-level\n");
    await writeFile(join(src, "keep.md"), "k");

    await run();

    expect(existsSync(join(dest, "CLAUDE.md"))).toBe(false);
    expect(existsSync(join(dest, "AGENTS.md"))).toBe(false);
    expect(await readFile(join(dest, "keep.md"), "utf8")).toBe("k");
    expect(await readFile(join(dest, "skills", "alpha", "CLAUDE.md"), "utf8")).toBe("skill-level\n");
  });

  test("ships lib so skill scripts can import their helpers", async () => {
    await mkdir(join(src, "lib", "hook_utilities"), { recursive: true });
    await writeFile(join(src, "lib", "paths.py"), "x = 1\n");
    await writeFile(join(src, "lib", "hook_utilities", "__init__.py"), "");
    await mkdir(join(src, "lib", "__pycache__"), { recursive: true });
    await writeFile(join(src, "lib", "__pycache__", "paths.cpython-314.pyc"), "b");

    await run();

    expect(await readFile(join(dest, "lib", "paths.py"), "utf8")).toBe("x = 1\n");
    expect(existsSync(join(dest, "lib", "hook_utilities", "__init__.py"))).toBe(true);
    expect(existsSync(join(dest, "lib", "__pycache__"))).toBe(false);
  });

  test("still omits hooks, settings.json, and the github skill", async () => {
    await mkdir(join(src, "hooks"), { recursive: true });
    await writeFile(join(src, "hooks", "h.py"), "h");
    await writeFile(join(src, "settings.json"), "{}");
    await mkdir(join(src, "skills", "github"), { recursive: true });
    await writeFile(join(src, "skills", "github", "SKILL.md"), "g");

    await run();

    expect(existsSync(join(dest, "hooks"))).toBe(false);
    expect(existsSync(join(dest, "settings.json"))).toBe(false);
    expect(existsSync(join(dest, "skills", "github"))).toBe(false);
  });
});

describe("bundle of the real .claude tree", () => {
  const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

  test("carries lib for the skill scripts and no maintainer instructions", async () => {
    const out = join(root, "real");
    const ctx = { allowedRoot: join(repoRoot, "src", "claude"), ancestors: [] };

    const count = await copyTree(join(repoRoot, ".claude"), out, 0, ctx);

    expect(count).toBeGreaterThan(0);
    for (const needed of [
      "lib/paths.py",
      "lib/hook_utilities/path_safety.py",
      "lib/github_core/api.py",
      "lib/failure_classifier/__init__.py",
      "skills/chestertons-fence/scripts/investigate.py",
    ]) {
      expect(existsSync(join(out, needed)), needed).toBe(true);
    }
    expect(existsSync(join(out, "CLAUDE.md"))).toBe(false);
    expect(existsSync(join(out, "AGENTS.md"))).toBe(false);
    expect(existsSync(join(out, "hooks"))).toBe(false);
  });
});
