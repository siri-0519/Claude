# STATE — 지금 상황

> 매 세션 자동 주입되는 카드. **로그가 아니라 예산**입니다 (상한 4096 bytes, HR-005).
> 자세한 내용은 `ops/bin/ops ctx log`로. 여기엔 "새 세션이 10초 안에 알아야 할 것"만.

<!-- BEGIN GENERATED: auto -->
**vault 3 artifacts · 0 edges · 0 stale**

**이전 세션이 남긴 인계**
- 다음 세션: 배선도를 그리다 나온 결함 2건이 미수정으로 남음 — 오늘 고친 4건과 성격이 같고 아직 안 고침. (A) HR-004(비밀정보)는 stage 가 pre_tool 뿐이라 결과 검사가 없다. HR-006/009/010 은 stop 에서 결과를 다시 보므로 인터프리터 쓰기(python3 -c open().write())로 우회해도 잡히지만, HR-004 는 어느 단계에서도 안 잡힌다 — pre_tool 의 _target_paths 가 리다이렉트/sed -i/편집도구 file_path 만 정규식으로 뽑기 때문. 이중 검사 설계에서 유일하게 빠진 자리. (B) evaluate() 의 fn = globals().get(rule['check']); if fn is None: continue — check 함수가 없으면 경고 없이 규칙이 통째로 건너뛰어진다. 크래시는 warn 을 내는데 부재는 침묵이라 비대칭. 함수명 오타 하나로 규칙이 소리 없이 사라질 수 있다. 둘 다 코드를 읽고 판단한 것이며 실제로 재현 시험은 하지 않았음.
- 배선도 아티팩트 발행됨 · vault 편입 여부 미결 — 세션 흐름/정보갱신 배선도를 아티팩트로 발행: https://claude.ai/code/artifact/406b41d4-c46f-468a-a9d1-1d06497a596d

**최근 로그**
- `2026-09-04` decision: kind 6종 유지, 분류의 무게는 라벨로
- `2026-09-04` work: 결함 2건 수정 — HR-004 결과 검사 추가, check 함수 부재 시 침묵 제거
- `2026-09-04` handoff: 다음 세션: 배선도를 그리다 나온 결함 2건이 미수정으로 남음
- `2026-09-04` note: 배선도 아티팩트 발행 · wake 구독은 두 세션 연속 403
- `2026-09-04` work: 검증에서 나온 결함 4건 수정 — 코드 파일 손상, inbox 잠김, 플래그 반복 유실, 문서 불일치
- `2026-09-04` decision: 콘텐츠 벡터: 자리만 확정, 활성화는 코퍼스 이후

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
