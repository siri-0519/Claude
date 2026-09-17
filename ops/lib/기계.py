"""기계 규칙 — ops/rules/기계.yml 의 대장을 읽고, 이름마다의 검사를 돈다.

    ops check          지금 작업 트리에서 걸리는 것
    ops check --커밋   스테이지된 것만 (pre-commit 이 부른다)
    ops rules          대장을 보인다
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from 공통 import 설정, git, rel, 주제파일들, 절나누기, 옛줄전부

대장파일 = "ops/rules/기계.yml"
제목괄호 = re.compile(r"「.*?」")
따옴표안 = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")   # 사용자나 문서의 말을 그대로 옮긴 자리 — 상대 날짜로 걸지 않는다 (2026-09-17)
자리들 = ("저장직전", "명령직전", "도구직후", "답끝", "커밋직전", "push직전", "세션시작", "원격")
목적들 = ("규칙 준수", "맥락 유지", "토큰 절약", "정보 추적성", "좋은 설명")   # 설계 1절 — 규칙은 전부 이 다섯에서 파생된다 (2026-09-17)
시험종류 = ("selftest", "시뮬", "읽힘", "워크플로")


def 대장(뿌리: Path) -> list[dict]:
    p = 뿌리 / 대장파일
    if not p.is_file():
        return []
    return yaml.safe_load(p.read_text(encoding="utf-8")) or []


def 시험참조검사(뿌리: Path, 참조: str) -> str:
    """시험 칸의 한 항이 실재하는가. "selftest: <시험 이름>" 은 ops/test/selftest.py 에 그 이름이 있어야 하고, "시뮬: S<n>" 은
    ops/test/시뮬.py 의 시나리오여야 하고, "워크플로: <파일>" 은 .github/workflows 에 있어야 한다. "읽힘: <기록>" 은 글이 있으면 된다.
    문제가 없으면 빈 문자열."""
    m = re.match(r"^\s*(selftest|시뮬|읽힘|워크플로)\s*:\s*(.+?)\s*$", str(참조))
    if not m:
        return f"시험 「{참조}」 는 「<종류>: <무엇>」 꼴이 아니다 (종류는 {' · '.join(시험종류)})"
    종류, 무엇 = m.group(1), m.group(2)
    if 종류 == "selftest":
        p = 뿌리 / "ops/test/selftest.py"
        if not (p.is_file() and 무엇 in p.read_text(encoding="utf-8")):
            return f"시험 「{참조}」: ops/test/selftest.py 에 그 이름의 시험이 없다"
    elif 종류 == "시뮬":
        p = 뿌리 / "ops/test/시뮬.py"
        if not (p.is_file() and re.search(r'"' + re.escape(무엇) + r'":\s*dict\(', p.read_text(encoding="utf-8"))):
            return f"시험 「{참조}」: ops/test/시뮬.py 에 그 시나리오가 없다"
    elif 종류 == "워크플로":
        if not (뿌리 / ".github/workflows" / 무엇).is_file():
            return f"시험 「{참조}」: .github/workflows/{무엇} 이 없다"
    return ""


def 목적검사(자리이름: str, 목적: object) -> list[str]:
    if not 목적 or not isinstance(목적, list):
        return [f"{자리이름}: 목적 칸이 없다 — 목적 다섯({' · '.join(목적들)}) 가운데 하나 이상을 적는다. 어디에도 안 닿는 규칙은 뺀다"]
    return [f"{자리이름}: 목적 「{x}」 는 다섯에 없다 ({' · '.join(목적들)})" for x in 목적 if x not in 목적들]


def 대장검사(뿌리: Path) -> list[str]:
    """규칙마다 여섯 칸(이름 · 문장 · 자리 · 검사 · 목적 · 시험)이 다 있고, 목적은 다섯 가운데 것이고, 시험은 실재하나. 없으면 커밋을 막는다."""
    문제 = []
    이름들: set[str] = set()
    for i, r in enumerate(대장(뿌리), 1):
        for k in ("이름", "문장", "자리", "검사", "목적", "시험"):
            if not r.get(k):
                문제.append(f"{대장파일} {r.get('이름') or f'{i}번째 규칙'}: {k} 칸이 없다")
        for a in r.get("자리") or []:
            if a not in 자리들:
                문제.append(f"{대장파일} {r.get('이름', i)}: 자리 {a} 는 없는 자리다 ({' · '.join(자리들)})")
        if r.get("목적"):
            문제 += 목적검사(f"{대장파일} {r.get('이름', i)}", r.get("목적"))
        for 참조 in (r.get("시험") or []) if isinstance(r.get("시험"), list) else ([r["시험"]] if r.get("시험") else []):
            x = 시험참조검사(뿌리, 참조)
            if x:
                문제.append(f"{대장파일} {r.get('이름', i)}: {x}")
        if r.get("이름") in 이름들:
            문제.append(f"{대장파일}: 이름 {r['이름']} 이 겹친다")
        이름들.add(r.get("이름"))
    return 문제


판단표절 = "규칙마다 목적과 시험"


def 판단대장(뿌리: Path) -> dict[str, dict]:
    """ops/rules/판단.md 끝의 「규칙마다 목적과 시험」 표 — 번호 → {목적: [...], 시험: [...]}. 판정 모델에는 넘기지 않는 절이다."""
    from 판정 import 규칙파일자리
    p = 규칙파일자리(뿌리)
    if not p.is_file():
        return {}
    글 = p.read_text(encoding="utf-8")
    줄 = 글.split("\n")
    나온것: dict[str, dict] = {}
    for 수준, 제목, s, e in 절나누기(글):
        if 판단표절 in 제목:
            for ln in 줄[s:e]:
                m = re.match(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", ln)
                if m:
                    나온것[m.group(1)] = {"목적": [x.strip() for x in m.group(2).split("·") if x.strip()],
                                        "시험": [x.strip() for x in m.group(3).split(" · ") if x.strip()]}
    return 나온것


def 판단대장검사(뿌리: Path) -> list[str]:
    """판단 규칙마다 표에 행이 있고, 목적은 다섯 가운데 것이고, 시험은 실재하나."""
    from 판정 import 규칙전문들, 규칙파일자리
    문제 = []
    표 = 판단대장(뿌리)
    파일 = rel(뿌리, 규칙파일자리(뿌리))
    for 번호 in 규칙전문들(뿌리):
        if 번호 not in 표:
            문제.append(f"{파일}: 규칙 {번호} 이 「{판단표절}」 표에 없다 — 「| {번호} | <목적> | <시험> |」 행을 더한다")
            continue
        문제 += 목적검사(f"{파일} 규칙 {번호}", 표[번호]["목적"])
        if not 표[번호]["시험"]:
            문제.append(f"{파일} 규칙 {번호}: 시험 칸이 비었다")
        for 참조 in 표[번호]["시험"]:
            x = 시험참조검사(뿌리, 참조)
            if x:
                문제.append(f"{파일} 규칙 {번호}: {x}")
    return 문제


훅글파일 = "ops/rules/훅-글.md"


def 훅글항들(뿌리: Path) -> list[dict]:
    """훅-글.md 의 이 레포 항(### A<n>) — {번호, 제목, 목적, 판정}."""
    p = 뿌리 / 훅글파일
    if not p.is_file():
        return []
    나온것: list[dict] = []
    for 덩이 in re.split(r"^(?=### A\d+)", p.read_text(encoding="utf-8"), flags=re.M):
        m = re.match(r"^### (A\d+)\s*·\s*(.*)$", 덩이, re.M)
        if not m:
            continue
        항 = {"번호": m.group(1), "제목": m.group(2).strip(), "목적": "", "판정": ""}
        for k in ("목적", "판정"):
            mm = re.search(rf"^- {k}:\s*(.*)$", 덩이, re.M)
            if mm:
                항[k] = mm.group(1).strip()
        나온것.append(항)
    return 나온것


def 훅글대장검사(뿌리: Path) -> list[str]:
    문제 = []
    for 항 in 훅글항들(뿌리):
        if not any(m in 항["목적"] for m in 목적들):
            문제.append(f"{훅글파일} {항['번호']}: 목적 줄에 목적 다섯({' · '.join(목적들)}) 가운데 것이 없다")
        if not 항["판정"]:
            문제.append(f"{훅글파일} {항['번호']}: 판정 줄이 없다 — 읽힘이나 시뮬로 본 결과를 적는다")
    return 문제


def 규칙대장(뿌리: Path, c: dict | None = None) -> list[str]:
    """클로드가 읽는 규칙 전부에 목적과 시험이 달려 있나 — 기계 규칙 · 판단 규칙 · 훅 글. 하나라도 빠지면 커밋을 막는다 (2026-09-17)."""
    return 대장검사(뿌리) + 판단대장검사(뿌리) + 훅글대장검사(뿌리)


def 목적별(뿌리: Path) -> dict[str, dict[str, list[str]]]:
    """목적 다섯마다 그것을 지키는 기계 규칙 · 판단 규칙 · 훅 글의 이름."""
    from 판정 import 규칙이름들
    표: dict[str, dict[str, list[str]]] = {m: {"기계": [], "판단": [], "훅글": []} for m in 목적들}
    for r in 대장(뿌리):
        for m in r.get("목적") or []:
            if m in 표:
                표[m]["기계"].append(str(r.get("이름")))
    이름 = 규칙이름들(뿌리)
    for 번호, 항 in 판단대장(뿌리).items():
        for m in 항["목적"]:
            if m in 표:
                표[m]["판단"].append(f"{번호} {이름.get(번호, '')}".strip())
    for 항 in 훅글항들(뿌리):
        for m in 목적들:
            if m in 항["목적"]:
                표[m]["훅글"].append(항["번호"])
    return 표


def 보이기(뿌리: Path) -> str:
    줄 = ["| 이름 | 규칙 | 자리 | 검사 | 목적 | 시험 |", "|---|---|---|---|---|---|"]
    for r in 대장(뿌리):
        시험 = r.get("시험") if isinstance(r.get("시험"), list) else [r.get("시험")] if r.get("시험") else []
        줄.append(f"| {r.get('이름','')} | {r.get('문장','')} | {' · '.join(r.get('자리') or [])} | {r.get('검사','')} | "
                 f"{' · '.join(r.get('목적') or [])} | {' · '.join(str(x) for x in 시험)} |")
    return "\n".join(줄)


# ------------------------------------------------------------- 검사들 ----

def 상대날짜(글: str, c: dict) -> list[str]:
    본문 = 따옴표안.sub("", 제목괄호.sub("", 글))
    본문 = re.sub(r"```.*?```", "", 본문, flags=re.S)
    본문 = re.sub(r"`[^`]*`", "", 본문)
    return sorted({w for w in c["상대날짜"] if w and w in 본문})


def 상대날짜_새줄(글: str, c: dict, 옛글: str = "") -> list[str]:
    옛 = set(x.strip() for x in 옛글.split("\n"))
    문제 = []
    울타리 = False
    for i, ln in enumerate(글.split("\n"), 1):
        if ln.startswith("```"):
            울타리 = not 울타리
            continue
        if 울타리 or ln.strip() in 옛:
            continue
        걸린 = 상대날짜(ln, c)
        if 걸린:
            문제.append(f"{i}줄: {' '.join(걸린)} — 오늘 날짜에서 센 날짜로 적는다: {ln.strip()[:50]}")
    return 문제


def 안쓰는말(글: str, c: dict) -> list[str]:
    """답이나 문서에 사용자가 쓰지 말라고 한 말(.ops.yml 의 안쓰는말)이 있나. 따옴표 · 「」 · 코드 안은 옮긴 말이라 보지 않는다.
    항마다 「<걸린 꼴>(<말>) → <대신 쓸 말>」 한 줄. 사용자가 2026-09-14 와 2026-09-17 에 같은 말을 두 번 짚어서 기계가 막는다."""
    본문 = 따옴표안.sub("", 제목괄호.sub("", 글))
    본문 = re.sub(r"```.*?```", "", 본문, flags=re.S)
    본문 = re.sub(r"`[^`]*`", "", 본문)
    나온것 = []
    for 항 in c.get("안쓰는말") or []:
        if not isinstance(항, dict):
            항 = {"말": str(항)}
        찾기 = str(항.get("찾기") or "") or ((r"(?<![가-힣])" + re.escape(str(항.get("말") or ""))) if 항.get("말") else "")
        if not 찾기:
            continue
        m = re.search(찾기, 본문)
        if m:
            나온것.append(f"「{m.group(0)}」({항.get('말')}) → {항.get('대신') or '그것이 무엇인지를 풀어 적는다'}")
    return 나온것


def 안쓰는말_새줄(글: str, c: dict, 옛글: str = "") -> list[str]:
    """새 줄(옛글에 없는 줄)에서만 안 쓰는 말을 찾는다. 코드 울타리 안은 보지 않는다."""
    옛 = set(x.strip() for x in 옛글.split("\n"))
    문제 = []
    울타리 = False
    for i, ln in enumerate(글.split("\n"), 1):
        if ln.startswith("```"):
            울타리 = not 울타리
            continue
        if 울타리 or ln.strip() in 옛:
            continue
        걸린 = 안쓰는말(ln, c)
        if 걸린:
            문제.append(f"{i}줄: 쓰지 않기로 한 말 {' / '.join(걸린)} — 화살표 뒤의 말 가운데 뜻에 맞는 것으로 적는다: {ln.strip()[:50]}")
    return 문제


def 안쓰는말파일인가(r: str, c: dict) -> bool:
    """안 쓰는 말을 새 줄에서 보는 파일 — 규칙 · 훅 글 · 목차 · 설명서 · 주제 파일 등 .md 와 .yml 전부. 기록(memory/)과 일지, 그 말의 목록 자체가 든 설정 파일은 뺀다."""
    from 공통 import 설정파일
    return (r.endswith(".md") or r.endswith(".yml")) and r != 설정파일 and not r.startswith("memory/") and r != "worklog.md" and not r.startswith(".git/")


def 목차크기(뿌리: Path, c: dict, 글: str | None = None) -> list[str]:
    p = 뿌리 / "CLAUDE.md"
    if 글 is None:
        if not p.is_file():
            return []
        글 = p.read_text(encoding="utf-8")
    줄수 = len(글.split("\n"))
    문제 = []
    방법 = ("이번 답 안에서 내용을 그 주제 파일(없으면 새로 만들고 목차에 한 줄 더한다)로 옮기고 목차에는 「이런 말이 나오면 이 파일을 읽는다」 한 줄만 "
          "남긴 뒤, 하려던 저장이나 커밋을 다시 한다")
    if 줄수 > int(c["목차최대줄"]):
        문제.append(f"CLAUDE.md 가 {줄수}줄이다. {c['목차최대줄']}줄 안으로 줄인다. {방법}")
    for 수준, 제목, s, e in 절나누기(글):
        if 수준 == 2 and e - s > int(c["절최대줄"]):
            문제.append(f"CLAUDE.md 의 「{제목}」 절(그 제목부터 다음 제목 앞까지)이 {e - s}줄이다. {c['절최대줄']}줄 안으로 줄인다. {방법}")
    return 문제


def 목차행(뿌리: Path, c: dict) -> list[str]:
    """주제 파일마다 .ops.yml 의 목차에 행이 하나 있다. 2026-09-14~17 에 있던 「파일크기」(30KB 를 넘으면 절로 나눈다) 대신 건다 —
    파일을 나누는 기준은 크기가 아니라 목차 행이고, 행 없는 파일은 목차로 못 찾아 읽히지 않는다 (설계 3절)."""
    목차파일 = {str(항.get("파일", "")) for 항 in (c.get("목차") or [])}
    결정로그 = str(c.get("결정로그") or "")
    문제 = []
    for p in 주제파일들(뿌리, c):
        r = rel(뿌리, p)
        if r == 결정로그 or r in 목차파일:
            continue
        문제.append(f"{r} 는 주제 파일인데 .ops.yml 의 목차에 행이 없다. 목차에 「- 말: <사용자가 이 파일의 내용을 물을 때 쓸 낱말들> / 파일: {r}」 항목을 더하고 "
                  f"`ops build` 를 돌린 뒤 다시 커밋한다. 파일을 지우거나 다른 파일에 합치는 것으로 넘기지 않는다")
    for r in sorted(목차파일):
        if r and not (뿌리 / r).is_file():
            문제.append(f".ops.yml 의 목차가 가리키는 {r} 가 없다. 파일을 옮겼으면 목차의 파일 칸을 새 경로로 고치고, 없앴으면 그 항목을 지운 뒤 `ops build` 를 돌린다")
    # ops/rules/ 는 규칙 파일 자리다. 주제 파일이 거기 생기면 제외 목록(ops/**) 때문에 목차 검사도 못 보고 목차로도 못 찾는다 —
    # 2026-09-17 시뮬 S13 에서 haiku 가 diet.md 를 ops/rules/ 에 만들었다.
    규칙파일 = {"판단.md", "훅-글.md", Path(str(c.get("판단규칙") or "ops/rules/판단.md")).name}
    for p in sorted((뿌리 / "ops" / "rules").glob("*.md")) if (뿌리 / "ops" / "rules").is_dir() else []:
        if p.name not in 규칙파일:
            문제.append(f"ops/rules/{p.name} 는 규칙 파일이 아니라 주제 파일이다. ops/rules/ 는 규칙 파일(판단.md · 훅-글.md) 자리라, 이 파일을 레포 맨 위({p.name})로 옮기고 "
                      f".ops.yml 의 목차에 행을 더한 뒤 `ops build` 를 돌리고 다시 커밋한다")
    return 문제


def 작업로그(뿌리: Path) -> list[str]:
    """worklog.md 를 더하거나 고친 채로 커밋하는 것을 막는다. 추적에서 빼는 것(D)은 바로 그 일이라 막지 않는다."""
    for ln in git(뿌리, "diff", "--cached", "--name-status").split("\n"):
        if ln.endswith("\tworklog.md") and not ln.startswith("D"):
            return ["worklog.md 가 스테이지에 있다. 커밋하지 않는다: git rm --cached worklog.md"]
    return []


def 브랜치(뿌리: Path, c: dict) -> list[str]:
    """커밋 안 한 변경 · push 안 한 커밋 · 원격에 없는 브랜치."""
    문제 = []
    상태 = [x for x in git(뿌리, "status", "--porcelain").split("\n") if x.strip()]
    if 상태:
        문제.append(f"커밋 안 한 변경이 {len(상태)}개 있다 (스크립트가 만든 STATUS.md · README.md 도 그대로 커밋한다): " + " ".join(x[3:] for x in 상태[:5]))
    가지 = git(뿌리, "rev-parse", "--abbrev-ref", "HEAD")
    if 가지 and 가지 != "HEAD":
        if not git(뿌리, "rev-parse", "--verify", "-q", f"origin/{가지}"):
            문제.append(f"브랜치 {가지} 가 원격에 없다: git push -u origin {가지}")
        else:
            n = git(뿌리, "rev-list", "--count", f"origin/{가지}..HEAD")
            if n and n != "0":
                문제.append(f"push 안 한 커밋이 {n}개 있다: git push origin {가지}")
    return 문제


보호자리 = ("ops", ".claude", "memory", ".ops.yml", ".git")


def 셸검사(명령: str, 뿌리: Path, c: dict) -> list[str]:
    """Bash 직전 — 이력을 다시 쓰는 push, 기계 지우기, 생성 파일로의 재지정."""
    import 생성
    문제 = []
    # heredoc 본문(cat > 파일 <<'EOF' … EOF)은 파일 내용이지 명령이 아니다 — 시험 코드의 글자가 걸렸다 (2026-09-14)
    명령 = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1(?:\n|$)", "<<HEREDOC\n", 명령, flags=re.S)
    if re.search(r"\bgit\b[^|;&]*\bpush\b[^|;&]*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s--delete\b|\s-d\b|\s\+\S|\s:\S)", 명령):
        문제.append("이 명령은 하지 않는다 — 이력을 다시 쓰거나 원격 브랜치를 지우는 push(--force · --delete · :브랜치)다. "
                    "원격과 다르면 `git pull --no-rebase` 로 합친 뒤 깃발 없는 보통 push 를 한 번 한다. "
                    "원격 브랜치를 지우려던 것이면 그 push 를 버리고, 원격 브랜치는 사람이 GitHub 에서 지운다고 사용자에게 알린다")
    if re.search(r"\bgit\b[^|;&]*\b(filter-branch|filter-repo)\b", 명령):
        문제.append("이력을 다시 쓰는 명령(filter-branch · filter-repo)이다. 하지 않는다. 이미 있는 커밋은 그대로 두고 새 커밋으로 고친다")
    # rm -r 의 대상은 그 명령 하나(&& · ; · | 앞까지)의 인자만 본다 — 뒤에 이어진 명령의 경로까지 보고 잘못 막았다 (2026-09-14 실측)
    for m in re.finditer(r"\brm\b\s+(-[a-zA-Z]*r[a-zA-Z]*|--recursive)\b([^|;&\n]*)", 명령):
        for w in m.group(2).split():
            w2 = w.strip("'\"").rstrip("/")
            if w2.startswith("-") or "__pycache__" in w2:
                continue
            base = w2.split("/")[0] if not w2.startswith("/") else rel(뿌리, w2).split("/")[0]
            if w2 in (".", "*", "/") or base in 보호자리 or rel(뿌리, w2) in 보호자리:
                문제.append(f"기계({w2} — ops/ · .claude/ · memory/ · .ops.yml 이 기계다)를 통째로 지우는 명령이다. 하지 않는다. "
                            "지울 파일이 있으면 이름을 하나씩 대고 `git rm <파일>` 로 지운다")
    for m in re.finditer(r"(?:>>?|\btee\b(?:\s+-a)?)\s*([\w./~-]+)", 명령):
        if 생성.생성파일인가(뿌리, m.group(1)):
            문제.append(생성.생성파일설명(뿌리, m.group(1), c) + " 셸로 덮어쓰지 않는다.")
    for m in re.finditer(r"\bsed\b\s+-i[^|;&]*?\s([\w./~-]+\.md)\b", 명령):
        if 생성.생성파일인가(뿌리, m.group(1)):
            문제.append(생성.생성파일설명(뿌리, m.group(1), c) + " sed 로 고치지 않는다.")
    return 문제


# ------------------------------------------------------------- 모아서 ----

def 지금검사(뿌리: Path, c: dict | None = None) -> list[str]:
    """작업 트리에서 지금 걸리는 것 전부 (ops check)."""
    import 생성, 지금, 표시
    c = c or 설정(뿌리)
    문제 = 규칙대장(뿌리, c)
    문제 += 표시.검사_새줄(뿌리, c, 스테이지=False)
    옛 = "\n".join(옛줄전부(뿌리, c))
    for p in 주제파일들(뿌리, c):
        r = rel(뿌리, p)
        for x in 상대날짜_새줄(p.read_text(encoding="utf-8"), c, 옛):
            문제.append(f"{r} {x}")
    for r in git(뿌리, "ls-files", "-co", "--exclude-standard").split("\n"):
        if r and 안쓰는말파일인가(r, c) and (뿌리 / r).is_file():
            옛파일 = git(뿌리, "show", f"HEAD:{r}")
            for x in 안쓰는말_새줄((뿌리 / r).read_text(encoding="utf-8", errors="ignore"), c, 옛파일):
                문제.append(f"{r} {x}")
    문제 += 목차크기(뿌리, c)
    문제 += 지금.검사(뿌리, c)
    문제 += 목차행(뿌리, c)
    문제 += 생성.다른것(뿌리, c)
    return 문제


def 커밋검사(뿌리: Path, c: dict | None = None) -> list[str]:
    """스테이지에서 걸리는 것 전부 (pre-commit)."""
    import 생성, 지금, 표시
    c = c or 설정(뿌리)
    문제 = 규칙대장(뿌리, c)
    문제 += 표시.검사_새줄(뿌리, c, 스테이지=True)
    문제 += 표시.제안이확인으로(뿌리, c, 스테이지=True)
    스테이지된 = [x for x in git(뿌리, "diff", "--cached", "--name-only").split("\n") if x]
    주제 = {rel(뿌리, p) for p in 주제파일들(뿌리, c)}
    옛 = "\n".join(옛줄전부(뿌리, c))
    for r in 스테이지된:
        if 안쓰는말파일인가(r, c):
            for x in 안쓰는말_새줄(git(뿌리, "show", f":{r}"), c, git(뿌리, "show", f"HEAD:{r}")):
                문제.append(f"{r} {x}")
        if r not in 주제:
            continue
        새 = git(뿌리, "show", f":{r}")
        for x in 상대날짜_새줄(새, c, 옛):
            문제.append(f"{r} {x}")
    if "CLAUDE.md" in 스테이지된:
        문제 += 목차크기(뿌리, c, git(뿌리, "show", ":CLAUDE.md"))
    문제 += 지금.검사(뿌리, c)
    문제 += 목차행(뿌리, c)
    문제 += 작업로그(뿌리)
    for x in 생성.다른것(뿌리, c):
        문제.append(x)
    for r in 생성.만들것(뿌리, c):
        if git(뿌리, "ls-files", "--error-unmatch", "--", r) and git(뿌리, "diff", "--name-only", "--", r):
            문제.append(f"{r} 가 스테이지와 다르다: git add {r}")
    return 문제
