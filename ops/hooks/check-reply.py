#!/usr/bin/env python3
"""답 끝(Stop) 훅 — 내 마지막 답이 규칙에 걸리면 되돌려보낸다. 검사는 ops/lib/reply.py.

레포의 .claude/settings.json 이 이 파일을 Stop 자리에 건다:
    "command": "python3 ${CLAUDE_PROJECT_DIR}/.claude-ops/ops/hooks/check-reply.py"
무엇을 잡을지는 그 레포의 .rules.yml 의 답검사: 칸이 준다. 레포마다 복사본을 두지 않는다.

이 훅 때문에 이미 한 번 되돌아온 상태(stop_hook_active)면 또 막지 않는다 — 무한 반복 방지.
transcript_path 를 읽는다 — 라우터(ops/lib/hooks.py)는 그것으로 답 훅을 알아본다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        d = json.loads(raw)
    except ValueError:
        return 0
    if d.get("stop_hook_active"):
        return 0
    t = d.get("transcript_path") or ""
    if not t or not Path(t).is_file():
        return 0
    import ledger, reply  # noqa: E402
    try:
        뿌리 = ledger.뿌리찾기(Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    except SystemExit:
        return 0                      # 대장이 없는 레포 — 볼 것이 없다
    c = reply.설정(ledger.대장(뿌리))
    답, 물음 = reply.마지막_답과_물음(Path(t))
    if not 답:
        return 0
    문제 = reply.검사(답, 물음, c)
    if not 문제:
        return 0
    print(reply.되돌리는말(문제), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
