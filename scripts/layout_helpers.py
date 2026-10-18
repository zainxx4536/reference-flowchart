"""Small explicit alignment helpers and obstacle-avoiding orthogonal routes."""
from __future__ import annotations

import heapq
import itertools
import math

DIRECTIONS = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def port(obj, side):
    if "width" not in obj:
        return [obj["x"], obj["y"]]
    x, y, w, h = (obj[k] for k in ("x", "y", "width", "height"))
    return {"left": [x, y+h/2], "right": [x+w, y+h/2],
            "top": [x+w/2, y], "bottom": [x+w/2, y+h]}[side]


def simplify(points):
    result = []
    for p in points:
        if result and p == result[-1]:
            continue
        result.append(p)
        while len(result) >= 3:
            a, b, c = result[-3:]
            if not ((a[0] == b[0] == c[0] and (b[1]-a[1])*(c[1]-b[1]) >= 0)
                    or (a[1] == b[1] == c[1] and (b[0]-a[0])*(c[0]-b[0]) >= 0)):
                break
            result.pop(-2)
    return result


def blocked(a, b, boxes):
    for left, top, right, bottom in boxes:
        if a[0] == b[0]:
            if left + 1e-6 < a[0] < right - 1e-6 and max(a[1], b[1]) > top + 1e-6 and min(a[1], b[1]) < bottom - 1e-6:
                return True
        elif top + 1e-6 < a[1] < bottom - 1e-6 and max(a[0], b[0]) > left + 1e-6 and min(a[0], b[0]) < right - 1e-6:
            return True
    return False


def grid_route(start, end, boxes, width, height):
    if start == end:
        return [start]
    xs = sorted({0, width, start[0], end[0], *(v for b in boxes for v in (b[0], b[2]) if 0 <= v <= width)})
    ys = sorted({0, height, start[1], end[1], *(v for b in boxes for v in (b[1], b[3]) if 0 <= v <= height)})
    initial = (xs.index(start[0]), ys.index(start[1]), -1)
    target = (xs.index(end[0]), ys.index(end[1]))
    distances, parents = {initial: 0}, {}
    serial = itertools.count()
    queue = [(0, next(serial), initial)]
    while queue:
        _, _, state = heapq.heappop(queue)
        ix, iy, direction = state
        cost = distances[state]
        if (ix, iy) == target:
            route = [[xs[ix], ys[iy]]]
            while state != initial:
                state = parents[state]
                route.append([xs[state[0]], ys[state[1]]])
            return list(reversed(route))
        for dx, dy, next_direction in ((1, 0, 0), (-1, 0, 0), (0, 1, 1), (0, -1, 1)):
            nx, ny = ix+dx, iy+dy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            a, b = [xs[ix], ys[iy]], [xs[nx], ys[ny]]
            if blocked(a, b, boxes):
                continue
            next_cost = cost + abs(a[0]-b[0]) + abs(a[1]-b[1]) + (12 if direction not in (-1, next_direction) else 0)
            neighbor = (nx, ny, next_direction)
            if next_cost >= distances.get(neighbor, math.inf):
                continue
            distances[neighbor], parents[neighbor] = next_cost, state
            heuristic = abs(b[0]-end[0]) + abs(b[1]-end[1])
            heapq.heappush(queue, (next_cost+heuristic, next(serial), neighbor))
    return None


def auto_route(edge, objects, spec):
    from flowchart_spec import SpecError
    route = edge["route"]
    clearance = route.get("clearance", 20)
    a, b = objects[edge["from"]], objects[edge["to"]]
    sides = lambda obj, value: [value] if value != "auto" else (list(DIRECTIONS) if "width" in obj else ["right"])
    combinations = []
    for sa in sides(a, route.get("from_port", "auto")):
        for sb in sides(b, route.get("to_port", "auto")):
            if a is b and sa == sb:
                continue
            start, end = port(a, sa), port(b, sb)
            distance = abs(start[0]-end[0])+abs(start[1]-end[1])
            combinations.append((distance, sa, sb, start, end))
    boxes = [(n["x"]-clearance, n["y"]-clearance, n["x"]+n["width"]+clearance,
              n["y"]+n["height"]+clearance) for n in spec["nodes"]]
    width, height = spec["canvas"]["width"], spec["canvas"]["height"]
    for _, sa, sb, start, end in sorted(combinations):
        stub = lambda p, side, obj: [p[i] + DIRECTIONS[side][i]*clearance for i in (0, 1)] if "width" in obj else p
        first, last = stub(start, sa, a), stub(end, sb, b)
        if not all(0 <= p[0] <= width and 0 <= p[1] <= height for p in (first, last)):
            continue
        # The short terminal segments may traverse their own node's clearance only.
        unrelated_a = [box for n, box in zip(spec["nodes"], boxes) if n["id"] != a["id"]]
        unrelated_b = [box for n, box in zip(spec["nodes"], boxes) if n["id"] != b["id"]]
        if blocked(start, first, unrelated_a) or blocked(last, end, unrelated_b):
            continue
        points = grid_route(first, last, boxes, width, height)
        if points is not None:
            return simplify([start, *points, end])
    raise SpecError(f"edge {edge['id']}.route: no obstacle-free route; move nodes, reduce clearance, or specify points")


def apply_layout(spec):
    nodes = {n["id"]: n for n in spec["nodes"]}
    directives = spec.pop("layout", {})
    for group in directives.get("align", []):
        axis = group["axis"]
        extent = "width" if axis == "x" else "height"
        factor = {"start": 0, "center": .5, "end": 1}[group.get("anchor", "start")]
        first = nodes[group["nodes"][0]]
        value = group.get("value", first[axis]+first[extent]*factor)
        for id_ in group["nodes"]:
            nodes[id_][axis] = value-nodes[id_][extent]*factor
    for group in directives.get("distribute", []):
        axis = group["axis"]
        extent = "width" if axis == "x" else "height"
        for a, b in zip(group["nodes"], group["nodes"][1:]):
            nodes[b][axis] = nodes[a][axis]+nodes[a][extent]+group["gap"]
    objects = {obj["id"]: obj for kind in ("nodes", "zones", "junctions") for obj in spec.get(kind, [])}
    for edge in spec.get("edges", []):
        if "route" in edge:
            edge["points"] = auto_route(edge, objects, spec)
            del edge["route"]
