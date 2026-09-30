"""Build a relocatable, universal macOS app from an official Python framework.

Only the explicit application source list is shipped; user data is never copied.
"""
import argparse
import hashlib
import json
import os
import pathlib
import plistlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
VERSION = '1.0.0'
PYTHON_VERSION = '3.14'
MIN_MACOS = '13.0'
SOURCES = ('server.py', 'model.py', 'session_io.py', 'runtime.py', 'pty_helper.py', 'index.html')
MACH_MAGICS = (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
               b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or str(args[0]) + ' failed')
    return result.stdout


def macho(path):
    if not path.is_file() or path.is_symlink():
        return False
    with path.open('rb') as f:
        return f.read(4) in MACH_MAGICS


def bundle_python(source, contents):
    version = contents / 'Frameworks/Python.framework/Versions' / PYTHON_VERSION
    (version / 'bin').mkdir(parents=True)
    shutil.copy2(source / 'Python', version / 'Python')
    shutil.copy2(source / 'bin' / ('python' + PYTHON_VERSION), version / 'bin' / ('python' + PYTHON_VERSION))
    (version / 'Resources').mkdir()
    shutil.copy2(source / 'Resources/Info.plist', version / 'Resources/Info.plist')
    library = version / 'lib'
    library.mkdir()
    for item in (source / 'lib').glob('*.dylib'):
        if item.is_symlink():
            (library / item.name).symlink_to(os.readlink(item))
        else:
            shutil.copy2(item, library / item.name)
    excluded = {'__pycache__', 'site-packages', 'test', 'tests', 'idlelib', 'tkinter',
                'turtledemo', 'ensurepip', 'config-3.14-darwin'}
    def ignore(directory, names):
        return [name for name in names if name in excluded or name.endswith(('.pyc', '.pyo'))
                or name.startswith(('_test', '_tkinter', 'xxlimited', 'xxsubtype'))]
    shutil.copytree(source / 'lib' / ('python' + PYTHON_VERSION),
                    library / ('python' + PYTHON_VERSION), ignore=ignore)
    framework = contents / 'Frameworks/Python.framework'
    (framework / 'Versions/Current').symlink_to(PYTHON_VERSION)
    (framework / 'Python').symlink_to('Versions/Current/Python')
    (framework / 'Resources').symlink_to('Versions/Current/Resources')
    prefix = '/Library/Frameworks/Python.framework/Versions/' + PYTHON_VERSION + '/'
    binaries = [p for p in version.rglob('*') if macho(p)]
    for binary in binaries:
        os.chmod(binary, 0o755)
        dependencies = set(line.strip().split(' (compatibility')[0]
                           for line in run('/usr/bin/otool', '-L', binary).splitlines() if '\t' in line)
        for dependency in dependencies:
            if dependency.startswith(prefix):
                target = version / dependency[len(prefix):]
                if not target.exists():
                    raise RuntimeError('Missing bundled dependency: ' + dependency)
                relative = os.path.relpath(target, binary.parent)
                run('/usr/bin/install_name_tool', '-change', dependency, '@loader_path/' + relative, binary)
            elif dependency.startswith('/') and not dependency.startswith(('/usr/lib/', '/System/Library/')):
                raise RuntimeError('Nonportable runtime dependency: ' + dependency)
        if binary.name == 'Python' or binary.suffix == '.dylib':
            run('/usr/bin/install_name_tool', '-id', '@loader_path/' + binary.name, binary)
    return framework, binaries


def compile_universal(source, output, temporary):
    slices = []
    for architecture in ('arm64', 'x86_64'):
        part = temporary / (output.name + '-' + architecture)
        run('/usr/bin/xcrun', 'swiftc', '-O', '-module-cache-path', temporary / 'module-cache',
            '-target', architecture + '-apple-macos' + MIN_MACOS, source, '-o', part)
        slices.append(part)
    run('/usr/bin/lipo', '-create', *slices, '-output', output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python-framework', type=pathlib.Path, required=True,
                        help='Extracted official Python.framework/Versions/3.14 directory')
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'dist')
    parser.add_argument('--identity', help='Developer ID Application signing identity; default is local ad hoc signing')
    parser.add_argument('--notary-profile', help='Existing notarytool keychain profile (requires --identity)')
    args = parser.parse_args()
    if args.notary_profile and not args.identity:
        parser.error('--notary-profile requires --identity')
    source = args.python_framework.resolve()
    if not (source / 'lib/python3.14/LICENSE.txt').is_file():
        parser.error('Expected the official Python 3.14 framework and license')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = output / 'AI Desk.app'
    if app.exists():
        parser.error('Output app already exists. Choose a new output directory to preserve the previous build.')
    contents = app / 'Contents'
    resources = contents / 'Resources'
    resources.mkdir(parents=True)
    (contents / 'MacOS').mkdir()
    for name in SOURCES:
        shutil.copy2(ROOT / name, resources / name)
    shutil.copytree(ROOT / 'vendor', resources / 'vendor')
    framework, binaries = bundle_python(source, contents)
    shutil.copy2(source / 'lib/python3.14/LICENSE.txt', resources / 'PYTHON-LICENSE.txt')
    shutil.copy2(ROOT / 'DISTRIBUTION.md', resources / 'DISTRIBUTION.md')
    plist = dict(CFBundleName='AI Desk', CFBundleDisplayName='AI Desk',
                 CFBundleIdentifier='org.aidesk.desktop', CFBundleExecutable='DesktopHost',
                 CFBundlePackageType='APPL', CFBundleShortVersionString=VERSION,
                 CFBundleVersion='100', CFBundleIconFile='AppIcon', LSMinimumSystemVersion=MIN_MACOS,
                 NSHighResolutionCapable=True, LSUIElement=False,
                 NSHumanReadableCopyright='AI Desk contributors')
    (contents / 'Info.plist').write_bytes(plistlib.dumps(plist))
    with tempfile.TemporaryDirectory(prefix='ai-desk-build-') as folder:
        temporary = pathlib.Path(folder)
        compile_universal(ROOT / 'DesktopHost.swift', contents / 'MacOS/DesktopHost', temporary)
        if (ROOT / 'AppIcon.icns').exists():
            shutil.copy2(ROOT / 'AppIcon.icns', resources / 'AppIcon.icns')
        else:
            run('/usr/bin/xcrun', 'swift', '-module-cache-path', temporary / 'module-cache',
                ROOT / 'IconBuilder.swift', temporary)
            run('/usr/bin/iconutil', '-c', 'icns', temporary / 'AppIcon.iconset', '-o', resources / 'AppIcon.icns')
    identity = args.identity or '-'
    flags = ['--options', 'runtime', '--timestamp'] if args.identity else []
    for binary in binaries:
        run('/usr/bin/codesign', '--force', '--sign', identity, *flags, binary)
    run('/usr/bin/codesign', '--force', '--sign', identity, *flags, framework)
    run('/usr/bin/codesign', '--force', '--sign', identity, *flags, contents / 'MacOS/DesktopHost')
    run('/usr/bin/codesign', '--force', '--sign', identity, *flags, app)
    staging = output / 'Install AI Desk'
    staging.mkdir()
    shutil.copytree(app, staging / app.name, symlinks=True)
    (staging / 'Applications').symlink_to('/Applications')
    shutil.copy2(ROOT / 'START_HERE.txt', staging / '먼저 읽어주세요.txt')
    dmg = output / ('AI-Desk-' + VERSION + '-universal.dmg')
    run('/usr/bin/hdiutil', 'create', '-volname', 'AI Desk', '-srcfolder', staging,
        '-format', 'UDZO', '-ov', dmg)
    if args.identity:
        run('/usr/bin/codesign', '--sign', identity, '--timestamp', dmg)
    if args.notary_profile:
        report = json.loads(run('/usr/bin/xcrun', 'notarytool', 'submit', dmg, '--keychain-profile', args.notary_profile, '--wait', '--output-format', 'json'))
        if report.get('status') != 'Accepted':
            raise RuntimeError('Apple notarization did not accept this release: ' + str(report.get('status')))
        run('/usr/bin/xcrun', 'stapler', 'staple', app)
        run('/usr/bin/xcrun', 'stapler', 'staple', dmg)
    manifest = {'version': VERSION, 'minimum_macOS': MIN_MACOS, 'architectures': ['arm64', 'x86_64'],
                'python': '3.14.7', 'user_data_included': False,
                'developer_id_signed': bool(args.identity), 'notarized': bool(args.notary_profile),
                'sha256': hashlib.sha256(dmg.read_bytes()).hexdigest(), 'file': dmg.name}
    (output / 'release.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Built: ' + str(dmg))
    print('Developer ID signed: ' + str(bool(args.identity)) + '; notarized: ' + str(bool(args.notary_profile)))


if __name__ == '__main__':
    main()
