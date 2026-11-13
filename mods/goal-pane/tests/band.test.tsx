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

test('입력창 위 영역에는 의도 · 가정 · 확인 질문만 보이고, 목표 · 들은 말 · 까닭은 보이지 않는다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  const empty = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await empty.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await empty.unmount()

  await $.tool.call({ tool: TOOL_FULL, title: '첫 의도', original: '첫 말', reason: '첫 까닭', goal: 'AI가 의도를 정확히' })
  await $.tool.call({ tool: TOOL_FULL, title: '둘째 의도', assumptions: ['로그는 git 기록일 것이다'], question: '로그는 무엇인가요?', original: '로그 다 읽을 수 있나', reason: '로그를 git 기록으로 짐작함' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /둘째 의도/ }))?.text).toContain('의도')
    expect((await ui.find({ type: 'Text', text: /확인 질문/ }))?.text).toContain('로그는 무엇인가요?')
    expect((await ui.find({ type: 'Text', text: /git 기록일 것이다/ }))?.text).toContain('가정')
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
  await $.tool.call({ tool: TOOL_FULL, title: '의도2', question: '질문2', original: '말2', reason: '까닭2' })
  await $.tool.call({ tool: TOOL_FULL, title: '의도3', original: '말3', reason: '까닭3', goal: '목표2', changed: true, why: '사용자가 바꿈' })

  const lines = (files.get(`${DIR}/기록/s1.jsonl`) ?? '').trim().split('\n').map(l => JSON.parse(l))
  expect(lines.length).toBe(3)
  expect(lines[0].kind).toBe('목표 정함')
  expect(lines[0].reason).toBe('까닭1')
  expect(lines[1].kind).toBe('의도')
  expect(lines[1].original).toBe('말2')
  expect(lines[1].question).toBe('질문2')
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

test('저장이 안 돼도 입력창 위 영역과 도구는 그대로 돈다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on, undefined)
  const r = await $.tool.call({ tool: TOOL_FULL, title: '의도만', original: '말', reason: '까닭', goal: '목표' })
  expect(JSON.stringify(r)).toContain('적었습니다')
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /의도만/ }))?.text).toContain('의도만')
  await ui.unmount()
})

test('가정과 확인 질문이 없으면 그 줄은 생략된다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '깔끔한 의도', original: '말', reason: '까닭' })
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /깔끔한 의도/ }))?.text).toContain('의도')
  expect((await ui.find({ type: 'Text', text: /가정/ }))?.text).toBe(undefined)
  expect((await ui.find({ type: 'Text', text: /확인 질문/ }))?.text).toBe(undefined)
  await ui.unmount()
})

test('앞 버전 칸 이름(guess · gap)으로 와도 가정 · 확인 질문으로 그린다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '옛 칸 의도', guess: ['옛 짐작'], gap: '옛 물음', original: '말', reason: '까닭' })
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /옛 짐작/ }))?.text).toContain('가정')
  expect((await ui.find({ type: 'Text', text: /확인 질문/ }))?.text).toContain('옛 물음')
  await ui.unmount()
})

test('설문이 입력창 위 영역을 쓰는 동안에는 비켜 준다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '어떤 의도', original: '말', reason: '까닭', goal: '목표' })

  const ui = await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
  await ui.unmount()
})

test('가정마다 ✗가 있고, 누르면 틀림(빨간 취소선)으로 바뀌고 다시 누르면 풀린다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '두 가정 의도', assumptions: ['첫 가정', '둘째 가정'], original: '말', reason: '까닭' })

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(4)
  expect((await ui.find({ type: 'Text', text: /다음 메시지에 함께/ }))?.text).toBe(undefined)

  await ui.press({ key: 'wrong-1' })
  const struck = await ui.find({ type: 'Text', text: /^둘째 가정$/ })
  expect(struck?.props.strikethrough).toBe(true)
  expect(struck?.props.color).toBe('error')
  expect((await ui.find({ type: 'Text', text: /^첫 가정$/ }))?.props.strikethrough).toBe(false)
  expect((await ui.find({ type: 'Text', text: /틀림 1개/ }))?.text).toContain('다음 메시지')

  await ui.press({ key: 'wrong-1' })
  expect((await ui.find({ type: 'Text', text: /^둘째 가정$/ }))?.props.strikethrough).toBe(false)
  expect((await ui.find({ type: 'Text', text: /다음 메시지에 함께/ }))?.text).toBe(undefined)
  await ui.unmount()
})

test('표시한 가정은 다음 메시지에 함께 실려 가고, 기록에 남고, 표시는 지워진다', async ($, on) => {
  engineDraws(on)
  const files = memoryFiles(on)
  let seen: readonly string[] = []
  on('prompt.submit', (_: unknown, e: { text: string; context?: readonly string[] }) => {
    seen = e.context ?? []

    return { text: e.text, context: e.context }
  })
  await $.tool.call({ tool: TOOL_FULL, title: '세 가정 의도', assumptions: ['가정A', '가정B', '가정C'], original: '말', reason: '까닭' })

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  await ui.press({ key: 'wrong-0' })
  await ui.press({ key: 'wrong-2' })

  await $.prompt.submit({ text: '다음 말', wait: false, origin: { kind: 'composer' } })
  const note = seen.find(c => c.includes('틀렸다고 표시한'))
  expect(note).toContain('가정A')
  expect(note).toContain('가정C')
  expect(note).not.toContain('가정B')
  expect(seen.some(c => c.includes('mcp__goal-pane__set_goal'))).toBe(true)

  const lines = (files.get(`${DIR}/기록/s1.jsonl`) ?? '').trim().split('\n').map(l => JSON.parse(l))
  expect(lines[lines.length - 1].kind).toBe('가정 표시')
  expect(lines[lines.length - 1].wrong).toEqual(['가정A', '가정C'])

  expect((await ui.find({ type: 'Text', text: /다음 메시지에 함께/ }))?.text).toBe(undefined)
  await $.prompt.submit({ text: '그다음 말', wait: false, origin: { kind: 'composer' } })
  expect(seen.some(c => c.includes('틀렸다고 표시한'))).toBe(false)
  await ui.unmount()
})

test('새 의도가 오면 앞 의도에 남은 표시는 따라오지 않는다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  let seen: readonly string[] = []
  on('prompt.submit', (_: unknown, e: { text: string; context?: readonly string[] }) => {
    seen = e.context ?? []

    return { text: e.text, context: e.context }
  })
  await $.tool.call({ tool: TOOL_FULL, title: '앞 의도', assumptions: ['앞 가정'], original: '말', reason: '까닭' })
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  await ui.press({ key: 'wrong-0' })
  await ui.unmount()

  await $.tool.call({ tool: TOOL_FULL, title: '새 의도', assumptions: ['새 가정'], original: '말', reason: '까닭' })
  const ui2 = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui2.find({ type: 'Text', text: /^새 가정$/ }))?.props.strikethrough).toBe(false)
  expect((await ui2.find({ type: 'Text', text: /다음 메시지에 함께/ }))?.text).toBe(undefined)
  await ui2.unmount()
  await $.prompt.submit({ text: '말', wait: false, origin: { kind: 'composer' } })
  expect(seen.some(c => c.includes('틀렸다고 표시한'))).toBe(false)
})

test('앱을 다시 켜 세션 상태가 비어도, 파일에 남은 앞 목표와 다르면 [바뀜] 단계로 둔다', async ($, on) => {
  const files = memoryFiles(on)
  files.set(`${DIR}/제목/s1.json`, JSON.stringify({ goal: '앞 목표', flag: 'none', lastSuffix: ' [앞 목표]' }))
  await $.tool.call({ tool: TOOL_FULL, title: '의도', original: '말', reason: '까닭', goal: '새 목표', changed: true, why: '바뀜' })
  expect(JSON.parse(files.get(`${DIR}/제목/s1.json`) ?? '{}')).toEqual({ goal: '새 목표', flag: 'pending', lastSuffix: ' [앞 목표]' })

  // 같은 목표를 다시 적으면 단계는 그대로
  files.set(`${DIR}/제목/s1.json`, JSON.stringify({ goal: '새 목표', flag: 'none', lastSuffix: ' [새 목표]' }))
  await $.tool.call({ tool: TOOL_FULL, title: '의도', original: '말', reason: '까닭', goal: '새 목표', changed: true, why: '같음' })
  expect(JSON.parse(files.get(`${DIR}/제목/s1.json`) ?? '{}').flag).toBe('none')
})

test('가정 줄 끝에 「확인 필요」를 붙이지 않고, 틀렸다고 누른 뒤에만 「틀림」을 적는다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '꼬리표 의도', assumptions: ['꼬리표 가정'], original: '말', reason: '까닭' })
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /확인 필요/ }))?.text).toBe(undefined)
  expect((await ui.find({ type: 'Text', text: /틀림/ }))?.text).toBe(undefined)
  await ui.press({ key: 'wrong-0' })
  expect((await ui.find({ type: 'Text', text: /틀림/ }))?.text).toContain('틀림')
  await ui.unmount()
})

test('✓를 누르면 초록 「확정」이 되고, ✗와 둘 중 하나만 서며, 다음 메시지에 확정 · 틀림이 따로 실려 간다', async ($, on) => {
  engineDraws(on)
  const files = memoryFiles(on)
  let seen: readonly string[] = []
  on('prompt.submit', (_: unknown, e: { text: string; context?: readonly string[] }) => {
    seen = e.context ?? []

    return { text: e.text, context: e.context }
  })
  await $.tool.call({ tool: TOOL_FULL, title: '확정 의도', assumptions: ['가정P', '가정Q'], original: '말', reason: '까닭' })
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })

  await ui.press({ key: 'right-0' })
  const ok = await ui.find({ type: 'Text', text: /^가정P$/ })
  expect(ok?.props.color).toBe('success')
  expect(ok?.props.strikethrough).toBe(false)
  expect((await ui.find({ type: 'Text', text: /확정$/ }))?.text).toContain('확정')

  // 같은 가정에 ✗를 누르면 ✓가 풀리고 틀림이 된다
  await ui.press({ key: 'wrong-0' })
  expect((await ui.find({ type: 'Text', text: /^가정P$/ }))?.props.color).toBe('error')
  await ui.press({ key: 'right-0' })
  await ui.press({ key: 'wrong-1' })
  expect((await ui.find({ type: 'Text', text: /다음 메시지에 함께/ }))?.text).toContain('확정 1개 · 틀림 1개')

  await $.prompt.submit({ text: '다음 말', wait: false, origin: { kind: 'composer' } })
  const note = seen.find(c => c.includes('가정을 표시했다')) ?? ''
  expect(note).toContain('맞다고 확정한 가정: 「가정P」')
  expect(note).toContain('틀렸다고 표시한 가정: 「가정Q」')
  const lines = (files.get(`${DIR}/기록/s1.jsonl`) ?? '').trim().split('\n').map(l => JSON.parse(l))
  expect(lines[lines.length - 1].right).toEqual(['가정P'])
  expect(lines[lines.length - 1].wrong).toEqual(['가정Q'])
  expect((await ui.find({ type: 'Text', text: /다음 메시지에 함께/ }))?.text).toBe(undefined)
  await ui.unmount()
})

test('fit 이 부합 · 곁가지면 goal 이 와도 목표는 그대로이고, 확장 · 변경이면 바뀌어 기록에 판단이 남는다', async ($, on) => {
  const files = memoryFiles(on)
  const title = () => JSON.parse(files.get(`${DIR}/제목/s1.json`) ?? '{}')
  await $.tool.call({ tool: TOOL_FULL, title: '의도1', original: '말', reason: '까닭', fit: '처음', goal: '목표A' })
  await $.tool.call({ tool: TOOL_FULL, title: '의도2', original: '말', reason: '까닭', fit: '부합', goal: '슬쩍B' })
  await $.tool.call({ tool: TOOL_FULL, title: '의도3', original: '말', reason: '까닭', fit: '곁가지', goal: '슬쩍C' })
  expect(title().goal).toBe('목표A')

  await $.tool.call({ tool: TOOL_FULL, title: '의도4', original: '말', reason: '까닭', fit: '확장', goal: '목표A+', why: '넓어짐' })
  expect(title()).toEqual({ goal: '목표A+', flag: 'pending', lastSuffix: '' })
  await $.tool.call({ tool: TOOL_FULL, title: '의도5', original: '말', reason: '까닭', fit: '변경', goal: '목표Z', why: '바뀜' })
  expect(title().goal).toBe('목표Z')

  const lines = (files.get(`${DIR}/기록/s1.jsonl`) ?? '').trim().split('\n').map(l => JSON.parse(l))
  expect(lines.map(l => l.fit)).toEqual(['처음', '부합', '곁가지', '확장', '변경'])
  expect(lines.map(l => l.kind)).toEqual(['목표 정함', '의도', '의도', '목표 바뀜', '목표 바뀜'])
  expect(lines[3].previous).toBe('목표A')
  expect(lines[4].why).toBe('바뀜')
})

test('확장 · 변경으로 판단했는데 새 목표가 없거나 같으면 다시 부르게 하고, 아무것도 적지 않는다', async ($, on) => {
  const files = memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '의도1', original: '말', reason: '까닭', fit: '처음', goal: '목표A' })
  const none = await $.tool.call({ tool: TOOL_FULL, title: '의도2', original: '말', reason: '까닭', fit: '확장' })
  expect(JSON.stringify(none)).toContain('다시 불러')
  const same = await $.tool.call({ tool: TOOL_FULL, title: '의도3', original: '말', reason: '까닭', fit: '변경', goal: '목표A' })
  expect(JSON.stringify(same)).toContain('목표A')
  expect((files.get(`${DIR}/기록/s1.jsonl`) ?? '').trim().split('\n')).toHaveLength(1)
})

test('곁가지로 본 요청은 입력창 위 영역에 곁가지 줄이 보이고, 부합은 줄이 생기지 않는다', async ($, on) => {
  engineDraws(on)
  memoryFiles(on)
  await $.tool.call({ tool: TOOL_FULL, title: '본 일', original: '말', reason: '까닭', fit: '처음', goal: '목표A' })
  await $.tool.call({ tool: TOOL_FULL, title: '맞는 일', original: '말', reason: '까닭', fit: '부합' })
  const fits = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await fits.find({ type: 'Text', text: /곁가지/ }))?.text).toBe(undefined)
  await fits.unmount()

  await $.tool.call({ tool: TOOL_FULL, title: '다른 일', original: '말', reason: '까닭', fit: '곁가지' })
  const side = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await side.find({ type: 'Text', text: /곁가지/ }))?.text).toContain('목표는 그대로')
  await side.unmount()
})

test('메시지마다 붙는 지침에 지금 목표가 실리고, 목표가 없으면 처음 정하라고 한다', async ($, on) => {
  memoryFiles(on)
  let seen: readonly string[] = []
  on('prompt.submit', (_: unknown, e: { text: string; context?: readonly string[] }) => {
    seen = e.context ?? []

    return { text: e.text, context: e.context }
  })
  await $.prompt.submit({ text: '첫 말', wait: false, origin: { kind: 'composer' } })
  const first = seen.find(c => c.includes(TOOL_FULL)) ?? ''
  expect(first).toContain('fit = 처음')
  expect(first).not.toContain('지금 목표')

  await $.tool.call({ tool: TOOL_FULL, title: '의도', original: '말', reason: '까닭', fit: '처음', goal: '목표A' })
  await $.prompt.submit({ text: '둘째 말', wait: false, origin: { kind: 'composer' } })
  const second = seen.find(c => c.includes(TOOL_FULL)) ?? ''
  expect(second).toContain('지금 목표: 「목표A」')
  expect(second).toContain('곁가지')
})
