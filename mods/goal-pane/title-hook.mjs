// 세션 제목 맨 뒤 대괄호에 목표를 붙이는 설정 훅(settings.json 의 UserPromptSubmit 명령 훅).
// 모드의 제목 훅은 데스크톱 앱에서 다른 플러그인(cc-plugin-sec-default)에 막혀 돌지 않아서 이 훅이 대신한다.
// 규칙: 대괄호 앞은 사용자 몫이라 건드리지 않는다. 이 훅이 마지막으로 붙인 글로 제목이 끝날 때만 그 부분을 갈아 끼우고,
// 아니면(사용자가 그 부분을 고쳤으면) 그대로 두고 뒤에 새로 붙인다.
// 목표가 바뀐 뒤 첫 메시지에는 「[바뀜]」을 붙이고 그다음 메시지에 뗀다.
// 무슨 일이 있어도 메시지를 막지 않도록 늘 0 으로 끝낸다.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

let raw = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', d => (raw += d))
process.stdin.on('end', () => {
  try {
    run(JSON.parse(raw))
  } catch {
    // 제목은 덤이다: 실패해도 아무것도 내지 않는다
  }
  process.exit(0)
})

function run(input) {
  const id = typeof input.session_id === 'string' ? input.session_id : ''
  const current = typeof input.session_title === 'string' ? input.session_title : ''
  if (!id || !current) return

  const file = path.join(os.homedir(), '.claude', 'goal-pane', '제목', `${id}.json`)
  if (!fs.existsSync(file)) return
  const st = JSON.parse(fs.readFileSync(file, 'utf8'))
  if (!st.goal) return

  const suffix = `${st.flag === 'pending' ? ' [바뀜]' : ''} [${st.goal}]`
  const front = st.lastSuffix && current.endsWith(st.lastSuffix) ? current.slice(0, -st.lastSuffix.length) : current
  const title = front.trimEnd() + suffix

  fs.writeFileSync(file, JSON.stringify({ ...st, lastSuffix: suffix, flag: st.flag === 'pending' ? 'shown' : 'none' }))
  if (title !== current) {
    process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'UserPromptSubmit', sessionTitle: title } }))
  }
}
