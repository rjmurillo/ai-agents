#!/usr/bin/env node

import { realpathSync } from "node:fs";
import { parseArgs } from "node:util";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { FsBundleSource } from "./io/bundle-source-fs.js";
import { FsTargetEmitter } from "./target/emitter-fs.js";
import { init } from "./init.js";
import { mergeClaudeMd } from "./target/merge-claude-md.js";
import { mergeCopilotInstructions } from "./target/merge-copilot-instructions.js";
import { writeAgentsMd } from "./target/write-agents-md.js";
import { writeVersionPin } from "./target/version-pin.js";
import { makePackFilter, knownPacks, parsePacks } from "./packs.js";
import { TARGETS, type BundleEntry, type Target, type TargetContext } from "./types.js";

const VERSION = "0.1.0";
const DEFAULT_TARGET: Target = "claude";

export interface RunInitOptions {
  targetDir: string;
  force: boolean;
  dryRun: boolean;
  assetsDir: string;
  version: string;
  target?: Target;
  packs?: string[];
}

// Append the inline harness block to the instruction file(s) the target selects.
async function writeTargetBlocks(
  targetDir: string,
  target: Target,
  dryRun: boolean,
): Promise<void> {
  if (target === "claude" || target === "both") {
    await mergeClaudeMd(targetDir, dryRun);
  }
  if (target === "copilot" || target === "both") {
    await mergeCopilotInstructions(targetDir, dryRun);
  }
}

// Reject any --target value outside the known set with a clear error message.
export function parseTarget(value: string): Target {
  if ((TARGETS as readonly string[]).includes(value)) {
    return value as Target;
  }
  throw new Error(
    `Invalid --target "${value}". Expected one of: ${TARGETS.join(", ")}.`,
  );
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

  // Optional skill packs are excluded by default; --pack opts them in. The
  // filter runs before capture so a non-requested pack's files are neither
  // vendored nor recorded in the version pin (issue #2509).
  const packFilter = makePackFilter(new Set(opts.packs ?? []));

  const code = await init(source, emitter, target, [packFilter, capture]);
  if (code !== 0) return code;

  if (!opts.dryRun) {
    await writeTargetBlocks(
      target.targetDir,
      opts.target ?? DEFAULT_TARGET,
      opts.dryRun,
    );
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
      target: { type: "string", default: DEFAULT_TARGET },
      yes: { type: "boolean", short: "y", default: false },
      help: { type: "boolean", short: "h", default: false },
      version: { type: "boolean", default: false },
      pack: { type: "string", multiple: true },
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
        "  --target T    Instruction file(s) to update: claude, copilot, or both",
        "                (default: claude)",
        `  --pack NAME   Also install an optional skill pack (${knownPacks().join(", ")})`,
        "                repeatable or comma-separated",
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

  let target: Target;
  try {
    target = parseTarget(values.target ?? DEFAULT_TARGET);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    process.stderr.write(`${message}\n`);
    return 2;
  }

  let packs: string[];
  try {
    packs = [...parsePacks(values.pack as string[] | undefined)];
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    process.stderr.write(`${message}\n`);
    return 2;
  }

  process.stdout.write(
    `ai-agents init: dir=${targetDir} target=${target} force=${force} dryRun=${dryRun}\n`,
  );

  return runInit({
    targetDir,
    force,
    dryRun,
    assetsDir: resolveAssetsDir(),
    version: VERSION,
    target,
    packs,
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

  const modulePath = fileURLToPath(import.meta.url);
  const entryPath = resolve(entry);
  if (modulePath === entryPath) return true;

  try {
    return modulePath === realpathSync(entryPath);
  } catch {
    return false;
  }
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
