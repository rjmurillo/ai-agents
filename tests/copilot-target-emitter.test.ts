import { describe, it, expect, beforeEach } from "bun:test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { CopilotTargetEmitter } from "../src/copilot-target-emitter.js";
import type { BundleEntry, TargetContext } from "../src/types.js";

describe("CopilotTargetEmitter", () => {
  let emitter: CopilotTargetEmitter;
  let tempDir: string;

  beforeEach(async () => {
    emitter = new CopilotTargetEmitter();
    tempDir = await mkdtemp(join(tmpdir(), "copilot-emitter-test-"));
  });

  describe("canEmit", () => {
    it("returns true for copilot target", () => {
      const ctx: TargetContext = { target: "copilot", destDir: tempDir };
      expect(emitter.canEmit(ctx)).toBe(true);
    });

    it("returns true for both target", () => {
      const ctx: TargetContext = { target: "both", destDir: tempDir };
      expect(emitter.canEmit(ctx)).toBe(true);
    });

    it("returns false for claude target", () => {
      const ctx: TargetContext = { target: "claude", destDir: tempDir };
      expect(emitter.canEmit(ctx)).toBe(false);
    });
  });

  describe("mapPath", () => {
    it("maps agent files to .github/copilot/agents/", () => {
      const entry: BundleEntry = {
        relativePath: ".claude/agents/analyst.md",
        category: "agent",
      };
      expect(emitter.mapPath(entry)).toBe(
        ".github/copilot/agents/analyst.agent.md",
      );
    });

    it("maps command files to .github/prompts/", () => {
      const entry: BundleEntry = {
        relativePath: ".claude/commands/build.md",
        category: "command",
      };
      expect(emitter.mapPath(entry)).toBe(".github/prompts/build.md");
    });

    it("maps CLAUDE.md to copilot-instructions.md", () => {
      const entry: BundleEntry = {
        relativePath: "CLAUDE.md",
        category: "config",
      };
      expect(emitter.mapPath(entry)).toBe(".github/copilot-instructions.md");
    });

    it("returns null for unknown categories", () => {
      const entry: BundleEntry = {
        relativePath: "README.md",
        category: "other",
      };
      expect(emitter.mapPath(entry)).toBeNull();
    });
  });

  describe("emit", () => {
    it("writes agent file to copilot layout", async () => {
      const entry: BundleEntry = {
        relativePath: ".claude/agents/analyst.md",
        category: "agent",
      };
      const ctx: TargetContext = { target: "copilot", destDir: tempDir };
      const content = Buffer.from("# Analyst Agent\n");

      await emitter.emit(entry, content, ctx);

      const written = await readFile(
        join(tempDir, ".github/copilot/agents/analyst.agent.md"),
        "utf-8",
      );
      expect(written).toBe("# Analyst Agent\n");
      await rm(tempDir, { recursive: true });
    });

    it("writes command file to prompts directory", async () => {
      const entry: BundleEntry = {
        relativePath: ".claude/commands/build.md",
        category: "command",
      };
      const ctx: TargetContext = { target: "copilot", destDir: tempDir };
      const content = Buffer.from("# Build\n");

      await emitter.emit(entry, content, ctx);

      const written = await readFile(
        join(tempDir, ".github/prompts/build.md"),
        "utf-8",
      );
      expect(written).toBe("# Build\n");
      await rm(tempDir, { recursive: true });
    });

    it("skips entries without path mapping", async () => {
      const entry: BundleEntry = {
        relativePath: "random.txt",
        category: "other",
      };
      const ctx: TargetContext = { target: "copilot", destDir: tempDir };

      await emitter.emit(entry, Buffer.from("data"), ctx);
      await rm(tempDir, { recursive: true });
    });
  });
});
