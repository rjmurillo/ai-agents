"""Stylesheet for the self-contained skill-doctor HTML report.

One token set per color scheme (light on ``:root``, dark under
``prefers-color-scheme``). Every section, including the audit tables, reads
those tokens, so the page never mixes a light block into a dark page. Prose
and headings use the system sans stack; monospace is kept for code, paths,
prompts and diffs.

Python 3.10+, stdlib only.
"""

PAGE_CSS = """
:root {
  --sans-font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono-font: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --page-bg: #f5f6f8; --surface: #ffffff; --panel: #eef0f4;
  --fg: #15181e; --muted: #4b5260;
  --line: #c3c9d4; --line-soft: #e1e5ec;
  --accent: #2a4bd0; --accent-fg: #ffffff;
  --notice-bg: #fff3cf; --notice-fg: #4d3a00;
  --ok-bg: #dff3e5; --ok-fg: #0b4d27;
  --bad-bg: #fbe3e3; --bad-fg: #7f1717;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --page-bg: #101216; --surface: #171a20; --panel: #1f232b;
    --fg: #eceef3; --muted: #b0b7c4;
    --line: #3b4250; --line-soft: #272c35;
    --accent: #9db2ff; --accent-fg: #0d1330;
    --notice-bg: #3a3010; --notice-fg: #f4e3a1;
    --ok-bg: #12341f; --ok-fg: #a5e5bd;
    --bad-bg: #431a1a; --bad-fg: #f5b5b5;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--page-bg); color: var(--fg);
  font: 1rem/1.6 var(--sans-font);
}
.page { max-width: 56rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
@media (min-width: 640px) { .page { padding: 2.5rem 1.5rem 5rem; } }
::selection { background: var(--accent); color: var(--accent-fg); }
a { color: var(--accent); text-underline-offset: 0.2em; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.skip { position: absolute; left: -999px; top: 0; background: var(--surface); padding: 0.5rem 0.75rem; }
.skip:focus { left: 0.5rem; top: 0.5rem; z-index: 10; }
h1 { font-size: 1.75rem; line-height: 1.2; font-weight: 650; letter-spacing: -0.01em; margin: 0;
  text-wrap: balance; overflow-wrap: anywhere; }
h2 { font-size: 1.25rem; line-height: 1.3; font-weight: 650; margin: 2.5rem 0 0.75rem; }
h3 { font-size: 1.0625rem; line-height: 1.35; font-weight: 650; margin: 0; }
h4 { font-size: 0.9375rem; font-weight: 650; margin: 0; }
p { margin: 0.5rem 0; max-width: 70ch; }
ul, ol { margin: 0.5rem 0; padding-left: 1.25rem; max-width: 70ch; }
li { margin-bottom: 0.5rem; }
code, pre { font-family: var(--mono-font); font-size: 0.875em; }
code { background: var(--panel); border: 1px solid var(--line-soft); border-radius: 4px; padding: 0.05em 0.35em;
  overflow-wrap: anywhere; }
.muted { color: var(--muted); font-size: 0.875rem; }
.page-head { display: grid; gap: 0.5rem; }
.title-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.75rem 1rem; }
.title-row h1 { flex: 1 1 18rem; }
.meta { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; list-style: none; padding: 0; margin: 0;
  color: var(--muted); font-size: 0.875rem; }
.meta li { margin: 0; }
button { font: inherit; cursor: pointer; }
.button { font-size: 0.9375rem; font-weight: 600; color: var(--accent-fg); background: var(--accent);
  border: 1px solid var(--accent); border-radius: 6px; padding: 0.5rem 1rem; min-height: 2.5rem; flex: none; }
.button:hover { filter: brightness(1.08); }
.button[disabled] { cursor: default; opacity: 0.65; }
.button-quiet { font-size: 0.875rem; font-weight: 600; color: var(--fg); background: var(--surface);
  border: 1px solid var(--line); border-radius: 6px; padding: 0.375rem 0.75rem; min-height: 2.25rem; }
.button-quiet:hover { border-color: var(--accent); }
@media (pointer: coarse) { .button-quiet, .button { min-height: 2.75rem; } }
.summary { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; margin-top: 1.5rem; }
.summary > h2 { margin: 0; padding: 0.75rem 1.25rem; font-size: 1rem; border-bottom: 1px solid var(--line-soft); }
.scorecard { display: flex; align-items: center; gap: 2rem; padding: 1.25rem; }
.grade-col { text-align: center; flex: none; min-width: 8rem; }
.grade { font-size: 4.5rem; font-weight: 700; line-height: 1; letter-spacing: -0.03em; color: var(--accent); }
.grade-label { font-size: 0.875rem; color: var(--muted); margin-top: 0.5rem; }
.bars { flex: 1; display: grid; gap: 0.75rem; min-width: 0; list-style: none; padding: 0; margin: 0; max-width: none; }
.bars li { margin: 0; }
.bar-head { display: flex; justify-content: space-between; gap: 1rem; font-size: 0.9375rem; margin-bottom: 0.25rem; }
.bar-val { font-weight: 650; font-variant-numeric: tabular-nums; }
.bar-track { height: 0.5rem; background: var(--line-soft); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--accent);
  animation: skill-doctor-fill 700ms cubic-bezier(0.22, 1, 0.36, 1) var(--metric-delay) both;
  transform-origin: left; }
.eval-band { margin: 0 1.25rem 1rem; padding: 0.75rem 1rem; background: var(--notice-bg); color: var(--notice-fg);
  border: 1px solid var(--line); border-radius: 6px; }
.eval-band h3 { font-size: 0.875rem; }
.eval-band p { margin: 0.25rem 0 0; max-width: 70ch; font-weight: 500; }
.stats { display: flex; flex-wrap: wrap; list-style: none; margin: 0; padding: 0; max-width: none;
  background: var(--panel); border-top: 1px solid var(--line-soft); border-radius: 0 0 8px 8px; }
.stat { flex: 1 1 7rem; margin: 0; padding: 0.75rem 1.25rem; display: flex; flex-direction: column; }
.stat .num { font-size: 1.5rem; font-weight: 650; font-variant-numeric: tabular-nums; }
.stat .lbl { color: var(--muted); font-size: 0.875rem; }
@media (max-width: 599px) {
  .scorecard { flex-direction: column; align-items: stretch; gap: 1.25rem; }
  .grade { font-size: 3.5rem; }
  h1 { font-size: 1.5rem; }
}
.findings li { max-width: 70ch; }
.empty { color: var(--muted); border: 1px dashed var(--line); border-radius: 6px; padding: 0.75rem 1rem; }
.candidate { background: var(--surface); border: 1px solid var(--line); border-radius: 8px;
  padding: 1rem 1.25rem; margin: 1rem 0; }
.candidate-head { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.75rem; }
.change { font-size: 1.0625rem; margin: 0.5rem 0 0.75rem; }
.badge { display: inline-block; font-size: 0.8125rem; font-weight: 650; padding: 0.1rem 0.6rem;
  border-radius: 999px; border: 1px solid var(--line); background: var(--panel); color: var(--fg); }
.badge[data-status="accepted"] { background: var(--ok-bg); color: var(--ok-fg); }
.badge[data-status="rejected"] { background: var(--bad-bg); color: var(--bad-fg); }
.badge[data-status="inconclusive"] { background: var(--notice-bg); color: var(--notice-fg); }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 0.75rem; margin: 0.75rem 0; }
.field { margin: 0; max-width: 70ch; }
.field + .field { margin-top: 0.625rem; }
.field-label { font-size: 0.8125rem; font-weight: 650; color: var(--muted); margin: 0; }
.field-value { margin: 0.125rem 0 0; }
.kind { display: inline-block; margin-right: 0.25rem; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--muted); }
.group { border-top: 1px solid var(--line-soft); padding-top: 0.75rem; margin-top: 0.75rem; }
.group-title { font-size: 0.9375rem; font-weight: 650; margin: 0 0 0.25rem; }
.missing { background: var(--notice-bg); color: var(--notice-fg); border-radius: 6px; padding: 0.5rem 0.75rem; }
.missing .field + .field { margin-top: 0.625rem; }
.field-label { color: inherit; }
.handoff { border-top: 1px solid var(--line-soft); margin-top: 0.75rem; padding-top: 0.75rem; }
.handoff-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem; }
.handoff-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
.copy-status { font-size: 0.875rem; color: var(--muted); min-height: 1.25rem; }
.prompt { white-space: pre-wrap; user-select: all; font-size: 0.8125rem; line-height: 1.6; background: var(--panel);
  border: 1px solid var(--line); border-radius: 6px; padding: 0.75rem 1rem; max-height: 20rem; overflow: auto; margin: 0.5rem 0 0; }
.notice { background: var(--notice-bg); color: var(--notice-fg); border: 1px solid var(--line);
  border-radius: 6px; padding: 0.5rem 0.75rem; }
details.section { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; margin: 0.75rem 0; }
details.section > summary { padding: 0.75rem 1rem; font-weight: 650; }
details.section > .section-body { padding: 0 1rem 1rem; }
details.section details.section { background: var(--page-bg); }
summary { cursor: pointer; }
summary:hover { color: var(--accent); }
.handoff summary { font-weight: 600; font-size: 0.875rem; color: var(--muted); }
.table-scroll { overflow-x: auto; max-width: 100%; margin: 0.5rem 0; border: 1px solid var(--line-soft); border-radius: 6px; }
table { border-collapse: collapse; width: 100%; font-size: 0.875rem; font-variant-numeric: tabular-nums; }
caption { text-align: left; padding: 0.5rem 0.75rem; color: var(--muted); font-size: 0.8125rem; }
th, td { border-top: 1px solid var(--line-soft); padding: 0.375rem 0.75rem; text-align: left; vertical-align: top; }
th { background: var(--panel); font-weight: 650; white-space: nowrap; }
td code { font-size: 0.8125rem; }
.diff-wrap { margin: 0.75rem 0 0.25rem; }
.diff-view { display: grid; gap: 10px; max-width: 100%;
  --diffs-font-family: var(--mono-font); --diffs-header-font-family: var(--mono-font); }
.diff-view > * { min-width: 0; }
.diff-fallback { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 0.75rem 1rem;
  color: var(--fg); font-size: 0.8125rem; line-height: 1.7; overflow-x: auto; margin: 0; white-space: pre; }
.diff-wrap[data-overflowing="true"][data-collapsed="true"] .diff-view {
  max-height: __CLAMP__px; overflow: hidden;
  -webkit-mask-image: linear-gradient(#000 calc(100% - 72px), transparent);
  mask-image: linear-gradient(#000 calc(100% - 72px), transparent);
}
.diff-toggle { margin-top: 0.5rem; }
@keyframes skill-doctor-fill {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}
@media (prefers-reduced-motion: reduce) {
  .bar-fill { animation: none; }
}
@media print {
  body { background: #fff; color: #000; }
  .button, .button-quiet, .skip, .handoff-actions { display: none !important; }
  details > summary { list-style: none; }
  details::details-content { content-visibility: visible; display: block; }
  .candidate, details.section, .summary { break-inside: avoid; }
  .diff-wrap[data-overflowing="true"][data-collapsed="true"] .diff-view { max-height: none; -webkit-mask-image: none; mask-image: none; }
  .prompt { max-height: none; }
}
"""
