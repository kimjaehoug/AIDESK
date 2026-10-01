import concurrent.futures,importlib.util,pathlib,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
spec=importlib.util.spec_from_file_location('session_io_under_test',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.ROOT=pathlib.Path(sys.argv[2])
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'OK')
 def log_message(self,*args):pass
ThreadingHTTPServer.request_queue_size=128
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
def fetch(_):
 with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port),timeout=3) as r:assert r.read()==b'OK'
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
 for cycle in range(60):
  term=m.TerminalSession(['/bin/cat'],sys.argv[2]);term.write('hello\n')
  jobs=[pool.submit(term.close) for _ in range(4)]+[pool.submit(fetch,i) for i in range(8)]
  for job in jobs:job.result()
  term.proc.wait(timeout=3)
server.shutdown();server.server_close()
print('PASS: 60 terminal lifecycles, concurrent closes, 480 HTTP requests')
