"""Update the user's authorized AI Desk app without changing planner data."""
import argparse
import json
import pathlib
import plistlib
import shutil
import sqlite3

parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');parser.add_argument('--preview-todo',action='store_true');parser.add_argument('--ui-only',action='store_true');parser.add_argument('--trust-folder-host');parser.add_argument('--trust-folder-path');args=parser.parse_args()
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
folder=pathlib.Path.home()/'Desktop/AI Desk';app=folder/'AI Desk.app';resources=app/'Contents/Resources';resources.mkdir(parents=True,exist_ok=True)
if args.ui_only:
 shutil.copy2(source/'index.html',resources/'index.html');shutil.copy2(source/'index.html',folder/'index.html')
 print('AI Desk typography updated; window size unchanged.');raise SystemExit(0)
for name in ('dashboard.py','model.py','native.py','server.py','session_io.py','runtime.py','pty_helper.py','index.html','README.md'):
 shutil.copy2(source/name,resources/name);shutil.copy2(source/name,folder/name)
shutil.copytree(source/'vendor',resources/'vendor',dirs_exist_ok=True)
shutil.copytree(source/'vendor',folder/'vendor',dirs_exist_ok=True)
(app/'Contents/MacOS').mkdir(parents=True,exist_ok=True)
shutil.copy2(source/'DesktopHost',app/'Contents/MacOS/DesktopHost');(app/'Contents/MacOS/DesktopHost').chmod(0o755)
logs=pathlib.Path.home()/'Library/Application Support/AI Desk';logs.mkdir(parents=True,exist_ok=True)
planner=logs/'planner.sqlite3';backup=logs/'planner.pre-v5.sqlite3'
if planner.exists() and not backup.exists():
 original=sqlite3.connect(planner);saved=sqlite3.connect(backup)
 try:original.backup(saved)
 finally:saved.close();original.close()
launch=app/'Contents/MacOS/launch';launch.parent.mkdir(parents=True,exist_ok=True)
launch.write_text('#!/bin/zsh\ncd "'+str(resources)+'"\nexec /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 server.py >> "$HOME/Library/Application Support/AI Desk/runtime.log" 2>&1\n');launch.chmod(0o755)
fallback=folder/'AI Desk.command';fallback.write_text(launch.read_text());fallback.chmod(0o755)
info=dict(CFBundleName='AI Desk',CFBundleDisplayName='AI Desk',CFBundleIdentifier='local.gimjaehong.aidesk',CFBundleExecutable='launch',CFBundlePackageType='APPL',CFBundleVersion='7.1',LSUIElement=False)
(app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
conn=sqlite3.connect(logs/'planner.sqlite3');conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)');conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('start_in_edit',json.dumps(args.verify)));conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('preview_todo',json.dumps(args.preview_todo)));conn.commit();conn.close()
print('AI Desk updated; planner data preserved.')
