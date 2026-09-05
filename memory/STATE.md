# STATE — 지금 상황

> 매 세션 자동 주입되는 카드. **로그가 아니라 예산**입니다 (상한 4096 bytes, HR-005).
> 자세한 내용은 `ops/bin/ops ctx log`로. 여기엔 "새 세션이 10초 안에 알아야 할 것"만.

<!-- BEGIN GENERATED: auto -->
**vault 3 artifacts · 1 edges · 0 stale**

**이전 세션이 남긴 인계**
- 승인 댓글 문구는 손대지 않음 — 사용자가 직접 고치기로 — 「승인 조건 판정」 코드 노드의 approve_comment 문자열이 그 자리다. 고치는 방법은 워크플로 안 스티키 메모 「승인 댓글 문구를 바꾸려면」에 적어뒀다. 별건: 스티키 「조건부 봇 승인 안내」는 '승인·승인 댓글 노드가 꺼져 있고 자격증명도 안 붙어 있다'고 적혀 있으나 실제 JSON에서는 둘 다 켜져 있고 jjiu_gitlab(최현민 개인 토큰)이 붙어 있다. 그 메모가 하지 말라던 바로 그 상태 — 사용자 확인 필요.
- 배선도 아티팩트 발행됨 · vault 편입 여부 미결 — 세션 흐름/정보갱신 배선도를 아티팩트로 발행: https://claude.ai/code/artifact/406b41d4-c46f-468a-a9d1-1d06497a596d

**미해결 blocker**
- ▲ GitLab 프로젝트 웹훅 등록은 Maintainer 권한 필요 — 최현민(Developer)은 못 함 (2026-09-05)

**최근 로그**
- `2026-09-05` handoff: 승인 댓글 문구는 손대지 않음 — 사용자가 직접 고치기로
- `2026-09-05` blocker: GitLab 프로젝트 웹훅 등록은 Maintainer 권한 필요 — 최현민(Developer)은 못 함
- `2026-09-05` work: n8n GitLab 알림 워크플로: 1분 폴링 → 웹훅 트리거로 교체
- `2026-09-04` note: SessionStart 훅은 아직 실제 세션에서 검증 안 됨
- `2026-09-04` handoff: 배선도 아티팩트 발행됨 · vault 편입 여부 미결
- `2026-09-04` handoff: 다음 세션: soft.md를 실제 취향으로 교체하고 진짜 데이터 넣기

더 보려면: `ops/bin/ops ctx log -n 30` / `ops/bin/ops ctx log --grep 키워드`
<!-- END GENERATED: auto -->

## 지금 하는 일

- n8n GitLab 알림 워크플로를 1분 폴링 → 웹훅 트리거로 교체. 브랜치 `claude/n8n-mr-trigger-comment-3dbj18`.
  결과물 `vault/code/n8n-gitlab-mr-webhook.json` (C-20260905-5bff4e), 원본은 `vault/inbox/`에 X-20260905-69ec7e.

## 다음

- **막힘**: GitLab 프로젝트 웹훅 등록은 Maintainer 권한. 세 저장소에 등록되기 전엔 워크플로가 조용하다.
- 승인 댓글 문구는 사용자가 직접 고칠 예정 — 「승인 조건 판정」 노드의 `approve_comment`.
- `ops/rules/soft.md`의 SR-001~005는 **시드값** — 실제 취향으로 교체할 것

## 열린 질문

- 스티키 「조건부 봇 승인 안내」와 실제 노드 상태가 어긋난다(메모: 꺼짐·자격증명 없음 / 실제: 켜짐·jjiu_gitlab). 어느 쪽이 맞나?
- `vault/` 하위 분류(code/docs/knowledge/records/inbox)가 실제 데이터에 맞는지는 미검증
