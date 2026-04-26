#!/usr/bin/env node

import { parseArgs } from "node:util";

const VERSION = "0.1.0";

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
  process.exit(0);
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
  process.exit(values.help ? 0 : 1);
}

const command = positionals[0];

if (command !== "init") {
  process.stderr.write(`Unknown command: ${command}\n`);
  process.exit(1);
}

const targetDir = positionals[1] ?? ".";

process.stdout.write(
  `ai-agents init: target=${targetDir} force=${values.force ?? false} dryRun=${values["dry-run"] ?? false}\n`,
);
process.stdout.write(
  "Wire FsBundleSource and FsTargetEmitter to init() in M3 follow-up.\n",
);
