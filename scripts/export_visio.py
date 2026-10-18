#!/usr/bin/env python3
"""Export a flowchart as native, editable Visio 2003 XML (.vdx).

Uses only the standard library. The Windows wrapper opens this interchange file
in Microsoft Visio and saves a .vsdx; this module never automates the desktop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET

from flowchart_spec import prepare

NS = "http://schemas.microsoft.com/visio/2003/core"
META_NS = "urn:reference-flowchart:layout:1"
PX_PER_INCH = 96.0
ET.register_namespace("", NS)
ET.register_namespace("flowchart", META_NS)


def number(value):
    """Stable decimal constants in Visio's internal drawing units (inches)."""
    value = float(value)
    return "0" if abs(value) < 1e-12 else format(value, ".12g")


def element(parent, name, value=None, **attributes):
    result = ET.SubElement(parent, "{" + NS + "}" + name,
                           {key: str(v) for key, v in attributes.items()})
    if value is not None:
        result.text = str(value)
    return result


def cell(parent, name, value, formula=None, unit=None):
    attributes = {}
    if formula is not None:
        attributes["F"] = formula
    if unit is not None:
        attributes["Unit"] = unit
    return element(parent, name, number(value) if isinstance(value, (int, float)) else value,
                   **attributes)


def _check_xml_strings(value):
    """JSON permits control characters which XML 1.0 cannot represent."""
    if isinstance(value, str):
        if any(not (c in "\t\n\r" or "\u0020" <= c <= "\ud7ff" or
                    "\ue000" <= c <= "\ufffd" or "\U00010000" <= c <= "\U0010ffff") for c in value):
            raise ValueError("VDX text contains a character not permitted by XML 1.0.")
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_xml_strings(key)
            _check_xml_strings(item)
    elif isinstance(value, list):
        for item in value:
            _check_xml_strings(item)


def _box(shape, obj, page_height):
    x, y, w, h = (float(obj[key]) / PX_PER_INCH for key in ("x", "y", "width", "height"))
    transform = element(shape, "XForm")
    cell(transform, "PinX", x + w / 2)
    cell(transform, "PinY", page_height - y - h / 2)
    cell(transform, "Width", w)
    cell(transform, "Height", h)
    cell(transform, "LocPinX", w / 2, "Width*0.5")
    cell(transform, "LocPinY", h / 2, "Height*0.5")
    cell(transform, "Angle", 0)
    cell(transform, "FlipX", 0)
    cell(transform, "FlipY", 0)
    return w, h


def _style(shape, *, filled=True, dashed=False, line_width=1.8,
           arrow=False, invisible=False, black=False):
    line = element(shape, "Line")
    cell(line, "LineWeight", line_width / PX_PER_INCH)
    cell(line, "LineColor", "#111111")
    cell(line, "LinePattern", 0 if invisible else 2 if dashed else 1)
    cell(line, "BeginArrow", 0)
    cell(line, "EndArrow", 4 if arrow else 0)
    cell(line, "EndArrowSize", 1)
    cell(line, "LineCap", 1)
    fill = element(shape, "Fill")
    cell(fill, "FillForegnd", "#111111" if black else "#FFFFFF")
    cell(fill, "FillBkgnd", "#FFFFFF")
    cell(fill, "FillPattern", 1 if filled else 0)
    cell(fill, "ShdwPattern", 0)


def _geometry(shape, points, width, height, *, index=0, filled=True):
    """A native closed or open geometry; normalized formulas allow resizing."""
    geom = element(shape, "Geom", IX=index)
    cell(geom, "NoFill", 0 if filled else 1)
    cell(geom, "NoLine", 0)
    for index, (x, y) in enumerate(points, 1):
        row = element(geom, "MoveTo" if index == 1 else "LineTo", IX=index)
        cell(row, "X", x, "Width*" + number(x / width) if width else "0")
        cell(row, "Y", y, "Height*" + number(y / height) if height else "0")
    return geom


def _arc(geom, index, x, y, a, b, width, height, ratio):
    row = element(geom, "EllipticalArcTo", IX=index)
    for key, value, extent, reference in (("X", x, width, "Width"), ("Y", y, height, "Height"),
                                           ("A", a, width, "Width"), ("B", b, height, "Height")):
        cell(row, key, value, reference + "*" + number(value / extent))
    cell(row, "C", 0)
    cell(row, "D", ratio, "Width/Height*" + number(ratio*height/width))


def _node_geometry(shape, obj, width, height):
    kind = obj.get("shape", "rect")
    if kind == "diamond":
        _geometry(shape, [(width/2, 0), (width, height/2), (width/2, height),
                          (0, height/2), (width/2, 0)], width, height)
    elif kind == "cylinder":
        radius = obj.get("ellipse_radius", 14) / PX_PER_INCH
        if width / (2 * radius) > 1000:
            raise ValueError(f"node {obj['id']}: ellipse_radius is too small for Visio; width/(2*ellipse_radius) must be <= 1000.")
        geom = _geometry(shape, [(0, radius)], width, height)
        _arc(geom, 2, width, radius, width/2, 0, width, height, width/(2*radius))
        row = element(geom, "LineTo", IX=3)
        cell(row, "X", width, "Width")
        cell(row, "Y", height-radius, "Height*" + number((height-radius)/height))
        _arc(geom, 4, 0, height-radius, width/2, height, width, height, width/(2*radius))
        row = element(geom, "LineTo", IX=5)
        cell(row, "X", 0)
        cell(row, "Y", radius, "Height*" + number(radius/height))
        top = _geometry(shape, [(0, height-radius)], width, height, index=1, filled=False)
        _arc(top, 2, width, height-radius, width/2, height-2*radius,
             width, height, width/(2*radius))
    elif kind == "terminator":
        radius = min(width, height)/2
        offset = radius * math.sqrt(0.5)
        geom = _geometry(shape, [(radius, 0), (width-radius, 0)], width, height)
        _arc(geom, 3, width, radius, width-radius+offset, radius-offset, width, height, 1)
        row = element(geom, "LineTo", IX=4)
        cell(row, "X", width, "Width")
        cell(row, "Y", height-radius, "Height*" + number((height-radius)/height))
        _arc(geom, 5, width-radius, height, width-radius+offset, height-radius+offset,
             width, height, 1)
        row = element(geom, "LineTo", IX=6)
        cell(row, "X", radius, "Width*" + number(radius/width))
        cell(row, "Y", height, "Height")
        _arc(geom, 7, 0, height-radius, radius-offset, height-radius+offset,
             width, height, 1)
        row = element(geom, "LineTo", IX=8)
        cell(row, "X", 0)
        cell(row, "Y", radius, "Height*" + number(radius/height))
        _arc(geom, 9, radius, 0, radius-offset, radius-offset, width, height, 1)
    else:
        _geometry(shape, [(0, 0), (width, 0), (width, height), (0, height), (0, 0)],
                  width, height)


def _text(shape, lines, size, *, bold_first=False, bold=False, anchor="middle", line_height=None):
    # Character run indices: regular, bold, regular subscript, bold subscript.
    for index in range(4):
        char = element(shape, "Char", IX=index)
        cell(char, "Font", 0)
        cell(char, "Color", "#111111")
        cell(char, "Style", index % 2)
        cell(char, "Pos", 2 if index >= 2 else 0)
        cell(char, "Size", size / PX_PER_INCH)
        cell(char, "AsianFont", 0)
    para = element(shape, "Para", IX=0)
    # A positive SpLine value is absolute spacing, in internal length units.
    cell(para, "SpLine", (line_height if line_height is not None else size*1.34) / PX_PER_INCH)
    cell(para, "HorzAlign", {"start": 0, "middle": 1, "end": 2}[anchor])
    block = element(shape, "TextBlock")
    for side in ("Left", "Right", "Top", "Bottom"):
        cell(block, side + "Margin", 0)
    cell(block, "VerticalAlign", 1)
    text = element(shape, "Text")
    element(text, "pp", IX=0)
    for index, line in enumerate(lines):
        is_bold = bool(bold or (bold_first and index == 0))
        if index:
            text[-1].tail = (text[-1].tail or "") + "\n"
        for fragment in re.split(r"(\{[^{}\n]+\})", str(line)):
            if not fragment:
                continue
            subscript = fragment.startswith("{") and fragment.endswith("}")
            run = element(text, "cp", IX=int(is_bold) + (2 if subscript else 0))
            run.tail = fragment[1:-1] if subscript else fragment


def _metadata(shape, kind, obj):
    element(shape, "Data1", json.dumps({"object_type": kind, **obj}, ensure_ascii=False, separators=(",", ":")))


def _connection(shape, obj, point, index, *, junction=False):
    """Attach to the original port's normalized position, not a page constant."""
    if junction:
        w = h = 2 * obj.get("radius", 5)
        x = y = 0.5
    else:
        w, h = obj["width"], obj["height"]
        x = (point[0]-obj["x"])/w
        y = 1-(point[1]-obj["y"])/h
    connection = element(shape, "Connection", IX=index)
    cell(connection, "X", x*w/PX_PER_INCH, "Width*" + number(x))
    cell(connection, "Y", y*h/PX_PER_INCH, "Height*" + number(y))
    cell(connection, "DirX", 0)
    cell(connection, "DirY", 0)
    cell(connection, "Type", 0)


def _edge(shape, edge, refs, page_height, connects, ports):
    points = [(p[0]/PX_PER_INCH, page_height-p[1]/PX_PER_INCH) for p in edge["points"]]
    begin, end = points[0], points[-1]
    dx, dy = end[0]-begin[0], end[1]-begin[1]
    length = math.hypot(dx, dy)
    angle = math.atan2(dy, dx) if length else 0
    # A 1D shape's local x axis follows its start/end vector. The geometry below
    # maps the explicit page-space bends into that coordinate system.
    transform = element(shape, "XForm")
    cell(transform, "PinX", begin[0], "BeginX")
    cell(transform, "PinY", begin[1], "BeginY")
    cell(transform, "Width", length, "SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)")
    cell(transform, "Height", 0)
    cell(transform, "LocPinX", 0)
    cell(transform, "LocPinY", 0)
    cell(transform, "Angle", angle, "ATAN2(EndY-BeginY,EndX-BeginX)")
    endpoints = element(shape, "XForm1D")
    for which, point, field in (("Begin", begin, "from"), ("End", end, "to")):
        target_id = refs[edge[field]][0]
        port = ports[(edge["id"], field)]
        formula = ("PAR(PNT(Sheet." + str(target_id) + "!Connections.X" + str(port+1) +
                   ",Sheet." + str(target_id) + "!Connections.Y" + str(port+1) + "))")
        cell(endpoints, which + "X", point[0], formula)
        cell(endpoints, which + "Y", point[1], formula)
        element(connects, "Connect", FromSheet=shape.get("ID"), FromCell=which+"X",
                FromPart=9 if which == "Begin" else 12, ToSheet=target_id,
                ToCell="Connections.X" + str(port+1), ToPart=100+port)
    _style(shape, filled=False, line_width=2.3 if edge.get("kind") == "main" else 2,
           arrow=edge.get("arrow", True))
    geom = element(shape, "Geom", IX=0)
    cell(geom, "NoFill", 1)
    for index, point in enumerate(points):
        row = element(geom, "MoveTo" if index == 0 else "LineTo", IX=index+1)
        if index == 0:
            cell(row, "X", 0)
            cell(row, "Y", 0)
        elif index == len(points)-1:
            cell(row, "X", length, "Width")
            cell(row, "Y", 0)
        else:
            # Keep bends on the first/last segment aligned with the glued port
            # when one endpoint moves. Interior waypoints remain editable.
            expressions = []
            for axis, axis_name in ((0, "X"), (1, "Y")):
                if abs(point[axis]-begin[axis]) < 1e-10:
                    expressions.append("Begin" + axis_name)
                elif abs(point[axis]-end[axis]) < 1e-10:
                    expressions.append("End" + axis_name)
                else:
                    expressions.append(number(point[axis]) + " in")
            px, py = expressions
            vx, vy = point[0]-begin[0], point[1]-begin[1]
            cell(row, "X", vx*math.cos(angle)+vy*math.sin(angle),
                 "("+px+"-BeginX)*COS(Angle)+("+py+"-BeginY)*SIN(Angle)")
            cell(row, "Y", -vx*math.sin(angle)+vy*math.cos(angle),
                 "-("+px+"-BeginX)*SIN(Angle)+("+py+"-BeginY)*COS(Angle)")
    _metadata(shape, "edge", edge)


def render_visio(spec):
    """Resolve and serialize a spec as a native VDX document (no bitmap data)."""
    spec = prepare(spec)
    _check_xml_strings(spec)
    canvas = spec["canvas"]
    width, height = canvas["width"]/PX_PER_INCH, canvas["height"]/PX_PER_INCH
    root = ET.Element("{"+NS+"}VisioDocument", {"version": "11.0", "metric": "0"})
    font_name = canvas.get("font_family", "SimSun").split(",")[0].strip().strip("\"'") or "SimSun"
    fonts = element(root, "FaceNames")
    element(fonts, "FaceName", ID=0, Name=font_name)
    pages = element(root, "Pages")
    page = element(pages, "Page", ID=0, Name="流程图", NameU="Flowchart")
    page_sheet = element(page, "PageSheet")
    properties = element(page_sheet, "PageProps")
    cell(properties, "PageWidth", width)
    cell(properties, "PageHeight", height)
    cell(properties, "PageScale", 1)
    cell(properties, "DrawingScale", 1)
    shapes, connects = element(page, "Shapes"), element(page, "Connects")
    refs, next_id = {}, 1
    for kind in ("zones", "nodes", "junctions"):
        for obj in spec.get(kind, []):
            refs[obj["id"]] = (next_id, kind, obj)
            next_id += 1
    edge_ids = {}
    for edge in spec.get("edges", []):
        edge_ids[edge["id"]] = next_id
        next_id += 1
    shape_elements = {}
    for obj_id, (shape_id, kind, obj) in refs.items():
        prefix = {"zones": "zone", "nodes": "node", "junctions": "junction"}[kind]
        shape_elements[obj_id] = ET.Element("{"+NS+"}Shape", {
            "ID": str(shape_id), "NameU": prefix+"-"+obj_id,
            "Name": prefix+"-"+obj_id, "Type": "Shape"})
    ports, counts = {}, {}
    for edge in spec.get("edges", []):
        for field, point in (("from", edge["points"][0]), ("to", edge["points"][-1])):
            obj_id = edge[field]
            port = counts.get(obj_id, 0)
            counts[obj_id] = port + 1
            ports[(edge["id"], field)] = port
    for zone in spec.get("zones", []):
        shape = shape_elements[zone["id"]]
        w, h = _box(shape, zone, height)
        _style(shape, filled=False, dashed=True, line_width=1.6)
        _node_geometry(shape, {}, w, h)
        _metadata(shape, "zone", zone)
        shapes.append(shape)
    for edge in spec.get("edges", []):
        shape = element(shapes, "Shape", ID=edge_ids[edge["id"]], Type="Shape",
                        Name="edge-"+edge["id"], NameU="edge-"+edge["id"])
        _edge(shape, edge, refs, height, connects, ports)
    for junction in spec.get("junctions", []):
        shape = shape_elements[junction["id"]]
        radius = junction.get("radius", 5)
        box = {"x": junction["x"]-radius, "y": junction["y"]-radius,
               "width": 2*radius, "height": 2*radius}
        w, h = _box(shape, box, height)
        _style(shape, black=True, line_width=0)
        geom = element(shape, "Geom", IX=0)
        row = element(geom, "Ellipse", IX=1)
        for name, value, formula in (("X", w/2, "Width*0.5"), ("Y", h/2, "Height*0.5"),
                                      ("A", w, "Width"), ("B", h/2, "Height*0.5"),
                                      ("C", w/2, "Width*0.5"), ("D", h, "Height")):
            cell(row, name, value, formula)
        _metadata(shape, "junction", junction)
        shapes.append(shape)
    for node in spec["nodes"]:
        shape = shape_elements[node["id"]]
        w, h = _box(shape, node, height)
        _style(shape)
        _node_geometry(shape, node, w, h)
        _text(shape, node["lines"], node.get("font_size", canvas.get("font_size", 25)),
              bold_first=True, line_height=node.get("line_height"))
        _metadata(shape, "node", node)
        shapes.append(shape)
    for edge in spec.get("edges", []):
        for field, point in (("from", edge["points"][0]), ("to", edge["points"][-1])):
            _, kind, obj = refs[edge[field]]
            _connection(shape_elements[edge[field]], obj, point, ports[(edge["id"], field)],
                        junction=kind == "junctions")

    def label(name, x, baseline, value, size, bold=False, anchor="middle"):
        nonlocal next_id
        # Width estimate reserves room for editing; native text retains alignment.
        columns = sum(1 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.6 for ch in str(value))
        box_width = max(size*2, columns*size+size*0.5)
        offset = {"start": 0, "middle": 0.5, "end": 1}[anchor]
        obj = {"x": x-box_width*offset, "y": baseline-size*0.84,
               "width": box_width, "height": size*1.2}
        shape = element(shapes, "Shape", ID=next_id, Type="Shape", Name=name, NameU=name)
        next_id += 1
        w, h = _box(shape, obj, height)
        _style(shape, filled=False, invisible=True)
        _geometry(shape, [(0, 0), (w, 0), (w, h), (0, h), (0, 0)], w, h, filled=False)
        _text(shape, [value], size, bold=bold, anchor=anchor)
        return shape

    if canvas.get("title"):
        label("chart-title", canvas["width"]/2, canvas.get("title_y", 46),
              canvas["title"], canvas.get("title_size", 35), True)
    if canvas.get("subtitle"):
        label("chart-subtitle", canvas["width"]/2, canvas.get("subtitle_y", 83),
              canvas["subtitle"], canvas.get("subtitle_size", 23))
    for zone in spec.get("zones", []):
        label("zone-title-"+zone["id"], zone["x"]+zone["width"]/2,
              zone.get("title_y", zone["y"]+38), zone["title"], zone.get("font_size", 28), True)
    for index, note in enumerate(spec.get("labels", [])):
        label_shape = label("label-"+str(index+1), note["x"], note["y"], note["text"],
                            note.get("font_size", 23), note.get("bold", False), note.get("anchor", "middle"))
        _metadata(label_shape, "label", note)
    solution = element(root, "SolutionXML", Name="reference-flowchart")
    layout_text = json.dumps(spec, ensure_ascii=False, indent=2)+"\n"
    data = ET.SubElement(solution, "{"+META_NS+"}Layout", {
        "sha256": hashlib.sha256(layout_text.encode("utf-8")).hexdigest()})
    data.text = layout_text
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write_visio(spec, output, overwrite=False):
    """Atomically write a native .vdx, refusing existing output by default."""
    output = Path(output).resolve()
    if output.suffix.lower() != ".vdx":
        raise ValueError("--output must have a .vdx extension.")
    if not overwrite and output.exists():
        raise FileExistsError("Output already exists. Use another path or explicitly pass --overwrite.")
    xml = render_visio(spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(xml)
        if overwrite:
            os.replace(temporary, output)
        else:
            # Linking a completed sibling is atomic and cannot clobber a file
            # created after our initial exists() check (unlike os.replace).
            try:
                os.link(temporary, output)
            except FileExistsError:
                raise FileExistsError("Output already exists. Use another path or explicitly pass --overwrite.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Native editable Visio XML (.vdx)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
        path = write_visio(spec, args.output, args.overwrite)
        print(json.dumps({"status": "rendered", "format": "vdx", "files": [str(path)]}, ensure_ascii=False))
    except (KeyError, ValueError, TypeError, OSError) as exc:
        parser.exit(1, "Visio generation failed: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
