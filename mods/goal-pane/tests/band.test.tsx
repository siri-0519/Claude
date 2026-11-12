import { expect, test } from 'claude-code/testing'

const TOOL_FULL = 'mcp__goal-pane__set_goal'
const DIR = 'C:/Users/T/.claude/goal-pane'

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

const PANE = {
  plugin: 'goal-pane',
  component: 'Pane',
  requestId: 'goal',
  props: { title: '이해한 의도', isFocused: false, bodyColumns: 40, placement: 'dock', scroll: { offset: 0, bodyRows: 20 }, view: {} },
} as const

// 엔진 자리: 모드가 그리지 않으면 이 글자가 남는다
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function engineDraws(on: any) {
  on('ui.render', ($: any, e: any) => {
    const { Text } = $.ui.resolve(e)

    return <Text>engine</Text>
  })
}

// 파일 자리: 쓴 것을 메모리에 모은다
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function memoryFiles(on: any, home: string | undefined = 'C:/Users/T') {
  const files = new Map<string, string>()
  on('env.get', (_: unknown, e: { name: string }) => ({ value: e.name === 'USERPROFILE' ? home : undefined }))
  on('session.id', () => ({ value: 's1' }))
  // 엔진은 경로를 운영체제 모양(윈도우는 \)으로 넘기므로 / 로 맞춰 둔다
  const key = (p: string) => p.split(String.fromCharCode(92)).join('/')
  on('fs.read', (_: unknown, e: { path: string }) => {
    const v = files.get(key(e.path))
    if (v === undefined) throw new Error('ENOENT')

    return { value: v }
  })
  on('fs.write', (_: unknown, e: { path: string; text: string }) => {
    files.set(key(e.path), e.text)

    return { value: undefined }
  })

  return files
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

test('띠에는 의도 · 짐작 · 물음만 보이고, 목표 · 들은 말 · 까닭은 보이지 않는다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  const empty = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await empty.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await empty.unmount()

  await $.tool.call({ tool: TOOL_FULL, title: '첫 의도', original: '첫 말', reason: '첫 까닭', goal: 'AI가 의도를 정확히' })
  await $.tool.call({ tool: TOOL_FULL, title: '둘째 의도', guess: ['로그는 git 기록일 것이다'], gap: '로그는 무엇인가요?', original: '로그 다 읽을 수 있나', reason: '로그를 git 기록으로 짐작함' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /둘째 의도/ }))?.text).toContain('의도')
    expect((await ui.find({ type: 'Text', text: /물음/ }))?.text).toContain('로그는 무엇인가요?')
    expect((await ui.find({ type: 'Text', text: /git 기록일 것이다/ }))?.text).toContain('AI 짐작')
    expect((await ui.find({ type: 'Text', text: /첫 의도/ }))?.text).toBe(undefined)
    expect((await ui.find({ type: 'Text', text: /AI가 의도를 정확히/ }))?.text).toBe(undefined)
    expect((await ui.find({ type: 'Text', text: /로그 다 읽을 수 있나/ }))?.text).toBe(undefined)
    expect((await ui.find({ type: 'Text', text: /짐작함/ }))?.text).toBe(undefined)
    await ui.unmount()
  }

  // 목표는 세션 제목에만 둔다: 패널에도 없다
  const pane = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await pane.find({ type: 'Text', text: /둘째 의도/ }))?.text).toContain('의도')
  expect((await pane.find({ type: 'Text', text: /AI가 의도를 정확히/ }))?.text).toBe(undefined)
  await pane.unmount()
})

test('왜 그렇게 이해했는지는 세션 파일에 한 줄씩 따로 쌓는다', async ($, on) => {
  const files = memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '의도1', original: '말1', reason: '까닭1', goal: '목표1' })
  await $.tool.call({ tool: TOOL_FULL, title: '의도2', gap: '물음2', original: '말2', reason: '까닭2' })
  await $.tool.call({ tool: TOOL_FULL, title: '의도3', original: '말3', reason: '까닭3', goal: '목표2', changed: true, why: '사용자가 바꿈' })

  const lines = (files.get(`${DIR}/기록/s1.jsonl`) ?? '').trim().split('\n').map(l => JSON.parse(l))
  expect(lines.length).toBe(3)
  expect(lines[0].kind).toBe('목표 정함')
  expect(lines[0].reason).toBe('까닭1')
  expect(lines[1].kind).toBe('의도')
  expect(lines[1].original).toBe('말2')
  expect(lines[1].gap).toBe('물음2')
  expect(lines[2].kind).toBe('목표 바뀜')
  expect(lines[2].previous).toBe('목표1')
  expect(lines[2].why).toBe('사용자가 바꿈')
})

test('제목용 파일: 목표를 정하면 적고, 바뀌면 [바뀜] 단계로 두되 훅이 붙인 글은 지킨다', async ($, on) => {
  const files = memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '의도', original: '말', reason: '까닭', goal: '[처음] 목표' })
  expect(JSON.parse(files.get(`${DIR}/제목/s1.json`) ?? '{}')).toEqual({ goal: '처음 목표', flag: 'none', lastSuffix: '' })

  // 설정 훅이 제목을 바꾼 뒤를 흉내 낸다
  files.set(`${DIR}/제목/s1.json`, JSON.stringify({ goal: '처음 목표', flag: 'none', lastSuffix: ' [처음 목표]' }))
  // changed 없는 다른 목표는 무시
  await $.tool.call({ tool: TOOL_FULL, title: '의도', original: '말', reason: '까닭', goal: '슬쩍' })
  expect(JSON.parse(files.get(`${DIR}/제목/s1.json`) ?? '{}').goal).toBe('처음 목표')

  await $.tool.call({ tool: TOOL_FULL, title: '의도', original: '말', reason: '까닭', goal: '새 목표', changed: true, why: '바뀜' })
  expect(JSON.parse(files.get(`${DIR}/제목/s1.json`) ?? '{}')).toEqual({ goal: '새 목표', flag: 'pending', lastSuffix: ' [처음 목표]' })
})

test('저장이 안 돼도 띠와 도구는 그대로 돈다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on, undefined)
  const r = await $.tool.call({ tool: TOOL_FULL, title: '의도만', original: '말', reason: '까닭', goal: '목표' })
  expect(JSON.stringify(r)).toContain('적었습니다')
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /의도만/ }))?.text).toContain('의도만')
  await ui.unmount()
})

test('짐작과 물음이 없으면 그 줄은 생략된다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '깔끔한 의도', original: '말', reason: '까닭' })
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /깔끔한 의도/ }))?.text).toContain('의도')
  expect((await ui.find({ type: 'Text', text: /짐작/ }))?.text).toBe(undefined)
  expect((await ui.find({ type: 'Text', text: /물음/ }))?.text).toBe(undefined)
  await ui.unmount()
})

test('설문이 띠를 쓰는 동안에는 비켜 준다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '어떤 의도', original: '말', reason: '까닭', goal: '목표' })

  const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await ui.unmount()
})
