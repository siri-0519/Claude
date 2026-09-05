#!/usr/bin/env python3
"""End-to-end proof that the four guarantees actually hold.

Runs against a throwaway copy of the machinery (OPS_ROOT), never the real vault.
    python3 ops/test/selftest.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REAL = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="ops-selftest-"))
os.environ["OPS_ROOT"] = str(TMP)

for d in ("vault/docs", "vault/knowledge", "vault/inbox", "memory/log",
          "memory/digest", "memory/decisions", ".meta"):
    (TMP / d).mkdir(parents=True, exist_ok=True)
for f in ("ops/lib/core.py", "ops/rules/hard.yml", "ops/rules/soft.md",
          "ops/schema/frontmatter.yml", "ops/bin/ops", ".claude/hooks/hook.py",
          "CLAUDE.md", "memory/STATE.md"):
    (TMP / f).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL / f, TMP / f)
subprocess.run(["git", "init", "-q"], cwd=TMP, check=False)

sys.path.insert(0, str(TMP / "ops" / "lib"))
import core  # noqa: E402

FAILED: list[str] = []
PASSED = 0

# Patterns the rules react to, assembled at runtime so this file can be written
# and read without tripping the very rules it exercises.
RM_RF = "rm -" + "rf ops/"
PRIVKEY = "-----BEGIN RSA PRIVATE " + "KEY-----"
CRED = 'api_key = "' + "sk9d8f7a6s5d4f3g2h1j0k" + '"'


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name}   {detail}")


def tctx(tool: str, **ti) -> dict:
    return {"stage": "pre_tool", "tool_name": tool, "tool_input": ti,
            "command": ti.get("command", ""), "cwd": str(TMP)}


STOPCTX = {"stage": "stop", "tool_name": None, "tool_input": {}, "cwd": str(TMP)}


def denied(stage: str, c: dict) -> list[str]:
    return [v.rule_id for v in core.evaluate(stage, c) if v.action == "deny"]


def warned(stage: str, c: dict) -> list[str]:
    return [v.rule_id for v in core.evaluate(stage, c) if v.action == "warn"]


def ops(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TMP / "ops/bin/ops"), *args],
                          cwd=TMP, capture_output=True, text=True,
                          env={**os.environ, "OPS_ROOT": str(TMP)})


def rewrite_body(relpath: str, body: str) -> None:
    p = TMP / relpath
    meta, _ = core.split_frontmatter(p.read_text())
    p.write_text(core.join_frontmatter(meta, body))


# --- R4: derivation linkage ------------------------------------------------
print("\n[R4] derivation linkage - 'A를 고치면 B도 고쳐져야 한다'")
ops("new", "doc", "vault/docs/spec.md", "--title", "Spec", "--label", "t",
    "--body", "\nv1 body\n")
src = core.id_for_path(TMP / "vault/docs/spec.md")
ok("source gets a stable id", bool(src), str(src))

ops("new", "knowledge", "vault/knowledge/summary.md", "--title", "Summary",
    "--source", src, "--body", "\nderived from v1\n")
kid = core.id_for_path(TMP / "vault/knowledge/summary.md")
ok("derived artifact pins its source", bool(kid) and not core.check_stale())

meta, _ = core.read_meta(TMP / "vault/docs/spec.md")
meta["labels"] = ["t", "extra"]
core.write_meta(TMP / "vault/docs/spec.md", meta)
ok("metadata-only edit does NOT falsely invalidate", not core.check_stale())

rewrite_body("vault/docs/spec.md", "\nv2 body - changed\n")
stale = core.check_stale()
ok("body edit marks the child stale",
   len(stale) == 1 and stale[0].child_id == kid, str(stale))
ok("HR-009 refuses to let the turn end", "HR-009" in denied("stop", STOPCTX))
ok("link impact names the child", kid in core.descendants(src))
ok("link why names the source", src in core.ancestors(kid))
r = ops("link", "ack", kid)
ok("ack reconciles it", r.returncode == 0 and not core.check_stale(), r.stdout + r.stderr)

ops("new", "knowledge", "vault/knowledge/deep.md", "--title", "Deep",
    "--source", kid, "--body", "\nfrom summary\n")
deep = core.id_for_path(TMP / "vault/knowledge/deep.md")
ok("derivation is transitive", set(core.descendants(src)) == {kid, deep})

# --- R1: rule enforcement --------------------------------------------------
print("\n[R1] rule enforcement")
ok("HR-001 blocks force-push",
   "HR-001" in denied("pre_tool", tctx("Bash", command="git push --force origin main")))
ok("HR-001 blocks reset --hard",
   "HR-001" in denied("pre_tool", tctx("Bash", command="git reset --hard HEAD~1")))
ok("HR-001 has a visible escape hatch",
   "HR-001" not in denied("pre_tool",
                          tctx("Bash", command="OPS_ALLOW=HR-001 git push --force o m")))
ok("HR-002 blocks recursive delete of machinery",
   "HR-002" in denied("pre_tool", tctx("Bash", command=RM_RF)))
ok("HR-002 leaves an ordinary delete alone",
   "HR-002" not in denied("pre_tool", tctx("Bash", command="rm vault/inbox/tmp.txt")))
ok("HR-002 ignores the same text inside a heredoc body",
   "HR-002" not in denied("pre_tool",
                          tctx("Bash", command="cat > n.md <<'E'\n" + RM_RF + "\nE")))
ok("HR-003 blocks Write to a generated file",
   "HR-003" in denied("pre_tool", tctx("Write", file_path=str(TMP / "INDEX.md"),
                                       content="x")))
ok("HR-003 blocks a shell redirect into one",
   "HR-003" in denied("pre_tool", tctx("Bash", command="echo hi > INDEX.md")))
ok("HR-003 blocks sed -i on one",
   "HR-003" in denied("pre_tool", tctx("Bash", command="sed -i 's/a/b/' INDEX.md")))
blk = (core.get_block((TMP / "CLAUDE.md").read_text(), "rules") or "").splitlines()
ok("HR-003 blocks edits INSIDE a generated block",
   "HR-003" in denied("pre_tool", tctx("Edit", file_path=str(TMP / "CLAUDE.md"),
                                       old_string=blk[0], new_string="x")))
ok("HR-003 allows edits outside that block",
   "HR-003" not in denied("pre_tool", tctx("Edit", file_path=str(TMP / "CLAUDE.md"),
                                           old_string="# 작업 규약", new_string="# 규약")))
ok("HR-004 blocks a private key",
   "HR-004" in denied("pre_tool", tctx("Write", file_path=str(TMP / "vault/inbox/k.txt"),
                                       content=PRIVKEY)))
ok("HR-004 blocks an inline credential",
   "HR-004" in denied("pre_tool", tctx("Write", file_path=str(TMP / "vault/inbox/c.py"),
                                       content=CRED)))
ok("HR-004 ignores an obvious placeholder",
   "HR-004" not in denied("pre_tool", tctx("Write", file_path=str(TMP / "vault/inbox/c.py"),
                                           content='api_key = "your-key-here"')))
ok("HR-004 exempts the files that DEFINE the patterns",
   "HR-004" not in denied("pre_tool", tctx("Write",
                                           file_path=str(TMP / "ops/test/x.py"),
                                           content=PRIVKEY)))
ok("HR-005 blocks blowing the STATE budget",
   "HR-005" in denied("pre_tool", tctx("Write", file_path=str(TMP / "memory/STATE.md"),
                                       content="x" * (core.limits()["state_md_bytes"] + 10))))
ok("HR-006 blocks an unlabelled new vault file",
   "HR-006" in denied("pre_tool", tctx("Write", file_path=str(TMP / "vault/docs/raw.md"),
                                       content="no header")))
ok("HR-007 warns on a bulk read",
   "HR-007" in warned("pre_tool", tctx("Bash", command="find . -name '*.md' | xargs cat")))

(TMP / "vault/inbox/orphan.txt").write_text("dropped in by hand")
ok("HR-006 catches an orphan that arrived by ANY means",
   "HR-006" in denied("stop", STOPCTX))
r = ops("ingest", "--label", "unsorted")
ok("ops ingest unblocks it in one command",
   r.returncode == 0 and "HR-006" not in denied("stop", STOPCTX), r.stdout + r.stderr)

# --- R2: cross-session context ---------------------------------------------
print("\n[R2] cross-session context")
ops("log", "add", "--kind", "work", "--title", "설계 확정", "--ref", "vault/docs/spec.md")
ops("log", "add", "--kind", "blocker", "--title", "미해결 이슈 X")
entries = core.log_read()
ok("machine log persists as jsonl",
   len(entries) == 2 and entries[0]["title"] == "설계 확정")
digest = TMP / f"memory/digest/{core.log_path().stem}.md"
ok("the human digest is DERIVED from that log, not written twice",
   digest.is_file() and "설계 확정" in digest.read_text())
card = core.session_card()
ok("session card surfaces the open blocker", "미해결 이슈 X" in card, card[:160])
ok("session card stays inside its byte budget",
   len(card.encode()) <= core.limits()["session_card_bytes"], f"{len(card.encode())}B")
r = ops("ctx", "log", "--grep", "설계")
ok("a targeted log query returns only what was asked for",
   "설계 확정" in r.stdout and "미해결" not in r.stdout)
subprocess.run(["git", "add", "-A"], cwd=TMP, check=False, capture_output=True)
core.session_file().write_text(json.dumps({"started_at": "2999-01-01T00:00:00Z"}))
ok("HR-011 blocks a change-making session that logged nothing",
   "HR-011" in denied("stop", STOPCTX))
core.session_file().write_text(json.dumps({"started_at": "1999-01-01T00:00:00Z"}))
ok("HR-011 passes once a log entry exists", "HR-011" not in denied("stop", STOPCTX))

# --- R3: token discipline --------------------------------------------------
print("\n[R3] token discipline")
core.build()
idx = (TMP / "INDEX.md").read_text()
ok("INDEX maps every artifact without opening any of them",
   all(i in idx for i in (src, kid, deep)))
ok("INDEX stays small", len(idx.encode()) < 8000, f"{len(idx.encode())}B")
r = ops("find", "--kind", "knowledge")
ok("find narrows by kind", kid in r.stdout and src not in r.stdout)
ok("find narrows by label", src in ops("find", "--label", "t").stdout)
ok("build is idempotent", core.build(write=False) == [])
(TMP / "INDEX.md").write_text("tampered")
ok("HR-010 catches a stale generated file", "HR-010" in denied("stop", STOPCTX))
core.build()
ok("ops build repairs it", "HR-010" not in denied("stop", STOPCTX))

# --- hook protocol ---------------------------------------------------------
print("\n[wiring] hooks speak the Claude Code protocol")


def hook(event: str, payload: dict) -> dict:
    r = subprocess.run([sys.executable, str(TMP / ".claude/hooks/hook.py"), event],
                       input=json.dumps(payload), capture_output=True, text=True,
                       cwd=TMP, env={**os.environ, "OPS_ROOT": str(TMP)})
    return json.loads(r.stdout) if r.stdout.strip() else {}


d = hook("pre_tool_use", {"tool_name": "Bash",
                          "tool_input": {"command": "git push -f"}, "cwd": str(TMP)})
ok("PreToolUse emits a deny decision",
   d.get("hookSpecificOutput", {}).get("permissionDecision") == "deny", str(d)[:140])
d = hook("session_start", {"session_id": "test", "source": "startup"})
ok("SessionStart injects the state card",
   "STATE" in d.get("hookSpecificOutput", {}).get("additionalContext", ""), str(d)[:140])
d = hook("user_prompt_submit", {})
ok("UserPromptSubmit re-injects the soft rules",
   "SR-001" in d.get("hookSpecificOutput", {}).get("additionalContext", ""))
rewrite_body("vault/docs/spec.md", "\nv3 - changed again\n")
d = hook("stop", {"session_id": "t2"})
ok("Stop blocks while a derivation is stale", d.get("decision") == "block", str(d)[:140])
for _ in range(4):
    d = hook("stop", {"session_id": "t2"})
ok("Stop gives up after the cap, so a session can never be trapped",
   d.get("decision") != "block", str(d)[:140])

# ---------------------------------------------------------------------------
print("\n[router] hooks survive a session opened above the repos")
# 레포 위에서 세션이 열리면 어느 레포의 .claude/settings.json 도 안 읽힌다 (2026-09-04).
# 위 디렉터리에 설정 하나를 걸고, 훅마다 guard 로 감싸 상관있는 레포만 돌린다.

sys.path.insert(0, str(REAL / "ops/lib"))
import hooks as _hooks
import origin  # noqa: E402

_W = Path(tempfile.mkdtemp(prefix="router-"))
_A, _B = _W / "alpha", _W / "beta"
for _r in (_A, _B):
    (_r / ".claude/hooks").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(_r)], check=True)
    (_r / ".claude/settings.json").write_text(json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
            "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/probe.sh pre_tool_use'}]}],
        "Stop": [{"hooks": [{"type": "command",
            "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/probe.sh stop'}]}],
    }}), encoding="utf-8")
    _p = _r / ".claude/hooks/probe.sh"
    _p.write_text('#!/bin/sh\necho "돌았다 $CLAUDE_PROJECT_DIR"\n', encoding="utf-8")
    _p.chmod(0o755)

def _pay(**kw): return json.dumps(kw)

def _guard(root, stage, payload):
    return subprocess.run(
        [sys.executable, str(REAL / "ops/bin/ops"), "guard", str(root), stage,
         "--", f'{root}/.claude/hooks/probe.sh {stage}'],
        input=payload, text=True, capture_output=True)

_in_a = _pay(tool_input={"file_path": str(_A / "x.md")}, cwd=str(_W))
ok("a call inside one repo runs that repo's hook",
   "돌았다" in _guard(_A, "pre_tool_use", _in_a).stdout)
ok("the same call stays silent in the other repo",
   _guard(_B, "pre_tool_use", _in_a).stdout.strip() == "")
ok("the hook is told which repo it is in",
   str(_A) in _guard(_A, "pre_tool_use", _in_a).stdout)
_in_cwd = _pay(tool_input={"command": "git status"}, cwd=str(_B))
ok("with no path in the call, the cwd decides the repo",
   "돌았다" in _guard(_B, "pre_tool_use", _in_cwd).stdout
   and _guard(_A, "pre_tool_use", _in_cwd).stdout.strip() == "")
ok("a call outside every repo runs nothing",
   _guard(_A, "pre_tool_use", _pay(tool_input={"command": "echo hi"}, cwd="/tmp")).stdout.strip() == "")
ok("the end of an answer has no path, so every repo runs",
   "돌았다" in _guard(_A, "stop", _pay(cwd=str(_W))).stdout
   and "돌았다" in _guard(_B, "stop", _pay(cwd=str(_W))).stdout)

_gen = _hooks.설정짓기(_W, REAL / "ops/bin/ops")
_names = [h["command"] for v in _gen["hooks"].values() for g in v for h in g["hooks"]]
ok("the generated settings register both repos",
   sum(str(_A) in c for c in _names) >= 2 and sum(str(_B) in c for c in _names) >= 2,
   f"{len(_names)} entries")
ok("nothing in the generated settings still says CLAUDE_PROJECT_DIR",
   not any("CLAUDE_PROJECT_DIR" in c for c in _names))
_hooks.설치(_W, REAL / "ops/bin/ops")
ok("installing is what makes the settings file exist",
   (_W / ".claude/settings.json").is_file())
_before = (_W / ".claude/settings.json").read_text(encoding="utf-8")
_hooks.설치(_W, REAL / "ops/bin/ops")
ok("installing twice changes nothing",
   (_W / ".claude/settings.json").read_text(encoding="utf-8") == _before)
_gp = _A / ".claude/hooks/git-pre-commit.sh"
_gp.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8"); _gp.chmod(0o755)
_r1 = _hooks.git훅설치(_A)
_hp = subprocess.run(["git", "-C", str(_A), "config", "--get", "core.hooksPath"],
                     capture_output=True, text=True).stdout.strip()
ok("the git hook is installed in a tracked .githooks/ directory",
   (_A / ".githooks/pre-commit").is_symlink() and "깔았다" in _r1, _r1)
ok("core.hooksPath points at it, so git actually runs it",
   _hp == ".githooks", _hp)
ok("git resolves the hooks dir to the tracked one",
   subprocess.run(["git", "-C", str(_A), "rev-parse", "--git-path", "hooks"],
                  capture_output=True, text=True).stdout.strip() == ".githooks")
ok("installing the git hook twice changes nothing", _hooks.git훅설치(_A) == "이미 깔려 있다")
shutil.rmtree(_W, ignore_errors=True)


# ---------------------------------------------------------------------------
print("\n[items] one item is one thing a person can judge on its own")
# 작가가 판정 문서를 읽고 셋을 짚었다 (2026-09-04) — 표 문법이 그대로 박히고,
# 코드 울이 다른 항에 섞여 들어가고, 문단이 문장 한가운데서 끊겼다.

_글 = "\n".join([
    "# 최연", "",
    "> 정본이다. 1~3루프는 최연이고 4루프부터 최연아다.", "",
    "## 1. 본문이 틀리면 안 되는 것", "",
    "| | |", "|---|---|",
    "| 몸 | TS다. 23세, 157cm. |",
    "| MBTI | INTP다 |", "",
    "## 2. 카드", "",
    "```",
    "신체 : 157cm",
    "성별 : 여성",
    "```", "",
    "## 3. 사람됨", "",
    "**사람은 모두 평범하면서 특별하다.** 어떤 범주에 속한다는 것은",
    "배역이 있다는 것이고, 특별함조차 하나의 배역이다.", "",
])
_항 = _hooks and origin.항들(_글)
_본문 = [b for _, b in _항]

ok("a fenced block is one item, not scattered lines",
   sum(1 for b in _본문 if b.startswith("```")) == 1
   and "신체 : 157cm" in [b for b in _본문 if b.startswith("```")][0],
   f"{len(_본문)} items")
ok("no item is left holding a stray fence",
   not any(b.rstrip().endswith("```") and not b.startswith("```") for b in _본문))
ok("a paragraph opening in bold is not cut into a bullet",
   any("특별함조차 하나의 배역이다." in b and "사람은 모두" in b for b in _본문),
   str(_본문[-1])[:80])
ok("a table row keeps its label and drops the pipes",
   origin.보기좋게("| 몸 | TS다. 23세, 157cm. |") == ("몸", "TS다. 23세, 157cm."),
   str(origin.보기좋게("| 몸 | TS다. 23세, 157cm. |")))
ok("a plain paragraph has no label",
   origin.보기좋게("INTP다") == ("", "INTP다"))
ok("sections are named, not just numbered",
   origin.절이름들(_글) == {1: "1. 본문이 틀리면 안 되는 것", 2: "2. 카드", 3: "3. 사람됨"},
   str(origin.절이름들(_글)))
ok("the file's own preamble comes along, so an item reads in context",
   "4루프부터 최연아다" in origin.머리말(_글), origin.머리말(_글)[:60])


print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print(f"  - {f}")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAILED else 0)
