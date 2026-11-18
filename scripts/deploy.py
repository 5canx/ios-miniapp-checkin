#!/usr/bin/env python3
"""Put one validated flow in the device's existing Downloads directory via a local USB MCP tunnel."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from flow import portable_flow, require, select

FILES_BUNDLE = "com.apple.DocumentsApp"
LOCAL_FILES = "group.com.apple.FileProvider.LocalStorage"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, endpoint):
        parsed = urllib.parse.urlsplit(endpoint)
        require(parsed.scheme in ("http", "https") and parsed.path == "/mcp" and
                parsed.username is None and parsed.password is None and not parsed.query and
                not parsed.fragment and parsed.port, "use the /mcp URL of the local USB forward")
        host = parsed.hostname
        require(host == "localhost" or (host and ipaddress.ip_address(host).is_loopback),
                "the USB MCP endpoint must be on loopback")
        self.endpoint = endpoint
        self.transport = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        self.seq = 0
        result = self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                         "clientInfo": {"name": "ios-miniapp-checkin", "version": "1"}})
        self.headers["MCP-Protocol-Version"] = result["protocolVersion"]
        self.rpc("notifications/initialized", {}, notify=True)

    def rpc(self, method, params, notify=False):
        self.seq += 1
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            message["id"] = self.seq
        request = urllib.request.Request(self.endpoint, json.dumps(message).encode(), self.headers)
        with self.transport.open(request, timeout=25) as response:
            session = response.headers.get("Mcp-Session-Id")
            if session:
                self.headers["Mcp-Session-Id"] = session
            if notify:
                return {}
            result = json.load(response)
        require(result.get("id") == self.seq and "error" not in result and isinstance(result.get("result"), dict),
                "MCP request failed: " + method)
        return result["result"]

    def call(self, name, **kwargs):
        result = self.rpc("tools/call", {"name": name, "arguments": kwargs})
        require(not result.get("isError"), f"MCP tool failed: {name}; check device lock and tool permissions")
        payload = result.get("structuredContent")
        require(isinstance(payload, dict) and not payload.get("blocked"), "unexpected MCP result: " + name)
        return payload


def deploy(client, args, raw):
    required = {"get_app_info", "list_dir", "write_file", "read_file"}
    catalog = client.rpc("tools/list", {})
    require(required <= {t.get("name") for t in catalog["tools"]}, "the connected runner lacks required file tools")
    editor = client.call("get_app_info", bundle_id=args.editor_bundle)
    require(editor.get("bundle_id") == args.editor_bundle, "editor bundle not confirmed")
    info = client.call("get_app_info", bundle_id=FILES_BUNDLE)
    require(info.get("bundle_id") == FILES_BUNDLE, "Files app identity not confirmed")
    root = info.get("group_containers", {}).get(LOCAL_FILES)
    require(isinstance(root, str) and root.startswith("/") and root != "/" and ".." not in PurePosixPath(root).parts,
            "the local Files provider has no visible App Group container")
    parts = ("File Provider Storage", "Downloads")
    path = PurePosixPath(root)
    for part in parts:
        items = client.call("list_dir", path=str(path)).get("entries")
        require(isinstance(items, list) and any(item.get("name") == part and item.get("type") == "directory"
                for item in items), "download directory missing, inaccessible or symlinked")
        path /= part
    existing = client.call("list_dir", path=str(path)).get("entries")
    require(isinstance(existing, list), "could not enumerate the destination")
    display_names = {"autodam-asus-task": "华硕商城", "autodam-storm-task": "影视飓风Club",
                     "autodam-colorful-task": "七彩虹商城", "autodam-yogurt-task": "安慕希"}
    filename = display_names.get(args.id, "checkin-flow") + "-" + uuid.uuid4().hex[:16] + ".json"
    require(not any(item.get("name") == filename for item in existing), "generated destination already exists")
    dest = str(path / filename)
    print("destination=" + dest, flush=True)
    if not args.write:
        print("Read-only preview. Add --write to transfer this flow using a fresh filename.")
        return
    # The server's write_file can replace a path. Use a fresh UUID and never accept a user-supplied filename.
    saved = client.call("write_file", path=dest, content=raw, encoding="utf8")
    size = len(raw.encode())
    require(saved.get("bytes_written") == size, "device did not confirm the full write")
    readback = client.call("read_file", path=dest, max_bytes=size)
    require(readback.get("encoding") == "utf8" and readback.get("content") == raw and not readback.get("truncated"),
            "readback mismatch; do not import")
    print("verified_sha256=" + hashlib.sha256(raw.encode()).hexdigest())
    print("Transferred. Import this file once in the editor, then reopen the saved flow to verify it.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--mcp-url", required=True, help="loopback /mcp URL from the authorized USB forward")
    parser.add_argument("--editor-bundle", default="local.autodam.app", help="confirmed installed editor bundle ID")
    parser.add_argument("--observe-only", action="store_true", help="reject flows that could perform UI actions")
    parser.add_argument("--write", action="store_true", help="transfer one new file; default is read-only discovery")
    args = parser.parse_args()
    flow, _ = select(args.export, args.id, args.observe_only)
    raw = json.dumps(portable_flow(flow), ensure_ascii=False, indent=2) + "\n"
    require(len(raw.encode()) <= 4 * 1024 * 1024, "selected flow exceeds the MCP readback limit; use Files import")
    deploy(Client(args.mcp_url), args, raw)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError, OSError, RecursionError) as exc:
        sys.exit(str(exc))
