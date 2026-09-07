#!/usr/bin/env python3
"""규칙 대장 — 규칙이 문장이 아니라 데이터고, 규칙마다 목표와 검사가 붙어 있다.

왜 있는가 (2026-09-07). me 와 broadcast 는 규칙을 `.claude/hooks/rules.md` 산문으로 두고
훅이 매 요청 통째로 붙여넣었다. 검사가 붙은 규칙과 안 붙은 규칙이 구분되지 않았고, 규칙을
왜 두는지(어느 목표를 지키려는지)도 어디에도 없었다. 그날 구조 목표 다섯을 그 산문 맨 위에
한 줄 더 얹었는데, 본인이 지적했다 — *그걸 왜 훅 규칙 맨 위에 박아? 구조적으로 지켜지는
방법으로 만들어야지. 그냥 한 줄 추가한다고 그게 되겠어?* 그 지적이 이 파일이다.

레포마다 `.rules.yml` 하나가 원본이다. 거기서 두 가지가 나온다.

  1. 매 요청 문맥에 들어가는 규칙 파일 (`ops ledger build` 가 만든다 — 손으로 고치면 게이트가 막는다)
  2. 커밋 게이트 (`ops ledger 검사`) — 목표 없는 규칙 · 배선 안 된 훅을 가리키는 규칙 ·
     손으로 고친 생성 파일을 막고, 검사 없는 규칙은 이름으로 세어 보인다

규칙 하나의 모양:

    - 번호: 3
      문장: "확정으로 적으려면 decisions.md 에 그 행이 있어야 한다. 없으면 제안이다"
      목표: [1, 2]              # 대장 머리의 목표 번호. 비면 커밋이 막힌다
      출처: 본인                # 본인 · 본인목표 · 함께 · 내가 · 모름
      날짜: 2026-08-26
      거는곳:
        - {자리: 커밋, 이름: "decisions.py 검사"}   # .githooks/pre-commit 이 그 명령을 부르는가
        - {자리: 훅, 이름: read-before-answer.py}   # 훅 파일이 있고 settings.json 에 배선됐는가
        - {자리: 푸시, 이름: pre-push}              # .githooks/pre-push 가 있는가
        - {자리: 커밋메시지}                         # .githooks/commit-msg 가 있는가
        - {자리: 넣기}                               # 검사 없음 — 문장만 매 요청 들어간다

「본인목표」 는 creation 레포의 대장이 정한 뜻 그대로다 — 본인이 어떤 결과가 나와야 하는지를
내고 내가 방법을 설계한 규칙. 지키고 있는데도 원한 결과가 안 나오면 규칙이 틀린 것이다.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import yaml

설정파일 = ".rules.yml"
자리들 = ("훅", "커밋", "푸시", "커밋메시지", "넣기")
출처들 = ("본인", "본인목표", "함께", "내가", "모름")
생성표지 = "<!-- 생성된 파일 — 고칠 곳은 .rules.yml"


# ------------------------------------------------------------ 레포와 설정 ----

def 뿌리찾기(p: Path) -> Path:
    p = p.resolve()
    for d in [p if p.is_dir() else p.parent, *p.parents]:
        if (d / 설정파일).is_file():
            return d
    raise SystemExit(f"{설정파일} 을 여기서도 위에서도 못 찾았다. 규칙 대장이 없는 레포다.")


def 대장(뿌리: Path) -> dict:
    d = yaml.safe_load((뿌리 / 설정파일).read_text(encoding="utf-8")) or {}
    d.setdefault("넣는곳", ".claude/hooks/rules.md")
    d.setdefault("훅설정", ".claude/settings.json")
    d.setdefault("훅자리", ".claude/hooks")
    d.setdefault("게이트", ".githooks/pre-commit")
    d.setdefault("푸시게이트", ".githooks/pre-push")
    d.setdefault("메시지게이트", ".githooks/commit-msg")
    d.setdefault("목표", {})
    d.setdefault("절", [])
    d["목표"] = {int(k): str(v) for k, v in (d["목표"] or {}).items()}
    return d


def 규칙들(d: dict):
    """(절번호, 절, 규칙) 을 순서대로. 규칙 id 는 「절번호-번호」 다."""
    for i, 절 in enumerate(d["절"], 1):
        for r in 절.get("규칙") or []:
            yield i, 절, r


def 규칙id(절번호: int, r: dict) -> str:
    return f"{절번호}-{r.get('번호', '?')}"


# ------------------------------------------------------------------ 배선 ----

def 배선된훅(뿌리: Path, d: dict) -> set[str]:
    """settings.json 의 hooks 에 command 로 적힌 훅 파일 이름들."""
    p = 뿌리 / d["훅설정"]
    if not p.is_file():
        return set()
    import json
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return set()
    나온것 = set()
    for arr in (s.get("hooks") or {}).values():
        for g in arr or []:
            for h in g.get("hooks") or []:
                cmd = str(h.get("command", ""))
                for m in re.finditer(r"([\w.-]+\.(?:sh|py))\b", cmd):
                    나온것.add(m.group(1))
    return 나온것


def _파일글(뿌리: Path, 상대: str) -> str:
    p = 뿌리 / 상대
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def 거는곳검사(뿌리: Path, d: dict, 절번호: int, r: dict) -> list[str]:
    """이 규칙의 거는곳이 실제로 있는지. 막을 것을 문장으로 돌려준다."""
    문제 = []
    배선 = 배선된훅(뿌리, d)
    게이트글 = _파일글(뿌리, d["게이트"])
    푸시글 = _파일글(뿌리, d["푸시게이트"])
    for e in r.get("거는곳") or []:
        자리 = str(e.get("자리", ""))
        이름 = str(e.get("이름", "")).strip()
        if 자리 not in 자리들:
            문제.append(f"자리 「{자리}」 는 없다 — {' · '.join(자리들)} 중 하나")
            continue
        if 자리 == "넣기":
            continue
        if 자리 == "훅":
            if not (뿌리 / d["훅자리"] / 이름).is_file():
                문제.append(f"훅 파일이 없다 — {d['훅자리']}/{이름}")
            elif 이름 not in 배선:
                문제.append(f"훅이 {d['훅설정']} 에 배선돼 있지 않다 — {이름}")
        elif 자리 == "커밋":
            if not 게이트글:
                문제.append(f"커밋 게이트 파일이 없다 — {d['게이트']}")
            elif 이름 and 이름 not in 게이트글:
                문제.append(f"커밋 게이트가 그 명령을 부르지 않는다 — {이름}")
        elif 자리 == "푸시":
            if not 푸시글:
                문제.append(f"푸시 게이트 파일이 없다 — {d['푸시게이트']}")
            elif 이름 and 이름 not in 푸시글 and 이름 != Path(d["푸시게이트"]).name:
                문제.append(f"푸시 게이트가 그 이름을 담고 있지 않다 — {이름}")
        elif 자리 == "커밋메시지":
            if not (뿌리 / d["메시지게이트"]).is_file():
                문제.append(f"커밋 메시지 게이트 파일이 없다 — {d['메시지게이트']}")
    return 문제


def 검사있나(r: dict) -> bool:
    return any(str(e.get("자리")) != "넣기" for e in (r.get("거는곳") or []))


# ------------------------------------------------------------------ 생성 ----

def 거는곳표시(r: dict) -> str:
    """규칙 줄 끝에 붙는 짧은 표시. 매 요청 들어가므로 짧게 둔다."""
    목표 = "·".join(str(n) for n in (r.get("목표") or []))
    검사 = [f"{e['자리']} {e.get('이름', '')}".strip() for e in (r.get("거는곳") or [])
            if str(e.get("자리")) != "넣기"]
    안 = f"목표 {목표}" if 목표 else "목표 없음"
    if 검사:
        안 += " · " + " · ".join(검사)
    return f"⟨{안}⟩"


def 만들기(뿌리: Path, d: dict) -> str:
    """넣는곳 파일의 전체 글. 첫 `---` 위는 사람용 머리고, speak-rules.sh 는 그 아래만 넣는다."""
    out = io.StringIO()
    w = out.write
    w("# 규칙 — 매 요청마다 훅이 넣는다\n\n")
    w(f"{생성표지} · `python3 .claude-ops/ops/bin/ops ledger build` -->\n")
    w(f"원본은 `{설정파일}` 이고 이 파일은 거기서 만든다. 여기를 손으로 고치면 커밋 게이트가 막는다.\n")
    w("`.claude/hooks/speak-rules.sh` 가 아래 `---` 밑을 매 요청 넣는다.\n\n---\n\n")
    if d["목표"]:
        w("## 목표 — 규칙마다 어느 목표를 지키는지 ⟨ ⟩ 에 붙어 있다\n\n")
        w("| | |\n|---|---|\n")
        for n, t in sorted(d["목표"].items()):
            w(f"| **{n}** | {t} |\n")
        w("\n")
    if d.get("머리"):
        w(str(d["머리"]).strip() + "\n\n")
    for i, 절 in enumerate(d["절"], 1):
        w(f"## {절.get('제목', f'{i}절')}\n\n")
        if 절.get("머리"):
            w(str(절["머리"]).strip() + "\n\n")
        for r in 절.get("규칙") or []:
            문장 = str(r.get("문장", "")).strip()
            w(f"- {문장} {거는곳표시(r)}\n")
        w("\n")
    return out.getvalue().rstrip() + "\n"


def build(뿌리: Path, 쓰기: bool = True) -> tuple[Path, bool]:
    d = 대장(뿌리)
    글 = 만들기(뿌리, d)
    p = 뿌리 / d["넣는곳"]
    바뀜 = (not p.is_file()) or p.read_text(encoding="utf-8") != 글
    if 쓰기 and 바뀜:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(글, encoding="utf-8")
    return p, 바뀜


# ------------------------------------------------------------------ 검사 ----

def 검사(뿌리: Path) -> tuple[list[str], list[str]]:
    """(막는 것, 알리는 것). 막는 것이 하나라도 있으면 커밋이 안 된다."""
    d = 대장(뿌리)
    막음, 알림 = [], []
    if not d["목표"]:
        막음.append("대장에 목표가 없다 — `목표:` 아래 번호와 문장을 적는다")
    본것 = set()
    for 절번호, 절, r in 규칙들(d):
        rid = 규칙id(절번호, r)
        머리 = f"규칙 {rid}"
        if rid in 본것:
            막음.append(f"{머리} — 번호가 겹친다")
        본것.add(rid)
        if not str(r.get("문장", "")).strip():
            막음.append(f"{머리} — 문장이 비었다")
        목표 = r.get("목표") or []
        if not 목표:
            막음.append(f"{머리} — 목표가 없다. 다섯 밖의 이유로 규칙을 두지 않는다: {str(r.get('문장',''))[:40]}")
        else:
            밖 = [n for n in 목표 if n not in d["목표"]]
            if 밖:
                막음.append(f"{머리} — 없는 목표 번호 {밖}")
        for 문제 in 거는곳검사(뿌리, d, 절번호, r):
            막음.append(f"{머리} — {문제}")
        출처 = str(r.get("출처", "")).strip()
        if not 출처:
            알림.append(f"{머리} — 출처가 비었다 ({' · '.join(출처들)})")
        elif 출처 not in 출처들:
            막음.append(f"{머리} — 출처 「{출처}」 는 없다 ({' · '.join(출처들)})")
        if not 검사있나(r):
            알림.append(f"{머리} — 검사 없이 문장만 들어간다: {str(r.get('문장',''))[:48]}")
    p, 바뀜 = build(뿌리, 쓰기=False)
    if 바뀜:
        if p.is_file() and 생성표지 not in p.read_text(encoding="utf-8"):
            막음.append(f"{d['넣는곳']} 이 대장에서 만든 파일이 아니다 — `ops ledger build` 로 만든다")
        else:
            막음.append(f"{d['넣는곳']} 이 대장과 다르다 — 손으로 고쳤거나 build 를 안 돌렸다. "
                        f"`.rules.yml` 을 고치고 `ops ledger build`")
    return 막음, 알림


def 현황(뿌리: Path) -> str:
    d = 대장(뿌리)
    전체 = list(규칙들(d))
    검사수 = sum(1 for _i, _s, r in 전체 if 검사있나(r))
    out = [f"규칙 {len(전체)}개 · 검사 있는 것 {검사수} · 문장만 {len(전체) - 검사수}"]
    for n, t in sorted(d["목표"].items()):
        해당 = [(i, r) for i, _s, r in 전체 if n in (r.get("목표") or [])]
        검 = sum(1 for _i, r in 해당 if 검사있나(r))
        out.append(f"  목표 {n} {t.split(' — ')[0]:<12} 규칙 {len(해당):>2} · 검사 {검:>2}"
                   + ("   ← 검사가 하나도 없다" if 해당 and not 검 else "")
                   + ("   ← 규칙이 없다" if not 해당 else ""))
    출처셈: dict[str, int] = {}
    for _i, _s, r in 전체:
        k = str(r.get("출처", "")).strip() or "빈칸"
        출처셈[k] = 출처셈.get(k, 0) + 1
    out.append("  출처 " + " · ".join(f"{k} {v}" for k, v in sorted(출처셈.items())))
    return "\n".join(out)


def 목표별(뿌리: Path, n: int) -> list[str]:
    d = 대장(뿌리)
    줄 = []
    for i, _s, r in 규칙들(d):
        if n in (r.get("목표") or []):
            줄.append(f"  {규칙id(i, r):<5} {'검사' if 검사있나(r) else '문장'}  {str(r.get('문장',''))[:70]}")
    return 줄
