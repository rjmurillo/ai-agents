import { describe, test, expect } from "bun:test";
import { parsePacks, makePackFilter, knownPacks } from "../src/packs.js";
import type { BundleEntry } from "../src/types.js";

const entry = (relativePath: string): BundleEntry => ({ relativePath });

describe("knownPacks", () => {
  test("includes the business pack", () => {
    expect(knownPacks()).toContain("business");
  });
});

describe("parsePacks", () => {
  test("empty input yields an empty set", () => {
    expect(parsePacks(undefined).size).toBe(0);
    expect(parsePacks([]).size).toBe(0);
  });

  test("accepts a single pack id", () => {
    expect([...parsePacks(["business"])]).toEqual(["business"]);
  });

  test("accepts comma-separated and repeated values, de-duplicated", () => {
    expect([...parsePacks(["business,business"])]).toEqual(["business"]);
    expect([...parsePacks(["business", "business"])]).toEqual(["business"]);
  });

  test("throws on an unknown pack id", () => {
    expect(() => parsePacks(["nope"])).toThrow(/Unknown pack "nope"/);
  });

  test("rejects inherited object properties", () => {
    expect(() => parsePacks(["toString"])).toThrow(/Unknown pack "toString"/);
  });
});

describe("makePackFilter", () => {
  test("drops a pack skill when its pack is not requested", () => {
    const filter = makePackFilter(new Set());
    expect(filter(entry("skills/business-strategy/SKILL.md"), null as never)).toBeNull();
  });

  test("keeps a pack skill when its pack is requested", () => {
    const filter = makePackFilter(new Set(["business"]));
    const e = entry("skills/business-strategy/SKILL.md");
    expect(filter(e, null as never)).toBe(e);
  });

  test("always keeps non-pack skills and non-skill entries", () => {
    const filter = makePackFilter(new Set());
    const core = entry("skills/review/SKILL.md");
    const agent = entry("agents/implementer.md");
    expect(filter(core, null as never)).toBe(core);
    expect(filter(agent, null as never)).toBe(agent);
  });

  test("normalizes backslash paths", () => {
    const filter = makePackFilter(new Set());
    expect(
      filter(entry("skills\\business-strategy\\references\\x.md"), null as never),
    ).toBeNull();
  });

  test("normalizes skill directory casing", () => {
    const filter = makePackFilter(new Set());
    expect(filter(entry("Skills/BUSINESS-STRATEGY/SKILL.md"), null as never)).toBeNull();
  });
});
