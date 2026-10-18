'use strict';

const EPS = 0.8;
const near = (a, b, tolerance = 1) => Math.abs(a - b) <= tolerance;
const samePoint = (a, b) => near(a[0], b[0]) && near(a[1], b[1]);

function interval(obj, coordinate, vertical = false, inset = 0) {
  const x = (vertical ? obj.y : obj.x) + inset;
  const y = (vertical ? obj.x : obj.y) + inset;
  const w = (vertical ? obj.height : obj.width) - 2 * inset;
  const h = (vertical ? obj.width : obj.height) - 2 * inset;
  if (w <= 0 || h <= 0 || coordinate < y || coordinate > y + h) return null;
  const shape = obj.shape || 'rect';
  if (shape === 'diamond') {
    const half = w / 2 * (1 - Math.abs(coordinate - y - h / 2) / (h / 2));
    return [x + w / 2 - half, x + w / 2 + half];
  }
  if (shape === 'terminator') {
    const r = Math.min(w, h) / 2;
    const dy = Math.max(y + r - coordinate, coordinate - (y + h - r), 0);
    const dx = Math.sqrt(Math.max(0, r * r - dy * dy));
    return [x + r - dx, x + w - r + dx];
  }
  if (shape === 'cylinder') {
    const r = Math.max(1, (obj.ellipse_radius || 14) - inset);
    if (vertical) {
      const d = Math.abs(coordinate - y - h / 2) / (h / 2);
      const cap = r * Math.sqrt(Math.max(0, 1 - d * d));
      return [x + r - cap, x + w - r + cap];
    }
    const dy = Math.max(y + r - coordinate, coordinate - (y + h - r), 0);
    const half = w / 2 * Math.sqrt(Math.max(0, 1 - (dy / r) ** 2));
    return [x + w / 2 - half, x + w / 2 + half];
  }
  return [x, x + w];
}

function contains(obj, point, inset = 0) {
  const span = interval(obj, point[1], false, inset);
  return !!span && point[0] >= span[0] && point[0] <= span[1];
}

function boundary(point, obj) {
  if (obj.width === undefined) return Math.hypot(point[0] - obj.x, point[1] - obj.y) <= 1;
  const horizontal = interval(obj, point[1]);
  const vertical = interval(obj, point[0], true);
  return !!((horizontal && horizontal.some(v => near(v, point[0]))) ||
    (vertical && vertical.some(v => near(v, point[1]))));
}

function segmentHit(a, b, obj, inset = EPS) {
  const isVertical = a[0] === b[0];
  const span = interval(obj, isVertical ? a[0] : a[1], isVertical, inset);
  const axis = isVertical ? 1 : 0;
  return !!span && Math.min(Math.max(a[axis], b[axis]), span[1]) >
    Math.max(Math.min(a[axis], b[axis]), span[0]) + 0.01;
}

function overlaps(a, b) {
  return Math.min(a.x + a.width, b.x + b.width) > Math.max(a.x, b.x) + 1 &&
    Math.min(a.y + a.height, b.y + b.height) > Math.max(a.y, b.y) + 1;
}

function segments(edge) {
  return edge.points.slice(1).map((b, i) => [edge.points[i], b]);
}

function intersection(a, b, c, d) {
  const va = a[0] === b[0], vb = c[0] === d[0];
  if (va === vb) {
    const fixed = va ? 0 : 1, axis = 1 - fixed;
    if (!near(a[fixed], c[fixed])) return null;
    const lo = Math.max(Math.min(a[axis], b[axis]), Math.min(c[axis], d[axis]));
    const hi = Math.min(Math.max(a[axis], b[axis]), Math.max(c[axis], d[axis]));
    if (hi < lo - 1) return null;
    const point = va ? [a[0], lo] : [lo, a[1]];
    return { point, overlap: hi - lo > 1 };
  }
  if (va) return intersection(c, d, a, b);
  const point = [c[0], a[1]];
  if (point[0] < Math.min(a[0], b[0]) - 2 || point[0] > Math.max(a[0], b[0]) + 2 ||
      point[1] < Math.min(c[1], d[1]) - 2 || point[1] > Math.max(c[1], d[1]) + 2) return null;
  return { point, overlap: false };
}

function sharedPort(a, b, point) {
  const endpoints = e => [[e.from, e.points[0]], [e.to, e.points.at(-1)]];
  return endpoints(a).some(([id, p]) => samePoint(p, point) &&
    endpoints(b).some(([other, q]) => other === id && samePoint(q, point)));
}

function staticCheck(spec) {
  const issues = [], objects = new Map(['nodes', 'zones', 'junctions'].flatMap(k => spec[k] || []).map(n => [n.id, n]));
  const edges = spec.edges || [];
  for (const edge of edges) {
    for (const [id, point] of [[edge.from, edge.points[0]], [edge.to, edge.points.at(-1)]]) {
      if (!objects.has(id) || !boundary(point, objects.get(id))) issues.push({ type: 'port-not-on-boundary', edge: edge.id, object: id, point });
    }
    for (const node of spec.nodes) {
      if (segments(edge).some(([a, b]) => segmentHit(a, b, node))) {
        issues.push({ type: 'connector-through-node', edge: edge.id, node: node.id });
      }
    }
  }
  for (let i = 0; i < spec.nodes.length; i++) for (let j = i + 1; j < spec.nodes.length; j++) {
    if (overlaps(spec.nodes[i], spec.nodes[j])) issues.push({ type: 'overlapping-nodes', nodes: [spec.nodes[i].id, spec.nodes[j].id] });
  }
  const emitted = new Set();
  for (let i = 0; i < edges.length; i++) for (let j = i + 1; j < edges.length; j++) {
    for (const [a, b] of segments(edges[i])) for (const [c, d] of segments(edges[j])) {
      const hit = intersection(a, b, c, d);
      if (!hit) continue;
      const junction = (spec.junctions || []).some(n => Math.hypot(n.x - hit.point[0], n.y - hit.point[1]) <= 1);
      if (!hit.overlap && (junction || sharedPort(edges[i], edges[j], hit.point))) continue;
      const strict = ![a, b, c, d].some(p => samePoint(p, hit.point));
      const type = hit.overlap ? 'collinear-overlap' : strict ? 'unmarked-crossing' : 'ambiguous-contact';
      const key = `${i}:${j}:${type}:${hit.point.join(',')}`;
      if (!emitted.has(key)) issues.push({ type, edges: [edges[i].id, edges[j].id], point: hit.point });
      emitted.add(key);
    }
  }
  return issues;
}

function checkText(spec, records) {
  const issues = [], nodes = new Map(spec.nodes.map(n => [n.id, n]));
  for (const record of records) {
    const box = record.bounds;
    if (box.x < 0 || box.y < 0 || box.x + box.width > spec.canvas.width || box.y + box.height > spec.canvas.height) {
      issues.push({ type: 'text-outside-canvas', text: record.text });
    }
    if (record.node) {
      const node = nodes.get(record.node);
      const padY = node.shape === 'cylinder' ? 2 * (node.ellipse_radius || 14) + 7 : 7;
      const corners = [[box.x, box.y], [box.x + box.width, box.y], [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]];
      if (box.y < node.y + padY || box.y + box.height > node.y + node.height - padY || !corners.every(p => contains(node, p, 7))) {
        issues.push({ type: 'text-outside-content-box', node: node.id, text: record.text, bounds: box });
      }
    } else {
      for (const node of spec.nodes) if (overlaps(box, node)) issues.push({ type: 'label-overlaps-node', node: node.id, text: record.text });
    }
    for (const edge of spec.edges || []) {
      if (segments(edge).some(([a, b]) => segmentHit(a, b, box, 0))) issues.push({ type: 'connector-through-text', edge: edge.id, text: record.text });
    }
  }
  for (let i = 0; i < records.length; i++) for (let j = i + 1; j < records.length; j++) {
    if (overlaps(records[i].bounds, records[j].bounds)) issues.push({ type: 'overlapping-text', texts: [records[i].text, records[j].text] });
  }
  return issues;
}

module.exports = { boundary, contains, segmentHit, intersection, staticCheck, checkText };
