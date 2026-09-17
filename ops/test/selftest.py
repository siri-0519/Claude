#!/usr/bin/env python3
"""자체 시험 — 임시 레포를 만들어 기계 전부를 한 번씩 돌린다. python3 ops/test/selftest.py

판정 모델은 부르지 않는다 (임시 레포의 .ops.yml 이 판정을 끈다). 판정 결과를 푸는 것만 본다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

여기 = Path(__file__).resolve()
틀 = 여기.parents[2]
sys.path.insert(0, str(틀 / "ops" / "lib"))

실패: list[str] = []


def 확인(조건: bool, 말: str, 덧말: str = "") -> None:
    print(("  ok  " if 조건 else "  FAIL") + " " + 말 + (f"\n       {덧말}" if 덧말 and not 조건 else ""))
    if not 조건:
        실패.append(말)


def git(r: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(r), *a], capture_output=True, text=True).stdout.strip()


def 임시레포() -> Path:
    d = Path(tempfile.mkdtemp(prefix="ops-selftest-"))
    for 것 in ("ops", ".claude", ".github"):     # .github 도 — 기계 규칙 「자체시험합치기」의 시험이 워크플로 파일을 가리킨다 (2026-09-17)
        if (틀 / 것).is_dir():
            shutil.copytree(틀 / 것, d / 것, ignore=shutil.ignore_patterns("__pycache__"))
    (d / ".ops.yml").write_text(
        "이름: 시험\n소개: 시험 레포다.\n주제파일: ['*.md']\n결정로그: decisions.md\n"
        "제외: [README.md, STATUS.md, CLAUDE.md, worklog.md, guide.md, 'memory/**', 'ops/**', '.claude/**']\n"   # guide.md 는 안내(파생물)지 주제 파일이 아니다
        "목차:\n  - 말: 몸\n    파일: body.md\n판정:\n  끄기: true\n", encoding="utf-8")
    (d / ".gitignore").write_text("worklog.md\n.meta/\n__pycache__/\n", encoding="utf-8")
    (d / "CLAUDE.md").write_text("# 목차\n\n<!-- BEGIN GENERATED: 목차 -->\n<!-- END GENERATED: 목차 -->\n", encoding="utf-8")
    (d / "body.md").write_text("# 몸\n\n## 지금\n\n- 허리 디스크로 요양한 적 있다 [확인 2026-09-01].\n- 계단은 한 번에 두 층까지다 [제안] (D-002).\n\n## 운동\n\n- 걷기는 하루 30분이다 [확인 2026-09-01].\n", encoding="utf-8")
    (d / "decisions.md").write_text("# 결정\n\n| 번호 | 결정 |\n|---|---|\n| D-001 | 걷기 30분 [확인 2026-09-01] |\n| ~~D-002~~ | 폐기 — 계단 [확인 2026-09-01] |\n", encoding="utf-8")
    (d / "memory").mkdir()
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t"); git(d, "config", "user.name", "t")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "첫 커밋")
    return d


def 훅돌리기(r: Path, 자리: str, payload: dict) -> tuple[int, str, str]:
    x = subprocess.run([sys.executable, str(r / ".claude/hooks/hook.py"), 자리], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=str(r), env=dict(os.environ, CLAUDE_PROJECT_DIR=str(r)))
    return x.returncode, x.stdout, x.stderr


def ops(r: Path, *a: str, env: dict | None = None) -> tuple[int, str]:
    x = subprocess.run([sys.executable, str(r / "ops/bin/ops"), *a], capture_output=True, text=True, cwd=str(r),
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=str(r), **(env or {})))
    return x.returncode, x.stdout + x.stderr


def main() -> int:
    r = 임시레포()
    print(f"임시 레포 {r}")
    import 공통, 기계, 낱말, 지금, 생성, 어긋남, 표시, 판정
    c = 공통.설정(r)

    print("설정 · 주제 파일")
    확인(c["이름"] == "시험" and c["판정"]["끄기"] is True and c["판정"]["모델"] == "haiku", "설정이 기본값 위에 겹친다")
    확인([공통.rel(r, p) for p in 공통.주제파일들(r, c)] == ["body.md", "decisions.md"], "주제 파일은 body.md 와 decisions.md 다 (CLAUDE.md 는 뺀다)")

    print("「지금」 절 · 생성 파일")
    확인(지금.첫줄(지금.지금절((r / "body.md").read_text(encoding="utf-8"))) == "허리 디스크로 요양한 적 있다 [확인 2026-09-01].", "「지금」 첫 줄을 뽑는다")
    code, out = ops(r, "build")
    확인(code == 0 and (r / "STATUS.md").is_file() and (r / "README.md").is_file(), "ops build 가 STATUS.md 와 README.md 를 만든다")
    확인("허리 디스크" in (r / "CLAUDE.md").read_text(encoding="utf-8"), "CLAUDE.md 목차 블록 셋째 칸에 「지금」 첫 줄이 든다")
    확인((r / "worklog.md").is_file() and "첫 커밋" in (r / "worklog.md").read_text(encoding="utf-8"), "worklog.md 를 git log 에서 만든다")
    확인(not 생성.다른것(r, c), "만든 직후에는 원본과 다른 생성 파일이 없다")
    (r / "STATUS.md").write_text("손으로 고침\n", encoding="utf-8")
    확인(any("STATUS.md" in x for x in 생성.다른것(r, c)), "손으로 고친 STATUS.md 를 짚는다")
    ops(r, "build")

    print("표시 · 상대 날짜")
    확인(표시.검사_글("- 새 주장이 하나 들어간다\n", c) != [], "표시 없는 주장 줄을 잡는다")
    확인(표시.검사_글("- 새 주장이 하나 들어간다 [제안]\n", c) == [], "[제안] 이 붙은 줄은 통과한다")
    확인(표시.검사_글("- `ops build`\n", c) == [], "코드만 있는 줄은 주장이 아니다")
    확인(기계.상대날짜("어제 잰 값이다", c) == ["어제"], "답의 상대 날짜를 잡는다")
    확인(기계.상대날짜("「어제보다 오늘 더」 를 불렀다", c) == [], "「」 안의 제목은 보지 않는다")
    확인(기계.상대날짜_새줄("- 아까 먹었다 [확인]\n", c) != [], "문서 새 줄의 상대 날짜를 잡는다")

    print("셸 검사")
    강제 = "git push " + "--force origin main"
    삭제 = "git push origin " + ":claude/x"
    지움 = "rm " + "-rf ops"
    재지정 = "echo x " + "> STATUS.md"
    확인(기계.셸검사(강제, r, c) != [], "force push 를 막는다")
    확인(기계.셸검사(삭제, r, c) != [], "원격 브랜치 삭제 push 를 막는다")
    확인(기계.셸검사("git push -u origin claude/x", r, c) == [], "보통 push 는 통과한다")
    확인(기계.셸검사(지움, r, c) != [], "rm -r ops 를 막는다")
    확인(기계.셸검사("rm " + "-rf /tmp/x", r, c) == [], "레포 밖 rm -r 은 통과한다")
    확인(기계.셸검사(재지정, r, c) != [], "생성 파일로의 재지정을 막는다")
    확인(기계.셸검사("cat > t.py <<'EOF'\n" + 강제 + "\nEOF\n", r, c) == [], "heredoc 본문의 글자는 명령이 아니다")

    print("훅 — 도구 직전")
    code, out, err = 훅돌리기(r, "pre_tool_use", {"tool_name": "Write", "tool_input": {"file_path": str(r / "STATUS.md"), "content": "x"}, "cwd": str(r)})
    확인(code == 2 and "스크립트가" in err and "ops build" in err, "생성 파일 Write 를 막는다")
    code, out, err = 훅돌리기(r, "pre_tool_use", {"tool_name": "Edit", "tool_input": {"file_path": str(r / "CLAUDE.md"), "old_string": "허리 디스크", "new_string": "손으로"}, "cwd": str(r)})
    확인(code == 2 and "블록" in err and "ops build" in err, "CLAUDE.md 생성 블록 안의 Edit 를 막는다")
    code, out, err = 훅돌리기(r, "pre_tool_use", {"tool_name": "Edit", "tool_input": {"file_path": str(r / "body.md"), "old_string": "## 운동\n", "new_string": "## 운동\n\n- 어제 계단을 올랐다\n"}, "cwd": str(r)})
    확인(code == 2 and "표시가 없다" in err and "어제" in err, "주제 파일 새 줄의 상대 날짜와 표시 없음을 막는다")
    code, out, err = 훅돌리기(r, "pre_tool_use", {"tool_name": "Edit", "tool_input": {"file_path": str(r / "body.md"), "old_string": "## 운동\n", "new_string": "## 운동\n\n- 계단을 올랐다 [확인 2026-09-02]\n"}, "cwd": str(r)})
    확인(code == 0 and "고칠 때" in out, "표시 있는 줄은 통과하고 「고칠 때」 규칙을 한 번 넣는다")
    code, out, err = 훅돌리기(r, "pre_tool_use", {"tool_name": "Edit", "tool_input": {"file_path": str(r / "body.md"), "old_string": "## 운동\n", "new_string": "## 운동\n\n- 계단을 올랐다 [확인 2026-09-02]\n"}, "cwd": str(r)})
    확인(code == 0 and "고칠 때" not in out, "두 번째에는 규칙을 다시 넣지 않는다")
    code, out, err = 훅돌리기(r, "pre_tool_use", {"tool_name": "Bash", "tool_input": {"command": 강제}, "cwd": str(r)})
    확인(code == 2, "Bash 의 force push 를 막는다")

    print("어긋남 목록")
    (r / "guide.md").write_text("# 안내\n\n몸 문서를 읽고 쓴 안내다 [제안].\n", encoding="utf-8")
    code, out = ops(r, "출처", "guide.md", "body.md")
    확인(code == 0 and (r / "guide.md.meta.yml").is_file(), "ops 출처 가 옆 파일(.meta.yml)을 만든다")
    글, 열쇠, _ = 어긋남.목록(r, c)
    확인(not any("guide.md" in k for k in 열쇠), "만든 직후에는 어긋나지 않는다")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8").replace("하루 30분", "하루 40분"), encoding="utf-8")
    글, 열쇠, _ = 어긋남.목록(r, c)
    확인(any("guide.md" in k for k in 열쇠) and "운동" in 글, "출처가 바뀌면 파생물이 오르고 바뀐 절 이름이 붙는다")
    확인(any("D-002" in k for k in 열쇠), "폐기된 결정 번호를 단 줄이 오른다")
    code, out = ops(r, "ack", "guide.md", "--그대로", "안내에는 분이 안 나온다")
    글, 열쇠, _ = 어긋남.목록(r, c)
    확인(code == 0 and not any("guide.md" in k for k in 열쇠), "ops ack --그대로 가 항을 지우고 로그에 남긴다")
    확인(any(e.get("종류") == "ack" for e in 공통.로그읽기(r)), "그대로 둔 이유가 로그에 있다")
    code, out, err = 훅돌리기(r, "post_tool_use", {"tool_name": "Edit", "tool_input": {"file_path": str(r / "body.md")}, "cwd": str(r)})
    확인(code == 0, "도구 직후 훅이 돈다")

    print("낱말 · 판정")
    아는 = 낱말.아는말(r, c, ["허리가 아프다"], {str(r / "body.md")})
    확인("허리" in 아는 and "디스크로" in 아는 and "디스크" in 아는, "사용자의 말과 읽은 파일의 낱말을 안다 (조사 뗀 꼴도)")
    후보 = 낱말.후보("허리 디스크에는 사다리 훈련이 좋다", 아는)
    확인("사다리" in 후보 and "허리" not in 후보 and "디스크에는" not in 후보, "아는 낱말은 빼고 모르는 낱말을 후보로 뽑는다")
    확인("커밋했고" not in 낱말.후보("표를 커밋했고 push 했다", 아는 | {"커밋"}), "아는 말에 활용 어미가 붙은 꼴은 후보가 아니다")
    확인(판정.풀기('앞말 {"어긴것": [{"규칙": "6", "문장": "사다리 훈련", "이유": "이름"}]} 뒷말')[0]["규칙"] == "6", "판정 결과를 푼다")
    확인(판정.풀기("아무것도 아님") == [], "JSON 이 없으면 빈 목록이다")
    확인("답할 때" in 판정.규칙글(r, "답할 때") and "고칠 때" not in 판정.규칙글(r, "답할 때"), "규칙 파일에서 「용어」와 「답할 때」만 뽑는다")
    확인(판정.이름맞추기(r, "6. 아는 말만 쓴다") == "6" and 판정.이름맞추기(r, "6 (아는 말만 쓴다)") == "6"
         and 판정.이름맞추기(r, "규칙 5") == "5" and 판정.이름맞추기(r, "아는 말만 쓴다") == "6",
         "판정이 부른 규칙 이름을 대장의 번호로 맞춘다")
    확인(판정.이름맞추기(r, "한 줄에는 표시 하나만 붙인다") == "한 줄에는 표시 하나만 붙인다", "대장에 없는 이름은 그대로 둔다")
    for 이름 in ("6", "6. 아는 말만 쓴다", "6 (아는 말만 쓴다)"):
        공통.횟수추가(r, "판정", 이름, "걸린 문장")
    공통.횟수추가(r, "기계", "상대날짜")
    요약 = {x[1]: x[2] for x in 공통.횟수요약(r)}
    확인(요약.get("판정·6") == 3 and 요약.get("기계·상대날짜") == 1, "횟수 표가 같은 규칙을 한 줄로 센다 (안 합친 줄도 센다)")
    확인((r / 공통.횟수대기).is_file() and "횟수.jsonl" not in git(r, "status", "--porcelain"),
         "어긴 것은 git 이 보지 않는 자리에 적혀 커밋을 만들지 않는다")
    앞줄수 = len((r / 공통.횟수파일).read_text(encoding="utf-8").splitlines()) if (r / 공통.횟수파일).is_file() else 0
    확인(공통.횟수합치기(r) >= 4 and len((r / 공통.횟수파일).read_text(encoding="utf-8").splitlines()) == 앞줄수 + 4 and not (r / 공통.횟수대기).is_file(),
         "합치면 memory/횟수.jsonl 로 옮겨지고 대기 파일은 없어진다 (문맥 · 판정 기록도 같이 합쳐진다)")
    ops(r, "build"); git(r, "add", "-A"); git(r, "commit", "-q", "-m", "횟수 합침")
    공통.횟수추가(r, "판정", "5", "다음 줄")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8") + "- 새 줄이다 [제안].\n", encoding="utf-8")
    ops(r, "build"); git(r, "add", "body.md", "STATUS.md", "README.md", "CLAUDE.md")
    code, out = ops(r, "check", "--커밋")
    # git 은 한글 경로를 \355\232… 꼴로 적어 내므로 quotePath 를 끄고 본다
    확인(code == 0 and "횟수.jsonl" in git(r, "-c", "core.quotePath=false", "diff", "--cached", "--name-only"),
         "커밋 직전 검사가 안 합친 줄을 그 커밋에 얹는다" + ("" if code == 0 else " — 검사 출력: " + out.replace("\n", " / ")[:300]))
    git(r, "commit", "-q", "-m", "새 줄과 횟수")
    code, out, err = 훅돌리기(r, "user_prompt_submit", {"cwd": str(r)})
    문맥 = 공통.기록읽기(r, "문맥")
    확인(any(d.get("자리") == "user_prompt_submit" for d in 문맥) and all(int(d.get("바이트", 0)) > 0 for d in 문맥), "훅이 넣은 글의 크기가 기록된다")
    code, out = ops(r, "토큰")
    확인(code == 0 and "user_prompt_submit" in out, "ops 토큰 이 날 · 자리별 크기를 보인다")

    print("커밋 직전 · 목차 행 · 읽기 기록")
    (r / "hair.md").write_text("# 머리\n\n## 지금\n\n- 숱이 적다 [확인 2026-09-01].\n", encoding="utf-8")
    git(r, "add", "hair.md")
    문제 = 기계.커밋검사(r, c)
    확인(any("hair.md 는 주제 파일인데" in x and "목차에 행이 없다" in x for x in 문제), "목차에 행이 없는 주제 파일을 커밋 직전에 잡는다")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8") + "- " + "긴 줄이다 [확인 2026-09-01]. " * 1500 + "\n", encoding="utf-8")
    git(r, "add", "body.md")
    문제 = 기계.커밋검사(r, c)
    확인((r / "body.md").stat().st_size > 30000 and not any("바이트" in x and "줄인다" in x for x in 문제),
         "주제 파일이 30KB 를 넘어도 막지 않는다 — 나누는 기준은 크기가 아니라 목차 행이다")
    git(r, "checkout", "-q", "--", "body.md"); (r / "hair.md").unlink(); git(r, "reset", "-q")
    훅돌리기(r, "post_tool_use", {"cwd": str(r), "tool_name": "Read", "tool_input": {"file_path": str(r / "body.md")}})
    확인(any(d.get("자리") == "읽기" and d.get("파일") == "body.md" and d.get("어떻게") == "통째로" and int(d.get("바이트", 0)) == (r / "body.md").stat().st_size
             for d in 공통.기록읽기(r, "문맥")), "Read 한 파일과 바이트가 기록된다")
    훅돌리기(r, "post_tool_use", {"cwd": str(r), "tool_name": "Read", "tool_input": {"file_path": str(r / "body.md"), "offset": 1, "limit": 2}})
    확인(any(d.get("자리") == "읽기" and d.get("어떻게") == "일부" and 0 < int(d.get("바이트", 0)) < (r / "body.md").stat().st_size for d in 공통.기록읽기(r, "문맥")),
         "일부만 읽으면 그 줄들의 바이트가 기록된다")
    code, out = ops(r, "토큰")
    확인(code == 0 and "읽은 파일" in out and "body.md" in out, "ops 토큰 이 읽은 파일을 보인다")
    확인(기계.상대날짜('사용자가 "아까 안 한다는거 아녔어?" 하고 물었다. 「방금」 도 그렇다.', c) == [] and 기계.상대날짜("아까 물었다.", c) == ["아까"],
         "따옴표와 「」 안에 옮긴 말의 상대 날짜는 걸지 않고, 밖의 것은 건다")

    (r / "ops/rules/diet.md").write_text("# 먹는 것\n\n## 지금\n\n- 아침은 안 먹는다 [확인 2026-09-17].\n", encoding="utf-8")
    확인(any("ops/rules/diet.md 는 규칙 파일이 아니라 주제 파일이다" in x for x in 기계.목차행(r, c)), "ops/rules/ 에 생긴 주제 파일을 잡는다")
    (r / "ops/rules/diet.md").unlink()
    print("규칙 대장 · 목적과 시험")
    import re as _re
    확인(기계.규칙대장(r) == [], "기계 · 판단 · 훅 글에 목적과 시험이 다 있다", " / ".join(기계.규칙대장(r))[:300])
    y = r / "ops/rules/기계.yml"; 옛y = y.read_text(encoding="utf-8")
    y.write_text(옛y.replace("  목적: [맥락 유지, 좋은 설명]\n", "", 1), encoding="utf-8")
    확인(any("목적 칸이 없다" in x for x in 기계.대장검사(r)), "기계 규칙에 목적이 없으면 잡는다")
    y.write_text(옛y.replace('"시뮬: S2"', '"시뮬: S99"', 1), encoding="utf-8")
    확인(any("그 시나리오가 없다" in x for x in 기계.대장검사(r)), "시험 참조가 실재하지 않으면 잡는다")
    y.write_text(옛y, encoding="utf-8")
    j = r / "ops/rules/판단.md"; 옛j = j.read_text(encoding="utf-8")
    j.write_text(_re.sub(r"^\| 9 \|.*\n", "", 옛j, flags=_re.M), encoding="utf-8")
    확인(any("규칙 9 이" in x for x in 기계.판단대장검사(r)), "판단 규칙 표에 행이 없으면 잡는다")
    j.write_text(옛j, encoding="utf-8")
    h = r / "ops/rules/훅-글.md"; 옛h = h.read_text(encoding="utf-8")
    h.write_text(_re.sub(r"^- 목적: 맥락 유지 — 새 세션이.*$", "- 목적: 새 세션이 상태를 알게 한다", 옛h, count=1, flags=_re.M), encoding="utf-8")
    확인(any("A1:" in x for x in 기계.훅글대장검사(r)), "훅 글에 목적이 없으면 잡는다")
    h.write_text(옛h, encoding="utf-8")
    확인(기계.목차크기(r, c, "# 목차\n" + "\n".join(f"- 줄 {i}" for i in range(801))) != [], "CLAUDE.md 가 800줄을 넘으면 잡는다")
    import 지금 as _지금
    b = r / "body.md"; 옛b = b.read_text(encoding="utf-8")
    b.write_text(옛b.replace("## 지금\n\n", "## 지금\n\n" + "".join(f"- 채움 {i} [제안].\n" for i in range(10)), 1), encoding="utf-8")
    확인(_지금.검사(r, c) != [], "「지금」 절이 열 줄을 넘으면 잡는다")
    b.write_text(옛b, encoding="utf-8")
    code, out = ops(r, "목표")
    확인(code == 0 and all(m in out for m in ("규칙 준수", "맥락 유지", "토큰 절약", "정보 추적성", "좋은 설명")), "ops 목표 가 목적 다섯을 보인다", out[-300:])
    code, out = ops(r, "rules", "--목적별")
    확인(code == 0 and "| 좋은 설명 |" in out, "ops rules --목적별 이 목적마다의 규칙을 보인다", out[-300:])
    (r / ".meta/시뮬").mkdir(parents=True, exist_ok=True)
    (r / ".meta/시뮬/시험.jsonl").write_text('{"시나리오": "S1", "목표": "맥락 유지", "모델": "haiku", "초": 3, "통과": true, "검사": {"a": true}}\n'
                                             '{"시나리오": "S2", "목표": "규칙 준수", "모델": "haiku", "초": 4, "통과": false, "검사": {"b": false}}\n'
                                             '{"시나리오": "S2", "목표": "규칙 준수", "모델": "opus", "초": 4, "통과": false, "검사": {"b": false}}\n', encoding="utf-8")
    code, out = ops(r, "시뮬", "--기록", str(r / ".meta/시뮬/시험.jsonl"), "--판", "시험판")
    확인(code == 0 and (r / "memory/시뮬.jsonl").is_file() and len((r / "memory/시뮬.jsonl").read_text(encoding="utf-8").splitlines()) == 3, "ops 시뮬 --기록 이 결과를 memory/시뮬.jsonl 에 남긴다", out)
    code, out = ops(r, "목표")
    확인("1/3 통과" in out and "S2(haiku · opus)" in out, "ops 목표 가 시뮬 마지막 판과 모델 둘 이상이 실패한 시나리오를 경보로 보인다", out[-400:])
    code, out, err = 훅돌리기(r, "session_start", {"session_id": "s", "source": "startup"})
    확인(code == 0 and "경보" in out and "S2(haiku · opus)" in out, "세션 시작에 경보 한 줄이 들어간다", out[-300:])
    (r / "memory/시뮬.jsonl").unlink()
    code, out, err = 훅돌리기(r, "user_prompt_submit", {"session_id": "s", "prompt": "안녕"})
    확인(code == 0 and "답할 때" in out and "4. 항목마다" in out, "기본값(답규칙넣기 켬)이면 첫 물음 직전에 「답할 때」 규칙이 들어간다", (out + err)[-300:])
    code, out, err = 훅돌리기(r, "user_prompt_submit", {"session_id": "s", "prompt": "또"})
    확인("4. 항목마다" not in out, "두 번째 물음에는 다시 넣지 않는다")
    y = r / ".ops.yml"; 옛y2 = y.read_text(encoding="utf-8")
    y.write_text(옛y2.replace("판정:\n  끄기: true\n", "판정:\n  끄기: true\n  답규칙넣기: false\n"), encoding="utf-8")
    상태 = r / ".meta/session.json"; 옛상태 = 상태.read_text(encoding="utf-8")
    상태.write_text(옛상태.replace('"답할 때"', '"x"'), encoding="utf-8")   # 넣은 적 없는 세션처럼
    code, out, err = 훅돌리기(r, "user_prompt_submit", {"session_id": "s", "prompt": "셋"})
    확인("4. 항목마다" not in out, "답규칙넣기 를 끄면 넣지 않는다")
    y.write_text(옛y2, encoding="utf-8"); 상태.write_text(옛상태, encoding="utf-8")

    print("커밋 직전 · 대장")
    확인(기계.대장검사(r) == [], "기계 규칙 대장에 여섯 칸이 다 있다")
    git(r, "add", "-A")
    문제 = 기계.커밋검사(r, c)
    확인(any("worklog.md" in x for x in 문제) is False, "worklog.md 는 .gitignore 라 스테이지에 없다")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8") + "\n- 표시 없는 새 줄이다\n", encoding="utf-8")
    git(r, "add", "body.md")
    문제 = 기계.커밋검사(r, c)
    확인(any("표시가 없다" in x for x in 문제), "스테이지된 표시 없는 줄을 잡는다")
    code, out = ops(r, "check", "--커밋")
    확인(code == 1 and "표시가 없다" in out, "ops check --커밋 이 1 로 끝난다")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8").replace("- 표시 없는 새 줄이다\n", "- 계단은 한 번에 두 층까지다 [확인 2026-09-03].\n"), encoding="utf-8")
    git(r, "add", "-A")
    ops(r, "build"); git(r, "add", "-A")
    code, out = ops(r, "check", "--커밋")
    확인(code == 0, "고치고 build 하면 통과한다: " + out.strip()[:80])
    x = subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "둘째 커밋"], capture_output=True, text=True)
    확인(x.returncode == 0, "core.hooksPath 없이도 커밋된다 (git 훅은 ops hooks --설치 가 건다)")
    code, out = ops(r, "hooks", "--설치")
    확인(git(r, "config", "core.hooksPath") == "ops/hooks", "ops hooks --설치 가 core.hooksPath 를 잡는다")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8") + "- 아까 넣은 줄 [제안]\n", encoding="utf-8")
    git(r, "add", "body.md")
    x = subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "막혀야 한다"], capture_output=True, text=True)
    확인(x.returncode != 0 and "아까" in x.stdout + x.stderr, "git 훅이 상대 날짜가 든 커밋을 막는다")
    git(r, "checkout", "-q", "--", "body.md"); git(r, "reset", "-q")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8").replace("[제안] (D-002).", "[확인 2026-09-03] (D-002)."), encoding="utf-8")
    git(r, "add", "body.md")
    확인(any("[제안]이 [확인]으로" in x for x in 표시.제안이확인으로(r, c)), "[제안]→[확인] 을 잡는다")
    git(r, "checkout", "-q", "--", "body.md"); git(r, "reset", "-q")

    print("이름 바꿈")
    (r / "sub").mkdir()
    (r / "sub/one.md").write_text("# 하나\n\n## 지금\n\n- 하나는 둘보다 앞이다 [확인 2026-09-03].\n", encoding="utf-8")
    # 표시 없는 옛 줄이라야 시험이 된다 — 검사 전부터 있던 줄은 표시가 없어도 옛 줄이다
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8") + "- 자세한 것은 `sub/one.md` 에 있다\n- 폴더 `sub/` 를 먼저 읽는다\n", encoding="utf-8")
    git(r, "add", "-A"); ops(r, "build"); git(r, "add", "-A")
    x = subprocess.run(["git", "-C", str(r), "commit", "-q", "--no-verify", "-m", "폴더 하나"], capture_output=True, text=True)
    확인(x.returncode == 0, "이름 바꿈 시험용 커밋이 들어갔다: " + (x.stdout + x.stderr).strip()[:80])
    git(r, "mv", "sub", "sub2")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8").replace("`sub/one.md`", "`sub2/one.md`").replace("`sub/`", "`sub2/`"), encoding="utf-8")
    git(r, "add", "-A")
    바뀜 = dict(공통.이름바뀐것(r))
    확인(바뀜.get("sub/one.md") == "sub2/one.md" and 바뀜.get("sub/") == "sub2/", "스테이지의 이름 바꿈을 파일과 폴더로 읽는다")
    확인(표시.검사_새줄(r, c, 스테이지=True) == [], "경로만 새 이름으로 바뀐 줄은 새 주장이 아니다")
    (r / "body.md").write_text((r / "body.md").read_text(encoding="utf-8").replace("- 폴더 `sub2/` 를 먼저 읽는다", "- 폴더 `sub2/` 를 나중에 읽는다"), encoding="utf-8")
    git(r, "add", "-A")
    확인(any("표시가 없다" in x for x in 표시.검사_새줄(r, c, 스테이지=True)), "경로 말고 뜻이 바뀐 줄은 여전히 잡는다")
    git(r, "reset", "-q", "--hard"); git(r, "clean", "-qfd")

    print("답 끝 · 브랜치")
    문제 = 기계.브랜치(r, c)
    확인(any("원격에 없다" in x for x in 문제), "원격에 없는 브랜치를 짚는다")
    tr = r / "t.jsonl"
    tr.write_text(json.dumps({"type": "user", "message": {"content": "허리 어때"}}) + "\n" +
                  json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "어제 잰 값으로는 괜찮다."}]}}) + "\n", encoding="utf-8")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r)})
    확인(code == 2 and "상대 날짜" in err, "답 끝에 상대 날짜를 되돌린다")
    깨진 = r / "ops/lib/대화.py"; 원래 = 깨진.read_text(encoding="utf-8")
    깨진.write_text("raise RuntimeError('시험용 오류')\n" + 원래, encoding="utf-8")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r)})
    확인(code == 2 and "훅이 오류로 죽었다" in err, "답 끝 훅이 죽으면 한 번 막아서 모델이 보게 한다")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r), "stop_hook_active": True})
    확인(code == 0, "되돌린 뒤에는 죽은 훅이 다시 막지 않는다")
    깨진.write_text(원래, encoding="utf-8")
    깨진2 = r / "ops/lib/어긋남.py"; 원래2 = 깨진2.read_text(encoding="utf-8")   # 도구 직후는 어긋남 모듈을 쓴다
    깨진2.write_text("raise RuntimeError('시험용 오류')\n" + 원래2, encoding="utf-8")
    code, out, err = 훅돌리기(r, "post_tool_use", {"tool_name": "Edit", "tool_input": {"file_path": str(r / "body.md")}, "cwd": str(r)})
    확인(code == 0 and "additionalContext" in out and "훅이 오류로 죽었다" in out, "다른 자리에서 죽으면 문맥으로 알린다")
    깨진2.write_text(원래2, encoding="utf-8")
    설정 = json.loads((r / ".claude/settings.json").read_text(encoding="utf-8"))
    답끝시간 = 설정["hooks"]["Stop"][0]["hooks"][0]["timeout"]
    확인(답끝시간 >= int(공통.설정(틀)["판정"].get("시간") or 90) + 60, "답 끝 훅의 제한 시간이 판정 시간보다 60초 이상 길다")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r), "stop_hook_active": True})
    확인("상대 날짜" not in err and code == 2 and "커밋하고 push" in err, "되돌린 뒤에는 상대 날짜로 다시 막지 않지만 커밋 · push 는 그대로 본다")
    tr.write_text(json.dumps({"type": "user", "message": {"content": "허리 어때"}}) + "\n" +
                  json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "2026-09-01 값으로는 괜찮다."}]}}) + "\n", encoding="utf-8")
    (r / ".meta").mkdir(exist_ok=True)
    (r / ".meta/session.json").write_text(json.dumps({"되돌림": 0, "어긋남": []}), encoding="utf-8")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r)})
    확인(code == 2 and "커밋하고 push" in err, "커밋 안 한 것이 있으면 답 끝에 되돌린다")
    (r / ".meta/session.json").write_text(json.dumps({"되돌림": 2, "어긋남": []}), encoding="utf-8")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r)})
    확인(code == 0 and "어긋남" in out, "두 번 되돌린 뒤에는 막지 않고 어긋남 개수만 알린다")
    # 기록 보존 (2026-09-17) — 고친 것이 없고 push 가 끝났으면, 한 시간에 한 번 훅이 스스로 기록을 memory/ 로 옮겨 커밋 · push 한다
    git(r, "add", "-A"); subprocess.run(["git", "-C", str(r), "commit", "-q", "--no-verify", "-m", "정리"], capture_output=True, text=True)
    원격 = Path(tempfile.mkdtemp(prefix="ops-origin-")); subprocess.run(["git", "init", "-q", "--bare", str(원격)], check=True)
    git(r, "remote", "add", "origin", str(원격)); git(r, "checkout", "-q", "-b", "claude/x"); git(r, "push", "-q", "-u", "origin", "claude/x")
    기록줄 = json.dumps({"날": "2026-09-17", "누가": "기계", "규칙": "상대날짜"}, ensure_ascii=False) + "\n"
    (r / ".meta/횟수.new.jsonl").write_text(기록줄, encoding="utf-8")
    (r / ".meta/session.json").write_text(json.dumps({"되돌림": 0, "어긋남": []}), encoding="utf-8")
    앞 = git(r, "rev-parse", "HEAD")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r)})
    확인(code == 0 and "커밋 · push 했다" in out and git(r, "rev-parse", "HEAD") != 앞
         and "memory/횟수.jsonl" in git(r, "-c", "core.quotePath=false", "show", "--stat", "--format=", "HEAD")
         and git(r, "rev-parse", "origin/claude/x") == git(r, "rev-parse", "HEAD")
         and not (r / ".meta/횟수.new.jsonl").exists(),
         "고친 것이 없으면 답 끝에 기록을 memory/ 로 옮겨 커밋 · push 한다", (out + " | " + err)[:300])
    (r / ".meta/횟수.new.jsonl").write_text(기록줄, encoding="utf-8")
    뒤 = git(r, "rev-parse", "HEAD")
    code, out, err = 훅돌리기(r, "stop", {"transcript_path": str(tr), "cwd": str(r)})
    확인(code == 0 and git(r, "rev-parse", "HEAD") == 뒤 and (r / ".meta/횟수.new.jsonl").exists(), "한 시간 안에는 기록을 다시 커밋하지 않는다")
    (r / ".meta/횟수.new.jsonl").unlink()
    code, out, err = 훅돌리기(r, "session_start", {"source": "startup", "cwd": str(r)})
    확인(code == 0 and "어긋남 목록" in out and "브랜치" in out, "세션 시작에 목록과 레포 상태가 들어간다")
    code, out, err = 훅돌리기(r, "user_prompt_submit", {"cwd": str(r)})
    확인(code == 0 and "어긋남" in out, "물음 직전에 어긋남 개수 한 줄이 들어간다")

    x = subprocess.run([sys.executable, str(r / "ops/bin/ops"), "hooks", "--push"], cwd=str(r), text=True, capture_output=True,
                       input="refs/heads/claude/x " + "1" * 40 + " refs/heads/main " + "0" * 40 + "\n")
    확인(x.returncode == 1 and "main" in x.stderr, "push 직전에 main 으로 직접 가는 push 를 막는다")
    x = subprocess.run([sys.executable, str(r / "ops/bin/ops"), "hooks", "--push"], cwd=str(r), text=True, capture_output=True,
                       input="refs/heads/claude/x " + "1" * 40 + " refs/heads/claude/x " + "0" * 40 + "\n")
    확인(x.returncode == 0, "세션 브랜치로 가는 새 push 는 막지 않는다")

    shutil.rmtree(r, ignore_errors=True)
    print(f"\n{'전부 통과' if not 실패 else str(len(실패)) + '개 실패: ' + ' / '.join(실패)}")
    return 1 if 실패 else 0


if __name__ == "__main__":
    sys.exit(main())
