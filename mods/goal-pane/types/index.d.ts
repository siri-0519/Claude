/** 지난 목표 하나 */
export type PastGoal = { goal: string; label: string; since: string; why: string }

/**
 * 이 대화의 목표: 요청 하나하나가 결과적으로 무엇을 하기 위함인가. 자주 바뀌지 않는다.
 * 세션 제목 맨 뒤 괄호([짧은 목표])도 이 값으로 만든다
 */
export type GoalState = {
  /** 목표 문장 */
  goal: string
  /** 제목 뒤 괄호에 붙이는 짧은 목표 */
  label: string
  /** 이 목표가 정해진 때 (ISO 시각) */
  since: string
  /** 몇 번째 목표인가. 처음 1 */
  n: number
  /** 바로 앞 목표에서 바뀐 까닭. 처음이면 빈 글 */
  why: string
  /** 지난 목표들 (최근 것이 뒤) */
  history: PastGoal[]
  /**
   * 제목의 「[바뀜]」 단계. pending: 목표가 바뀌었고 다음 메시지에 붙인다,
   * shown: 붙였고 그다음 메시지에 뗀다, none: 붙이지 않는다
   */
  flag: 'none' | 'pending' | 'shown'
  /** 모드가 마지막으로 제목 뒤에 붙인 글. 제목이 이 글로 끝날 때만 그 부분을 갈아 끼운다 */
  lastSuffix: string
}

/**
 * 요청 하나를 AI 에이전트가 이해해 적은 것.
 * 칸은 SSoT 기록 확인함의 기록 한 건(kind · source · said_at · title · gap · original)을 따른다. 목적(body)은 의도와 겹쳐 뺐다(2026-11-12 사용자)
 */
export type RequestEntry = {
  /** 기록 종류. 이 모드가 적는 것은 늘 「요청」 */
  kind: '요청'
  /** 누구의 말을 이해한 것인가. 이 모드는 늘 「사용자」 */
  source: '사용자'
  /** 적은 때 (ISO 시각) */
  said_at: string
  /** 의도: 이번 요청으로 사용자가 무엇을 원하나, 한 문장 */
  title: string
  /** 사용자에게 물을 것 */
  gap?: { prompt: string }
  /** 근거가 된 사용자의 말 그대로 */
  original: string
}

declare module 'claude-code' {
  interface PluginState {
    'goal-pane': { goal: Shaped<GoalState | null>; requests: Shaped<RequestEntry[]> }
  }
}
