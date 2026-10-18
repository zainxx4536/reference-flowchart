#!/usr/bin/env node
'use strict';
const path = require('node:path');
const { ROOT, runPython } = require('./lib/runtime.cjs');
const { exportDiagram } = require('./export_png.cjs');

async function main() {
  const [mode, ...args] = process.argv.slice(2), opts = {};
  for (let i = 0; i < args.length; i++) {
    if (!['--python', '--playwright-module', '--browser-path', '--font-path'].includes(args[i]) || !args[i + 1] || args[i + 1].startsWith('--')) throw Error('Unknown or incomplete option: ' + args[i]);
    opts[args[i].slice(2)] = args[++i];
  }
  const cases = mode === 'paper' ? [['example/paper-flowchart.json', 'paper-flowchart']]
    : mode === 'demo' ? [['assets/example-flowchart.json', 'example-flowchart'], ['assets/branching-flowchart.json', 'branching-flowchart']] : null;
  if (!cases) throw Error('Usage: node scripts/flowchart.cjs demo|paper [--python PATH] [--browser-path PATH] [--font-path PATH] [--playwright-module PATH]');
  for (const [input, name] of cases) {
    const base = path.join(ROOT, 'output', name);
    runPython([path.join(ROOT, 'scripts/render_flowchart.py'), path.join(ROOT, input), '--output-base', base, '--overwrite'], opts.python);
    const { report } = await exportDiagram({ ...opts, html: base + '.html', scale: 2, overwrite: true });
    console.log(JSON.stringify({ example: name, status: report.status, pngSize: report.pngSize, issues: report.issues }));
    if (report.issues.length) process.exitCode = 1;
  }
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
