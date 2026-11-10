import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  BEGIN_MARKER,
  END_MARKER,
  MarkerBlockError,
  appendMarkerBlock,
} from "../src/target/append-marker-block.js";

const BLOCK = `${BEGIN_MARKER}\nbody\n${END_MARKER}`;

let dir: string;
let file: string;

beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), "marker-block-"));
  file = join(dir, "CLAUDE.md");
});

afterEach(async () => {
  await rm(dir, { recursive: true, force: true });
});

describe("appendMarkerBlock", () => {
  test("appends one block to a file with no markers", async () => {
    await writeFile(file, "# mine\n");
    await appendMarkerBlock(file, BLOCK, false);
    const text = await readFile(file, "utf-8");
    expect(text.split(BEGIN_MARKER)).toHaveLength(2);
  });

  test("leaves a file with both markers untouched", async () => {
    const original = `# mine\n${BLOCK}\n`;
    await writeFile(file, original);
    await appendMarkerBlock(file, BLOCK, false);
    expect(await readFile(file, "utf-8")).toBe(original);
  });

  test("throws and names the file when only the begin marker exists", async () => {
    const original = `# mine\n${BEGIN_MARKER}\nbody\n`;
    await writeFile(file, original);
    const failure = appendMarkerBlock(file, BLOCK, false);
    await expect(failure).rejects.toBeInstanceOf(MarkerBlockError);
    await expect(failure).rejects.toThrow(file);
    expect(await readFile(file, "utf-8")).toBe(original);
  });

  test("throws and names the file when only the end marker exists", async () => {
    const original = `# mine\nbody\n${END_MARKER}\n`;
    await writeFile(file, original);
    await expect(appendMarkerBlock(file, BLOCK, false)).rejects.toThrow(file);
    expect(await readFile(file, "utf-8")).toBe(original);
  });
});
