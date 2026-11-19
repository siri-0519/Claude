# 목표 모드 0.12.0 「새로 만들기 전에 먼저 묻기」가 지켜지는지 기록으로 센다.
# 어느 세션에서든 돌릴 수 있다: python -I ask-first-check.py [기준 시각(UTC), 기본 2026-11-19T06:17 = 0.12.0 적용]
#
# 읽는 곳
#   ~/.claude/goal-pane/기록/*.jsonl  — 의도마다 가정 · 확인 질문, 가정에 누른 ✓ · ✗
#   ~/.claude/projects/**/*.jsonl     — 세션 대화 원문(새 Artifact를 발행한 순간)
#
# 세는 것
#   묻는 비율: 의도 가운데 확인 질문이 적힌 비율(기준 시각 전후)
#   ✗ 수: 가정에 틀렸다고 표시한 수(기준 시각 전후)
#   새 Artifact: url 없이 발행해 버전 1이 나온 순간마다, 그 턴이나 바로 앞 턴에 확인 질문이 있었는지
#
# 자동으로 못 하는 것: 사용자가 만들라고 직접 말한 경우(「표로 만들어」)는 물을 필요가 없다.
# 그래서 새 Artifact 목록은 후보이고, 줄마다 요청을 읽어 「물었어야 했는가」를 따로 판정한다.
# 갈라져 나온(포크) 세션은 같은 원문을 가지므로 같은 시각 · 같은 요청은 한 번만 센다.
import glob
import json
import os
import sys

CUT = sys.argv[1] if len(sys.argv) > 1 else '2026-11-19T06:17'
SINCE = '2026-11-12'
HOME = os.path.expanduser('~')
GP = os.path.join(HOME, '.claude', 'goal-pane', '기록')
PROJECTS = os.path.join(HOME, '.claude', 'projects')


def goal_pane_counts():
    pre, post = [0, 0], [0, 0]
    wrong = [0, 0]
    for f in glob.glob(os.path.join(GP, '*.jsonl')):
        for line in open(f, encoding='utf-8'):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            after = r.get('at', '') >= CUT
            if r.get('kind') == '가정 표시':
                wrong[after] += len(r.get('wrong') or [])
                continue
            if 'intent' not in r:
                continue
            b = post if after else pre
            b[0] += 1
            b[1] += 1 if (r.get('question') or '').strip() else 0
    return pre, post, wrong


def user_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list) and not any(isinstance(x, dict) and x.get('type') == 'tool_result' for x in c):
        return ''.join(x.get('text', '') for x in c if isinstance(x, dict))
    return None


def new_artifacts():
    events = {}
    for f in glob.glob(os.path.join(PROJECTS, '**', '*.jsonl'), recursive=True):
        if 'subagents' in f:
            continue
        sid = os.path.basename(f)[:8]
        turn_q = prev_q = False
        prompt = ''
        publish_ids = set()
        for line in open(f, encoding='utf-8', errors='replace'):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get('isSidechain'):
                continue
            ts = r.get('timestamp', '')
            if ts and ts < SINCE:
                continue
            m = r.get('message') if isinstance(r.get('message'), dict) else {}
            c = m.get('content')
            if r.get('type') == 'user':
                txt = user_text(c)
                if txt is not None:
                    if txt and not txt.startswith('<') and not txt.startswith('[Request interrupted'):
                        prev_q, turn_q, prompt = turn_q, False, txt[:60].replace('\n', ' ')
                    continue
                for x in c or []:
                    if isinstance(x, dict) and x.get('type') == 'tool_result' and x.get('tool_use_id') in publish_ids:
                        s = json.dumps(x.get('content'), ensure_ascii=False)
                        if '(Version 1,' in s:
                            key = (ts[:16], prompt)
                            if key not in events:
                                events[key] = (ts[:16], sid, turn_q, prev_q, prompt)
            elif r.get('type') == 'assistant' and isinstance(c, list):
                for x in c:
                    if not isinstance(x, dict) or x.get('type') != 'tool_use':
                        continue
                    inp = x.get('input') or {}
                    if x.get('name', '').endswith('set_goal') and (inp.get('question') or '').strip():
                        turn_q = True
                    if x.get('name') == 'Artifact' and inp.get('action', 'publish') == 'publish' and not inp.get('url') and not inp.get('asset'):
                        publish_ids.add(x.get('id'))
    return sorted(events.values())


def main():
    pre, post, wrong = goal_pane_counts()
    pct = lambda a: f'{a[1] / a[0]:.0%}' if a[0] else '-'
    print(f'기준 시각(UTC): {CUT}')
    print(f'[묻는 비율] 전 {pre[0]}건 중 {pre[1]}건({pct(pre)}) | 뒤 {post[0]}건 중 {post[1]}건({pct(post)})')
    print(f'[✗ 수] 전 {wrong[0]}개 | 뒤 {wrong[1]}개')
    ev = new_artifacts()
    for label, part in (('전', [e for e in ev if e[0] < CUT[:16]]), ('뒤', [e for e in ev if e[0] >= CUT[:16]])):
        asked = sum(1 for e in part if e[2] or e[3])
        print(f'[새 Artifact {label}] {len(part)}개 중 그 턴이나 앞 턴에 확인 질문이 있던 것 {asked}개')
        for e in part:
            q = ('이번 턴' if e[2] else '') + (' 앞 턴' if e[3] else '')
            print(f'  {e[0]} {e[1]} 질문: {q.strip() or "없음"} | 요청: {e[4]}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
