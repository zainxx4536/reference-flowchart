'use strict';

// Runs inside Chromium. SVG getBBox includes the font's full metric box, which
// can overlap adjacent lines even when their actual glyphs are separate.
function measureTextBounds() {
  const canvas = document.createElement('canvas'), context = canvas.getContext('2d');
  return [...document.querySelectorAll('#flowchart text')].map(text => {
    const raw = text.getBBox(), walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT);
    let child, address = 0, left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    while ((child = walker.nextNode())) {
      const style = getComputedStyle(child.parentElement);
      context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      for (const character of child.nodeValue) {
        if (address >= text.getNumberOfChars()) break;
        const start = text.getStartPositionOfChar(address), metrics = context.measureText(character);
        if (metrics.actualBoundingBoxAscent + metrics.actualBoundingBoxDescent > 0) {
          left = Math.min(left, start.x - metrics.actualBoundingBoxLeft);
          right = Math.max(right, start.x + metrics.actualBoundingBoxRight);
          top = Math.min(top, start.y - metrics.actualBoundingBoxAscent);
          bottom = Math.max(bottom, start.y + metrics.actualBoundingBoxDescent);
        }
        address += character.length;
      }
    }
    const parent = text.closest('.node');
    return { node: parent ? parent.id.replace(/^node-/, '') : null, text: text.textContent,
      bounds: Number.isFinite(left) ? { x: left, y: top, width: right - left, height: bottom - top }
        : { x: raw.x, y: raw.y, width: raw.width, height: raw.height },
      metricBounds: { x: raw.x, y: raw.y, width: raw.width, height: raw.height } };
  });
}

module.exports = { measureTextBounds };
