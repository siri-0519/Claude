#!/usr/bin/env python3
"""이 레포의 훅 전부. `.claude/settings.json` 이 `hook.py <자리>` 로 부른다. 논리는 `ops/lib/훅.py` 에 있다.

답 끝 자리에서는 transcript_path 를 읽는다 — 레포 여럿 위에서 연 세션의 라우터는 이 낱말로 답 훅을 알아본다.
"""
import sys
from pathlib import Path

뿌리 = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(뿌리 / "ops" / "lib"))
import 훅  # noqa: E402

sys.exit(훅.돌리기(sys.argv[1] if len(sys.argv) > 1 else "stop", 뿌리))
