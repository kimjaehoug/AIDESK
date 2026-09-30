#!/usr/bin/env python3
"""AI Desk: an interactive desktop-layer planner and SSH session hub."""
import calendar
import datetime as dt
import fcntl
import os
import pathlib
import queue
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from model import Store, local_sessions, remote_sessions, ssh_hosts, control_path
from native import DesktopLayer

HOME=pathlib.Path.home()
DATA=pathlib.Path(os.environ.get('AI_DESK_DATA',str(HOME/'Library/Application Support/AI Desk')))
TITLE='AI Desk · Desktop'
THEMES={
 'dark':dict(bg='#10131E',card='#191E2D',inset='#121724',border='#293147',text='#EDF0FA',muted='#95A0B8',accent='#ABA5FF',soft='#2B2949',green='#7FD9B8',danger='#F3A3AA',white='#151529'),
 'light':dict(bg='#F2F3F9',card='#FFFFFF',inset='#F5F6FB',border='#E2E5F0',text='#24263B',muted='#7A829B',accent='#6257D9',soft='#EFEDFC',green='#258B71',danger='#C85966',white='#FFFFFF')}
DAYS=['월','화','수','목','금','토','일']

class Dashboard:
 def __init__(self,root,store):
  self.root=root; self.store=store; self.theme=store.setting('theme','light'); self.palette=THEMES[self.theme]
  self.day=dt.date.today(); self.month=self.day.replace(day=1); self.host='local'; self.sessions=local_sessions(); self.remote={}; self.host_states={}
  self.hosts=list(dict.fromkeys(ssh_hosts()+store.setting('extra_hosts',[]))); self.selected=None; self.todo_offset=0; self.session_offset=0
  self.inbox=queue.Queue(); self.busy=set(); self.move_mode=store.setting('start_in_edit',False); self.embedded=not self.move_mode; store.set_setting('start_in_edit',False); self.undo_id=None; self.toast=''; self.closed=False
  self.native=DesktopLayer(); self.root.title(TITLE); self.root.overrideredirect(not self.move_mode)
  width=min(1160,root.winfo_screenwidth()-100); height=min(770,root.winfo_screenheight()-100)
  saved=store.setting('geometry')
  if saved:
   try:
    import re
    match=re.fullmatch(r'(\d+)x(\d+)\+(\d+)\+(\d+)',saved)
    if match:
     sw,sh,x,y=map(int,match.groups()); width=max(1000,min(width,sw)); height=max(680,min(height,sh)); x=min(x,max(0,root.winfo_screenwidth()-width)); y=min(y,max(30,root.winfo_screenheight()-height)); saved=f'{width}x{height}+{x}+{y}'
   except Exception: saved=None
  if not saved: saved=f'{width}x{height}+{max(45,(root.winfo_screenwidth()-width)//2)}+{max(60,(root.winfo_screenheight()-height)//2)}'
  self.root.geometry(saved); self.root.minsize(1000,680)
  bg=self.palette['bg']; self.root.configure(bg=bg)
  self.canvas=tk.Canvas(root,bg=bg,highlightthickness=0); self.canvas.pack(fill='both',expand=True)
  self.canvas.bind('<Configure>',lambda e:self.draw()); self.canvas.bind('<ButtonPress-1>',self.drag_start); self.canvas.bind('<B1-Motion>',self.drag); self.canvas.bind('<ButtonRelease-1>',self.drag_end)
  self.root.bind('<Escape>',lambda e:self.set_move(False)); self.root.bind('<Command-n>',lambda e:self.todo_dialog()); self.root.bind('<Command-d>',lambda e:self.toggle_theme()); self.root.bind('<Command-b>',lambda e:self.set_move(not self.move_mode)); self.root.protocol('WM_DELETE_WINDOW',self.quit)
  self.style=ttk.Style(); self.style.theme_use('clam'); self.apply_form_style()
  self.draw(); self.root.after(300,self.embed); self.root.after(150,self.poll); self.root.after(60000,self.tick)
  if self.store.setting('preview_todo',False):
   self.store.set_setting('preview_todo',False);self.root.after(700,self.todo_dialog)
  self.root.after(1500,self.refresh_remote_all); self.root.after(5000,self.check_authenticated)

 def apply_form_style(self):
  p=self.palette
  self.style.configure('Desk.TCombobox',fieldbackground=p['inset'],background=p['card'],foreground=p['text'],arrowcolor=p['muted'],bordercolor=p['border'],padding=5)
  self.style.map('Desk.TCombobox',fieldbackground=[('readonly',p['inset'])],foreground=[('readonly',p['text'])])

 def embed(self):
  try:
   good=self.native.apply(TITLE,self.embedded)
   if not good: self.toast='바탕화면 레이어를 적용하지 못했습니다. 이동 모드에서 다시 시도하세요.'
   print('AI_DESK_LAYER', 'desktop' if self.embedded and good else 'editing',flush=True)
  except Exception as exc: self.toast='바탕화면 레이어: '+str(exc)
  self.draw()

 def set_move(self,state):
  self.move_mode=state; self.embedded=not state; self.root.overrideredirect(not state); self.root.update_idletasks(); self.embed(); self.notice('상단 빈 공간을 잡아 이동하고, 배치 완료를 누르세요.' if state else '바탕화면에 매립했습니다.')
 def drag_start(self,event):
  if self.move_mode and event.y<85: self.drag_origin=(event.x_root,event.y_root,self.root.winfo_x(),self.root.winfo_y())
  else: self.drag_origin=None
 def drag(self,event):
  if self.move_mode and getattr(self,'drag_origin',None):
   x,y,wx,wy=self.drag_origin
   self.root.geometry(f'+{max(0,wx+event.x_root-x)}+{max(28,wy+event.y_root-y)}')
 def drag_end(self,event):
  if getattr(self,'drag_origin',None): self.store.set_setting('geometry',self.root.geometry()); self.drag_origin=None

 def round(self,x,y,w,h,fill,r=14,outline=None):
  points=[x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y]
  return self.canvas.create_polygon(points,smooth=True,splinesteps=24,fill=fill,outline=outline or fill,width=1)
 def text(self,x,y,text,size=12,color=None,bold=False,anchor='nw',width=None):
  return self.canvas.create_text(x,y,text=text,fill=color or self.palette['text'],font=('Apple SD Gothic Neo',size,'bold' if bold else 'normal'),anchor=anchor,width=width)
 def fit(self,text,width,size=12):
  from tkinter.font import Font
  font=Font(family='Apple SD Gothic Neo',size=size)
  if font.measure(text)<=width: return text
  while text and font.measure(text+'…')>width: text=text[:-1]
  return text+'…'
 def button(self,x,y,w,h,label,action,primary=False,subtle=False):
  p=self.palette; tag='b'+uuid.uuid4().hex; fill=p['accent'] if primary else (p['bg'] if subtle else p['inset'])
  shape=self.round(x,y,w,h,fill,r=9); txt=self.text(x+w/2,y+h/2,label,11,p['white'] if primary else p['text'],True,anchor='center')
  for item in (shape,txt): self.canvas.addtag_withtag(tag,item)
  self.canvas.tag_bind(tag,'<Button-1>',lambda e:action()); self.canvas.tag_bind(tag,'<Enter>',lambda e:self.canvas.config(cursor='hand2')); self.canvas.tag_bind(tag,'<Leave>',lambda e:self.canvas.config(cursor=''))
 def hit(self,tag,action):
  self.canvas.tag_bind(tag,'<Button-1>',lambda e:action()); self.canvas.tag_bind(tag,'<Enter>',lambda e:self.canvas.config(cursor='hand2')); self.canvas.tag_bind(tag,'<Leave>',lambda e:self.canvas.config(cursor=''))
 def notice(self,text):
  self.toast=text; self.draw(); self.root.after(12000,lambda:(setattr(self,'toast',''),self.draw()))

 def draw(self):
  if self.closed: return
  c=self.canvas;p=self.palette;c.delete('all'); w=max(self.root.winfo_width(),1000);h=max(self.root.winfo_height(),680)
  self.round(1,1,w-2,h-2,p['bg'],r=24,outline=p['border'])
  self.round(26,24,37,37,p['soft'],r=12); self.text(44,42,'✦',23,p['accent'],anchor='center')
  self.text(76,24,'AI Desk',22,bold=True); self.text(78,53,'A little clarity for your day.',10,p['muted'])
  self.button(w-355,25,105,34,'Dark' if self.theme=='light' else 'Light',self.toggle_theme)
  self.button(w-241,25,121,34,'배치 완료' if self.move_mode else '위치 조정',lambda:self.set_move(not self.move_mode))
  self.button(w-111,25,85,34,'설정',self.settings_dialog)
  left=26; lx=275; center=left+lx+16; cw=370; right=center+cw+16; rw=w-right-26; top=89; bottom=h-44
  self.round(left,top,lx,bottom-top,p['card']); self.round(center,top,cw,bottom-top,p['card']); self.round(right,top,rw,bottom-top,p['card'])
  self.draw_left(left,top,lx,bottom); self.draw_planner(center,top,cw,bottom); self.draw_ai(right,top,rw,bottom)
  footer=self.toast or ('바탕화면 매립 · 로컬에 자동 저장 · SSH 인증 정보는 저장하지 않습니다.' if self.embedded else '위치 조정 모드 · 상단을 잡아서 이동하세요.')
  self.text(28,h-25,self.fit(footer,w-200,10),10,p['muted'])
  if self.undo_id: self.button(w-128,h-33,100,24,'삭제 되돌리기',self.undo_archive,subtle=True)

 def draw_left(self,x,y,w,bottom):
  p=self.palette; now=dt.datetime.now(); self.text(x+20,y+18,now.strftime('%Y. %m. %d'),11,p['muted'])
  self.text(x+20,y+43,'오늘을 설계하세요',20,bold=True)
  self.text(x+20,y+79,now.strftime('%H:%M')+'   '+DAYS[now.weekday()]+'요일',13,p['accent'],True)
  cy=y+112
  self.text(x+20,cy,self.month.strftime('%Y년 %m월'),13,bold=True)
  self.button(x+w-80,cy-5,28,25,'‹',lambda:self.month_delta(-1)); self.button(x+w-45,cy-5,28,25,'›',lambda:self.month_delta(1))
  days=self.store.tasks(); counts={}
  for task in days:
   if not task['done']: counts[task['date']]=counts.get(task['date'],0)+1
  for column,day in enumerate(DAYS): self.text(x+26+column*33,cy+37,day,10,p['muted'],anchor='center')
  for row,week in enumerate(calendar.monthcalendar(self.month.year,self.month.month)):
   for column,num in enumerate(week):
    if not num: continue
    date=dt.date(self.month.year,self.month.month,num); dx=x+11+column*33;dy=cy+51+row*29;tag='date'+str(date)
    if date==self.day: shape=self.round(dx,dy,30,30,p['accent'],r=9);c=self.canvas; c.addtag_withtag(tag,shape)
    else:
     shape=self.canvas.create_rectangle(dx,dy,dx+30,dy+30,fill=p['card'],outline=p['card']);self.canvas.addtag_withtag(tag,shape)
    color=p['white'] if date==self.day else (p['accent'] if date==dt.date.today() else p['text'])
    item=self.text(dx+15,dy+13,str(num),12,color,date==dt.date.today(),anchor='center');self.canvas.addtag_withtag(tag,item)
    if counts.get(str(date)):
     dot=self.canvas.create_oval(dx+13,dy+25,dx+17,dy+29,fill=p['white'] if date==self.day else p['accent'],outline='');self.canvas.addtag_withtag(tag,dot)
    self.hit(tag,lambda d=date:self.select_day(d))
  self.button(x+17,cy+238,w-34,27,'오늘로 돌아가기',lambda:self.select_day(dt.date.today()))
  sy=cy+277; self.text(x+20,sy,'SSH SERVERS',10,p['muted'],True)
  for i,host in enumerate(self.hosts[:max(1,min(4,int((bottom-64-(sy+26))/33)))]):
   yy=sy+26+i*33; state=self.host_states.get(host,'미조회'); color=p['green'] if state=='연결됨' else p['danger'] if state in ('인증 필요','접속 불가') else p['muted']
   self.canvas.create_oval(x+20,yy+7,x+26,yy+13,fill=color,outline='')
   tag='host'+str(i); item=self.text(x+36,yy,self.fit(host,w-106,11),11,p['accent'] if host==self.host else p['text'],host==self.host); self.canvas.addtag_withtag(tag,item); self.hit(tag,lambda host=host:self.select_host(host))
   self.text(x+36,yy+17,state,9,color)
   self.button(x+w-50,yy,31,28,'↗',lambda host=host:self.terminal_login(host))
  if sy+80<bottom: self.button(x+17,bottom-49,w-34,32,'서버 추가 / 관리',self.server_dialog)

 def month_delta(self,n):
  month=self.month.month-1+n; self.month=dt.date(self.month.year+month//12,month%12+1,1);self.draw()
 def select_day(self,day): self.day=day;self.month=day.replace(day=1);self.todo_offset=0;self.draw()
 def toggle_theme(self):
  self.theme='dark' if self.theme=='light' else 'light';self.palette=THEMES[self.theme];self.root.configure(bg=self.palette['bg']);self.canvas.configure(bg=self.palette['bg']);self.store.set_setting('theme',self.theme);self.apply_form_style();self.draw()

 def draw_planner(self,x,y,w,bottom):
  p=self.palette;tasks=self.store.tasks(self.day);done=sum(t['done'] for t in tasks);pending=[t for t in tasks if not t['done']]
  self.text(x+22,y+20,'DAY PLANNER',10,p['muted'],True)
  self.text(x+22,y+47,self.day.strftime('%m월 %d일')+' '+DAYS[self.day.weekday()]+'요일',21,bold=True)
  self.text(x+22,y+84,f'{len(pending)}개 남음   ·   {done}/{len(tasks)} 완료',11,p['muted'])
  self.button(x+w-92,y+46,70,32,'+ 할 일',self.todo_dialog,primary=True)
  self.round(x+22,y+116,w-44,5,p['inset'],r=2)
  if tasks and done: self.round(x+22,y+116,(w-44)*done/len(tasks),5,p['accent'],r=2)
  yy=y+150
  if not tasks:
   self.round(x+22,yy+27,w-44,184,p['inset'],r=14)
   self.text(x+w/2,yy+56,'✦',29,p['accent'],anchor='n')
   self.text(x+w/2,yy+102,'빈 하루에 여유를 남기세요.',15,bold=True,anchor='n')
   self.text(x+w/2,yy+133,'달력에서 날짜를 고르고\n해야 할 일을 시간별로 추가하세요.',12,p['muted'],anchor='n')
  capacity=max(1,int((bottom-yy-78)//83));max_offset=max(0,len(tasks)-capacity);self.todo_offset=min(self.todo_offset,max_offset)
  for i,task in enumerate(tasks[self.todo_offset:self.todo_offset+capacity]):
   ty=yy+i*83; tag='task'+task['id']; a=self.round(x+20,ty,w-40,72,p['inset'],r=12);self.canvas.addtag_withtag(tag,a)
   col=p['muted'] if task['done'] else p['accent']; self.text(x+34,ty+12,task['start']+' — '+task['end'],10,col,True)
   t=self.text(x+34,ty+33,self.fit(task['title'],w-100,13),13,p['muted'] if task['done'] else p['text'],True);self.canvas.addtag_withtag(tag,t)
   self.hit(tag,lambda task=task:self.todo_dialog(task))
   self.button(x+w-63,ty+23,28,28,'✓' if task['done'] else '○',lambda task=task:self.complete(task))
  if len(tasks)>capacity:
   self.button(x+w-95,bottom-50,30,27,'↑',lambda:self.scroll_tasks(-1));self.button(x+w-57,bottom-50,30,27,'↓',lambda:self.scroll_tasks(1))
   self.text(x+22,bottom-42,f'{self.todo_offset+1}–{min(len(tasks),self.todo_offset+capacity)} / {len(tasks)}',10,p['muted'])
  elif pending:
   total=sum((dt.datetime.strptime(t['end'],'%H:%M')-dt.datetime.strptime(t['start'],'%H:%M')).seconds//60 for t in pending)
   self.text(x+22,bottom-42,f'계획한 시간  {total//60}시간 {total%60}분',11,p['muted'])
  else: self.text(x+22,bottom-42,'완료 체크와 일정 수정은 즉시 저장됩니다.',10,p['muted'])
 def scroll_tasks(self,n): self.todo_offset=max(0,self.todo_offset+n);self.draw()
 def complete(self,task): self.store.toggle(task['id']);self.draw()
 def undo_archive(self):
  if self.undo_id: self.store.archive(self.undo_id,0);self.undo_id=None;self.notice('할 일을 복원했습니다.')

 def draw_ai(self,x,y,w,bottom):
  p=self.palette; self.text(x+20,y+20,'AI WORKSPACE',10,p['muted'],True)
  self.text(x+20,y+47,'이어지는 작업들',21,bold=True)
  self.button(x+w-74,y+49,54,29,'새로',self.refresh)
  self.button(x+18,y+91,72,29,'내 Mac',lambda:self.select_host('local'))
  self.text(x+103,y+99,self.fit('LOCAL' if self.host=='local' else self.host,w-122,10),10,p['accent'],True)
  sessions=self.sessions if self.host=='local' else self.remote.get(self.host,[])
  yy=y+138;capacity=max(1,int((bottom-yy-155)//70));self.session_offset=min(self.session_offset,max(0,len(sessions)-capacity))
  if not sessions:
   self.text(x+22,yy+10,'표시할 세션이 없습니다.',13,bold=True)
   explanation='로컬 Claude / Cursor 기록을 조회합니다.' if self.host=='local' else ('조회 중입니다…' if self.host in self.busy else 'SSH 인증 또는 연결 상태를 확인하세요.\n서버의 ↗ 버튼으로 터미널을 열 수 있습니다.')
   self.text(x+22,yy+45,explanation,11,p['muted'],width=w-44)
  for i,s in enumerate(sessions[self.session_offset:self.session_offset+capacity]):
   sy=yy+i*70;tag='session'+str(i);active=self.selected and self.selected['id']==s['id'] and self.selected['host']==s['host'];shape=self.round(x+16,sy,w-32,61,p['soft'] if active else p['inset'],r=11);self.canvas.addtag_withtag(tag,shape)
   provider=s['provider'];time=dt.datetime.fromtimestamp(s['time']).strftime('%m/%d %H:%M')
   self.text(x+29,sy+10,provider,10,p['accent'],True);self.text(x+w-27,sy+10,time,9,p['muted'],anchor='ne')
   title=self.text(x+29,sy+30,self.fit(s['name'],w-58,12),12,bold=True);self.canvas.addtag_withtag(tag,title);self.hit(tag,lambda s=s:self.select_session(s))
  by=bottom-127
  if len(sessions)>capacity:
   self.text(x+20,by-26,f'{self.session_offset+1}–{min(len(sessions),self.session_offset+capacity)} / {len(sessions)}',9,p['muted']);self.button(x+w-82,by-35,27,24,'↑',lambda:self.scroll_sessions(-1));self.button(x+w-48,by-35,27,24,'↓',lambda:self.scroll_sessions(1))
  self.button(x+18,by,w-36,34,'선택한 세션 열기 / 요청',self.compose,primary=True)
  self.button(x+18,by+43,(w-46)/2,30,'ChatGPT',lambda:self.compose('ChatGPT'));self.button(x+28+(w-46)/2,by+43,(w-46)/2,30,'Cursor',lambda:self.compose('Cursor'))
  self.text(x+20,by+88,'기록 시각 기준 · 완료 상태는 미확인',9,p['muted'])
  self.text(x+20,by+106,'SSH: Claude · Codex · tmux',9,p['muted'])

 def select_session(self,s): self.selected=s;self.draw()
 def scroll_sessions(self,n): self.session_offset=max(0,self.session_offset+n);self.draw()
 def select_host(self,host):
  self.host=host;self.session_offset=0;self.selected=None;self.draw()
  if host!='local' and host not in self.remote:self.connect(host)
 def refresh(self):
  self.sessions=local_sessions();self.draw()
  if self.host!='local':self.connect(self.host)
 def refresh_remote_all(self):
  for host in self.hosts:self.connect(host)
 def connect(self,host):
  if host in self.busy:return
  self.busy.add(host);self.host_states[host]='조회 중';self.draw()
  def work():
   try:self.inbox.put(('remote',host,remote_sessions(host)))
   except Exception as error:self.inbox.put(('error',host,str(error)))
  threading.Thread(target=work,daemon=True).start()
 def poll(self):
  while not self.inbox.empty():
   kind,host,data=self.inbox.get();self.busy.discard(host)
   if kind=='remote':self.remote[host]=data;self.host_states[host]='연결됨'
   else:
    self.host_states[host]='인증 필요' if 'Permission denied' in data else '접속 불가'
    if self.host==host:self.notice(self.fit(data,1000,10))
   self.draw()
  if not self.closed:self.root.after(200,self.poll)
 def tick(self):
  if self.closed:return
  self.sessions=local_sessions();self.draw();self.root.after(60000,self.tick)

 def dialog(self,title,width=440,height=440):
  p=self.palette;win=tk.Toplevel(self.root);win.title(title);win.configure(bg=p['card']);win.geometry(f'{width}x{height}+{max(20,self.root.winfo_x()+150)}+{max(35,self.root.winfo_y()+100)}');win.resizable(False,False)
  # A dialog is a normal app window even while the main surface lives at desktop level.
  win.lift();win.after(100,win.focus_force);return win
 def label(self,win,text): return tk.Label(win,text=text,bg=self.palette['card'],fg=self.palette['muted'],font=('Apple SD Gothic Neo',11),anchor='w')
 def entry(self,win,value=''):
  p=self.palette;var=tk.StringVar(value=value);e=tk.Entry(win,textvariable=var,bg=p['inset'],fg=p['text'],insertbackground=p['text'],relief='flat',font=('Apple SD Gothic Neo',13),highlightthickness=1,highlightbackground=p['border'],highlightcolor=p['accent']);return var,e
 def form_button(self,win,label,action,primary=False):
  p=self.palette;b=tk.Label(win,text=label,bg=p['accent'] if primary else p['inset'],fg=p['white'] if primary else p['text'],font=('Apple SD Gothic Neo',12,'bold'),padx=14,pady=9,cursor='hand2');b.bind('<Button-1>',lambda e:action());return b

 def todo_dialog(self,task=None):
  win=self.dialog('계획 수정' if task else '시간을 계획하기',480,540);p=self.palette
  self.label(win,'할 일').pack(fill='x',padx=26,pady=(20,7));title,field=self.entry(win,task['title'] if task else '');field.pack(fill='x',padx=26,ipady=8);field.focus_set()
  self.label(win,'날짜 · YYYY-MM-DD').pack(fill='x',padx=26,pady=(15,7));day,e=self.entry(win,task['date'] if task else str(self.day));e.pack(fill='x',padx=26,ipady=7)
  self.label(win,'시간 · 시작 → 종료').pack(fill='x',padx=26,pady=(15,7));row=tk.Frame(win,bg=p['card']);row.pack(fill='x',padx=26)
  hour=dt.datetime.now().hour;start=tk.StringVar(value=task['start'] if task else f'{min(hour+1,23):02d}:00');end=tk.StringVar(value=task['end'] if task else (f'{min(hour+2,23):02d}:00' if hour<22 else '23:59'))
  options=[f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]+['23:59']
  for var in (start,end):ttk.Combobox(row,textvariable=var,values=options,width=17,style='Desk.TCombobox').pack(side='left',padx=(0,14))
  self.label(win,'메모').pack(fill='x',padx=26,pady=(15,7));notes=tk.Text(win,height=4,bg=p['inset'],fg=p['text'],insertbackground=p['text'],relief='flat',font=('Apple SD Gothic Neo',12),padx=10,pady=9);notes.pack(fill='x',padx=26);notes.insert('1.0',task['notes'] if task else '')
  hint=tk.Label(win,text='선택한 날짜의 시간순으로 자동 정렬됩니다.',bg=p['card'],fg=p['muted'],font=('Apple SD Gothic Neo',10),wraplength=425);hint.pack(padx=26,pady=10)
  def save():
   try:
    self.store.save_task(title.get(),day.get(),start.get(),end.get(),notes.get('1.0','end').strip(),task['id'] if task else None)
    self.select_day(dt.date.fromisoformat(day.get()));win.destroy();self.notice('계획을 저장했습니다.')
   except ValueError as exc:hint.config(text=str(exc),fg=p['danger'])
  row=tk.Frame(win,bg=p['card']);row.pack(fill='x',padx=26,pady=8)
  self.form_button(row,'저장',save,True).pack(side='right');self.form_button(row,'취소',win.destroy).pack(side='right',padx=8)
  if task:
   def archive():self.store.archive(task['id']);self.undo_id=task['id'];win.destroy();self.notice('할 일을 삭제했습니다. 아래에서 되돌릴 수 있습니다.')
   self.form_button(row,'삭제',archive).pack(side='left')
  win.bind('<Command-Return>',lambda e:save())

 def server_dialog(self):
  win=self.dialog('SSH 서버 관리',450,370);p=self.palette
  self.label(win,'~/.ssh/config의 서버를 자동으로 읽었습니다.').pack(fill='x',padx=24,pady=(20,8))
  self.label(win,'추가할 Host 별칭 또는 user@hostname').pack(fill='x',padx=24,pady=8);target,e=self.entry(win);e.pack(fill='x',padx=24,ipady=8)
  self.label(win,'포트와 SSH 키는 ~/.ssh/config에서 설정하세요.').pack(fill='x',padx=24,pady=10)
  listing=tk.Label(win,text='\n'.join(self.hosts),bg=p['card'],fg=p['text'],font=('Apple SD Gothic Neo',12),anchor='w',justify='left');listing.pack(fill='x',padx=24)
  def add():
   host=target.get().strip()
   if not host or host.startswith('-') or any(c.isspace() for c in host):messagebox.showerror('서버 이름','공백 없는 SSH Host 이름을 입력해 주세요.',parent=win);return
   if host not in self.hosts:self.hosts.append(host);self.store.set_setting('extra_hosts',self.hosts)
   win.destroy();self.select_host(host)
  self.form_button(win,'추가하고 조회',add,True).pack(side='bottom',fill='x',padx=24,pady=18)

 def terminal_command(self,command):
  directory=DATA/'launchers';directory.mkdir(exist_ok=True);script=directory/(uuid.uuid4().hex+'.command')
  script.write_text('#!/bin/zsh\n'+command+'\n',encoding='utf-8');script.chmod(0o700);subprocess.Popen(['open','-a','Terminal',str(script)])
 def check_authenticated(self):
  for host in self.hosts:
   if self.host_states.get(host)!='연결됨' and pathlib.Path(control_path(host)).exists():self.connect(host)
  if not self.closed:self.root.after(5000,self.check_authenticated)

 def terminal_login(self,host):
  # Password entry belongs to Terminal; AI Desk never handles or stores passwords.
  self.terminal_command('ssh -o ControlMaster=auto -o ControlPersist=600 -S '+shlex.quote(control_path(host))+' '+shlex.quote(host));self.notice('터미널에서 인증하면 대시보드가 연결을 감지해 세션 목록을 자동으로 조회합니다.')

 def compose(self,provider=None):
  s=self.selected if provider is None else None
  if not s and not provider:self.notice('먼저 AI 세션을 선택해 주세요.');return
  provider=provider or s['provider'];name=s['name'] if s else provider;win=self.dialog('AI 세션 · '+provider,520,440);p=self.palette
  self.label(win,self.fit(name,470,12)).pack(fill='x',padx=24,pady=(20,6))
  context=(s['host']+' · '+s['status']) if s else '프롬프트를 복사하고 앱을 엽니다.';self.label(win,context).pack(fill='x',padx=24,pady=(0,10))
  text=tk.Text(win,height=8,bg=p['inset'],fg=p['text'],insertbackground=p['text'],relief='flat',font=('Apple SD Gothic Neo',13),padx=12,pady=12);text.pack(fill='both',expand=True,padx=24);text.focus_set()
  note='Claude는 기존 세션을 이어서 실행합니다.' if provider=='Claude' else '세션을 열고 프롬프트를 복사합니다. 대상 대화에 붙여넣으세요.'
  self.label(win,note).pack(fill='x',padx=24,pady=12)
  def action(send):
   prompt=text.get('1.0','end').strip()
   if send and not prompt:self.notice('요청 내용을 입력해 주세요.');return
   if provider=='Claude' and s:
    cmd='claude --resume '+shlex.quote(s['id'])+(' '+shlex.quote(prompt) if send else '')
    if s['host']=='local':
     cli=HOME/'.local/bin/claude';cmd=(shlex.quote(str(cli)) if cli.exists() else 'claude')+' --resume '+shlex.quote(s['id'])+(' '+shlex.quote(prompt) if send else '')
     if s.get('cwd') and pathlib.Path(s['cwd']).is_dir():cmd='cd '+shlex.quote(s['cwd'])+' && '+cmd
    else:
     if s.get('cwd'):cmd='cd '+shlex.quote(s['cwd'])+' && '+cmd
     cmd='export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"; '+cmd
     cmd='ssh -t '+shlex.quote(s['host'])+' '+shlex.quote(cmd)
    self.terminal_command(cmd)
   elif s and s['host']!='local':
    if prompt:self.root.clipboard_clear();self.root.clipboard_append(prompt)
    if provider=='tmux':command='tmux attach-session -t '+shlex.quote('='+s['id'])
    elif provider=='Codex':command='export PATH="$HOME/.local/bin:$PATH"; '+('cd '+shlex.quote(s['cwd'])+' && ' if s.get('cwd') else '')+'codex resume '+shlex.quote(s['id'])
    else:command='exec "$SHELL" -l'
    self.terminal_command('ssh -t '+shlex.quote(s['host'])+' '+shlex.quote(command))
   else:
    if prompt:self.root.clipboard_clear();self.root.clipboard_append(prompt)
    subprocess.Popen(['open','-a','Cursor' if provider=='Cursor' else 'ChatGPT'])
   win.destroy();self.notice('세션을 열었습니다.' if provider=='Claude' or not prompt else '세션을 열고 요청을 복사했습니다. 원하는 대화에 붙여넣으세요.')
  row=tk.Frame(win,bg=p['card']);row.pack(fill='x',padx=24,pady=(0,20));self.form_button(row,'세션 열기',lambda:action(False)).pack(side='left')
  self.form_button(row,'요청 보내기' if provider=='Claude' else '복사하고 열기',lambda:action(True),True).pack(side='right')

 def settings_dialog(self):
  win=self.dialog('AI Desk 설정',420,290)
  self.label(win,'바탕화면에 직접 표시됩니다.').pack(fill='x',padx=24,pady=(22,8))
  self.label(win,'상단의 위치 조정 → 드래그 → 배치 완료로 이동합니다.').pack(fill='x',padx=24,pady=8)
  self.label(win,'Todo는 로컬에 저장되며 Apple 캘린더와 별개입니다.').pack(fill='x',padx=24,pady=8)
  self.form_button(win,'SSH 서버 관리',lambda:(win.destroy(),self.server_dialog())).pack(fill='x',padx=24,pady=8)
  self.form_button(win,'대시보드 종료',self.quit).pack(fill='x',padx=24,pady=8)
 def quit(self):
  self.store.set_setting('geometry',self.root.geometry());self.closed=True;self.root.destroy()

if __name__=='__main__':
 DATA.mkdir(parents=True,exist_ok=True)
 lock=(DATA/'instance.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:sys.exit(0)
 root=tk.Tk();Dashboard(root,Store(DATA));root.mainloop()
