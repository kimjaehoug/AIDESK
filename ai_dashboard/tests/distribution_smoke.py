"""Exercise a built app's runtime/API with isolated home and planner data; no AI requests."""
import datetime
import json
import os
import pathlib
import select
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


def verify(app):
    app = pathlib.Path(app).resolve()
    resources = app / 'Contents/Resources'
    runtime = app / 'Contents/Frameworks/Python.framework/Versions/3.14'
    with tempfile.TemporaryDirectory(prefix='ai-desk-smoke-') as temporary:
        env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
        env.update(HOME=temporary, AI_DESK_DATA=temporary+'/data', PYTHONHOME=str(runtime),
                   PYTHONNOUSERSITE='1', PYTHON_JIT='0', LANG='en_US.UTF-8',
                   PATH='/usr/bin:/bin:/usr/sbin:/sbin')
        # The original failure was in bin/python3.14, so exercise the launcher too.
        check = subprocess.run([str(runtime/'bin/python3.14'), '-s', '-B', '-c',
                                'import sqlite3,ssl,socket,fcntl;print("runtime-ready")'],
                               env=env, capture_output=True, text=True, timeout=15)
        assert check.returncode == 0, check.stderr
        assert 'runtime-ready' in check.stdout
        command = [str(runtime/'Resources/Python.app/Contents/MacOS/Python'), '-s', '-B',
                   str(resources/'server.py'), '--headless']
        child = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            assert select.select([child.stdout], [], [], 15)[0], 'backend startup timed out'
            line = child.stdout.readline()
            assert line, 'backend exited before emitting startup URL'
            startup = json.loads(line)
            url = urllib.parse.urlsplit(startup['url'])
            assert url.hostname == '127.0.0.1' and startup['foreground'] is True
            token = urllib.parse.parse_qs(url.query)['token'][0]
            base = 'http://'+url.netloc

            def request(route, body=None, auth=True):
                headers = {'X-AI-Desk-Token': token} if auth else {}
                data = None if body is None else json.dumps(body).encode()
                if data is not None:headers['Content-Type'] = 'application/json'
                req = urllib.request.Request(base+route, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read()

            state = json.loads(request('/api/state'))
            assert state['tasks'] == [] and state['local'] == [] and state['hosts'] == []
            assert state['capabilities']['codex_messages'] is True
            html = urllib.request.urlopen(startup['url'], timeout=10).read().decode()
            assert '__TOKEN__' not in html and 'canQueueCodex' in html
            for asset in ('xterm.js', 'xterm.css', 'markdown-it.min.js'):
                assert request('/vendor/'+asset+'?token='+token)
            try:request('/api/state', auth=False)
            except urllib.error.HTTPError as error:assert error.code == 403
            else:raise AssertionError('unauthenticated API accepted')
            key = json.loads(request('/api/todo', {'title':'배포 확인', 'date':datetime.date.today().isoformat(),
                                                   'start':'09:00', 'end':'10:00'}))['id']
            assert json.loads(request('/api/state'))['tasks'][0]['id'] == key
            request('/api/preferences', {'onboarding_complete':True})
            assert json.loads(request('/api/state'))['settings']['onboarding_complete'] is True
            try:request('/api/codex/send', {'session':{'provider':'Codex','host':'local','id':'not-a-session'}, 'text':'not sent'})
            except urllib.error.HTTPError as error:assert error.code == 400
            else:raise AssertionError('undiscovered session accepted')
        finally:
            child.terminate()
            try:_, stderr = child.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill(); _, stderr = child.communicate()
            if child.returncode not in (0, -15):
                raise RuntimeError('packaged backend failed: '+stderr[-3000:])
    print('PASS: packaged launcher, native runtime target, startup, authenticated API, assets, planner and Codex route')


if __name__ == '__main__':
    verify(sys.argv[1])
