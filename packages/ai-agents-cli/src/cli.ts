#!/usr/bin/env node

import { parseArgs } from "node:util";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { FsBundleSource } from "./io/bundle-source-fs.js";
import { FsTargetEmitter } from "./target/emitter-fs.js";
import { init } from "./init.js";
import { mergeClaudeMd } from "./target/merge-claude-md.js";
import { writeAgentsMd } from "./target/write-agents-md.js";
import { writeVersionPin } from "./target/version-pin.js";
import type { BundleEntry, TargetContext } from "./types.js";

const VERSION = "0.1.0";

export interface RunInitOptions {
  targetDir: string;
  force: boolean;
  dryRun: boolean;
  assetsDir: string;
  version: string;
}

// Exported for tests: wires the vendoring pipeline end-to-end.
export async function runInit(opts: RunInitOptions): Promise<number> {
  const target: TargetContext = {
    targetDir: resolve(opts.targetDir),
    force: opts.force,
    dryRun: opts.dryRun,
  };
  const source = new FsBundleSource(opts.assetsDir);
  const emitter = new FsTargetEmitter();

  // Capture the manifest as files stream through so the version pin reflects
  // exactly what was vendored on this run.
  const manifestEntries: string[] = [];
  const capture = (entry: BundleEntry): BundleEntry => {
    manifestEntries.push(entry.relativePath);
    return entry;
  };

  const code = await init(source, emitter, target, [capture]);
  if (code !== 0) return code;

  if (!opts.dryRun) {
    await mergeClaudeMd(target.targetDir, opts.dryRun);
    await writeAgentsMd(target.targetDir, opts.dryRun);
    await writeVersionPin(
      target.targetDir,
      opts.version,
      manifestEntries,
      opts.dryRun,
    );
  }

  return 0;
}

function resolveAssetsDir(): string {
  // bundle/assets is shipped alongside dist/ in the published package.
  // When running from src/ in dev, the same relative path resolves correctly.
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, "..", "bundle", "assets");
}

async function main(): Promise<number> {
  const { values, positionals } = parseArgs({
    args: process.argv.slice(2),
    options: {
      force: { type: "boolean", default: false },
      "dry-run": { type: "boolean", default: false },
      yes: { type: "boolean", short: "y", default: false },
      help: { type: "boolean", short: "h", default: false },
      version: { type: "boolean", default: false },
    },
    allowPositionals: true,
    strict: true,
  });

  if (values.version) {
    process.stdout.write(`${VERSION}\n`);
    return 0;
  }

  if (values.help || positionals.length === 0) {
    process.stdout.write(
      [
        "Usage: ai-agents init [path] [options]",
        "",
        "Commands:",
        "  init [path]   Vendor the ai-agents Claude kit into a repo",
        "",
        "Options:",
        "  --force       Overwrite existing files that diverge from snapshot",
        "  --dry-run     Show what would be written without touching disk",
        "  -y, --yes     Skip confirmation prompts",
        "  -h, --help    Show this help message",
        "  --version     Print the CLI version and exit",
        "",
      ].join("\n"),
    );
    return values.help ? 0 : 1;
  }

  const command = positionals[0];

  if (command !== "init") {
    process.stderr.write(`Unknown command: ${command}\n`);
    return 1;
  }

  const targetDir = positionals[1] ?? ".";
  const force = values.force ?? false;
  const dryRun = values["dry-run"] ?? false;

  process.stdout.write(
    `ai-agents init: target=${targetDir} force=${force} dryRun=${dryRun}\n`,
  );

  return runInit({
    targetDir,
    force,
    dryRun,
    assetsDir: resolveAssetsDir(),
    version: VERSION,
  });
}

// Only execute when run as a script, not when imported for testing.
// `import.meta.main` is Bun-specific. For Node.js compatibility, also compare the
// resolved module URL to process.argv[1] (Node sets the latter to the entry script).
function isEntryModule(): boolean {
  const meta = import.meta as { main?: boolean };
  if (meta.main === true) return true;
  const entry = process.argv[1];
  if (entry === undefined) return false;
  return fileURLToPath(import.meta.url) === resolve(entry);
}

if (isEntryModule()) {
  main().then(
    (code) => process.exit(code),
    (err) => {
      const message = err instanceof Error ? err.message : String(err);
      process.stderr.write(`ai-agents: ${message}\n`);
      process.exit(1);
    },
  );
}
