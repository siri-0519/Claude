"""기계 규칙 — ops/rules/기계.yml 의 대장을 읽고, 이름마다의 검사를 돈다.

    ops check          지금 작업 트리에서 걸리는 것
    ops check --커밋   스테이지된 것만 (pre-commit 이 부른다)
    ops rules          대장을 보인다
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from 공통 import 설정, git, rel, 주제파일들, 절나누기, 옛줄전부

대장파일 = "ops/rules/기계.yml"
제목괄호 = re.compile(r"「.*?」")
자리들 = ("저장직전", "명령직전", "도구직후", "답끝", "커밋직전", "push직전", "세션시작")


def 대장(뿌리: Path) -> list[dict]:
    p = 뿌리 / 대장파일
    if not p.is_file():
        return []
    return yaml.safe_load(p.read_text(encoding="utf-8")) or []


def 대장검사(뿌리: Path) -> list[str]:
    """규칙마다 네 칸이 다 있나. 없으면 커밋을 막는다."""
    문제 = []
    이름들: set[str] = set()
    for i, r in enumerate(대장(뿌리), 1):
        for k in ("이름", "문장", "자리", "검사"):
            if not r.get(k):
                문제.append(f"{대장파일} {i}번째 규칙에 {k} 칸이 없다")
        for a in r.get("자리") or []:
            if a not in 자리들:
                문제.append(f"{대장파일} {r.get('이름', i)}: 자리 {a} 는 없는 자리다 ({' · '.join(자리들)})")
        if r.get("이름") in 이름들:
            문제.append(f"{대장파일}: 이름 {r['이름']} 이 겹친다")
        이름들.add(r.get("이름"))
    return 문제


def 보이기(뿌리: Path) -> str:
    줄 = ["| 이름 | 규칙 | 자리 | 검사 |", "|---|---|---|---|"]
    for r in 대장(뿌리):
        줄.append(f"| {r.get('이름','')} | {r.get('문장','')} | {' · '.join(r.get('자리') or [])} | {r.get('검사','')} |")
    return "\n".join(줄)


# ------------------------------------------------------------- 검사들 ----

def 상대날짜(글: str, c: dict) -> list[str]:
    본문 = 제목괄호.sub("", 글)
    본문 = re.sub(r"```.*?```", "", 본문, flags=re.S)
    본문 = re.sub(r"`[^`]*`", "", 본문)
    return sorted({w for w in c["상대날짜"] if w and w in 본문})


def 상대날짜_새줄(글: str, c: dict, 옛글: str = "") -> list[str]:
    옛 = set(x.strip() for x in 옛글.split("\n"))
    문제 = []
    울타리 = False
    for i, ln in enumerate(글.split("\n"), 1):
        if ln.startswith("```"):
            울타리 = not 울타리
            continue
        if 울타리 or ln.strip() in 옛:
            continue
        걸린 = 상대날짜(ln, c)
        if 걸린:
            문제.append(f"{i}줄: {' '.join(걸린)} — 날짜로 적는다: {ln.strip()[:50]}")
    return 문제


def 목차크기(뿌리: Path, c: dict, 글: str | None = None) -> list[str]:
    p = 뿌리 / "CLAUDE.md"
    if 글 is None:
        if not p.is_file():
            return []
        글 = p.read_text(encoding="utf-8")
    줄수 = len(글.split("\n"))
    문제 = []
    if 줄수 > int(c["목차최대줄"]):
        문제.append(f"CLAUDE.md 가 {줄수}줄이다. {c['목차최대줄']}줄 안으로 줄인다")
    for 수준, 제목, s, e in 절나누기(글):
        if 수준 == 2 and e - s > int(c["절최대줄"]):
            문제.append(f"CLAUDE.md 의 「{제목}」 절이 {e - s}줄이다. {c['절최대줄']}줄 안으로 줄인다")
    return 문제


def 파일크기(뿌리: Path, c: dict) -> list[str]:
    최대 = int(c["파일최대바이트"])
    문제 = []
    for p in 주제파일들(뿌리, c):
        n = p.stat().st_size
        if n > 최대:
            문제.append(f"{rel(뿌리, p)} 가 {n} 바이트다. {최대} 바이트 안으로 절을 나눈다")
    return 문제


def 작업로그(뿌리: Path) -> list[str]:
    if "worklog.md" in git(뿌리, "diff", "--cached", "--name-only").split("\n"):
        return ["worklog.md 가 스테이지에 있다. 커밋하지 않는다: git rm --cached worklog.md"]
    return []


def 브랜치(뿌리: Path, c: dict) -> list[str]:
    """커밋 안 한 변경 · push 안 한 커밋 · 원격에 없는 브랜치."""
    문제 = []
    상태 = [x for x in git(뿌리, "status", "--porcelain").split("\n") if x.strip()]
    if 상태:
        문제.append(f"커밋 안 한 변경이 {len(상태)}개 있다: " + " ".join(x[3:] for x in 상태[:5]))
    가지 = git(뿌리, "rev-parse", "--abbrev-ref", "HEAD")
    if 가지 and 가지 != "HEAD":
        if not git(뿌리, "rev-parse", "--verify", "-q", f"origin/{가지}"):
            문제.append(f"브랜치 {가지} 가 원격에 없다: git push -u origin {가지}")
        else:
            n = git(뿌리, "rev-list", "--count", f"origin/{가지}..HEAD")
            if n and n != "0":
                문제.append(f"push 안 한 커밋이 {n}개 있다: git push origin {가지}")
    return 문제


보호자리 = ("ops", ".claude", "memory", ".ops.yml", ".git")


def 셸검사(명령: str, 뿌리: Path, c: dict) -> list[str]:
    """Bash 직전 — 이력을 다시 쓰는 push, 기계 지우기, 생성 파일로의 재지정."""
    import 생성
    문제 = []
    # heredoc 본문(cat > 파일 <<'EOF' … EOF)은 파일 내용이지 명령이 아니다 — 시험 코드의 글자가 걸렸다 (2026-09-14)
    명령 = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1(?:\n|$)", "<<HEREDOC\n", 명령, flags=re.S)
    if re.search(r"\bgit\b[^|;&]*\bpush\b[^|;&]*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s--delete\b|\s-d\b|\s\+\S|\s:\S)", 명령):
        문제.append("이력을 다시 쓰거나 원격 브랜치를 지우는 push 다. 하지 않는다")
    if re.search(r"\bgit\b[^|;&]*\b(filter-branch|filter-repo)\b", 명령):
        문제.append("이력을 다시 쓰는 명령이다. 하지 않는다")
    m = re.search(r"\brm\b\s+(-[a-zA-Z]*r[a-zA-Z]*|--recursive)\b(.*)", 명령)
    if m:
        for w in m.group(2).split():
            w2 = w.strip("'\"").rstrip("/")
            if w2.startswith("-"):
                continue
            base = w2.split("/")[0] if not w2.startswith("/") else rel(뿌리, w2).split("/")[0]
            if w2 in (".", "*", "/") or base in 보호자리 or rel(뿌리, w2) in 보호자리:
                문제.append(f"기계({w2})를 통째로 지우는 명령이다. 파일 이름을 대고 git rm 으로 지운다")
    for m in re.finditer(r"(?:>>?|\btee\b(?:\s+-a)?)\s*([\w./~-]+)", 명령):
        if 생성.생성파일인가(뿌리, m.group(1)):
            문제.append(f"{m.group(1)} 는 스크립트가 만든다. 원본을 고치고 `ops build` 를 돌린다")
    for m in re.finditer(r"\bsed\b\s+-i[^|;&]*?\s([\w./~-]+\.md)\b", 명령):
        if 생성.생성파일인가(뿌리, m.group(1)):
            문제.append(f"{m.group(1)} 는 스크립트가 만든다. 원본을 고치고 `ops build` 를 돌린다")
    return 문제


# ------------------------------------------------------------- 모아서 ----

def 지금검사(뿌리: Path, c: dict | None = None) -> list[str]:
    """작업 트리에서 지금 걸리는 것 전부 (ops check)."""
    import 생성, 지금, 표시
    c = c or 설정(뿌리)
    문제 = 대장검사(뿌리)
    문제 += 표시.검사_새줄(뿌리, c, 스테이지=False)
    옛 = "\n".join(옛줄전부(뿌리, c))
    for p in 주제파일들(뿌리, c):
        r = rel(뿌리, p)
        for x in 상대날짜_새줄(p.read_text(encoding="utf-8"), c, 옛):
            문제.append(f"{r} {x}")
    문제 += 목차크기(뿌리, c)
    문제 += 지금.검사(뿌리, c)
    문제 += 파일크기(뿌리, c)
    문제 += 생성.다른것(뿌리, c)
    return 문제


def 커밋검사(뿌리: Path, c: dict | None = None) -> list[str]:
    """스테이지에서 걸리는 것 전부 (pre-commit)."""
    import 생성, 지금, 표시
    c = c or 설정(뿌리)
    문제 = 대장검사(뿌리)
    문제 += 표시.검사_새줄(뿌리, c, 스테이지=True)
    문제 += 표시.제안이확인으로(뿌리, c, 스테이지=True)
    스테이지된 = [x for x in git(뿌리, "diff", "--cached", "--name-only").split("\n") if x]
    주제 = {rel(뿌리, p) for p in 주제파일들(뿌리, c)}
    옛 = "\n".join(옛줄전부(뿌리, c))
    for r in 스테이지된:
        if r not in 주제:
            continue
        새 = git(뿌리, "show", f":{r}")
        for x in 상대날짜_새줄(새, c, 옛):
            문제.append(f"{r} {x}")
    if "CLAUDE.md" in 스테이지된:
        문제 += 목차크기(뿌리, c, git(뿌리, "show", ":CLAUDE.md"))
    문제 += 지금.검사(뿌리, c)
    문제 += 파일크기(뿌리, c)
    문제 += 작업로그(뿌리)
    for x in 생성.다른것(뿌리, c):
        문제.append(x)
    for r in 생성.만들것(뿌리, c):
        if git(뿌리, "ls-files", "--error-unmatch", "--", r) and git(뿌리, "diff", "--name-only", "--", r):
            문제.append(f"{r} 가 스테이지와 다르다: git add {r}")
    return 문제
