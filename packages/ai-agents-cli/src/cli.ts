#!/usr/bin/env node

import { Command } from "commander";
import type {
  BundleEntry,
  BundleSource,
  TargetContext,
  TargetEmitter,
  Transform,
} from "./types.js";

const program = new Command();

program
  .name("ai-agents")
  .description("Vendor a curated .claude/ kit into any repository")
  .version("0.1.0");

program
  .command("init")
  .description("Initialize .claude/ kit in the current directory")
  .option("-f, --force", "Overwrite existing files", false)
  .option("-n, --dry-run", "Show what would be done without making changes", false)
  .action((options: { force: boolean; dryRun: boolean }) => {
    console.log("init stub");
    console.log(`Options: force=${options.force}, dryRun=${options.dryRun}`);
  });

program.parse();

export type { BundleEntry, BundleSource, TargetContext, TargetEmitter, Transform };
