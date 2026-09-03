OPS := ops/bin/ops

.PHONY: help ctx build check test find stale
help:            ## 이 목록
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'
ctx:             ## 지금 상황 카드
	@$(OPS) ctx card
build:           ## 파생/생성 파일 전부 재생성
	@$(OPS) build
check:           ## 기계적으로 검사 가능한 규칙 전부 실행
	@$(OPS) check
stale:           ## 출처와 어긋난 파생물 목록
	@$(OPS) link check
test:            ## 4가지 보장이 실제로 성립하는지 end-to-end 검증
	@python3 ops/test/selftest.py
