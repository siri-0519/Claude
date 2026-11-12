import { expect, test } from 'claude-code/testing'

const TOOL_FULL = 'mcp__goal-pane__set_goal'

const BAND = {
  plugin: 'goal-pane',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 12,
    bodyColumns: 80,
    scroll: { offset: 0, bodyRows: 11 },
    view: {},
  },
} as const

// 엔진 자리: 모드가 그리지 않으면 이 글자가 남는다
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function engineDraws(on: any) {
  on('ui.render', ($: any, e: any) => {
    const { Text } = $.ui.resolve(e)

    return <Text>engine</Text>
  })
}

test('세션이 시작돼도 옆 패널을 저절로 열지 않는다', async ($, on) => {
  let opened = 0
  on('tool.register', () => ({ value: { tool: TOOL_FULL } }))
  on('command.register', () => ({ value: { command: 'goal-pane' } }))
  on('ui.open', () => {
    opened += 1

    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect(opened).toBe(0)
})

test('적으면 상태 줄과 알림은 쓰지 않는다', async ($, on) => {
  let status = 0
  let toast = 0
  on('ui.status', () => {
    status += 1

    return { value: undefined }
  })
  on('ui.toast', () => {
    toast += 1

    return { value: undefined }
  })
  await $.tool.call({ tool: TOOL_FULL, title: '첫 의도', body: [{ t: '첫 목적' }], original: '첫 말', changed: false })
  await $.tool.call({ tool: TOOL_FULL, title: '둘째 의도', body: [{ t: '둘째 목적' }], original: '둘째 말', changed: true, why: '바뀜' })
  expect(status).toBe(0)
  expect(toast).toBe(0)
})

test('목표가 없으면 띠를 엔진에 넘기고, 적히면 마지막 이해를 SSoT 기록 칸으로 그린다', async ($, on) => {
  engineDraws(on)

  const empty = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await empty.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await empty.unmount()

  await $.tool.call({ tool: TOOL_FULL, title: '첫 의도', body: [{ t: '첫 목적' }], original: '첫 말', changed: false })
  await $.tool.call({
    tool: TOOL_FULL,
    title: '둘째 의도',
    body: [{ t: '물어보고 멈춘다' }, { t: '로그는 git 기록일 것이다', mark: 'guess' }],
    gap: '로그는 무엇인가요?',
    original: '로그 다 읽을 수 있나',
    changed: true,
    why: '사용자가 바꿈',
  })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /둘째 의도/ }))?.text).toContain('둘째 의도')
    expect((await ui.find({ type: 'Text', text: /첫 의도/ }))?.text).toBe(undefined)
    expect((await ui.find({ type: 'Text', text: /물어보고 멈춘다/ }))?.text).toContain('목적')
    expect((await ui.find({ type: 'Text', text: /git 기록일 것이다/ }))?.text).toContain('AI 짐작')
    expect((await ui.find({ type: 'Text', text: /물음/ }))?.text).toContain('로그는 무엇인가요?')
    expect((await ui.find({ type: 'Text', text: /바뀐 까닭/ }))?.text).toContain('사용자가 바꿈')
    expect((await ui.find({ type: 'Text', text: /들은 말/ }))?.text).toContain('지난 이해 1건')
    expect((await ui.find({ type: 'Text', text: /사용자가 말함/ }))?.text).toContain('요청')
    await ui.unmount()
  }
})

test('앞 판 입력(goal · asks)도 받아 띠에 그린다', async ($, on) => {
  engineDraws(on)
  await $.tool.call({ tool: TOOL_FULL, goal: '앞 판 목표', changed: false, asks: ['앞 판 물음'] })

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /앞 판 목표/ }))?.text).toContain('앞 판 목표')
  expect((await ui.find({ type: 'Text', text: /물음/ }))?.text).toContain('앞 판 물음')
  await ui.unmount()
})

test('설문이 띠를 쓰는 동안에는 비켜 준다', async ($, on) => {
  engineDraws(on)
  await $.tool.call({ tool: TOOL_FULL, title: '어떤 의도', body: [], original: '말', changed: false })

  const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await ui.unmount()
})
