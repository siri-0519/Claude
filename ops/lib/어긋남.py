"""어긋남 목록 — 막지 않고 목록에 둔다 (설계 4절).

파생물 옆의 `<파일>.meta.yml`:
    출처:
      - 경로: story/04-themes.md
        커밋: 1a2b3c4
        해시: <그때 본문의 sha256 앞 16자리>

원본의 해시가 달라진 파생물마다 한 항이다. 항에는 파생물 · 출처 · 어긋나기 시작한 날 · 바뀐 절이 있다.
같은 목록에 오르는 것: 기본 브랜치에 안 합쳐진 세션 브랜치, 폐기된 결정 번호를 단 주제 파일의 줄, 원본과 다른 생성 파일.
목록은 `memory/어긋남.md` 이고 스크립트가 세션마다 만든다. 커밋하지 않는다 (.gitignore). 시작한 날은 git log 에서 읽는다.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from 공통 import 설정, git, rel, 오늘, 절나누기, 주제파일들, 로그추가

목록파일 = "memory/어긋남.md"


def 해시(글: str) -> str:
    return hashlib.sha256(글.encode("utf-8")).hexdigest()[:16]


def 출처파일들(뿌리: Path) -> list[Path]:
    """파생물 옆의 <파생물>.meta.yml 전부."""
    return [p for p in sorted(뿌리.rglob("*.meta.yml"))
            if ".git" not in p.parts and ".meta" not in p.parts and not str(p).startswith(str(뿌리 / "ops"))]


def 읽기(p: Path) -> dict:
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def 바뀐절(뿌리: Path, 경로: str, 커밋: str) -> list[str]:
    """그때 커밋과 지금 사이에 본문이 달라진 절의 제목."""
    옛 = git(뿌리, "show", f"{커밋}:{경로}") if 커밋 else ""
    p = 뿌리 / 경로
    새 = p.read_text(encoding="utf-8") if p.is_file() else ""
    if not 옛:
        return ["(그때 커밋을 못 찾았다)"]
    def 절본문(글: str) -> dict[str, str]:
        줄 = 글.split("\n")
        d: dict[str, str] = {}
        절들 = 절나누기(글)
        if not 절들:
            return {"(제목 없음)": 글}
        d["(머리)"] = "\n".join(줄[:절들[0][2]])
        for _, 제목, s, e in 절들:
            d[제목] = "\n".join(줄[s:e])
        return d
    a, b = 절본문(옛), 절본문(새)
    나온것 = []
    for k in list(a) + [k for k in b if k not in a]:
        if a.get(k, "") != b.get(k, ""):
            나온것.append(k)
    return 나온것


def 파생물항들(뿌리: Path) -> list[dict]:
    항들 = []
    for sc in 출처파일들(뿌리):
        파생물 = rel(뿌리, sc.with_name(sc.name[:-len(".meta.yml")]))
        for 출처 in 읽기(sc).get("출처") or []:
            경로 = str(출처.get("경로", ""))
            p = 뿌리 / 경로
            지금해시 = 해시(p.read_text(encoding="utf-8")) if p.is_file() else ""
            if 지금해시 != str(출처.get("해시", "")):
                커밋 = str(출처.get("커밋", ""))
                항들.append({"파생물": 파생물, "출처": 경로, "시작": 시작일(뿌리, 경로, 커밋),
                             "바뀐절": 바뀐절(뿌리, 경로, 커밋) if p.is_file() else ["(출처 파일이 없다)"]})
    return 항들


def 시작일(뿌리: Path, 경로: str, 커밋: str) -> str:
    """어긋나기 시작한 날 — 고정한 커밋 뒤에 출처를 처음 바꾼 커밋의 날. 커밋 안 된 변경이면 오늘이다.
    파일에 적어 두지 않고 git 에서 읽는다 — 목록 파일은 세션마다 다시 만들고 커밋하지 않는다."""
    if 커밋:
        out = git(뿌리, "log", "--reverse", "--format=%ad", "--date=short", f"{커밋}..HEAD", "--", 경로)
        if out:
            return out.split("\n")[0]
    return 오늘()


def 브랜치항들(뿌리: Path, c: dict) -> list[str]:
    기본 = c["기본브랜치"]
    앞 = "refs/remotes/origin/" + c["세션브랜치"].rstrip("/")
    refs = git(뿌리, "for-each-ref", "--format=%(refname:short) %(committerdate:short)", 앞)
    기준 = "origin/" + 기본 if git(뿌리, "rev-parse", "--verify", "-q", "origin/" + 기본) else "HEAD"
    나온것 = []
    for ln in refs.split("\n") if refs else []:
        이름, _, 날 = ln.partition(" ")
        if git(뿌리, "merge-base", "--is-ancestor", 이름, 기준) == "" and \
                _돌려줌(뿌리, "merge-base", "--is-ancestor", 이름, 기준) != 0 and \
                _돌려줌(뿌리, "merge-base", "--is-ancestor", 이름, "HEAD") != 0:
            나온것.append(f"{이름} ({날})")
    return 나온것


def _돌려줌(뿌리: Path, *a: str) -> int:
    import subprocess
    return subprocess.run(["git", "-C", str(뿌리), *a], capture_output=True).returncode


def 폐기결정항들(뿌리: Path, c: dict) -> list[str]:
    f = c.get("결정로그") or ""
    p = 뿌리 / f if f else None
    if not p or not p.is_file():
        return []
    폐기: set[str] = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        m = re.search(r"\b(D-\d{3,})\b", ln)
        if m and ("폐기" in ln or "~~" in ln):
            폐기.add(m.group(1))
    if not 폐기:
        return []
    나온것 = []
    for t in 주제파일들(뿌리, c):
        if rel(뿌리, t) == f:
            continue
        for i, ln in enumerate(t.read_text(encoding="utf-8").splitlines(), 1):
            for n in 폐기:
                if n in ln and "~~" not in ln:
                    나온것.append(f"`{rel(뿌리, t)}` {i}줄: {n}")
    return 나온것


def 목록(뿌리: Path, c: dict | None = None) -> tuple[str, list[str], dict[str, str]]:
    """(파일 내용, 항의 열쇠 목록, 열쇠 → 그 항의 줄)."""
    c = c or 설정(뿌리)
    import 생성
    열쇠들: list[str] = []
    항줄: dict[str, str] = {}
    줄 = ["# 어긋남 목록", "",
          "원본이 바뀌어 낡은 것이 여기 오른다. 파생물은 다른 파일(출처)을 읽고 다시 쓴 파일이고, `<파생물> ← <출처>` 는 "
          "출처가 바뀐 뒤 파생물이 아직 따라오지 않았다는 뜻이다. 어긋난 날은 출처가 바뀐 날이다.",
          "이 목록은 막지 않는다. 항마다 이번 세션에 이렇게 한다. 파생물을 출처의 바뀐 절에 맞춰 고치고 `ops ack <파생물>` 을 돌린다. "
          "고칠 것이 없으면 `ops ack <파생물> --그대로 \"<이유>\"` 를 돌린다. 둘 다 항을 지운다.",
          "스크립트가 세션 시작마다 다시 만들고 커밋하지 않는다.", ""]
    파생 = 파생물항들(뿌리)
    줄 += ["## 파생물", ""]
    if 파생:
        for 항 in 파생:
            k = f"`{항['파생물']}` ← `{항['출처']}`"
            열쇠들.append(k)
            항줄[k] = f"- {k} · 어긋난 날 {항['시작']} · 바뀐 절: {' · '.join(항['바뀐절']) or '(없음)'}"
            줄.append(항줄[k])
    else:
        줄.append("없다.")
    줄 += ["", "## 기본 브랜치에 안 합쳐진 세션 브랜치", "",
           "합칠지는 사용자가 정한다. 사용자가 합치라고 하면 `git merge <브랜치>` 로 합치고 push 한다.", ""]
    가지 = 브랜치항들(뿌리, c)
    if 가지:
        for b in 가지:
            k = "브랜치 " + b.split(" ")[0]
            열쇠들.append(k)
            항줄[k] = f"- {b}"
            줄.append(항줄[k])
    else:
        줄.append("없다.")
    줄 += ["", "## 폐기된 결정 번호를 단 줄", "",
           "폐기된 결정을 아직 가리키는 줄이다. 그 줄을 지금 맞는 문장으로 고치거나 지운다.", ""]
    폐 = 폐기결정항들(뿌리, c)
    if 폐:
        for x in 폐:
            열쇠들.append(x)
            항줄[x] = f"- {x}"
            줄.append(항줄[x])
    else:
        줄.append("없다.")
    줄 += ["", "## 원본과 다른 생성 파일", "", "`ops build` 를 돌리면 맞는다.", ""]
    생 = [x for x in 생성.다른것(뿌리, c) if not x.startswith("memory/어긋남.md")]
    if 생:
        for x in 생:
            열쇠들.append(x)
            항줄[x] = f"- {x}"
            줄.append(항줄[x])
    else:
        줄.append("없다.")
    return "\n".join(줄) + "\n", 열쇠들, 항줄


def 만들기(뿌리: Path, c: dict | None = None) -> bool:
    글, _, _ = 목록(뿌리, c)
    p = 뿌리 / 목록파일
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_file() and p.read_text(encoding="utf-8") == 글:
        return False
    p.write_text(글, encoding="utf-8")
    return True


def ack(뿌리: Path, 파생물: str, 그대로: str | None = None) -> str:
    p = 뿌리 / 파생물
    sc = p.with_name(p.name + ".meta.yml")
    if not sc.is_file():
        return f"{파생물} 옆에 .meta.yml 이 없다. 파생물이 아니다."
    d = 읽기(sc)
    head = git(뿌리, "rev-parse", "--short", "HEAD")
    for 출처 in d.get("출처") or []:
        q = 뿌리 / str(출처.get("경로", ""))
        if q.is_file():
            출처["해시"] = 해시(q.read_text(encoding="utf-8"))
            출처["커밋"] = head
    sc.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if 그대로:
        로그추가(뿌리, "ack", f"{파생물} 은 그대로 둔다", 그대로, [파생물])
    만들기(뿌리)
    return f"{파생물} 을 다시 고정했다 ({head})" + (f" — 그대로: {그대로}" if 그대로 else "")


def 새로만들기(뿌리: Path, 파생물: str, 출처들: list[str]) -> str:
    """파생물 옆에 <파생물>.meta.yml 을 만든다. `ops 출처 <파생물> <출처>...`"""
    p = 뿌리 / 파생물
    if not p.is_file():
        return f"{파생물} 이 없다."
    head = git(뿌리, "rev-parse", "--short", "HEAD")
    항 = []
    for s in 출처들:
        q = 뿌리 / s
        if not q.is_file():
            return f"출처 {s} 가 없다."
        항.append({"경로": s, "커밋": head, "해시": 해시(q.read_text(encoding="utf-8"))})
    sc = p.with_name(p.name + ".meta.yml")
    sc.write_text(yaml.safe_dump({"출처": 항}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    만들기(뿌리)
    return f"{rel(뿌리, sc)} 을 만들었다 (출처 {len(항)})"
