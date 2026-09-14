"""판정 — 다른 모델에게 판단 규칙을 넘겨 어긴 문장을 받는다 (설계 5절).

    답이 끝날 때:   사용자의 요청 · 에이전트의 답 · 규칙(용어 + 답할 때) · 바뀐 파일 · 낱말 후보
    커밋 직전:      스테이지된 주제 파일의 새 줄 · 규칙(용어 + 고칠 때)

쓴 쪽과 보는 쪽이 다르기 때문에 된다. 모델은 어긴 규칙과 어긴 문장만 돌려준다.
명령과 모델은 `.ops.yml` 의 판정 칸이 정한다. `claude -p --model haiku` 가 기본이다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from 공통 import 설정

규칙파일 = "ops/rules/판단.md"


def 규칙글(뿌리: Path, 절: str) -> str:
    """판단.md 에서 「용어」와 「고칠 때」 또는 「답할 때」 절을 한 글로."""
    p = 뿌리 / 규칙파일
    if not p.is_file():
        return ""
    글 = p.read_text(encoding="utf-8")
    from 공통 import 절나누기
    줄 = 글.split("\n")
    나온것 = []
    for 수준, 제목, s, e in 절나누기(글):
        t = 제목.strip("「」 ")
        if t == "용어" or t == 절:
            나온것.append("\n".join(줄[s:e]).strip())
    return "\n\n".join(나온것)


def 물음(요청: str, 답: str, 규칙: str, 바뀐파일: list[str], 낱말후보: list[str], 자리: str) -> str:
    머리 = ("아래 규칙으로 아래 글을 판정한다. 어긴 규칙과 어긴 문장만 JSON 으로 돌려준다.\n"
            '형식: {"어긴것": [{"규칙": "<규칙 번호나 이름>", "문장": "<어긴 문장을 그대로>", "이유": "<한 문장>"}]}\n'
            '어긴 것이 없으면 {"어긴것": []} 만 돌려준다. JSON 밖에 아무것도 쓰지 않는다.\n'
            "규칙에 없는 것으로 판정하지 않는다. 확실하지 않으면 어긴 것에 넣지 않는다.\n"
            "글 전체를 읽고 판정한다. 한 문장에 빠진 근거나 표시가 바로 앞뒤 문장에 있으면 어긴 것이 아니다. "
            "무엇을 봤는지 적힌 값은 직접 본 것이다. "
            "「직접 본 것 · 추측 · 크기를 밝힌다」는 사실 · 값 · 판정을 말하는 문장에만 건다. "
            "에이전트가 한 일이나 할 일을 말하는 문장(했다 · 한다 · 기다린다)에는 그 규칙을 걸지 않는다. "
            "표시가 붙어 있는 것 자체는 어느 규칙도 어긴 것이 아니다.\n")
    부분 = [머리, "=== 규칙 ===", 규칙]
    if 자리 == "답":
        부분 += ["=== 사용자의 이번 요청 ===", 요청 or "(없음)", "=== 에이전트의 답 ===", 답]
        if 바뀐파일:
            부분 += ["=== 이 답에서 바뀐 파일 ===", "\n".join(바뀐파일)]
        if 낱말후보:
            부분 += ["=== 사용자의 말 · 읽은 파일 · 허용 목록 어디에도 없는 답의 낱말 (규칙 「아는 말만 쓴다」의 후보) ===",
                     " ".join(낱말후보),
                     "후보는 하나씩 그 문장 안에서 본다. 글자 그대로의 뜻으로 쓰인 보통 낱말이면 넘긴다. "
                     "다른 것에 빗대어 쓰였거나(몸 · 일 · 상태를 돈 · 물건 · 싸움 따위에 빗댄 말), "
                     "저장소에 없는 사물 · 방법 · 절차의 이름이거나, 업계 용어면 「아는 말만 쓴다」를 어긴 것으로 넣는다."]
    else:
        부분 += ["=== 사용자의 요청 (있으면) ===", 요청 or "(없음)", "=== 문서에 새로 들어가는 줄 ===", 답]
    return "\n\n".join(부분)


def 부르기(뿌리: Path, 글: str, c: dict | None = None) -> tuple[list[dict], str]:
    """(어긴 것 목록, 오류 메시지). 오류면 목록은 비고 메시지에 이유가 있다."""
    c = c or 설정(뿌리)
    j = c["판정"]
    if j.get("끄기"):
        return [], "판정을 껐다 (.ops.yml 판정.끄기)"
    명령 = str(j.get("명령") or "claude")
    if not shutil.which(명령):
        return [], f"판정 명령 {명령} 이 없다"
    # 레포 안에서 부르면 판정 세션이 이 레포의 훅을 또 돌리고, 그 답 끝 훅이 판정을 또 불러 끝없이 돈다 (2026-09-14 실측: 90초 시간 초과).
    # 그래서 빈 임시 디렉터리에서 부르고, 이 기계의 훅은 OPS_HOOKS=off 로 끈다.
    import os, tempfile
    빈곳 = tempfile.mkdtemp(prefix="ops-judge-")
    env = dict(os.environ, OPS_HOOKS="off", OPS_JUDGING="1")
    try:
        r = subprocess.run([명령, "-p", "--model", str(j.get("모델") or "haiku"), "--output-format", "text"],
                           input=글, capture_output=True, text=True, timeout=int(j.get("시간") or 90),
                           cwd=빈곳, env=env)
    except subprocess.TimeoutExpired:
        return [], "판정이 시간을 넘겼다"
    except OSError as e:
        return [], f"판정을 못 돌렸다: {e}"
    finally:
        shutil.rmtree(빈곳, ignore_errors=True)
    if r.returncode != 0:
        return [], f"판정 명령이 실패했다: {(r.stderr or r.stdout).strip()[:200]}"
    return 풀기(r.stdout), ""


def 풀기(out: str) -> list[dict]:
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return []
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return []
    나온것 = []
    for x in d.get("어긴것") or []:
        if isinstance(x, dict) and x.get("문장"):
            규칙 = re.sub(r"^\s*규칙\s*", "", str(x.get("규칙", "?")))
            나온것.append({"규칙": 규칙, "문장": str(x["문장"]), "이유": str(x.get("이유", ""))})
    return 나온것


def 규칙전문들(뿌리: Path) -> dict[str, str]:
    """판단.md 의 "5. 직접 본 것 · 추측 · 크기를 밝힌다. …" 줄에서 번호 → 그 규칙 전문."""
    p = 뿌리 / 규칙파일
    d: dict[str, str] = {}
    if p.is_file():
        for ln in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(\d+)\.\s+(.+)$", ln.strip())
            if m:
                d[m.group(1)] = m.group(2).strip()
    return d


def 규칙이름들(뿌리: Path) -> dict[str, str]:
    """번호 → 규칙의 첫 문장(이름)."""
    return {k: v.split(".")[0].strip() for k, v in 규칙전문들(뿌리).items()}


def 되돌리는말(어긴것: list[dict], 뿌리: Path | None = None) -> str:
    전문 = 규칙전문들(뿌리) if 뿌리 else {}
    줄 = ["방금 쓴 답이 판단 규칙에 걸렸다. 판단 규칙은 다른 모델이 판정한 것이다. "
          "걸린 문장은 통째로 다시 써서 그 문장만 낸다. 답 전체를 다시 붙이지 않는다."]
    for x in 어긴것:
        번호 = x['규칙']
        줄.append(f"- 걸린 문장: {x['문장']}" + (f" — {x['이유']}" if x['이유'] else ""))
        if 번호 in 전문:
            줄.append(f"  규칙 {번호}: {전문[번호]}")
        else:
            줄.append(f"  규칙 {번호}")
    return "\n".join(줄)
