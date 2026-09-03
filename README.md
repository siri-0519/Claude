# Claude 작업 레포

코드·문서·지식·기록·결정·비정형 투입물을 한 곳에 쌓되, **각 조각이 어디서 왔는지**를
기계가 알고 있는 상태를 유지하는 저장소입니다. 규칙은 문서가 아니라 훅으로 강제됩니다.

## 5분 안에 쓰기

```bash
make help          # 명령 목록
make ctx           # 지금 상황
make check         # 규칙 위반 있나
make test          # 4가지 보장이 실제로 성립하는지 검증 (48 checks)
```

데이터 넣기:

```bash
ops/bin/ops new doc vault/docs/plan.md --title "계획" --label proj-a
ops/bin/ops new knowledge vault/knowledge/plan-summary.md \
    --title "계획 요약" --source D-20260904-ab12c3      # ← 파생 선언
ops/bin/ops ingest vault/inbox --label proj-a          # 이미 있는 파일에 라벨 붙이기
```

## 네 가지 보장과, 그것을 실제로 지키는 장치

| 보장 | 장치 | 강제 |
|---|---|---|
| ① 규칙이 지켜진다 | `ops/rules/hard.yml` → PreToolUse/Stop 훅 | **차단** (HR-001~011) |
| | `ops/rules/soft.md` → 매 턴 재주입 | 자가 준수 (강제 불가) |
| ② 세션 간 문맥 유지 | `memory/STATE.md` 자동 주입 + `memory/log/*.jsonl` | HR-011이 무기록 종료 차단 |
| ③ 토큰 절약 | `INDEX.md` 지도 + `ops find` + 카드 바이트 상한 | HR-007 경고, 카드 상한 강제 |
| ④ 파생 연계 | front-matter `derives_from: [{id, hash}]` | HR-009가 stale 상태 종료 차단 |

④의 핵심: B가 A에서 파생될 때 B는 **그 시점 A의 본문 해시**를 박아둡니다. A의 본문이 바뀌면
해시가 어긋나 B는 자동으로 `stale`이 되고, 반영 후 `ops/bin/ops link ack B`로 다시 고정합니다.
A의 라벨만 바꾸는 것처럼 본문이 그대로인 변경은 B를 건드리지 않습니다.

## 구조

```
CLAUDE.md              항상 로드되는 규약. 규칙 표는 hard.yml/soft.md에서 자동 생성
INDEX.md               모든 아티팩트의 지도 (자동 생성) — 레포를 훑는 대신 이걸 보세요
ops/     rules/        hard.yml (기계 강제) · soft.md (자가 준수)
         schema/       메타데이터 정의 = 단일 진실원
         lib/core.py   규칙 엔진 + 파생 그래프 + 생성기
         bin/ops       유일한 CLI
         test/         end-to-end 검증
memory/  STATE.md      세션 시작 시 자동 주입되는 카드 (4KB 상한)
         log/*.jsonl   기계용 정본 로그
         digest/*.md   사람용 한국어 요약 (jsonl에서 자동 생성)
         decisions/    ADR
vault/   code/ docs/ knowledge/ records/ inbox/    실제로 쌓이는 것들
```

## 문제가 생기면

- 차단이 부당하다 → `ops/rules/hard.yml`의 해당 규칙을 고치세요. 규칙이 곧 코드입니다.
- 일회성 예외 → `OPS_ALLOW=HR-001 <명령>` (눈에 보이게, 사용자 동의 후)
- 훅 자체를 끄기 → `OPS_HOOKS=off` (훅 디버깅 전용)
- 턴이 안 끝난다 → `make check`. 3회 차단 후에는 자동으로 풀립니다.

## 이 시스템이 막지 못하는 것 (알고 쓰세요)

- **soft 규칙은 강제되지 않습니다.** 매 턴 재주입해 확률을 올릴 뿐입니다. 지켜지는지
  확인하려면 결과물을 읽는 수밖에 없습니다. 짧게 유지하는 것이 유일한 레버입니다.
- **PreToolUse 차단은 우회 가능합니다.** 셸 리다이렉트·`sed -i`·편집 도구는 잡지만,
  인터프리터가 직접 파일을 쓰면(`python3 -c "open(...).write(...)"`) 통과합니다.
  그래서 같은 규칙을 **Stop 단계에서 결과로 다시 검사**합니다 — 어떤 경로로 썼든
  생성물이 낡았거나(HR-010) 파생이 어긋났거나(HR-009) 라벨이 없으면(HR-006) 턴이 끝나지 않습니다.
- **파생 갱신은 자동이 아닙니다.** 지식 문서는 결정론적 함수가 아니므로 자동 재생성 대신
  `stale` 표시 + 종료 차단으로 판단을 강제합니다. 실제로 고치는 것은 사람/모델의 몫입니다.
- **Stop 차단은 3회 후 풀립니다.** 고칠 수 없는 위반에 세션이 갇히는 것을 막기 위한
  의도적 상한입니다. 풀렸다는 것은 해결됐다는 뜻이 아닙니다 — `make check`로 확인하세요.
