# AI Desk · Desktop

## 다른 Mac에 설치하기

배포용 파일은 `dist/v1.0.1/AI-Desk-1.0.1-universal.dmg`입니다. macOS 13 이상에서 Intel과 Apple Silicon을 지원하도록 구성했습니다. Python이 앱에 포함되고 첫 실행에 연결 준비 안내가 나옵니다. DMG 안의 앱을 응용 프로그램으로 드래그한 뒤 여세요. 현재 버전은 Developer ID 서명·Apple 공증 전이므로 다른 Mac에서 실행이 차단될 수 있습니다. 정식 배포 절차와 빌드 방법은 `DISTRIBUTION.md`, 사용자 안내는 `START_HERE.txt`에 있습니다.

바탕화면에 직접 표시되는 macOS 대시보드입니다. 제목줄 없는 macOS 전용 창을 일반 프로그램 뒤에 배치하고 각 Desktop Space에서 유지합니다. Python은 Todo 저장과 SSH 조회를 담당하며, 화면과 입력은 macOS WebKit과 AppKit이 처리합니다. 외부 웹사이트를 사용하지 않습니다.

## 실행과 배치

바탕화면 `AI Desk/AI Desk.app`을 여세요. 일반 프로그램을 내려 바탕화면을 보면 대시보드를 직접 사용할 수 있습니다. 상단 가운데 빈 공간을 드래그해 위치를 옮길 수 있습니다. `위치 조정`으로 전면에서 배치한 뒤 `배치 완료`로 바탕화면에 고정하세요. 위치와 라이트/다크 테마는 저장됩니다. 종료는 설정에서 가능합니다.

## 날짜·시간 계획

달력에서 날짜를 고른 뒤 `+ 할 일`을 누릅니다. 제목, 날짜, 시작·종료 시각, 메모를 저장하면 시간순으로 정렬되고 달력에 점이 표시됩니다. 카드 오른쪽 원으로 완료 체크, 카드 클릭으로 수정합니다. 삭제는 보관 처리이며 아래 `삭제 되돌리기`로 복구할 수 있습니다. 일정과 테마는 `~/Library/Application Support/AI Desk/planner.sqlite3`에 저장됩니다. Apple 캘린더/iCloud 동기화는 포함하지 않습니다. 단축키는 Command-N(할 일 추가), Command-D(테마 전환)입니다.

## SSH 서버 세션

`~/.ssh/config`의 Host 별칭을 읽고 연결 가능 여부를 확인합니다. 서버를 선택해 Claude Code, Codex, tmux 세션 목록을 조회합니다. 서버에 Python 3가 필요합니다. SSH 키가 없으면 서버 옆 `↗`에서 터미널을 열고 로그인하세요. OpenSSH ControlMaster 연결을 감지하면 세션 목록을 자동으로 조회합니다. 비밀번호는 터미널에서만 입력하고 앱은 저장하지 않습니다. 마지막 터미널을 닫은 뒤 공유 연결은 최대 10분간 유지됩니다. 서버 추가는 `+ 관리`에서 가능합니다.

- Claude: 선택한 세션을 이어서 실행하고 요청을 보냅니다.
- Codex: 선택한 원격 세션을 터미널에서 이어서 열고 요청을 복사합니다.
- tmux: 기존 세션에 연결하고 요청을 복사합니다.
- SSH HostKey 검증과 AI 도구의 권한 확인을 유지합니다.

서버 세션 조회에는 먼저 해당 서버의 SSH 연결과 인증이 필요합니다.

## 로컬 AI

Claude Code와 Cursor 메타데이터를 읽기 전용으로 표시합니다. Claude는 특정 세션을 이어서 실행합니다. ChatGPT와 Cursor는 프롬프트 복사와 앱 열기를 제공하며 대상 대화 선택과 붙여넣기는 앱에서 합니다. 기록 시각 및 밤사이(전날 20시–오늘 09시) 수정 감지를 표시합니다. 세션 파일의 수정 시각만으로 AI 작업의 완료 여부를 단정하지 않습니다.

## 구현

- `DesktopHost.swift` / `DesktopHost`: macOS 바탕화면 창과 WebKit
- `index.html`: 대시보드 디자인, 달력, Todo 입력
- `server.py`: 로컬 전용 API와 작업 연결. 127.0.0.1의 임시 포트에만 바인딩하며 요청 토큰과 Host를 검사합니다.
- `model.py`: SQLite 저장과 읽기 전용 SSH 메타데이터 조회
- `install.py`: 기존 플래너 데이터를 유지하며 앱 갱신

이전 Tkinter 구현은 소스 참고용으로 남아 있고 실행 앱은 새 네이티브 호스트를 사용합니다.

## Pin and in-dashboard sessions (v4)

- **핀 고정** toggles the native AppKit floating window level and remembers the setting across launches. The placement button still controls desktop/editing mode.
- Select a local or SSH session, then **내역 보기 · 여기서 채팅**. History is read only when opened/refreshed, from the existing session files/database. Large histories show the latest 250 messages within the last 32 MiB; individual message previews are capped at 24,000 characters.
- **채팅 연결** explicitly resumes Claude or Codex in an embedded xterm.js PTY, or attaches to the selected remote tmux session. Enter sends keyboard input; original CLI permission prompts remain in place. Stop another client for the same AI session before resuming here.
- **접기** hides the panel while its process continues. **연결 종료**, or exiting AI Desk, closes processes launched by this dashboard. tmux sessions remain on the remote host when the attachment ends.
- Cursor GUI conversation history is read locally; continuing that GUI conversation opens Cursor. Cloud ChatGPT conversations are not synchronized. Local Codex tasks from the ChatGPT app appear as Codex sessions.
- xterm.js is bundled from the locally installed Cursor distribution; its MIT license is included at vendor/XTERM-LICENSE. No CDN is used.
- Loopback HTTP APIs require a random launch token; terminal launch resolves the requested session against the displayed server cache. Paths/cwd from client requests are not executed directly.


## Session organization and daily routines (v5)

- Session pencil / **제목 수정** sets an AI Desk display alias; **원래 제목** removes it. This does not rewrite the source agent's files. Aliases and stars use the tuple (provider, SSH host, session ID) so identical IDs on different hosts do not collide.
- **★ 즐겨찾기** collects starred sessions across the Mac and SSH servers. Previously saved discovery metadata keeps favorites visible offline; opening a remote history/terminal still requires SSH authentication.
- Conversation previews render Markdown headings, emphasis, lists, tables, quotes, and fenced code. Code blocks have copy buttons; tables scroll within their message. **넓게 보기** gives history the full panel width. Raw HTML is escaped and remote images do not load automatically. Markdown-it's MIT license is bundled under vendor/MARKDOWN-IT-LICENSE.
- Check **매일 루틴으로 반복** in the Todo form. The selected date is the first occurrence; start/end time and notes repeat daily. Occurrences have independent completion/edit/delete state and are materialized idempotently for the month being viewed plus the current day. Existing planner records remain intact.
- **↻ 루틴** lists active routines and allows deleting a routine. This stops repetition and archives its incomplete occurrences dated today or later. Past records and completed occurrences remain. Deleting a single occurrence skips only that date.


## Automatic refresh and day/week/month planners (v6)

- **↻ 자동 ON/OFF** controls session discovery refresh. Intervals: 15/30/60/120/300 seconds, default 30. Settings are stored in the planner database. Local metadata and connected SSH hosts are reread; failed SSH connections use retry backoff. A cached control socket is used; no credentials are stored.
- **새로** explicitly refreshes the current source, including local metadata (favorites refresh their local/server sources). The UI shows pending refresh and last successful refresh time.
- When auto refresh is on, open conversation history follows new source activity without resuming/sending AI requests. Rendering preserves the reading position unless already near the bottom. An unchanged message history is not rerendered. Live terminal output keeps its existing separate stream.
- **일 / 주 / 월** share the same Todo and routine records. The most recently selected view is remembered. Previous/Today/Next navigate by the active period.
- Week view starts Monday, lays events on a 24-hour timeline, displays overlaps in separate lanes, and supports completion/editing. Click a blank half-hour slot to create an event with its date/time filled in.
- Month view displays six weeks, including adjacent dates, up to three event previews per day, and a link to additional items. Date numbers open day view; + or empty cell creates an event for that date.
- Routine materialization includes the whole displayed range (up to 63 days), so weeks/month grids spanning month/year boundaries include recurring events. Each occurrence remains independently editable/completable.
- UI status polling is lightweight and only replaces planner/session markup when its displayed content has changed, retaining scroll position during background updates.


## Unified conversation (v7)

- Session history, connect/disconnect, and message composer now share one full-width conversation panel. Markdown history refreshes every three seconds while connected, preserving reading position. Saved replies are updated in place as the CLI writes its session log. New messages reveal progressively without replacing the entire conversation.
- The standard textarea supports Korean IME composition. Enter submits only outside composition; Shift+Enter adds a line. Drafts survive switching tasks during this app run; a failed send retains its text. Clicking the input gives the native desktop window keyboard focus without changing its layer.
- Messages go to the existing dashboard PTY in UTF-8, using bracketed paste when enabled by the CLI, followed by a separate submit key. Control characters are rejected. Multiline messages require bracketed paste support.
- **실시간 제어** opens an inline drawer for login, permission selections, CLI status, arrow keys, Enter, Esc, and interrupt. It does not approve prompts automatically. tmux opens this drawer by default; Cursor GUI sessions still continue through **앱에서 열기**.


## Scoped folder trust automation

- **폴더 자동 신뢰 설정** asks for an explicit choice showing the server and exact session cwd. The approval is stored locally per host and cwd, and can be disabled from the same button. It starts off for every new folder.
- Only Claude's recognizable Security guide prompt, with that exact folder and the selected No/Yes option visible, is handled. The app sends Up then Enter once per attached connection (or Enter if Yes is selected). Different folders and tool permission prompts still require a choice.


## Chat type size and workspace terminal

- Default chat text is 12px. **A− / A+** and the numeric input set 10–20px; body text, headings, tables, code, and composer scale together. The size is stored in the planner database and survives random loopback ports/app relaunches.
- Opening a session replaces the calendar/server sidebar with a separate shell at that session's host and cwd. Remote connections reuse SSH authentication; local sessions get a local login shell. Shell launch targets are resolved against server discovery metadata, not client paths.
- **캘린더 보기** temporarily reveals the planner sidebar; **서버 터미널로 돌아가기** restores the shell. Closing the session view restores the calendar. Shells remain alive while hidden; **종료** closes that shell, **재연결** resumes or replaces it. App exit closes dashboard shell processes.


## Motion and progressive replies

- Claude replies sent from the dashboard are mirrored from the existing xterm output while they are being generated (approximately 180ms polling). The latest reply after the submitted prompt appears in a live bubble; terminal tool output, spinners, and permission controls are excluded. No extra AI request or API credential is used. Unsupported/truncated terminal layouts fall back to saved history with progressive text display.
- Confirmed Markdown replaces the live preview. Conversation nodes are reused by message ID, so refreshes do not replay older replies, lose selections, or rebuild the entire view. Scrolling follows new content only when the reader is already near the bottom. Initial history is shown immediately with a short entrance transition.
- Cards, session transitions, messages, calendar selections, dialogs, focus and hover states have motion. Waiting replies show animated dots and text reveals with a caret. OS Reduce Motion disables motion and typing delays.
- Settings include animation and streaming toggles, three reveal speeds, and a local effect preview. Preferences are saved with the planner. Codex/Cursor and background updates use progressive saved history; their GUI/provider token streams are not directly available.


## Codex 세션에 직접 메시지 보내기

- Codex 세션을 선택하고 대화 화면의 **보내기**를 누릅니다. 실시간 터미널 연결 없이도 해당 세션 UUID로 메시지를 전달합니다.
- 설치된 Codex의 `queue --thread … --message …` 기능을 사용합니다. 기존 로그인과 세션 설정을 그대로 사용하며, 실행 중인 작업이 있으면 다음 차례에 처리됩니다.
- 한국어와 여러 줄 메시지를 지원합니다. 전송 확인에 실패하면 입력을 유지하고 오류를 표시합니다. 확인 시간 초과 시 자동 재전송하지 않습니다.
- 로컬과 SSH를 지원합니다. 서버의 CLI가 `queue`를 지원하지 않으면 업데이트 안내가 표시됩니다. SSH 인증은 기존 연결을 재사용하고 메시지는 원격 명령 문자열에 넣지 않고 표준 입력으로 전달합니다.
- 권한 요청과 실행 상태는 Codex 앱이나 **실시간 제어 연결**에서 확인합니다. Cursor의 메시지 전송은 아직 지원하지 않습니다.
