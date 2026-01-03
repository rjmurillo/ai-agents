#!/usr/bin/env tsx
/**
 * Wrapper script for claude-mem import-memories
 * Forwards all arguments to the installed plugin script
 */

import { spawn } from 'child_process';
import { join } from 'path';
import { homedir } from 'os';

const pluginScriptPath = join(
  homedir(),
  '.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts'
);

const args = process.argv.slice(2);

const child = spawn('npx', ['tsx', pluginScriptPath, ...args], {
  stdio: 'inherit',
  shell: true
});

child.on('exit', (code) => {
  process.exit(code ?? 1);
});
