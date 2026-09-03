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

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print(f"  - {f}")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAILED else 0)
