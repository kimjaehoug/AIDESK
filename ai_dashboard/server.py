#!/usr/bin/env python3
import datetime as dt
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import pathlib
import secrets
import signal
import sys
import shlex
import subprocess
import threading
import time
import urllib.parse
import uuid
from runtime import executable_for,app_for,setup_status
from session_io import read_history,session_command,shell_command,TerminalSession,queue_codex_message
from model import Store,local_sessions,remote_sessions,ssh_hosts,control_path

ROOT=pathlib.Path(__file__).resolve().parent
HOME=pathlib.Path.home()
DATA=pathlib.Path(os.environ.get('AI_DESK_DATA',str(HOME/'Library/Application Support/AI Desk')))
DATA.mkdir(parents=True,exist_ok=True)
TOKEN=secrets.token_hex(32)
store=Store(DATA)
mutex=threading.RLock()
hosts=list(dict.fromkeys(ssh_hosts()+store.setting('extra_hosts',[])))
remotes={};statuses={};errors={};busy=set()
locals_cache=local_sessions()
terminals={};session_terminals={}
refreshed={'local':time.time()};attempts={};failures={};local_busy=False;local_error=''

def connect(host):
 with mutex:
  if host in busy:return
  busy.add(host);attempts[host]=time.time()
  if host not in remotes:statuses[host]='조회 중'
  errors.pop(host,None)
 def work():
  try:
   data=remote_sessions(host)
   with mutex:remotes[host]=data;statuses[host]='연결됨';refreshed[host]=time.time();failures[host]=0
  except Exception as exc:
   with mutex:statuses[host]='인증 필요' if 'Permission denied' in str(exc) else '접속 불가';errors[host]=str(exc);failures[host]=failures.get(host,0)+1
  finally:
   with mutex:busy.discard(host)
 threading.Thread(target=work,daemon=True).start()

def refresh_local():
 global locals_cache,local_busy,local_error
 with mutex:
  if local_busy:return
  local_busy=True
 def work():
  global locals_cache,local_busy,local_error
  try:
   rows=local_sessions()
   with mutex:locals_cache=rows;refreshed['local']=time.time();local_error=''
  except Exception as exc:
   with mutex:local_error=str(exc);refreshed['local']=time.time()
  finally:
   with mutex:local_busy=False
 threading.Thread(target=work,daemon=True).start()

def terminal(command):
 folder=DATA/'launchers';folder.mkdir(exist_ok=True,mode=0o700)
 path=folder/(uuid.uuid4().hex+'.command')
 path.write_text('#!/bin/zsh\n'+command+'\n',encoding='utf-8');path.chmod(0o700)
 subprocess.Popen(['open','-a','Terminal',str(path)])

def launch_session(body):
 s=body.get('session');provider=body.get('provider') or (s or {}).get('provider','ChatGPT');prompt=body.get('prompt','');send=body.get('send',False)
 if s and s.get('host')!='local' and s.get('host') not in hosts:raise ValueError('등록된 서버를 선택하세요.')
 if s and provider in ('Claude','Codex','tmux'):
  args,cwd=session_command(s)
  if send and prompt and provider=='Claude':
   if s['host']=='local':args.append(prompt)
   else:
    # A positional prompt belongs to the resumed agent, not the remote shell.
    request=json.dumps({'provider':provider,'id':s['id'],'cwd':s.get('cwd',''),'prompt':prompt},ensure_ascii=False)
    from session_io import REMOTE_LAUNCH_SOURCE
    args[-1]='exec python3 -c '+shlex.quote(REMOTE_LAUNCH_SOURCE)+' '+shlex.quote(request)
  terminal('cd '+shlex.quote(cwd)+' && '+shlex.join(args));return {'message':'선택한 '+provider+' 세션을 터미널에서 열었습니다.'}
 else:
  name='Cursor' if provider=='Cursor' else 'ChatGPT'
  app=app_for(name)
  if not app:raise ValueError(name+' 앱을 설치한 뒤 다시 열어 주세요. 응용 프로그램 폴더에 넣으면 자동으로 찾습니다.')
  subprocess.Popen(['/usr/bin/open',app])
 return {'message':'세션을 열었습니다. 복사된 요청을 대상 대화에 붙여넣으세요.' if prompt else '앱 또는 세션을 열었습니다.'}

def session_view():
 prefs={(p['provider'],p['host'],p['session_id']):p for p in store.session_preferences()}
 def decorate(session):
  row=dict(session);key=tuple(row[k] for k in ('provider','host','id'));pref=prefs.get(key,{})
  row['original_name']=row['name'];row['name']=pref.get('title') or row['name'];row['favorite']=bool(pref.get('favorite'));return row
 local=[decorate(s) for s in locals_cache];remote={h:[decorate(s) for s in rows] for h,rows in remotes.items()}
 live={tuple(s[k] for k in ('provider','host','id')):s for s in local+sum(remote.values(),[])}
 favorites=[]
 for key,pref in prefs.items():
  if not pref['favorite']:continue
  session=live.get(key)
  if session is None:
   try:session=decorate(json.loads(pref['snapshot']))
   except (ValueError,KeyError,TypeError):continue
   session['cached']=True
  favorites.append(session)
 return local,remote,sorted(favorites,key=lambda s:s.get('time',0),reverse=True)

def resolve_session(body):
 with mutex:
  requested=body.get('session',{})
  if requested.get('host')!='local' and requested.get('host') not in hosts:raise ValueError('등록된 서버를 선택하세요.')
  rows=locals_cache if requested.get('host')=='local' else remotes.get(requested.get('host'),[])
  for row in rows:
   if all(row.get(k)==requested.get(k) for k in ('id','provider','host')):return dict(row)
  for pref in store.session_preferences():
   if pref['favorite'] and all(pref.get(k)==requested.get(r) for k,r in (('provider','provider'),('host','host'),('session_id','id'))):return json.loads(pref['snapshot'])
 raise ValueError('목록에서 세션을 다시 선택하세요.')

def terminal_by_id(key):
 with mutex:term=terminals.get(key)
 if term is None:raise ValueError('터미널 연결을 찾지 못했습니다.')
 return term

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def respond(self,value,status=200):
  data=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def allowed(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and self.headers.get('X-AI-Desk-Token')==TOKEN
 def do_GET(self):
  parsed=urllib.parse.urlparse(self.path)
  if parsed.path=='/' and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and urllib.parse.parse_qs(parsed.query).get('token')==[TOKEN]:
   data=(ROOT/'index.html').read_text().replace('__TOKEN__',TOKEN).encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  if parsed.path in ('/vendor/xterm.js','/vendor/xterm.css','/vendor/markdown-it.min.js') and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and urllib.parse.parse_qs(parsed.query).get('token')==[TOKEN]:
   data=(ROOT/parsed.path.lstrip('/')).read_bytes();self.send_response(200);self.send_header('Content-Type','text/css' if parsed.path.endswith('.css') else 'application/javascript');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  if not self.allowed():self.respond({'error':'Unauthorized'},403);return
  if parsed.path=='/api/terminal/read':
   try:
    q=urllib.parse.parse_qs(parsed.query);self.respond(terminal_by_id(q['id'][0]).read(int(q.get('cursor',['0'])[0])))
   except (ValueError,KeyError) as error:self.respond({'error':str(error)},400)
   return
  if parsed.path=='/api/setup':
   self.respond(setup_status());return
  if parsed.path=='/api/state':
   try:
    query=urllib.parse.parse_qs(parsed.query);month=query.get('month',[dt.date.today().strftime('%Y-%m')])[0]
    with mutex:
     if 'start' in query and 'end' in query:store.ensure_routine_range(query['start'][0],query['end'][0])
     else:store.ensure_routines(month)
     local,remote,favorites=session_view()
     self.respond(dict(tasks=store.tasks(),routines=store.routines(),favorites=favorites,capabilities={"codex_messages":True},settings={'theme':store.setting('theme','light'),'session_auto':store.setting('session_auto',True),'session_interval':store.setting('session_interval',30),'planner_view':store.setting('planner_view','day'),'chat_font':store.setting('chat_font',12),'trusted_auto_folders':store.setting('trusted_auto_folders',[]),'ui_motion':store.setting('ui_motion',True),'ui_stream':store.setting('ui_stream',True),'stream_speed':store.setting('stream_speed',360),'onboarding_complete':store.setting('onboarding_complete',False)},local=local,hosts=hosts,remote=remote,statuses=statuses,errors=errors,refreshed=refreshed,refreshing=list(busy)+(['local'] if local_busy else []),local_error=local_error))
   except ValueError as error:self.respond({'error':str(error)},400)
  else:self.respond({'error':'Not found'},404)
 def do_POST(self):
  if not self.allowed():self.respond({'error':'Unauthorized'},403);return
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length>200000:raise ValueError('입력이 너무 깁니다.')
   body=json.loads(self.rfile.read(length));route=self.path
   if route=='/api/history':self.respond(read_history(resolve_session(body)));return
   if route=='/api/codex/send':
    self.respond(queue_codex_message(resolve_session(body),body.get('text')));return
   if route=='/api/shell/start':
    session=resolve_session(body);key=('shell',session['host'],session.get('cwd',''))
    with mutex:
     term=terminals.get(session_terminals.get(key))
     if term is None or term.proc.poll() is not None:
      if term is not None:term.close();terminals.pop(term.id,None)
      if len(terminals)>=12:raise ValueError('열린 연결이 많습니다. 사용하지 않는 연결을 종료하세요.')
      args,cwd=shell_command(session);term=TerminalSession(args,cwd,cols=45,rows=35);terminals[term.id]=term;session_terminals[key]=term.id
    self.respond({'id':term.id,'host':session['host'],'cwd':session.get('cwd','')});return
   if route=='/api/session/trust-auto':
    session=resolve_session(body)
    if session['provider']!='Claude' or not session.get('cwd'):raise ValueError('작업 폴더를 확인할 수 있는 Claude 세션만 설정할 수 있습니다.')
    key=json.dumps([session['host'],session['cwd']],ensure_ascii=False)
    with mutex:
     folders=store.setting('trusted_auto_folders',[])
     folders=[folder for folder in folders if folder!=key]
     if body.get('enabled') is True:folders.append(key)
     store.set_setting('trusted_auto_folders',folders)
    self.respond({'enabled':key in folders,'cwd':session['cwd']});return
   if route=='/api/terminal/start':
    session=resolve_session(body);key=tuple(session[k] for k in ('provider','host','id'))
    with mutex:
     term=terminals.get(session_terminals.get(key))
     if term is None or term.proc.poll() is not None:
      if term is not None:term.close();terminals.pop(term.id,None)
      if len(terminals)>=12:raise ValueError('열린 연결이 많습니다. 사용하지 않는 연결을 종료하세요.')
      args,cwd=session_command(session);term=TerminalSession(args,cwd);terminals[term.id]=term;session_terminals[key]=term.id
    trust_key=json.dumps([session['host'],session.get('cwd','')],ensure_ascii=False)
    self.respond({'id':term.id,'autoTrust':session['provider']=='Claude' and trust_key in store.setting('trusted_auto_folders',[]),'cwd':session.get('cwd','')});return
   if route.startswith('/api/terminal/'):
    term=terminal_by_id(body['id'])
    if route=='/api/terminal/input':term.write(body['data'])
    elif route=='/api/terminal/message':term.send_message(body['text'],body.get('bracketed',False))
    elif route=='/api/terminal/resize':term.resize(body['cols'],body['rows'])
    elif route=='/api/terminal/close':
     term.close()
     with mutex:terminals.pop(term.id,None)
    else:self.respond({'error':'Not found'},404);return
    self.respond({});return
   with mutex:
    if route=='/api/todo':
     save=store.create_routine if body.get('routine') else store.save_task
     key=save(body['title'],body['date'],body['start'],body['end'],body.get('notes',''),body.get('id'));value={'id':key}
    elif route=='/api/refresh':
     selected=body.get('hosts',[])
     if not isinstance(selected,list) or any(host not in hosts for host in selected):raise ValueError('등록된 서버를 선택하세요.')
     if body.get('local',True):refresh_local()
     for host in selected:connect(host)
     value={}
    elif route=='/api/preferences':
     updates={}
     if 'session_auto' in body:
      if not isinstance(body['session_auto'],bool):raise ValueError('자동 갱신 설정이 올바르지 않습니다.')
      updates['session_auto']=body['session_auto']
     if 'session_interval' in body:
      if type(body['session_interval']) is not int or body['session_interval'] not in (15,30,60,120,300):raise ValueError('올바른 갱신 간격을 선택하세요.')
      updates['session_interval']=body['session_interval']
     if 'chat_font' in body:
      if type(body['chat_font']) is not int or not 10<=body['chat_font']<=20:raise ValueError('글씨 크기는 10~20 사이로 선택하세요.')
      updates['chat_font']=body['chat_font']
     for key in ('ui_motion','ui_stream','onboarding_complete'):
      if key in body:
       if not isinstance(body[key],bool):raise ValueError('화면 효과 설정이 올바르지 않습니다.')
       updates[key]=body[key]
     if 'stream_speed' in body:
      if type(body['stream_speed']) is not int or body['stream_speed'] not in (180,360,720):raise ValueError('글자 등장 속도가 올바르지 않습니다.')
      updates['stream_speed']=body['stream_speed']
     if 'planner_view' in body:
      if body['planner_view'] not in ('day','week','month'):raise ValueError('올바른 플래너 보기를 선택하세요.')
      updates['planner_view']=body['planner_view']
     for key,value in updates.items():store.set_setting(key,value)
     value={}
    elif route=='/api/routine/delete':store.delete_routine(body['id']);value={}
    elif route=='/api/session/update':
     session=resolve_session(body);store.update_session(session,body);value={}
    elif route=='/api/toggle':store.toggle(body['id']);value={}
    elif route=='/api/archive':store.archive(body['id'],body.get('archived',1));value={}
    elif route=='/api/theme':
     if body['theme'] not in ('light','dark'):raise ValueError('유효하지 않은 테마')
     store.set_setting('theme',body['theme']);value={}
    elif route=='/api/host':
     host=body['host'].strip()
     if not host or host.startswith('-') or any(c.isspace() for c in host):raise ValueError('공백 없는 SSH Host 별칭 또는 user@hostname을 입력하세요.')
     if host not in hosts:hosts.append(host);store.set_setting('extra_hosts',hosts)
     value={};connect(host)
    elif route=='/api/connect':
     if body['host'] not in hosts:raise ValueError('등록된 서버가 아닙니다.')
     connect(body['host']);value={}
    elif route=='/api/login':
     host=body['host']
     if host not in hosts:raise ValueError('등록된 서버가 아닙니다.')
     terminal('ssh -o ControlMaster=auto -o ControlPersist=600 -S '+shlex.quote(control_path(host))+' '+shlex.quote(host));value={'message':'터미널에서 로그인하면 세션 목록을 자동으로 조회합니다.'}
    elif route=='/api/open':
     if body.get('session'):body['session']=resolve_session(body)
     value=launch_session(body)
    else:self.respond({'error':'Not found'},404);return
   self.respond(value)
  except (ValueError,KeyError) as error:self.respond({'error':str(error)},400)
  except Exception as error:self.respond({'error':str(error)},500)

def monitor():
 while True:
  time.sleep(2)
  with mutex:
   auto=store.setting('session_auto',True);interval=store.setting('session_interval',30)
   known=list(hosts);now=time.time();local_due=auto and now-refreshed.get('local',0)>=interval and not local_busy
   due=[]
   for host in known:
    if host in busy:continue
    if statuses.get(host)=='연결됨':
     if auto and now-refreshed.get(host,0)>=interval:due.append(host)
    elif auto and pathlib.Path(control_path(host)).exists():
     # A saved SSH control socket may have expired. Back off failures.
     delay=min(300,30*2**min(failures.get(host,0),4))
     if now-attempts.get(host,0)>=delay:due.append(host)
  if local_due:refresh_local()
  for host in due:connect(host)

if __name__=='__main__':
 lock=(DATA/'instance.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit(0)
 http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 threading.Thread(target=http.serve_forever,daemon=True).start();threading.Thread(target=monitor,daemon=True).start()
 for host in hosts:connect(host)
 url=f'http://127.0.0.1:{http.server_port}/?token={TOKEN}'
 executable=ROOT/'DesktopHost'
 if not executable.exists():executable=ROOT.parent/'MacOS/DesktopHost'
 try:
  if '--headless' in sys.argv:
   signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
   signal.signal(signal.SIGINT,lambda *_:sys.exit(0))
   print(json.dumps({'url':url,'foreground':not store.setting('onboarding_complete',False)}),flush=True)
   while True:signal.pause()
  else:
   print('AI_DESK_NATIVE_STARTED',flush=True)
   subprocess.run([str(executable),url]+(['--foreground'] if not store.setting('onboarding_complete',False) else []),check=False)
 finally:
  http.shutdown()
  for term in list(terminals.values()):term.close()
  store.db.close()
