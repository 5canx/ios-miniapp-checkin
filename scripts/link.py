#!/usr/bin/env python3
"""USB autodam control and private evidence sync; CLI or MCP stdio server."""
import argparse
import base64
import contextlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import shlex
import socket
import subprocess
import sys
import time
import uuid

from deploy import Client
from flow import FORMAT, inspect_blocks, require, load_json, portable_flow

UI_TOOLS = set('get_screen_info get_frontmost_app get_ui_elements get_element_at_point get_device_info get_app_info list_apps list_running_apps screenshot ocr_screen describe_screen tap_screen long_press swipe_screen press_home press_key input_text launch_app wake_and_home wait_for_element wait_for_disappear'.split())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data if isinstance(data, bytes) else (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())


def safe_id(value):
    require(isinstance(value, str) and value and len(value) < 160 and all(c.isalnum() or c in '-_' for c in value), 'unsafe artifact ID')
    return value


class Link:
    def __init__(self, udid=None, endpoint=None, local=None):
        self.proxy = None
        self.local = Path(local or Path.home() / 'Library/Application Support/autodam-link')
        self.local.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.local, 0o700)
        if not endpoint:
            ids = subprocess.check_output(['idevice_id', '-l'], text=True, timeout=8).split()
            require(udid in ids if udid else len(ids) == 1, 'connect one paired iPhone over USB, or select --udid')
            udid = udid or ids[0]
            with contextlib.closing(socket.socket()) as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            self.proxy = subprocess.Popen(['iproxy', '-l', '-s', '127.0.0.1', '-u', udid, f'{port}:8090'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            endpoint = f'http://127.0.0.1:{port}/mcp'
        try:
            for attempt in range(12):
                try:
                    self.client = Client(endpoint)
                    break
                except OSError as error:
                    if isinstance(error, TimeoutError) or isinstance(getattr(error, 'reason', None), TimeoutError) or attempt == 11:
                        raise
                    time.sleep(.25)
            self.catalog = {t['name']: t for t in self.client.rpc('tools/list', {})['tools']}
            require({'get_app_info', 'run_command', 'read_file', 'list_dir'} <= self.catalog.keys(), 'device MCP lacks control/file tools')
            # File/control discovery must not depend on SpringBoard answering a UI probe.
            # Native execution already checks wake/lock state before touching the screen.
            app = self.client.call('get_app_info', bundle_id='local.autodam.app')
            require(app.get('bundle_id') == 'local.autodam.app', 'autodam app not confirmed')
            app_path = app.get('bundle_path') or app.get('path')
            require(isinstance(app_path, str) and app_path.endswith('/Applications/autodam.app'), 'unrecognized app install layout; inspect get_app_info')
            self.executable = str(PurePosixPath(app_path).parent.parent / 'usr/bin/autodamd')
            self.info = self.command('--bridge-info')
            require(self.info.get('protocol') == 1, 'install autodam 0.3.0 or later control protocol 1')
            self.root = self.info['state_directory']
            require(self.root.startswith('/') and '..' not in PurePosixPath(self.root).parts, 'invalid discovered state directory')
            self.info['app_version'] = app.get('short_version', app.get('version'))
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.proxy:
            self.proxy.terminate()
            try:
                self.proxy.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proxy.kill()
            self.proxy = None

    def command(self, *args):
        cmd = shlex.join([self.executable, *args])
        out = self.client.call('run_command', command=cmd, timeout=12)
        require(out.get('exitCode') == 0, 'autodam command failed: ' + str(out.get('output', ''))[:700])
        return json.loads(out['output'])

    def control(self, op, **args):
        request = {'op': op, 'request_id': args.pop('request_id', str(uuid.uuid4())), **args}
        require(str(uuid.UUID(request['request_id'])).lower() == request['request_id'].lower(), 'invalid control request ID')
        # Persist the ID before sending; transport failure must never create a duplicate run.
        save(self.local / 'requests' / (request['request_id'] + '.json'), request)
        result = self.command('--bridge', json.dumps(request, ensure_ascii=False, separators=(',', ':')))
        require(result.get('ok'), json.dumps(result, ensure_ascii=False))
        return result['result']

    def read_bytes(self, path, maximum=4194304):
        doc = self.client.call('read_file', path=path, binary=True, max_bytes=maximum)
        require(doc.get('encoding') in (None, 'base64'), 'unexpected file encoding')
        data = base64.b64decode(doc['content'], validate=True)
        require(len(data) < maximum, 'file may be truncated; use a bounded artifact')
        return data

    def read(self, flow_id):
        value = self.control('read', flow_id=flow_id)
        save(self.local / 'scripts' / (safe_id(flow_id) + '.json'), {'format': FORMAT, 'version': 1, 'flows': [value['flow']]})
        return value

    def deploy(self, flow, expected_revision, observe_only=False):
        count, checks = inspect_blocks(flow.get('blocks'), observe_only=observe_only)
        require(checks > 0, 'flow needs observable verification')
        require(isinstance(flow.get('name'), str) and flow['name'].strip(), 'missing flow name')
        identifier = safe_id(flow['id'])
        result = self.control('deploy', flow_id=identifier, flow=flow, expected_revision=expected_revision)
        fetched = self.read(identifier)
        require(fetched['revision'] == result['revision'] and fetched['flow']['blocks'] == flow['blocks'], 'deployed readback mismatch')
        save(self.local / 'versions' / identifier / (result['revision'] + '.json'), {'result': result, 'flow': fetched['flow']})
        return {**result, 'steps': count}

    def fetch(self, run_id):
        identifier = safe_id(run_id)
        remote = self.root + '/runs/' + identifier
        dest = self.local / 'runs' / identifier
        status = json.loads(self.read_bytes(remote + '/status.json'))
        save(dest / 'status.json', status)
        if 'run_events' in self.info.get('capabilities', []):
            save(dest / 'events.json', self.control('events', run_id=identifier)['events'])
        entries = {e['name'] for e in self.client.call('list_dir', path=remote)['entries']}
        manifest = json.loads(self.read_bytes(remote + '/pages.json')) if 'pages.json' in entries else {'pages': [], 'edges': [], 'reason': 'no page was captured before termination'}
        save(dest / 'pages.json', manifest)
        images = 0
        for item in manifest['pages']:
            page_id = safe_id(item['id'])
            source = remote + '/' + page_id
            content = json.loads(self.read_bytes(source + '/page.json'))
            save(dest / page_id / 'page.json', content)
            if content.get('screenshot') == 'screen.jpg':
                image = self.read_bytes(source + '/screen.jpg', 8388608)
                save(dest / page_id / 'screen.jpg', image)
                images += 1
        log = self.read_bytes(self.root + '/daemon.log')
        save(dest / 'daemon.log', log)
        if 'login.json' in entries:
            save(dest / 'login.json', self.read_bytes(remote + '/login.json'))
        receipts = []
        for task in ('asus', 'storm', 'yogurt', 'colorful'):
            filename = 'receipt-' + task + '.json'
            if filename in entries:
                data = self.read_bytes(remote + '/' + filename)
                save(dest / filename, data)
                receipts.append({'task': task, 'outcome': json.loads(data).get('outcome')})
        receipt_error = None
        try:
            # RootHide can list a parent overlay without its daemon-created children.
            dates = [] if receipts else self.client.call('list_dir', path=self.root + '/checkin-records')['entries']
        except ValueError as error:
            dates = []
            receipt_error = str(error)
        for date in dates:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date['name']):
                continue
            day = self.root + '/checkin-records/' + date['name']
            for task in self.client.call('list_dir', path=day)['entries']:
                if task['name'] not in ('asus', 'storm', 'yogurt', 'colorful'):
                    continue
                folder = day + '/' + task['name'] + '/runs'
                names = {e['name'] for e in self.client.call('list_dir', path=folder)['entries']}
                if identifier + '.json' in names:
                    data = self.read_bytes(folder + '/' + identifier + '.json')
                    save(dest / ('receipt-' + task['name'] + '.json'), data)
                    receipts.append({'task': task['name'], 'outcome': json.loads(data).get('outcome')})
        result = {'run_id': identifier, 'state': status['state'], 'pages': len(manifest['pages']), 'screenshots': images, 'edges': len(manifest['edges']), 'receipts': receipts, 'local_directory': str(dest), 'private': True}
        if receipt_error:
            result['receipt_read_error'] = receipt_error
        return result

    def sample(self, name='current-page'):
        safe_id(name)
        screen = self.client.call('get_screen_info')
        require(not screen.get('device_state', {}).get('locked'), 'device locked')
        before = self.client.call('ocr_screen', min_confidence=.4)
        page = self.client.call('describe_screen', include_ocr=False, include_screenshot=True, clickable_only=False)
        after = self.client.call('ocr_screen', min_confidence=.4)
        page['ocr_texts'] = after.get('texts', [])
        words = lambda value: [n.get('text') for n in value.get('texts', []) if n.get('rect', {}).get('y', 0) > 45]
        page['capture_stable'] = words(before) == words(after)
        texts = ''.join(n.get('text', '') for n in page.get('ocr_texts', []))
        sensitive = any(s in texts.lower() for s in ('密码', '验证码', '短信验证', 'password', 'passcode'))
        image = page.pop('screenshot', None)
        dest = self.local / 'samples' / (name + '-' + uuid.uuid4().hex[:12])
        if sensitive:
            page = {'withheld': 'credential_screen', 'screen': screen, 'name': name}
        elif image:
            save(dest / 'screen.jpg', base64.b64decode(image, validate=True))
            page['screenshot'] = 'screen.jpg'
        page.update(name=name, captured_at=time.time(), private=True, ax_authoritative=False)
        save(dest / 'page.json', page)
        return {'local_directory': str(dest), 'screenshot': bool(image) and not sensitive, 'withheld': sensitive}

    def watch(self, nonce, seconds=180):
        require(str(uuid.UUID(nonce)).lower() == nonce.lower(), 'invalid request nonce')
        deadline = time.monotonic() + min(seconds, 600)
        while time.monotonic() < deadline:
            if 'request_tracking' in self.info.get('capabilities', []):
                try:
                    runtime = json.loads(self.read_bytes(self.root + '/request-runs/' + nonce + '.json'))
                    state = {'runtime': runtime, 'manual': {'nonce': nonce, 'state': runtime['state']}}
                except ValueError:
                    time.sleep(1)
                    continue
            else:
                state = self.control('status', nonce=nonce)
            manual = state['manual']
            terminal = state['runtime'].get('nonce') == nonce and state['runtime'].get('state') in ('succeeded', 'failed', 'stopped', 'interrupted', 'timed_out')
            if terminal or (manual.get('nonce') == nonce and manual.get('state') in ('succeeded', 'failed')):
                runtime = state['runtime']
                try:
                    evidence = self.fetch(runtime['run_id'])
                except (ValueError, OSError, KeyError) as error:
                    evidence = {'error': str(error), 'run_id': runtime.get('run_id')}
                return {'manual': manual, 'runtime': runtime, 'evidence': evidence}
            time.sleep(2)
        return {'pending': True, 'nonce': nonce, 'status': self.control('status', nonce=nonce)}

    def dispatch(self, op, args):
        if op == 'discover':
            return {**self.info, **self.control('list'), 'device_screen': self.client.call('get_screen_info')}
        if op == 'read':
            return self.read(args['flow_id'])
        if op == 'deploy':
            return self.deploy(**args)
        if op == 'fetch':
            return self.fetch(args['run_id'])
        if op == 'sample':
            return self.sample(**args)
        if op == 'watch':
            return self.watch(**args)
        if op == 'device':
            require(args['name'] in UI_TOOLS and args['name'] in self.catalog, 'unsupported exploration tool')
            if args['name'] == 'screenshot':
                return self.sample('screenshot')
            return self.client.call(args['name'], **args.get('arguments', {}))
        if op == 'tool_schema':
            require(args['name'] in UI_TOOLS and args['name'] in self.catalog, 'unsupported exploration tool')
            return self.catalog[args['name']]
        if op == 'capture':
            submitted = self.control('capture')
            for _ in range(30):
                time.sleep(.5)
                # The previous capture is left intact until this request finishes.
                try:
                    result = json.loads(self.read_bytes(self.root + '/capture-latest.json', 16777216))
                except ValueError:
                    continue
                if result.get('id') == submitted['id']:
                    require(not result.get('error'), result.get('error'))
                    dest = self.local / 'samples' / submitted['id']
                    page = result['page']
                    image = page.pop('screenshot', None)
                    if image: save(dest / 'screen.jpg', base64.b64decode(image, validate=True))
                    save(dest / 'page.json', result)
                    return {'id': submitted['id'], 'local_directory': str(dest), 'screenshot': bool(image)}
            return {**submitted, 'pending': True}
        if op == 'recording_fetch':
            doc = self.control('recorder', command='status')
            identifier = safe_id(doc['session_id'])
            dest = self.local / 'recordings' / identifier
            save(dest / 'recording.json', doc)
            images = 0
            for frame in doc.get('frames', []):
                name = frame.get('preview_name')
                if name and re.fullmatch(r'autodam-frame-\d{3}\.jpg', name):
                    save(dest / name, self.read_bytes(self.root + '/recording-previews/' + identifier + '/' + name))
                    images += 1
            return {'session_id': identifier, 'state': doc['status'], 'frames': len(doc.get('frames', [])), 'previews': images, 'local_directory': str(dest)}
        if op == 'learn':
            from learn import analyze
            recording = self.dispatch('recording_fetch', {})
            document = load_json(Path(recording['local_directory']) / 'recording.json')
            output = self.local / 'learning' / (recording['session_id'] + '-' + uuid.uuid4().hex[:8])
            result = analyze(document, output, **args)
            result['recording_directory'] = recording['local_directory']
            return result
        require(op in ('list', 'status', 'run', 'pause', 'resume', 'stop', 'rollback', 'recorder', 'history', 'events'), 'unknown operation')
        return self.control(op, **args)


def mcp(link):
    schema = {'type': 'object', 'properties': {'operation': {'type': 'string', 'enum': ['discover', 'list', 'read', 'deploy', 'run', 'status', 'watch', 'pause', 'resume', 'stop', 'rollback', 'sample', 'fetch', 'device', 'tool_schema', 'capture', 'recorder', 'recording_fetch', 'learn', 'history', 'events', 'batch', 'batch_start', 'batch_resume', 'batch_stop', 'batch_retry', 'batch_skip']}, 'arguments': {'type': 'object'}}, 'required': ['operation']}
    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            if 'id' not in request:
                continue
            method = request.get('method')
            if method == 'initialize':
                result = {'protocolVersion': request.get('params', {}).get('protocolVersion', '2024-11-05'), 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'autodam-usb', 'version': '0.3.3'}}
            elif method == 'tools/list':
                result = {'tools': [{'name': 'autodam', 'description': 'Control the paired iPhone. Read returns flow/revision; deploy requires flow + expected_revision (absent for new). Run requires flow_id + expected_revision; watch requires nonce. Pause/resume/stop require run_id. Fetch returns private evidence paths. Device accepts an observed iOS MCP UI tool name and arguments.', 'inputSchema': schema}]}
            elif method == 'tools/call':
                require(request['params']['name'] == 'autodam', 'unknown tool')
                p = request['params'].get('arguments', {})
                arguments = dict(p.get('arguments', {}))
                # Keep the stdio server available for pause/stop between bounded watch snapshots.
                if p['operation'] == 'watch':
                    arguments['seconds'] = min(arguments.get('seconds', 5), 5)
                value = link.dispatch(p['operation'], arguments)
                result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'structuredContent': value if isinstance(value, dict) else {'value': value}}
            elif method == 'ping':
                result = {}
            else:
                raise ValueError('unsupported MCP method')
            reply = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        except Exception as error:
            reply = {'jsonrpc': '2.0', 'id': request.get('id'), 'result': {'isError': True, 'content': [{'type': 'text', 'text': str(error)}]}}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--udid')
    parser.add_argument('--mcp-url')
    parser.add_argument('--local', type=Path)
    parser.add_argument('operation', help='discover/list/read/deploy/run/status/watch/pause/resume/stop/rollback/sample/fetch/device/serve')
    parser.add_argument('--args', default='{}', help='JSON operation arguments')
    parser.add_argument('--args-file', type=Path, help='private JSON operation arguments file')
    args = parser.parse_args()
    class LazyLink:
        connection = None
        def dispatch(self, op, params):
            if self.connection is None:
                self.connection = Link(args.udid, args.mcp_url, args.local)
            return self.connection.dispatch(op, params)
        def close(self):
            if self.connection:
                self.connection.close()
    link = LazyLink()
    try:
        if args.operation == 'serve':
            mcp(link)
        else:
            params = load_json(args.args_file) if args.args_file else json.loads(args.args)
            print(json.dumps(link.dispatch(args.operation, params), ensure_ascii=False, indent=2))
    finally:
        link.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
