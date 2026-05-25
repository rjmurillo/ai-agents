import { describe, it, expect } from "bun:test";
import { commandSyntaxTranslator } from "../src/transforms/command-syntax-translator.js";
import type { BundleEntry, TargetContext } from "../src/types.js";

describe("commandSyntaxTranslator", () => {
  const copilotCtx: TargetContext = { target: "copilot", destDir: "/tmp" };
  const claudeCtx: TargetContext = { target: "claude", destDir: "/tmp" };

  it("translates slash commands to prompt references", () => {
    const entry: BundleEntry = {
      relativePath: ".claude/commands/build.md",
      category: "command",
    };
    const content = Buffer.from("Run /spec then /build to start.");

    const result = commandSyntaxTranslator(entry, content, copilotCtx);

    expect(result).not.toBeNull();
    const text = result!.content.toString("utf-8");
    expect(text).toContain("`.github/prompts/spec.md`");
    expect(text).toContain("`.github/prompts/build.md`");
  });

  it("comments out @import directives", () => {
    const entry: BundleEntry = {
      relativePath: "CLAUDE.md",
      category: "config",
    };
    const content = Buffer.from("@AGENTS.md\nSome instructions.");

    const result = commandSyntaxTranslator(entry, content, copilotCtx);

    expect(result).not.toBeNull();
    const text = result!.content.toString("utf-8");
    expect(text).toContain("<!-- @AGENTS.md -->");
    expect(text).toContain("Some instructions.");
  });

  it("comments out @import directives with paths containing slashes before expanding slash commands", () => {
    const entry: BundleEntry = {
      relativePath: "CLAUDE.md",
      category: "config",
    };
    const content = Buffer.from("@agents/analyst.md\nRun /spec to plan.");

    const result = commandSyntaxTranslator(entry, content, copilotCtx);

    expect(result).not.toBeNull();
    const text = result!.content.toString("utf-8");
    // The @import directive must be inside an HTML comment, not exposed raw.
    expect(text).not.toMatch(/^@agents\/analyst\.md/m);
    expect(text).toContain("<!--");
    // The slash command on a normal line must still be translated.
    expect(text).toContain("`.github/prompts/spec.md`");
  });

  it("passes through non-command entries unchanged", () => {
    const entry: BundleEntry = {
      relativePath: ".claude/agents/analyst.md",
      category: "agent",
    };
    const content = Buffer.from("Use /build for implementation.");

    const result = commandSyntaxTranslator(entry, content, copilotCtx);

    expect(result).not.toBeNull();
    expect(result!.content.toString("utf-8")).toBe(
      "Use /build for implementation.",
    );
  });

  it("passes through when target is claude", () => {
    const entry: BundleEntry = {
      relativePath: ".claude/commands/build.md",
      category: "command",
    };
    const content = Buffer.from("Run /spec to start.");

    const result = commandSyntaxTranslator(entry, content, claudeCtx);

    expect(result).not.toBeNull();
    expect(result!.content.toString("utf-8")).toBe("Run /spec to start.");
  });
});
