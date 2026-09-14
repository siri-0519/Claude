"""worklog.md — 무엇을 왜 바꿨나. git log 에서 만들고 커밋하지 않는다(.gitignore).

세션마다 다시 만들어 커밋하는 파일은 세션 둘이 겹치면 반드시 충돌한다 (me 의 안 합쳐진 브랜치 넷이 전부 여기서 충돌했다, 2026-09-13).
"""
from __future__ import annotations

import collections
import datetime
import re
from pathlib import Path

from 공통 import git

파일 = "worklog.md"
날짜별 = 7
줄상한 = 80
건너뜀 = re.compile(r"^(Merge |작업 로그)")


def 만들기(뿌리: Path) -> str:
    out = git(뿌리, "log", "--no-merges", "--date=short", "--format=%ad\t%s", "-n", "400")
    if not out:
        return ""
    오늘 = datetime.date.today()
    잘라 = (오늘 - datetime.timedelta(days=날짜별)).isoformat()
    최근: dict[str, list[str]] = collections.OrderedDict()
    주별: dict[str, list[str]] = collections.OrderedDict()
    for ln in out.split("\n"):
        d, _, msg = ln.partition("\t")
        if 건너뜀.match(msg):
            continue
        if d >= 잘라:
            최근.setdefault(d, []).append("- " + msg)
        else:
            y, m, dd = map(int, d.split("-"))
            a = datetime.date(y, m, dd)
            k = (a - datetime.timedelta(days=a.weekday())).isoformat() + " 주"
            주별.setdefault(k, []).append("- " + msg)
    줄 = ["# 작업 로그", "",
          f"무엇을 왜 바꿨나. git log 에서 `ops build` 와 세션 시작 훅이 만든다. 커밋하지 않는다. "
          f"지난 {날짜별}일은 날짜별로, 그 앞은 주 단위로 둔다.", ""]
    for k, v in 최근.items():
        줄 += [f"## {k}", ""] + v + [""]
    남은 = 줄상한 - sum(len(v) for v in 최근.values())
    for k, v in 주별.items():
        if 남은 <= 0:
            break
        줄 += [f"## {k}", ""] + v[:남은] + [""]
        남은 -= len(v)
    글 = "\n".join(줄).rstrip("\n") + "\n"
    p = 뿌리 / 파일
    if p.is_file() and p.read_text(encoding="utf-8") == 글:
        return ""
    p.write_text(글, encoding="utf-8")
    return f"{sum(len(v) for v in 최근.values())}줄"
