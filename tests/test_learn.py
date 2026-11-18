import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from learn import analyze


def frame(at, label):
    return {'at': at, 'bundle_id': 'com.example.fixture', 'screen': {'width': 400, 'height': 800},
            'ax': [{'text': label, 'clickable': True, 'rect_norm': [.1, .2, .3, .1]}], 'ocr': []}


class LearningTests(unittest.TestCase):
    def document(self):
        return {'schema': 'local.autodam.page-recording.v1', 'status': 'stopped', 'session_id': 'fixture',
                'frames': [frame(10, '入口'), frame(25, '终点')], 'annotations': []}

    def test_page_interval_never_becomes_invented_touch_or_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(self.document(), directory, final_keyword='终点')
            doc = json.loads((Path(directory) / 'analysis.json').read_text())
            flow = json.loads((Path(directory) / 'flow-candidate.json').read_text())['flows'][0]
            self.assertFalse(result['candidate_ready_for_device_test'])
            self.assertEqual(doc['transitions'][0]['action'], 'unknown')
            self.assertEqual(doc['transitions'][0]['observation_delta_seconds'], 15)
            self.assertFalse(any(b['type'] in ('tap', 'wait') for b in flow['blocks']))

    def test_annotation_creates_bound_coordinates_without_claiming_verified_touches(self):
        doc = self.document();doc['annotations'] = [{'frame': 1, 'tap_pt': [80, 200]}]
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(doc, directory, final_keyword='终点')
            analysis = json.loads((Path(directory) / 'analysis.json').read_text())
            flow = json.loads((Path(directory) / 'flow-candidate.json').read_text())['flows'][0]
            self.assertTrue(result['candidate_ready_for_device_test'])
            self.assertFalse(analysis['business_verified'])
            self.assertFalse(analysis['capabilities']['physical_touches'])
            tap = next(b for b in flow['blocks'] if b['type'] == 'tap')
            self.assertEqual((tap['x'], tap['y']), (80, 200))
            self.assertEqual((tap['reference_width'], tap['reference_height'], tap['reference_scale']), (400, 800, 1))
            self.assertNotIn('keyword', tap);self.assertNotIn('region', tap)
            book = json.loads((Path(directory) / 'coordinates.json').read_text())
            self.assertFalse(book['verified']); self.assertIsNone(book['steps'][0]['wait_seconds'])

    def test_bad_annotated_coordinates_are_not_deployed(self):
        for point in ([float('nan'), 200], [400, 200], [-1, 200], ['80', 200]):
            doc = self.document(); doc['annotations'] = [{'frame': 1, 'tap_pt': point}]
            with tempfile.TemporaryDirectory() as directory:
                result = analyze(doc, directory, final_keyword='终点')
                self.assertFalse(result['candidate_ready_for_device_test'])

    def test_credentials_and_unobserved_final_assertion_are_rejected(self):
        doc = self.document();doc['frames'][1] = frame(25, '短信验证码')
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(doc, directory)
            analysis = json.loads((Path(directory) / 'analysis.json').read_text())
            self.assertTrue(analysis['pages'][1]['withheld'])
            self.assertEqual(analysis['pages'][1]['locators'], [])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): analyze(doc, directory, final_keyword='签到成功')

    def test_interrupted_recording_stays_incomplete_even_with_a_visible_endpoint(self):
        doc = self.document();doc['frames'] = [frame(10, '终点')];doc['status'] = 'interrupted'
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(doc, directory, final_keyword='终点')
            self.assertFalse(result['candidate_ready_for_device_test'])


if __name__ == '__main__': unittest.main()
