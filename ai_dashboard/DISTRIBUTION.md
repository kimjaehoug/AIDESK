# AI Desk 배포

## 사용 환경

macOS 13 이상, Apple Silicon 및 Intel Mac. Python 3.14.7 universal2 실행 환경과 화면 라이브러리를 앱 안에 포함합니다. AI 서비스의 CLI, 앱, 로그인은 각 사용자가 준비합니다. 서버에는 Python 3가 필요합니다. 플래너와 루틴은 연결 없이 사용할 수 있습니다.

`.app`은 자기 내부의 상대 경로로 실행합니다. 응용 프로그램 폴더, 사용자 이름, Homebrew 설치 위치가 달라도 개발자 머신의 Python 경로를 사용하지 않습니다. 도구는 PATH, Homebrew, 사용자 설치, nvm, VS Code/Cursor 확장 및 일반 앱 설치 위치에서 찾습니다. 첫 실행은 전면 창과 시작 안내를 표시하고, 이후 바탕화면에서 시작합니다.

## 포함하는 파일

배포 빌더는 서버, 저장 모델, 세션 연결, 도구 탐색, 화면, PTY helper, native host, vendor 라이브러리, 공식 Python 런타임과 라이선스만 복사합니다. SQLite 일정 DB, SSH config/키/소켓, 세션 데이터, 작업 로그와 사용자 홈 파일은 복사하지 않습니다. 사용자마다 `~/Library/Application Support/AI Desk`에 새 저장소를 만듭니다. 기존 데이터가 있으면 유지합니다.

## 다시 빌드하기

Python 공식 macOS installer: <https://www.python.org/ftp/python/3.14.7/python-3.14.7-macos11.pkg>

공식 release 페이지: <https://www.python.org/downloads/release/python-3147/>

SHA-256: `70c5239ad2d62925d2947e46921d0ddd3d35be3d2f0a2d50db33da507dbcb419`

다운로드 후 해시를 확인하고 `pkgutil --expand-full`로 별도 작업 폴더에 풀어 주세요. 시스템에 Python installer를 실행하지 않아도 됩니다. Xcode command line tools가 있는 Mac에서:

```sh
python3 build_release.py --python-framework '/path/to/extracted/Python_Framework.pkg/Payload/Versions/3.14' --output '/path/to/new-release-folder'
```

출력은 `AI Desk.app`, Applications 링크와 안내문을 담은 DMG, SHA-256 및 서명 상태를 담은 `release.json`입니다. 런타임 동적 라이브러리 경로를 앱 내부로 옮기고 두 CPU용 native host를 합칩니다. 기존 배포본 덮어쓰기는 피하도록 새 출력 폴더를 사용합니다.

## 정식 배포

현재 빌드는 개발용 ad hoc 서명입니다. Apple 발급 Developer ID 인증서가 없으므로 타인의 Mac에서 Gatekeeper를 통과하는 정식 배포본으로 간주하면 안 됩니다. Apple 보안 설정을 해제하는 설치 스크립트는 제공하지 않습니다.

배포용 인증서와 기존 notarization keychain profile이 준비되면:

```sh
python3 build_release.py --python-framework '/path/to/framework/Versions/3.14' --output '/path/to/new-release-folder' --identity 'Developer ID Application: YOUR NAME (TEAMID)' --notary-profile 'AI-Desk-Notary'
```

빌더는 내부 바이너리부터 Developer ID로 서명하고 DMG를 Apple에 제출한 뒤 공증 티켓을 붙입니다. 인증서·비밀번호·Apple 계정은 소스나 배포본에 저장하지 않습니다. 공증에 실패하면 빌드가 실패하며 성공으로 기록하지 않습니다.

Apple 안내: <https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution>

## 배포 전 확인 범위

빌드가 완료되었다고 별도 Intel Mac이나 최소 macOS에서 실제 사용을 확인했다는 뜻은 아닙니다. 정식 배포 전에는 두 CPU의 실제 Mac에서 최초 실행, Dock 재열기, 한글 입력, 로컬 CLI, SSH 로그인, 세션 복구와 데이터 유지까지 확인해야 합니다.

## 라이선스

Python: 앱 안의 `PYTHON-LICENSE.txt`. xterm.js 및 Markdown-it: `vendor`의 MIT 라이선스. Python은 공식 설치 패키지의 라이브러리와 표준 라이브러리를 사용하며 사용자 설치 패키지를 포함하지 않습니다.
