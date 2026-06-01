import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, mkdir, writeFile, access } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { runInit } from "../src/cli.js";

let assetsDir: string;
let targetDir: string;

beforeEach(async () => {
  assetsDir = await mkdtemp(join(tmpdir(), "run-init-target-assets-"));
  targetDir = await mkdtemp(join(tmpdir(), "run-init-target-dir-"));

  await mkdir(join(assetsDir, "agents"), { recursive: true });
  await writeFile(join(assetsDir, "agents", "implementer.md"), "# implementer\n");
});

afterEach(async () => {
  await rm(assetsDir, { recursive: true, force: true });
  await rm(targetDir, { recursive: true, force: true });
});

function claudePath(): string {
  return join(targetDir, "CLAUDE.md");
}

function copilotPath(): string {
  return join(targetDir, ".github", "copilot-instructions.md");
}

describe("runInit --target dispatch", () => {
  test("claude target writes CLAUDE.md and not copilot instructions", async () => {
    const code = await runInit({
      targetDir,
      force: false,
      dryRun: false,
      assetsDir,
      version: "0.1.0",
      target: "claude",
    });

    expect(code).toBe(0);
    await access(claudePath());
    await expect(access(copilotPath())).rejects.toThrow();
  });

  test("copilot target writes copilot instructions and not CLAUDE.md", async () => {
    const code = await runInit({
      targetDir,
      force: false,
      dryRun: false,
      assetsDir,
      version: "0.1.0",
      target: "copilot",
    });

    expect(code).toBe(0);
    await access(copilotPath());
    await expect(access(claudePath())).rejects.toThrow();
  });

  test("both target writes CLAUDE.md and copilot instructions", async () => {
    const code = await runInit({
      targetDir,
      force: false,
      dryRun: false,
      assetsDir,
      version: "0.1.0",
      target: "both",
    });

    expect(code).toBe(0);
    await access(claudePath());
    await access(copilotPath());
  });

  test("omitted target defaults to claude", async () => {
    const code = await runInit({
      targetDir,
      force: false,
      dryRun: false,
      assetsDir,
      version: "0.1.0",
    });

    expect(code).toBe(0);
    await access(claudePath());
    await expect(access(copilotPath())).rejects.toThrow();
  });

  test("dry-run with both target writes neither instruction file", async () => {
    const code = await runInit({
      targetDir,
      force: false,
      dryRun: true,
      assetsDir,
      version: "0.1.0",
      target: "both",
    });

    expect(code).toBe(0);
    await expect(access(claudePath())).rejects.toThrow();
    await expect(access(copilotPath())).rejects.toThrow();
  });
});
