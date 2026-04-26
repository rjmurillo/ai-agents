import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { writeVersionPin, computeManifestHash } from "../src/target/version-pin.js";

let testDir: string;

beforeEach(async () => {
  testDir = await mkdtemp(join(tmpdir(), "version-pin-"));
});

afterEach(async () => {
  await rm(testDir, { recursive: true, force: true });
});

describe("computeManifestHash", () => {
  test("produces consistent hash for same entries", () => {
    const a = computeManifestHash(["commands/build.md", "agents/analyst.md"]);
    const b = computeManifestHash(["agents/analyst.md", "commands/build.md"]);
    expect(a).toBe(b);
  });

  test("produces different hash for different entries", () => {
    const a = computeManifestHash(["commands/build.md"]);
    const b = computeManifestHash(["commands/test.md"]);
    expect(a).not.toBe(b);
  });

  test("returns 16-char hex string", () => {
    const hash = computeManifestHash(["a", "b"]);
    expect(hash).toMatch(/^[0-9a-f]{16}$/);
  });
});

describe("writeVersionPin", () => {
  test("writes valid version pin JSON", async () => {
    const entries = ["commands/build.md", "agents/analyst.md"];
    await writeVersionPin(testDir, "0.1.0", entries, false);

    const raw = await readFile(join(testDir, ".claude", ".ai-agents-version.json"), "utf-8");
    const pin = JSON.parse(raw);

    expect(pin.version).toBe("0.1.0");
    expect(pin.manifestHash).toMatch(/^[0-9a-f]{16}$/);
    expect(pin.manifestHash).toBe(computeManifestHash(entries));
    expect(pin.installedAt).toBeTruthy();
    expect(pin.source).toBe("@rjmurillo/ai-agents");
  });

  test("dry run writes nothing", async () => {
    await writeVersionPin(testDir, "0.1.0", ["a"], true);

    try {
      await readFile(join(testDir, ".claude", ".ai-agents-version.json"));
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err.code).toBe("ENOENT");
    }
  });
});
