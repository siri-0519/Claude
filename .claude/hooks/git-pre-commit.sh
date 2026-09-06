#!/usr/bin/env bash
#
# 커밋 앞에서 이 레포의 검사를 돌린다.
#
# 세션 설정(.claude/settings.json)은 세션의 프로젝트 자리가 이 레포일 때만 읽힌다.
# 레포 위에서 세션이 열리면 그 설정이 통째로 안 읽히고 훅이 아무 말 없이 꺼진다.
# git 훅은 세션과 무관하게 도니까 마지막 방벽이다 (2026-09-04).
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"
[ -x "$ROOT/ops/bin/ops" ] || exit 0
[ "${OPS_HOOKS:-}" = off ] && exit 0
"$ROOT/ops/bin/ops" check
