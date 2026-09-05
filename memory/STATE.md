# STATE — 지금 상황

> 매 세션 자동 주입되는 카드. **로그가 아니라 예산**입니다 (상한 4096 bytes, HR-005).
> 자세한 내용은 `ops/bin/ops ctx log`로. 여기엔 "새 세션이 10초 안에 알아야 할 것"만.

<!-- BEGIN GENERATED: auto -->
**vault 1 artifacts · 0 edges · 0 stale**

**이전 세션이 남긴 인계**
- 배선도 아티팩트 발행됨 · vault 편입 여부 미결 — 세션 흐름/정보갱신 배선도를 아티팩트로 발행: https://claude.ai/code/artifact/406b41d4-c46f-468a-a9d1-1d06497a596d
- 다음 세션: soft.md를 실제 취향으로 교체하고 진짜 데이터 넣기 — ops/rules/soft.md의 SR-001~005는 시드값입니다. vault/는 아직 비어 있고 ADR 1건뿐.

**최근 로그**
- `2026-09-05` work: answer-level hooks are detected by content, not by name
- `2026-09-05` work: one item is now one thing a person can judge on its own
- `2026-09-04` work: the router now finds the parent directory from inside a submodule
- `2026-09-04` work: 판정을 일감 단위로 좁힐 수 있게 했다
- `2026-09-04` work: 항에 안 바뀌는 이름을 붙였다 — 본문을 고쳐도 판정이 남는다
- `2026-09-04` decision: 누가 냈나 — 레포끼리 나눠 쓰는 기계를 여기에 두었다

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
