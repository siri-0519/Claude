#!/usr/bin/env python3
"""Every Claude Code hook for this repo, in one dispatcher.

    hook.py session_start | user_prompt_submit | pre_tool_use | post_tool_use | stop

Design constraints:
  * A hook must NEVER brick the session. Anything unexpected -> exit 0 quietly,
    except that a crash inside a *rule* surfaces as a visible warning so a broken
    check can't silently switch enforcement off.
  * Only `deny` verdicts block. Everything else is context, not a wall.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR.parents[1] / "ops" / "lib"))

STOP_BLOCK_CAP = 3          # never trap a session in an unbreakable stop loop


def out(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def ctx_out(event: str, text: str) -> None:
    out({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def make_ctx(p: dict, stage: str) -> dict:
    ti = p.get("tool_input") or {}
    command = ti.get("command", "") if isinstance(ti, dict) else ""
    return {
        "stage": stage,
        "tool_name": p.get("tool_name"),
        "tool_input": ti if isinstance(ti, dict) else {},
        "command": command,
        "cwd": p.get("cwd") or os.getcwd(),
        "session_id": p.get("session_id", ""),
    }


def split(verdicts):
    return ([v for v in verdicts if v.action == "deny"],
            [v for v in verdicts if v.action != "deny"])


# ------------------------------------------------------------------ events ----

def session_start(core, p: dict) -> None:
    core.META.mkdir(exist_ok=True)
    try:
        core.session_file().write_text(json.dumps({
            "session_id": p.get("session_id", ""),
            "started_at": core.now_iso(),
            "source": p.get("source", "startup"),
        }), encoding="utf-8")
    except OSError:
        pass

    card = core.session_card(p.get("source", "startup"))
    pending = []
    try:
        if core.build(write=False):
            pending.append("생성물이 낡았습니다 → `ops/bin/ops build`")
        if core.check_stale():
            pending.append("stale 파생물이 있습니다 → `ops/bin/ops link check`")
    except Exception:
        pass
    if pending:
        card += "\n\n**시작 전에 처리할 것**\n- " + "\n- ".join(pending)
    ctx_out("SessionStart", card)


def user_prompt_submit(core, p: dict) -> None:
    """Re-inject the soft rules right before the model answers.

    Soft rules cannot be checked mechanically, so the only lever is recency:
    keep them short and put them last. This costs ~150 tokens a turn.
    """
    try:
        text = (core.OPS / "rules" / "soft.md").read_text(encoding="utf-8")
    except OSError:
        return
    rules = re.findall(r"^## (SR-\d+) · (.+?)\n> (.+?)$", text, re.M)
    if not rules:
        return
    lines = ["<soft-rules> 자가 준수 — 훅이 막아주지 않습니다. 답하기 전에 훑으세요."]
    lines += [f"{rid} {stmt}" for rid, _name, stmt in rules]
    lines.append("</soft-rules>")
    ctx_out("UserPromptSubmit", "\n".join(lines))


def pre_tool_use(core, p: dict) -> None:
    denies, warns = split(core.evaluate("pre_tool", make_ctx(p, "pre_tool")))
    if denies:
        out({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "\n\n".join(v.render() for v in denies),
        }})
        return
    if warns:
        ctx_out("PreToolUse", "\n\n".join(v.render() for v in warns))


def post_tool_use(core, p: dict) -> None:
    verdicts = core.evaluate("post_tool", make_ctx(p, "post_tool"))
    if verdicts:
        ctx_out("PostToolUse", "\n\n".join(v.render() for v in verdicts))


def stop(core, p: dict) -> None:
    sid = p.get("session_id", "") or "default"
    guard = core.META / "stop_guard.json"
    try:
        counts = json.loads(guard.read_text()) if guard.is_file() else {}
    except (OSError, json.JSONDecodeError):
        counts = {}

    denies, warns = split(core.evaluate("stop", make_ctx(p, "stop")))
    for v in warns:            # a stop-stage warn reaches no one otherwise
        print(f"[ops] {v.render()}", file=sys.stderr)
    if not denies:
        counts.pop(sid, None)
        _save(guard, counts)
        return

    n = int(counts.get(sid, 0)) + 1
    counts[sid] = n
    _save(guard, counts)
    if n > STOP_BLOCK_CAP:
        print(f"[ops] {len(denies)} rule(s) still failing after {STOP_BLOCK_CAP} "
              f"attempts — letting the turn end so you are not stuck. "
              f"Run `ops/bin/ops check`.", file=sys.stderr)
        return
    body = "\n\n".join(v.render() for v in denies)
    out({"decision": "block",
         "reason": (f"이 턴은 아직 끝낼 수 없습니다 ({n}/{STOP_BLOCK_CAP}). "
                    f"아래를 해결하거나, 못 고치겠으면 사용자에게 이유를 말하세요.\n\n"
                    f"{body}\n\n지금 상태 확인: `ops/bin/ops check`")})


def _save(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


EVENTS = {
    "session_start": session_start,
    "user_prompt_submit": user_prompt_submit,
    "pre_tool_use": pre_tool_use,
    "post_tool_use": post_tool_use,
    "stop": stop,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in EVENTS:
        return 0
    if os.environ.get("OPS_HOOKS") == "off":
        return 0
    payload = read_payload()
    try:
        import core                                  # noqa: PLC0415
    except Exception as exc:                          # loud: enforcement is OFF
        print(f"[ops] hooks disabled — cannot import ops/lib/core.py: {exc!r}",
              file=sys.stderr)
        return 0
    try:
        EVENTS[sys.argv[1]](core, payload)
    except Exception as exc:
        print(f"[ops] hook '{sys.argv[1]}' failed: {exc!r} — rules NOT enforced "
              f"for this call.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
