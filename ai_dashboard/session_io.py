"""Read conversation history and host interactive CLI sessions inside AI Desk."""
import base64
import collections
import fcntl
import json
import os
import pathlib
import re
import select
import shlex
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import termios
import threading
import time
import uuid
from model import control_path
from runtime import executable_for

HOME=pathlib.Path.home()
ROOT=pathlib.Path(__file__).resolve().parent


def content_text(content):
    if isinstance(content,str):return content
    if not isinstance(content,list):return ''
    parts=[]
    for item in content:
        if not isinstance(item,dict):continue
        kind=item.get('type')
        if kind in ('text','input_text','output_text') and item.get('text'):parts.append(item['text'])
        elif kind=='tool_use':parts.append('[도구 호출: '+str(item.get('name','tool'))+']')
        elif kind=='image':parts.append('[이미지]')
    return '\n\n'.join(parts)


def locate_jsonl(provider,sid,home):
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',sid):raise ValueError('올바른 세션 ID가 아닙니다.')
    if provider=='Claude':
        files=list((home/'.claude/projects').glob('*/'+sid+'.jsonl'))
    else:
        files=[]
        for db in (home/'.codex').glob('state*.sqlite'):
            try:
                c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=1)
                row=c.execute('select rollout_path from threads where id=?',(sid,)).fetchone();c.close()
                if row and row[0] and pathlib.Path(row[0]).is_file():files=[pathlib.Path(row[0])];break
            except sqlite3.Error:continue
        if not files:files=list((home/'.codex/sessions').glob('**/*'+sid+'.jsonl'))
    if not files:raise ValueError('이 세션의 대화 파일을 찾지 못했습니다.')
    return files[0]


def history_jsonl(path,provider):
    messages=[];last_model=None;size=path.stat().st_size;clipped=size>32*1024*1024
    with path.open('rb') as f:
        if clipped:f.seek(size-32*1024*1024);f.readline()
        for line in f:
            try:r=json.loads(line)
            except (ValueError,UnicodeDecodeError):continue
            if provider=='Claude':
                if r.get('type') not in ('user','assistant') or r.get('isSidechain'):continue
                m=r.get('message',{});role=m.get('role',r['type']);text=content_text(m.get('content'))
                if role=='assistant' and isinstance(m.get('model'),str) and m['model'] not in ('<synthetic>','synthetic'):last_model=m['model']
            else:
                if r.get('type')!='response_item':continue
                m=r.get('payload',{})
                if m.get('type')!='message' or m.get('role') not in ('user','assistant'):continue
                role=m['role'];text=content_text(m.get('content'))
            if not text.strip():continue
            # System scaffolding and tool payloads remain in the original session file.
            if provider=='Codex' and role=='user' and text.lstrip().startswith(('<environment_context>','<permissions instructions>','<INSTRUCTIONS>','# AGENTS.md')):continue
            messages.append({'role':role,'text':text[:24000],'time':r.get('timestamp',''),'id':r.get('uuid',str(len(messages)))})
    return {'messages':messages[-250:],'total':len(messages),'limited':clipped or len(messages)>250,'model':last_model}


def cursor_history(sid):
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',sid):raise ValueError('올바른 Cursor 세션 ID가 아닙니다.')
    path=HOME/'Library/Application Support/Cursor/User/globalStorage/state.vscdb'
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=1)
    try:
        row=db.execute('select value from cursorDiskKV where key=?',('composerData:'+sid,)).fetchone()
        if not row:raise ValueError('Cursor가 이 세션의 대화 내용을 로컬에 저장하지 않았습니다.')
        data=json.loads(row[0]);messages=[];headers=data.get('fullConversationHeadersOnly',[])
        for head in reversed(headers):
            bid=head.get('bubbleId')
            if not bid:continue
            row=db.execute('select value from cursorDiskKV where key=?',('bubbleId:'+sid+':'+bid,)).fetchone()
            if not row:continue
            bubble=json.loads(row[0]);text=bubble.get('text','')
            if not isinstance(text,str) or not text.strip():continue
            role='user' if bubble.get('type')==1 else 'assistant'
            messages.append({'id':bid,'role':role,'text':text[:24000],'time':bubble.get('createdAt','')})
            if len(messages)>=250:break
        messages.reverse()
        return {'messages':messages,'total':len(messages),'limited':len(messages)>=250,'note':'Cursor의 로컬 대화 내역입니다. 이 GUI 세션으로 보내기는 Cursor 앱에서 진행합니다.'}
    finally:db.close()


def read_history(session):
    provider=session['provider'];host=session['host'];sid=session['id']
    if provider=='tmux':return {'messages':[],'note':'tmux는 실시간 터미널에 연결하면 현재 화면과 터미널 내역을 볼 수 있습니다.'}
    if host=='local':
        if provider=='Cursor':return cursor_history(sid)
        return history_jsonl(locate_jsonl(provider,sid,HOME),provider)
    if provider not in ('Claude','Codex'):raise ValueError('이 서버 세션의 내역 조회는 지원하지 않습니다.')
    import inspect
    request=json.dumps({'provider':provider,'id':sid})
    source='import json,pathlib,re,sqlite3\n'+inspect.getsource(content_text)+'\n'+inspect.getsource(locate_jsonl)+'\n'+inspect.getsource(history_jsonl)+'\nrequest=json.loads('+repr(request)+')\nprint(json.dumps(history_jsonl(locate_jsonl(request["provider"],request["id"],pathlib.Path.home()),request["provider"])))\n'
    args=['ssh','-S',control_path(host),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=6',host,'python3 -']
    r=subprocess.run(args,input=source,text=True,capture_output=True,timeout=25)
    if r.returncode:raise RuntimeError(r.stderr.strip() or '원격 대화 내역을 읽지 못했습니다.')
    for line in reversed(r.stdout.splitlines()):
        if line.startswith('{"messages"'):return json.loads(line)
    raise RuntimeError('서버의 대화 내역 응답을 읽지 못했습니다.')


# Sent as a constant python -c argument so the PTY's stdin remains free for typing.
REMOTE_LAUNCH_SOURCE = r'''import json,os,pathlib,re,shutil,sys
request=json.loads(sys.argv[1]);home=pathlib.Path.home();provider=request['provider'];sid=request['id']
paths=[home/'.local/bin',home/'.npm-global/bin',home/'.npm/bin',home/'.volta/bin',home/'.bun/bin',pathlib.Path('/usr/local/bin')]
def version_key(path):
 return tuple(int(part) for part in re.findall(r'\d+',str(path)))
paths.extend(sorted((home/'.nvm/versions/node').glob('*/bin'),key=version_key,reverse=True))
os.environ['PATH']=os.environ.get('PATH','')+':'+':'.join(str(path) for path in paths if path.is_dir())
name={'Claude':'claude','Codex':'codex','tmux':'tmux'}[provider]
executable=shutil.which(name)
if not executable and provider in ('Claude','Codex'):
 candidates=[]
 for base in ('.vscode-server/extensions','.vscode-server-insiders/extensions','.cursor-server/extensions','.cursor-server-insiders/extensions'):
  directory=home/base
  if provider=='Claude':
   candidates.extend(directory.glob('anthropic.claude-code-*/resources/native-binary/claude'))
  else:
   candidates.extend(directory.glob('openai.chatgpt-*/bin/*/codex'))
   candidates.extend(directory.glob('openai.chatgpt-*/resources/codex'))
 candidates=[path for path in candidates if path.is_file() and os.access(path,os.X_OK)]
 if candidates:executable=str(max(candidates,key=version_key))
if not executable:
 print('AI Desk: '+name+' 실행 파일을 찾지 못했습니다. 서버에 CLI 또는 해당 VS Code 확장이 설치되어 있는지 확인하세요.',file=sys.stderr,flush=True);sys.exit(127)
cwd=request.get('cwd')
if cwd:
 try:os.chdir(cwd)
 except OSError as error:
  print('AI Desk: 작업 폴더에 들어가지 못했습니다: '+str(error),file=sys.stderr,flush=True);sys.exit(126)
args=[executable]+(['--resume',sid] if provider=='Claude' else ['resume',sid,'--no-alt-screen'] if provider=='Codex' else ['attach-session','-t','='+sid])
if provider=='Claude' and request.get('prompt'):args.append(request['prompt'])
print('AI Desk: '+provider+' 연결 · '+executable,flush=True)
os.execvpe(executable,args,os.environ)
'''

def session_command(session):
    provider=session['provider'];sid=session['id'];host=session['host'];cwd=session.get('cwd','')
    if provider=='Cursor':raise ValueError('Cursor GUI 세션의 내역은 볼 수 있습니다. 보내기는 Cursor 앱을 사용하세요.')
    if provider not in ('Claude','Codex','tmux'):raise ValueError('연결할 수 없는 세션입니다.')
    if provider!='tmux' and not re.fullmatch(r'[a-fA-F0-9-]{36}',sid):raise ValueError('세션 ID가 올바르지 않습니다.')
    if host=='local':
        exe=executable_for(provider)
        if not exe:raise ValueError(provider+' 실행 도구를 찾지 못했습니다. 설정 → 시작 안내에서 설치 상태를 확인하세요.')
        args=[exe]+(['--resume',sid] if provider=='Claude' else ['resume',sid,'--no-alt-screen'] if provider=='Codex' else ['attach-session','-t','='+sid])
        return args,cwd if cwd and pathlib.Path(cwd).is_dir() else str(HOME)
    request=json.dumps({'provider':provider,'id':sid,'cwd':cwd},ensure_ascii=False)
    cmd='exec python3 -c '+shlex.quote(REMOTE_LAUNCH_SOURCE)+' '+shlex.quote(request)
    return ['ssh','-tt','-S',control_path(host),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=6',host,cmd],str(HOME)



def shell_command(session):
    host=session['host'];cwd=session.get('cwd') or ''
    if host=='local':
        directory=cwd if cwd and pathlib.Path(cwd).is_dir() else str(HOME)
        return [os.environ.get('SHELL','/bin/zsh'),'-l'],directory
    command=('cd -- '+shlex.quote(cwd)+' && ' if cwd else '')+'exec "${SHELL:-/bin/bash}" -l'
    return ['ssh','-tt','-S',control_path(host),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=6',host,command],str(HOME)


class TerminalSession:
    def __init__(self,args,cwd,cols=100,rows=28):
        self.id=uuid.uuid4().hex;self.lock=threading.RLock();self.chunks=collections.deque();self.bytes=0;self.seq=0;self.closed=False
        self.master,slave=os.openpty()
        fcntl.ioctl(self.master,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
        env=dict(os.environ,TERM='xterm-256color',COLORTERM='truecolor',LANG='en_US.UTF-8')
        try:self.proc=subprocess.Popen([sys.executable,str(ROOT/'pty_helper.py'),*args],cwd=cwd,env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True,close_fds=True)
        except Exception:os.close(self.master);raise
        finally:os.close(slave)
        threading.Thread(target=self.reader,daemon=True).start()
    def reader(self):
        try:
            while True:
                block=os.read(self.master,65536)
                if not block:break
                with self.lock:
                    self.seq+=1;self.chunks.append((self.seq,block));self.bytes+=len(block)
                    while self.bytes>8*1024*1024:self.bytes-=len(self.chunks.popleft()[1])
        except OSError:pass
    def read(self,cursor):
        with self.lock:
            blocks=[];size=0;next_cursor=cursor
            for seq,block in self.chunks:
                if seq<=cursor:continue
                blocks.append(block);next_cursor=seq;size+=len(block)
                if size>=512000:break
            return {'data':base64.b64encode(b''.join(blocks)).decode(),'cursor':next_cursor,'running':self.proc.poll() is None,'exitCode':self.proc.poll(),'reset':bool(self.chunks and cursor and cursor<self.chunks[0][0]-1)}
    def write(self,data):
        if self.proc.poll() is not None:raise ValueError('세션 연결이 종료되었습니다. 다시 연결하세요.')
        raw=data.encode('utf-8')
        if len(raw)>100000:raise ValueError('한 번에 입력할 수 있는 길이를 초과했습니다.')
        with self.lock:
            while raw:written=os.write(self.master,raw);raw=raw[written:]
    def resize(self,cols,rows):
        cols=max(2,min(400,int(cols)));rows=max(1,min(150,int(rows)))
        if not self.closed:fcntl.ioctl(self.master,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
    def send_message(self,text,bracketed=False):
        if not isinstance(text,str) or not text.strip():raise ValueError('메시지를 입력하세요.')
        text=text.replace('\r\n','\n').replace('\r','\n')
        if any(ord(c)<32 and c not in '\n\t' for c in text) or '\x7f' in text:raise ValueError('메시지에 제어 문자가 포함되어 있습니다.')
        if len(text.encode('utf-8'))>90000:raise ValueError('메시지가 너무 깁니다.')
        if '\n' in text and not bracketed:raise ValueError('현재 연결이 여러 줄 붙여넣기를 지원하지 않습니다. 실시간 제어에서 입력하거나 한 줄로 보내세요.')
        self.write('\x1b[200~'+text+'\x1b[201~' if bracketed else text)
        # Let the CLI finish its paste event before handling the submit key.
        time.sleep(.15)
        self.write('\r')
    def close(self):
        if self.closed:return
        self.closed=True
        if self.proc.poll() is None:
            try:os.killpg(self.proc.pid,signal.SIGHUP)
            except ProcessLookupError:pass
        try:os.close(self.master)
        except OSError:pass
