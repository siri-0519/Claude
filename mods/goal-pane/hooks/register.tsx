import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { GoalState, RequestEntry, Sentence } from '../types'

const PANE = 'goal'
const TITLE = '목표와 이해한 의도'
const TOOL = 'set_goal'
const TOOL_FULL = 'mcp__goal-pane__set_goal'

// 항목이 바뀌면 shape 꼬리표를 바꾼다: 앞 버전이 남긴 값을 받지 않게 한다
const goalAtom = atom({ plugin: 'goal-pane', key: 'goal' } as const, null as GoalState | null, { shape: 'goal-1' })
const requests = atom({ plugin: 'goal-pane', key: 'requests' } as const, [] as RequestEntry[], { shape: 'req-1' })

// 모델이 읽는 지침: 무엇을 하라기보다 이 표시가 무엇을 위한 것인지를 먼저 말한다
const RULE = [
  '이 세션에는 사용자가 보는 띠가 입력창 바로 위에 있고, 세션 제목 맨 뒤 대괄호에도 목표가 붙는다.',
  '이것은 AI 에이전트가 사용자를 어떻게 이해하고 있는지 늘 보여 주어, 이해가 어긋나거나 사용자의 뜻이 바뀌었을 때 사용자가 바로 알아차리고 고칠 수 있게 하려는 것이다.',
  '목표와 의도는 다르다. 목표는 사용자의 요청 하나하나가 결과적으로 무엇을 하기 위함인가이고, 자주 바뀌지 않는다. 의도는 이번 요청 하나로 사용자가 무엇을 원하는가이고, 메시지마다 다르다.',
  `사용자의 새 메시지를 받으면, 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 를 한 번 불러 이번 요청을 적는다: title(의도 한 문장), body(목적: 이번 답에서 무엇을 어디까지 하고 무엇은 하지 않는지, 문장마다 하나. 사용자가 정하지 않았는데 고르거나 짐작한 문장은 mark "guess"), gap(사용자에게 물을 것), original(근거가 된 사용자의 말 그대로).`,
  '목표(goal)와 짧은 목표(label, 20자 안팎)는 처음 한 번, 그리고 목표 자체가 바뀌었을 때만 적는다. 바뀌었으면 changed 를 true 로 하고 무엇이 왜 바뀌었는지(사용자의 어느 말 때문인지) why 에 적는다. 요청마다 의도가 달라지는 것은 목표가 바뀐 것이 아니다.',
  '사용자의 말을 부풀리지 않는다: 「할 수도 있다」를 「한다」로, 「그중 하나」를 「전부」로 바꾸지 않는다. gap 에 물음이 있으면 답을 받기 전에는 그 짐작대로 진행하지 않는다.',
  '세션 제목은 대괄호 앞은 사용자가, 맨 뒤 대괄호는 이 모드가 바꾼다. AI 에이전트는 제목을 직접 바꾸지 않는다.',
].join('\n')

// 메시지마다 붙이는 짧은 지침
const NUDGE = `목표 · 의도 띠: 이 메시지에 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 로 이번 요청을 적는다. title = 의도(이번 요청으로 무엇을 원하나, 한 문장), body = 목적(무슨 작업을 어디까지 하고 무엇은 안 하나, 문장마다 하나, 짐작이나 직접 고른 것은 mark "guess"), gap = 사용자에게 물을 것(있으면 답 전에는 그 짐작대로 진행하지 않는다), original = 근거가 된 사용자의 말 그대로. goal(목표: 요청들이 결과적으로 무엇을 하기 위함인가)과 label(짧은 목표, 20자 안팎)은 처음과 목표 자체가 바뀔 때만 적고, 바뀌면 changed true · why 에 까닭. 사용자의 말을 부풀리지 않는다. 답의 맨 위에 이것을 따로 쓰지 않고, 세션 제목은 직접 바꾸지 않는다.`

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : ''
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.map(str).filter(s => s.length > 0).slice(0, 8) : []
}

// body 는 문장 목록. 문자열만 온 경우도 받아 준다
function sentences(v: unknown): Sentence[] {
  if (typeof v === 'string') return v.trim() ? [{ t: v.trim() }] : []
  if (!Array.isArray(v)) return []
  const out: Sentence[] = []
  for (const s of v.slice(0, 8)) {
    if (typeof s === 'string' && s.trim()) out.push({ t: s.trim() })
    else if (s && typeof s === 'object') {
      const t = str((s as Record<string, unknown>).t)
      if (t) out.push((s as Record<string, unknown>).mark === 'guess' ? { t, mark: 'guess' } : { t })
    }
  }

  return out
}

// 짧은 목표가 없으면 목표 문장 앞부분으로 만든다. 대괄호는 제목 규칙을 깨므로 뺀다
function makeLabel(label: string, goal: string): string {
  const base = (label || goal).replace(/[[\]]/g, '').trim()

  return base.length > 24 ? base.slice(0, 24) + '…' : base
}

// 도구 입력에서 이번 요청을 SSoT 기록 한 건 형태로 옮긴다
function toRequest(input: Record<string, unknown>, at: string): RequestEntry | null {
  const title = str(input.title)
  if (!title) return null
  const gapText = str(input.gap) || strList(input.asks).join(' / ')

  return {
    kind: '요청',
    source: '사용자',
    said_at: at,
    title,
    body: sentences(input.body),
    ...(gapText ? { gap: { prompt: gapText } } : {}),
    original: str(input.original),
  }
}

// 목표를 처음 정하거나, 바뀌었을 때만 새 값을 만든다. 그 밖에는 null (그대로 둔다)
function nextGoal(old: GoalState | null, input: Record<string, unknown>, at: string): GoalState | null {
  const goal = str(input.goal)
  if (!goal) return null
  const label = makeLabel(str(input.label), goal)
  if (!old) return { goal, label, since: at, n: 1, why: '', history: [], flag: 'none', lastSuffix: '' }
  if (input.changed !== true || goal === old.goal) return null

  return {
    ...old,
    goal,
    label,
    since: at,
    n: old.n + 1,
    why: str(input.why),
    history: [...old.history, { goal: old.goal, label: old.label, since: old.since, why: old.why }].slice(-20),
    flag: 'pending',
  }
}

// 제목 맨 뒤에 모드가 붙이는 글
function suffixOf(g: GoalState): string {
  return `${g.flag === 'pending' ? ' [바뀜]' : ''} [${g.label}]`
}

// 사용자가 지은 부분(앞)은 그대로 두고, 모드가 붙였던 맨 뒤 글만 갈아 끼운다.
// 제목이 모드가 붙였던 글로 끝나지 않으면(사용자가 그 부분을 고쳤으면) 그 글은 사용자 것으로 둔다
function retitle(current: string, g: GoalState): string {
  const front = g.lastSuffix && current.endsWith(g.lastSuffix) ? current.slice(0, -g.lastSuffix.length) : current

  return front.trimEnd() + suffixOf(g)
}

// 한국 시각 HH:MM
function kst(iso: string): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const d = new Date(t + 9 * 3600 * 1000)
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')

  return `${hh}:${mm}`
}

type Els = { Box: any; Text: any }

// 목표 부분: 굵게. 바뀐 뒤 두 메시지 동안은 바뀐 사실을 노랗게 붙인다
function goalTree({ Box, Text }: Els, g: GoalState) {
  const prev = g.history[g.history.length - 1]
  const isFresh = g.flag !== 'none' && prev !== undefined

  return (
    <Box flexDirection="column">
      <Text>
        <Text size="caption" dimColor>
          목표{'  '}
        </Text>
        <Text bold>{g.goal}</Text>
      </Text>
      {isFresh && (
        <Text color="warning">
          {'      '}▲ {kst(g.since)} 목표 바뀜 · 이전 「{prev.goal}」{g.why ? ` · 까닭: ${g.why}` : ''}
        </Text>
      )}
    </Box>
  )
}

// 요청 부분: 사용자가 몰라도 되는 칸은 작고 흐리게
function requestTree({ Box, Text }: Els, r: RequestEntry, foot: string) {
  const meta = [r.kind, '사용자가 말함', kst(r.said_at)].filter(Boolean).join(' · ')
  const tail = [r.original ? `들은 말 「${r.original.replace(/^「|」$/g, '')}」` : '', foot].filter(Boolean).join(' · ')

  return (
    <Box flexDirection="column">
      <Text>
        <Text size="caption" dimColor>
          의도{'  '}
        </Text>
        <Text>{r.title}</Text>
      </Text>
      {r.body.map((s, i) => (
        <Text>
          <Text size="caption" dimColor>
            {i === 0 ? '목적  ' : '      '}
          </Text>
          {s.mark === 'guess' ? (
            <Text color="warning">
              {s.t}
              <Text size="caption" color="warning">
                {'  '}AI 짐작 · 확인 필요
              </Text>
            </Text>
          ) : (
            <Text>{s.t}</Text>
          )}
        </Text>
      ))}
      {r.gap && (
        <Text color="warning">
          <Text bold color="warning">
            물음{'  '}
          </Text>
          {r.gap.prompt}
        </Text>
      )}
      <Text size="caption" dimColor>
        {[meta, tail].filter(Boolean).join(' · ')}
      </Text>
    </Box>
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: TOOL,
      description:
        '사용자가 보는 띠에, AI 에이전트가 이번 요청을 어떻게 이해했는지(의도 · 목적 · 짐작 · 물음 · 들은 말)를 적는다. 이 대화의 목표는 처음과 목표가 바뀔 때만 함께 적는다. 사용자의 새 메시지마다 답하기 전에 한 번 부른다.',
      inputSchema: {
        type: 'object',
        properties: {
          title: { type: 'string', description: '의도: 이번 요청으로 사용자가 무엇을 원하는지 한 문장. 사용자의 말을 부풀리지 않는다.' },
          body: {
            type: 'array',
            description: '목적: 그래서 이번 답에서 무엇을 어디까지 하고 무엇은 하지 않는지, 문장마다 하나.',
            items: {
              type: 'object',
              properties: {
                t: { type: 'string', description: '문장 하나' },
                mark: { type: 'string', enum: ['guess'], description: '사용자가 정하지 않았는데 AI 에이전트가 고르거나 짐작한 문장이면 "guess"' },
              },
              required: ['t'],
            },
          },
          gap: { type: 'string', description: '확인하지 못해 사용자에게 물어야 할 것. 없으면 비운다.' },
          original: { type: 'string', description: '이번 이해의 근거가 된 사용자의 말. 짧게, 그대로 옮긴다.' },
          goal: { type: 'string', description: '목표: 사용자의 요청들이 결과적으로 무엇을 하기 위함인가. 처음 한 번과 목표 자체가 바뀔 때만 적는다.' },
          label: { type: 'string', description: '세션 제목 뒤 대괄호에 붙일 짧은 목표, 20자 안팎. goal 을 적을 때 함께 적는다.' },
          changed: { type: 'boolean', description: '목표 자체가 바뀌었으면 true. 요청마다 의도가 다른 것은 바뀐 것이 아니다.' },
          why: { type: 'string', description: '목표가 바뀌었다면 무엇이 왜 바뀌었는지, 사용자의 어느 말 때문인지' },
        },
        required: ['title', 'body', 'original'],
      },
      isDeferred: false,
    })
    // 명령 등록이 거절돼도 도구와 띠는 살아 있게 한다.
    // 옆 패널은 채팅 칸을 좁히므로 저절로 열지 않고, /goal-pane 을 입력할 때만 연다
    await $.command.register({ name: 'goal-pane', description: `「${TITLE}」 옆 패널을 연다` }).catch(() => undefined)

    return next(e)
  })

  // 패널이 실제로 그려졌는지, 아니면 왜 안 그려졌는지를 그대로 알린다
  on('command.run', { command: 'goal-pane' }, async $ => {
    const opened = await $.ui.open({ id: PANE, title: TITLE })
    const surfaces = await $.session.surfaces().catch(() => [] as readonly string[])
    const where = `화면 종류: ${surfaces.length > 0 ? surfaces.join(', ') : '없음'}`

    return {
      text: opened.isPlaced
        ? `「${TITLE}」 패널이 그려졌습니다. (${where})`
        : `패널을 열었지만 이 화면에는 그려지지 않았습니다. 까닭: ${opened.reason} (${where}) 목표와 의도는 입력창 위 띠와 대화 안의 도구 줄 아래 카드로도 보입니다.`,
    }
  }).catch(() => ({ text: '패널을 열지 못했습니다.' }))

  // 대화 안에서도 보이도록, 적는 도구 줄 아래에 이번에 적은 것을 카드로 그린다
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.props.tool !== TOOL_FULL) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const row = await next(e)
    const input = (e.props.input ?? {}) as Record<string, unknown>
    const req = toRequest(input, '')
    const goal = str(input.goal)
    if (!req && !goal) return row

    return (
      <Box flexDirection="column" borderStyle="round" paddingX={1}>
        {row}
        {goal && (
          <Text>
            <Text size="caption" dimColor>
              {input.changed === true ? '목표 바뀜  ' : '목표  '}
            </Text>
            <Text bold>{goal}</Text>
          </Text>
        )}
        {req && requestTree({ Box, Text }, req, '')}
      </Box>
    )
  })

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)

    return { sections: [...composed.sections, { id: 'goal-pane:rule', text: RULE, scope: 'session' as const }] }
  })

  // 다른 플러그인이 시스템 프롬프트 단계를 먼저 처리해 위 지침이 빠질 수 있다.
  // 그래서 사용자 메시지마다 짧은 지침을 함께 붙인다 (사용자에게는 보이지 않는다)
  on('prompt.submit', ($, e, next) =>
    e.command || e.isMeta ? next(e) : next({ ...e, context: [...(e.context ?? []), NUDGE] }),
  )

  // 세션 제목: 앞은 사용자 몫, 맨 뒤 대괄호는 모드 몫. 엔진이 제목을 바꾸게 해 주는 때는 메시지가 들어올 때뿐이라 여기서 한다.
  // 목표가 바뀐 뒤 첫 메시지에 「[바뀜]」을 붙이고, 그다음 메시지에 뗀다
  on('classic.UserPromptSubmit', async ($, e, next) => {
    const result = await next(e)
    const current = typeof e.session_title === 'string' ? e.session_title : ''
    const g = await read($, goalAtom)
    if (!g || !current) return result

    const title = retitle(current, g)
    const suffix = suffixOf(g)
    await update($, goalAtom, (old): GoalState | null =>
      old ? { ...old, lastSuffix: suffix, flag: old.flag === 'pending' ? 'shown' : 'none' } : old,
    )

    return title === current ? result : { ...result, sessionTitle: title }
  }).catch(($, e, next) => next(e))

  // 상태 줄과 알림은 쓰지 않는다: 상태 줄은 글이 잘리고, 알림은 쌓여서 보지 않게 된다(2026-11-12 사용자)
  on('tool.call', { tool: TOOL_FULL }, async ($, e) => {
    const input = e as unknown as Record<string, unknown>
    const at = new Date().toISOString()
    const req = toRequest(input, at)
    const old = await read($, goalAtom)
    const goal = nextGoal(old, input, at)
    if (!req && !goal && !old) {
      return { deny: '이번 요청의 의도(title)와, 처음이라면 이 대화의 목표(goal)를 적어 주세요.' }
    }
    if (!req && !goal) return { deny: '이번 요청의 의도(title)를 한 문장으로 적어 주세요.' }

    if (goal) await update($, goalAtom, () => goal)
    const list = req ? await update($, requests, l => [...l, req].slice(-50)) : await read($, requests)

    const now = goal ?? old
    const goalNote = goal ? (goal.n === 1 ? ' 목표를 정했습니다.' : ` 목표가 바뀌었습니다(${goal.n}번째 목표).`) : ''
    const attached = await $.session.surfaces().catch(() => [] as readonly string[])

    return {
      result: `적었습니다 (요청 ${list.length}번째).${goalNote}${now ? '' : ' 아직 목표가 없습니다: 다음에 goal 과 label 을 함께 적어 주세요.'} 연결된 화면: ${attached.length > 0 ? attached.join(', ') : '없음'}.`,
    }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: 'goal-pane: 저장하지 못했습니다. 답은 계속 써도 됩니다.' },
  )

  // 입력창 바로 위 띠: 가로 폭을 더 쓰지 않고 목표와 이번 의도를 보인다. 접기([-])는 엔진이 그린다
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const g = await read($, goalAtom)
    const list = await read($, requests)
    const now = list[list.length - 1]
    if (!g && !now) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const older = list.length - 1

    return (
      <Box flexDirection="column">
        {g && goalTree({ Box, Text }, g)}
        {now && requestTree({ Box, Text }, now, older > 0 ? `지난 요청 ${older}건은 /goal-pane` : '')}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const g = await read($, goalAtom)
    const list = await read($, requests)
    const now = list[list.length - 1]
    if (!g && !now) {
      return (
        <Box flexDirection="column">
          <Text bold>아직 없습니다</Text>
          <Text dimColor>메시지를 보내면, AI 에이전트가 이해한 목표와 의도가 여기에 뜹니다.</Text>
        </Box>
      )
    }

    const pastGoals = g ? [...g.history].reverse() : []
    const older = list.slice(0, -1).reverse().slice(0, 8)

    return (
      <Box flexDirection="column" gap={1}>
        {g && goalTree({ Box, Text }, g)}
        {pastGoals.length > 0 && (
          <Box flexDirection="column">
            <Text size="caption" dimColor>
              지난 목표 (최근 것부터)
            </Text>
            {pastGoals.map(p => (
              <Text size="caption" dimColor>
                {kst(p.since)} {p.goal}
              </Text>
            ))}
          </Box>
        )}
        {now && requestTree({ Box, Text }, now, '')}
        {older.length > 0 && (
          <Box flexDirection="column">
            <Text size="caption" dimColor>
              지난 요청 (최근 것부터)
            </Text>
            {older.map(r => (
              <Text size="caption" dimColor>
                {kst(r.said_at)} {r.title}
              </Text>
            ))}
          </Box>
        )}
      </Box>
    )
  })
}
