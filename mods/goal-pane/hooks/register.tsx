import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { GoalEntry, Sentence } from '../types'

const PANE = 'goal'
const TITLE = '지금 이해한 의도'
const TOOL = 'set_goal'
const TOOL_FULL = 'mcp__goal-pane__set_goal'

// 항목이 바뀌면 shape 꼬리표를 바꾼다: 앞 버전이 남긴 값을 받지 않게 한다.
// goals-2: 목표 한 줄에서 SSoT 기록 확인함의 기록 한 건 형태(title · body · gap · original …)로 바꿨다
const goals = atom({ plugin: 'goal-pane', key: 'goals' } as const, [] as GoalEntry[], {
  shape: 'goals-2',
})

// 모델이 읽는 지침: 무엇을 하라기보다 이 표시가 무엇을 위한 것인지를 먼저 말한다
const RULE = [
  '이 세션에는 사용자가 보는 「지금 이해한 의도」 띠가 입력창 바로 위에 있다.',
  '이 띠는 AI 에이전트가 사용자의 말을 어떻게 이해했는지, 곧 사용자가 무엇을 원하는지(의도)와 그래서 어떤 작업을 하려는지(목적)를 늘 보여 주어, 이해가 어긋나거나 사용자의 의도가 바뀌었을 때 사용자가 바로 알아차리고 고칠 수 있게 하려는 것이다.',
  `사용자의 새 메시지를 받으면, 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 를 한 번 불러 적는다.`,
  'title 에는 의도를 한 문장으로 쓴다. 사용자의 말을 부풀리지 않는다: 「할 수도 있다」를 「한다」로, 「그중 하나」를 「전부」로 바꾸지 않는다.',
  'body 에는 목적, 곧 이번 답에서 무엇을 어디까지 하고 무엇은 하지 않는지를 문장마다 하나씩 쓴다. 사용자가 정하지 않았는데 AI 에이전트가 고르거나 짐작한 문장은 mark 를 "guess" 로 한다.',
  'gap 에는 확인하지 못해 사용자에게 물어야 할 것을 쓴다. 물음이 있으면 답을 받기 전에는 그 짐작대로 진행하지 않는다.',
  'original 에는 이번 이해의 근거가 된 사용자의 말을 짧게 그대로 옮긴다.',
  '바로 앞에 적은 것에서 이해가 달라졌으면 changed 를 true 로 하고, 무엇이 왜 달라졌는지(사용자의 어느 말 때문인지) why 에 적는다.',
].join('\n')

// 메시지마다 붙이는 짧은 지침
const NUDGE = `「${TITLE}」 띠: 이 메시지에 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 로 적는다. title = 의도(사용자가 무엇을 원하나, 한 문장), body = 목적(그래서 무슨 작업을 어디까지 하고 무엇은 안 하나, 문장마다 하나, 짐작이나 직접 고른 것은 mark "guess"), gap = 사용자에게 물을 것(있으면 답 전에는 그 짐작대로 진행하지 않는다), original = 근거가 된 사용자의 말 그대로. 사용자의 말을 부풀리지 않는다(「할 수도 있다」를 「한다」로, 「그중 하나」를 「전부」로 바꾸지 않는다). 앞에서 이해가 달라졌으면 changed 를 true 로 하고 why 에 까닭을 적는다. 답의 맨 위에 이것을 따로 쓰지는 않는다. 세션 제목은 사용자가 정하는 것이므로 바꾸지 않는다.`

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

// 도구 입력을 SSoT 기록 한 건 형태로 옮긴다. 앞 버전 입력(goal · asks)도 받아 준다
function toEntry(input: Record<string, unknown>, at: string): GoalEntry | null {
  const title = str(input.title) || str(input.goal)
  if (!title) return null
  const gapText = str(input.gap) || strList(input.asks).join(' / ')
  const isChange = input.changed === true

  return {
    kind: '요청',
    source: '사용자',
    said_at: at,
    title,
    body: sentences(input.body),
    ...(gapText ? { gap: { prompt: gapText } } : {}),
    original: str(input.original),
    isChange,
    why: isChange ? str(input.why) : '',
  }
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

// 띠 · 카드 · 패널이 같이 쓰는 기록 한 건의 모양. 사용자가 몰라도 되는 칸은 작고 흐리게
function recordTree({ Box, Text }: Els, g: GoalEntry, foot: string) {
  const meta = [g.kind, g.source === '사용자' ? '사용자가 말함' : 'AI가 찾음', kst(g.said_at), g.isChange ? '이해가 바뀜' : '']
    .filter(Boolean)
    .join(' · ')

  return (
    <Box flexDirection="column">
      <Text size="caption" dimColor>
        {meta}
      </Text>
      <Text>
        <Text size="caption" dimColor>
          의도{'  '}
        </Text>
        <Text bold>{g.title}</Text>
      </Text>
      {g.body.map((s, i) => (
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
      {g.gap && (
        <Text color="warning">
          <Text bold color="warning">
            물음{'  '}
          </Text>
          {g.gap.prompt}
        </Text>
      )}
      {g.isChange && g.why.length > 0 && (
        <Text size="caption" dimColor>
          바뀐 까닭: {g.why}
        </Text>
      )}
      {(g.original.length > 0 || foot.length > 0) && (
        <Text size="caption" dimColor>
          {[g.original ? `들은 말 「${g.original.replace(/^「|」$/g, '')}」` : '', foot].filter(Boolean).join(' · ')}
        </Text>
      )}
    </Box>
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: TOOL,
      description:
        '사용자가 보는 「지금 이해한 의도」 띠에, AI 에이전트가 사용자의 말을 어떻게 이해했는지를 SSoT 기록 한 건의 형태로 적는다. 사용자의 새 메시지마다 답하기 전에 한 번 부른다.',
      inputSchema: {
        type: 'object',
        properties: {
          title: { type: 'string', description: '의도: 사용자가 무엇을 원하는지 한 문장. 사용자의 말을 부풀리지 않는다.' },
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
          changed: { type: 'boolean', description: '바로 앞에 적은 이해에서 달라졌으면 true' },
          why: { type: 'string', description: '달라졌다면 무엇이 왜 달라졌는지, 사용자의 어느 말 때문인지' },
        },
        required: ['title', 'body', 'original', 'changed'],
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
        : `패널을 열었지만 이 화면에는 그려지지 않았습니다. 까닭: ${opened.reason} (${where}) 이해한 의도는 입력창 위 띠와 대화 안의 도구 줄 아래 카드로도 보입니다.`,
    }
  }).catch(() => ({ text: '패널을 열지 못했습니다.' }))

  // 대화 안에서도 보이도록, 적는 도구 줄 아래에 같은 모양의 카드를 그린다
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.props.tool !== TOOL_FULL) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const row = await next(e)
    const entry = toEntry((e.props.input ?? {}) as Record<string, unknown>, new Date().toISOString())
    if (!entry) return row

    return (
      <Box flexDirection="column" borderStyle="round" paddingX={1}>
        {row}
        {recordTree({ Box, Text }, { ...entry, said_at: '' }, '')}
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

  // 상태 줄과 알림은 쓰지 않는다: 상태 줄은 글이 잘리고, 알림은 쌓여서 보지 않게 된다(2026-11-12 사용자)
  on('tool.call', { tool: TOOL_FULL }, async ($, e) => {
    const entry = toEntry(e as unknown as Record<string, unknown>, new Date().toISOString())
    if (!entry) return { deny: 'title 이 비어 있습니다. 사용자가 무엇을 원하는지(의도)를 한 문장으로 적어 주세요.' }

    const list = await update($, goals, old => [...old, entry].slice(-50))

    // 지금 이 세션에 붙은 화면을 함께 알린다: 띠가 그려질 수 있는지 알 수 있게
    const attached = await $.session.surfaces().catch(() => [] as readonly string[])
    const surfaceNote = ` 연결된 화면: ${attached.length > 0 ? attached.join(', ') : '없음'}.`

    return { result: `적었습니다 (${list.length}번째).${surfaceNote}` }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: 'goal-pane: 저장하지 못했습니다. 답은 계속 써도 됩니다.' },
  )

  // 입력창 바로 위 띠: 가로 폭을 더 쓰지 않고 지금 이해만 보인다. 접기([-])는 엔진이 그린다
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const list = await read($, goals)
    const now = list[list.length - 1]
    if (!now) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const older = list.length - 1

    return recordTree({ Box, Text }, now, older > 0 ? `지난 이해 ${older}건은 /goal-pane` : '')
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, goals)

    const now = list[list.length - 1]
    if (!now) {
      return (
        <Box flexDirection="column">
          <Text bold>아직 없습니다</Text>
          <Text dimColor>메시지를 보내면, AI 에이전트가 이해한 의도가 여기에 뜹니다.</Text>
        </Box>
      )
    }

    const older = list.slice(0, -1).reverse().slice(0, 8)

    return (
      <Box flexDirection="column" gap={1}>
        {recordTree({ Box, Text }, now, '')}
        {older.length > 0 && (
          <Box flexDirection="column">
            <Text size="caption" dimColor>
              지난 이해 (최근 것부터)
            </Text>
            {older.map(g => (
              <Text size="caption" dimColor>
                {kst(g.said_at)} {g.isChange ? '[바뀜] ' : ''}
                {g.title}
              </Text>
            ))}
          </Box>
        )}
      </Box>
    )
  })
}
