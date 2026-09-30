"""Isolated API verification; never writes to the user's planner."""
import tempfile,os,sys,threading,json,urllib.request,urllib.error
with tempfile.TemporaryDirectory() as folder:
 os.environ['AI_DESK_DATA']=folder
 import server
 http=server.HTTPServer(('127.0.0.1',0),server.Handler)
 threading.Thread(target=http.serve_forever,daemon=True).start()
 base=f'http://127.0.0.1:{http.server_port}'
 def request(path,data=None,auth=True,host=None):
  headers={'X-AI-Desk-Token':server.TOKEN} if auth else {}
  if host:headers['Host']=host
  if data is not None:headers['Content-Type']='application/json'
  req=urllib.request.Request(base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
  with urllib.request.urlopen(req) as response:return json.load(response)
 key=request('todo',{'title':'Temporary test','date':'2026-09-29','start':'09:00','end':'10:00'})['id']
 assert request('state')['tasks'][0]['id']==key
 request('toggle',{'id':key});assert request('state')['tasks'][0]['done']==1
 request('archive',{'id':key});assert request('state')['tasks']==[]
 request('archive',{'id':key,'archived':0});assert len(request('state')['tasks'])==1
 request('theme',{'theme':'dark'});assert request('state')['settings']['theme']=='dark'
 for kwargs in ({'auth':False},{'host':'malicious.example'}):
  try:request('state',**kwargs)
  except urllib.error.HTTPError as error:assert error.code==403
  else:raise AssertionError('Unauthorized API request accepted')
 try:request('todo',{'title':'Invalid','date':'2026-09-29','start':'12:00','end':'10:00'})
 except urllib.error.HTTPError as error:assert error.code==400
 else:raise AssertionError('Invalid time accepted')
 http.shutdown();http.server_close();server.store.db.close()
 print('PASS: Todo create/complete/archive/restore, themes, time validation, authenticated local API')
