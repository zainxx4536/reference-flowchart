#!/usr/bin/env python3
"""Render an explicitly laid-out flowchart JSON as editable SVG and HTML.

Standard library only. Semantic review and routing remain the caller's work.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path
from urllib.parse import quote


def escape(value):
    return html.escape(str(value), quote=True)


def number(value):
    return f"{float(value):g}"


def rich(value, size):
    # Optional subscript notation: S{t+1}. Everything else is literal, escaped text.
    return "".join(
        f'<tspan baseline-shift="sub" font-size="{size * .7:g}">{escape(c[1:-1])}</tspan>'
        if c.startswith("{") else escape(c)
        for c in re.split(r"(\{[^{}\n]+\})", str(value))
    )


def text(x, y, value, size=25, bold=False, anchor="middle", extra=""):
    return (
        f'<text x="{number(x)}" y="{number(y)}" font-size="{number(size)}" '
        f'font-weight="{700 if bold else 400}" text-anchor="{escape(anchor)}" {extra}>'
        f'{rich(value, size)}</text>'
    )


def validate(spec):
    canvas = spec["canvas"]
    width, height = float(canvas["width"]), float(canvas["height"])
    if not all(math.isfinite(v) and 100 <= v <= 20000 for v in (width, height)):
        raise ValueError("Canvas dimensions must be finite numbers between 100 and 20000.")
    if not spec.get("nodes"):
        raise ValueError("At least one node is required.")
    objects = {}
    for kind in ("zones", "nodes", "junctions"):
        for obj in spec.get(kind, []):
            id_ = obj["id"]
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", id_) or id_ in objects:
                raise ValueError(f"Invalid or duplicate object id: {id_}")
            objects[id_] = obj
            x, y = float(obj["x"]), float(obj["y"])
            w, h = (float(obj["width"]), float(obj["height"])) if kind != "junctions" else (0, 0)
            if not all(math.isfinite(v) for v in (x, y, w, h)):
                raise ValueError(f"Non-finite geometry: {id_}")
            if x < 0 or y < 0 or x+w > width or y+h > height or (kind != "junctions" and min(w, h) <= 0):
                raise ValueError(f"Object outside canvas or non-positive size: {id_}")
            if kind == "nodes" and (obj.get("shape", "rect") not in ("rect", "cylinder") or not obj.get("lines")):
                raise ValueError(f"Node needs lines and a supported shape: {id_}")
    for obj in objects.values():
        if obj.get("parent"):
            parent = objects.get(obj["parent"])
            if not parent or parent not in spec.get("zones", []):
                raise ValueError(f"Unknown parent zone: {obj['id']}")
            if not (parent["x"] <= obj["x"] and parent["y"] <= obj["y"] and
                    obj["x"]+obj.get("width", 0) <= parent["x"]+parent["width"] and
                    obj["y"]+obj.get("height", 0) <= parent["y"]+parent["height"]):
                raise ValueError(f"Object is not contained in parent zone: {obj['id']}")
    edge_ids, links = set(), set()
    for edge in spec.get("edges", []):
        id_ = edge["id"]
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", id_) or id_ in edge_ids:
            raise ValueError(f"Invalid or duplicate edge id: {id_}")
        edge_ids.add(id_)
        if edge["from"] not in objects or edge["to"] not in objects:
            raise ValueError(f"Unknown endpoint in edge: {id_}")
        points = edge["points"]
        if len(points) < 2:
            raise ValueError(f"Edge needs at least two points: {id_}")
        for p in points:
            if len(p) != 2 or not all(math.isfinite(float(v)) for v in p) or not (0 <= p[0] <= width and 0 <= p[1] <= height):
                raise ValueError(f"Invalid point in edge: {id_}")
        for p, q in zip(points, points[1:]):
            if p[0] != q[0] and p[1] != q[1]:
                raise ValueError(f"Helper supports orthogonal routing only: {id_}")
        links.add((edge["from"], edge["to"]))
    for route in spec.get("paths", []):
        for a, b in zip(route["nodes"], route["nodes"][1:]):
            if (a, b) not in links:
                raise ValueError(f"Declared path '{route['name']}' has no edge {a} -> {b}")
    return width, height


def render(spec):
    width, height = validate(spec)
    canvas = spec["canvas"]
    size = float(canvas.get("font_size", 25))
    parts = [f'<rect width="{number(width)}" height="{number(height)}" fill="#fff"/>']
    if canvas.get("title"):
        parts.append(text(width/2, canvas.get("title_y", 46), canvas["title"], canvas.get("title_size", 35), True))
    if canvas.get("subtitle"):
        parts.append(text(width/2, canvas.get("subtitle_y", 83), canvas["subtitle"], canvas.get("subtitle_size", 23)))
    for z in spec.get("zones", []):
        x, y, w, h = [z[k] for k in ("x", "y", "width", "height")]
        parts.append(
            f'<g class="zone" id="zone-{z["id"]}" data-box="{x},{y},{w},{h}">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>'
            + text(x+w/2, z.get("title_y", y+38), z["title"], z.get("font_size", 28), True, extra='class="zone-title"')
            + '</g>'
        )
    for e in spec.get("edges", []):
        points = " ".join(",".join(number(v) for v in p) for p in e["points"])
        marker = 'marker-end="url(#arrow)"' if e.get("arrow", True) else ""
        line_width = 2.3 if e.get("kind") == "main" else 2
        parts.append(
            f'<polyline class="flow" id="edge-{e["id"]}" points="{points}" '
            f'data-from="{e["from"]}" data-to="{e["to"]}" stroke-width="{line_width}" {marker}/>'
        )
    for j in spec.get("junctions", []):
        parts.append(f'<circle class="junction" id="junction-{j["id"]}" cx="{j["x"]}" cy="{j["y"]}" r="{j.get("radius", 5)}"/>')
    for n in spec["nodes"]:
        x, y, w, h = [n[k] for k in ("x", "y", "width", "height")]
        font = float(n.get("font_size", size))
        line_height = float(n.get("line_height", font*1.34))
        radius = float(n.get("ellipse_radius", 14))
        shape = n.get("shape", "rect")
        padding_y = 2*radius+7 if shape == "cylinder" else 7
        parts.append(f'<g class="node" id="node-{n["id"]}" data-box="{x},{y},{w},{h}" data-padding-y="{padding_y}">')
        if shape == "cylinder":
            parts.append(
                f'<path class="box" d="M{x},{y+radius} a{w/2},{radius} 0 0 1 {w},0 v{h-2*radius} '
                f'a{w/2},{radius} 0 0 1 {-w},0 Z"/>'
                f'<path class="arc" d="M{x},{y+radius} a{w/2},{radius} 0 0 0 {w},0"/>'
            )
        else:
            parts.append(f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}"/>')
        baseline = y+h/2-(len(n["lines"])-1)*line_height/2+font*.34
        for i, line in enumerate(n["lines"]):
            parts.append(text(x+w/2, baseline+i*line_height, line, font, i == 0))
        parts.append('</g>')
    for label in spec.get("labels", []):
        parts.append(text(label["x"], label["y"], label["text"], label.get("font_size", 23), label.get("bold", False), label.get("anchor", "middle")))
    font_family = escape(canvas.get("font_family", 'SimSun, "Songti SC", "Noto Serif CJK SC", serif'))
    title = escape(canvas.get("title", "流程图"))
    description = escape(spec.get("description", "输入、处理、输出及反馈关系。"))
    return f'''<svg id="flowchart" xmlns="http://www.w3.org/2000/svg" width="{number(width)}" height="{number(height)}" viewBox="0 0 {number(width)} {number(height)}" font-family="{font_family}" role="img" aria-labelledby="chart-title chart-desc">
<title id="chart-title">{title}</title><desc id="chart-desc">{description}</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 Z" fill="#111"/></marker></defs>
<style>text{{fill:#111}}.zone>rect{{fill:none;stroke:#111;stroke-width:1.6;stroke-dasharray:10 6}}.flow{{fill:none;stroke:#111;stroke-linejoin:round;stroke-linecap:round}}.box{{fill:#fff;stroke:#111;stroke-width:1.8}}.arc{{fill:none;stroke:#111;stroke-width:1.5}}.junction{{fill:#111}}</style>
{''.join(parts)}</svg>'''


def write_outputs(spec, base, overwrite=False):
    width, _ = validate(spec)
    outputs = [Path(str(base)+ext) for ext in (".svg", ".html", ".layout.json")]
    if not overwrite and any(p.exists() for p in outputs):
        raise FileExistsError("Output already exists. Use another base or explicitly pass --overwrite.")
    base.parent.mkdir(parents=True, exist_ok=True)
    svg = render(spec)
    title = escape(spec["canvas"].get("title", "流程图"))
    notes = "".join(f"<p>{escape(note)}</p>" for note in spec.get("notes", []))
    stem = quote(base.name)
    doc = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#eee;color:#111;font-family:"Microsoft YaHei",sans-serif}}.toolbar{{display:flex;gap:12px;flex-wrap:wrap;align-items:center;padding:12px 18px;background:#fff;border-bottom:1px solid #aaa}}.toolbar strong{{margin-right:auto}}button,a{{font:inherit;color:#111}}button,.toolbar a{{padding:6px 10px;border:1px solid #444;background:#fff;text-decoration:none;cursor:pointer}}.viewport{{width:100%;padding:18px;overflow-x:auto}}#flowchart{{display:block;background:white;width:min(100%,{number(width)}px);height:auto;margin:auto}}body.actual #flowchart{{width:{number(width)}px;min-width:{number(width)}px;max-width:none}}.notes{{max-width:1500px;margin:0 auto 20px;padding:12px 24px;background:white;line-height:1.8}}@media print{{.toolbar,.notes{{display:none}}body,.viewport{{margin:0;padding:0;background:white}}#flowchart{{width:100%!important;min-width:0!important;max-width:100%!important}}}}</style></head><body>
<div class="toolbar"><strong>{title}</strong><button id="scale" type="button">按原尺寸查看</button><button id="print" type="button">打印</button><a href="{stem}.svg" download>矢量 SVG</a><a href="{stem}.png">高清 PNG</a></div>
<main class="viewport">{svg}</main><div class="notes">{notes}</div>
<script>document.getElementById('scale').onclick=function(){{this.textContent=document.body.classList.toggle('actual')?'适应窗口':'按原尺寸查看'}};document.getElementById('print').onclick=()=>window.print();</script></body></html>'''
    for target, value in zip(outputs, (svg, doc, json.dumps(spec, ensure_ascii=False, indent=2))):
        target.write_text(value, encoding="utf-8")
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output-base", required=True, type=Path, help="Output prefix without extension")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
        if args.output_base.suffix.lower() in (".svg", ".png", ".html", ".json"):
            raise ValueError("--output-base must not include a file extension.")
        paths = write_outputs(spec, args.output_base.resolve(), args.overwrite)
        print(json.dumps({"status": "rendered", "files": [str(p) for p in paths]}, ensure_ascii=False))
    except (KeyError, ValueError, TypeError, OSError) as exc:
        parser.exit(1, f"Flowchart generation failed: {exc}\n")


if __name__ == "__main__":
    main()
