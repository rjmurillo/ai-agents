import { describe, test, expect } from "bun:test";
import { join } from "node:path";

const cliPath = join(import.meta.dir, "..", "src", "cli.ts");

describe("CLI argument parsing", () => {
  test("--help prints usage and exits 0", async () => {
    const proc = Bun.spawn(["bun", "run", cliPath, "--help"], {
      stdout: "pipe",
    });
    const output = await new Response(proc.stdout).text();
    await proc.exited;
    expect(proc.exitCode).toBe(0);
    expect(output).toContain("Usage:");
    expect(output).toContain("init");
  });

  test("no arguments prints usage and exits non-zero", async () => {
    const proc = Bun.spawn(["bun", "run", cliPath], { stdout: "pipe" });
    const output = await new Response(proc.stdout).text();
    await proc.exited;
    expect(proc.exitCode).not.toBe(0);
    expect(output).toContain("Usage:");
  });

  test("unknown command exits non-zero", async () => {
    const proc = Bun.spawn(["bun", "run", cliPath, "bogus"], { stderr: "pipe" });
    const stderr = await new Response(proc.stderr).text();
    await proc.exited;
    expect(proc.exitCode).not.toBe(0);
    expect(stderr).toContain("Unknown command");
  });

  test("init command runs stub", async () => {
    const proc = Bun.spawn(["bun", "run", cliPath, "init", "."], {
      stdout: "pipe",
    });
    const output = await new Response(proc.stdout).text();
    await proc.exited;
    expect(proc.exitCode).toBe(0);
    expect(output).toContain("ai-agents init");
  });
});
