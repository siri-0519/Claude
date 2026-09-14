"""낱말 거르기 — 답에서 사용자의 말 · 이 세션에 읽은 파일 · 허용 목록 어디에도 없는 낱말을 뽑는다.

사고 때마다 낱말을 목록에 더하는 방식은 그만둔다 (설계 5절). 여기서 뽑은 후보는 판정 모델에 넘기고,
판정 모델이 규칙 6(아는 말만 쓴다)으로 정한다. 기계는 후보만 댄다.

형태소 분석 없이 한다. 한글 명사꼴(두 글자 이상의 한글 덩어리)에서 조사를 떼어 본다. 정확하지 않아도
된다 — 판정 모델이 보는 후보일 뿐이고, 없는 낱말을 잡는 것이 목표라 놓치는 쪽이 낫다.
"""
from __future__ import annotations

import re
from pathlib import Path

한글덩어리 = re.compile(r"[가-힣]{2,}")
조사들 = ("으로써", "에서는", "에게서", "으로는", "에서도", "부터", "까지", "에서", "으로", "에게", "이다",
          "이며", "이고", "이라", "처럼", "보다", "마다", "조차", "마저", "이나", "이든", "과는", "와는",
          "에는", "에도", "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "야", "다")


def 어간후보(w: str) -> set[str]:
    """조사를 뗀 꼴들. 원형도 넣는다."""
    s = {w}
    for 조 in 조사들:
        if len(w) > len(조) + 1 and w.endswith(조):
            s.add(w[: -len(조)])
    return s


def 낱말들(글: str) -> set[str]:
    글 = re.sub(r"```.*?```", " ", 글, flags=re.S)
    글 = re.sub(r"`[^`]*`", " ", 글)
    return set(한글덩어리.findall(글))


def 허용목록(뿌리: Path, c: dict) -> set[str]:
    p = 뿌리 / c["허용낱말"]
    if not p.is_file():
        return set()
    s: set[str] = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln:
            s.update(ln.split())
    return s


def 아는말(뿌리: Path, c: dict, 사용자글: list[str], 읽은파일: set[str]) -> set[str]:
    """사용자의 말 · 읽은 파일 · 허용 목록 · 규칙 파일 · 설정에 나온 낱말 전부 (조사 뗀 꼴 포함)."""
    본문 = "\n".join(사용자글)
    for f in 읽은파일:
        p = Path(f)
        if not p.is_absolute():
            p = 뿌리 / f
        if p.is_file() and p.suffix in (".md", ".txt", ".yml", ".yaml"):
            try:
                본문 += "\n" + p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
    for r in ("ops/rules/판단.md", "ops/rules/기계.yml", ".ops.yml", "CLAUDE.md"):
        p = 뿌리 / r
        if p.is_file():
            본문 += "\n" + p.read_text(encoding="utf-8", errors="ignore")
    s: set[str] = set()
    for w in 낱말들(본문) | 허용목록(뿌리, c):
        s |= 어간후보(w)
    return s


def 후보(답: str, 아는: set[str]) -> list[str]:
    """답에 있는데 아는 말 어디에도 없는 낱말. 조사 뗀 꼴이 하나라도 아는 말이면 안다고 본다."""
    나온것 = []
    for w in sorted(낱말들(답)):
        if 어간후보(w) & 아는:
            continue
        나온것.append(w)
    return 나온것
