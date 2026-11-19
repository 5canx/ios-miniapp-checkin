#!/usr/bin/env python3
"""Audit previously fetched run artifacts offline; never connect to the phone.

Counts come from tool metrics, not deduplicated page samples. Text, balances,
account fields, commands and device identifiers are deliberately not exported.
"""
import argparse
import json
from pathlib import Path


def audit(directory, run_id):
    steps = []
    for line in (directory / 'daemon.log').read_text().splitlines():
        if '{' not in line:
            continue
        try:
            event = json.loads(line[line.index('{'):])
        except ValueError:
            continue
        if event.get('marker') != run_id or event.get('event') != 'flow_step_completed':
            continue
        metrics = event.get('device_tools', {}).get('ocr_screen', {})
        steps.append({'step': event['step'], 'type': event['type'],
                      'ocr_calls': metrics.get('calls', 0),
                      'ocr_seconds': metrics.get('seconds', 0)})
    manifest = json.loads((directory / 'pages.json').read_text())
    observations = []
    for item in manifest.get('pages', []):
        page = json.loads((directory / item['id'] / 'page.json').read_text())
        observations.append({'page_id': item['id'], 'step': page['step'],
                             'scope': page.get('observation_scope', 'unknown'),
                             'region_points': page.get('observation_region'),
                             'captured_at': page.get('captured_at')})
    return {'run_id': run_id, 'metric_calls': sum(s['ocr_calls'] for s in steps),
            'ocr_seconds': sum(s['ocr_seconds'] for s in steps),
            'unique_observations': len(observations),
            'warning': 'Samples may be deduplicated; this file contains no runtime call stack. Trace routes against the source revision.',
            'steps': steps, 'observations': observations}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, args.run_id), ensure_ascii=False, indent=2))
