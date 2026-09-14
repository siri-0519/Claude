"""훅 — Claude Code 의 다섯 자리에서 하는 일. `.claude/hooks/hook.py <자리>` 가 여기로 넘긴다.

    session_start        원격을 받고(fetch --prune) worklog 와 어긋남 목록을 다시 만들고, 목록 전체와 레포 상태 한 줄을 문맥에 넣는다
    user_prompt_submit   어긋남이 있으면 "어긋남 N개, 이번 세션에 새로 M개" 한 줄
    pre_tool_use         Edit · Write: 생성 파일 · 생성 블록을 막고, 주제 파일의 새 줄에서 상대 날짜와 표시 없는 주장을 막고, 「고칠 때」 규칙을 넣는다
                         Bash: 이력을 다시 쓰는 push · 기계 지우기 · 생성 파일로의 재지정을 막는다
    post_tool_use        어긋남 목록을 다시 만들고 새로 오른 것을 알린다
    stop                 상대 날짜 → 판정 모델(답할 때 규칙 + 낱말 후보) → 커밋 · push → 어긋남 개수

막는 것은 exit 2 + stderr 다. 훅이 예상 못 한 이유로 죽어도 세션을 막지 않는다 — 그 경우 stderr 에 한 줄 남기고 0 이다.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path

from 공통 import (설정, git, rel, 주제파일들, 훅입력, 문맥출력, 막기, 상태읽기, 상태쓰기, 횟수추가, 지금시각)

세션파일 = "session.json"


def 돌리기(자리: str, 뿌리: Path) -> int:
    p = 훅입력()
    c = 설정(뿌리)
    if os.environ.get("OPS_HOOKS") == "off" or os.environ.get("OPS_판정중"):
        return 0                                   # 훅을 고칠 때 · 판정 세션 안
    try:
        return {"session_start": 세션시작, "user_prompt_submit": 물음직전, "pre_tool_use": 도구직전,
                "post_tool_use": 도구직후, "stop": 답끝}[자리](뿌리, c, p)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — 훅이 세션을 죽이면 안 된다
        자리이름 = {"session_start": "세션 시작", "user_prompt_submit": "물음 직전", "pre_tool_use": "도구 직전",
                    "post_tool_use": "도구 직후", "stop": "답 끝"}.get(자리, 자리)
        print(f"[훅 · {자리이름}] 훅이 오류로 죽었다. 막지 않았고 이번 호출에는 검사가 안 걸렸으니 답을 스스로 한 번 더 본다. "
              f"오류가 훅 코드(ops/lib/훅.py)의 것이면 고치고, 아니면 사용자에게 알린다. 오류 내용(traceback):\n"
              + traceback.format_exc()[-600:], file=sys.stderr)
        return 0


# ----------------------------------------------------------- 세션 시작 ----

def 레포상태줄(뿌리: Path, c: dict) -> str:
    가지 = git(뿌리, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(뿌리, "log", "-1", "--format=%h")
    제목 = git(뿌리, "log", "-1", "--format=%s")
    변경 = len([x for x in git(뿌리, "status", "--porcelain").split("\n") if x.strip()])
    줄 = f"레포 {c['이름']}: 브랜치 {가지} / 마지막 커밋 {head} (메시지 첫 줄: {제목})"
    if 변경:
        줄 += f" / 커밋 안 한 변경 {변경}개 — 지난 세션이 남긴 것이어도 git status 로 보고 첫 답 안에 커밋한다"
    if 가지 and 가지 != "HEAD" and not git(뿌리, "rev-parse", "--verify", "-q", f"origin/{가지}"):
        줄 += f" / 이 브랜치는 아직 원격에 없다 — git push -u origin {가지}"
    return 줄


def 세션시작(뿌리: Path, c: dict, p: dict) -> int:
    import 어긋남, 작업로그
    git(뿌리, "fetch", "--prune", "--quiet", "origin")
    if git(뿌리, "config", "core.hooksPath") != "ops/hooks":
        git(뿌리, "config", "core.hooksPath", "ops/hooks")
    작업로그.만들기(뿌리)
    어긋남.만들기(뿌리, c)
    _, 열쇠들, _ = 어긋남.목록(뿌리, c)
    상태쓰기(뿌리, 세션파일, {"시작": 지금시각(), "어긋남": 열쇠들, "되돌림": 0, "규칙넣음": []})
    글 = [레포상태줄(뿌리, c),
          f"고친 것은 이 세션의 브랜치로 커밋하고 push 한다. 기본 브랜치는 {c['기본브랜치']} 다. 답이 끝날 때 훅이 커밋 · push 를 확인한다.",
          "아래 어긋남 목록의 줄은 사용자의 요청과 상관없어도 이번 세션의 첫 답 안에서 처리하고, 처리한 것을 답에 한 줄로 알린다.", ""]
    목록 = (뿌리 / 어긋남.목록파일).read_text(encoding="utf-8") if (뿌리 / 어긋남.목록파일).is_file() else ""
    if 열쇠들:
        글.append(목록.strip())
    else:
        글.append("어긋남 목록(memory/어긋남.md)은 비어 있다.")
    if p.get("source") in ("compact", "resume"):
        글.append("")
        글.append("대화가 요약으로 바뀌었다. 요약 앞에서 읽은 파일은 문맥에 없다. 이번 물음에 걸리는 주제 파일(CLAUDE.md 「언제 무엇을 읽나」 표에서 물음의 말이 든 행의 파일)을 답하기 전에 다시 읽는다. 「고칠 때」 규칙도 다음 저장 때 다시 들어온다.")
    문맥출력("session_start", "\n".join(글))
    return 0


# ----------------------------------------------------------- 물음 직전 ----

def 어긋남개수(뿌리: Path, c: dict, 다시: bool = False) -> tuple[int, list[str]]:
    """(전체 수, 이번 세션에 새로 오른 열쇠들)."""
    import 어긋남
    if 다시:
        어긋남.만들기(뿌리, c)
    _, 열쇠들, _ = 어긋남.목록(뿌리, c)
    옛 = set(상태읽기(뿌리, 세션파일).get("어긋남") or [])
    return len(열쇠들), [k for k in 열쇠들 if k not in 옛]


def 어긋남한줄(n: int, 새로: list[str]) -> str:
    if 새로:
        return (f"어긋남 목록(memory/어긋남.md)에 {n}줄, 이번 세션에 새로 오른 것 {len(새로)}줄: " + " / ".join(새로)
                + " — 새로 오른 줄은 이번 답에서 고치거나 ops ack 한다.")
    return f"어긋남 목록(memory/어긋남.md)에 {n}줄, 이번 세션에 새로 오른 것 없음"


def 물음직전(뿌리: Path, c: dict, p: dict) -> int:
    n, 새로 = 어긋남개수(뿌리, c)
    if n:
        문맥출력("user_prompt_submit", 어긋남한줄(n, 새로))
    return 0


# ----------------------------------------------------------- 도구 직전 ----

def _경로(p: dict) -> str:
    ti = p.get("tool_input") or {}
    return str(ti.get("file_path") or ti.get("notebook_path") or "")


def _새글(뿌리: Path, p: dict, 지금글: str) -> str | None:
    """Edit · Write 가 만들 새 본문. 못 만들면 None."""
    ti = p.get("tool_input") or {}
    이름 = p.get("tool_name")
    if 이름 == "Write":
        return str(ti.get("content") or "")
    if 이름 == "Edit":
        old, new = str(ti.get("old_string") or ""), str(ti.get("new_string") or "")
        if old and old in 지금글:
            return 지금글.replace(old, new) if ti.get("replace_all") else 지금글.replace(old, new, 1)
        return None
    if 이름 == "MultiEdit":
        글 = 지금글
        for e in ti.get("edits") or []:
            old, new = str(e.get("old_string") or ""), str(e.get("new_string") or "")
            if old and old in 글:
                글 = 글.replace(old, new) if e.get("replace_all") else 글.replace(old, new, 1)
        return 글
    return None


def 도구직전(뿌리: Path, c: dict, p: dict) -> int:
    import 기계, 생성, 표시, 판정
    이름 = p.get("tool_name") or ""
    if 이름 == "Bash":
        문제 = 기계.셸검사(str((p.get("tool_input") or {}).get("command") or ""), 뿌리, c)
        return 막기("\n".join(문제)) if 문제 else 0
    if 이름 not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return 0
    경로 = _경로(p)
    if not 경로:
        return 0
    q = Path(경로)
    q = (q if q.is_absolute() else Path(p.get("cwd") or os.getcwd()) / q).resolve()
    try:
        r = str(q.relative_to(뿌리.resolve()))
    except ValueError:
        return 0                                   # 이 레포 밖
    if 생성.생성파일인가(뿌리, r):
        return 막기(생성.생성파일설명(뿌리, r, c))
    지금글 = q.read_text(encoding="utf-8") if q.is_file() else ""
    새글 = _새글(뿌리, p, 지금글)
    if 새글 is None:
        return 0
    if 지금글 and 생성.블록이름들(지금글):
        for b in 생성.블록이름들(지금글):
            if 생성.블록읽기(지금글, b) != 생성.블록읽기(새글, b):
                return 막기(f"{r} 의 「{b}」 블록(<!-- BEGIN GENERATED: {b} --> 와 <!-- END GENERATED: {b} --> 사이)은 스크립트가 만든다. "
                          f"표의 첫째 · 둘째 칸은 .ops.yml 의 목차 항목(말 · 파일)에서, 셋째 칸은 그 주제 파일의 「{c['지금절']['제목']}」 절 첫 줄에서 온다. "
                          f"그 사이는 손으로 고치지 않고, 같은 내용을 블록 밖에 적지도 않는다. 블록 밖의 다른 글은 고쳐도 된다. "
                          f"바꾸려는 것이 첫째 · 둘째 칸이면 .ops.yml 의 그 항목을, 셋째 칸이면 그 주제 파일의 「{c['지금절']['제목']}」 절 첫 줄을 고치고 `ops build` 를 돌린다.")
    if r == "CLAUDE.md":
        문제 = 기계.목차크기(뿌리, c, 새글)
        if 문제:
            return 막기("\n".join(문제))
    주제 = {rel(뿌리, t) for t in 주제파일들(뿌리, c)}
    if r not in 주제 and not (q.suffix == ".md" and r not in c["제외"] and not r.startswith(("ops/", ".claude/", "memory/"))):
        return 0
    from 공통 import 옛줄전부
    옛 = 지금글 + "\n" + "\n".join(옛줄전부(뿌리, c))
    문제 = [f"{r} {x}" for x in 기계.상대날짜_새줄(새글, c, 옛)]
    문제 += [f"{r} {x}" for x in 표시.검사_글(새글, c, 옛)]
    if 문제:
        from 공통 import 오늘
        return 막기(f"저장하기 전에 걸렸다. 아래 줄만 고쳐서 같은 저장을 다시 한다. 다른 줄은 손대지 않는다. 오늘은 {오늘()} 다. "
                  "누구의 말인지 모르면 [제안] 이다.\n" + "\n".join(문제))
    s = 상태읽기(뿌리, 세션파일)
    if "고칠 때" not in (s.get("규칙넣음") or []):
        규칙 = 판정.규칙글(뿌리, "고칠 때")
        if 규칙:
            s.setdefault("규칙넣음", []).append("고칠 때")
            상태쓰기(뿌리, 세션파일, s)
            문맥출력("pre_tool_use", "문서를 고칠 때의 판단 규칙이다. 판단 규칙은 스크립트가 못 보고 다른 모델이 판정하는 규칙이다. "
                     "이 글은 막는 것이 아니라 하려던 저장은 그대로 된다. 이 세션에 지금 한 번만 넣으니(요약 뒤에는 다시 넣는다), "
                     "이번 저장과 이 세션의 다음 저장에도 적용한다.\n\n" + 규칙)
    return 0


# ----------------------------------------------------------- 도구 직후 ----

def 도구직후(뿌리: Path, c: dict, p: dict) -> int:
    이름 = p.get("tool_name") or ""
    if 이름 not in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"):
        return 0
    if 이름 == "Bash" and not re.search(r"\b(git|ops|sed -i|>|mv|rm|cp)\b", str((p.get("tool_input") or {}).get("command") or "")):
        return 0
    import 어긋남
    어긋남.만들기(뿌리, c)
    _, 열쇠들, 항줄 = 어긋남.목록(뿌리, c)
    s = 상태읽기(뿌리, 세션파일)
    본것 = set(s.get("알린것") or []) | set(s.get("어긋남") or [])
    새로 = [k for k in 열쇠들 if k not in 본것]
    if 새로:
        s.setdefault("알린것", []).extend(새로)
        상태쓰기(뿌리, 세션파일, s)
        고친 = _경로(p) or str((p.get("tool_input") or {}).get("command") or "")[:60]
        문맥출력("post_tool_use", f"방금 고친 것({rel(뿌리, 고친) if 고친 else '?'}) 때문에 어긋남 목록에 새로 올랐다 (막지 않는다):\n" + "\n".join(항줄.get(k, "- " + k) for k in 새로)
                 + "\n이 답이 끝나기 전에 파생물을 출처의 바뀐 절에 맞춰 고치고 `ops ack <파생물>` 을 돌리거나, 고칠 것이 없으면 "
                   "`ops ack <파생물> --그대로 \"<이유>\"` (파생물을 고치지 않고 둔다는 뜻) 를 돌린다. "
                   "브랜치 · 폐기된 번호 · 생성 파일 줄은 memory/어긋남.md 의 그 절에 적힌 대로 한다.")
    return 0


# --------------------------------------------------------------- 답 끝 ----

def 답끝(뿌리: Path, c: dict, p: dict) -> int:
    import 기계, 낱말, 대화, 판정
    if p.get("stop_hook_active"):
        return 0
    t = p.get("transcript_path") or ""
    d = 대화.훑기(Path(t)) if t and Path(t).is_file() else {"답": "", "물음": "", "사용자글": [], "읽은파일": set(), "고친파일": set()}
    답 = d["답"]
    s = 상태읽기(뿌리, 세션파일)
    알림: list[str] = []
    if 답:
        걸린 = 기계.상대날짜(답, c)
        if 걸린:
            횟수추가(뿌리, "기계", "상대날짜")
            from 공통 import 오늘
            return 막기(f"답에 상대 날짜가 있다: {' '.join(걸린)} — 오늘({오늘()})에서 센 날짜로 바꾼다. 그 낱말이 든 문장만 고쳐서 그 문장만 다시 쓴다. 답 전체를 다시 붙이지 않는다.")
        규칙 = 판정.규칙글(뿌리, "답할 때")
        if 규칙 and len(답) > 80:
            후보 = 낱말.후보(답, 낱말.아는말(뿌리, c, d["사용자글"], set(d["읽은파일"])))
            바뀐 = [x[3:] for x in git(뿌리, "status", "--porcelain").split("\n") if x.strip()]
            어긴것, 오류 = 판정.부르기(뿌리, 판정.물음(d["물음"], 답, 규칙, 바뀐, 후보[:60], "답"), c)
            if 오류:
                알림.append(f"판정을 못 했다: {오류}")
            elif 어긴것:
                for x in 어긴것:
                    횟수추가(뿌리, "판정", x["규칙"], x["문장"][:80])
                return 막기(판정.되돌리는말(어긴것, 뿌리))
    문제 = 기계.브랜치(뿌리, c)
    if 문제 and int(s.get("되돌림") or 0) < 2:
        s["되돌림"] = int(s.get("되돌림") or 0) + 1
        상태쓰기(뿌리, 세션파일, s)
        return 막기("답을 끝내기 전에 커밋하고 push 한다. 이번 요청의 변경은 커밋 하나로 묶고, 메시지 첫 줄은 이번 요청의 핵심이다. "
                  "생성 파일이 원본과 다르면 먼저 `ops build` 를 돌리고 나서 커밋한다.\n" + "\n".join("- " + x for x in 문제))
    n, 새로 = 어긋남개수(뿌리, c, 다시=True)
    if n:
        알림.append(어긋남한줄(n, 새로))
    if 알림:
        print(json.dumps({"systemMessage": " / ".join(알림)}, ensure_ascii=False))
    return 0


# --------------------------------------------------------- 여러 레포 ----

def 라우트(자리: str, 위: Path) -> int:
    """레포 여럿을 한 디렉터리 아래 두고 그 위에서 세션을 열었을 때. ~/.claude/route.sh 가 부른다.

    .ops.yml 을 가진 레포마다 그 레포의 hook.py 를 돌린다. 파일이 걸린 자리(도구 직전 · 직후)는 그 파일이 든
    레포에서만, 답 끝은 이 세션에 파일을 고치거나 읽은 레포(없으면 서 있는 자리의 레포)에서만 돈다.
    """
    import subprocess
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        p = json.loads(raw) if raw.strip() else {}
    except ValueError:
        p = {}
    레포들 = [d for d in sorted(위.iterdir()) if d.is_dir() and (d / ".ops.yml").is_file() and (d / ".claude/hooks/hook.py").is_file()]
    if not 레포들:
        return 0
    고를것 = 레포들
    if 자리 in ("pre_tool_use", "post_tool_use"):
        ti = p.get("tool_input") or {}
        후보 = [str(ti.get(k) or "") for k in ("file_path", "notebook_path")] + re.findall(r"[\w./~-]+", str(ti.get("command") or ""))
        cwd = Path(p.get("cwd") or os.getcwd())
        고를것 = []
        for r in 레포들:
            for s in 후보:
                if not s or s.startswith("-"):
                    continue
                q = Path(os.path.expanduser(s))
                q = (q if q.is_absolute() else cwd / q)
                try:
                    q = q.resolve()
                except OSError:
                    continue
                if q == r.resolve() or r.resolve() in q.parents:
                    고를것.append(r); break
        if not 고를것:
            고를것 = [r for r in 레포들 if cwd.resolve() == r.resolve() or r.resolve() in cwd.resolve().parents]
    elif 자리 == "stop":
        import 대화
        t = p.get("transcript_path") or ""
        d = 대화.훑기(Path(t)) if t and Path(t).is_file() else {"읽은파일": set(), "고친파일": set()}
        닿은 = set()
        for f in set(d["읽은파일"]) | set(d["고친파일"]):
            q = Path(f)
            for r in 레포들:
                if q.is_absolute() and (q == r.resolve() or r.resolve() in q.parents):
                    닿은.add(r)
        cwd = Path(p.get("cwd") or os.getcwd()).resolve()
        고를것 = sorted(닿은) or [r for r in 레포들 if cwd == r.resolve() or r.resolve() in cwd.parents] or 레포들[:1]
    코드 = 0
    for r in 고를것:
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(r))
        try:
            x = subprocess.run([sys.executable, str(r / ".claude/hooks/hook.py"), 자리], input=raw, text=True,
                               capture_output=True, cwd=str(r), env=env, timeout=230)
        except subprocess.TimeoutExpired:
            print(f"[훅] {r.name} {자리} 이 시간을 넘겼다", file=sys.stderr)
            continue
        if x.stdout:
            sys.stdout.write(x.stdout)
        if x.stderr:
            sys.stderr.write(x.stderr)
        if x.returncode == 2:
            코드 = 2
    return 코드
