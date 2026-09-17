"""목표 — 목적 다섯(규칙 준수 · 맥락 유지 · 토큰 절약 · 정보 추적성 · 좋은 설명)이 지켜지는지 기록에서 세고, 경보를 낸다 (설계 1절, 2026-09-17).

    ops 목표              세는 것 표 + 시뮬 마지막 판 + 경보
    ops 시뮬 --기록 <파일>  ops/test/시뮬.py 의 결과(.meta/시뮬/*.jsonl)를 memory/시뮬.jsonl 에 한 줄씩 남긴다
    세션 시작 훅            경보가 있으면 한 줄 넣는다 (훅-글 A1)

문제가 생기면 기계가 바로 알고 빨리 고칠 수 있어야 한다는 사용자의 2026-09-17 요구에서 왔다. 경보 다섯: 판정 시간이 제한에 가까움 ·
답 끝 판정 모델이 대부분의 답을 고치라고 함 · 규칙별 위반이 지난 주의 두 배 · 목적이나 시험이 빠진 규칙 · 어긋남 목록 · 시뮬에서 모델 둘 이상이 실패한 시나리오.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from 공통 import 기록읽기, 오늘, 설정

시뮬기록파일 = "memory/시뮬.jsonl"


def _주(날) -> tuple | None:
    try:
        return date.fromisoformat(str(날)[:10]).isocalendar()[:2]
    except ValueError:
        return None


def 세기(뿌리: Path, c: dict | None = None) -> tuple[list[tuple[str, str, str, str]], dict]:
    """목적마다 세는 것을 (이번 주, 지난 주) 로. 둘째 값은 경보가 쓰는 중간값."""
    import 판정
    c = c or 설정(뿌리)
    오늘날 = date.fromisoformat(오늘())
    이번주, 지난주 = 오늘날.isocalendar()[:2], (오늘날 - timedelta(days=7)).isocalendar()[:2]
    횟수 = 기록읽기(뿌리, "횟수"); 판정들 = 기록읽기(뿌리, "판정"); 문맥 = 기록읽기(뿌리, "문맥")

    def 세기(줄들, 날열쇠, 조건):
        n: Counter = Counter()
        for d in 줄들:
            w = _주(d.get(날열쇠))
            if w and 조건(d):
                n[w] += 1
        return n[이번주], n[지난주]

    def 합(줄들, 날열쇠, 조건):
        n: Counter = Counter()
        for d in 줄들:
            w = _주(d.get(날열쇠))
            if w and 조건(d):
                n[w] += int(d.get("바이트") or 0)
        return n[이번주], n[지난주]

    def 번호(d):
        return 판정.이름맞추기(뿌리, str(d.get("규칙", "")))

    줄: list[tuple[str, str, str, str]] = []
    판정번, 판정지난 = 세기(판정들, "때", lambda d: d.get("자리") == "답")
    걸린번, 걸린지난 = 세기(판정들, "때", lambda d: d.get("자리") == "답" and int(d.get("어긴") or 0) > 0)
    줄.append(("규칙 준수", "답 끝 판정을 시킨 번 가운데 판정 모델이 고치라고 한 번", f"{걸린번}/{판정번}", f"{걸린지난}/{판정지난}"))
    for 이름, 조건 in [("판정 모델이 건 횟수(전체)", lambda d: d.get("누가") == "판정"), ("기계가 막은 횟수", lambda d: d.get("누가") == "기계"),
                     ("본인이 고치라고 한 횟수", lambda d: d.get("누가") == "본인")]:
        a, b = 세기(횟수, "날", 조건); 줄.append(("규칙 준수", 이름, str(a), str(b)))
    a, b = 세기(횟수, "날", lambda d: d.get("누가") == "본인" and "맥락" in str(d.get("규칙", "")))
    줄.append(("맥락 유지", "본인이 「바뀌었다 · 맥락」으로 고치라고 한 횟수", str(a), str(b)))
    시작 = [d for d in 문맥 if d.get("자리") == "session_start"]
    (sa, sb), (na, nb) = 합(시작, "때", lambda d: True), 세기(시작, "때", lambda d: True)
    줄.append(("맥락 유지 · 토큰 절약", "세션 시작에 들어간 글의 바이트 합 / 번", f"{sa}/{na}", f"{sb}/{nb}"))
    a, b = 합(문맥, "때", lambda d: d.get("어떻게") == "막기"); 줄.append(("토큰 절약", "훅이 막으며 보낸 글의 바이트 합", str(a), str(b)))
    a, b = 합(문맥, "때", lambda d: d.get("자리") == "읽기"); 줄.append(("토큰 절약", "Read 한 파일의 바이트 합", str(a), str(b)))
    import 훅
    어긋남수, _ = 훅.어긋남개수(뿌리, c, 다시=False)
    줄.append(("정보 추적성", "어긋남 목록의 항 수(지금)", str(어긋남수), "-"))
    a, b = 세기(횟수, "날", lambda d: d.get("누가") == "기계" and str(d.get("규칙")) == "표시"); 줄.append(("정보 추적성", "기계가 표시 없는 줄을 막은 횟수", str(a), str(b)))
    a, b = 세기(횟수, "날", lambda d: d.get("누가") == "본인" and "어긋남" in str(d.get("규칙", ""))); 줄.append(("정보 추적성", "본인이 「어긋남」으로 찾아낸 횟수", str(a), str(b)))
    a, b = 세기(횟수, "날", lambda d: d.get("누가") == "판정" and 번호(d) in ("4", "5", "6", "9")); 줄.append(("좋은 설명", "판정이 규칙 4 · 5 · 6 · 9 로 건 횟수", str(a), str(b)))
    a, b = 세기(횟수, "날", lambda d: d.get("누가") == "기계" and str(d.get("규칙")) == "상대날짜"); 줄.append(("좋은 설명", "기계가 상대 날짜로 막은 횟수", str(a), str(b)))
    a, b = 세기(횟수, "날", lambda d: d.get("누가") == "본인" and "설명" in str(d.get("규칙", ""))); 줄.append(("좋은 설명", "본인이 「설명」으로 고치라고 한 횟수", str(a), str(b)))
    규칙별: dict = defaultdict(Counter)
    for d in 횟수:
        w = _주(d.get("날"))
        if w in (이번주, 지난주):
            규칙별[str(d.get("규칙"))][w] += 1
    초들 = [float(d["초"]) for d in 판정들 if d.get("초") and _주(d.get("때")) == 이번주]
    return 줄, {"판정번": 판정번, "걸린번": 걸린번, "초들": 초들, "규칙별": 규칙별, "이번주": 이번주, "지난주": 지난주, "어긋남수": 어긋남수}


def 시뮬요약(뿌리: Path) -> dict | None:
    """memory/시뮬.jsonl 의 마지막 판(같은 날 · 같은 판 이름) — 통과 수 · 전체 · 모델 둘 이상이 실패한 시나리오."""
    p = 뿌리 / 시뮬기록파일
    if not p.is_file():
        return None
    줄들 = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            줄들.append(json.loads(ln))
        except ValueError:
            pass
    if not 줄들:
        return None
    마지막 = 줄들[-1]
    판 = [d for d in 줄들 if d.get("날") == 마지막.get("날") and d.get("판") == 마지막.get("판")]
    실패모델: dict = defaultdict(list)
    for d in 판:
        if not d.get("통과"):
            실패모델[d["시나리오"]].append(d["모델"])
    둘이상 = {s: ms for s, ms in 실패모델.items() if len(ms) >= 2}
    return {"날": 마지막.get("날"), "판": 마지막.get("판"), "통과": sum(1 for d in 판 if d.get("통과")), "전체": len(판),
            "실패": dict(실패모델), "둘이상": 둘이상}


def 시뮬기록(뿌리: Path, 결과파일: Path, 판이름: str = "") -> int:
    """시뮬 결과 파일의 줄마다 요약 한 줄을 memory/시뮬.jsonl 에 붙인다. 붙인 줄 수."""
    p = 뿌리 / 시뮬기록파일
    p.parent.mkdir(exist_ok=True)
    n = 0
    with p.open("a", encoding="utf-8") as f:
        for ln in 결과파일.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            실패 = [k for k, v in (o.get("검사") or {}).items() if v is False]
            f.write(json.dumps({"날": 오늘(), "판": 판이름 or 결과파일.stem, "시나리오": o.get("시나리오"), "목표": o.get("목표"), "모델": o.get("모델"),
                                "통과": bool(o.get("통과")), "초": o.get("초"), "실패": 실패}, ensure_ascii=False) + "\n")
            n += 1
    return n


def 경보(뿌리: Path, c: dict | None = None, 중간: dict | None = None) -> list[str]:
    import 기계
    c = c or 설정(뿌리)
    if 중간 is None:
        _, 중간 = 세기(뿌리, c)
    나온것: list[str] = []
    초들 = 중간["초들"]
    if 초들 and max(초들) > int(c["판정"]["시간"]) * 0.8:
        나온것.append(f"판정 시간이 제한({c['판정']['시간']}초)의 8할을 넘은 적이 있다 — 이번 주 최대 {max(초들):.0f}초, 평균 {sum(초들)/len(초들):.0f}초. 넘으면 답 끝 검사가 통째로 건너뛰어진다")
    if 중간["판정번"] and 중간["걸린번"] / 중간["판정번"] >= 0.7:
        나온것.append(f"답 끝 판정을 시킨 {중간['판정번']}번 가운데 {중간['걸린번']}번은 판정 모델이 답을 고치라고 했다 — 규칙이 안 지켜지거나 판정이 지나치다. `ops 횟수` 로 규칙별로 본다")
    for 규칙, cc in 중간["규칙별"].items():
        if cc[중간["이번주"]] >= 5 and cc[중간["지난주"]] and cc[중간["이번주"]] >= 2 * cc[중간["지난주"]]:
            나온것.append(f"규칙 「{규칙}」 이 이번 주 {cc[중간['이번주']]}번으로 지난 주({cc[중간['지난주']]}번)의 두 배를 넘었다")
    빠진 = 기계.규칙대장(뿌리, c)
    if 빠진:
        나온것.append(f"목적이나 시험이 빠진 규칙이 {len(빠진)}개다 — `ops rules` 로 본다")
    if 중간["어긋남수"]:
        나온것.append(f"어긋남 목록에 {중간['어긋남수']}개가 있다 — `ops 어긋남`")
    s = 시뮬요약(뿌리)
    if s and s["둘이상"]:
        나온것.append("시뮬 마지막 판(" + str(s["날"]) + ")에서 모델 둘 이상이 실패한 시나리오: " + " · ".join(f"{k}({' · '.join(v)})" for k, v in s["둘이상"].items()) + " — 규칙이나 글을 고친다")
    return 나온것


def 보이기(뿌리: Path, c: dict | None = None) -> str:
    c = c or 설정(뿌리)
    줄, 중간 = 세기(뿌리, c)
    나온것 = ["목적 다섯이 지켜지는지 기록에서 센 것 (memory/횟수.jsonl · 판정.jsonl · 문맥.jsonl · 어긋남 목록). 무엇을 세나는 설계 1절.", "",
            "| 목적 | 무엇을 세나 | 이번 주 | 지난 주 |", "|---|---|---|---|"]
    나온것 += [f"| {a} | {b} | {x} | {y} |" for a, b, x, y in 줄]
    s = 시뮬요약(뿌리)
    if s:
        나온것.append(f"\n실제로 돌린 시뮬(ops/test/시뮬.py)의 마지막 판 {s['날']} 「{s['판']}」: {s['통과']}/{s['전체']} 통과." +
                   (" 실패: " + " · ".join(f"{k}({' · '.join(v)})" for k, v in s["실패"].items()) if s["실패"] else " 실패 없음."))
    else:
        나온것.append("\n실제로 돌린 시뮬의 기록(memory/시뮬.jsonl)이 없다 — `python3 ops/test/시뮬.py` 뒤에 `ops 시뮬 --기록 <결과 파일>`.")
    경보들 = 경보(뿌리, c, 중간)
    나온것.append("\n경보:\n" + "\n".join("- " + x for x in 경보들) if 경보들 else "\n경보 없음")
    return "\n".join(나온것)
