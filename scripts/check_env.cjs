#!/usr/bin/env node
'use strict';
const { findPython, loadPlaywright, browserPath, applyFont, inspectFonts } = require('./lib/runtime.cjs');

async function checkEnvironment(opts = {}) {
  const checks = [];
  const record = (name, fn) => {
    try { const value = fn(); checks.push({ name, status: 'pass', value }); return value; }
    catch (error) { checks.push({ name, status: 'fail', message: error.message }); return null; }
  };
  record('node', () => { if (Number(process.versions.node.split('.')[0]) < 22) throw Error('Node.js >= 22 is required.'); return process.version; });
  record('python', () => findPython(opts.python));
  const pw = record('playwright', () => loadPlaywright(opts['playwright-module']));
  if (pw) {
    checks.find(c => c.name === 'playwright').value = { version: pw.version, path: pw.modulePath };
    const browser = record('browser-path', () => browserPath(opts['browser-path'], pw.api));
    if (browser) {
      let instance;
      try {
        instance = await pw.api.chromium.launch({ executablePath: browser, headless: true });
        checks.push({ name: 'browser-launch', status: 'pass', value: instance.version() });
        const page = await instance.newPage();
        await page.setContent('<html><body><svg id="flowchart" style=\'font-family:SimSun,"Songti SC","Noto Serif CJK SC",serif\'></svg></body></html>');
        await applyFont(page, opts['font-path']);
        const fonts = await inspectFonts(page);
        checks.push({ name: 'chinese-fonts', status: fonts.missingGlyphs.length ? 'fail' : 'pass', value: fonts });
      } catch (error) { checks.push({ name: 'browser-or-fonts', status: 'fail', message: error.message }); }
      finally { if (instance) await instance.close(); }
    }
  }
  return { status: checks.some(c => c.status === 'fail') ? 'not-ready' : 'ready', platform: process.platform, checks };
}

async function main() {
  const opts = {}, args = process.argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (!['--python', '--playwright-module', '--browser-path', '--font-path'].includes(args[i]) || !args[i + 1] || args[i + 1].startsWith('--')) throw Error('Usage: npm run check:env -- [--python PATH] [--playwright-module PATH] [--browser-path PATH] [--font-path PATH]');
    opts[args[i].slice(2)] = args[++i];
  }
  const report = await checkEnvironment(opts);
  console.log(JSON.stringify(report, null, 2));
  if (report.status !== 'ready') process.exitCode = 1;
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
module.exports = { checkEnvironment };
