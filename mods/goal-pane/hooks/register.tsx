import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { GoalEntry } from '../types'

const PANE = 'goal'
const TITLE = '지금 이해한 목표'
const TOOL = 'set_goal'
const TOOL_FULL = 'mcp__goal-pane__set_goal'

// 항목이 바뀌면 shape 꼬리표를 바꾼다: 앞 버전이 남긴 값을 받지 않게 한다
const goals = atom({ plugin: 'goal-pane', key: 'goals' } as const, [] as GoalEntry[], {
  shape: 'goals-1',
})

// 모델이 읽는 지침: 무엇을 하라기보다 패널이 무엇을 위한 것인지를 먼저 말한다
const RULE = [
  '이 세션에는 사용자가 보는 「지금 이해한 목표」 패널이 있다.',
  '이 패널은 AI 에이전트가 사용자의 뜻을 지금 어떻게 이해하고 있는지 늘 보여 주어, 이해가 어긋나거나 사용자의 의도가 바뀌었을 때 사용자가 바로 알아차리고 고칠 수 있게 하려는 것이다.',
  `사용자의 새 메시지를 받으면, 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 를 한 번 불러 지금 이해한 사용자의 목표를 적는다.`,
  '목표에는 이 대화에서 사용자가 이루려는 것을 한두 문장으로 쓴다. 사용자의 말을 부풀리지 않는다: 「할 수도 있다」를 「한다」로, 「그중 하나」를 「전부」로 바꾸지 않는다.',
  '바로 앞에 적은 목표에서 달라졌으면 changed 를 true 로 하고, 무엇이 왜 달라졌는지(사용자의 어느 말 때문인지) 적는다.',
  '확인하지 못한 짐작은 목표에 섞지 않고 asks 에 둔다.',
].join('\n')

// 메시지마다 붙이는 짧은 지침
const NUDGE = `「지금 이해한 목표」 패널: 이 메시지에 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 로 지금 이해한 사용자의 목표를 한두 문장으로 적는다. 사용자의 말을 부풀리지 않는다(「할 수도 있다」를 「한다」로, 「그중 하나」를 「전부」로 바꾸지 않는다). 앞 목표에서 달라졌으면 changed 를 true 로 하고 까닭을 적는다. 확인하지 못한 짐작은 asks 에 둔다. 답의 맨 위에 목표를 따로 쓰지는 않는다. 세션 제목은 사용자가 정하는 것이므로 바꾸지 않는다.`

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : ''
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.map(str).filter(s => s.length > 0).slice(0, 8) : []
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

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: TOOL,
      description:
        '사용자가 보는 「지금 이해한 목표」 패널에, AI 에이전트가 지금 이해한 사용자의 목표를 적는다. 사용자의 새 메시지마다 답하기 전에 한 번 부른다.',
      inputSchema: {
        type: 'object',
        properties: {
          goal: { type: 'string', description: '지금 이해한 사용자의 목표. 한두 문장. 사용자의 말을 부풀리지 않는다.' },
          changed: { type: 'boolean', description: '바로 앞에 적은 목표에서 달라졌으면 true' },
          why: { type: 'string', description: '달라졌다면 무엇이 왜 달라졌는지, 사용자의 어느 말 때문인지' },
          asks: { type: 'array', items: { type: 'string' }, description: '확인하지 못해 사용자에게 물어야 할 것' },
        },
        required: ['goal', 'changed'],
      },
      isDeferred: false,
    })
    // 명령 등록이 거절돼도 도구와 패널은 살아 있게 한다
    await $.command.register({ name: 'goal-pane', description: '「지금 이해한 목표」 패널을 연다' }).catch(() => undefined)
    void $.ui.open({ id: PANE, title: TITLE })

    return next(e)
  })

  // 앱이 나중에 화면으로 붙으면 그때 패널을 연다
  on('session.attach', async ($, e, next) => {
    const joined = await next(e)
    void $.ui.open({ id: PANE, title: TITLE })
    $.ui.toast(`화면이 붙었습니다 (${e.surface}). 「지금 이해한 목표」 패널을 엽니다.`)

    return joined
  })

  // 패널이 실제로 그려졌는지, 아니면 왜 안 그려졌는지를 그대로 알린다
  on('command.run', { command: 'goal-pane' }, async $ => {
    const opened = await $.ui.open({ id: PANE, title: TITLE })
    const surfaces = await $.session.surfaces().catch(() => [] as readonly string[])
    const where = `화면 종류: ${surfaces.length > 0 ? surfaces.join(', ') : '없음'}`

    return {
      text: opened.isPlaced
        ? `「지금 이해한 목표」 패널이 그려졌습니다. (${where})`
        : `패널을 열었지만 이 화면에는 그려지지 않았습니다. 까닭: ${opened.reason} (${where}) 목표는 대화 안의 도구 줄 아래 카드로도 보입니다.`,
    }
  }).catch(() => ({ text: '패널을 열지 못했습니다.' }))

  // 패널을 그리지 않는 화면에서도 보이도록, 목표를 적는 도구 줄 아래에 카드로 목표를 그린다
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.props.tool !== TOOL_FULL) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const row = await next(e)
    const input = (e.props.input ?? {}) as Record<string, unknown>
    const goal = str(input.goal)
    const why = str(input.why)
    const asks = strList(input.asks)
    if (!goal) return row

    return (
      <Box flexDirection="column" borderStyle="round" paddingX={1}>
        {row}
        <Box flexDirection="column">
          <Text bold>{input.changed === true ? '목표가 바뀌었습니다' : '지금 이해한 목표'}</Text>
          <Text>{goal}</Text>
          {input.changed === true && why.length > 0 && <Text dimColor>바뀐 까닭: {why}</Text>}
          {asks.length > 0 && <Text dimColor>확인이 필요한 것: {asks.join(' / ')}</Text>}
        </Box>
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

  on('tool.call', { tool: TOOL_FULL }, async ($, e) => {
    const args = e as unknown as Record<string, unknown>
    const goal = str(args.goal)
    if (!goal) return { deny: 'goal 이 비어 있습니다. 지금 이해한 사용자의 목표를 한두 문장으로 적어 주세요.' }

    const entry: GoalEntry = {
      at: new Date().toISOString(),
      goal,
      isChange: args.changed === true,
      why: str(args.why),
      asks: strList(args.asks),
    }
    const list = await update($, goals, old => [...old, entry].slice(-50))

    $.ui.status(`목표: ${goal.length > 40 ? goal.slice(0, 40) + '…' : goal}`)
    if (entry.isChange && list.length > 1) $.ui.toast('목표가 바뀌었습니다. 옆 패널에서 확인해 주세요.')

    // 지금 이 세션에 붙은 화면을 함께 알린다: 패널이 그려질 수 있는지 알 수 있게
    const attached = await $.session.surfaces().catch(() => [] as readonly string[])
    const surfaceNote = ` 연결된 화면: ${attached.length > 0 ? attached.join(', ') : '없음'}.`

    return { result: `목표를 적었습니다 (${list.length}번째).${surfaceNote}` }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: 'goal-pane: 목표를 저장하지 못했습니다. 답은 계속 써도 됩니다.' },
  )

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, goals)

    const now = list[list.length - 1]
    if (!now) {
      return (
        <Box flexDirection="column">
          <Text bold>아직 없습니다</Text>
          <Text dimColor>메시지를 보내면, AI 에이전트가 이해한 목표가 여기에 뜹니다.</Text>
        </Box>
      )
    }

    const older = list.slice(0, -1).reverse().slice(0, 8)

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text dimColor>지금 목표 · {kst(now.at)}</Text>
          <Text bold>{now.goal}</Text>
          {now.isChange && now.why.length > 0 && <Text dimColor>바뀐 까닭: {now.why}</Text>}
        </Box>
        {now.asks.length > 0 && (
          <Box flexDirection="column">
            <Text bold>확인이 필요한 것</Text>
            {now.asks.map(a => (
              <Text>· {a}</Text>
            ))}
          </Box>
        )}
        {older.length > 0 && (
          <Box flexDirection="column">
            <Text dimColor>지난 목표 (최근 것부터)</Text>
            {older.map(g => (
              <Text dimColor>
                {kst(g.at)} {g.isChange ? '[바뀜] ' : ''}
                {g.goal}
              </Text>
            ))}
          </Box>
        )}
      </Box>
    )
  })
}
