"""생성 파일 — 스크립트가 원본에서 통째로 만드는 파일과 블록. 손으로 고치지 않는다.

    ops build         전부 다시 만든다
    ops build --검사  원본과 다른 것을 이름으로 짚는다 (어긋남 목록에도 오른다)
"""
from __future__ import annotations

import re
from pathlib import Path

from 공통 import 설정, rel
import 지금 as 지금모듈
import 작업로그

시작표 = "<!-- BEGIN GENERATED: {} -->"
끝표 = "<!-- END GENERATED: {} -->"


def 블록바꾸기(글: str, 이름: str, 내용: str) -> str:
    s, e = 시작표.format(이름), 끝표.format(이름)
    if s not in 글 or e not in 글:
        return 글
    i = 글.index(s) + len(s)
    j = 글.index(e)
    return 글[:i] + "\n" + 내용.rstrip("\n") + "\n" + 글[j:]


def 블록읽기(글: str, 이름: str) -> str | None:
    s, e = 시작표.format(이름), 끝표.format(이름)
    if s not in 글 or e not in 글:
        return None
    return 글[글.index(s) + len(s):글.index(e)].strip("\n")


def 블록이름들(글: str) -> list[str]:
    return re.findall(r"<!-- BEGIN GENERATED: (.+?) -->", 글)


def 만들것(뿌리: Path, c: dict | None = None) -> dict[str, str]:
    """경로 → 원본에서 만든 내용. 블록이 든 파일은 그 파일 전체(블록만 바뀐 것)."""
    c = c or 설정(뿌리)
    나온것 = {
        "STATUS.md": 지금모듈.STATUS(뿌리, c),
        "README.md": 지금모듈.README(뿌리, c),
    }
    p = 뿌리 / "CLAUDE.md"
    if p.is_file():
        글 = p.read_text(encoding="utf-8")
        새 = 블록바꾸기(글, "목차", 지금모듈.목차표(뿌리, c))
        if 새 != 글:
            나온것["CLAUDE.md"] = 새
    return 나온것


def 생성파일인가(뿌리: Path, p: Path | str, c: dict | None = None) -> bool:
    r = rel(뿌리, p)
    return r in ("STATUS.md", "README.md", "worklog.md", "memory/어긋남.md")


def 다른것(뿌리: Path, c: dict | None = None) -> list[str]:
    """원본과 다른 생성 파일의 이름."""
    c = c or 설정(뿌리)
    문제 = []
    for r, 내용 in 만들것(뿌리, c).items():
        p = 뿌리 / r
        if not p.is_file():
            문제.append(f"{r} 가 없다. `ops build`")
        elif p.read_text(encoding="utf-8") != 내용:
            문제.append(f"{r} 가 원본과 다르다. `ops build`")
    return 문제


def 만들기(뿌리: Path, c: dict | None = None) -> list[str]:
    c = c or 설정(뿌리)
    한것 = []
    for r, 내용 in 만들것(뿌리, c).items():
        p = 뿌리 / r
        if not p.is_file() or p.read_text(encoding="utf-8") != 내용:
            p.write_text(내용, encoding="utf-8")
            한것.append(r)
    n = 작업로그.만들기(뿌리)
    if n:
        한것.append(f"worklog.md ({n})")
    import 어긋남
    if 어긋남.만들기(뿌리, c):
        한것.append("memory/어긋남.md")
    return 한것
