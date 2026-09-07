#!/usr/bin/env python3
"""누가 냈나 — 항 단위 표시와 읽을 수 있는 판정 문서.

왜 있는가 (2026-09-07). broadcast 는 판정 없는 항의 총 개수를 `.origin-baseline` 에 두고 그 수가
늘면 막았다. 막힐 때 손쓸 길이 숫자 맞추기뿐이라, 그날 기준을 손으로 올려 통과시키고, 그 길을
막으니 표를 문장으로 눌러 개수를 줄였다. 둘 다 판정과 상관이 없었다. 본인 — *너가 그냥 갯수로
판정하는게 잘못 되었다 이말이야.* 이 파일은 항 하나하나를 본다.

`origin.py` 가 항마다 열쇠를 만들고 사이드카(`<파일>.meta.yml`)의 `항출처` 칸에 **본인의 판정**을
둔다 — GitHub 웹 커밋 서명으로만 들어가고, 내가 나에게 판정을 줄 수 없다. 이 파일은 그 옆에
`항초안` 칸을 둔다. **사실 기록**이고 값은 셋이다.

  클로드   내가 낸 것
  기존     이 검사가 생기기 전부터 있던 것 (한 번 붙이고 다시 붙이지 않는다)
  틀       구분선 · 표 머리 · 갱신 날짜 — 판정할 내용이 아니다

새 항에 판정도 초안도 없으면 커밋을 막고, 그 항을 파일과 이름으로 짚는다. 재포맷으로는 못
빠져나간다 — 문장을 고치면 열쇠가 새로 생겨 다시 걸린다. 「본인이 냈다」 는 항출처로만 들어간다.

판정 문서(`ORIGIN-REVIEW.md`)는 틀을 뺀 항만 절별로 묶어 짧게 낸다 — 기계가 만든 것을 그대로
넘겼더니 본인이 *이런저런 온갖 내용들이 다 뒤죽박죽 섞여있잖아* 라고 했다.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

import origin

내것 = "클로드"
묵은것 = "기존"
틀값 = "틀"
구분선 = re.compile(r"^([-*_])\1{2,}$")
표구분 = re.compile(r"^\|[\s:|-]+\|$")


# ------------------------------------------------------------- 사이드카 ----

def 초안_읽기(p: Path) -> dict:
    return dict(origin._메타(p).get("항초안") or {})


def 초안_쓰기(p: Path, 초안: dict, 살아있는열쇠: set) -> None:
    """항초안만 손댄다. 항·항출처·updated 는 origin 이 적는 칸이라 그대로 둔다."""
    meta = origin._메타(p)
    남길것 = {k: v for k, v in sorted(초안.items()) if k in 살아있는열쇠}
    if 남길것:
        meta["항초안"] = 남길것
    else:
        meta.pop("항초안", None)
    origin.사이드카(p).write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")


def 훑기(뿌리: Path):
    """문서마다 (경로, 판정있음, 초안, 빈항목록, 살아있는열쇠). 초안은 {이름: 값}."""
    for p in origin.세는문서(뿌리):
        초안 = 초안_읽기(p)
        판정있음, 빈것, 열쇠 = 0, [], set()
        for 이름, _절, 본문, 값 in origin.현황(p):
            열쇠.add(이름)
            if 값 != "없다":
                판정있음 += 1
            elif 이름 not in 초안:
                빈것.append((이름, 본문))
        yield p, 판정있음, 초안, 빈것, 열쇠


# ------------------------------------------------------------------ 게이트 ----

def 검사(뿌리: Path, 짚는수: int = 12) -> tuple[int, str]:
    빈전체 = []
    for p, _판정, _초안, 빈것, _열쇠 in 훑기(뿌리):
        빈전체 += [(origin.상대(뿌리, p), 이름, 본문) for 이름, 본문 in 빈것]
    if not 빈전체:
        return 0, "[누가 냈나] 모든 항에 누가 냈는지가 붙어 있다."
    줄 = [f"[누가 냈나] 누가 냈는지가 없는 항 {len(빈전체)}개:"]
    for 파일, 이름, 본문 in 빈전체[:짚는수]:
        줄.append(f"   {파일}  {이름}  {' '.join(본문.split())[:60]}")
    if len(빈전체) > 짚는수:
        줄.append(f"   … 그 밖 {len(빈전체) - 짚는수}개")
    줄.append("  내가 낸 것이면:   ops draft 표시")
    줄.append("  본인이 낸 것이면: ops draft 검토 <파일>  → GitHub 웹에서 채우고 커밋")
    return 1, "\n".join(줄)


def 채우기(뿌리: Path, 값: str) -> int:
    붙인수 = 0
    for p, _판정, 초안, 빈것, 열쇠 in 훑기(뿌리):
        if not 빈것:
            continue
        for 이름, _본문 in 빈것:
            초안[이름] = 값
            붙인수 += 1
        초안_쓰기(p, 초안, 열쇠)
    return 붙인수


def 현황(뿌리: Path) -> str:
    합 = [0, 0, 0, 0, 0]
    줄 = []
    for p, 판정, 초안, 빈것, _열쇠 in 훑기(뿌리):
        셈 = {내것: 0, 묵은것: 0, 틀값: 0}
        for v in 초안.values():
            if str(v) in 셈:
                셈[str(v)] += 1
        합[0] += 판정; 합[1] += 셈[내것]; 합[2] += 셈[묵은것]; 합[3] += 셈[틀값]; 합[4] += len(빈것)
        줄.append(f"  판정 {판정:>4} · 클로드 {셈[내것]:>4} · 기존 {셈[묵은것]:>4} · 틀 {셈[틀값]:>3} · 빈 것 {len(빈것):>4}   "
                  f"{origin.상대(뿌리, p)}")
    머리 = (f"판정 {합[0]}개 · 클로드 {합[1]}개 · 기존 {합[2]}개 · 틀 {합[3]}개 · 누가 냈는지 없는 항 {합[4]}개")
    return "\n".join([머리, *줄])


# ------------------------------------------------------------- 판정 문서 ----

def 표머리들(p: Path) -> set[str]:
    줄 = p.read_text(encoding="utf-8").splitlines()
    return {줄[i].strip() for i in range(len(줄) - 1)
            if 줄[i].startswith("|") and 표구분.match(줄[i + 1].strip())}


def 틀인가(본문: str, 머리: set[str]) -> bool:
    첫줄 = 본문.strip().splitlines()[0].strip() if 본문.strip() else ""
    return bool(구분선.match(첫줄) or 첫줄 in 머리
                or 첫줄.startswith("마지막 갱신:") or 첫줄.startswith("> "))


def 보기좋게(본문: str) -> str:
    한줄 = " ".join(본문.split())
    if 한줄.startswith("|") and 한줄.endswith("|"):
        칸 = [c.strip() for c in 한줄.strip("|").split("|")]
        return " · ".join(c for c in 칸 if c)
    return 한줄


def 검토문서(뿌리: Path, 상대경로: str) -> tuple[int, int]:
    """틀을 사이드카에 적고, 나머지 항으로 ORIGIN-REVIEW.md 를 만든다. (물을 것 수, 새로 틀로 뺀 수)."""
    p = (뿌리 / 상대경로).resolve()
    if not p.is_file():
        raise SystemExit(f"그런 파일이 없다: {상대경로}")
    머리 = 표머리들(p)
    초안 = 초안_읽기(p)
    열쇠, 물을것, 새틀 = set(), [], 0
    for 이름, 절, 본문, 값 in origin.현황(p):
        열쇠.add(이름)
        if 값 != "없다":
            continue
        if 틀인가(본문, 머리):
            if 초안.get(이름) != 틀값:
                초안[이름] = 틀값
                새틀 += 1
            continue
        물을것.append((이름, 절, 본문))
    초안_쓰기(p, 초안, 열쇠)

    이름들 = origin.절이름들(p.read_text(encoding="utf-8"))
    줄 = [f"# 누가 냈나 — {상대경로}", "",
          f"> **물을 것이 {len(물을것)}개다.** 각 항의 `누가:` 줄에 한 낱말만 적으신다.", "",
          "| 값 | 언제 |", "|---|---|",
          "| `작가` | 본인이 확정 · 지시 · 컨셉으로 냈다 |",
          "| `채택` | 클로드가 낸 것을 본인이 채택하거나 확인했다 |",
          "| `봤다` | 본인 표시는 있는데 누가 낸 것인지가 안 적혀 있다 |",
          "| `없다` | 클로드가 적었고 본인은 아직 안 봤다 — 그대로 두면 된다 |", "",
          "**★ GitHub 웹 화면에서 고치고 커밋해야 들어온다.** 로컬 커밋은 받지 않는다 —",
          "저자 메일은 `.git/config` 로 뚫려서 근거가 못 된다 (2026-09-05 실측).", "",
          "**`<!-- 항 -->` 주석과 본문은 그대로 둔다.** 그게 열쇠라 고치면 짝이 끊긴다.", ""]
    이전절 = None
    for i, (이름, 절, 본문) in enumerate(물을것, 1):
        if 절 != 이전절:
            줄 += ["", f"## {이름들.get(절) or f'{절}절'}", ""]
            이전절 = 절
        한줄 = 보기좋게(본문)
        if len(한줄) > 160:
            한줄 = 한줄[:160] + " …"
        줄 += [f"<!-- 항 {이름} -->", f"**{i}.** {한줄}", "", "누가: 없다", ""]
    (뿌리 / origin.검토문서).write_text("\n".join(줄) + "\n", encoding="utf-8")
    return len(물을것), 새틀
