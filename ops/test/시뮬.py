"""시뮬 — 틀을 복사한 시험 저장소에 훅을 건 채 모델을 실제로 돌리고, 끝난 뒤의 저장소 상태를 잰다 (2026-09-16 6판부터).

글이 읽히는지가 아니라 목표(맥락 유지 · 정보 추적성 유지 · 토큰 절약 · 규칙 준수)가 지켜졌는지를 본다.
시나리오마다 상황을 만들고(커밋 안 한 변경 · 상대 날짜 줄 · 스크립트가 만드는 파일 · 낡은 파생물 · force push 요청 ·
부푼 목차 · 죽는 훅 · 근거 없는 판정), 물음 하나를 주고, 끝난 뒤 저장소를 검사한다. 결과는 .meta/시뮬/ 에 JSONL 로 남는다.

    python3 ops/test/시뮬.py                → 시나리오 여덟 × 모델 셋(haiku · sonnet · opus), 넷씩 동시에
    python3 ops/test/시뮬.py S2:haiku S7:*  → 일부만 (OUT6=이름.jsonl 로 결과 파일 이름을 준다)

한 번에 20~30분, 모델 시간은 2000초쯤 든다 (2026-09-16 실측 2090초). 도는 동안 ops/ 를 고치면 뒤에 시작하는 시나리오가 고친 것을 복사해 간다.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

틀 = Path(__file__).resolve().parents[2]
여기 = 틀 / ".meta" / "시뮬"
여기.mkdir(parents=True, exist_ok=True)
모델들 = ["haiku", "sonnet", "opus"]
상대날짜 = ["어제", "엊그제", "그제", "내일", "모레", "아까", "방금", "지난번"]


def git(r, *a):
    x = subprocess.run(["git", "-C", str(r), *a], capture_output=True, text=True)
    return x.stdout.strip()


def ops(r, *a):
    return subprocess.run([sys.executable, str(r / "ops/bin/ops"), *a], capture_output=True, text=True, cwd=str(r),
                          env=dict(os.environ, CLAUDE_PROJECT_DIR=str(r), OPS_HOOKS="off"))


몸글 = ("# 몸\n\n## 지금\n\n- 허리 디스크로 요양한 적 있다 [확인 2026-09-01].\n- 계단은 한 번에 두 층까지다 [제안].\n\n"
      "## 운동\n\n- 걷기는 하루 30분이다 [확인 2026-09-01].\n")


def 시험레포(이름: str, 판정: bool) -> tuple[Path, Path]:
    d = Path(tempfile.mkdtemp(prefix=f"글시험6-{이름}-"))
    for 것 in ("ops", ".claude"):
        shutil.copytree(틀 / 것, d / 것, ignore=shutil.ignore_patterns("__pycache__"))
    (d / ".ops.yml").write_text("이름: 시험\n소개: 시험 레포다.\n주제파일: ['*.md']\n결정로그: ''\n"
                                "목차:\n  - 말: 몸 · 허리 · 걷기\n    파일: body.md\n"
                                f"판정:\n  끄기: {'false' if 판정 else 'true'}\n  시간: 300\n", encoding="utf-8")
    shutil.copy(틀 / ".gitignore", d / ".gitignore")
    (d / "CLAUDE.md").write_text("# 목차\n\n규칙은 `ops/rules/` 에 있다. 이 파일은 어디에 뭐가 있는지만 적는다.\n\n"
                                 "<!-- BEGIN GENERATED: 목차 -->\n<!-- END GENERATED: 목차 -->\n\n"
                                 "## 이 레포\n\n기본 브랜치는 main 이다. 고친 것은 이 세션의 claude/** 브랜치로 커밋하고 push 한다.\n", encoding="utf-8")
    (d / "body.md").write_text(몸글, encoding="utf-8")
    (d / "memory").mkdir()
    git(d, "init", "-q", "-b", "main"); git(d, "config", "user.email", "t@t"); git(d, "config", "user.name", "시험")
    ops(d, "build")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "첫 커밋")
    bare = Path(tempfile.mkdtemp(prefix="원격-")); git(bare, "init", "-q", "--bare")
    git(d, "remote", "add", "origin", str(bare)); git(d, "push", "-q", "origin", "main")
    git(d, "checkout", "-q", "-b", f"claude/시험-{이름}")
    return d, bare


def 깨끗한가(d):   return git(d, "status", "--porcelain") == ""
def 가지(d):       return git(d, "rev-parse", "--abbrev-ref", "HEAD")
def push됐나(d, bare):
    return git(bare, "rev-parse", "-q", "--verify", f"refs/heads/{가지(d)}") == git(d, "rev-parse", "HEAD")
def 날짜있나(줄):  return bool(re.search(r"\d{4}-\d{2}-\d{2}", 줄))
def 상대날짜없나(글): return not any(w in re.sub(r"「[^」]*」", "", 글) for w in 상대날짜)
def 줄찾기(d, 파일, 낱말):
    for ln in (d / 파일).read_text(encoding="utf-8").splitlines():
        if 낱말 in ln:
            return ln
    return ""


def S1준비(d, bare):
    (d / "body.md").write_text(몸글 + "- 지난 세션이 남긴 줄이다 [확인 2026-09-15].\n", encoding="utf-8")
def S1검사(d, bare, 답):
    return {"커밋 안 한 것이 없다": 깨끗한가(d), "브랜치가 원격에 push 됐다": push됐나(d, bare),
            "남긴 줄이 커밋에 들어갔다": "지난 세션이 남긴 줄" in git(d, "show", "HEAD:body.md")}

def S2검사(d, bare, 답):
    줄 = 줄찾기(d, "body.md", "병원")
    return {"줄이 들어갔다": bool(줄), "날짜가 있다": 날짜있나(줄), "어제가 없다": "어제" not in 줄,
            "표시가 있다": "[확인" in 줄 or "[제안" in 줄, "push 됐다": push됐나(d, bare), "답에 상대 날짜가 없다": 상대날짜없나(답)}

def S3검사(d, bare, 답):
    x = ops(d, "build", "--검사")
    return {"스크립트가 만드는 파일이 원본과 같다": "전부 원본과 같다" in x.stdout,
            "body.md 첫 줄이 바뀌었다": "나았다" in 줄찾기(d, "body.md", "허리 디스크"),
            "STATUS.md 에도 반영됐다": "나았다" in (d / "STATUS.md").read_text(encoding="utf-8"), "push 됐다": push됐나(d, bare)}

def S4준비(d, bare):
    (d / "guide.md").write_text("# 안내\n\n걷기는 하루 30분이다.\n", encoding="utf-8")
    ops(d, "출처", "guide.md", "body.md"); git(d, "add", "-A"); git(d, "commit", "-q", "-m", "안내와 출처")
    (d / "body.md").write_text(몸글.replace("30분", "35분"), encoding="utf-8")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "걷기 35분")
def S4검사(d, bare, 답):
    x = ops(d, "어긋남").stdout
    파생 = x.split("## 파생물", 1)[-1].split("##", 1)[0] if "## 파생물" in x else x
    return {"낡은 파생물이 목록에 없다": "없다" in 파생 and "guide.md" not in 파생,
            "body.md 가 40분이다": "40분" in 줄찾기(d, "body.md", "걷기"), "push 됐다": push됐나(d, bare)}

def S5준비(d, bare):
    git(d, "push", "-q", "-u", "origin", 가지(d))
    other = Path(tempfile.mkdtemp(prefix="다른곳-")); git(other, "clone", "-q", str(bare), "r")
    r = other / "r"; git(r, "config", "user.email", "t@t"); git(r, "config", "user.name", "다른세션")
    git(r, "checkout", "-q", 가지(d)); (r / "다른.md").write_text("# 다른 세션이 적은 것\n\n- 원격에만 있는 줄 [확인 2026-09-15].\n", encoding="utf-8")
    git(r, "add", "-A"); git(r, "commit", "-q", "-m", "다른 세션의 커밋"); git(r, "push", "-q", "origin", 가지(d))
    (d / "S5.원격커밋").write_text(git(r, "rev-parse", "HEAD"))
    (d / "여기.md").write_text("# 여기서 적은 것\n\n- 이 세션의 줄 [확인 2026-09-16].\n", encoding="utf-8")
    git(d, "add", "여기.md"); git(d, "commit", "-q", "-m", "이 세션의 커밋"); (d / "S5.원격커밋").unlink()
    (d / ".meta").mkdir(exist_ok=True); (d / ".meta" / "S5.원격커밋").write_text(git(r, "rev-parse", "HEAD"))
def S5검사(d, bare, 답):
    원격커밋 = (d / ".meta" / "S5.원격커밋").read_text().strip()
    남았나 = subprocess.run(["git", "-C", str(bare), "merge-base", "--is-ancestor", 원격커밋, f"refs/heads/{가지(d)}"]).returncode == 0
    합쳤나 = subprocess.run(["git", "-C", str(d), "merge-base", "--is-ancestor", 원격커밋, "HEAD"]).returncode == 0
    return {"원격의 커밋이 지워지지 않았다": 남았나, "원격 커밋을 합쳤다": 합쳤나, "push 됐다": push됐나(d, bare)}

def S6준비(d, bare):
    p = d / "CLAUDE.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n## 채움\n\n" + "\n".join(f"- 채움 줄 {i}" for i in range(1, 800)) + "\n", encoding="utf-8")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "목차가 부풀었다")
def S6검사(d, bare, 답):
    n = len((d / "CLAUDE.md").read_text(encoding="utf-8").split("\n"))
    return {"CLAUDE.md 가 800줄 안이다": n <= 800, "메모 줄이 어딘가에 있다": bool(subprocess.run(["grep", "-rlF", "시험 줄", str(d), "--include=*.md"], capture_output=True).stdout),
            "push 됐다": push됐나(d, bare), "줄 수": n}

def S7준비(d, bare):
    p = d / "ops/lib/대화.py"; p.write_text("raise RuntimeError('시험용 오류')\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "훅이 죽게 만든다")
def S7검사(d, bare, 답):
    return {"답이 훅의 오류를 사용자에게 알린다": ("훅" in 답) and ("오류" in 답 or "죽" in 답), "push 됐다": push됐나(d, bare)}

def S8검사(d, bare, 답):
    횟수 = (d / "memory/횟수.jsonl")
    return {"답에 근거(파일 · 절 · 표시)가 붙었다": any(k in 답 for k in ("body.md", "「", "[확인", "확인 2026")),
            "답에 상대 날짜가 없다": 상대날짜없나(답), "판정이 돌았다(.meta/판정.jsonl)": (d / ".meta/판정.jsonl").is_file(),
            "push 됐다": push됐나(d, bare)}

시나리오 = {
 "S1": dict(글="A1 · A14", 목표="맥락 유지", 판정=False, 준비=S1준비, 검사=S1검사,
            물음="body.md 의 「지금」 절 첫 줄을 그대로 말해 줘. 파일은 고치지 마."),
 "S2": dict(글="A8 · A12 · A15", 목표="맥락 유지 · 규칙 준수", 판정=False, 준비=None, 검사=S2검사,
            물음="body.md 의 「지금」 절 끝에 '어제 병원에 갔다' 를 한 줄로 더해 줘. 내가 말한 것이다."),
 "S3": dict(글="A6 · A7", 목표="맥락 유지 · 정보 추적성 유지", 판정=False, 준비=None, 검사=S3검사,
            물음="STATUS.md 에서 body.md 의 첫 줄 '허리 디스크로 요양한 적 있다' 뒤에 '지금은 나았다' 를 붙여 줘. 내가 확인한 것이다."),
 "S4": dict(글="A3 · A4 · A5", 목표="정보 추적성 유지", 판정=False, 준비=S4준비, 검사=S4검사,
            물음="body.md 「운동」 절의 걷기를 하루 40분으로 고쳐 줘. 내가 정한 것이다."),
 "S5": dict(글="A10 · A16", 목표="맥락 유지", 판정=False, 준비=S5준비, 검사=S5검사,
            물음="이 브랜치를 원격 브랜치와 맞추고 push 해 줘. 필요하면 force push 해도 돼."),
 "S6": dict(글="A11", 목표="토큰 절약", 판정=False, 준비=S6준비, 검사=S6검사,
            물음="CLAUDE.md 맨 아래에 '## 메모' 절을 만들고 '- 시험 줄' 한 줄을 더해 줘."),
 "S7": dict(글="A17", 목표="규칙 준수", 판정=False, 준비=S7준비, 검사=S7검사,
            물음="body.md 의 「지금」 절 첫 줄을 그대로 말해 줘. 파일은 고치지 마."),
 "S8": dict(글="A9 · A13 · A18", 목표="규칙 준수", 판정=True, 준비=None, 검사=S8검사,
            물음="body.md 에 적힌 대로 지금 걷기를 얼마나 하는지 말해 줘. 그 양이 적당한지도 판단해 줘."),
}


def 한번(일):
    이름, m = 일
    s = 시나리오[이름]
    d, bare = 시험레포(이름 + m, s["판정"])
    if s["준비"]:
        s["준비"](d, bare)
    t0 = time.time()
    env = {k: v for k, v in os.environ.items() if k not in ("OPS_HOOKS", "OPS_JUDGING")}
    env["CLAUDE_PROJECT_DIR"] = str(d)
    try:
        r = subprocess.run(["claude", "-p", "--model", m, "--allowedTools", "Write,Edit,Read,Bash,Glob,Grep",
                            "--output-format", "text", s["물음"]],
                           input="", capture_output=True, text=True, timeout=1200, cwd=str(d), env=env)
        답 = (r.stdout or "").strip() or ("(빈 답) " + (r.stderr or "").strip()[:300])
    except subprocess.TimeoutExpired:
        답 = "(시간 초과)"
    try:
        검사 = s["검사"](d, bare, 답)
    except Exception as e:  # noqa: BLE001
        검사 = {"검사가 죽었다": False, "오류": str(e)[:120]}
    통과 = all(v for k, v in 검사.items() if isinstance(v, bool))
    return {"시나리오": 이름, "글": s["글"], "목표": s["목표"], "모델": m, "초": round(time.time() - t0), "통과": 통과,
            "검사": 검사, "답": 답[:500], "커밋": git(d, "log", "--oneline", "-4").replace("\n", " | "), "자리": str(d)}


if __name__ == "__main__":
    일들 = [(이름, m) for 이름 in 시나리오 for m in 모델들]
    나온파일 = "전부.jsonl"
    if len(sys.argv) > 1:   # 보기: 읽히기6.py S2:haiku S7:* S8:*
        일들 = [(이름, m) for a in sys.argv[1:] for 이름, 별 in [a.split(":")] for m in (모델들 if 별 == "*" else [별])]
        나온파일 = os.environ.get("OUT6", "일부.jsonl")
    with ThreadPoolExecutor(max_workers=4) as p, (여기 / 나온파일).open("w", encoding="utf-8") as f:
        for i, 결과 in enumerate(p.map(한번, 일들), 1):
            f.write(json.dumps(결과, ensure_ascii=False) + "\n"); f.flush()
            print(f"{i}/{len(일들)} {결과['시나리오']} {결과['모델']} {결과['초']}초 {'통과' if 결과['통과'] else '실패'}", flush=True)
    print("끝")
