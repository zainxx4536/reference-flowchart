'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { boundary, segmentHit, staticCheck, checkText } = require('../scripts/lib/geometry.cjs');
const { options, provenance } = require('../scripts/export_png.cjs');

function linesSpec(lines, extra = {}) {
  const zones = [], edges = lines.map((points, index) => {
    for (const [side, p] of [['start', points[0]], ['end', points.at(-1)]]) zones.push({ id: `e${index}-${side}`, x: p[0], y: p[1], width: 1, height: 1 });
    return { id: `e${index}`, from: `e${index}-start`, to: `e${index}-end`, points };
  });
  return { canvas: { width: 1000, height: 1000 }, nodes: [], edges, zones, junctions: [], ...extra };
}
const types = spec => staticCheck(spec).map(issue => issue.type);

test('strict crossings are detected', () => assert.ok(types(linesSpec([[[10,100],[200,100]],[[100,10],[100,200]]])).includes('unmarked-crossing')));
test('T contacts at segment endpoints are detected', () => assert.ok(types(linesSpec([[[10,100],[200,100]],[[100,10],[100,100]]])).includes('ambiguous-contact')));
test('near contacts within 2 units are detected', () => assert.ok(types(linesSpec([[[10,100],[200,100]],[[100,10],[100,99]]])).includes('ambiguous-contact')));
test('positive collinear overlap is detected', () => assert.ok(types(linesSpec([[[10,100],[200,100]],[[100,100],[250,100]]])).includes('collinear-overlap')));
test('an explicit junction removes an ambiguous crossing', () => {
  const spec=linesSpec([[[10,100],[200,100]],[[100,10],[100,200]]]);
  spec.junctions.push({id:'join',x:100,y:100}); assert.deepEqual(staticCheck(spec),[]);
});
test('separate connectors sharing the same declared endpoint are valid', () => {
  const spec=linesSpec([[[10,100],[200,100]],[[200,10],[200,100]]]);
  spec.edges[1].to=spec.edges[0].to; assert.deepEqual(staticCheck(spec),[]);
});
test('parallel disjoint lines have no false crossing', () => assert.deepEqual(staticCheck(linesSpec([[[10,100],[200,100]],[[10,110],[200,110]]])),[]));
test('connectors passing through a node are reported', () => {
  const spec=linesSpec([[[10,100],[200,100]]],{nodes:[{id:'obstacle',x:60,y:70,width:50,height:60}]});
  assert.ok(types(spec).includes('connector-through-node'));
});
test('overlapping nodes are reported', () => {
  const spec=linesSpec([],{nodes:[{id:'a',x:60,y:70,width:50,height:60},{id:'b',x:80,y:80,width:50,height:60}]});
  assert.ok(types(spec).includes('overlapping-nodes'));
});
for (const shape of ['diamond','terminator','cylinder']) {
  test(`${shape} ports follow the actual outline rather than its bounding rectangle`, () => {
    const node={shape,x:100,y:100,width:200,height:100};
    assert.equal(boundary([200,100],node),true);
    assert.equal(boundary([100,150],node),true);
    assert.equal(boundary([100,100],node),false);
  });
}
test('a connector in a diamond bounding corner does not hit the diamond', () => assert.equal(segmentHit([100,102],[120,102],{shape:'diamond',x:100,y:100,width:200,height:100}),false));
test('text crossing a connector is reported', () => {
  const spec=linesSpec([[[10,100],[200,100]]]);
  assert.ok(checkText(spec,[{node:null,text:'标签',bounds:{x:60,y:90,width:60,height:20}}]).some(i=>i.type==='connector-through-text'));
});
test('overlapping labels are reported', () => {
  const records=[{node:null,text:'甲',bounds:{x:60,y:90,width:60,height:20}},{node:null,text:'乙',bounds:{x:90,y:90,width:60,height:20}}];
  assert.ok(checkText(linesSpec([]),records).some(i=>i.type==='overlapping-text'));
});
test('text in the bounding corner of a diamond is rejected', () => {
  const spec=linesSpec([],{nodes:[{id:'a',shape:'diamond',x:100,y:100,width:200,height:100}]});
  assert.ok(checkText(spec,[{node:'a',text:'越框',bounds:{x:110,y:110,width:50,height:20}}]).some(i=>i.type==='text-outside-content-box'));
});
test('source records distinguish code, paper and design', () => {
  const result=provenance({nodes:[{id:'a',sources:[{kind:'code',document:'app.py',symbol:'main'}]},{id:'b'}],edges:[]});
  assert.equal(result.sourcedNodes,1);assert.equal(result.records[0].sources[0].symbol,'main');
});
test('CLI rejects incomplete and invalid options', () => {
  for (const args of [[],['x.html','--scale'],['x.html','--scale','0'],['x.html','--unknown'],['x.svg']]) assert.throws(()=>options(args));
  assert.equal(options(['x.html','--scale','1.5']).scale,1.5);
});
