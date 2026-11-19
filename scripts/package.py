#!/usr/bin/env python3
"""Install an explicitly selected local AutoDam deb over the discovered USB MCP."""
import argparse
import base64
import hashlib
import json
import shlex
import time
import uuid
from pathlib import Path
from link import Link, save
from flow import require


def checked(link, args, timeout=20):
    reply = link.client.call('run_command', command=shlex.join(args), timeout=timeout)
    require(reply.get('exitCode') == 0, 'device command failed')
    return reply.get('output', '')


def upload(link, path, data):
    # Small text chunks avoid the MCP request limit and preserve Mach-O bytes.
    parts = []
    try:
        for offset in range(0, len(data), 49152):
            part = path + '.part-' + str(offset)
            parts.append(part)
            link.client.call('write_file', path=part, encoding='utf8',
                             content=base64.b64encode(data[offset:offset + 49152]).decode())
        command = shlex.join(['cat', *parts]) + ' | base64 -d > ' + shlex.quote(path)
        reply = link.client.call('run_command', command=command, timeout=20)
        require(reply.get('exitCode') == 0, 'package reconstruction failed')
        digest = hashlib.sha256(data).hexdigest()
        require(checked(link, ['sha256sum', path]).split()[0] == digest, 'upload hash mismatch')
        return digest
    finally:
        if parts:
            checked(link, ['rm', '-f', *parts])


def install(package):
    require(package.is_file() and package.suffix == '.deb', 'select a local deb')
    link = Link()
    try:
        require(not link.control('status')['busy'], 'stop the running task before installing')
        stamp = str(uuid.uuid4())
        backup = link.local / 'backups' / stamp
        save(backup / 'device-version.json', link.info)
        flows = link.control('list')
        save(backup / 'flows.json', flows)
        for flow in flows['flows']:
            save(backup / (flow['id'] + '.json'), link.read(flow['id']))
        # Preserve preferences privately; they can contain account endpoints.
        preferences = '/var/mobile/Library/Preferences/' + link.info['preferences_domain'] + '.plist'
        save(backup / 'preferences.plist', link.read_bytes(preferences))
        device = link.client.call('get_device_info', debug=True)
        helper = device['jailbreak']['helpers']['mcpRoot']['path']
        directory = '/var/mobile/Library/Caches/autodam-release-' + stamp
        checked(link, ['mkdir', '-p', directory])
        remote = directory + '/autodam.deb'
        digest = upload(link, remote, package.read_bytes())
        result = checked(link, [helper, '/usr/bin/dpkg', '-i', remote], timeout=30)
        save(backup / 'install.json', {'package_sha256': digest, 'output': result})
        installed = link.command('--bridge-info')
        return {'version': installed['version'], 'backup_directory': str(backup), 'sha256': digest}
    finally:
        link.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    print(json.dumps(install(parser.parse_args().package), ensure_ascii=False, indent=2))
