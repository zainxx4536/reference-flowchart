#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { ROOT, runPython } = require('./lib/runtime.cjs');

function main() {
  if (process.argv.slice(2).some(a => a !== '--no-browser')) throw Error('Usage: npm test, or npm run test:unit');
  runPython(['-m', 'unittest', 'discover', '-s', path.join(ROOT, 'tests'), '-p', 'test_*.py', '-v']);
  const files = fs.readdirSync(path.join(ROOT, 'tests')).filter(name => name.endsWith('.test.cjs') &&
    (!process.argv.includes('--no-browser') || name !== 'browser.test.cjs')).map(name => path.join(ROOT, 'tests', name));
  const result = spawnSync(process.execPath, ['--test', ...files], { cwd: ROOT, stdio: 'inherit', windowsHide: true });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
}
try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
