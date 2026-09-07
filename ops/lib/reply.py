#!/usr/bin/env python3
"""내 마지막 답을 검사한다 — 지어낸 이름 · 비유 · 상대 날짜 · 짧은 질문에 긴 답.

왜 있는가 (2026-09-07). broadcast 에는 이 검사가 셸 훅(check-plain-words.sh)으로 있었고
me 에는 없었다. 규칙 대장을 세우니 me 의 말하기 규칙 8개 중 7개가 검사 없이 문장만 들어가고,
답변 가시성 목표에 검사가 하나였다. 검사를 레포마다 복사하면 다시 갈라지므로 여기 한 벌을 두고,
무엇을 잡을지(낱말 목록·길이 기준)만 레포의 `.rules.yml` 이 준다.

    답검사:
      지어낸이름: [사다리, 두 음 드릴]        # 대화에서 쓸 자리가 없는 내가 붙인 이름
      비유: [빚, 방벽]                         # 본인이 실제로 지적한 말만 넣는다
      상대날짜: [어제, 아까, 방금]             # 비우면 기본 목록
      긴답: {질문: 150, 답: 3000}              # 질문이 이보다 짧은데 답이 이보다 길면 걸린다

못 잡는 것 — "결론 먼저", "물은 것만 답한다", "확인 가능한 지시". 판단이라 기계로 안 된다.
통과했다고 규칙을 지킨 게 아니다.

한계 — 답이 화면에 나온 뒤에 잡힌다. 본인은 틀린 답을 한 번 보고, 내가 그 자리에서 고친다.
그래서 되돌릴 때 「걸린 자리만 고치라」고 명시한다 — 2026-09-04 에 낱말 하나가 걸렸는데 답 전체를
다시 붙여서 본인이 같은 글을 두 번 읽었다.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

기본_상대날짜 = ["어제", "엊그제", "그제", "내일", "모레", "아까", "방금", "지난번"]
기본_긴답 = {"질문": 150, "답": 3000}
제목괄호 = re.compile(r"「.*?」")   # 「…」 — 곡 제목 안은 안 본다 (「어제보다 오늘 더」 가 잡혔다)


def 설정(d: dict) -> dict:
    c = dict(d.get("답검사") or {})
    c["지어낸이름"] = [str(x) for x in (c.get("지어낸이름") or [])]
    c["비유"] = [str(x) for x in (c.get("비유") or [])]
    c["상대날짜"] = [str(x) for x in (c.get("상대날짜") or 기본_상대날짜)]
    긴 = dict(기본_긴답); 긴.update(c.get("긴답") or {})
    c["긴답"] = {"질문": int(긴["질문"]), "답": int(긴["답"])}
    return c


def 마지막_답과_물음(transcript: Path) -> tuple[str, str]:
    """transcript 의 마지막 assistant 글과 마지막 user 글."""
    답, 물음 = "", ""
    for line in transcript.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        c = (d.get("message") or {}).get("content")
        if isinstance(c, list):
            글 = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
        elif isinstance(c, str):
            글 = c
        else:
            continue
        if d.get("type") == "assistant" and 글.strip():
            답 = 글
        elif d.get("type") == "user" and 글.strip() and "<system-reminder>" not in 글:
            물음 = 글
    return 답, 물음


def 검사(답: str, 물음: str, c: dict, 오늘: date | None = None) -> list[str]:
    """걸린 것을 문장으로. 비면 통과."""
    문제 = []
    for n in c["지어낸이름"]:
        if n and n in 답:
            문제.append(f"지어낸 이름: {n}")
    for w in c["비유"]:
        if w and w in 답:
            문제.append(f"비유: {w} → 실제 동작을 그대로 쓸 것")
    본문 = 제목괄호.sub("", 답)
    걸린 = sorted({w for w in c["상대날짜"] if w and w in 본문})
    if 걸린:
        오늘 = 오늘 or date.today()
        문제.append(f"상대 날짜: {' '.join(걸린)} → 날짜로 쓸 것 (오늘은 {오늘.month}/{오늘.day})")
    a, b = len(물음), len(답)
    if a < c["긴답"]["질문"] and b > c["긴답"]["답"]:
        문제.append(f"질문 {a}자에 답 {b}자다. 결론부터 짧게 다시 쓸 것 — 표·새 절을 만들었으면 지울 것")
    return 문제


def 되돌리는말(문제: list[str]) -> str:
    return ("방금 쓴 답이 규칙에 걸린다.\n" + "".join(f"  {x}\n" for x in 문제)
            + "\n하는 동작을 그대로 써서, 걸린 자리만 고칠 것.\n"
              "답 전체를 다시 붙이지 말 것 — 본인이 같은 글을 두 번 읽는다. 고친 부분만 낸다.")
