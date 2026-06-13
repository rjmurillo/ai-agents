import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, mkdir, writeFile, readFile, access } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { runInit } from "../src/cli.js";

let assetsDir: string;
let targetDir: string;

beforeEach(async () => {
  assetsDir = await mkdtemp(join(tmpdir(), "run-init-assets-"));
  targetDir = await mkdtemp(join(tmpdir(), "run-init-target-"));

  // Seed a tiny bundle: one nested file is enough to prove the pipeline runs.
  await mkdir(join(assetsDir, "agents"), { recursive: true });
  await writeFile(join(assetsDir, "agents", "implementer.md"), "# implementer\n");
  await writeFile(join(assetsDir, "AGENTS.md"), "bundled agents.md\n");
});

afterEach(async () => {
  await rm(assetsDir, { recursive: true, force: true });
  await rm(targetDir, { recursive: true, force: true });
});

describe("runInit (end-to-end pipeline)", () => {
  test("invokes vendoring pipeline and writes files under .claude/", async () => {
    const code = await runInit({
      targetDir,
      force: false,
      dryRun: false,
      assetsDir,
      version: "0.1.0",
    });

    expect(code).toBe(0);
    // Bundle entries land under .claude/
    await access(join(targetDir, ".claude", "agents", "implementer.md"));
    await access(join(targetDir, ".claude", "AGENTS.md"));
    // Version pin recorded
    const pin = JSON.parse(
      await readFile(join(targetDir, ".claude", ".ai-agents-version.json"), "utf-8"),
    );
    expect(pin.version).toBe("0.1.0");
    expect(pin.manifestHash).toMatch(/^[0-9a-f]{16}$/);
    // CLAUDE.md and AGENTS.md (target stub) created at repo root
    await access(join(targetDir, "CLAUDE.md"));
    await access(join(targetDir, "AGENTS.md"));
  });

  test("--dry-run writes nothing", async () => {
    const code = await runInit({
      targetDir,
      force: false,
      dryRun: true,
      assetsDir,
      version: "0.1.0",
    });

    expect(code).toBe(0);
    await expect(
      access(join(targetDir, ".claude", "agents", "implementer.md")),
    ).rejects.toThrow();
    await expect(
      access(join(targetDir, ".claude", ".ai-agents-version.json")),
    ).rejects.toThrow();
    await expect(access(join(targetDir, "CLAUDE.md"))).rejects.toThrow();
  });

  test("excludes optional pack skills by default", async () => {
    await mkdir(join(assetsDir, "skills", "business-strategy"), { recursive: true });
    await writeFile(join(assetsDir, "skills", "business-strategy", "SKILL.md"), "# biz\n");
    await mkdir(join(assetsDir, "skills", "review"), { recursive: true });
    await writeFile(join(assetsDir, "skills", "review", "SKILL.md"), "# review\n");

    const code = await runInit({ targetDir, force: false, dryRun: false, assetsDir, version: "0.1.0" });
    expect(code).toBe(0);
    // Core skill vendored; pack skill excluded.
    await access(join(targetDir, ".claude", "skills", "review", "SKILL.md"));
    await expect(
      access(join(targetDir, ".claude", "skills", "business-strategy", "SKILL.md")),
    ).rejects.toThrow();
  });

  test("installs an optional pack when requested via packs", async () => {
    await mkdir(join(assetsDir, "skills", "business-strategy"), { recursive: true });
    await writeFile(join(assetsDir, "skills", "business-strategy", "SKILL.md"), "# biz\n");

    const code = await runInit({
      targetDir,
      force: false,
      dryRun: false,
      assetsDir,
      version: "0.1.0",
      packs: ["business"],
    });
    expect(code).toBe(0);
    await access(join(targetDir, ".claude", "skills", "business-strategy", "SKILL.md"));
  });
});
