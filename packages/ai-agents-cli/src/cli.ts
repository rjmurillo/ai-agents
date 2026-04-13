#!/usr/bin/env node

import { resolve } from "node:path";
import { init } from "./init.js";
import { CliError } from "./io/errfmt.js";

const VERSION = "0.1.0";

const HELP = `Usage: ai-agents init [path] [options]

Vendor a curated Claude Code kit into a target repository.

Arguments:
  path          Target directory (default: current directory)

Options:
  --force       Overwrite existing .claude/ directory
  --dry-run     List files that would be created without writing
  --yes, -y     Skip confirmation prompt
  --version     Show version number
  --help, -h    Show this help message
`;

function parseArgs(argv: string[]): {
  command: string;
  targetDir: string;
  force: boolean;
  dryRun: boolean;
  yes: boolean;
  help: boolean;
  version: boolean;
} {
  const args = argv.slice(2);
  let command = "";
  let targetDir = ".";
  let force = false;
  let dryRun = false;
  let yes = false;
  let help = false;
  let version = false;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--force") { force = true; continue; }
    if (arg === "--dry-run") { dryRun = true; continue; }
    if (arg === "--yes" || arg === "-y") { yes = true; continue; }
    if (arg === "--help" || arg === "-h") { help = true; continue; }
    if (arg === "--version") { version = true; continue; }
    if (!command) { command = arg; continue; }
    targetDir = arg;
  }

  return { command, targetDir, force, dryRun, yes, help, version };
}

function isTty(): boolean {
  return Boolean(process.stdin.isTTY);
}

async function confirm(message: string): Promise<boolean> {
  if (!isTty()) return true;

  process.stdout.write(`${message} [Y/n] `);
  return new Promise((resolve) => {
    process.stdin.setEncoding("utf-8");
    process.stdin.once("data", (data: string) => {
      const answer = data.trim().toLowerCase();
      resolve(answer === "" || answer === "y" || answer === "yes");
    });
  });
}

async function main(): Promise<void> {
  const opts = parseArgs(process.argv);

  if (opts.version) {
    console.log(VERSION);
    return;
  }

  if (opts.help || !opts.command) {
    console.log(HELP);
    return;
  }

  if (opts.command !== "init") {
    console.error(`error: Unknown command "${opts.command}"`);
    console.error(`fix: Run "ai-agents --help" for available commands`);
    process.exit(1);
  }

  const targetDir = resolve(opts.targetDir);

  if (!opts.yes && !opts.dryRun && isTty()) {
    const ok = await confirm(`Vendor Claude Code kit into ${targetDir}?`);
    if (!ok) {
      console.log("Aborted.");
      return;
    }
  }

  if (opts.dryRun) {
    console.log("Dry run: listing files that would be created\n");
  }

  const result = await init({
    targetDir,
    force: opts.force,
    dryRun: opts.dryRun,
    version: VERSION,
  });

  if (opts.dryRun) {
    for (const file of result.filesWritten) {
      console.log(`  .claude/${file}`);
    }
    console.log(`  CLAUDE.md (merge block)`);
    console.log(`  AGENTS.md (stub)`);
    console.log(`  .claude/.ai-agents-version.json`);
    return;
  }

  console.log(
    `Vendored ${result.commands} commands, ${result.agents} agents, ${result.skills} skills into ${targetDir}`,
  );
  console.log(`\nOpen this folder in Claude Code and run /spec to start.`);
}

main().catch((err) => {
  if (err instanceof CliError) {
    console.error(err.format());
    process.exit(2);
  }
  console.error(err);
  process.exit(1);
});
