#!/usr/bin/env python3
"""도구가 파일에 글을 쓴 직후, 그 글에 나온 약호를 용어집에서 찾아 본 결과를 클로드에게 알린다.

뜻을 판단하거나 무엇을 하라고 말하지 않는다. 용어집에 무엇이 적혀 있는지만 알린다.
- 둘 이상의 용어집에 다른 뜻으로 적힌 약호: 어디에 무엇으로 적혀 있는지
- 어느 용어집에도 없고, 그 글 안에서도 풀어 적지 않은 약호: 없다는 것
한 세션에서 같은 약호는 한 번만 알린다.
"""
import json
import re
import sys
from pathlib import Path

입력 = json.load(sys.stdin)
뿌리 = Path(입력.get("cwd") or ".")
도구 = 입력.get("tool_name", "")
값 = 입력.get("tool_input") or {}

if 도구 in ("Edit", "MultiEdit"):
    글 = (값.get("new_string") or "") + "".join(e.get("new_string", "") for e in 값.get("edits") or [])
    대상들 = [값.get("file_path") or ""]
elif 도구 == "Write":
    글, 대상들 = 값.get("content") or "", [값.get("file_path") or ""]
elif 도구 == "Bash":
    글 = 값.get("command") or ""
    if not re.search(r">>?|\btee\b|sed -i", 글):      # 파일에 쓰는 명령만 본다
        sys.exit(0)
    for 표지 in re.findall(r"<<-?\s*['\"]?(\w+)['\"]?", 글):   # heredoc 표지는 약호가 아니다
        글 = re.sub(rf"(?m)<<-?\s*['\"]?{표지}['\"]?|^\s*{표지}\s*$", "", 글)
    대상들 = re.findall(r"작업/[^\s'\"<>|;]+", 글)
else:
    sys.exit(0)


def 용어집(경로: Path) -> dict:
    뜻 = {}
    if 경로.is_file():
        for 줄 in 경로.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", 줄)
            if m and m.group(1) not in ("말",) and not set(m.group(1)) <= set("-: "):
                뜻[m.group(1)] = m.group(2)
    return 뜻


쓰는곳 = sorted((뿌리 / "용어집").glob("*.md")) if (뿌리 / "용어집").is_dir() else []
for 대상 in 대상들:
    try:
        상대 = Path(대상).resolve().relative_to(뿌리.resolve()) if Path(대상).is_absolute() else Path(대상)
    except ValueError:
        continue
    if len(상대.parts) > 2 and 상대.parts[0] == "작업":
        쓰는곳.append(뿌리 / "작업" / 상대.parts[1] / "용어집.md")
쓰는곳 = [p for p in dict.fromkeys(쓰는곳) if p.is_file()]
모음 = {}
for p in 쓰는곳:
    for 말, 뜻 in 용어집(p).items():
        모음.setdefault(말, []).append((str(p.relative_to(뿌리)), 뜻))

약호들 = dict.fromkeys(re.findall(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]*(?:-[0-9]+)?)(?![A-Za-z0-9]|\.\w)", 글))
상태 = 뿌리 / ".claude" / "용어-알린것.json"
try:
    알린것 = set(json.loads(상태.read_text(encoding="utf-8")).get(입력.get("session_id", ""), []))
except (OSError, ValueError):
    알린것 = set()
줄들 = []
for 약 in 약호들:
    if len(약) < 2 or 약 in 알린것:
        continue
    뜻들 = 모음.get(약, [])
    if len({뜻 for _, 뜻 in 뜻들}) >= 2:
        줄들.append(f"- 「{약}」: " + ", ".join(f"{곳} 에는 「{뜻}」" for 곳, 뜻 in 뜻들) + " 로 적혀 있다.")
    elif not 뜻들 and not re.search(re.escape(약) + r"\s*[(（:]", 글):
        줄들.append(f"- 「{약}」: 용어집({', '.join(str(p.relative_to(뿌리)) for p in 쓰는곳) or '없음'})에 없다.")
    else:
        continue
    알린것.add(약)
if 줄들:
    try:
        전 = json.loads(상태.read_text(encoding="utf-8")) if 상태.is_file() else {}
    except ValueError:
        전 = {}
    전[입력.get("session_id", "")] = sorted(알린것)
    try:
        상태.parent.mkdir(parents=True, exist_ok=True)
        상태.write_text(json.dumps(전, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    print("[용어집 확인] 방금 쓴 글에 나온 약호를 용어집에서 찾아 본 결과다.\n" + "\n".join(줄들), file=sys.stderr)
    sys.exit(2)
