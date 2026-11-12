import { expect, test } from 'claude-code/testing'

const TOOL_FULL = 'mcp__goal-pane__set_goal'

const BAND = {
  plugin: 'goal-pane',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 14,
    bodyColumns: 90,
    scroll: { offset: 0, bodyRows: 13 },
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

// 설정 훅 자리: 아무것도 바꾸지 않는다
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function noSettingsHooks(on: any) {
  on('classic.UserPromptSubmit', () => ({}))
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function submit($: any, title: string): Promise<string | undefined> {
  const r = await $.classic.UserPromptSubmit({ prompt: '아무 말', session_title: title })

  return r.sessionTitle
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

test('적어도 상태 줄과 알림은 쓰지 않는다', async ($, on) => {
  let calls = 0
  on('ui.status', () => {
    calls += 1

    return { value: undefined }
  })
  on('ui.toast', () => {
    calls += 1

    return { value: undefined }
  })
  await $.tool.call({ tool: TOOL_FULL, title: '의도1', body: [{ t: '목적1' }], original: '말1', goal: '목표1', label: '짧은1' })
  await $.tool.call({ tool: TOOL_FULL, title: '의도2', body: [], original: '말2', goal: '목표2', label: '짧은2', changed: true, why: '바뀜' })
  expect(calls).toBe(0)
})

test('띠: 목표는 위에 굵게, 이번 요청의 의도 · 목적 · 짐작 · 물음은 그 아래', async ($, on) => {
  engineDraws(on)
  const empty = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await empty.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await empty.unmount()

  await $.tool.call({ tool: TOOL_FULL, title: '첫 의도', body: [{ t: '첫 목적' }], original: '첫 말', goal: '모드를 다듬는다', label: '모드 다듬기' })
  await $.tool.call({
    tool: TOOL_FULL,
    title: '둘째 의도',
    body: [{ t: '물어보고 멈춘다' }, { t: '로그는 git 기록일 것이다', mark: 'guess' }],
    gap: '로그는 무엇인가요?',
    original: '로그 다 읽을 수 있나',
  })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /모드를 다듬는다/ }))?.text).toContain('목표')
    expect((await ui.find({ type: 'Text', text: /목표 바뀜/ }))?.text).toBe(undefined)
    expect((await ui.find({ type: 'Text', text: /둘째 의도/ }))?.text).toContain('의도')
    expect((await ui.find({ type: 'Text', text: /첫 의도/ }))?.text).toBe(undefined)
    expect((await ui.find({ type: 'Text', text: /물어보고 멈춘다/ }))?.text).toContain('목적')
    expect((await ui.find({ type: 'Text', text: /git 기록일 것이다/ }))?.text).toContain('AI 짐작')
    expect((await ui.find({ type: 'Text', text: /물음/ }))?.text).toContain('로그는 무엇인가요?')
    expect((await ui.find({ type: 'Text', text: /들은 말/ }))?.text).toContain('지난 요청 1건')
    await ui.unmount()
  }
})

test('목표는 changed 일 때만 바뀌고, 바뀌면 띠에 이전 목표와 까닭이 붙는다', async ($, on) => {
  engineDraws(on)
  await $.tool.call({ tool: TOOL_FULL, title: '의도1', body: [], original: '말', goal: '처음 목표', label: '처음' })
  // changed 없이 다른 목표를 적으면 무시한다: 요청마다 목표가 흔들리지 않게
  await $.tool.call({ tool: TOOL_FULL, title: '의도2', body: [], original: '말', goal: '슬쩍 바꾼 목표', label: '슬쩍' })
  let ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /처음 목표/ }))?.text).toContain('처음 목표')
  expect((await ui.find({ type: 'Text', text: /슬쩍 바꾼 목표/ }))?.text).toBe(undefined)
  await ui.unmount()

  await $.tool.call({ tool: TOOL_FULL, title: '의도3', body: [], original: '말', goal: '새 목표', label: '새', changed: true, why: '사용자가 방향을 바꿈' })
  ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /새 목표/ }))?.text).toContain('새 목표')
  const changed = (await ui.find({ type: 'Text', text: /목표 바뀜/ }))?.text ?? ''
  expect(changed).toContain('처음 목표')
  expect(changed).toContain('사용자가 방향을 바꿈')
  await ui.unmount()
})

test('제목: 앞은 그대로, 맨 뒤 대괄호만 모드가 바꾼다. 바뀐 뒤 첫 메시지에만 [바뀜]', async ($, on) => {
  noSettingsHooks(on)
  engineDraws(on)
  // 목표가 없으면 제목을 건드리지 않는다
  expect(await submit($, '모드 설치 및 설정')).toBe(undefined)

  await $.tool.call({ tool: TOOL_FULL, title: '의도', body: [], original: '말', goal: '목표1', label: '의도 이해 실시간 표시' })
  expect(await submit($, '모드 설치 및 설정')).toBe('모드 설치 및 설정 [의도 이해 실시간 표시]')
  // 이미 맞으면 다시 쓰지 않는다
  expect(await submit($, '모드 설치 및 설정 [의도 이해 실시간 표시]')).toBe(undefined)

  await $.tool.call({ tool: TOOL_FULL, title: '의도', body: [], original: '말', goal: '목표2', label: '제목 규칙 정하기', changed: true, why: '바뀜' })
  // 바뀐 직후 띠에는 바뀐 사실이 보인다
  let ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /목표 바뀜/ }))?.text).toContain('목표1')
  await ui.unmount()

  expect(await submit($, '모드 설치 및 설정 [의도 이해 실시간 표시]')).toBe('모드 설치 및 설정 [바뀜] [제목 규칙 정하기]')
  ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /목표 바뀜/ }))?.text).toContain('목표1')
  await ui.unmount()

  expect(await submit($, '모드 설치 및 설정 [바뀜] [제목 규칙 정하기]')).toBe('모드 설치 및 설정 [제목 규칙 정하기]')
  ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /목표 바뀜/ }))?.text).toBe(undefined)
  await ui.unmount()

  // 사용자가 앞을 고치면 앞은 그대로 두고 뒤만 맞춘다
  expect(await submit($, '새 이름 [제목 규칙 정하기]')).toBe(undefined)
  // 사용자가 대괄호를 직접 고치면 그것도 사용자 것으로 두고 모드 것을 뒤에 붙인다
  expect(await submit($, '새 이름 [내가 고침]')).toBe('새 이름 [내가 고침] [제목 규칙 정하기]')
})

test('짧은 목표에 대괄호가 들어오면 빼서 제목 규칙이 깨지지 않게 한다', async ($, on) => {
  noSettingsHooks(on)
  await $.tool.call({ tool: TOOL_FULL, title: '의도', body: [], original: '말', goal: '목표', label: '[괄호] 목표' })
  expect(await submit($, '제목')).toBe('제목 [괄호 목표]')
})

test('설문이 띠를 쓰는 동안에는 비켜 준다', async ($, on) => {
  engineDraws(on)
  await $.tool.call({ tool: TOOL_FULL, title: '어떤 의도', body: [], original: '말', goal: '목표', label: '목표' })

  const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await ui.unmount()
})
