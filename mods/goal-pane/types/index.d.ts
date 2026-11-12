/** 문장 하나. AI 에이전트가 고르거나 짐작한 문장은 mark 가 guess (SSoT 기록 확인함과 같은 표시) */
export type Sentence = { t: string; mark?: 'guess' }

/**
 * AI 에이전트가 사용자의 말을 한 번 이해해 적은 것.
 * 칸은 SSoT 기록 확인함의 기록 한 건(kind · source · said_at · title · body · gap · original)을 따른다
 */
export type GoalEntry = {
  /** 기록 종류. 이 모드가 적는 것은 늘 「요청」 */
  kind: '요청'
  /** 누구의 말을 이해한 것인가. 이 모드는 늘 「사용자」 */
  source: '사용자'
  /** 적은 때 (ISO 시각) */
  said_at: string
  /** 의도: 사용자가 무엇을 원하나, 한 문장 */
  title: string
  /** 목적: 그래서 무슨 작업을 어디까지 하나, 문장마다 하나 */
  body: Sentence[]
  /** 사용자에게 물을 것 */
  gap?: { prompt: string }
  /** 근거가 된 사용자의 말 그대로 */
  original: string
  /** 바로 앞 이해에서 달라졌는가 */
  isChange: boolean
  /** 달라졌다면 무엇이 왜 */
  why: string
}

declare module 'claude-code' {
  interface PluginState {
    'goal-pane': { goals: Shaped<GoalEntry[]> }
  }
}
