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
});
