# 작업 규약

이 레포는 **쌓이는 모든 것**(코드·문서·지식·기록·결정·비정형 투입물)을 한 곳에 두되,
각 조각이 **어디서 왔는지(provenance)** 를 기계가 알 수 있게 유지하는 것을 목표로 합니다.

명령은 전부 하나입니다: **`ops/bin/ops`** (이하 `ops`). 다른 곳에 스크립트를 만들지 마세요.

---

## 1. 세션 시작 — 레포를 읽지 마세요

SessionStart 훅이 `memory/STATE.md`를 자동 주입합니다. 그게 출발점입니다.
더 필요하면 **그때만** 좁혀서 읽으세요:

| 알고 싶은 것 | 명령 |
|---|---|
| 최근에 무슨 일이 있었나 | `ops ctx log -n 20` |
| 특정 주제의 이력 | `ops ctx log --grep 키워드` |
| 어떤 자료가 있나 | `INDEX.md` → `ops find --label X --kind Y` |
| 이건 어디서 나왔나 | `ops link why <id\|path>` |
| 이걸 고치면 뭐가 깨지나 | `ops link impact <id\|path>` |
| 지금 규칙 위반이 있나 | `ops check` |

**전체 레포 훑기 금지.** `INDEX.md`는 모든 아티팩트의 id·라벨·요약을 담은 지도입니다.
지도를 먼저 보고, 맞는 파일만 여세요. 큰 파일은 `sed -n 'A,Bp'`로 구간만.

## 2. 데이터를 쌓을 때 — 라벨과 출처를 같이

```bash
ops new <kind> <path> --title "..." --label a,b --summary "..." [--source <출처 id>]
ops ingest [경로]        # 이미 있는 무라벨 파일들에 메타데이터 일괄 부여
```

`kind`: `code` `doc` `knowledge` `record` `raw` `decision` — 정의는 `ops/schema/frontmatter.yml`.
비정형/바이너리는 `<파일>.meta.yml` 사이드카로 같은 메타데이터를 갖습니다.

**`--source`가 이 레포의 핵심입니다.** B가 A에서 파생됐다면 B는 A의 id와 *그 시점의 해시*를
박아둡니다. 나중에 A의 본문이 바뀌면 B는 자동으로 `stale`이 되고, HR-009가 턴 종료를 막습니다.

## 3. 무언가를 고쳤을 때

1. 출처를 고쳤다면 → PostToolUse 훅이 영향받는 파생물을 즉시 알려줍니다.
2. 파생물을 실제로 갱신했으면 → `ops link ack <파생물 id>` (해시 재고정 = "반영 완료" 선언)
3. 갱신이 불필요하다고 판단했어도 → 그래도 `ack`. 판단했다는 사실을 남기는 것입니다.
4. 생성물(INDEX.md, digest, 아래 규칙 블록, STATE.md 자동 블록)은 **손으로 고치지 말고** `ops build`.

## 4. 세션 종료 전 — 다음 세션을 위해

```bash
ops log add --kind work     --title "무엇을 했는지" --body "..." --ref 경로
ops log add --kind decision --title "무엇을 왜 정했는지"      # 큰 결정은 memory/decisions/에 ADR도
ops log add --kind blocker  --title "막힌 것"
ops log add --kind handoff  --title "다음 세션이 먼저 볼 것"
```

로그의 정본은 `memory/log/YYYY-MM.jsonl`(기계용)이고, 사람이 읽는
`memory/digest/YYYY-MM.md`(한국어)는 거기서 **자동 생성**됩니다. 둘을 따로 쓰지 마세요 — 어긋납니다.
`memory/STATE.md`는 "지금 상황" 카드입니다. 로그가 아니라 예산이므로 짧게 유지하세요.

---

<!-- BEGIN GENERATED: rules -->
### Hard rules — enforced by hooks, not by your goodwill

| id | stage | on violation | rule |
|----|-------|--------------|------|
| `HR-001` | pre_tool | **deny** | No history rewriting or force-push |
| `HR-002` | pre_tool | **deny** | No recursive delete of the repo's own machinery |
| `HR-003` | pre_tool | **deny** | Generated files and generated blocks are not hand-editable |
| `HR-004` | pre_tool | **deny** | No secrets into the working tree |
| `HR-005` | pre_tool+stop | **deny** | memory/STATE.md stays under its size cap |
| `HR-006` | pre_tool+stop | **deny** | New vault artifacts must carry front-matter |
| `HR-007` | pre_tool | **warn** | Don't bulk-read the repo |
| `HR-008` | post_tool | **warn** | Editing a source makes its descendants stale |
| `HR-009` | stop | **deny** | No stale derivations at end of turn |
| `HR-010` | stop | **deny** | Generated files must be current |
| `HR-011` | stop | **deny** | A session that changed things must leave a log entry |

Full text + escape hatches: `ops/rules/hard.yml`. A `deny` is not advice —
the tool call does not run. Don't try to route around it; fix the cause or ask.

### Soft rules — you enforce these; nothing else can

- **SR-001** (no unhedged assertions) — Separate what you verified from what you inferred; never state an unchecked claim flatly.
- **SR-002** (report outcomes faithfully) — Say plainly what failed, what you skipped, and what you did not verify. Never round a partial result up to "done".
- **SR-003** (hold the scope) — Deliver exactly the requested scope. Raise a concern in one or two sentences, then finish the work — don't silently shrink or widen it.
- **SR-004** (answer in Korean) — Reply to the user in Korean. Code, identifiers, file paths, and rule text stay in English.
- **SR-005** (no preamble, no flattery) — Open with the answer. No "좋은 질문입니다", no restating the request back.

Examples of each: `ops/rules/soft.md`.
<!-- END GENERATED: rules -->

---

## 위반이 막혔을 때

`deny`는 조언이 아니라 차단입니다. 우회하려 하지 말고: 원인을 고치거나, 사용자에게 물으세요.
정말 필요한 예외는 눈에 보이게 — `OPS_ALLOW=HR-001 git push --force ...` (쓰기 전에 사용자 동의).
훅 자체를 끄는 `OPS_HOOKS=off`는 훅을 디버깅할 때만.
