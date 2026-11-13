import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { AssumptionMarks, GoalState, RequestEntry, TitleState } from '../types'

const PANE = 'goal'
const TITLE = '이해한 의도'
const TOOL = 'set_goal'
const TOOL_FULL = 'mcp__goal-pane__set_goal'

// 이번 요청이 지금 목표에 맞는지의 판단. 맞으면 그대로, 안 맞으면 목표가 넓어지거나 바뀐 것인지, 목표와 별개인 곁가지 작업이 새로 생긴 것인지 가린다(2026-11-13 사용자).
// 칸을 따로 둔 까닭: 「바뀔 때만 goal 을 적는다」만으로는 AI가 판단 자체를 건너뛰어, 세션 10개에서 목표가 바뀐 기록이 2번뿐이었다(2026-11-13 측정)
const FITS = ['처음', '부합', '확장', '변경', '곁가지'] as const
// 블라인드 테스트(2026-11-13)에서 짚인 두 곳을 풀었다: 「목표 그대로」가 뜻풀이인지 goal 을 적지 말라는 말인지 · 확장과 변경의 경계
const FIT_RULE = '부합(지금 목표 안의 일) · 확장(지금 목표를 품으며 넓어짐) · 변경(지금 목표 대신 다른 목표가 됨) · 곁가지(목표와 별개인 작업이 새로 생김). 부합 · 곁가지면 goal 을 적지 않는다(목표 그대로). 확장 · 변경이면 goal 에 바뀐 뒤의 목표 전체를, why 에 사용자의 어느 말 때문인지 적는다.'

// 항목이 바뀌면 shape 꼬리표를 바꾼다: 앞 버전이 남긴 값을 받지 않게 한다
const goalAtom = atom({ plugin: 'goal-pane', key: 'goal' } as const, null as GoalState | null, { shape: 'goal-2' })
const requests = atom({ plugin: 'goal-pane', key: 'requests' } as const, [] as RequestEntry[], { shape: 'req-3' })
// 사용자가 ✓(확정) · ✗(틀림)로 표시한 가정. 그 의도(said_at)에만 붙고, 다음 메시지에 실려 가면 지운다
const marksAtom = atom({ plugin: 'goal-pane', key: 'marks' } as const, null as AssumptionMarks | null, { shape: 'marks-1' })

// 사람이 보낸 메시지에만 표시한 가정을 싣는다. 알림 · 예약 작업 · 다른 세션 · 플러그인이 보낸 것에 실으면 표시가 엉뚱한 데로 새고 지워진다
const MACHINE_ORIGINS = new Set(['task-notification', 'scheduled-trigger', 'peer', 'peer-send-message', 'projects-relay', 'channel', 'coordinator', 'plugin'])

// 보여 주는 곳과 저장하는 곳을 나눈다(2026-11-12 사용자: 「판넬은 시각화 · 최적화용, 저장은 따로」).
// 입력창 위 영역: 의도(AI가 사용자의 최근 요청을 어떻게 이해했나) · 가정 · 확인 질문(가정 · 확인 질문은 있을 때만).
// 목표: 세션 제목 맨 뒤 대괄호에만. 근거가 된 말 · 그렇게 이해한 까닭: 화면에 내지 않고 세션마다 파일에 쌓는다.
// 낱말은 Claude 레포 설계.md 규칙 6 순서(업계 통용 용어 먼저)로 골랐다: 의도(intent) · 가정(assumption) · 확인 질문(clarifying question)
const RULE = [
  '이 세션에서는 입력창 바로 위 영역과 세션 제목 맨 뒤 대괄호에, AI 에이전트가 사용자를 어떻게 이해하고 있는지가 늘 보인다. 이해가 어긋나거나 사용자의 뜻이 바뀌었을 때 사용자가 바로 알아차리고 고칠 수 있게 하려는 것이다.',
  '의도는 AI 에이전트가 사용자의 최근 요청을 어떻게 이해했는가이고, 메시지마다 다르다. 목표는 사용자의 요청들이 궁극적으로 이루려는 것이고, 거의 바뀌지 않는다.',
  `사용자의 새 메시지를 받으면, 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 를 한 번 불러 적는다: title(의도 한 문장), assumptions(가정: 사용자가 말하지 않았는데 AI 에이전트가 전제하거나 대신 고른 것, 있을 때만), question(확인 질문: 사용자에게 물어야 할 것, 있을 때만), original(근거가 된 사용자의 말 그대로), reason(왜 그렇게 이해했는지: 사용자의 어느 말과 앞의 어떤 맥락 때문인지).`,
  '입력창 위 영역에는 의도 · 가정 · 확인 질문만 보인다. original 과 reason 은 화면에 나오지 않고 나중에 이해를 되짚기 위해 따로 저장된다.',
  `메시지마다 이번 요청이 지금 목표에 맞는지 판단해 fit 에 적는다: ${FIT_RULE} 목표가 아직 없으면 fit 은 처음이고 goal 을 적는다. goal 은 세션 제목 뒤에 붙으므로 20자 안팎으로 짧게 쓴다.`,
  '사용자의 말을 부풀리지 않는다: 「할 수도 있다」를 「한다」로, 「그중 하나」를 「전부」로 바꾸지 않는다. 확인 질문이 있으면 답을 받기 전에는 그 가정대로 진행하지 않는다.',
  '세션 제목은 대괄호 앞은 사용자가, 맨 뒤 대괄호는 이 모드가 바꾼다. AI 에이전트는 제목을 직접 바꾸지 않는다.',
].join('\n')

// 메시지마다 붙이는 짧은 지침. 지금 목표를 실어 보내 AI가 이번 요청과 나란히 놓고 판단하게 한다:
// 지금 목표가 지침에 없을 때는 AI가 목표를 다시 보지 않아 판단을 건너뛰었다(2026-11-13)
function nudge(goal: string | undefined): string {
  const goalPart = goal
    ? `지금 목표: 「${goal}」. fit = 이번 요청이 이 목표에 맞는지: ${FIT_RULE}`
    : 'fit = 처음, goal = 사용자의 요청들이 궁극적으로 이루려는 것(20자 안팎, 세션 제목 뒤에 붙음).'

  return `입력창 위 영역: 이 메시지에 답하거나 다른 도구를 쓰기 전에 ${TOOL_FULL} 로 적는다. title = 의도(AI 에이전트가 사용자의 최근 요청을 어떻게 이해했나, 한 문장), assumptions = 가정(사용자가 말하지 않았는데 전제하거나 대신 고른 것, 있을 때만, 하나씩), question = 확인 질문(사용자에게 물어야 할 것, 있을 때만. 있으면 답 전에는 그 가정대로 진행하지 않는다), original = 근거가 된 사용자의 말 그대로, reason = 왜 그렇게 이해했는지(어느 말 · 어떤 앞 맥락 때문인지). 화면에는 의도 · 가정 · 확인 질문만 보이고 original · reason 은 따로 저장된다. ${goalPart} 사용자의 말을 부풀리지 않는다. 답의 맨 위에 이것을 따로 쓰지 않고, 세션 제목은 직접 바꾸지 않는다.`
}

function fitOf(v: unknown): (typeof FITS)[number] | '' {
  const s = typeof v === 'string' ? v.trim() : ''

  return (FITS as readonly string[]).includes(s) ? (s as (typeof FITS)[number]) : ''
}

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : ''
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.map(str).filter(s => s.length > 0).slice(0, 8) : []
}

// 문자열 하나로 와도 목록으로 받는다
function listOf(v: unknown): string[] {
  return typeof v === 'string' ? strList([v]) : strList(v)
}

// 제목 뒤 대괄호에 들어가므로 짧게, 대괄호는 빼서 제목 규칙이 깨지지 않게 한다
function shortGoal(goal: string): string {
  const base = goal.replace(/[[\]]/g, '').trim()

  return base.length > 30 ? base.slice(0, 30) + '…' : base
}

// 도구 입력에서 이번 요청을 옮긴다. 화면에는 title · assumptions · question 만 쓴다.
// 앞 버전 칸 이름(guess · gap · asks)으로 와도 받는다
function toRequest(input: Record<string, unknown>, at: string): RequestEntry | null {
  const title = str(input.title)
  if (!title) return null
  const assumptions = listOf(input.assumptions).length ? listOf(input.assumptions) : listOf(input.guess)
  const question = str(input.question) || str(input.gap) || strList(input.asks).join(' / ')
  const fit = fitOf(input.fit)

  return {
    said_at: at,
    title,
    ...(assumptions.length ? { assumptions } : {}),
    ...(question ? { question } : {}),
    ...(fit ? { fit } : {}),
    original: str(input.original),
    reason: str(input.reason),
  }
}

// 목표가 넓어지거나 바뀌었다는 판단인가. fit 이 없던 앞 버전의 changed: true 도 받는다
function isGoalMove(input: Record<string, unknown>): boolean {
  const fit = fitOf(input.fit)

  return fit === '확장' || fit === '변경' || (fit === '' && input.changed === true)
}

// 목표를 처음 정하거나, 넓어지거나 바뀌었을 때만 새 값을 만든다. 부합 · 곁가지는 goal 이 와도 null (그대로 둔다)
function nextGoal(old: GoalState | null, input: Record<string, unknown>, at: string): GoalState | null {
  const raw = str(input.goal) || str(input.label)
  if (!raw) return null
  const goal = shortGoal(raw)
  if (!old) return { goal, since: at, n: 1, why: '', history: [] }
  if (!isGoalMove(input) || goal === old.goal) return null

  return {
    goal,
    since: at,
    n: old.n + 1,
    why: str(input.why),
    history: [...old.history, { goal: old.goal, since: old.since, why: old.why }].slice(-20),
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

// 내 사용자 폴더 아래 goal-pane 폴더. 윈도우와 맥 모두
async function homeDir($: EngineInterface): Promise<string | undefined> {
  const home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME'))

  return home ? `${home.replace(/\\/g, '/')}/.claude/goal-pane` : undefined
}

// 이해한 까닭을 세션마다 파일 한 줄씩 쌓는다. 실패해도 화면과 답은 그대로 간다
async function keep($: EngineInterface, line: Record<string, unknown>): Promise<void> {
  const dir = await homeDir($)
  if (!dir) return
  const id = await $.session.id()
  const path = `${dir}/기록/${id}.jsonl`
  const before = await $.fs.read(path).catch(() => '')
  await $.fs.write(path, `${typeof before === 'string' ? before : ''}${JSON.stringify(line)}\n`)
}

// 세션 제목은 설정 훅(title-hook.mjs)이 바꾼다: 이 앱에서는 모드의 제목 훅이 다른 플러그인에 막혀 돌지 않는다(2026-11-12).
// 모드는 목표와 「[바뀜]」 단계를 세션 파일에 적기만 한다. 훅이 마지막으로 붙인 글(lastSuffix)은 지키며 고친다
async function markTitle($: EngineInterface, goal: string, isChange: boolean): Promise<void> {
  const dir = await homeDir($)
  if (!dir) return
  const id = await $.session.id()
  const path = `${dir}/제목/${id}.json`
  const raw = await $.fs.read(path).catch(() => '')
  let old: Partial<TitleState> = {}
  try {
    old = typeof raw === 'string' && raw ? (JSON.parse(raw) as Partial<TitleState>) : {}
  } catch {
    old = {}
  }
  // 앱을 다시 켜면 세션 상태가 비어 바뀐 목표도 「처음 정함」으로 온다. 그래서 파일에 남은 앞 목표와도 견준다
  const changed = isChange || (typeof old.goal === 'string' && old.goal !== '' && old.goal !== goal)
  const next: TitleState = { goal, flag: changed ? 'pending' : old.flag ?? 'none', lastSuffix: old.lastSuffix ?? '' }
  await $.fs.write(path, JSON.stringify(next))
}

type MarkKind = 'right' | 'wrong'

// ✓ 또는 ✗를 누를 때마다 그 가정의 표시를 켜고 끈다. 한 가정에는 둘 중 하나만 선다(✓를 누르면 ✗가 풀린다).
// 다른 의도에 남은 표시는 버린다
function toggleMark(old: AssumptionMarks | null, saidAt: string, i: number, kind: MarkKind): AssumptionMarks | null {
  const cur = old && old.said_at === saidAt ? old : { said_at: saidAt, right: [] as number[], wrong: [] as number[] }
  const other: MarkKind = kind === 'right' ? 'wrong' : 'right'
  const mine = cur[kind].includes(i) ? cur[kind].filter(m => m !== i) : [...cur[kind], i].sort((a, b) => a - b)
  const theirs = cur[other].filter(m => m !== i)
  const next = { said_at: saidAt, [kind]: mine, [other]: theirs } as AssumptionMarks

  return next.right.length || next.wrong.length ? next : null
}

// 지금 의도에 붙은 표시만 쓴다
function marksFor(w: AssumptionMarks | null, r: RequestEntry | undefined): { right: number[]; wrong: number[] } {
  const ok = (i: number) => i >= 0 && i < (r?.assumptions ?? []).length
  if (!w || !r || w.said_at !== r.said_at) return { right: [], wrong: [] }

  return { right: (w.right ?? []).filter(ok), wrong: (w.wrong ?? []).filter(ok) }
}

type Els = { Box: any; Text: any; Button?: any }
type Marking = { right: number[]; wrong: number[]; toggle?: (i: number, kind: MarkKind) => void }

// 입력창 위 영역 · 카드 · 패널이 같이 쓰는 의도 · 가정 · 확인 질문. 가정과 확인 질문은 있을 때만 줄이 생긴다.
// 입력창 위 영역에서는 가정 줄마다 오른쪽 끝에 ✓ ✗가 서고(줄 양끝 정렬이라 글 길이와 상관없이 세로로 맞는다),
// ✓는 초록 「확정」, ✗는 빨간 취소선 「틀림」으로 바뀐다(2026-11-13 사용자: 「확정, 클로드한테 확신 주기」)
function intentTree({ Box, Text, Button }: Els, r: Pick<RequestEntry, 'title' | 'assumptions' | 'question' | 'fit'>, m: Marking = { right: [], wrong: [] }) {
  const counts = [m.right.length ? `확정 ${m.right.length}개` : '', m.wrong.length ? `틀림 ${m.wrong.length}개` : ''].filter(Boolean).join(' · ')

  return (
    <Box flexDirection="column">
      <Text>
        <Text size="caption" dimColor>
          의도{'  '}
        </Text>
        <Text>{r.title}</Text>
      </Text>
      {(r.assumptions ?? []).map((a, i) => {
        const isWrong = m.wrong.includes(i)
        const isRight = m.right.includes(i)
        const tone = isWrong ? 'error' : isRight ? 'success' : 'warning'

        return (
          <Box flexDirection="row" justifyContent="space-between" width="100%">
            <Box flexShrink={1}>
              <Text color={tone}>
                <Text size="caption" color={tone}>
                  가정{'  '}
                </Text>
                <Text color={tone} strikethrough={isWrong}>
                  {a}
                </Text>
                {/* 「확인 필요」는 「가정」이란 이름과 같은 말이라 붙이지 않는다(2026-11-12 사용자). 눌렀을 때만 상태를 적는다 */}
                {(isWrong || isRight) && (
                  <Text size="caption" color={tone}>
                    {'  '}
                    {isWrong ? '틀림' : '확정'}
                  </Text>
                )}
              </Text>
            </Box>
            {Button && m.toggle && (
              <Box flexDirection="row" marginLeft={1} gap={1}>
                <Button key={`right-${i}`} plain onPress={() => m.toggle?.(i, 'right')}>
                  <Text color="success" bold={isRight}>
                    ✓
                  </Text>
                </Button>
                <Button key={`wrong-${i}`} plain onPress={() => m.toggle?.(i, 'wrong')}>
                  <Text color="error" bold={isWrong}>
                    ✗
                  </Text>
                </Button>
              </Box>
            )}
          </Box>
        )
      })}
      {/* 곁가지로 본 판단도 사용자가 확인할 수 있게 보인다. 부합은 보이지 않는다(늘 그런 것이라 줄만 늘어난다) */}
      {r.fit === '곁가지' && (
        <Text dimColor>
          <Text size="caption" dimColor>
            곁가지{'  '}
          </Text>
          목표와 별개인 새 작업으로 봄, 목표는 그대로
        </Text>
      )}
      {m.toggle && counts && (
        <Text size="caption" dimColor>
          {counts} → 다음 메시지에 함께 보냅니다
        </Text>
      )}
      {r.question && (
        <Text color="warning">
          <Text bold color="warning">
            확인 질문{'  '}
          </Text>
          {r.question}
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
        '사용자가 보는 입력창 위 영역에, AI 에이전트가 사용자의 최근 요청을 어떻게 이해했는지(의도)와 가정 · 확인 질문을 적고, 왜 그렇게 이해했는지(근거가 된 말 · 까닭)는 따로 저장한다. 이번 요청이 지금 목표에 맞는지(fit)를 매번 판단해 적고, 목표는 처음과 넓어지거나 바뀔 때만 적는다(세션 제목 맨 뒤 대괄호에 붙는다). 사용자의 새 메시지마다 답하기 전에 한 번 부른다.',
      inputSchema: {
        type: 'object',
        properties: {
          title: { type: 'string', description: '의도: AI 에이전트가 사용자의 최근 요청을 어떻게 이해했는지 한 문장. 사용자의 말을 부풀리지 않는다.' },
          assumptions: { type: 'array', items: { type: 'string' }, description: '가정: 사용자가 말하지 않았는데 AI 에이전트가 전제하거나 대신 고른 것, 하나씩. 화면에 노랗게 보인다. 없으면 비운다.' },
          question: { type: 'string', description: '확인 질문: 확인하지 못해 사용자에게 물어야 할 것. 없으면 비운다.' },
          original: { type: 'string', description: '이번 이해의 근거가 된 사용자의 말. 짧게, 그대로 옮긴다. 화면에는 나오지 않고 저장된다.' },
          reason: { type: 'string', description: '왜 그렇게 이해했는지: 사용자의 어느 말과 앞의 어떤 맥락 때문인지. 화면에는 나오지 않고 저장된다.' },
          fit: { type: 'string', enum: [...FITS], description: `이번 요청이 지금 목표에 맞는지. 처음(아직 목표 없음) · ${FIT_RULE}` },
          goal: { type: 'string', description: '목표: 사용자의 요청들이 궁극적으로 이루려는 것, 20자 안팎. 세션 제목 뒤 대괄호에 붙는다. fit 이 처음 · 확장 · 변경일 때만 적는다.' },
          why: { type: 'string', description: '목표가 넓어지거나 바뀌었다면 무엇이 왜 그런지, 사용자의 어느 말 때문인지' },
        },
        required: ['title', 'original', 'reason', 'fit'],
      },
      isDeferred: false,
    })
    // 명령 등록이 거절돼도 도구와 입력창 위 영역은 살아 있게 한다.
    // 옆 패널은 채팅 칸을 좁히므로 저절로 열지 않고, /goal-pane 을 입력할 때만 연다
    await $.command.register({ name: 'goal-pane', description: '지금 의도와 지난 의도를 옆 패널에 연다' }).catch(() => undefined)

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
        : `패널을 열었지만 이 화면에는 그려지지 않았습니다. 까닭: ${opened.reason} (${where}) 의도는 입력창 위 영역과 대화 안의 도구 줄 아래 카드로도 보입니다.`,
    }
  }).catch(() => ({ text: '패널을 열지 못했습니다.' }))

  // 대화 안에서도 보이도록, 적는 도구 줄 아래에 이번에 적은 의도 · 가정 · 확인 질문을 카드로 그린다. 목표는 세션 제목에만 둔다
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.props.tool !== TOOL_FULL) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const row = await next(e)
    const req = toRequest((e.props.input ?? {}) as Record<string, unknown>, '')
    if (!req) return row

    return (
      <Box flexDirection="column" borderStyle="round" paddingX={1}>
        {row}
        {intentTree({ Box, Text }, req)}
      </Box>
    )
  })

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)

    return { sections: [...composed.sections, { id: 'goal-pane:rule', text: RULE, scope: 'session' as const }] }
  })

  // 다른 플러그인이 시스템 프롬프트 단계를 먼저 처리해 위 지침이 빠질 수 있다.
  // 그래서 사용자 메시지마다 짧은 지침을 함께 붙인다 (사용자에게는 보이지 않는다)
  // ✓ · ✗로 표시한 가정은 바로 보내지 않고(가정이 여럿일 수 있고, 잘못 누르면 풀 수 있게) 사용자의 다음 메시지에 함께 싣는다(2026-11-12 · 11-13 사용자)
  on('prompt.submit', async ($, e, next) => {
    if (e.command || e.isMeta) return next(e)
    const list = await read($, requests)
    const now = list[list.length - 1]
    const fromPerson = !e.origin || !MACHINE_ORIGINS.has(e.origin.kind)
    const marked = fromPerson && now ? marksFor(await read($, marksAtom), now) : { right: [], wrong: [] }
    const text = (ix: number[]) => ix.map(i => (now?.assumptions ?? [])[i] ?? '').filter(Boolean)
    const right = text(marked.right)
    const wrong = text(marked.wrong)
    // 번호 · 개수 없이 가정 글만 「」로 묶는다. 무엇이 맞고 틀렸는지만 필요하다(2026-11-13 사용자)
    const quoted = (xs: string[]) => xs.map(x => `「${x}」`).join(', ')
    const parts = [
      right.length ? `맞다고 확정한 가정: ${quoted(right)}. 사용자가 확정했으니 다시 묻지 말고 그대로 진행한다.` : '',
      wrong.length ? `틀렸다고 표시한 가정: ${quoted(wrong)}. 이 가정대로 진행하지 말고, 이번 메시지와 함께 바로잡아 반영한다.` : '',
    ].filter(Boolean)
    const extra = parts.length ? [`사용자가 입력창 위 영역에서 앞 의도(「${now?.title ?? ''}」)의 가정을 표시했다. ${parts.join(' ')}`] : []

    const goal = await read($, goalAtom)
    const r = await next({ ...e, context: [...(e.context ?? []), ...extra, nudge(goal?.goal)] })
    if (parts.length && !r.drop) {
      await update($, marksAtom, () => null)
      await keep($, { at: new Date().toISOString(), kind: '가정 표시', intent: now?.title ?? '', right, wrong }).catch(() => undefined)
    }

    return r
  })

  // 상태 줄과 알림은 쓰지 않는다: 상태 줄은 글이 잘리고, 알림은 쌓여서 보지 않게 된다(2026-11-12 사용자)
  on('tool.call', { tool: TOOL_FULL }, async ($, e) => {
    const input = e as unknown as Record<string, unknown>
    const at = new Date().toISOString()
    const req = toRequest(input, at)
    const old = await read($, goalAtom)
    const goal = nextGoal(old, input, at)
    if (!req && !goal) return { deny: '이번 요청을 어떻게 이해했는지(title)를 한 문장으로 적어 주세요.' }
    // 넓어지거나 바뀌었다고 판단했는데 새 목표가 없으면, 판단과 제목이 어긋난 채 남지 않게 다시 부르게 한다
    if (old && isGoalMove(input) && !goal) {
      return { deny: `fit 을 ${fitOf(input.fit) || '변경'}(으)로 판단했다면 goal 에 지금 목표(「${old.goal}」)와 다른 새 목표를, why 에 까닭을 함께 적어 다시 불러 주세요.` }
    }
    const fit = fitOf(input.fit)

    if (goal) await update($, goalAtom, () => goal)
    const list = req ? await update($, requests, l => [...l, req].slice(-50)) : await read($, requests)
    const now = goal ?? old

    // 저장: 화면에 내지 않는 근거와 까닭까지 한 줄로. 제목용 파일은 목표가 정해지거나 바뀔 때만
    const problems: string[] = []
    await keep($, {
      at,
      kind: goal ? (goal.n === 1 ? '목표 정함' : '목표 바뀜') : '의도',
      goal: now?.goal ?? '',
      ...(fit ? { fit } : {}),
      ...(goal && goal.n > 1 ? { previous: old?.goal ?? '', why: goal.why } : {}),
      ...(req
        ? { intent: req.title, assumptions: req.assumptions ?? [], question: req.question ?? '', original: req.original, reason: req.reason }
        : {}),
    }).catch(() => problems.push('이해한 까닭을 저장하지 못했습니다.'))
    if (goal) await markTitle($, goal.goal, goal.n > 1).catch(() => problems.push('제목용 목표를 적지 못했습니다.'))

    const goalNote = goal ? (goal.n === 1 ? ' 목표를 정했습니다.' : ` 목표가 바뀌었습니다(${goal.n}번째 목표).`) : ''
    const attached = await $.session.surfaces().catch(() => [] as readonly string[])

    return {
      result: `적었습니다 (의도 ${list.length}번째).${goalNote}${problems.length ? ' ' + problems.join(' ') : ''}${now ? '' : ' 아직 목표가 없습니다: 다음에 goal 을 함께 적어 주세요.'} 연결된 화면: ${attached.length > 0 ? attached.join(', ') : '없음'}.`,
    }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: 'goal-pane: 저장하지 못했습니다. 답은 계속 써도 됩니다.' },
  )

  // 입력창 바로 위 영역(엔진 이름 AbovePrompt): 의도 · 가정 · 확인 질문만. 목표는 세션 제목에 있다. 접기([-])는 엔진이 그린다
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const list = await read($, requests)
    const now = list[list.length - 1]
    if (!now) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    const marked = marksFor(await read($, marksAtom), now)
    const toggle = (i: number, kind: MarkKind) => {
      void update($, marksAtom, old => toggleMark(old, now.said_at, i, kind))
    }

    return intentTree({ Box, Text, Button }, now, { ...marked, toggle })
  })

  // /goal-pane 옆 패널: 지금 의도와 지난 의도. 목표는 세션 제목에만 둔다
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, requests)
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
    const marked = marksFor(await read($, marksAtom), now)

    return (
      <Box flexDirection="column" gap={1}>
        {intentTree({ Box, Text }, now, marked)}
        {older.length > 0 && (
          <Box flexDirection="column">
            <Text size="caption" dimColor>
              지난 의도 (최근 것부터)
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
