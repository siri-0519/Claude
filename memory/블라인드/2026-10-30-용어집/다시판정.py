"""사용량 제한에 막혀 판정하지 못한 줄만 다시 판정한다. 답과 파일 상태는 결과 파일에 남은 것을 그대로 쓴다.
쓰는 법: python3 다시판정.py <가|나> <회>
"""
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

판, 회 = sys.argv[1], sys.argv[2]
sys.argv = ["시험.py", 판, 회]
spec = importlib.util.spec_from_file_location("시험", Path(__file__).with_name("시험.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

파일 = Path(__file__).with_name(f"결과-{판}-{회}.json")
d = json.loads(파일.read_text(encoding="utf-8"))
막힘 = [i for i, x in enumerate(d["결과"]) if x["종류"] == "상황" and ("hit your" in x["근거"] or "limit" in x["근거"])]
with ThreadPoolExecutor(14) as ex:
    새 = list(ex.map(lambda i: t.판정({k: v for k, v in d["결과"][i].items() if k not in ("같다", "근거")}), 막힘))
for i, x in zip(막힘, 새):
    d["결과"][i] = {**x, "다시 판정": True}
파일.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"다시 판정 {len(막힘)}줄, 아직 막힌 줄 {sum(1 for x in 새 if 'hit your' in x['근거'])}")
for x in 새:
    print(f"  {x['모델']:7} {x['상황']:26} {'같다' if x['같다'] else '다르다'} — {x['근거'][:200]}")
