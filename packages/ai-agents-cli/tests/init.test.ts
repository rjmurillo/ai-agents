import { describe, test, expect } from "bun:test";
import { init } from "../src/init.js";
import type {
  BundleEntry,
  BundleSource,
  TargetContext,
  TargetEmitter,
  Transform,
} from "../src/types.js";

function makeSource(entries: BundleEntry[]): BundleSource {
  return {
    async *list() {
      for (const entry of entries) yield entry;
    },
    async read(entry) {
      return Buffer.from(`content:${entry.relativePath}`);
    },
  };
}

function makeEmitter(canEmit = true): TargetEmitter & {
  written: Array<{ entry: BundleEntry; content: Buffer }>;
} {
  const written: Array<{ entry: BundleEntry; content: Buffer }> = [];
  return {
    written,
    canEmit() {
      return canEmit;
    },
    async emit(entry, content) {
      written.push({ entry, content });
    },
  };
}

const target: TargetContext = {
  targetDir: "/tmp/x",
  force: false,
  dryRun: false,
};

describe("init", () => {
  test("returns 2 when canEmit is false", async () => {
    const code = await init(
      makeSource([{ relativePath: "a", size: 1 }]),
      makeEmitter(false),
      target,
    );
    expect(code).toBe(2);
  });

  test("vendors all entries when no transforms", async () => {
    const emitter = makeEmitter();
    const entries: BundleEntry[] = [
      { relativePath: "a.md", size: 1 },
      { relativePath: "b.md", size: 1 },
    ];
    const code = await init(makeSource(entries), emitter, target);
    expect(code).toBe(0);
    expect(emitter.written).toHaveLength(2);
  });

  test("transform returning null skips entry", async () => {
    const emitter = makeEmitter();
    const skipB: Transform = (entry) =>
      entry.relativePath === "b.md" ? null : entry;
    const entries: BundleEntry[] = [
      { relativePath: "a.md", size: 1 },
      { relativePath: "b.md", size: 1 },
    ];
    const code = await init(makeSource(entries), emitter, target, [skipB]);
    expect(code).toBe(0);
    expect(emitter.written).toHaveLength(1);
    expect(emitter.written[0].entry.relativePath).toBe("a.md");
  });

  test("returns 0 with empty bundle", async () => {
    const emitter = makeEmitter();
    const code = await init(makeSource([]), emitter, target);
    expect(code).toBe(0);
    expect(emitter.written).toHaveLength(0);
  });

  test("returns 1 when source.read throws", async () => {
    const emitter = makeEmitter();
    const source: BundleSource = {
      async *list() {
        yield { relativePath: "a.md", size: 1 };
      },
      async read() {
        throw new Error("boom");
      },
    };
    const code = await init(source, emitter, target);
    expect(code).toBe(1);
  });
});
