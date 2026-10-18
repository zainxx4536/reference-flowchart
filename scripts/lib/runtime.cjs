'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { createRequire } = require('node:module');
const ROOT = path.resolve(__dirname, '..', '..');

function findPython(explicit) {
  const candidates = explicit || process.env.FLOWCHART_PYTHON
    ? [[explicit || process.env.FLOWCHART_PYTHON, []]] : [['python3', []], ['python', []], ['py', ['-3']]];
  for (const [command, prefix] of candidates) {
    const result = spawnSync(command, [...prefix, '-c', 'import sys; print("%d.%d.%d" % sys.version_info[:3])'], { encoding: 'utf8', timeout: 5000, windowsHide: true });
    const version = (result.stdout || '').trim();
    if (result.status === 0 && /^3\.(\d+)\./.test(version) && Number(version.split('.')[1]) >= 10) return { command, prefix, version };
  }
  throw Error('Python >= 3.10 not found. Pass --python PATH or set FLOWCHART_PYTHON.');
}

function runPython(args, explicit) {
  const py = findPython(explicit);
  const result = spawnSync(py.command, [...py.prefix, '-X', 'utf8', ...args], { stdio: 'inherit', windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0) throw Error(`Python command failed (exit ${result.status}).`);
}

function loadPlaywright(explicit) {
  const selected = explicit || process.env.FLOWCHART_PLAYWRIGHT_MODULE;
  const candidates = selected ? [path.resolve(selected)] : ['playwright', path.join(os.homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'node', 'node_modules', 'playwright')];
  for (const candidate of candidates) {
    let resolved;
    try { resolved = require.resolve(candidate); }
    catch (error) {
      if (error.code === 'MODULE_NOT_FOUND' && !selected) continue;
      throw error;
    }
    const localRequire = createRequire(resolved);
    const packageFile = localRequire.resolve('./package.json');
    return { api: require(resolved), version: JSON.parse(fs.readFileSync(packageFile, 'utf8')).version, modulePath: path.dirname(packageFile) };
  }
  throw Error('Node Playwright not found. Run npm ci, or pass --playwright-module PATH.');
}

function browserPath(explicit, pw) {
  const selected = explicit || process.env.FLOWCHART_BROWSER_PATH;
  const candidates = selected ? [path.resolve(selected)] : [pw.chromium.executablePath(),
    ...['ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'].flatMap(k => process.env[k] ? [
      path.join(process.env[k], 'Google', 'Chrome', 'Application', 'chrome.exe'),
      path.join(process.env[k], 'Microsoft', 'Edge', 'Application', 'msedge.exe')] : []),
    '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'];
  const found = candidates.find(p => p && fs.existsSync(p) && fs.statSync(p).isFile());
  if (!found) throw Error('Chromium browser not found. Pass --browser-path PATH, or run npx playwright install chromium.');
  return found;
}

async function applyFont(page, explicit) {
  const fontPath = explicit || process.env.FLOWCHART_FONT_PATH;
  if (!fontPath) return;
  const data = fs.readFileSync(path.resolve(fontPath));
  if (data.length > 32 * 1024 * 1024) throw Error('Local font file exceeds 32 MiB.');
  await page.addStyleTag({ content: `@font-face{font-family:FlowchartLocal;src:url(data:application/octet-stream;base64,${data.toString('base64')})}#flowchart{font-family:FlowchartLocal,serif!important}` });
  await page.evaluate(() => document.fonts.ready);
}

async function inspectFonts(page) {
  const result = await page.evaluate(async () => {
    const family = getComputedStyle(document.getElementById('flowchart') || document.body).fontFamily;
    const probe = document.createElement('span');
    probe.id = 'flowchart-font-probe'; probe.textContent = '中文流程图';
    Object.assign(probe.style, { fontFamily: family, fontSize: '64px', position: 'fixed', top: '-1000px' });
    document.body.appendChild(probe); await document.fonts.ready;
    const canvas = document.createElement('canvas'); canvas.width = 160; canvas.height = 120;
    const ctx = canvas.getContext('2d'); ctx.font = `64px ${family}`;
    const draw = c => { ctx.clearRect(0, 0, 160, 120); ctx.fillText(c, 8, 80); return canvas.toDataURL(); };
    const missing = [draw('\uFFFF'), draw('\u{10FFFF}')];
    return { family, sample: probe.textContent, missingGlyphs: [...probe.textContent].filter(c => missing.includes(draw(c))) };
  });
  const session = await page.context().newCDPSession(page);
  try {
    await session.send('DOM.enable'); await session.send('CSS.enable');
    const { root } = await session.send('DOM.getDocument');
    const { nodeId } = await session.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#flowchart-font-probe' });
    result.usedFonts = (await session.send('CSS.getPlatformFontsForNode', { nodeId })).fonts;
  } finally {
    await session.detach();
    await page.evaluate(() => document.getElementById('flowchart-font-probe')?.remove());
  }
  if (!result.usedFonts.length) result.missingGlyphs = [...result.sample];
  return result;
}

module.exports = { ROOT, findPython, runPython, loadPlaywright, browserPath, applyFont, inspectFonts };
