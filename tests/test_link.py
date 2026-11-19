import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import link
from flow import portable_flow, select

class LinkTests(unittest.TestCase):
    def test_portable_group_roundtrip_does_not_enable_schedule(self):
        flow = {'id': 'fixture', 'name': 'Fixture', 'group': '小程序',
                'blocks': [{'type': 'verify', 'keyword': 'Fixture'}], 'schedule_enabled': True}
        document = portable_flow(flow)
        self.assertEqual(document['flows'][0]['group'], '小程序')
        self.assertNotIn('schedule_enabled', document['flows'][0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flow.json'
            path.write_text(json.dumps(document))
            self.assertEqual(select(path, 'fixture')[0]['group'], '小程序')
            document['flows'][0]['group'] = '   '
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                select(path, 'fixture')

    def test_discovery_does_not_probe_or_wake_the_ui(self):
        class Client:
            def __init__(self, endpoint): pass
            def rpc(self, method, args):
                return {'tools': [{'name': n} for n in ['get_app_info', 'run_command', 'read_file', 'list_dir']]}
            def call(self, name, **args):
                if name == 'get_app_info':
                    return {'bundle_id': 'local.autodam.app', 'bundle_path': '/fixture/Applications/autodam.app'}
                if name == 'run_command':
                    return {'exitCode': 0, 'output': json.dumps({'protocol': 1, 'state_directory': '/state'})}
                raise AssertionError('must not contact UI during file discovery: '+name)
        with tempfile.TemporaryDirectory() as directory, patch.object(link, 'Client', Client):
            connection = link.Link(endpoint='http://127.0.0.1:1234/mcp', local=directory)
            self.assertEqual(connection.root, '/state')
            connection.close()

    def test_receipts_are_read_without_trusting_parent_overlay_listing(self):
        connection = object.__new__(link.Link)
        connection.root = '/state'
        connection.info = {'capabilities': []}
        class Files:
            def call(self, name, path):
                rows = {'/state/runs/run': [], '/state/checkin-records': ['2026-11-18'],
                        '/state/checkin-records/2026-11-18': ['storm'],
                        '/state/checkin-records/2026-11-18/storm/runs': ['run.json']}
                return {'entries': [{'name': n} for n in rows[path]]}
        connection.client = Files()
        def read(path):
            if path.endswith('status.json'): return b'{"state":"succeeded"}'
            if path.endswith('daemon.log'): return b'fixture'
            return b'{"outcome":"already_signed"}'
        connection.read_bytes = read
        with tempfile.TemporaryDirectory() as directory:
            connection.local = Path(directory)
            result = connection.fetch('run')
            self.assertEqual(result['receipts'], [{'task': 'storm', 'outcome': 'already_signed'}])

    def test_private_files_and_identifiers(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'evidence' / 'page.json'
            link.save(path, {'result': 'unknown'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for name in ('../escape', '/absolute', 'a/b', ''):
            with self.assertRaises(ValueError): link.safe_id(name)

    def test_deploy_observe_only_rejects_before_transport(self):
        connection = object.__new__(link.Link)
        connection.control = lambda *a, **k: self.fail('must not contact device')
        with self.assertRaises(ValueError):
            connection.deploy({'id': 'test', 'name': 'test', 'blocks': [{'type': 'tap', 'keyword': '签到'}]}, 'absent', True)

    def test_stdio_results_and_errors(self):
        class Device:
            def dispatch(self, op, args):
                if op == 'status': return {'state': 'paused'}
                raise ValueError('not supported')
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'autodam', 'arguments': {'operation': 'status'}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'autodam', 'arguments': {'operation': 'bad'}}}]
        out = io.StringIO()
        with patch('sys.stdin', io.StringIO('\n'.join(map(json.dumps, requests)))), patch('sys.stdout', out): link.mcp(Device())
        rows = [json.loads(s) for s in out.getvalue().splitlines()]
        self.assertEqual([r['id'] for r in rows], [1, 2, 3, 4])
        self.assertEqual(rows[2]['result']['structuredContent'], {'state': 'paused'})
        self.assertTrue(rows[3]['result']['isError'])

class DeviceReplyTests(unittest.TestCase):
    def test_ios_action_text_is_success_without_duplicate_tap(self):
        client = object.__new__(link.Client)
        calls = []
        def rpc(method, params):
            calls.append(params)
            return {'content': [{'type': 'text', 'text': 'Tapped screen.'}]}
        client.rpc = rpc
        self.assertEqual(client.call('tap_screen', x=10, y=20), {'message': 'Tapped screen.'})
        self.assertEqual(len(calls), 1)

    def test_blocked_tool_never_becomes_success(self):
        client = object.__new__(link.Client)
        client.rpc = lambda *a, **k: {'structuredContent': {'blocked': True}}
        with self.assertRaises(ValueError): client.call('tap_screen', x=10, y=20)

if __name__ == '__main__': unittest.main()
