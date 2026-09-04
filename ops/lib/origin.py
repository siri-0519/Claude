#!/usr/bin/env python3
"""누가 냈나 — 문서의 항마다 그것이 어디서 왔는지를 세고, 판정을 받아 둔다.

왜 있는가 (2026-09-04). 이 계정의 레포 넷에서 같은 사고가 났다. 클로드가 적은 것과
사람이 정한 것이 같은 문장으로 같은 문서에 앉아 있어서, 다음 세션의 클로드가 전부
사람의 결정으로 읽고 그 위에 또 쌓는다. `broadcast` 레포의 규칙 파일에는 *제안이 문서
사이에서 서로 인용되며 확정으로 굳는 사고가 두 번 났다* 고 적혀 있고, `creation`
레포에서는 떡밥 대장 42행 가운데 22행이 클로드가 넣은 것이었다.

무엇을 하는가.
  - 문서를 항으로 가른다. 항은 불릿 한 줄 · 표 한 행 · 문단 하나다.
  - 항마다 누가 냈는지를 사이드카(`<파일>.meta.yml`)의 항출처 칸에 둔다.
    본문에는 표시를 붙이지 않는다 — 본문은 사람도 클로드도 읽는 것이라, 줄마다 기호가
    붙으면 읽는 양이 그만큼 늘고 글이 지저분해진다.
  - 판정은 **사람이 직접 커밋한 줄에서만** 받는다 (git blame). 클로드가 자기에게
    판정을 줄 수 없게 하기 위해서다.
  - 판정이 없는 항의 수를 센다. 그 수가 늘면 커밋을 막는 것은 부르는 쪽의 몫이다.

어느 문서를 세는가는 레포마다 다르다. 레포 뿌리의 `.origin.yml` 이 정한다:

    문서:            # 셀 문서. glob 으로 적는다
      - "story/characters/*.md"
      - "identity/**/*.md"
    빼는것:          # 경로에 이 조각이 들어가면 세지 않는다
      - "/log/"
    사람메일:        # 판정을 받을 사람의 커밋 메일. 여럿이면 여러 줄
      - "someone@example.com"

기계는 여기 하나, 대장은 레포마다 — 그것이 이 파일이 따로 있는 이유다.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import subprocess
from datetime import date
from pathlib import Path

import yaml

# 클로드가 커밋할 때 쓰는 메일. 이 메일이 아닌 커밋을 사람의 것으로 본다.
클로드메일 = "noreply@anthropic.com"

# 값은 넷이다. 한 낱말로 적는다.
누가냈나 = {
    "작가": "사람이 확정 · 지시 · 컨셉 · 설정으로 냈다",
    "채택": "클로드가 낸 것을 사람이 채택하거나 확인했다",
    "봤다": "사람의 표시는 붙어 있으나 누가 낸 것인지가 안 적혀 있다",
    "없다": "클로드가 적었고 사람은 아직 안 봤다",
}

설정파일 = ".origin.yml"
검토문서 = "ORIGIN-REVIEW.md"


# ------------------------------------------------------------ 레포와 설정 ----

def 설정(뿌리: Path) -> dict:
    p = 뿌리 / 설정파일
    if not p.is_file():
        raise SystemExit(
            f"{설정파일} 이 없다. 어느 문서의 항을 셀지 정해야 한다.\n"
            f"보기:\n문서:\n  - \"*.md\"\n빼는것:\n  - \"/log/\"\n")
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    d.setdefault("문서", [])
    d.setdefault("빼는것", [])
    d.setdefault("사람메일", [])
    return d


def 세는문서(뿌리: Path) -> list[Path]:
    c = 설정(뿌리)
    본 = []
    for 무늬 in c["문서"]:
        본 += sorted(뿌리.glob(무늬))
    빼기 = tuple(c["빼는것"])
    나온것, 본것 = [], set()
    for p in 본:
        r = p.relative_to(뿌리).as_posix()
        if p.is_file() and r not in 본것 and not any(x in "/" + r for x in 빼기):
            본것.add(r)
            나온것.append(p)
    return 나온것


def 상대(뿌리: Path, p: Path) -> str:
    try:
        return p.relative_to(뿌리).as_posix()
    except ValueError:
        return str(p)


# ------------------------------------------------------------- 항 가르기 ----

def 항들(글: str) -> list[tuple[int, str]]:
    """문서를 항으로 가른다. 항은 불릿 한 줄 · 표 한 행 · 문단 하나다.

    머리와 빈 줄과 인용(>)과 표의 구분선은 항이 아니다. 절 번호는 `##` 를 셈해서
    붙인다 — 항을 가리키는 열쇠의 절반이 그 번호다."""
    절, 결과, 문단 = 0, [], []

    def 닫기():
        if 문단:
            결과.append((절, " ".join(문단)))
            문단.clear()

    for l in 글.splitlines():
        s = l.strip()
        m = re.match(r"^(#+)\s", l)
        if m:
            닫기()
            if m.group(1) == "##":
                절 += 1
            continue
        if not s or s.startswith(">") or re.match(r"^\|[\s:|-]+\|$", s):
            닫기()
            continue
        if s.startswith(("-", "*", "|")) or re.match(r"^\d+\.", s):
            닫기()
            결과.append((절, s))
        else:
            문단.append(s)
    닫기()
    return 결과


def 앞머리(본문: str) -> str:
    """항의 본문에서 표기를 걷어낸 앞부분. 항을 알아보는 데 쓴다."""
    민 = re.sub(r"[`*_|#\[\]()]", "", 본문)
    민 = re.sub(r"^[-*\d.\s]+", "", 민)
    민 = re.sub(r"\s+", " ", 민).strip()
    return 민[:24]


def 항열쇠(절: int, 본문: str) -> str:
    """옛 열쇠. 사이드카에 이 모양으로 적힌 것을 읽기 위해서만 남긴다."""
    return f"{절}:{앞머리(본문)}"


def 항이름(절: int, 본문: str) -> str:
    """항에 처음 붙이는 이름. 한 번 붙으면 본문이 바뀌어도 그대로 간다.

    왜 이름이 따로 필요한가 (2026-09-04). 처음에는 「절 번호 + 본문 앞 24자」를 열쇠로
    썼는데, 그러면 본문의 오타 하나만 고쳐도 열쇠가 바뀌고 사람이 내린 판정이 통째로
    날아갔다. 판정을 6,700번 받아 놓고 문장을 다듬으면 다 없어지는 구조였다.

    그래서 이름은 처음 볼 때 한 번 짓고, 그 뒤로는 앵커(사이드카의 `항` 칸)가 그 이름과
    그때의 앞머리를 함께 갖는다. 다음에 읽을 때는 앞머리로 다시 찾고, 앞머리가 조금
    달라졌으면 닮은 정도로 잇는다. 많이 달라졌으면 잇지 않는다 — 사람이 판정한 것은
    그때의 문장이므로, 문장이 달라졌으면 다시 판정받아야 한다."""
    씨 = f"{절}:{앞머리(본문)}"
    return hashlib.sha1(씨.encode("utf-8")).hexdigest()[:8]


# 앞머리가 이만큼 닮았으면 같은 항으로 본다. 이보다 멀면 새 항이고 판정이 없다.
닮음선 = 0.62


def 닮음(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def 맞추기(p: Path) -> tuple[list, dict, list, int]:
    """지금 문서의 항을 사이드카의 앵커에 맞춘다.

    돌려주는 것 넷:
      줄목록  (이름, 절, 본문, 값, 흐름) — 흐름은 앞머리가 달라진 채로 이어 붙인 항이다
      앵커    이름 → "절:앞머리". 지금 문서에 있는 항만 남는다
      흐른것  (이름, 옛 앞머리, 새 앞머리) — 사람에게 다시 보여야 하는 것들
      사라진수 앵커에는 있는데 문서에 없는 항. 그 판정은 버린다
    """
    메타 = _메타(p)
    옛앵커 = dict(메타.get("항") or {})
    판정 = dict(메타.get("항출처") or {})

    # 옛 모양(절:앞머리 를 열쇠로 쓰던 것)을 앵커로 옮긴다
    for k in list(판정):
        if re.match(r"^\d+:", k) and k not in 옛앵커.values():
            이름 = hashlib.sha1(k.encode("utf-8")).hexdigest()[:8]
            옛앵커[이름] = k
            판정[이름] = 판정.pop(k)

    지금 = [(절, 본문, f"{절}:{앞머리(본문)}") for 절, 본문 in 항들(p.read_text(encoding="utf-8"))]
    남은앵커 = dict(옛앵커)
    붙인것 = {}

    # 1. 절과 앞머리가 그대로인 것부터
    for i, (_절, _본문, 씨) in enumerate(지금):
        for 이름, 옛씨 in list(남은앵커.items()):
            if 옛씨 == 씨:
                붙인것[i] = (이름, False)
                del 남은앵커[이름]
                break

    # 2. 남은 것은 같은 절 안에서 가장 닮은 앵커에 잇는다
    흐른것 = []
    for i, (절, _본문, 씨) in enumerate(지금):
        if i in 붙인것:
            continue
        짝, 점수 = None, 0.0
        for 이름, 옛씨 in 남은앵커.items():
            if not 옛씨.startswith(f"{절}:"):
                continue
            s = 닮음(옛씨.split(":", 1)[1], 씨.split(":", 1)[1])
            if s > 점수:
                짝, 점수 = 이름, s
        if 짝 and 점수 >= 닮음선:
            붙인것[i] = (짝, True)
            흐른것.append((짝, 남은앵커[짝], 씨))
            del 남은앵커[짝]

    # 3. 그래도 안 붙은 것은 새 항이다
    줄목록, 새앵커 = [], {}
    for i, (절, 본문, 씨) in enumerate(지금):
        이름, 흐름 = 붙인것.get(i, (None, False))
        if 이름 is None:
            이름 = 항이름(절, 본문)
            while 이름 in 새앵커:
                이름 = hashlib.sha1((이름 + 씨).encode("utf-8")).hexdigest()[:8]
        새앵커[이름] = 씨
        줄목록.append((이름, 절, 본문, 값만(판정.get(이름, "없다")), 흐름))
    return 줄목록, 새앵커, 흐른것, len(남은앵커)


# --------------------------------------------------------------- 사이드카 ----

def 사이드카(p: Path) -> Path:
    return p.with_name(p.name + ".meta.yml")


def _메타(p: Path) -> dict:
    side = 사이드카(p)
    if not side.is_file():
        return {}
    try:
        return yaml.safe_load(side.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def 값만(칸) -> str:
    """사이드카의 한 칸에서 값만 꺼낸다.

    칸은 두 모양이다. 글자 하나면 사람이 검토 문서를 커밋해서 들어온 판정이고,
    표(누가 · 근거)면 사람이 대화로만 말해서 클로드가 적은 판정이다."""
    return 칸 if isinstance(칸, str) else str((칸 or {}).get("누가") or "없다")


def 항출처_읽기(p: Path) -> dict:
    return dict(_메타(p).get("항출처") or {})


def 쓰기(p: Path, 판정: dict, 앵커: dict) -> None:
    """판정과 앵커를 같이 적는다. 둘은 짝이라 따로 적으면 어긋난다."""
    meta = _메타(p)
    meta["항"] = dict(sorted(앵커.items()))
    meta["항출처"] = {k: v for k, v in sorted(판정.items()) if k in 앵커}
    meta["updated"] = date.today().isoformat()
    사이드카(p).write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")


def 내가_적은_판정(p: Path) -> list[tuple[str, str, str]]:
    """사람의 커밋에서 오지 않고 클로드가 적은 판정. 이름 · 값 · 근거."""
    return [(k, 값만(v), str((v or {}).get("근거") or ""))
            for k, v in 항출처_읽기(p).items() if not isinstance(v, str)]


def 현황(p: Path) -> list[tuple[str, int, str, str]]:
    """그 문서의 항과, 항마다 지금 붙어 있는 값. 이름 · 절 · 본문 · 값."""
    줄목록, _앵커, _흐른것, _사라진 = 맞추기(p)
    return [(이름, 절, 본문, 값) for 이름, 절, 본문, 값, _흐름 in 줄목록]


def 앵커_고치기(p: Path) -> tuple[list, int]:
    """지금 문서에 맞춰 앵커를 다시 적는다. 흐른 항과 사라진 항의 수를 돌려준다.

    본문을 고친 뒤에 이것을 돌려야 판정이 새 문장을 따라간다. 돌리지 않으면 판정은
    옛 앞머리에 묶여 있고, 다음에 읽을 때 닮음으로 다시 찾긴 하지만 매번 다시 찾는다."""
    줄목록, 앵커, 흐른것, 사라진 = 맞추기(p)
    쓰기(p, 항출처_읽기(p), 앵커)
    return 흐른것, 사라진


# --------------------------------------------------- 판정은 사람의 커밋에서 ----

def 사람이_쓴_줄(뿌리: Path, 쪽: Path, 사람메일: list[str] | None = None) -> set[int]:
    """그 파일에서 사람이 직접 커밋한 줄 번호. git blame 이 판정한다.

    판정을 클로드가 적을 수 있으면 이 대장은 아무것도 보장하지 못한다. 사람이 커밋한
    줄은 커밋한 사람이 달라서 클로드의 줄과 기계적으로 갈린다.

    막지 못하는 것을 적어 둔다. 클로드가 사람 이름으로 커밋하면 뚫린다 — 그것은 부르는
    레포의 훅이 도구 직전에 막아야 한다. 그리고 사람이 직접 커밋할 수 없는 자리(대화로만
    한 판정)는 이 길로 못 들어온다. 그런 판정은 클로드가 적고 근거를 남기며, 세는 쪽이
    「클로드가 적은 판정」으로 따로 세어 눈에 보이게 한다."""
    if not 쪽.is_file():
        return set()
    r = subprocess.run(["git", "blame", "--line-porcelain", "--", 상대(뿌리, 쪽)],
                       cwd=뿌리, capture_output=True, text=True)
    if r.returncode != 0:
        return set()
    허용 = [m.lower() for m in (사람메일 or [])]
    나온것, 줄번호 = set(), 0
    for l in r.stdout.splitlines():
        m = re.match(r"^[0-9a-f]{7,40} \d+ (\d+)", l)
        if m:
            줄번호 = int(m.group(1))
        elif l.startswith("author-mail "):
            메일 = l[len("author-mail "):].strip().strip("<>").lower()
            사람인가 = (메일 in 허용) if 허용 else (클로드메일 not in 메일)
            if 사람인가:
                나온것.add(줄번호)
    return 나온것


# ------------------------------------------------------------- 일감 고르기 ----
# 왜 있는가 (2026-09-04): 검토 문서가 문서 하나를 통째로 냈다. 정본 하나가 94항이고
# 결정 대장 하나가 191항이라 사람이 못 쓴다. 세 레포에 판정 없는 항이 9,000개 넘게
# 밀려 있는데 판정된 항은 0개였다 — 만들어만 놓고 한 번도 안 쓴 것이 그 증거다.
#
# 다 판정하는 것은 목표가 아니다. 목표는 「지금 쓰는 대목만 판정된 상태」다. 그러려면
# 지금 쓰는 대목을 골라낼 수 있어야 한다. 고르는 길이 셋이다 — 절로, 낱말로, 그리고
# 일감으로. 마지막 것이 핵심이다: 어떤 파생물(원고 · 각색본)이 어느 출처의 어느 절에
# 기대는지가 이미 사이드카에 적혀 있으므로, 그것을 뒤집으면 「이 원고를 쓰려면 어느
# 항을 판정해야 하는가」가 나온다.

def 아티팩트찾기(뿌리: Path) -> dict:
    """사이드카에 적힌 id → 그 파일. 출처를 id 로 가리키는 것을 풀기 위해서다."""
    나온것 = {}
    for side in 뿌리.rglob("*.meta.yml"):
        if ".git" in side.parts or ".claude-ops" in side.parts:
            continue
        본 = side.with_name(side.name[: -len(".meta.yml")])
        if not 본.is_file():
            continue
        try:
            meta = yaml.safe_load(side.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        이름 = str(meta.get("id") or 상대(뿌리, 본))
        나온것[이름] = 본
    return 나온것


def 일감_출처(뿌리: Path, 파생: Path) -> list[tuple[Path, list]]:
    """그 파생물이 기대는 출처와 절. 사이드카의 derives_from 을 뒤집는다."""
    meta = _메타(파생)
    지도 = 아티팩트찾기(뿌리)
    나온것 = []
    for e in meta.get("derives_from") or []:
        아이디 = e.get("id") if isinstance(e, dict) else e
        절 = list(e.get("절") or []) if isinstance(e, dict) else []
        본 = 지도.get(str(아이디))
        if 본 and 본.is_file():
            나온것.append((본, [int(x) for x in 절]))
    return 나온것


def 고르기(p: Path, 절: list | None = None, 찾기: str | None = None,
        판정없는것만: bool = True) -> list:
    """그 문서에서 판정할 항만 고른다."""
    줄목록, _앵커, _흐른것, _사라진 = 맞추기(p)
    골 = []
    for 이름, 절번호, 본문, 값, 흐름 in 줄목록:
        if 절 and 절번호 not in 절:
            continue
        if 찾기 and 찾기 not in 본문:
            continue
        if 판정없는것만 and 값 != "없다" and not 흐름:
            continue
        골.append((이름, 절번호, 본문, 값, 흐름))
    return 골


# ------------------------------------------------------------- 검토 문서 ----

def 검토문서_만들기(뿌리: Path, 대상들: list, 제목: str = "", 몇개: int | None = None,
              찾기: str | None = None, write: bool = True) -> tuple[str, int]:
    """사람이 한 항씩 판정할 문서를 만든다. 대상들은 (파일, 절목록|None) 의 목록이다.

    표가 아니라 항마다 블록으로 낸다. 문서의 표 행 하나가 1,500자를 넘는 일이 있는데,
    그것을 표의 한 칸에 넣으면 오른쪽 끝의 낱말을 찾을 수 없다."""
    덩이, 셈 = [], 0
    for p, 절 in 대상들:
        골 = 고르기(p, 절, 찾기)
        if not 골:
            continue
        덩이.append((p, 골))
        셈 += len(골)

    남은 = 몇개
    글 = [f"# 누가 냈나 — {제목 or (상대(뿌리, 대상들[0][0]) if 대상들 else '')}", "",
         f"> 판정할 항이 {셈}개다."
         + (f" 그 가운데 앞에서 {min(몇개, 셈)}개만 담았다." if 몇개 and 몇개 < 셈 else ""),
         "> 각 항 아래 `누가:` 줄에 한 낱말만 적으신다. 나머지 줄은 고치지 않는다.", ""]
    글 += [f"- `{k}` — {v}" for k, v in 누가냈나.items()]
    글 += ["",
          "**적으신 뒤에 이 파일을 커밋해 주셔야 한다.** 판정이 사람의 커밋에서 왔는지를",
          "`git blame` 이 보고, 클로드가 적은 줄은 받지 않는다.", "", "---", ""]

    담은 = 0
    for p, 골 in 덩이:
        if 남은 is not None and 남은 <= 0:
            break
        쓸것 = 골 if 남은 is None else 골[:남은]
        if 남은 is not None:
            남은 -= len(쓸것)
        글 += [f"## {상대(뿌리, p)}", ""]
        for 이름, 절, 본문, 값, 흐름 in 쓸것:
            머리 = f"### [{이름}] {절}절" + ("  — 본문이 바뀌었다" if 흐름 else "")
            글 += [머리, "", 본문, "", f"누가: {값}", ""]
            담은 += 1
        _줄, 앵커, _흐른것, _사라진 = 맞추기(p)
        쓰기(p, 항출처_읽기(p), 앵커)     # 이름을 지금 본문에 묶어 둔다

    글 = "\n".join(글) + "\n"
    if write:
        (뿌리 / 검토문서).write_text(글, encoding="utf-8")
    return 글, 담은


def 검토문서_읽기(뿌리: Path) -> tuple[int, list, int]:
    """사람이 채운 문서를 사이드카로 옮긴다. 사람이 커밋한 줄만 받는다."""
    쪽 = 뿌리 / 검토문서
    if not 쪽.is_file():
        raise SystemExit(f"{검토문서} 가 없다. 먼저 만든다.")
    줄들 = 쪽.read_text(encoding="utf-8").splitlines()
    사람줄 = 사람이_쓴_줄(뿌리, 쪽, 설정(뿌리)["사람메일"])

    바뀐, 튄것, 클로드것 = 0, [], 0
    지금파일, 지금 , 앵커, 아는이름 = None, {}, {}, set()
    이름 = None

    def 닫기():
        if 지금파일 is not None:
            쓰기(지금파일, 지금, 앵커)

    for i, l in enumerate(줄들, start=1):
        m = re.match(r"^## (\S+)$", l.strip())
        if m:
            닫기()
            지금파일 = 뿌리 / m.group(1)
            if not 지금파일.is_file():
                튄것.append(f"{i}줄 — 그런 문서가 없다: {m.group(1)}")
                지금파일 = None
                continue
            줄목록, 앵커, _흐른것, _사라진 = 맞추기(지금파일)
            지금 = 항출처_읽기(지금파일)
            아는이름 = {x[0] for x in 줄목록}
            continue
        m = re.match(r"^### \[([0-9a-f]{8})\]", l.strip())
        if m:
            이름 = m.group(1)
            continue
        if not l.startswith("누가:") or 지금파일 is None:
            continue
        값 = l[len("누가:"):].strip()
        if 값 not in 누가냈나:
            튄것.append(f"{i}줄 — 모르는 값 «{값}»")
        elif 이름 not in 아는이름:
            튄것.append(f"{i}줄 — 문서에 없는 항이다 ({이름})")
        elif i not in 사람줄:
            if 값 != "없다" and 값만(지금.get(이름, "없다")) != 값:
                클로드것 += 1
        elif 값 == "없다":
            if 지금.pop(이름, None) is not None:
                바뀐 += 1
        elif 값만(지금.get(이름, "없다")) != 값:
            지금[이름] = 값
            바뀐 += 1
        이름 = None
    닫기()
    return 바뀐, 튄것, 클로드것


# ------------------------------------------------------------------ 세기 ----

def 세기(뿌리: Path) -> tuple[int, int, list]:
    """항 전체 · 판정 없는 항 · 문서마다의 수. 이 수가 늘면 막는 것은 부르는 쪽이다."""
    전체, 표 = 0, []
    for p in 세는문서(뿌리):
        줄목록 = 현황(p)
        n = sum(1 for *_x, v in 줄목록 if v == "없다")
        전체 += len(줄목록)
        if n:
            표.append((n, len(줄목록), 상대(뿌리, p)))
    표.sort(reverse=True)
    return 전체, sum(n for n, _t, _f in 표), 표
