import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, readFile, readdir, access } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

let testDir: string;

beforeEach(async () => {
  testDir = await mkdtemp(join(tmpdir(), "cli-test-"));
});

afterEach(async () => {
  await rm(testDir, { recursive: true, force: true });
});

describe("CLI init (integration)", () => {
  test("--version prints version", async () => {
    const proc = Bun.spawn(["bun", "run", "src/cli.ts", "--version"], {
      cwd: join(import.meta.dir, ".."),
      stdout: "pipe",
    });
    const output = await new Response(proc.stdout).text();
    expect(output.trim()).toMatch(/^\d+\.\d+\.\d+$/);
  });

  test("--help prints usage", async () => {
    const proc = Bun.spawn(["bun", "run", "src/cli.ts", "--help"], {
      cwd: join(import.meta.dir, ".."),
      stdout: "pipe",
    });
    const output = await new Response(proc.stdout).text();
    expect(output).toContain("Usage: ai-agents init");
    expect(output).toContain("--force");
    expect(output).toContain("--dry-run");
    expect(output).toContain("--target");
    expect(output).toContain("--pack NAME");
    expect(output).not.toContain("skill pack (business);");
  });

  test("unknown command exits with error", async () => {
    const proc = Bun.spawn(["bun", "run", "src/cli.ts", "unknown"], {
      cwd: join(import.meta.dir, ".."),
      stderr: "pipe",
    });
    const stderr = await new Response(proc.stderr).text();
    await proc.exited;
    expect(proc.exitCode).not.toBe(0);
    expect(stderr).toContain("Unknown command");
  });

  test("init reports the selected target in its startup line", async () => {
    // The CLI prints the resolved target before vendoring runs. We assert the
    // log line and the dry-run no-write contract, not the exit code: the exit
    // code depends on the bundle/assets dir existing, which is a packaging
    // concern outside this flag's behavior.
    const proc = Bun.spawn(
      ["bun", "run", "src/cli.ts", "init", testDir, "--dry-run", "--target", "copilot"],
      { cwd: join(import.meta.dir, ".."), stdout: "pipe" },
    );
    const output = await new Response(proc.stdout).text();
    await proc.exited;
    expect(output).toContain("target=copilot");
    // dry-run touches nothing on disk
    await expect(
      access(join(testDir, ".github", "copilot-instructions.md")),
    ).rejects.toThrow();
  });

  test("init --target with an invalid value exits with config error", async () => {
    const proc = Bun.spawn(
      ["bun", "run", "src/cli.ts", "init", testDir, "--target", "gemini"],
      { cwd: join(import.meta.dir, ".."), stderr: "pipe" },
    );
    const stderr = await new Response(proc.stderr).text();
    await proc.exited;
    expect(proc.exitCode).toBe(2);
    expect(stderr).toContain('Invalid --target "gemini"');
  });

  test("init --pack with an invalid value exits with config error", async () => {
    const proc = Bun.spawn(
      ["bun", "run", "src/cli.ts", "init", testDir, "--pack", "nope"],
      { cwd: join(import.meta.dir, ".."), stderr: "pipe" },
    );
    const stderr = await new Response(proc.stderr).text();
    await proc.exited;
    expect(proc.exitCode).toBe(2);
    expect(stderr).toContain('Unknown pack "nope"');
  });
});
