"""Shared core for the ops CLI and the Claude Code hooks.

One module so that the thing which ENFORCES a rule and the thing which
DOCUMENTS it are the same code path. Nothing here may import anything outside
the stdlib except PyYAML.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

# ---------------------------------------------------------------- paths ----

def repo_root(start: Path | None = None) -> Path:
    """Repo root = nearest ancestor holding ops/lib/core.py."""
    env = os.environ.get("OPS_ROOT")
    if env:
        return Path(env).resolve()
    cur = (start or Path(__file__)).resolve()
    for p in [cur, *cur.parents]:
        if (p / "ops" / "lib" / "core.py").is_file():
            return p
    return Path.cwd().resolve()


ROOT = repo_root()
OPS = ROOT / "ops"
MEMORY = ROOT / "memory"
VAULT = ROOT / "vault"
META = ROOT / ".meta"
STATE_MD = MEMORY / "STATE.md"
INDEX_MD = ROOT / "INDEX.md"
CLAUDE_MD = ROOT / "CLAUDE.md"

# Directories that hold managed artifacts (front-matter required).
ARTIFACT_ROOTS = ("vault", "memory/decisions")

TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".yml", ".yaml",
    ".json", ".toml", ".ini", ".cfg", ".sql", ".html", ".css", ".rs", ".go",
    ".java", ".c", ".h", ".cpp", ".rb", ".php", ".csv",
}

# --------------------------------------------------------------- schema ----

_schema_cache: dict | None = None


def schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = yaml.safe_load((OPS / "schema" / "frontmatter.yml").read_text())
    return _schema_cache


def kinds() -> dict:
    return schema()["kinds"]


def limits() -> dict:
    return schema()["limits"]


def tz():
    name = schema().get("timezone") or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return timezone.utc


def now_local() -> datetime:
    return datetime.now(tz())


def now_iso() -> str:
    """Local time WITH its offset: unambiguous, and its date is the user's date."""
    return now_local().isoformat(timespec="seconds")


def parse_ts(value: str) -> datetime:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=tz())


def today() -> str:
    return now_local().strftime("%Y-%m-%d")


def rel(p: Path | str) -> str:
    p = Path(p)
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------- front-matter ----

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


# Prose formats only. A `---` fence at the top of a .py/.js/.sh file is a
# syntax error, so those carry their metadata in a `.meta.yml` sidecar instead.
FRONTMATTER_SUFFIXES = {".md", ".txt"}


def is_texty(path: Path) -> bool:
    """Readable as text. Says nothing about where metadata goes."""
    return path.suffix.lower() in TEXT_SUFFIXES


def takes_frontmatter(path: Path) -> bool:
    """Can carry inline YAML front-matter without becoming invalid."""
    return path.suffix.lower() in FRONTMATTER_SUFFIXES


def drop_zone() -> str:
    """The one place under vault/ where an unlabelled file may land, so that
    `ops ingest` has something to pick up. HR-006 still refuses to let the turn
    END while anything there is unlabelled."""
    return kinds().get("raw", {}).get("home", "vault/inbox")


def sidecar_for(path: Path) -> Path:
    return path.with_name(path.name + ".meta.yml")


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (metadata, body). Missing/!dict front-matter yields ({}, text)."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, text[m.end():]


def join_frontmatter(meta: dict, body: str) -> str:
    dumped = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{dumped}\n---\n{body}"


def read_meta(path: Path) -> tuple[dict, str | None]:
    """(metadata, body-or-None). Binary/unstructured files use a sidecar."""
    if not path.exists():
        return {}, None
    if takes_frontmatter(path):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            text = None
        if text is not None:
            meta, body = split_frontmatter(text)
            if meta:
                return meta, body
    side = sidecar_for(path)
    if side.is_file():
        try:
            return yaml.safe_load(side.read_text()) or {}, None
        except yaml.YAMLError:
            return {}, None
    return {}, None


def body_hash(path: Path) -> str:
    """sha256 of CONTENT ONLY — front-matter excluded.

    So bumping `updated:` or adding a label on A does not mark A's children
    stale. Only a real content change does.
    """
    if not path.exists():
        return ""
    meta, body = read_meta(path)
    if body is not None:
        data = body.encode("utf-8")
    else:
        try:
            data = path.read_bytes()
        except OSError:
            return ""
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]


def new_id(kind: str, seed: str = "") -> str:
    prefix = kinds().get(kind, {}).get("prefix", "X")
    salt = hashlib.sha256((seed + now_iso() + os.urandom(6).hex()).encode()).hexdigest()[:6]
    return f"{prefix}-{now_local().strftime('%Y%m%d')}-{salt}"


# ------------------------------------------------------------ artifacts ----

@dataclass
class Artifact:
    path: Path
    meta: dict
    hash: str = ""
    body: str | None = None

    @property
    def id(self) -> str:
        return str(self.meta.get("id", "")) or f"?{rel(self.path)}"

    @property
    def kind(self) -> str:
        return str(self.meta.get("kind", "raw"))

    @property
    def title(self) -> str:
        return str(self.meta.get("title", self.path.stem))

    @property
    def labels(self) -> list[str]:
        v = self.meta.get("labels") or []
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]

    @property
    def parents(self) -> list[dict]:
        v = self.meta.get("derives_from") or []
        out = []
        for e in v if isinstance(v, list) else []:
            if isinstance(e, dict) and e.get("id"):
                out.append({"id": str(e["id"]), "hash": str(e.get("hash", ""))})
            elif isinstance(e, str):
                out.append({"id": e, "hash": ""})
        return out


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".meta", ".venv", "dist", "build"}


def iter_artifacts() -> Iterable[Artifact]:
    """Every file under ARTIFACT_ROOTS that carries metadata."""
    seen: set[Path] = set()
    for root_name in ARTIFACT_ROOTS:
        base = ROOT / root_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path in seen:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name.endswith(".meta.yml") or path.name == ".gitkeep":
                continue
            meta, body = read_meta(path)
            if not meta.get("id"):
                continue
            seen.add(path)
            yield Artifact(path=path, meta=meta, hash=body_hash(path), body=body)


def artifact_map() -> dict[str, Artifact]:
    return {a.id: a for a in iter_artifacts()}


# ---------------------------------------------------------------- graph ----

@dataclass
class Stale:
    child_id: str
    child_path: str
    parent_id: str
    parent_path: str
    reason: str          # "changed" | "missing-parent" | "unpinned"


def build_graph() -> dict:
    arts = artifact_map()
    nodes = {
        a.id: {"path": rel(a.path), "kind": a.kind, "title": a.title,
               "labels": a.labels, "hash": a.hash}
        for a in arts.values()
    }
    edges = []
    for a in arts.values():
        for p in a.parents:
            edges.append({"from": p["id"], "to": a.id, "pinned_hash": p["hash"]})
    return {"generated": now_iso(), "nodes": nodes, "edges": edges}


def check_stale(graph: dict | None = None) -> list[Stale]:
    """A child is stale when its parent's CURRENT body hash differs from the
    hash the child pinned when it was derived."""
    g = graph or build_graph()
    nodes, out = g["nodes"], []
    for e in g["edges"]:
        child, parent = nodes.get(e["to"]), nodes.get(e["from"])
        if child is None:
            continue
        if parent is None:
            out.append(Stale(e["to"], child["path"], e["from"], "?", "missing-parent"))
        elif not e["pinned_hash"]:
            out.append(Stale(e["to"], child["path"], e["from"], parent["path"], "unpinned"))
        elif e["pinned_hash"] != parent["hash"]:
            out.append(Stale(e["to"], child["path"], e["from"], parent["path"], "changed"))
    return out


def descendants(node_id: str, graph: dict | None = None) -> list[str]:
    g = graph or build_graph()
    kids: dict[str, list[str]] = {}
    for e in g["edges"]:
        kids.setdefault(e["from"], []).append(e["to"])
    out, stack, seen = [], list(kids.get(node_id, [])), {node_id}
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
        stack.extend(kids.get(n, []))
    return out


def ancestors(node_id: str, graph: dict | None = None) -> list[str]:
    g = graph or build_graph()
    par: dict[str, list[str]] = {}
    for e in g["edges"]:
        par.setdefault(e["to"], []).append(e["from"])
    out, stack, seen = [], list(par.get(node_id, [])), {node_id}
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
        stack.extend(par.get(n, []))
    return out


def id_for_path(path: Path | str) -> str | None:
    meta, _ = read_meta(Path(path) if Path(path).is_absolute() else ROOT / path)
    return str(meta["id"]) if meta.get("id") else None


def repin(child_id: str, parent_ids: list[str] | None = None) -> list[str]:
    """Re-record parents' current hashes on the child == 'I have reconciled'."""
    arts = artifact_map()
    child = arts.get(child_id)
    if child is None:
        raise KeyError(f"unknown id: {child_id}")
    changed = []
    edges = child.meta.get("derives_from") or []
    norm: list[dict] = []
    for e in edges:
        e = {"id": e, "hash": ""} if isinstance(e, str) else dict(e)
        pid = str(e.get("id", ""))
        if parent_ids and pid not in parent_ids:
            norm.append(e)
            continue
        parent = arts.get(pid)
        if parent and e.get("hash") != parent.hash:
            e["hash"] = parent.hash
            changed.append(pid)
        norm.append(e)
    if changed:
        child.meta["derives_from"] = norm
        child.meta["updated"] = today()
        write_meta(child.path, child.meta)
    return changed


def write_meta(path: Path, meta: dict) -> None:
    """Persist metadata, leaving the body byte-identical."""
    if takes_frontmatter(path) and path.exists():
        text = path.read_text(encoding="utf-8")
        _, body = split_frontmatter(text)
        if FM_RE.match(text):
            path.write_text(join_frontmatter(meta, body), encoding="utf-8")
            return
    sidecar_for(path).write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")


# ----------------------------------------------------- generated content ----

def is_generated_path(path: Path | str) -> bool:
    r = rel(path)
    for pat in schema().get("generated_paths", []):
        if fnmatch.fnmatch(r, pat) or (pat.endswith("/**") and r.startswith(pat[:-3] + "/")):
            return True
    return False


BLOCK_RE = re.compile(
    r"(<!-- BEGIN GENERATED: *(?P<name>[\w.-]+) *-->)(?P<body>.*?)(<!-- END GENERATED: *(?P=name) *-->)",
    re.S)


def generated_block_names(text: str) -> list[str]:
    return [m.group("name") for m in BLOCK_RE.finditer(text)]


def replace_block(text: str, name: str, content: str) -> str:
    def sub(m):
        if m.group("name") != name:
            return m.group(0)
        return f"{m.group(1)}\n{content.strip()}\n{m.group(4)}"
    return BLOCK_RE.sub(sub, text)


def get_block(text: str, name: str) -> str | None:
    for m in BLOCK_RE.finditer(text):
        if m.group("name") == name:
            return m.group("body").strip()
    return None


def line_span_of_blocks(text: str) -> list[tuple[int, int, str]]:
    spans = []
    for m in BLOCK_RE.finditer(text):
        start = text.count("\n", 0, m.start()) + 1
        end = text.count("\n", 0, m.end()) + 1
        spans.append((start, end, m.group("name")))
    return spans


# ------------------------------------------------------------------ log ----

def log_path(month: str | None = None) -> Path:
    return MEMORY / "log" / f"{month or now_local().strftime('%Y-%m')}.jsonl"


LOG_KINDS = ("work", "decision", "blocker", "note", "handoff")


def log_add(kind: str, title: str, body: str = "", refs: list[str] | None = None,
            labels: list[str] | None = None, session: str = "") -> dict:
    entry = {
        "ts": now_iso(),
        "session": session or os.environ.get("OPS_SESSION", "")[:12],
        "kind": kind,
        "title": title.strip(),
        "body": body.strip(),
        "refs": [rel(r) for r in (refs or [])],
        "labels": labels or [],
    }
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def log_read(months: int = 3) -> list[dict]:
    files = sorted((MEMORY / "log").glob("*.jsonl"))[-months:]
    out = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def log_since(iso_ts: str) -> list[dict]:
    """Timestamps carry offsets now, so compare instants — not strings."""
    cutoff = parse_ts(iso_ts)
    return [e for e in log_read(2) if parse_ts(e.get("ts", "")) >= cutoff]


# ------------------------------------------------------------ renderers ----
# Every renderer must be a PURE function of repo content: no timestamps, no
# randomness. Otherwise "is the generated file current?" can never be true.

def _fence(rows: list[list[str]], head: list[str]) -> str:
    if not rows:
        return "_(none)_"
    widths = [max(len(str(r[i])) for r in [head, *rows]) for i in range(len(head))]
    def line(cells):
        return "| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([line(head), sep, *[line(r) for r in rows]])


def render_index() -> str:
    arts = sorted(iter_artifacts(), key=lambda a: (a.kind, rel(a.path)))
    g = build_graph()
    parents_of = {}
    for e in g["edges"]:
        parents_of.setdefault(e["to"], []).append(e["from"])

    parts = [
        "# INDEX",
        "",
        "> GENERATED by `ops/bin/ops build`. Do not hand-edit — HR-003 blocks it.",
        "> This is the map: find what you need here, then open only that file.",
        "> Narrower queries: `ops/bin/ops find --label X --kind Y --text Z`.",
        "",
        f"**{len(arts)} artifacts · {len(g['edges'])} derivation edges**",
        "",
    ]
    for kind, spec in kinds().items():
        group = [a for a in arts if a.kind == kind]
        parts.append(f"## {kind} ({len(group)}) — {spec['desc']}")
        parts.append("")
        rows = []
        for a in group:
            summary = str(a.meta.get("summary", "") or "").replace("|", "\\|")
            rows.append([
                a.id,
                rel(a.path),
                ",".join(a.labels) or "—",
                summary[:limits()["summary_chars"]] or a.title.replace("|", "\\|"),
                ",".join(parents_of.get(a.id, [])) or "—",
            ])
        parts.append(_fence(rows, ["id", "path", "labels", "summary", "derives_from"]))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_digest(month: str) -> str:
    """Human-readable Korean view DERIVED from the machine log. The .jsonl is the
    source of truth; this file is disposable and always regenerable."""
    entries = []
    p = log_path(month)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    icon = {"work": "•", "decision": "◆", "blocker": "▲", "note": "·", "handoff": "→"}
    out = [f"# {month} 작업 다이제스트", "",
           f"> GENERATED from `memory/log/{month}.jsonl` by `ops/bin/ops build`. 하드 카피 금지 — 원본을 고치세요.",
           ""]
    by_day: dict[str, list[dict]] = {}
    for e in entries:
        by_day.setdefault(e.get("ts", "")[:10], []).append(e)
    for day in sorted(by_day, reverse=True):
        out.append(f"## {day}")
        out.append("")
        for e in by_day[day]:
            mark = icon.get(e.get("kind", "note"), "·")
            out.append(f"- {mark} **{e.get('title','')}** `{e.get('kind','')}`")
            if e.get("body"):
                for ln in e["body"].splitlines():
                    out.append(f"  {ln}")
            if e.get("refs"):
                out.append("  ↳ " + ", ".join(f"`{r}`" for r in e["refs"]))
        out.append("")
    if not entries:
        out.append("_(기록 없음)_")
    return "\n".join(out).rstrip() + "\n"


def render_rules_block() -> str:
    hard = yaml.safe_load((OPS / "rules" / "hard.yml").read_text())["rules"]
    soft_txt = (OPS / "rules" / "soft.md").read_text()
    soft = re.findall(r"^## (SR-\d+) · (.+?)\n> (.+?)$", soft_txt, re.M)

    out = ["### Hard rules — enforced by hooks, not by your goodwill",
           "",
           "| id | stage | on violation | rule |",
           "|----|-------|--------------|------|"]
    for r in hard:
        st = "+".join(_stages(r))
        out.append(f"| `{r['id']}` | {st} | **{r['action']}** | {r['title']} |")
    out += ["",
            "Full text + escape hatches: `ops/rules/hard.yml`. A `deny` is not advice —",
            "the tool call does not run. Don't try to route around it; fix the cause or ask.",
            "",
            "### Soft rules — you enforce these; nothing else can",
            ""]
    for rid, name, stmt in soft:
        out.append(f"- **{rid}** ({name}) — {stmt}")
    out += ["", "Examples of each: `ops/rules/soft.md`."]
    return "\n".join(out)


def render_state_auto_block() -> str:
    entries = log_read(2)
    recent = entries[-6:][::-1]
    blockers = [e for e in entries if e.get("kind") == "blocker"][-4:][::-1]
    handoffs = [e for e in entries if e.get("kind") == "handoff"][-2:][::-1]
    stale = check_stale()
    g = build_graph()

    out = [f"**vault {len(g['nodes'])} artifacts · {len(g['edges'])} edges · "
           f"{len(stale)} stale**", ""]
    if handoffs:
        out.append("**이전 세션이 남긴 인계**")
        for e in handoffs:
            out.append(f"- {e['title']}" + (f" — {e['body'].splitlines()[0]}" if e.get("body") else ""))
        out.append("")
    if blockers:
        out.append("**미해결 blocker**")
        for e in blockers:
            out.append(f"- ▲ {e['title']} ({e['ts'][:10]})")
        out.append("")
    if stale:
        out.append("**stale 파생물 — 고치기 전엔 턴이 안 끝납니다 (HR-009)**")
        for s in stale[:8]:
            out.append(f"- `{s.child_path}` ← `{s.parent_path}` ({s.reason})")
        out.append("")
    out.append("**최근 로그**")
    for e in recent:
        out.append(f"- `{e['ts'][:10]}` {e.get('kind','')}: {e.get('title','')}")
    if not recent:
        out.append("- _(없음)_")
    out += ["", "더 보려면: `ops/bin/ops ctx log -n 30` / `ops/bin/ops ctx log --grep 키워드`"]
    return "\n".join(out)


# ------------------------------------------------------------- building ----

def planned_writes() -> dict[str, str]:
    """rel-path -> the content that SHOULD be on disk."""
    out: dict[str, str] = {"INDEX.md": render_index()}
    months = sorted(p.stem for p in (MEMORY / "log").glob("*.jsonl"))
    for m in months:
        out[f"memory/digest/{m}.md"] = render_digest(m)
    blocks = {
        "CLAUDE.md": {"rules": render_rules_block},
        "memory/STATE.md": {"auto": render_state_auto_block},
    }
    for relpath, mapping in blocks.items():
        p = ROOT / relpath
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        for name, fn in mapping.items():
            if name in generated_block_names(text):
                text = replace_block(text, name, fn())
        out[relpath] = text
    return out


def build(write: bool = True) -> list[str]:
    """Returns rel-paths whose on-disk content differs from what it should be."""
    changed = []
    for relpath, content in planned_writes().items():
        p = ROOT / relpath
        current = p.read_text(encoding="utf-8") if p.is_file() else None
        if current == content:
            continue
        changed.append(relpath)
        if write:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    return changed


# ---------------------------------------------------------- rule engine ----

@dataclass
class Verdict:
    rule_id: str
    action: str          # deny | warn
    title: str
    message: str
    detail: str = ""

    def render(self) -> str:
        head = f"[{self.rule_id}] {self.title}"
        parts = [head, self.message.strip()]
        if self.detail:
            parts.append(self.detail.strip())
        return "\n".join(parts)


_rules_cache: list[dict] | None = None


def hard_rules() -> list[dict]:
    global _rules_cache
    if _rules_cache is None:
        _rules_cache = yaml.safe_load((OPS / "rules" / "hard.yml").read_text())["rules"]
    return _rules_cache


def _stages(rule: dict) -> list[str]:
    s = rule.get("stage", "pre_tool")
    return s if isinstance(s, list) else [s]


def _escaped(rule: dict, ctx: dict) -> bool:
    """`OPS_ALLOW=HR-001 <cmd>` — a deliberate, visible, per-call override."""
    tok = rule.get("escape")
    if not tok:
        return False
    hay = " ".join([ctx.get("command", "") or "", os.environ.get(tok, "")])
    return bool(re.search(rf"{re.escape(tok)}=[\w,\-]*{re.escape(rule['id'])}", hay)
                or rule["id"] in os.environ.get(tok, "").split(","))


def evaluate(stage: str, ctx: dict) -> list[Verdict]:
    if "command_raw" not in ctx:
        ctx = dict(ctx)
        ctx["command_raw"] = ctx.get("command", "") or ""
        ctx["command"] = strip_heredocs(ctx["command_raw"])
    out: list[Verdict] = []
    for rule in hard_rules():
        if stage not in _stages(rule):
            continue
        if _escaped(rule, ctx):
            continue
        detail = None
        m = rule.get("match")
        if m:
            tools = m.get("tool")
            if tools and ctx.get("tool_name") not in tools:
                continue
            cre = m.get("command_regex")
            if cre and not re.search(cre, ctx.get("command", "") or "", re.X):
                continue
            detail = ""
        if rule.get("check"):
            fn = globals().get(rule["check"])
            if fn is None:
                continue
            try:
                detail = fn(ctx)
            except Exception as exc:                       # never brick a session
                detail = None
                out.append(Verdict(rule["id"], "warn", rule["title"],
                                   f"rule check crashed ({exc!r}) — enforcement skipped, "
                                   f"please fix ops/lib/core.py:{rule['check']}"))
            if detail is None:
                continue
        if detail is None:
            continue
        out.append(Verdict(rule["id"], rule["action"], rule["title"],
                           rule.get("message", ""), detail))
    return out


# --------------------------------------------------------- check helpers ----

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\t*\2\s*$", re.S | re.M)


def strip_heredocs(command: str) -> str:
    """A heredoc body is the DATA a command writes, not a command to run.

    Without this, `cat > f <<'EOF' ... rm -rf ops/ ... EOF` reads as a deletion
    and every file that documents a rule becomes unwritable.
    """
    return HEREDOC_RE.sub("<<HEREDOC_BODY_ELIDED", command or "")


def _exempt_from_content_scan(ctx: dict) -> bool:
    """Describing a rule is not violating it: the rule files and their tests
    are allowed to contain the very patterns they define."""
    pats = schema().get("content_scan_exempt", [])
    targets = _target_paths(ctx)
    if not targets:
        return False
    for p in targets:
        r = rel(p)
        if not any(fnmatch.fnmatch(r, pat)
                   or (pat.endswith("/**") and r.startswith(pat[:-3] + "/"))
                   for pat in pats):
            return False
    return True
REDIRECT_RE = re.compile(r"(?:>>?|\btee\b(?:\s+-\w+)*)\s+([\w./~$-]+)")
SEDI_RE = re.compile(r"\bsed\b[^|;&\n]*\s-\w*i\w*\b[^|;&\n]*?\s([\w./-]+)\s*$", re.M)


def _target_paths(ctx: dict) -> list[Path]:
    """Every path this tool call plausibly WRITES to, Bash included."""
    ti = ctx.get("tool_input") or {}
    out = []
    if ctx.get("tool_name") in EDIT_TOOLS:
        fp = ti.get("file_path") or ti.get("notebook_path")
        if fp:
            out.append(Path(fp))
    cmd = ctx.get("command") or ""
    if cmd:
        for m in REDIRECT_RE.finditer(cmd):
            out.append(Path(os.path.expanduser(m.group(1))))
        for m in SEDI_RE.finditer(cmd):
            out.append(Path(os.path.expanduser(m.group(1))))
    resolved = []
    for p in out:
        resolved.append(p if p.is_absolute() else (Path(ctx.get("cwd") or ROOT) / p))
    return resolved


def _written_text(ctx: dict) -> str:
    ti = ctx.get("tool_input") or {}
    chunks = [str(ti.get("content", "")), str(ti.get("new_string", "")),
              str(ti.get("new_source", "")),
              ctx.get("command_raw") or ctx.get("command", "") or ""]
    for e in ti.get("edits", []) or []:
        if isinstance(e, dict):
            chunks.append(str(e.get("new_string", "")))
    return "\n".join(c for c in chunks if c)


def check_generated_target(ctx: dict) -> str | None:
    hits = []
    for p in _target_paths(ctx):
        if is_generated_path(p):
            hits.append(f"{rel(p)} — fully generated")
            continue
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        names = generated_block_names(text)
        if not names:
            continue
        ti = ctx.get("tool_input") or {}
        old = str(ti.get("old_string", ""))
        touched = []
        for n in names:
            blk = get_block(text, n) or ""
            if old and old.strip() and old.strip() in blk:
                touched.append(n)
            elif ctx.get("tool_name") == "Write":
                new_blk = get_block(str(ti.get("content", "")), n)
                if new_blk is not None and new_blk.strip() != blk.strip():
                    touched.append(n)
        if touched:
            spans = {n: (s, e) for s, e, n in line_span_of_blocks(text)}
            hits += [f"{rel(p)} block `{n}` (lines {spans[n][0]}-{spans[n][1]})" for n in touched]
    return "Blocked target(s):\n  - " + "\n  - ".join(hits) if hits else None


SECRET_PATTERNS = [
    (r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY", "private key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    (r"\bgh[pousr]_[A-Za-z0-9]{30,}\b", "GitHub token"),
    (r"\bsk-[A-Za-z0-9_-]{20,}\b", "API secret key"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "Slack token"),
    (r"(?i)\b(?:api[_-]?key|secret|passwd|password|access[_-]?token)\s*[:=]\s*"
     r"['\"][^'\"\s]{16,}['\"]", "inline credential"),
]
PLACEHOLDER_RE = re.compile(r"(?i)x{3,}|your[_-]|example|placeholder|dummy|redacted|<[^>]+>|\.\.\.")


def check_secret_write(ctx: dict) -> str | None:
    if _exempt_from_content_scan(ctx):
        return None
    text = _written_text(ctx)
    hits = []
    for pat, label in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            if PLACEHOLDER_RE.search(m.group(0)):
                continue
            hits.append(f"{label}: …{m.group(0)[:12]}…")
    if re.search(r"\bgit\s+add\b[^\n;&|]*\s(?:\S*/)?\.env\b", ctx.get("command", "") or ""):
        hits.append("git add of a .env file")
    return "Detected:\n  - " + "\n  - ".join(dict.fromkeys(hits)) if hits else None


def check_state_size(ctx: dict) -> str | None:
    cap = limits()["state_md_bytes"]
    if ctx.get("stage") == "stop" or not ctx.get("tool_name"):
        if STATE_MD.is_file():
            n = STATE_MD.stat().st_size
            if n > cap:
                return f"memory/STATE.md is {n} bytes (cap {cap})."
        return None
    for p in _target_paths(ctx):
        if p.resolve() != STATE_MD.resolve():
            continue
        ti = ctx.get("tool_input") or {}
        cur = STATE_MD.stat().st_size if STATE_MD.is_file() else 0
        if ctx.get("tool_name") == "Write":
            size = len(str(ti.get("content", "")).encode())
        elif ctx.get("tool_name") in EDIT_TOOLS:
            size = cur - len(str(ti.get("old_string", "")).encode()) \
                       + len(str(ti.get("new_string", "")).encode())
        else:
            size = cur + len(_written_text(ctx).encode())
        if size > cap:
            return f"Result would be ~{size} bytes; cap is {cap}."
    return None


def _needs_frontmatter(p: Path) -> bool:
    r = rel(p)
    if not any(r.startswith(a + "/") for a in ARTIFACT_ROOTS):
        return False
    return not (p.name.endswith(".meta.yml") or p.name == ".gitkeep"
                or p.name.startswith("."))


def check_frontmatter_on_create(ctx: dict) -> str | None:
    if ctx.get("stage") == "stop" or not ctx.get("tool_name"):
        orphans = []
        for a in ARTIFACT_ROOTS:
            base = ROOT / a
            if not base.is_dir():
                continue
            for p in sorted(base.rglob("*")):
                if not p.is_file() or not _needs_frontmatter(p):
                    continue
                if any(part in SKIP_DIRS for part in p.parts):
                    continue
                meta, _ = read_meta(p)
                if not meta.get("id"):
                    orphans.append(rel(p))
        if orphans:
            return ("Unlabelled artifacts:\n  - " + "\n  - ".join(orphans[:15])
                    + f"\n  ({len(orphans)} total)  Fix all at once: `ops/bin/ops ingest`")
        return None
    for p in _target_paths(ctx):
        if p.is_file() or not _needs_frontmatter(p) or sidecar_for(p).is_file():
            continue
        if rel(p).startswith(drop_zone() + "/"):
            continue          # drop zone: land it now, `ops ingest` before the turn ends
        text = _written_text(ctx)
        if takes_frontmatter(p) and split_frontmatter(text)[0].get("id"):
            continue
        return f"New artifact without metadata: {rel(p)}"
    return None


BULK_PATTERNS = [
    (r"\bfind\b[^|;&\n]*\|\s*xargs\s+(?:cat|head|tail)\b", "find | xargs cat"),
    (r"\bfind\b[^|;&\n]*-exec\s+(?:cat|head)\b", "find -exec cat"),
    (r"\b(?:cat|head|tail)\b[^|;&\n]*\*\*?/\*", "glob-cat over a tree"),
    (r"\bgit\s+log\b(?![^|;&\n]*(?:-n\b|-\d|--max-count|--oneline))[^|;&\n]*-p\b", "full git log -p"),
]


def check_bulk_read(ctx: dict) -> str | None:
    cmd = ctx.get("command", "") or ""
    for pat, label in BULK_PATTERNS:
        if re.search(pat, cmd):
            return f"Pattern: {label}"
    if len(re.findall(r"(?:^|[;&|]\s*)(?:cat|head)\s", cmd)) >= 4:
        return "4+ file dumps in one command"
    if ctx.get("tool_name") == "Read":
        ti = ctx.get("tool_input") or {}
        fp = ti.get("file_path")
        if fp and not ti.get("limit") and Path(fp).is_file():
            n = Path(fp).stat().st_size
            if n > 120_000:
                return f"{rel(fp)} is {n // 1000}KB and no limit/offset was given"
    return None


def _under_artifact_root(p: Path) -> bool:
    r = rel(p)
    return any(r.startswith(a + "/") for a in ARTIFACT_ROOTS)


def check_impact_after_edit(ctx: dict) -> str | None:
    targets = [p for p in _target_paths(ctx) if _under_artifact_root(p)]
    if not targets:                                   # nothing derivable was touched
        return None
    g = build_graph()
    stale = {s.child_id: s for s in check_stale(g)}
    lines = []
    for p in targets:
        nid = id_for_path(p)
        if not nid:
            continue
        for d in descendants(nid, g):
            if d in stale:
                lines.append(f"{stale[d].child_path}  (derives from {rel(p)})")
    if not lines:
        return None
    return ("Now stale:\n  - " + "\n  - ".join(dict.fromkeys(lines))
            + "\nHR-009 will block the end of this turn until they are reconciled.")


def check_no_stale(ctx: dict) -> str | None:
    stale = check_stale()
    if not stale:
        return None
    lines = [f"{s.child_path}  ←  {s.parent_path}  [{s.reason}]" for s in stale]
    return "  - " + "\n  - ".join(lines[:20]) + (
        f"\n  ({len(lines)} total)" if len(lines) > 20 else "")


def check_generated_current(ctx: dict) -> str | None:
    changed = build(write=False)
    return "Out of date:\n  - " + "\n  - ".join(changed) if changed else None


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def session_file() -> Path:
    return META / "session.json"


def check_session_logged(ctx: dict) -> str | None:
    dirty = [l for l in _git("status", "--porcelain").splitlines()
             if l[3:].strip() and not l[3:].strip().startswith(".meta/")]
    if not dirty:
        return None
    started = ""
    if session_file().is_file():
        try:
            started = json.loads(session_file().read_text()).get("started_at", "")
        except (OSError, json.JSONDecodeError):
            pass
    if not started:
        return None
    if log_since(started):
        return None
    preview = [l.strip() for l in dirty[:8]]
    return ("Uncommitted changes with no log entry:\n  - " + "\n  - ".join(preview)
            + f"\n  ({len(dirty)} paths changed since {started})")


# ---------------------------------------------------------- session card ----

def session_card(source: str = "startup") -> str:
    cap = limits()["session_card_bytes"]
    state = STATE_MD.read_text(encoding="utf-8") if STATE_MD.is_file() else "_(STATE.md 없음)_"
    card = "\n".join([
        f"## 세션 컨텍스트 (memory/STATE.md · {source})",
        "",
        state.strip(),
        "",
        "---",
        "필요할 때만 더 읽기 — 통째로 읽지 마세요:",
        "  `ops/bin/ops ctx log -n 20` · `ops/bin/ops ctx log --grep X` · `ops/bin/ops find --label X`",
        "  `ops/bin/ops link why <id>` (출처) · `ops/bin/ops link impact <path>` (수정 시 영향)",
        "규칙 전문은 CLAUDE.md에 이미 로드돼 있습니다.",
    ])
    b = card.encode()
    if len(b) > cap:
        card = b[:cap].decode("utf-8", "ignore") + "\n…(잘림; `cat memory/STATE.md`)"
    return card
