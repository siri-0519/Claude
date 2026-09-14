"""대화 — Claude Code 의 transcript(jsonl)에서 필요한 것만 뽑는다.

마지막 물음과 답, 이 세션에서 읽은 파일, 사용자가 쓴 낱말, 요약이 접힌 자리.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _글(c) -> str:
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    return c if isinstance(c, str) else ""


def 훑기(transcript: Path) -> dict:
    """한 번 지나가며 전부 뽑는다."""
    답, 물음 = "", ""
    사용자글: list[str] = []
    읽은파일: set[str] = set()
    고친파일: set[str] = set()
    시작 = ""
    for line in transcript.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not 시작 and d.get("timestamp"):
            시작 = str(d["timestamp"])
        if d.get("type") == "summary" or d.get("isCompactSummary"):
            # 요약으로 접힌 자리 — 그 앞에서 읽은 것은 문맥에 없다
            읽은파일 = set()
        m = d.get("message") or {}
        c = m.get("content")
        if isinstance(c, list):
            for x in c:
                if not isinstance(x, dict):
                    continue
                if x.get("type") == "tool_use":
                    이름 = x.get("name") or ""
                    ti = x.get("input") or {}
                    fp = ti.get("file_path") or ti.get("notebook_path") or ""
                    if 이름 in ("Read",) and fp:
                        읽은파일.add(fp)
                    elif 이름 in ("Edit", "Write", "MultiEdit", "NotebookEdit") and fp:
                        고친파일.add(fp)
                    elif 이름 == "Bash":
                        cmd = str(ti.get("command") or "")
                        if re.match(r"\s*(cat|sed|head|tail|less|grep)\b", cmd):
                            for p in re.findall(r"(?<![\w-])[\w./~-]+\.(?:md|yml|yaml|txt|py|json)\b", cmd):
                                읽은파일.add(p)
        글 = _글(c)
        if d.get("type") == "assistant" and 글.strip():
            답 = 글
        elif d.get("type") == "user" and 글.strip() and "<system-reminder>" not in 글 \
                and not 글.lstrip().startswith(("<local-command", "<command-name", "[Request interrupted")):
            물음 = 글
            사용자글.append(글)
    return {"답": 답, "물음": 물음, "사용자글": 사용자글, "읽은파일": 읽은파일,
            "고친파일": 고친파일, "시작": 시작}
