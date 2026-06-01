import { describe, test, expect } from "bun:test";
import { parseTarget } from "../src/cli.js";

describe("parseTarget", () => {
  test("accepts claude", () => {
    expect(parseTarget("claude")).toBe("claude");
  });

  test("accepts copilot", () => {
    expect(parseTarget("copilot")).toBe("copilot");
  });

  test("accepts both", () => {
    expect(parseTarget("both")).toBe("both");
  });

  test("rejects an unknown target", () => {
    expect(() => parseTarget("gemini")).toThrow(/Invalid --target "gemini"/);
  });

  test("rejects an empty target", () => {
    expect(() => parseTarget("")).toThrow(/Invalid --target/);
  });

  test("is case-sensitive: Claude is not claude", () => {
    expect(() => parseTarget("Claude")).toThrow(/Invalid --target "Claude"/);
  });

  test("error message lists the valid targets", () => {
    expect(() => parseTarget("none")).toThrow(/claude, copilot, both/);
  });
});
