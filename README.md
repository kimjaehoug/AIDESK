# AI Desk

바탕화면에서 일정과 AI 작업을 함께 관리하는 macOS 앱입니다.

## 설치

[최신 릴리스](https://github.com/kimjaehoug/AIDESK/releases/latest)에서 `AI-Desk-1.0.0-universal.dmg`를 다운로드하고, DMG 안의 **AI Desk**를 **Applications**로 드래그하세요.

- macOS 13 이상, Apple Silicon 및 Intel Mac용 universal 빌드
- Python 실행 환경 포함
- AI 서비스 로그인과 CLI 설치는 사용자별로 필요
- 현재 v1.0.0은 Developer ID 서명과 Apple 공증 전입니다. 다른 Mac에서 실행이 차단될 수 있으며, 별도 Intel Mac에서의 실행 확인은 아직 진행하지 않았습니다.

## 주요 기능

- 바탕화면 배치, 드래그 이동, 크기 조절, 핀 고정
- 라이트·다크 모드와 글씨 크기 설정
- 일·주·월 플래너, 시간별 할 일, 매일 반복 루틴
- 로컬 및 SSH의 Claude·Codex·tmux 세션 조회와 연결
- 세션 제목 별칭과 즐겨찾기
- Markdown 대화 표시, 메시지 전송, 실시간 터미널, 자동 재연결
- 애니메이션 및 답변 스트리밍 표시 설정

Cursor 대화는 로컬 내역 조회와 앱 열기를 지원합니다. ChatGPT 앱은 프롬프트 복사와 앱 열기를 지원하며, 클라우드 대화 동기화는 포함하지 않습니다.

일정과 설정은 각 사용자의 `~/Library/Application Support/AI Desk`에 저장됩니다. 저장소와 배포본에는 개인 대화 기록, 일정 DB, SSH 키·설정이나 로그인 정보가 포함되지 않습니다.

## 소스와 빌드

앱 소스는 [`ai_dashboard`](ai_dashboard)에 있습니다.

- [기능 및 사용 안내](ai_dashboard/README.md)
- [사용자 시작 안내](ai_dashboard/START_HERE.txt)
- [배포 빌드 및 서명 절차](ai_dashboard/DISTRIBUTION.md)

빌드에는 macOS, Xcode Command Line Tools와 공식 Python framework가 필요합니다. 다음 명령은 추출한 framework를 앱 안에 포함하고 두 CPU용 네이티브 호스트와 DMG를 만듭니다.

```sh
python3 ai_dashboard/build_release.py \
  --python-framework '/path/to/Python.framework/Versions/3.14' \
  --output '/path/to/new-release-folder'
```

완성된 앱과 DMG는 Git 이력에 넣지 않고 GitHub Releases에 첨부합니다. 포함된 외부 라이브러리의 라이선스는 [`ai_dashboard/vendor`](ai_dashboard/vendor)와 배포 앱의 `PYTHON-LICENSE.txt`에 있습니다.
