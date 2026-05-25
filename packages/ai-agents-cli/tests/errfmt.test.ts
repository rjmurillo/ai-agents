import { describe, test, expect } from "bun:test";
import {
  CliError,
  TargetNotEmptyError,
  TargetWriteError,
} from "../src/io/errfmt.js";

describe("CliError", () => {
  test("format produces error/cause/fix lines", () => {
    const err = new CliError({
      error: "boom",
      cause: "thing went wrong",
      fix: "do the thing",
    });
    const out = err.format();
    expect(out).toContain("error: boom");
    expect(out).toContain("cause: thing went wrong");
    expect(out).toContain("fix: do the thing");
    expect(out).not.toContain("docs:");
  });

  test("format includes docs line when provided", () => {
    const err = new CliError({
      error: "x",
      cause: "y",
      fix: "z",
      docs: "https://example.test/docs",
    });
    expect(err.format()).toContain("docs: https://example.test/docs");
  });

  test("CliError is an Error instance with name set", () => {
    const err = new CliError({ error: "x", cause: "y", fix: "z" });
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("CliError");
    expect(err.message).toBe("x");
  });
});

describe("TargetNotEmptyError", () => {
  test("references the target directory", () => {
    const err = new TargetNotEmptyError("/tmp/repo");
    const out = err.format();
    expect(out).toContain("/tmp/repo/.claude/");
    expect(out).toContain("--force");
  });
});

describe("TargetWriteError", () => {
  test("includes path and reason", () => {
    const err = new TargetWriteError("/tmp/x.md", "EACCES: permission denied");
    const out = err.format();
    expect(out).toContain("/tmp/x.md");
    expect(out).toContain("EACCES");
  });
});
