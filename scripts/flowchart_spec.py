"""Validate the bundled JSON Schema and graph constraints without third-party packages."""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "flowchart.schema.json"


class SpecError(ValueError):
    """An input error with a JSON field path suitable for users and CI."""


def fail(path, message):
    raise SpecError(f"{path}: {message}")


def check_schema(value, schema, root, path="$"):
    """Implement the assertion keywords used by our checked-in schema, without network IO."""
    if "$ref" in schema:
        ref = schema["$ref"]
        target = root
        for component in ref.removeprefix("#/").split("/"):
            target = target[component]
        check_schema(value, target, root, path)
        return
    kind = schema.get("type")
    def finite_number(v):
        try:
            return type(v) in (int, float) and math.isfinite(v)
        except OverflowError:
            return False
    predicates = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "number": finite_number,
        "integer": lambda v: type(v) is int,
        "boolean": lambda v: type(v) is bool,
    }
    if kind and not predicates[kind](value):
        fail(path, f"expected {kind}" + (" (finite, not a numeric string)" if kind == "number" else ""))
    if "enum" in schema and value not in schema["enum"]:
        fail(path, f"expected one of {schema['enum']}")
    if kind in ("number", "integer"):
        for key, bad in (("minimum", lambda n: value < n), ("maximum", lambda n: value > n),
                         ("exclusiveMinimum", lambda n: value <= n)):
            if key in schema and bad(schema[key]):
                fail(path, f"violates {key}={schema[key]}")
    if kind == "string":
        if len(value) < schema.get("minLength", 0):
            fail(path, "must not be empty")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            fail(path, f"does not match {schema['pattern']}")
    if kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            fail(path, "array length is outside the allowed range")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            fail(path, "items must be unique")
        for index, item in enumerate(value):
            check_schema(item, schema["items"], root, f"{path}[{index}]")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                fail(f"{path}.{key}", "required field is missing")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                check_schema(item, props[key], root, f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                fail(f"{path}.{key}", "unknown field (check the spelling)")
        if "line_end" in value and "line_start" in value and value["line_end"] < value["line_start"]:
            fail(path + ".line_end", "must not be before line_start")


def validate_structure(spec):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    check_schema(spec, schema, schema)
    objects = {}
    for kind in ("zones", "nodes", "junctions"):
        for index, obj in enumerate(spec.get(kind, [])):
            path = f"$.{kind}[{index}]"
            if obj["id"] in objects:
                fail(path + ".id", f"duplicate object id {obj['id']}")
            objects[obj["id"]] = (obj, kind, path)
    for obj, kind, path in objects.values():
        visited = {obj["id"]}
        parent_id = obj.get("parent")
        while parent_id:
            if parent_id not in objects or objects[parent_id][1] != "zones":
                fail(path + ".parent", f"unknown parent zone {parent_id}")
            if parent_id in visited:
                fail(path + ".parent", "parent zones must not form a cycle")
            visited.add(parent_id)
            parent_id = objects[parent_id][0].get("parent")
    links, edge_ids = set(), set()
    for index, edge in enumerate(spec.get("edges", [])):
        path = f"$.edges[{index}]"
        if edge["id"] in edge_ids:
            fail(path + ".id", f"duplicate edge id {edge['id']}")
        edge_ids.add(edge["id"])
        for endpoint in ("from", "to"):
            if edge[endpoint] not in objects:
                fail(path + "." + endpoint, f"unknown object {edge[endpoint]}")
        if ("points" in edge) == ("route" in edge):
            fail(path, "provide exactly one of points or route")
        links.add((edge["from"], edge["to"]))
    for index, route in enumerate(spec.get("paths", [])):
        for j, id_ in enumerate(route["nodes"]):
            if id_ not in objects:
                fail(f"$.paths[{index}].nodes[{j}]", f"unknown object {id_}")
        for a, b in zip(route["nodes"], route["nodes"][1:]):
            if (a, b) not in links:
                fail(f"$.paths[{index}]", f"no directed edge {a} -> {b}")
    for mode in ("align", "distribute"):
        for index, group in enumerate(spec.get("layout", {}).get(mode, [])):
            for id_ in group["nodes"]:
                if id_ not in objects or objects[id_][1] != "nodes":
                    fail(f"$.layout.{mode}[{index}].nodes", f"unknown node {id_}")
    return objects


def validate_geometry(spec):
    width, height = spec["canvas"]["width"], spec["canvas"]["height"]
    objects = validate_structure(spec)
    for obj, kind, path in objects.values():
        x, y, w, h = obj["x"], obj["y"], obj.get("width", 0), obj.get("height", 0)
        if x < 0 or y < 0 or x + w > width or y + h > height:
            fail(path, "object extends outside canvas")
        if obj.get("parent"):
            parent = objects[obj["parent"]][0]
            if not (parent["x"] <= x and parent["y"] <= y and x + w <= parent["x"] + parent["width"]
                    and y + h <= parent["y"] + parent["height"]):
                fail(path + ".parent", "object is outside its parent zone")
        if kind == "nodes" and obj.get("shape") == "cylinder":
            radius = obj.get("ellipse_radius", 14)
            if radius * 4 + 14 >= h or radius >= w / 2:
                fail(path + ".ellipse_radius", "cylinder must leave room for the content between its arcs")
    for index, edge in enumerate(spec.get("edges", [])):
        for j, point in enumerate(edge.get("points", [])):
            if not (0 <= point[0] <= width and 0 <= point[1] <= height):
                fail(f"$.edges[{index}].points[{j}]", "point extends outside canvas")
        for a, b in zip(edge.get("points", []), edge.get("points", [])[1:]):
            if a == b:
                fail(f"$.edges[{index}].points", "zero-length segment")
            if a[0] != b[0] and a[1] != b[1]:
                fail(f"$.edges[{index}].points", "segments must be horizontal or vertical")
    return width, height


def prepare(spec):
    from layout_helpers import apply_layout
    spec = copy.deepcopy(spec)
    validate_structure(spec)
    apply_layout(spec)
    validate_geometry(spec)
    return spec
