# STATE — 지금 상황

> 매 세션 자동 주입되는 카드. **로그가 아니라 예산**입니다 (상한 4096 bytes, HR-005).
> 자세한 내용은 `ops/bin/ops ctx log`로. 여기엔 "새 세션이 10초 안에 알아야 할 것"만.

<!-- BEGIN GENERATED: auto -->
**vault 1 artifacts · 0 edges · 0 stale**

**이전 세션이 남긴 인계**
- 다음 세션: soft.md를 실제 취향으로 교체하고 진짜 데이터 넣기 — ops/rules/soft.md의 SR-001~005는 시드값입니다. vault/는 아직 비어 있고 ADR 1건뿐.

**최근 로그**
- `2026-09-04` handoff: 다음 세션: soft.md를 실제 취향으로 교체하고 진짜 데이터 넣기
- `2026-09-04` note: 훅을 직접 써보며 결함 2개 수정
- `2026-09-04` decision: 검사 가능한 규칙은 전부 훅으로, 나머지만 자연어로
- `2026-09-04` work: 작업 환경 초기 구축

더 보려면: `ops/bin/ops ctx log -n 30` / `ops/bin/ops ctx log --grep 키워드`
<!-- END GENERATED: auto -->

## 지금 하는 일

- 작업 환경 구축 완료. `make test` 48개 통과. 브랜치 `claude/work-environment-setup-oiqrl4`.

## 다음

- `ops/rules/soft.md`의 SR-001~005는 **시드값** — 실제 취향으로 교체할 것
- `vault/`는 비어 있음. 실제 데이터를 `ops/bin/ops new` / `ingest`로 넣으며 라벨 체계 다듬기
- 규칙이 거슬리면 `ops/rules/hard.yml`을 고치면 됨 (규칙 = 코드, 표는 CLAUDE.md에 자동 반영)

## 열린 질문

- `vault/` 하위 분류(code/docs/knowledge/records/inbox)가 실제 데이터에 맞는지는 미검증
