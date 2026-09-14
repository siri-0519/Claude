"""「지금」 절 — 주제 파일 맨 위의 지금 참인 것. 사실은 한 자리에만 있다.

STATUS.md 와 README.md 와 CLAUDE.md 목차의 셋째 칸은 여기서 만든다. 손으로 고치면 훅이 막는다.
"""
from __future__ import annotations

from pathlib import Path

from 공통 import 절나누기, 주제파일들, 설정, rel


def 지금절(글: str, 제목: str = "지금") -> list[str] | None:
    """「지금」 절의 내용 줄들. 절이 없으면 None."""
    for 수준, 이름, s, e in 절나누기(글):
        if 이름.strip("「」 ") == 제목:
            줄 = 글.split("\n")[s + 1:e]
            return [x for x in 줄 if x.strip()]
    return None


def 첫줄(줄들: list[str] | None) -> str:
    if not 줄들:
        return "「지금」 절이 없다"
    첫 = 줄들[0].lstrip("-* ").strip()
    return 첫


def 문서마다(뿌리: Path, c: dict | None = None) -> list[tuple[str, list[str] | None]]:
    c = c or 설정(뿌리)
    제목 = c["지금절"]["제목"]
    나온것 = []
    for p in 주제파일들(뿌리, c):
        나온것.append((rel(뿌리, p), 지금절(p.read_text(encoding="utf-8"), 제목)))
    return 나온것


def 검사(뿌리: Path, c: dict | None = None) -> list[str]:
    """「지금」 절이 최대 줄 수를 넘는 파일을 이름으로 짚는다."""
    c = c or 설정(뿌리)
    최대 = int(c["지금절"]["최대줄"])
    문제 = []
    for 이름, 줄들 in 문서마다(뿌리, c):
        if 줄들 is not None and len(줄들) > 최대:
            문제.append(f"{이름} 의 「{c['지금절']['제목']}」 절이 {len(줄들)}줄이다. {최대}줄 안으로 줄인다")
    return 문제


def STATUS(뿌리: Path, c: dict | None = None) -> str:
    c = c or 설정(뿌리)
    줄 = ["# 지금 상태", "",
          f"이 파일은 주제 파일마다의 「{c['지금절']['제목']}」 절을 모아 `ops build` 가 만든다. 손으로 고치지 않는다. 고칠 것은 그 주제 파일의 그 절이다.", ""]
    for 이름, 줄들 in 문서마다(뿌리, c):
        줄.append(f"## {이름}")
        줄.append("")
        if 줄들 is None:
            줄.append(f"(「{c['지금절']['제목']}」 절이 없다)")
        else:
            줄.extend(줄들)
        줄.append("")
    return "\n".join(줄).rstrip("\n") + "\n"


def README(뿌리: Path, c: dict | None = None) -> str:
    c = c or 설정(뿌리)
    줄 = [f"# {c['이름']}", "", c["소개"].rstrip(), "",
          "이 파일은 `ops build` 가 만든다. 소개는 `.ops.yml` 의 소개 칸, 아래 줄은 주제 파일마다의 "
          f"「{c['지금절']['제목']}」 절 첫 줄이다.", "",
          "| 파일 | 지금 |", "|---|---|"]
    for 이름, 줄들 in 문서마다(뿌리, c):
        줄.append(f"| `{이름}` | {첫줄(줄들)} |")
    줄 += ["", "규칙은 `ops/rules/`, 설계는 `설계.md`, 어긋난 파생물은 `memory/어긋남.md` 에 있다."]
    return "\n".join(줄) + "\n"


def 목차표(뿌리: Path, c: dict | None = None) -> str:
    """CLAUDE.md 의 목차 표. 셋째 칸은 그 파일의 「지금」 첫 줄이다."""
    c = c or 설정(뿌리)
    지금들 = dict(문서마다(뿌리, c))
    줄 = ["| 이런 말이 나오면 | 읽는다 | 지금 (그 파일의 「" + c["지금절"]["제목"] + "」 첫 줄) |", "|---|---|---|"]
    for 항 in c.get("목차") or []:
        파일 = str(항.get("파일", ""))
        말 = str(항.get("말", ""))
        지금 = 첫줄(지금들.get(파일)) if 파일 in 지금들 else "(주제 파일이 아니다)"
        줄.append(f"| {말} | `{파일}` | {지금} |")
    return "\n".join(줄) + "\n"
