"""표시 — 주제 파일의 주장 줄에 누구의 말인지가 붙어 있나.

기계 규칙 둘을 본다.
  1. 주제 파일에 새로 들어가는 주장 줄(목록 항 · 번호 항 · 표 행)에는 표시 가운데 하나가 붙어 있다.
  2. [제안]이 [확인]으로 바뀌는 것은 사용자가 GitHub 웹에서 한 커밋에서만 된다. 에이전트의 커밋에서는 막는다.

무엇이 표시인지는 `.ops.yml` 의 표시 · 표시패턴 칸이 정한다. 검사 전부터 있던 줄은 보지 않고
바뀌는 줄만 본다 — 개수로 재지 않는다 (2026-09-07 결정).
"""
from __future__ import annotations

import re
from pathlib import Path

from 공통 import 설정, git, rel, 주제파일들, 옛줄전부

주장줄꼴 = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S|^\|")   # 목록 항 · 번호 항 · 표 행
표머리꼴 = re.compile(r"^\|\s*(?:-{3,}|:?-+:?)\s*\|")


def 표시꼴(c: dict) -> re.Pattern:
    return re.compile(c["표시패턴"])


def 주장줄인가(ln: str) -> bool:
    if not 주장줄꼴.match(ln) or 표머리꼴.match(ln):
        return False
    # 링크만 있는 목차 항, 코드, 빈 칸 표는 주장이 아니다
    본문 = re.sub(r"`[^`]*`", "", ln)
    본문 = re.sub(r"\[[^\]]*\]\([^)]*\)", "", 본문)
    if ln.startswith("|"):
        칸 = [x.strip() for x in ln.strip().strip("|").split("|")]
        if all(not x or x.startswith("`") for x in 칸):
            return False
    return len(re.findall(r"[가-힣]", 본문)) >= 6


def 표시없는줄(글: str, c: dict, 줄들: set[int] | None = None) -> list[tuple[int, str]]:
    """(줄 번호, 줄) — 주장 줄인데 표시가 없는 것. 줄들이 있으면 그 줄만 본다."""
    꼴 = 표시꼴(c)
    나온것 = []
    울타리 = False
    for i, ln in enumerate(글.split("\n"), 1):
        if ln.startswith("```"):
            울타리 = not 울타리
            continue
        if 울타리 or (줄들 is not None and i not in 줄들):
            continue
        if 주장줄인가(ln) and not 꼴.search(ln):
            나온것.append((i, ln.strip()))
    return 나온것


def 새줄들(뿌리: Path, 경로: str, 기준: str = "HEAD", 스테이지: bool = False) -> set[int]:
    """지금 파일에서 기준 커밋과 달라진(더해진) 줄 번호."""
    인자 = ["diff", "--unified=0", "--no-color"]
    if 스테이지:
        인자.append("--cached")
    out = git(뿌리, *인자, 기준, "--", 경로)
    번호: set[int] = set()
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", out, re.M):
        s = int(m.group(1)); n = int(m.group(2)) if m.group(2) is not None else 1
        번호.update(range(s, s + n))
    return 번호


def 붙이는말(c: dict) -> str:
    """어느 표시를 붙이라는 말 — 표시가 [확인] · [제안] 둘이면 누구의 말인지로, 아니면 목록으로."""
    표 = list(c["표시"])
    if sorted(표) == ["제안", "확인"]:
        return "사용자가 말한 것이면 [확인], 내가 제안한 것이면 [제안] 을 줄 끝에 붙인다"
    return "이 저장소의 표시(" + " · ".join("[" + t + "]" for t in 표) + ") 가운데 맞는 것을 줄 끝에 붙인다. 사용자가 말한 것과 내가 제안한 것을 가른다"


def 검사_새줄(뿌리: Path, c: dict | None = None, 스테이지: bool = False) -> list[str]:
    """바뀐 주제 파일의 새 줄 가운데 표시 없는 주장 줄을 이름으로 짚는다."""
    c = c or 설정(뿌리)
    문제 = []
    옛 = 옛줄전부(뿌리, c)
    for p in 주제파일들(뿌리, c):
        r = rel(뿌리, p)
        if 스테이지:
            if not git(뿌리, "diff", "--cached", "--name-only", "--", r):
                continue
            글 = git(뿌리, "show", f":{r}")
        else:
            글 = p.read_text(encoding="utf-8")
        추적 = git(뿌리, "ls-files", "--error-unmatch", "--", r)
        줄 = 새줄들(뿌리, r, 스테이지=스테이지) if 추적 else None
        if 추적 and not 줄:
            continue
        for i, ln in 표시없는줄(글, c, 줄):
            if ln in 옛:
                continue                           # 다른 파일에서 옮겨 온 줄
            문제.append(f"{r} {i}줄에 표시가 없다 — {붙이는말(c)}: {ln[:60]}")
    return 문제


def 검사_글(글: str, c: dict, 옛글: str = "") -> list[str]:
    """Edit · Write 직전 — 새 글에서 옛 글에 없던 주장 줄에 표시가 있나."""
    옛줄 = set(x.strip() for x in 옛글.split("\n"))
    문제 = []
    for i, ln in 표시없는줄(글, c):
        if ln not in 옛줄:
            문제.append(f"{i}줄에 표시가 없다 — {붙이는말(c)}: {ln[:60]}")
    return 문제


def 제안이확인으로(뿌리: Path, c: dict | None = None, 스테이지: bool = True) -> list[str]:
    """[제안] 줄이 [확인] 으로 바뀐 것. 사용자가 GitHub 웹에서 한 커밋이 아니면 막는다."""
    c = c or 설정(뿌리)
    표시들 = c["표시"]
    if not ("제안" in 표시들 and "확인" in 표시들):
        return []
    문제 = []
    for p in 주제파일들(뿌리, c):
        r = rel(뿌리, p)
        out = git(뿌리, "diff", "--cached" if 스테이지 else "HEAD", "--unified=0", "--no-color", "--", r)
        뺀 = [x[1:] for x in out.split("\n") if x.startswith("-") and not x.startswith("---")]
        더한 = [x[1:] for x in out.split("\n") if x.startswith("+") and not x.startswith("+++")]
        뺀제안 = [x for x in 뺀 if "[제안" in x]
        for ln in 더한:
            if "[확인" not in ln:
                continue
            핵 = re.sub(r"\[(확인|제안)[^\]]*\]", "", ln).strip()
            for old in 뺀제안:
                if re.sub(r"\[(확인|제안)[^\]]*\]", "", old).strip() == 핵:
                    문제.append(f"{r}: [제안]이 [확인]으로 바뀌었다 — [제안]으로 되돌린다. [확인]으로 바꾸는 것은 사용자가 GitHub 웹에서 하는 커밋에서만 된다: {핵[:50]}")
    return 문제
