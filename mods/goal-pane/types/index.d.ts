/** 지난 목표 하나 */
export type PastGoal = { goal: string; since: string; why: string }

/**
 * 사용자의 요청들이 궁극적으로 이루려는 것. 거의 바뀌지 않는다.
 * 세션 제목 맨 뒤 대괄호에 붙는다(제목은 설정 훅 title-hook.mjs 가 바꾼다)
 */
export type GoalState = {
  /** 짧은 궁극 목표, 20자 안팎 */
  goal: string
  /** 이 목표가 정해진 때 (ISO 시각) */
  since: string
  /** 몇 번째 목표인가. 처음 1 */
  n: number
  /** 바로 앞 목표에서 바뀐 까닭. 처음이면 빈 글 */
  why: string
  /** 지난 목표들 (최근 것이 뒤) */
  history: PastGoal[]
}

/**
 * 세션 제목용 파일(~/.claude/goal-pane/제목/<세션 id>.json). 모드가 goal · flag 를 쓰고,
 * 설정 훅이 메시지가 들어올 때 읽어 제목 맨 뒤 대괄호를 바꾼 뒤 flag · lastSuffix 를 고친다
 */
export type TitleState = {
  goal: string
  /** pending: 목표가 바뀌었고 다음 메시지에 「[바뀜]」을 붙인다, shown: 붙였고 그다음에 뗀다, none */
  flag: 'none' | 'pending' | 'shown'
  /** 훅이 마지막으로 제목 뒤에 붙인 글. 제목이 이 글로 끝날 때만 그 부분을 갈아 끼운다 */
  lastSuffix: string
}

/**
 * AI 에이전트가 사용자의 최근 요청을 어떻게 이해했나. 화면에는 title(의도)과 gap(물음)만 보이고,
 * original · reason 은 세션마다 파일(~/.claude/goal-pane/기록/<세션 id>.jsonl)에 따로 쌓인다
 */
export type RequestEntry = {
  /** 적은 때 (ISO 시각) */
  said_at: string
  /** 의도: 사용자의 최근 요청을 어떻게 이해했나, 한 문장 */
  title: string
  /** 사용자에게 물을 것 */
  gap?: string
  /** 근거가 된 사용자의 말 그대로 */
  original: string
  /** 왜 그렇게 이해했나: 어느 말 · 어떤 앞 맥락 때문인지, 짐작한 것 */
  reason: string
}

declare module 'claude-code' {
  interface PluginState {
    'goal-pane': { goal: Shaped<GoalState | null>; requests: Shaped<RequestEntry[]> }
  }
}
