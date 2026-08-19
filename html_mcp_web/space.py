"""Validation and geometry calculations for browser-measured layout space."""

import math
from typing import Any


def validated_bbox(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("bbox must contain x, y, width, and height")
    box = [float(item) for item in value]
    if not all(math.isfinite(item) for item in box) or box[2] < 0 or box[3] < 0:
        raise ValueError("bbox values must be finite and dimensions must be non-negative")
    return box


def validated_width_constraints(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("table width_constraints must be an object")
    numeric_names = [
        "current_width",
        "min_no_wrap_width",
        "reducible_width",
        "reducible_ratio",
        "required_expansion",
    ]
    numbers = {name: float(value[name]) for name in numeric_names}
    if not all(math.isfinite(number) and number >= 0 for number in numbers.values()):
        raise ValueError("table width constraint values must be finite and non-negative")
    if numbers["reducible_ratio"] > 1:
        raise ValueError("table reducible_ratio must not exceed one")

    allowed_range = value["allowed_width_range"]
    if allowed_range is not None:
        if not isinstance(allowed_range, list) or len(allowed_range) != 2:
            raise ValueError("table allowed_width_range must contain minimum and current widths")
        allowed_range = [float(item) for item in allowed_range]
        if not all(math.isfinite(item) and item >= 0 for item in allowed_range):
            raise ValueError("table allowed_width_range values must be finite and non-negative")

    wrapped_cells = value["wrapped_cells"]
    if not isinstance(wrapped_cells, list) or not all(isinstance(ref, str) for ref in wrapped_cells):
        raise ValueError("table wrapped_cells must contain cell references")

    raw_constraint_cells = value["constraint_cells"]
    if not isinstance(raw_constraint_cells, list):
        raise ValueError("table constraint_cells must be a list")
    constraint_cells = []
    for raw_cell in raw_constraint_cells:
        if not isinstance(raw_cell, dict):
            raise ValueError("table constraint cell must be an object")
        if not isinstance(raw_cell["ref"], str) or not raw_cell["ref"]:
            raise ValueError("table constraint cell ref must be a non-empty string")
        cell = {
            "ref": raw_cell["ref"],
            "row": int(raw_cell["row"]),
            "column": int(raw_cell["column"]),
            "colspan": int(raw_cell["colspan"]),
            "min_no_wrap_width": float(raw_cell["min_no_wrap_width"]),
        }
        if cell["row"] < 1 or cell["column"] < 1 or cell["colspan"] < 1:
            raise ValueError("table constraint cell positions must be positive integers")
        if not math.isfinite(cell["min_no_wrap_width"]) or cell["min_no_wrap_width"] < 0:
            raise ValueError("table constraint cell width must be finite and non-negative")
        constraint_cells.append(cell)

    return {
        **numbers,
        "allowed_width_range": allowed_range,
        "wrapped_cells": list(wrapped_cells),
        "constraint_cells": constraint_cells,
    }


def validated_space_pages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("space must be a list of page measurements")
    pages: list[dict[str, Any]] = []
    seen_pages: set[int] = set()
    for raw_page in value:
        if not isinstance(raw_page, dict):
            raise ValueError("space page must be an object")
        number = int(raw_page["number"])
        if number < 1 or number in seen_pages:
            raise ValueError("space page numbers must be unique positive integers")
        seen_pages.add(number)
        raw_nodes = raw_page["nodes"]
        if not isinstance(raw_nodes, dict):
            raise ValueError("space page nodes must be an object")
        nodes: dict[str, Any] = {}
        for ref, raw_node in raw_nodes.items():
            if not isinstance(ref, str) or not isinstance(raw_node, dict):
                raise ValueError("space node references and values must be objects")
            children = raw_node["children"]
            lines = raw_node["lines"]
            padding = raw_node["padding"]
            if not isinstance(children, list) or not all(isinstance(item, str) for item in children):
                raise ValueError("space node children must be string references")
            if not isinstance(lines, list):
                raise ValueError("space node lines must be a list")
            if not isinstance(padding, list) or len(padding) != 4:
                raise ValueError("space node padding must contain four values")
            padding_values = [float(item) for item in padding]
            if not all(math.isfinite(item) and item >= 0 for item in padding_values):
                raise ValueError("space node padding must contain finite non-negative values")
            node = {
                "kind": str(raw_node["kind"]),
                "element": str(raw_node["element"]),
                "bbox": validated_bbox(raw_node["bbox"]),
                "padding": padding_values,
                "children": list(children),
                "lines": [validated_bbox(line) for line in lines],
                "overflow": bool(raw_node["overflow"]),
            }
            if "content_bbox" in raw_node:
                if node["kind"] != "object":
                    raise ValueError("content_bbox is only valid for objects")
                node["content_bbox"] = validated_bbox(raw_node["content_bbox"])
            if "width_constraints" in raw_node:
                if node["kind"] != "table":
                    raise ValueError("width_constraints are only valid for tables")
                node["width_constraints"] = validated_width_constraints(raw_node["width_constraints"])
            if "row" in raw_node:
                node["row"] = int(raw_node["row"])
                node["column"] = int(raw_node["column"])
            nodes[ref] = node
        children = raw_page["children"]
        if not isinstance(children, list) or not all(isinstance(item, str) for item in children):
            raise ValueError("space page children must be string references")
        referenced = list(children) + [child for node in nodes.values() for child in node["children"]]
        for node in nodes.values():
            if "width_constraints" not in node:
                continue
            referenced.extend(node["width_constraints"]["wrapped_cells"])
            referenced.extend(cell["ref"] for cell in node["width_constraints"]["constraint_cells"])
        if any(ref not in nodes for ref in referenced):
            raise ValueError("space measurement references an unknown node")
        pages.append({
            "number": number,
            "bbox": validated_bbox(raw_page["bbox"]),
            "children": list(children),
            "nodes": nodes,
        })
    return pages


def intersection(box: list[float], scope: list[float]) -> list[float] | None:
    left = max(box[0], scope[0])
    top = max(box[1], scope[1])
    right = min(box[0] + box[2], scope[0] + scope[2])
    bottom = min(box[1] + box[3], scope[1] + scope[3])
    return None if right <= left or bottom <= top else [left, top, right - left, bottom - top]


def union_bbox(boxes: list[list[float]]) -> list[float] | None:
    if not boxes:
        return None
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    return [left, top, right - left, bottom - top]


def merged_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def union_area(boxes: list[list[float]], scope: list[float]) -> float:
    clipped = [value for box in boxes if (value := intersection(box, scope)) is not None]
    xs = sorted({
        scope[0],
        scope[0] + scope[2],
        *(box[0] for box in clipped),
        *(box[0] + box[2] for box in clipped),
    })
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        spans = merged_intervals([
            (box[1], box[1] + box[3])
            for box in clipped
            if box[0] < right and box[0] + box[2] > left
        ])
        area += (right - left) * sum(end - start for start, end in spans)
    return area


def maximal_free_regions(
    scope: list[float],
    boxes: list[list[float]],
    clearance: float,
    min_width: float,
    min_height: float,
) -> list[list[float]]:
    expanded = []
    for box in boxes:
        padded = [box[0] - clearance, box[1] - clearance, box[2] + 2 * clearance, box[3] + 2 * clearance]
        clipped = intersection(padded, scope)
        if clipped is not None:
            expanded.append(clipped)
    left, top, width, height = scope
    right = left + width
    bottom = top + height
    xs = sorted({
        left,
        right,
        *(box[0] for box in expanded),
        *(box[0] + box[2] for box in expanded),
    })
    candidates: set[tuple[float, float, float, float]] = set()
    for start_index, x1 in enumerate(xs[:-1]):
        for x2 in xs[start_index + 1:]:
            if x2 - x1 < min_width:
                continue
            merged = merged_intervals([
                (box[1], box[1] + box[3])
                for box in expanded
                if box[0] < x2 and box[0] + box[2] > x1
            ])
            cursor = top
            for y1, y2 in [*merged, (bottom, bottom)]:
                if y1 > cursor and y1 - cursor >= min_height:
                    candidates.add((x1, cursor, x2 - x1, y1 - cursor))
                cursor = max(cursor, y2)
    values = [list(candidate) for candidate in candidates]
    maximal = [
        box for box in values
        if not any(
            other is not box
            and other[0] <= box[0]
            and other[1] <= box[1]
            and other[0] + other[2] >= box[0] + box[2]
            and other[1] + other[3] >= box[1] + box[3]
            for other in values
        )
    ]
    maximal.sort(key=lambda box: (-(box[2] * box[3]), box[1], box[0]))
    return [[round(value, 2) for value in box] for box in maximal]
