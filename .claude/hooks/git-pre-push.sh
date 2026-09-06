#!/usr/bin/env bash
#
# git 의 pre-push 훅. 이력을 다시 쓰는 push(force · non-fast-forward)와 원격 브랜치 삭제를 막는다.
#
# 왜 있는가 (2026-09-05). 「누가 냈나」는 git 이력의 커밋을 근거로 삼는다 — 작가의 판정
# 커밋이 그 근거다. 이력을 다시 쓰면 근거가 사라진다. 어제 적대 검증에서 force-push 를
# 막는 것이 이 레포에 없었다. 명령문을 보는 검사와 달리 git 자체가 도는 자리라, 명령을
# 파일에 넣어 돌려도 못 피한다.
#
# 셸 변수 이름은 영문으로 둔다. bash 는 한글 이름을 못 쓴다.
#
# 넘기려면: OPS_ALLOW=force-push git push ... (쓰기 전에 작가에게 말한다)
set -uo pipefail
case ",${OPS_ALLOW:-}," in *,force-push,*) exit 0 ;; esac
ZERO=0000000000000000000000000000000000000000
status=0
while read -r local_ref local_sha remote_ref remote_sha; do
  [ -n "${remote_ref:-}" ] || continue
  if [ "$local_sha" = "$ZERO" ]; then
    echo "[이력] 원격 브랜치 삭제를 막는다: $remote_ref"
    echo "  정말 지워야 하면 OPS_ALLOW=force-push 를 붙이고, 쓰기 전에 작가에게 말한다."
    status=1
    continue
  fi
  if [ "$remote_sha" != "$ZERO" ] && ! git merge-base --is-ancestor "$remote_sha" "$local_sha" 2>/dev/null; then
    echo "[이력] 이력을 다시 쓰는 push 를 막는다: $remote_ref"
    echo "  원격의 $(git rev-parse --short "$remote_sha" 2>/dev/null || echo "$remote_sha") 가 보내려는 $(git rev-parse --short "$local_sha") 의 조상이 아니다 — 원격에 있는 커밋이 사라진다."
    echo "  먼저 원격을 합친다: git pull --no-rebase. 정말 필요하면 OPS_ALLOW=force-push 를 붙이고, 쓰기 전에 작가에게 말한다."
    status=1
  fi
done
exit $status
