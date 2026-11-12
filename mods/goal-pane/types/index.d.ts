/** AI 에이전트가 한 번 적은 「지금 이해한 목표」 */
export type GoalEntry = {
  /** 적은 때 (ISO 시각) */
  at: string
  /** 지금 이해한 사용자의 목표, 한두 문장 */
  goal: string
  /** 바로 앞 목표에서 달라졌는가 */
  isChange: boolean
  /** 달라졌다면 무엇이 왜 */
  why: string
  /** 확인하지 못해 사용자에게 물어야 할 것 */
  asks: string[]
}

declare module 'claude-code' {
  interface PluginState {
    'goal-pane': { goals: Shaped<GoalEntry[]> }
  }
}
