#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { ROOT, findPython } = require('./lib/runtime.cjs');

function runChecked(command, args) {
  const result = spawnSync(command, args, { cwd: ROOT, encoding: 'utf8', windowsHide: true, maxBuffer: 8 * 1024 * 1024 });
  const output = (result.stdout || '') + (result.stderr || '');
  process.stdout.write(output);
  if (result.error) throw result.error;
  if (result.status !== 0) {
    if (process.env.GITHUB_ACTIONS === 'true') {
      const message = output.slice(-6000).replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
      console.log('::error title=Regression test failure::' + message);
    }
    throw Error(`Test command failed (exit ${result.status}).`);
  }
}

function main() {
  if (process.argv.slice(2).some(a => a !== '--no-browser')) throw Error('Usage: npm test, or npm run test:unit');
  const py = findPython();
  runChecked(py.command, [...py.prefix, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', path.join(ROOT, 'tests'), '-p', 'test_*.py', '-v']);
  const files = fs.readdirSync(path.join(ROOT, 'tests')).filter(name => name.endsWith('.test.cjs') &&
    (!process.argv.includes('--no-browser') || name !== 'browser.test.cjs')).map(name => path.join(ROOT, 'tests', name));
  runChecked(process.execPath, ['--test', ...files]);
}
try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
