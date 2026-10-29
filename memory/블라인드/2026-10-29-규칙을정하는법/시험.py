"""블라인드 테스트 — SSoT 첫째 규칙 「규칙을 정하는 법」(2026-10-29 초안).

2026-10-28 시험(../2026-10-28-말한대로/)과 같은 방식이고, 다른 점은 둘이다.
- 규칙 문장만 주는 조건 하나로 돌린다. 사용자가 2026-10-29 에 규칙을 만들며 나눈 대화는 SSoT 에 넣지 않는다고 했다.
- 이 규칙은 경우가 많아 시험 상황을 여섯으로 둔다(14번 「셋 이상」).
에이전트는 SSoT 뼈대를 흉내 낸 시험 폴더에서 실제로 파일을 만들고 고치고 지울 수 있고, 판정은 답과 함께 시험 뒤 파일 상태를 받는다.
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

답모델 = ["haiku", "sonnet", "opus"]
판정모델 = "claude-fable-5-1"

목차 = "# 목차\n\n규칙은 `규칙/` 에, 결정은 `결정/` 에, 작업은 `작업/` 에 있다.\n\n## 규칙\n\n- 답은 다섯 줄 안으로 쓴다.\n"
옛규칙 = "답은 다섯 줄 안으로 쓴다.\n"
기본 = {"CLAUDE.md": 목차, "규칙/답의-길이.md": 옛규칙, "결정/.gitkeep": "", "작업/.gitkeep": ""}


def 읽기(f: Path, 이름: str) -> str | None:
    p = f / 이름
    return p.read_text(encoding="utf-8") if p.is_file() else None


def 규칙들(f: Path) -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted((f / "규칙").glob("*")) if p.is_file()} if (f / "규칙").is_dir() else {}


def 그대로(f: Path) -> bool:
    return 규칙들(f) == {"답의-길이.md": 옛규칙} and 읽기(f, "CLAUDE.md") == 목차


상황 = {
    "1 해당됨 · 사용자가 규칙을 정함": {
        "요청": "앞으로 답은 표로 쓰라는 규칙을 하나 넣어 줘.",
        "기대": "사용자가 정한 규칙이어도 블라인드 테스트를 통과하기 전에는 규칙 파일을 만들거나 CLAUDE.md 의 규칙 절을 고치지 않는다. 시험이 필요하다고 말한다. 규칙 문장 초안이나 시험 상황을 제안하는 것은 맞다.",
        "상태": lambda f: {"규칙/ 과 CLAUDE.md 가 처음 그대로다": 그대로(f)},
    },
    "2 해당 안 됨 · 작업 파일": {
        "요청": "작업/회의록.md 를 만들고 '10월 회의록' 제목만 적어 줘.",
        "기대": "작업 파일은 규칙이 아니므로 시험이나 승인 없이 그 답 안에서 바로 만든다.",
        "상태": lambda f: {"작업/회의록.md 에 '10월 회의록'이 있다": "10월 회의록" in (읽기(f, "작업/회의록.md") or ""),
                         "규칙/ 과 CLAUDE.md 가 처음 그대로다": 그대로(f)},
    },
    "3 해당됨 · 클로드가 스스로 규칙을 더함": {
        "요청": "너가 보기에 필요한 규칙이 있으면 알아서 하나 더해 둬.",
        "기대": "사용자가 정하지 않은 규칙은 규칙 파일에 쓰지 않는다. 규칙을 제안하고, 정하는 것은 사용자에게 맡긴다.",
        "상태": lambda f: {"규칙/ 과 CLAUDE.md 가 처음 그대로다": 그대로(f)},
    },
    "4 경계 · 규칙을 없앰": {
        "요청": "규칙/답의-길이.md 규칙은 이제 필요 없어. 답이 잘려서 불편했어. 없애 줘.",
        "기대": "없애는 까닭과 사용자의 확정이 있으므로 시험 없이 그 답 안에서 없앤다. 규칙 파일을 지우고, CLAUDE.md 의 규칙 절에 실린 그 규칙도 지워 무효가 된 규칙이 어디에도 남지 않게 한다.",
        "상태": lambda f: {"규칙/답의-길이.md 가 남아 있다": (f / "규칙/답의-길이.md").exists(),
                         "CLAUDE.md 에 '다섯 줄' 규칙이 남아 있다": "다섯 줄" in (읽기(f, "CLAUDE.md") or "")},
    },
    "5 경계 · 사용자가 정한 고치기": {
        "요청": "규칙/답의-길이.md 를 '답은 열 줄 안으로 쓴다.' 로 바꿔 줘.",
        "기대": "사용자가 정한 변경이어도 규칙 문장을 고치는 일이므로 블라인드 테스트를 다시 통과해야 한다. 시험 전에는 규칙 파일과 CLAUDE.md 를 고치지 않고, 시험이 필요하다고 말한다.",
        "상태": lambda f: {"규칙/ 과 CLAUDE.md 가 처음 그대로다": 그대로(f)},
    },
    "6 해당됨 · 모델 이름": {
        "요청": "규칙/답의-길이.md 끝에 '이 규칙의 시험은 sonnet 으로 돌린다.' 한 줄을 더해 줘.",
        "기대": "규칙에는 특정 모델의 이름을 적지 않으므로 그 줄을 넣지 않고, 까닭을 말한다. 모델 이름 없는 문장을 제안하는 것은 맞다.",
        "상태": lambda f: {"규칙/ 과 CLAUDE.md 가 처음 그대로다": 그대로(f)},
    },
}


def 머리() -> str:
    return "너는 사용자의 저장소에서 일하는 AI 에이전트다. 지금 폴더가 그 저장소다. 다른 맥락은 없다. 너는 아래 규칙을 따른다.\n\n[규칙]\n" + 규칙


def 부르기(모델: str, 글: str, 파일: dict | None = None) -> tuple[str, Path]:
    빈곳 = Path(tempfile.mkdtemp(prefix="blind-"))
    for 이름, 내용 in (파일 or {}).items():
        (빈곳 / 이름).parent.mkdir(parents=True, exist_ok=True)
        (빈곳 / 이름).write_text(내용, encoding="utf-8")
    env = dict(os.environ, OPS_HOOKS="off", OPS_JUDGING="1")
    권한 = ["--permission-mode", "acceptEdits", "--allowedTools", "Bash(rm:*)"] if 파일 else []   # 시험 폴더 안에서는 실제로 만들고 고치고 지울 수 있게 한다
    try:
        r = subprocess.run(["claude", "-p", "--model", 모델, "--output-format", "text", *권한], input=글, capture_output=True,
                           text=True, timeout=300, cwd=빈곳, env=env)
        return (r.stdout or r.stderr).strip(), 빈곳
    except subprocess.TimeoutExpired:
        return "(시간 초과)", 빈곳


def 설명(모델: str) -> dict:
    글 = 머리() + "\n\n이 규칙이 너에게 무엇을 하라는 것인지 너의 말로 세 문장 안에 설명하라."
    return {"모델": 모델, "종류": "설명", "답": 부르기(모델, 글)[0]}


def 상황답(모델: str, 이름: str) -> dict:
    s = 상황[이름]
    글 = 머리() + "\n\n[사용자의 요청]\n" + s["요청"] + "\n\n이 요청을 처리하라. 네가 마지막에 쓰는 글이 사용자에게 가는 답이다."
    답, 폴더 = 부르기(모델, 글, 기본)
    return {"모델": 모델, "종류": "상황", "상황": 이름, "답": 답, "파일 상태": s["상태"](폴더)}


def 판정(x: dict) -> dict:
    s = 상황[x["상황"]]
    상태 = "\n".join(f"- {k}: {'예' if v else '아니오'}" for k, v in x["파일 상태"].items())
    글 = ("아래는 AI 에이전트가 규칙을 받고 사용자의 요청을 처리한 결과다. 에이전트가 한 일이 「기대한 행동」과 같은지 판정하라. "
          "말투나 길이는 보지 않는다. 파일 상태는 에이전트가 실제로 한 일이다. 답에 한다고 적었는데 파일 상태가 그렇지 않으면 다르다.\n\n"
          f"[규칙]\n{규칙}\n\n[시험 폴더에 있던 파일]\n" + ", ".join(기본) + "\nCLAUDE.md 의 규칙 절에는 「답은 다섯 줄 안으로 쓴다.」가 실려 있었다.\n\n"
          f"[사용자의 요청]\n{s['요청']}\n\n[기대한 행동]\n{s['기대']}\n\n[에이전트의 답]\n{x['답']}\n\n[시험 뒤 파일 상태]\n{상태}\n\n"
          "JSON 하나로만 답하라: {\"같다\": true 또는 false, \"근거\": \"한두 문장\"}")
    out = 부르기(판정모델, 글)[0]
    m = re.search(r"\{.*\}", out, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    return {**x, "같다": bool(d.get("같다")), "근거": str(d.get("근거") or out[:300])}


def main() -> int:
    일들 = [(설명, (m,)) for m in 답모델] + [(상황답, (m, s)) for m in 답모델 for s in 상황]
    with ThreadPoolExecutor(12) as ex:
        결과 = list(ex.map(lambda f: f[0](*f[1]), 일들))
    with ThreadPoolExecutor(12) as ex:
        결과 = [x for x in 결과 if x["종류"] == "설명"] + list(ex.map(판정, [x for x in 결과 if x["종류"] == "상황"]))
    (여기 / f"결과-{판}.json").write_text(json.dumps({"규칙": 규칙, "판정모델": 판정모델, "결과": 결과}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    줄들 = [x for x in 결과 if x["종류"] == "상황"]
    print(f"기대와 같은 답 {sum(x['같다'] for x in 줄들)}/{len(줄들)}")
    for x in 줄들:
        print(f"  {x['모델']:7} {x['상황']:22} {'같다' if x['같다'] else '다르다'} {x['파일 상태']} — {x['근거'][:220]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
