#!/usr/bin/env python3
"""레포 위에서 세션이 열려도 훅이 살아 있게 한다.

왜 있는가 (2026-09-04). Claude Code 는 세션의 프로젝트 자리 **하나**에서만
`.claude/settings.json` 을 읽는다. 레포 여럿을 한 디렉터리 아래 두고 그 위에서 세션을
열면 — `/home/user/{Claude,creation,me,broadcast}` 처럼 — 어느 레포의 설정도 안 읽히고
훅이 **아무 말 없이** 전부 꺼진다. 그날 커밋 29개가 검사 없이 지나갔다.

여기서 하는 일은 셋이다.

  1. 위 디렉터리에 설정 하나를 만든다. 그 설정은 아래 레포들의 훅을 전부 등록하되,
     레포마다 `ops guard` 로 감싸서 그 호출이 그 레포와 상관없으면 바로 통과시킨다.
  2. 레포마다 git 훅을 깐다. git 훅은 세션 설정과 무관하게 도니까 마지막 방벽이다.
  3. 셋 중 무엇이 지금 도는지 말한다.

답을 검사하는 훅(마지막 답의 문형·버린 말)은 레포마다 목록이 달라서 여러 번 돌면
같은 지적이 여러 벌 나온다. 그래서 그것만 **주 레포** 하나에서 돈다.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

설정이름 = "settings.json"
router이름 = ".claude-router.json"

# 답을 보는 훅이다 — 레포마다 돌면 같은 말이 여러 벌 나오므로 주 레포에서만 돈다
답훅 = ("stop-reply-rules.py", "user_prompt_submit")

# 자리에 파일 경로가 없다. 어느 레포인지 payload 로 못 가리므로 전부 돈다
파일없는자리 = ("session_start", "user_prompt_submit", "stop")


# --------------------------------------------------------------- 레포 찾기 ----

def 레포들(위: Path) -> list[Path]:
    """위 디렉터리 바로 아래에서, 훅을 가진 git 레포를 찾는다."""
    나온것 = []
    for d in sorted(위.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not (d / ".git").exists():
            continue
        if (d / ".claude" / "hooks").is_dir() or (d / ".claude" / 설정이름).is_file():
            나온것.append(d)
    return 나온것


def 주레포(레포들_: list[Path]) -> Path | None:
    """답을 검사하는 훅을 돌릴 레포. 그 훅을 실제로 가진 레포 중 규칙이 제일 많은 곳."""
    가진곳 = [r for r in 레포들_ if (r / ".claude/hooks/stop-reply-rules.py").is_file()]
    if not 가진곳:
        return None
    def 규칙수(r: Path) -> int:
        f = r / "tools/rules.yml"
        return len(f.read_text(encoding="utf-8").splitlines()) if f.is_file() else 0
    return max(가진곳, key=규칙수)


# ------------------------------------------------------------ 이 호출이 어디냐 ----

경로꼴 = re.compile(r"~?[\w.@+-]*(?:/[\w.@+-]+)+/?")


def 후보경로(p: dict) -> list[str]:
    """payload 에서 파일 경로가 될 만한 것을 전부 긁는다."""
    ti = p.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    나온것: list[str] = []
    for k in ("file_path", "notebook_path", "path", "pattern"):
        v = ti.get(k)
        if isinstance(v, str) and v:
            나온것.append(v)
    for k in ("edits",):
        v = ti.get(k)
        if isinstance(v, list):
            for e in v:
                if isinstance(e, dict) and isinstance(e.get("file_path"), str):
                    나온것.append(e["file_path"])
    cmd = ti.get("command")
    if isinstance(cmd, str) and cmd:
        try:
            토막 = shlex.split(cmd)
        except ValueError:
            토막 = cmd.split()
        for t in 토막:
            나온것.extend(경로꼴.findall(t))
    return 나온것


def 관계(뿌리: Path, p: dict, 자리: str) -> bool:
    """이 훅 호출이 이 레포와 상관있나."""
    if 자리 in 파일없는자리:
        return True
    뿌리 = 뿌리.resolve()
    cwd = Path(p.get("cwd") or os.getcwd())
    맞은레포 = False
    다른레포 = False
    for s in 후보경로(p):
        try:
            q = Path(os.path.expanduser(s))
            q = (q if q.is_absolute() else cwd / q).resolve()
        except (OSError, ValueError):
            continue
        if q == 뿌리 or 뿌리 in q.parents:
            맞은레포 = True
        elif (q / ".git").exists() or any((a / ".git").exists() for a in list(q.parents)[:4]):
            다른레포 = True
    if 맞은레포:
        return True
    if 다른레포:
        return False
    # 경로가 안 나왔으면 지금 서 있는 자리로 가른다
    try:
        cwd = cwd.resolve()
    except OSError:
        return False
    return cwd == 뿌리 or 뿌리 in cwd.parents


# ------------------------------------------------------------------ 설정 짓기 ----

def _훅명령(ops: Path, 뿌리: Path, 자리: str, 명령: str) -> dict:
    안 = f"{shlex.quote(str(ops))} guard {shlex.quote(str(뿌리))} {자리} -- {명령}"
    return {"type": "command", "timeout": 60, "command": 안}


def 설정짓기(위: Path, ops: Path) -> dict:
    """위 디렉터리에 걸 settings.json 을 만든다. 아래 레포들의 훅을 전부 등록한다."""
    rs = 레포들(위)
    주 = 주레포(rs)
    hooks: dict[str, list] = {}

    def 걸기(이벤트: str, 자리: str, 항목: dict, matcher: str | None = None) -> None:
        묶음 = {"hooks": [항목]}
        if matcher:
            묶음["matcher"] = matcher
        hooks.setdefault(이벤트, []).append(묶음)

    for r in rs:
        h = r / ".claude/hooks"
        본 = json.loads((r / ".claude" / 설정이름).read_text(encoding="utf-8")) \
            if (r / ".claude" / 설정이름).is_file() else {}
        for 이벤트, 묶음들 in (본.get("hooks") or {}).items():
            자리 = {"SessionStart": "session_start", "UserPromptSubmit": "user_prompt_submit",
                    "PreToolUse": "pre_tool_use", "PostToolUse": "post_tool_use",
                    "Stop": "stop"}.get(이벤트, "stop")
            for 묶음 in 묶음들:
                for 항목 in 묶음.get("hooks", []):
                    cmd = 항목.get("command", "")
                    cmd = cmd.replace('"$CLAUDE_PROJECT_DIR"', str(r)) \
                             .replace("${CLAUDE_PROJECT_DIR}", str(r)) \
                             .replace("$CLAUDE_PROJECT_DIR", str(r))
                    이름 = Path(cmd.split()[0].strip('"')).name
                    if 이름 in 답훅 or 이벤트 == "UserPromptSubmit":
                        if 주 is None or r != 주:
                            continue
                    if not (h / 이름).is_file():
                        continue
                    걸기(이벤트, 자리,
                         _훅명령(ops, r, 자리, cmd),
                         묶음.get("matcher"))
    return {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "hooks": hooks,
    }


# -------------------------------------------------------------------- 설치 ----

def git훅설치(뿌리: Path) -> str:
    """레포의 .git/hooks/pre-commit 을 레포 안 스크립트로 잇는다."""
    src = 뿌리 / ".claude/hooks/git-pre-commit.sh"
    if not src.is_file():
        return "없다 — .claude/hooks/git-pre-commit.sh 가 이 레포에 없다"
    깃 = subprocess.run(["git", "-C", str(뿌리), "rev-parse", "--git-path", "hooks"],
                        capture_output=True, text=True)
    if 깃.returncode != 0:
        return "없다 — git 레포가 아니다"
    d = Path(깃.stdout.strip())
    d = d if d.is_absolute() else 뿌리 / d
    d.mkdir(parents=True, exist_ok=True)
    tgt = d / "pre-commit"
    want = os.path.relpath(src, d)
    if tgt.is_symlink() and os.readlink(tgt) == want:
        return "이미 깔려 있다"
    if tgt.exists() or tgt.is_symlink():
        tgt.unlink()
    tgt.symlink_to(want)
    return "깔았다"


def 설치(위: Path, ops: Path) -> list[str]:
    줄 = []
    rs = 레포들(위)
    if not rs:
        return [f"{위} 아래에 훅을 가진 레포가 없다"]

    d = 위 / ".claude"
    d.mkdir(exist_ok=True)
    설정 = 설정짓기(위, ops)
    (d / 설정이름).write_text(json.dumps(설정, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    걸린수 = sum(len(v) for v in 설정["hooks"].values())
    줄.append(f"{d / 설정이름} — 훅 {걸린수}개를 걸었다 (레포 {len(rs)}개)")

    (위 / router이름).write_text(json.dumps(
        {"위": str(위), "레포": [str(r) for r in rs],
         "주": str(주레포(rs) or ""), "ops": str(ops)},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for r in rs:
        줄.append(f"  {r.name}: git 훅 {git훅설치(r)}")
    return 줄


# -------------------------------------------------------------------- 상태 ----

def 상태(위: Path) -> list[tuple[str, bool, str]]:
    나온것 = []
    rs = 레포들(위)
    설정 = 위 / ".claude" / 설정이름
    자리 = os.environ.get("CLAUDE_PROJECT_DIR") or ""

    걸렸나 = 설정.is_file()
    나온것.append(("위 디렉터리 설정", 걸렸나,
                 f"{설정} — 레포 {len(rs)}개의 훅을 건다" if 걸렸나
                 else f"{설정} 이 없다. `ops hooks --설치` 로 만든다"))

    맞나 = bool(자리) and Path(자리).resolve() in [위.resolve()] + [r.resolve() for r in rs]
    나온것.append(("세션의 프로젝트 자리", 맞나,
                 f"{자리}" if 맞나 else f"{자리 or '안 알려졌다'} — 위 디렉터리도 레포도 아니다"))

    for r in rs:
        깃 = subprocess.run(["git", "-C", str(r), "rev-parse", "--git-path", "hooks"],
                            capture_output=True, text=True)
        p = Path(깃.stdout.strip()) if 깃.returncode == 0 else Path("x")
        p = p if p.is_absolute() else r / p
        있나 = (p / "pre-commit").exists()
        맥 = r / ".git/claude-hook-heartbeat"
        말 = "커밋 게이트가 돈다" if 있나 else "커밋 게이트가 안 걸렸다"
        if 맥.is_file():
            try:
                말 += " · 훅 맥박 " + json.loads(맥.read_text(encoding="utf-8"))["때"][11:16]
            except Exception:
                pass
        else:
            말 += " · 훅이 한 번도 안 돌았다"
        나온것.append((f"{r.name}", 있나, 말))
    return 나온것


# -------------------------------------------------------------------- guard ----

def guard(뿌리: Path, 자리: str, 명령: list[str]) -> int:
    """훅 하나를 이 레포의 것으로 감싸 돌린다. 상관없는 호출이면 조용히 통과."""
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        p = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        p = {}
    if not 뿌리.is_dir():
        return 0
    if not 관계(뿌리, p, 자리):
        return 0
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(뿌리))
    try:
        r = subprocess.run(" ".join(명령), shell=True, input=raw, text=True,
                           cwd=str(뿌리), env=env, capture_output=True, timeout=55)
    except subprocess.TimeoutExpired:
        print(f"[훅] {뿌리.name} {자리} 이 시간을 넘겼다", file=sys.stderr)
        return 0
    except OSError as e:
        print(f"[훅] {뿌리.name} {자리} 을 못 돌렸다: {e}", file=sys.stderr)
        return 0
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r.returncode
