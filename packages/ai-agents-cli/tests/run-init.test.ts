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

// Capture process.stdout and process.stderr writes made while fn runs.
async function capture<T>(
  fn: () => Promise<T>,
): Promise<{ result: T; stdout: string; stderr: string }> {
  const outWrite = process.stdout.write;
  const errWrite = process.stderr.write;
  let stdout = "";
  let stderr = "";
  process.stdout.write = ((chunk: string | Uint8Array) => {
    stdout += String(chunk);
    return true;
  }) as typeof process.stdout.write;
  process.stderr.write = ((chunk: string | Uint8Array) => {
    stderr += String(chunk);
    return true;
  }) as typeof process.stderr.write;
  try {
    return { result: await fn(), stdout, stderr };
  } finally {
    process.stdout.write = outWrite;
    process.stderr.write = errWrite;
  }
}

const base = () => ({ force: false, dryRun: false, version: "0.1.0" });
const agentPath = () => join(targetDir, ".claude", "agents", "implementer.md");
const pinPath = () => join(targetDir, ".claude", ".ai-agents-version.json");

describe("runInit local modification guard (issue #7218)", () => {
  test("clean install writes files and records a content hash per file", async () => {
    const code = await runInit({ ...base(), targetDir, assetsDir });

    expect(code).toBe(0);
    const pin = JSON.parse(await readFile(pinPath(), "utf-8"));
    expect(Object.keys(pin.files).sort()).toEqual(["AGENTS.md", "agents/implementer.md"]);
    expect(pin.files["agents/implementer.md"]).toMatch(/^[0-9a-f]{64}$/);
  });

  test("re-run on an unmodified install exits 0", async () => {
    await runInit({ ...base(), targetDir, assetsDir });
    const code = await runInit({ ...base(), targetDir, assetsDir });

    expect(code).toBe(0);
    expect(await readFile(agentPath(), "utf-8")).toBe("# implementer\n");
  });

  test("re-run picks up a new bundle version over an unmodified install", async () => {
    await runInit({ ...base(), targetDir, assetsDir });
    await writeFile(join(assetsDir, "agents", "implementer.md"), "# implementer v2\n");

    const code = await runInit({ ...base(), targetDir, assetsDir });

    expect(code).toBe(0);
    expect(await readFile(agentPath(), "utf-8")).toBe("# implementer v2\n");
  });

  test("modified file without --force exits 2, lists the file, and writes nothing", async () => {
    await runInit({ ...base(), targetDir, assetsDir });
    await writeFile(agentPath(), "MY CUSTOM\n");
    // A second bundle file would be new on disk. A refused run must not add it.
    await writeFile(join(assetsDir, "agents", "analyst.md"), "# analyst\n");
    const pinBefore = await readFile(pinPath(), "utf-8");

    const { result, stderr } = await capture(() =>
      runInit({ ...base(), targetDir, assetsDir }),
    );

    expect(result).toBe(2);
    expect(stderr).toContain("agents/implementer.md");
    expect(await readFile(agentPath(), "utf-8")).toBe("MY CUSTOM\n");
    await expect(access(join(targetDir, ".claude", "agents", "analyst.md"))).rejects.toThrow();
    expect(await readFile(pinPath(), "utf-8")).toBe(pinBefore);
  });

  test("modified file with --force is overwritten and exits 0", async () => {
    await runInit({ ...base(), targetDir, assetsDir });
    await writeFile(agentPath(), "MY CUSTOM\n");

    const code = await runInit({ ...base(), force: true, targetDir, assetsDir });

    expect(code).toBe(0);
    expect(await readFile(agentPath(), "utf-8")).toBe("# implementer\n");
  });

  test("pre-existing unpinned file that differs counts as diverging", async () => {
    await mkdir(join(targetDir, ".claude", "agents"), { recursive: true });
    await writeFile(agentPath(), "FROM ANOTHER TOOL\n");

    const { result, stderr } = await capture(() =>
      runInit({ ...base(), targetDir, assetsDir }),
    );

    expect(result).toBe(2);
    expect(stderr).toContain("agents/implementer.md");
    expect(await readFile(agentPath(), "utf-8")).toBe("FROM ANOTHER TOOL\n");
    await expect(access(pinPath())).rejects.toThrow();
  });

  test("pre-existing unpinned file with identical content is not a divergence", async () => {
    await mkdir(join(targetDir, ".claude", "agents"), { recursive: true });
    await writeFile(agentPath(), "# implementer\n");

    const code = await runInit({ ...base(), targetDir, assetsDir });

    expect(code).toBe(0);
  });

  test("old-format pin without hashes is read as no record", async () => {
    await mkdir(join(targetDir, ".claude", "agents"), { recursive: true });
    await writeFile(
      pinPath(),
      JSON.stringify({
        version: "0.0.9",
        manifestHash: "0123456789abcdef",
        installedAt: "2026-01-01T00:00:00.000Z",
        source: "@rjmurillo/ai-agents",
      }),
    );
    await writeFile(agentPath(), "OLD INSTALL EDIT\n");

    const { result } = await capture(() => runInit({ ...base(), targetDir, assetsDir }));

    expect(result).toBe(2);
    expect(await readFile(agentPath(), "utf-8")).toBe("OLD INSTALL EDIT\n");
  });

  test("--force upgrades an old-format pin to one with hashes", async () => {
    await mkdir(join(targetDir, ".claude"), { recursive: true });
    await writeFile(pinPath(), JSON.stringify({ version: "0.0.9" }));

    const code = await runInit({ ...base(), force: true, targetDir, assetsDir });

    expect(code).toBe(0);
    const pin = JSON.parse(await readFile(pinPath(), "utf-8"));
    expect(pin.files["agents/implementer.md"]).toMatch(/^[0-9a-f]{64}$/);
  });

  test("an unreadable pin file is read as no record", async () => {
    await mkdir(join(targetDir, ".claude"), { recursive: true });
    await writeFile(pinPath(), "{not json");

    const code = await runInit({ ...base(), targetDir, assetsDir });

    expect(code).toBe(0);
  });
});

describe("runInit --dry-run output (issue #7229)", () => {
  test("says 'Would vendor' and lists the skipped writes", async () => {
    const { result, stdout } = await capture(() =>
      runInit({ ...base(), dryRun: true, targetDir, assetsDir, target: "both" }),
    );

    expect(result).toBe(0);
    expect(stdout).toContain("Would vendor 2 files.");
    expect(stdout).not.toContain("Vendored");
    expect(stdout).toContain("CLAUDE.md");
    expect(stdout).toContain(".github/copilot-instructions.md");
    expect(stdout).toContain("AGENTS.md");
    expect(stdout).toContain(".claude/.ai-agents-version.json");
    expect(stdout).not.toContain("run /spec");
  });

  test("omits the copilot file for the claude target", async () => {
    const { stdout } = await capture(() =>
      runInit({ ...base(), dryRun: true, targetDir, assetsDir, target: "claude" }),
    );

    expect(stdout).not.toContain("copilot-instructions.md");
  });

  test("a real run still says 'Vendored'", async () => {
    const { stdout } = await capture(() => runInit({ ...base(), targetDir, assetsDir }));

    expect(stdout).toContain("Vendored 2 files.");
  });
});

describe("runInit half-present marker block (issue #7229)", () => {
  test("returns 1 and names CLAUDE.md when only the begin marker exists", async () => {
    const claudeMd = join(targetDir, "CLAUDE.md");
    await writeFile(claudeMd, "# mine\n<!-- ai-agents:begin -->\nstuff\n");

    const { result, stderr } = await capture(() =>
      runInit({ ...base(), targetDir, assetsDir }),
    );

    expect(result).toBe(1);
    expect(stderr).toContain(claudeMd);
    expect(await readFile(claudeMd, "utf-8")).toBe("# mine\n<!-- ai-agents:begin -->\nstuff\n");
  });
});
