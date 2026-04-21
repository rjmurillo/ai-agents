#!/usr/bin/env node

import { parseArgs } from "node:util";

const { values, positionals } = parseArgs({
  args: process.argv.slice(2),
  options: {
    force: { type: "boolean", default: false },
    help: { type: "boolean", short: "h", default: false },
  },
  allowPositionals: true,
  strict: true,
});

if (values.help || positionals.length === 0) {
  process.stdout.write(
    [
      "Usage: ai-agents <command> [path] [options]",
      "",
      "Commands:",
      "  init [path]   Vendor the ai-agents Claude kit into a repo",
      "",
      "Options:",
      "  --force       Overwrite existing files that diverge from snapshot",
      "  -h, --help    Show this help message",
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
  `ai-agents init: target=${targetDir} force=${values.force ?? false}\n`,
);
process.stdout.write("Concrete BundleSource and TargetEmitter ship in M3.\n");
