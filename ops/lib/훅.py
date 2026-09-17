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

from 공통 import 보낸이
세션파일 = "session.json"


def 돌리기(자리: str, 뿌리: Path) -> int:
    p = 훅입력()
    c = 설정(뿌리)
    if os.environ.get("OPS_HOOKS") == "off" or os.environ.get("OPS_JUDGING"):
        return 0                                   # 훅을 고칠 때 · 판정 세션 안
    try:
        return {"session_start": 세션시작, "user_prompt_submit": 물음직전, "pre_tool_use": 도구직전,
                "post_tool_use": 도구직후, "stop": 답끝}[자리](뿌리, c, p)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — 훅이 세션을 죽이면 안 된다
        자리이름 = {"session_start": "세션 시작", "user_prompt_submit": "물음 직전", "pre_tool_use": "도구 직전",
                    "post_tool_use": "도구 직후", "stop": "답 끝"}.get(자리, 자리)
        글 = (f"[훅 · {자리이름}] 훅이 오류로 죽었다. 이번 호출에는 검사가 하나도 안 걸렸으니 답을 스스로 한 번 더 보고, "
              f"커밋 · push 도 스스로 한다. 오류가 훅 코드(ops/lib/훅.py)의 것이면 고치고, 아니면 사용자에게 훅이 죽었다고 알린다. "
              f"오류 내용(traceback):\n" + traceback.format_exc()[-600:])
        # stderr 에 exit 0 으로 내면 모델이 못 본다 — 2026-09-16 6판 S7 에서 셋 다 훅이 죽은 것을 모른 채 답을 끝냈다.
        # 답 끝이면 한 번 막아서(exit 2) 보게 하고, 되돌린 뒤(stop_hook_active)에는 다시 막지 않는다. 다른 자리는 문맥으로 넣는다.
        if 자리 == "stop" and not p.get("stop_hook_active"):
            print(글, file=sys.stderr)
            return 2
        if 자리 in ("session_start", "user_prompt_submit", "pre_tool_use", "post_tool_use"):
            문맥출력(자리, 글)
        print(글, file=sys.stderr)
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
                + " — 새로 오른 줄은 이번 답 안에서 파생물을 고치고 `ops ack <파생물>` 까지 한다. 목록을 읽는 것으로 끝내지 않는다.")
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
                          f"바꾸려는 것이 첫째 · 둘째 칸이면 .ops.yml 의 그 항목을, 셋째 칸이면 그 주제 파일의 「{c['지금절']['제목']}」 절 첫 줄을 고치고 `ops build` 를 돌린 뒤, 하려던 저장을 다시 한다.")
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
                  "누구의 말인지 모르면 [제안] 을 붙인다. 사용자에게 되묻지 않는다.\n" + "\n".join(문제))
    s = 상태읽기(뿌리, 세션파일)
    if "고칠 때" not in (s.get("규칙넣음") or []):
        규칙 = 판정.규칙글(뿌리, "고칠 때")
        if 규칙:
            s.setdefault("규칙넣음", []).append("고칠 때")
            상태쓰기(뿌리, 세션파일, s)
            문맥출력("pre_tool_use", 보낸이 + "문서를 고칠 때의 판단 규칙이다. 판단 규칙은 스크립트가 못 보고 다른 모델이 판정하는 규칙이다. "
                     "이 글은 막는 것이 아니라 하려던 저장은 그대로 된다. 이 세션에 지금 한 번만 넣으니(요약 뒤에는 다시 넣는다), "
                     "이번 저장과 이 세션의 다음 저장에도 적용한다.\n\n" + 규칙)
    return 0


# ----------------------------------------------------------- 도구 직후 ----

def 읽기기록(뿌리: Path, p: dict) -> None:
    """Read 마다 어느 파일을 몇 바이트 읽었나 — 토큰 절약의 재는 법(설계 1절)에서 빠져 있던 것. 2026-09-03 creation 에서 사용자가 손으로 센
    「큰 파일을 통째로 읽는 것이 가장 크다」를 훅이 늘 센다. 커밋 직전에 memory/문맥.jsonl 로 합쳐지고 `ops 토큰` 이 파일별로 보인다."""
    ti = p.get("tool_input") or {}
    경로 = str(ti.get("file_path") or "")
    if not 경로:
        return
    q = Path(경로)
    if not q.is_absolute():
        q = Path(p.get("cwd") or os.getcwd()) / q
    try:
        r = str(q.resolve().relative_to(뿌리.resolve()))
    except ValueError:
        return
    if not q.is_file():
        return
    limit = ti.get("limit")
    if limit:
        줄들 = q.read_bytes().split(b"\n")
        s = max(int(ti.get("offset") or 1) - 1, 0)
        n, 어떻게 = len(b"\n".join(줄들[s:s + int(limit)])), "일부"
    else:
        n, 어떻게 = q.stat().st_size, "통째로"
    from 공통 import 기록추가, 지금시각
    기록추가(뿌리, "문맥", {"때": 지금시각(), "자리": "읽기", "어떻게": 어떻게, "파일": r, "바이트": n})


def 도구직후(뿌리: Path, c: dict, p: dict) -> int:
    이름 = p.get("tool_name") or ""
    if 이름 == "Read":
        읽기기록(뿌리, p)
        return 0
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
                   "브랜치 · 폐기된 번호 · 생성 파일 줄은 memory/어긋남.md 의 그 절에 적힌 대로 한다. 목록을 읽는 것으로 끝내지 않는다.")
    return 0


# --------------------------------------------------------------- 답 끝 ----

def 판정기록(뿌리: Path, 자리: str, 어긴수: int, 오류: str, 초: float = 0.0, 모델: str = "") -> None:
    """판정을 한 번 시킬 때마다 한 줄 — 어긴 것만 적는 memory/횟수.jsonl 에는 분모가 없다 (2026-09-16 사용자 물음). 커밋 직전에 memory/판정.jsonl 로 합쳐진다.
    걸린 초와 모델도 적는다 — 판정 모델을 haiku 에서 sonnet 으로 바꿀지는 답마다 걸리는 시간으로 정한다 (2026-09-16 사용자가 내게 맡김)."""
    from 공통 import 기록추가, 지금시각
    기록추가(뿌리, "판정", {"때": 지금시각(), "자리": 자리, "어긴": 어긴수, "오류": 오류 or "", "초": round(초, 1), "모델": 모델})


def 기록커밋(뿌리: Path, c: dict, s: dict) -> str | None:
    """답 끝 검사가 .meta/ 에 적어 둔 기록(위반 횟수 · 판정 · 문맥 크기)을, 고친 것이 없고 push 도 끝난 답 끝에서
    한 시간에 한 번까지 훅이 스스로 memory/ 로 옮겨 커밋 · push 한다 (2026-09-17, 사용자 승인).

    기록은 다음 커밋에 얹는 것이 기본이다(기록 한 줄짜리 커밋을 안 만들려고, 2026-09-16). 그런데 커밋 없이 끝난 세션의 기록은
    이 세션이 도는 컴퓨터가 지워질 때 함께 사라진다. 답마다 커밋하면 기록 커밋이 쌓이므로(2026-09-16: 커밋 31개 중 16개)
    한 시간에 한 번이다. 돌려주는 것은 사용자에게 보일 한 줄이고, 아무것도 안 했으면 None 이다."""
    import subprocess, time
    from 공통 import 기록들, 횟수합치기
    if not any((뿌리 / 대기).is_file() and (뿌리 / 대기).stat().st_size for _, 대기 in 기록들.values()):
        return None
    if time.time() - float(s.get("기록커밋때") or 0) < 3600:
        return None
    if git(뿌리, "status", "--porcelain").strip():
        return None                                   # 다른 고친 것이 있으면 그 커밋에 얹는다 (ops check --커밋)
    가지 = git(뿌리, "rev-parse", "--abbrev-ref", "HEAD")
    if not 가지 or 가지 == "HEAD" or 가지 == c.get("기본브랜치"):
        return None                                   # 세션 브랜치에서만 — main 에 직접 push 하지 않는다
    n = 횟수합치기(뿌리)
    if not n:
        return None
    s["기록커밋때"] = time.time()
    상태쓰기(뿌리, 세션파일, s)
    git(뿌리, "add", "--", *[파일 for 파일, _ in 기록들.values() if (뿌리 / 파일).is_file()])
    # --no-verify: 커밋 직전 검사(ops check --커밋)는 모델이 고친 문서를 보는 것이다. 이 커밋은 훅이 만든 기록 줄만 담으므로 거치지 않는다 —
    # 거치면 다른 파일(예: 손으로 고친 STATUS.md)의 문제로 기록 커밋이 막히고, 그 문제는 어차피 다음 답 끝의 커밋 · push 확인이 잡는다.
    r = subprocess.run(["git", "-C", str(뿌리), "commit", "-q", "--no-verify", "-m", f"답 끝 검사의 기록 {n}줄을 memory/ 로 옮긴다 — 훅이 한 시간에 한 번 스스로 한다"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return f"답 끝 검사의 기록 {n}줄을 memory/ 로 옮겼지만 커밋이 안 됐다 — 다음 답 끝의 커밋 · push 확인이 잡는다: {r.stderr.strip()[-200:]}"
    try:
        x = subprocess.run(["git", "-C", str(뿌리), "push", "-q", "origin", 가지], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return f"답 끝 검사의 기록 {n}줄을 커밋했지만 push 가 60초를 넘겼다 — 다음 답 끝의 커밋 · push 확인이 잡는다"
    if x.returncode != 0:
        return f"답 끝 검사의 기록 {n}줄을 커밋했지만 push 가 안 됐다 — 다음 답 끝의 커밋 · push 확인이 잡는다: {x.stderr.strip()[-200:]}"
    return f"답 끝 검사의 기록 {n}줄을 memory/ 로 옮겨 커밋 · push 했다 (훅이 한 시간에 한 번 스스로 한다)"


def 답끝(뿌리: Path, c: dict, p: dict) -> int:
    import 기계, 낱말, 대화, 판정
    # 되돌린 뒤(stop_hook_active)에는 상대 날짜와 판정으로 다시 막지 않는다 — 끝없이 도는 것을 막는다. 그러나 커밋 · push 확인은
    # 그대로 한다: 판정이 한 번 막으면 다음 답 끝이 통째로 건너뛰어져 push 없이 끝난 것이 2026-09-16 6판 S8 에서 나왔다.
    되돌린뒤 = bool(p.get("stop_hook_active"))
    t = p.get("transcript_path") or ""
    d = 대화.훑기(Path(t)) if t and Path(t).is_file() else {"답": "", "물음": "", "사용자글": [], "읽은파일": set(), "고친파일": set()}
    답 = d["답"]
    s = 상태읽기(뿌리, 세션파일)
    알림: list[str] = []
    if 답 and not 되돌린뒤:
        걸린 = 기계.상대날짜(답, c)
        if 걸린:
            횟수추가(뿌리, "기계", "상대날짜")
            from 공통 import 오늘
            return 막기(f"답에 상대 날짜가 있다: {' '.join(걸린)} — 이 낱말을 지우고 그 자리에 날짜를 적는다. "
                       f"오늘은 {오늘()} 이니, 그 일이 오늘 있었으면 {오늘()} 이라고 적는다. 그 낱말이 든 문장만 고쳐서 그 문장만 다시 쓴다. 답 전체를 다시 붙이지 않는다.")
        규칙 = 판정.규칙글(뿌리, "답할 때")
        if 규칙 and len(답) > 80:
            후보 = 낱말.후보(답, 낱말.아는말(뿌리, c, d["사용자글"], set(d["읽은파일"])))
            바뀐 = [x[3:] for x in git(뿌리, "status", "--porcelain").split("\n") if x.strip()]
            import time
            t0 = time.time()
            어긴것, 오류 = 판정.부르기(뿌리, 판정.물음(d["물음"], 답, 규칙, 바뀐, 후보[:60], "답"), c)
            판정기록(뿌리, "답", len(어긴것), 오류, time.time() - t0, str(c["판정"].get("모델") or "haiku"))
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
                  "STATUS.md 와 README.md 는 스크립트가 다른 파일을 읽어 만드는 파일이다 — 그 둘이 스크립트가 만들 결과와 다르면 "
                  "`ops build` 를 먼저 돌려 맞춘 뒤 커밋한다.\n" + "\n".join("- " + x for x in 문제))
    if 문제:
        # 두 번 되돌려도 안 하면 막지 않는다(끝없이 도는 것을 막는다). 대신 사용자가 알게 한다 — 6판 S8 에서 push 안 된 채 끝났다.
        알림.append("답을 두 번 되돌렸는데도 커밋 · push 가 안 됐다: " + " / ".join(문제))
    if not 문제:
        한줄 = 기록커밋(뿌리, c, s)                     # 고친 것이 없고 push 도 끝났을 때만 — 기록이 컴퓨터와 함께 사라지지 않게
        if 한줄:
            알림.append(한줄)
    n, 새로 = 어긋남개수(뿌리, c, 다시=True)
    if n:
        알림.append(어긋남한줄(n, 새로))
    if 알림:
        print(json.dumps({"systemMessage": " / ".join(알림)}, ensure_ascii=False))
    return 0


# --------------------------------------------------------- 여러 레포 ----

def 라우트(자리: str, 위: Path) -> int:
    """레포 여럿을 한 디렉터리 아래 두고 그 위에서 세션을 열었을 때. ~/.claude/route.sh 가 부른다.

    .ops.yml 을 가진 레포는 그 레포의 hook.py 를 돌리고, 그것 없이 .claude/settings.json 만 가진 레포(creation 처럼 자체 기계를
    둔 레포)는 그 설정에 적힌 훅 명령을 돌린다 (2026-09-15 4단계). 파일이 걸린 자리(도구 직전 · 직후)는 그 파일이 든 레포에서만,
    답 끝은 이 세션에 파일을 고치거나 읽은 레포(없으면 서 있는 자리의 레포)에서만, 세션 시작과 물음 직전은 전부 돈다.
    결과는 하나로 합친다 — 막는 것(종료 코드 2)이 하나라도 있으면 그 stderr 를 모아 2 로 끝내고, JSON 으로 막은 것(permissionDecision
    deny · decision block)은 첫 것을 내고, additionalContext 와 systemMessage 는 이어 붙인다. 레포마다 settings.json 의
    permissions.deny 는 합쳐서 건다 — 위에서 연 세션에는 레포의 설정이 안 읽히기 때문이다.
    """
    import subprocess
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        p = json.loads(raw) if raw.strip() else {}
    except ValueError:
        p = {}
    도구 = str(p.get("tool_name") or "")
    이벤트 = {"session_start": "SessionStart", "user_prompt_submit": "UserPromptSubmit", "pre_tool_use": "PreToolUse",
            "post_tool_use": "PostToolUse", "stop": "Stop"}.get(자리, 자리)
    디렉터리들 = [d for d in sorted(위.iterdir()) if d.is_dir() and not d.name.startswith(".") and (d / ".git").exists()]
    틀레포 = [d for d in 디렉터리들 if (d / ".ops.yml").is_file() and (d / ".claude/hooks/hook.py").is_file()]
    설정레포 = [d for d in 디렉터리들 if d not in 틀레포 and (d / ".claude/settings.json").is_file()]
    레포들 = 틀레포 + 설정레포
    if not 레포들:
        return 0

    def 설정읽기(r: Path) -> dict:
        try:
            return json.loads((r / ".claude/settings.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    if 자리 == "pre_tool_use" and 도구:
        for r in 레포들:
            for 막 in (설정읽기(r).get("permissions") or {}).get("deny") or []:
                if isinstance(막, str) and (도구 == 막 or 도구.startswith(막.rstrip("*")) and (막.endswith("*") or 도구[len(막):len(막) + 2] == "__")):
                    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                          "permissionDecisionReason": f"{막} 은 {r.name} 레포 설정이 막아 둔 도구다 (permissions.deny)"}}, ensure_ascii=False))
                    return 0

    def 고르기(후보레포: list[Path]) -> list[Path]:
        if 자리 in ("pre_tool_use", "post_tool_use"):
            ti = p.get("tool_input") or {}
            후보 = [str(ti.get(k) or "") for k in ("file_path", "notebook_path", "path")] + re.findall(r"[\w./~-]+", str(ti.get("command") or ""))
            cwd = Path(p.get("cwd") or os.getcwd())
            고른 = []
            for r in 후보레포:
                for s_ in 후보:
                    if not s_ or s_.startswith("-"):
                        continue
                    q = Path(os.path.expanduser(s_))
                    q = (q if q.is_absolute() else cwd / q)
                    try:
                        q = q.resolve()
                    except OSError:
                        continue
                    if q == r.resolve() or r.resolve() in q.parents:
                        고른.append(r); break
            return 고른 or [r for r in 후보레포 if cwd.resolve() == r.resolve() or r.resolve() in cwd.resolve().parents]
        if 자리 == "stop":
            import 대화
            t = p.get("transcript_path") or ""
            d = 대화.훑기(Path(t)) if t and Path(t).is_file() else {"읽은파일": set(), "고친파일": set()}
            닿은 = set()
            for f in set(d["읽은파일"]) | set(d["고친파일"]):
                q = Path(f)
                for r in 후보레포:
                    if q.is_absolute() and (q == r.resolve() or r.resolve() in q.parents):
                        닿은.add(r)
            cwd = Path(p.get("cwd") or os.getcwd()).resolve()
            return sorted(닿은) or [r for r in 후보레포 if cwd == r.resolve() or r.resolve() in cwd.parents] or 후보레포[:1]
        return 후보레포

    def 맞나(matcher, 도구이름: str) -> bool:
        if not matcher or matcher == "*":
            return True
        try:
            return re.fullmatch(str(matcher), 도구이름) is not None
        except re.error:
            return matcher == 도구이름

    할것: list[tuple[Path, list[str] | str]] = []
    for r in 고르기(틀레포):
        할것.append((r, [sys.executable, str(r / ".claude/hooks/hook.py"), 자리]))
    for r in 고르기(설정레포):
        for 묶음 in (설정읽기(r).get("hooks") or {}).get(이벤트) or []:
            if 자리 in ("pre_tool_use", "post_tool_use") and not 맞나(묶음.get("matcher"), 도구):
                continue
            for 항목 in 묶음.get("hooks") or []:
                cmd = str(항목.get("command") or "")
                if not cmd:
                    continue
                cmd = cmd.replace('"$CLAUDE_PROJECT_DIR"', str(r)).replace("${CLAUDE_PROJECT_DIR}", str(r)).replace("$CLAUDE_PROJECT_DIR", str(r))
                할것.append((r, cmd))
    if not 할것:
        return 0
    시간 = 320 if 자리 == "stop" else 110

    def 돌리기(r: Path, cmd) -> tuple[Path, int, str, str]:
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(r))
        try:
            x = subprocess.run(cmd, shell=isinstance(cmd, str), input=raw, text=True, capture_output=True,
                               cwd=str(r), env=env, timeout=시간)
        except subprocess.TimeoutExpired:
            return (r, 0, "", f"[훅] {r.name} {자리} 이 시간을 넘겼다\n")
        except OSError as e:
            return (r, 0, "", f"[훅] {r.name} {자리} 을 못 돌렸다 — {e}\n")
        return (r, x.returncode, x.stdout, x.stderr)

    묶음별: dict[Path, list] = {}
    for r, cmd in 할것:
        묶음별.setdefault(r, []).append(cmd)
    if 자리 == "stop" and len(묶음별) > 1:
        # 답 끝은 레포마다 판정(haiku)을 불러 레포당 1~3분이다. 레포 넷을 차례로 돌리면 4분을 넘고, 그 사이에 플랫폼이
        # 세션을 끈 일이 있었다 (2026-09-15 10:31 실측 — 훅이 251초 만에 끊겼다). 그래서 레포끼리는 동시에 돌리고,
        # 한 레포 안의 명령은 차례를 지킨다. 레포가 다르면 건드리는 파일이 겹치지 않는다.
        from concurrent.futures import ThreadPoolExecutor

        def 레포하나(r: Path) -> list:
            return [돌리기(r, cmd) for cmd in 묶음별[r]]

        with ThreadPoolExecutor(max_workers=len(묶음별)) as ex:
            결과 = [x for 묶 in ex.map(레포하나, list(묶음별)) for x in 묶]
    else:
        결과 = [돌리기(r, cmd) for r, cmd in 할것]
    막힘 = [err for _r, rc, _o, err in 결과 if rc == 2]
    if 막힘:
        for _r, rc, _o, err in 결과:
            if rc != 2 and err.strip():
                sys.stderr.write(err if err.endswith("\n") else err + "\n")
        sys.stderr.write("\n".join(x.rstrip("\n") for x in 막힘 if x.strip()) + "\n")
        return 2
    결정, 문맥, 알림 = [], [], []
    for r, rc, out, err in 결과:
        if err.strip():
            sys.stderr.write(err if err.endswith("\n") else err + "\n")
        if not out.strip():
            continue
        for 조각 in out.strip().split("\n"):
            try:
                js = json.loads(조각)
            except ValueError:
                js = None
            if not isinstance(js, dict):
                if 자리 in ("session_start", "user_prompt_submit"):
                    문맥.append(조각.strip())
                continue
            hso = js.get("hookSpecificOutput") or {}
            if js.get("decision") == "block" or js.get("continue") is False or hso.get("permissionDecision") in ("deny", "ask"):
                결정.append(js)
                continue
            if hso.get("additionalContext"):
                문맥.append(str(hso["additionalContext"]).strip())
            if js.get("systemMessage"):
                알림.append(str(js["systemMessage"]))
    if 결정:
        print(json.dumps(결정[0], ensure_ascii=False))
        return 0
    나갈것: dict = {}
    if 문맥:
        나갈것["hookSpecificOutput"] = {"hookEventName": 이벤트, "additionalContext": "\n\n".join(문맥)}
    if 알림:
        나갈것["systemMessage"] = "\n".join(알림)
    if 나갈것:
        print(json.dumps(나갈것, ensure_ascii=False))
    return 0