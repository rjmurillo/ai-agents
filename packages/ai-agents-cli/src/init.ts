import { access, readdir } from "node:fs/promises";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import type { BundleSource, TargetContext, TargetEmitter, InitResult } from "./types.js";
import { FsBundleSource } from "./io/bundle-source-fs.js";
import { FsTargetEmitter } from "./target/emitter-fs.js";
import { mergeClaudeMd } from "./target/merge-claude-md.js";
import { writeAgentsMd } from "./target/write-agents-md.js";
import { writeVersionPin } from "./target/version-pin.js";
import { TargetNotEmptyError } from "./io/errfmt.js";

function resolveAssetsDir(): string {
  const currentFile = fileURLToPath(import.meta.url);
  return join(dirname(currentFile), "..", "bundle", "assets");
}

async function dirExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function targetHasClaudeDir(targetDir: string): Promise<boolean> {
  return dirExists(join(targetDir, ".claude"));
}

export async function init(opts: {
  targetDir: string;
  force: boolean;
  dryRun: boolean;
  version: string;
}): Promise<InitResult> {
  const targetDir = resolve(opts.targetDir);

  if (!opts.force && !opts.dryRun && await targetHasClaudeDir(targetDir)) {
    throw new TargetNotEmptyError(targetDir);
  }

  const assetsDir = resolveAssetsDir();
  const source: BundleSource = new FsBundleSource(assetsDir);
  const emitter: TargetEmitter = new FsTargetEmitter();

  const target: TargetContext = {
    targetDir,
    force: opts.force,
    dryRun: opts.dryRun,
  };

  const filesWritten: string[] = [];
  let commands = 0;
  let agents = 0;
  let skills = 0;

  for await (const entry of source.list()) {
    const content = await source.read(entry);
    await emitter.emit(entry, content, target);
    filesWritten.push(entry.relativePath);

    if (entry.relativePath.startsWith("commands/")) commands++;
    if (entry.relativePath.startsWith("agents/")) agents++;
    if (entry.relativePath.startsWith("skills/")) skills++;
  }

  await mergeClaudeMd(targetDir, opts.dryRun);
  await writeAgentsMd(targetDir, opts.dryRun);
  await writeVersionPin(targetDir, opts.version, filesWritten, opts.dryRun);

  return { commands, agents, skills, filesWritten };
}
