"""Resolve this user's tools without depending on a developer's Mac."""
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()


def prepare_environment():
    directories = [HOME / '.local/bin', pathlib.Path('/opt/homebrew/bin'),
                   pathlib.Path('/usr/local/bin'), HOME / '.npm-global/bin',
                   HOME / '.npm/bin', HOME / '.volta/bin', HOME / '.bun/bin']
    directories += sorted((HOME / '.nvm/versions/node').glob('*/bin'),
                          key=lambda p: tuple(int(n) for n in re.findall(r'\d+', str(p))),
                          reverse=True)
    current = os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin').split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join(dict.fromkeys(
        current + [str(p) for p in directories if p.is_dir()]))
    os.environ.setdefault('LANG', 'en_US.UTF-8')


def executable_for(provider):
    name = {'Claude': 'claude', 'Codex': 'codex', 'tmux': 'tmux'}[provider]
    found = shutil.which(name)
    if found:
        return found
    candidates = []
    if provider == 'Codex':
        for base in (pathlib.Path('/Applications'), HOME / 'Applications'):
            for app in ('ChatGPT.app', 'Codex.app'):
                candidates.append(base / app / 'Contents/Resources/codex')
                candidates.append(base / app / 'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
    for base in (HOME / '.vscode/extensions', HOME / '.cursor/extensions'):
        patterns = ('anthropic.claude-code-*/resources/native-binary/claude',) if provider == 'Claude' else (
            'openai.chatgpt-*/bin/*/codex', 'openai.chatgpt-*/resources/codex')
        for pattern in patterns:
            candidates.extend(base.glob(pattern))
    arch = 'arm64' if platform.machine() == 'arm64' else 'x64'
    for p in sorted(candidates, key=lambda p: (arch in str(p), str(p)), reverse=True):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def app_for(name):
    for base in (HOME / 'Applications', pathlib.Path('/Applications')):
        path = base / (name + '.app')
        if path.is_dir():
            return str(path)
    # LaunchServices also knows renamed apps and installations elsewhere.
    result = subprocess.run(['/usr/bin/osascript', '-e',
                             'POSIX path of (path to application "' + name + '")'],
                            capture_output=True, text=True, timeout=5)
    return result.stdout.strip().rstrip('/') if result.returncode == 0 else None


def setup_status():
    return {'version': '1.0.1', 'macOS': platform.mac_ver()[0],
            'architecture': platform.machine(), 'python': platform.python_version(),
            'tools': {name: bool(executable_for(name)) for name in ('Claude', 'Codex', 'tmux')},
            'apps': {name: bool(app_for(name)) for name in ('Cursor', 'ChatGPT')},
            'data_location': str(HOME / 'Library/Application Support/AI Desk')}


prepare_environment()
