import type { BundleEntry, TargetContext, Transform } from "../types.js";

const CLAUDE_SLASH_CMD = /\/([a-z][\w-]*)/g;

const CLAUDE_DIRECTIVES: RegExp[] = [
  /^@[\w/.]+\.md\s*$/gm,
  /\bSkill\s*\(\s*["'][^"']+["']\s*\)/g,
  /\bTask\s*\(\s*subagent_type\s*=\s*["'][^"']+["'][^)]*\)/g,
];

function translateContent(text: string): string {
  let result = text;

  result = result.replace(CLAUDE_SLASH_CMD, (match, name) => {
    return `\`/${name}\` (prompt: \`.github/prompts/${name}.md\`)`;
  });

  for (const directive of CLAUDE_DIRECTIVES) {
    directive.lastIndex = 0;
    result = result.replace(directive, (match) => `<!-- ${match.trim()} -->`);
  }

  return result;
}

export const commandSyntaxTranslator: Transform = (
  entry: BundleEntry,
  content: Buffer,
  target: TargetContext,
) => {
  if (target.target !== "copilot" && target.target !== "both") {
    return { entry, content };
  }

  if (entry.category !== "command" && entry.category !== "config") {
    return { entry, content };
  }

  const text = content.toString("utf-8");
  const translated = translateContent(text);
  return { entry, content: Buffer.from(translated, "utf-8") };
};
