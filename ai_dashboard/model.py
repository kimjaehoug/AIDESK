"""Persistent planning and read-only session discovery for AI Desk."""
import calendar
import datetime as dt
import hashlib
import os
import json
import pathlib
import re
import shlex
import sqlite3
import subprocess
import uuid

HOME = pathlib.Path.home()

class Store:
    def __init__(self, directory):
        self.directory = pathlib.Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / 'planner.sqlite3',check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS todo (id TEXT PRIMARY KEY,title TEXT,date TEXT,start TEXT,end TEXT,notes TEXT,done INTEGER DEFAULT 0,archived INTEGER DEFAULT 0)')
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)')
        columns={row[1] for row in self.db.execute('PRAGMA table_info(todo)')}
        if 'routine_id' not in columns:self.db.execute('ALTER TABLE todo ADD COLUMN routine_id TEXT')
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS todo_routine_day ON todo(routine_id,date) WHERE routine_id IS NOT NULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS routines (id TEXT PRIMARY KEY,title TEXT,start_date TEXT,start TEXT,end TEXT,notes TEXT,active INTEGER DEFAULT 1)')
        self.db.execute('CREATE TABLE IF NOT EXISTS session_preferences (provider TEXT,host TEXT,session_id TEXT,title TEXT,favorite INTEGER DEFAULT 0,snapshot TEXT,PRIMARY KEY(provider,host,session_id))')
        self.db.commit()
    def setting(self, key, default=None):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default
    def set_setting(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
        self.db.commit()
    def tasks(self, day=None):
        self.db.row_factory = sqlite3.Row
        query = 'SELECT * FROM todo WHERE archived=0'
        args = ()
        if day: query += ' AND date=?'; args=(str(day),)
        return [dict(r) for r in self.db.execute(query+' ORDER BY date,start,title',args)]
    def save_task(self, title, day, start, end, notes='', task_id=None):
        title=title.strip()
        if not title: raise ValueError('할 일을 입력해 주세요.')
        day=dt.date.fromisoformat(day).isoformat()
        start=dt.datetime.strptime(start,'%H:%M').strftime('%H:%M')
        end=dt.datetime.strptime(end,'%H:%M').strftime('%H:%M')
        if end<=start: raise ValueError('종료 시간을 시작 시간보다 뒤로 지정해 주세요.')
        task_id=task_id or str(uuid.uuid4())
        existing=self.db.execute('SELECT routine_id,date FROM todo WHERE id=?',(task_id,)).fetchone()
        if existing and existing[0] and existing[1]!=day:raise ValueError('루틴 일정의 날짜는 변경할 수 없습니다. 새 할 일로 추가하세요.')
        self.db.execute('INSERT INTO todo (id,title,date,start,end,notes) VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,date=excluded.date,start=excluded.start,end=excluded.end,notes=excluded.notes',(task_id,title,day,start,end,notes))
        self.db.commit()
        return task_id
    def create_routine(self,title,day,start,end,notes='',task_id=None):
        title=title.strip()
        if not title:raise ValueError('할 일을 입력해 주세요.')
        day=dt.date.fromisoformat(day).isoformat()
        start=dt.datetime.strptime(start,'%H:%M').strftime('%H:%M');end=dt.datetime.strptime(end,'%H:%M').strftime('%H:%M')
        if end<=start:raise ValueError('종료 시간을 시작 시간보다 뒤로 지정해 주세요.')
        routine_id=str(uuid.uuid4());key=task_id or str(uuid.uuid4())
        with self.db:
            existing=self.db.execute('SELECT routine_id FROM todo WHERE id=?',(key,)).fetchone()
            if existing and existing[0]:raise ValueError('이미 루틴에서 생성된 일정입니다.')
            self.db.execute('INSERT INTO routines (id,title,start_date,start,end,notes) VALUES (?,?,?,?,?,?)',(routine_id,title,day,start,end,notes))
            self.db.execute('INSERT INTO todo (id,title,date,start,end,notes,routine_id) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,date=excluded.date,start=excluded.start,end=excluded.end,notes=excluded.notes,routine_id=excluded.routine_id',(key,title,day,start,end,notes,routine_id))
        return key
    def routines(self):
        self.db.row_factory=sqlite3.Row
        return [dict(row) for row in self.db.execute('SELECT * FROM routines WHERE active=1 ORDER BY start,title')]
    def ensure_routines(self,month):
        first=dt.date.fromisoformat(month+'-01')
        self.ensure_routine_range(first.isoformat(),first.replace(day=calendar.monthrange(first.year,first.month)[1]).isoformat())
    def ensure_routine_range(self,start,end):
        first=dt.date.fromisoformat(start);last=dt.date.fromisoformat(end)
        if last<first or (last-first).days>62:raise ValueError('플래너 범위는 63일 이내로 지정하세요.')
        windows=[(first,last),(dt.date.today(),dt.date.today())]
        rows=self.routines()
        with self.db:
            for row in rows:
                for low,high in windows:
                    day=max(low,dt.date.fromisoformat(row['start_date']))
                    while day<=high:
                        stamp=day.isoformat();key=str(uuid.uuid5(uuid.NAMESPACE_URL,'ai-desk-routine:'+row['id']+':'+stamp))
                        self.db.execute('INSERT OR IGNORE INTO todo (id,title,date,start,end,notes,routine_id) VALUES (?,?,?,?,?,?,?)',(key,row['title'],stamp,row['start'],row['end'],row['notes'],row['id']))
                        if day==high:break
                        day+=dt.timedelta(days=1)
    def delete_routine(self,key):
        with self.db:
            self.db.execute('UPDATE routines SET active=0 WHERE id=?',(key,))
            self.db.execute('UPDATE todo SET archived=1 WHERE routine_id=? AND date>=? AND done=0',(key,dt.date.today().isoformat()))
    def session_preferences(self):
        self.db.row_factory=sqlite3.Row
        return [dict(row) for row in self.db.execute('SELECT * FROM session_preferences')]
    def update_session(self,session,changes):
        key=tuple(session[k] for k in ('provider','host','id'))
        row=self.db.execute('SELECT title,favorite FROM session_preferences WHERE provider=? AND host=? AND session_id=?',key).fetchone()
        title=row[0] if row else None;favorite=row[1] if row else 0
        if 'title' in changes:
            title=changes['title'].strip()
            if len(title)>160:raise ValueError('제목은 160자 이내로 입력하세요.')
            title=title or None
        if 'favorite' in changes:
            if not isinstance(changes['favorite'],bool):raise ValueError('즐겨찾기 상태가 올바르지 않습니다.')
            favorite=int(changes['favorite'])
        snapshot=dict(session)
        # Only discovery metadata reaches this method; aliases stay separate.
        snapshot['name']=session.get('original_name',session['name'])
        snapshot.pop('favorite',None);snapshot.pop('original_name',None)
        self.db.execute('INSERT INTO session_preferences VALUES (?,?,?,?,?,?) ON CONFLICT(provider,host,session_id) DO UPDATE SET title=excluded.title,favorite=excluded.favorite,snapshot=excluded.snapshot',(*key,title,favorite,json.dumps(snapshot,ensure_ascii=False)))
        self.db.commit()

    def toggle(self, task):
        self.db.execute('UPDATE todo SET done=1-done WHERE id=?',(task,)); self.db.commit()
    def archive(self, task, state=1):
        self.db.execute('UPDATE todo SET archived=? WHERE id=?',(state,task)); self.db.commit()

def ssh_hosts():
    paths=[HOME/'.ssh/config']; seen=set(); hosts=[]
    while paths:
        path=paths.pop()
        if path in seen: continue
        seen.add(path)
        try: lines=path.read_text().splitlines()
        except OSError: continue
        for line in lines:
            try: bits=shlex.split(line,comments=True)
            except ValueError: continue
            if not bits: continue
            if bits[0].lower()=='host':
                for host in bits[1:]:
                    if not any(x in host for x in '*?!') and host not in hosts: hosts.append(host)
            elif bits[0].lower()=='include':
                for pattern in bits[1:]:
                    p=pathlib.Path(pattern).expanduser()
                    if not p.is_absolute(): p=HOME/'.ssh'/p
                    paths.extend(p.parent.glob(p.name))
    return hosts

def claude_metadata(base, host='local'):
    sessions=[]
    for f in base.glob('*/*.jsonl'):
        if not re.fullmatch(r'[a-f0-9-]{36}',f.stem): continue
        cwd=''
        try:
            with f.open() as stream:
                for _ in range(12):
                    line=stream.readline()
                    if not line: break
                    item=json.loads(line)
                    if item.get('cwd'): cwd=item['cwd']; break
            sessions.append(dict(provider='Claude',id=f.stem,name=pathlib.Path(cwd).name or f.parent.name,cwd=cwd,time=f.stat().st_mtime,host=host,status='활동 기록'))
        except (OSError,ValueError): continue
    return sessions

def local_sessions():
    rows=claude_metadata(HOME/'.claude/projects')
    path=HOME/'Library/Application Support/Cursor/User/globalStorage/state.vscdb'
    if path.exists():
        try:
            db=sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=1)
            data=db.execute('SELECT composerId,lastUpdatedAt,isArchived,value FROM composerHeaders ORDER BY lastUpdatedAt DESC LIMIT 25').fetchall(); db.close()
            for sid,stamp,archived,value in data:
                meta=json.loads(value or '{}')
                rows.append(dict(provider='Cursor',id=sid,name=meta.get('name') or '이름 없는 작업',time=(stamp or 0)/1000,host='local',cwd='',status='보관됨' if archived else '활동 기록'))
        except (sqlite3.Error,ValueError): pass
    for dbpath in (HOME/'.codex').glob('state*.sqlite'):
        try:
            db=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True,timeout=1)
            data=db.execute('SELECT id,title,cwd,updated_at FROM threads WHERE archived=0 ORDER BY updated_at DESC LIMIT 30').fetchall();db.close()
            for sid,title,cwd,stamp in data:
                rows.append(dict(provider='Codex',id=sid,name=title or pathlib.Path(cwd or '').name or 'Codex session',cwd=cwd or '',time=stamp or 0,host='local',status='활동 기록'))
            break
        except sqlite3.Error:continue
    return sorted(rows,key=lambda x:x['time'],reverse=True)

# This source executes on the selected server over SSH, returning only session metadata.
REMOTE_SOURCE = r'''
import json,pathlib,subprocess,shutil,re
home=pathlib.Path.home(); out=[]
for f in (home/'.claude/projects').glob('*/*.jsonl'):
 if not re.fullmatch(r'[a-f0-9-]{36}',f.stem): continue
 try:
  cwd=''
  with f.open() as stream:
   for _ in range(12):
    line=stream.readline()
    if not line: break
    rec=json.loads(line)
    if rec.get('cwd'): cwd=rec['cwd']; break
  out.append(dict(provider='Claude',id=f.stem,name=pathlib.Path(cwd).name or f.parent.name,cwd=cwd,time=f.stat().st_mtime,status='활동 기록'))
 except (OSError,ValueError): pass
if shutil.which('tmux'):
 r=subprocess.run(['tmux','list-sessions','-F','#{session_name}\t#{session_created}\t#{session_attached}\t#{session_windows}'],capture_output=True,text=True,timeout=5)
 for line in r.stdout.splitlines():
  bits=line.split('\t')
  if len(bits)==4:
   out.append(dict(provider='tmux',id=bits[0],name=bits[0],cwd='',time=int(bits[1]),status=('연결 중' if int(bits[2]) else '분리됨')+' · '+bits[3]+' 창'))
for f in sorted((home/'.codex/sessions').glob('**/*.jsonl'),key=lambda f:f.stat().st_mtime,reverse=True)[:25]:
 try:
  with f.open() as stream: rec=json.loads(stream.readline())
  p=rec.get('payload',{})
  if rec.get('type')=='session_meta' and p.get('id'):
   out.append(dict(provider='Codex',id=p['id'],name=pathlib.Path(p.get('cwd','')).name or 'Codex session',cwd=p.get('cwd',''),time=f.stat().st_mtime,status='활동 기록'))
 except (OSError,ValueError): pass
print(json.dumps({'sessions':sorted(out,key=lambda x:x['time'],reverse=True)[:70]}))
'''

def control_path(host):
    directory=pathlib.Path(os.environ.get("AI_DESK_DATA",str(HOME/"Library/Application Support/AI Desk")))/"ssh"
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    return str(directory/(hashlib.sha256(host.encode()).hexdigest()[:16]+".sock"))

def remote_sessions(host):
    if not host or host.startswith('-') or any(c in host for c in '\n\r\x00'): raise ValueError('유효한 SSH Host 이름을 입력해 주세요.')
    result=subprocess.run(['ssh','-S',control_path(host),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=6',host,'python3 -'],input=REMOTE_SOURCE,text=True,capture_output=True,timeout=18)
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'SSH 세션 조회에 실패했습니다.')
    # Login banners can precede the response.
    lines=result.stdout.splitlines()
    value=next((json.loads(line) for line in reversed(lines) if line.startswith('{"sessions"')),None)
    if value is None: raise RuntimeError('서버에 Python 3가 필요하거나 SSH 출력 형식이 올바르지 않습니다.')
    for session in value['sessions']: session['host']=host
    return value['sessions']
