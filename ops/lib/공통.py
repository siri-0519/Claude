"""공통 — 뿌리 · 설정 · git · 훅 입출력.

이 레포는 틀이다. 복사한 레포는 `.ops.yml` 만 제 것으로 고친다. 기계는 그대로 둔다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

설정파일 = ".ops.yml"

기본설정 = {
    "이름": "틀",
    "소개": "문서 레포의 틀이다.",
    "주제파일": ["*.md"],
    "제외": ["README.md", "STATUS.md", "CLAUDE.md", "worklog.md", "memory/**", "ops/**", ".claude/**"],
    "표시": ["확인", "제안"],
    "표시패턴": r"\[(확인|제안)(?:\s[^\]]*)?\]",
    "결정로그": "",
    "목차": [],
    "지금절": {"제목": "지금", "최대줄": 10},
    "파일최대바이트": 30000,
    "목차최대줄": 800,
    "절최대줄": 120,
    "판정": {"모델": "haiku", "명령": "claude", "시간": 180, "끄기": False},
    "허용낱말": "ops/rules/낱말.txt",
    "상대날짜": ["어제", "엊그제", "그제", "내일", "모레", "아까", "방금", "지난번"],
    "기본브랜치": "main",
    "세션브랜치": "claude/",
}


def 뿌리찾기(p: Path | None = None) -> Path:
    p = (p or Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())).resolve()
    for d in [p if p.is_dir() else p.parent, *p.parents]:
        if (d / 설정파일).is_file():
            return d
    raise SystemExit(f"{설정파일} 을 여기서도 위에서도 못 찾았다. 틀에서 복사한 레포가 아니다.")


def 설정(뿌리: Path) -> dict:
    d = dict(기본설정)
    본 = yaml.safe_load((뿌리 / 설정파일).read_text(encoding="utf-8")) or {}
    for k, v in 본.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            m = dict(d[k]); m.update(v); d[k] = m
        else:
            d[k] = v
    return d


def rel(뿌리: Path, p: Path | str) -> str:
    try:
        return str(Path(p).resolve().relative_to(뿌리.resolve()))
    except ValueError:
        return str(p)


def git(뿌리: Path, *a: str, ok: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(뿌리), *a], capture_output=True, text=True)
    if r.returncode != 0 and not ok:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.rstrip("\n")


def 오늘() -> str:
    return date.today().isoformat()


def 지금시각() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def 주제파일들(뿌리: Path, c: dict | None = None) -> list[Path]:
    c = c or 설정(뿌리)
    나온것: list[Path] = []
    for g in c["주제파일"]:
        for p in sorted(뿌리.glob(g)):
            if p.is_file() and p.suffix == ".md":
                나온것.append(p)
    def 빠지나(p: Path) -> bool:
        r = rel(뿌리, p)
        for g in c["제외"]:
            if Path(r).match(g) or (g.endswith("/**") and r.startswith(g[:-3] + "/")):
                return True
        return r.endswith(".meta.yml")
    return [p for p in dict.fromkeys(나온것) if not 빠지나(p)]


def 훅입력() -> dict:
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}


def 문맥출력(자리: str, 글: str) -> None:
    이름 = {"session_start": "SessionStart", "user_prompt_submit": "UserPromptSubmit",
            "pre_tool_use": "PreToolUse", "post_tool_use": "PostToolUse", "stop": "Stop"}[자리]
    print(json.dumps({"hookSpecificOutput": {"hookEventName": 이름, "additionalContext": 글}},
                     ensure_ascii=False))


def 막기(말: str) -> int:
    """훅에서 도구 호출이나 답을 막는다. 2 를 돌려주면 Claude Code 가 stderr 를 보여 주고 막는다."""
    print(말, file=sys.stderr)
    return 2


def 상태파일(뿌리: Path, 이름: str) -> Path:
    d = 뿌리 / ".meta"
    d.mkdir(exist_ok=True)
    return d / 이름


def 상태읽기(뿌리: Path, 이름: str) -> dict:
    p = 상태파일(뿌리, 이름)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def 상태쓰기(뿌리: Path, 이름: str, d: dict) -> None:
    상태파일(뿌리, 이름).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def 로그추가(뿌리: Path, 종류: str, 제목: str, 본문: str = "", 참조: list[str] | None = None) -> Path:
    d = 뿌리 / "memory" / "log"
    d.mkdir(parents=True, exist_ok=True)
    p = d / (오늘()[:7] + ".jsonl")
    항 = {"때": 지금시각(), "종류": 종류, "제목": 제목}
    if 본문:
        항["본문"] = 본문
    if 참조:
        항["참조"] = 참조
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(항, ensure_ascii=False) + "\n")
    return p


def 로그읽기(뿌리: Path, n: int = 20) -> list[dict]:
    d = 뿌리 / "memory" / "log"
    항들: list[dict] = []
    for p in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                항들.append(json.loads(ln))
            except ValueError:
                pass
    return 항들[-n:]


def 횟수추가(뿌리: Path, 누가: str, 규칙: str, 어디: str = "") -> None:
    d = 뿌리 / "memory"
    d.mkdir(exist_ok=True)
    항 = {"날": 오늘(), "누가": 누가, "규칙": 규칙}
    if 어디:
        항["어디"] = 어디
    with (d / "횟수.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(항, ensure_ascii=False) + "\n")


def 횟수요약(뿌리: Path, 주: int = 4) -> list[tuple[str, str, int]]:
    p = 뿌리 / "memory" / "횟수.jsonl"
    if not p.is_file():
        return []
    from collections import Counter
    c: Counter = Counter()
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        try:
            y, w, _ = date.fromisoformat(d["날"]).isocalendar()
        except (KeyError, ValueError):
            continue
        c[(f"{y}-W{w:02d}", f"{d.get('누가','?')}·{d.get('규칙','?')}")] += 1
    항 = sorted(c.items(), reverse=True)
    return [(k[0], k[1], v) for k, v in 항][: 40]


제목꼴 = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def 절나누기(글: str) -> list[tuple[int, str, int, int]]:
    """(수준, 제목, 시작줄, 끝줄) 목록. 줄 번호는 0부터."""
    줄 = 글.split("\n")
    나온것: list[tuple[int, str, int, int]] = []
    울타리 = False
    for i, ln in enumerate(줄):
        if ln.startswith("```"):
            울타리 = not 울타리
            continue
        if 울타리:
            continue
        m = 제목꼴.match(ln)
        if m:
            나온것.append((len(m.group(1)), m.group(2), i, len(줄)))
    for k in range(len(나온것) - 1):
        수준, 제목, s, _ = 나온것[k]
        e = 나온것[k + 1][2]
        나온것[k] = (수준, 제목, s, e)
    return 나온것


def 옛줄전부(뿌리: Path, c: dict | None = None) -> set[str]:
    """HEAD 에 있는 주제 파일 전부의 줄(양끝 공백을 뗀 것). 파일을 나누거나 옮겨도 이 줄들은 새 줄이 아니다."""
    c = c or 설정(뿌리)
    s: set[str] = set()
    for p in 주제파일들(뿌리, c):
        r = rel(뿌리, p)
        if git(뿌리, "ls-files", "--error-unmatch", "--", r):
            s.update(x.strip() for x in git(뿌리, "show", f"HEAD:{r}").split("\n"))
    s.discard("")
    return s
