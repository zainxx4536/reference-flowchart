'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { ROOT, runPython, loadPlaywright, browserPath } = require('../scripts/lib/runtime.cjs');
const { exportDiagram } = require('../scripts/export_png.cjs');
const { checkEnvironment } = require('../scripts/check_env.cjs');
const testRoot=path.resolve(ROOT,'output','browser-tests');
fs.mkdirSync(testRoot,{recursive:true});
const directories=[];
function workspace() { const dir=fs.mkdtempSync(path.join(testRoot,'中文 case-'));directories.push(dir);return dir; }
after(()=>{
  if(process.env.FLOWCHART_KEEP_TEST_OUTPUT==='1')return;
  for(const dir of directories) {
    const resolved=path.resolve(dir), relative=path.relative(testRoot,resolved);
    if(!relative || relative.startsWith('..') || path.isAbsolute(relative)) throw Error('Unsafe test cleanup path');
    fs.rmSync(resolved,{recursive:true,force:true});
  }
});
function render(input,base) { runPython([path.join(ROOT,'scripts/render_flowchart.py'),input,'--output-base',base]); }

for(const [input,size] of [['assets/example-flowchart.json',[3000,2060]],['assets/branching-flowchart.json',[2800,1900]],['example/paper-flowchart.json',[4560,2940]]]) {
  test(`actual browser export: ${input}`,async()=>{
    const base=path.join(workspace(),'可编辑 图件');render(path.join(ROOT,input),base);
    const {report}=await exportDiagram({html:base+'.html',scale:2});
    assert.equal(report.status,'layout-pass');assert.deepEqual(report.issues,[]);
    assert.deepEqual([report.pngSize.width,report.pngSize.height],size);
    assert.ok(report.fonts.usedFonts.length);assert.deepEqual(report.fonts.missingGlyphs,[]);
    if(process.env.FLOWCHART_FONT_PATH)assert.ok(report.geometry.bounds.some(b=>b.metricBounds.height>b.bounds.height));
    assert.equal(report.hashes.png.length,64);
    if(input.includes('paper-'))assert.equal(report.provenance.sourcedNodes,20);
    await assert.rejects(exportDiagram({html:base+'.html',scale:2}),/already exists/);
  });
}
test('browser evidence reports actual text overflow',async()=>{
  const base=path.join(workspace(),'overflow'), input=base+'.json';
  const spec=JSON.parse(fs.readFileSync(path.join(ROOT,'assets/example-flowchart.json'),'utf8'));
  spec.nodes[0].lines=['这是一段明显超过模块宽度而必须被检查报告发现的长文字'];
  fs.writeFileSync(input,JSON.stringify(spec));render(input,base);
  const {report}=await exportDiagram({html:base+'.html',scale:1.5});
  assert.equal(report.status,'needs-fix');
  assert.ok(report.issues.some(i=>i.type==='text-outside-content-box'));
  assert.deepEqual(report.pngSize,{width:2250,height:1545});
  assert.ok(fs.existsSync(base+'.validation.json'));
});
test('mismatched layout is rejected before a misleading report is written',async()=>{
  const base=path.join(workspace(),'mismatch');render(path.join(ROOT,'assets/example-flowchart.json'),base);
  fs.appendFileSync(base+'.layout.json',' ');
  await assert.rejects(exportDiagram({html:base+'.html',scale:2}),/do not match/);
  assert.equal(fs.existsSync(base+'.validation.json'),false);
});
test('edited HTML is rejected when it no longer matches its SVG',async()=>{
  const base=path.join(workspace(),'edited');render(path.join(ROOT,'assets/example-flowchart.json'),base);
  fs.writeFileSync(base+'.html',fs.readFileSync(base+'.html','utf8').replace('业务输入','变更输入'));
  await assert.rejects(exportDiagram({html:base+'.html',scale:2}),/do not match/);
});
test('environment check confirms browser and Chinese glyphs',async()=>{
  const report=await checkEnvironment();assert.equal(report.status,'ready');
  assert.ok(report.checks.some(c=>c.name==='chinese-fonts'&&c.status==='pass'));
});
test('missing executable is reported by the environment check',async()=>{
  const report=await checkEnvironment({'browser-path':path.join(workspace(),'missing-browser.exe')});
  assert.equal(report.status,'not-ready');
  assert.ok(report.checks.some(c=>c.name==='browser-path'&&c.status==='fail'));
});
test('explicit missing Playwright does not silently fall back',()=>assert.throws(()=>loadPlaywright(path.join(workspace(),'missing-module'))));
test('explicit missing Python is reported',async()=>{
  const report=await checkEnvironment({python:path.join(workspace(),'missing-python')});
  assert.equal(report.status,'not-ready');assert.ok(report.checks.some(c=>c.name==='python'&&c.status==='fail'));
});
test('a supplied local font is actually used by Chromium', {skip:!process.env.FLOWCHART_FONT_PATH}, async()=>{
  const report=await checkEnvironment();
  const fonts=report.checks.find(c=>c.name==='chinese-fonts').value;
  assert.deepEqual(fonts.missingGlyphs,[]);
  assert.ok(fonts.usedFonts.some(font=>font.isCustomFont));
});
