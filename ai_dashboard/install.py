"""Update the user's authorized AI Desk app without changing planner data."""
import argparse
import json
import pathlib
import plistlib
import shutil
import sqlite3

parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');parser.add_argument('--ui-only',action='store_true');parser.add_argument('--app-bundle',type=pathlib.Path);parser.add_argument('--destination',type=pathlib.Path);parser.add_argument('--trust-folder-host');parser.add_argument('--trust-folder-path');args=parser.parse_args()
if args.trust_folder_host or args.trust_folder_path:
 if not args.trust_folder_host or not args.trust_folder_path:parser.error('서버와 폴더를 함께 지정하세요.')
 planner=pathlib.Path.home()/'Library/Application Support/AI Desk/planner.sqlite3'
 conn=sqlite3.connect(planner)
 key=json.dumps([args.trust_folder_host,args.trust_folder_path],ensure_ascii=False)
 row=conn.execute('SELECT value FROM settings WHERE key=?',('trusted_auto_folders',)).fetchone()
 folders=json.loads(row[0]) if row else []
 if key not in folders:folders.append(key)
 conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('trusted_auto_folders',json.dumps(folders)));conn.commit();conn.close()
 print('승인된 서버/폴더 자동 신뢰를 저장했습니다.');raise SystemExit(0)
source=pathlib.Path(__file__).resolve().parent
legacy=pathlib.Path.home()/'Desktop/AI Desk/AI Desk.app'
app=args.destination or (legacy if args.ui_only and legacy.exists() else pathlib.Path.home()/'Applications/AI Desk.app')
app=app.expanduser().resolve()
if args.ui_only:
 resources=app/'Contents/Resources'
 if not (resources/'index.html').is_file():parser.error('기존 AI Desk 앱이 없습니다. --destination으로 앱 위치를 지정하세요.')
 shutil.copy2(source/'index.html',resources/'index.html')
 print('개발용 화면 갱신 완료. 배포 앱을 수정하면 서명이 무효화되므로 배포용은 다시 빌드하세요.');raise SystemExit(0)
if not args.app_bundle:parser.error('--app-bundle에 build_release.py가 만든 AI Desk.app을 지정하세요. DMG는 앱을 응용 프로그램으로 드래그해 설치합니다.')
bundle=args.app_bundle.expanduser().resolve()
if bundle==app:parser.error('원본과 설치 위치가 같습니다.')
try:info=plistlib.loads((bundle/'Contents/Info.plist').read_bytes())
except (OSError,ValueError):parser.error('올바른 macOS 앱 번들이 아닙니다.')
if info.get('CFBundleIdentifier')!='org.aidesk.desktop' or info.get('CFBundleExecutable')!='DesktopHost':parser.error('배포 빌더가 만든 AI Desk 앱을 선택하세요.')
required=['Contents/MacOS/DesktopHost','Contents/Resources/server.py','Contents/Resources/runtime.py','Contents/Resources/vendor/xterm.js','Contents/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python']
if any(not (bundle/name).is_file() for name in required):parser.error('앱에 필수 실행 파일이 빠져 있습니다. 최신 배포본으로 다시 빌드하세요.')
if args.verify:
 import subprocess,sys
 subprocess.run([sys.executable,str(source/'tests/distribution_smoke.py'),str(bundle)],check=True)
app.parent.mkdir(parents=True,exist_ok=True)
import datetime,tempfile,subprocess,sys
with tempfile.TemporaryDirectory(prefix='.ai-desk-install-',dir=app.parent) as temporary:
 staged=pathlib.Path(temporary)/'AI Desk.app'
 shutil.copytree(bundle,staged,symlinks=True)
 backup=None
 if app.exists():
  stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
  backup=app.with_name(app.stem+'.backup-'+stamp+'.app')
  app.rename(backup)
 try:staged.rename(app)
 except OSError:
  if backup and backup.exists():backup.rename(app)
  raise
print('설치 완료: '+str(app))
if backup:print('이전 앱 보관: '+str(backup))
print('일정·설정과 SSH 인증 정보는 변경하지 않았습니다. 실행 중인 이전 앱을 종료한 뒤 새 앱을 여세요.')
