#!/usr/bin/env python3
"""Compare a new observation with the last operator-accepted, end-to-end baseline."""
import argparse
import json
from pathlib import Path
import re
import sys

from flow import load_json, private_json, require, text_value

FIELDS = {"runner_version", "host_version", "ios_version", "mini_version", "layout", "flow_sha256", "pages"}


def read_observation(obj):
    require(isinstance(obj, dict) and set(obj) == FIELDS, "unexpected or missing observation fields")
    for key in FIELDS - {"pages", "layout", "flow_sha256"}:
        require(text_value(obj[key]), f"missing {key}; use 'unavailable' for a hidden mini version")
    require(bool(re.fullmatch("[a-f0-9]{64}", str(obj["flow_sha256"]))), "invalid flow digest")
    layout = obj["layout"]
    require(isinstance(layout, dict) and set(layout) == {"width", "height", "scale", "orientation"}, "invalid layout")
    for key in ("width", "height", "scale"):
        require(type(layout[key]) in (int, float) and 0 < layout[key] <= 100000, "invalid positive screen dimension or scale")
    require(layout["orientation"] in ("portrait", "landscape"), "unknown orientation")
    pages = obj["pages"]
    require(isinstance(pages, dict) and bool(pages), "need at least one page")
    require(all(text_value(k) and isinstance(v, list) and v and all(text_value(s) for s in v)
                for k, v in pages.items()), "pages need stable semantic anchor IDs")
    return {**obj, "pages": {key: sorted(set(items)) for key, items in pages.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="record an operator-confirmed real-device baseline")
    record.add_argument("observation")
    record.add_argument("--verified", choices=("already_today", "new_receipt", "profile_verified"), required=True)
    record.add_argument("--out", type=Path, required=True)
    plan = commands.add_parser("plan", help="decide what needs re-inspection before replay")
    plan.add_argument("observation")
    plan.add_argument("--baseline", type=Path, help="prefer this local verified baseline over the shipped one")
    plan.add_argument("--task", choices=("asus", "storm", "yogurt", "colorful"), help="look up the shipped baseline")
    plan.add_argument("--gate", choices=("normal", "unknown_page", "account", "privacy", "verification", "payment"),
                      default="normal", help="current UI gate; overrides replay even if the fingerprint matches")
    args = parser.parse_args()
    if args.command == "plan" and args.gate != "normal":
        print(json.dumps({"action": "pause_and_inspect" if args.gate == "unknown_page" else "await_user", "gate": args.gate}))
        return
    current = read_observation(load_json(args.observation))
    if args.command == "record":
        private_json(args.out, {"version": 1, "verified": args.verified, "observation": current})
        print("Saved operator-verified baseline.")
        return
    baseline = args.baseline
    if baseline is None and args.task:
        bundled = Path(__file__).resolve().parent.parent / "references" / "baselines" / (args.task + ".json")
        if bundled.is_file():
            baseline = bundled
    if baseline is None:
        print(json.dumps({"action": "inspect_first_run", "pages": sorted(current["pages"])}))
        return
    prior = load_json(baseline)
    require(isinstance(prior, dict) and prior.get("version") == 1 and
            prior.get("verified") in ("already_today", "new_receipt", "profile_verified"), "unverified baseline")
    previous = read_observation(prior.get("observation"))
    changed = sorted(k for k in FIELDS - {"pages"} if current[k] != previous[k])
    pages = sorted(k for k, anchors in current["pages"].items() if anchors != previous["pages"].get(k))
    pending = sorted(previous["pages"].keys() - current["pages"].keys())
    action = "check_changed" if changed or pages else ("reuse_observed" if pending else "reuse")
    print(json.dumps({"action": action,
                      "changed_fields": changed, "changed_pages": pages, "pending_pages": pending}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RecursionError) as exc:
        sys.exit(str(exc))
