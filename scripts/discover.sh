#!/bin/sh
# Read-only. Invoke on the device, or pass the root of an extracted filesystem to inspect locally.
set -eu
if [ "$#" -gt 1 ]; then echo 'usage: sh discover.sh [mounted-root]' >&2; exit 2; fi
root=${1:-/}
[ -d "$root" ] || { echo 'root is not a directory' >&2; exit 2; }
root=$(CDPATH= cd "$root" && pwd -P)
root=${root%/}
emit() { printf '%s\t%s\n' "$1" "${2#"$root"}"; }
read_state_dir() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import json,sys; v=json.load(open(sys.argv[1])).get("state_directory"); print(v if isinstance(v,str) and v.startswith("/") and not any(ord(c)<32 for c in v) else "")' "$1" 2>/dev/null
    elif command -v plutil >/dev/null 2>&1; then
        plutil -extract state_directory raw -o - "$1" 2>/dev/null
    fi
}
inspect_config() {
    [ -f "$1" ] || return 0
    emit base_config "$1"
    state=$(read_state_dir "$1") || state=
    case "$state" in
        /*) if [ -d "$root$state" ]; then emit state_directory "$root$state"; else printf 'configured_state_directory\t%s\n' "$state"; fi ;;
        *) printf 'state_directory\t%s\n' 'unresolved; inspect state_directory in the listed base config' ;;
    esac
}
file_entry() {
    [ -e "$1" ] || return 0
    case "$1" in
        *.app/Info.plist) emit app_bundle "${1%/Info.plist}" ;;
        */bin/*damd|*/bin/*mamd) emit daemon "$1" ;;
        */etc/*/config.json) inspect_config "$1" ;;
        */LaunchDaemons/*.plist) emit launchd "$1" ;;
    esac
}
inspect_prefix() {
    p=$1
    for app in "$p"/Applications/*; do
        case "${app##*/}" in *[Dd][Aa][Mm]*.app|*[Mm][Aa][Mm]*.app) file_entry "$app/Info.plist" ;; esac
    done
    for cfg in "$p"/etc/autodam/config.json "$p"/etc/automam/config.json; do inspect_config "$cfg"; done
    for item in "$p"/usr/bin/autodamd "$p"/usr/bin/automamd "$p"/Library/LaunchDaemons/*autodam*.plist "$p"/Library/LaunchDaemons/*automam*.plist; do file_entry "$item"; done
}
{
    if [ -z "$root" ] && command -v dpkg-query >/dev/null 2>&1; then
        dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package} ${Version}\n' 2>/dev/null |
        while read -r status pkg version; do
            [ "$status" = ii ] || continue
            case "$pkg" in
                *autodam*|*automam*) printf 'package\t%s %s\n' "$pkg" "$version"
                    dpkg-query -L "$pkg" 2>/dev/null | while IFS= read -r file; do file_entry "$file"; done ;;
                *ios-mcp*) printf 'mcp_package\t%s %s\n' "$pkg" "$version" ;;
            esac
        done
    fi
    inspect_prefix "$root"
    for prefix in "$root"/var/jb "$root"/var/containers/Bundle/Application/.jbroot-*; do
        [ -d "$prefix" ] || continue
        # An absolute symlink in a copied filesystem would lead into the inspecting host.
        if [ -n "$root" ] && [ -L "$prefix" ]; then continue; fi
        inspect_prefix "$prefix"
    done
    for pref in "$root"/var/mobile/Library/Preferences/*autodam*.plist "$root"/var/mobile/Library/Preferences/*automam*.plist; do
        [ -f "$pref" ] || continue
        emit preferences_candidate "$pref"
        if command -v python3 >/dev/null 2>&1; then
            if python3 -c 'import json,plistlib,sys; d=plistlib.load(open(sys.argv[1],"rb")); v=json.loads(d["configuration_json"]); sys.exit(0 if isinstance(v.get("flows"),list) else 1)' "$pref" >/dev/null 2>&1; then
                emit confirmed_flow_preferences "$pref"
            fi
        elif command -v plutil >/dev/null 2>&1 && plutil -extract configuration_json raw -o - "$pref" >/dev/null 2>&1; then
            emit configuration_key_present "$pref"
        fi
    done
} | awk '!seen[$0]++ { print; count++ } END { if (!count) { print "No matching installation found in accessible paths." > "/dev/stderr"; exit 1 } }'
