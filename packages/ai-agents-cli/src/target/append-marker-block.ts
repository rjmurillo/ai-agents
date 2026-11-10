import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

export const BEGIN_MARKER = "<!-- ai-agents:begin -->";
export const END_MARKER = "<!-- ai-agents:end -->";

export class MarkerBlockError extends Error {
  constructor(
    readonly filePath: string,
    present: string,
    missing: string,
  ) {
    super(
      `${filePath} has ${present} but no ${missing}. Restore the missing ` +
        "marker or delete the ai-agents block, then run init again.",
    );
    this.name = "MarkerBlockError";
  }
}

// Append a marker-delimited block to a markdown instruction file, preserving
// existing content and CRLF line endings. Idempotent: a file that already
// contains both markers is left untouched. A file with only one marker throws
// MarkerBlockError, in dry-run too, so a preview reports the same failure a
// real run hits. The dry-run guard writes nothing.
//
// Shared by the CLAUDE.md (claude target) and copilot-instructions.md
// (copilot target) writers so the CRLF and idempotency rules live in one place.
export async function appendMarkerBlock(
  filePath: string,
  block: string,
  dryRun: boolean,
): Promise<void> {
  if (!block.includes(BEGIN_MARKER) || !block.includes(END_MARKER)) {
    throw new Error(
      "appendMarkerBlock requires the block to contain both " +
        `${BEGIN_MARKER} and ${END_MARKER}; the idempotency check relies on ` +
        "them.",
    );
  }

  let existing = "";
  let detectedCrlf = false;
  try {
    const raw = await readFile(filePath);
    existing = raw.toString("utf-8");
    detectedCrlf = existing.includes("\r\n");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") {
      throw err;
    }
    // File does not exist yet, proceed with empty existing content
  }

  const hasBegin = existing.includes(BEGIN_MARKER);
  const hasEnd = existing.includes(END_MARKER);
  if (hasBegin && hasEnd) {
    return;
  }
  if (hasBegin !== hasEnd) {
    // Appending here would duplicate the surviving marker. Leave the file for
    // the user to repair.
    throw new MarkerBlockError(
      filePath,
      hasBegin ? BEGIN_MARKER : END_MARKER,
      hasBegin ? END_MARKER : BEGIN_MARKER,
    );
  }

  if (dryRun) return;
  await mkdir(dirname(filePath), { recursive: true });

  let blockToWrite = block;
  if (detectedCrlf) {
    // Match optional CR so a block already using CRLF does not become
    // corrupted \r\r\n line endings.
    blockToWrite = blockToWrite.replace(/\r?\n/g, "\r\n");
  }

  let result: string;
  if (existing.length === 0) {
    result = blockToWrite + "\n";
  } else {
    const lineEnding = detectedCrlf ? "\r\n" : "\n";
    const trimmed = existing.endsWith(lineEnding)
      ? existing
      : existing + lineEnding;
    result = trimmed + lineEnding + blockToWrite + lineEnding;
  }

  if (detectedCrlf) {
    // Equivalent to /(?<!\r)\n/g but avoids negative lookbehind for
    // broader engine compatibility: match optional CR + LF and
    // unconditionally rewrite to CRLF (\r\n is an identity, \n is fixed).
    result = result.replace(/\r?\n/g, "\r\n");
  }

  await writeFile(filePath, result, "utf-8");
}
