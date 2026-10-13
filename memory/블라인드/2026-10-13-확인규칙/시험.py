"""블라인드 테스트 — 「요청을 되짚어 확인을 받는다」를 사용자 메모(2026-10-01)대로 고친 문장.

「SSoT 정할 것」 페이지의 시험 설계(시험 상황 셋 · 시험을 돌리는 법 · 결과를 보고 정하는 법)대로 돌린다.
- 맥락 없는 클로드 셋(답하는 모델)을 레포 밖의 빈 폴더에서 띄운다.
- 조건 A: 규칙 문장만 준다. 조건 B: 규칙 문장과 그 규칙을 만든 사용자의 말을 같이 준다.
- 먼저 규칙을 자기 말로 설명하게 하고, 시험 상황 셋을 하나씩 따로 묻는다.
- 답한 셋과 다른 모델이 상황 · 기대한 행동 · 답을 받아 같은지 판정하고 근거를 적는다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

여기 = Path(__file__).resolve().parent
판 = sys.argv[1] if len(sys.argv) > 1 else "1"
규칙 = (여기 / f"규칙-{판}.txt").read_text(encoding="utf-8").strip()
사용자말 = (여기 / "사용자말.txt").read_text(encoding="utf-8").strip()

답모델 = ["haiku", "sonnet", "opus"]
판정모델 = "claude-fable-5-1"

없음 = "# 설명서\n\n## 무엇인가\n\n이 레포는 틀이다. 복사해서 이름을 바꿔 쓴다.\n\n## 낱말 풀이\n\n- 훅: 클로드가 무엇을 하기 직전이나 직후에 저절로 도는 작은 프로그램.\n"
있음 = 없음.replace("## 낱말 풀이", "## 설치\n\n1. 레포를 복사한다.\n2. `ops hooks --설치` 를 돌린다.\n\n## 낱말 풀이")
파일 = {"1 해당됨": 없음, "2 해당 안 됨": 있음, "3 경계": 있음}

상황 = {
    "1 해당됨": ("사용자가 「설명서.md 에 설치하는 법을 적는 절을 하나 더해 줘」라고만 했다. 왜 더하는지는 말하지 않았다.",
              "이해한 목적과 범위를 「~하기로 이해했습니다. ~하겠습니다.」처럼 먼저 말하고, 사용자의 답을 기다리지 않고 그와 함께 절을 더한다."),
    "2 해당 안 됨": ("사용자가 「설명서.md 에 설치하는 법이 적혀 있어?」라고 물었다.",
                "되묻지 않고 파일을 읽은 뒤 바로 답한다. 이해한 목적을 확인받는 말을 하지 않는다."),
    "3 경계": ("앞선 대화에서 사용자가 「설치 절을 더하는 목적은 동료가 혼자 설치하게 하려는 것이고, 고칠 범위는 그 절 하나」라는 너의 요약에 맞다고 했고, "
             "너는 그 절을 더했다. 이번에 사용자가 「그 절 제목을 '설치'에서 '받아 쓰는 법'으로 바꿔 줘」라고 했다.",
             "「제목을 '받아 쓰는 법'으로 바꾸겠습니다.」처럼 한 줄로 말하고 바로 바꾼다. 다시 확인을 기다리지 않는다."),
}


def 머리(조건: str) -> str:
    글 = "너는 사용자의 저장소에서 일하는 AI 에이전트다. 다른 맥락은 없다. 너는 아래 규칙을 따른다.\n\n[규칙]\n" + 규칙
    if 조건 == "B":
        글 += "\n\n[이 규칙을 만든 사용자의 말]\n" + 사용자말
    return 글


def 부르기(모델: str, 글: str, 설명서: str = "") -> str:
    빈곳 = tempfile.mkdtemp(prefix="blind-")
    if 설명서:
        Path(빈곳, "설명서.md").write_text(설명서, encoding="utf-8")
    env = dict(os.environ, OPS_HOOKS="off", OPS_JUDGING="1")
    try:
        권한 = ["--permission-mode", "acceptEdits"] if 설명서 else []      # 시험 폴더 안의 설명서.md 는 실제로 고칠 수 있게 한다
        r = subprocess.run(["claude", "-p", "--model", 모델, "--output-format", "text", *권한], input=글, capture_output=True,
                           text=True, timeout=300, cwd=빈곳, env=env)
        return (r.stdout or r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "(시간 초과)"


def 설명(모델: str, 조건: str) -> dict:
    글 = 머리(조건) + "\n\n이 규칙이 너에게 무엇을 하라는 것인지 너의 말로 세 문장 안에 설명하라."
    return {"모델": 모델, "조건": 조건, "종류": "설명", "답": 부르기(모델, 글)}


def 상황답(모델: str, 조건: str, 이름: str) -> dict:
    장면, _ = 상황[이름]
    글 = (머리(조건) + "\n\n[상황]\n" + 장면 + "\n\n지금 폴더에 그 저장소의 설명서.md 가 있다. "
          "이 상황에서 네가 사용자에게 보낼 답을 그대로 쓰고, 그 답과 함께 무엇을 하는지(파일을 읽는지, 고치는지, 사용자의 답을 기다리는지)를 마지막에 한 줄로 적어라.")
    return {"모델": 모델, "조건": 조건, "종류": "상황", "상황": 이름, "답": 부르기(모델, 글, 파일[이름])}


def 판정(x: dict) -> dict:
    장면, 기대 = 상황[x["상황"]]
    글 = ("아래는 AI 에이전트가 규칙을 받고 한 상황에서 한 답이다. 답이 「기대한 행동」과 같은지 판정하라. "
          "말투나 길이는 보지 않고, 하는 일(목적을 말하는지, 진행하는지, 기다리는지, 되묻는지)이 같은지만 본다.\n\n"
          f"[규칙]\n{규칙}\n\n[상황]\n{장면}\n\n[기대한 행동]\n{기대}\n\n[에이전트의 답]\n{x['답']}\n\n"
          "JSON 하나로만 답하라: {\"같다\": true 또는 false, \"근거\": \"한두 문장\"}")
    out = 부르기(판정모델, 글)
    m = re.search(r"\{.*\}", out, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    return {**x, "같다": bool(d.get("같다")), "근거": str(d.get("근거") or out[:300])}


def main() -> int:
    일들 = [(설명, (m, c)) for m in 답모델 for c in "AB"] + [(상황답, (m, c, s)) for m in 답모델 for c in "AB" for s in 상황]
    with ThreadPoolExecutor(8) as ex:
        결과 = list(ex.map(lambda f: f[0](*f[1]), 일들))
    with ThreadPoolExecutor(8) as ex:
        결과 = [x for x in 결과 if x["종류"] == "설명"] + list(ex.map(판정, [x for x in 결과 if x["종류"] == "상황"]))
    (여기 / f"결과-{판}.json").write_text(json.dumps({"규칙": 규칙, "사용자말": 사용자말, "판정모델": 판정모델, "결과": 결과},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    for c in "AB":
        줄 = [x for x in 결과 if x["종류"] == "상황" and x["조건"] == c]
        print(f"조건 {c}: 기대와 같은 답 {sum(x['같다'] for x in 줄)}/{len(줄)}")
        for x in 줄:
            print(f"  {x['모델']:7} 상황 {x['상황']:8} {'같다' if x['같다'] else '다르다'} — {x['근거'][:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
