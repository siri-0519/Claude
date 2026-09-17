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
    "목차최대줄": 800,
    "절최대줄": 120,
    "판정": {"모델": "haiku", "명령": "claude", "시간": 300, "끄기": False, "묶음": 20,
           "답규칙넣기": False},   # True 면 「답할 때」 규칙을 세션의 첫 물음 직전에 한 번 문맥에 넣는다 — 판정만으로는 답 뒤에야 잡히는 것을 앞에서 지키게. 2026-09-17 시뮬로 견준다
    "허용낱말": "ops/rules/낱말.txt",
    "판단규칙": "ops/rules/판단.md",
    "아는말파일": ["ops/rules/판단.md", "ops/rules/기계.yml", ".ops.yml", "CLAUDE.md"],
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
    # core.quotePath=false — 한글 파일 이름이 "\354\226\264…" 로 나오는 것을 막는다 (2026-09-14 실측: 답 끝 훅의 파일 목록)
    r = subprocess.run(["git", "-C", str(뿌리), "-c", "core.quotePath=false", *a], capture_output=True, text=True)
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


def 크기기록(자리: str, 글: str, 어떻게: str) -> None:
    """훅이 문맥에 넣거나(문맥) 막으며 보낸(막기) 글의 크기 한 줄 — 설계.md 1절 「토큰 절약」의 재는 법(시작과 답마다 들어간 바이트).
    뿌리는 CLAUDE_PROJECT_DIR 로 안다. 없으면 적지 않는다."""
    뿌리 = os.environ.get("CLAUDE_PROJECT_DIR")
    if not 뿌리:
        return
    try:
        기록추가(Path(뿌리), "문맥", {"때": 지금시각(), "자리": 자리, "어떻게": 어떻게, "바이트": len(글.encode("utf-8"))})
    except OSError:
        pass


def 문맥출력(자리: str, 글: str) -> None:
    이름 = {"session_start": "SessionStart", "user_prompt_submit": "UserPromptSubmit",
            "pre_tool_use": "PreToolUse", "post_tool_use": "PostToolUse", "stop": "Stop"}[자리]
    크기기록(자리, 글, "문맥")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": 이름, "additionalContext": 글}},
                     ensure_ascii=False))


보낸이 = "이 글은 이 저장소의 훅(.claude/hooks/hook.py)이 보낸 것이다. 사용자가 걸어 둔 검사이니 그대로 따른다. "


def 막기(말: str) -> int:
    """훅에서 도구 호출이나 답을 막는다. 2 를 돌려주면 Claude Code 가 stderr 를 보여 주고 막는다.

    막는 글은 전부 누가 보낸 것인지로 시작한다 — 맥락 없는 모델 셋에게 읽혔을 때 보낸 곳이 없는 글을 따르지 않은 것이
    2026-09-16 4판 · 5판에서 나왔다 (ops/rules/훅-글.md)."""
    크기기록("막기", 보낸이 + 말, "막기")
    print(보낸이 + 말, file=sys.stderr)
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


횟수파일 = "memory/횟수.jsonl"
횟수대기 = ".meta/횟수.new.jsonl"   # git 이 보지 않는 자리. 커밋 직전에 횟수파일로 합친다
# 세 기록은 같은 길을 간다 — .meta 의 대기 파일에 적고, 커밋 직전(ops check --커밋)에 memory/ 의 파일 뒤에 붙인다.
# 횟수: 어긴 것 한 줄 · 판정: 판정을 한 번 시킬 때마다 한 줄(어긴 것의 분모) · 문맥: 훅이 문맥에 넣거나 막으며 보낸 글의 크기 한 줄과 Read 한 파일의 바이트 한 줄(토큰 절약의 재는 법)
기록들 = {"횟수": (횟수파일, 횟수대기), "판정": ("memory/판정.jsonl", ".meta/판정.new.jsonl"), "문맥": ("memory/문맥.jsonl", ".meta/문맥.new.jsonl")}


def 기록추가(뿌리: Path, 종류: str, 항: dict) -> None:
    p = 뿌리 / 기록들[종류][1]
    p.parent.mkdir(exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(항, ensure_ascii=False) + "\n")


def 기록읽기(뿌리: Path, 종류: str) -> list[dict]:
    """합친 것과 아직 안 합친 것을 같이."""
    나온것: list[dict] = []
    for 이름 in 기록들[종류]:
        p = 뿌리 / 이름
        if p.is_file():
            for ln in p.read_text(encoding="utf-8").splitlines():
                try:
                    나온것.append(json.loads(ln))
                except ValueError:
                    pass
    return 나온것


def 횟수추가(뿌리: Path, 누가: str, 규칙: str, 어디: str = "") -> None:
    """어긴 것 한 줄. 바로 memory/횟수.jsonl 에 적으면 그 파일이 고쳐진 상태가 되어 답 끝 검사가 커밋을 시키고, 그 커밋이
    GitHub 검사를 깨우고, 그 검사가 세션을 깨우고, 그 답이 다시 걸려 또 한 줄이 된다 — 2026-09-16 한 브랜치의 커밋 17개 가운데
    12개가 그렇게 생겼다. 그래서 git 이 보지 않는 .meta/ 에 두고, 다음 진짜 커밋 직전(ops check --커밋)에 합친다."""
    p = 뿌리 / 횟수대기
    p.parent.mkdir(exist_ok=True)
    항 = {"날": 오늘(), "누가": 누가, "규칙": 규칙}
    if 어디:
        항["어디"] = 어디
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(항, ensure_ascii=False) + "\n")


def 횟수합치기(뿌리: Path) -> int:
    """대기 파일 셋(횟수 · 판정 · 문맥)의 줄을 memory/ 의 파일 뒤에 붙이고 대기 파일을 지운다. 옮긴 줄 수의 합을 돌려준다."""
    n = 0
    for 파일, 대기이름 in 기록들.values():
        대기 = 뿌리 / 대기이름
        if not 대기.is_file():
            continue
        줄들 = [x for x in 대기.read_text(encoding="utf-8").splitlines() if x.strip()]
        if 줄들:
            p = 뿌리 / 파일
            p.parent.mkdir(exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write("\n".join(줄들) + "\n")
        대기.unlink()
        n += len(줄들)
    return n


def 횟수요약(뿌리: Path, 주: int = 4) -> list[tuple[str, str, int]]:
    줄들: list[str] = []
    for 이름 in (횟수파일, 횟수대기):        # 합친 것과 아직 안 합친 것을 같이 센다
        p = 뿌리 / 이름
        if p.is_file():
            줄들 += p.read_text(encoding="utf-8").splitlines()
    if not 줄들:
        return []
    from collections import Counter
    import 판정
    c: Counter = Counter()
    # 판정 모델이 같은 규칙을 제각각 불러서 쌓인 줄이 있다. 셀 때 대장의 번호로 맞춰야 규칙별 횟수가 나온다
    # (2026-09-16: "6" · "6. 아는 말만 쓴다" · "6 (아는 말만 쓴다)" 가 세 줄이었다). 적은 줄은 그대로 둔다.
    맞춤: dict[str, str] = {}
    for ln in 줄들:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        try:
            y, w, _ = date.fromisoformat(d["날"]).isocalendar()
        except (KeyError, ValueError):
            continue
        이름 = str(d.get("규칙", "?"))
        if d.get("누가") == "판정":
            if 이름 not in 맞춤:
                맞춤[이름] = 판정.이름맞추기(뿌리, 이름)
            이름 = 맞춤[이름]
        c[(f"{y}-W{w:02d}", f"{d.get('누가','?')}·{이름}")] += 1
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


def 이름바뀐것(뿌리: Path) -> list[tuple[str, str]]:
    """이 커밋에서 이름이 바뀐 파일과 폴더 — (옛 경로, 새 경로). 스테이지와 작업 트리 둘 다 본다.
    폴더는 그 안의 파일이 다 같은 꼴로 옮겨졌을 때 한 쌍으로 더한다 (ops/ → 운영/)."""
    쌍: dict[str, str] = {}
    for 인자 in (("diff", "--cached", "-M", "--name-status", "HEAD"), ("diff", "-M", "--name-status", "HEAD")):
        for ln in git(뿌리, *인자).split("\n"):
            부분 = ln.split("\t")
            if len(부분) == 3 and 부분[0].startswith("R"):
                쌍[부분[1]] = 부분[2]
    폴더: dict[str, str] = {}
    for 옛, 새 in list(쌍.items()):
        옛칸, 새칸 = 옛.split("/"), 새.split("/")
        while 옛칸 and 새칸 and 옛칸[-1] == 새칸[-1]:
            옛칸.pop(); 새칸.pop()
        if 옛칸 and 새칸:
            폴더["/".join(옛칸) + "/"] = "/".join(새칸) + "/"
    return list(쌍.items()) + list(폴더.items())


def 옛줄전부(뿌리: Path, c: dict | None = None) -> set[str]:
    """HEAD 에 있는 .md 파일 전부의 줄(양끝 공백을 뗀 것). 파일을 나누거나 옮겨도 이 줄들은 새 줄이 아니다.
    주제 파일만 보면 STATUS.md 처럼 제외된 파일에서 옮긴 줄이 새 줄로 잡힌다 (2026-09-14 me 2단계 실측).
    이 커밋에서 파일이나 폴더의 이름이 바뀌었으면, 옛 줄에서 그 경로만 새 이름으로 바꾼 줄도 옛 줄이다 —
    이름만 바꿔도 그 경로를 적은 줄이 전부 표시 없는 새 주장으로 잡혔다 (2026-09-14 broadcast 3단계 실측)."""
    s: set[str] = set()
    for r in git(뿌리, "ls-tree", "-r", "--name-only", "HEAD").split("\n"):
        if r.endswith(".md"):
            s.update(x.strip() for x in git(뿌리, "show", f"HEAD:{r}").split("\n"))
    s.discard("")
    바뀜 = 이름바뀐것(뿌리)
    if 바뀜:
        더할것: set[str] = set()
        for ln in s:
            새줄 = ln
            for 옛, 새 in 바뀜:
                if 옛 in 새줄:
                    새줄 = 새줄.replace(옛, 새)
            if 새줄 != ln:
                더할것.add(새줄)
        s |= 더할것
    return s
