#!/usr/bin/env python3
"""Analyze native autodam page recordings locally; never invent physical touch events."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from flow import FORMAT, inspect_blocks, load_json, private_json, require


def words(frame):
    return {n.get('text', '').strip() for key in ('ax', 'ocr') for n in frame.get(key, []) if isinstance(n, dict)} - {''}


def sensitive(frame):
    return any(re.search(r'密码|验证码|安全码|password|passcode|one.time.code', t, re.I) for t in words(frame))


def locators(frame):
    result, seen = [], set()
    for source in ('ax', 'ocr'):
        for node in frame.get(source, []):
            text, rect = node.get('text', '').strip(), node.get('rect_norm')
            if not text or not isinstance(rect, list) or len(rect) != 4 or tuple([text] + rect) in seen:
                continue
            if not all(type(v) in (int, float) and math.isfinite(v) for v in rect):
                continue
            x, y, w, h = rect
            if w <= 0 or h <= 0 or y + h < .05:
                continue
            seen.add(tuple([text] + rect))
            result.append({'source': source, 'text': text, 'match': 'exact',
                           'region': [max(0, x-.015), max(0, y-.015), min(1, x+w+.015), min(1, y+h+.015)],
                           'clickable': node.get('clickable'), 'screen': frame['screen'],
                           'verified': False})
    return result


def login_state(frame):
    text = ' '.join(words(frame))
    if re.search(r'登录/注册|立即登录|请先登录|点击登录|授权登录', text):
        return 'logged_out'
    if re.search(r'申请获取并验证你的手机号|一键绑定手机号码|上次提供', text):
        return 'account_consent'
    if ('华硕会员' in text and '绑定设备' in text) or re.search(r'退出登录|会员ID|用户ID', text):
        return 'logged_in_evidence'
    return 'unconfirmed'


def analyze(recording, out, flow_id='recording-candidate', name='录制生成候选', final_keyword=None):
    require(recording.get('schema') == 'local.autodam.page-recording.v1', 'use the native autodam recording schema')
    require(recording.get('status') != 'recording', 'stop recording before analysis')
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', flow_id), 'invalid candidate flow ID')
    frames = recording.get('frames', [])
    require(isinstance(frames, list) and frames, 'recording has no real captured pages')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not any(out.iterdir()), 'analysis directory must be new; retain the previous analysis')
    annotations = {a['frame']: a for a in recording.get('annotations', []) if isinstance(a, dict) and 'frame' in a}
    pages, transitions, gaps, blocks, coordinates = [], [], [], [], []
    if recording.get('status') != 'stopped':
        gaps.append({'reason': 'recording_interrupted_or_incomplete', 'state': recording.get('status')})
    previous = None
    for index, frame in enumerate(frames, 1):
        require(isinstance(frame.get('screen'), dict) and isinstance(frame.get('at'), (int, float)), 'frame lacks geometry or observation timestamp')
        page_id = f'page-{index:03d}'
        withheld = sensitive(frame)
        candidates = [] if withheld else locators(frame)
        page = {'id': page_id, 'source_frame': frame.get('index', index), 'observed_at': frame['at'],
                'bundle_id': frame.get('bundle_id'), 'screen': frame['screen'], 'locators': candidates,
                'login_state': 'withheld' if withheld else login_state(frame),
                'preview': None if withheld else frame.get('preview_name'), 'withheld': withheld,
                'ax_truncated': frame.get('ax_total', 0) > len(frame.get('ax', [])),
                'ocr_truncated': frame.get('ocr_total', 0) > len(frame.get('ocr', [])),
                'ax_hierarchy': 'not_provided_by_native_recording', 'verified': False}
        pages.append(page)
        if withheld:
            gaps.append({'page': page_id, 'reason': 'credential_page_withheld'})
        if previous:
            transitions.append({'from': previous['id'], 'to': page_id,
                'observation_delta_seconds': max(0, frame['at'] - previous['observed_at']),
                'action': 'unknown', 'actual_touch_timestamp': None,
                'note': 'Page observation interval is not a measured touch or required wait duration.'})
        previous = page
    # Native annotations are operator-entered intentions, not a captured stream of touches.
    for index, edge in enumerate(transitions):
        frame, page = frames[index], pages[index]
        annotation = annotations.get(frame.get('index', index+1), {})
        point = annotation.get('tap_pt')
        if page['withheld'] or not isinstance(point, list) or len(point) != 2:
            gaps.append({'transition': [edge['from'], edge['to']], 'reason': 'no_recorded_action_or_operator_tap'})
            continue
        width, height = frame['screen'].get('width', 0), frame['screen'].get('height', 0)
        if not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (width, height)):
            gaps.append({'page': page['id'], 'reason': 'missing_coordinate_geometry'})
            continue
        if not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v < limit for v, limit in zip(point, (width, height))):
            gaps.append({'page': page['id'], 'reason': 'tap_outside_reference_geometry'})
            continue
        x, y = point[0] / width, point[1] / height
        hits = [l for l in page['locators'] if l['region'][0] <= x <= l['region'][2] and l['region'][1] <= y <= l['region'][3]]
        labels = {l['text'] for l in hits}
        if len(labels) != 1 or frame.get('bundle_id') != frames[index+1].get('bundle_id'):
            gaps.append({'page': page['id'], 'reason': 'ambiguous_tap_or_app_switch_needs_review'})
            continue
        hit = hits[0]
        edge.update(action='operator_annotated_tap', label=hit['text'], tap_pt=point, source='operator_annotation')
        # Verify the entry once; replay annotated coordinates, then verify the business endpoint.
        if index == 0:
            blocks.append({'type': 'verify', 'keyword': hit['text'], 'match': 'exact', 'region': hit['region']})
        block = {'type': 'tap', 'name': f"{page['id']}: {hit['text']}", 'x': point[0], 'y': point[1],
                 'reference_width': width, 'reference_height': height, 'reference_scale': 1}
        blocks.append(block)
        coordinates.append({'page_id': page['id'], 'page_name': hit['text'], 'bundle_id': page['bundle_id'],
            'entry_page': pages[index-1]['id'] if index else None, 'next_page': edge['to'],
            'sequence': index+1, 'screen': frame['screen'], 'coordinate_unit': 'screen_points',
            'orientation': frame['screen'].get('orientation', 'portrait' if height > width else 'landscape'),
            'action': block, 'wait_seconds': None, 'wait_status': 'not_measured',
            'fallback_locator': hit, 'source': 'operator_annotation', 'verified': False})
    first_bundle = frames[0].get('bundle_id')
    if first_bundle and not pages[0]['withheld']:
        blocks.insert(0, {'type': 'launch_app', 'bundle_id': first_bundle})
    last = pages[-1]
    if final_keyword:
        require(final_keyword in words(frames[-1]) and not last['withheld'], 'final assertion must be visible in the real last frame')
        choices = [l for l in last['locators'] if l['text'] == final_keyword]
        require(choices, 'final assertion has no bounded locator')
        blocks.append({'type': 'verify', 'keyword': final_keyword, 'match': 'exact', 'region': choices[0]['region']})
    else:
        gaps.append({'page': last['id'], 'reason': 'final_business_assertion_not_selected'})
    candidate = {'format': FORMAT, 'version': 1, 'flows': [{'id': flow_id, 'name': name,
                 'schedule_enabled': False, 'interval_minutes': 60, 'blocks': blocks}]}
    runnable = bool(final_keyword) and not gaps
    if runnable:
        inspect_blocks(blocks)
    report = {'schema': 'autodam.recording-analysis.v1', 'session_id': recording.get('session_id'),
        'recording_sha256': hashlib.sha256(json.dumps(recording, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'source': 'native_real_device_recording', 'pages': pages, 'transitions': transitions,
        'capabilities': {'page_frames': True, 'ocr': True, 'flat_ax_elements': True, 'screen_video': False,
                         'physical_touches': False, 'physical_swipes': False, 'touch_timestamps': False},
        'missing': gaps, 'candidate_ready_for_device_test': runnable, 'device_tested': False,
        'business_verified': False, 'privacy': 'private_local_only'}
    private_json(out / 'analysis.json', report)
    private_json(out / 'flow-candidate.json', candidate)
    private_json(out / 'coordinates.json', {'schema': 'autodam.coordinate-library.v1',
        'flow_id': flow_id, 'recording_sha256': report['recording_sha256'], 'verified': False, 'steps': coordinates})
    graph = ['flowchart TD']
    for page in pages:
        graph.append(f'  {page["id"].replace("-", "_")}["{page["id"]}: {page["login_state"]}"]')
    for edge in transitions:
        graph.append(f'  {edge["from"].replace("-", "_")} -->|{edge["action"]}| {edge["to"].replace("-", "_")}')
    (out / 'navigation.mmd').write_text('\n'.join(graph)+'\n')
    (out / 'navigation.mmd').chmod(0o600)
    notes = ['# 私有录制学习记录', '', '状态：候选经验；未经过真机回放，不可标记签到成功。', '',
             '原生录制只有页面观察时间，不含真实触摸、滑动或触摸时间戳。页面间隔不能直接转换成脚本等待时间。', '',
             '复用顺序：已验证流程及绑定页面、几何的坐标 → 必要的稳定元素 → 动态数据/结果 OCR → 异常识别。正常固定点击不重新 OCR。', '',
             'coordinates.json 保存标注坐标、页面转移和设备几何。候选仍未验证；等待时间未知，不能把观察间隔当等待时间。首次真机校准后填写已测等待及回执。', '',
             '登录：优先复用会话与 references/login-workflow.md；仅发生变化时重新采样。', '',
             '恢复：缺失动作、未知弹窗、账号验证或页面不匹配时停在当前页；不要重放未确认的签到。', '',
             f'页面数：{len(pages)}；未解决项：{len(gaps)}。详细定位与登录状态变化见 analysis.json。', '',
             '将业务终点选择为实际可见断言，人工标注或 AI 根据已验证规则补齐未知转移；部署候选，实际回放并核对独立业务回执。',
             '公开 Skill 只摘录经回放确认的通用规则。此目录及候选内的文字可能含个人信息，不得直接提交 GitHub。']
    (out / 'learning-notes.md').write_text('\n'.join(notes)+'\n')
    (out / 'learning-notes.md').chmod(0o600)
    return {'local_directory': str(out), 'pages': len(pages), 'transitions': len(transitions),
            'missing_count': len(gaps), 'candidate_ready_for_device_test': runnable,
            'device_tested': False, 'physical_touch_events_available': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--flow-id', default='recording-candidate')
    parser.add_argument('--name', default='录制生成候选')
    parser.add_argument('--final-keyword')
    args = parser.parse_args()
    print(json.dumps(analyze(load_json(args.recording), args.out, args.flow_id, args.name, args.final_keyword), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, TypeError) as error:
        sys.exit(str(error))
