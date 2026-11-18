#!/usr/bin/env python3
"""Preflight one existing autodam flow or prepare a private JSON import copy."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

FORMAT = "com.witchan.mcpflow.flows"
BLOCKS = set("launch_app find tap input scroll key loop wait verify tool builtin_task open_mini mini_nav mini_step".split())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("non-finite JSON number")

    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=reject_constant)


def text_value(value):
    return isinstance(value, str) and bool(value.strip())


def numeric(value, low, high):
    return type(value) in (float, int) and low <= value <= high and math.isfinite(value)


def rectangle(value):
    return (isinstance(value, list) and len(value) == 4 and
            all(numeric(v, 0, 1) for v in value) and value[0] < value[2] and value[1] < value[3])


def inspect_blocks(blocks, depth=0, observe_only=False):
    require(isinstance(blocks, list) and 0 < len(blocks) <= 1000 and depth <= 6, "invalid block list/depth")
    count = 0
    checks = 0
    for index, block in enumerate(blocks):
        require(isinstance(block, dict), "block must be an object")
        kind = block.get("type")
        require(isinstance(kind, str) and kind in BLOCKS, f"unrecognized block at index {index}")
        if observe_only:
            safe = kind in ("verify", "find") and not block.get("scroll") and block.get("action", "none") == "none"
            require(safe or kind in ("wait", "loop"), f"observe-only scope rejects {kind} or its side effects")
        if kind == "loop":
            repeats = block.get("count")
            require(type(repeats) is int and 1 <= repeats <= 100, "invalid loop count")
            size, child_checks = inspect_blocks(block.get("blocks"), depth + 1, observe_only)
            count += repeats * size
            checks += repeats * child_checks
        else:
            count += 1
        require(count <= 1000, "expanded flow exceeds 1000 steps")
        if "region" in block:
            require(rectangle(block["region"]), "region requires [left,top,right,bottom] in 0..1")
        if "regions" in block:
            areas = block["regions"]
            require(isinstance(areas, dict) and len(areas) <= 128 and all(rectangle(v) for v in areas.values()),
                    "invalid task region overrides")
        if kind in ("open_mini", "mini_step", "builtin_task", "mini_nav"):
            require(text_value(block.get("task")), "missing registered task")
        if kind in ("mini_step", "mini_nav"):
            require(text_value(block.get("step")), "missing registered step")
        if kind == "launch_app":
            require(text_value(block.get("bundle_id")), "missing target bundle")
        if kind in ("verify", "find", "tap"):
            coordinate = kind == "tap" and ("x" in block or "y" in block)
            if coordinate:
                require(all(numeric(block.get(key), 0, 100000) for key in ("x", "y")), "invalid tap coordinates")
                require("region" not in block and "timeout_seconds" not in block, "coordinate tap has text conditions")
            if 'reference_width' in block or 'reference_height' in block:
                require(coordinate and 'coordinate_scale' not in block, 'reference geometry requires same-unit coordinates')
                require(all(numeric(block.get(k), 1, 100000) for k in ('reference_width', 'reference_height')), 'invalid reference geometry')
                require(block['x'] < block['reference_width'] and block['y'] < block['reference_height'], 'tap outside reference geometry')
            if 'reference_scale' in block:
                require('reference_width' in block and 'reference_height' in block and numeric(block['reference_scale'], .1, 10), 'invalid reference scale')
            if 'coordinate_scale' in block:
                require(type(block['coordinate_scale']) in (int, float) and math.isfinite(block['coordinate_scale']) and block['coordinate_scale'] > 0, 'invalid coordinate scale')
            if not coordinate:
                require(text_value(block.get("keyword")), "missing text locator")
            require(block.get("match", "contains") in ("exact", "contains"), "unknown text match")
        if kind == "wait":
            require(numeric(block.get("seconds"), 0.1, 60), "invalid wait duration")
        if kind == "scroll":
            pages = block.get("pages")
            require(type(pages) is int and 1 <= pages <= 100 and block.get("direction") in ("up", "down"),
                    "invalid scroll")
        if kind == "tool":
            require(text_value(block.get("name")) and isinstance(block.get("arguments"), dict), "invalid tool")
        if kind == "input":
            require(text_value(block.get("text")) and block.get("mode") in ("direct", "clipboard"), "invalid input")
        if kind in ("verify", "builtin_task", "open_mini") or (kind == "mini_step" and
                block["step"] in ("verify_profile", "check_receipt", "close")):
            checks += 1
    return count, checks


def select(path, identifier, observe_only=False):
    doc = load_json(path)
    require(isinstance(doc, dict) and doc.get("format") == FORMAT and type(doc.get("version")) is int
            and doc["version"] == 1, "use an autodam v1 flow export, not a daemon configuration or plist")
    flows = doc.get("flows")
    require(isinstance(flows, list) and 1 <= len(flows) <= 100, "invalid flow collection")
    matches = [f for f in flows if isinstance(f, dict) and f.get("id") == identifier]
    require(len(matches) == 1, "flow ID must identify exactly one exported flow")
    flow = matches[0]
    require(text_value(flow.get("name")), "missing flow name")
    if "group" in flow:
        require(text_value(flow["group"]) and len(flow["group"].strip()) <= 40, "invalid flow group")
    interval = flow.get("interval_minutes", 60)
    require(type(interval) is int and 1 <= interval <= 525600, "interval must be integer minutes in 1..525600")
    count, checks = inspect_blocks(flow.get("blocks"), observe_only=observe_only)
    require(checks, "no verification block or registered task with a verification stage")
    return flow, count


def portable_flow(flow):
    fields = ("id", "name", "group", "blocks", "test_data", "interval_minutes")
    return {"format": FORMAT, "version": 1, "flows": [{key: flow[key] for key in fields if key in flow}]}


def private_json(path, doc):
    content = json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as dest:
            dest.write(content)
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "prepare"):
        sub = commands.add_parser(name)
        sub.add_argument("export", type=Path)
        sub.add_argument("--id", required=True, help="exact existing flow ID")
        sub.add_argument("--observe-only", action="store_true", help="allow only read-only checks on the current page")
        if name == "prepare":
            sub.add_argument("--out", required=True, type=Path, help="new private import file")
    args = parser.parse_args()
    flow, count = select(args.export, args.id, args.observe_only)
    canonical = json.dumps(flow["blocks"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    print(f"steps={count} blocks_sha256={hashlib.sha256(canonical.encode()).hexdigest()}")
    if args.command == "prepare":
        private_json(args.out, portable_flow(flow))
        print("Prepared one flow. Use the editor's JSON import; it creates an independent, unscheduled copy.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RecursionError) as exc:
        sys.exit(str(exc))
